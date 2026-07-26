from __future__ import annotations

import re
import threading
from contextlib import contextmanager
from typing import Any

from .postgres_migrations import apply_postgres_migrations
from .store import Store


class _PostgresConnection:
    """Small DB-API compatibility layer used by the normalized repositories."""

    def __init__(self, connection: Any):
        self.raw = connection

    @staticmethod
    def _sql(statement: str) -> str:
        sql = statement
        ignored = bool(re.search(r"\bINSERT\s+OR\s+IGNORE\s+INTO\b", sql, re.IGNORECASE))
        sql = re.sub(r"\bINSERT\s+OR\s+IGNORE\s+INTO\b", "INSERT INTO", sql, flags=re.IGNORECASE)
        if ignored and "ON CONFLICT" not in sql.upper():
            sql = f"{sql.rstrip()} ON CONFLICT DO NOTHING"
        if re.search(r"INSERT\s+OR\s+REPLACE\s+INTO\s+metadata", sql, re.IGNORECASE):
            sql = re.sub(
                r"INSERT\s+OR\s+REPLACE\s+INTO\s+metadata",
                "INSERT INTO metadata",
                sql,
                flags=re.IGNORECASE,
            ).rstrip()
            sql += " ON CONFLICT(key) DO UPDATE SET value=excluded.value"
        sql = sql.replace(
            "MAX(projects.current_revision, excluded.current_revision)",
            "GREATEST(projects.current_revision, excluded.current_revision)",
        )
        sql = re.sub(
            r"ORDER BY rowid DESC LIMIT 1", "ORDER BY observed_at DESC NULLS LAST LIMIT 1", sql,
            flags=re.IGNORECASE,
        )
        if "FROM tokens" in sql:
            sql = re.sub(r"ORDER BY rowid DESC", "ORDER BY expires_at DESC", sql, flags=re.IGNORECASE)
        return sql.replace("?", "%s")

    def execute(self, statement: str, parameters: Any = None):
        return self.raw.execute(self._sql(statement), parameters or ())

    def executemany(self, statement: str, parameters: Any):
        return self.raw.cursor().executemany(self._sql(statement), parameters)

    def commit(self) -> None:
        self.raw.commit()

    def rollback(self) -> None:
        self.raw.rollback()

    def close(self) -> None:
        self.raw.close()


class PostgreSQLStore(Store):
    """PostgreSQL implementation of the SAG repository unit of work."""

    def __init__(self, database_url: str, *, seed: bool = False):
        try:
            import psycopg
            from psycopg.rows import dict_row
        except ImportError as error:  # pragma: no cover - deployment dependency guard
            raise RuntimeError("PostgreSQL backend requires the 'psycopg' package") from error
        self.database_path = database_url
        self._lock = threading.RLock()
        raw = psycopg.connect(database_url, row_factory=dict_row)
        self._connection = _PostgresConnection(raw)
        self._transaction_depth = 0
        apply_postgres_migrations(raw)
        raw.execute("SET search_path TO sag, public")
        raw.commit()
        if seed:
            self.seed()

    @contextmanager
    def transaction(self):
        with self._lock:
            outermost = self._transaction_depth == 0
            self._transaction_depth += 1
            context = self._connection.raw.transaction() if outermost else self._connection.raw.transaction()
            try:
                with context:
                    yield self
            finally:
                self._transaction_depth -= 1

    def get_project_for_update(self, project_id: str):
        self._connection.execute("SELECT id FROM projects WHERE id=? FOR UPDATE", (project_id,)).fetchone()
        return self.get_project(project_id)

    def get_journal_head_for_update(self, namespace: str, hash_alg: str) -> tuple[int, str | None, str]:
        self._connection.execute(
            """INSERT INTO sag_journal_streams(namespace,head_seq,head_hash,hash_alg,updated_at)
               VALUES (?,0,NULL,?,?) ON CONFLICT(namespace) DO NOTHING""",
            (namespace, hash_alg, __import__("sag_video.models", fromlist=["utc_now"]).utc_now()),
        )
        row = self._connection.execute(
            "SELECT head_seq,head_hash,hash_alg FROM sag_journal_streams WHERE namespace=? FOR UPDATE",
            (namespace,),
        ).fetchone()
        return int(row["head_seq"]), row["head_hash"], str(row["hash_alg"])

    def claim_next_job(self, worker_id: str, accepted_kinds: list[str]):
        if not accepted_kinds:
            return None
        placeholders = ",".join("?" for _ in accepted_kinds)
        with self.transaction():
            row = self._connection.execute(
                f"""SELECT * FROM jobs
                    WHERE state='queued' AND kind IN ({placeholders})
                    ORDER BY created_at,id FOR UPDATE SKIP LOCKED LIMIT 1""",
                accepted_kinds,
            ).fetchone()
            if row is None:
                return None
            now = __import__("sag_video.models", fromlist=["utc_now"]).utc_now()
            self._connection.execute(
                "UPDATE jobs SET state='claimed',worker_id=?,updated_at=? WHERE id=? AND state='queued'",
                (worker_id, now, row["id"]),
            )
            attempt = self._connection.execute(
                "SELECT COALESCE(MAX(attempt),0)+1 AS value FROM job_attempts WHERE job_id=?",
                (row["id"],),
            ).fetchone()["value"]
            self._connection.execute(
                "INSERT INTO job_attempts(job_id,attempt,worker_id,state,started_at) VALUES (?,?,?,?,?)",
                (row["id"], attempt, worker_id, "claimed", now),
            )
        return self.get_job(str(row["id"]))
