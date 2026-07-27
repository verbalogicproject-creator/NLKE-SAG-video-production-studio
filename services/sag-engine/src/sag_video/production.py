"""Engine-owned production-session contracts.

The production session is the durable cursor through the Studio workflow. It
does not replace the canonical project revision, receipts, or provider
operations. It only binds those authoritative records into one recoverable
production context.
"""
from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, Field

from .models import utc_now
from .repo_to_video import CreativeBrief, RepositoryEvidence, RepoStoryboard


PRODUCTION_SESSION_SCHEMA_VERSION = "sag-production-session/1.0"

ProductionStage = Literal["director", "scenes", "edit", "finish", "review", "deliver"]
StudioDepth = Literal["edit", "context", "system"]
WorkflowMode = Literal["repo_to_video", "source_to_shorts"]
IntakeStage = Literal[
    "evidence", "brief", "storyboard", "keyframes",
    "source", "analysis", "ranked_clips", "reframe",
]


class RepoVideoDraft(BaseModel):
    """Persistable Director form state before it is ready for dispatch.

    Operation endpoints still accept ``RepoVideoRequest`` and therefore retain
    strict repository URL validation. The Studio session must also be able to
    save an empty or partially typed form without turning navigation into a
    validation error.
    """

    repository_url: str = Field(default="", max_length=500)
    ref: str = Field(default="", max_length=120)
    audience: str = Field(default="developers evaluating this project", max_length=500)
    goal: str = Field(default="tutorial short that earns qualified repository traffic", max_length=500)
    creative_instructions: str = Field(default="", max_length=4000)
    visual_style: str = Field(default="clear, modern developer documentary", max_length=300)
    duration_seconds: int = Field(default=60, ge=15, le=180)
    target_platform: str = Field(default="youtube_shorts", max_length=120)
    brand_kit: str = Field(default="", max_length=2000)
    reference_assets: list[str] = Field(default_factory=list, max_length=20)


class ProductionSession(BaseModel):
    schema_version: Literal["sag-production-session/1.0"] = PRODUCTION_SESSION_SCHEMA_VERSION
    project_id: str
    revision: int = Field(default=1, ge=1)
    workflow_mode: WorkflowMode = "repo_to_video"
    current_stage: ProductionStage = "director"
    intake_stage: IntakeStage = "evidence"
    director_tab: Literal["direction", "brief", "prompts", "storyboard", "queue"] = "direction"
    active_depth: StudioDepth = "edit"
    focused_entity_id: str | None = Field(default=None, max_length=200)
    focused_candidate_id: str | None = Field(default=None, max_length=200)
    active_analysis_revision_id: str | None = Field(default=None, max_length=200)
    active_generation_revision_id: str | None = Field(default=None, max_length=200)
    active_variant_id: str | None = Field(default=None, max_length=200)
    review_context: dict[str, Any] = Field(default_factory=dict)
    director_input: RepoVideoDraft | None = None
    repository_evidence: RepositoryEvidence | None = None
    evidence_revision: str | None = Field(default=None, max_length=128)
    active_brief: CreativeBrief | None = None
    brief_versions: list[CreativeBrief] = Field(default_factory=list, max_length=40)
    brief_approved: bool = False
    active_storyboard: RepoStoryboard | None = None
    storyboard_proposal_receipt_id: str | None = Field(default=None, max_length=120)
    approved_storyboard_receipt_id: str | None = Field(default=None, max_length=120)
    active_prompt_revision_id: str | None = Field(default=None, max_length=160)
    prompt_revisions: list[dict[str, Any]] = Field(default_factory=list, max_length=100)
    generation_plan: dict[str, Any] | None = None
    generation_receipt_id: str | None = Field(default=None, max_length=120)
    scene_decisions: dict[str, dict[str, Any]] = Field(default_factory=dict)
    variants: dict[str, dict[str, Any]] = Field(default_factory=dict)
    operation_ids: list[str] = Field(default_factory=list, max_length=500)
    generation_operations: list[dict[str, Any]] = Field(default_factory=list, max_length=500)
    updated_at: str = Field(default_factory=utc_now)


class ProductionSessionUpdate(BaseModel):
    """Partial, optimistic update accepted by the production PUT route."""

    expected_revision: int = Field(ge=1)
    workflow_mode: WorkflowMode | None = None
    current_stage: ProductionStage | None = None
    intake_stage: IntakeStage | None = None
    director_tab: Literal["direction", "brief", "prompts", "storyboard", "queue"] | None = None
    active_depth: StudioDepth | None = None
    focused_entity_id: str | None = Field(default=None, max_length=200)
    focused_candidate_id: str | None = Field(default=None, max_length=200)
    active_analysis_revision_id: str | None = Field(default=None, max_length=200)
    active_generation_revision_id: str | None = Field(default=None, max_length=200)
    active_variant_id: str | None = Field(default=None, max_length=200)
    review_context: dict[str, Any] | None = None
    director_input: RepoVideoDraft | None = None
    repository_evidence: RepositoryEvidence | None = None
    evidence_revision: str | None = Field(default=None, max_length=128)
    active_brief: CreativeBrief | None = None
    brief_versions: list[CreativeBrief] | None = Field(default=None, max_length=40)
    brief_approved: bool | None = None
    active_storyboard: RepoStoryboard | None = None
    storyboard_proposal_receipt_id: str | None = Field(default=None, max_length=120)
    approved_storyboard_receipt_id: str | None = Field(default=None, max_length=120)
    active_prompt_revision_id: str | None = Field(default=None, max_length=160)
    prompt_revisions: list[dict[str, Any]] | None = Field(default=None, max_length=100)
    generation_plan: dict[str, Any] | None = None
    generation_receipt_id: str | None = Field(default=None, max_length=120)
    scene_decisions: dict[str, dict[str, Any]] | None = None
    variants: dict[str, dict[str, Any]] | None = None
    operation_ids: list[str] | None = Field(default=None, max_length=500)
    generation_operations: list[dict[str, Any]] | None = Field(default=None, max_length=500)

    def patch(self) -> dict[str, Any]:
        return self.model_dump(exclude={"expected_revision"}, exclude_unset=True)


def production_schemas() -> dict[str, dict[str, Any]]:
    return {
        "RepoVideoDraft": RepoVideoDraft.model_json_schema(),
        "ProductionSession": ProductionSession.model_json_schema(),
        "ProductionSessionUpdate": ProductionSessionUpdate.model_json_schema(),
    }
