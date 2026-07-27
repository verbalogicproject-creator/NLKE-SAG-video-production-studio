from conftest import command_body


def test_fixture_exposes_stable_semantic_selection(client):
    payload = client.get("/api/projects/demo").json()
    assert payload["project"]["revision"] == 1
    assert payload["selection"] == ["title_intro"]
    context = client.get("/api/projects/demo/context").json()
    assert context["selection"][0]["id"] == "title_intro"
    assert context["authority"]["context_grants_authority"] is False


def test_command_is_idempotent_and_revision_checked(client):
    body = command_body(
        "timeline.set_title_transform",
        {"item_id": "title_intro", "x": 60, "y": 56},
    )
    first = client.post("/api/projects/demo/commands", json=body)
    assert first.status_code == 200
    assert first.json()["project_revision"] == 2

    repeated = client.post("/api/projects/demo/commands", json=body)
    assert repeated.status_code == 200
    assert repeated.json()["id"] == first.json()["id"]
    assert client.get("/api/projects/demo").json()["project"]["revision"] == 2

    stale = client.post(
        "/api/projects/demo/commands",
        json=command_body(
            "timeline.set_title_transform",
            {"item_id": "title_intro", "x": 80, "y": 56},
            request_id="test-request-stale",
        ),
    )
    assert stale.status_code == 409
    assert stale.json()["code"] == "stale_revision"
    assert stale.json()["current_revision"] == 2


def test_unknown_command_fails_closed(client):
    response = client.post(
        "/api/projects/demo/commands",
        json=command_body("timeline.run_ffmpeg", {"shell": "anything"}),
    )
    assert response.status_code == 200
    assert response.json()["status"] == "denied"
    assert response.json()["payload"]["reason"] == "unknown or undeclared command"


def test_project_rename_is_revisioned_and_validated(client):
    renamed = client.post(
        "/api/projects/demo/commands",
        json=command_body(
            "project.rename", {"name": "SAG Repository Proof"},
            request_id="project-rename-0001",
        ),
    )
    assert renamed.status_code == 200, renamed.text
    assert renamed.json()["project_revision"] == 2
    assert client.get("/api/projects/demo").json()["project"]["name"] == "SAG Repository Proof"

    blank = client.post(
        "/api/projects/demo/commands",
        json=command_body(
            "project.rename", {"name": "   "}, revision=2,
            request_id="project-rename-0002",
        ),
    )
    assert blank.status_code == 422
    assert "cannot be blank" in blank.json()["detail"]


def test_undo_creates_compensating_revision(client):
    moved = client.post(
        "/api/projects/demo/commands",
        json=command_body(
            "timeline.set_title_transform",
            {"item_id": "title_intro", "x": 80, "y": 70},
        ),
    )
    assert moved.json()["project_revision"] == 2
    undone = client.post(
        "/api/projects/demo/commands",
        json=command_body("project.undo", {}, revision=2, request_id="test-request-undo"),
    )
    assert undone.json()["project_revision"] == 3
    project = client.get("/api/projects/demo").json()["project"]
    title = next(item for track in project["tracks"] for item in track["items"] if item["id"] == "title_intro")
    assert title["x"] == -22
    assert project["revision"] == 3


def test_multi_step_undo_and_redo_walk_edit_history(client):
    first = client.post(
        "/api/projects/demo/commands",
        json=command_body(
            "timeline.set_title_transform", {"item_id": "title_intro", "x": 80},
            request_id="history-first-0001",
        ),
    )
    assert first.status_code == 200
    second = client.post(
        "/api/projects/demo/commands",
        json=command_body(
            "timeline.set_title_transform", {"item_id": "title_intro", "y": 90},
            revision=2, request_id="history-second-0001",
        ),
    )
    assert second.status_code == 200
    assert client.post(
        "/api/projects/demo/commands",
        json=command_body("project.undo", {}, revision=3, request_id="history-undo-0001"),
    ).status_code == 200
    assert client.post(
        "/api/projects/demo/commands",
        json=command_body("project.undo", {}, revision=4, request_id="history-undo-0002"),
    ).status_code == 200
    base_title = next(
        item for track in client.get("/api/projects/demo").json()["project"]["tracks"]
        for item in track["items"] if item["id"] == "title_intro"
    )
    assert (base_title["x"], base_title["y"]) == (-22, 56)
    assert client.post(
        "/api/projects/demo/commands",
        json=command_body("project.redo", {}, revision=5, request_id="history-redo-0001"),
    ).status_code == 200
    assert client.post(
        "/api/projects/demo/commands",
        json=command_body("project.redo", {}, revision=6, request_id="history-redo-0002"),
    ).status_code == 200
    restored = next(
        item for track in client.get("/api/projects/demo").json()["project"]["tracks"]
        for item in track["items"] if item["id"] == "title_intro"
    )
    assert (restored["x"], restored["y"]) == (80, 90)


def test_magnetic_and_ripple_move_are_canonical(client):
    response = client.post(
        "/api/projects/demo/commands",
        json=command_body(
            "timeline.move_item",
            {"item_id": "clip_result", "start_ticks": 360100, "magnetic": True},
            request_id="magnetic-move-0001",
        ),
    )
    assert response.status_code == 200
    assert response.json()["payload"]["observation"]["start_ticks"] == 360000
    ripple = client.post(
        "/api/projects/demo/commands",
        json=command_body(
            "timeline.move_item",
            {"item_id": "clip_terminal", "start_ticks": 120000, "ripple": True},
            revision=2, request_id="ripple-move-0001",
        ),
    )
    assert ripple.status_code == 200
    project = client.get("/api/projects/demo").json()["project"]
    result = next(item for track in project["tracks"] for item in track["items"] if item["id"] == "clip_result")
    assert result["start_ticks"] == 480000


def test_edit_receipt_discloses_non_independent_readback(client):
    response = client.post(
        "/api/projects/demo/commands",
        json=command_body(
            "timeline.set_title_transform",
            {"item_id": "title_intro", "x": 60, "y": 56},
        ),
    )
    observation = response.json()["payload"]["observation"]
    assert observation["kind"] == "canonical_revision_readback"
    assert observation["independent_failure_domain"] is False
