from __future__ import annotations

import json
import hashlib
import subprocess
import re
from io import BytesIO
from pathlib import Path
from typing import Any

from PIL import Image

from .models import ObservationContract, ObservationFinding, ObservationResult


def _run(command: list[str], timeout: float = 30) -> subprocess.CompletedProcess[bytes]:
    return subprocess.run(command, capture_output=True, check=False, timeout=timeout)


def _ratio(value: str | None) -> float:
    try:
        numerator, denominator = (value or "0/1").split("/", 1)
        return float(numerator) / float(denominator)
    except (ValueError, ZeroDivisionError):
        return 0


def observe_artifact(contract: ObservationContract) -> ObservationResult:
    findings: list[ObservationFinding] = []
    artifact = Path(contract.artifact_path)
    if not artifact.exists():
        return ObservationResult(
            passed=False,
            findings=[ObservationFinding(code="artifact_exists", passed=False, summary="Rendered artifact is missing")],
        )

    observed_sha256 = hashlib.sha256(artifact.read_bytes()).hexdigest()
    hash_passed = observed_sha256 == contract.artifact_sha256
    findings.append(
        ObservationFinding(
            code="artifact_hash_contract",
            passed=hash_passed,
            summary="Artifact hash matches the controller handoff" if hash_passed else "Artifact changed after the controller handoff",
            evidence={"observed_sha256": observed_sha256, "expected_sha256": contract.artifact_sha256},
        )
    )

    probe = _run(
        [
            "ffprobe",
            "-v",
            "error",
            "-show_entries",
            "format=duration:stream=codec_type,width,height,r_frame_rate,codec_name,channels,sample_rate",
            "-of",
            "json",
            str(artifact),
        ]
    )
    if probe.returncode != 0:
        return ObservationResult(
            passed=False,
            findings=[
                ObservationFinding(
                    code="artifact_probe",
                    passed=False,
                    summary="ffprobe could not read the rendered artifact",
                    evidence={"stderr": probe.stderr.decode(errors="replace")[-500:]},
                )
            ],
        )

    metadata: dict[str, Any] = json.loads(probe.stdout)
    video = next((stream for stream in metadata.get("streams", []) if stream.get("codec_type") == "video"), None)
    stream_passed = bool(video and video.get("width") == contract.width and video.get("height") == contract.height)
    findings.append(
        ObservationFinding(
            code="video_stream_contract",
            passed=stream_passed,
            summary="Video stream matches the requested canvas" if stream_passed else "Video stream does not match the requested canvas",
            evidence={"observed": video, "expected_width": contract.width, "expected_height": contract.height},
        )
    )

    observed_fps = _ratio(video.get("r_frame_rate") if video else None)
    fps_passed = bool(video and abs(observed_fps - contract.fps) <= .05)
    findings.append(ObservationFinding(
        code="frame_rate_contract", passed=fps_passed,
        summary="Frame rate matches the render specification" if fps_passed else "Frame rate does not match the render specification",
        evidence={"observed_fps": observed_fps, "expected_fps": contract.fps},
    ))

    audio = next((stream for stream in metadata.get("streams", []) if stream.get("codec_type") == "audio"), None)
    audio_passed = bool(audio) if contract.expect_audio else audio is None
    findings.append(ObservationFinding(
        code="audio_stream_contract", passed=audio_passed,
        summary="Audio stream presence matches the render specification" if audio_passed else "Audio stream presence does not match the render specification",
        evidence={"expected_audio": contract.expect_audio, "observed": audio},
    ))
    if contract.expect_audio and audio:
        loudness = _run([
            "ffmpeg", "-nostdin", "-i", str(artifact), "-filter_complex",
            "ebur128=framelog=verbose", "-f", "null", "-",
        ], timeout=60)
        matches = re.findall(rb"I:\s*(-?\d+(?:\.\d+)?)\s*LUFS", loudness.stderr)
        integrated = float(matches[-1]) if matches else None
        loudness_passed = integrated is not None and -19.0 <= integrated <= -13.0
        findings.append(ObservationFinding(
            code="integrated_loudness", passed=loudness_passed,
            summary="Integrated loudness is inside the delivery range" if loudness_passed else "Integrated loudness is missing or outside the delivery range",
            evidence={"integrated_lufs": integrated, "minimum_lufs": -19.0, "maximum_lufs": -13.0},
        ))

    observed_duration = float(metadata.get("format", {}).get("duration", 0))
    duration_passed = abs(observed_duration - contract.duration_seconds) <= max(0.15, 2 / contract.fps)
    findings.append(
        ObservationFinding(
            code="duration_contract",
            passed=duration_passed,
            summary="Artifact duration is within tolerance" if duration_passed else "Artifact duration is outside tolerance",
            evidence={"observed_seconds": observed_duration, "expected_seconds": contract.duration_seconds},
        )
    )

    frame = _run(
        [
            "ffmpeg",
            "-v",
            "error",
            "-ss",
            f"{(contract.title_active_seconds if contract.title_active_seconds is not None else contract.duration_seconds / 2):.3f}",
            "-i",
            str(artifact),
            "-frames:v",
            "1",
            "-f",
            "image2pipe",
            "-vcodec",
            "png",
            "-",
        ]
    )
    if frame.returncode != 0 or not frame.stdout:
        findings.append(
            ObservationFinding(
                code="representative_frame_readable",
                passed=False,
                summary="Observer could not decode a representative output frame",
                evidence={"stderr": frame.stderr.decode(errors="replace")[-500:]},
            )
        )
        return ObservationResult(passed=False, findings=findings)

    image = Image.open(BytesIO(frame.stdout)).convert("RGB")
    findings.append(ObservationFinding(
        code="representative_frame_readable", passed=True,
        summary="Observer decoded a representative output frame",
        evidence={"width": image.width, "height": image.height},
    ))
    if contract.expect_captions:
        lower = image.crop((0, image.height // 2, image.width, image.height))
        bright_pixels = sum(1 for red, green, blue in lower.getdata() if max(red, green, blue) >= 210)
        caption_passed = bright_pixels >= max(100, image.width * image.height // 2000)
        findings.append(ObservationFinding(
            code="caption_pixels_present", passed=caption_passed,
            summary="Caption-like high-contrast pixels are present" if caption_passed else "Expected caption pixels were not detected",
            evidence={"bright_pixels": bright_pixels, "sample_region": "lower_half"},
        ))
    if contract.title_id is None or contract.marker_rgb is None:
        return ObservationResult(passed=all(finding.passed for finding in findings), findings=findings)
    expected = contract.marker_rgb
    points: list[tuple[int, int]] = []
    for y in range(image.height):
        for x in range(image.width):
            red, green, blue = image.getpixel((x, y))
            if all(abs(observed - wanted) <= 55 for observed, wanted in zip((red, green, blue), expected)):
                points.append((x, y))

    marker_found = len(points) >= 100
    findings.append(
        ObservationFinding(
            code="title_marker_visible",
            passed=marker_found,
            summary="Expected title plate is visible in the encoded frame" if marker_found else "Expected title plate was not detected in the encoded frame",
            evidence={"matching_pixels": len(points), "title_id": contract.title_id},
        )
    )
    if marker_found:
        xs = [point[0] for point in points]
        ys = [point[1] for point in points]
        bounds = {"left": min(xs), "top": min(ys), "right": max(xs), "bottom": max(ys)}
        safe = {
            "left": contract.safe_margin_x,
            "top": contract.safe_margin_y,
            "right": contract.width - contract.safe_margin_x - 1,
            "bottom": contract.height - contract.safe_margin_y - 1,
        }
        inside = (
            bounds["left"] >= safe["left"]
            and bounds["top"] >= safe["top"]
            and bounds["right"] <= safe["right"]
            and bounds["bottom"] <= safe["bottom"]
        )
        findings.append(
            ObservationFinding(
                code="title_safe_area",
                passed=inside,
                summary="Observed title is inside the safe area" if inside else "Observed title is clipped or outside the safe area",
                evidence={"observed_bounds": bounds, "safe_bounds": safe, "source": "decoded_output_frame"},
            )
        )

    return ObservationResult(passed=all(finding.passed for finding in findings), findings=findings)
