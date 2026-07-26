from __future__ import annotations

import json
import hashlib
import secrets
import sqlite3
import threading
from contextlib import contextmanager
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any
from uuid import uuid4

from .migrations import apply_migrations, read_project_snapshot, read_receipt, write_project_snapshot, write_receipt
from .models import APPLICATION_SCHEMA_VERSION, Project, Receipt, ReceiptStatus, utc_now
from .repository import (
    AnalysisArtifactRecord,
    ArtifactRecord,
    JobRecord,
    MediaBlobRecord,
    ModelRunRecord,
    SuggestionRecord,
)


def fixture_project() -> Project:
    second = 120_000
    return Project.model_validate(
        {
            "id": "demo",
            "name": "Verified developer demo",
            "schema_version": APPLICATION_SCHEMA_VERSION,
            "revision": 1,
            "duration_ticks": 6 * second,
            "canvas": {"width": 960, "height": 540, "fps_numerator": 30, "fps_denominator": 1},
            "assets": [
                {"id": "asset_intro", "kind": "generated", "name": "Terminal capture", "uri": "generated://slate/intro"},
                {"id": "asset_result", "kind": "generated", "name": "Product result", "uri": "generated://slate/result"},
            ],
            "tracks": [
                {
                    "id": "track_video",
                    "kind": "video",
                    "name": "Screen recordings",
                    "items": [
                        {
                            "id": "clip_terminal",
                            "kind": "video",
                            "track_id": "track_video",
                            "name": "Terminal assembles the cut",
                            "start_ticks": 0,
                            "duration_ticks": 3 * second,
                            "asset_id": "asset_intro",
                            "color": "#17213a",
                        },
                        {
                            "id": "clip_result",
                            "kind": "video",
                            "track_id": "track_video",
                            "name": "GUI reflects the revision",
                            "start_ticks": 3 * second,
                            "duration_ticks": 3 * second,
                            "asset_id": "asset_result",
                            "color": "#102b29",
                        },
                    ],
                },
                {
                    "id": "track_titles",
                    "kind": "overlay",
                    "name": "Titles",
                    "items": [
                        {
                            "id": "title_intro",
                            "kind": "title",
                            "track_id": "track_titles",
                            "name": "Observed effect",
                            "text": "DISPATCH IS NOT SUCCESS",
                            "start_ticks": int(0.6 * second),
                            "duration_ticks": int(3.9 * second),
                            "x": -22,
                            "y": 56,
                            "width": 410,
                            "height": 86,
                            "color": "#e940ff",
                        }
                    ],
                },
                {"id": "track_audio", "kind": "audio", "name": "Narration", "items": []},
            ],
        }
    )


def empty_project(name: str, preset: str, workspace_id: str | None = None) -> Project:
    canvases = {
        "landscape_1080p": {"width": 1920, "height": 1080},
        "vertical_1080p": {"width": 1080, "height": 1920},
        "preview_540p": {"width": 960, "height": 540},
    }
    canvas = canvases[preset]
    return Project.model_validate(
        {
            "id": f"project_{uuid4().hex[:12]}",
            "name": name.strip(),
            "workspace_id": workspace_id,
            "schema_version": APPLICATION_SCHEMA_VERSION,
            "revision": 1,
            "duration_ticks": 6 * 120_000,
            "canvas": {**canvas, "fps_numerator": 30, "fps_denominator": 1},
            "assets": [],
            "tracks": [
                {"id": "track_video", "kind": "video", "name": "Video", "items": []},
                {"id": "track_titles", "kind": "overlay", "name": "Titles", "items": []},
                {"id": "track_audio", "kind": "audio", "name": "Narration", "items": []},
            ],
        }
    )


class Store:
    """SQLite implementation of the provider-neutral repository contracts."""

    def __init__(self, database_path: str | Path):
        self.database_path = str(database_path)
        if self.database_path != ":memory:":
            Path(self.database_path).parent.mkdir(parents=True, exist_ok=True)
        self._lock = threading.RLock()
        self._connection = sqlite3.connect(self.database_path, check_same_thread=False)
        self._connection.row_factory = sqlite3.Row
        self._transaction_depth = 0
        self._connection.execute("PRAGMA busy_timeout=5000")
        self._connection.execute("PRAGMA synchronous=NORMAL")
        if self.database_path != ":memory:":
            self._connection.execute("PRAGMA journal_mode=WAL")
        apply_migrations(self._connection)
        self.seed()

    def close(self) -> None:
        self._connection.close()

    @contextmanager
    def transaction(self):
        """Run one atomic write unit, nesting repository writes without early commits."""
        with self._lock:
            outermost = self._transaction_depth == 0
            if outermost:
                self._connection.execute("BEGIN IMMEDIATE")
            self._transaction_depth += 1
            try:
                yield self
            except Exception:
                self._transaction_depth -= 1
                if outermost:
                    self._connection.rollback()
                raise
            else:
                self._transaction_depth -= 1
                if outermost:
                    self._connection.commit()

    @contextmanager
    def _write(self):
        with self._lock:
            if self._transaction_depth:
                yield self
            else:
                with self.transaction():
                    yield self

    def seed(self) -> None:
        with self.transaction():
            existing = self._connection.execute("SELECT 1 FROM projects WHERE id='demo'").fetchone()
            if existing is None:
                project = fixture_project()
                write_project_snapshot(self._connection, project, command="fixture.seed", actor="system")
                self._connection.execute(
                    "INSERT INTO selections(project_id,item_id,ordinal) VALUES (?,?,0)",
                    (project.id, "title_intro"),
                )

    def reset_demo(self) -> Project:
        project = fixture_project()
        with self.transaction():
            self._connection.execute("DELETE FROM projects WHERE id=?", (project.id,))
            write_project_snapshot(self._connection, project, command="fixture.reset", actor="browser")
            self._connection.execute(
                "INSERT INTO selections(project_id,item_id,ordinal) VALUES (?,?,0)",
                (project.id, "title_intro"),
            )
        return project

    def get_project(self, project_id: str) -> Project:
        with self._lock:
            return read_project_snapshot(self._connection, project_id)

    def get_project_for_update(self, project_id: str) -> Project:
        """Return the project head while holding the current write transaction."""
        return self.get_project(project_id)

    def get_project_revision(self, project_id: str, revision: int) -> Project:
        with self._lock:
            return read_project_snapshot(self._connection, project_id, revision)

    def list_projects(self) -> list[Project]:
        with self._lock:
            rows = self._connection.execute("SELECT id FROM projects ORDER BY updated_at DESC,id").fetchall()
            return [self.get_project(str(row["id"])) for row in rows]

    def list_projects_for_workspace(self, workspace_id: str) -> list[Project]:
        with self._lock:
            rows = self._connection.execute(
                "SELECT id FROM projects WHERE workspace_id=? ORDER BY updated_at DESC,id",
                (workspace_id,),
            ).fetchall()
            return [self.get_project(str(row["id"])) for row in rows]

    def project_in_workspace(self, project_id: str, workspace_id: str) -> bool:
        with self._lock:
            return self._connection.execute(
                "SELECT 1 FROM projects WHERE id=? AND workspace_id=?",
                (project_id, workspace_id),
            ).fetchone() is not None

    def workspace_for_project(self, project_id: str) -> str:
        with self._lock:
            row = self._connection.execute("SELECT workspace_id FROM projects WHERE id=?", (project_id,)).fetchone()
            if row is None:
                raise KeyError(project_id)
            return str(row["workspace_id"] or project_id)

    def create_project(self, name: str, preset: str, workspace_id: str | None = None) -> Project:
        project = empty_project(name, preset, workspace_id)
        with self.transaction():
            project.workspace_id = workspace_id or project.id
            self._connection.execute(
                "INSERT OR IGNORE INTO workspaces(id,name,created_at,updated_at) VALUES (?,?,?,?)",
                (project.workspace_id, project.name, project.updated_at, project.updated_at),
            )
            write_project_snapshot(self._connection, project, command="project.create", actor="browser")
        return project

    def create_derived_project(self, project: Project) -> Project:
        with self.transaction():
            workspace_id = project.workspace_id or project.id
            self._connection.execute(
                "INSERT OR IGNORE INTO workspaces(id,name,created_at,updated_at) VALUES (?,?,?,?)",
                (workspace_id, project.name, project.updated_at, project.updated_at),
            )
            write_project_snapshot(self._connection, project, command="shorts.accept", actor="system")
        return self.get_project(project.id)

    def put_project(self, project: Project) -> None:
        with self._write():
            write_project_snapshot(self._connection, project)

    def get_selection(self, project_id: str) -> list[str]:
        with self._lock:
            rows = self._connection.execute(
                "SELECT item_id FROM selections WHERE project_id=? ORDER BY ordinal",
                (project_id,),
            ).fetchall()
            return [str(row["item_id"]) for row in rows]

    def set_selection(self, project_id: str, item_ids: list[str]) -> None:
        with self._write():
            self._connection.execute("DELETE FROM selections WHERE project_id=?", (project_id,))
            self._connection.executemany(
                "INSERT INTO selections(project_id,item_id,ordinal) VALUES (?,?,?)",
                [(project_id, item_id, ordinal) for ordinal, item_id in enumerate(item_ids)],
            )

    def receipt_for_request(self, project_id: str, request_id: str) -> Receipt | None:
        with self._lock:
            row = self._connection.execute(
                "SELECT * FROM receipts WHERE project_id=? AND request_id=?",
                (project_id, request_id),
            ).fetchone()
            return read_receipt(self._connection, row) if row else None

    def get_receipt(self, receipt_id: str) -> Receipt:
        with self._lock:
            row = self._connection.execute("SELECT * FROM receipts WHERE id=?", (receipt_id,)).fetchone()
            if row is None:
                raise KeyError(receipt_id)
            return read_receipt(self._connection, row)

    def list_receipts(self, project_id: str, limit: int = 50) -> list[Receipt]:
        with self._lock:
            rows = self._connection.execute(
                "SELECT * FROM receipts WHERE project_id=? ORDER BY created_at DESC LIMIT ?",
                (project_id, limit),
            ).fetchall()
            return [read_receipt(self._connection, row) for row in rows]

    def create_receipt(
        self,
        *,
        project_id: str,
        command: str,
        status: ReceiptStatus,
        request_id: str,
        actor: str,
        project_revision: int,
        payload: dict[str, Any] | None = None,
    ) -> Receipt:
        existing = self.receipt_for_request(project_id, request_id)
        if existing:
            return existing
        now = utc_now()
        receipt = Receipt(
            id=f"receipt_{uuid4().hex[:16]}",
            project_id=project_id,
            command=command,
            status=status,
            request_id=request_id,
            actor=actor,
            project_revision=project_revision,
            payload={**(payload or {}), "transitions": [{"status": status.value, "at": now}]},
            created_at=now,
            updated_at=now,
        )
        with self._write():
            write_receipt(self._connection, receipt)
        return receipt

    def update_receipt(
        self,
        receipt: Receipt,
        status: ReceiptStatus,
        payload_patch: dict[str, Any] | None = None,
    ) -> Receipt:
        receipt.status = status
        receipt.updated_at = utc_now()
        receipt.payload.setdefault("transitions", []).append({"status": status.value, "at": receipt.updated_at})
        if payload_patch:
            receipt.payload.update(payload_patch)
        with self._write():
            write_receipt(self._connection, receipt)
        return receipt

    def append_event(
        self,
        *,
        before: Project,
        after: Project,
        request_id: str,
        actor: str,
        command: str,
        arguments: dict[str, Any],
    ) -> None:
        with self._write():
            write_project_snapshot(
                self._connection,
                after,
                request_id=request_id,
                actor=actor,
                command=command,
            )
            self._connection.execute(
                """INSERT INTO events(
                     project_id,before_revision,after_revision,request_id,actor,
                     command,arguments_json,created_at
                   ) VALUES (?,?,?,?,?,?,?,?)""",
                (
                    after.id, before.revision, after.revision, request_id, actor,
                    command, json.dumps(arguments, sort_keys=True), utc_now(),
                ),
            )

    def last_event(self, project_id: str) -> sqlite3.Row | None:
        with self._lock:
            return self._connection.execute(
                "SELECT * FROM events WHERE project_id=? ORDER BY id DESC LIMIT 1",
                (project_id,),
            ).fetchone()

    def _history_target_revision(self, project_id: str) -> int:
        event = self.last_event(project_id)
        if event is None:
            return self.get_project(project_id).revision
        if str(event["command"]) in {"project.undo", "project.redo"}:
            arguments = json.loads(event["arguments_json"] or "{}")
            if "history_target_revision" in arguments:
                return int(arguments["history_target_revision"])
        return self.get_project(project_id).revision

    def previous_edit_revision(self, project_id: str) -> int | None:
        target = self._history_target_revision(project_id)
        row = self._connection.execute(
            """SELECT before_revision FROM events
               WHERE project_id=? AND command NOT IN ('project.undo','project.redo') AND after_revision<=?
               ORDER BY after_revision DESC,id DESC LIMIT 1""",
            (project_id, target),
        ).fetchone()
        return int(row["before_revision"]) if row else None

    def next_edit_revision(self, project_id: str) -> int | None:
        event = self.last_event(project_id)
        if event is None or str(event["command"]) not in {"project.undo", "project.redo"}:
            return None
        target = self._history_target_revision(project_id)
        row = self._connection.execute(
            """SELECT after_revision FROM events
               WHERE project_id=? AND command NOT IN ('project.undo','project.redo') AND before_revision>=?
               ORDER BY before_revision,after_revision,id LIMIT 1""",
            (project_id, target),
        ).fetchone()
        return int(row["after_revision"]) if row else None

    def start_pairing(
        self,
        workspace_id: str,
        *,
        project_id: str | None = None,
        sequence_id: str | None = None,
        scopes: list[str] | None = None,
    ) -> tuple[str, str]:
        code = f"{secrets.randbelow(1_000_000):06d}"
        expires = datetime.now(timezone.utc) + timedelta(minutes=10)
        with self._write():
            self._connection.execute(
                """INSERT INTO pairings(
                     code,workspace_id,project_id,sequence_id,scopes_json,expires_at,consumed
                   ) VALUES (?,?,?,?,?,?,0)""",
                (code, workspace_id, project_id, sequence_id, json.dumps(scopes or []), expires.isoformat()),
            )
        return code, expires.isoformat()

    def attach_pairing(self, code: str, actor_name: str) -> tuple[str, str, dict[str, Any]]:
        with self.transaction():
            row = self._connection.execute("SELECT * FROM pairings WHERE code=?", (code,)).fetchone()
            if row is None or row["consumed"]:
                raise ValueError("invalid or consumed pairing code")
            if datetime.fromisoformat(row["expires_at"]) < datetime.now(timezone.utc):
                raise ValueError("expired pairing code")
            self._connection.execute("UPDATE pairings SET consumed=1 WHERE code=?", (code,))
            token, expires_at = self.issue_token(
                str(row["workspace_id"]), actor_name,
                project_id=row["project_id"], sequence_id=row["sequence_id"],
                scopes=json.loads(row["scopes_json"] or "[]"),
            )
        return token, expires_at, self.principal_for_token(token) or {}

    def principal_for_token(self, token: str) -> dict[str, Any] | None:
        row = self._connection.execute("SELECT * FROM tokens WHERE token=?", (token,)).fetchone()
        if row is None or row["revoked"]:
            return None
        if datetime.fromisoformat(row["expires_at"]) < datetime.now(timezone.utc):
            return None
        return {
            "actor_name": str(row["actor_name"]),
            "workspace_id": str(row["workspace_id"]),
            "project_id": str(row["project_id"]) if row["project_id"] else None,
            "sequence_id": str(row["sequence_id"]) if row["sequence_id"] else None,
            "scopes": json.loads(row["scopes_json"] or "[]"),
            "token": token,
            "expires_at": str(row["expires_at"]),
        }

    def actor_for_token(self, token: str) -> str | None:
        principal = self.principal_for_token(token)
        return principal["actor_name"] if principal else None

    def issue_token(
        self,
        workspace_id: str,
        actor_name: str,
        *,
        hours: int = 8,
        project_id: str | None = None,
        sequence_id: str | None = None,
        scopes: list[str] | None = None,
    ) -> tuple[str, str]:
        token = secrets.token_urlsafe(32)
        expires = datetime.now(timezone.utc) + timedelta(hours=hours)
        with self._write():
            self._connection.execute(
                """INSERT INTO tokens(
                     token,workspace_id,project_id,sequence_id,scopes_json,actor_name,expires_at,revoked
                   ) VALUES (?,?,?,?,?,?,?,0)""",
                (token, workspace_id, project_id, sequence_id, json.dumps(scopes or ["*"]), actor_name, expires.isoformat()),
            )
        return token, expires.isoformat()

    def active_actors(self, workspace_id: str) -> list[dict[str, str]]:
        now = datetime.now(timezone.utc)
        rows = self._connection.execute(
            "SELECT actor_name,expires_at,project_id,scopes_json FROM tokens WHERE workspace_id=? AND revoked=0 ORDER BY rowid DESC",
            (workspace_id,),
        ).fetchall()
        return [
            {
                "actor_name": str(row["actor_name"]), "expires_at": str(row["expires_at"]),
                "project_id": str(row["project_id"]) if row["project_id"] else None,
                "scopes": json.loads(row["scopes_json"] or "[]"),
            }
            for row in rows
            if datetime.fromisoformat(row["expires_at"]) >= now
        ]

    def revoke_token(self, token: str) -> None:
        with self._write():
            self._connection.execute("UPDATE tokens SET revoked=1 WHERE token=?", (token,))

    def set_actor_focus(
        self, token: str, project_id: str, item_ids: list[str],
        *, visible_surface: str = "studio", active_workflow: str | None = None,
        active_depth: str = "edit",
    ) -> None:
        with self._write():
            self._connection.execute(
                """INSERT INTO actor_focus(token,project_id,item_ids_json,visible_surface,active_workflow,active_depth,updated_at)
                   VALUES (?,?,?,?,?,?,?) ON CONFLICT(token,project_id) DO UPDATE SET
                   item_ids_json=excluded.item_ids_json,visible_surface=excluded.visible_surface,
                   active_workflow=excluded.active_workflow,active_depth=excluded.active_depth,
                   updated_at=excluded.updated_at""",
                (token, project_id, json.dumps(item_ids), visible_surface, active_workflow, active_depth, utc_now()),
            )

    def get_actor_focus(self, token: str | None, project_id: str) -> dict[str, Any]:
        if not token:
            return {"item_ids": [], "visible_surface": "studio", "active_workflow": None, "active_depth": "edit"}
        row = self._connection.execute(
            "SELECT * FROM actor_focus WHERE token=? AND project_id=?", (token, project_id)
        ).fetchone()
        if row is None:
            return {"item_ids": [], "visible_surface": "studio", "active_workflow": None, "active_depth": "edit"}
        return {
            "item_ids": json.loads(row["item_ids_json"] or "[]"),
            "visible_surface": str(row["visible_surface"]),
            "active_workflow": row["active_workflow"],
            "active_depth": str(row["active_depth"] or "edit"),
            "updated_at": str(row["updated_at"]),
        }

    def reconcile_event_definitions(self, definitions: tuple[Any, ...]) -> None:
        with self.transaction():
            for definition in definitions:
                existing = self._connection.execute(
                    "SELECT source_hash,release_status FROM sag_event_definitions WHERE kind=?",
                    (definition.kind,),
                ).fetchone()
                if (
                    existing is not None
                    and str(existing["release_status"]) == "released"
                    and str(existing["source_hash"]) != definition.source_hash
                ):
                    raise RuntimeError(f"released runtime event schema drift: {definition.kind}")
                self._connection.execute(
                    """INSERT INTO sag_event_definitions(
                         kind,version,json_schema,source_hash,release_status,retention_class,reconciled_at
                       ) VALUES (?,?,?,?,?,?,?) ON CONFLICT(kind) DO UPDATE SET
                         version=excluded.version,json_schema=excluded.json_schema,
                         source_hash=excluded.source_hash,release_status=excluded.release_status,
                         retention_class=excluded.retention_class,reconciled_at=excluded.reconciled_at""",
                    (
                        definition.kind, definition.version,
                        json.dumps(definition.json_schema, sort_keys=True), definition.source_hash,
                        definition.release_status, definition.retention_class, utc_now(),
                    ),
                )

    def append_runtime_event(
        self, *, event_id: str, workspace_id: str, project_id: str, sequence_id: str,
        revision: int, actor: str, session_id: str | None, kind: str,
        trace_id: str | None, payload: dict[str, Any], created_at: str, expires_at: str,
    ) -> dict[str, Any]:
        with self._write():
            if self._connection.execute(
                "SELECT 1 FROM sag_event_definitions WHERE kind=?", (kind,)
            ).fetchone() is None:
                raise RuntimeError(f"runtime event kind must be registered before emit: {kind}")
            self._connection.execute(
                """INSERT INTO sag_runtime_events(
                     event_id,workspace_id,project_id,sequence_id,revision,actor,session_id,
                     kind,trace_id,payload_json,created_at,expires_at
                   ) VALUES (?,?,?,?,?,?,?,?,?,?,?,?)""",
                (
                    event_id, workspace_id, project_id, sequence_id, revision, actor,
                    session_id, kind, trace_id, json.dumps(payload, sort_keys=True), created_at, expires_at,
                ),
            )
            row = self._connection.execute(
                "SELECT * FROM sag_runtime_events WHERE event_id=?", (event_id,)
            ).fetchone()
        return self._runtime_event_dict(row)

    @staticmethod
    def _runtime_event_dict(row: Any) -> dict[str, Any]:
        return {
            "cursor": int(row["cursor"]), "event_id": str(row["event_id"]),
            "workspace_id": str(row["workspace_id"]), "project_id": str(row["project_id"]),
            "sequence_id": str(row["sequence_id"]), "revision": int(row["revision"]),
            "actor": str(row["actor"]), "session_id": row["session_id"],
            "kind": str(row["kind"]), "trace_id": row["trace_id"],
            "payload": json.loads(row["payload_json"] or "{}"),
            "created_at": str(row["created_at"]), "expires_at": str(row["expires_at"]),
        }

    def list_runtime_events(
        self, project_id: str, *, after_cursor: int = 0, limit: int = 200,
    ) -> list[dict[str, Any]]:
        with self._lock:
            rows = self._connection.execute(
                """SELECT * FROM sag_runtime_events
                   WHERE project_id=? AND cursor>? ORDER BY cursor LIMIT ?""",
                (project_id, after_cursor, limit),
            ).fetchall()
            return [self._runtime_event_dict(row) for row in rows]

    def get_runtime_event(self, project_id: str, event_id: str) -> dict[str, Any]:
        with self._lock:
            row = self._connection.execute(
                "SELECT * FROM sag_runtime_events WHERE project_id=? AND event_id=?",
                (project_id, event_id),
            ).fetchone()
            if row is None:
                raise KeyError(event_id)
            return self._runtime_event_dict(row)

    def latest_runtime_event(self, project_id: str, kind: str) -> dict[str, Any] | None:
        with self._lock:
            row = self._connection.execute(
                """SELECT * FROM sag_runtime_events
                   WHERE project_id=? AND kind=? ORDER BY cursor DESC LIMIT 1""",
                (project_id, kind),
            ).fetchone()
            return self._runtime_event_dict(row) if row is not None else None

    def find_runtime_event(self, project_id: str, kind: str, session_id: str) -> dict[str, Any]:
        with self._lock:
            row = self._connection.execute(
                """SELECT * FROM sag_runtime_events
                   WHERE project_id=? AND kind=? AND session_id=? ORDER BY cursor DESC LIMIT 1""",
                (project_id, kind, session_id),
            ).fetchone()
            if row is None:
                raise KeyError(session_id)
            return self._runtime_event_dict(row)

    def runtime_cursor_bounds(self, project_id: str) -> tuple[int | None, int | None]:
        row = self._connection.execute(
            "SELECT MIN(cursor) AS oldest,MAX(cursor) AS newest FROM sag_runtime_events WHERE project_id=?",
            (project_id,),
        ).fetchone()
        return (
            int(row["oldest"]) if row and row["oldest"] is not None else None,
            int(row["newest"]) if row and row["newest"] is not None else None,
        )

    def prune_runtime_events(self, project_id: str, *, max_events: int = 50_000) -> int:
        removed = 0
        with self._write():
            cursor = self._connection.execute(
                "DELETE FROM sag_runtime_events WHERE project_id=? AND expires_at<?",
                (project_id, utc_now()),
            )
            removed += max(0, int(getattr(cursor, "rowcount", 0) or 0))
            boundary = self._connection.execute(
                """SELECT cursor FROM sag_runtime_events WHERE project_id=?
                   ORDER BY cursor DESC LIMIT 1 OFFSET ?""",
                (project_id, max_events - 1),
            ).fetchone()
            if boundary is not None:
                cursor = self._connection.execute(
                    "DELETE FROM sag_runtime_events WHERE project_id=? AND cursor<?",
                    (project_id, int(boundary["cursor"])),
                )
                removed += max(0, int(getattr(cursor, "rowcount", 0) or 0))
        return removed

    def reconcile_journal_kinds(self, definitions: tuple[dict[str, Any], ...]) -> None:
        with self.transaction():
            for definition in definitions:
                existing = self._connection.execute(
                    "SELECT source_hash,release_status FROM sag_journal_kind_definitions WHERE kind=?",
                    (definition["kind"],),
                ).fetchone()
                if (
                    existing is not None
                    and str(existing["release_status"]) == "released"
                    and str(existing["source_hash"]) != definition["source_hash"]
                ):
                    raise RuntimeError(f"released journal kind drift: {definition['kind']}")
                self._connection.execute(
                    """INSERT INTO sag_journal_kind_definitions(
                         kind,version,protocol,release_status,source_hash,reconciled_at
                       ) VALUES (?,?,?,?,?,?) ON CONFLICT(kind) DO UPDATE SET
                         version=excluded.version,protocol=excluded.protocol,
                         release_status=excluded.release_status,source_hash=excluded.source_hash,
                         reconciled_at=excluded.reconciled_at""",
                    (
                        definition["kind"], definition["version"], definition["protocol"],
                        definition["release_status"], definition["source_hash"], utc_now(),
                    ),
                )

    def journal_kind_registered(self, kind: str) -> bool:
        return self._connection.execute(
            "SELECT 1 FROM sag_journal_kind_definitions WHERE kind=?", (kind,)
        ).fetchone() is not None

    @staticmethod
    def _journal_entry_dict(row: Any) -> dict[str, Any]:
        return {
            "namespace": str(row["namespace"]), "seq": int(row["seq"]) if row["seq"] is not None else None,
            "prev_hash": row["prev_hash"], "row_hash": row["row_hash"], "hash_alg": row["hash_alg"],
            "id": str(row["id"]), "kind": str(row["kind"]), "content": str(row["content"]),
            "session_id": row["session_id"], "batch": row["batch"],
            "tags": json.loads(row["tags_json"] or "[]"),
            "metadata": json.loads(row["metadata_json"] or "{}"),
            "method": str(row["method"]), "schema_version": int(row["schema_version"]),
            "created_at": str(row["created_at"]),
        }

    def get_journal_entry(self, namespace: str, entry_id: str) -> dict[str, Any] | None:
        row = self._connection.execute(
            "SELECT * FROM sag_journal_entries WHERE namespace=? AND id=?", (namespace, entry_id)
        ).fetchone()
        return self._journal_entry_dict(row) if row is not None else None

    def get_journal_head_for_update(self, namespace: str, hash_alg: str) -> tuple[int, str | None, str]:
        self._connection.execute(
            """INSERT INTO sag_journal_streams(namespace,head_seq,head_hash,hash_alg,updated_at)
               VALUES (?,0,NULL,?,?) ON CONFLICT(namespace) DO NOTHING""",
            (namespace, hash_alg, utc_now()),
        )
        row = self._connection.execute(
            "SELECT head_seq,head_hash,hash_alg FROM sag_journal_streams WHERE namespace=?", (namespace,)
        ).fetchone()
        return int(row["head_seq"]), row["head_hash"], str(row["hash_alg"])

    def insert_journal_entry(self, row: dict[str, Any]) -> dict[str, Any]:
        self._connection.execute(
            """INSERT INTO sag_journal_entries(
                 namespace,seq,id,prev_hash,row_hash,hash_alg,kind,content,session_id,batch,
                 tags_json,metadata_json,method,schema_version,created_at
               ) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
            (
                row["namespace"], row["seq"], row["id"], row["prev_hash"], row["row_hash"],
                row["hash_alg"], row["kind"], row["content"], row.get("session_id"), row.get("batch"),
                json.dumps(row.get("tags", [])), json.dumps(row.get("metadata", {})),
                row["method"], row["schema_version"], row["created_at"],
            ),
        )
        return self.get_journal_entry(row["namespace"], row["id"])

    def advance_journal_head(self, namespace: str, seq: int, row_hash: str, hash_alg: str) -> None:
        cursor = self._connection.execute(
            """UPDATE sag_journal_streams SET head_seq=?,head_hash=?,hash_alg=?,updated_at=?
               WHERE namespace=? AND head_seq=?""",
            (seq, row_hash, hash_alg, utc_now(), namespace, seq - 1),
        )
        if int(getattr(cursor, "rowcount", 0) or 0) != 1:
            raise RuntimeError("journal head changed during append")

    def list_journal_entries(
        self, namespace: str, *, limit: int = 200, include_unchained: bool = True,
    ) -> list[dict[str, Any]]:
        predicate = "namespace=?" if include_unchained else "namespace=? AND seq IS NOT NULL"
        rows = self._connection.execute(
            f"""SELECT * FROM sag_journal_entries WHERE {predicate}
                ORDER BY CASE WHEN seq IS NULL THEN 1 ELSE 0 END,seq,created_at,id LIMIT ?""",
            (namespace, max(1, limit)),
        ).fetchall()
        return [self._journal_entry_dict(row) for row in rows]

    def count_unchained_journal_entries(self, namespace: str) -> int:
        row = self._connection.execute(
            "SELECT COUNT(*) AS value FROM sag_journal_entries WHERE namespace=? AND seq IS NULL", (namespace,)
        ).fetchone()
        return int(row["value"])

    @staticmethod
    def _provider_connection_summary(row: Any) -> dict[str, Any]:
        return {
            "id": str(row["id"]), "workspace_id": str(row["workspace_id"]),
            "provider": str(row["provider"]), "purpose": str(row["purpose"]),
            "display_name": str(row["display_name"]), "state": str(row["state"]),
            "scopes": json.loads(row["scopes_json"] or "[]"),
            "secret_fingerprint": str(row["secret_fingerprint"]),
            "metadata": json.loads(row["metadata_json"] or "{}"),
            "created_at": str(row["created_at"]), "updated_at": str(row["updated_at"]),
        }

    def list_provider_connections(self, workspace_id: str) -> list[dict[str, Any]]:
        rows = self._connection.execute(
            "SELECT * FROM provider_connections WHERE workspace_id=? ORDER BY updated_at DESC,id",
            (workspace_id,),
        ).fetchall()
        return [self._provider_connection_summary(row) for row in rows]

    def get_provider_connection_secret(self, workspace_id: str, connection_id: str) -> dict[str, Any]:
        row = self._connection.execute(
            "SELECT * FROM provider_connections WHERE workspace_id=? AND id=?",
            (workspace_id, connection_id),
        ).fetchone()
        if row is None:
            raise KeyError(connection_id)
        value = self._provider_connection_summary(row)
        value.update({
            "encrypted_secret": str(row["encrypted_secret"]),
            "kms_key_version": str(row["kms_key_version"]),
        })
        return value

    def put_provider_connection(
        self, *, connection_id: str, workspace_id: str, provider: str, purpose: str,
        display_name: str, state: str, scopes: list[str], encrypted_secret: str,
        kms_key_version: str, secret_fingerprint: str, metadata: dict[str, Any],
    ) -> dict[str, Any]:
        now = utc_now()
        with self._write():
            self._connection.execute(
                """INSERT INTO provider_connections(
                     id,workspace_id,provider,purpose,display_name,state,scopes_json,
                     encrypted_secret,kms_key_version,secret_fingerprint,metadata_json,created_at,updated_at
                   ) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?) ON CONFLICT(id) DO UPDATE SET
                     provider=excluded.provider,purpose=excluded.purpose,display_name=excluded.display_name,
                     state=excluded.state,scopes_json=excluded.scopes_json,
                     encrypted_secret=excluded.encrypted_secret,kms_key_version=excluded.kms_key_version,
                     secret_fingerprint=excluded.secret_fingerprint,metadata_json=excluded.metadata_json,
                     updated_at=excluded.updated_at""",
                (
                    connection_id, workspace_id, provider, purpose, display_name, state,
                    json.dumps(sorted(set(scopes))), encrypted_secret, kms_key_version,
                    secret_fingerprint, json.dumps(metadata, sort_keys=True), now, now,
                ),
            )
        return self.get_provider_connection_secret(workspace_id, connection_id)

    def revoke_provider_connection(self, workspace_id: str, connection_id: str) -> dict[str, Any]:
        with self._write():
            cursor = self._connection.execute(
                "UPDATE provider_connections SET state='revoked',updated_at=? WHERE workspace_id=? AND id=?",
                (utc_now(), workspace_id, connection_id),
            )
            if not int(getattr(cursor, "rowcount", 0) or 0):
                raise KeyError(connection_id)
        return self.get_provider_connection_secret(workspace_id, connection_id)

    def put_delivery_profile(self, row: dict[str, Any]) -> dict[str, Any]:
        now = utc_now()
        created_at = row.get("created_at", now)
        updated_at = row.get("updated_at", created_at)
        with self._write():
            self._connection.execute(
                """INSERT INTO delivery_profiles(
                     id,project_id,destination,aspect_ratio,width,height,caption_placement,
                     safe_zone_x,safe_zone_y,metadata_json,created_at,updated_at
                   ) VALUES (?,?,?,?,?,?,?,?,?,?,?,?) ON CONFLICT(project_id,destination) DO UPDATE SET
                     aspect_ratio=excluded.aspect_ratio,width=excluded.width,height=excluded.height,
                     caption_placement=excluded.caption_placement,safe_zone_x=excluded.safe_zone_x,
                     safe_zone_y=excluded.safe_zone_y,metadata_json=excluded.metadata_json,
                     updated_at=excluded.updated_at""",
                (
                    row["id"], row["project_id"], row["destination"], row["aspect_ratio"],
                    row["width"], row["height"], row["caption_placement"], row["safe_zone_x"],
                    row["safe_zone_y"], json.dumps(row.get("metadata", {}), sort_keys=True), created_at, updated_at,
                ),
            )
        return next(entry for entry in self.list_delivery_profiles(row["project_id"]) if entry["destination"] == row["destination"])

    def list_delivery_profiles(self, project_id: str) -> list[dict[str, Any]]:
        rows = self._connection.execute(
            "SELECT * FROM delivery_profiles WHERE project_id=? ORDER BY destination,id", (project_id,)
        ).fetchall()
        return [{
            "id": str(row["id"]), "project_id": str(row["project_id"]),
            "destination": str(row["destination"]), "aspect_ratio": str(row["aspect_ratio"]),
            "width": int(row["width"]), "height": int(row["height"]),
            "caption_placement": str(row["caption_placement"]),
            "safe_zone_x": int(row["safe_zone_x"]), "safe_zone_y": int(row["safe_zone_y"]),
            "metadata": json.loads(row["metadata_json"] or "{}"),
            "created_at": str(row["created_at"]), "updated_at": str(row["updated_at"]),
        } for row in rows]

    @staticmethod
    def _release_approval_dict(row: Any) -> dict[str, Any]:
        return {
            "id": str(row["id"]), "workspace_id": str(row["workspace_id"]),
            "project_id": str(row["project_id"]), "project_revision": int(row["project_revision"]),
            "bundle_hash": str(row["bundle_hash"]),
            "artifact_hashes": json.loads(row["artifact_hashes_json"] or "[]"),
            "destinations": json.loads(row["destinations_json"] or "[]"),
            "state": str(row["state"]), "approved_by": str(row["approved_by"]),
            "expires_at": str(row["expires_at"]), "consumed_at": row["consumed_at"],
            "created_at": str(row["created_at"]),
        }

    def put_release_approval(self, row: dict[str, Any]) -> dict[str, Any]:
        with self._write():
            self._connection.execute(
                """INSERT INTO release_approvals(
                     id,workspace_id,project_id,project_revision,bundle_hash,artifact_hashes_json,
                     destinations_json,state,approved_by,expires_at,consumed_at,created_at
                   ) VALUES (?,?,?,?,?,?,?,?,?,?,?,?) ON CONFLICT(workspace_id,bundle_hash) DO NOTHING""",
                (
                    row["id"], row["workspace_id"], row["project_id"], row["project_revision"],
                    row["bundle_hash"], json.dumps(row["artifact_hashes"], sort_keys=True),
                    json.dumps(row["destinations"], sort_keys=True), row["state"], row["approved_by"],
                    row["expires_at"], row.get("consumed_at"), row["created_at"],
                ),
            )
        existing = self._connection.execute(
            "SELECT * FROM release_approvals WHERE workspace_id=? AND bundle_hash=?",
            (row["workspace_id"], row["bundle_hash"]),
        ).fetchone()
        return self._release_approval_dict(existing)

    def get_release_approval(self, project_id: str, approval_id: str) -> dict[str, Any]:
        row = self._connection.execute(
            "SELECT * FROM release_approvals WHERE project_id=? AND id=?", (project_id, approval_id)
        ).fetchone()
        if row is None:
            raise KeyError(approval_id)
        return self._release_approval_dict(row)

    def list_release_approvals(self, project_id: str) -> list[dict[str, Any]]:
        rows = self._connection.execute(
            "SELECT * FROM release_approvals WHERE project_id=? ORDER BY created_at DESC,id", (project_id,)
        ).fetchall()
        return [self._release_approval_dict(row) for row in rows]

    def consume_release_approval(self, project_id: str, approval_id: str) -> dict[str, Any]:
        with self._write():
            cursor = self._connection.execute(
                """UPDATE release_approvals SET state='consumed',consumed_at=?
                   WHERE project_id=? AND id=? AND state='active'""",
                (utc_now(), project_id, approval_id),
            )
            if not int(getattr(cursor, "rowcount", 0) or 0):
                raise ValueError("release approval is not active")
        return self.get_release_approval(project_id, approval_id)

    @staticmethod
    def _release_attempt_dict(row: Any) -> dict[str, Any]:
        return {
            "id": str(row["id"]), "workspace_id": str(row["workspace_id"]),
            "project_id": str(row["project_id"]), "approval_id": str(row["approval_id"]),
            "destination": str(row["destination"]), "idempotency_key": str(row["idempotency_key"]),
            "state": str(row["state"]), "external_id": row["external_id"],
            "bounded_error": row["bounded_error"], "attempt": int(row["attempt"]),
            "created_at": str(row["created_at"]), "updated_at": str(row["updated_at"]),
        }

    def put_release_attempt(self, row: dict[str, Any]) -> dict[str, Any]:
        now = utc_now()
        created_at = row.get("created_at", now)
        updated_at = row.get("updated_at", created_at)
        with self._write():
            self._connection.execute(
                """INSERT INTO release_publication_attempts(
                     id,workspace_id,project_id,approval_id,destination,idempotency_key,state,
                     external_id,bounded_error,attempt,created_at,updated_at
                   ) VALUES (?,?,?,?,?,?,?,?,?,?,?,?) ON CONFLICT(approval_id,destination) DO NOTHING""",
                (
                    row["id"], row["workspace_id"], row["project_id"], row["approval_id"],
                    row["destination"], row["idempotency_key"], row["state"], row.get("external_id"),
                    row.get("bounded_error"), row.get("attempt", 0), created_at, updated_at,
                ),
            )
        existing = self._connection.execute(
            "SELECT * FROM release_publication_attempts WHERE approval_id=? AND destination=?",
            (row["approval_id"], row["destination"]),
        ).fetchone()
        return self._release_attempt_dict(existing)

    def list_release_attempts(self, project_id: str) -> list[dict[str, Any]]:
        rows = self._connection.execute(
            "SELECT * FROM release_publication_attempts WHERE project_id=? ORDER BY created_at DESC,id",
            (project_id,),
        ).fetchall()
        return [self._release_attempt_dict(row) for row in rows]

    def list_jobs(self, project_id: str, limit: int = 200) -> list[JobRecord]:
        rows = self._connection.execute(
            "SELECT * FROM jobs WHERE project_id=? ORDER BY created_at DESC,id LIMIT ?",
            (project_id, limit),
        ).fetchall()
        return [self._job_record(row) for row in rows]

    def list_artifacts(self, project_id: str, limit: int = 200) -> list[ArtifactRecord]:
        rows = self._connection.execute(
            "SELECT * FROM artifacts WHERE project_id=? ORDER BY created_at DESC,id LIMIT ?",
            (project_id, limit),
        ).fetchall()
        return [self._artifact_record(row) for row in rows]

    @staticmethod
    def arguments_hash(arguments: dict[str, Any]) -> str:
        return hashlib.sha256(json.dumps(arguments, sort_keys=True, separators=(",", ":")).encode()).hexdigest()

    def create_confirmation(
        self, project_id: str, command: str, arguments: dict[str, Any], expected_revision: int, confirmed_by: str,
    ) -> dict[str, str]:
        confirmation_id = f"confirm_{uuid4().hex[:16]}"
        now = datetime.now(timezone.utc)
        expires = now + timedelta(minutes=10)
        with self._write():
            self._connection.execute(
                """INSERT INTO action_confirmations(
                     id,project_id,command,arguments_hash,expected_revision,confirmed_by,expires_at,created_at
                   ) VALUES (?,?,?,?,?,?,?,?)""",
                (confirmation_id, project_id, command, self.arguments_hash(arguments), expected_revision,
                 confirmed_by, expires.isoformat(), now.isoformat()),
            )
        return {"id": confirmation_id, "expires_at": expires.isoformat()}

    def consume_confirmation(
        self, confirmation_id: str | None, project_id: str, command: str,
        arguments: dict[str, Any], expected_revision: int,
    ) -> bool:
        if not confirmation_id:
            return False
        with self.transaction():
            row = self._connection.execute(
                "SELECT * FROM action_confirmations WHERE id=?", (confirmation_id,)
            ).fetchone()
            if row is None or row["consumed_at"]:
                return False
            if datetime.fromisoformat(row["expires_at"]) < datetime.now(timezone.utc):
                return False
            valid = (
                row["project_id"] == project_id and row["command"] == command
                and int(row["expected_revision"]) == expected_revision
                and row["arguments_hash"] == self.arguments_hash(arguments)
            )
            if valid:
                self._connection.execute(
                    "UPDATE action_confirmations SET consumed_at=? WHERE id=?",
                    (utc_now(), confirmation_id),
                )
            return bool(valid)

    @staticmethod
    def _job_record(row: sqlite3.Row) -> JobRecord:
        return JobRecord(
            id=row["id"], project_id=row["project_id"], project_revision=row["project_revision"],
            kind=row["kind"], state=row["state"], progress=float(row["progress"]),
            frozen_spec=json.loads(row["frozen_spec_json"]), worker_id=row["worker_id"],
            result_artifact_id=row["result_artifact_id"], error_code=row["error_code"],
            error_detail=row["error_detail"], cancellation_requested=bool(row["cancellation_requested"]),
            stage=row["stage"] if "stage" in row.keys() else None,
            status_message=row["status_message"] if "status_message" in row.keys() else None,
        )

    def create_job(self, record: JobRecord) -> JobRecord:
        now = utc_now()
        with self._write():
            self._connection.execute(
                """INSERT INTO jobs(
                     id,project_id,project_revision,kind,state,progress,worker_id,
                     frozen_spec_json,result_artifact_id,error_code,error_detail,
                     cancellation_requested,stage,status_message,created_at,updated_at
                   ) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
                (
                    record.id, record.project_id, record.project_revision, record.kind,
                    record.state, record.progress, record.worker_id,
                    json.dumps(record.frozen_spec, sort_keys=True), record.result_artifact_id,
                    record.error_code, record.error_detail, int(record.cancellation_requested),
                    record.stage, record.status_message, now, now,
                ),
            )
        return self.get_job(record.id)

    def get_job(self, job_id: str) -> JobRecord:
        with self._lock:
            row = self._connection.execute("SELECT * FROM jobs WHERE id=?", (job_id,)).fetchone()
            if row is None:
                raise KeyError(job_id)
            return self._job_record(row)

    def claim_next_job(self, worker_id: str, accepted_kinds: list[str]) -> JobRecord | None:
        if not accepted_kinds:
            return None
        placeholders = ",".join("?" for _ in accepted_kinds)
        with self.transaction():
            row = self._connection.execute(
                f"SELECT * FROM jobs WHERE state='queued' AND kind IN ({placeholders}) ORDER BY created_at,id LIMIT 1",
                accepted_kinds,
            ).fetchone()
            if row is None:
                return None
            now = utc_now()
            changed = self._connection.execute(
                "UPDATE jobs SET state='claimed',worker_id=?,updated_at=? WHERE id=? AND state='queued'",
                (worker_id, now, row["id"]),
            ).rowcount
            if changed != 1:
                return None
            attempt = self._connection.execute(
                "SELECT COALESCE(MAX(attempt),0)+1 AS value FROM job_attempts WHERE job_id=?",
                (row["id"],),
            ).fetchone()["value"]
            self._connection.execute(
                "INSERT INTO job_attempts(job_id,attempt,worker_id,state,started_at) VALUES (?,?,?,?,?)",
                (row["id"], attempt, worker_id, "claimed", now),
            )
        return self.get_job(str(row["id"]))

    def update_job(
        self,
        job_id: str,
        *,
        state: str,
        progress: float | None = None,
        result_artifact_id: str | None = None,
        error_code: str | None = None,
        error_detail: str | None = None,
        stage: str | None = None,
        status_message: str | None = None,
    ) -> JobRecord:
        current = self.get_job(job_id)
        next_progress = current.progress if progress is None else max(0.0, min(1.0, progress))
        with self._write():
            self._connection.execute(
                """UPDATE jobs SET state=?,progress=?,result_artifact_id=COALESCE(?,result_artifact_id),
                     error_code=?,error_detail=?,stage=COALESCE(?,stage),
                     status_message=COALESCE(?,status_message),updated_at=? WHERE id=?""",
                (state, next_progress, result_artifact_id, error_code, error_detail,
                 stage, status_message, utc_now(), job_id),
            )
            if current.worker_id:
                self._connection.execute(
                    """UPDATE job_attempts SET state=?,finished_at=CASE WHEN ? IN
                         ('observed_success','observed_failure','execution_failed','cancelled','timeout','interrupted')
                         THEN ? ELSE finished_at END,error_code=?,error_detail=?
                       WHERE job_id=? AND attempt=(SELECT MAX(attempt) FROM job_attempts WHERE job_id=?)""",
                    (state, state, utc_now(), error_code, error_detail, job_id, job_id),
                )
        return self.get_job(job_id)

    def request_job_cancellation(self, job_id: str) -> JobRecord:
        self.get_job(job_id)
        with self._write():
            self._connection.execute(
                "UPDATE jobs SET cancellation_requested=1,updated_at=? WHERE id=?",
                (utc_now(), job_id),
            )
        return self.get_job(job_id)

    def recover_interrupted_jobs(self, worker_id: str | None = None) -> list[JobRecord]:
        parameters: list[Any] = [utc_now(), "worker_restart", "Worker execution ended before a terminal observation."]
        worker_clause = ""
        if worker_id is not None:
            worker_clause = " AND worker_id=?"
            parameters.append(worker_id)
        with self._write():
            rows = self._connection.execute(
                f"SELECT id FROM jobs WHERE state IN ('claimed','running','rendering','awaiting_observation'){worker_clause}",
                parameters[3:],
            ).fetchall()
            if rows:
                ids = [str(row["id"]) for row in rows]
                placeholders = ",".join("?" for _ in ids)
                self._connection.execute(
                    f"UPDATE jobs SET state='interrupted',updated_at=?,error_code=?,error_detail=? WHERE id IN ({placeholders})",
                    [*parameters[:3], *ids],
                )
            else:
                ids = []
        return [self.get_job(job_id) for job_id in ids]

    @staticmethod
    def _artifact_record(row: sqlite3.Row) -> ArtifactRecord:
        return ArtifactRecord(
            id=row["id"], project_id=row["project_id"], job_id=row["job_id"],
            asset_id=row["asset_id"], kind=row["kind"], managed_uri=row["managed_uri"],
            sha256=row["sha256"], byte_size=int(row["byte_size"]), mime_type=row["mime_type"],
            provenance=json.loads(row["provenance_json"]),
            storage_backend=row["storage_backend"], storage_namespace=row["storage_namespace"],
            storage_key=row["storage_key"], storage_version=row["storage_version"],
        )

    def create_artifact(self, record: ArtifactRecord) -> ArtifactRecord:
        with self._write():
            self._connection.execute(
                """INSERT INTO artifacts(
                     id,project_id,job_id,asset_id,kind,managed_uri,sha256,byte_size,
                     mime_type,provenance_json,storage_backend,storage_namespace,
                     storage_key,storage_version,created_at
                   ) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
                (
                    record.id, record.project_id, record.job_id, record.asset_id,
                    record.kind, record.managed_uri, record.sha256, record.byte_size,
                    record.mime_type, json.dumps(record.provenance, sort_keys=True),
                    record.storage_backend, record.storage_namespace, record.storage_key,
                    record.storage_version, utc_now(),
                ),
            )
        return self.get_artifact(record.id)

    def get_artifact(self, artifact_id: str) -> ArtifactRecord:
        with self._lock:
            row = self._connection.execute("SELECT * FROM artifacts WHERE id=?", (artifact_id,)).fetchone()
            if row is None:
                raise KeyError(artifact_id)
            return self._artifact_record(row)

    def register_provider(
        self,
        provider_id: str,
        *,
        provider_kind: str,
        display_name: str,
        adapter_version: str,
        capability_snapshot: dict[str, Any],
        enabled: bool,
    ) -> None:
        now = utc_now()
        with self._write():
            self._connection.execute(
                """INSERT INTO providers(
                     id,provider_kind,display_name,adapter_version,capability_snapshot_json,
                     enabled,created_at,updated_at
                   ) VALUES (?,?,?,?,?,?,?,?)
                   ON CONFLICT(id) DO UPDATE SET provider_kind=excluded.provider_kind,
                     display_name=excluded.display_name,adapter_version=excluded.adapter_version,
                     capability_snapshot_json=excluded.capability_snapshot_json,
                     enabled=excluded.enabled,updated_at=excluded.updated_at""",
                (
                    provider_id, provider_kind, display_name, adapter_version,
                    json.dumps(capability_snapshot, sort_keys=True), int(enabled), now, now,
                ),
            )

    @staticmethod
    def _model_run_record(row: sqlite3.Row) -> ModelRunRecord:
        return ModelRunRecord(
            id=row["id"], project_id=row["project_id"], provider_id=row["provider_id"],
            model_id=row["model_id"], purpose=row["purpose"], state=row["state"],
            external_operation_id=row["external_operation_id"],
            capability_snapshot=json.loads(row["capability_snapshot_json"]),
            request_spec=json.loads(row["request_spec_json"]),
            response_summary=json.loads(row["response_summary_json"]),
            source_hashes=json.loads(row["source_hashes_json"]),
        )

    def create_model_run(self, record: ModelRunRecord) -> ModelRunRecord:
        now = utc_now()
        with self._write():
            self._connection.execute(
                """INSERT INTO model_runs(
                     id,project_id,provider_id,model_id,purpose,state,external_operation_id,
                     capability_snapshot_json,request_spec_json,response_summary_json,
                     source_hashes_json,cost_summary_json,created_at,updated_at
                   ) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
                (
                    record.id, record.project_id, record.provider_id, record.model_id,
                    record.purpose, record.state, record.external_operation_id,
                    json.dumps(record.capability_snapshot, sort_keys=True),
                    json.dumps(record.request_spec, sort_keys=True),
                    json.dumps(record.response_summary, sort_keys=True),
                    json.dumps(record.source_hashes, sort_keys=True), "{}", now, now,
                ),
            )
        return self.get_model_run(record.id)

    def get_model_run(self, run_id: str) -> ModelRunRecord:
        with self._lock:
            row = self._connection.execute("SELECT * FROM model_runs WHERE id=?", (run_id,)).fetchone()
            if row is None:
                raise KeyError(run_id)
            return self._model_run_record(row)

    def update_model_run(
        self,
        run_id: str,
        *,
        state: str,
        external_operation_id: str | None = None,
        response_summary: dict[str, Any] | None = None,
    ) -> ModelRunRecord:
        current = self.get_model_run(run_id)
        with self._write():
            self._connection.execute(
                """UPDATE model_runs SET state=?,external_operation_id=COALESCE(?,external_operation_id),
                     response_summary_json=?,updated_at=? WHERE id=?""",
                (
                    state, external_operation_id,
                    json.dumps(response_summary if response_summary is not None else current.response_summary, sort_keys=True),
                    utc_now(), run_id,
                ),
            )
        return self.get_model_run(run_id)

    @staticmethod
    def _media_blob_record(row: sqlite3.Row) -> MediaBlobRecord:
        return MediaBlobRecord(
            id=row["id"], sha256=row["sha256"], byte_size=int(row["byte_size"]),
            mime_type=row["mime_type"], storage_project_id=row["storage_project_id"],
            storage_asset_id=row["storage_asset_id"], storage_kind=row["storage_kind"],
            storage_backend=row["storage_backend"], storage_namespace=row["storage_namespace"],
            storage_key=row["storage_key"], storage_version=row["storage_version"],
        )

    def register_media_blob(self, record: MediaBlobRecord) -> MediaBlobRecord:
        with self._write():
            self._connection.execute(
                """INSERT INTO media_blobs(
                     id,sha256,byte_size,mime_type,storage_project_id,storage_asset_id,storage_kind,
                     storage_backend,storage_namespace,storage_key,storage_version,created_at
                   ) VALUES (?,?,?,?,?,?,?,?,?,?,?,?) ON CONFLICT(sha256) DO NOTHING""",
                (record.id,record.sha256,record.byte_size,record.mime_type,record.storage_project_id,
                 record.storage_asset_id,record.storage_kind,record.storage_backend,
                 record.storage_namespace,record.storage_key,record.storage_version,utc_now()),
            )
            row = self._connection.execute("SELECT * FROM media_blobs WHERE sha256=?", (record.sha256,)).fetchone()
        assert row is not None
        return self._media_blob_record(row)

    def get_media_blob(self, blob_id: str) -> MediaBlobRecord:
        with self._lock:
            row = self._connection.execute("SELECT * FROM media_blobs WHERE id=?", (blob_id,)).fetchone()
            if row is None:
                raise KeyError(blob_id)
            return self._media_blob_record(row)

    @staticmethod
    def _analysis_artifact_record(row: sqlite3.Row) -> AnalysisArtifactRecord:
        return AnalysisArtifactRecord(
            id=row["id"],project_id=row["project_id"],source_revision=int(row["source_revision"]),
            source_asset_id=row["source_asset_id"],source_sha256=row["source_sha256"],kind=row["kind"],
            schema_version=row["schema_version"],provider_id=row["provider_id"],
            provider_version=row["provider_version"],settings_hash=row["settings_hash"],
            body=json.loads(row["body_json"]),
        )

    def put_analysis_artifact(self, record: AnalysisArtifactRecord) -> AnalysisArtifactRecord:
        with self._write():
            self._connection.execute(
                """INSERT INTO analysis_artifacts(
                     id,project_id,source_revision,source_asset_id,source_sha256,kind,schema_version,
                     provider_id,provider_version,settings_hash,body_json,created_at
                   ) VALUES (?,?,?,?,?,?,?,?,?,?,?,?) ON CONFLICT(
                     source_sha256,kind,schema_version,provider_id,provider_version,settings_hash
                   ) DO NOTHING""",
                (record.id,record.project_id,record.source_revision,record.source_asset_id,
                 record.source_sha256,record.kind,record.schema_version,record.provider_id,
                 record.provider_version,record.settings_hash,json.dumps(record.body,sort_keys=True),utc_now()),
            )
        cached = self.find_analysis_artifact(
            source_sha256=record.source_sha256,kind=record.kind,schema_version=record.schema_version,
            provider_id=record.provider_id,provider_version=record.provider_version,settings_hash=record.settings_hash,
        )
        assert cached is not None
        return cached

    def find_analysis_artifact(
        self, *, source_sha256: str, kind: str, schema_version: str,
        provider_id: str, provider_version: str, settings_hash: str,
    ) -> AnalysisArtifactRecord | None:
        with self._lock:
            row = self._connection.execute(
                """SELECT * FROM analysis_artifacts WHERE source_sha256=? AND kind=? AND schema_version=?
                     AND provider_id=? AND provider_version=? AND settings_hash=?""",
                (source_sha256,kind,schema_version,provider_id,provider_version,settings_hash),
            ).fetchone()
            return self._analysis_artifact_record(row) if row else None

    @staticmethod
    def _suggestion_record(row: sqlite3.Row) -> SuggestionRecord:
        return SuggestionRecord(
            id=row["id"],project_id=row["project_id"],source_revision=int(row["source_revision"]),
            generator_kind=row["generator_kind"],state=row["state"],commands=json.loads(row["commands_json"]),
            reason=row["reason"],evidence=json.loads(row["evidence_json"]),confidence=row["confidence"],
            job_id=row["job_id"] if "job_id" in row.keys() else None,
        )

    def create_suggestion(self, record: SuggestionRecord) -> SuggestionRecord:
        now = utc_now()
        with self._write():
            self._connection.execute(
                """INSERT INTO suggestions(
                     id,project_id,source_revision,generator_kind,state,commands_json,reason,
                     evidence_json,confidence,job_id,created_at,updated_at
                   ) VALUES (?,?,?,?,?,?,?,?,?,?,?,?)""",
                (record.id,record.project_id,record.source_revision,record.generator_kind,record.state,
                 json.dumps(record.commands,sort_keys=True),record.reason,json.dumps(record.evidence,sort_keys=True),
                 record.confidence,record.job_id,now,now),
            )
        return self.get_suggestion(record.id)

    def get_suggestion(self, suggestion_id: str) -> SuggestionRecord:
        with self._lock:
            row = self._connection.execute("SELECT * FROM suggestions WHERE id=?", (suggestion_id,)).fetchone()
            if row is None:
                raise KeyError(suggestion_id)
            return self._suggestion_record(row)

    def list_suggestions(self, project_id: str, *, state: str | None = None) -> list[SuggestionRecord]:
        with self._lock:
            sql = "SELECT * FROM suggestions WHERE project_id=?"
            values: list[Any] = [project_id]
            if state is not None:
                sql += " AND state=?"
                values.append(state)
            sql += " ORDER BY confidence DESC,created_at,id"
            return [self._suggestion_record(row) for row in self._connection.execute(sql,values).fetchall()]

    def update_suggestion_state(self, suggestion_id: str, expected_state: str, state: str) -> SuggestionRecord:
        with self._write():
            changed = self._connection.execute(
                "UPDATE suggestions SET state=?,updated_at=? WHERE id=? AND state=?",
                (state,utc_now(),suggestion_id,expected_state),
            ).rowcount
            if changed != 1:
                current = self.get_suggestion(suggestion_id)
                if current.state != state:
                    raise ValueError(f"suggestion is {current.state}, expected {expected_state}")
        return self.get_suggestion(suggestion_id)
