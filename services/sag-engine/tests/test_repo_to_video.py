import pytest
from fastapi.testclient import TestClient

from sag_video.app import Settings, create_app
from sag_video.models import ReceiptStatus
from sag_video.repo_to_video import (
    CreativeBrief,
    RepoVideoRequest,
    RepositoryEvidence,
    StoryboardScene,
    aspect_ratio_for_platform,
    creative_director_prompt,
    evidence_prompt,
    evidence_revision,
    parse_creative_brief,
    parse_storyboard,
    redact,
    scene_generation_prompt,
    scene_negative_prompt,
    storyboard_response_schema,
)


def test_repository_url_is_bounded_to_github():
    request = RepoVideoRequest(repository_url="https://github.com/example/project.git")
    assert request.repository_url == "https://github.com/example/project"
    with pytest.raises(ValueError):
        RepoVideoRequest(repository_url="https://evil.example/example/project")


def test_repository_evidence_redacts_secrets():
    assert "[REDACTED]" in redact("API_KEY=AIza123456789012345678901234")
    assert "AIza" not in redact("AIza123456789012345678901234")


def test_storyboard_prompt_has_bounded_evidence():
    request = RepoVideoRequest(repository_url="https://github.com/example/project")
    prompt = evidence_prompt(request, RepositoryEvidence(repository_url=request.repository_url, ref="main", name="example/project", readme="README"))
    assert "example/project" in prompt
    assert "scene id must start with scene_" in prompt
    assert "Use 8 to 10 scenes of 4 to 8 seconds each" in prompt
    assert "Provider aspect ratio: 9:16" in prompt
    assert len(prompt) < 30000


def test_storyboard_requires_matching_evidence_revision():
    evidence = RepositoryEvidence(repository_url="https://github.com/example/project", ref="main", name="example/project")
    raw = '{"title":"Demo","hook":"Try it","call_to_action":"Clone it","evidence_revision":"wrong","scenes":[{"id":"scene_intro","start_seconds":0,"duration_seconds":5,"purpose":"hook","narration":"Try it","visual_direction":"show it","evidence_refs":["README"]}]}'
    with pytest.raises(ValueError, match="evidence revision"):
        parse_storyboard(raw, evidence=evidence)


def test_creative_director_brief_is_structured_and_evidence_bound():
    evidence = RepositoryEvidence(repository_url="https://github.com/example/project", ref="main", name="example/project")
    request = RepoVideoRequest(repository_url=evidence.repository_url, creative_instructions="Make the hook energetic")
    assert "Make the hook energetic" in creative_director_prompt(request, evidence)
    raw = '{"title":"Demo","logline":"A factual demo","audience_promise":"Understand the project","tone":"energetic","visual_language":"clean UI","narrative_arc":["hook","proof","cta"],"omni_prompt":"show the proof","veo_prompt":"cinematic terminal","music_prompt":"minimal pulse","narration_guidance":"clear","evidence_revision":"' + evidence_revision(evidence) + '"}'
    brief = parse_creative_brief(raw, evidence=evidence)
    assert brief.narrative_arc == ["hook", "proof", "cta"]


def test_official_prompt_anatomy_is_encoded_for_omni_and_veo():
    brief = CreativeBrief(
        title="Demo", logline="Factual demo", audience_promise="Understand it", tone="precise",
        visual_language="dark developer studio, crisp UI, restrained cyan accents",
        narrative_arc=["hook", "proof", "cta"],
        omni_prompt="A stable workstation and terminal anchor every shot; slow dolly movement and soft key light.",
        veo_prompt="A controlled cinematic developer workstation with a readable terminal and slow dolly movement.",
        music_prompt="restrained pulse", narration_guidance="clear", evidence_revision="evidence-1",
    )
    scene = StoryboardScene(
        id="scene_proof", start_seconds=0, duration_seconds=8, purpose="show proof",
        narration="The engine verifies generated media.",
        visual_direction="Medium shot of a developer triggering a verified media operation in the Studio UI.",
        evidence_refs=["README: verification"], generation_model="gemini-omni-flash-preview",
    )
    prompt = scene_generation_prompt(scene, brief, aspect_ratio="9:16")
    assert "Subject, action, scene, and context" in prompt
    assert "single continuous, unbroken scene" in prompt
    assert "Native ambience" in prompt
    assert "9:16" in prompt
    assert "README: verification" in prompt
    assert "no dialogue" not in scene_negative_prompt(aspect_ratio="9:16").lower()
    assert "unreadable interface text" in scene_negative_prompt(aspect_ratio="9:16")
    assert aspect_ratio_for_platform("youtube_16_9") == "16:9"
    assert aspect_ratio_for_platform("youtube_shorts") == "9:16"


def test_storyboard_requires_evidence_refs_and_fits_requested_duration():
    evidence = RepositoryEvidence(repository_url="https://github.com/example/project", ref="main", name="example/project")
    revision = evidence_revision(evidence)
    without_refs = '{"title":"Demo","hook":"Try it","call_to_action":"Clone it","evidence_revision":"' + revision + '","scenes":[{"id":"scene_intro","start_seconds":0,"duration_seconds":5,"purpose":"hook","narration":"Try it","visual_direction":"show it"}]}'
    with pytest.raises(ValueError, match="evidence_refs"):
        parse_storyboard(without_refs, evidence=evidence, requested_duration_seconds=60)
    too_long = '{"title":"Demo","hook":"Try it","call_to_action":"Clone it","evidence_revision":"' + revision + '","scenes":[{"id":"scene_intro","start_seconds":55,"duration_seconds":10,"purpose":"hook","narration":"Try it","visual_direction":"show it","evidence_refs":["README"]}]}'
    with pytest.raises(ValueError, match="requested production duration"):
        parse_storyboard(too_long, evidence=evidence, requested_duration_seconds=60)


def test_storyboard_rejects_evidence_paths_outside_collected_snapshot():
    evidence = RepositoryEvidence(
        repository_url="https://github.com/example/project", ref="main", name="example/project",
        files=["README.md", "src/engine.py"],
    )
    revision = evidence_revision(evidence)
    raw = '{"title":"Demo","hook":"Try it","call_to_action":"Clone it","evidence_revision":"' + revision + '","scenes":[{"id":"scene_intro","start_seconds":0,"duration_seconds":5,"purpose":"hook","narration":"Try it","visual_direction":"show it","evidence_refs":["src/missing.py"]}]}'
    with pytest.raises(ValueError, match="absent from collected evidence"):
        parse_storyboard(raw, evidence=evidence, requested_duration_seconds=60)


def test_storyboard_schema_limits_citations_to_collected_evidence():
    evidence = RepositoryEvidence(
        repository_url="https://github.com/example/project", ref="main", name="example/project",
        files=["README.md", "src/engine.py"], manifests={"package.json": "{}"},
    )
    schema = storyboard_response_schema(evidence)
    evidence_items = schema["$defs"]["StoryboardScene"]["properties"]["evidence_refs"]["items"]
    assert evidence_items["enum"] == ["README.md", "package.json", "src/engine.py"]


def test_trusted_web_proxy_requires_exact_human_confirmation(tmp_path):
    app = create_app(Settings(
        database_path=str(tmp_path / "sag.db"), artifact_dir=str(tmp_path / "artifacts"),
        media_dir=str(tmp_path / "media"), proxy_dir=str(tmp_path / "proxy"),
        service_token="trusted-web", start_analysis_worker=False, start_render_worker=False,
    ))
    project = app.state.store.create_project("Director test", "landscape_1080p", "workspace-1")
    receipt = app.state.store.create_receipt(
        project_id=project.id, command="media.propose_storyboard", status=ReceiptStatus.AWAITING_USER_CONSENT,
        request_id="storyboard_confirmation_test", actor="browser", project_revision=project.revision,
        payload={"evidence_revision": "evidence-1"},
    )
    service_headers = {"x-sag-service-token": "trusted-web", "x-sag-workspace-id": "workspace-1"}
    confirmation_id = "human-confirmation-1234"
    body = {"receipt_id": receipt.id, "expected_revision": project.revision, "confirmation_id": confirmation_id}
    with TestClient(app) as client:
        denied = client.post(f"/api/projects/{project.id}/repo-to-video/storyboard/commit", headers=service_headers, json=body)
        assert denied.status_code == 403
        generation_denied = client.post(
            f"/api/projects/{project.id}/repo-to-video/generate",
            headers={**service_headers, "x-sag-human-confirmation": confirmation_id},
            json={
                "storyboard_receipt_id": receipt.id,
                "storyboard": {
                    "title": "Demo", "hook": "Hook", "call_to_action": "Act", "evidence_revision": "evidence-1",
                    "scenes": [{
                        "id": "scene_one", "start_seconds": 0, "duration_seconds": 5, "purpose": "proof",
                        "narration": "Proof", "visual_direction": "Static terminal", "evidence_refs": ["README.md"],
                        "generation_model": "gemini-omni-flash-preview",
                    }],
                },
                "creative_brief": {
                    "title": "Demo", "logline": "Proof", "audience_promise": "Learn", "tone": "precise",
                    "visual_language": "clean", "narrative_arc": ["hook", "proof", "cta"],
                    "omni_prompt": "clean UI", "veo_prompt": "clean UI", "music_prompt": "pulse",
                    "narration_guidance": "clear", "evidence_revision": "evidence-1",
                },
                "expected_revision": project.revision, "confirmation_id": confirmation_id, "aspect_ratio": "9:16",
            },
        )
        assert generation_denied.status_code == 409
        assert "not human-approved" in generation_denied.json()["detail"]
        accepted = client.post(
            f"/api/projects/{project.id}/repo-to-video/storyboard/commit",
            headers={**service_headers, "x-sag-human-confirmation": confirmation_id}, json=body,
        )
        assert accepted.status_code == 200
        assert accepted.json()["receipt"]["status"] == "committed"
        events = client.get(f"/api/projects/{project.id}/runtime/events?cursor=0", headers=service_headers)
        assert events.status_code == 200
        assert any(
            event["kind"] == "receipt.transitioned"
            and event["payload"]["receipt_id"] == receipt.id
            and event["payload"]["status"] == "committed"
            for event in events.json()["events"]
        )
