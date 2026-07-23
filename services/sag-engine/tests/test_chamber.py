from __future__ import annotations

import time

from fastapi.testclient import TestClient

from media_fixtures import tiny_video
from sag_video.app import Settings, create_app
from sag_video.chamber import BrandContract, DraftPlan, DraftScene, PlatformVariant, validate_draft_plan
from sag_video.models import TICKS_PER_SECOND
from sag_video.shorts import _assign_variant_candidates
from test_shorts_pipeline import FakeTranscriber


def _wait(client: TestClient, job_id: str):
    deadline = time.monotonic() + 25
    while time.monotonic() < deadline:
        job = client.get(f"/api/jobs/{job_id}").json()
        if job["state"] in {"observed_success", "execution_failed", "cancelled"}:
            return job
        time.sleep(.1)
    raise AssertionError("job did not finish")


def test_variant_assignment_is_distinct_and_platform_bounded():
    candidates = [
        {"candidate_id": "long", "start_ticks": 0, "end_ticks": 55 * TICKS_PER_SECOND, "clip_score": 99},
        {"candidate_id": "short", "start_ticks": 60 * TICKS_PER_SECOND, "end_ticks": 95 * TICKS_PER_SECOND, "clip_score": 95},
        {"candidate_id": "third", "start_ticks": 100 * TICKS_PER_SECOND, "end_ticks": 140 * TICKS_PER_SECOND, "clip_score": 90},
    ]
    assigned = _assign_variant_candidates(candidates, [
        PlatformVariant.TIKTOK_9_16,
        PlatformVariant.YT_SHORTS_9_16,
        PlatformVariant.IG_REELS_9_16,
    ])
    assert [entry[1]["candidate_id"] for entry in assigned] == ["short", "long", "third"]
    assert len({entry[1]["candidate_id"] for entry in assigned}) == 3


def test_brand_contract_halts_source_backed_forbidden_caption():
    brand = BrandContract(version=4, forbidden_phrases=["game-changing"])
    plan = DraftPlan(
        target_variant=PlatformVariant.YT_SHORTS_9_16,
        source_project_id="project",
        source_revision=2,
        source_asset_id="asset",
        source_sha256="a" * 64,
        scenes=[DraftScene(source_start_ticks=0, source_end_ticks=TICKS_PER_SECOND, word_ids=["w1"])],
        score=80,
        reason="Strong source-backed hook",
        brand_version=brand.version,
        brand_hash=brand.contract_hash,
    )
    violations = validate_draft_plan(plan, "A game-changing result", brand)
    assert [(entry.code, entry.field) for entry in violations] == [("forbidden_phrase", "captions")]


def test_platform_draft_preserves_contract_and_lineage(client: TestClient, tmp_path):
    client.app.state.shorts.transcriber = FakeTranscriber()
    source = tiny_video(tmp_path / "chamber-source.mp4", duration=16.1)
    imported = client.post(
        "/api/projects/demo/assets/uploads",
        data={"request_id": "chamber-upload-0001", "actor": "test"},
        files={"file": (source.name, source.read_bytes(), "video/mp4")},
    ).json()
    queued = client.post("/api/projects/demo/shorts/jobs", json={
        "source_revision": imported["receipt"]["project_revision"],
        "asset_id": imported["asset"]["id"],
        "candidate_count": 1,
        "target_variants": ["YT_SHORTS_9_16"],
        "brand_contract": {"version": 3, "forbidden_phrases": []},
    }).json()
    assert _wait(client, queued["id"])["state"] == "observed_success"
    draft = client.get(f"/api/projects/demo/suggestions?job_id={queued['id']}").json()["suggestions"][0]
    assert draft["generator_kind"] == "platform_short"
    assert draft["evidence"]["draft_plan"]["contract_version"] == "chamber-draft-1.0"
    assert draft["evidence"]["draft_plan"]["target_variant"] == "YT_SHORTS_9_16"
    assert draft["evidence"]["draft_plan"]["scenes"][0]["word_ids"]
    accepted = client.post(f"/api/suggestions/{draft['id']}/accept", json={
        "request_id": "chamber-accept-0001", "actor": "test", "expected_state": "pending",
    }).json()["project"]
    assert accepted["target_variant"] == "YT_SHORTS_9_16"
    assert accepted["brand_version"] == 3
    assert accepted["source_project_revision"] == imported["receipt"]["project_revision"]


def test_service_token_scopes_created_projects(tmp_path):
    app = create_app(Settings(
        database_path=str(tmp_path / "service.db"),
        artifact_dir=str(tmp_path / "artifacts"),
        media_dir=str(tmp_path / "media"),
        proxy_dir=str(tmp_path / "proxies"),
        service_token="secret-token",
    ))
    with TestClient(app) as client:
        headers = {"x-sag-service-token": "secret-token", "x-sag-workspace-id": "workspace-a"}
        created = client.post("/api/projects", headers=headers, json={
            "name": "Scoped", "preset": "vertical_1080p", "workspace_id": "workspace-a",
        })
        assert created.status_code == 200
        project_id = created.json()["project"]["id"]
        denied = client.get(f"/api/projects/{project_id}", headers={
            "x-sag-service-token": "secret-token", "x-sag-workspace-id": "workspace-b",
        })
        assert denied.status_code == 403
