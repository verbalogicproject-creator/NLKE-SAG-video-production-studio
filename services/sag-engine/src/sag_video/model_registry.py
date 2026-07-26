"""Versioned, provider-neutral model capabilities used by SAG Video.

The registry is deliberately data-only.  Provider adapters may implement a
capability, but they cannot invent models at request time.  This keeps model
selection auditable and makes provider deprecations explicit.
"""
from __future__ import annotations

import hashlib
import json
from typing import Any, Literal

from pydantic import BaseModel, Field


class ModelDescriptor(BaseModel):
    id: str = Field(pattern=r"^[a-z0-9][a-z0-9._-]{2,127}$")
    provider: Literal["google"]
    family: Literal["video", "audio", "music", "image", "reasoning"]
    lifecycle: Literal["preview", "ga", "deprecated"]
    capabilities: list[str] = Field(min_length=1, max_length=32)
    input_modalities: list[Literal["text", "image", "audio", "video"]] = Field(default_factory=list)
    output_modalities: list[Literal["video", "audio", "image", "text"]] = Field(default_factory=list)
    default_for: list[str] = Field(default_factory=list)
    documentation_url: str
    notes: str = Field(default="", max_length=1000)


MODEL_REGISTRY_VERSION = "google-gemini-2026-07-26.1"

GOOGLE_MODELS: tuple[ModelDescriptor, ...] = (
    ModelDescriptor(
        id="gemini-omni-flash-preview", provider="google", family="video", lifecycle="preview",
        capabilities=["video_generation", "conversational_video_editing", "multimodal_reasoning", "multi_turn_interactions"],
        input_modalities=["text", "image", "audio", "video"], output_modalities=["video"],
        default_for=["video_generation", "video_editing"],
        documentation_url="https://ai.google.dev/gemini-api/docs/video",
        notes="Default conversational video generation and editing model.",
    ),
    ModelDescriptor(
        id="veo-3.1-generate-preview", provider="google", family="video", lifecycle="preview",
        capabilities=["video_generation", "native_audio", "scene_extension", "first_last_frame_control", "reference_images"],
        input_modalities=["text", "image", "video"], output_modalities=["video", "audio"],
        default_for=["controlled_video_generation", "video_extension"],
        documentation_url="https://ai.google.dev/gemini-api/docs/video",
        notes="Use when Veo-specific cinematic controls are required.",
    ),
    ModelDescriptor(
        id="veo-3.1-lite-generate-preview", provider="google", family="video", lifecycle="preview",
        capabilities=["video_generation", "video_editing", "rapid_iteration"],
        input_modalities=["text", "image", "video"], output_modalities=["video", "audio"],
        default_for=["video_preview"],
        documentation_url="https://ai.google.dev/gemini-api/docs/models",
        notes="Cost-efficient preview/iteration model; never silently promoted to production default.",
    ),
    ModelDescriptor(
        id="lyria-3-clip-preview", provider="google", family="music", lifecycle="preview",
        capabilities=["music_generation", "instrumental_clip", "loop_generation"],
        input_modalities=["text", "image"], output_modalities=["audio"],
        default_for=["soundtrack_preview"],
        documentation_url="https://ai.google.dev/gemini-api/docs/generate-content/music-generation",
    ),
    ModelDescriptor(
        id="lyria-3-pro-preview", provider="google", family="music", lifecycle="preview",
        capabilities=["music_generation", "full_length_song"],
        input_modalities=["text", "image"], output_modalities=["audio"],
        default_for=["soundtrack_production"],
        documentation_url="https://ai.google.dev/gemini-api/docs/generate-content/music-generation",
    ),
    ModelDescriptor(
        id="gemini-3.1-flash-tts-preview", provider="google", family="audio", lifecycle="preview",
        capabilities=["text_to_speech", "multi_speaker_tts", "style_control"],
        input_modalities=["text"], output_modalities=["audio"],
        default_for=["narration", "dialogue"],
        documentation_url="https://ai.google.dev/gemini-api/docs/speech-generation",
    ),
)


def model_registry() -> list[dict[str, Any]]:
    return [entry.model_dump(mode="json") for entry in GOOGLE_MODELS]


def model_registry_hash() -> str:
    payload = json.dumps(model_registry(), sort_keys=True, separators=(",", ":")).encode()
    return hashlib.sha256(payload).hexdigest()


def get_model(model_id: str) -> ModelDescriptor:
    for model in GOOGLE_MODELS:
        if model.id == model_id:
            return model
    raise ValueError(f"unsupported generative model: {model_id}")


def validate_model_for(model_id: str, capability: str) -> ModelDescriptor:
    model = get_model(model_id)
    if model.lifecycle == "deprecated":
        raise ValueError(f"model is deprecated: {model_id}")
    if capability not in model.capabilities:
        raise ValueError(f"model {model_id} does not support {capability}")
    return model
