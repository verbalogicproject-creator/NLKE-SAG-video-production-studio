from __future__ import annotations

import os
from pathlib import Path
from typing import Any
from uuid import uuid4

import httpx
from mcp.server.fastmcp import FastMCP


mcp = FastMCP("SAG Video", instructions="Operate the canonical SAG Video timeline. Dispatch is not render success; inspect the returned receipt.")
DEFAULT_PROJECT_ID = os.getenv("SAG_VIDEO_PROJECT_ID", "demo")


def _access_token() -> str:
    token = os.getenv("SAG_VIDEO_TOKEN", "").strip()
    token_file = os.getenv("SAG_VIDEO_TOKEN_FILE", "").strip()
    if token or not token_file:
        return token
    try:
        return Path(token_file).read_text(encoding="utf-8").strip()
    except (OSError, UnicodeError):
        return ""


def _client() -> httpx.Client:
    headers: dict[str, str] = {}
    token = _access_token()
    invite = os.getenv("SAG_VIDEO_INVITE_TOKEN", "")
    if token:
        headers["Authorization"] = f"Bearer {token}"
    if invite:
        headers["X-Invite-Token"] = invite
    return httpx.Client(base_url=os.getenv("SAG_VIDEO_URL", "http://localhost:8080"), headers=headers, timeout=90)


def _request_id() -> str:
    return f"mcp-{uuid4()}"


def _json(response: httpx.Response) -> dict[str, Any]:
    response.raise_for_status()
    return response.json()


@mcp.tool()
def list_projects() -> dict[str, Any]:
    """List only the projects visible to the current paired identity."""
    with _client() as client:
        return _json(client.get("/api/projects"))


@mcp.tool()
def get_project_context(project_id: str = DEFAULT_PROJECT_ID) -> dict[str, Any]:
    """Get the current revision, semantic selection, and allowed reversible commands."""
    with _client() as client:
        return _json(client.get(f"/api/projects/{project_id}/context"))


@mcp.tool()
def get_application_contract() -> dict[str, Any]:
    """Discover entities, commands, effects, authority requirements, and read-only capabilities."""
    with _client() as client:
        return _json(client.get("/api/contract"))


@mcp.tool()
def list_active_commands(project_id: str = DEFAULT_PROJECT_ID) -> dict[str, Any]:
    """List active commands; availability does not grant mutation authority."""
    with _client() as client:
        return _json(client.get(f"/api/projects/{project_id}/commands/active"))


@mcp.tool()
def propose_actions(
    commands: list[dict[str, Any]], expected_revision: int,
    project_id: str = DEFAULT_PROJECT_ID,
) -> dict[str, Any]:
    """Preview an atomic semantic change without mutating the sequence."""
    with _client() as client:
        return _json(client.post(
            f"/api/projects/{project_id}/commands/propose",
            json={"commands": commands, "expected_revision": expected_revision},
        ))


@mcp.tool()
def execute_action_batch(
    commands: list[dict[str, Any]], expected_revision: int,
    project_id: str = DEFAULT_PROJECT_ID,
    confirmation_id: str | None = None,
) -> dict[str, Any]:
    """Commit an all-or-nothing batch of registry-declared reversible actions."""
    with _client() as client:
        return _json(client.post(
            f"/api/projects/{project_id}/commands/batch",
            json={
                "commands": commands, "expected_revision": expected_revision,
                "request_id": _request_id(), "actor": "mcp-agent",
                "confirmation_id": confirmation_id,
            },
        ))


@mcp.tool()
def get_selection(project_id: str = DEFAULT_PROJECT_ID) -> dict[str, Any]:
    """Get the exact application-owned semantic selection and project revision."""
    with _client() as client:
        context = _json(client.get(f"/api/projects/{project_id}/context"))
        return {"project_id": context["project_id"], "revision": context["revision"], "selection": context["selection"]}


@mcp.tool()
def get_spatial_snapshot(
    project_id: str = DEFAULT_PROJECT_ID, focus_id: str | None = None,
    depth: str = "context", hop_count: int = 2,
) -> dict[str, Any]:
    """Get the bounded deterministic semantic projection used by Studio and Codex."""
    parameters: dict[str, Any] = {"depth": depth, "hop_count": hop_count}
    if focus_id:
        parameters["focus_id"] = focus_id
    with _client() as client:
        return _json(client.get(f"/api/projects/{project_id}/spatial/snapshot", params=parameters))


@mcp.tool()
def get_current_spatial_focus(project_id: str = DEFAULT_PROJECT_ID) -> dict[str, Any]:
    """Resolve current focus to the same stable entity identities used by every Studio depth."""
    snapshot = get_spatial_snapshot(project_id=project_id)
    return {
        "project_id": project_id, "revision": snapshot["canonical_revision"],
        "projection_hash": snapshot["projection_hash"], "focus": snapshot["focus"],
    }


@mcp.tool()
def get_spatial_neighborhood(
    entity_id: str, project_id: str = DEFAULT_PROJECT_ID, hop_count: int = 2,
) -> dict[str, Any]:
    """Get a capped causal neighborhood around one exact semantic identity."""
    with _client() as client:
        return _json(client.get(
            f"/api/projects/{project_id}/spatial/entities/{entity_id}/neighborhood",
            params={"hop_count": hop_count},
        ))


@mcp.tool()
def get_spatial_hierarchy(project_id: str = DEFAULT_PROJECT_ID) -> dict[str, Any]:
    """Get the production-wide Workspace, Project, Sequence, and lifecycle hierarchy."""
    return get_spatial_snapshot(project_id=project_id, depth="system")


@mcp.tool()
def get_spatial_blast_radius(entity_id: str, project_id: str = DEFAULT_PROJECT_ID) -> dict[str, Any]:
    """Trace bounded downstream consequences from one exact semantic identity."""
    with _client() as client:
        return _json(client.get(f"/api/projects/{project_id}/spatial/entities/{entity_id}/blast-radius"))


@mcp.tool()
def get_semantic_graph(project_id: str = DEFAULT_PROJECT_ID, revision: int | None = None) -> dict[str, Any]:
    """Get the provider-neutral X1 draft graph adapter over the authoritative SAG projection."""
    parameters = {"revision": revision} if revision is not None else None
    with _client() as client:
        return _json(client.get(f"/api/projects/{project_id}/semantic/graph", params=parameters))


@mcp.tool()
def query_semantic_neighborhood(
    scope_uri: str, seed_uris: list[str], project_id: str = DEFAULT_PROJECT_ID,
    mode: str = "adjacent", max_hops: int = 2, relationship_kinds: list[str] | None = None,
    entity_limit: int = 200, edge_limit: int = 400, include_provenance: bool = True,
) -> dict[str, Any]:
    """Run a deterministic URI-based structural neighborhood query using the X1 draft contract."""
    with _client() as client:
        return _json(client.post(
            f"/api/projects/{project_id}/semantic/neighborhood",
            json={
                "schema_version": "sag-neighborhood/0.1-draft", "scope_uri": scope_uri,
                "seed_uris": seed_uris, "mode": mode, "relationship_kinds": relationship_kinds or [],
                "max_hops": max_hops, "entity_limit": entity_limit, "edge_limit": edge_limit,
                "include_provenance": include_provenance,
            },
        ))


@mcp.tool()
def list_journal_entries(project_id: str = DEFAULT_PROJECT_ID, limit: int = 200) -> dict[str, Any]:
    """List bounded durable causal entries; runtime telemetry is deliberately excluded."""
    with _client() as client:
        return _json(client.get(f"/api/projects/{project_id}/journal", params={"limit": limit}))


@mcp.tool()
def verify_journal(project_id: str = DEFAULT_PROJECT_ID) -> dict[str, Any]:
    """Verify the project journal hash chain and report the first continuity break."""
    with _client() as client:
        return _json(client.get(f"/api/projects/{project_id}/journal/verify"))


@mcp.tool()
def append_journal_entry(
    entry_id: str, kind: str, content: str, created_at: str,
    project_id: str = DEFAULT_PROJECT_ID, metadata: dict[str, Any] | None = None,
    tags: list[str] | None = None, session_id: str | None = None,
) -> dict[str, Any]:
    """Append one declared, bounded, idempotent entry to the durable causal journal."""
    with _client() as client:
        return _json(client.post(
            f"/api/projects/{project_id}/journal/entries",
            json={
                "id": entry_id, "kind": kind, "content": content, "created_at": created_at,
                "metadata": metadata or {}, "tags": tags or [], "session_id": session_id,
            },
        ))


@mcp.tool()
def request_spatial_directive(
    action: str, expected_revision: int, expected_projection_hash: str,
    target_ids: list[str] | None = None, project_id: str = DEFAULT_PROJECT_ID,
) -> dict[str, Any]:
    """Request a registry-declared reversible view action and return an awaiting-consumer receipt."""
    with _client() as client:
        return _json(client.post(
            f"/api/projects/{project_id}/spatial/directives",
            json={
                "action": action, "target_ids": target_ids or [],
                "expected_revision": expected_revision,
                "expected_projection_hash": expected_projection_hash,
                "intended_observed_effect": {"target_ids": target_ids or []},
            },
        ))


@mcp.tool()
def verify_spatial_receipt(receipt_id: str) -> dict[str, Any]:
    """Verify whether the matching browser reported an observed spatial effect."""
    receipt = get_receipt(receipt_id)
    return {
        "receipt_id": receipt_id, "command": receipt["command"], "status": receipt["status"],
        "observed": receipt["status"] in {"observed_success", "observed_failure", "timeout"},
        "payload": receipt["payload"],
    }


@mcp.tool()
def list_timeline_items(project_id: str = DEFAULT_PROJECT_ID) -> dict[str, Any]:
    """List stable tracks and timeline item identities in the canonical project."""
    with _client() as client:
        return _json(client.get(f"/api/projects/{project_id}"))


def _semantic_command(project_id: str, command: str, arguments: dict[str, Any], expected_revision: int) -> dict[str, Any]:
    with _client() as client:
        return _json(
            client.post(
                f"/api/projects/{project_id}/commands",
                json={
                    "command": command,
                    "arguments": arguments,
                    "expected_revision": expected_revision,
                    "request_id": _request_id(),
                    "actor": "mcp-agent",
                },
            )
        )


@mcp.tool()
def generate_shorts(
    source_revision: int,
    project_id: str = DEFAULT_PROJECT_ID,
    prompt: str | None = None,
    language: str = "auto",
    candidate_count: int = 5,
    asset_id: str | None = None,
    min_seconds: int = 15,
    max_seconds: int = 90,
) -> dict[str, Any]:
    """Start ranked short-clip discovery against an exact immutable source revision."""
    body: dict[str, Any] = {
        "source_revision": source_revision, "language": language,
        "candidate_count": candidate_count,
        "min_duration_ticks": min_seconds * 120000,
        "max_duration_ticks": max_seconds * 120000,
    }
    if prompt:
        body["prompt"] = prompt
    if asset_id:
        body["asset_id"] = asset_id
    with _client() as client:
        return _json(client.post(f"/api/projects/{project_id}/shorts/jobs", json=body))


@mcp.tool()
def list_short_drafts(project_id: str = DEFAULT_PROJECT_ID, state: str | None = "pending") -> dict[str, Any]:
    """List ranked short drafts with score evidence and immutable source lineage."""
    parameters = {"state": state} if state else {}
    with _client() as client:
        return _json(client.get(f"/api/projects/{project_id}/suggestions", params=parameters))


@mcp.tool()
def get_short_draft(suggestion_id: str) -> dict[str, Any]:
    """Inspect one short draft, its score components, transcript evidence, crop plan, and warnings."""
    with _client() as client:
        return _json(client.get(f"/api/suggestions/{suggestion_id}"))


@mcp.tool()
def accept_short_draft(suggestion_id: str, name: str | None = None) -> dict[str, Any]:
    """Create an independently editable vertical project from a pending draft."""
    body: dict[str, Any] = {"request_id": _request_id(), "actor": "mcp-agent", "expected_state": "pending"}
    if name:
        body["name"] = name
    with _client() as client:
        return _json(client.post(f"/api/suggestions/{suggestion_id}/accept", json=body))


@mcp.tool()
def reject_short_draft(suggestion_id: str) -> dict[str, Any]:
    """Reject a pending short draft while retaining its audit trail."""
    with _client() as client:
        return _json(client.post(
            f"/api/suggestions/{suggestion_id}/reject",
            json={"request_id": _request_id(), "actor": "mcp-agent", "expected_state": "pending"},
        ))


@mcp.tool()
def set_caption_style(
    item_id: str,expected_revision: int,project_id: str = DEFAULT_PROJECT_ID,
    preset: str = "bold_pop",position: str = "bottom",font_family: str = "Noto Sans",
    font_size: int = 64,text_color: str = "#FFFFFF",highlight_color: str = "#F8E71C",
    background_color: str = "#000000B8",words_per_cue: int = 5,
) -> dict[str, Any]:
    """Apply a validated caption preset and typography controls to an editable short."""
    return _semantic_command(project_id,"timeline.set_caption_style",{
        "item_id":item_id,"preset":preset,"position":position,"font_family":font_family,
        "font_size":font_size,"text_color":text_color,"highlight_color":highlight_color,
        "background_color":background_color,"words_per_cue":words_per_cue,
    },expected_revision)


@mcp.tool()
def set_crop_keyframes(item_id: str,keyframes: list[dict[str,Any]],expected_revision: int,project_id: str = DEFAULT_PROJECT_ID) -> dict[str,Any]:
    """Replace a video's bounded time-varying crop path for manual framing correction."""
    return _semantic_command(project_id,"timeline.set_crop_keyframes",{"item_id":item_id,"keyframes":keyframes},expected_revision)


@mcp.tool()
def set_caption_words(item_id: str,words: list[dict[str,Any]],expected_revision: int,project_id: str = DEFAULT_PROJECT_ID) -> dict[str,Any]:
    """Replace editable word-timed caption content while preserving explicit timing evidence."""
    return _semantic_command(project_id,"timeline.set_caption_words",{"item_id":item_id,"words":words},expected_revision)


@mcp.tool()
def set_selection(item_ids: list[str], expected_revision: int, project_id: str = DEFAULT_PROJECT_ID) -> dict[str, Any]:
    """Set actor-local semantic focus without overwriting the browser's shared focus."""
    with _client() as client:
        return _json(
            client.post(
                f"/api/projects/{project_id}/selection",
                json={
                    "item_ids": item_ids,
                    "expected_revision": expected_revision,
                    "request_id": _request_id(),
                    "actor": "mcp-agent",
                },
            )
        )


@mcp.tool()
def focus_browser(item_ids: list[str], expected_revision: int, project_id: str = DEFAULT_PROJECT_ID) -> dict[str, Any]:
    """Explicitly project stable timeline identities into the browser's shared focus."""
    with _client() as client:
        return _json(client.post(
            f"/api/projects/{project_id}/focus/shared",
            json={
                "item_ids": item_ids, "expected_revision": expected_revision,
                "request_id": _request_id(), "actor": "mcp-agent",
            },
        ))


@mcp.tool()
def insert_asset(asset_id: str, expected_revision: int, project_id: str = DEFAULT_PROJECT_ID, start_ticks: int | None = None) -> dict[str, Any]:
    """Insert one observed-valid managed asset on its compatible canonical track."""
    arguments: dict[str, Any] = {"asset_id": asset_id}
    if start_ticks is not None:
        arguments["start_ticks"] = start_ticks
    return _semantic_command(project_id, "timeline.insert_asset", arguments, expected_revision)


@mcp.tool()
def move_timeline_item(
    item_id: str, start_ticks: int, expected_revision: int, project_id: str = DEFAULT_PROJECT_ID,
    magnetic: bool = False, ripple: bool = False, snap_threshold_ticks: int | None = None,
) -> dict[str, Any]:
    """Move a stable timeline item to an exact integer-tick position."""
    arguments: dict[str, Any] = {
        "item_id": item_id, "start_ticks": start_ticks, "magnetic": magnetic, "ripple": ripple,
    }
    if snap_threshold_ticks is not None:
        arguments["snap_threshold_ticks"] = snap_threshold_ticks
    return _semantic_command(project_id, "timeline.move_item", arguments, expected_revision)


@mcp.tool()
def split_clip(item_id: str, at_ticks: int, expected_revision: int, project_id: str = DEFAULT_PROJECT_ID) -> dict[str, Any]:
    """Split a video or audio item at an exact timeline tick into two stable identities."""
    return _semantic_command(project_id, "timeline.split_clip", {"item_id": item_id, "at_ticks": at_ticks}, expected_revision)


@mcp.tool()
def delete_timeline_item(item_id: str, expected_revision: int, project_id: str = DEFAULT_PROJECT_ID) -> dict[str, Any]:
    """Request deletion. The server denies it without an exact browser-issued human confirmation."""
    return _semantic_command(project_id, "timeline.delete_item", {"item_id": item_id}, expected_revision)


@mcp.tool()
def set_title_transform(item_id: str, x: int, y: int, expected_revision: int, project_id: str = DEFAULT_PROJECT_ID) -> dict[str, Any]:
    """Move a title through a revision-checked, reversible semantic command."""
    with _client() as client:
        return _json(
            client.post(
                f"/api/projects/{project_id}/commands",
                json={
                    "command": "timeline.set_title_transform",
                    "arguments": {"item_id": item_id, "x": x, "y": y},
                    "expected_revision": expected_revision,
                    "request_id": _request_id(),
                    "actor": "mcp-agent",
                },
            )
        )


@mcp.tool()
def trim_clip(
    item_id: str, duration_ticks: int, expected_revision: int, project_id: str = DEFAULT_PROJECT_ID,
    start_ticks: int | None = None, source_in_ticks: int | None = None,
) -> dict[str, Any]:
    """Trim either clip edge atomically using 120,000 integer ticks per second."""
    arguments: dict[str, Any] = {"item_id": item_id, "duration_ticks": duration_ticks}
    if start_ticks is not None:
        arguments["start_ticks"] = start_ticks
    if source_in_ticks is not None:
        arguments["source_in_ticks"] = source_in_ticks
        arguments["source_out_ticks"] = source_in_ticks + duration_ticks
    return _semantic_command(project_id, "timeline.trim_clip", arguments, expected_revision)


@mcp.tool()
def set_clip_transform(
    item_id: str, expected_revision: int, project_id: str = DEFAULT_PROJECT_ID,
    x: int | None = None, y: int | None = None, scale: float | None = None,
    rotation: float | None = None, opacity: float | None = None, fit_mode: str | None = None,
) -> dict[str, Any]:
    """Move, resize, rotate, fade, or fit a visual clip through one semantic revision."""
    arguments: dict[str, Any] = {"item_id": item_id}
    for key, value in {"x": x, "y": y, "scale": scale, "rotation": rotation, "opacity": opacity, "fit_mode": fit_mode}.items():
        if value is not None:
            arguments[key] = value
    return _semantic_command(project_id, "timeline.set_clip_transform", arguments, expected_revision)


@mcp.tool()
def undo_revision(expected_revision: int, project_id: str = DEFAULT_PROJECT_ID) -> dict[str, Any]:
    """Create a compensating revision for the latest project edit."""
    with _client() as client:
        return _json(
            client.post(
                f"/api/projects/{project_id}/commands",
                json={
                    "command": "project.undo",
                    "arguments": {},
                    "expected_revision": expected_revision,
                    "request_id": _request_id(),
                    "actor": "mcp-agent",
                },
            )
        )


@mcp.tool()
def redo_revision(expected_revision: int, project_id: str = DEFAULT_PROJECT_ID) -> dict[str, Any]:
    """Reapply the next canonical edit after an undo."""
    return _semantic_command(project_id, "project.redo", {}, expected_revision)


@mcp.tool()
def start_verified_render(project_revision: int, project_id: str = DEFAULT_PROJECT_ID) -> dict[str, Any]:
    """Queue an exact revision and return an accepted receipt with a persistent job ID."""
    with _client() as client:
        return _json(
            client.post(
                f"/api/projects/{project_id}/renders",
                json={"project_revision": project_revision, "request_id": _request_id(), "actor": "mcp-agent"},
            )
        )


@mcp.tool()
def get_render_job(job_id: str) -> dict[str, Any]:
    """Inspect persistent render progress; only an observed terminal state proves the output."""
    with _client() as client:
        return _json(client.get(f"/api/jobs/{job_id}"))


@mcp.tool()
def cancel_render_job(job_id: str) -> dict[str, Any]:
    """Request cancellation of a nonterminal render job."""
    with _client() as client:
        return _json(client.post(f"/api/jobs/{job_id}/cancel", json={}))


@mcp.tool()
def get_receipt(receipt_id: str) -> dict[str, Any]:
    """Inspect a causal edit or render receipt and its bounded observation evidence."""
    with _client() as client:
        return _json(client.get(f"/api/receipts/{receipt_id}"))


def main() -> None:
    mcp.run(transport="stdio")


if __name__ == "__main__":
    main()
