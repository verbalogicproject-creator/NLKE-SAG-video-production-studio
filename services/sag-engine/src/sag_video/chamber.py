from __future__ import annotations

import hashlib
import json
from enum import StrEnum
from typing import Any, Literal

from pydantic import BaseModel, Field, field_validator, model_validator


class PlatformVariant(StrEnum):
    YT_SHORTS_9_16 = "YT_SHORTS_9_16"
    TIKTOK_9_16 = "TIKTOK_9_16"
    IG_REELS_9_16 = "IG_REELS_9_16"


class BrandContract(BaseModel):
    version: int = Field(default=1, ge=1)
    contract_hash: str = ""
    forbidden_phrases: list[str] = Field(default_factory=list)
    required_disclosures: dict[str, str] = Field(default_factory=dict)
    palette: list[str] = Field(default_factory=list)
    font_family: str = "Noto Sans"
    caption_preset: Literal["bold_pop", "clean", "minimal"] = "bold_pop"
    text_color: str = "#FFFFFF"
    highlight_color: str = "#F8E71C"
    background_color: str = "#000000B8"

    @field_validator("forbidden_phrases")
    @classmethod
    def normalize_phrases(cls, value: list[str]) -> list[str]:
        return list(dict.fromkeys(phrase.strip() for phrase in value if phrase.strip()))

    @model_validator(mode="after")
    def populate_hash(self) -> "BrandContract":
        if self.contract_hash:
            return self
        body = self.model_dump(mode="json", exclude={"contract_hash"})
        self.contract_hash = hashlib.sha256(
            json.dumps(body, sort_keys=True, separators=(",", ":")).encode()
        ).hexdigest()
        return self


class DraftScene(BaseModel):
    source_start_ticks: int = Field(ge=0)
    source_end_ticks: int = Field(gt=0)
    word_ids: list[str] = Field(min_length=1)

    @model_validator(mode="after")
    def ordered(self) -> "DraftScene":
        if self.source_end_ticks <= self.source_start_ticks:
            raise ValueError("source_end_ticks must be greater than source_start_ticks")
        return self


class DraftPlan(BaseModel):
    contract_version: Literal["chamber-draft-1.0"] = "chamber-draft-1.0"
    target_variant: PlatformVariant
    source_project_id: str
    source_revision: int = Field(ge=1)
    source_asset_id: str
    source_sha256: str = Field(min_length=16)
    scenes: list[DraftScene] = Field(min_length=1)
    hook_title: str | None = Field(default=None, max_length=200)
    post_copy: str = Field(default="", max_length=5000)
    hashtags: list[str] = Field(default_factory=list)
    caption_register: Literal["casual", "hook-first", "polished"] = "hook-first"
    score: float = Field(ge=0, le=100)
    score_components: dict[str, float] = Field(default_factory=dict)
    reason: str = Field(max_length=500)
    brand_version: int = Field(ge=1)
    brand_hash: str
    provider: dict[str, Any] = Field(default_factory=dict)
    warnings: list[str] = Field(default_factory=list)


class BrandViolation(BaseModel):
    code: str
    field: str
    phrase: str | None = None
    summary: str


def validate_brand_text(text: str, brand: BrandContract, field: str) -> list[BrandViolation]:
    folded = text.casefold()
    return [
        BrandViolation(
            code="forbidden_phrase",
            field=field,
            phrase=phrase,
            summary=f"Forbidden brand phrase appears in {field}",
        )
        for phrase in brand.forbidden_phrases
        if phrase.casefold() in folded
    ]


def validate_draft_plan(plan: DraftPlan, transcript_text: str, brand: BrandContract) -> list[BrandViolation]:
    violations = validate_brand_text(transcript_text, brand, "captions")
    violations.extend(validate_brand_text(plan.hook_title or "", brand, "hook_title"))
    violations.extend(validate_brand_text(plan.post_copy, brand, "post_copy"))
    disclosure = brand.required_disclosures.get(plan.target_variant.value)
    if disclosure and disclosure.casefold() not in plan.post_copy.casefold():
        violations.append(BrandViolation(
            code="missing_disclosure",
            field="post_copy",
            phrase=disclosure,
            summary="Required platform disclosure is missing",
        ))
    return violations


def draft_plan_to_edl(plan: DraftPlan, source_key: str, words: list[dict[str, Any]]) -> dict[str, Any]:
    """Compatibility export. DraftPlan remains the canonical pre-acceptance contract."""
    selected = {word_id for scene in plan.scenes for word_id in scene.word_ids}
    caption_words = [word for word in words if str(word.get("id")) in selected]
    first_tick = min(scene.source_start_ticks for scene in plan.scenes)
    return {
        "version": "1.0.0",
        "variant": plan.target_variant.value,
        "sourceR2Key": source_key,
        "hookSummary": plan.hook_title or plan.reason,
        "scenes": [{
            "sourceStartMs": round(scene.source_start_ticks / 120),
            "sourceEndMs": round(scene.source_end_ticks / 120),
            "speed": 1,
            "transition": "cut",
            "transitionDurationMs": 0,
        } for scene in plan.scenes],
        "captions": [{
            "style": "karaoke",
            "words": [{
                "startMs": round((int(word["start_ticks"]) - first_tick) / 120),
                "endMs": round((int(word["end_ticks"]) - first_tick) / 120),
                "text": str(word["text"]),
                "emphasis": "none",
            } for word in caption_words],
        }],
        "audio": {"kind": "source", "gain": 1, "duckUnderSpeech": False},
        "overlays": [],
        "captionRegister": plan.caption_register,
        "postCopy": {"description": plan.post_copy, "hashtags": plan.hashtags},
    }
