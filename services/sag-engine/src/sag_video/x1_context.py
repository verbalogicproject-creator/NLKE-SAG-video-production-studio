from __future__ import annotations

from datetime import datetime
from typing import Literal

from pydantic import BaseModel, Field, field_validator, model_validator


RRF_LABELS = {"bm25", "structural", "rules", "dense", "weighted"}
RRF_SOURCE_MAX = 64


class RRFSourceEvidence(BaseModel):
    """The bounded, provider-neutral evidence attached to one ranked result."""

    rrf_sources: list[str] = Field(min_length=1, max_length=RRF_SOURCE_MAX)
    score: float

    @field_validator("rrf_sources")
    @classmethod
    def validate_sources(cls, values: list[str]) -> list[str]:
        for value in values:
            if not value or len(value) > 160:
                raise ValueError("rrf source labels must be non-empty and bounded")
            root, _, suffix = value.partition(":")
            if root not in RRF_LABELS:
                raise ValueError(f"unknown rrf source label: {value}")
            if root == "structural" and suffix and len(suffix) > 120:
                raise ValueError("structural rrf source suffix is too long")
        if len(set(values)) != len(values):
            raise ValueError("rrf source labels must be unique")
        return values


class ContextNodeReceipt(RRFSourceEvidence):
    task: str = Field(min_length=1, max_length=4_096)
    anchor: str = Field(max_length=1_024)
    path: str = Field(min_length=1, max_length=1_024)
    title: str = Field(min_length=1, max_length=512)
    tokens: int = Field(ge=0)
    decision: Literal["kept", "dropped"]
    reason: str = Field(default="", max_length=512)
    ts: datetime

    @model_validator(mode="after")
    def validate_traceability(self) -> "ContextNodeReceipt":
        if self.decision == "kept" and (not self.anchor or not self.rrf_sources):
            raise ValueError("kept context nodes require an anchor and rrf_sources")
        if self.decision == "kept" and self.reason:
            raise ValueError("kept context nodes must have an empty reason")
        if self.decision == "dropped" and not self.reason:
            raise ValueError("dropped context nodes require a reason")
        return self


class ContextLoadReceipt(BaseModel):
    """Selection-level sag.context_load receipt; contents and prompts stay out of it."""

    task: str = Field(min_length=1, max_length=4_096)
    nodes: list[ContextNodeReceipt] = Field(default_factory=list, max_length=10_000)
    budget: int | None = Field(default=None, ge=0)
    tokens_used: int = Field(ge=0)
    total_candidates: int = Field(ge=0)
    would_load_blind: int = Field(ge=0)
    tokens_saved: int
    anchors: list[str] = Field(default_factory=list, max_length=10_000)

    @model_validator(mode="after")
    def validate_budget(self) -> "ContextLoadReceipt":
        if self.budget is not None and self.tokens_used > self.budget:
            raise ValueError("tokens_used exceeds the hard context budget")
        kept = [node for node in self.nodes if node.decision == "kept"]
        if self.tokens_used != sum(node.tokens for node in kept):
            raise ValueError("tokens_used must equal the cost of kept nodes")
        if self.total_candidates < len(self.nodes):
            raise ValueError("total_candidates cannot be less than recorded nodes")
        if self.tokens_saved != self.would_load_blind - self.tokens_used:
            raise ValueError("tokens_saved must equal blind cost minus selected cost")
        expected_anchors = [node.anchor for node in kept]
        if self.anchors != expected_anchors:
            raise ValueError("anchors must match kept node anchors in selection order")
        return self


def x1_context_schemas() -> dict[str, object]:
    return {
        "RRFSourceEvidence": RRFSourceEvidence.model_json_schema(),
        "ContextNodeReceipt": ContextNodeReceipt.model_json_schema(),
        "ContextLoadReceipt": ContextLoadReceipt.model_json_schema(),
    }
