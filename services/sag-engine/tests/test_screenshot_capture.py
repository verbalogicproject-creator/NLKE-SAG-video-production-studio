from io import BytesIO

from PIL import Image


def png_bytes() -> bytes:
    output = BytesIO()
    Image.new("RGB", (720, 1280), "#102030").save(output, format="PNG")
    return output.getvalue()


def upload_screenshot(client):
    return client.post(
        "/api/projects/demo/assets/uploads",
        data={"request_id": "screenshot-upload-0001", "actor": "test"},
        files={"file": ("studio.png", png_bytes(), "image/png")},
    )


def recipe_body():
    return {
        "name": "Director evidence checkpoint",
        "allowed_origin": "https://sag.example",
        "viewport_width": 1080,
        "viewport_height": 1920,
        "steps": [
            {"action": "open_project", "target": "demo"},
            {"action": "select_tab", "target": "storyboard"},
            {"action": "wait_for_checkpoint", "target": "director-ready"},
            {"action": "capture", "target": "viewport"},
        ],
        "checkpoint_id": "director-ready",
        "expected_labels": ["Storyboard"],
        "excluded_labels": ["HF_TOKEN"],
        "evidence_claim_ids": ["claim_storyboard"],
        "source_commit": "a" * 40,
        "application_revision": "studio-1",
    }


def test_screenshot_recipe_capture_review_and_visual_proof(client):
    uploaded = upload_screenshot(client)
    assert uploaded.status_code == 200
    asset = uploaded.json()["asset"]
    assert asset["kind"] == "image"
    assert asset["mime_type"] == "image/png"
    assert asset["observation_summary"]["incoming_sha256"]
    assert asset["observation_summary"]["canonical_sha256"] == asset["sha256"]

    recipe_response = client.post("/api/projects/demo/screenshot-recipes", json=recipe_body())
    assert recipe_response.status_code == 201
    recipe = recipe_response.json()["recipe"]
    capture_response = client.post("/api/projects/demo/screenshot-captures", json={
        "recipe_id": recipe["id"], "asset_id": asset["id"], "adapter": "android_screenshot",
        "checkpoint_id": "director-ready", "observed_labels": ["Storyboard"],
        "sensitive_content_status": "passed", "observation_report": {"selector_checks": "passed"},
    })
    assert capture_response.status_code == 201
    capture = capture_response.json()["capture"]
    assert capture["asset_sha256"] == asset["sha256"]
    assert capture["approval_state"] == "pending"
    assert capture["adapter"] == "android_screenshot"

    decision = client.post(f"/api/projects/demo/screenshot-captures/{capture['id']}/decisions", json={
        "decision": "approved", "actor": "human-owner",
    })
    assert decision.status_code == 201
    assert decision.json()["capture"]["approval_state"] == "approved"

    proof = client.post("/api/projects/demo/visual-proof-plans", json={
        "source_commit": "a" * 40, "evidence_revision": "evidence-1",
        "claims": [{
            "id": "claim_storyboard", "claim": "SAG creates a reviewable storyboard",
            "capture_id": capture["id"], "duration_ticks": 600000,
        }],
    })
    assert proof.status_code == 201


def test_screenshot_recipe_rejects_unbounded_or_unverified_capture(client):
    bad = recipe_body()
    bad["allowed_origin"] = "http://public.example"
    assert client.post("/api/projects/demo/screenshot-recipes", json=bad).status_code == 422

    asset = upload_screenshot(client).json()["asset"]
    recipe = client.post("/api/projects/demo/screenshot-recipes", json=recipe_body()).json()["recipe"]
    denied = client.post("/api/projects/demo/screenshot-captures", json={
        "recipe_id": recipe["id"], "asset_id": asset["id"], "adapter": "playwright",
        "checkpoint_id": "director-ready", "observed_labels": ["Storyboard", "HF_TOKEN"],
        "sensitive_content_status": "passed",
    })
    assert denied.status_code == 409


def test_image_can_be_inserted_as_a_timed_overlay_and_frozen_for_render(client):
    asset = upload_screenshot(client).json()["asset"]
    project = client.get("/api/projects/demo").json()["project"]
    inserted = client.post("/api/projects/demo/commands", json={
        "command": "timeline.insert_asset",
        "arguments": {"asset_id": asset["id"], "duration_ticks": 600000},
        "expected_revision": project["revision"], "request_id": "insert-screenshot-0001", "actor": "test",
    })
    assert inserted.status_code == 200
    assert inserted.json()["status"] == "committed"
    current = client.app.state.store.get_project("demo")
    item = current.item(inserted.json()["payload"]["observation"]["item_id"])
    assert item.kind == "image"
    assert item.track_id == "track_titles"
    current.tracks[0].items = []
    spec = client.app.state.renderer.build_spec(current)
    assert any(media.kind == "image" and media.duration_seconds == 5 for media in spec.media)
    command = client.app.state.renderer._command(spec, current, client.app.state.renderer.artifact_dir / "test.mp4", client.app.state.renderer.artifact_dir)
    assert "-loop" in command


def test_title_can_be_created_through_the_canonical_command_gateway(client):
    project = client.get("/api/projects/demo").json()["project"]
    created = client.post("/api/projects/demo/commands", json={
        "command": "timeline.create_title",
        "arguments": {
            "text": "Proof before promotion", "start_ticks": 0,
            "duration_ticks": 360000, "x": 60, "y": 900,
            "width": 960, "height": 180, "color": "#101820",
        },
        "expected_revision": project["revision"], "request_id": "create-title-0001", "actor": "test",
    })
    assert created.status_code == 200, created.text
    assert created.json()["status"] == "committed"
    item_id = created.json()["payload"]["observation"]["item_id"]
    item = client.app.state.store.get_project("demo").item(item_id)
    assert item.kind == "title"
    assert item.text == "Proof before promotion"

    recolored = client.post("/api/projects/demo/commands", json={
        "command": "timeline.set_title_transform",
        "arguments": {"item_id": item_id, "color": "#0E7490"},
        "expected_revision": created.json()["project_revision"],
        "request_id": "recolor-title-0001", "actor": "test",
    })
    assert recolored.status_code == 200, recolored.text
    assert recolored.json()["payload"]["observation"]["color"] == "#0E7490"
