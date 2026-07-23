from sag_video.commands import CommandService
from sag_video.contracts import COMMAND_REGISTRY
from sag_video.models import Project


def test_contract_matches_allowlisted_handlers(client):
    contract = client.get("/api/contract")
    assert contract.status_code == 200
    advertised = {entry["name"] for entry in contract.json()["commands"]}
    assert advertised == set(COMMAND_REGISTRY) == set(CommandService.HANDLERS)
    assert contract.json()["authority"]["context_grants_authority"] is False


def test_active_commands_and_read_only_capabilities(client):
    active = client.get("/api/projects/demo/commands/active").json()
    assert "project.undo" not in {entry["name"] for entry in active["commands"]}
    capabilities = client.get("/api/capabilities").json()
    assert capabilities["tools"]["ffmpeg"]["available"] is True
    assert capabilities["privacy"]["activated_device_capabilities"] == []
    assert all(tool["detection_only"] for tool in capabilities["tools"].values())


def test_old_project_json_loads_with_schema_default():
    old = Project.model_validate(
        {
            "id": "old",
            "name": "Old fixture",
            "revision": 1,
            "duration_ticks": 120000,
            "assets": [{"id": "legacy", "kind": "generated", "name": "Legacy", "uri": "generated://legacy"}],
            "tracks": [],
        }
    )
    assert old.schema_version == 1
    assert old.assets[0].source_kind == "generated"
    assert old.assets[0].intake_status == "pending"
