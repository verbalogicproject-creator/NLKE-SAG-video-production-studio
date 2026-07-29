"""Canonical contracts for source-to-shorts editorial intelligence.

These records are descriptive and revisioned. The project timeline, commands,
receipts, and FFmpeg renderer remain the media authorities.
"""
from __future__ import annotations

import hashlib
import json
from typing import Any, Literal

from pydantic import BaseModel, Field, model_validator

from .models import TICKS_PER_SECOND, utc_now


SCORE_POLICY_VERSION = "sag-clip-quality/1.0"
ANALYSIS_REVISION_SCHEMA_VERSION = "sag-source-analysis/1.0"
SCORE_WEIGHTS: dict[str, float] = {
    "hook": .30,
    "flow": .25,
    "value": .20,
    "delivery": .10,
    "visual_evidence": .10,
    "boundary_quality": .05,
}

ContentProfile = Literal["talking_head", "multi_speaker", "screen_recording", "action_broll"]


class NormalizedBox(BaseModel):
    x: float = Field(ge=0, le=1)
    y: float = Field(ge=0, le=1)
    width: float = Field(gt=0, le=1)
    height: float = Field(gt=0, le=1)

    @model_validator(mode="after")
    def bounded(self) -> "NormalizedBox":
        if self.x + self.width > 1.000001 or self.y + self.height > 1.000001:
            raise ValueError("normalized box must remain inside the source frame")
        return self


class SpeakerTurn(BaseModel):
    speaker_id: str
    start_ticks: int = Field(ge=0)
    end_ticks: int = Field(gt=0)
    confidence: float | None = Field(default=None, ge=0, le=1)
    provider: dict[str, Any] = Field(default_factory=dict)


class SubjectObservation(BaseModel):
    time_ticks: int = Field(ge=0)
    box: NormalizedBox
    confidence: float = Field(ge=0, le=1)


class SubjectTrack(BaseModel):
    id: str
    kind: Literal["face", "speaker", "cursor", "motion", "manual_region"]
    observations: list[SubjectObservation] = Field(default_factory=list)
    confidence: float = Field(ge=0, le=1)
    provenance: dict[str, Any] = Field(default_factory=dict)


class CropPoint(BaseModel):
    time_ticks: int = Field(ge=0)
    center_x: float = Field(ge=0, le=1)
    center_y: float = Field(ge=0, le=1)
    zoom: float = Field(default=1, ge=.25, le=8)
    confidence: float = Field(default=0, ge=0, le=1)


class CropPlan(BaseModel):
    id: str
    aspect_ratio: Literal["9:16", "16:9", "1:1"]
    strategy: Literal["dominant_face", "speaker_switch", "stable_split", "saliency", "manual", "center_fallback"]
    points: list[CropPoint] = Field(min_length=1)
    confidence: float = Field(ge=0, le=1)
    provenance: dict[str, Any] = Field(default_factory=dict)
    warnings: list[str] = Field(default_factory=list)


class SourceAnalysisRevision(BaseModel):
    schema_version: Literal["sag-source-analysis/1.0"] = ANALYSIS_REVISION_SCHEMA_VERSION
    id: str
    project_id: str
    source_revision: int = Field(ge=1)
    source_asset_id: str
    source_asset_hash: str = Field(min_length=16)
    proxy_hash: str | None = None
    transcription_provider: str
    transcription_version: str
    analysis_profile: ContentProfile
    settings_hash: str = Field(min_length=16)
    transcript_artifact_id: str | None = None
    feature_artifact_id: str | None = None
    speaker_turns: list[SpeakerTurn] = Field(default_factory=list)
    subject_tracks: list[SubjectTrack] = Field(default_factory=list)
    crop_plans: list[CropPlan] = Field(default_factory=list)
    provider_identity: dict[str, Any] = Field(default_factory=dict)
    warnings: list[str] = Field(default_factory=list)
    created_at: str = Field(default_factory=utc_now)


class ScoreComponent(BaseModel):
    name: Literal["hook", "flow", "value", "delivery", "visual_evidence", "boundary_quality"]
    weight: float = Field(gt=0, le=1)
    score: float = Field(ge=0, le=100)
    weighted_score: float = Field(ge=0, le=100)
    evidence: list[str] = Field(default_factory=list)
    confidence: float = Field(ge=0, le=1)


class ClipQualityScore(BaseModel):
    schema_version: Literal["sag-clip-quality/1.0"] = SCORE_POLICY_VERSION
    total: float = Field(ge=0, le=100)
    components: list[ScoreComponent] = Field(min_length=6, max_length=6)
    confidence: float = Field(ge=0, le=1)
    warnings: list[str] = Field(default_factory=list)
    content_profile: ContentProfile
    provider_identity: dict[str, Any] = Field(default_factory=dict)
    score_policy_version: Literal["sag-clip-quality/1.0"] = SCORE_POLICY_VERSION
    calibration_revision: str | None = None


class ClipScoreRequest(BaseModel):
    source_revision: int = Field(ge=1)
    asset_id: str | None = None
    suggestion_id: str | None = None
    analysis_revision_id: str | None = None
    start_ticks: int | None = Field(default=None, ge=0)
    end_ticks: int | None = Field(default=None, gt=0)
    content_profile: ContentProfile = "talking_head"
    component_scores: dict[str, float] | None = None

    @model_validator(mode="after")
    def selected_range(self) -> "ClipScoreRequest":
        if self.suggestion_id is None and (self.start_ticks is None or self.end_ticks is None):
            raise ValueError("provide suggestion_id or a selected start_ticks/end_ticks range")
        if self.start_ticks is not None and self.end_ticks is not None and self.end_ticks <= self.start_ticks:
            raise ValueError("end_ticks must be greater than start_ticks")
        if self.component_scores:
            unknown = set(self.component_scores) - set(SCORE_WEIGHTS)
            if unknown:
                raise ValueError(f"unknown score components: {', '.join(sorted(unknown))}")
            if any(not 0 <= float(value) <= 100 for value in self.component_scores.values()):
                raise ValueError("component scores must be between 0 and 100")
        return self


class EditorialFeedback(BaseModel):
    id: str
    project_id: str
    suggestion_id: str
    decision: Literal["accepted", "rejected", "needs_revision"]
    reasons: list[Literal[
        "weak_hook", "poor_flow", "low_value", "delivery", "visuals",
        "bad_boundary", "duplicate", "off_brand", "other",
    ]] = Field(default_factory=list)
    note: str | None = Field(default=None, max_length=2000)
    actor: str = Field(default="browser", min_length=1, max_length=100)
    score_policy_version: str = SCORE_POLICY_VERSION
    created_at: str = Field(default_factory=utc_now)


class EditorialFeedbackRequest(BaseModel):
    decision: Literal["accepted", "rejected", "needs_revision"]
    reasons: list[str] = Field(default_factory=list, max_length=12)
    note: str | None = Field(default=None, max_length=2000)
    actor: str = Field(default="browser", min_length=1, max_length=100)


class CaptionTemplate(BaseModel):
    id: Literal["clean", "karaoke", "bold_pop", "glow_pulse", "typewriter_reveal"]
    renderer: Literal["ffmpeg_ass", "engine_overlay"] = "ffmpeg_ass"
    revision: int = Field(default=1, ge=1)
    settings: dict[str, Any] = Field(default_factory=dict)


class BrollCandidate(BaseModel):
    id: str
    project_id: str
    source_kind: Literal["workspace_media", "repository_capture", "generated", "stock"]
    asset_id: str | None = None
    uri: str | None = None
    description: str
    provenance: dict[str, Any]
    license_status: Literal["workspace_owned", "verified", "unknown", "restricted"]
    semantic_confidence: float = Field(ge=0, le=1)
    claim_association: list[str] = Field(default_factory=list)
    authentic_evidence: bool = False
    requires_human_approval: bool = True


class BrollSearchRequest(BaseModel):
    query: str = Field(min_length=1, max_length=500)
    claim_ids: list[str] = Field(default_factory=list, max_length=50)
    limit: int = Field(default=12, ge=1, le=50)


class BrollDecision(BaseModel):
    id: str
    project_id: str
    candidate_id: str
    decision: Literal["approved", "rejected"]
    actor: str
    note: str | None = None
    created_at: str = Field(default_factory=utc_now)


class BrollDecisionRequest(BaseModel):
    decision: Literal["approved", "rejected"]
    actor: str = Field(default="browser", min_length=1, max_length=100)
    note: str | None = Field(default=None, max_length=2000)


class BrandKitRevision(BaseModel):
    schema_version: Literal["sag-brand-kit/1.0"] = "sag-brand-kit/1.0"
    id: str
    workspace_id: str
    revision: int = Field(ge=1)
    colors: dict[str, str] = Field(default_factory=dict)
    typography: dict[str, Any] = Field(default_factory=dict)
    logos: list[dict[str, Any]] = Field(default_factory=list)
    caption_rules: dict[str, Any] = Field(default_factory=dict)
    lower_thirds: list[dict[str, Any]] = Field(default_factory=list)
    watermark: dict[str, Any] | None = None
    intro: dict[str, Any] | None = None
    cta_templates: list[dict[str, Any]] = Field(default_factory=list)
    end_card_templates: list[dict[str, Any]] = Field(default_factory=list)
    created_at: str = Field(default_factory=utc_now)


class BrandKitUpdate(BaseModel):
    expected_revision: int = Field(ge=0)
    colors: dict[str, str] = Field(default_factory=dict)
    typography: dict[str, Any] = Field(default_factory=dict)
    logos: list[dict[str, Any]] = Field(default_factory=list)
    caption_rules: dict[str, Any] = Field(default_factory=dict)
    lower_thirds: list[dict[str, Any]] = Field(default_factory=list)
    watermark: dict[str, Any] | None = None
    intro: dict[str, Any] | None = None
    cta_templates: list[dict[str, Any]] = Field(default_factory=list)
    end_card_templates: list[dict[str, Any]] = Field(default_factory=list)


class VariantDefinition(BaseModel):
    schema_version: Literal["sag-variant/1.0"] = "sag-variant/1.0"
    id: str
    project_id: str
    revision: int = Field(ge=1)
    master_revision: int = Field(ge=1)
    aspect_ratio: Literal["9:16", "16:9", "1:1"]
    crop_overrides: dict[str, Any] = Field(default_factory=dict)
    caption_overrides: dict[str, Any] = Field(default_factory=dict)
    timing_overrides: dict[str, Any] = Field(default_factory=dict)
    inclusion_overrides: dict[str, bool] = Field(default_factory=dict)
    title_overrides: dict[str, Any] = Field(default_factory=dict)
    audio_overrides: dict[str, Any] = Field(default_factory=dict)
    stale_overrides: list[str] = Field(default_factory=list)
    updated_at: str = Field(default_factory=utc_now)


class VariantUpdate(BaseModel):
    expected_revision: int = Field(ge=0)
    master_revision: int = Field(ge=1)
    aspect_ratio: Literal["9:16", "16:9", "1:1"]
    crop_overrides: dict[str, Any] = Field(default_factory=dict)
    caption_overrides: dict[str, Any] = Field(default_factory=dict)
    timing_overrides: dict[str, Any] = Field(default_factory=dict)
    inclusion_overrides: dict[str, bool] = Field(default_factory=dict)
    title_overrides: dict[str, Any] = Field(default_factory=dict)
    audio_overrides: dict[str, Any] = Field(default_factory=dict)


class ReviewDecision(BaseModel):
    id: str
    project_id: str
    project_revision: int = Field(ge=1)
    subject_kind: Literal["timeline", "scene", "candidate", "broll", "variant", "export"]
    subject_id: str
    decision: Literal["approved", "rejected", "changes_requested"]
    actor: str
    note: str | None = None
    created_at: str = Field(default_factory=utc_now)


class ReviewDecisionRequest(BaseModel):
    project_revision: int = Field(ge=1)
    subject_kind: Literal["timeline", "scene", "candidate", "broll", "variant", "export"]
    subject_id: str = Field(min_length=1, max_length=200)
    decision: Literal["approved", "rejected", "changes_requested"]
    actor: str = Field(default="browser", min_length=1, max_length=100)
    note: str | None = Field(default=None, max_length=2000)


class UsageReservation(BaseModel):
    id: str
    workspace_id: str
    project_id: str
    category: Literal["provider_call", "tokens", "generated_seconds", "render_seconds", "storage_bytes"]
    reserved_quantity: float = Field(ge=0)
    unit: str
    state: Literal["reserved", "settled", "released"] = "reserved"
    estimated_cost: float | Literal["unknown"] = "unknown"
    currency: str | None = None
    created_at: str = Field(default_factory=utc_now)


class UsageEvent(BaseModel):
    id: str
    reservation_id: str | None = None
    workspace_id: str
    project_id: str
    category: Literal["provider_call", "tokens", "generated_seconds", "render_seconds", "storage_bytes"]
    quantity: float = Field(ge=0)
    unit: str
    cost: float | Literal["unknown"] = "unknown"
    currency: str | None = None
    provider: dict[str, Any] = Field(default_factory=dict)
    created_at: str = Field(default_factory=utc_now)


class QCCheck(BaseModel):
    code: Literal[
        "dimensions", "duration", "frame_rate", "representative_decode", "scene_coverage",
        "caption_readability", "caption_timing", "safe_areas", "audio_presence",
        "integrated_loudness", "true_peak", "narration_spectral_activity", "sha256",
        "protected_composite_lineage",
    ]
    passed: bool
    observed: Any = None
    expected: Any = None
    detail: str = ""


class QCReport(BaseModel):
    schema_version: Literal["sag-qc-report/1.0"] = "sag-qc-report/1.0"
    id: str
    project_id: str
    project_revision: int = Field(ge=1)
    artifact_id: str
    passed: bool
    checks: list[QCCheck]
    artifact_sha256: str = Field(min_length=16)
    created_at: str = Field(default_factory=utc_now)


class ExportRequest(BaseModel):
    project_revision: int = Field(ge=1)
    variant_id: str | None = Field(default=None, max_length=200)
    request_id: str = Field(min_length=8, max_length=120)
    actor: str = Field(default="browser", min_length=1, max_length=100)


class ExportBundle(BaseModel):
    schema_version: Literal["sag-export-bundle/1.0"] = "sag-export-bundle/1.0"
    id: str
    project_id: str
    project_revision: int = Field(ge=1)
    variant_id: str | None = None
    render_receipt_id: str
    state: Literal["accepted", "rendering", "verified", "failed"] = "accepted"
    artifact_ids: list[str] = Field(default_factory=list)
    qc_report_id: str | None = None
    bundle_sha256: str | None = None
    created_at: str = Field(default_factory=utc_now)


def stable_settings_hash(payload: dict[str, Any]) -> str:
    return hashlib.sha256(json.dumps(payload, sort_keys=True, separators=(",", ":")).encode()).hexdigest()


def infer_content_profile(features: dict[str, Any]) -> ContentProfile:
    if float(features.get("two_person_ratio", 0)) >= .35:
        return "multi_speaker"
    if features.get("cursor_tracks"):
        return "screen_recording"
    if len(features.get("scene_ticks") or []) >= 8:
        return "action_broll"
    return "talking_head"


def build_clip_quality_score(
    raw_components: dict[str, float], *, content_profile: ContentProfile,
    evidence: dict[str, list[str]] | None = None, confidence: float = .75,
    warnings: list[str] | None = None, provider_identity: dict[str, Any] | None = None,
) -> ClipQualityScore:
    aliases = {"visual": "visual_evidence", "boundary": "boundary_quality"}
    normalized = {aliases.get(key, key): float(value) for key, value in raw_components.items()}
    components: list[ScoreComponent] = []
    for name, weight in SCORE_WEIGHTS.items():
        score = max(0, min(100, normalized.get(name, 50)))
        components.append(ScoreComponent(
            name=name, weight=weight, score=round(score, 2), weighted_score=round(score * weight, 2),
            evidence=(evidence or {}).get(name, []), confidence=confidence,
        ))
    return ClipQualityScore(
        total=round(sum(component.weighted_score for component in components), 2), components=components,
        confidence=confidence, warnings=warnings or [], content_profile=content_profile,
        provider_identity=provider_identity or {"id": "sag_deterministic", "version": "1"},
    )


def deterministic_range_score(
    *, text: str, start_ticks: int, end_ticks: int, features: dict[str, Any],
    content_profile: ContentProfile, explicit: dict[str, float] | None = None,
) -> ClipQualityScore:
    lowered = text.casefold()
    hook_terms = ("how", "why", "secret", "mistake", "never", "imagine", "איך", "למה", "סוד", "טעות")
    value_terms = ("because", "therefore", "step", "result", "learn", "example", "בגלל", "לכן", "שלב", "תוצאה")
    duration_seconds = max(1, (end_ticks - start_ticks) / TICKS_PER_SECOND)
    words = text.split()
    scene_count = sum(start_ticks <= int(tick) <= end_ticks for tick in features.get("scene_ticks", []))
    face_points = [point for point in features.get("face_tracks", []) if start_ticks <= int(point.get("time_ticks", -1)) <= end_ticks]
    raw = {
        "hook": min(100, 52 + 12 * sum(term in lowered[:160] for term in hook_terms)),
        "flow": min(100, 58 + min(24, len(words) / duration_seconds * 8) + (10 if text.rstrip().endswith((".", "!", "?", "׃")) else 0)),
        "value": min(100, 52 + 9 * sum(term in lowered for term in value_terms)),
        "delivery": min(100, 58 + min(28, len(words) / duration_seconds * 9)),
        "visual_evidence": min(100, 48 + min(30, scene_count * 4) + (12 if face_points else 0)),
        "boundary_quality": 88 if text.rstrip().endswith((".", "!", "?", "׃")) else 62,
    }
    if explicit:
        raw.update(explicit)
    warnings: list[str] = []
    if not text.strip():
        warnings.append("No word-timed transcript overlapped the selected range; neutral language scores were used")
    if not face_points and content_profile in {"talking_head", "multi_speaker"}:
        warnings.append("No reliable face tracking evidence was available; use centered or manual framing")
    evidence = {
        "hook": [f"Opening text inspected across {min(len(text), 160)} characters"],
        "flow": [f"{len(words)} transcript words across {duration_seconds:.1f} seconds"],
        "value": ["Transcript checked for explanation, steps, examples, and outcomes"],
        "delivery": ["Speech density derived from word timestamps"],
        "visual_evidence": [f"{scene_count} shot boundaries and {len(face_points)} face observations in range"],
        "boundary_quality": ["Range ending checked against sentence punctuation and word timing"],
    }
    evidence_confidence = .82 if text and features else .55 if text else .3
    return build_clip_quality_score(
        raw, content_profile=content_profile, evidence=evidence, confidence=evidence_confidence,
        warnings=warnings,
    )


def production_intelligence_schemas() -> dict[str, dict[str, Any]]:
    types = [
        SourceAnalysisRevision, ClipQualityScore, ScoreComponent, EditorialFeedback,
        SpeakerTurn, SubjectTrack, CropPlan, CaptionTemplate, BrollCandidate, BrollDecision,
        BrandKitRevision, UsageReservation, UsageEvent, QCReport, VariantDefinition, ReviewDecision,
        ExportBundle,
    ]
    return {model.__name__: model.model_json_schema() for model in types}
