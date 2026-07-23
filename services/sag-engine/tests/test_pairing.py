from pathlib import Path

from fastapi.testclient import TestClient

from sag_video.app import Settings, create_app


def test_invite_gate_and_single_use_pairing(tmp_path: Path):
    app = create_app(
        Settings(
            database_path=str(tmp_path / "auth.db"),
            artifact_dir=str(tmp_path / "artifacts"),
            media_dir=str(tmp_path / "media"),
            proxy_dir=str(tmp_path / "proxies"),
            invite_token="invited",
        )
    )
    with TestClient(app) as client:
        assert client.get("/").status_code == 200
        assert client.get("/api/projects/demo").status_code == 401
        headers = {"X-Invite-Token": "invited"}
        pairing = client.post("/api/pairing/start", headers=headers, json={"workspace_id": "demo"})
        assert pairing.cookies.get("sag_video_session")
        assert pairing.cookies.get("sag_video_session") != "invited"
        assert client.get("/api/projects/demo").status_code == 200
        code = pairing.json()["code"]
        attached = client.post("/api/pairing/attach", json={"code": code, "actor_name": "codex"})
        assert attached.status_code == 200
        token = attached.json()["access_token"]
        assert client.get("/api/projects/demo", headers={"Authorization": f"Bearer {token}"}).status_code == 200
        assert client.post("/api/pairing/attach", json={"code": code, "actor_name": "again"}).status_code == 401


def test_paired_actor_is_attributed_and_cannot_cross_project_scope(tmp_path: Path):
    app = create_app(
        Settings(
            database_path=str(tmp_path / "scope.db"),
            artifact_dir=str(tmp_path / "artifacts"),
            media_dir=str(tmp_path / "media"),
            proxy_dir=str(tmp_path / "proxies"),
            invite_token="invited",
        )
    )
    with TestClient(app) as client:
        browser = {"X-Invite-Token": "invited"}
        other = client.post("/api/projects", headers=browser, json={"name": "Other", "preset": "preview_540p"}).json()["project"]
        code = client.post("/api/pairing/start", headers=browser, json={"workspace_id": "demo"}).json()["code"]
        token = client.post("/api/pairing/attach", json={"code": code, "actor_name": "codex"}).json()["access_token"]
        paired = {"Authorization": f"Bearer {token}"}

        visible = client.get("/api/projects", headers=paired).json()["projects"]
        assert [project["id"] for project in visible] == ["demo"]
        assert client.get(f"/api/projects/{other['id']}", headers=paired).status_code == 403
        assert client.post("/api/projects", headers=paired, json={"name": "Denied", "preset": "preview_540p"}).status_code == 403

        receipt = client.post(
            "/api/projects/demo/commands",
            headers=paired,
            json={
                "command": "timeline.set_title_transform",
                "arguments": {"item_id": "title_intro", "x": 10, "y": 20},
                "expected_revision": 1,
                "request_id": "paired-actor-command-0001",
                "actor": "mcp-agent",
            },
        ).json()
        assert receipt["actor"] == "codex"


def test_loopback_pairing_still_establishes_identity_and_scope(tmp_path: Path):
    app = create_app(
        Settings(
            database_path=str(tmp_path / "loopback.db"),
            artifact_dir=str(tmp_path / "artifacts"),
            media_dir=str(tmp_path / "media"),
            proxy_dir=str(tmp_path / "proxies"),
        )
    )
    with TestClient(app) as client:
        other = client.post("/api/projects", json={"name": "Other", "preset": "preview_540p"}).json()["project"]
        code = client.post("/api/pairing/start", json={"workspace_id": "demo"}).json()["code"]
        token = client.post("/api/pairing/attach", json={"code": code, "actor_name": "codex"}).json()["access_token"]
        paired = {"Authorization": f"Bearer {token}"}
        contract = client.get("/api/contract", headers=paired).json()
        assert contract["authority"]["actor"] == "codex"
        assert client.get(f"/api/projects/{other['id']}", headers=paired).status_code == 403
