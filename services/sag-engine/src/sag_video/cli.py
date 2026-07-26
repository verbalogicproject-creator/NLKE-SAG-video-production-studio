from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
from typing import Any
from urllib.error import HTTPError
from urllib.request import Request, urlopen
from uuid import uuid4

import httpx


def _api(method: str, path: str, body: dict[str, Any] | None = None) -> Any:
    base = os.getenv("SAG_VIDEO_URL", "http://localhost:8080").rstrip("/")
    token = os.getenv("SAG_VIDEO_TOKEN", "")
    invite = os.getenv("SAG_VIDEO_INVITE_TOKEN", "")
    data = json.dumps(body).encode() if body is not None else None
    headers = {"Content-Type": "application/json"}
    if token:
        headers["Authorization"] = f"Bearer {token}"
    if invite:
        headers["X-Invite-Token"] = invite
    request = Request(f"{base}{path}", data=data, headers=headers, method=method)
    try:
        with urlopen(request, timeout=90) as response:
            return json.load(response)
    except HTTPError as error:
        detail = error.read().decode(errors="replace")
        raise SystemExit(f"SAG Video API returned {error.code}: {detail}") from error


def _request_id() -> str:
    return f"cli-{uuid4()}"


def _multipart(path: str, fields: dict[str, str], file_path: Path) -> Any:
    base = os.getenv("SAG_VIDEO_URL", "http://localhost:8080").rstrip("/")
    headers: dict[str, str] = {}
    token = os.getenv("SAG_VIDEO_TOKEN", "")
    invite = os.getenv("SAG_VIDEO_INVITE_TOKEN", "")
    if token:
        headers["Authorization"] = f"Bearer {token}"
    if invite:
        headers["X-Invite-Token"] = invite
    with file_path.open("rb") as source, httpx.Client(base_url=base, headers=headers, timeout=180) as client:
        response = client.post(path, data=fields, files={"file": (file_path.name, source, "application/octet-stream")})
    if response.is_error:
        raise SystemExit(f"SAG Video API returned {response.status_code}: {response.text}")
    return response.json()


def parser() -> argparse.ArgumentParser:
    root = argparse.ArgumentParser(prog="sag-video", description="Operate a SAG Video project through semantic commands")
    root.add_argument("--project", default="demo")
    sub = root.add_subparsers(dest="area", required=True)

    contract = sub.add_parser("contract")
    contract_sub = contract.add_subparsers(dest="action", required=True)
    contract_show = contract_sub.add_parser("show")
    contract_show.add_argument("--json", action="store_true")

    context = sub.add_parser("context")
    context_sub = context.add_subparsers(dest="action", required=True)
    context_show = context_sub.add_parser("show")
    context_show.add_argument("--json", action="store_true")

    command = sub.add_parser("command")
    command_sub = command.add_subparsers(dest="action", required=True)
    command_list = command_sub.add_parser("list")
    command_list.add_argument("--active", action="store_true")
    command_list.add_argument("--json", action="store_true")

    action = sub.add_parser("action")
    action_sub = action.add_subparsers(dest="action", required=True)
    for name in ("propose", "batch"):
        operation = action_sub.add_parser(name)
        operation.add_argument("--commands-json", required=True, help="JSON array of registry command/arguments objects")
        operation.add_argument("--expected-revision", type=int, required=True)

    asset = sub.add_parser("asset")
    asset_sub = asset.add_subparsers(dest="action", required=True)
    asset_import = asset_sub.add_parser("import")
    asset_import.add_argument("file")
    asset_sub.add_parser("list")
    asset_show = asset_sub.add_parser("show")
    asset_show.add_argument("asset_id")
    asset_show.add_argument("--json", action="store_true")

    timeline = sub.add_parser("timeline")
    timeline_sub = timeline.add_subparsers(dest="action", required=True)
    insert = timeline_sub.add_parser("insert")
    insert.add_argument("asset_id")
    insert.add_argument("--start-ticks", type=int)
    insert.add_argument("--expected-revision", type=int, required=True)
    move_item = timeline_sub.add_parser("move")
    move_item.add_argument("item_id")
    move_item.add_argument("--start-ticks", type=int, required=True)
    move_item.add_argument("--magnetic", action="store_true")
    move_item.add_argument("--snap-threshold-ticks", type=int)
    move_item.add_argument("--ripple", action="store_true")
    move_item.add_argument("--expected-revision", type=int, required=True)
    split = timeline_sub.add_parser("split")
    split.add_argument("item_id")
    split.add_argument("--at-ticks", type=int, required=True)
    split.add_argument("--expected-revision", type=int, required=True)
    delete = timeline_sub.add_parser("delete")
    delete.add_argument("item_id")
    delete.add_argument("--expected-revision", type=int, required=True)

    project = sub.add_parser("project")
    project_sub = project.add_subparsers(dest="action", required=True)
    project_sub.add_parser("list")
    create = project_sub.add_parser("create")
    create.add_argument("name")
    create.add_argument("--preset", choices=["landscape_1080p", "vertical_1080p", "preview_540p"], default="landscape_1080p")
    show = project_sub.add_parser("show")
    show.add_argument("--json", action="store_true")
    undo = project_sub.add_parser("undo")
    undo.add_argument("--expected-revision", type=int, required=True)
    redo = project_sub.add_parser("redo")
    redo.add_argument("--expected-revision", type=int, required=True)

    selection = sub.add_parser("selection")
    selection_sub = selection.add_subparsers(dest="action", required=True)
    selection_set = selection_sub.add_parser("set")
    selection_set.add_argument("item_ids", nargs="+")
    selection_set.add_argument("--expected-revision", type=int, required=True)

    title = sub.add_parser("title")
    title_sub = title.add_subparsers(dest="action", required=True)
    move = title_sub.add_parser("move")
    move.add_argument("item_id")
    move.add_argument("--x", type=int, required=True)
    move.add_argument("--y", type=int, required=True)
    move.add_argument("--expected-revision", type=int, required=True)

    clip = sub.add_parser("clip")
    clip_sub = clip.add_subparsers(dest="action", required=True)
    trim = clip_sub.add_parser("trim")
    trim.add_argument("item_id")
    trim.add_argument("--start-ticks", type=int)
    trim.add_argument("--duration-ticks", type=int, required=True)
    trim.add_argument("--source-in-ticks", type=int)
    trim.add_argument("--expected-revision", type=int, required=True)
    transform = clip_sub.add_parser("transform")
    transform.add_argument("item_id")
    transform.add_argument("--x", type=int)
    transform.add_argument("--y", type=int)
    transform.add_argument("--scale", type=float)
    transform.add_argument("--rotation", type=float)
    transform.add_argument("--opacity", type=float)
    transform.add_argument("--fit-mode", choices=["fit", "fill", "stretch"])
    transform.add_argument("--expected-revision", type=int, required=True)
    crop = clip_sub.add_parser("crop")
    crop.add_argument("item_id")
    crop.add_argument("--keyframes-json", required=True, help="JSON array of time_ticks/center_x/center_y/zoom keyframes")
    crop.add_argument("--expected-revision", type=int, required=True)

    caption = sub.add_parser("caption")
    caption_sub = caption.add_subparsers(dest="action",required=True)
    caption_style = caption_sub.add_parser("style")
    caption_style.add_argument("item_id")
    caption_style.add_argument("--preset",choices=["bold_pop","clean","minimal"])
    caption_style.add_argument("--position",choices=["top","middle","bottom"])
    caption_style.add_argument("--font-family")
    caption_style.add_argument("--font-size",type=int)
    caption_style.add_argument("--text-color")
    caption_style.add_argument("--highlight-color")
    caption_style.add_argument("--background-color")
    caption_style.add_argument("--words-per-cue",type=int)
    caption_style.add_argument("--expected-revision",type=int,required=True)
    caption_words = caption_sub.add_parser("words")
    caption_words.add_argument("item_id")
    caption_words.add_argument("--words-json",required=True,help="JSON array of word IDs, text, and tick ranges")
    caption_words.add_argument("--expected-revision",type=int,required=True)

    render = sub.add_parser("render")
    render_sub = render.add_subparsers(dest="action", required=True)
    start = render_sub.add_parser("start")
    start.add_argument("--revision", type=int, required=True)
    status = render_sub.add_parser("status")
    status.add_argument("job_id")
    cancel = render_sub.add_parser("cancel")
    cancel.add_argument("job_id")

    shorts = sub.add_parser("shorts")
    shorts_sub = shorts.add_subparsers(dest="action", required=True)
    shorts_generate = shorts_sub.add_parser("generate")
    shorts_generate.add_argument("--revision", type=int, required=True)
    shorts_generate.add_argument("--asset-id")
    shorts_generate.add_argument("--prompt")
    shorts_generate.add_argument("--language", choices=["auto", "en", "he"], default="auto")
    shorts_generate.add_argument("--count", type=int, default=5)
    shorts_generate.add_argument("--min-seconds", type=int, default=15)
    shorts_generate.add_argument("--max-seconds", type=int, default=90)
    shorts_sub.add_parser("list").add_argument("--state", choices=["pending", "accepted", "rejected"])
    shorts_show = shorts_sub.add_parser("show")
    shorts_show.add_argument("suggestion_id")
    shorts_accept = shorts_sub.add_parser("accept")
    shorts_accept.add_argument("suggestion_id")
    shorts_accept.add_argument("--name")
    shorts_reject = shorts_sub.add_parser("reject")
    shorts_reject.add_argument("suggestion_id")

    receipt = sub.add_parser("receipt")
    receipt_sub = receipt.add_subparsers(dest="action", required=True)
    receipt_show = receipt_sub.add_parser("show")
    receipt_show.add_argument("receipt_id")
    receipt_show.add_argument("--json", action="store_true")

    pair = sub.add_parser("pair")
    pair.add_argument("code")
    pair.add_argument("--actor", default="terminal")
    pair.add_argument("--save-token", type=Path, help="write the short-lived paired token to a mode-0600 file")
    return root


def main() -> None:
    args = parser().parse_args()
    if args.area == "contract":
        result = _api("GET", "/api/contract")
    elif args.area == "context":
        result = _api("GET", f"/api/projects/{args.project}/context")
    elif args.area == "command":
        result = _api("GET", f"/api/projects/{args.project}/commands/active") if args.active else _api("GET", "/api/contract")
        if not args.active:
            result = {"commands": result["commands"]}
    elif args.area == "action":
        try:
            invocations = json.loads(args.commands_json)
        except json.JSONDecodeError as error:
            raise SystemExit(f"invalid --commands-json: {error}") from error
        body = {"commands": invocations, "expected_revision": args.expected_revision}
        if args.action == "batch":
            body.update({"request_id": _request_id(), "actor": "terminal"})
        result = _api("POST", f"/api/projects/{args.project}/commands/{args.action}", body)
    elif args.area == "asset" and args.action == "import":
        file_path = Path(args.file).expanduser()
        if not file_path.is_file():
            raise SystemExit(f"not a readable file: {file_path}")
        result = _multipart(
            f"/api/projects/{args.project}/assets/uploads",
            {"request_id": _request_id(), "actor": "terminal"},
            file_path,
        )
    elif args.area == "asset" and args.action == "list":
        project = _api("GET", f"/api/projects/{args.project}")
        result = {"project_id": args.project, "assets": project["project"]["assets"]}
    elif args.area == "asset":
        result = _api("GET", f"/api/projects/{args.project}/assets/{args.asset_id}")
    elif args.area == "timeline":
        command_names = {
            "insert": "timeline.insert_asset",
            "move": "timeline.move_item",
            "split": "timeline.split_clip",
            "delete": "timeline.delete_item",
        }
        arguments = {"asset_id": args.asset_id} if args.action == "insert" else {"item_id": args.item_id}
        if args.action == "insert" and args.start_ticks is not None:
            arguments["start_ticks"] = args.start_ticks
        elif args.action == "move":
            arguments["start_ticks"] = args.start_ticks
            if args.magnetic:
                arguments["magnetic"] = True
            if args.snap_threshold_ticks is not None:
                arguments["snap_threshold_ticks"] = args.snap_threshold_ticks
            if args.ripple:
                arguments["ripple"] = True
        elif args.action == "split":
            arguments["at_ticks"] = args.at_ticks
        result = _api(
            "POST",
            f"/api/projects/{args.project}/commands",
            {
                "command": command_names[args.action],
                "arguments": arguments,
                "expected_revision": args.expected_revision,
                "request_id": _request_id(),
                "actor": "terminal",
            },
        )
    elif args.area == "project" and args.action == "list":
        result = _api("GET", "/api/projects")
    elif args.area == "project" and args.action == "create":
        result = _api("POST", "/api/projects", {"name": args.name, "preset": args.preset})
    elif args.area == "project" and args.action == "show":
        result = _api("GET", f"/api/projects/{args.project}")
    elif args.area == "project":
        result = _api(
            "POST",
            f"/api/projects/{args.project}/commands",
            {
                "command": f"project.{args.action}",
                "arguments": {},
                "expected_revision": args.expected_revision,
                "request_id": _request_id(),
                "actor": "terminal",
            },
        )
    elif args.area == "selection":
        result = _api(
            "POST",
            f"/api/projects/{args.project}/selection",
            {"item_ids": args.item_ids, "expected_revision": args.expected_revision, "request_id": _request_id(), "actor": "terminal"},
        )
    elif args.area == "title":
        result = _api(
            "POST",
            f"/api/projects/{args.project}/commands",
            {
                "command": "timeline.set_title_transform",
                "arguments": {"item_id": args.item_id, "x": args.x, "y": args.y},
                "expected_revision": args.expected_revision,
                "request_id": _request_id(),
                "actor": "terminal",
            },
        )
    elif args.area == "clip":
        arguments = {"item_id": args.item_id}
        if args.action == "trim":
            arguments["duration_ticks"] = args.duration_ticks
            if args.start_ticks is not None:
                arguments["start_ticks"] = args.start_ticks
            if args.source_in_ticks is not None:
                arguments["source_in_ticks"] = args.source_in_ticks
                arguments["source_out_ticks"] = args.source_in_ticks + args.duration_ticks
            command = "timeline.trim_clip"
        elif args.action == "transform":
            for field in ("x", "y", "scale", "rotation", "opacity", "fit_mode"):
                value = getattr(args, field)
                if value is not None:
                    arguments[field] = value
            command = "timeline.set_clip_transform"
        else:
            try:
                arguments["keyframes"] = json.loads(args.keyframes_json)
            except json.JSONDecodeError as error:
                raise SystemExit(f"invalid --keyframes-json: {error}") from error
            command = "timeline.set_crop_keyframes"
        result = _api(
            "POST",
            f"/api/projects/{args.project}/commands",
            {
                "command": command,
                "arguments": arguments,
                "expected_revision": args.expected_revision,
                "request_id": _request_id(),
                "actor": "terminal",
            },
        )
    elif args.area == "caption":
        arguments = {"item_id":args.item_id}
        if args.action == "style":
            for field in ("preset","position","font_family","font_size","text_color","highlight_color","background_color","words_per_cue"):
                value = getattr(args,field)
                if value is not None:
                    arguments[field] = value
            command = "timeline.set_caption_style"
        else:
            try:
                arguments["words"] = json.loads(args.words_json)
            except json.JSONDecodeError as error:
                raise SystemExit(f"invalid --words-json: {error}") from error
            command = "timeline.set_caption_words"
        result = _api("POST",f"/api/projects/{args.project}/commands",{
            "command":command,"arguments":arguments,
            "expected_revision":args.expected_revision,"request_id":_request_id(),"actor":"terminal",
        })
    elif args.area == "render" and args.action == "start":
        result = _api(
            "POST",
            f"/api/projects/{args.project}/renders",
            {"project_revision": args.revision, "request_id": _request_id(), "actor": "terminal"},
        )
    elif args.area == "render" and args.action == "status":
        result = _api("GET", f"/api/jobs/{args.job_id}")
    elif args.area == "render":
        result = _api("POST", f"/api/jobs/{args.job_id}/cancel", {})
    elif args.area == "shorts" and args.action == "generate":
        body = {
            "source_revision": args.revision, "language": args.language,
            "candidate_count": args.count,
            "min_duration_ticks": args.min_seconds * 120000,
            "max_duration_ticks": args.max_seconds * 120000,
        }
        if args.asset_id:
            body["asset_id"] = args.asset_id
        if args.prompt:
            body["prompt"] = args.prompt
        result = _api("POST", f"/api/projects/{args.project}/shorts/jobs", body)
    elif args.area == "shorts" and args.action == "list":
        suffix = f"?state={args.state}" if args.state else ""
        result = _api("GET", f"/api/projects/{args.project}/suggestions{suffix}")
    elif args.area == "shorts" and args.action == "show":
        result = _api("GET", f"/api/suggestions/{args.suggestion_id}")
    elif args.area == "shorts" and args.action in {"accept", "reject"}:
        body = {"request_id": _request_id(), "actor": "terminal", "expected_state": "pending"}
        if args.action == "accept" and args.name:
            body["name"] = args.name
        result = _api("POST", f"/api/suggestions/{args.suggestion_id}/{args.action}", body)
    elif args.area == "receipt":
        result = _api("GET", f"/api/receipts/{args.receipt_id}")
    else:
        result = _api("POST", "/api/pairing/attach", {"code": args.code, "actor_name": args.actor})
        if args.save_token:
            token_path = args.save_token.expanduser().resolve()
            token_path.parent.mkdir(parents=True, exist_ok=True)
            descriptor = os.open(token_path, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
            with os.fdopen(descriptor, "w", encoding="utf-8") as token_file:
                token_file.write(result["access_token"] + "\n")
            token_path.chmod(0o600)
            result = {
                **result,
                "access_token": "[stored in token file]",
                "token_file": str(token_path),
            }
    print(json.dumps(result, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
