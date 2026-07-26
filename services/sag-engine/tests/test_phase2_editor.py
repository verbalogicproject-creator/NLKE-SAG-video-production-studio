from conftest import command_body
from media_fixtures import tiny_video


def _upload_video(client, tmp_path, request_id="phase2-upload-0001"):
    source = tiny_video(tmp_path / f"{request_id}.mp4", duration=2.0)
    response = client.post(
        "/api/projects/demo/assets/uploads",
        data={"request_id": request_id, "actor": "test"},
        files={"file": (source.name, source.read_bytes(), "video/mp4")},
    )
    assert response.status_code == 200
    return response.json()["asset"]


def test_project_create_list_and_open(client):
    created = client.post("/api/projects", json={"name": "Phone tips", "preset": "vertical_1080p"})
    assert created.status_code == 200
    project = created.json()["project"]
    assert project["canvas"]["width"] == 1080
    assert project["canvas"]["height"] == 1920
    assert [track["kind"] for track in project["tracks"]] == ["video", "overlay", "audio"]
    listed = client.get("/api/projects").json()["projects"]
    assert project["id"] in {entry["id"] for entry in listed}
    assert client.get(f"/api/projects/{project['id']}").status_code == 200


def test_insert_split_move_delete_and_undo_are_canonical(client, tmp_path):
    asset = _upload_video(client, tmp_path)
    inserted = client.post(
        "/api/projects/demo/commands",
        json=command_body(
            "timeline.insert_asset",
            {"asset_id": asset["id"]},
            revision=2,
            request_id="phase2-insert-0001",
        ),
    )
    assert inserted.status_code == 200
    item_id = inserted.json()["payload"]["observation"]["item_id"]
    project = client.get("/api/projects/demo").json()["project"]
    item = next(item for track in project["tracks"] for item in track["items"] if item["id"] == item_id)
    assert item["asset_id"] == asset["id"]
    assert item["source_out_ticks"] == asset["duration_ticks"]

    split_at = item["start_ticks"] + item["duration_ticks"] // 2
    split = client.post(
        "/api/projects/demo/commands",
        json=command_body(
            "timeline.split_clip",
            {"item_id": item_id, "at_ticks": split_at},
            revision=3,
            request_id="phase2-split-0001",
        ),
    )
    assert split.status_code == 200
    new_id = split.json()["payload"]["observation"]["new_item_id"]

    moved = client.post(
        "/api/projects/demo/commands",
        json=command_body(
            "timeline.move_item",
            {"item_id": new_id, "start_ticks": split_at + 120000},
            revision=4,
            request_id="phase2-move-0001",
        ),
    )
    assert moved.status_code == 200

    confirmation = client.post(
        "/api/projects/demo/confirmations",
        json={"command": "timeline.delete_item", "arguments": {"item_id": new_id}, "expected_revision": 5},
    ).json()
    delete_body = command_body(
        "timeline.delete_item", {"item_id": new_id}, revision=5, request_id="phase2-delete-0001"
    )
    delete_body["confirmation_id"] = confirmation["id"]
    deleted = client.post(
        "/api/projects/demo/commands",
        json=delete_body,
    )
    assert deleted.status_code == 200
    assert all(item["id"] != new_id for track in client.get("/api/projects/demo").json()["project"]["tracks"] for item in track["items"])

    undone = client.post(
        "/api/projects/demo/commands",
        json=command_body("project.undo", {}, revision=6, request_id="phase2-undo-0001"),
    )
    assert undone.status_code == 200
    assert any(item["id"] == new_id for track in client.get("/api/projects/demo").json()["project"]["tracks"] for item in track["items"])


def test_trim_transform_gain_and_title_validation(client, tmp_path):
    asset = _upload_video(client, tmp_path, "phase2-upload-0002")
    insert = client.post(
        "/api/projects/demo/commands",
        json=command_body("timeline.insert_asset", {"asset_id": asset["id"]}, revision=2, request_id="phase2-insert-0002"),
    ).json()
    item_id = insert["payload"]["observation"]["item_id"]
    duration = asset["duration_ticks"] // 2
    trimmed = client.post(
        "/api/projects/demo/commands",
        json=command_body(
            "timeline.trim_clip",
            {"item_id": item_id, "duration_ticks": duration, "source_in_ticks": 12000, "source_out_ticks": 12000 + duration},
            revision=3,
            request_id="phase2-trim-0001",
        ),
    )
    assert trimmed.status_code == 200
    transform = client.post(
        "/api/projects/demo/commands",
        json=command_body(
            "timeline.set_clip_transform",
            {"item_id": item_id, "fit_mode": "fill", "scale": 1.2, "opacity": .8},
            revision=4,
            request_id="phase2-transform-0001",
        ),
    )
    assert transform.status_code == 200
    gain = client.post(
        "/api/projects/demo/commands",
        json=command_body(
            "timeline.set_audio_gain",
            {"item_id": item_id, "gain_db": -3.5, "muted": True},
            revision=5,
            request_id="phase2-gain-0001",
        ),
    )
    assert gain.status_code == 200
    title = client.post(
        "/api/projects/demo/commands",
        json=command_body(
            "timeline.set_title", {"item_id": "title_intro", "text": "A real preview"}, revision=6, request_id="phase2-title-0001"
        ),
    )
    assert title.status_code == 200
    project = client.get("/api/projects/demo").json()["project"]
    updated = next(item for track in project["tracks"] for item in track["items"] if item["id"] == item_id)
    assert updated["fit_mode"] == "fill"
    assert updated["gain_db"] == -3.5 and updated["muted"] is True
    assert project["revision"] == 7

    invalid = client.post(
        "/api/projects/demo/commands",
        json=command_body(
            "timeline.trim_clip",
            {"item_id": item_id, "duration_ticks": duration, "source_in_ticks": asset["duration_ticks"], "source_out_ticks": asset["duration_ticks"] + duration},
            revision=7,
            request_id="phase2-invalid-trim",
        ),
    )
    assert invalid.status_code == 422


def test_pairing_status_reports_attached_actor(client):
    initial = client.get("/api/pairing/status/demo").json()
    assert initial["connected"] is False
    code = client.post("/api/pairing/start", json={"workspace_id": "demo"}).json()["code"]
    assert client.post("/api/pairing/attach", json={"code": code, "actor_name": "codex"}).status_code == 200
    status = client.get("/api/pairing/status/demo").json()
    assert status["connected"] is True
    assert status["actors"][0]["actor_name"] == "codex"


def test_left_edge_trim_is_one_atomic_revision(client, tmp_path):
    asset = _upload_video(client, tmp_path, "edge-trim-upload")
    inserted = client.post(
        "/api/projects/demo/commands",
        json=command_body(
            "timeline.insert_asset", {"asset_id": asset["id"]}, revision=2,
            request_id="edge-trim-insert",
        ),
    ).json()
    item_id = inserted["payload"]["observation"]["item_id"]
    before_revision = inserted["project_revision"]
    delta = 12000
    trimmed = client.post(
        "/api/projects/demo/commands",
        json=command_body(
            "timeline.trim_clip",
            {
                "item_id": item_id, "start_ticks": delta,
                "duration_ticks": asset["duration_ticks"] - delta,
                "source_in_ticks": delta, "source_out_ticks": asset["duration_ticks"],
            },
            revision=before_revision, request_id="edge-trim-left",
        ),
    )
    assert trimmed.status_code == 200
    assert trimmed.json()["project_revision"] == before_revision + 1
    item = client.get("/api/projects/demo").json()["project"]
    item = next(entry for track in item["tracks"] for entry in track["items"] if entry["id"] == item_id)
    assert item["start_ticks"] == item["source_in_ticks"] == delta
    assert item["duration_ticks"] == asset["duration_ticks"] - delta


def test_interactive_editor_controls_are_shipped(client):
    html = client.get("/").text
    javascript = client.get("/static/app.js").text
    assert 'id="transform-box"' in html
    assert 'data-trim="left"' in javascript and 'data-trim="right"' in javascript
    assert "requestAnimationFrame(playbackTick)" in javascript
    assert "activeVideoItem" in javascript
    assert 'id="monitor-placeholder"' in html
    assert 'placeholder.querySelector("strong").textContent = asset.name' in javascript
    assert "activateMobilePane" in javascript
    assert 'id="copy-pair-command"' in html
    assert "navigator.clipboard.writeText" in javascript
    assert '$("pair-dialog").close()' not in javascript.split("async function checkPairStatus()", 1)[1].split('$("pair").onclick', 1)[0]
