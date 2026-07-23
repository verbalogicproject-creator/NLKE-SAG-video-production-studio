from __future__ import annotations

import subprocess
from pathlib import Path


def tiny_video(path: Path, *, duration: float = 1.0) -> Path:
    subprocess.run(
        [
            "ffmpeg", "-nostdin", "-y", "-v", "error",
            "-f", "lavfi", "-i", f"color=c=0x17213a:s=320x180:r=30:d={duration}",
            "-f", "lavfi", "-i", f"sine=frequency=440:sample_rate=48000:duration={duration}",
            "-shortest", "-c:v", "libx264", "-pix_fmt", "yuv420p",
            "-c:a", "aac", "-movflags", "+faststart", str(path),
        ],
        check=True,
        capture_output=True,
        timeout=30,
    )
    return path


def tiny_audio(path: Path, *, duration: float = 0.6) -> Path:
    subprocess.run(
        [
            "ffmpeg", "-nostdin", "-y", "-v", "error",
            "-f", "lavfi", "-i", f"sine=frequency=660:sample_rate=48000:duration={duration}",
            "-c:a", "aac", str(path),
        ],
        check=True,
        capture_output=True,
        timeout=30,
    )
    return path
