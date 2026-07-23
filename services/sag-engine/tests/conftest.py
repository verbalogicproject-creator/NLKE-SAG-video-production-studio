from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from sag_video.app import Settings, create_app


@pytest.fixture
def client(tmp_path: Path):
    app = create_app(
        Settings(
            database_path=str(tmp_path / "sag-video.db"),
            artifact_dir=str(tmp_path / "artifacts"),
            media_dir=str(tmp_path / "media"),
            proxy_dir=str(tmp_path / "proxies"),
        )
    )
    with TestClient(app) as test_client:
        yield test_client


def command_body(
    command: str,
    arguments: dict,
    *,
    revision: int = 1,
    request_id: str = "test-request-0001",
) -> dict:
    return {
        "command": command,
        "arguments": arguments,
        "expected_revision": revision,
        "request_id": request_id,
        "actor": "test",
    }
