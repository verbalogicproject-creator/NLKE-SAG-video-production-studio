#!/usr/bin/env python3
from __future__ import annotations

import json
import os
from pathlib import Path
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen


def get(base_url: str, path: str, token: str) -> dict:
    headers = {"Authorization": f"Bearer {token}"} if token else {}
    request = Request(f"{base_url.rstrip('/')}{path}", headers=headers)
    with urlopen(request, timeout=15) as response:
        return json.load(response)


def main() -> None:
    base_url = os.getenv("SAG_VIDEO_URL", "http://127.0.0.1:8080")
    project_id = os.getenv("SAG_VIDEO_PROJECT_ID", "demo")
    token_path = Path(os.getenv("SAG_VIDEO_TOKEN_FILE", ".sag-video/codex-token"))
    token = token_path.read_text(encoding="utf-8").strip() if token_path.is_file() else ""
    try:
        health = get(base_url, "/health", token)
        contract = get(base_url, "/api/contract", token)
        projects = get(base_url, "/api/projects", token)
        context = get(base_url, f"/api/projects/{project_id}/context", token)
        active = get(base_url, f"/api/projects/{project_id}/commands/active", token)
    except (HTTPError, URLError, OSError, ValueError) as error:
        raise SystemExit(f"Codex–SAG preflight failed: {error}") from error

    command_names = {command["name"] for command in active["commands"]}
    required = {
        "timeline.insert_asset",
        "timeline.move_item",
        "timeline.split_clip",
        "timeline.trim_clip",
        "timeline.set_clip_transform",
    }
    missing = sorted(required - command_names)
    if missing:
        raise SystemExit(f"Codex–SAG preflight failed: missing active commands: {', '.join(missing)}")
    if contract["authority"]["context_grants_authority"] is not False:
        raise SystemExit("Codex–SAG preflight failed: context incorrectly grants authority")

    print(json.dumps({
        "status": "ready",
        "service": health["service"],
        "contract_version": contract["application"]["contract_version"],
        "actor": contract["authority"]["actor"],
        "project_id": context["project_id"],
        "revision": context["revision"],
        "visible_projects": [project["id"] for project in projects["projects"]],
        "selected_item_ids": [item["id"] for item in context["selection"]],
        "active_command_count": len(command_names),
        "token_file_present": token_path.is_file(),
    }, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
