from __future__ import annotations

import json
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

    def start_pairing(self, workspace_id: str) -> tuple[str, str]:
        code = f"{secrets.randbelow(1_000_000):06d}"
        expires = datetime.now(timezone.utc) + timedelta(minutes=10)
        with self._write():
            self._connection.execute(
                "INSERT INTO pairings(code,workspace_id,expires_at,consumed) VALUES (?,?,?,0)",
                (code, workspace_id, expires.isoformat()),
            )
        return code, expires.isoformat()

    def attach_pairing(self, code: str, actor_name: str) -> tuple[str, str, str]:
        with self.transaction():
            row = self._connection.execute("SELECT * FROM pairings WHERE code=?", (code,)).fetchone()
            if row is None or row["consumed"]:
                raise ValueError("invalid or consumed pairing code")
            if datetime.fromisoformat(row["expires_at"]) < datetime.now(timezone.utc):
                raise ValueError("expired pairing code")
            self._connection.execute("UPDATE pairings SET consumed=1 WHERE code=?", (code,))
            token, expires_at = self.issue_token(str(row["workspace_id"]), actor_name)
        return token, expires_at, str(row["workspace_id"])

    def principal_for_token(self, token: str) -> dict[str, str] | None:
        row = self._connection.execute("SELECT * FROM tokens WHERE token=?", (token,)).fetchone()
        if row is None or row["revoked"]:
            return None
        if datetime.fromisoformat(row["expires_at"]) < datetime.now(timezone.utc):
            return None
        return {
            "actor_name": str(row["actor_name"]),
            "workspace_id": str(row["workspace_id"]),
            "expires_at": str(row["expires_at"]),
        }

    def actor_for_token(self, token: str) -> str | None:
        principal = self.principal_for_token(token)
        return principal["actor_name"] if principal else None

    def issue_token(self, workspace_id: str, actor_name: str, *, hours: int = 8) -> tuple[str, str]:
        token = secrets.token_urlsafe(32)
        expires = datetime.now(timezone.utc) + timedelta(hours=hours)
        with self._write():
            self._connection.execute(
                "INSERT INTO tokens(token,workspace_id,actor_name,expires_at,revoked) VALUES (?,?,?,?,0)",
                (token, workspace_id, actor_name, expires.isoformat()),
            )
        return token, expires.isoformat()

    def active_actors(self, workspace_id: str) -> list[dict[str, str]]:
        now = datetime.now(timezone.utc)
        rows = self._connection.execute(
            "SELECT actor_name,expires_at FROM tokens WHERE workspace_id=? AND revoked=0 ORDER BY rowid DESC",
            (workspace_id,),
        ).fetchall()
        return [
            {"actor_name": str(row["actor_name"]), "expires_at": str(row["expires_at"])}
            for row in rows
            if datetime.fromisoformat(row["expires_at"]) >= now
        ]

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
        )

    def create_artifact(self, record: ArtifactRecord) -> ArtifactRecord:
        with self._write():
            self._connection.execute(
                """INSERT INTO artifacts(
                     id,project_id,job_id,asset_id,kind,managed_uri,sha256,byte_size,
                     mime_type,provenance_json,created_at
                   ) VALUES (?,?,?,?,?,?,?,?,?,?,?)""",
                (
                    record.id, record.project_id, record.job_id, record.asset_id,
                    record.kind, record.managed_uri, record.sha256, record.byte_size,
                    record.mime_type, json.dumps(record.provenance, sort_keys=True), utc_now(),
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
        )

    def register_media_blob(self, record: MediaBlobRecord) -> MediaBlobRecord:
        with self._write():
            self._connection.execute(
                """INSERT INTO media_blobs(
                     id,sha256,byte_size,mime_type,storage_project_id,storage_asset_id,storage_kind,created_at
                   ) VALUES (?,?,?,?,?,?,?,?) ON CONFLICT(sha256) DO NOTHING""",
                (record.id,record.sha256,record.byte_size,record.mime_type,record.storage_project_id,
                 record.storage_asset_id,record.storage_kind,utc_now()),
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
