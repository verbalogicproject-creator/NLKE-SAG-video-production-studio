import hashlib
import time
from pathlib import Path

from media_fixtures import tiny_video
from sag_video.models import ObservationContract
from sag_video.observer import observe_artifact


TERMINAL = {"observed_success", "observed_failure", "execution_failed", "cancelled", "timeout", "interrupted"}


def _wait_for_job(client, job_id: str, timeout: float = 15) -> dict:
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        response = client.get(f"/api/jobs/{job_id}")
        assert response.status_code == 200
        job = response.json()
        if job["state"] in TERMINAL:
            return job
        time.sleep(.1)
    raise AssertionError(f"render job {job_id} did not finish")


def _real_project(client, tmp_path: Path) -> tuple[dict, dict]:
    project = client.post(
        "/api/projects", json={"name": "Verified output", "preset": "preview_540p"}
    ).json()["project"]
    source = tiny_video(tmp_path / "real-source.mp4", duration=.7)
    imported = client.post(
        f"/api/projects/{project['id']}/assets/uploads",
        data={"request_id": "render-upload-0001", "actor": "test"},
        files={"file": (source.name, source.read_bytes(), "video/mp4")},
    ).json()
    asset = imported["asset"]
    inserted = client.post(
        f"/api/projects/{project['id']}/commands",
        json={
            "command": "timeline.insert_asset", "arguments": {"asset_id": asset["id"]},
            "expected_revision": imported["receipt"]["project_revision"],
            "request_id": "render-insert-0001", "actor": "test",
        },
    ).json()
    project["revision"] = inserted["project_revision"]
    return project, asset


def test_real_media_render_is_async_persistent_and_observed(client, tmp_path):
    project, _ = _real_project(client, tmp_path)
    response = client.post(
        f"/api/projects/{project['id']}/renders",
        json={"project_revision": project["revision"], "request_id": "render-real-0001", "actor": "test"},
    )
    assert response.status_code == 200
    accepted = response.json()
    assert accepted["status"] == "accepted"
    assert accepted["payload"]["job_id"]

    job = _wait_for_job(client, accepted["payload"]["job_id"])
    assert job["state"] == "observed_success"
    assert job["progress"] == 1
    assert job["result_artifact_id"]

    receipt = client.get(f"/api/receipts/{accepted['id']}").json()
    assert receipt["status"] == "observed_success"
    assert [entry["status"] for entry in receipt["payload"]["transitions"]] == [
        "accepted", "dispatched", "rendering", "artifact_written",
        "awaiting_observation", "observed_success",
    ]
    findings = {entry["code"]: entry for entry in receipt["payload"]["observation"]["findings"]}
    assert findings["artifact_hash_contract"]["passed"] is True
    assert findings["video_stream_contract"]["passed"] is True
    assert findings["frame_rate_contract"]["passed"] is True
    assert findings["audio_stream_contract"]["passed"] is True
    assert findings["representative_frame_readable"]["passed"] is True

    artifact = client.get(receipt["payload"]["artifact_url"])
    assert artifact.status_code == 200
    assert hashlib.sha256(artifact.content).hexdigest() == receipt["payload"]["artifact_sha256"]


def test_unmaterialized_proof_slates_fail_before_dispatch(client):
    response = client.post(
        "/api/projects/demo/renders",
        json={"project_revision": 1, "request_id": "render-placeholder-0001", "actor": "test"},
    )
    assert response.status_code == 422
    assert response.json()["code"] == "render_spec_rejected"
    assert "observed-valid" in response.json()["detail"]


def test_two_trimmed_clips_and_unicode_title_render_from_textfile(client, tmp_path):
    source = tiny_video(tmp_path / "two-clips.mp4", duration=.8)
    imported = client.post(
        "/api/projects/demo/assets/uploads",
        data={"request_id": "render-title-upload", "actor": "test"},
        files={"file": (source.name, source.read_bytes(), "video/mp4")},
    ).json()
    revision = imported["receipt"]["project_revision"]

    def command(name, arguments, request_id):
        nonlocal revision
        body = {
            "command": name, "arguments": arguments, "expected_revision": revision,
            "request_id": request_id, "actor": "test",
        }
        if name == "timeline.delete_item":
            confirmation = client.post("/api/projects/demo/confirmations", json={
                "command": name, "arguments": arguments, "expected_revision": revision,
            }).json()
            body["confirmation_id"] = confirmation["id"]
        result = client.post("/api/projects/demo/commands", json=body)
        assert result.status_code == 200, result.text
        payload = result.json()
        revision = payload["project_revision"]
        return payload

    command("timeline.delete_item", {"item_id": "clip_terminal"}, "render-delete-placeholder-1")
    command("timeline.delete_item", {"item_id": "clip_result"}, "render-delete-placeholder-2")
    first = command("timeline.insert_asset", {"asset_id": imported["asset"]["id"]}, "render-insert-clip-1")
    second = command(
        "timeline.insert_asset", {"asset_id": imported["asset"]["id"], "start_ticks": 48000},
        "render-insert-clip-2",
    )
    command(
        "timeline.trim_clip",
        {"item_id": first["payload"]["observation"]["item_id"], "duration_ticks": 48000,
         "source_in_ticks": 0, "source_out_ticks": 48000},
        "render-trim-clip-1",
    )
    command(
        "timeline.trim_clip",
        {"item_id": second["payload"]["observation"]["item_id"], "duration_ticks": 48000,
         "source_in_ticks": 12000, "source_out_ticks": 60000},
        "render-trim-clip-2",
    )
    command(
        "timeline.set_title", {"item_id": "title_intro", "text": "Cut: שלום, 100% ready?"},
        "render-unicode-title",
    )
    command(
        "timeline.set_title_transform",
        {"item_id": "title_intro", "x": 60, "y": 56, "width": 410, "height": 86},
        "render-safe-title",
    )
    accepted = client.post("/api/projects/demo/renders", json={
        "project_revision": revision, "request_id": "render-two-clips-0001", "actor": "test",
    }).json()
    job = _wait_for_job(client, accepted["payload"]["job_id"])
    assert job["state"] == "observed_success"
    receipt = client.get(f"/api/receipts/{accepted['id']}").json()
    safe = next(entry for entry in receipt["payload"]["observation"]["findings"] if entry["code"] == "title_safe_area")
    assert safe["passed"] is True


def test_missing_artifact_never_becomes_success(tmp_path: Path):
    result = observe_artifact(
        ObservationContract(
            project_id="demo", project_revision=1,
            artifact_path=str(tmp_path / "missing.mp4"), artifact_sha256="0" * 64,
            width=960, height=540, duration_seconds=6, fps=30,
            title_id="title_intro", title_active_seconds=.9,
            safe_margin_x=48, safe_margin_y=27, marker_rgb=(233, 64, 255),
        )
    )
    assert result.passed is False
    assert result.findings[0].code == "artifact_exists"
