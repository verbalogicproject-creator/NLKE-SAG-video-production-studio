"""Immutable, evidence-bound screenshot capture contracts.

Navigation and pixel acquisition stay in user-authorized browser or Playwright
adapters.  The engine validates recipes, binds observed image assets to their
provenance, and keeps human review authoritative.
"""
from __future__ import annotations

import hashlib
import json
from typing import Any, Literal
from urllib.parse import urlparse
from uuid import uuid4

from pydantic import BaseModel, Field, field_validator, model_validator

from .models import utc_now
from .production_intelligence import NormalizedBox


SCREENSHOT_SCHEMA_VERSION = "sag-screenshot/1.0"
ScreenshotAdapter = Literal["android_screenshot", "browser_mediarecorder", "playwright"]
SEMANTIC_ACTIONS = {
    "open_project", "focus_entity", "set_depth", "select_tab",
    "wait_for_checkpoint", "capture",
}


class ScreenshotStep(BaseModel):
    action: Literal[
        "open_project", "focus_entity", "set_depth", "select_tab",
        "wait_for_checkpoint", "capture",
    ]
    target: str = Field(min_length=1, max_length=240)
    expected_text: str | None = Field(default=None, max_length=300)


class ScreenshotRecipeRequest(BaseModel):
    name: str = Field(min_length=1, max_length=160)
    allowed_origin: str = Field(min_length=1, max_length=500)
    viewport_width: int = Field(default=1080, ge=320, le=8192)
    viewport_height: int = Field(default=1920, ge=320, le=8192)
    device_scale_factor: float = Field(default=1, ge=.5, le=4)
    mode: Literal["viewport", "full_page", "element", "protected_region"] = "viewport"
    steps: list[ScreenshotStep] = Field(min_length=1, max_length=40)
    checkpoint_id: str = Field(min_length=1, max_length=160, pattern=r"^[A-Za-z0-9._:-]+$")
    expected_labels: list[str] = Field(default_factory=list, max_length=30)
    excluded_labels: list[str] = Field(default_factory=list, max_length=30)
    protected_regions: list[NormalizedBox] = Field(default_factory=list, max_length=12)
    evidence_claim_ids: list[str] = Field(default_factory=list, max_length=30)
    source_commit: str = Field(min_length=7, max_length=64, pattern=r"^[0-9a-fA-F]+$")
    application_revision: str = Field(min_length=1, max_length=160)

    @field_validator("allowed_origin")
    @classmethod
    def secure_bounded_origin(cls, value: str) -> str:
        parsed = urlparse(value)
        hostname = (parsed.hostname or "").lower()
        if parsed.path not in {"", "/"} or parsed.query or parsed.fragment or parsed.username or parsed.password:
            raise ValueError("allowed_origin must be an origin without credentials, path, query, or fragment")
        if parsed.scheme == "https" and hostname:
            return f"https://{parsed.netloc}"
        if parsed.scheme == "http" and hostname in {"localhost", "127.0.0.1", "::1"}:
            return f"http://{parsed.netloc}"
        raise ValueError("allowed_origin must use HTTPS, except for localhost development")

    @model_validator(mode="after")
    def ends_in_capture(self) -> "ScreenshotRecipeRequest":
        if self.steps[-1].action != "capture":
            raise ValueError("the final semantic step must be capture")
        if any(step.action not in SEMANTIC_ACTIONS for step in self.steps):
            raise ValueError("recipe contains a non-semantic action")
        return self


class ScreenshotRecipe(ScreenshotRecipeRequest):
    schema_version: Literal["sag-screenshot/1.0"] = SCREENSHOT_SCHEMA_VERSION
    id: str
    project_id: str
    revision: int = Field(default=1, ge=1)
    recipe_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    created_at: str = Field(default_factory=utc_now)


class ScreenshotCaptureRequest(BaseModel):
    recipe_id: str = Field(min_length=1, max_length=160)
    asset_id: str = Field(min_length=1, max_length=160)
    family_id: str | None = Field(default=None, max_length=160)
    adapter: ScreenshotAdapter
    checkpoint_id: str = Field(min_length=1, max_length=160)
    observed_labels: list[str] = Field(default_factory=list, max_length=50)
    sensitive_content_status: Literal["passed", "failed", "uncertain"]
    observation_report: dict[str, Any] = Field(default_factory=dict)
    captured_at: str = Field(default_factory=utc_now)


class ScreenshotCapture(BaseModel):
    schema_version: Literal["sag-screenshot/1.0"] = SCREENSHOT_SCHEMA_VERSION
    id: str
    project_id: str
    recipe_id: str
    recipe_sha256: str
    family_id: str
    asset_id: str
    asset_sha256: str
    adapter: ScreenshotAdapter
    checkpoint_id: str
    observed_labels: list[str] = Field(default_factory=list)
    sensitive_content_status: Literal["passed"] = "passed"
    observation_report: dict[str, Any] = Field(default_factory=dict)
    source_commit: str
    application_revision: str
    evidence_claim_ids: list[str] = Field(default_factory=list)
    approval_state: Literal["pending", "approved", "rejected"] = "pending"
    captured_at: str
    created_at: str = Field(default_factory=utc_now)


class ScreenshotDecisionRequest(BaseModel):
    decision: Literal["approved", "rejected"]
    actor: str = Field(min_length=1, max_length=120)
    note: str | None = Field(default=None, max_length=2000)


class VisualProofClaim(BaseModel):
    id: str = Field(min_length=1, max_length=160)
    claim: str = Field(min_length=1, max_length=500)
    capture_id: str = Field(min_length=1, max_length=160)
    narration: str = Field(default="", max_length=1000)
    duration_ticks: int = Field(gt=0)
    protected_regions: list[NormalizedBox] = Field(default_factory=list, max_length=12)


class VisualProofPlanRequest(BaseModel):
    source_commit: str = Field(min_length=7, max_length=64, pattern=r"^[0-9a-fA-F]+$")
    evidence_revision: str = Field(min_length=1, max_length=160)
    claims: list[VisualProofClaim] = Field(min_length=1, max_length=30)


class ScreenshotService:
    def __init__(self, store: Any):
        self.store = store

    @staticmethod
    def _hash(value: dict[str, Any]) -> str:
        return hashlib.sha256(json.dumps(value, sort_keys=True, separators=(",", ":")).encode()).hexdigest()

    def create_recipe(self, project_id: str, request: ScreenshotRecipeRequest) -> ScreenshotRecipe:
        project = self.store.get_project(project_id)
        body = request.model_dump(mode="json")
        recipe = ScreenshotRecipe(
            **body, id=f"screenshot_recipe_{uuid4().hex[:16]}", project_id=project_id,
            recipe_sha256=self._hash(body),
        )
        saved = self.store.put_editorial_record(
            record_id=recipe.id, kind="screenshot_recipe", body=recipe.model_dump(mode="json"),
            expected_revision=0, project_id=project_id, workspace_id=project.workspace_id or project.id,
            append_only=True,
        )
        return ScreenshotRecipe.model_validate(saved)

    def list_recipes(self, project_id: str) -> list[ScreenshotRecipe]:
        return [ScreenshotRecipe.model_validate(value) for value in self.store.list_editorial_records(kind="screenshot_recipe", project_id=project_id)]

    def create_capture(self, project_id: str, request: ScreenshotCaptureRequest) -> ScreenshotCapture:
        project = self.store.get_project(project_id)
        try:
            recipe = ScreenshotRecipe.model_validate(self.store.get_editorial_record(request.recipe_id, kind="screenshot_recipe"))
            asset = project.asset(request.asset_id)
        except KeyError as error:
            raise ValueError("screenshot recipe or asset was not found in this project") from error
        if recipe.project_id != project_id:
            raise ValueError("screenshot recipe belongs to another project")
        if asset.kind != "image" or asset.intake_status != "observed_valid" or not asset.sha256 or not asset.managed_uri:
            raise ValueError("screenshot capture requires an observed-valid managed image")
        if request.checkpoint_id != recipe.checkpoint_id:
            raise ValueError("capture checkpoint does not match the immutable recipe")
        if request.sensitive_content_status != "passed":
            raise ValueError("screenshot sensitive-content screening must pass before binding")
        missing = sorted(set(recipe.expected_labels) - set(request.observed_labels))
        excluded = sorted(set(recipe.excluded_labels) & set(request.observed_labels))
        if missing or excluded:
            raise ValueError("screenshot checkpoint labels do not satisfy the recipe")
        capture = ScreenshotCapture(
            id=f"screenshot_capture_{uuid4().hex[:16]}", project_id=project_id,
            recipe_id=recipe.id, recipe_sha256=recipe.recipe_sha256,
            family_id=request.family_id or f"screenshot_family_{uuid4().hex[:16]}",
            asset_id=asset.id, asset_sha256=asset.sha256, adapter=request.adapter,
            checkpoint_id=request.checkpoint_id, observed_labels=request.observed_labels,
            observation_report=request.observation_report, source_commit=recipe.source_commit,
            application_revision=recipe.application_revision,
            evidence_claim_ids=recipe.evidence_claim_ids, captured_at=request.captured_at,
        )
        saved = self.store.put_editorial_record(
            record_id=capture.id, kind="screenshot_capture", body=capture.model_dump(mode="json"),
            expected_revision=0, project_id=project_id, workspace_id=project.workspace_id or project.id,
            append_only=True,
        )
        return ScreenshotCapture.model_validate(saved)

    def list_captures(
        self, project_id: str, *, source_commit: str | None = None,
        application_revision: str | None = None,
    ) -> list[dict[str, Any]]:
        captures = [ScreenshotCapture.model_validate(value) for value in self.store.list_editorial_records(kind="screenshot_capture", project_id=project_id)]
        return [{
            **capture.model_dump(mode="json"),
            "stale": bool(
                (source_commit and capture.source_commit != source_commit)
                or (application_revision and capture.application_revision != application_revision)
            ),
        } for capture in captures]

    def decide(self, project_id: str, capture_id: str, request: ScreenshotDecisionRequest) -> dict[str, Any]:
        project = self.store.get_project(project_id)
        try:
            capture = ScreenshotCapture.model_validate(self.store.get_editorial_record(capture_id, kind="screenshot_capture"))
        except KeyError as error:
            raise ValueError("screenshot capture was not found") from error
        if capture.project_id != project_id:
            raise ValueError("screenshot capture belongs to another project")
        decision_id = f"screenshot_decision_{uuid4().hex[:16]}"
        decision = {
            "id": decision_id, "project_id": project_id, "capture_id": capture_id,
            "decision": request.decision, "actor": request.actor, "note": request.note,
            "asset_sha256": capture.asset_sha256, "recipe_sha256": capture.recipe_sha256,
            "created_at": utc_now(),
        }
        self.store.put_editorial_record(
            record_id=decision_id, kind="screenshot_decision", body=decision,
            expected_revision=0, project_id=project_id, workspace_id=project.workspace_id or project.id,
            append_only=True,
        )
        updated = capture.model_copy(update={"approval_state": request.decision})
        saved = self.store.put_editorial_record(
            record_id=capture.id, kind="screenshot_capture", body=updated.model_dump(mode="json"),
            expected_revision=int(self.store.get_editorial_record(capture.id)["revision"]),
            project_id=project_id, workspace_id=project.workspace_id or project.id,
        )
        return {"capture": ScreenshotCapture.model_validate(saved).model_dump(mode="json"), "decision": decision}

    def create_visual_proof_plan(self, project_id: str, request: VisualProofPlanRequest) -> dict[str, Any]:
        project = self.store.get_project(project_id)
        for claim in request.claims:
            try:
                capture = ScreenshotCapture.model_validate(self.store.get_editorial_record(claim.capture_id, kind="screenshot_capture"))
            except KeyError as error:
                raise ValueError(f"capture not found: {claim.capture_id}") from error
            if capture.project_id != project_id or capture.approval_state != "approved":
                raise ValueError("visual proof plans require approved project screenshots")
            if capture.source_commit != request.source_commit:
                raise ValueError("visual proof capture is stale for the requested source commit")
        body = {
            "schema_version": "sag-visual-proof-plan/1.0", "project_id": project_id,
            **request.model_dump(mode="json"), "created_at": utc_now(),
        }
        plan_id = f"visual_proof_plan_{uuid4().hex[:16]}"
        saved = self.store.put_editorial_record(
            record_id=plan_id, kind="visual_proof_plan", body=body, expected_revision=0,
            project_id=project_id, workspace_id=project.workspace_id or project.id, append_only=True,
        )
        return saved


def screenshot_schemas() -> dict[str, Any]:
    return {
        model.__name__: model.model_json_schema()
        for model in (
            ScreenshotRecipeRequest, ScreenshotRecipe, ScreenshotCaptureRequest,
            ScreenshotCapture, ScreenshotDecisionRequest, VisualProofPlanRequest,
        )
    }
