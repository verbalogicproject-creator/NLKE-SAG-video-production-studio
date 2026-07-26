"""Convert provider outputs into observed-valid canonical media assets."""
from __future__ import annotations

import base64
import binascii
import io
import wave
from typing import Any

import httpx


MAX_PROVIDER_BYTES = 512 * 1024 * 1024


def provider_bytes(output: Any) -> tuple[bytes, str]:
    if not isinstance(output, dict):
        raise ValueError("provider output is not materializable")
    encoded = output.get("data_base64") or output.get("inline_data_base64")
    if encoded:
        try:
            data = base64.b64decode(str(encoded), validate=True)
        except (binascii.Error, ValueError) as error:
            raise ValueError("provider returned invalid base64 media") from error
        if len(data) > MAX_PROVIDER_BYTES:
            raise ValueError("provider media exceeds the bounded download limit")
        mime_type = str(output.get("mime_type") or "").lower()
        if "audio/l16" in mime_type or "audio/pcm" in mime_type:
            wrapped = io.BytesIO()
            with wave.open(wrapped, "wb") as destination:
                destination.setnchannels(1)
                destination.setsampwidth(2)
                destination.setframerate(24000)
                destination.writeframes(data)
            data = wrapped.getvalue()
            return data, "generated.wav"
        if "audio/mpeg" in mime_type or "audio/mp3" in mime_type:
            return data, "generated.mp3"
        if mime_type.startswith("audio/"):
            return data, "generated.wav"
        return data, "generated.mp4"
    url = output.get("download_url") or output.get("uri") or output.get("video_uri") or output.get("audio_uri")
    if not isinstance(url, str) or not url.startswith("https://"):
        raise ValueError("provider output has no permitted HTTPS download URL")
    with httpx.stream("GET", url, timeout=120, follow_redirects=False) as response:
        response.raise_for_status()
        content_length = int(response.headers.get("content-length", "0") or 0)
        if content_length > MAX_PROVIDER_BYTES:
            raise ValueError("provider media exceeds the bounded download limit")
        chunks: list[bytes] = []
        total = 0
        for chunk in response.iter_bytes(1024 * 1024):
            total += len(chunk)
            if total > MAX_PROVIDER_BYTES:
                raise ValueError("provider media exceeds the bounded download limit")
            chunks.append(chunk)
        suffix = ".wav" if "audio" in response.headers.get("content-type", "") else ".mp4"
        return b"".join(chunks), f"generated{suffix}"


def materialize(media_service: Any, project_id: str, output: Any, *, request_id: str, actor: str):
    data, filename = provider_bytes(output)
    return media_service.import_file(
        project_id, io.BytesIO(data), filename, None, request_id=request_id, actor=actor,
    )
