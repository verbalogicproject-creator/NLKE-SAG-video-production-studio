from __future__ import annotations

import json
import sqlite3
from collections.abc import Iterable
from typing import Any
from uuid import uuid4

from .models import Asset, Canvas, Project, Receipt, ReceiptStatus, TimelineItem, Track, utc_now


SCHEMA_VERSION = 5


NORMALIZED_SCHEMA = """
CREATE TABLE IF NOT EXISTS projects (
    id TEXT PRIMARY KEY,
    name TEXT NOT NULL,
    workspace_id TEXT,
    parent_project_id TEXT,
    source_project_revision INTEGER,
    source_suggestion_id TEXT,
    variant_kind TEXT,
    target_aspect_ratio TEXT,
    current_revision INTEGER NOT NULL CHECK(current_revision >= 1),
    schema_version INTEGER NOT NULL CHECK(schema_version >= 1),
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS metadata (
    key TEXT PRIMARY KEY,
    value TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS project_revisions (
    project_id TEXT NOT NULL,
    revision INTEGER NOT NULL CHECK(revision >= 1),
    parent_revision INTEGER,
    request_id TEXT,
    actor TEXT,
    command TEXT,
    name TEXT NOT NULL,
    canvas_width INTEGER NOT NULL CHECK(canvas_width > 0),
    canvas_height INTEGER NOT NULL CHECK(canvas_height > 0),
    fps_numerator INTEGER NOT NULL CHECK(fps_numerator > 0),
    fps_denominator INTEGER NOT NULL CHECK(fps_denominator > 0),
    duration_ticks INTEGER NOT NULL CHECK(duration_ticks > 0),
    created_at TEXT NOT NULL,
    PRIMARY KEY(project_id, revision),
    FOREIGN KEY(project_id) REFERENCES projects(id) ON DELETE CASCADE
);

CREATE TABLE IF NOT EXISTS assets (
    project_id TEXT NOT NULL,
    id TEXT NOT NULL,
    kind TEXT NOT NULL,
    name TEXT NOT NULL,
    uri TEXT,
    source_kind TEXT NOT NULL,
    managed_uri TEXT,
    original_filename TEXT,
    sha256 TEXT,
    blob_id TEXT,
    byte_size INTEGER,
    mime_type TEXT,
    duration_ticks INTEGER,
    width INTEGER,
    height INTEGER,
    frame_rate TEXT,
    video_codec TEXT,
    rotation INTEGER,
    audio_codec TEXT,
    audio_channels INTEGER,
    audio_sample_rate INTEGER,
    proxy_asset_id TEXT,
    thumbnail_asset_id TEXT,
    parent_asset_id TEXT,
    intake_status TEXT NOT NULL,
    observation_summary_json TEXT NOT NULL DEFAULT '{}',
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL,
    PRIMARY KEY(project_id, id),
    FOREIGN KEY(project_id) REFERENCES projects(id) ON DELETE CASCADE
);

CREATE TABLE IF NOT EXISTS project_revision_assets (
    project_id TEXT NOT NULL,
    revision INTEGER NOT NULL,
    asset_id TEXT NOT NULL,
    sort_order INTEGER NOT NULL,
    PRIMARY KEY(project_id, revision, asset_id),
    FOREIGN KEY(project_id, revision) REFERENCES project_revisions(project_id, revision) ON DELETE CASCADE,
    FOREIGN KEY(project_id, asset_id) REFERENCES assets(project_id, id) ON DELETE CASCADE
);

CREATE TABLE IF NOT EXISTS asset_versions (
    project_id TEXT NOT NULL,
    revision INTEGER NOT NULL,
    asset_id TEXT NOT NULL,
    kind TEXT NOT NULL,
    name TEXT NOT NULL,
    uri TEXT,
    source_kind TEXT NOT NULL,
    managed_uri TEXT,
    original_filename TEXT,
    sha256 TEXT,
    blob_id TEXT,
    byte_size INTEGER,
    mime_type TEXT,
    duration_ticks INTEGER,
    width INTEGER,
    height INTEGER,
    frame_rate TEXT,
    video_codec TEXT,
    rotation INTEGER,
    audio_codec TEXT,
    audio_channels INTEGER,
    audio_sample_rate INTEGER,
    proxy_asset_id TEXT,
    thumbnail_asset_id TEXT,
    parent_asset_id TEXT,
    intake_status TEXT NOT NULL,
    observation_summary_json TEXT NOT NULL DEFAULT '{}',
    PRIMARY KEY(project_id, revision, asset_id),
    FOREIGN KEY(project_id, revision) REFERENCES project_revisions(project_id, revision) ON DELETE CASCADE,
    FOREIGN KEY(project_id, asset_id) REFERENCES assets(project_id, id) ON DELETE CASCADE
);

CREATE TABLE IF NOT EXISTS tracks (
    project_id TEXT NOT NULL,
    id TEXT NOT NULL,
    created_at TEXT NOT NULL,
    PRIMARY KEY(project_id, id),
    FOREIGN KEY(project_id) REFERENCES projects(id) ON DELETE CASCADE
);

CREATE TABLE IF NOT EXISTS project_revision_tracks (
    project_id TEXT NOT NULL,
    revision INTEGER NOT NULL,
    track_id TEXT NOT NULL,
    kind TEXT NOT NULL,
    name TEXT NOT NULL,
    sort_order INTEGER NOT NULL,
    PRIMARY KEY(project_id, revision, track_id),
    FOREIGN KEY(project_id, revision) REFERENCES project_revisions(project_id, revision) ON DELETE CASCADE,
    FOREIGN KEY(project_id, track_id) REFERENCES tracks(project_id, id) ON DELETE CASCADE
);

CREATE TABLE IF NOT EXISTS timeline_items (
    project_id TEXT NOT NULL,
    id TEXT NOT NULL,
    kind TEXT NOT NULL,
    asset_id TEXT,
    created_at TEXT NOT NULL,
    PRIMARY KEY(project_id, id),
    FOREIGN KEY(project_id) REFERENCES projects(id) ON DELETE CASCADE
);

CREATE TABLE IF NOT EXISTS timeline_item_versions (
    project_id TEXT NOT NULL,
    revision INTEGER NOT NULL,
    item_id TEXT NOT NULL,
    track_id TEXT NOT NULL,
    name TEXT NOT NULL,
    start_ticks INTEGER NOT NULL CHECK(start_ticks >= 0),
    duration_ticks INTEGER NOT NULL CHECK(duration_ticks > 0),
    trim_start_ticks INTEGER NOT NULL,
    trim_end_ticks INTEGER NOT NULL,
    source_in_ticks INTEGER NOT NULL,
    source_out_ticks INTEGER,
    color TEXT NOT NULL,
    text TEXT,
    x INTEGER NOT NULL,
    y INTEGER NOT NULL,
    width INTEGER NOT NULL,
    height INTEGER NOT NULL,
    fit_mode TEXT NOT NULL,
    scale REAL NOT NULL,
    opacity REAL NOT NULL,
    rotation REAL NOT NULL,
    gain_db REAL NOT NULL,
    muted INTEGER NOT NULL CHECK(muted IN (0,1)),
    crop_keyframes_json TEXT NOT NULL DEFAULT '[]',
    caption_words_json TEXT NOT NULL DEFAULT '[]',
    caption_style_json TEXT,
    PRIMARY KEY(project_id, revision, item_id),
    FOREIGN KEY(project_id, revision) REFERENCES project_revisions(project_id, revision) ON DELETE CASCADE,
    FOREIGN KEY(project_id, item_id) REFERENCES timeline_items(project_id, id) ON DELETE CASCADE
);

CREATE TABLE IF NOT EXISTS timeline_crop_keyframes (
    project_id TEXT NOT NULL, revision INTEGER NOT NULL, item_id TEXT NOT NULL,
    ordinal INTEGER NOT NULL, time_ticks INTEGER NOT NULL, center_x REAL NOT NULL,
    center_y REAL NOT NULL, zoom REAL NOT NULL, confidence REAL, locked INTEGER NOT NULL,
    PRIMARY KEY(project_id,revision,item_id,ordinal)
);

CREATE TABLE IF NOT EXISTS timeline_caption_words (
    project_id TEXT NOT NULL, revision INTEGER NOT NULL, item_id TEXT NOT NULL,
    ordinal INTEGER NOT NULL, word_id TEXT NOT NULL, text TEXT NOT NULL,
    start_ticks INTEGER NOT NULL, end_ticks INTEGER NOT NULL, confidence REAL,
    PRIMARY KEY(project_id,revision,item_id,ordinal)
);

CREATE TABLE IF NOT EXISTS timeline_caption_styles (
    project_id TEXT NOT NULL, revision INTEGER NOT NULL, item_id TEXT NOT NULL,
    preset TEXT NOT NULL,font_family TEXT NOT NULL,font_size INTEGER NOT NULL,
    text_color TEXT NOT NULL,highlight_color TEXT NOT NULL,background_color TEXT NOT NULL,
    position TEXT NOT NULL,words_per_cue INTEGER NOT NULL,
    PRIMARY KEY(project_id,revision,item_id)
);

CREATE TABLE IF NOT EXISTS events (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    project_id TEXT NOT NULL,
    before_revision INTEGER NOT NULL,
    after_revision INTEGER NOT NULL,
    request_id TEXT NOT NULL,
    actor TEXT NOT NULL,
    command TEXT NOT NULL,
    arguments_json TEXT NOT NULL,
    created_at TEXT NOT NULL,
    UNIQUE(project_id, request_id),
    FOREIGN KEY(project_id) REFERENCES projects(id) ON DELETE CASCADE,
    FOREIGN KEY(project_id, before_revision) REFERENCES project_revisions(project_id, revision),
    FOREIGN KEY(project_id, after_revision) REFERENCES project_revisions(project_id, revision)
);

CREATE TABLE IF NOT EXISTS receipts (
    id TEXT PRIMARY KEY,
    project_id TEXT NOT NULL,
    request_id TEXT NOT NULL,
    command TEXT NOT NULL,
    status TEXT NOT NULL,
    actor TEXT NOT NULL,
    project_revision INTEGER NOT NULL,
    payload_json TEXT NOT NULL DEFAULT '{}',
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL,
    UNIQUE(project_id, request_id),
    FOREIGN KEY(project_id) REFERENCES projects(id) ON DELETE CASCADE
);

CREATE TABLE IF NOT EXISTS receipt_transitions (
    receipt_id TEXT NOT NULL,
    sequence INTEGER NOT NULL,
    status TEXT NOT NULL,
    transitioned_at TEXT NOT NULL,
    PRIMARY KEY(receipt_id, sequence),
    FOREIGN KEY(receipt_id) REFERENCES receipts(id) ON DELETE CASCADE
);

CREATE TABLE IF NOT EXISTS observations (
    id TEXT PRIMARY KEY,
    receipt_id TEXT NOT NULL,
    kind TEXT,
    observer TEXT,
    failure_domain TEXT,
    independent_failure_domain INTEGER,
    passed INTEGER,
    inconclusive INTEGER NOT NULL DEFAULT 0,
    observed_at TEXT,
    body_json TEXT NOT NULL DEFAULT '{}',
    FOREIGN KEY(receipt_id) REFERENCES receipts(id) ON DELETE CASCADE
);

CREATE TABLE IF NOT EXISTS observation_findings (
    observation_id TEXT NOT NULL,
    sequence INTEGER NOT NULL,
    code TEXT NOT NULL,
    passed INTEGER,
    severity TEXT,
    summary TEXT NOT NULL,
    evidence_json TEXT NOT NULL DEFAULT '{}',
    body_json TEXT NOT NULL DEFAULT '{}',
    PRIMARY KEY(observation_id, sequence),
    FOREIGN KEY(observation_id) REFERENCES observations(id) ON DELETE CASCADE
);

CREATE TABLE IF NOT EXISTS selections (
    project_id TEXT NOT NULL,
    item_id TEXT NOT NULL,
    ordinal INTEGER NOT NULL,
    PRIMARY KEY(project_id, item_id),
    FOREIGN KEY(project_id) REFERENCES projects(id) ON DELETE CASCADE
);

CREATE TABLE IF NOT EXISTS jobs (
    id TEXT PRIMARY KEY,
    project_id TEXT NOT NULL,
    project_revision INTEGER NOT NULL,
    kind TEXT NOT NULL,
    state TEXT NOT NULL,
    progress REAL NOT NULL DEFAULT 0,
    worker_id TEXT,
    frozen_spec_json TEXT NOT NULL,
    result_artifact_id TEXT,
    error_code TEXT,
    error_detail TEXT,
    cancellation_requested INTEGER NOT NULL DEFAULT 0,
    stage TEXT,
    status_message TEXT,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL,
    FOREIGN KEY(project_id) REFERENCES projects(id) ON DELETE CASCADE
);

CREATE TABLE IF NOT EXISTS job_attempts (
    job_id TEXT NOT NULL,
    attempt INTEGER NOT NULL,
    worker_id TEXT,
    state TEXT NOT NULL,
    started_at TEXT NOT NULL,
    finished_at TEXT,
    error_code TEXT,
    error_detail TEXT,
    PRIMARY KEY(job_id, attempt),
    FOREIGN KEY(job_id) REFERENCES jobs(id) ON DELETE CASCADE
);

CREATE TABLE IF NOT EXISTS artifacts (
    id TEXT PRIMARY KEY,
    project_id TEXT NOT NULL,
    job_id TEXT,
    asset_id TEXT,
    kind TEXT NOT NULL,
    managed_uri TEXT NOT NULL,
    sha256 TEXT NOT NULL,
    byte_size INTEGER NOT NULL,
    mime_type TEXT,
    provenance_json TEXT NOT NULL DEFAULT '{}',
    created_at TEXT NOT NULL,
    FOREIGN KEY(project_id) REFERENCES projects(id) ON DELETE CASCADE,
    FOREIGN KEY(job_id) REFERENCES jobs(id) ON DELETE SET NULL
);

CREATE TABLE IF NOT EXISTS capture_sessions (
    id TEXT PRIMARY KEY,
    project_id TEXT NOT NULL,
    adapter_id TEXT NOT NULL,
    state TEXT NOT NULL,
    capability_snapshot_json TEXT NOT NULL,
    request_spec_json TEXT NOT NULL,
    consent_state TEXT NOT NULL,
    result_asset_id TEXT,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL,
    FOREIGN KEY(project_id) REFERENCES projects(id) ON DELETE CASCADE
);

CREATE TABLE IF NOT EXISTS suggestions (
    id TEXT PRIMARY KEY,
    project_id TEXT NOT NULL,
    source_revision INTEGER NOT NULL,
    generator_kind TEXT NOT NULL,
    state TEXT NOT NULL,
    commands_json TEXT NOT NULL,
    reason TEXT NOT NULL,
    evidence_json TEXT NOT NULL DEFAULT '{}',
    confidence REAL,
    job_id TEXT,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL,
    FOREIGN KEY(project_id) REFERENCES projects(id) ON DELETE CASCADE
);

CREATE TABLE IF NOT EXISTS approvals (
    id TEXT PRIMARY KEY,
    project_id TEXT NOT NULL,
    subject_kind TEXT NOT NULL,
    subject_id TEXT NOT NULL,
    approval_kind TEXT NOT NULL,
    state TEXT NOT NULL,
    actor TEXT,
    disclosure_json TEXT NOT NULL DEFAULT '{}',
    created_at TEXT NOT NULL,
    decided_at TEXT,
    FOREIGN KEY(project_id) REFERENCES projects(id) ON DELETE CASCADE
);

CREATE TABLE IF NOT EXISTS providers (
    id TEXT PRIMARY KEY,
    provider_kind TEXT NOT NULL,
    display_name TEXT NOT NULL,
    adapter_version TEXT NOT NULL,
    capability_snapshot_json TEXT NOT NULL DEFAULT '{}',
    enabled INTEGER NOT NULL DEFAULT 0,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS model_runs (
    id TEXT PRIMARY KEY,
    project_id TEXT NOT NULL,
    provider_id TEXT NOT NULL,
    model_id TEXT NOT NULL,
    purpose TEXT NOT NULL,
    state TEXT NOT NULL,
    external_operation_id TEXT,
    capability_snapshot_json TEXT NOT NULL,
    request_spec_json TEXT NOT NULL,
    response_summary_json TEXT NOT NULL DEFAULT '{}',
    source_hashes_json TEXT NOT NULL DEFAULT '[]',
    cost_summary_json TEXT NOT NULL DEFAULT '{}',
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL,
    FOREIGN KEY(project_id) REFERENCES projects(id) ON DELETE CASCADE,
    FOREIGN KEY(provider_id) REFERENCES providers(id)
);

CREATE TABLE IF NOT EXISTS interaction_threads (
    id TEXT PRIMARY KEY,
    project_id TEXT NOT NULL,
    provider_id TEXT NOT NULL,
    model_id TEXT NOT NULL,
    external_thread_id TEXT,
    parent_thread_id TEXT,
    state TEXT NOT NULL,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL,
    FOREIGN KEY(project_id) REFERENCES projects(id) ON DELETE CASCADE,
    FOREIGN KEY(provider_id) REFERENCES providers(id)
);

CREATE TABLE IF NOT EXISTS generation_candidates (
    id TEXT PRIMARY KEY,
    project_id TEXT NOT NULL,
    model_run_id TEXT NOT NULL,
    interaction_thread_id TEXT,
    artifact_id TEXT,
    state TEXT NOT NULL,
    source_revision INTEGER NOT NULL,
    provenance_json TEXT NOT NULL,
    observation_summary_json TEXT NOT NULL DEFAULT '{}',
    accepted_asset_id TEXT,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL,
    FOREIGN KEY(project_id) REFERENCES projects(id) ON DELETE CASCADE,
    FOREIGN KEY(model_run_id) REFERENCES model_runs(id),
    FOREIGN KEY(interaction_thread_id) REFERENCES interaction_threads(id),
    FOREIGN KEY(artifact_id) REFERENCES artifacts(id)
);

CREATE TABLE IF NOT EXISTS pairings (
    code TEXT PRIMARY KEY,
    workspace_id TEXT NOT NULL,
    expires_at TEXT NOT NULL,
    consumed INTEGER NOT NULL DEFAULT 0
);

CREATE TABLE IF NOT EXISTS tokens (
    token TEXT PRIMARY KEY,
    workspace_id TEXT NOT NULL,
    actor_name TEXT NOT NULL,
    expires_at TEXT NOT NULL,
    revoked INTEGER NOT NULL DEFAULT 0
);

CREATE TABLE IF NOT EXISTS workspaces (
    id TEXT PRIMARY KEY,
    name TEXT NOT NULL,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS media_blobs (
    id TEXT PRIMARY KEY,
    sha256 TEXT NOT NULL UNIQUE,
    byte_size INTEGER NOT NULL,
    mime_type TEXT,
    storage_project_id TEXT NOT NULL,
    storage_asset_id TEXT NOT NULL,
    storage_kind TEXT NOT NULL,
    created_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS analysis_artifacts (
    id TEXT PRIMARY KEY,
    project_id TEXT NOT NULL,
    source_revision INTEGER NOT NULL,
    source_asset_id TEXT NOT NULL,
    source_sha256 TEXT NOT NULL,
    kind TEXT NOT NULL,
    schema_version TEXT NOT NULL,
    provider_id TEXT NOT NULL,
    provider_version TEXT NOT NULL,
    settings_hash TEXT NOT NULL,
    body_json TEXT NOT NULL,
    created_at TEXT NOT NULL,
    UNIQUE(source_sha256,kind,schema_version,provider_id,provider_version,settings_hash),
    FOREIGN KEY(project_id) REFERENCES projects(id) ON DELETE CASCADE
);

CREATE INDEX IF NOT EXISTS idx_projects_updated ON projects(updated_at DESC);
CREATE INDEX IF NOT EXISTS idx_revision_assets_project ON project_revision_assets(project_id, revision, sort_order);
CREATE INDEX IF NOT EXISTS idx_asset_versions_project ON asset_versions(project_id, revision);
CREATE INDEX IF NOT EXISTS idx_revision_tracks_project ON project_revision_tracks(project_id, revision, sort_order);
CREATE INDEX IF NOT EXISTS idx_item_versions_track ON timeline_item_versions(project_id, revision, track_id, start_ticks);
CREATE INDEX IF NOT EXISTS idx_events_project_revision ON events(project_id, after_revision DESC);
CREATE INDEX IF NOT EXISTS idx_receipts_project_created ON receipts(project_id, created_at DESC);
CREATE INDEX IF NOT EXISTS idx_jobs_state_created ON jobs(state, created_at);
CREATE INDEX IF NOT EXISTS idx_model_runs_project_created ON model_runs(project_id, created_at DESC);
CREATE INDEX IF NOT EXISTS idx_candidates_project_state ON generation_candidates(project_id, state, created_at DESC);
CREATE INDEX IF NOT EXISTS idx_projects_workspace ON projects(workspace_id,updated_at DESC);
CREATE INDEX IF NOT EXISTS idx_suggestions_project_state ON suggestions(project_id,state,created_at DESC);
CREATE INDEX IF NOT EXISTS idx_analysis_cache ON analysis_artifacts(source_sha256,kind,settings_hash);
"""


def _table_columns(connection: sqlite3.Connection, table: str) -> set[str]:
    return {str(row["name"]) for row in connection.execute(f"PRAGMA table_info({table})").fetchall()}


def _table_exists(connection: sqlite3.Connection, table: str) -> bool:
    return connection.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name=?", (table,)).fetchone() is not None


def _json(value: Any) -> str:
    return json.dumps(value, sort_keys=True, separators=(",", ":"))


def write_project_snapshot(
    connection: sqlite3.Connection,
    project: Project,
    *,
    request_id: str | None = None,
    actor: str | None = None,
    command: str | None = None,
) -> None:
    existing = connection.execute("SELECT created_at FROM projects WHERE id = ?", (project.id,)).fetchone()
    created_at = str(existing["created_at"]) if existing else project.updated_at
    connection.execute(
        """INSERT INTO projects(
             id,name,workspace_id,parent_project_id,source_project_revision,
             source_suggestion_id,variant_kind,target_aspect_ratio,current_revision,
             schema_version,created_at,updated_at)
           VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
           ON CONFLICT(id) DO UPDATE SET
             name=excluded.name,
             workspace_id=COALESCE(excluded.workspace_id,projects.workspace_id),
             parent_project_id=excluded.parent_project_id,
             source_project_revision=excluded.source_project_revision,
             source_suggestion_id=excluded.source_suggestion_id,
             variant_kind=excluded.variant_kind,
             target_aspect_ratio=excluded.target_aspect_ratio,
             current_revision=MAX(projects.current_revision, excluded.current_revision),
             schema_version=excluded.schema_version,
             updated_at=excluded.updated_at""",
        (
            project.id, project.name, project.workspace_id or project.id,
            project.parent_project_id, project.source_project_revision,
            project.source_suggestion_id, project.variant_kind, project.target_aspect_ratio,
            project.revision, project.schema_version, created_at, project.updated_at,
        ),
    )
    parent_revision = project.revision - 1 if project.revision > 1 else None
    connection.execute(
        """INSERT INTO project_revisions(
             project_id, revision, parent_revision, request_id, actor, command, name,
             canvas_width, canvas_height, fps_numerator, fps_denominator,
             duration_ticks, created_at
           ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
           ON CONFLICT(project_id, revision) DO UPDATE SET
             request_id=COALESCE(excluded.request_id, project_revisions.request_id),
             actor=COALESCE(excluded.actor, project_revisions.actor),
             command=COALESCE(excluded.command, project_revisions.command),
             name=excluded.name, canvas_width=excluded.canvas_width,
             canvas_height=excluded.canvas_height, fps_numerator=excluded.fps_numerator,
             fps_denominator=excluded.fps_denominator, duration_ticks=excluded.duration_ticks,
             created_at=excluded.created_at""",
        (
            project.id, project.revision, parent_revision, request_id, actor, command,
            project.name, project.canvas.width, project.canvas.height,
            project.canvas.fps_numerator, project.canvas.fps_denominator,
            project.duration_ticks, project.updated_at,
        ),
    )
    connection.execute("DELETE FROM project_revision_assets WHERE project_id=? AND revision=?", (project.id, project.revision))
    connection.execute("DELETE FROM asset_versions WHERE project_id=? AND revision=?", (project.id, project.revision))
    connection.execute("DELETE FROM timeline_item_versions WHERE project_id=? AND revision=?", (project.id, project.revision))
    connection.execute("DELETE FROM timeline_crop_keyframes WHERE project_id=? AND revision=?", (project.id, project.revision))
    connection.execute("DELETE FROM timeline_caption_words WHERE project_id=? AND revision=?", (project.id, project.revision))
    connection.execute("DELETE FROM timeline_caption_styles WHERE project_id=? AND revision=?", (project.id, project.revision))
    connection.execute("DELETE FROM project_revision_tracks WHERE project_id=? AND revision=?", (project.id, project.revision))
    for order, asset in enumerate(project.assets):
        connection.execute(
            """INSERT INTO assets(
                 project_id,id,kind,name,uri,source_kind,managed_uri,original_filename,
                 sha256,blob_id,byte_size,mime_type,duration_ticks,width,height,frame_rate,
                 video_codec,rotation,audio_codec,audio_channels,audio_sample_rate,
                 proxy_asset_id,thumbnail_asset_id,parent_asset_id,intake_status,
                 observation_summary_json,created_at,updated_at
               ) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)
               ON CONFLICT(project_id,id) DO UPDATE SET
                 kind=excluded.kind,name=excluded.name,uri=excluded.uri,
                 source_kind=excluded.source_kind,managed_uri=excluded.managed_uri,
                 original_filename=excluded.original_filename,sha256=excluded.sha256,blob_id=excluded.blob_id,
                 byte_size=excluded.byte_size,mime_type=excluded.mime_type,
                 duration_ticks=excluded.duration_ticks,width=excluded.width,height=excluded.height,
                 frame_rate=excluded.frame_rate,video_codec=excluded.video_codec,
                 rotation=excluded.rotation,audio_codec=excluded.audio_codec,
                 audio_channels=excluded.audio_channels,audio_sample_rate=excluded.audio_sample_rate,
                 proxy_asset_id=excluded.proxy_asset_id,thumbnail_asset_id=excluded.thumbnail_asset_id,
                 parent_asset_id=excluded.parent_asset_id,intake_status=excluded.intake_status,
                 observation_summary_json=excluded.observation_summary_json,updated_at=excluded.updated_at""",
            (
                project.id, asset.id, asset.kind, asset.name, asset.uri, asset.source_kind,
                asset.managed_uri, asset.original_filename, asset.sha256, asset.blob_id, asset.byte_size,
                asset.mime_type, asset.duration_ticks, asset.width, asset.height,
                asset.frame_rate, asset.video_codec, asset.rotation, asset.audio_codec,
                asset.audio_channels, asset.audio_sample_rate, asset.proxy_asset_id,
                asset.thumbnail_asset_id, asset.parent_asset_id, asset.intake_status,
                _json(asset.observation_summary), project.updated_at, project.updated_at,
            ),
        )
        connection.execute(
            "INSERT INTO project_revision_assets(project_id,revision,asset_id,sort_order) VALUES (?,?,?,?)",
            (project.id, project.revision, asset.id, order),
        )
        connection.execute(
            """INSERT INTO asset_versions(
                 project_id,revision,asset_id,kind,name,uri,source_kind,managed_uri,
                 original_filename,sha256,blob_id,byte_size,mime_type,duration_ticks,width,height,
                 frame_rate,video_codec,rotation,audio_codec,audio_channels,audio_sample_rate,
                 proxy_asset_id,thumbnail_asset_id,parent_asset_id,intake_status,
                 observation_summary_json
               ) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
            (
                project.id, project.revision, asset.id, asset.kind, asset.name, asset.uri,
                asset.source_kind, asset.managed_uri, asset.original_filename, asset.sha256, asset.blob_id,
                asset.byte_size, asset.mime_type, asset.duration_ticks, asset.width, asset.height,
                asset.frame_rate, asset.video_codec, asset.rotation, asset.audio_codec,
                asset.audio_channels, asset.audio_sample_rate, asset.proxy_asset_id,
                asset.thumbnail_asset_id, asset.parent_asset_id, asset.intake_status,
                _json(asset.observation_summary),
            ),
        )
    for track_order, track in enumerate(project.tracks):
        connection.execute(
            "INSERT OR IGNORE INTO tracks(project_id,id,created_at) VALUES (?,?,?)",
            (project.id, track.id, project.updated_at),
        )
        connection.execute(
            "INSERT INTO project_revision_tracks(project_id,revision,track_id,kind,name,sort_order) VALUES (?,?,?,?,?,?)",
            (project.id, project.revision, track.id, track.kind, track.name, track_order),
        )
        for item in track.items:
            connection.execute(
                """INSERT INTO timeline_items(project_id,id,kind,asset_id,created_at) VALUES (?,?,?,?,?)
                   ON CONFLICT(project_id,id) DO UPDATE SET kind=excluded.kind,asset_id=excluded.asset_id""",
                (project.id, item.id, item.kind, item.asset_id, project.updated_at),
            )
            connection.execute(
                """INSERT INTO timeline_item_versions(
                     project_id,revision,item_id,track_id,name,start_ticks,duration_ticks,
                     trim_start_ticks,trim_end_ticks,source_in_ticks,source_out_ticks,color,
                     text,x,y,width,height,fit_mode,scale,opacity,rotation,gain_db,muted,
                     crop_keyframes_json,caption_words_json,caption_style_json
                   ) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
                (
                    project.id, project.revision, item.id, track.id, item.name,
                    item.start_ticks, item.duration_ticks, item.trim_start_ticks,
                    item.trim_end_ticks, item.source_in_ticks, item.source_out_ticks,
                    item.color, item.text, item.x, item.y, item.width, item.height,
                    item.fit_mode, item.scale, item.opacity, item.rotation,
                    item.gain_db, int(item.muted), "[]", "[]", None,
                ),
            )
            for ordinal, keyframe in enumerate(item.crop_keyframes):
                connection.execute(
                    """INSERT INTO timeline_crop_keyframes(
                         project_id,revision,item_id,ordinal,time_ticks,center_x,center_y,zoom,confidence,locked
                       ) VALUES (?,?,?,?,?,?,?,?,?,?)""",
                    (project.id,project.revision,item.id,ordinal,keyframe.time_ticks,keyframe.center_x,
                     keyframe.center_y,keyframe.zoom,keyframe.confidence,int(keyframe.locked)),
                )
            for ordinal, word in enumerate(item.caption_words):
                connection.execute(
                    """INSERT INTO timeline_caption_words(
                         project_id,revision,item_id,ordinal,word_id,text,start_ticks,end_ticks,confidence
                       ) VALUES (?,?,?,?,?,?,?,?,?)""",
                    (project.id,project.revision,item.id,ordinal,word.id,word.text,word.start_ticks,word.end_ticks,word.confidence),
                )
            if item.caption_style:
                style = item.caption_style
                connection.execute(
                    """INSERT INTO timeline_caption_styles(
                         project_id,revision,item_id,preset,font_family,font_size,text_color,highlight_color,
                         background_color,position,words_per_cue
                       ) VALUES (?,?,?,?,?,?,?,?,?,?,?)""",
                    (project.id,project.revision,item.id,style.preset,style.font_family,style.font_size,
                     style.text_color,style.highlight_color,style.background_color,style.position,style.words_per_cue),
                )


def read_project_snapshot(connection: sqlite3.Connection, project_id: str, revision: int | None = None) -> Project:
    head = connection.execute("SELECT * FROM projects WHERE id=?", (project_id,)).fetchone()
    if head is None:
        raise KeyError(project_id)
    revision = int(revision or head["current_revision"])
    row = connection.execute(
        "SELECT * FROM project_revisions WHERE project_id=? AND revision=?",
        (project_id, revision),
    ).fetchone()
    if row is None:
        raise KeyError(f"{project_id}@{revision}")
    assets: list[Asset] = []
    asset_rows = connection.execute(
        """SELECT av.*, av.asset_id AS id FROM project_revision_assets pra
           JOIN asset_versions av ON av.project_id=pra.project_id
             AND av.revision=pra.revision AND av.asset_id=pra.asset_id
           WHERE pra.project_id=? AND pra.revision=? ORDER BY pra.sort_order""",
        (project_id, revision),
    ).fetchall()
    for asset in asset_rows:
        assets.append(Asset.model_validate({
            "id": asset["id"], "kind": asset["kind"], "name": asset["name"], "uri": asset["uri"],
            "source_kind": asset["source_kind"], "managed_uri": asset["managed_uri"],
            "original_filename": asset["original_filename"], "sha256": asset["sha256"],
            "blob_id": asset["blob_id"] if "blob_id" in asset.keys() else None,
            "byte_size": asset["byte_size"], "mime_type": asset["mime_type"],
            "duration_ticks": asset["duration_ticks"], "width": asset["width"], "height": asset["height"],
            "frame_rate": asset["frame_rate"], "video_codec": asset["video_codec"], "rotation": asset["rotation"],
            "audio_codec": asset["audio_codec"], "audio_channels": asset["audio_channels"],
            "audio_sample_rate": asset["audio_sample_rate"], "proxy_asset_id": asset["proxy_asset_id"],
            "thumbnail_asset_id": asset["thumbnail_asset_id"], "parent_asset_id": asset["parent_asset_id"],
            "intake_status": asset["intake_status"],
            "observation_summary": json.loads(asset["observation_summary_json"] or "{}"),
        }))
    tracks: list[Track] = []
    track_rows = connection.execute(
        "SELECT * FROM project_revision_tracks WHERE project_id=? AND revision=? ORDER BY sort_order",
        (project_id, revision),
    ).fetchall()
    for track_row in track_rows:
        item_rows = connection.execute(
            """SELECT tiv.*, ti.kind, ti.asset_id FROM timeline_item_versions tiv
               JOIN timeline_items ti ON ti.project_id=tiv.project_id AND ti.id=tiv.item_id
               WHERE tiv.project_id=? AND tiv.revision=? AND tiv.track_id=?
               ORDER BY tiv.start_ticks, tiv.item_id""",
            (project_id, revision, track_row["track_id"]),
        ).fetchall()
        items = []
        for item in item_rows:
            crop_rows = connection.execute(
                """SELECT * FROM timeline_crop_keyframes
                   WHERE project_id=? AND revision=? AND item_id=? ORDER BY ordinal""",
                (project_id,revision,item["item_id"]),
            ).fetchall()
            word_rows = connection.execute(
                """SELECT * FROM timeline_caption_words
                   WHERE project_id=? AND revision=? AND item_id=? ORDER BY ordinal""",
                (project_id,revision,item["item_id"]),
            ).fetchall()
            style_row = connection.execute(
                "SELECT * FROM timeline_caption_styles WHERE project_id=? AND revision=? AND item_id=?",
                (project_id,revision,item["item_id"]),
            ).fetchone()
            crop = [dict(entry) | {"locked":bool(entry["locked"])} for entry in crop_rows]
            words = [{
                "id":entry["word_id"],"text":entry["text"],"start_ticks":entry["start_ticks"],
                "end_ticks":entry["end_ticks"],"confidence":entry["confidence"],
            } for entry in word_rows]
            style = ({
                "preset":style_row["preset"],"font_family":style_row["font_family"],
                "font_size":style_row["font_size"],"text_color":style_row["text_color"],
                "highlight_color":style_row["highlight_color"],"background_color":style_row["background_color"],
                "position":style_row["position"],"words_per_cue":style_row["words_per_cue"],
            } if style_row else None)
            # JSON columns are a one-release compatibility fallback for databases
            # written before normalized caption/keyframe children were introduced.
            if not crop and "crop_keyframes_json" in item.keys():
                crop = json.loads(item["crop_keyframes_json"] or "[]")
            if not words and "caption_words_json" in item.keys():
                words = json.loads(item["caption_words_json"] or "[]")
            if style is None and "caption_style_json" in item.keys() and item["caption_style_json"]:
                style = json.loads(item["caption_style_json"])
            items.append(TimelineItem.model_validate({
                "id": item["item_id"], "kind": item["kind"], "track_id": item["track_id"],
                "name": item["name"], "start_ticks": item["start_ticks"], "duration_ticks": item["duration_ticks"],
                "trim_start_ticks": item["trim_start_ticks"], "trim_end_ticks": item["trim_end_ticks"],
                "source_in_ticks": item["source_in_ticks"], "source_out_ticks": item["source_out_ticks"],
                "asset_id": item["asset_id"], "color": item["color"], "text": item["text"],
                "x": item["x"], "y": item["y"], "width": item["width"], "height": item["height"],
                "fit_mode": item["fit_mode"], "scale": item["scale"], "opacity": item["opacity"],
                "rotation": item["rotation"], "gain_db": item["gain_db"], "muted": bool(item["muted"]),
                "crop_keyframes":crop,"caption_words":words,"caption_style":style,
            }))
        tracks.append(Track(id=track_row["track_id"], kind=track_row["kind"], name=track_row["name"], items=items))
    return Project(
        id=project_id,
        name=row["name"],
        # Root project snapshots predate workspaces; the database head owns their
        # workspace membership without rewriting historical domain snapshots.
        workspace_id=(head["workspace_id"] if "workspace_id" in head.keys() else project_id)
        if ("parent_project_id" in head.keys() and head["parent_project_id"] is not None) else None,
        parent_project_id=head["parent_project_id"] if "parent_project_id" in head.keys() else None,
        source_project_revision=head["source_project_revision"] if "source_project_revision" in head.keys() else None,
        source_suggestion_id=head["source_suggestion_id"] if "source_suggestion_id" in head.keys() else None,
        variant_kind=head["variant_kind"] if "variant_kind" in head.keys() else None,
        target_aspect_ratio=head["target_aspect_ratio"] if "target_aspect_ratio" in head.keys() else None,
        schema_version=int(head["schema_version"]),
        revision=revision,
        canvas=Canvas(
            width=row["canvas_width"], height=row["canvas_height"],
            fps_numerator=row["fps_numerator"], fps_denominator=row["fps_denominator"],
        ),
        duration_ticks=row["duration_ticks"],
        assets=assets,
        tracks=tracks,
        updated_at=row["created_at"],
    )


def store_observation(connection: sqlite3.Connection, receipt_id: str, observation: dict[str, Any]) -> None:
    connection.execute("DELETE FROM observations WHERE receipt_id=?", (receipt_id,))
    observation_id = f"observation_{uuid4().hex[:16]}"
    findings = list(observation.get("findings") or [])
    body = {key: value for key, value in observation.items() if key != "findings"}
    independent = observation.get("independent_failure_domain")
    connection.execute(
        """INSERT INTO observations(
             id,receipt_id,kind,observer,failure_domain,independent_failure_domain,
             passed,inconclusive,observed_at,body_json
           ) VALUES (?,?,?,?,?,?,?,?,?,?)""",
        (
            observation_id, receipt_id, observation.get("kind"), observation.get("observer"),
            observation.get("observer_failure_domain") or observation.get("failure_domain"),
            None if independent is None else int(bool(independent)),
            None if observation.get("passed") is None else int(bool(observation.get("passed"))),
            int(bool(observation.get("inconclusive", False))), observation.get("observed_at"), _json(body),
        ),
    )
    for sequence, finding in enumerate(findings):
        connection.execute(
            """INSERT INTO observation_findings(
                 observation_id,sequence,code,passed,severity,summary,evidence_json,body_json
               ) VALUES (?,?,?,?,?,?,?,?)""",
            (
                observation_id, sequence, str(finding.get("code", "unknown")),
                None if finding.get("passed") is None else int(bool(finding.get("passed"))),
                finding.get("severity"), str(finding.get("summary", "")),
                _json(finding.get("evidence") or {}), _json(finding),
            ),
        )


def write_receipt(connection: sqlite3.Connection, receipt: Receipt) -> None:
    payload = dict(receipt.payload)
    transitions = list(payload.pop("transitions", []))
    observation = payload.pop("observation", None)
    connection.execute(
        """INSERT INTO receipts(
             id,project_id,request_id,command,status,actor,project_revision,
             payload_json,created_at,updated_at
           ) VALUES (?,?,?,?,?,?,?,?,?,?)
           ON CONFLICT(id) DO UPDATE SET status=excluded.status,actor=excluded.actor,
             project_revision=excluded.project_revision,payload_json=excluded.payload_json,
             updated_at=excluded.updated_at""",
        (
            receipt.id, receipt.project_id, receipt.request_id, receipt.command,
            receipt.status.value, receipt.actor, receipt.project_revision,
            _json(payload), receipt.created_at, receipt.updated_at,
        ),
    )
    connection.execute("DELETE FROM receipt_transitions WHERE receipt_id=?", (receipt.id,))
    for sequence, transition in enumerate(transitions):
        connection.execute(
            "INSERT INTO receipt_transitions(receipt_id,sequence,status,transitioned_at) VALUES (?,?,?,?)",
            (receipt.id, sequence, transition["status"], transition.get("at") or receipt.updated_at),
        )
    if observation is not None:
        store_observation(connection, receipt.id, observation)


def read_receipt(connection: sqlite3.Connection, row: sqlite3.Row) -> Receipt:
    payload = json.loads(row["payload_json"] or "{}")
    transitions = connection.execute(
        "SELECT status,transitioned_at FROM receipt_transitions WHERE receipt_id=? ORDER BY sequence",
        (row["id"],),
    ).fetchall()
    payload["transitions"] = [{"status": entry["status"], "at": entry["transitioned_at"]} for entry in transitions]
    observation = connection.execute("SELECT * FROM observations WHERE receipt_id=? ORDER BY rowid DESC LIMIT 1", (row["id"],)).fetchone()
    if observation:
        body = json.loads(observation["body_json"] or "{}")
        finding_rows = connection.execute(
            "SELECT body_json FROM observation_findings WHERE observation_id=? ORDER BY sequence",
            (observation["id"],),
        ).fetchall()
        body["findings"] = [json.loads(finding["body_json"]) for finding in finding_rows]
        payload["observation"] = body
    return Receipt(
        id=row["id"], project_id=row["project_id"], command=row["command"],
        status=ReceiptStatus(row["status"]), request_id=row["request_id"], actor=row["actor"],
        project_revision=row["project_revision"], payload=payload,
        created_at=row["created_at"], updated_at=row["updated_at"],
    )


def _rename_legacy_tables(connection: sqlite3.Connection) -> None:
    candidates = {
        "projects": "body",
        "receipts": "body",
        "events": "before_body",
        "selections": "body",
    }
    for table, legacy_column in candidates.items():
        if _table_exists(connection, table) and legacy_column in _table_columns(connection, table):
            connection.execute(f"ALTER TABLE {table} RENAME TO legacy_{table}")


def _migrate_legacy(connection: sqlite3.Connection) -> None:
    snapshots: dict[tuple[str, int], Project] = {}
    if _table_exists(connection, "legacy_events"):
        for event in connection.execute("SELECT before_body,after_body FROM legacy_events ORDER BY id"):
            for body in (event["before_body"], event["after_body"]):
                project = Project.model_validate_json(body)
                snapshots[(project.id, project.revision)] = project
    if _table_exists(connection, "legacy_projects"):
        for row in connection.execute("SELECT body FROM legacy_projects"):
            project = Project.model_validate_json(row["body"])
            snapshots[(project.id, project.revision)] = project
    for project in sorted(snapshots.values(), key=lambda entry: (entry.id, entry.revision)):
        write_project_snapshot(connection, project, command="legacy.migration", actor="migration")
    if _table_exists(connection, "legacy_events"):
        for event in connection.execute("SELECT * FROM legacy_events ORDER BY id"):
            before = Project.model_validate_json(event["before_body"])
            after = Project.model_validate_json(event["after_body"])
            connection.execute(
                """INSERT OR IGNORE INTO events(
                     id,project_id,before_revision,after_revision,request_id,actor,
                     command,arguments_json,created_at
                   ) VALUES (?,?,?,?,?,?,?,?,?)""",
                (
                    event["id"], event["project_id"], before.revision, after.revision,
                    event["request_id"], event["actor"], event["command"],
                    event["arguments"], event["created_at"],
                ),
            )
            connection.execute(
                """UPDATE project_revisions SET request_id=?,actor=?,command=?
                   WHERE project_id=? AND revision=?""",
                (event["request_id"], event["actor"], event["command"], event["project_id"], after.revision),
            )
    if _table_exists(connection, "legacy_receipts"):
        for row in connection.execute("SELECT body FROM legacy_receipts ORDER BY rowid"):
            write_receipt(connection, Receipt.model_validate_json(row["body"]))
    if _table_exists(connection, "legacy_selections"):
        for row in connection.execute("SELECT project_id,body FROM legacy_selections"):
            for ordinal, item_id in enumerate(json.loads(row["body"])):
                connection.execute(
                    "INSERT OR IGNORE INTO selections(project_id,item_id,ordinal) VALUES (?,?,?)",
                    (row["project_id"], item_id, ordinal),
                )
    for table in ("legacy_projects", "legacy_events", "legacy_receipts", "legacy_selections"):
        if _table_exists(connection, table):
            connection.execute(f"DROP TABLE {table}")


def apply_migrations(connection: sqlite3.Connection) -> None:
    connection.execute("PRAGMA foreign_keys=OFF")
    connection.execute(
        """CREATE TABLE IF NOT EXISTS schema_migrations(
             version INTEGER PRIMARY KEY,
             name TEXT NOT NULL,
             applied_at TEXT NOT NULL
           )"""
    )
    applied = {int(row["version"]) for row in connection.execute("SELECT version FROM schema_migrations")}
    if 1 not in applied:
        with connection:
            _rename_legacy_tables(connection)
            connection.executescript(NORMALIZED_SCHEMA)
            _migrate_legacy(connection)
            connection.execute(
                "INSERT INTO schema_migrations(version,name,applied_at) VALUES (1,?,?)",
                ("normalized_provider_neutral_core", utc_now()),
            )
            connection.execute("PRAGMA user_version=1")
        applied.add(1)
    if 2 not in applied:
        with connection:
            connection.execute("CREATE TABLE IF NOT EXISTS metadata(key TEXT PRIMARY KEY,value TEXT NOT NULL)")
            connection.execute(
                """UPDATE assets SET intake_status='pending',updated_at=?
                   WHERE source_kind='generated' AND managed_uri IS NULL AND sha256 IS NULL""",
                (utc_now(),),
            )
            if _table_exists(connection, "asset_versions"):
                connection.execute(
                    """UPDATE asset_versions SET intake_status='pending'
                       WHERE source_kind='generated' AND managed_uri IS NULL AND sha256 IS NULL"""
                )
            connection.execute(
                "INSERT OR REPLACE INTO metadata(key,value) VALUES ('persistence_schema_version',?)",
                (str(SCHEMA_VERSION),),
            )
            connection.execute(
                "INSERT INTO schema_migrations(version,name,applied_at) VALUES (2,?,?)",
                ("storage_metadata_and_legacy_asset_truth", utc_now()),
            )
            connection.execute("PRAGMA user_version=2")
        applied.add(2)
    if 3 not in applied:
        with connection:
            connection.execute(
                """CREATE TABLE IF NOT EXISTS asset_versions (
                     project_id TEXT NOT NULL, revision INTEGER NOT NULL, asset_id TEXT NOT NULL,
                     kind TEXT NOT NULL, name TEXT NOT NULL, uri TEXT, source_kind TEXT NOT NULL,
                     managed_uri TEXT, original_filename TEXT, sha256 TEXT, byte_size INTEGER,
                     mime_type TEXT, duration_ticks INTEGER, width INTEGER, height INTEGER,
                     frame_rate TEXT, video_codec TEXT, rotation INTEGER, audio_codec TEXT,
                     audio_channels INTEGER, audio_sample_rate INTEGER, proxy_asset_id TEXT,
                     thumbnail_asset_id TEXT, parent_asset_id TEXT, intake_status TEXT NOT NULL,
                     observation_summary_json TEXT NOT NULL DEFAULT '{}',
                     PRIMARY KEY(project_id, revision, asset_id),
                     FOREIGN KEY(project_id, revision)
                       REFERENCES project_revisions(project_id, revision) ON DELETE CASCADE,
                     FOREIGN KEY(project_id, asset_id)
                       REFERENCES assets(project_id, id) ON DELETE CASCADE
                   )"""
            )
            connection.execute(
                """INSERT OR IGNORE INTO asset_versions(
                     project_id,revision,asset_id,kind,name,uri,source_kind,managed_uri,
                     original_filename,sha256,byte_size,mime_type,duration_ticks,width,height,
                     frame_rate,video_codec,rotation,audio_codec,audio_channels,audio_sample_rate,
                     proxy_asset_id,thumbnail_asset_id,parent_asset_id,intake_status,
                     observation_summary_json
                   )
                   SELECT pra.project_id,pra.revision,a.id,a.kind,a.name,a.uri,a.source_kind,
                     a.managed_uri,a.original_filename,a.sha256,a.byte_size,a.mime_type,
                     a.duration_ticks,a.width,a.height,a.frame_rate,a.video_codec,a.rotation,
                     a.audio_codec,a.audio_channels,a.audio_sample_rate,a.proxy_asset_id,
                     a.thumbnail_asset_id,a.parent_asset_id,a.intake_status,
                     a.observation_summary_json
                   FROM project_revision_assets pra
                   JOIN assets a ON a.project_id=pra.project_id AND a.id=pra.asset_id"""
            )
            connection.execute(
                """UPDATE asset_versions SET intake_status='pending'
                   WHERE source_kind='generated' AND managed_uri IS NULL AND sha256 IS NULL"""
            )
            connection.execute(
                "CREATE INDEX IF NOT EXISTS idx_asset_versions_project ON asset_versions(project_id,revision)"
            )
            connection.execute(
                "INSERT OR REPLACE INTO metadata(key,value) VALUES ('persistence_schema_version',?)",
                (str(SCHEMA_VERSION),),
            )
            connection.execute(
                "INSERT INTO schema_migrations(version,name,applied_at) VALUES (3,?,?)",
                ("revisioned_asset_snapshots", utc_now()),
            )
            connection.execute("PRAGMA user_version=3")
        applied.add(3)
    if 4 not in applied:
        with connection:
            project_columns = _table_columns(connection, "projects")
            for name, sql_type in (
                ("workspace_id", "TEXT"), ("parent_project_id", "TEXT"),
                ("source_project_revision", "INTEGER"), ("source_suggestion_id", "TEXT"),
                ("variant_kind", "TEXT"), ("target_aspect_ratio", "TEXT"),
            ):
                if name not in project_columns:
                    connection.execute(f"ALTER TABLE projects ADD COLUMN {name} {sql_type}")
            if "blob_id" not in _table_columns(connection, "assets"):
                connection.execute("ALTER TABLE assets ADD COLUMN blob_id TEXT")
            if "blob_id" not in _table_columns(connection, "asset_versions"):
                connection.execute("ALTER TABLE asset_versions ADD COLUMN blob_id TEXT")
            item_columns = _table_columns(connection, "timeline_item_versions")
            if "crop_keyframes_json" not in item_columns:
                connection.execute("ALTER TABLE timeline_item_versions ADD COLUMN crop_keyframes_json TEXT NOT NULL DEFAULT '[]'")
            if "caption_words_json" not in item_columns:
                connection.execute("ALTER TABLE timeline_item_versions ADD COLUMN caption_words_json TEXT NOT NULL DEFAULT '[]'")
            if "caption_style_json" not in item_columns:
                connection.execute("ALTER TABLE timeline_item_versions ADD COLUMN caption_style_json TEXT")
            if "job_id" not in _table_columns(connection, "suggestions"):
                connection.execute("ALTER TABLE suggestions ADD COLUMN job_id TEXT")
            job_columns = _table_columns(connection, "jobs")
            if "stage" not in job_columns:
                connection.execute("ALTER TABLE jobs ADD COLUMN stage TEXT")
            if "status_message" not in job_columns:
                connection.execute("ALTER TABLE jobs ADD COLUMN status_message TEXT")
            connection.executescript("""
                CREATE TABLE IF NOT EXISTS workspaces (
                    id TEXT PRIMARY KEY,name TEXT NOT NULL,created_at TEXT NOT NULL,updated_at TEXT NOT NULL
                );
                CREATE TABLE IF NOT EXISTS media_blobs (
                    id TEXT PRIMARY KEY,sha256 TEXT NOT NULL UNIQUE,byte_size INTEGER NOT NULL,
                    mime_type TEXT,storage_project_id TEXT NOT NULL,storage_asset_id TEXT NOT NULL,
                    storage_kind TEXT NOT NULL,created_at TEXT NOT NULL
                );
                CREATE TABLE IF NOT EXISTS analysis_artifacts (
                    id TEXT PRIMARY KEY,project_id TEXT NOT NULL,source_revision INTEGER NOT NULL,
                    source_asset_id TEXT NOT NULL,source_sha256 TEXT NOT NULL,kind TEXT NOT NULL,
                    schema_version TEXT NOT NULL,provider_id TEXT NOT NULL,provider_version TEXT NOT NULL,
                    settings_hash TEXT NOT NULL,body_json TEXT NOT NULL,created_at TEXT NOT NULL,
                    UNIQUE(source_sha256,kind,schema_version,provider_id,provider_version,settings_hash)
                );
                CREATE TABLE IF NOT EXISTS timeline_crop_keyframes (
                    project_id TEXT NOT NULL,revision INTEGER NOT NULL,item_id TEXT NOT NULL,
                    ordinal INTEGER NOT NULL,time_ticks INTEGER NOT NULL,center_x REAL NOT NULL,
                    center_y REAL NOT NULL,zoom REAL NOT NULL,confidence REAL,locked INTEGER NOT NULL,
                    PRIMARY KEY(project_id,revision,item_id,ordinal)
                );
                CREATE TABLE IF NOT EXISTS timeline_caption_words (
                    project_id TEXT NOT NULL,revision INTEGER NOT NULL,item_id TEXT NOT NULL,
                    ordinal INTEGER NOT NULL,word_id TEXT NOT NULL,text TEXT NOT NULL,
                    start_ticks INTEGER NOT NULL,end_ticks INTEGER NOT NULL,confidence REAL,
                    PRIMARY KEY(project_id,revision,item_id,ordinal)
                );
                CREATE TABLE IF NOT EXISTS timeline_caption_styles (
                    project_id TEXT NOT NULL,revision INTEGER NOT NULL,item_id TEXT NOT NULL,
                    preset TEXT NOT NULL,font_family TEXT NOT NULL,font_size INTEGER NOT NULL,
                    text_color TEXT NOT NULL,highlight_color TEXT NOT NULL,background_color TEXT NOT NULL,
                    position TEXT NOT NULL,words_per_cue INTEGER NOT NULL,
                    PRIMARY KEY(project_id,revision,item_id)
                );
                CREATE INDEX IF NOT EXISTS idx_projects_workspace ON projects(workspace_id,updated_at DESC);
                CREATE INDEX IF NOT EXISTS idx_suggestions_project_state ON suggestions(project_id,state,created_at DESC);
                CREATE INDEX IF NOT EXISTS idx_analysis_cache ON analysis_artifacts(source_sha256,kind,settings_hash);
            """)
            now = utc_now()
            connection.execute("UPDATE projects SET workspace_id=id WHERE workspace_id IS NULL")
            connection.execute(
                "INSERT OR IGNORE INTO workspaces(id,name,created_at,updated_at) SELECT id,name,?,? FROM projects",
                (now, now),
            )
            for row in connection.execute(
                "SELECT project_id,id,sha256,byte_size,mime_type,source_kind FROM assets WHERE sha256 IS NOT NULL AND byte_size IS NOT NULL"
            ).fetchall():
                blob_id = f"blob_{str(row['sha256'])[:24]}"
                connection.execute(
                    """INSERT OR IGNORE INTO media_blobs(
                         id,sha256,byte_size,mime_type,storage_project_id,storage_asset_id,storage_kind,created_at
                       ) VALUES (?,?,?,?,?,?,?,?)""",
                    (blob_id,row["sha256"],row["byte_size"],row["mime_type"],row["project_id"],row["id"],row["source_kind"],now),
                )
                connection.execute("UPDATE assets SET blob_id=? WHERE project_id=? AND id=?", (blob_id,row["project_id"],row["id"]))
                connection.execute("UPDATE asset_versions SET blob_id=? WHERE project_id=? AND asset_id=?", (blob_id,row["project_id"],row["id"]))
            connection.execute(
                "INSERT OR REPLACE INTO metadata(key,value) VALUES ('persistence_schema_version',?)",
                (str(SCHEMA_VERSION),),
            )
            connection.execute(
                "INSERT INTO schema_migrations(version,name,applied_at) VALUES (4,?,?)",
                ("shorts_workspaces_blobs_and_analysis", utc_now()),
            )
            connection.execute("PRAGMA user_version=4")
        applied.add(4)
    if 5 not in applied:
        with connection:
            connection.executescript("""
                CREATE TABLE IF NOT EXISTS timeline_crop_keyframes (
                    project_id TEXT NOT NULL,revision INTEGER NOT NULL,item_id TEXT NOT NULL,
                    ordinal INTEGER NOT NULL,time_ticks INTEGER NOT NULL,center_x REAL NOT NULL,
                    center_y REAL NOT NULL,zoom REAL NOT NULL,confidence REAL,locked INTEGER NOT NULL,
                    PRIMARY KEY(project_id,revision,item_id,ordinal)
                );
                CREATE TABLE IF NOT EXISTS timeline_caption_words (
                    project_id TEXT NOT NULL,revision INTEGER NOT NULL,item_id TEXT NOT NULL,
                    ordinal INTEGER NOT NULL,word_id TEXT NOT NULL,text TEXT NOT NULL,
                    start_ticks INTEGER NOT NULL,end_ticks INTEGER NOT NULL,confidence REAL,
                    PRIMARY KEY(project_id,revision,item_id,ordinal)
                );
                CREATE TABLE IF NOT EXISTS timeline_caption_styles (
                    project_id TEXT NOT NULL,revision INTEGER NOT NULL,item_id TEXT NOT NULL,
                    preset TEXT NOT NULL,font_family TEXT NOT NULL,font_size INTEGER NOT NULL,
                    text_color TEXT NOT NULL,highlight_color TEXT NOT NULL,background_color TEXT NOT NULL,
                    position TEXT NOT NULL,words_per_cue INTEGER NOT NULL,
                    PRIMARY KEY(project_id,revision,item_id)
                );
            """)
            for row in connection.execute("SELECT * FROM timeline_item_versions").fetchall():
                for ordinal, entry in enumerate(json.loads(row["crop_keyframes_json"] or "[]")):
                    connection.execute(
                        """INSERT OR IGNORE INTO timeline_crop_keyframes(
                             project_id,revision,item_id,ordinal,time_ticks,center_x,center_y,zoom,confidence,locked
                           ) VALUES (?,?,?,?,?,?,?,?,?,?)""",
                        (row["project_id"],row["revision"],row["item_id"],ordinal,entry["time_ticks"],
                         entry.get("center_x",.5),entry.get("center_y",.5),entry.get("zoom",1),
                         entry.get("confidence"),int(entry.get("locked",False))),
                    )
                for ordinal, entry in enumerate(json.loads(row["caption_words_json"] or "[]")):
                    connection.execute(
                        """INSERT OR IGNORE INTO timeline_caption_words(
                             project_id,revision,item_id,ordinal,word_id,text,start_ticks,end_ticks,confidence
                           ) VALUES (?,?,?,?,?,?,?,?,?)""",
                        (row["project_id"],row["revision"],row["item_id"],ordinal,entry["id"],entry["text"],
                         entry["start_ticks"],entry["end_ticks"],entry.get("confidence")),
                    )
                style = json.loads(row["caption_style_json"]) if row["caption_style_json"] else None
                if style:
                    connection.execute(
                        """INSERT OR IGNORE INTO timeline_caption_styles(
                             project_id,revision,item_id,preset,font_family,font_size,text_color,highlight_color,
                             background_color,position,words_per_cue
                           ) VALUES (?,?,?,?,?,?,?,?,?,?,?)""",
                        (row["project_id"],row["revision"],row["item_id"],style["preset"],style["font_family"],
                         style["font_size"],style["text_color"],style["highlight_color"],style["background_color"],
                         style["position"],style["words_per_cue"]),
                    )
            connection.execute(
                "INSERT OR REPLACE INTO metadata(key,value) VALUES ('persistence_schema_version',?)",
                (str(SCHEMA_VERSION),),
            )
            connection.execute(
                "INSERT INTO schema_migrations(version,name,applied_at) VALUES (5,?,?)",
                ("normalized_caption_and_crop_children",utc_now()),
            )
            connection.execute("PRAGMA user_version=5")
    connection.execute("PRAGMA foreign_keys=ON")
    violations = connection.execute("PRAGMA foreign_key_check").fetchall()
    if violations:
        raise sqlite3.IntegrityError(f"foreign key violations after migration: {len(violations)}")
