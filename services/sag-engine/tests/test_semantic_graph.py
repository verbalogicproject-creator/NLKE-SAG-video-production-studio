from __future__ import annotations

import hashlib
import json
from pathlib import Path

from test_delivery_governance import seed_verified_artifact


def entities_by_local_id(graph: dict) -> dict[str, dict]:
    return {entry["local_id"]: entry for entry in graph["entities"]}


def test_x1_draft_graph_has_stable_uris_edges_hash_and_provenance(client):
    first = client.get("/api/projects/demo/semantic/graph").json()
    second = client.get("/api/projects/demo/semantic/graph").json()
    assert first["schema_version"] == "sag-semantic-graph/0.1-draft"
    assert first["projection_hash"] == second["projection_hash"]
    assert first["entities"] == second["entities"]
    entities = entities_by_local_id(first)
    clip = entities["clip_terminal"]
    asset = entities["asset_intro"]
    assert clip["uri"] == "sag://sag-video/project/demo/timeline-item/clip_terminal"
    assert clip["kind"] == "timeline-item"
    assert clip["extensions"]["sag.video.spatial"]["local_kind"] == "video"
    assert clip["provenance"][0]["derivation"] == "derived"
    consumes = next(edge for edge in first["edges"] if (
        edge["source_uri"] == clip["uri"] and edge["target_uri"] == asset["uri"]
        and edge["relationship_kind"] == "consumes"
    ))
    digest = hashlib.sha256(f"consumes\0{clip['uri']}\0{asset['uri']}\0".encode()).hexdigest()[:32]
    assert consumes["uri"] == f"sag://sag-video/project/demo/edge/{digest}"


def test_x1_fixture_a_adjacent_order_and_provenance_toggle(client):
    fixture_path = Path(__file__).resolve().parents[3] / "contracts/x1/sag-video-runtime-fixtures.json"
    fixture = next(entry for entry in json.loads(fixture_path.read_text())["fixtures"] if entry["id"] == "runtime-adjacency")
    graph = client.get("/api/projects/demo/semantic/graph").json()
    entities = entities_by_local_id(graph)
    response = client.post("/api/projects/demo/semantic/neighborhood", json={
        "scope_uri": graph["scope_uri"], "seed_uris": [entities["clip_terminal"]["uri"]],
        "mode": fixture["mode"], "max_hops": fixture["max_hops"], "entity_limit": 20, "edge_limit": 30,
        "include_provenance": False,
    }).json()
    assert response["reset_required"] is False
    assert [entry["local_id"] for entry in response["entities"]] == fixture["expected_local_id_order"]
    assert all(not entry["provenance"] for entry in response["entities"])
    assert all(not entry["provenance"] for entry in response["edges"])


def test_x1_fixture_b_blast_radius_reaches_render_artifact_and_approval(client):
    artifact = seed_verified_artifact(client)
    approved = client.post("/api/projects/demo/release/approvals", json={
        "request_id": "semantic-approval-test-0001", "project_revision": 1,
        "artifact_hashes": [artifact.sha256],
        "destinations": [{"destination": "download", "visibility": "manual"}],
        "approved_by": "human-test-owner",
    }).json()["approval"]
    graph = client.get("/api/projects/demo/semantic/graph").json()
    entities = entities_by_local_id(graph)
    response = client.post("/api/projects/demo/semantic/neighborhood", json={
        "scope_uri": graph["scope_uri"], "seed_uris": [entities["asset_intro"]["uri"]],
        "mode": "blast-radius", "max_hops": 4, "entity_limit": 50, "edge_limit": 100,
    }).json()
    reached = {entry["local_id"] for entry in response["entities"]}
    assert {"asset_intro", "clip_terminal", "job_release_verified", artifact.id, approved["id"]} <= reached


def test_x1_neighborhood_refuses_unknown_seed_and_unretained_revision(client):
    graph = client.get("/api/projects/demo/semantic/graph").json()
    unknown = client.post("/api/projects/demo/semantic/neighborhood", json={
        "scope_uri": graph["scope_uri"], "seed_uris": ["sag://sag-video/project/demo/asset/missing"],
    }).json()
    assert unknown["reset_required"] is True
    assert "unknown" in unknown["reset_reason"]
    old = client.post("/api/projects/demo/semantic/neighborhood", json={
        "scope_uri": graph["scope_uri"], "seed_uris": [graph["entities"][0]["uri"]],
        "at_revision": {"authority": "sag-video", "value": "999"},
    }).json()
    assert old["reset_required"] is True
    assert old["reset_reason"] == "revision is not retained"
