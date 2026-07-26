from __future__ import annotations

import os
import threading
from pathlib import Path
from uuid import uuid4

import pytest

from sag_video.models import ReceiptStatus, utc_now
from sag_video.journal import JournalEntryRequest, SagJournalService
from sag_video.repository import ArtifactRecord, JobRecord, MediaBlobRecord
from sag_video.store import Store


def exercise_repository(store):
    project = store.create_project("Parity", "vertical_1080p", "workspace_parity")
    before = project.model_copy(deep=True)
    project.name = "Parity revision two"
    project.revision += 1
    project.updated_at = utc_now()
    with store.transaction():
        store.put_project(project)
        store.append_event(
            before=before, after=project, request_id="parity-revision-0001",
            actor="test", command="project.rename", arguments={"name": project.name},
        )
        receipt = store.create_receipt(
            project_id=project.id, command="project.rename", status=ReceiptStatus.OBSERVED_SUCCESS,
            request_id="parity-revision-0001", actor="test", project_revision=2,
        )
    assert store.get_project_revision(project.id, 1).name == "Parity"
    assert store.get_project(project.id).name == "Parity revision two"
    assert store.receipt_for_request(project.id, receipt.request_id).id == receipt.id

    job = store.create_job(JobRecord(
        id=f"job_{uuid4().hex}", project_id=project.id, project_revision=2,
        kind="render", state="queued", progress=0, frozen_spec={"revision": 2},
    ))
    claimed = store.claim_next_job("parity-worker", ["render"])
    assert claimed and claimed.id == job.id and claimed.state == "claimed"
    store.update_job(job.id, state="running", progress=.5)
    assert store.get_job(job.id).progress == .5
    artifact = store.create_artifact(ArtifactRecord(
        id=f"artifact_{uuid4().hex}", project_id=project.id, job_id=job.id,
        asset_id=None, kind="rendered_video", managed_uri="sag-artifact://parity",
        sha256="a" * 64, byte_size=12, mime_type="video/mp4", provenance={"revision": 2},
        storage_backend="filesystem", storage_namespace="/tmp", storage_key="parity", storage_version="1",
    ))
    assert store.get_artifact(artifact.id) == artifact
    blob = store.register_media_blob(MediaBlobRecord(
        id=f"blob_{uuid4().hex}", sha256="b" * 64, byte_size=3, mime_type="video/mp4",
        storage_project_id=project.id, storage_asset_id="asset_parity", storage_kind="upload",
        storage_backend="filesystem", storage_namespace="/tmp", storage_key="blob", storage_version="1",
    ))
    assert store.get_media_blob(blob.id) == blob
    journal = SagJournalService(store)
    namespace = f"sag://sag-video/project/{project.id}/project/{project.id}"
    entry, inserted = journal.append(namespace, JournalEntryRequest(
        id="parity-journal-entry-0001", kind="sag.receipt", content="parity receipt committed",
        created_at="2026-07-24T12:00:00+00:00", metadata={"revision": 2},
    ))
    assert inserted is True and entry.seq == 1
    assert journal.verify(namespace)["ok"] is True


def test_sqlite_repository_contract(tmp_path: Path):
    store = Store(tmp_path / "parity.db")
    try:
        exercise_repository(store)
    finally:
        store.close()


@pytest.mark.skipif(not os.getenv("SAG_TEST_POSTGRES_URL"), reason="SAG_TEST_POSTGRES_URL is not configured")
def test_postgres_repository_contract_and_atomic_claim():
    psycopg = pytest.importorskip("psycopg")
    from psycopg import sql
    from psycopg.conninfo import conninfo_to_dict, make_conninfo
    from sag_video.postgres_store import PostgreSQLStore

    base = conninfo_to_dict(os.environ["SAG_TEST_POSTGRES_URL"])
    database_name = f"sag_test_{uuid4().hex}"
    admin = psycopg.connect(make_conninfo(**{**base, "dbname": "postgres"}), autocommit=True)
    admin.execute(sql.SQL("CREATE DATABASE {}").format(sql.Identifier(database_name)))
    url = make_conninfo(**{**base, "dbname": database_name})
    first = PostgreSQLStore(url)
    second = PostgreSQLStore(url)
    try:
        exercise_repository(first)
        project = first.list_projects_for_workspace("workspace_parity")[0]
        contested = first.create_job(JobRecord(
            id=f"job_{uuid4().hex}", project_id=project.id, project_revision=2,
            kind="analysis", state="queued", progress=0, frozen_spec={},
        ))
        claims: list[str] = []

        def claim(store, worker):
            result = store.claim_next_job(worker, ["analysis"])
            if result:
                claims.append(result.id)

        threads = [threading.Thread(target=claim, args=(first, "one")), threading.Thread(target=claim, args=(second, "two"))]
        for thread in threads:
            thread.start()
        for thread in threads:
            thread.join()
        assert claims == [contested.id]

        namespace = f"sag://sag-video/project/{project.id}/project/{project.id}/concurrent"
        journal_first, journal_second = SagJournalService(first), SagJournalService(second)
        journal_results: list[bool] = []
        request = JournalEntryRequest(
            id="parity-concurrent-journal-0001", kind="sag.claim", content="worker claimed task",
            created_at="2026-07-24T12:01:00+00:00", metadata={"revision": 2},
        )

        def append(service):
            journal_results.append(service.append(namespace, request)[1])

        journal_threads = [threading.Thread(target=append, args=(journal_first,)), threading.Thread(target=append, args=(journal_second,))]
        for thread in journal_threads:
            thread.start()
        for thread in journal_threads:
            thread.join()
        assert sorted(journal_results) == [False, True]
        assert journal_first.verify(namespace)["checked"] == 1

        admin_connection = psycopg.connect(url, autocommit=True)
        admin_connection.execute('CREATE SCHEMA control')
        admin_connection.execute('CREATE TYPE control."CanonicalJobState" AS ENUM (\'CLAIMED\',\'RUNNING\',\'SUCCEEDED\',\'FAILED\',\'CANCELLED\',\'INTERRUPTED\',\'AWAITING_OBSERVATION\')')
        admin_connection.execute('CREATE TYPE control."CanonicalJobKind" AS ENUM (\'RENDER\')')
        admin_connection.execute('''CREATE TABLE control."CanonicalJob"(
          id TEXT PRIMARY KEY,"workspaceId" TEXT NOT NULL,"projectId" TEXT,
          kind control."CanonicalJobKind" NOT NULL,state control."CanonicalJobState" NOT NULL,
          "requestId" TEXT NOT NULL,"canonicalEntityId" TEXT NOT NULL,
          "inputVersion" TEXT NOT NULL,"inputSnapshot" JSONB NOT NULL,attempt INTEGER NOT NULL,
          "heartbeatAt" TIMESTAMPTZ,"leaseExpiresAt" TIMESTAMPTZ,"updatedAt" TIMESTAMPTZ NOT NULL,
          progress DOUBLE PRECISION NOT NULL,stage TEXT,"cancellationRequested" BOOLEAN NOT NULL,
          "resultSnapshot" JSONB,"errorCode" TEXT,"errorDetail" TEXT
        )''')
        admin_connection.execute('''INSERT INTO control."CanonicalJob"(
          id,"workspaceId",kind,state,"requestId","canonicalEntityId","inputVersion",
          "inputSnapshot",attempt,"updatedAt",progress,"cancellationRequested")
          VALUES ('canonical-1','workspace_parity','RENDER','CLAIMED','request-1','variant-1',
                  'sag-render-job-1','{}',1,now(),0,false)''')
        admin_connection.close()
        from sag_video.control_jobs import ControlJobs

        control = ControlJobs(url)
        try:
            canonical = control.claim("canonical-1", "RENDER")
            assert canonical and canonical.workspace_id == "workspace_parity"
            assert control.claim("canonical-1", "RENDER") is None
            assert control.heartbeat("canonical-1", progress=.5, stage="rendering") is False
            control.finish("canonical-1", "SUCCEEDED", result={"artifactId": "artifact-1"})
            state = control.connection.execute(
                'SELECT state,progress,"resultSnapshot" FROM control."CanonicalJob" WHERE id=%s',
                ("canonical-1",),
            ).fetchone()
            assert str(state["state"]) == "SUCCEEDED"
            assert state["progress"] == 1
            assert state["resultSnapshot"]["artifactId"] == "artifact-1"
        finally:
            control.close()
    finally:
        first.close()
        second.close()
        admin.execute(
            "SELECT pg_terminate_backend(pid) FROM pg_stat_activity WHERE datname=%s", (database_name,)
        )
        admin.execute(sql.SQL("DROP DATABASE {}").format(sql.Identifier(database_name)))
        admin.close()
