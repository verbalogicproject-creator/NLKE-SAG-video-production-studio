import pytest
from fastapi.testclient import TestClient

import sag_video.app as app_module
from sag_video.app import Settings, create_app
from sag_video.generative import ProviderOperation
from sag_video.models import ReceiptStatus
from sag_video.repo_to_video import (
    CreativeBrief,
    RepoStoryboard,
    RepoVideoRequest,
    RepositoryEvidence,
    StoryboardScene,
    SceneSpatialLayout,
    StoryboardRegion,
    aspect_ratio_for_platform,
    creative_director_prompt,
    evidence_prompt,
    evidence_revision,
    parse_creative_brief,
    parse_storyboard,
    prompt_studio_preview,
    PromptStudioPreviewRequest,
    redact,
    resolved_generation_prompt_revision,
    scene_generation_prompt,
    scene_negative_prompt,
    storyboard_response_schema,
)


def test_repository_url_is_bounded_to_github():
    request = RepoVideoRequest(repository_url="https://github.com/example/project.git")
    assert request.repository_url == "https://github.com/example/project"
    with pytest.raises(ValueError):
        RepoVideoRequest(repository_url="https://evil.example/example/project")


def test_prompt_studio_contract_and_preview_are_read_only(client):
    contract = client.get("/api/contract").json()
    assert contract["prompt_studio_schema_version"] == "sag-prompt-studio/0.1"
    assert "PromptStudioPreviewRequest" in contract["prompt_studio_schemas"]
    before = len(client.get("/api/projects/demo/receipts").json())
    response = client.post("/api/projects/demo/repo-to-video/prompts/preview", json={
        "creative_instruction": "Create an evidence-bound developer tutorial.",
        "aspect_ratio": "9:16",
    })
    assert response.status_code == 200, response.text
    body = response.json()
    assert body["modules"][0]["id"] == "direction.instruction"
    assert body["models"]
    assert len(body["resolved_prompt_revision"]) == 64
    after = len(client.get("/api/projects/demo/receipts").json())
    assert after == before


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


def test_scene_spatial_contract_preserves_authentic_regions_in_generation_prompt():
    brief = CreativeBrief(
        title="Demo", logline="Factual demo", audience_promise="Understand it", tone="precise",
        visual_language="authentic product footage", narrative_arc=["hook", "proof", "cta"],
        omni_prompt="Preserve the supplied Studio capture.", veo_prompt="Controlled motion around the supplied frame.",
        music_prompt="pulse", narration_guidance="clear", evidence_revision="evidence-1",
    )
    layout = SceneSpatialLayout(regions=[
        StoryboardRegion(
            id="region_studio", purpose="authentic_reference", behavior="preserve",
            x=0.05, y=0.1, width=0.9, height=0.65, source_asset_id="asset_studio_capture",
            evidence_refs=["README.md"],
        ),
        StoryboardRegion(
            id="region_motion", purpose="safe_motion", behavior="animate",
            x=0.05, y=0.78, width=0.9, height=0.12,
        ),
    ])
    scene = StoryboardScene(
        id="scene_authentic", start_seconds=0, duration_seconds=6, purpose="show the real Studio",
        narration="The Studio exposes a governed timeline.", visual_direction="Use the supplied Studio screenshot.",
        evidence_refs=["README.md"], spatial_layout=layout,
    )
    prompt = scene_generation_prompt(scene, brief, aspect_ratio="9:16")
    assert "Spatial contract" in prompt
    assert "region_studio: authentic_reference, preserve" in prompt
    assert "source asset asset_studio_capture" in prompt
    with pytest.raises(ValueError, match="source asset"):
        StoryboardRegion(
            id="region_invalid", purpose="authentic_reference", x=0, y=0, width=1, height=1,
        )


def test_prompt_studio_resolves_the_exact_generation_bundle_revision():
    brief = CreativeBrief(
        title="Demo", logline="Factual demo", audience_promise="Understand it", tone="precise",
        visual_language="authentic Studio", narrative_arc=["hook", "proof", "cta"],
        omni_prompt="Preserve the real Studio capture.", veo_prompt="Use controlled camera motion.",
        music_prompt="restrained pulse", narration_guidance="calm and direct", evidence_revision="evidence-1",
    )
    storyboard = RepoStoryboard(
        title="Demo", hook="See the proof", call_to_action="Inspect the repository", evidence_revision="evidence-1",
        scenes=[StoryboardScene(
            id="scene_proof", start_seconds=0, duration_seconds=6, purpose="show proof",
            narration="The engine verifies generated media.", visual_direction="Show the authentic Studio.",
            evidence_refs=["README.md"], generation_model="gemini-omni-flash-preview",
        )],
    )
    preview = prompt_studio_preview(PromptStudioPreviewRequest(
        creative_instruction="Build a factual repository tutorial.", creative_brief=brief,
        storyboard=storyboard, aspect_ratio="9:16", active_scene_id="scene_proof",
    ))
    modules = {module["id"]: module for module in preview["modules"]}
    assert preview["resolved_prompt_revision"] == resolved_generation_prompt_revision(
        storyboard, brief, aspect_ratio="9:16",
    )
    assert "Spatial" not in modules["generation.resolved_scene"]["content"]
    assert modules["generation.resolved_scene"]["dispatch"] == "derived_provider_input"
    assert modules["generation.narration_script"]["content"] == "The engine verifies generated media."
    assert "Current TTS dispatch" in modules["planning.narration_guidance"]["warnings"][0]

    changed = brief.model_copy(update={"omni_prompt": "A different continuity direction."})
    changed_preview = prompt_studio_preview(PromptStudioPreviewRequest(
        creative_brief=changed, storyboard=storyboard, aspect_ratio="9:16",
    ))
    assert changed_preview["resolved_prompt_revision"] != preview["resolved_prompt_revision"]


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
        payload={
            "evidence_revision": "evidence-1", "allowed_evidence_refs": ["README.md"],
            "requested_duration_seconds": 60,
        },
    )
    service_headers = {"x-sag-service-token": "trusted-web", "x-sag-workspace-id": "workspace-1"}
    confirmation_id = "human-confirmation-1234"
    reviewed_storyboard = {
        "title": "Demo", "hook": "Hook", "call_to_action": "Act", "evidence_revision": "evidence-1",
        "scenes": [{
            "id": "scene_one", "start_seconds": 0, "duration_seconds": 5, "purpose": "proof",
            "narration": "Reviewed proof", "visual_direction": "Static terminal", "evidence_refs": ["README.md"],
            "generation_model": "gemini-omni-flash-preview",
        }],
    }
    body = {
        "receipt_id": receipt.id, "expected_revision": project.revision,
        "confirmation_id": confirmation_id, "storyboard": reviewed_storyboard,
    }
    with TestClient(app) as client:
        denied = client.post(f"/api/projects/{project.id}/repo-to-video/storyboard/commit", headers=service_headers, json=body)
        assert denied.status_code == 403
        generation_denied = client.post(
            f"/api/projects/{project.id}/repo-to-video/generate",
            headers={**service_headers, "x-sag-human-confirmation": confirmation_id},
            json={
                "storyboard_receipt_id": receipt.id,
                "storyboard": reviewed_storyboard,
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
        assert accepted.json()["receipt"]["payload"]["storyboard"]["scenes"][0]["narration"] == "Reviewed proof"
        events = client.get(f"/api/projects/{project.id}/runtime/events?cursor=0", headers=service_headers)
        assert events.status_code == 200
        assert any(
            event["kind"] == "receipt.transitioned"
            and event["payload"]["receipt_id"] == receipt.id
            and event["payload"]["status"] == "committed"
            for event in events.json()["events"]
        )


def test_generation_persists_partial_dispatch_and_retry_is_idempotent(tmp_path, monkeypatch):
    class PartialProvider:
        video_calls = 0

        def start_video(self, request):
            self.video_calls += 1
            return ProviderOperation(
                request_id="gen_video", model=request.model, operation_name="interactions/video-one",
            )

        def start_audio(self, request):
            raise RuntimeError("provider_failure: audio model unavailable")

    provider = PartialProvider()
    monkeypatch.setattr(app_module, "GoogleGenerativeAdapter", lambda: provider)
    app = create_app(Settings(
        database_path=str(tmp_path / "sag.db"), artifact_dir=str(tmp_path / "artifacts"),
        media_dir=str(tmp_path / "media"), proxy_dir=str(tmp_path / "proxy"),
        service_token="trusted-web", start_analysis_worker=False, start_render_worker=False,
    ))
    project = app.state.store.create_project("Dispatch test", "landscape_1080p", "workspace-1")
    storyboard = {
        "title": "Demo", "hook": "Hook", "call_to_action": "Act", "evidence_revision": "evidence-1",
        "scenes": [{
            "id": "scene_one", "start_seconds": 0, "duration_seconds": 5, "purpose": "proof",
            "narration": "Reviewed proof", "visual_direction": "Static terminal", "evidence_refs": ["README.md"],
            "generation_model": "gemini-omni-flash-preview",
        }],
    }
    receipt = app.state.store.create_receipt(
        project_id=project.id, command="media.propose_storyboard", status=ReceiptStatus.COMMITTED,
        request_id="approved_storyboard", actor="browser", project_revision=project.revision,
        payload={"evidence_revision": "evidence-1", "storyboard": storyboard},
    )
    confirmation_id = "human-confirmation-1234"
    body = {
        "storyboard_receipt_id": receipt.id, "storyboard": storyboard,
        "creative_brief": {
            "title": "Demo", "logline": "Proof", "audience_promise": "Learn", "tone": "precise",
            "visual_language": "clean", "narrative_arc": ["hook", "proof", "cta"],
            "omni_prompt": "clean UI", "veo_prompt": "clean UI", "music_prompt": "pulse",
            "narration_guidance": "clear", "evidence_revision": "evidence-1",
        },
        "expected_revision": project.revision, "confirmation_id": confirmation_id, "aspect_ratio": "9:16",
    }
    headers = {
        "x-sag-service-token": "trusted-web", "x-sag-workspace-id": "workspace-1",
        "x-sag-human-confirmation": confirmation_id,
    }
    with TestClient(app) as client:
        first = client.post(f"/api/projects/{project.id}/repo-to-video/generate", headers=headers, json=body)
        assert first.status_code == 202
        assert first.json()["receipt"]["status"] == "execution_failed"
        assert first.json()["receipt"]["payload"]["dispatch_state"] == "failed"
        assert first.json()["receipt"]["payload"]["operations"][0]["operation_name"] == "interactions/video-one"
        assert first.json()["partial"] is True
        second = client.post(f"/api/projects/{project.id}/repo-to-video/generate", headers=headers, json=body)
        assert second.status_code == 202
        assert second.json()["idempotent"] is True
        assert provider.video_calls == 1
        changed_body = {
            **body,
            "creative_brief": {**body["creative_brief"], "omni_prompt": "a changed clean UI direction"},
        }
        third = client.post(f"/api/projects/{project.id}/repo-to-video/generate", headers=headers, json=changed_body)
        assert third.status_code == 202
        assert third.json()["receipt"]["id"] != first.json()["receipt"]["id"]
        assert third.json()["receipt"]["payload"]["resolved_prompt_revision"] != first.json()["receipt"]["payload"]["resolved_prompt_revision"]
        assert provider.video_calls == 2
