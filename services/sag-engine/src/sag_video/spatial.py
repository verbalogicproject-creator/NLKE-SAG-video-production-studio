from __future__ import annotations

import hashlib
import json
import os
from collections import defaultdict, deque
from datetime import datetime, timedelta, timezone
from typing import Any, Literal
from uuid import uuid4

from pydantic import BaseModel, ConfigDict, Field

from .contracts import APPLICATION_ACTIONS
from .models import Project, ReceiptStatus, TICKS_PER_SECOND, utc_now
from .runtime import RuntimeEventService, sanitize_payload


PROJECTION_VERSION = "sag-spatial-1"
SPATIAL_SCHEMA_VERSION = "1.0"
SPATIAL_FRAME_SCHEMA_VERSION = "sag-spatial-frame/1.0"
SemanticLayer = Literal["workspace", "project", "sequence", "creation", "composition", "runtime", "governance", "delivery"]
RelationshipKind = Literal[
    "contains", "consumes", "derives_from", "overlaps", "blocks", "confirms",
    "renders_to", "publishes_to", "observed_by",
]


class SpatialPosition(BaseModel):
    x: float
    y: float
    z: float


class SpatialBounds(BaseModel):
    width: float = Field(gt=0)
    height: float = Field(gt=0)
    depth: float = Field(gt=0)


class SpatialEntity(BaseModel):
    id: str
    uri: str | None = None
    kind: str
    label: str
    parent_id: str | None = None
    semantic_layer: SemanticLayer
    revision: int
    state: dict[str, Any] = Field(default_factory=dict)
    eligible_action_ids: list[str] = Field(default_factory=list)
    metadata: dict[str, Any] = Field(default_factory=dict)
    position: SpatialPosition
    bounds: SpatialBounds = Field(default_factory=lambda: SpatialBounds(width=4, height=2, depth=1))
    aggregate_count: int | None = None


class SpatialEdge(BaseModel):
    id: str
    source: str
    target: str
    relationship_kind: RelationshipKind
    direction: Literal["directed", "undirected"] = "directed"
    state: dict[str, Any] = Field(default_factory=dict)


class SpatialTruncation(BaseModel):
    truncated: bool = False
    omitted_entities: int = 0
    omitted_edges: int = 0
    aggregates: list[str] = Field(default_factory=list)


class SpatialSnapshot(BaseModel):
    workspace_id: str
    project_id: str
    sequence_id: str
    schema_version: str = SPATIAL_SCHEMA_VERSION
    projection_version: str = PROJECTION_VERSION
    canonical_revision: int
    runtime_cursor: int
    projection_hash: str
    entities: list[SpatialEntity]
    edges: list[SpatialEdge]
    focus: list[str] = Field(default_factory=list)
    truncation: SpatialTruncation = Field(default_factory=SpatialTruncation)
    generated_at: str = Field(default_factory=utc_now)


class SpatialDelta(BaseModel):
    previous_cursor: int
    current_cursor: int
    previous_revision: int
    current_revision: int
    previous_projection_hash: str | None = None
    current_projection_hash: str | None = None
    entity_upserts: list[SpatialEntity] = Field(default_factory=list)
    entity_removals: list[str] = Field(default_factory=list)
    edge_upserts: list[SpatialEdge] = Field(default_factory=list)
    edge_removals: list[str] = Field(default_factory=list)
    focus: list[str] = Field(default_factory=list)
    snapshot_required: bool = False


class ViewportState(BaseModel):
    active_depth: Literal["edit", "context", "system"] = "edit"
    camera: dict[str, float] = Field(default_factory=dict)
    filters: list[str] = Field(default_factory=list)
    collapsed_groups: list[str] = Field(default_factory=list)
    selected_ids: list[str] = Field(default_factory=list)


class NormalizedRect(BaseModel):
    x: float = Field(ge=0, le=1)
    y: float = Field(ge=0, le=1)
    width: float = Field(gt=0, le=1)
    height: float = Field(gt=0, le=1)


class ViewportMetrics(BaseModel):
    width_css_px: int = Field(ge=1, le=16384)
    height_css_px: int = Field(ge=1, le=16384)
    device_pixel_ratio: float = Field(default=1, ge=0.25, le=8)
    scroll_x_css_px: float = Field(default=0, ge=0, le=10_000_000)
    scroll_y_css_px: float = Field(default=0, ge=0, le=10_000_000)


class AdaptiveGrid(BaseModel):
    coordinate_space: Literal["normalized_0_1"] = "normalized_0_1"
    origin: Literal["top_left"] = "top_left"
    columns: int = Field(ge=4, le=16)
    rows: int = Field(ge=6, le=24)
    target_cell_css_px: int = Field(default=80, ge=44, le=240)
    cell_width_css_px: float = Field(ge=44)
    cell_height_css_px: float = Field(ge=44)


class SpatialRegionBinding(BaseModel):
    model_config = ConfigDict(extra="forbid")

    binding_id: str = Field(min_length=8, max_length=160)
    entity_id: str = Field(min_length=1, max_length=200)
    role: str = Field(default="region", min_length=1, max_length=80)
    label: str = Field(default="", max_length=240)
    rect: NormalizedRect
    cells: list[str] = Field(default_factory=list, max_length=64)
    visible: bool = True
    occluded: bool = False
    eligible_action_ids: list[str] = Field(default_factory=list, max_length=24)
    source: Literal["dom", "accessibility", "canvas", "manual", "gemini"] = "dom"
    confidence: float = Field(default=1, ge=0, le=1)
    protected: bool = False
    evidence_refs: list[str] = Field(default_factory=list, max_length=16)


class SpatialFrameRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    frame_id: str = Field(pattern=r"^frame_[A-Za-z0-9_-]{8,120}$")
    schema_version: Literal["sag-spatial-frame/1.0"] = SPATIAL_FRAME_SCHEMA_VERSION
    canonical_revision: int = Field(ge=1)
    projection_hash: str = Field(min_length=16, max_length=128)
    runtime_cursor: int = Field(default=0, ge=0)
    active_depth: Literal["edit", "context", "system"] = "edit"
    viewport: ViewportMetrics
    grid: AdaptiveGrid | None = None
    bindings: list[SpatialRegionBinding] = Field(default_factory=list, max_length=64)
    truncated_bindings: int = Field(default=0, ge=0)
    media_sha256: str | None = Field(default=None, pattern=r"^[a-f0-9]{64}$")
    redaction_state: Literal["metadata_only", "redacted", "not_applicable"] = "metadata_only"
    session_id: str | None = Field(default=None, max_length=120)


class SpatialFrame(SpatialFrameRequest):
    workspace_id: str
    project_id: str
    sequence_id: str
    generated_at: str = Field(default_factory=utc_now)
    expires_at: str


class SpatialRegionResolveRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    entity_id: str | None = Field(default=None, max_length=200)
    cell: str | None = Field(default=None, pattern=r"^[A-P](?:[1-9]|1[0-9]|2[0-4])$")
    point: dict[Literal["x", "y"], float] | None = None
    minimum_confidence: float = Field(default=0.5, ge=0, le=1)
    include_occluded: bool = False


class ActionRoute(BaseModel):
    model_config = ConfigDict(extra="forbid")

    kind: Literal["observer_only", "semantic_handler", "canonical_command", "coordinate_fallback"]
    action: str = Field(min_length=1, max_length=160)
    target_id: str | None = Field(default=None, max_length=200)
    binding_id: str | None = Field(default=None, max_length=160)
    confidence: float = Field(default=1, ge=0, le=1)
    transformations: list[dict[str, Any]] = Field(default_factory=list, max_length=16)


class SpatialObservationRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    observation_id: str = Field(pattern=r"^observation_[A-Za-z0-9_-]{8,120}$")
    before_frame_id: str = Field(pattern=r"^frame_[A-Za-z0-9_-]{8,120}$")
    after_frame_id: str = Field(pattern=r"^frame_[A-Za-z0-9_-]{8,120}$")
    expected_revision: int = Field(ge=1)
    expected_projection_hash: str = Field(min_length=16, max_length=128)
    directive_receipt_id: str | None = Field(default=None, max_length=160)
    trace_id: str | None = Field(default=None, max_length=120)
    changed_entity_ids: list[str] = Field(default_factory=list, max_length=64)
    changed_cells: list[str] = Field(default_factory=list, max_length=128)
    route: ActionRoute
    findings: list[dict[str, Any]] = Field(default_factory=list, max_length=20)
    success: bool = True


def adaptive_grid(viewport: ViewportMetrics, *, target_cell_css_px: int = 80) -> AdaptiveGrid:
    columns = max(4, min(16, round(viewport.width_css_px / target_cell_css_px)))
    rows = max(6, min(24, round(viewport.height_css_px / target_cell_css_px)))
    while columns > 4 and viewport.width_css_px / columns < 44:
        columns -= 1
    while rows > 6 and viewport.height_css_px / rows < 44:
        rows -= 1
    return AdaptiveGrid(
        columns=columns, rows=rows, target_cell_css_px=target_cell_css_px,
        cell_width_css_px=viewport.width_css_px / columns,
        cell_height_css_px=viewport.height_css_px / rows,
    )


class SpatialDirectiveRequest(BaseModel):
    action: str
    target_ids: list[str] = Field(default_factory=list, max_length=24)
    expected_revision: int = Field(ge=1)
    expected_projection_hash: str = Field(min_length=16, max_length=128)
    trace_id: str | None = Field(default=None, max_length=120)
    expires_in_seconds: int = Field(default=30, ge=5, le=120)
    intended_observed_effect: dict[str, Any] = Field(default_factory=dict)
    expected_frame_id: str | None = Field(default=None, pattern=r"^frame_[A-Za-z0-9_-]{8,120}$")
    binding_id: str | None = Field(default=None, max_length=160)
    preferred_interaction_route: Literal["semantic_handler", "coordinate_fallback"] = "semantic_handler"


class SpatialDirective(BaseModel):
    action: str
    target_ids: list[str]
    expected_revision: int
    expected_projection_hash: str
    trace_id: str
    receipt_id: str
    expires_at: str
    intended_observed_effect: dict[str, Any]
    expected_frame_id: str | None = None
    binding_id: str | None = None
    preferred_interaction_route: Literal["semantic_handler", "coordinate_fallback"] = "semantic_handler"


class SpatialDirectiveAck(BaseModel):
    consumer_id: str = Field(min_length=1, max_length=120)
    projection_hash: str = Field(min_length=16, max_length=128)
    observed_target_ids: list[str] = Field(default_factory=list, max_length=24)
    active_depth: Literal["edit", "context", "system"]
    renderer_mode: Literal["dom_tree", "webgl", "webgl_lod", "unavailable"]
    findings: list[dict[str, Any]] = Field(default_factory=list, max_length=20)
    success: bool = True
    before_frame_id: str | None = Field(default=None, pattern=r"^frame_[A-Za-z0-9_-]{8,120}$")
    after_frame_id: str | None = Field(default=None, pattern=r"^frame_[A-Za-z0-9_-]{8,120}$")
    changed_entity_ids: list[str] = Field(default_factory=list, max_length=64)
    changed_cells: list[str] = Field(default_factory=list, max_length=128)
    action_route: ActionRoute | None = None


def spatial_schemas() -> dict[str, Any]:
    return {
        "SpatialEntity": SpatialEntity.model_json_schema(),
        "SpatialEdge": SpatialEdge.model_json_schema(),
        "SpatialSnapshot": SpatialSnapshot.model_json_schema(),
        "SpatialDelta": SpatialDelta.model_json_schema(),
        "ViewportState": ViewportState.model_json_schema(),
        "AdaptiveGrid": AdaptiveGrid.model_json_schema(),
        "SpatialRegionBinding": SpatialRegionBinding.model_json_schema(),
        "SpatialFrame": SpatialFrame.model_json_schema(),
        "SpatialObservationRequest": SpatialObservationRequest.model_json_schema(),
        "ActionRoute": ActionRoute.model_json_schema(),
        "SpatialDirective": SpatialDirective.model_json_schema(),
    }


VIEWPORT_AFFORDANCES: dict[str, set[str]] = {
    "viewport:studio": {"spatial.reset_view"},
    "viewport:studio-header": {"spatial.set_depth"},
    "viewport:studio-depth-edit": {"spatial.set_depth"},
    "viewport:studio-depth-context": {"spatial.set_depth"},
    "viewport:studio-depth-system": {"spatial.set_depth"},
    "viewport:media": {"spatial.frame_entity"},
    "viewport:monitor": {"spatial.frame_entity"},
    "viewport:timeline": {"spatial.frame_entity"},
    "viewport:inspector": {"spatial.frame_entity"},
    "viewport:director": {"spatial.frame_entity"},
    "viewport:governance": {"spatial.frame_entity"},
    "viewport:spatial-workspace": {"spatial.reset_view"},
}

SENSITIVE_COORDINATE_ACTION_PREFIXES = (
    "connection.", "oauth.", "provider.", "release.", "publish.", "publication.",
    "repo_to_video.generate", "generative.", "timeline.delete", "asset.delete",
)


class SpatialFrameService:
    """Ephemeral binding plane over the canonical spatial projection."""

    def __init__(self, store: Any, projection: "SpatialProjectionService", runtime: RuntimeEventService):
        self.store = store
        self.projection = projection
        self.runtime = runtime

    @staticmethod
    def _cell_is_valid(cell: str, grid: AdaptiveGrid) -> bool:
        if len(cell) < 2:
            return False
        column = ord(cell[0]) - ord("A")
        try:
            row = int(cell[1:]) - 1
        except ValueError:
            return False
        return 0 <= column < grid.columns and 0 <= row < grid.rows

    def declare(self, project_id: str, request: SpatialFrameRequest, *, actor: str) -> SpatialFrame:
        snapshot = self.projection.snapshot(project_id, depth="system")
        if snapshot.canonical_revision != request.canonical_revision:
            from .models import StaleRevisionError
            raise StaleRevisionError(request.canonical_revision, snapshot.canonical_revision)
        if snapshot.projection_hash != request.projection_hash:
            raise ValueError("stale spatial projection hash")
        computed_grid = adaptive_grid(request.viewport)
        if request.grid is not None and (
            request.grid.columns != computed_grid.columns or request.grid.rows != computed_grid.rows
        ):
            raise ValueError("adaptive grid does not match the declared viewport")
        known = {entity.id: set(entity.eligible_action_ids) for entity in snapshot.entities}
        binding_ids: set[str] = set()
        for binding in request.bindings:
            if binding.binding_id in binding_ids:
                raise ValueError("duplicate spatial binding id")
            binding_ids.add(binding.binding_id)
            if binding.rect.x + binding.rect.width > 1.000001 or binding.rect.y + binding.rect.height > 1.000001:
                raise ValueError("spatial binding exceeds normalized viewport bounds")
            allowed = known.get(binding.entity_id)
            if allowed is None:
                allowed = VIEWPORT_AFFORDANCES.get(binding.entity_id)
            if allowed is None:
                raise ValueError(f"unknown spatial binding entity: {binding.entity_id}")
            if any(action not in allowed for action in binding.eligible_action_ids):
                raise ValueError("spatial binding claims an ineligible action")
            if any(not self._cell_is_valid(cell, computed_grid) for cell in binding.cells):
                raise ValueError("spatial binding contains a cell outside the adaptive grid")
            if binding.source == "gemini":
                if os.getenv("SAG_GEMINI_OBSERVER_ENABLED", "").lower() not in {"1", "true", "yes"}:
                    raise ValueError("Gemini spatial observation is disabled")
                if request.redaction_state != "redacted":
                    raise ValueError("Gemini bindings require an explicitly redacted frame")
        body = request.model_copy(update={"grid": computed_grid}).model_dump(mode="json")
        if len(json.dumps(body, sort_keys=True, separators=(",", ":")).encode()) > 15_000:
            raise ValueError("spatial frame declaration exceeds the bounded runtime payload")
        project = self.store.get_project(project_id)
        now = datetime.now(timezone.utc)
        frame = SpatialFrame(
            **body, workspace_id=str(project.workspace_id or project.id), project_id=project.id,
            sequence_id=project.id, generated_at=now.isoformat(),
            expires_at=(now + timedelta(days=7)).isoformat(),
        )
        self.runtime.emit(
            workspace_id=frame.workspace_id, project_id=project.id, sequence_id=project.id,
            revision=project.revision, actor=actor, kind="spatial.frame.declared",
            session_id=frame.frame_id, payload={"frame": frame.model_dump(mode="json")},
        )
        if any(binding.source != "dom" for binding in frame.bindings):
            self.runtime.emit(
                workspace_id=frame.workspace_id, project_id=project.id, sequence_id=project.id,
                revision=project.revision, actor=actor, kind="spatial.bindings.reconciled",
                session_id=frame.frame_id, payload={
                    "frame_id": frame.frame_id,
                    "bindings": [
                        {
                            "binding_id": binding.binding_id, "entity_id": binding.entity_id,
                            "source": binding.source, "confidence": binding.confidence,
                        }
                        for binding in frame.bindings if binding.source != "dom"
                    ],
                },
            )
        return frame

    @staticmethod
    def _frame_from_event(event: dict[str, Any] | None) -> SpatialFrame:
        if event is None or not isinstance(event.get("payload", {}).get("frame"), dict):
            raise KeyError("spatial frame not found")
        return SpatialFrame.model_validate(event["payload"]["frame"])

    def current(self, project_id: str) -> SpatialFrame:
        return self._frame_from_event(self.store.latest_runtime_event(project_id, "spatial.frame.declared"))

    def get(self, project_id: str, frame_id: str) -> SpatialFrame:
        return self._frame_from_event(self.store.find_runtime_event(
            project_id, "spatial.frame.declared", frame_id,
        ))

    def resolve(self, project_id: str, frame_id: str, request: SpatialRegionResolveRequest) -> dict[str, Any]:
        frame = self.get(project_id, frame_id)
        if sum(value is not None for value in (request.entity_id, request.cell, request.point)) != 1:
            raise ValueError("resolve exactly one entity, cell, or point")
        point = request.point
        if point is not None and (
            set(point) != {"x", "y"} or not 0 <= point["x"] <= 1 or not 0 <= point["y"] <= 1
        ):
            raise ValueError("resolve point must use normalized x and y")
        matches = []
        for binding in frame.bindings:
            if binding.confidence < request.minimum_confidence or (binding.occluded and not request.include_occluded):
                continue
            selected = request.entity_id == binding.entity_id if request.entity_id is not None else False
            selected = selected or (request.cell is not None and request.cell in binding.cells)
            selected = selected or bool(point and (
                binding.rect.x <= point["x"] <= binding.rect.x + binding.rect.width
                and binding.rect.y <= point["y"] <= binding.rect.y + binding.rect.height
            ))
            if selected:
                matches.append(binding)
        matches.sort(key=lambda entry: (-entry.confidence, entry.rect.width * entry.rect.height, entry.entity_id))
        return {
            "frame_id": frame.frame_id, "canonical_revision": frame.canonical_revision,
            "projection_hash": frame.projection_hash,
            "matches": [entry.model_dump(mode="json") for entry in matches],
        }

    def observe(self, project_id: str, request: SpatialObservationRequest, *, actor: str) -> dict[str, Any]:
        before = self.get(project_id, request.before_frame_id)
        after = self.get(project_id, request.after_frame_id)
        if before.canonical_revision != request.expected_revision or after.canonical_revision != request.expected_revision:
            raise ValueError("spatial observation frame revision mismatch")
        if before.projection_hash != request.expected_projection_hash:
            raise ValueError("spatial observation before-frame projection mismatch")
        if request.route.kind == "coordinate_fallback":
            if request.route.action.startswith(SENSITIVE_COORDINATE_ACTION_PREFIXES):
                raise ValueError("sensitive actions cannot use coordinate fallback")
            if os.getenv("SAG_COORDINATE_FALLBACK_ENABLED", "").lower() not in {"1", "true", "yes"}:
                raise ValueError("coordinate fallback is disabled")
            if request.route.confidence < 0.95:
                raise ValueError("coordinate fallback requires confidence of at least 0.95")
        project = self.store.get_project(project_id)
        payload = {"observation": request.model_dump(mode="json")}
        event = self.runtime.emit(
            workspace_id=str(project.workspace_id or project.id), project_id=project.id,
            sequence_id=project.id, revision=project.revision, actor=actor,
            kind="spatial.effect.observed", trace_id=request.trace_id,
            session_id=request.observation_id, payload=payload,
        )
        return {"observation": request.model_dump(mode="json"), "event": event.model_dump(mode="json")}


class SpatialProjectionService:
    LAYER_Z = {
        "workspace": -36, "project": -30, "sequence": -24, "creation": 0,
        "composition": 24, "runtime": 48, "governance": 72, "delivery": 96,
    }

    def __init__(self, store: Any):
        self.store = store

    @staticmethod
    def _edge(source: str, target: str, kind: RelationshipKind, *, state: dict[str, Any] | None = None) -> SpatialEdge:
        identity = f"{kind}:{source}:{target}"
        return SpatialEdge(
            id=f"edge:{hashlib.sha256(identity.encode()).hexdigest()[:20]}",
            source=source, target=target, relationship_kind=kind, state=state or {},
        )

    @classmethod
    def _entity(
        cls, *, identity: str, kind: str, label: str, parent_id: str | None,
        layer: SemanticLayer, revision: int, x: float, y: float,
        state: dict[str, Any] | None = None, metadata: dict[str, Any] | None = None,
        actions: list[str] | None = None, width: float = 4,
    ) -> SpatialEntity:
        return SpatialEntity(
            id=identity, uri=f"sag://{kind}/{identity}", kind=kind, label=label,
            parent_id=parent_id, semantic_layer=layer, revision=revision,
            state=sanitize_payload(state or {}), metadata=sanitize_payload(metadata or {}),
            eligible_action_ids=sorted(actions or []),
            position=SpatialPosition(x=round(x, 6), y=round(y, 6), z=float(cls.LAYER_Z[layer])),
            bounds=SpatialBounds(width=max(2, round(width, 6)), height=2, depth=1),
        )

    def _full_graph(self, project: Project) -> tuple[list[SpatialEntity], list[SpatialEdge]]:
        workspace_id = project.workspace_id or project.id
        root = f"workspace:{workspace_id}"
        project_node = f"project:{project.id}"
        sequence = f"sequence:{project.id}"
        entities = [
            self._entity(identity=root, kind="workspace", label=workspace_id, parent_id=None, layer="workspace", revision=project.revision, x=0, y=0),
            self._entity(identity=project_node, kind="project", label=project.name, parent_id=root, layer="project", revision=project.revision, x=0, y=0),
            self._entity(identity=sequence, kind="sequence", label=project.name, parent_id=project_node, layer="sequence", revision=project.revision, x=0, y=0),
        ]
        edges = [self._edge(root, project_node, "contains"), self._edge(project_node, sequence, "contains")]
        layer_nodes: dict[str, str] = {}
        for order, layer in enumerate(("creation", "composition", "runtime", "governance", "delivery")):
            identity = f"layer:{layer}:{project.id}"
            layer_nodes[layer] = identity
            entities.append(self._entity(
                identity=identity, kind="semantic_layer", label=layer.title(), parent_id=sequence,
                layer=layer, revision=project.revision, x=0, y=order * 3,
            ))
            edges.append(self._edge(sequence, identity, "contains"))

        for index, asset in enumerate(sorted(project.assets, key=lambda entry: entry.id)):
            duration = float((asset.duration_ticks or TICKS_PER_SECOND) / TICKS_PER_SECOND)
            x = duration / 2
            entity = self._entity(
                identity=asset.id, kind="asset", label=asset.name,
                parent_id=layer_nodes["creation"], layer="creation", revision=project.revision,
                x=x, y=index * 3, width=max(3, duration),
                state={"intake_status": asset.intake_status},
                metadata={"asset_kind": asset.kind, "source_kind": asset.source_kind, "duration_ticks": asset.duration_ticks},
                actions=["timeline.insert_asset"] if asset.intake_status == "observed_valid" else [],
            )
            entities.append(entity)
            edges.append(self._edge(layer_nodes["creation"], asset.id, "contains"))
            if asset.parent_asset_id:
                edges.append(self._edge(asset.id, asset.parent_asset_id, "derives_from"))

        for track_index, track in enumerate(project.tracks):
            track_id = track.id
            entities.append(self._entity(
                identity=track_id, kind="track", label=track.name,
                parent_id=layer_nodes["composition"], layer="composition", revision=project.revision,
                x=project.duration_ticks / TICKS_PER_SECOND / 2, y=track_index * 6,
                metadata={"track_kind": track.kind, "item_count": len(track.items)},
                width=max(4, project.duration_ticks / TICKS_PER_SECOND),
            ))
            edges.append(self._edge(layer_nodes["composition"], track_id, "contains"))
            ordered = sorted(track.items, key=lambda entry: (entry.start_ticks, entry.id))
            for item_index, item in enumerate(ordered):
                start = item.start_ticks / TICKS_PER_SECOND
                duration = item.duration_ticks / TICKS_PER_SECOND
                item_actions = ["timeline.move_item"]
                if item.kind in {"video", "audio"}:
                    item_actions.extend(["timeline.trim_clip", "timeline.split_clip"])
                item_actions.extend(["timeline.delete_item", *sorted(name for name in APPLICATION_ACTIONS if name.startswith("spatial."))])
                entities.append(self._entity(
                    identity=item.id, kind=item.kind, label=item.name, parent_id=track_id,
                    layer="composition", revision=project.revision, x=start + duration / 2,
                    y=track_index * 6 + item_index * 0.25, width=max(2, duration),
                    state={"muted": item.muted, "selected": False},
                    metadata={
                        "track_id": track.id, "start_ticks": item.start_ticks,
                        "duration_ticks": item.duration_ticks, "asset_id": item.asset_id,
                    }, actions=item_actions,
                ))
                edges.append(self._edge(track_id, item.id, "contains"))
                if item.asset_id:
                    edges.append(self._edge(item.id, item.asset_id, "consumes"))
            for left_index, left in enumerate(ordered):
                left_end = left.start_ticks + left.duration_ticks
                for right in ordered[left_index + 1:]:
                    if right.start_ticks >= left_end:
                        break
                    edges.append(self._edge(left.id, right.id, "overlaps", state={"track_id": track.id}))

        jobs = self.store.list_jobs(project.id)
        for index, job in enumerate(sorted(jobs, key=lambda entry: entry.id)):
            entities.append(self._entity(
                identity=job.id, kind="job", label=f"{job.kind} job", parent_id=layer_nodes["runtime"],
                layer="runtime", revision=job.project_revision, x=project.duration_ticks / TICKS_PER_SECOND / 2,
                y=index * 3, state={"state": job.state, "progress": job.progress},
                metadata={"kind": job.kind, "stage": job.stage},
            ))
            edges.extend([self._edge(layer_nodes["runtime"], job.id, "contains"), self._edge(job.id, sequence, "consumes")])
            render_spec = job.frozen_spec.get("render_spec", {}) if isinstance(job.frozen_spec, dict) else {}
            for collection in ("media", "titles", "captions"):
                entries = render_spec.get(collection, []) if isinstance(render_spec, dict) else []
                for entry in entries if isinstance(entries, (list, tuple)) else []:
                    if not isinstance(entry, dict):
                        continue
                    if entry.get("item_id"):
                        edges.append(self._edge(job.id, str(entry["item_id"]), "consumes"))
                    if entry.get("asset_id"):
                        edges.append(self._edge(job.id, str(entry["asset_id"]), "consumes"))
            source_asset_id = job.frozen_spec.get("source_asset_id") if isinstance(job.frozen_spec, dict) else None
            if source_asset_id:
                edges.append(self._edge(job.id, str(source_asset_id), "consumes"))

        artifacts = self.store.list_artifacts(project.id)
        for index, artifact in enumerate(sorted(artifacts, key=lambda entry: entry.id)):
            entities.append(self._entity(
                identity=artifact.id, kind="artifact", label=artifact.kind, parent_id=layer_nodes["runtime"],
                layer="runtime", revision=project.revision, x=project.duration_ticks / TICKS_PER_SECOND,
                y=(len(jobs) + index) * 3, state={"verified": bool(artifact.sha256)},
                metadata={"kind": artifact.kind, "sha256": artifact.sha256, "byte_size": artifact.byte_size},
            ))
            edges.append(self._edge(layer_nodes["runtime"], artifact.id, "contains"))
            if artifact.job_id:
                edges.append(self._edge(artifact.job_id, artifact.id, "renders_to"))

        actors = self.store.active_actors(workspace_id)
        for index, actor in enumerate(actors):
            identity = f"actor:{hashlib.sha256((actor['actor_name'] + str(actor.get('project_id'))).encode()).hexdigest()[:16]}"
            entities.append(self._entity(
                identity=identity, kind="actor", label=actor["actor_name"], parent_id=layer_nodes["governance"],
                layer="governance", revision=project.revision, x=0, y=index * 3,
                state={"connection": "connected"}, metadata={"scopes": actor.get("scopes", [])},
            ))
            edges.append(self._edge(layer_nodes["governance"], identity, "contains"))

        receipts = self.store.list_receipts(project.id, limit=200)
        for index, receipt in enumerate(sorted(receipts, key=lambda entry: entry.id)):
            entities.append(self._entity(
                identity=receipt.id, kind="receipt", label=receipt.command, parent_id=layer_nodes["governance"],
                layer="governance", revision=receipt.project_revision,
                x=project.duration_ticks / TICKS_PER_SECOND, y=(len(actors) + index) * 2,
                state={"status": receipt.status.value},
                metadata={"command": receipt.command, "actor": receipt.actor},
            ))
            edges.append(self._edge(layer_nodes["governance"], receipt.id, "contains"))
            target_ids = receipt.payload.get("target_ids", [])
            for target_id in target_ids if isinstance(target_ids, list) else []:
                edges.append(self._edge(receipt.id, str(target_id), "confirms"))
            artifact_id = receipt.payload.get("artifact_id")
            if artifact_id:
                edges.append(self._edge(str(artifact_id), receipt.id, "observed_by"))

        connections = self.store.list_provider_connections(workspace_id)
        for index, connection in enumerate(connections):
            entities.append(self._entity(
                identity=connection["id"], kind="provider_connection",
                label=connection["display_name"], parent_id=layer_nodes["governance"],
                layer="governance", revision=project.revision,
                x=0, y=(len(actors) + len(receipts) + index) * 2,
                state={"state": connection["state"]},
                metadata={
                    "provider": connection["provider"], "purpose": connection["purpose"],
                    "scopes": connection["scopes"],
                    "secret_fingerprint": connection["secret_fingerprint"],
                }, actions=["connection.oauth"] if connection["state"] != "revoked" else [],
            ))
            edges.append(self._edge(layer_nodes["governance"], connection["id"], "contains"))

        delivery_profiles = self.store.list_delivery_profiles(project.id)
        for index, profile in enumerate(delivery_profiles):
            entities.append(self._entity(
                identity=profile["id"], kind="delivery_profile", label=profile["destination"],
                parent_id=layer_nodes["delivery"], layer="delivery", revision=project.revision,
                x=project.duration_ticks / TICKS_PER_SECOND, y=index * 3,
                state={"aspect_ratio": profile["aspect_ratio"]},
                metadata={
                    "width": profile["width"], "height": profile["height"],
                    "caption_placement": profile["caption_placement"],
                    "safe_zone_x": profile["safe_zone_x"], "safe_zone_y": profile["safe_zone_y"],
                },
            ))
            edges.append(self._edge(layer_nodes["delivery"], profile["id"], "contains"))

        artifact_by_hash = {artifact.sha256: artifact.id for artifact in artifacts if artifact.sha256}
        approvals = self.store.list_release_approvals(project.id)
        attempts = self.store.list_release_attempts(project.id)
        for index, approval in enumerate(approvals):
            entities.append(self._entity(
                identity=approval["id"], kind="release_approval", label="Release approval",
                parent_id=layer_nodes["delivery"], layer="delivery", revision=approval["project_revision"],
                x=project.duration_ticks / TICKS_PER_SECOND, y=(len(delivery_profiles) + index) * 3,
                state={"state": approval["state"]},
                metadata={
                    "bundle_hash": approval["bundle_hash"], "destinations": approval["destinations"],
                    "expires_at": approval["expires_at"], "approved_by": approval["approved_by"],
                }, actions=["publish.dispatch_approved"] if approval["state"] == "active" else [],
            ))
            edges.append(self._edge(layer_nodes["delivery"], approval["id"], "contains"))
            for artifact_hash in approval["artifact_hashes"]:
                if artifact_hash in artifact_by_hash:
                    edges.append(self._edge(approval["id"], artifact_by_hash[artifact_hash], "confirms"))
        for index, attempt in enumerate(attempts):
            entities.append(self._entity(
                identity=attempt["id"], kind="publication_attempt", label=attempt["destination"],
                parent_id=layer_nodes["delivery"], layer="delivery", revision=project.revision,
                x=project.duration_ticks / TICKS_PER_SECOND,
                y=(len(delivery_profiles) + len(approvals) + index) * 3,
                state={"state": attempt["state"], "attempt": attempt["attempt"]},
                metadata={"bounded_error": attempt["bounded_error"], "external_id": attempt["external_id"]},
            ))
            edges.extend([
                self._edge(layer_nodes["delivery"], attempt["id"], "contains"),
                self._edge(attempt["approval_id"], attempt["id"], "publishes_to"),
            ])
        return entities, edges

    @staticmethod
    def _hash(entities: list[SpatialEntity], edges: list[SpatialEdge], revision: int, focus: list[str]) -> str:
        body = {
            "projection_version": PROJECTION_VERSION, "revision": revision, "focus": sorted(focus),
            "entities": [entity.model_dump(mode="json") for entity in sorted(entities, key=lambda entry: entry.id)],
            "edges": [edge.model_dump(mode="json") for edge in sorted(edges, key=lambda entry: entry.id)],
        }
        return hashlib.sha256(json.dumps(body, sort_keys=True, separators=(",", ":")).encode()).hexdigest()

    def _snapshot_for_project(
        self, project: Project, *, focus_id: str | None = None, hop_count: int = 2,
        entity_limit: int = 200, edge_limit: int = 400, depth: str = "context",
    ) -> SpatialSnapshot:
        project_id = project.id
        all_entities, all_edges = self._full_graph(project)
        entity_map = {entity.id: entity for entity in all_entities}
        focus = [focus_id] if focus_id and focus_id in entity_map else self.store.get_selection(project_id)
        if depth == "system" or not focus:
            selected = set(entity_map)
        else:
            adjacency: dict[str, set[str]] = defaultdict(set)
            for edge in all_edges:
                adjacency[edge.source].add(edge.target)
                adjacency[edge.target].add(edge.source)
            selected = set(focus)
            frontier = set(focus)
            for _ in range(max(0, min(hop_count, 6))):
                frontier = {neighbor for identity in frontier for neighbor in adjacency[identity]} - selected
                selected.update(frontier)
            for identity in list(selected):
                parent = entity_map.get(identity).parent_id if identity in entity_map else None
                while parent:
                    selected.add(parent)
                    parent = entity_map.get(parent).parent_id if parent in entity_map else None

        ordered = sorted(
            (entity for entity in all_entities if entity.id in selected),
            key=lambda entry: (0 if entry.id in focus else 1, entry.position.z, entry.position.y, entry.position.x, entry.id),
        )
        entity_limit = max(10, min(entity_limit, 1000))
        kept = ordered[:entity_limit]
        kept_ids = {entity.id for entity in kept}
        omitted = ordered[entity_limit:]
        aggregates: list[str] = []
        if omitted and kept:
            counts: dict[str, int] = defaultdict(int)
            for entity in omitted:
                counts[entity.semantic_layer] += 1
            if len(kept) < entity_limit:
                layer, count = sorted(counts.items(), key=lambda value: (-value[1], value[0]))[0]
                aggregate_id = f"aggregate:{layer}:{project.id}"
                aggregate = self._entity(
                        identity=aggregate_id, kind="aggregate", label=f"{count} more {layer} entities",
                        parent_id=f"layer:{layer}:{project.id}", layer=layer, revision=project.revision,
                        x=0, y=999, state={"collapsed": True},
                    )
                aggregate.aggregate_count = count
                kept.append(aggregate)
                kept_ids.add(aggregate_id)
                aggregates.append(aggregate_id)

        eligible_edges = [edge for edge in all_edges if edge.source in kept_ids and edge.target in kept_ids]
        edge_limit = max(10, min(edge_limit, 2000))
        kept_edges = sorted(eligible_edges, key=lambda entry: entry.id)[:edge_limit]
        _, newest = self.store.runtime_cursor_bounds(project_id)
        projection_hash = self._hash(kept, kept_edges, project.revision, focus)
        return SpatialSnapshot(
            workspace_id=project.workspace_id or project.id, project_id=project.id, sequence_id=project.id,
            canonical_revision=project.revision, runtime_cursor=newest or 0,
            projection_hash=projection_hash, entities=kept, edges=kept_edges, focus=focus,
            truncation=SpatialTruncation(
                truncated=bool(omitted or len(eligible_edges) > edge_limit), omitted_entities=len(omitted),
                omitted_edges=max(0, len(eligible_edges) - edge_limit), aggregates=aggregates,
            ),
        )

    def snapshot(
        self, project_id: str, *, focus_id: str | None = None, hop_count: int = 2,
        entity_limit: int = 200, edge_limit: int = 400, depth: str = "context",
    ) -> SpatialSnapshot:
        return self._snapshot_for_project(
            self.store.get_project(project_id), focus_id=focus_id, hop_count=hop_count,
            entity_limit=entity_limit, edge_limit=edge_limit, depth=depth,
        )

    def neighborhood(self, project_id: str, entity_id: str, *, hop_count: int = 2, entity_limit: int = 200, edge_limit: int = 400) -> SpatialSnapshot:
        return self.snapshot(
            project_id, focus_id=entity_id, hop_count=hop_count,
            entity_limit=entity_limit, edge_limit=edge_limit, depth="context",
        )

    def blast_radius(self, project_id: str, entity_id: str, *, entity_limit: int = 200, edge_limit: int = 400) -> SpatialSnapshot:
        project = self.store.get_project(project_id)
        entities, edges = self._full_graph(project)
        downstream: dict[str, set[str]] = defaultdict(set)
        for edge in edges:
            if edge.relationship_kind in {"renders_to", "blocks", "publishes_to", "confirms", "observed_by"}:
                downstream[edge.source].add(edge.target)
            elif edge.relationship_kind in {"consumes", "derives_from"}:
                downstream[edge.target].add(edge.source)
        affected = {entity_id}
        queue = deque([entity_id])
        while queue and len(affected) < entity_limit:
            current = queue.popleft()
            for target in sorted(downstream[current]):
                if target not in affected:
                    affected.add(target)
                    queue.append(target)
        snapshot = self.snapshot(project_id, focus_id=entity_id, depth="system", entity_limit=1000, edge_limit=2000)
        snapshot.entities = [entity for entity in snapshot.entities if entity.id in affected]
        ids = {entity.id for entity in snapshot.entities}
        snapshot.edges = [edge for edge in snapshot.edges if edge.source in ids and edge.target in ids][:edge_limit]
        snapshot.truncation = SpatialTruncation(truncated=len(affected) >= entity_limit)
        snapshot.projection_hash = self._hash(snapshot.entities, snapshot.edges, snapshot.canonical_revision, snapshot.focus)
        return snapshot

    def delta(
        self, project_id: str, *, previous_revision: int, previous_cursor: int,
        previous_projection_hash: str | None = None,
    ) -> SpatialDelta:
        current_project = self.store.get_project(project_id)
        current = self._snapshot_for_project(current_project, depth="system", entity_limit=1000, edge_limit=2000)
        try:
            previous_project = self.store.get_project_revision(project_id, previous_revision)
        except (KeyError, ValueError):
            return SpatialDelta(
                previous_cursor=previous_cursor, current_cursor=current.runtime_cursor,
                previous_revision=previous_revision, current_revision=current.canonical_revision,
                previous_projection_hash=previous_projection_hash,
                current_projection_hash=current.projection_hash,
                focus=current.focus, snapshot_required=True,
            )

        previous = self._snapshot_for_project(
            previous_project, depth="system", entity_limit=1000, edge_limit=2000,
        )
        if previous_projection_hash and previous_projection_hash != previous.projection_hash:
            return SpatialDelta(
                previous_cursor=previous_cursor, current_cursor=current.runtime_cursor,
                previous_revision=previous_revision, current_revision=current.canonical_revision,
                previous_projection_hash=previous.projection_hash,
                current_projection_hash=current.projection_hash,
                focus=current.focus, snapshot_required=True,
            )

        previous_entities = {entity.id: entity for entity in previous.entities}
        current_entities = {entity.id: entity for entity in current.entities}
        previous_edges = {edge.id: edge for edge in previous.edges}
        current_edges = {edge.id: edge for edge in current.edges}
        return SpatialDelta(
            previous_cursor=previous_cursor, current_cursor=current.runtime_cursor,
            previous_revision=previous_revision, current_revision=current.canonical_revision,
            previous_projection_hash=previous.projection_hash,
            current_projection_hash=current.projection_hash,
            entity_upserts=[
                entity for identity, entity in sorted(current_entities.items())
                if identity not in previous_entities or entity != previous_entities[identity]
            ],
            entity_removals=sorted(set(previous_entities) - set(current_entities)),
            edge_upserts=[
                edge for identity, edge in sorted(current_edges.items())
                if identity not in previous_edges or edge != previous_edges[identity]
            ],
            edge_removals=sorted(set(previous_edges) - set(current_edges)),
            focus=current.focus,
        )


class SpatialDirectiveService:
    def __init__(
        self, store: Any, projection: SpatialProjectionService, runtime: RuntimeEventService,
        frames: SpatialFrameService | None = None,
    ):
        self.store = store
        self.projection = projection
        self.runtime = runtime
        self.frames = frames

    def dispatch(self, project_id: str, request: SpatialDirectiveRequest, *, actor: str) -> tuple[Any, SpatialDirective]:
        declaration = APPLICATION_ACTIONS.get(request.action)
        if declaration is None or not request.action.startswith("spatial."):
            raise ValueError("unknown spatial directive")
        snapshot = self.projection.snapshot(project_id, depth="system")
        if snapshot.canonical_revision != request.expected_revision:
            from .models import StaleRevisionError
            raise StaleRevisionError(request.expected_revision, snapshot.canonical_revision)
        if snapshot.projection_hash != request.expected_projection_hash:
            raise ValueError("stale spatial projection hash")
        known = {entity.id for entity in snapshot.entities}
        if any(target not in known for target in request.target_ids):
            raise ValueError("spatial directive contains an unknown target")
        if request.preferred_interaction_route == "coordinate_fallback":
            if request.action.startswith(SENSITIVE_COORDINATE_ACTION_PREFIXES):
                raise ValueError("sensitive actions cannot use coordinate fallback")
            if os.getenv("SAG_COORDINATE_FALLBACK_ENABLED", "").lower() not in {"1", "true", "yes"}:
                raise ValueError("coordinate fallback is disabled")
        if request.binding_id and not request.expected_frame_id:
            raise ValueError("a binding id requires an expected frame id")
        if request.expected_frame_id:
            if self.frames is None:
                raise ValueError("spatial frame binding is unavailable")
            frame = self.frames.get(project_id, request.expected_frame_id)
            if frame.canonical_revision != request.expected_revision or frame.projection_hash != request.expected_projection_hash:
                raise ValueError("stale spatial frame")
            if request.binding_id:
                binding = next((entry for entry in frame.bindings if entry.binding_id == request.binding_id), None)
                if binding is None:
                    raise ValueError("spatial binding not found in expected frame")
                if request.target_ids and binding.entity_id not in request.target_ids:
                    raise ValueError("spatial binding does not resolve to the directive target")
        trace_id = request.trace_id or f"trace_{uuid4().hex}"
        expires_at = (datetime.now(timezone.utc) + timedelta(seconds=request.expires_in_seconds)).isoformat()
        receipt = self.store.create_receipt(
            project_id=project_id, command=request.action, status=ReceiptStatus.ACCEPTED,
            request_id=f"directive-{uuid4()}", actor=actor, project_revision=snapshot.canonical_revision,
            payload={
                "target_ids": request.target_ids, "projection_hash": snapshot.projection_hash,
                "trace_id": trace_id, "expires_at": expires_at,
                "intended_observed_effect": sanitize_payload(request.intended_observed_effect),
                "expected_frame_id": request.expected_frame_id, "binding_id": request.binding_id,
                "preferred_interaction_route": request.preferred_interaction_route,
            },
        )
        receipt = self.store.update_receipt(receipt, ReceiptStatus.AWAITING_CONSUMER)
        directive = SpatialDirective(
            action=request.action, target_ids=request.target_ids,
            expected_revision=request.expected_revision,
            expected_projection_hash=request.expected_projection_hash,
            trace_id=trace_id, receipt_id=receipt.id, expires_at=expires_at,
            intended_observed_effect=sanitize_payload(request.intended_observed_effect),
            expected_frame_id=request.expected_frame_id, binding_id=request.binding_id,
            preferred_interaction_route=request.preferred_interaction_route,
        )
        project = self.store.get_project(project_id)
        self.runtime.emit(
            workspace_id=project.workspace_id or project.id, project_id=project.id, sequence_id=project.id,
            revision=project.revision, actor=actor, kind="spatial.directive.dispatched",
            trace_id=trace_id, payload={"receipt_id": receipt.id, "action": request.action, "directive": directive.model_dump(mode="json")},
        )
        self.runtime.emit(
            workspace_id=project.workspace_id or project.id, project_id=project.id, sequence_id=project.id,
            revision=project.revision, actor=actor, kind="spatial.action.routed", trace_id=trace_id,
            payload={
                "receipt_id": receipt.id, "action": request.action,
                "route": {
                    "kind": request.preferred_interaction_route,
                    "target_ids": request.target_ids, "expected_frame_id": request.expected_frame_id,
                    "binding_id": request.binding_id,
                },
            },
        )
        return receipt, directive

    def acknowledge(self, receipt_id: str, ack: SpatialDirectiveAck) -> Any:
        receipt = self.store.get_receipt(receipt_id)
        if not receipt.command.startswith("spatial.") or receipt.status != ReceiptStatus.AWAITING_CONSUMER:
            raise ValueError("directive is not awaiting a consumer")
        expires_at = datetime.fromisoformat(str(receipt.payload["expires_at"]))
        timed_out = expires_at < datetime.now(timezone.utc)
        targets_match = sorted(ack.observed_target_ids) == sorted(receipt.payload.get("target_ids", []))
        hash_matches = ack.projection_hash == receipt.payload.get("projection_hash")
        expected_frame_id = receipt.payload.get("expected_frame_id")
        frame_matches = expected_frame_id is None or ack.before_frame_id == expected_frame_id
        after_frame_valid = True
        if expected_frame_id is not None:
            after_frame_valid = bool(ack.after_frame_id)
            if after_frame_valid and self.frames is not None:
                try:
                    after = self.frames.get(receipt.project_id, str(ack.after_frame_id))
                    after_frame_valid = after.canonical_revision == receipt.project_revision
                except KeyError:
                    after_frame_valid = False
        route_matches = (
            ack.action_route is None
            or ack.action_route.kind == receipt.payload.get("preferred_interaction_route", "semantic_handler")
        )
        success = (
            ack.success and targets_match and hash_matches and frame_matches
            and after_frame_valid and route_matches and not timed_out
        )
        status = ReceiptStatus.TIMEOUT if timed_out else ReceiptStatus.OBSERVED_SUCCESS if success else ReceiptStatus.OBSERVED_FAILURE
        updated = self.store.update_receipt(receipt, status, {
            "consumer_id": ack.consumer_id, "observed_target_ids": ack.observed_target_ids,
            "active_depth": ack.active_depth, "renderer_mode": ack.renderer_mode,
            "findings": sanitize_payload(ack.findings), "targets_match": targets_match,
            "projection_hash_match": hash_matches,
            "before_frame_id": ack.before_frame_id, "after_frame_id": ack.after_frame_id,
            "frame_match": frame_matches, "after_frame_valid": after_frame_valid,
            "changed_entity_ids": ack.changed_entity_ids, "changed_cells": ack.changed_cells,
            "action_route": ack.action_route.model_dump(mode="json") if ack.action_route else None,
            "route_match": route_matches,
        })
        project = self.store.get_project(receipt.project_id)
        kind = "spatial.directive.timeout" if timed_out else "spatial.directive.consumed" if success else "spatial.directive.failed"
        self.runtime.emit(
            workspace_id=project.workspace_id or project.id, project_id=project.id, sequence_id=project.id,
            revision=project.revision, actor=ack.consumer_id, kind=kind,
            trace_id=receipt.payload.get("trace_id"), payload={"receipt_id": receipt.id, "status": status.value},
        )
        if ack.before_frame_id and ack.after_frame_id:
            self.runtime.emit(
                workspace_id=project.workspace_id or project.id, project_id=project.id, sequence_id=project.id,
                revision=project.revision, actor=ack.consumer_id, kind="spatial.effect.observed",
                trace_id=receipt.payload.get("trace_id"),
                payload={"observation": {
                    "directive_receipt_id": receipt.id, "before_frame_id": ack.before_frame_id,
                    "after_frame_id": ack.after_frame_id, "changed_entity_ids": ack.changed_entity_ids,
                    "changed_cells": ack.changed_cells,
                    "route": ack.action_route.model_dump(mode="json") if ack.action_route else None,
                    "success": success, "findings": sanitize_payload(ack.findings),
                }},
            )
        return updated
