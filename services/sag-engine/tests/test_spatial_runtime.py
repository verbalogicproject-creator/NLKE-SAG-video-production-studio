from __future__ import annotations

from datetime import datetime, timedelta, timezone

from sag_video.runtime import RUNTIME_PAYLOAD_LIMIT, bounded_payload

from conftest import command_body


def test_contract_exposes_versioned_runtime_and_spatial_contracts(client):
    contract = client.get("/api/contract").json()
    assert contract["projection_version"] == "sag-spatial-1"
    assert "SpatialSnapshot" in contract["spatial_schemas"]
    assert "SemanticGraphEnvelope" in contract["semantic_graph_schemas"]
    assert contract["semantic_projection_version"] == "sag-video-semantic-adapter/0.1-draft"
    kinds = {entry["kind"] for entry in contract["event_definitions"]}
    assert {"studio.focus_changed", "spatial.directive.dispatched", "command.committed"} <= kinds
    actions = {entry["name"] for entry in contract["spatial_actions"]}
    assert "spatial.focus_entity" in actions
    assert "spatial.reset_view" in actions


def test_runtime_payloads_redact_secrets_and_bound_large_values():
    clean = bounded_payload({"access_token": "secret", "prompt": "private", "safe": "ok"})
    assert clean == {"access_token": "[redacted]", "prompt": "[redacted]", "safe": "ok"}
    large = bounded_payload({"safe": ["x" * 1024 for _ in range(40)]})
    assert large["truncated"] is True
    assert len(large["sha256"]) == 64


def test_spatial_snapshot_is_deterministic_and_uses_canonical_identity(client):
    first = client.get("/api/projects/demo/spatial/snapshot?depth=system").json()
    second = client.get("/api/projects/demo/spatial/snapshot?depth=system").json()
    assert first["projection_hash"] == second["projection_hash"]
    assert first["entities"] == second["entities"]
    entities = {entry["id"]: entry for entry in first["entities"]}
    assert entities["title_intro"]["parent_id"] == "track_titles"
    assert entities["title_intro"]["semantic_layer"] == "composition"
    assert entities["asset_intro"]["semantic_layer"] == "creation"
    consumes = {
        (edge["source"], edge["target"], edge["relationship_kind"])
        for edge in first["edges"]
    }
    assert ("clip_terminal", "asset_intro", "consumes") in consumes


def test_neighborhood_blast_radius_and_delta_are_bounded(client):
    neighborhood = client.get(
        "/api/projects/demo/spatial/entities/clip_terminal/neighborhood?hop_count=2&entity_limit=20&edge_limit=30"
    ).json()
    assert neighborhood["focus"] == ["clip_terminal"]
    assert len(neighborhood["entities"]) <= 20
    blast = client.get("/api/projects/demo/spatial/entities/asset_intro/blast-radius").json()
    assert {entry["id"] for entry in blast["entities"]} >= {"asset_intro", "clip_terminal"}
    delta = client.get("/api/projects/demo/spatial/delta?previous_revision=1&previous_cursor=0").json()
    assert delta["snapshot_required"] is False
    client.post(
        "/api/projects/demo/commands",
        json=command_body(
            "timeline.set_title_transform", {"item_id": "title_intro", "x": 10},
            request_id="spatial-delta-edit-0001",
        ),
    )
    stale = client.get("/api/projects/demo/spatial/delta?previous_revision=1&previous_cursor=0").json()
    assert stale["snapshot_required"] is False
    assert stale["previous_revision"] == 1
    assert stale["current_revision"] == 2
    assert "title_intro" in {entry["id"] for entry in stale["entity_upserts"]}
    bad_hash = client.get(
        "/api/projects/demo/spatial/delta?previous_revision=1&previous_cursor=0&previous_projection_hash=bad"
    ).json()
    assert bad_hash["snapshot_required"] is True


def test_runtime_cursor_replay_and_spatial_directive_ack(client):
    snapshot = client.get("/api/projects/demo/spatial/snapshot?depth=system").json()
    dispatched = client.post(
        "/api/projects/demo/spatial/directives",
        json={
            "action": "spatial.focus_entity", "target_ids": ["clip_terminal"],
            "expected_revision": snapshot["canonical_revision"],
            "expected_projection_hash": snapshot["projection_hash"],
            "intended_observed_effect": {"focus": "clip_terminal"},
        },
    )
    assert dispatched.status_code == 200
    body = dispatched.json()
    assert body["receipt"]["status"] == "awaiting_consumer"
    history = client.get("/api/projects/demo/runtime/events?cursor=0").json()
    assert history["snapshot_required"] is False
    event = next(entry for entry in history["events"] if entry["kind"] == "spatial.directive.dispatched")
    replay = client.get(f"/api/projects/demo/runtime/events?cursor={event['cursor'] - 1}").json()
    assert replay["events"][0]["cursor"] == event["cursor"]
    ack = client.post(
        f"/api/spatial/directives/{body['receipt']['id']}/ack",
        json={
            "consumer_id": "studio-browser", "projection_hash": snapshot["projection_hash"],
            "observed_target_ids": ["clip_terminal"], "active_depth": "context",
            "renderer_mode": "dom_tree", "findings": [], "success": True,
        },
    )
    assert ack.status_code == 200
    assert ack.json()["status"] == "observed_success"


def test_runtime_retention_prunes_expiry_and_resets_pruned_cursor(client):
    store = client.app.state.store
    now = datetime.now(timezone.utc)
    for index in range(5):
        store.append_runtime_event(
            event_id=f"retention-event-{index}", workspace_id="demo", project_id="demo",
            sequence_id="demo", revision=1, actor="test", session_id=None,
            kind="studio.focus_changed", trace_id=None, payload={"entity_ids": ["title_intro"]},
            created_at=(now + timedelta(seconds=index)).isoformat(),
            expires_at=(now + timedelta(days=1)).isoformat(),
        )
    store.append_runtime_event(
        event_id="retention-expired", workspace_id="demo", project_id="demo",
        sequence_id="demo", revision=1, actor="test", session_id=None,
        kind="studio.focus_changed", trace_id=None, payload={"entity_ids": []},
        created_at=(now - timedelta(days=8)).isoformat(),
        expires_at=(now - timedelta(seconds=1)).isoformat(),
    )
    assert store.prune_runtime_events("demo", max_events=2) == 4
    oldest, newest = store.runtime_cursor_bounds("demo")
    assert oldest is not None and newest is not None and newest - oldest == 1
    reset = client.get("/api/projects/demo/runtime/events?cursor=1").json()
    assert reset["snapshot_required"] is True
    assert reset["events"] == []


def test_directive_ack_fails_when_exact_target_does_not_match(client):
    snapshot = client.get("/api/projects/demo/spatial/snapshot?depth=system").json()
    dispatched = client.post(
        "/api/projects/demo/spatial/directives",
        json={
            "action": "spatial.focus_entity", "target_ids": ["clip_terminal"],
            "expected_revision": 1, "expected_projection_hash": snapshot["projection_hash"],
        },
    ).json()
    ack = client.post(
        f"/api/spatial/directives/{dispatched['receipt']['id']}/ack",
        json={
            "consumer_id": "studio-browser", "projection_hash": snapshot["projection_hash"],
            "observed_target_ids": ["clip_result"], "active_depth": "context",
            "renderer_mode": "webgl", "success": True,
        },
    )
    assert ack.json()["status"] == "observed_failure"
    assert ack.json()["payload"]["targets_match"] is False


def test_protected_provider_connection_projects_only_sanitized_summary(client):
    created = client.post(
        "/api/workspaces/demo/connections",
        json={
            "provider": "openai", "purpose": "analysis", "display_name": "Studio analysis",
            "scopes": ["responses:create"], "encrypted_secret": "ciphertext-not-plaintext-value",
            "kms_key_version": "projects/demo/locations/global/keyRings/sag/cryptoKeys/connections/1",
            "secret_fingerprint": "0123456789abcdef", "metadata": {"region": "global"},
        },
    )
    assert created.status_code == 201
    connection = created.json()
    assert "encrypted_secret" not in connection
    protected = client.get(f"/api/workspaces/demo/connections/{connection['id']}/protected")
    assert protected.status_code == 403
    snapshot = client.get("/api/projects/demo/spatial/snapshot?depth=system").json()
    projected = next(entity for entity in snapshot["entities"] if entity["id"] == connection["id"])
    encoded = str(projected)
    assert projected["kind"] == "provider_connection"
    assert "ciphertext-not-plaintext-value" not in encoded
    revoked = client.delete(f"/api/workspaces/demo/connections/{connection['id']}")
    assert revoked.json()["state"] == "revoked"


def _frame_body(snapshot, frame_id: str, *, bindings=None, **overrides):
    body = {
        "frame_id": frame_id,
        "canonical_revision": snapshot["canonical_revision"],
        "projection_hash": snapshot["projection_hash"],
        "runtime_cursor": snapshot["runtime_cursor"],
        "active_depth": "edit",
        "viewport": {
            "width_css_px": 400, "height_css_px": 800, "device_pixel_ratio": 2,
            "scroll_x_css_px": 0, "scroll_y_css_px": 0,
        },
        "bindings": bindings or [],
        "redaction_state": "metadata_only",
    }
    body.update(overrides)
    return body


def test_spatial_frame_declares_adaptive_grid_and_resolves_semantic_regions(client):
    snapshot = client.get("/api/projects/demo/spatial/snapshot?depth=system").json()
    binding = {
        "binding_id": "binding_clip_terminal",
        "entity_id": "clip_terminal", "role": "button", "label": "Terminal clip",
        "rect": {"x": 0.2, "y": 0.5, "width": 0.4, "height": 0.1},
        "cells": ["B6", "C6", "B7", "C7"],
        "eligible_action_ids": ["spatial.focus_entity"],
        "source": "dom", "confidence": 1,
    }
    declared = client.post(
        "/api/projects/demo/spatial/frames",
        json=_frame_body(snapshot, "frame_acceptance_0001", bindings=[binding]),
    )
    assert declared.status_code == 201, declared.text
    frame = declared.json()
    assert frame["grid"]["columns"] == 5
    assert frame["grid"]["rows"] == 10
    assert frame["redaction_state"] == "metadata_only"
    assert client.get("/api/projects/demo/spatial/frames/current").json()["frame_id"] == frame["frame_id"]
    resolved = client.post(
        f"/api/projects/demo/spatial/frames/{frame['frame_id']}/resolve",
        json={"cell": "B6", "minimum_confidence": 0.9},
    ).json()
    assert [entry["entity_id"] for entry in resolved["matches"]] == ["clip_terminal"]
    by_point = client.post(
        f"/api/projects/demo/spatial/frames/{frame['frame_id']}/resolve",
        json={"point": {"x": 0.3, "y": 0.55}},
    ).json()
    assert by_point["matches"][0]["binding_id"] == "binding_clip_terminal"


def test_frame_bound_directive_requires_matching_before_and_valid_after_frame(client):
    snapshot = client.get("/api/projects/demo/spatial/snapshot?depth=system").json()
    binding = {
        "binding_id": "binding_clip_terminal", "entity_id": "clip_terminal",
        "rect": {"x": 0.1, "y": 0.2, "width": 0.3, "height": 0.1},
        "cells": ["A3", "B3"], "eligible_action_ids": ["spatial.focus_entity"],
    }
    before = client.post(
        "/api/projects/demo/spatial/frames",
        json=_frame_body(snapshot, "frame_before_directive", bindings=[binding]),
    ).json()
    dispatched = client.post(
        "/api/projects/demo/spatial/directives",
        json={
            "action": "spatial.focus_entity", "target_ids": ["clip_terminal"],
            "expected_revision": snapshot["canonical_revision"],
            "expected_projection_hash": snapshot["projection_hash"],
            "expected_frame_id": before["frame_id"], "binding_id": binding["binding_id"],
        },
    )
    assert dispatched.status_code == 200, dispatched.text
    after_snapshot = client.get("/api/projects/demo/spatial/snapshot?depth=system").json()
    after = client.post(
        "/api/projects/demo/spatial/frames",
        json=_frame_body(after_snapshot, "frame_after_directive", bindings=[binding]),
    ).json()
    receipt_id = dispatched.json()["receipt"]["id"]
    ack = client.post(
        f"/api/spatial/directives/{receipt_id}/ack",
        json={
            "consumer_id": "studio-browser", "projection_hash": snapshot["projection_hash"],
            "observed_target_ids": ["clip_terminal"], "active_depth": "context",
            "renderer_mode": "dom_tree", "before_frame_id": before["frame_id"],
            "after_frame_id": after["frame_id"], "changed_entity_ids": ["clip_terminal"],
            "changed_cells": ["A3"],
            "action_route": {
                "kind": "semantic_handler", "action": "spatial.focus_entity",
                "target_id": "clip_terminal", "binding_id": binding["binding_id"], "confidence": 1,
            },
        },
    )
    assert ack.status_code == 200
    assert ack.json()["status"] == "observed_success"
    assert ack.json()["payload"]["frame_match"] is True
    assert ack.json()["payload"]["after_frame_valid"] is True


def test_spatial_frames_reject_raw_media_unknown_entities_and_unsafe_coordinate_routes(client):
    snapshot = client.get("/api/projects/demo/spatial/snapshot?depth=system").json()
    raw = _frame_body(snapshot, "frame_raw_rejected")
    raw["raw_screenshot"] = "data:image/png;base64,secret"
    assert client.post("/api/projects/demo/spatial/frames", json=raw).status_code == 422
    unknown = _frame_body(snapshot, "frame_unknown_binding", bindings=[{
        "binding_id": "binding_unknown_entity", "entity_id": "unknown-control",
        "rect": {"x": 0, "y": 0, "width": 0.2, "height": 0.2}, "cells": ["A1"],
    }])
    assert client.post("/api/projects/demo/spatial/frames", json=unknown).status_code == 422

    before = client.post(
        "/api/projects/demo/spatial/frames", json=_frame_body(snapshot, "frame_safe_before_01"),
    ).json()
    after = client.post(
        "/api/projects/demo/spatial/frames", json=_frame_body(snapshot, "frame_safe_after_001"),
    ).json()
    unsafe = client.post("/api/projects/demo/spatial/observations", json={
        "observation_id": "observation_unsafe_coordinate",
        "before_frame_id": before["frame_id"], "after_frame_id": after["frame_id"],
        "expected_revision": snapshot["canonical_revision"],
        "expected_projection_hash": snapshot["projection_hash"],
        "route": {
            "kind": "coordinate_fallback", "action": "release.approve",
            "confidence": 1,
        },
    })
    assert unsafe.status_code == 422
    assert "sensitive actions" in unsafe.text


def test_gemini_bindings_are_opt_in_redacted_and_reconciled(client, monkeypatch):
    snapshot = client.get("/api/projects/demo/spatial/snapshot?depth=system").json()
    binding = {
        "binding_id": "binding_gemini_clip_terminal",
        "entity_id": "clip_terminal",
        "role": "region",
        "label": "Observed terminal clip",
        "rect": {"x": 0.1, "y": 0.2, "width": 0.4, "height": 0.2},
        "cells": ["A3", "B3"],
        "source": "gemini",
        "confidence": 0.96,
    }
    disabled = client.post(
        "/api/projects/demo/spatial/frames",
        json=_frame_body(snapshot, "frame_gemini_disabled_01", bindings=[binding], redaction_state="redacted"),
    )
    assert disabled.status_code == 422
    assert "disabled" in disabled.text

    monkeypatch.setenv("SAG_GEMINI_OBSERVER_ENABLED", "1")
    unredacted = client.post(
        "/api/projects/demo/spatial/frames",
        json=_frame_body(snapshot, "frame_gemini_unredacted", bindings=[binding]),
    )
    assert unredacted.status_code == 422
    assert "redacted" in unredacted.text

    declared = client.post(
        "/api/projects/demo/spatial/frames",
        json=_frame_body(snapshot, "frame_gemini_redacted_01", bindings=[binding], redaction_state="redacted"),
    )
    assert declared.status_code == 201, declared.text
    history = client.get("/api/projects/demo/runtime/events?cursor=0").json()
    reconciled = [event for event in history["events"] if event["kind"] == "spatial.bindings.reconciled"]
    assert reconciled[-1]["payload"]["bindings"] == [{
        "binding_id": binding["binding_id"],
        "entity_id": "clip_terminal",
        "source": "gemini",
        "confidence": 0.96,
    }]
