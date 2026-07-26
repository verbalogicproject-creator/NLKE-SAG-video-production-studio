from __future__ import annotations

from collections.abc import Iterator
from contextlib import AbstractContextManager
from dataclasses import dataclass
from typing import Any, Protocol, runtime_checkable

from .models import Project, Receipt, ReceiptStatus


@dataclass(frozen=True)
class JobRecord:
    id: str
    project_id: str
    project_revision: int
    kind: str
    state: str
    progress: float
    frozen_spec: dict[str, Any]
    worker_id: str | None = None
    result_artifact_id: str | None = None
    error_code: str | None = None
    error_detail: str | None = None
    cancellation_requested: bool = False
    stage: str | None = None
    status_message: str | None = None


@dataclass(frozen=True)
class ModelRunRecord:
    id: str
    project_id: str
    provider_id: str
    model_id: str
    purpose: str
    state: str
    capability_snapshot: dict[str, Any]
    request_spec: dict[str, Any]
    response_summary: dict[str, Any]
    source_hashes: list[str]
    external_operation_id: str | None = None


@dataclass(frozen=True)
class ArtifactRecord:
    id: str
    project_id: str
    job_id: str | None
    asset_id: str | None
    kind: str
    managed_uri: str
    sha256: str
    byte_size: int
    mime_type: str | None
    provenance: dict[str, Any]
    storage_backend: str | None = None
    storage_namespace: str | None = None
    storage_key: str | None = None
    storage_version: str | None = None


@dataclass(frozen=True)
class MediaBlobRecord:
    id: str
    sha256: str
    byte_size: int
    mime_type: str | None
    storage_project_id: str
    storage_asset_id: str
    storage_kind: str
    storage_backend: str | None = None
    storage_namespace: str | None = None
    storage_key: str | None = None
    storage_version: str | None = None


@dataclass(frozen=True)
class AnalysisArtifactRecord:
    id: str
    project_id: str
    source_revision: int
    source_asset_id: str
    source_sha256: str
    kind: str
    schema_version: str
    provider_id: str
    provider_version: str
    settings_hash: str
    body: dict[str, Any]


@dataclass(frozen=True)
class SuggestionRecord:
    id: str
    project_id: str
    source_revision: int
    generator_kind: str
    state: str
    commands: list[dict[str, Any]]
    reason: str
    evidence: dict[str, Any]
    confidence: float | None
    job_id: str | None = None


@runtime_checkable
class ProjectRepository(Protocol):
    def get_project(self, project_id: str) -> Project: ...
    def get_project_for_update(self, project_id: str) -> Project: ...
    def get_project_revision(self, project_id: str, revision: int) -> Project: ...
    def list_projects(self) -> list[Project]: ...
    def create_project(self, name: str, preset: str, workspace_id: str | None = None) -> Project: ...
    def list_projects_for_workspace(self, workspace_id: str) -> list[Project]: ...
    def project_in_workspace(self, project_id: str, workspace_id: str) -> bool: ...
    def put_project(self, project: Project) -> None: ...
    def get_selection(self, project_id: str) -> list[str]: ...
    def set_selection(self, project_id: str, item_ids: list[str]) -> None: ...
    def append_event(
        self,
        *,
        before: Project,
        after: Project,
        request_id: str,
        actor: str,
        command: str,
        arguments: dict[str, Any],
    ) -> None: ...


@runtime_checkable
class ReceiptRepository(Protocol):
    def receipt_for_request(self, project_id: str, request_id: str) -> Receipt | None: ...
    def get_receipt(self, receipt_id: str) -> Receipt: ...
    def list_receipts(self, project_id: str, limit: int = 50) -> list[Receipt]: ...
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
    ) -> Receipt: ...
    def update_receipt(
        self,
        receipt: Receipt,
        status: ReceiptStatus,
        payload_patch: dict[str, Any] | None = None,
    ) -> Receipt: ...


@runtime_checkable
class JobRepository(Protocol):
    def create_job(self, record: JobRecord) -> JobRecord: ...
    def get_job(self, job_id: str) -> JobRecord: ...
    def claim_next_job(self, worker_id: str, accepted_kinds: list[str]) -> JobRecord | None: ...
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
    ) -> JobRecord: ...
    def request_job_cancellation(self, job_id: str) -> JobRecord: ...
    def recover_interrupted_jobs(self, worker_id: str | None = None) -> list[JobRecord]: ...
    def create_artifact(self, record: ArtifactRecord) -> ArtifactRecord: ...
    def get_artifact(self, artifact_id: str) -> ArtifactRecord: ...


@runtime_checkable
class ShortsRepository(Protocol):
    def register_media_blob(self, record: MediaBlobRecord) -> MediaBlobRecord: ...
    def get_media_blob(self, blob_id: str) -> MediaBlobRecord: ...
    def put_analysis_artifact(self, record: AnalysisArtifactRecord) -> AnalysisArtifactRecord: ...
    def find_analysis_artifact(
        self, *, source_sha256: str, kind: str, schema_version: str,
        provider_id: str, provider_version: str, settings_hash: str,
    ) -> AnalysisArtifactRecord | None: ...
    def create_suggestion(self, record: SuggestionRecord) -> SuggestionRecord: ...
    def get_suggestion(self, suggestion_id: str) -> SuggestionRecord: ...
    def list_suggestions(self, project_id: str, *, state: str | None = None) -> list[SuggestionRecord]: ...
    def update_suggestion_state(self, suggestion_id: str, expected_state: str, state: str) -> SuggestionRecord: ...


@runtime_checkable
class ProviderRunRepository(Protocol):
    def register_provider(
        self,
        provider_id: str,
        *,
        provider_kind: str,
        display_name: str,
        adapter_version: str,
        capability_snapshot: dict[str, Any],
        enabled: bool,
    ) -> None: ...
    def create_model_run(self, record: ModelRunRecord) -> ModelRunRecord: ...
    def get_model_run(self, run_id: str) -> ModelRunRecord: ...
    def update_model_run(
        self,
        run_id: str,
        *,
        state: str,
        external_operation_id: str | None = None,
        response_summary: dict[str, Any] | None = None,
    ) -> ModelRunRecord: ...


class RepositoryUnitOfWork(Protocol):
    projects: ProjectRepository
    receipts: ReceiptRepository
    jobs: JobRepository
    providers: ProviderRunRepository
    shorts: ShortsRepository

    def transaction(self) -> AbstractContextManager[Any]: ...
