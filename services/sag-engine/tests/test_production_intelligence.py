from __future__ import annotations

from sag_video.production_intelligence import SCORE_WEIGHTS, deterministic_range_score
from sag_video.repository import SuggestionRecord


def test_clip_quality_score_is_explainable_and_weighted():
    score = deterministic_range_score(
        text="How this works because every step produces a useful result.",
        start_ticks=0,
        end_ticks=10 * 120_000,
        features={"scene_ticks": [120_000, 480_000], "face_tracks": [
            {"time_ticks": 240_000, "center_x": .5, "center_y": .4, "confidence": .9},
        ]},
        content_profile="talking_head",
    )
    assert [component.name for component in score.components] == list(SCORE_WEIGHTS)
    assert {component.name: component.weight for component in score.components} == SCORE_WEIGHTS
    assert score.total == round(sum(component.weighted_score for component in score.components), 2)
    assert all(component.evidence for component in score.components)
    assert score.score_policy_version == "sag-clip-quality/1.0"


def test_canonical_production_mode_and_manual_range_scoring(client):
    initial = client.get("/api/projects/demo/production")
    assert initial.status_code == 200
    production = initial.json()["production"]
    assert production["workflow_mode"] == "repo_to_video"
    assert production["intake_stage"] == "evidence"

    changed = client.put("/api/projects/demo/production", json={
        "expected_revision": production["revision"],
        "workflow_mode": "source_to_shorts",
        "intake_stage": "analysis",
        "focused_candidate_id": "candidate_manual",
        "review_context": {"panel": "quality"},
    })
    assert changed.status_code == 200, changed.text
    saved = changed.json()["production"]
    assert saved["workflow_mode"] == "source_to_shorts"
    assert saved["focused_candidate_id"] == "candidate_manual"
    assert client.get("/api/projects/demo/repo-to-video/production").json()["production"] == saved

    scored = client.post("/api/projects/demo/shorts/score", json={
        "source_revision": 1,
        "start_ticks": 0,
        "end_ticks": 120_000,
        "content_profile": "screen_recording",
        "component_scores": {
            "hook": 90, "flow": 80, "value": 70, "delivery": 60,
            "visual_evidence": 50, "boundary_quality": 40,
        },
    })
    assert scored.status_code == 200, scored.text
    body = scored.json()
    assert body["historical"] is False
    assert body["score"]["total"] == 74
    assert body["score"]["content_profile"] == "screen_recording"


def test_feedback_brand_variant_broll_and_review_records(client):
    store = client.app.state.store
    store.create_suggestion(SuggestionRecord(
        id="suggestion_feedback", project_id="demo", source_revision=1,
        generator_kind="short_clip", state="pending", commands=[], reason="Candidate",
        evidence={"start_ticks": 0, "end_ticks": 120_000}, confidence=.7,
    ))
    feedback = client.post("/api/projects/demo/shorts/suggestions/suggestion_feedback/feedback", json={
        "decision": "rejected", "reasons": ["weak_hook", "bad_boundary"], "actor": "editor",
    })
    assert feedback.status_code == 201, feedback.text
    assert feedback.json()["feedback"]["score_policy_version"] == "sag-clip-quality/1.0"

    brand = client.put("/api/workspaces/demo/brand-kits/default", json={
        "expected_revision": 0,
        "colors": {"accent": "#47A99A"},
        "typography": {"family": "Noto Sans"},
        "caption_rules": {"template": "karaoke"},
    })
    assert brand.status_code == 200, brand.text
    assert brand.json()["brand_kit"]["revision"] == 1
    assert client.get("/api/workspaces/demo/brand-kits/default").status_code == 200

    variant = client.put("/api/projects/demo/variants/vertical", json={
        "expected_revision": 0, "master_revision": 1, "aspect_ratio": "9:16",
        "crop_overrides": {"clip_terminal": {"center_x": .4}},
    })
    assert variant.status_code == 200, variant.text
    assert variant.json()["variant"]["stale_overrides"] == []

    broll = client.post("/api/projects/demo/b-roll/search", json={"query": "terminal"})
    assert broll.status_code == 200, broll.text
    assert broll.json()["candidates"]
    candidate = broll.json()["candidates"][0]
    assert candidate["requires_human_approval"] is True
    decision = client.post(
        f"/api/projects/demo/b-roll/candidates/{candidate['id']}/decisions",
        json={"decision": "approved", "actor": "editor"},
    )
    assert decision.status_code == 201, decision.text
    assert decision.json()["inserted"] is False

    review = client.post("/api/projects/demo/review/decisions", json={
        "project_revision": 1, "subject_kind": "timeline", "subject_id": "demo",
        "decision": "approved", "actor": "editor",
    })
    assert review.status_code == 201, review.text
