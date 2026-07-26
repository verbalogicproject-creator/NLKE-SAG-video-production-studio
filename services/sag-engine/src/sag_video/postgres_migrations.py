from __future__ import annotations

import hashlib
from collections.abc import Iterator

from .migrations import NORMALIZED_SCHEMA
from .models import utc_now


POSTGRES_SCHEMA_VERSION = 8


def _postgres_schema() -> str:
    """Translate the frozen normalized v6 schema to PostgreSQL DDL.

    SQLite upgrades remain in migrations.py. PostgreSQL starts from the current
    normalized contract and receives append-only migrations from this module.
    """
    # Migration 1 is immutable. Strip later authority additions before hashing
    # so already-deployed databases continue to validate its original checksum.
    schema = NORMALIZED_SCHEMA.replace(
        "    project_id TEXT,\n    sequence_id TEXT,\n    scopes_json TEXT NOT NULL DEFAULT '[]',\n",
        "",
    )
    start = schema.index("CREATE TABLE IF NOT EXISTS actor_focus (")
    end = schema.index("CREATE TABLE IF NOT EXISTS workspaces (", start)
    schema = schema[:start] + schema[end:]
    return schema.replace(
        "id INTEGER PRIMARY KEY AUTOINCREMENT,", "id BIGSERIAL PRIMARY KEY,"
    )


MIGRATIONS: tuple[tuple[int, str, str], ...] = (
    (1, "normalized_provider_neutral_core_v6", _postgres_schema()),
    (
        2,
        "durable_storage_locators",
        """ALTER TABLE media_blobs ADD COLUMN IF NOT EXISTS storage_backend TEXT;
           ALTER TABLE media_blobs ADD COLUMN IF NOT EXISTS storage_namespace TEXT;
           ALTER TABLE media_blobs ADD COLUMN IF NOT EXISTS storage_key TEXT;
           ALTER TABLE media_blobs ADD COLUMN IF NOT EXISTS storage_version TEXT;
           ALTER TABLE artifacts ADD COLUMN IF NOT EXISTS storage_backend TEXT;
           ALTER TABLE artifacts ADD COLUMN IF NOT EXISTS storage_namespace TEXT;
           ALTER TABLE artifacts ADD COLUMN IF NOT EXISTS storage_key TEXT;
           ALTER TABLE artifacts ADD COLUMN IF NOT EXISTS storage_version TEXT;""",
    ),
    (
        3,
        "resumable_import_checkpoints",
        """CREATE TABLE IF NOT EXISTS import_runs(
             id TEXT PRIMARY KEY, source_fingerprint TEXT NOT NULL UNIQUE,
             state TEXT NOT NULL, report_json TEXT NOT NULL DEFAULT '{}',
             created_at TEXT NOT NULL, updated_at TEXT NOT NULL
           );
           CREATE TABLE IF NOT EXISTS import_items(
             run_id TEXT NOT NULL REFERENCES import_runs(id) ON DELETE CASCADE,
             item_kind TEXT NOT NULL, source_identity TEXT NOT NULL,
             sha256 TEXT, state TEXT NOT NULL, detail TEXT,
             updated_at TEXT NOT NULL,
             PRIMARY KEY(run_id,item_kind,source_identity)
           );""",
    ),
    (
        4,
        "scoped_actor_authority_and_confirmations",
        """ALTER TABLE pairings ADD COLUMN IF NOT EXISTS project_id TEXT;
           ALTER TABLE pairings ADD COLUMN IF NOT EXISTS sequence_id TEXT;
           ALTER TABLE pairings ADD COLUMN IF NOT EXISTS scopes_json TEXT NOT NULL DEFAULT '[]';
           ALTER TABLE tokens ADD COLUMN IF NOT EXISTS project_id TEXT;
           ALTER TABLE tokens ADD COLUMN IF NOT EXISTS sequence_id TEXT;
           ALTER TABLE tokens ADD COLUMN IF NOT EXISTS scopes_json TEXT NOT NULL DEFAULT '[]';
           CREATE TABLE IF NOT EXISTS actor_focus(
             token TEXT NOT NULL REFERENCES tokens(token) ON DELETE CASCADE,
             project_id TEXT NOT NULL REFERENCES projects(id) ON DELETE CASCADE,
             item_ids_json TEXT NOT NULL DEFAULT '[]', visible_surface TEXT NOT NULL DEFAULT 'studio',
             active_workflow TEXT, updated_at TEXT NOT NULL, PRIMARY KEY(token,project_id)
           );
           CREATE TABLE IF NOT EXISTS action_confirmations(
             id TEXT PRIMARY KEY, project_id TEXT NOT NULL REFERENCES projects(id) ON DELETE CASCADE,
             command TEXT NOT NULL, arguments_hash TEXT NOT NULL, expected_revision INTEGER NOT NULL,
             confirmed_by TEXT NOT NULL, expires_at TEXT NOT NULL, consumed_at TEXT, created_at TEXT NOT NULL
           );""",
    ),
    (
        5,
        "semantic_runtime_events_and_spatial_focus",
        """ALTER TABLE actor_focus ADD COLUMN IF NOT EXISTS active_depth TEXT NOT NULL DEFAULT 'edit';
           CREATE TABLE IF NOT EXISTS sag_event_definitions(
             kind TEXT PRIMARY KEY, version INTEGER NOT NULL CHECK(version >= 1),
             json_schema TEXT NOT NULL, source_hash TEXT NOT NULL,
             release_status TEXT NOT NULL, retention_class TEXT NOT NULL,
             reconciled_at TEXT NOT NULL
           );
           CREATE TABLE IF NOT EXISTS sag_runtime_events(
             cursor BIGSERIAL PRIMARY KEY, event_id TEXT NOT NULL UNIQUE,
             workspace_id TEXT NOT NULL, project_id TEXT NOT NULL REFERENCES projects(id) ON DELETE CASCADE,
             sequence_id TEXT NOT NULL, revision INTEGER NOT NULL,
             actor TEXT NOT NULL, session_id TEXT, kind TEXT NOT NULL REFERENCES sag_event_definitions(kind),
             trace_id TEXT, payload_json TEXT NOT NULL, created_at TEXT NOT NULL, expires_at TEXT NOT NULL
           );
           CREATE INDEX IF NOT EXISTS idx_sag_runtime_scope_cursor
             ON sag_runtime_events(workspace_id,project_id,sequence_id,cursor);
           CREATE INDEX IF NOT EXISTS idx_sag_runtime_expiry ON sag_runtime_events(expires_at);""",
    ),
    (
        6,
        "provider_neutral_protected_connections",
        """CREATE TABLE IF NOT EXISTS provider_connections(
             id TEXT PRIMARY KEY, workspace_id TEXT NOT NULL,
             provider TEXT NOT NULL, purpose TEXT NOT NULL, display_name TEXT NOT NULL,
             state TEXT NOT NULL, scopes_json TEXT NOT NULL DEFAULT '[]',
             encrypted_secret TEXT NOT NULL, kms_key_version TEXT NOT NULL,
             secret_fingerprint TEXT NOT NULL, metadata_json TEXT NOT NULL DEFAULT '{}',
             created_at TEXT NOT NULL, updated_at TEXT NOT NULL,
             UNIQUE(workspace_id,provider,purpose,display_name)
           );
           CREATE INDEX IF NOT EXISTS idx_provider_connections_workspace
             ON provider_connections(workspace_id,state,updated_at DESC);""",
    ),
    (
        7,
        "engine_owned_delivery_governance",
        """CREATE TABLE IF NOT EXISTS delivery_profiles(
             id TEXT PRIMARY KEY, project_id TEXT NOT NULL REFERENCES projects(id) ON DELETE CASCADE,
             destination TEXT NOT NULL, aspect_ratio TEXT NOT NULL, width INTEGER NOT NULL, height INTEGER NOT NULL,
             caption_placement TEXT NOT NULL, safe_zone_x INTEGER NOT NULL, safe_zone_y INTEGER NOT NULL,
             metadata_json TEXT NOT NULL DEFAULT '{}', created_at TEXT NOT NULL, updated_at TEXT NOT NULL,
             UNIQUE(project_id,destination)
           );
           CREATE TABLE IF NOT EXISTS release_approvals(
             id TEXT PRIMARY KEY, workspace_id TEXT NOT NULL,
             project_id TEXT NOT NULL REFERENCES projects(id) ON DELETE RESTRICT,
             project_revision INTEGER NOT NULL, bundle_hash TEXT NOT NULL,
             artifact_hashes_json TEXT NOT NULL, destinations_json TEXT NOT NULL,
             state TEXT NOT NULL, approved_by TEXT NOT NULL, expires_at TEXT NOT NULL,
             consumed_at TEXT, created_at TEXT NOT NULL, UNIQUE(workspace_id,bundle_hash)
           );
           CREATE TABLE IF NOT EXISTS release_publication_attempts(
             id TEXT PRIMARY KEY, workspace_id TEXT NOT NULL,
             project_id TEXT NOT NULL REFERENCES projects(id) ON DELETE RESTRICT,
             approval_id TEXT NOT NULL REFERENCES release_approvals(id) ON DELETE RESTRICT,
             destination TEXT NOT NULL, idempotency_key TEXT NOT NULL UNIQUE,
             state TEXT NOT NULL, external_id TEXT, bounded_error TEXT, attempt INTEGER NOT NULL DEFAULT 0,
             created_at TEXT NOT NULL, updated_at TEXT NOT NULL, UNIQUE(approval_id,destination)
           );
           CREATE INDEX IF NOT EXISTS idx_release_approvals_project
             ON release_approvals(project_id,state,created_at DESC);
           CREATE INDEX IF NOT EXISTS idx_release_attempts_project
             ON release_publication_attempts(project_id,state,updated_at DESC);""",
    ),
    (
        8,
        "provider_neutral_tamper_evident_journal",
        """CREATE TABLE IF NOT EXISTS sag_journal_kind_definitions(
             kind TEXT PRIMARY KEY, version INTEGER NOT NULL CHECK(version >= 1),
             protocol TEXT NOT NULL, release_status TEXT NOT NULL,
             source_hash TEXT NOT NULL, reconciled_at TEXT NOT NULL
           );
           CREATE TABLE IF NOT EXISTS sag_journal_streams(
             namespace TEXT PRIMARY KEY, head_seq BIGINT NOT NULL DEFAULT 0,
             head_hash TEXT, hash_alg TEXT NOT NULL, updated_at TEXT NOT NULL
           );
           CREATE TABLE IF NOT EXISTS sag_journal_entries(
             namespace TEXT NOT NULL, seq BIGINT, id TEXT NOT NULL,
             prev_hash TEXT, row_hash TEXT, hash_alg TEXT,
             kind TEXT NOT NULL REFERENCES sag_journal_kind_definitions(kind),
             content TEXT NOT NULL, session_id TEXT, batch TEXT,
             tags_json TEXT NOT NULL DEFAULT '[]', metadata_json TEXT NOT NULL DEFAULT '{}',
             method TEXT NOT NULL, schema_version INTEGER NOT NULL, created_at TEXT NOT NULL,
             PRIMARY KEY(namespace,id), UNIQUE(namespace,seq)
           );
           CREATE INDEX IF NOT EXISTS idx_sag_journal_namespace_seq
             ON sag_journal_entries(namespace,seq);
           CREATE INDEX IF NOT EXISTS idx_sag_journal_kind_created
             ON sag_journal_entries(kind,created_at);""",
    ),
)


def migration_checksum(name: str, sql: str) -> str:
    return hashlib.sha256(f"{name}\0{sql}".encode()).hexdigest()


def apply_postgres_migrations(connection: object) -> None:
    connection.execute("CREATE SCHEMA IF NOT EXISTS sag")
    connection.execute("SET search_path TO sag, public")
    connection.execute("SELECT pg_advisory_lock(hashtext('sag-video-python-migrations'))")
    try:
        connection.execute(
            """CREATE TABLE IF NOT EXISTS schema_migrations(
                 version INTEGER PRIMARY KEY,
                 name TEXT NOT NULL,
                 checksum TEXT NOT NULL,
                 applied_at TEXT NOT NULL
               )"""
        )
        applied = {
            int(row["version"]): (str(row["name"]), str(row["checksum"]))
            for row in connection.execute(
                "SELECT version,name,checksum FROM schema_migrations ORDER BY version"
            ).fetchall()
        }
        for version, name, sql in MIGRATIONS:
            checksum = migration_checksum(name, sql)
            if version in applied:
                if applied[version] != (name, checksum):
                    raise RuntimeError(f"PostgreSQL migration {version} checksum mismatch")
                continue
            connection.execute(sql)
            connection.execute(
                "INSERT INTO schema_migrations(version,name,checksum,applied_at) VALUES (%s,%s,%s,%s)",
                (version, name, checksum, utc_now()),
            )
        connection.commit()
    except Exception:
        connection.rollback()
        raise
    finally:
        connection.execute("SELECT pg_advisory_unlock(hashtext('sag-video-python-migrations'))")
        connection.commit()


def expected_migrations() -> Iterator[tuple[int, str, str]]:
    yield from MIGRATIONS
