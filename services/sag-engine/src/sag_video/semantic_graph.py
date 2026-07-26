from __future__ import annotations

import hashlib
import json
import unicodedata
from collections import defaultdict, deque
from typing import Any, Literal
from urllib.parse import quote

from pydantic import BaseModel, Field

from .models import utc_now
from .runtime import sanitize_payload
from .spatial import SpatialEdge, SpatialEntity, SpatialProjectionService, SpatialSnapshot


SEMANTIC_SCHEMA_VERSION = "sag-semantic-graph/0.1-draft"
NEIGHBORHOOD_SCHEMA_VERSION = "sag-neighborhood/0.1-draft"
SEMANTIC_PROJECTION_VERSION = "sag-video-semantic-adapter/0.1-draft"
AUTHORITY = "sag-video"

RELATIONSHIP_MAP = {
    "contains": "contains", "consumes": "consumes", "derives_from": "derives-from",
    "overlaps": "overlaps", "blocks": "blocks", "confirms": "confirms",
    "renders_to": "renders-to", "publishes_to": "publishes-to", "observed_by": "observed-by",
}
DEPENDENCY_ORIENTATION = {
    "contains": 1, "consumes": -1, "derives-from": -1, "blocks": 1,
    "confirms": -1, "renders-to": 1, "publishes-to": 1, "observed-by": 1,
}
BLAST_RELATIONSHIPS = {
    "consumes", "derives-from", "blocks", "confirms", "renders-to", "publishes-to", "observed-by",
}
TIMELINE_KINDS = {"video", "audio", "image", "caption", "title", "effect"}
REGISTERED_ENTITY_KINDS = {
    "workspace", "project", "sequence", "semantic-layer", "asset", "track", "timeline-item",
    "job", "artifact", "actor", "receipt", "provider-connection", "delivery-profile",
    "release-approval", "publication-attempt", "aggregate",
}


def _segment(value: str) -> str:
    return quote(unicodedata.normalize("NFC", value), safe="")


def _kind(value: str) -> str:
    return value.strip().lower().replace("_", "-")


def semantic_uri(scope_kind: str, scope_id: str, entity_kind: str, entity_id: str) -> str:
    return f"sag://{AUTHORITY}/{_segment(_kind(scope_kind))}/{_segment(scope_id)}/{_segment(_kind(entity_kind))}/{_segment(entity_id)}"


def _canonical_hash(value: Any) -> str:
    encoded = json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode()
    return hashlib.sha256(encoded).hexdigest()


class SemanticRevision(BaseModel):
    authority: str
    value: str


class ProvenanceAnchor(BaseModel):
    source_uri: str
    source_revision: str | None = None
    content_hash: str | None = None
    anchor: dict[str, Any]
    derivation: Literal["declared", "derived", "observed"]
    receipt_uri: str | None = None
    evidence: dict[str, Any] = Field(default_factory=dict)


class SemanticEntity(BaseModel):
    schema_version: str = SEMANTIC_SCHEMA_VERSION
    uri: str
    local_id: str | None = None
    kind: str
    label: str
    scope_uri: str
    parent_uri: str | None = None
    revision: SemanticRevision
    state: dict[str, Any] = Field(default_factory=dict)
    eligible_action_ids: list[str] = Field(default_factory=list)
    provenance: list[ProvenanceAnchor] = Field(default_factory=list)
    extensions: dict[str, Any] = Field(default_factory=dict)


class SemanticEdge(BaseModel):
    schema_version: str = SEMANTIC_SCHEMA_VERSION
    uri: str
    source_uri: str
    target_uri: str
    relationship_kind: str
    direction: Literal["directed", "undirected"]
    revision: SemanticRevision
    state: dict[str, Any] = Field(default_factory=dict)
    provenance: list[ProvenanceAnchor] = Field(default_factory=list)
    extensions: dict[str, Any] = Field(default_factory=dict)


class SemanticTruncation(BaseModel):
    truncated: bool = False
    omitted_entities: int = 0
    omitted_edges: int = 0


class SemanticGraphEnvelope(BaseModel):
    schema_version: str = SEMANTIC_SCHEMA_VERSION
    scope_uri: str
    canonical_revision: SemanticRevision
    projection_kind: Literal["authoritative", "spatial", "retrieval", "context", "physics"] = "spatial"
    projection_version: str = SEMANTIC_PROJECTION_VERSION
    projection_hash: str
    entities: list[SemanticEntity]
    edges: list[SemanticEdge]
    focus_uris: list[str] = Field(default_factory=list)
    truncation: SemanticTruncation = Field(default_factory=SemanticTruncation)
    generated_at: str = Field(default_factory=utc_now)


class StructuralNeighborhoodRequest(BaseModel):
    schema_version: Literal["sag-neighborhood/0.1-draft"] = NEIGHBORHOOD_SCHEMA_VERSION
    scope_uri: str
    seed_uris: list[str] = Field(min_length=1, max_length=32)
    mode: Literal["adjacent", "upstream", "downstream", "blast-radius"] = "adjacent"
    relationship_kinds: list[str] = Field(default_factory=list, max_length=32)
    max_hops: int = Field(default=2, ge=0, le=6)
    entity_limit: int = Field(default=200, ge=1, le=1000)
    edge_limit: int = Field(default=400, ge=0, le=2000)
    at_revision: SemanticRevision | None = None
    include_provenance: bool = True


class NeighborhoodHit(BaseModel):
    uri: str
    distance: int
    paths: list[list[str]] = Field(default_factory=list)
    evidence: dict[str, Any] = Field(default_factory=dict)


class StructuralNeighborhoodResponse(BaseModel):
    schema_version: str = NEIGHBORHOOD_SCHEMA_VERSION
    request_hash: str
    scope_uri: str
    canonical_revision: SemanticRevision
    entities: list[SemanticEntity] = Field(default_factory=list)
    edges: list[SemanticEdge] = Field(default_factory=list)
    hits: list[NeighborhoodHit] = Field(default_factory=list)
    focus_uris: list[str] = Field(default_factory=list)
    truncation: SemanticTruncation = Field(default_factory=SemanticTruncation)
    reset_required: bool = False
    reset_reason: str | None = None
    receipt: dict[str, Any] | None = None


def semantic_schemas() -> dict[str, Any]:
    return {
        model.__name__: model.model_json_schema()
        for model in (
            ProvenanceAnchor, SemanticEntity, SemanticEdge, SemanticGraphEnvelope,
            StructuralNeighborhoodRequest, StructuralNeighborhoodResponse,
        )
    }


class SemanticGraphAdapter:
    """Provider-neutral X1 draft projection over the existing authoritative spatial graph."""

    def __init__(self, store: Any, spatial: SpatialProjectionService):
        self.store = store
        self.spatial = spatial

    @staticmethod
    def _entity_kind(entity: SpatialEntity) -> str:
        value = "timeline-item" if entity.kind in TIMELINE_KINDS else _kind(entity.kind)
        if value not in REGISTERED_ENTITY_KINDS:
            raise ValueError(f"unregistered semantic entity kind: {value}")
        return value

    @staticmethod
    def _scope_uri(snapshot: SpatialSnapshot) -> str:
        return semantic_uri("project", snapshot.project_id, "project", snapshot.project_id)

    def _entity_uri(self, snapshot: SpatialSnapshot, entity: SpatialEntity) -> str:
        kind = self._entity_kind(entity)
        if kind == "workspace":
            workspace_id = entity.id.removeprefix("workspace:")
            return semantic_uri("workspace", workspace_id, "workspace", workspace_id)
        return semantic_uri("project", snapshot.project_id, kind, entity.id)

    @staticmethod
    def _edge_uri(scope_id: str, relationship: str, source_uri: str, target_uri: str) -> str:
        digest = hashlib.sha256(f"{relationship}\0{source_uri}\0{target_uri}\0".encode()).hexdigest()[:32]
        return semantic_uri("project", scope_id, "edge", digest)

    def _adapt(self, snapshot: SpatialSnapshot) -> SemanticGraphEnvelope:
        uri_by_id = {entity.id: self._entity_uri(snapshot, entity) for entity in snapshot.entities}
        scope_uri = self._scope_uri(snapshot)
        revision = SemanticRevision(authority=AUTHORITY, value=str(snapshot.canonical_revision))
        source_hash = f"sha256:{snapshot.projection_hash}"
        entities: list[SemanticEntity] = []
        for entity in snapshot.entities:
            uri = uri_by_id[entity.id]
            spatial_extension = {
                "semantic_layer": entity.semantic_layer,
                "position": entity.position.model_dump(mode="json"),
                "bounds": entity.bounds.model_dump(mode="json"),
                "local_kind": entity.kind,
                "metadata": sanitize_payload(entity.metadata),
            }
            entities.append(SemanticEntity(
                uri=uri, local_id=entity.id, kind=self._entity_kind(entity), label=entity.label,
                scope_uri=scope_uri if entity.kind != "workspace" else uri,
                parent_uri=uri_by_id.get(entity.parent_id) if entity.parent_id else None,
                revision=SemanticRevision(authority=AUTHORITY, value=str(entity.revision)),
                state=sanitize_payload(entity.state), eligible_action_ids=sorted(entity.eligible_action_ids),
                provenance=[ProvenanceAnchor(
                    source_uri=uri, source_revision=str(entity.revision), content_hash=source_hash,
                    anchor={"kind": "entity", "value": {"local_id": entity.id}}, derivation="derived",
                    receipt_uri=uri if entity.kind == "receipt" else None,
                )],
                extensions={"sag.video.spatial": spatial_extension},
            ))
        edges: list[SemanticEdge] = []
        for edge in snapshot.edges:
            if edge.source not in uri_by_id or edge.target not in uri_by_id:
                continue
            relationship = RELATIONSHIP_MAP[edge.relationship_kind]
            source_uri, target_uri = uri_by_id[edge.source], uri_by_id[edge.target]
            edge_uri = self._edge_uri(snapshot.project_id, relationship, source_uri, target_uri)
            edges.append(SemanticEdge(
                uri=edge_uri, source_uri=source_uri, target_uri=target_uri,
                relationship_kind=relationship, direction=edge.direction, revision=revision,
                state=sanitize_payload(edge.state),
                provenance=[ProvenanceAnchor(
                    source_uri=scope_uri, source_revision=str(snapshot.canonical_revision), content_hash=source_hash,
                    anchor={"kind": "entity", "value": {"source": edge.source, "target": edge.target}},
                    derivation="derived",
                )],
                extensions={"sag.video.spatial": {"local_edge_id": edge.id}},
            ))
        entities.sort(key=lambda entry: entry.uri)
        edges.sort(key=lambda entry: entry.uri)
        focus_uris = sorted(uri_by_id[identity] for identity in snapshot.focus if identity in uri_by_id)
        body = {
            "schema_version": SEMANTIC_SCHEMA_VERSION, "scope_uri": scope_uri,
            "canonical_revision": revision.model_dump(mode="json"), "projection_kind": "spatial",
            "projection_version": SEMANTIC_PROJECTION_VERSION,
            "entities": [entry.model_dump(mode="json") for entry in entities],
            "edges": [entry.model_dump(mode="json") for entry in edges], "focus_uris": focus_uris,
            "truncation": {
                "truncated": snapshot.truncation.truncated,
                "omitted_entities": snapshot.truncation.omitted_entities,
                "omitted_edges": snapshot.truncation.omitted_edges,
            },
        }
        return SemanticGraphEnvelope(
            **body, projection_hash=_canonical_hash(body), generated_at=snapshot.generated_at,
        )

    def graph(self, project_id: str, *, revision: int | None = None) -> SemanticGraphEnvelope:
        project = self.store.get_project(project_id)
        if revision is not None and revision != project.revision:
            # Runtime/governance rows do not all have historical versions, so a mixed-time graph
            # would be unprovable even when the canonical timeline revision is retained.
            raise ValueError("semantic graph revision continuity cannot be proven")
        snapshot = self.spatial._snapshot_for_project(project, depth="system", entity_limit=1000, edge_limit=2000)
        return self._adapt(snapshot)

    def neighborhood(self, project_id: str, request: StructuralNeighborhoodRequest) -> StructuralNeighborhoodResponse:
        request_body = request.model_dump(mode="json")
        request_hash = _canonical_hash(request_body)
        requested_revision = None
        if request.at_revision:
            if request.at_revision.authority != AUTHORITY:
                current = self.graph(project_id)
                return self._reset(request, request_hash, current, "incompatible revision authority")
            try:
                requested_revision = int(request.at_revision.value)
            except ValueError:
                current = self.graph(project_id)
                return self._reset(request, request_hash, current, "invalid revision value")
        try:
            graph = self.graph(project_id, revision=requested_revision)
        except (KeyError, ValueError):
            current = self.graph(project_id)
            return self._reset(request, request_hash, current, "revision is not retained")
        if request.scope_uri != graph.scope_uri:
            return self._reset(request, request_hash, graph, "scope does not match project")
        entity_by_uri = {entity.uri: entity for entity in graph.entities}
        if any(seed not in entity_by_uri for seed in request.seed_uris):
            return self._reset(request, request_hash, graph, "one or more seed URIs are unknown")
        registered_relationships = set(RELATIONSHIP_MAP.values())
        if set(request.relationship_kinds) - registered_relationships:
            return self._reset(request, request_hash, graph, "one or more relationship kinds are unregistered")
        allowed = set(request.relationship_kinds) if request.relationship_kinds else registered_relationships
        edges = [edge for edge in graph.edges if edge.relationship_kind in allowed]
        adjacency: dict[str, list[tuple[str, SemanticEdge]]] = defaultdict(list)
        for edge in edges:
            if request.mode == "adjacent":
                adjacency[edge.source_uri].append((edge.target_uri, edge))
                adjacency[edge.target_uri].append((edge.source_uri, edge))
                continue
            orientation = DEPENDENCY_ORIENTATION.get(edge.relationship_kind)
            if orientation is None or (request.mode == "blast-radius" and edge.relationship_kind not in BLAST_RELATIONSHIPS):
                continue
            downstream_source, downstream_target = (
                (edge.source_uri, edge.target_uri) if orientation == 1 else (edge.target_uri, edge.source_uri)
            )
            source, target = (
                (downstream_target, downstream_source) if request.mode == "upstream"
                else (downstream_source, downstream_target)
            )
            adjacency[source].append((target, edge))
        distances = {seed: 0 for seed in request.seed_uris}
        paths: dict[str, list[str]] = {seed: [] for seed in request.seed_uris}
        queue = deque(sorted(request.seed_uris))
        while queue:
            current = queue.popleft()
            if distances[current] >= request.max_hops:
                continue
            candidates = sorted(
                adjacency[current], key=lambda entry: (entry[1].relationship_kind, entry[1].uri, entry[0]),
            )
            for neighbor, edge in candidates:
                if neighbor in distances:
                    continue
                distances[neighbor] = distances[current] + 1
                paths[neighbor] = [*paths[current], edge.uri]
                queue.append(neighbor)
        ordered_uris = sorted(distances, key=lambda uri: (distances[uri], uri))
        kept_uris = ordered_uris[:request.entity_limit]
        kept_set = set(kept_uris)
        eligible_edges = sorted(
            (edge for edge in edges if edge.source_uri in kept_set and edge.target_uri in kept_set),
            key=lambda entry: entry.uri,
        )
        kept_edges = eligible_edges[:request.edge_limit]
        selected_entities = [entity_by_uri[uri] for uri in kept_uris]
        if not request.include_provenance:
            selected_entities = [entry.model_copy(update={"provenance": []}) for entry in selected_entities]
            kept_edges = [entry.model_copy(update={"provenance": []}) for entry in kept_edges]
        return StructuralNeighborhoodResponse(
            request_hash=request_hash, scope_uri=graph.scope_uri, canonical_revision=graph.canonical_revision,
            entities=selected_entities, edges=kept_edges,
            hits=[NeighborhoodHit(uri=uri, distance=distances[uri], paths=[paths[uri]] if paths[uri] else []) for uri in kept_uris],
            focus_uris=sorted(request.seed_uris),
            truncation=SemanticTruncation(
                truncated=len(ordered_uris) > len(kept_uris) or len(eligible_edges) > len(kept_edges),
                omitted_entities=max(0, len(ordered_uris) - len(kept_uris)),
                omitted_edges=max(0, len(eligible_edges) - len(kept_edges)),
            ),
        )

    @staticmethod
    def _reset(
        request: StructuralNeighborhoodRequest, request_hash: str,
        graph: SemanticGraphEnvelope, reason: str,
    ) -> StructuralNeighborhoodResponse:
        return StructuralNeighborhoodResponse(
            request_hash=request_hash, scope_uri=request.scope_uri,
            canonical_revision=graph.canonical_revision, focus_uris=sorted(request.seed_uris),
            reset_required=True, reset_reason=reason,
        )
