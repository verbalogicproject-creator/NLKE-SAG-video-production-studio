from __future__ import annotations

import threading
from contextlib import contextmanager
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import Any
from uuid import uuid4


@dataclass(frozen=True)
class CanonicalJob:
    id: str
    workspace_id: str
    control_project_id: str | None
    kind: str
    state: str
    request_id: str
    entity_id: str
    input_version: str
    input_snapshot: dict[str, Any]
    attempt: int


class ControlJobs:
    """Narrow SQL boundary for Python workers; Prisma still owns this schema."""

    def __init__(self, database_url: str):
        try:
            import psycopg
            from psycopg.rows import dict_row
        except ImportError as error:  # pragma: no cover
            raise RuntimeError("canonical cloud jobs require psycopg") from error
        self.connection = psycopg.connect(database_url, row_factory=dict_row)
        self._lock = threading.RLock()

    def close(self) -> None:
        self.connection.close()

    @staticmethod
    def _record(row: dict[str, Any]) -> CanonicalJob:
        return CanonicalJob(
            id=str(row["id"]), workspace_id=str(row["workspaceId"]),
            control_project_id=str(row["projectId"]) if row["projectId"] else None,
            kind=str(row["kind"]), state=str(row["state"]), request_id=str(row["requestId"]),
            entity_id=str(row["canonicalEntityId"]), input_version=str(row["inputVersion"]),
            input_snapshot=dict(row["inputSnapshot"] or {}), attempt=int(row["attempt"]),
        )

    def claim(self, job_id: str, expected_kind: str) -> CanonicalJob | None:
        with self._lock, self.connection.transaction():
            row = self.connection.execute(
                """UPDATE control."CanonicalJob"
                   SET state='RUNNING', "heartbeatAt"=now(),
                       "leaseExpiresAt"=now() + interval '15 minutes', "updatedAt"=now()
                   WHERE id=%s AND state='CLAIMED'
                   RETURNING *""",
                (job_id,),
            ).fetchone()
            if row is None:
                return None
            job = self._record(row)
            if job.kind != expected_kind:
                raise RuntimeError(f"job kind mismatch: expected {expected_kind}, found {job.kind}")
            return job

    def heartbeat(self, job_id: str, *, progress: float | None = None, stage: str | None = None) -> bool:
        with self._lock, self.connection.transaction():
            row = self.connection.execute(
                """UPDATE control."CanonicalJob" SET
                     "heartbeatAt"=now(), "leaseExpiresAt"=now() + interval '15 minutes',
                     progress=GREATEST(progress,COALESCE(%s,progress)),
                     stage=COALESCE(%s,stage), "updatedAt"=now()
                   WHERE id=%s AND state IN ('RUNNING','AWAITING_OBSERVATION')
                   RETURNING "cancellationRequested"
                """,
                (progress, stage, job_id),
            ).fetchone()
            return bool(row and row["cancellationRequested"])

    def finish(self, job_id: str, state: str, *, result: dict[str, Any] | None = None,
               error_code: str | None = None, error_detail: str | None = None) -> None:
        from psycopg.types.json import Jsonb

        if state not in {"SUCCEEDED", "FAILED", "CANCELLED", "INTERRUPTED", "AWAITING_OBSERVATION"}:
            raise ValueError(state)
        with self._lock, self.connection.transaction():
            self.connection.execute(
                f"""UPDATE control."CanonicalJob" SET state='{state}', progress=%s,
                     "resultSnapshot"=COALESCE(%s,"resultSnapshot"), "errorCode"=%s,
                     "errorDetail"=%s, "leaseExpiresAt"=NULL, "updatedAt"=now()
                   WHERE id=%s AND state IN ('RUNNING','AWAITING_OBSERVATION')""",
                (1.0 if state in {"SUCCEEDED", "FAILED", "CANCELLED"} else .9,
                 Jsonb(result) if result is not None else None, error_code,
                 (error_detail or "")[:2000] or None, job_id),
            )

    def engine_project_id(self, control_project_id: str) -> str:
        row = self.connection.execute(
            "SELECT \"engineProjectId\" FROM control.\"Project\" WHERE id=%s", (control_project_id,)
        ).fetchone()
        if not row or not row["engineProjectId"]:
            raise RuntimeError("control project has no SAG project")
        return str(row["engineProjectId"])

    def complete_intake(self, asset_id: str, *, workspace_id: str, engine_asset_id: str, sha256: str,
                        duration_ms: int | None, storage_bytes: int, metadata: dict[str, Any]) -> None:
        from psycopg.types.json import Jsonb

        with self._lock, self.connection.transaction():
            workspace = self.connection.execute(
                "SELECT \"storageLimitBytes\" FROM control.\"Workspace\" WHERE id=%s FOR UPDATE",
                (workspace_id,),
            ).fetchone()
            used = self.connection.execute(
                "SELECT COALESCE(SUM(amount),0) AS value FROM control.\"QuotaLedger\" WHERE \"workspaceId\"=%s AND kind='STORAGE_BYTES'",
                (workspace_id,),
            ).fetchone()
            if not workspace or int(used["value"]) + storage_bytes > int(workspace["storageLimitBytes"]):
                raise RuntimeError("workspace storage quota would be exceeded by intake derivatives")
            self.connection.execute(
                """UPDATE control."Asset" SET "engineAssetId"=%s,sha256=%s,"durationMs"=%s,
                     "verifiedAt"=now(),metadata=COALESCE(metadata,'{}'::jsonb) || %s
                   WHERE id=%s""",
                (engine_asset_id, sha256, duration_ms, Jsonb(metadata), asset_id),
            )
            self.connection.execute(
                """UPDATE control."StorageObject" object SET sha256=%s
                   FROM control."Asset" asset
                   WHERE asset.id=%s AND asset."storageObjectId"=object.id""",
                (sha256, asset_id),
            )
            self.connection.execute(
                "UPDATE control.\"UploadSession\" SET status='PROMOTED',\"checksumSha256\"=%s,\"updatedAt\"=now() WHERE \"assetId\"=%s",
                (sha256, asset_id),
            )
            self.connection.execute(
                """INSERT INTO control."QuotaLedger"(
                     id,"workspaceId",kind,amount,"requestId","occurredAt",metadata)
                   VALUES (%s,%s,'STORAGE_BYTES',%s,%s,now(),%s)
                   ON CONFLICT("workspaceId",kind,"requestId") DO NOTHING""",
                (f"storage-intake-{asset_id}", workspace_id, storage_bytes,
                 f"storage:intake:{asset_id}", Jsonb({"assetId": asset_id, "includesDerivatives": True})),
            )

    def create_observation(self, render_job: CanonicalJob, artifact: Any) -> str:
        from psycopg.types.json import Jsonb

        observer_job_id = str(uuid4())
        now = datetime.now(timezone.utc)
        snapshot = {
            "workspaceId": render_job.workspace_id,
            "controlProjectId": render_job.control_project_id,
            "renderJobId": render_job.id,
            "chamberVariantId": render_job.entity_id,
            "artifactId": artifact.id,
            "artifactSha256": artifact.sha256,
        }
        with self._lock, self.connection.transaction():
            self.connection.execute(
                """INSERT INTO control."CanonicalJob"(
                     id,"workspaceId","projectId",kind,state,"requestId","canonicalEntityId",
                     attempt,"inputVersion","inputSnapshot",progress,"cancellationRequested",
                     "maxAttempts","createdAt","updatedAt")
                   VALUES (%s,%s,%s,'OBSERVE','DISPATCH_PENDING',%s,%s,0,'sag-observe-1',%s,0,false,3,%s,%s)""",
                (observer_job_id, render_job.workspace_id, render_job.control_project_id,
                 f"observe:{render_job.id}:{artifact.sha256}", artifact.id, Jsonb(snapshot), now, now),
            )
            self.connection.execute(
                """INSERT INTO queue."OutboxEvent"(
                     id,"jobId",state,attempt,"availableAt","createdAt")
                   VALUES (%s,%s,'PENDING',0,%s,%s)""",
                (str(uuid4()), observer_job_id, now, now),
            )
            self.connection.execute(
                """UPDATE control."CanonicalJob" SET state='AWAITING_OBSERVATION',progress=.9,
                     "resultSnapshot"=%s,"leaseExpiresAt"=NULL,"updatedAt"=now() WHERE id=%s""",
                (Jsonb({"artifactId": artifact.id, "observerJobId": observer_job_id}), render_job.id),
            )
            self.connection.execute(
                "UPDATE control.\"ChamberVariant\" SET status='VERIFYING',\"updatedAt\"=now() WHERE id=%s",
                (render_job.entity_id,),
            )
        return observer_job_id

    def set_render_receipt(self, variant_id: str, receipt_id: str) -> None:
        with self._lock, self.connection.transaction():
            self.connection.execute(
                "UPDATE control.\"ChamberVariant\" SET \"receiptId\"=%s,\"updatedAt\"=now() WHERE id=%s",
                (receipt_id, variant_id),
            )

    def complete_observation(self, job: CanonicalJob, artifact: Any, result: Any) -> tuple[bool, dict[str, Any]]:
        from psycopg.types.json import Jsonb

        render_job_id = str(job.input_snapshot["renderJobId"])
        variant_id = str(job.input_snapshot["chamberVariantId"])
        passed = bool(result.passed)
        evidence = result.model_dump(mode="json")
        provider = "GCS" if artifact.storage_backend == "gcs" else "LOCAL"
        storage_id = f"storage-{artifact.id}"
        with self._lock, self.connection.transaction():
            if passed:
                workspace = self.connection.execute(
                    "SELECT \"storageLimitBytes\" FROM control.\"Workspace\" WHERE id=%s FOR UPDATE",
                    (job.workspace_id,),
                ).fetchone()
                used = self.connection.execute(
                    "SELECT COALESCE(SUM(amount),0) AS value FROM control.\"QuotaLedger\" WHERE \"workspaceId\"=%s AND kind='STORAGE_BYTES'",
                    (job.workspace_id,),
                ).fetchone()
                if not workspace or int(used["value"]) + int(artifact.byte_size) > int(workspace["storageLimitBytes"]):
                    passed = False
                    evidence["passed"] = False
                    evidence.setdefault("findings", []).append({
                        "code": "workspace_storage_quota", "passed": False,
                        "summary": "Verified artifact would exceed the workspace storage quota",
                        "evidence": {"artifact_bytes": artifact.byte_size},
                    })
            self.connection.execute(
                """INSERT INTO control."ArtifactObservation"(
                     id,"jobId","artifactSha256",passed,evidence,"observedAt")
                   VALUES (%s,%s,%s,%s,%s,now())""",
                (str(uuid4()), job.id, artifact.sha256, passed, Jsonb(evidence)),
            )
            if passed:
                self.connection.execute(
                    """INSERT INTO control."StorageObject"(
                         id,provider,bucket,"objectKey",generation,sha256,"byteSize","createdAt")
                       VALUES (%s,CAST(%s AS control."StorageProvider"),%s,%s,%s,%s,%s,now()) ON CONFLICT(id) DO NOTHING""",
                    (storage_id, provider, artifact.storage_namespace if provider == "GCS" else None,
                     artifact.storage_key or artifact.id, artifact.storage_version,
                     artifact.sha256, artifact.byte_size),
                )
                self.connection.execute(
                    """INSERT INTO control."Asset"(
                         id,"projectId","storageObjectId",kind,"managedUri","mimeType","sizeBytes",
                         metadata,"engineAssetId",sha256,"verifiedAt","createdAt")
                       VALUES (%s,%s,%s,'DELIVERABLE',%s,%s,%s,%s,%s,%s,now(),now())
                       ON CONFLICT(id) DO UPDATE SET sha256=excluded.sha256,"verifiedAt"=now(),metadata=excluded.metadata""",
                    (artifact.id, job.control_project_id, storage_id, artifact.managed_uri,
                     artifact.mime_type, artifact.byte_size, Jsonb(artifact.provenance),
                     artifact.id, artifact.sha256),
                )
                self.connection.execute(
                    """INSERT INTO control."QuotaLedger"(
                         id,"workspaceId",kind,amount,"requestId","occurredAt",metadata)
                       VALUES (%s,%s,'STORAGE_BYTES',%s,%s,now(),%s)
                       ON CONFLICT("workspaceId",kind,"requestId") DO NOTHING""",
                    (f"storage-artifact-{artifact.id}", job.workspace_id, artifact.byte_size,
                     f"storage:artifact:{artifact.id}", Jsonb({"artifactId": artifact.id})),
                )
                self.connection.execute(
                    """UPDATE control."ChamberVariant" SET status='READY_TO_PUBLISH',
                         "deliverableAssetId"=%s,"updatedAt"=now() WHERE id=%s""",
                    (artifact.id, variant_id),
                )
                self.connection.execute(
                    """UPDATE control."CanonicalJob" SET state='SUCCEEDED',progress=1,
                         "updatedAt"=now() WHERE id=%s AND state='AWAITING_OBSERVATION'""",
                    (render_job_id,),
                )
            else:
                self.connection.execute(
                    "UPDATE control.\"ChamberVariant\" SET status='FAILED',\"warningDetails\"=%s,\"updatedAt\"=now() WHERE id=%s",
                    (Jsonb(evidence), variant_id),
                )
                self.connection.execute(
                    """UPDATE control."CanonicalJob" SET state='FAILED',progress=1,
                         "errorCode"='observation_failed',"errorDetail"='Independent artifact observation failed',
                         "updatedAt"=now() WHERE id=%s AND state='AWAITING_OBSERVATION'""",
                    (render_job_id,),
                )
        return passed, evidence


@contextmanager
def lease_heartbeat(control: ControlJobs, job_id: str, sag_store: Any = None):
    stop = threading.Event()

    def beat() -> None:
        while not stop.wait(45):
            if control.heartbeat(job_id) and sag_store is not None:
                try:
                    sag_store.request_job_cancellation(job_id)
                except KeyError:
                    pass

    thread = threading.Thread(target=beat, name=f"lease-{job_id}", daemon=True)
    thread.start()
    try:
        yield
    finally:
        stop.set()
        thread.join(timeout=2)
