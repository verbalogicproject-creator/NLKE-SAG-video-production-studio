from sag_video.commands import CommandService
from sag_video.contracts import APPLICATION_ACTIONS, COMMAND_REGISTRY, declared_actions, registry_hash


def _pair(client, scopes):
    code = client.post(
        "/api/pairing/start",
        json={"workspace_id": "demo", "project_id": "demo", "sequence_id": "demo", "scopes": scopes},
    ).json()["code"]
    attached = client.post("/api/pairing/attach", json={"code": code, "actor_name": "codex"}).json()
    return {"Authorization": f"Bearer {attached['access_token']}"}, attached


def test_registry_has_stable_hashes_and_complete_handler_allowlist(client):
    assert set(COMMAND_REGISTRY) == set(CommandService.HANDLERS)
    assert all(entry.source_hash for entry in [*COMMAND_REGISTRY.values(), *APPLICATION_ACTIONS.values()])
    assert len(registry_hash()) == 64
    action_names = {entry["stable_id"] for entry in declared_actions()}
    assert action_names == set(COMMAND_REGISTRY) | set(APPLICATION_ACTIONS)
    assert APPLICATION_ACTIONS["capture.start"].safety_class == "browser_permission_only"
    assert APPLICATION_ACTIONS["release.approve"].confirmation_policy == "human_only"


def test_scoped_pairing_enforces_scope_and_project_boundary(client):
    headers, attached = _pair(client, ["context:read", "project:read", "receipt:read"])
    assert attached["project_id"] == "demo"
    context = client.get("/api/projects/demo/context", headers=headers).json()
    assert context["authority"]["scopes"] == ["context:read", "project:read", "receipt:read"]
    denied = client.post(
        "/api/projects/demo/commands", headers=headers,
        json={
            "command": "timeline.set_title_transform", "arguments": {"item_id": "title_intro", "x": 5},
            "expected_revision": 1, "request_id": "scope-denied-0001", "actor": "spoofed",
        },
    ).json()
    assert denied["status"] == "denied"
    assert denied["actor"] == "codex"
    assert "project:write" in denied["payload"]["reason"]


def test_destructive_action_requires_exact_human_confirmation(client):
    headers, _ = _pair(client, ["project:read", "project:write", "context:read"])
    body = {
        "command": "timeline.delete_item", "arguments": {"item_id": "title_intro"},
        "expected_revision": 1, "request_id": "delete-denied-0001", "actor": "codex",
    }
    denied = client.post("/api/projects/demo/commands", headers=headers, json=body).json()
    assert denied["status"] == "denied"
    assert client.get("/api/projects/demo").json()["project"]["revision"] == 1

    confirmation = client.post(
        "/api/projects/demo/confirmations",
        json={"command": body["command"], "arguments": body["arguments"], "expected_revision": 1},
    ).json()
    body["request_id"] = "delete-confirmed-0002"
    body["confirmation_id"] = confirmation["id"]
    committed = client.post("/api/projects/demo/commands", headers=headers, json=body).json()
    assert committed["status"] == "committed"
    assert committed["project_revision"] == 2

    body["request_id"] = "delete-replay-0003"
    body["expected_revision"] = 2
    replay = client.post("/api/projects/demo/commands", headers=headers, json=body).json()
    assert replay["status"] == "denied"


def test_proposal_is_read_only_and_batch_commits_one_revision(client):
    proposal = client.post(
        "/api/projects/demo/commands/propose",
        json={
            "expected_revision": 1,
            "commands": [
                {"command": "timeline.set_title", "arguments": {"item_id": "title_intro", "text": "Grounded cut"}},
                {"command": "timeline.set_title_transform", "arguments": {"item_id": "title_intro", "x": 42, "y": 64}},
            ],
        },
    ).json()
    assert proposal["before_revision"] == 1
    assert proposal["proposed_revision"] == 2
    assert client.get("/api/projects/demo").json()["project"]["revision"] == 1

    receipt = client.post(
        "/api/projects/demo/commands/batch",
        json={
            "expected_revision": 1, "request_id": "atomic-batch-0001", "actor": "browser",
            "commands": [
                {"command": "timeline.set_title", "arguments": {"item_id": "title_intro", "text": "Grounded cut"}},
                {"command": "timeline.set_title_transform", "arguments": {"item_id": "title_intro", "x": 42, "y": 64}},
            ],
        },
    ).json()
    assert receipt["status"] == "committed"
    assert receipt["project_revision"] == 2
    assert len(receipt["payload"]["children"]) == 2
    assert client.get("/api/projects/demo").json()["project"]["revision"] == 2


def test_actor_focus_does_not_overwrite_shared_browser_focus(client):
    headers, _ = _pair(client, ["context:read", "project:read", "focus:write"])
    focused = client.post(
        "/api/projects/demo/selection", headers=headers,
        json={"item_ids": ["clip_terminal"], "expected_revision": 1, "request_id": "actor-focus-0001"},
    ).json()
    assert focused["focus"] == "actor_local"
    paired_context = client.get("/api/projects/demo/context", headers=headers).json()
    assert paired_context["actor_focus"]["item_ids"] == ["clip_terminal"]
    assert paired_context["shared_focus"][0]["id"] == "title_intro"
    browser_context = client.get("/api/projects/demo/context").json()
    assert browser_context["shared_focus"][0]["id"] == "title_intro"
