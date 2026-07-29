import subprocess
from pathlib import Path

from sag_video.contracts import COMMAND_REGISTRY
from test_screenshot_capture import recipe_body, upload_screenshot


def silent_video(path: Path, *, duration: float = 1.0) -> Path:
    subprocess.run([
        "ffmpeg", "-nostdin", "-y", "-v", "error",
        "-f", "lavfi", "-i", f"color=c=0x123849:s=320x568:r=30:d={duration}",
        "-c:v", "libx264", "-pix_fmt", "yuv420p", "-an", "-movflags", "+faststart", str(path),
    ], check=True, capture_output=True, timeout=30)
    return path


def upload_video(client, path: Path, request_id: str) -> dict:
    response = client.post(
        "/api/projects/demo/assets/uploads",
        data={"request_id": request_id, "actor": "test"},
        files={"file": (path.name, path.read_bytes(), "video/mp4")},
    )
    assert response.status_code == 200, response.text
    return response.json()["asset"]


def approved_capture(client) -> dict:
    asset = upload_screenshot(client).json()["asset"]
    recipe = client.post("/api/projects/demo/screenshot-recipes", json=recipe_body()).json()["recipe"]
    capture = client.post("/api/projects/demo/screenshot-captures", json={
        "recipe_id": recipe["id"], "asset_id": asset["id"], "adapter": "android_screenshot",
        "checkpoint_id": "director-ready", "observed_labels": ["Storyboard"],
        "sensitive_content_status": "passed",
    }).json()["capture"]
    response = client.post(f"/api/projects/demo/screenshot-captures/{capture['id']}/decisions", json={
        "decision": "approved", "actor": "human-owner",
    })
    assert response.status_code == 201
    return response.json()["capture"]


def composite_body(capture: dict, plate: dict, output: dict) -> dict:
    return {
        "plate_asset_id": plate["id"], "source_capture_id": capture["id"],
        "composite_asset_id": output["id"], "tracking_report_sha256": "b" * 64,
        "source_crop": {"x": 0, "y": 100, "width": 720, "height": 1100},
        "tracking_method": "sift_ransac_homography", "frame_count": 30,
        "direct_tracked_frames": 30, "interpolated_frames": 0,
        "direct_tracking_ratio": 1, "min_inlier_count": 124, "min_inlier_ratio": .58,
        "min_opaque_coverage_pixels": 185000, "max_untracked_gap_frames": 0,
    }


def test_protected_composite_requires_review_then_exact_revision_insertion(client, tmp_path):
    declaration = COMMAND_REGISTRY["timeline.insert_protected_composite"]
    assert declaration.confirmation_policy == "exact_human_confirmation"
    assert "studio" in declaration.eligible_surfaces
    assert "mcp" not in declaration.eligible_surfaces
    capture = approved_capture(client)
    plate = upload_video(client, silent_video(tmp_path / "plate.mp4"), "plate-upload-0001")
    output = upload_video(client, silent_video(tmp_path / "composite.mp4"), "composite-upload-0001")

    created = client.post(
        "/api/projects/demo/protected-screen-composites",
        json=composite_body(capture, plate, output),
    )
    assert created.status_code == 201, created.text
    record = created.json()["composite"]
    assert record["approval_state"] == "pending"
    project = client.get("/api/projects/demo").json()["project"]
    bypass = client.post("/api/projects/demo/commands", json={
        "command": "timeline.insert_asset", "arguments": {"asset_id": output["id"]},
        "expected_revision": project["revision"], "request_id": "composite-generic-insert-bypass",
        "actor": "test",
    })
    assert bypass.status_code == 422
    assert "reviewed" in bypass.json()["detail"]
    pending = client.get("/api/projects/demo/protected-screen-composites").json()["composites"][0]
    assert pending["insertion_ready"] is False
    assert pending["stale"] is False

    decision = client.post(
        f"/api/projects/demo/protected-screen-composites/{record['id']}/decisions",
        json={"decision": "approved", "actor": "human-owner"},
    )
    assert decision.status_code == 201, decision.text
    approved = decision.json()["composite"]
    assert approved["approved_project_revision"] == client.get("/api/projects/demo").json()["project"]["revision"]
    assert approved["insertion_ready"] is True

    project = client.get("/api/projects/demo").json()["project"]
    arguments = {"composite_id": record["id"]}
    denied = client.post("/api/projects/demo/commands", json={
        "command": "timeline.insert_protected_composite", "arguments": arguments,
        "expected_revision": project["revision"], "request_id": "composite-insert-denied",
        "actor": "test",
    })
    assert denied.status_code == 200
    assert denied.json()["status"] == "denied"

    confirmation = client.post("/api/projects/demo/confirmations", json={
        "command": "timeline.insert_protected_composite", "arguments": arguments,
        "expected_revision": project["revision"],
    })
    assert confirmation.status_code == 200
    inserted = client.post("/api/projects/demo/commands", json={
        "command": "timeline.insert_protected_composite", "arguments": arguments,
        "expected_revision": project["revision"], "request_id": "composite-insert-approved",
        "actor": "test", "confirmation_id": confirmation.json()["id"],
    })
    assert inserted.status_code == 200, inserted.text
    assert inserted.json()["status"] == "committed"
    observation = inserted.json()["payload"]["observation"]
    assert observation["source_asset_sha256"] == record["source_asset_sha256"]
    assert observation["tracking_report_sha256"] == "b" * 64

    current = client.app.state.store.get_project("demo")
    item = current.item(observation["item_id"])
    assert item.kind == "protected_composite"
    assert item.protected_screen_composite_id == record["id"]
    active = client.get("/api/projects/demo/protected-screen-composites").json()["composites"][0]
    assert active["active"] is True
    assert active["insertion_ready"] is False
    composite_reject = client.post(
        f"/api/projects/demo/protected-screen-composites/{record['id']}/decisions",
        json={"decision": "rejected", "actor": "human-owner"},
    )
    assert composite_reject.status_code == 409
    source_reject = client.post(
        f"/api/projects/demo/screenshot-captures/{capture['id']}/decisions",
        json={"decision": "rejected", "actor": "human-owner"},
    )
    assert source_reject.status_code == 409

    for track in current.tracks:
        track.items = [entry for entry in track.items if entry.id == item.id]
    spec = client.app.state.renderer.build_spec(current)
    protected = next(entry for entry in spec.media if entry.kind == "protected_composite")
    assert protected.has_audio is False
    assert protected.protected_composite_lineage["source_asset_sha256"] == record["source_asset_sha256"]
    assert protected.protected_composite_lineage["plate_asset_sha256"] == record["plate_asset_sha256"]
    command = client.app.state.renderer._command(
        spec, current, tmp_path / "protected-render.mp4", tmp_path,
    )
    assert "-an" in command


def test_protected_composite_rejects_weak_tracking(client, tmp_path):
    capture = approved_capture(client)
    plate = upload_video(client, silent_video(tmp_path / "weak-plate.mp4"), "weak-plate-upload")
    output = upload_video(client, silent_video(tmp_path / "weak-output.mp4"), "weak-output-upload")
    body = composite_body(capture, plate, output)
    body.update({"direct_tracked_frames": 20, "interpolated_frames": 10, "direct_tracking_ratio": 20 / 30})
    response = client.post("/api/projects/demo/protected-screen-composites", json=body)
    assert response.status_code == 409
    assert "coverage" in response.json()["detail"]
