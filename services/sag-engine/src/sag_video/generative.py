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
import time
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


def _provider_failure(error: Exception) -> RuntimeError:
    detail = str(error)
    lowered = detail.lower()
    if "quota" in lowered or "rate limit" in lowered or "too_many_requests" in lowered or "429" in lowered:
        return RuntimeError("quota_failure: Google generative quota is exhausted or rate-limited")
    return RuntimeError(f"provider_failure: {detail[:500]}")


def _is_quota_failure(error: Exception) -> bool:
    lowered = str(error).lower()
    return "quota" in lowered or "rate limit" in lowered or "too_many_requests" in lowered or "429" in lowered


class GoogleGenerativeAdapter:
    """Adapter around the official Google GenAI client.

    The SDK is loaded lazily so the engine remains usable when generative
    features are not configured. Missing credentials are an explicit error,
    never a successful mock response.
    """

    def __init__(
        self, client: GoogleProviderClient | None = None, *, api_key: str | None = None, backend: str | None = None,
    ):
        self.client = client
        self.api_key = api_key if api_key is not None else (os.getenv("GEMINI_API_KEY") or _local_env_value("GEMINI_API_KEY"))
        self.backend = (backend or os.getenv("SAG_GOOGLE_GENAI_BACKEND") or _local_env_value("SAG_GOOGLE_GENAI_BACKEND") or "auto").lower()
        if self.backend not in {"auto", "developer", "vertex"}:
            raise ValueError("SAG_GOOGLE_GENAI_BACKEND must be auto, developer, or vertex")
        self._developer_sdk: GoogleProviderClient | None = None
        self._vertex_sdk: GoogleProviderClient | None = None

    def _client(self) -> GoogleProviderClient:
        if self.client is not None:
            return self.client
        if self.backend == "vertex" or (not self.api_key and self.backend == "auto"):
            return self._vertex_client()
        if not self.api_key:
            raise RuntimeError("Google generative media is not configured: GEMINI_API_KEY or Vertex credentials required")
        if self._developer_sdk is not None:
            return self._developer_sdk
        try:
            from google import genai  # type: ignore
        except ImportError as error:
            raise RuntimeError("install the google-genai package to enable generative media") from error
        # Keep the SDK object behind the protocol. The concrete calls are
        # isolated here so provider SDK upgrades cannot leak into the engine.
        self._developer_sdk = _SdkClient(genai.Client(api_key=self.api_key))
        return self._developer_sdk

    def _vertex_client(self) -> GoogleProviderClient:
        if self._vertex_sdk is not None:
            return self._vertex_sdk
        try:
            from google import genai  # type: ignore
            import google.auth  # type: ignore
            from google.oauth2 import service_account  # type: ignore
        except ImportError as error:
            raise RuntimeError("install Google auth and google-genai packages to enable Vertex generative media") from error
        credential_value = os.getenv("GOOGLE_APPLICATION_CREDENTIALS") or _local_env_value("GOOGLE_APPLICATION_CREDENTIALS")
        credentials: Any
        discovered_project: str | None
        if credential_value:
            path = Path(credential_value).expanduser()
            if not path.is_absolute():
                repository_root = Path(__file__).resolve().parents[4]
                candidates = (Path.cwd() / path, repository_root / path, repository_root.parent / path)
                path = next((candidate for candidate in candidates if candidate.is_file()), path)
            credentials = service_account.Credentials.from_service_account_file(
                str(path), scopes=["https://www.googleapis.com/auth/cloud-platform"],
            )
            discovered_project = getattr(credentials, "project_id", None)
        else:
            credentials, discovered_project = google.auth.default(
                scopes=["https://www.googleapis.com/auth/cloud-platform"]
            )
        project = os.getenv("GOOGLE_CLOUD_PROJECT") or _local_env_value("GOOGLE_CLOUD_PROJECT") or discovered_project
        if not project:
            raise RuntimeError("Vertex generative media requires GOOGLE_CLOUD_PROJECT or project-bearing ADC")
        location = os.getenv("GOOGLE_GENAI_LOCATION") or _local_env_value("GOOGLE_GENAI_LOCATION") or "global"
        self._vertex_sdk = _SdkClient(genai.Client(
            vertexai=True, project=project, location=location, credentials=credentials,
        ))
        return self._vertex_sdk

    def _call(self, method: str, **arguments: Any) -> Any:
        try:
            return getattr(self._client(), method)(**arguments)
        except (RuntimeError, ValueError):
            raise
        except Exception as error:
            if self.client is None and self.backend == "auto" and self.api_key and _is_quota_failure(error):
                try:
                    return getattr(self._vertex_client(), method)(**arguments)
                except (RuntimeError, ValueError):
                    raise
                except Exception as fallback_error:
                    raise _provider_failure(fallback_error) from fallback_error
            raise _provider_failure(error) from error

    def start_video(self, request: GenerativeVideoRequest) -> ProviderOperation:
        validate_model_for(request.model, "video_generation")
        operation_name = self._call("start_video", model=request.model, request=request)
        return ProviderOperation(request_id=f"gen_{request_hash(request)[:24]}", model=request.model, operation_name=operation_name)

    def start_audio(self, request: GenerativeAudioRequest) -> ProviderOperation:
        capability = "music_generation" if request.model.startswith("lyria-") else "text_to_speech"
        validate_model_for(request.model, capability)
        operation_name = self._call("start_audio", model=request.model, request=request)
        return ProviderOperation(request_id=f"gen_{request_hash(request)[:24]}", model=request.model, operation_name=operation_name)

    def poll(self, operation: ProviderOperation) -> ProviderOperation:
        result = self._call("poll", operation_name=operation.operation_name)
        state = result.get("state", "running")
        if state not in {"pending", "running", "completed", "failed"}:
            raise RuntimeError("provider returned an invalid operation state")
        return operation.model_copy(update={"state": state, "output": result.get("output"), "error_code": result.get("error_code"), "error_detail": result.get("error_detail")})

    def plan_text(self, *, model: str, prompt: str, response_schema: dict[str, Any] | None = None) -> str:
        validate_model_for(model, "multi_turn_interactions")
        return self._call("plan_text", model=model, prompt=prompt, response_schema=response_schema)


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
        arguments: dict[str, Any] = {
            "model": model, "input": prompt, "background": False, "store": False, "stream": False,
        }
        if response_schema is not None:
            arguments["response_format"] = {
                "type": "text", "mime_type": "application/json", "schema": _inline_json_schema(response_schema),
            }
        getter = getattr(getattr(self.client, "interactions", None), "get", None)
        last_status = "unknown"
        for attempt in range(2):
            if attempt:
                arguments["input"] = prompt + "\n\nFinal instruction: emit the requested JSON object now; do not return an empty response."
            interaction = create(**arguments)
            text = _text_output(interaction)
            if text:
                return text
            identifier = getattr(interaction, "id", None) or getattr(interaction, "name", None)
            last_status = str(getattr(interaction, "status", "")).lower() or "unknown"
            for _ in range(5):
                if not identifier or getter is None or last_status in {"completed", "succeeded", "done", "failed", "error"}:
                    break
                time.sleep(1)
                interaction = getter(id=str(identifier).removeprefix("interactions/"))
                text = _text_output(interaction)
                if text:
                    return text
                last_status = str(getattr(interaction, "status", "")).lower() or "unknown"
        raise RuntimeError(f"Omni interaction returned no text output (status={last_status})")


def _inline_json_schema(schema: dict[str, Any]) -> dict[str, Any]:
    """Inline Pydantic local refs for the Interactions structured-output subset."""
    definitions = schema.get("$defs", {})
    supported_keywords = {
        "type", "properties", "required", "additionalProperties", "items", "enum", "format",
        "description", "anyOf", "oneOf",
    }

    def visit(value: Any, resolving: frozenset[str] = frozenset()) -> Any:
        if isinstance(value, list):
            return [visit(item, resolving) for item in value]
        if not isinstance(value, dict):
            return value
        reference = value.get("$ref")
        if isinstance(reference, str) and reference.startswith("#/$defs/"):
            name = reference.removeprefix("#/$defs/")
            if name not in definitions or name in resolving:
                raise ValueError("structured output schema contains an unresolved or recursive local reference")
            merged = {**definitions[name], **{key: item for key, item in value.items() if key != "$ref"}}
            return visit(merged, resolving | {name})
        result: dict[str, Any] = {}
        for key, item in value.items():
            if key not in supported_keywords:
                continue
            if key == "properties" and isinstance(item, dict):
                result[key] = {name: visit(property_schema, resolving) for name, property_schema in item.items()}
            else:
                result[key] = visit(item, resolving)
        return result

    result = visit(schema)
    if not isinstance(result, dict):
        raise ValueError("structured output schema must be an object")
    return result


def _text_output(value: Any) -> str | None:
    """Read current and legacy Interactions text shapes without returning thoughts or user input."""
    for attribute in ("output_text", "text"):
        text = getattr(value, attribute, None)
        if text:
            return str(text)
    outputs = getattr(value, "outputs", None) or []
    for output in outputs:
        text = getattr(output, "text", None)
        if text:
            return str(text)
    if hasattr(value, "model_dump"):
        value = value.model_dump(exclude_none=True)
    if not isinstance(value, dict):
        return None
    direct = value.get("output_text")
    if direct:
        return str(direct)
    for step in reversed(value.get("steps", [])):
        if isinstance(step, dict) and step.get("type") == "model_output":
            for content in step.get("content", []):
                if isinstance(content, dict) and content.get("type") == "text" and content.get("text"):
                    return str(content["text"])
    return None


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
