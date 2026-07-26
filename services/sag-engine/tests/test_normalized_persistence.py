from __future__ import annotations

import json
import sqlite3
from pathlib import Path

import pytest

from sag_video.models import Receipt, ReceiptStatus, utc_now
from sag_video.repository import (
    JobRecord,
    JobRepository,
    ModelRunRecord,
    ProjectRepository,
    ProviderRunRepository,
    ReceiptRepository,
)
from sag_video.store import Store, fixture_project


def _legacy_database(path: Path) -> tuple[object, object, Receipt]:
    before = fixture_project()
    after = before.model_copy(deep=True)
    after.revision = 2
    after.updated_at = utc_now()
    after.item("title_intro").x = 84
    receipt = Receipt(
        id="receipt_legacy",
        project_id="demo",
        command="timeline.set_title_transform",
        status=ReceiptStatus.OBSERVED_SUCCESS,
        request_id="legacy-request-0001",
        actor="legacy-test",
        project_revision=2,
        payload={
            "before_revision": 1,
            "after_revision": 2,
            "transitions": [
                {"status": "accepted", "at": before.updated_at},
                {"status": "observed_success", "at": after.updated_at},
            ],
            "observation": {
                "kind": "canonical_revision_readback",
                "independent_failure_domain": False,
                "passed": True,
                "findings": [
                    {
                        "code": "title_transform_readback",
                        "passed": True,
                        "summary": "The canonical title transform matched.",
                        "evidence": {"x": 84},
                    }
                ],
            },
        },
        created_at=before.updated_at,
        updated_at=after.updated_at,
    )
    connection = sqlite3.connect(path)
    connection.executescript(
        """
        CREATE TABLE projects(id TEXT PRIMARY KEY, body TEXT NOT NULL);
        CREATE TABLE receipts(
          id TEXT PRIMARY KEY, project_id TEXT NOT NULL, request_id TEXT NOT NULL,
          body TEXT NOT NULL, UNIQUE(project_id,request_id)
        );
        CREATE TABLE events(
          id INTEGER PRIMARY KEY AUTOINCREMENT, project_id TEXT NOT NULL,
          revision INTEGER NOT NULL, request_id TEXT NOT NULL, actor TEXT NOT NULL,
          command TEXT NOT NULL, arguments TEXT NOT NULL, before_body TEXT NOT NULL,
          after_body TEXT NOT NULL, created_at TEXT NOT NULL,
          UNIQUE(project_id,request_id)
        );
        CREATE TABLE selections(project_id TEXT PRIMARY KEY, body TEXT NOT NULL);
        CREATE TABLE pairings(
          code TEXT PRIMARY KEY, workspace_id TEXT NOT NULL, expires_at TEXT NOT NULL,
          consumed INTEGER NOT NULL DEFAULT 0
        );
        CREATE TABLE tokens(
          token TEXT PRIMARY KEY, workspace_id TEXT NOT NULL, actor_name TEXT NOT NULL,
          expires_at TEXT NOT NULL, revoked INTEGER NOT NULL DEFAULT 0
        );
        """
    )
    connection.execute("INSERT INTO projects(id,body) VALUES (?,?)", (after.id, after.model_dump_json()))
    connection.execute(
        """INSERT INTO events(
             project_id,revision,request_id,actor,command,arguments,before_body,
             after_body,created_at
           ) VALUES (?,?,?,?,?,?,?,?,?)""",
        (
            "demo", 2, "legacy-request-0001", "legacy-test",
            "timeline.set_title_transform", json.dumps({"item_id": "title_intro", "x": 84}),
            before.model_dump_json(), after.model_dump_json(), after.updated_at,
        ),
    )
    connection.execute(
        "INSERT INTO receipts(id,project_id,request_id,body) VALUES (?,?,?,?)",
        (receipt.id, receipt.project_id, receipt.request_id, receipt.model_dump_json()),
    )
    connection.execute("INSERT INTO selections(project_id,body) VALUES (?,?)", ("demo", '["title_intro"]'))
    connection.commit()
    connection.close()
    return before, after, receipt


def test_legacy_blob_store_migrates_without_losing_history(tmp_path: Path):
    database = tmp_path / "legacy.db"
    before, after, expected_receipt = _legacy_database(database)

    store = Store(database)
    assert store.get_project_revision("demo", 1).model_dump() == before.model_dump()
    assert store.get_project("demo").model_dump() == after.model_dump()
    assert store.get_selection("demo") == ["title_intro"]
    assert store.get_receipt(expected_receipt.id).model_dump() == expected_receipt.model_dump()
    store.close()

    connection = sqlite3.connect(database)
    tables = {row[0] for row in connection.execute("SELECT name FROM sqlite_master WHERE type='table'")}
    assert not {"legacy_projects", "legacy_events", "legacy_receipts", "legacy_selections"} & tables
    assert connection.execute("PRAGMA user_version").fetchone()[0] == 12
    assert connection.execute("PRAGMA integrity_check").fetchone()[0] == "ok"
    assert connection.execute("PRAGMA foreign_key_check").fetchall() == []
    connection.close()


def test_normalized_store_has_no_aggregate_project_or_event_blobs(tmp_path: Path):
    database = tmp_path / "normalized.db"
    store = Store(database)
    store.close()
    connection = sqlite3.connect(database)
    columns = {
        table: {row[1] for row in connection.execute(f"PRAGMA table_info({table})")}
        for table in ("projects", "project_revisions", "events", "receipts", "selections")
    }
    assert "body" not in columns["projects"]
    assert "before_body" not in columns["events"]
    assert "after_body" not in columns["events"]
    assert "body" not in columns["receipts"]
    assert "body" not in columns["selections"]
    assert [row[0] for row in connection.execute("SELECT version FROM schema_migrations ORDER BY version")] == [1, 2, 3, 4, 5, 6, 7, 8, 9, 10, 11, 12]
    connection.close()


def test_restart_preserves_head_and_exact_revision_asset_state(tmp_path: Path):
    database = tmp_path / "restart.db"
    store = Store(database)
    before = store.get_project("demo")
    after = before.model_copy(deep=True)
    after.revision = 2
    after.updated_at = utc_now()
    after.assets[0].name = "Changed only in revision two"
    with store.transaction():
        store.append_event(
            before=before,
            after=after,
            request_id="restart-request-0001",
            actor="test",
            command="asset.rename.test",
            arguments={"asset_id": after.assets[0].id},
        )
    store.close()

    reopened = Store(database)
    assert reopened.get_project("demo").assets[0].name == "Changed only in revision two"
    assert reopened.get_project_revision("demo", 1).assets[0].name == "Terminal capture"
    assert reopened.get_project_revision("demo", 2).revision == 2
    reopened.close()


def test_unit_of_work_rolls_back_nested_repository_writes(tmp_path: Path):
    store = Store(tmp_path / "rollback.db")
    with pytest.raises(RuntimeError):
        with store.transaction():
            store.create_receipt(
                project_id="demo", command="test.rollback", status=ReceiptStatus.ACCEPTED,
                request_id="rollback-request-0001", actor="test", project_revision=1,
            )
            raise RuntimeError("force rollback")
    assert store.receipt_for_request("demo", "rollback-request-0001") is None
    store.close()


def test_store_implements_repository_protocols_and_job_recovery(tmp_path: Path):
    store = Store(tmp_path / "protocols.db")
    assert isinstance(store, ProjectRepository)
    assert isinstance(store, ReceiptRepository)
    assert isinstance(store, JobRepository)
    assert isinstance(store, ProviderRunRepository)

    queued = store.create_job(
        JobRecord(
            id="job_render_1", project_id="demo", project_revision=1,
            kind="render", state="queued", progress=0, frozen_spec={"preset": "preview_540p"},
        )
    )
    assert queued.state == "queued"
    claimed = store.claim_next_job("phone-worker", ["render"])
    assert claimed and claimed.worker_id == "phone-worker" and claimed.state == "claimed"
    assert store.request_job_cancellation(claimed.id).cancellation_requested is True
    store.update_job(claimed.id, state="running", progress=0.25)
    recovered = store.recover_interrupted_jobs("phone-worker")
    assert [job.id for job in recovered] == [claimed.id]
    assert recovered[0].state == "interrupted"
    store.close()


def test_provider_runs_are_vendor_neutral_and_restart_safe(tmp_path: Path):
    database = tmp_path / "providers.db"
    store = Store(database)
    store.register_provider(
        "cloud-video-primary",
        provider_kind="video_generation",
        display_name="Configured cloud video adapter",
        adapter_version="1.0",
        capability_snapshot={"text_to_video": True, "max_seconds": 8},
        enabled=True,
    )
    created = store.create_model_run(
        ModelRunRecord(
            id="run_1", project_id="demo", provider_id="cloud-video-primary",
            model_id="configured-model", purpose="b_roll_candidate", state="submitted",
            capability_snapshot={"max_seconds": 8}, request_spec={"prompt": "A quiet terminal close-up"},
            response_summary={}, source_hashes=["a" * 64],
        )
    )
    assert created.external_operation_id is None
    store.update_model_run(
        "run_1", state="completed", external_operation_id="provider-operation-42",
        response_summary={"candidate_count": 1},
    )
    store.close()

    reopened = Store(database)
    run = reopened.get_model_run("run_1")
    assert run.state == "completed"
    assert run.external_operation_id == "provider-operation-42"
    assert run.response_summary == {"candidate_count": 1}
    schema = " ".join(
        str(row[0]) for row in reopened._connection.execute(
            "SELECT sql FROM sqlite_master WHERE sql IS NOT NULL ORDER BY name"
        )
    ).lower()
    assert "gemini" not in schema and "veo" not in schema
    reopened.close()
