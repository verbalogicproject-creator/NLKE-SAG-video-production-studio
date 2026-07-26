"""Credential-gated Google generative media boundary.

This module intentionally does not fabricate completed assets.  Provider
operations are asynchronous and must be reconciled and observed by the
canonical job/receipt pipeline before becoming timeline assets.
"""
from __future__ import annotations

import hashlib
import json
import os
import base64
from pathlib import Path
from datetime import datetime, timezone
from typing import Any, Literal, Protocol

from pydantic import BaseModel, Field, field_validator

from .model_registry import validate_model_for


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _local_env_value(name: str) -> str | None:
    """Read one local development secret without logging or exporting it."""
    candidates = [Path.cwd() / ".env.local", Path(__file__).resolve().parents[4] / ".env.local"]
    for path in candidates:
        try:
            if not path.is_file():
                continue
            for line in path.read_text(encoding="utf-8").splitlines():
                key, separator, value = line.partition("=")
                if separator and key.strip() == name:
                    value = value.strip().strip('"').strip("'")
                    return value or None
        except OSError:
            continue
    return None


class GenerativeVideoRequest(BaseModel):
    model: str = "veo-3.1-lite-generate-preview"
    prompt: str = Field(min_length=1, max_length=12000)
    duration_seconds: float = Field(default=8.0, ge=1.0, le=30.0)
    aspect_ratio: Literal["16:9", "9:16", "1:1"] = "16:9"
    resolution: Literal["720p", "1080p", "4k"] = "720p"
    negative_prompt: str = Field(default="", max_length=2000)
    reference_asset_ids: list[str] = Field(default_factory=list, max_length=3)
    first_frame_asset_id: str | None = None
    last_frame_asset_id: str | None = None

    @field_validator("reference_asset_ids")
    @classmethod
    def bounded_ids(cls, value: list[str]) -> list[str]:
        if any(len(item) > 160 or not item.strip() for item in value):
            raise ValueError("reference asset IDs must be non-empty and bounded")
        return list(dict.fromkeys(value))


class GenerativeAudioRequest(BaseModel):
    model: str = "gemini-3.1-flash-tts-preview"
    text: str = Field(min_length=1, max_length=20000)
    voice_name: str | None = Field(default=None, max_length=80)
    duration_seconds: float = Field(default=30.0, ge=1.0, le=600.0)


class ProviderOperation(BaseModel):
    request_id: str
    provider: Literal["google"] = "google"
    model: str
    operation_name: str
    state: Literal["pending", "running", "completed", "failed"] = "pending"
    created_at: str = Field(default_factory=_now)
    error_code: str | None = None
    error_detail: str | None = None
    output: dict[str, Any] | None = None


class GoogleProviderClient(Protocol):
    """Small protocol allowing deterministic adapter tests without Google."""

    def start_video(self, *, model: str, request: GenerativeVideoRequest) -> str: ...
    def start_audio(self, *, model: str, request: GenerativeAudioRequest) -> str: ...
    def poll(self, *, operation_name: str) -> dict[str, Any]: ...
    def plan_text(self, *, model: str, prompt: str, response_schema: dict[str, Any] | None = None) -> str: ...


def request_hash(request: BaseModel) -> str:
    body = json.dumps(request.model_dump(mode="json"), sort_keys=True, separators=(",", ":")).encode()
    return hashlib.sha256(body).hexdigest()


class GoogleGenerativeAdapter:
    """Adapter around the official Google GenAI client.

    The SDK is loaded lazily so the engine remains usable when generative
    features are not configured. Missing credentials are an explicit error,
    never a successful mock response.
    """

    def __init__(self, client: GoogleProviderClient | None = None, *, api_key: str | None = None):
        self.client = client
        self.api_key = api_key if api_key is not None else (os.getenv("GEMINI_API_KEY") or _local_env_value("GEMINI_API_KEY"))

    def _client(self) -> GoogleProviderClient:
        if self.client is not None:
            return self.client
        if not self.api_key:
            raise RuntimeError("Google generative media is not configured: GEMINI_API_KEY or Vertex credentials required")
        try:
            from google import genai  # type: ignore
        except ImportError as error:
            raise RuntimeError("install the google-genai package to enable generative media") from error
        # Keep the SDK object behind the protocol. The concrete calls are
        # isolated here so provider SDK upgrades cannot leak into the engine.
        return _SdkClient(genai.Client(api_key=self.api_key))

    def start_video(self, request: GenerativeVideoRequest) -> ProviderOperation:
        validate_model_for(request.model, "video_generation")
        operation_name = self._client().start_video(model=request.model, request=request)
        return ProviderOperation(request_id=f"gen_{request_hash(request)[:24]}", model=request.model, operation_name=operation_name)

    def start_audio(self, request: GenerativeAudioRequest) -> ProviderOperation:
        capability = "music_generation" if request.model.startswith("lyria-") else "text_to_speech"
        validate_model_for(request.model, capability)
        operation_name = self._client().start_audio(model=request.model, request=request)
        return ProviderOperation(request_id=f"gen_{request_hash(request)[:24]}", model=request.model, operation_name=operation_name)

    def poll(self, operation: ProviderOperation) -> ProviderOperation:
        result = self._client().poll(operation_name=operation.operation_name)
        state = result.get("state", "running")
        if state not in {"pending", "running", "completed", "failed"}:
            raise RuntimeError("provider returned an invalid operation state")
        return operation.model_copy(update={"state": state, "output": result.get("output"), "error_code": result.get("error_code"), "error_detail": result.get("error_detail")})

    def plan_text(self, *, model: str, prompt: str, response_schema: dict[str, Any] | None = None) -> str:
        validate_model_for(model, "multi_turn_interactions")
        return self._client().plan_text(model=model, prompt=prompt, response_schema=response_schema)


class _SdkClient:
    def __init__(self, client: Any):
        self.client = client

    def start_video(self, *, model: str, request: GenerativeVideoRequest) -> str:
        if model == "gemini-omni-flash-preview":
            create_interaction = getattr(getattr(self.client, "interactions", None), "create", None)
            if create_interaction is None:
                raise RuntimeError("installed google-genai SDK does not expose Interactions API")
            interaction = create_interaction(
                model=model,
                input=request.prompt,
                response_format={"type": "video", "aspect_ratio": request.aspect_ratio, "delivery": "uri"},
                generation_config={"video_config": {"task": "text_to_video"}},
            )
            identifier = getattr(interaction, "id", None) or getattr(interaction, "name", None)
            if not identifier:
                raise RuntimeError("Gemini Omni did not return an interaction ID")
            return f"interactions/{identifier}"
        generate = getattr(getattr(self.client, "models", None), "generate_videos", None)
        if generate is None:
            raise RuntimeError("installed google-genai SDK does not expose video generation")
        config: dict[str, Any] = {"aspect_ratio": request.aspect_ratio, "resolution": request.resolution}
        if request.negative_prompt:
            config["negative_prompt"] = request.negative_prompt
        operation = generate(model=model, prompt=request.prompt, config=config)
        name = getattr(operation, "name", None) or getattr(operation, "operation_name", None)
        if not name:
            raise RuntimeError("Google video generation did not return an operation name")
        return str(name)

    def start_audio(self, *, model: str, request: GenerativeAudioRequest) -> str:
        create = getattr(getattr(self.client, "interactions", None), "create", None)
        if create is None:
            raise RuntimeError("installed google-genai SDK does not expose Interactions API")
        interaction = create(model=model, input=request.text)
        name = getattr(interaction, "id", None) or getattr(interaction, "name", None)
        if not name:
            raise RuntimeError("Google audio generation did not return an operation ID")
        return f"interactions/{str(name).removeprefix('interactions/')}"

    def poll(self, *, operation_name: str) -> dict[str, Any]:
        if operation_name.startswith("interactions/"):
            getter = getattr(getattr(self.client, "interactions", None), "get", None)
            if getter is None:
                raise RuntimeError("installed google-genai SDK does not expose interaction polling")
            interaction = getter(id=operation_name.removeprefix("interactions/"))
            status = str(getattr(interaction, "status", "completed")).lower()
            output = _media_output(interaction)
            return {"state": "failed" if status in {"failed", "error"} else ("completed" if status in {"completed", "succeeded", "done"} else "running"), "output": output}
        get = getattr(getattr(self.client, "operations", None), "get", None)
        if get is None:
            raise RuntimeError("installed google-genai SDK does not expose operation polling")
        operation = get(name=operation_name)
        done = bool(getattr(operation, "done", False))
        error = getattr(operation, "error", None)
        response = getattr(operation, "response", None)
        output = _media_output(response) if response is not None else None
        return {"state": "failed" if error else ("completed" if done else "running"), "error_detail": str(error) if error else None, "output": output}

    def plan_text(self, *, model: str, prompt: str, response_schema: dict[str, Any] | None = None) -> str:
        create = getattr(getattr(self.client, "interactions", None), "create", None)
        if create is None:
            raise RuntimeError("installed google-genai SDK does not expose Interactions API")
        arguments: dict[str, Any] = {"model": model, "input": prompt}
        if response_schema is not None:
            arguments["response_format"] = {
                "type": "text", "mime_type": "application/json", "schema": response_schema,
            }
        interaction = create(**arguments)
        outputs = getattr(interaction, "outputs", None) or []
        for output in outputs:
            text = getattr(output, "text", None)
            if text:
                return str(text)
        text = getattr(interaction, "text", None)
        if text:
            return str(text)
        output_text = getattr(interaction, "output_text", None)
        if output_text:
            return str(output_text)
        raise RuntimeError("Omni interaction returned no text output")


def _media_output(value: Any) -> dict[str, Any] | None:
    """Find bounded provider media in SDK objects without depending on one preview response shape."""
    if hasattr(value, "model_dump"):
        value = value.model_dump(exclude_none=True)
    if isinstance(value, dict):
        inline = value.get("inline_data") or value.get("inlineData")
        if inline is not None:
            if hasattr(inline, "model_dump"):
                inline = inline.model_dump(exclude_none=True)
            if isinstance(inline, dict) and inline.get("data"):
                data = inline["data"]
                return {"data_base64": base64.b64encode(data).decode() if isinstance(data, bytes) else str(data)}
        for key in ("uri", "video_uri", "audio_uri", "file_uri"):
            if value.get(key):
                return {"uri": str(value[key])}
        for nested in value.values():
            found = _media_output(nested)
            if found:
                return found
    elif isinstance(value, (list, tuple)):
        for nested in value:
            found = _media_output(nested)
            if found:
                return found
    return None
