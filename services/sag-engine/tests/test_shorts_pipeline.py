from __future__ import annotations

import time

from media_fixtures import tiny_video
from sag_video.models import CaptionStyle, CaptionWord, CropKeyframe, Project, TICKS_PER_SECOND, TimelineItem, Track, utc_now
from sag_video.shorts import _candidate_windows


class FakeTranscriber:
    id = "fake_transcriber"
    version = "test-1"

    def capabilities(self):
        return {"available": True, "word_timestamps": True, "languages": ["en", "he"]}

    def transcribe(self, _wav_path, language):
        words = []
        vocabulary = ["How", "to", "build", "a", "better", "video", "because", "each", "step", "matters."]
        for index in range(32):
            start = index * TICKS_PER_SECOND // 2
            words.append({
                "id": f"word_{index:06d}", "text": vocabulary[index % len(vocabulary)],
                "start_ticks": start, "end_ticks": start + TICKS_PER_SECOND // 2,
                "confidence": .99,
            })
        return {"language": "he" if language == "he" else "en", "text": " ".join(word["text"] for word in words), "words": words}


class SlowTranscriber(FakeTranscriber):
    id = "slow_transcriber"

    def transcribe(self, wav_path, language, cancelled=None):
        for _ in range(100):
            if cancelled and cancelled():
                from sag_video.shorts import AnalysisCancelled
                raise AnalysisCancelled()
            time.sleep(.02)
        return super().transcribe(wav_path,language)


def _wait(client, job_id, timeout=25):
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        job = client.get(f"/api/jobs/{job_id}").json()
        if job["state"] in {"observed_success", "observed_failure", "execution_failed", "cancelled", "timeout", "interrupted"}:
            return job
        time.sleep(.1)
    raise AssertionError("shorts job did not finish")


def test_short_discovery_acceptance_lineage_and_editable_render_spec(client, tmp_path):
    client.app.state.shorts.transcriber = FakeTranscriber()
    source = tiny_video(tmp_path / "long-source.mp4", duration=16.1)
    imported = client.post(
        "/api/projects/demo/assets/uploads",
        data={"request_id": "shorts-upload-0001", "actor": "test"},
        files={"file": (source.name, source.read_bytes(), "video/mp4")},
    ).json()
    asset = imported["asset"]
    revision = imported["receipt"]["project_revision"]
    queued = client.post("/api/projects/demo/shorts/jobs", json={
        "source_revision": revision, "asset_id": asset["id"], "prompt": "Find practical advice",
        "language": "en", "candidate_count": 5,
    })
    assert queued.status_code == 200
    job = _wait(client, queued.json()["id"])
    assert job["state"] == "observed_success", job
    assert job["stage"] == "complete" and job["progress"] == 1

    drafts = client.get("/api/projects/demo/suggestions?state=pending").json()["suggestions"]
    assert drafts
    draft = drafts[0]
    assert draft["evidence"]["source_sha256"] == asset["sha256"]
    assert set(draft["evidence"]["score_components"]) == {"hook", "flow", "value", "delivery", "visual", "boundary"}
    accepted = client.post(f"/api/suggestions/{draft['id']}/accept", json={
        "request_id": "accept-short-0001", "actor": "test", "expected_state": "pending",
    })
    assert accepted.status_code == 200, accepted.text
    child = accepted.json()["project"]
    assert child["parent_project_id"] == "demo"
    assert child["source_project_revision"] == revision
    assert child["source_suggestion_id"] == draft["id"]
    assert child["canvas"]["width"] == 1080 and child["canvas"]["height"] == 1920
    assert child["assets"][0]["blob_id"] == asset["blob_id"]
    assert {track["kind"] for track in child["tracks"]} >= {"video", "caption"}
    caption = next(item for track in child["tracks"] for item in track["items"] if item["kind"] == "caption")
    video = next(item for track in child["tracks"] for item in track["items"] if item["kind"] == "video")
    assert caption["caption_words"] and caption["caption_style"]["preset"] == "bold_pop"
    assert video["crop_keyframes"]

    spec = client.app.state.renderer.build_spec(client.app.state.store.get_project(child["id"]))
    assert spec.contract_version == "sag-render-0.2"
    assert spec.captions and spec.media[0].crop_keyframes
    visible = {entry["id"] for entry in client.get("/api/projects").json()["projects"]}
    assert child["id"] in visible
    code = client.post("/api/pairing/start",json={"workspace_id":"demo"}).json()["code"]
    token = client.post("/api/pairing/attach",json={"code":code,"actor_name":"codex"}).json()["access_token"]
    paired_visible = {entry["id"] for entry in client.get("/api/projects",headers={"Authorization":f"Bearer {token}"}).json()["projects"]}
    assert paired_visible >= {"demo",child["id"]}


def test_caption_and_crop_commands_are_revisioned(client, tmp_path):
    # Reuse a pending suggestion to get the canonical derived-project shape without rendering it.
    client.app.state.shorts.transcriber = FakeTranscriber()
    source = tiny_video(tmp_path / "edit-source.mp4", duration=16.1)
    imported = client.post(
        "/api/projects/demo/assets/uploads", data={"request_id": "shorts-upload-edit", "actor": "test"},
        files={"file": (source.name, source.read_bytes(), "video/mp4")},
    ).json()
    job = client.post("/api/projects/demo/shorts/jobs", json={
        "source_revision": imported["receipt"]["project_revision"], "asset_id": imported["asset"]["id"],
    }).json()
    assert _wait(client, job["id"])["state"] == "observed_success"
    draft = client.get("/api/projects/demo/suggestions?state=pending").json()["suggestions"][0]
    child = client.post(f"/api/suggestions/{draft['id']}/accept", json={
        "request_id": "accept-short-edit", "actor": "test", "expected_state": "pending",
    }).json()["project"]
    caption = next(item for track in child["tracks"] for item in track["items"] if item["kind"] == "caption")
    video = next(item for track in child["tracks"] for item in track["items"] if item["kind"] == "video")
    styled = client.post(f"/api/projects/{child['id']}/commands", json={
        "command": "timeline.set_caption_style", "arguments": {"item_id": caption["id"], "preset": "clean", "position": "top", "font_size": 52},
        "expected_revision": 1, "request_id": "caption-style-edit", "actor": "test",
    })
    assert styled.status_code == 200
    cropped = client.post(f"/api/projects/{child['id']}/commands", json={
        "command": "timeline.set_crop_keyframes", "arguments": {"item_id": video["id"], "keyframes": [
            {"time_ticks": 0, "center_x": .4, "center_y": .5, "zoom": 1, "locked": True},
            {"time_ticks": video["duration_ticks"], "center_x": .6, "center_y": .5, "zoom": 1, "locked": True},
        ]}, "expected_revision": 2, "request_id": "crop-path-edit", "actor": "test",
    })
    assert cropped.status_code == 200
    updated = client.get(f"/api/projects/{child['id']}").json()["project"]
    assert updated["revision"] == 3
    assert next(item for track in updated["tracks"] for item in track["items"] if item["kind"] == "caption")["caption_style"]["preset"] == "clean"


def test_candidate_windows_preserve_hebrew_word_ids_and_bounds():
    words = [{
        "id": f"w{index}", "text": ("למה" if index == 0 else "מילה." if index == 39 else "מילה"),
        "start_ticks": index * 60000, "end_ticks": (index + 1) * 60000,
    } for index in range(40)]
    from sag_video.models import ShortsGenerateRequest
    candidates = _candidate_windows(
        {"language": "he", "words": words}, {"scene_ticks": [], "silences": []},
        ShortsGenerateRequest(source_revision=1),
    )
    assert candidates
    assert candidates[0]["word_ids"][0] == "w0"
    assert 15 * TICKS_PER_SECOND <= candidates[0]["end_ticks"] - candidates[0]["start_ticks"] <= 90 * TICKS_PER_SECOND


def test_analysis_cancellation_interrupts_transcription(client,tmp_path):
    client.app.state.shorts.transcriber = SlowTranscriber()
    source = tiny_video(tmp_path / "cancel-source.mp4",duration=.8)
    imported = client.post(
        "/api/projects/demo/assets/uploads",data={"request_id":"cancel-shorts-upload","actor":"test"},
        files={"file":(source.name,source.read_bytes(),"video/mp4")},
    ).json()
    job = client.post("/api/projects/demo/shorts/jobs",json={
        "source_revision":imported["receipt"]["project_revision"],"asset_id":imported["asset"]["id"],
    }).json()
    deadline = time.monotonic()+5
    while time.monotonic()<deadline:
        current = client.get(f"/api/jobs/{job['id']}").json()
        if current["stage"] == "transcription":
            break
        time.sleep(.02)
    client.post(f"/api/jobs/{job['id']}/cancel",json={})
    assert _wait(client,job["id"])["state"] == "cancelled"


def test_caption_and_keyframed_crop_render_through_ffmpeg(client, tmp_path):
    project = client.post("/api/projects", json={"name":"Caption render","preset":"preview_540p"}).json()["project"]
    source = tiny_video(tmp_path / "caption-render.mp4", duration=.8)
    imported = client.post(
        f"/api/projects/{project['id']}/assets/uploads",data={"request_id":"caption-render-upload","actor":"test"},
        files={"file":(source.name,source.read_bytes(),"video/mp4")},
    ).json()
    inserted = client.post(f"/api/projects/{project['id']}/commands",json={
        "command":"timeline.insert_asset","arguments":{"asset_id":imported["asset"]["id"]},
        "expected_revision":imported["receipt"]["project_revision"],"request_id":"caption-render-insert","actor":"test",
    }).json()
    canonical = client.app.state.store.get_project(project["id"])
    video = next(item for track in canonical.tracks for item in track.items if item.kind == "video")
    video.width, video.height = canonical.canvas.width, canonical.canvas.height
    video.crop_keyframes = [
        CropKeyframe(time_ticks=0,center_x=.45,center_y=.5),
        CropKeyframe(time_ticks=video.duration_ticks,center_x=.55,center_y=.5),
    ]
    canonical.tracks.append(Track(id="track_captions",kind="caption",name="Captions",items=[TimelineItem(
        id="caption_render",kind="caption",track_id="track_captions",name="Captions",start_ticks=0,
        duration_ticks=video.duration_ticks,caption_style=CaptionStyle(font_size=34),caption_words=[
            CaptionWord(id="w1",text="שלום",start_ticks=0,end_ticks=36000),
            CaptionWord(id="w2",text="world",start_ticks=36000,end_ticks=min(video.duration_ticks,90000)),
        ],
    )]))
    canonical.duration_ticks = video.duration_ticks
    canonical.revision = inserted["project_revision"] + 1
    canonical.updated_at = utc_now()
    client.app.state.store.put_project(canonical)
    receipt = client.post(f"/api/projects/{project['id']}/renders",json={
        "project_revision":canonical.revision,"request_id":"caption-render-job","actor":"test",
    }).json()
    job = _wait(client,receipt["payload"]["job_id"])
    assert job["state"] == "observed_success", job
