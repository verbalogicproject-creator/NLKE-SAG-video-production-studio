from __future__ import annotations

import hashlib
import json
from datetime import datetime, timedelta, timezone
from typing import Any, Literal
from uuid import uuid4

from pydantic import BaseModel, Field

from .models import ReceiptStatus, StaleRevisionError, utc_now
from .runtime import RuntimeEventService, sanitize_payload


class DeliveryDestination(BaseModel):
    destination: Literal["youtube_shorts", "tiktok", "instagram_reels", "download"]
    visibility: Literal["private", "draft", "manual", "test"] = "private"
    title: str | None = Field(default=None, max_length=100)
    description: str | None = Field(default=None, max_length=5000)


class DeliveryProfileRequest(BaseModel):
    id: str | None = None
    destination: Literal["youtube_shorts", "tiktok", "instagram_reels", "download"]
    aspect_ratio: str = Field(pattern=r"^\d{1,3}:\d{1,3}$")
    width: int = Field(ge=16, le=16384)
    height: int = Field(ge=16, le=16384)
    caption_placement: str = Field(default="safe_bottom", min_length=1, max_length=64)
    safe_zone_x: int = Field(default=48, ge=0, le=4096)
    safe_zone_y: int = Field(default=96, ge=0, le=4096)
    metadata: dict[str, Any] = Field(default_factory=dict)


class ReleaseApprovalRequest(BaseModel):
    request_id: str = Field(min_length=8, max_length=120)
    project_revision: int = Field(ge=1)
    artifact_hashes: list[str] = Field(min_length=1, max_length=4)
    destinations: list[DeliveryDestination] = Field(min_length=1, max_length=4)
    approved_by: str = Field(min_length=1, max_length=120)
    expires_in_seconds: int = Field(default=600, ge=60, le=3600)


class ReleaseDispatchRequest(BaseModel):
    request_id: str = Field(min_length=8, max_length=120)


class DeliveryProfileImportRequest(DeliveryProfileRequest):
    id: str = Field(min_length=1, max_length=160)
    created_at: str | None = None
    updated_at: str | None = None


class ReleaseAttemptImportRequest(BaseModel):
    id: str = Field(min_length=1, max_length=160)
    destination: str = Field(min_length=1, max_length=64)
    idempotency_key: str = Field(min_length=8, max_length=160)
    state: Literal[
        "pending", "uploading", "processing", "awaiting_user_action",
        "verified_private", "published_test", "published", "failed", "ambiguous",
    ] = "pending"
    external_id: str | None = Field(default=None, max_length=256)
    bounded_error: str | None = Field(default=None, max_length=2000)
    attempt: int = Field(default=0, ge=0, le=1000)
    created_at: str | None = None
    updated_at: str | None = None


class ReleaseApprovalImportRequest(BaseModel):
    id: str = Field(min_length=1, max_length=160)
    project_revision: int = Field(ge=1)
    bundle_hash: str = Field(min_length=8, max_length=160)
    artifact_hashes: list[str] = Field(min_length=1, max_length=32)
    destinations: list[DeliveryDestination] = Field(min_length=1, max_length=16)
    state: Literal["active", "consumed", "revoked", "expired"] = "active"
    approved_by: str = Field(min_length=1, max_length=160)
    expires_at: str
    consumed_at: str | None = None
    created_at: str
    attempts: list[ReleaseAttemptImportRequest] = Field(default_factory=list, max_length=64)


class DeliveryImportRequest(BaseModel):
    profiles: list[DeliveryProfileImportRequest] = Field(default_factory=list, max_length=100)
    approvals: list[ReleaseApprovalImportRequest] = Field(default_factory=list, max_length=1000)


def delivery_schemas() -> dict[str, Any]:
    return {
        model.__name__: model.model_json_schema()
        for model in (
            DeliveryDestination,
            DeliveryProfileRequest,
            ReleaseApprovalRequest,
            ReleaseDispatchRequest,
        )
    }


class DeliveryService:
    def __init__(self, store: Any, runtime: RuntimeEventService):
        self.store = store
        self.runtime = runtime

    def state(self, project_id: str) -> dict[str, Any]:
        attempts = self.store.list_release_attempts(project_id)
        by_approval: dict[str, list[dict[str, Any]]] = {}
        for attempt in attempts:
            by_approval.setdefault(attempt["approval_id"], []).append(attempt)
        approvals = self.store.list_release_approvals(project_id)
        for approval in approvals:
            approval["attempts"] = by_approval.get(approval["id"], [])
        return {"delivery_profiles": self.store.list_delivery_profiles(project_id), "release_approvals": approvals}

    def put_profile(self, project_id: str, request: DeliveryProfileRequest) -> dict[str, Any]:
        self.store.get_project(project_id)
        return self.store.put_delivery_profile({
            **request.model_dump(mode="json"), "id": request.id or f"delivery_{uuid4().hex}",
            "project_id": project_id, "metadata": sanitize_payload(request.metadata),
        })

    def import_legacy(self, project_id: str, request: DeliveryImportRequest) -> dict[str, Any]:
        """Idempotently copy the former control-plane delivery records into the engine."""
        project = self.store.get_project(project_id)
        workspace_id = project.workspace_id or project.id
        imported_profiles: list[str] = []
        imported_approvals: list[str] = []
        imported_attempts: list[str] = []
        with self.store.transaction():
            for profile in request.profiles:
                row = profile.model_dump(mode="json", exclude_none=True)
                stored = self.store.put_delivery_profile({
                    **row, "project_id": project_id, "metadata": sanitize_payload(profile.metadata),
                })
                imported_profiles.append(stored["id"])
            for approval in request.approvals:
                approval_row = approval.model_dump(mode="json", exclude={"attempts"})
                approval_row["destinations"] = [
                    entry.model_dump(mode="json", exclude_none=True) for entry in approval.destinations
                ]
                stored_approval = self.store.put_release_approval({
                    **approval_row, "workspace_id": workspace_id, "project_id": project_id,
                })
                imported_approvals.append(stored_approval["id"])
                for attempt in approval.attempts:
                    stored_attempt = self.store.put_release_attempt({
                        **attempt.model_dump(mode="json", exclude_none=True),
                        "workspace_id": workspace_id, "project_id": project_id,
                        "approval_id": stored_approval["id"],
                    })
                    imported_attempts.append(stored_attempt["id"])
        return {
            "project_id": project_id,
            "profiles": sorted(set(imported_profiles)),
            "approvals": sorted(set(imported_approvals)),
            "attempts": sorted(set(imported_attempts)),
            "state": self.state(project_id),
        }

    def approve(self, project_id: str, request: ReleaseApprovalRequest) -> tuple[dict[str, Any], Any]:
        duplicate = self.store.receipt_for_request(project_id, request.request_id)
        if duplicate is not None:
            approval_id = duplicate.payload.get("approval_id")
            if duplicate.command != "release.approve" or not approval_id:
                raise ValueError("request id is already bound to another operation")
            return self.store.get_release_approval(project_id, str(approval_id)), duplicate
        project = self.store.get_project(project_id)
        if project.revision != request.project_revision:
            raise StaleRevisionError(request.project_revision, project.revision)
        artifact_hashes = sorted(set(request.artifact_hashes))
        observed_jobs = {
            job.id for job in self.store.list_jobs(project_id)
            if job.state == "observed_success" and job.result_artifact_id
        }
        observed_hashes = {
            artifact.sha256 for artifact in self.store.list_artifacts(project_id)
            if artifact.sha256 and artifact.job_id in observed_jobs
        }
        if len(artifact_hashes) != len(request.artifact_hashes) or any(value not in observed_hashes for value in artifact_hashes):
            raise ValueError("independently verified engine artifacts are required")
        destinations = sorted(
            (entry.model_dump(mode="json", exclude_none=True) for entry in request.destinations),
            key=lambda entry: entry["destination"],
        )
        if any(entry["destination"] == "instagram_reels" and entry["visibility"] not in {"manual", "test"} for entry in destinations):
            raise ValueError("instagram requires manual or explicitly confirmed test release until public promotion")
        canonical = {
            "project_id": project_id, "project_revision": project.revision,
            "artifact_hashes": artifact_hashes, "destinations": destinations,
        }
        bundle_hash = hashlib.sha256(json.dumps(canonical, sort_keys=True, separators=(",", ":")).encode()).hexdigest()
        workspace_id = project.workspace_id or project.id
        with self.store.transaction():
            approval = self.store.put_release_approval({
                "id": f"approval_{uuid4().hex}", "workspace_id": workspace_id, "project_id": project_id,
                "project_revision": project.revision, "bundle_hash": bundle_hash,
                "artifact_hashes": artifact_hashes, "destinations": destinations, "state": "active",
                "approved_by": request.approved_by,
                "expires_at": (datetime.now(timezone.utc) + timedelta(seconds=request.expires_in_seconds)).isoformat(),
                "created_at": utc_now(),
            })
            receipt = self.store.create_receipt(
                project_id=project_id, command="release.approve", status=ReceiptStatus.COMMITTED,
                request_id=request.request_id, actor=request.approved_by, project_revision=project.revision,
                payload={"approval_id": approval["id"], "bundle_hash": bundle_hash, "artifact_hashes": artifact_hashes},
            )
        self.runtime.emit(
            workspace_id=workspace_id, project_id=project_id, sequence_id=project_id,
            revision=project.revision, actor=request.approved_by, kind="release.transitioned",
            payload={"approval_id": approval["id"], "state": "active", "receipt_id": receipt.id},
        )
        return approval, receipt

    def dispatch(self, project_id: str, approval_id: str, request: ReleaseDispatchRequest, *, actor: str) -> tuple[dict[str, Any], list[dict[str, Any]], Any]:
        duplicate = self.store.receipt_for_request(project_id, request.request_id)
        if duplicate is not None:
            bound_approval = duplicate.payload.get("approval_id")
            if duplicate.command != "publish.dispatch_approved" or bound_approval != approval_id:
                raise ValueError("request id is already bound to another operation")
            approval = self.store.get_release_approval(project_id, approval_id)
            attempts = [
                entry for entry in self.store.list_release_attempts(project_id)
                if entry["approval_id"] == approval_id
            ]
            return approval, attempts, duplicate
        project = self.store.get_project(project_id)
        approval = self.store.get_release_approval(project_id, approval_id)
        if approval["state"] != "active" or datetime.fromisoformat(approval["expires_at"]) <= datetime.now(timezone.utc):
            raise ValueError("release approval is not active")
        if approval["project_revision"] != project.revision:
            raise StaleRevisionError(approval["project_revision"], project.revision)
        workspace_id = project.workspace_id or project.id
        with self.store.transaction():
            attempts = []
            for destination in approval["destinations"]:
                destination_id = destination["destination"]
                attempts.append(self.store.put_release_attempt({
                    "id": f"publication_{uuid4().hex}", "workspace_id": workspace_id,
                    "project_id": project_id, "approval_id": approval_id, "destination": destination_id,
                    "idempotency_key": hashlib.sha256(f"{approval['bundle_hash']}\0{destination_id}".encode()).hexdigest(),
                    "state": "pending", "bounded_error": "verified_download_fallback"
                    if destination_id == "download" or destination["visibility"] == "manual"
                    else "official_platform_adapter_requires_connected_account",
                }))
            approval = self.store.consume_release_approval(project_id, approval_id)
            receipt = self.store.create_receipt(
                project_id=project_id, command="publish.dispatch_approved", status=ReceiptStatus.COMMITTED,
                request_id=request.request_id, actor=actor, project_revision=project.revision,
                payload={"approval_id": approval_id, "attempt_ids": [entry["id"] for entry in attempts]},
            )
        self.runtime.emit(
            workspace_id=workspace_id, project_id=project_id, sequence_id=project_id,
            revision=project.revision, actor=actor, kind="publication.transitioned",
            payload={"approval_id": approval_id, "state": "dispatched", "attempt_ids": [entry["id"] for entry in attempts]},
        )
        return approval, attempts, receipt
