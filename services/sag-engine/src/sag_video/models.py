from __future__ import annotations

from datetime import datetime, timezone
from enum import StrEnum
from typing import Any, Literal

from pydantic import BaseModel, Field, field_validator

from .chamber import BrandContract, PlatformVariant


TICKS_PER_SECOND = 120_000
APPLICATION_SCHEMA_VERSION = 2


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


class Canvas(BaseModel):
    width: int = Field(default=960, ge=320, le=3840)
    height: int = Field(default=540, ge=180, le=2160)
    fps_numerator: int = Field(default=30, ge=1, le=240)
    fps_denominator: int = Field(default=1, ge=1, le=1001)


class Asset(BaseModel):
    id: str
    kind: Literal["video", "audio", "image", "terminal_capture", "caption", "generated"]
    name: str
    uri: str | None = None
    source_kind: Literal[
        "upload",
        "android_picker",
        "termux_microphone",
        "asciinema",
        "playwright",
        "android_companion",
        "generated",
        "derived",
    ] = "generated"
    managed_uri: str | None = None
    original_filename: str | None = None
    sha256: str | None = None
    blob_id: str | None = None
    byte_size: int | None = Field(default=None, ge=0)
    mime_type: str | None = None
    duration_ticks: int | None = Field(default=None, ge=0)
    width: int | None = Field(default=None, gt=0)
    height: int | None = Field(default=None, gt=0)
    frame_rate: str | None = None
    video_codec: str | None = None
    rotation: int | None = None
    audio_codec: str | None = None
    audio_channels: int | None = Field(default=None, gt=0)
    audio_sample_rate: int | None = Field(default=None, gt=0)
    proxy_asset_id: str | None = None
    thumbnail_asset_id: str | None = None
    parent_asset_id: str | None = None
    intake_status: Literal["pending", "observed_valid", "observed_invalid"] = "pending"
    observation_summary: dict[str, Any] = Field(default_factory=dict)


class CropKeyframe(BaseModel):
    time_ticks: int = Field(ge=0)
    center_x: float = Field(default=.5, ge=0, le=1)
    center_y: float = Field(default=.5, ge=0, le=1)
    zoom: float = Field(default=1, ge=1, le=4)
    confidence: float | None = Field(default=None, ge=0, le=1)
    locked: bool = False


class CaptionWord(BaseModel):
    id: str
    text: str
    start_ticks: int = Field(ge=0)
    end_ticks: int = Field(gt=0)
    confidence: float | None = Field(default=None, ge=0, le=1)


class CaptionStyle(BaseModel):
    preset: Literal["bold_pop", "clean", "minimal"] = "bold_pop"
    font_family: str = Field(default="Noto Sans", min_length=1, max_length=120, pattern=r"^[^,\r\n]+$")
    font_size: int = Field(default=64, ge=16, le=160)
    text_color: str = Field(default="#FFFFFF", pattern=r"^#[0-9A-Fa-f]{6}([0-9A-Fa-f]{2})?$")
    highlight_color: str = Field(default="#F8E71C", pattern=r"^#[0-9A-Fa-f]{6}([0-9A-Fa-f]{2})?$")
    background_color: str = Field(default="#000000B8", pattern=r"^#[0-9A-Fa-f]{6}([0-9A-Fa-f]{2})?$")
    position: Literal["top", "middle", "bottom"] = "bottom"
    words_per_cue: int = Field(default=5, ge=1, le=12)


class TimelineItem(BaseModel):
    id: str
    kind: Literal["video", "audio", "title", "image", "caption"]
    track_id: str
    name: str
    start_ticks: int = Field(ge=0)
    duration_ticks: int = Field(gt=0)
    trim_start_ticks: int = Field(default=0, ge=0)
    trim_end_ticks: int = Field(default=0, ge=0)
    source_in_ticks: int = Field(default=0, ge=0)
    source_out_ticks: int | None = Field(default=None, gt=0)
    asset_id: str | None = None
    color: str = "#17213a"
    text: str | None = None
    x: int = 0
    y: int = 0
    width: int = Field(default=320, gt=0)
    height: int = Field(default=80, gt=0)
    fit_mode: Literal["fit", "fill", "stretch"] = "fit"
    scale: float = Field(default=1.0, gt=0, le=20)
    opacity: float = Field(default=1.0, ge=0, le=1)
    rotation: float = Field(default=0, ge=-360, le=360)
    gain_db: float = Field(default=0, ge=-60, le=24)
    muted: bool = False
    crop_keyframes: list[CropKeyframe] = Field(default_factory=list)
    caption_words: list[CaptionWord] = Field(default_factory=list)
    caption_style: CaptionStyle | None = None


class Track(BaseModel):
    id: str
    kind: Literal["video", "audio", "overlay", "caption"]
    name: str
    items: list[TimelineItem] = Field(default_factory=list)


class Project(BaseModel):
    id: str
    name: str
    workspace_id: str | None = None
    parent_project_id: str | None = None
    source_project_revision: int | None = Field(default=None, ge=1)
    source_suggestion_id: str | None = None
    variant_kind: str | None = None
    target_aspect_ratio: str | None = None
    target_variant: PlatformVariant | None = None
    brand_version: int | None = Field(default=None, ge=1)
    brand_hash: str | None = None
    # Missing schema_version in historical JSON always means the original v1 shape.
    schema_version: int = Field(default=1, ge=1)
    revision: int = Field(ge=1)
    canvas: Canvas = Field(default_factory=Canvas)
    duration_ticks: int = Field(gt=0)
    assets: list[Asset] = Field(default_factory=list)
    tracks: list[Track] = Field(default_factory=list)
    updated_at: str = Field(default_factory=utc_now)

    def item(self, item_id: str) -> TimelineItem:
        for track in self.tracks:
            for item in track.items:
                if item.id == item_id:
                    return item
        raise KeyError(item_id)

    def asset(self, asset_id: str) -> Asset:
        for asset in self.assets:
            if asset.id == asset_id:
                return asset
        raise KeyError(asset_id)


class ReceiptStatus(StrEnum):
    ACCEPTED = "accepted"
    COMMITTED = "committed"
    AWAITING_USER_ACTION = "awaiting_user_action"
    AWAITING_USER_CONSENT = "awaiting_user_consent"
    DISPATCHED = "dispatched"
    CAPTURING = "capturing"
    RENDERING = "rendering"
    ARTIFACT_WRITTEN = "artifact_written"
    AWAITING_OBSERVATION = "awaiting_observation"
    AWAITING_APPROVAL = "awaiting_approval"
    AWAITING_CONSUMER = "awaiting_consumer"
    OBSERVED_SUCCESS = "observed_success"
    OBSERVED_FAILURE = "observed_failure"
    EXECUTION_FAILED = "execution_failed"
    DENIED = "denied"
    CANCELLED = "cancelled"
    TIMEOUT = "timeout"


TERMINAL_RECEIPT_STATUSES = {
    ReceiptStatus.COMMITTED,
    ReceiptStatus.OBSERVED_SUCCESS,
    ReceiptStatus.OBSERVED_FAILURE,
    ReceiptStatus.EXECUTION_FAILED,
    ReceiptStatus.DENIED,
    ReceiptStatus.CANCELLED,
    ReceiptStatus.TIMEOUT,
}


class Receipt(BaseModel):
    id: str
    project_id: str
    command: str
    status: ReceiptStatus
    request_id: str
    actor: str
    project_revision: int
    payload: dict[str, Any] = Field(default_factory=dict)
    created_at: str = Field(default_factory=utc_now)
    updated_at: str = Field(default_factory=utc_now)


class CommandRequest(BaseModel):
    command: str
    arguments: dict[str, Any] = Field(default_factory=dict)
    expected_revision: int = Field(ge=1)
    request_id: str = Field(min_length=8, max_length=120)
    actor: str = Field(default="browser", min_length=1, max_length=100)
    confirmation_id: str | None = Field(default=None, min_length=8, max_length=120)


class CommandInvocation(BaseModel):
    command: str
    arguments: dict[str, Any] = Field(default_factory=dict)


class CommandBatchRequest(BaseModel):
    commands: list[CommandInvocation] = Field(min_length=1, max_length=50)
    expected_revision: int = Field(ge=1)
    request_id: str = Field(min_length=8, max_length=120)
    actor: str = Field(default="browser", min_length=1, max_length=100)
    confirmation_id: str | None = Field(default=None, min_length=8, max_length=120)


class CommandProposalRequest(BaseModel):
    commands: list[CommandInvocation] = Field(min_length=1, max_length=50)
    expected_revision: int = Field(ge=1)


class ConfirmationCreateRequest(BaseModel):
    command: str = Field(min_length=1, max_length=120)
    arguments: dict[str, Any] = Field(default_factory=dict)
    expected_revision: int = Field(ge=1)


class SelectionRequest(BaseModel):
    item_ids: list[str] = Field(min_length=1, max_length=12)
    expected_revision: int = Field(ge=1)
    request_id: str = Field(min_length=8, max_length=120)
    actor: str = "browser"


class RenderRequest(BaseModel):
    project_revision: int = Field(ge=1)
    request_id: str = Field(min_length=8, max_length=120)
    actor: str = "browser"


class ProjectCreateRequest(BaseModel):
    name: str = Field(min_length=1, max_length=120)
    preset: Literal["landscape_1080p", "vertical_1080p", "preview_540p"] = "landscape_1080p"
    workspace_id: str | None = Field(default=None, min_length=1, max_length=120)

    @field_validator("name")
    @classmethod
    def meaningful_name(cls, value: str) -> str:
        value = value.strip()
        if not value:
            raise ValueError("project name cannot be blank")
        return value


class ShortsGenerateRequest(BaseModel):
    source_revision: int = Field(ge=1)
    asset_id: str | None = None
    prompt: str | None = Field(default=None, max_length=2000)
    language: Literal["auto", "en", "he"] = "auto"
    candidate_count: int = Field(default=5, ge=1, le=10)
    min_duration_ticks: int = Field(default=15 * TICKS_PER_SECOND, ge=15 * TICKS_PER_SECOND, le=90 * TICKS_PER_SECOND)
    max_duration_ticks: int = Field(default=90 * TICKS_PER_SECOND, ge=15 * TICKS_PER_SECOND, le=90 * TICKS_PER_SECOND)
    aspect_ratio: Literal["9:16"] = "9:16"
    target_variants: list[PlatformVariant] = Field(default_factory=list, max_length=3)
    brand_contract: BrandContract = Field(default_factory=BrandContract)

    @field_validator("max_duration_ticks")
    @classmethod
    def duration_range_is_valid(cls, value: int, info):
        minimum = info.data.get("min_duration_ticks")
        if minimum is not None and value < minimum:
            raise ValueError("max_duration_ticks must be greater than or equal to min_duration_ticks")
        return value


class SuggestionDecisionRequest(BaseModel):
    request_id: str = Field(min_length=8, max_length=120)
    actor: str = Field(default="browser", min_length=1, max_length=100)
    expected_state: Literal["pending"] = "pending"
    name: str | None = Field(default=None, min_length=1, max_length=120)


class MediaImportResult(BaseModel):
    receipt: Receipt
    asset: Asset | None = None


class PairStartRequest(BaseModel):
    workspace_id: str = "demo"
    project_id: str | None = None
    sequence_id: str | None = None
    scopes: list[str] = Field(
        default_factory=lambda: [
            "context:read", "project:read", "project:write", "analysis:run",
            "render:run", "receipt:read", "focus:write", "release:prepare",
        ],
        min_length=1,
        max_length=16,
    )


class PairAttachRequest(BaseModel):
    code: str = Field(pattern=r"^\d{6}$")
    actor_name: str = Field(min_length=1, max_length=80)


class ObservationContract(BaseModel):
    project_id: str
    project_revision: int
    artifact_path: str
    artifact_sha256: str
    width: int
    height: int
    duration_seconds: float
    fps: float
    title_id: str | None = None
    title_active_seconds: float | None = None
    safe_margin_x: int
    safe_margin_y: int
    marker_rgb: tuple[int, int, int] | None = None
    expect_audio: bool = False
    expect_captions: bool = False


class ObservationFinding(BaseModel):
    code: str
    passed: bool
    summary: str
    evidence: dict[str, Any] = Field(default_factory=dict)


class ObservationResult(BaseModel):
    observer: str = "artifact-frame-observer-v0.1"
    observer_failure_domain: str = "separate-process-compatible"
    passed: bool
    findings: list[ObservationFinding]
    observed_at: str = Field(default_factory=utc_now)


class ObserverRequest(BaseModel):
    contract: ObservationContract


class StaleRevisionError(Exception):
    def __init__(self, expected: int, actual: int):
        self.expected = expected
        self.actual = actual
        super().__init__(f"stale project revision: expected {expected}, current {actual}")


class CommandValidationError(Exception):
    pass
