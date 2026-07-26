from __future__ import annotations

import argparse
import hashlib
import json
import sqlite3
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any

from .blob_storage import GcsBlobStorage, sha256_file
from .models import utc_now
from .postgres_migrations import apply_postgres_migrations


TABLE_ORDER = (
    "metadata", "workspaces", "projects", "project_revisions", "assets", "project_revision_assets",
    "asset_versions", "tracks", "project_revision_tracks", "timeline_items",
    "timeline_item_versions", "timeline_crop_keyframes", "timeline_caption_words",
    "timeline_caption_styles", "events", "receipts", "receipt_transitions",
    "observations", "observation_findings", "selections", "jobs", "job_attempts",
    "artifacts", "capture_sessions", "approvals", "providers", "model_runs",
    "interaction_threads", "generation_candidates", "suggestions", "media_blobs",
    "analysis_artifacts",
)

# Local Codex pairings and bearer tokens are intentionally not portable. Hosted
# access is reprovisioned through hashed, scoped control-plane API keys.


@dataclass
class ImportReport:
    source_fingerprint: str
    mode: str
    rows: dict[str, int]
    files: int
    bytes: int
    missing_files: list[str]
    hash_mismatches: list[str]
    status: str


def database_fingerprint(path: Path) -> str:
    return sha256_file(path)


def load_mapping(path: str | None) -> dict[str, str]:
    if not path:
        return {}
    value = json.loads(Path(path).read_text(encoding="utf-8"))
    if not isinstance(value, dict) or not all(isinstance(key, str) and isinstance(item, str) for key, item in value.items()):
        raise ValueError("workspace mapping must be a JSON object of source and target IDs")
    return value


class MaintenanceImporter:
    def __init__(self, args: argparse.Namespace):
        self.args = args
        self.sqlite_path = Path(args.sqlite).resolve()
        self.media_root = Path(args.media_root).resolve()
        self.proxy_root = Path(args.proxy_root).resolve()
        self.artifact_root = Path(args.artifact_root).resolve()
        self.workspace_map = load_mapping(args.workspace_map)
        self.fingerprint = database_fingerprint(self.sqlite_path)

    def _source(self) -> sqlite3.Connection:
        wal = Path(f"{self.sqlite_path}-wal")
        if wal.exists() and wal.stat().st_size > 0:
            raise RuntimeError("refusing an active WAL database; create a consistent SQLite backup first")
        # SQLite backups retain their source journal-mode header. immutable=1
        # prevents a read-only verification pass from creating empty -wal/-shm
        # companions and then falsely rejecting its own next resumable run.
        connection = sqlite3.connect(f"file:{self.sqlite_path}?mode=ro&immutable=1", uri=True)
        connection.row_factory = sqlite3.Row
        result = connection.execute("PRAGMA quick_check").fetchone()
        if not result or result[0] != "ok":
            raise RuntimeError("SQLite backup failed quick_check")
        return connection

    @staticmethod
    def _managed_file(root: Path, project_id: str, asset_id: str) -> Path | None:
        directory = (root / project_id / asset_id).resolve()
        if not directory.is_relative_to(root) or not directory.is_dir():
            return None
        files = [path for path in directory.iterdir() if path.is_file()]
        return files[0] if len(files) == 1 else None

    def plan(self) -> ImportReport:
        source = self._source()
        try:
            rows = {
                table: int(source.execute(f'SELECT COUNT(*) FROM "{table}"').fetchone()[0])
                for table in TABLE_ORDER
                if source.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name=?", (table,)).fetchone()
            }
            missing: list[str] = []
            mismatches: list[str] = []
            count = 0
            byte_size = 0
            for row in source.execute("SELECT * FROM media_blobs ORDER BY id"):
                root = self.proxy_root if row["storage_kind"] == "derived" else self.media_root
                path = self._managed_file(root, str(row["storage_project_id"]), str(row["storage_asset_id"]))
                if path is None:
                    missing.append(str(row["id"]))
                    continue
                count += 1
                byte_size += path.stat().st_size
                if sha256_file(path) != row["sha256"]:
                    mismatches.append(str(row["id"]))
            for row in source.execute("SELECT * FROM artifacts ORDER BY id"):
                path = (self.artifact_root / f"{row['id']}.mp4").resolve()
                if not path.is_relative_to(self.artifact_root) or not path.is_file():
                    missing.append(str(row["id"]))
                    continue
                count += 1
                byte_size += path.stat().st_size
                if sha256_file(path) != row["sha256"]:
                    mismatches.append(str(row["id"]))
            status = "ready" if not missing and not mismatches else "blocked"
            return ImportReport(self.fingerprint, "plan", rows, count, byte_size, missing, mismatches, status)
        finally:
            source.close()

    def _target(self):
        import psycopg
        from psycopg.rows import dict_row

        connection = psycopg.connect(self.args.database_url, row_factory=dict_row)
        apply_postgres_migrations(connection)
        connection.execute("SET search_path TO sag, public")
        connection.commit()
        return connection

    def run(self) -> ImportReport:
        report = self.plan()
        if report.status != "ready":
            raise RuntimeError("import plan is blocked by missing or changed files")
        from psycopg import sql

        source = self._source()
        target = self._target()
        run_id = f"import-{self.fingerprint[:24]}"
        storage = GcsBlobStorage(self.args.bucket, Path(self.args.cache_dir))
        try:
            target.execute("SELECT pg_advisory_lock(hashtext('sag-video-maintenance-import'))")
            with target.transaction():
                target.execute(
                    """INSERT INTO import_runs(id,source_fingerprint,state,report_json,created_at,updated_at)
                       VALUES (%s,%s,'running','{}',%s,%s)
                       ON CONFLICT(id) DO UPDATE SET state='running',updated_at=excluded.updated_at""",
                    (run_id, self.fingerprint, utc_now(), utc_now()),
                )
            for table in TABLE_ORDER:
                exists = source.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name=?", (table,)).fetchone()
                if not exists:
                    continue
                target_columns = {
                    row["column_name"] for row in target.execute(
                        "SELECT column_name FROM information_schema.columns WHERE table_schema='sag' AND table_name=%s",
                        (table,),
                    ).fetchall()
                }
                for row in source.execute(f'SELECT * FROM "{table}"'):
                    values = dict(row)
                    if table == "workspaces" and "id" in values:
                        values["id"] = self.workspace_map.get(str(values["id"]), values["id"])
                    if "workspace_id" in values:
                        values["workspace_id"] = self.workspace_map.get(str(values["workspace_id"]), values["workspace_id"])
                    columns = [column for column in values if column in target_columns]
                    query = sql.SQL("INSERT INTO sag.{} ({}) VALUES ({}) ON CONFLICT DO NOTHING").format(
                        sql.Identifier(table), sql.SQL(",").join(map(sql.Identifier, columns)),
                        sql.SQL(",").join(sql.Placeholder() for _ in columns),
                    )
                    target.execute(query, [values[column] for column in columns])
                target.commit()
            self._upload_media(source, target, storage, run_id)
            verified = self.verify(target=target)
            with target.transaction():
                target.execute(
                    "UPDATE import_runs SET state=%s,report_json=%s,updated_at=%s WHERE id=%s",
                    ("verified" if verified.status == "verified" else "failed", json.dumps(asdict(verified), sort_keys=True), utc_now(), run_id),
                )
            return verified
        finally:
            try:
                target.execute("SELECT pg_advisory_unlock(hashtext('sag-video-maintenance-import'))")
                target.commit()
            finally:
                source.close()
                target.close()

    def _upload_media(self, source: sqlite3.Connection, target: Any, storage: GcsBlobStorage, run_id: str) -> None:
        for kind, rows in (
            ("blob", source.execute("SELECT * FROM media_blobs ORDER BY id").fetchall()),
            ("artifact", source.execute("SELECT * FROM artifacts ORDER BY id").fetchall()),
        ):
            for row in rows:
                identity = str(row["id"])
                checkpoint = target.execute(
                    "SELECT state FROM import_items WHERE run_id=%s AND item_kind=%s AND source_identity=%s",
                    (run_id, kind, identity),
                ).fetchone()
                if checkpoint and checkpoint["state"] == "verified":
                    continue
                if kind == "blob":
                    root = self.proxy_root if row["storage_kind"] == "derived" else self.media_root
                    path = self._managed_file(root, str(row["storage_project_id"]), str(row["storage_asset_id"]))
                    project_id, category = str(row["storage_project_id"]), "media"
                    workspace_row = source.execute("SELECT workspace_id FROM projects WHERE id=?", (project_id,)).fetchone()
                    workspace_id = str(workspace_row[0] if workspace_row else project_id)
                else:
                    path = (self.artifact_root / f"{identity}.mp4").resolve()
                    project_id, category = str(row["project_id"]), "artifacts"
                    workspace_row = source.execute("SELECT workspace_id FROM projects WHERE id=?", (project_id,)).fetchone()
                    workspace_id = str(workspace_row[0] if workspace_row else project_id)
                workspace_id = self.workspace_map.get(workspace_id, workspace_id)
                assert path is not None
                stored = storage.put_immutable(
                    path, workspace_id=workspace_id, project_id=project_id, identity=identity,
                    category=category, content_type=row["mime_type"], expected_sha256=str(row["sha256"]),
                )
                table = "media_blobs" if kind == "blob" else "artifacts"
                target.execute(
                    f"""UPDATE sag.{table} SET storage_backend=%s,storage_namespace=%s,
                         storage_key=%s,storage_version=%s WHERE id=%s""",
                    (stored.locator.backend, stored.locator.namespace, stored.locator.key, stored.locator.version, identity),
                )
                target.execute(
                    """INSERT INTO import_items(run_id,item_kind,source_identity,sha256,state,updated_at)
                       VALUES (%s,%s,%s,%s,'verified',%s)
                       ON CONFLICT(run_id,item_kind,source_identity) DO UPDATE SET state='verified',sha256=excluded.sha256,updated_at=excluded.updated_at""",
                    (run_id, kind, identity, stored.sha256, utc_now()),
                )
                target.commit()

    def verify(self, target: Any | None = None) -> ImportReport:
        own_target = target is None
        source = self._source()
        target = target or self._target()
        try:
            rows: dict[str, int] = {}
            mismatches: list[str] = []
            for table in TABLE_ORDER:
                exists = source.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name=?", (table,)).fetchone()
                if not exists:
                    continue
                source_count = int(source.execute(f'SELECT COUNT(*) FROM "{table}"').fetchone()[0])
                target_count = int(target.execute(f'SELECT COUNT(*) AS value FROM sag."{table}"').fetchone()["value"])
                rows[table] = target_count
                if target_count < source_count:
                    mismatches.append(f"{table}: expected at least {source_count}, found {target_count}")
            pending = int(target.execute(
                "SELECT COUNT(*) AS value FROM sag.import_items WHERE run_id=%s AND state<>'verified'",
                (f"import-{self.fingerprint[:24]}",),
            ).fetchone()["value"])
            if pending:
                mismatches.append(f"{pending} import checkpoints are not verified")
            return ImportReport(
                self.fingerprint, "verify", rows, 0, 0, [], mismatches,
                "verified" if not mismatches else "failed",
            )
        finally:
            source.close()
            if own_target:
                target.close()


def parser() -> argparse.ArgumentParser:
    result = argparse.ArgumentParser(description="Import SAG SQLite/filesystem state into PostgreSQL and GCS")
    result.add_argument("command", choices=("plan", "run", "verify", "report"))
    result.add_argument("--sqlite", required=True)
    result.add_argument("--media-root", required=True)
    result.add_argument("--proxy-root", required=True)
    result.add_argument("--artifact-root", required=True)
    result.add_argument("--database-url", default="")
    result.add_argument("--bucket", default="")
    result.add_argument("--workspace-map")
    result.add_argument("--cache-dir", default="/tmp/sag-import-cache")
    result.add_argument("--report-file")
    return result


def main() -> None:
    args = parser().parse_args()
    importer = MaintenanceImporter(args)
    if args.command == "plan":
        report = importer.plan()
    elif args.command == "run":
        if not args.database_url or not args.bucket:
            raise SystemExit("run requires --database-url and --bucket")
        report = importer.run()
    elif args.command == "verify":
        if not args.database_url:
            raise SystemExit("verify requires --database-url")
        report = importer.verify()
    else:
        if not args.database_url:
            raise SystemExit("report requires --database-url")
        target = importer._target()
        try:
            row = target.execute(
                "SELECT report_json FROM import_runs WHERE source_fingerprint=%s", (importer.fingerprint,)
            ).fetchone()
            if not row:
                raise SystemExit("no import report exists for this source")
            report = ImportReport(**json.loads(row["report_json"]))
        finally:
            target.close()
    body = json.dumps(asdict(report), indent=2, sort_keys=True)
    if args.report_file:
        Path(args.report_file).write_text(f"{body}\n", encoding="utf-8")
    print(body)


if __name__ == "__main__":
    main()
