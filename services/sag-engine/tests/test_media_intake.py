import hashlib
from io import BytesIO

from media_fixtures import browser_capture, tiny_audio, tiny_video


def _upload(client, path, request_id="upload-request-0001", name=None):
    return client.post(
        "/api/projects/demo/assets/uploads",
        data={"request_id": request_id, "actor": "test"},
        files={"file": (name or path.name, path.read_bytes(), "application/octet-stream")},
    )


def test_video_import_is_observed_and_serves_derivatives(client, tmp_path):
    source = tiny_video(tmp_path / "sample.mp4")
    response = _upload(client, source)
    assert response.status_code == 200
    result = response.json()
    assert result["receipt"]["status"] == "observed_success"
    assert [entry["status"] for entry in result["receipt"]["payload"]["transitions"]] == [
        "accepted", "awaiting_observation", "observed_success"
    ]
    asset = result["asset"]
    assert asset["kind"] == "video"
    assert asset["intake_status"] == "observed_valid"
    assert asset["sha256"] and asset["byte_size"] > 0
    assert asset["width"] == 320 and asset["height"] == 180
    assert asset["duration_ticks"] > 0
    assert asset["proxy_asset_id"] and asset["thumbnail_asset_id"]
    proxy_url = f"/api/projects/demo/assets/{asset['id']}/proxy"
    assert client.get(proxy_url).status_code == 200
    ranged = client.get(proxy_url, headers={"Range": "bytes=0-127"})
    assert ranged.status_code == 206
    assert len(ranged.content) == 128
    assert client.get(f"/api/projects/demo/assets/{asset['id']}/thumbnail").status_code == 200
    public = client.get(f"/api/projects/demo/assets/{asset['id']}").text
    assert str(tmp_path) not in public


def test_audio_import_and_idempotent_retry(client, tmp_path):
    source = tiny_audio(tmp_path / "voice.m4a")
    first = _upload(client, source, "upload-audio-0001")
    repeated = _upload(client, source, "upload-audio-0001")
    assert first.status_code == repeated.status_code == 200
    assert first.json()["asset"]["kind"] == "audio"
    assert repeated.json()["receipt"]["id"] == first.json()["receipt"]["id"]
    assert repeated.json()["asset"]["id"] == first.json()["asset"]["id"]


def test_duplicate_bytes_reuse_observed_asset_without_new_identity(client, tmp_path):
    source = tiny_video(tmp_path / "duplicate.mp4")
    first = _upload(client, source, "upload-duplicate-0001")
    revision_after_first = client.get("/api/projects/demo").json()["project"]["revision"]
    second = _upload(client, source, "upload-duplicate-0002", name="renamed.mp4")
    assert second.status_code == 200
    assert second.json()["asset"]["id"] == first.json()["asset"]["id"]
    assert second.json()["receipt"]["payload"]["deduplicated"] is True
    assert client.get("/api/projects/demo").json()["project"]["revision"] == revision_after_first


def test_broken_media_becomes_observed_failure(client, tmp_path):
    broken = tmp_path / "broken.mp4"
    broken.write_bytes(b"not an mp4")
    response = _upload(client, broken, "upload-broken-0001")
    assert response.status_code == 200
    assert response.json()["asset"] is None
    assert response.json()["receipt"]["status"] == "observed_failure"
    assert str(tmp_path) not in response.text


def test_browser_webm_without_duration_is_normalized_and_observed(client, tmp_path):
    source = browser_capture(tmp_path / "camera.webm")
    incoming_sha256 = hashlib.sha256(source.read_bytes()).hexdigest()

    response = _upload(client, source, "upload-browser-camera-0001")

    assert response.status_code == 200
    result = response.json()
    assert result["receipt"]["status"] == "observed_success"
    asset = result["asset"]
    assert asset["kind"] == "video"
    assert asset["intake_status"] == "observed_valid"
    assert asset["duration_ticks"] > 0
    assert asset["sha256"] != incoming_sha256
    assert asset["observation_summary"]["container_normalized"] is True
    assert asset["observation_summary"]["incoming_sha256"] == incoming_sha256
    assert asset["proxy_asset_id"] and asset["thumbnail_asset_id"]


def test_unsupported_and_traversal_filenames_fail_closed(client):
    for index, name in enumerate(("../../payload.mp4.exe", "payload.txt")):
        response = client.post(
            "/api/projects/demo/assets/uploads",
            data={"request_id": f"upload-reject-{index:04d}", "actor": "test"},
            files={"file": (name, BytesIO(b"payload"), "application/octet-stream")},
        )
        assert response.status_code == 415
        assert response.json()["code"] == "media_intake_rejected"


def test_mobile_stylesheet_is_loaded(client):
    index = client.get("/")
    assert index.status_code == 200
    assert "/static/mobile.css" in index.text
    stylesheet = client.get("/static/mobile.css")
    assert stylesheet.status_code == 200
    assert "@media (max-width: 800px)" in stylesheet.text
    assert ".workspace > .panel:not(.mobile-pane-active)" in stylesheet.text
    assert 'class="timeline-scroll"' in index.text
    assert 'role="tablist"' in index.text
