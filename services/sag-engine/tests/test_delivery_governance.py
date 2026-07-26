from __future__ import annotations

from fastapi.testclient import TestClient

from sag_video.app import Settings, create_app
from sag_video.repository import ArtifactRecord, JobRecord


def seed_verified_artifact(client) -> ArtifactRecord:
    store = client.app.state.store
    job = JobRecord(
        id="job_release_verified", project_id="demo", project_revision=1,
        kind="render", state="observed_success", progress=1,
        frozen_spec={"render_spec": {"media": [{"item_id": "clip_terminal", "asset_id": "asset_intro"}]}},
        result_artifact_id="artifact_release_verified",
    )
    store.create_job(job)
    artifact = ArtifactRecord(
        id="artifact_release_verified", project_id="demo", job_id=job.id,
        asset_id=None, kind="render", managed_uri="sag-artifact://demo/artifact_release_verified",
        sha256="a" * 64, byte_size=1024, mime_type="video/mp4",
        provenance={"observer": "test-independent-observer", "passed": True},
    )
    return store.create_artifact(artifact)


def test_engine_owns_delivery_approval_attempts_and_projection(client):
    artifact = seed_verified_artifact(client)
    profile = client.post("/api/projects/demo/delivery/profiles", json={
        "destination": "youtube_shorts", "aspect_ratio": "9:16",
        "width": 1080, "height": 1920, "caption_placement": "safe_bottom",
    })
    assert profile.status_code == 201

    approved = client.post("/api/projects/demo/release/approvals", json={
        "request_id": "release-approval-test-0001", "project_revision": 1,
        "artifact_hashes": [artifact.sha256],
        "destinations": [{"destination": "youtube_shorts", "visibility": "private"}],
        "approved_by": "human-test-owner",
    })
    assert approved.status_code == 201
    approval = approved.json()["approval"]
    assert approval["state"] == "active"
    assert approved.json()["receipt"]["status"] == "committed"

    duplicate = client.post("/api/projects/demo/release/approvals", json={
        "request_id": "release-approval-test-0001", "project_revision": 1,
        "artifact_hashes": [artifact.sha256],
        "destinations": [{"destination": "youtube_shorts", "visibility": "private"}],
        "approved_by": "human-test-owner",
    })
    assert duplicate.json()["approval"]["id"] == approval["id"]
    assert duplicate.json()["receipt"]["id"] == approved.json()["receipt"]["id"]

    dispatched = client.post(
        f"/api/projects/demo/release/approvals/{approval['id']}/dispatch",
        json={"request_id": "release-dispatch-test-0001"},
    )
    assert dispatched.status_code == 202
    assert dispatched.json()["approval"]["state"] == "consumed"
    assert dispatched.json()["attempts"][0]["state"] == "pending"
    repeated = client.post(
        f"/api/projects/demo/release/approvals/{approval['id']}/dispatch",
        json={"request_id": "release-dispatch-test-0001"},
    )
    assert repeated.status_code == 202
    assert repeated.json()["attempts"][0]["id"] == dispatched.json()["attempts"][0]["id"]

    state = client.get("/api/projects/demo/delivery").json()
    assert state["delivery_profiles"][0]["destination"] == "youtube_shorts"
    assert state["release_approvals"][0]["attempts"][0]["destination"] == "youtube_shorts"
    snapshot = client.get("/api/projects/demo/spatial/snapshot?depth=system").json()
    entities = {entry["id"]: entry for entry in snapshot["entities"]}
    assert entities[profile.json()["id"]]["semantic_layer"] == "delivery"
    assert entities[approval["id"]]["kind"] == "release_approval"
    assert entities[dispatched.json()["attempts"][0]["id"]]["kind"] == "publication_attempt"
    relationships = {
        (edge["source"], edge["target"], edge["relationship_kind"])
        for edge in snapshot["edges"]
    }
    assert (approval["id"], artifact.id, "confirms") in relationships
    assert (approval["id"], dispatched.json()["attempts"][0]["id"], "publishes_to") in relationships


def test_release_refuses_unobserved_artifact_and_nonmanual_instagram(client):
    store = client.app.state.store
    artifact = store.create_artifact(ArtifactRecord(
        id="artifact_unobserved", project_id="demo", job_id=None, asset_id=None,
        kind="render", managed_uri="sag-artifact://demo/artifact_unobserved",
        sha256="b" * 64, byte_size=12, mime_type="video/mp4", provenance={},
    ))
    denied = client.post("/api/projects/demo/release/approvals", json={
        "request_id": "release-unobserved-test-0001", "project_revision": 1,
        "artifact_hashes": [artifact.sha256],
        "destinations": [{"destination": "download", "visibility": "manual"}],
        "approved_by": "human-test-owner",
    })
    assert denied.status_code == 409
    seed_verified_artifact(client)
    instagram = client.post("/api/projects/demo/release/approvals", json={
        "request_id": "release-instagram-test-0001", "project_revision": 1,
        "artifact_hashes": ["a" * 64],
        "destinations": [{"destination": "instagram_reels", "visibility": "private"}],
        "approved_by": "human-test-owner",
    })
    assert instagram.status_code == 409


def test_legacy_delivery_import_is_service_only_and_idempotent(tmp_path):
    app = create_app(Settings(
        database_path=str(tmp_path / "import.db"), artifact_dir=str(tmp_path / "artifacts"),
        media_dir=str(tmp_path / "media"), proxy_dir=str(tmp_path / "proxies"),
        storage_root=str(tmp_path / "storage"), storage_cache_dir=str(tmp_path / "cache"),
        service_token="migration-secret", start_render_worker=False, start_analysis_worker=False,
    ))
    with TestClient(app) as client:
        assert client.post("/api/projects/demo/delivery/import", json={}).status_code == 403
        headers = {"x-sag-service-token": "migration-secret", "x-sag-workspace-id": "demo"}
        body = {
            "profiles": [{
                "id": "legacy_profile_youtube", "destination": "youtube_shorts",
                "aspect_ratio": "9:16", "width": 1080, "height": 1920,
                "caption_placement": "safe_bottom", "safe_zone_x": 48, "safe_zone_y": 96,
                "metadata": {"source": "legacy-control-plane"},
                "created_at": "2026-07-01T00:00:00+00:00", "updated_at": "2026-07-02T00:00:00+00:00",
            }],
            "approvals": [{
                "id": "legacy_approval_1", "project_revision": 1, "bundle_hash": "legacy-bundle-hash-0001",
                "artifact_hashes": ["c" * 64],
                "destinations": [{"destination": "download", "visibility": "manual"}],
                "state": "consumed", "approved_by": "legacy-human",
                "expires_at": "2026-07-01T01:00:00+00:00", "consumed_at": "2026-07-01T00:30:00+00:00",
                "created_at": "2026-07-01T00:00:00+00:00",
                "attempts": [{
                    "id": "legacy_attempt_1", "destination": "download",
                    "idempotency_key": "legacy-attempt-key-0001", "state": "pending",
                    "bounded_error": "verified_download_fallback", "attempt": 0,
                    "created_at": "2026-07-01T00:30:00+00:00", "updated_at": "2026-07-01T00:30:00+00:00",
                }],
            }],
        }
        first = client.post("/api/projects/demo/delivery/import", headers=headers, json=body)
        second = client.post("/api/projects/demo/delivery/import", headers=headers, json=body)
        assert first.status_code == 200
        assert second.status_code == 200
        assert first.json()["profiles"] == ["legacy_profile_youtube"]
        assert first.json()["approvals"] == ["legacy_approval_1"]
        assert first.json()["attempts"] == ["legacy_attempt_1"]
        state = second.json()["state"]
        assert len(state["delivery_profiles"]) == 1
        assert len(state["release_approvals"]) == 1
        assert state["release_approvals"][0]["attempts"][0]["id"] == "legacy_attempt_1"
