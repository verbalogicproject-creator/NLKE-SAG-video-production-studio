import hashlib
import json
from io import BytesIO
from pathlib import Path

from fastapi.testclient import TestClient
from PIL import Image

from sag_video.app import Settings, create_app


def digest(value: str) -> str:
    return hashlib.sha256(value.encode()).hexdigest()


def checkpoint_bytes(color: str) -> bytes:
    output = BytesIO()
    Image.new("RGB", (360, 640), color).save(output, format="PNG")
    return output.getvalue()


def observation(state: str, revision: int, *, actions: bool = True) -> dict:
    return {
        "origin": "http://localhost:3000", "route_hash": digest("/studio/demo"),
        "title_hash": digest("SAG Studio"),
        "viewport": {"width": 1080, "height": 1920, "device_scale_factor": 1},
        "application_state_hash": digest(state),
        "bindings": [{
            "binding_id": "binding_selected_clip", "entity_id": "studio.timeline.selected_clip",
            "role": "timeline_item", "label": "Selected clip",
            "rect": {"x": 0.1, "y": 0.2, "width": 0.8, "height": 0.4},
            "source": "profile",
            "eligible_action_ids": ["timeline.set_clip_transform"] if actions else [],
        }],
        "context_refs": [{"kind": "project", "id": "demo", "revision": revision}],
    }


def computer_use_client(tmp_path: Path) -> TestClient:
    return TestClient(create_app(Settings(
        database_path=str(tmp_path / "computer-use.db"), artifact_dir=str(tmp_path / "artifacts"),
        media_dir=str(tmp_path / "media"), proxy_dir=str(tmp_path / "proxies"),
        storage_root=str(tmp_path / "storage"), storage_cache_dir=str(tmp_path / "cache"),
        computer_use_enabled=True,
    )))


def test_signed_profile_observe_edit_verify_and_compensate(tmp_path: Path):
    with computer_use_client(tmp_path) as client:
        profile = json.loads(Path("services/sag-engine/profiles/sag-studio-local.v1.json").read_text())
        bad = {**profile, "version": 2, "signature": "A" * 86}
        assert client.post(
            "/api/computer-use/profiles", headers={"x-sag-workspace-id": "demo"}, json=bad,
        ).status_code == 409

        started = client.post("/api/pairing/start", json={
            "workspace_id": "demo", "principal_kind": "browser_extension", "audience": "computer_use",
        })
        assert started.status_code == 200, started.text
        attached = client.post("/api/pairing/attach", json={
            "code": started.json()["code"], "actor_name": "sag-extension",
        })
        token = attached.json()["access_token"]
        headers = {"authorization": f"Bearer {token}"}
        assert attached.json()["project_id"] is None
        assert attached.json()["audience"] == "computer_use"
        assert set(attached.json()["scopes"]) == {
            "computer_use:observe", "computer_use:act", "computer_use:capture", "computer_use:attach",
        }
        listed = client.get("/api/computer-use/profiles", headers=headers)
        assert listed.status_code == 200
        assert listed.json()["profiles"][0]["profile_sha256"]
        assert client.get("/api/projects/demo", headers=headers).status_code == 403

        activity = client.post("/api/computer-use/activities", headers=headers, json={
            "origin": "http://localhost:3000", "tab_session_id": "tab-session-0001",
            "profile_id": "sag.studio.local",
            "context_refs": [{"kind": "project", "id": "demo", "revision": 1}],
        }).json()
        before = client.post(
            f"/api/computer-use/activities/{activity['id']}/observations",
            headers=headers, json=observation("scale=1", 1),
        ).json()
        checkpoint = client.post(
            f"/api/computer-use/activities/{activity['id']}/checkpoints", headers=headers,
            data={"observation_id": before["id"], "redaction_state": "redacted"},
            files={"file": ("before.png", checkpoint_bytes("#102030"), "image/png")},
        )
        assert checkpoint.status_code == 201, checkpoint.text
        downloaded = client.get(
            f"/api/computer-use/checkpoints/{checkpoint.json()['id']}/content", headers=headers,
        )
        assert downloaded.status_code == 200
        assert downloaded.headers["content-type"].startswith("image/png")

        intent = client.post(
            f"/api/computer-use/activities/{activity['id']}/intents", headers=headers, json={
                "request_id": "computer-use-scale-0001", "before_observation_id": before["id"],
                "action_id": "timeline.set_clip_transform", "target_binding_id": "binding_selected_clip",
                "arguments": {"item_id": "clip_terminal", "scale": 0.85},
                "context_ref": {"kind": "project", "id": "demo", "revision": 1},
                "expected_project_revision": 1,
            },
        ).json()
        assert intent["ticket"]
        persisted = client.app.state.store.get_editorial_record(intent["id"], kind="computer_use_intent")
        assert "ticket" not in persisted

        execution = client.post(
            f"/api/computer-use/intents/{intent['id']}/execute", headers=headers,
            json={"ticket": intent["ticket"]},
        )
        assert execution.status_code == 202, execution.text
        assert client.post(
            f"/api/computer-use/intents/{intent['id']}/execute", headers=headers,
            json={"ticket": intent["ticket"]},
        ).status_code == 409
        assert client.app.state.store.get_project("demo").item("clip_terminal").scale == 0.85

        after = client.post(
            f"/api/computer-use/activities/{activity['id']}/observations",
            headers=headers, json=observation("scale=.85", 2),
        ).json()
        client.post(
            f"/api/computer-use/activities/{activity['id']}/checkpoints", headers=headers,
            data={"observation_id": after["id"], "redaction_state": "redacted"},
            files={"file": ("after.png", checkpoint_bytes("#203040"), "image/png")},
        ).raise_for_status()
        receipt = client.post(
            f"/api/computer-use/executions/{execution.json()['id']}/complete", headers=headers,
            json={"after_observation_id": after["id"], "observed_effect": {"target_selected": True}},
        )
        assert receipt.status_code == 200, receipt.text
        assert receipt.json()["status"] == "observed_success"
        assert receipt.json()["underlying_receipt_id"]
        assert receipt.json()["profile_sha256"] == listed.json()["profiles"][0]["profile_sha256"]
        assert receipt.json()["verification_failure_domain"] == "same_extension_adapter"
        assert len(receipt.json()["before_checkpoint_ids"]) == 1
        assert len(receipt.json()["after_checkpoint_ids"]) == 1

        compensation = client.post(
            f"/api/computer-use/activities/{activity['id']}/intents", headers=headers, json={
                "request_id": "computer-use-scale-undo-0001", "before_observation_id": after["id"],
                "action_id": "timeline.set_clip_transform", "target_binding_id": "binding_selected_clip",
                "arguments": {"item_id": "clip_terminal", "scale": 1},
                "context_ref": {"kind": "project", "id": "demo", "revision": 2},
                "expected_project_revision": 2,
            },
        ).json()
        restored = client.post(
            f"/api/computer-use/intents/{compensation['id']}/execute", headers=headers,
            json={"ticket": compensation["ticket"]},
        )
        assert restored.status_code == 202, restored.text
        assert client.app.state.store.get_project("demo").item("clip_terminal").scale == 1
        restored_observation = client.post(
            f"/api/computer-use/activities/{activity['id']}/observations",
            headers=headers, json=observation("scale=1-restored", 3),
        ).json()
        client.post(
            f"/api/computer-use/activities/{activity['id']}/checkpoints", headers=headers,
            data={"observation_id": restored_observation["id"], "redaction_state": "redacted"},
            files={"file": ("restored.png", checkpoint_bytes("#304050"), "image/png")},
        ).raise_for_status()
        restored_receipt = client.post(
            f"/api/computer-use/executions/{restored.json()['id']}/complete", headers=headers,
            json={"after_observation_id": restored_observation["id"]},
        )
        assert restored_receipt.status_code == 200, restored_receipt.text
        assert restored_receipt.json()["status"] == "observed_success"


def test_generic_observation_has_no_actions_and_navigation_pauses(tmp_path: Path):
    with computer_use_client(tmp_path) as client:
        headers = {"x-sag-workspace-id": "demo"}
        activity = client.post("/api/computer-use/activities", headers=headers, json={
            "origin": "http://example.com", "tab_session_id": "generic-tab-0001",
        }).json()
        body = observation("generic", 1, actions=False)
        body["origin"] = "http://example.com"
        first = client.post(
            f"/api/computer-use/activities/{activity['id']}/observations", headers=headers, json=body,
        )
        assert first.status_code == 201
        spoofed = client.post(
            f"/api/computer-use/activities/{activity['id']}/checkpoints", headers=headers,
            data={"observation_id": first.json()["id"], "redaction_state": "not_applicable"},
            files={"file": ("spoofed.jpg", checkpoint_bytes("#102030"), "image/jpeg")},
        )
        assert spoofed.status_code == 415
        assert client.get(
            f"/api/computer-use/activities/{activity['id']}/actions", headers=headers,
        ).json() == {"actions": []}
        body["route_hash"] = digest("/navigated")
        assert client.post(
            f"/api/computer-use/activities/{activity['id']}/observations", headers=headers, json=body,
        ).status_code == 409
        assert client.get(
            f"/api/computer-use/activities/{activity['id']}", headers=headers,
        ).json()["state"] == "paused"
