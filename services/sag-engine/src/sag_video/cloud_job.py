from __future__ import annotations

import os
import tempfile
from pathlib import Path

from .blob_storage import GcsBlobStorage, StorageLocator, StoredBlob, sha256_file
from .control_jobs import CanonicalJob, ControlJobs, lease_heartbeat
from .media import MediaService
from .models import ObservationContract, ReceiptStatus, ShortsGenerateRequest, TICKS_PER_SECOND
from .observer import observe_artifact
from .rendering import RenderService
from .repository import JobRecord
from .repository_factory import create_repository
from .shorts import ShortsService, providers_from_env


def required(name: str) -> str:
    value = os.getenv(name, "").strip()
    if not value:
        raise RuntimeError(f"{name} is required")
    return value


class CloudJobRunner:
    def __init__(self):
        self.database_url = required("DATABASE_URL")
        self.job_id = required("SAG_CANONICAL_JOB_ID")
        self.kind = required("SAG_JOB_KIND").upper()
        self.work = Path(tempfile.mkdtemp(prefix=f"sag-{self.kind.lower()}-"))
        self.control = ControlJobs(self.database_url)
        self.store = create_repository(
            backend="postgres", database_path="", database_url=self.database_url,
        )
        self.blobs = GcsBlobStorage(required("SAG_VIDEO_GCS_BUCKET"), self.work / "cache")
        self.media = MediaService(
            self.store, self.work / "media", self.work / "proxies",
            upload_limit_bytes=int(os.getenv("SAG_VIDEO_UPLOAD_LIMIT_BYTES", str(512 * 1024 * 1024))),
            blob_storage=self.blobs,
        )
        self.renderer = RenderService(
            self.store, self.work / "artifacts", self.media.path_for_asset,
            observer=observe_artifact, timeout_seconds=int(os.getenv("SAG_VIDEO_RENDER_TIMEOUT_SECONDS", "3300")),
            blob_storage=self.blobs,
        )

    def close(self) -> None:
        self.store.close()
        self.control.close()

    def run(self) -> None:
        job = self.control.claim(self.job_id, self.kind)
        if job is None:
            return
        try:
            with lease_heartbeat(self.control, job.id, self.store):
                getattr(self, f"run_{self.kind.lower()}")(job)
        except Exception as error:
            self.control.finish(job.id, "FAILED", error_code=f"{self.kind.lower()}_failed", error_detail=str(error))
            raise

    def run_intake(self, job: CanonicalJob) -> None:
        from google.cloud import storage

        snapshot = job.input_snapshot
        object_ = dict(snapshot["object"])
        if object_.get("bucket") != required("SAG_VIDEO_GCS_BUCKET"):
            raise RuntimeError("intake object belongs to another bucket")
        prefix = f"workspaces/{job.workspace_id}/projects/{snapshot['controlProjectId']}/uploads/"
        if not str(object_["key"]).startswith(prefix):
            raise RuntimeError("intake object escaped its workspace/project prefix")
        source = self.work / "intake-upload"
        blob = storage.Client().bucket(str(object_["bucket"])).blob(
            str(object_["key"]), generation=int(object_["generation"]),
        )
        blob.download_to_filename(str(source), if_generation_match=int(object_["generation"]), checksum="crc32c")
        if source.stat().st_size != int(snapshot["expectedSizeBytes"]):
            raise RuntimeError("intake size differs from frozen upload contract")
        engine_project_id = self.control.engine_project_id(str(snapshot["controlProjectId"]))
        with source.open("rb") as stream:
            digest = sha256_file(source)
            promoted_source = StoredBlob(
                StorageLocator("gcs", str(object_["bucket"]), str(object_["key"]), str(object_["generation"])),
                digest, source.stat().st_size, str(snapshot["expectedMimeType"]),
            )
            result = self.media.import_file(
                engine_project_id, stream, str(snapshot["originalFilename"]),
                str(snapshot["expectedMimeType"]), job.request_id, "cloud-intake",
                asset_id_override=str(snapshot["assetId"]),
                source_storage_override=promoted_source,
            )
        if not result.asset or result.receipt.status != ReceiptStatus.OBSERVED_SUCCESS:
            raise RuntimeError("media intake did not produce an observed-valid asset")
        asset = result.asset
        project = self.store.get_project(engine_project_id)
        derivative_bytes = sum(
            int(item.byte_size or 0) for item in project.assets
            if item.id in {asset.proxy_asset_id, asset.thumbnail_asset_id}
        )
        self.control.complete_intake(
            str(snapshot["assetId"]), workspace_id=job.workspace_id,
            engine_asset_id=asset.id, sha256=asset.sha256 or "",
            duration_ms=round((asset.duration_ticks or 0) * 1000 / TICKS_PER_SECOND),
            storage_bytes=int(asset.byte_size or 0) + derivative_bytes,
            metadata={"intakeStatus": "observed_valid", "observation": asset.observation_summary},
        )
        self.control.finish(job.id, "SUCCEEDED", result={"engineAssetId": asset.id, "sha256": asset.sha256})

    def run_analysis(self, job: CanonicalJob) -> None:
        snapshot = job.input_snapshot
        request = ShortsGenerateRequest.model_validate({
            "source_revision": snapshot["sourceRevision"], "asset_id": snapshot["sourceAssetId"],
            "prompt": snapshot.get("prompt"), "language": snapshot.get("language", "auto"),
            "candidate_count": snapshot.get("candidateCount", 3),
            "min_duration_ticks": 15 * TICKS_PER_SECOND, "max_duration_ticks": 90 * TICKS_PER_SECOND,
            "aspect_ratio": "9:16", "target_variants": snapshot.get("variants", []),
            "brand_contract": snapshot.get("brandContract", {}),
        })
        frozen = request.model_dump(mode="json")
        frozen.update({"source_asset_id": snapshot["sourceAssetId"], "source_sha256": snapshot["sourceSha256"]})
        record = JobRecord(
            id=job.id, project_id=str(snapshot["engineProjectId"]),
            project_revision=int(snapshot["sourceRevision"]), kind="shorts.generate",
            state="claimed", progress=0, frozen_spec=frozen, worker_id=f"cloud-analysis-{job.attempt}",
        )
        try:
            self.store.create_job(record)
        except Exception:
            existing = self.store.get_job(job.id)
            if existing.state == "observed_success":
                self.control.finish(job.id, "SUCCEEDED", result={"sagJobId": job.id})
                return
            self.store.update_job(job.id, state="claimed", progress=existing.progress)
        transcriber, ranker = providers_from_env()
        ShortsService(self.store, self.media.path_for_asset, transcriber, ranker).run_job(self.store.get_job(job.id))
        completed = self.store.get_job(job.id)
        if completed.state != "observed_success":
            raise RuntimeError(completed.error_detail or f"analysis ended in {completed.state}")
        suggestions = self.store.list_suggestions(record.project_id)
        self.control.finish(job.id, "SUCCEEDED", result={"sagJobId": job.id, "suggestionIds": [entry.id for entry in suggestions if entry.job_id == job.id]})

    def run_render(self, job: CanonicalJob) -> None:
        snapshot = job.input_snapshot
        project_id = str(snapshot["engineProjectId"])
        revision = int(snapshot["projectRevision"])
        project = self.store.get_project_revision(project_id, revision)
        spec = self.renderer.build_spec(project)
        receipt = self.store.receipt_for_request(project_id, str(snapshot["requestId"]))
        if receipt is None:
            receipt = self.store.create_receipt(
                project_id=project_id, command="render.verified", status=ReceiptStatus.ACCEPTED,
                request_id=str(snapshot["requestId"]), actor="cloud-render", project_revision=revision,
                payload={"project_revision": revision, "job_id": job.id},
            )
        self.control.set_render_receipt(job.entity_id, receipt.id)
        try:
            self.store.create_job(JobRecord(
                id=job.id, project_id=project_id, project_revision=revision, kind="render",
                state="claimed", progress=0, worker_id=f"cloud-render-{job.attempt}",
                frozen_spec={"receipt_id": receipt.id, "render_spec": spec.model_dump(mode="json")},
            ))
        except Exception:
            existing = self.store.get_job(job.id)
            if existing.state == "observed_success":
                self.control.finish(job.id, "SUCCEEDED", result={"artifactId": existing.result_artifact_id})
                return
            if existing.state == "awaiting_observation" and existing.result_artifact_id:
                self.control.create_observation(job, self.store.get_artifact(existing.result_artifact_id))
                return
            self.store.update_job(job.id, state="claimed", progress=existing.progress)
        artifact = self.renderer.execute(self.store.get_job(job.id), defer_observation=True)
        if artifact is None:
            raise RuntimeError("renderer produced no artifact")
        self.control.create_observation(job, artifact)

    def run_observe(self, job: CanonicalJob) -> None:
        artifact = self.store.get_artifact(str(job.input_snapshot["artifactId"]))
        path = self.renderer.path_for_artifact(artifact)
        contract = ObservationContract.model_validate({
            **dict(artifact.provenance["observation_contract"]),
            "artifact_path": str(path), "artifact_sha256": artifact.sha256,
        })
        result = observe_artifact(contract)
        passed, evidence = self.control.complete_observation(job, artifact, result)
        render_job = self.store.get_job(str(job.input_snapshot["renderJobId"]))
        receipt = self.store.get_receipt(str(render_job.frozen_spec["receipt_id"]))
        terminal = ReceiptStatus.OBSERVED_SUCCESS if passed else ReceiptStatus.OBSERVED_FAILURE
        self.store.update_receipt(receipt, terminal, {"observation": evidence, "observer_deployment": "cloud_run_job"})
        self.store.update_job(
            render_job.id, state=terminal.value, progress=1, result_artifact_id=artifact.id,
            error_code=None if result.passed else "observation_failed",
        )
        self.control.finish(job.id, "SUCCEEDED" if passed else "FAILED", result={"artifactId": artifact.id, "passed": passed})


def main() -> None:
    runner = CloudJobRunner()
    try:
        runner.run()
    finally:
        runner.close()


if __name__ == "__main__":
    main()
