from __future__ import annotations

import shutil
import subprocess
from typing import Any


READ_ONLY_EXECUTABLES = {
    "ffmpeg": "ffmpeg",
    "ffprobe": "ffprobe",
    "termux_microphone": "termux-microphone-record",
    "termux_camera": "termux-camera-photo",
    "termux_sensors": "termux-sensor",
    "termux_share": "termux-share",
    "termux_media_scan": "termux-media-scan",
    "asciinema": "asciinema",
    "whisper_cpp": "whisper-cli",
}


def _first_version_line(executable: str) -> str | None:
    try:
        result = subprocess.run(
            [executable, "-version"],
            capture_output=True,
            check=False,
            timeout=3,
            text=True,
        )
    except (OSError, subprocess.TimeoutExpired):
        return None
    output = result.stdout or result.stderr
    return output.splitlines()[0][:240] if output else None


def _ffmpeg_filters(executable: str) -> set[str]:
    try:
        result = subprocess.run(
            [executable, "-hide_banner", "-filters"],
            capture_output=True,
            check=False,
            timeout=5,
            text=True,
        )
    except (OSError, subprocess.TimeoutExpired):
        return set()
    return {
        name
        for name in ("drawtext", "showwavespic", "loudnorm", "silencedetect", "subtitles", "crop")
        if name in result.stdout
    }


def detect_capabilities() -> dict[str, Any]:
    tools: dict[str, Any] = {}
    for capability, executable in READ_ONLY_EXECUTABLES.items():
        path = shutil.which(executable)
        tools[capability] = {
            "available": path is not None,
            "executable": executable,
            "detection_only": True,
        }
        if path and capability in {"ffmpeg", "ffprobe"}:
            tools[capability]["version"] = _first_version_line(path)
    ffmpeg_path = shutil.which("ffmpeg")
    filters = _ffmpeg_filters(ffmpeg_path) if ffmpeg_path else set()
    return {
        "tools": tools,
        "ffmpeg_filters": {name: name in filters for name in ("drawtext", "showwavespic", "loudnorm", "silencedetect", "subtitles", "crop")},
        "privacy": {
            "activated_device_capabilities": [],
            "note": "Detection checks executable presence only; it does not record, sample, scan, or share.",
        },
    }
