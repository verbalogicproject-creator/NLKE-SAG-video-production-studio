"""Evidence-bound composites that place authentic UI inside generated motion plates.

The compositor itself is deliberately adapter-neutral.  This module records and
validates its observable result so generated pixels can never masquerade as UI
evidence in SAG.
"""
from __future__ import annotations

from fractions import Fraction
from typing import Any, Literal
from uuid import uuid4

from pydantic import BaseModel, Field, model_validator

from .models import TICKS_PER_SECOND, Project, utc_now
from .screenshots import ScreenshotCapture


PROTECTED_COMPOSITE_SCHEMA_VERSION = "sag-protected-screen-composite/1.0"


class PixelCrop(BaseModel):
    x: int = Field(ge=0)
    y: int = Field(ge=0)
    width: int = Field(gt=0, le=8192)
    height: int = Field(gt=0, le=8192)


class ProtectedScreenCompositeRequest(BaseModel):
    plate_asset_id: str = Field(min_length=1, max_length=160)
    source_capture_id: str = Field(min_length=1, max_length=160)
    composite_asset_id: str = Field(min_length=1, max_length=160)
    tracking_report_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    source_crop: PixelCrop
    tracking_method: Literal["sift_ransac_homography", "orb_ransac_homography"]
    frame_count: int = Field(gt=0, le=1_000_000)
    direct_tracked_frames: int = Field(ge=0)
    interpolated_frames: int = Field(ge=0)
    direct_tracking_ratio: float = Field(ge=0, le=1)
    min_inlier_count: int = Field(ge=0)
    min_inlier_ratio: float = Field(ge=0, le=1)
    min_opaque_coverage_pixels: int = Field(gt=0)
    max_untracked_gap_frames: int = Field(ge=0)

    @model_validator(mode="after")
    def consistent_tracking_counts(self) -> "ProtectedScreenCompositeRequest":
        if self.direct_tracked_frames + self.interpolated_frames != self.frame_count:
            raise ValueError("direct and interpolated frame counts must equal frame_count")
        observed_ratio = self.direct_tracked_frames / self.frame_count
        if abs(observed_ratio - self.direct_tracking_ratio) > .001:
            raise ValueError("direct_tracking_ratio does not match the frame counts")
        return self


class ProtectedScreenComposite(ProtectedScreenCompositeRequest):
    schema_version: Literal["sag-protected-screen-composite/1.0"] = PROTECTED_COMPOSITE_SCHEMA_VERSION
    id: str
    project_id: str
    plate_asset_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    source_asset_id: str
    source_asset_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    composite_asset_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    source_recipe_id: str
    source_recipe_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    source_commit: str
    application_revision: str
    approval_state: Literal["pending", "approved", "rejected"] = "pending"
    approved_project_revision: int | None = Field(default=None, ge=1)
    created_at: str = Field(default_factory=utc_now)


class ProtectedScreenCompositeDecisionRequest(BaseModel):
    decision: Literal["approved", "rejected"]
    actor: str = Field(min_length=1, max_length=120)
    note: str | None = Field(default=None, max_length=2000)


class ProtectedScreenCompositeService:
    MIN_DIRECT_TRACKING_RATIO = .90
    MAX_UNTRACKED_GAP_FRAMES = 12

    def __init__(self, store: Any):
        self.store = store

    @staticmethod
    def _capture(store: Any, capture_id: str) -> ScreenshotCapture:
        try:
            return ScreenshotCapture.model_validate(
                store.get_editorial_record(capture_id, kind="screenshot_capture")
            )
        except KeyError as error:
            raise ValueError("source screenshot capture was not found") from error

    @staticmethod
    def _active_ids(project: Project) -> set[str]:
        return {
            item.protected_screen_composite_id
            for track in project.tracks for item in track.items
            if item.protected_screen_composite_id
        }

    @staticmethod
    def _integrity(record: ProtectedScreenComposite, project: Project, capture: ScreenshotCapture) -> bool:
        try:
            source = project.asset(record.source_asset_id)
            plate = project.asset(record.plate_asset_id)
            composite = project.asset(record.composite_asset_id)
        except KeyError:
            return False
        return bool(
            capture.project_id == project.id
            and capture.approval_state == "approved"
            and capture.asset_id == source.id
            and capture.asset_sha256 == record.source_asset_sha256 == source.sha256
            and capture.recipe_sha256 == record.source_recipe_sha256
            and plate.sha256 == record.plate_asset_sha256
            and composite.sha256 == record.composite_asset_sha256
            and source.intake_status == plate.intake_status == composite.intake_status == "observed_valid"
        )

    def create(self, project_id: str, request: ProtectedScreenCompositeRequest) -> ProtectedScreenComposite:
        project = self.store.get_project(project_id)
        capture = self._capture(self.store, request.source_capture_id)
        if capture.project_id != project_id or capture.approval_state != "approved":
            raise ValueError("protected composites require an approved project screenshot")
        try:
            source = project.asset(capture.asset_id)
            plate = project.asset(request.plate_asset_id)
            composite = project.asset(request.composite_asset_id)
        except KeyError as error:
            raise ValueError("composite source, plate, or output asset was not found") from error
        for asset, label in ((source, "source"), (plate, "plate"), (composite, "composite")):
            if asset.intake_status != "observed_valid" or not asset.managed_uri or not asset.sha256:
                raise ValueError(f"{label} must be observed-valid managed media")
        if source.kind != "image" or plate.kind != "video" or composite.kind != "video":
            raise ValueError("protected composites require an image source and video plate/output")
        if composite.audio_codec:
            raise ValueError("protected composite outputs must be audio-free; narration and music use owned tracks")
        if request.direct_tracking_ratio < self.MIN_DIRECT_TRACKING_RATIO:
            raise ValueError("direct tracking coverage is below the protected-composite threshold")
        if request.max_untracked_gap_frames > self.MAX_UNTRACKED_GAP_FRAMES:
            raise ValueError("untracked frame gap exceeds the protected-composite threshold")
        if request.min_inlier_count < 8 or request.min_inlier_ratio < .20:
            raise ValueError("tracking evidence is too weak for a protected composite")
        if not source.width or not source.height:
            raise ValueError("source screenshot dimensions were not observed")
        crop = request.source_crop
        if crop.x + crop.width > source.width or crop.y + crop.height > source.height:
            raise ValueError("source_crop lies outside the observed screenshot")
        if not composite.duration_ticks or not composite.frame_rate:
            raise ValueError("composite duration and frame rate must be observed")
        try:
            expected_frames = composite.duration_ticks / TICKS_PER_SECOND * float(Fraction(composite.frame_rate))
        except (ValueError, ZeroDivisionError) as error:
            raise ValueError("composite frame rate is malformed") from error
        if abs(expected_frames - request.frame_count) > 1.1:
            raise ValueError("tracking frame_count does not match the observed composite duration")
        record = ProtectedScreenComposite(
            **request.model_dump(mode="json"), id=f"protected_composite_{uuid4().hex[:16]}",
            project_id=project_id, plate_asset_sha256=plate.sha256,
            source_asset_id=source.id, source_asset_sha256=source.sha256,
            composite_asset_sha256=composite.sha256, source_recipe_id=capture.recipe_id,
            source_recipe_sha256=capture.recipe_sha256, source_commit=capture.source_commit,
            application_revision=capture.application_revision,
        )
        saved = self.store.put_editorial_record(
            record_id=record.id, kind="protected_screen_composite",
            body=record.model_dump(mode="json"), expected_revision=0, project_id=project_id,
            workspace_id=project.workspace_id or project.id, append_only=True,
        )
        return ProtectedScreenComposite.model_validate(saved)

    def list(self, project_id: str) -> list[dict[str, Any]]:
        project = self.store.get_project(project_id)
        active_ids = self._active_ids(project)
        values = self.store.list_editorial_records(kind="protected_screen_composite", project_id=project_id)
        result: list[dict[str, Any]] = []
        for value in values:
            record = ProtectedScreenComposite.model_validate(value)
            try:
                capture = self._capture(self.store, record.source_capture_id)
                integrity = self._integrity(record, project, capture)
            except ValueError:
                integrity = False
            active = record.id in active_ids
            result.append({
                **record.model_dump(mode="json"),
                "stale": not integrity,
                "active": active,
                "insertion_ready": bool(
                    integrity and not active and record.approval_state == "approved"
                    and record.approved_project_revision == project.revision
                ),
            })
        return result

    def decide(
        self, project_id: str, composite_id: str,
        request: ProtectedScreenCompositeDecisionRequest,
    ) -> dict[str, Any]:
        project = self.store.get_project(project_id)
        try:
            raw = self.store.get_editorial_record(composite_id, kind="protected_screen_composite")
            record = ProtectedScreenComposite.model_validate(raw)
        except KeyError as error:
            raise ValueError("protected composite was not found") from error
        if record.project_id != project_id:
            raise ValueError("protected composite belongs to another project")
        if record.id in self._active_ids(project):
            raise ValueError("remove the protected composite from the timeline before changing its decision")
        capture = self._capture(self.store, record.source_capture_id)
        if request.decision == "approved" and not self._integrity(record, project, capture):
            raise ValueError("protected composite lineage is stale or invalid")
        decision = {
            "id": f"protected_composite_decision_{uuid4().hex[:16]}",
            "project_id": project_id, "composite_id": composite_id,
            "decision": request.decision, "actor": request.actor, "note": request.note,
            "project_revision": project.revision,
            "source_asset_sha256": record.source_asset_sha256,
            "plate_asset_sha256": record.plate_asset_sha256,
            "composite_asset_sha256": record.composite_asset_sha256,
            "tracking_report_sha256": record.tracking_report_sha256,
            "created_at": utc_now(),
        }
        self.store.put_editorial_record(
            record_id=decision["id"], kind="protected_screen_composite_decision", body=decision,
            expected_revision=0, project_id=project_id,
            workspace_id=project.workspace_id or project.id, append_only=True,
        )
        updated = record.model_copy(update={
            "approval_state": request.decision,
            "approved_project_revision": project.revision if request.decision == "approved" else None,
        })
        saved = self.store.put_editorial_record(
            record_id=record.id, kind="protected_screen_composite",
            body=updated.model_dump(mode="json"), expected_revision=int(raw["revision"]),
            project_id=project_id, workspace_id=project.workspace_id or project.id,
        )
        response = ProtectedScreenComposite.model_validate(saved).model_dump(mode="json")
        response.update({"stale": False, "active": False, "insertion_ready": request.decision == "approved"})
        return {"composite": response, "decision": decision}


def protected_composite_schemas() -> dict[str, Any]:
    return {
        model.__name__: model.model_json_schema()
        for model in (
            PixelCrop, ProtectedScreenCompositeRequest, ProtectedScreenComposite,
            ProtectedScreenCompositeDecisionRequest,
        )
    }
