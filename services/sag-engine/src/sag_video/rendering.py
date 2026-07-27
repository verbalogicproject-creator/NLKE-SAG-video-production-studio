from __future__ import annotations

import hashlib
import os
import subprocess
import tempfile
import threading
import time
from pathlib import Path
from typing import Any, Callable, Literal
from uuid import uuid4

from pydantic import BaseModel, ConfigDict

from .models import CaptionStyle, ObservationContract, Project, Receipt, ReceiptStatus, TICKS_PER_SECOND
from .repository import ArtifactRecord, JobRecord
from .production_intelligence import QCCheck, QCReport
from .store import Store
from .blob_storage import BlobStorage, FilesystemBlobStorage, StorageLocator


class RenderValidationError(ValueError):
    pass


class RenderMediaSpec(BaseModel):
    model_config = ConfigDict(frozen=True)
    item_id: str
    asset_id: str
    kind: Literal["video", "audio", "image"]
    asset_sha256: str
    has_audio: bool
    start_seconds: float
    duration_seconds: float
    source_in_seconds: float
    fit_mode: str
    x: int
    y: int
    scale: float
    opacity: float
    rotation: float
    gain_db: float
    muted: bool
    source_width: int | None = None
    source_height: int | None = None
    crop_keyframes: tuple[dict, ...] = ()
    output_width: int | None = None
    output_height: int | None = None


class RenderTitleSpec(BaseModel):
    model_config = ConfigDict(frozen=True)
    item_id: str
    text: str
    start_seconds: float
    end_seconds: float
    x: int
    y: int
    width: int
    height: int
    color: str


class RenderCaptionSpec(BaseModel):
    model_config = ConfigDict(frozen=True)
    item_id: str
    words: tuple[dict, ...]
    style: dict


class RenderSpecification(BaseModel):
    model_config = ConfigDict(frozen=True)
    contract_version: str = "sag-render-0.2"
    project_id: str
    project_revision: int
    width: int
    height: int
    fps_numerator: int
    fps_denominator: int
    duration_seconds: float
    media: tuple[RenderMediaSpec, ...]
    titles: tuple[RenderTitleSpec, ...]
    captions: tuple[RenderCaptionSpec, ...] = ()

    @property
    def fps(self) -> float:
        return self.fps_numerator / self.fps_denominator


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as source:
        for chunk in iter(lambda: source.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _filter_path(path: Path) -> str:
    return str(path).replace("\\", "\\\\").replace(":", "\\:").replace("'", "\\'")


def _rgb(value: str) -> tuple[int, int, int]:
    value = value.lstrip("#")
    if len(value) == 3:
        value = "".join(character * 2 for character in value)
    try:
        return tuple(int(value[index:index + 2], 16) for index in (0, 2, 4))  # type: ignore[return-value]
    except (ValueError, TypeError):
        return (224, 160, 107)


def _ass_color(value: str) -> str:
    red, green, blue = _rgb(value[:7])
    alpha = 0
    if len(value.lstrip("#")) == 8:
        alpha = 255 - int(value.lstrip("#")[6:8], 16)
    return f"&H{alpha:02X}{blue:02X}{green:02X}{red:02X}"


def _ass_time(seconds: float) -> str:
    centiseconds = max(0, round(seconds * 100))
    hours, remainder = divmod(centiseconds, 360000)
    minutes, remainder = divmod(remainder, 6000)
    whole, fraction = divmod(remainder, 100)
    return f"{hours}:{minutes:02d}:{whole:02d}.{fraction:02d}"


def _ass_escape(value: str) -> str:
    return value.replace("\\", r"\\").replace("{", r"\{").replace("}", r"\}").replace("\n", r"\N")


def _keyframe_expression(keyframes: tuple[dict, ...], field: str, timeline_start: float) -> str:
    points = sorted(
        ((timeline_start + int(entry.get("time_ticks", 0)) / TICKS_PER_SECOND, float(entry.get(field, .5))) for entry in keyframes),
        key=lambda entry: entry[0],
    )
    if len(points) < 2:
        return f"{points[0][1] if points else .5:.8f}"
    expression = f"{points[-1][1]:.8f}"
    for index in range(len(points) - 2, -1, -1):
        start_t, start_value = points[index]
        end_t, end_value = points[index + 1]
        span = max(.000001, end_t - start_t)
        interpolation = f"{start_value:.8f}+({end_value - start_value:.8f})*(t-{start_t:.8f})/{span:.8f}"
        expression = f"if(lt(t,{end_t:.8f}),{interpolation},{expression})"
    return expression


def _write_ass(path: Path, captions: tuple[RenderCaptionSpec, ...], width: int, height: int) -> None:
    lines = [
        "[Script Info]", "ScriptType: v4.00+", f"PlayResX: {width}", f"PlayResY: {height}",
        "WrapStyle: 2", "ScaledBorderAndShadow: yes", "", "[V4+ Styles]",
        "Format: Name,Fontname,Fontsize,PrimaryColour,SecondaryColour,OutlineColour,BackColour,Bold,Italic,Underline,StrikeOut,ScaleX,ScaleY,Spacing,Angle,BorderStyle,Outline,Shadow,Alignment,MarginL,MarginR,MarginV,Encoding",
    ]
    for index, caption in enumerate(captions):
        style = CaptionStyle.model_validate(caption.style)
        alignment = {"top": 8, "middle": 5, "bottom": 2}[style.position]
        bold = -1 if style.preset in {"bold_pop", "glow_pulse"} else 0
        outline = 5 if style.preset == "bold_pop" else 3
        shadow = 4 if style.preset == "glow_pulse" else 1
        lines.append(
            f"Style: Caption{index},{style.font_family},{style.font_size},{_ass_color(style.text_color)},"
            f"{_ass_color(style.highlight_color)},&_H00000000,{_ass_color(style.background_color)},{bold},0,0,0,100,100,0,0,1,{outline},{shadow},{alignment},70,70,110,1".replace("&_H", "&H")
        )
    lines.extend(["", "[Events]", "Format: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text"])
    for index, caption in enumerate(captions):
        style = CaptionStyle.model_validate(caption.style)
        words = list(caption.words)
        for offset in range(0, len(words), style.words_per_cue):
            cue = words[offset:offset + style.words_per_cue]
            if not cue:
                continue
            start = int(cue[0]["start_ticks"]) / TICKS_PER_SECOND
            end = int(cue[-1]["end_ticks"]) / TICKS_PER_SECOND
            if style.preset == "typewriter_reveal":
                for word_index, word in enumerate(cue):
                    word_start = int(word["start_ticks"]) / TICKS_PER_SECOND
                    word_end = (
                        int(cue[word_index + 1]["start_ticks"]) / TICKS_PER_SECOND
                        if word_index + 1 < len(cue) else end
                    )
                    text = _ass_escape(" ".join(str(entry["text"]) for entry in cue[:word_index + 1]))
                    lines.append(
                        f"Dialogue: 0,{_ass_time(word_start)},{_ass_time(word_end)},Caption{index},,0,0,0,,{text}"
                    )
                continue
            if style.preset in {"karaoke", "bold_pop"}:
                text = " ".join(
                    f"{{\\kf{max(1,round((int(word['end_ticks'])-int(word['start_ticks']))/TICKS_PER_SECOND*100))}}}{_ass_escape(str(word['text']))}"
                    for word in cue
                )
            else:
                text = _ass_escape(" ".join(str(word["text"]) for word in cue))
            if style.preset == "glow_pulse":
                text = r"{\blur3\t(0,250,\fscx108\fscy108)\t(250,500,\fscx100\fscy100)}" + text
            lines.append(f"Dialogue: 0,{_ass_time(start)},{_ass_time(end)},Caption{index},,0,0,0,,{text}")
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


class RenderService:
    def __init__(
        self,
        store: Store,
        artifact_dir: str | Path,
        media_resolver: Callable[[Project, str], Path],
        observer: Callable[[ObservationContract], object],
        timeout_seconds: float = 180,
        blob_storage: BlobStorage | None = None,
    ):
        self.store = store
        self.artifact_dir = Path(artifact_dir).resolve()
        self.artifact_dir.mkdir(parents=True, exist_ok=True)
        self.media_resolver = media_resolver
        self.observer = observer
        self.blob_storage = blob_storage or FilesystemBlobStorage(self.artifact_dir / "storage")
        self.timeout_seconds = timeout_seconds

    def path_for_artifact(self, artifact: ArtifactRecord) -> Path:
        if artifact.storage_backend and artifact.storage_namespace and artifact.storage_key:
            return self.blob_storage.materialize(
                StorageLocator(
                    artifact.storage_backend, artifact.storage_namespace,
                    artifact.storage_key, artifact.storage_version,
                ),
                identity=artifact.id,
                expected_sha256=artifact.sha256,
            )
        path = (self.artifact_dir / f"{artifact.id}.mp4").resolve()
        if not path.is_relative_to(self.artifact_dir) or not path.is_file():
            raise FileNotFoundError(artifact.id)
        return path

    def build_spec(self, project: Project) -> RenderSpecification:
        media: list[RenderMediaSpec] = []
        titles: list[RenderTitleSpec] = []
        captions: list[RenderCaptionSpec] = []
        for track in project.tracks:
            for item in track.items:
                if item.kind in {"video", "audio", "image"}:
                    if not item.asset_id:
                        raise RenderValidationError(f"timeline item {item.id} has no asset")
                    try:
                        asset = project.asset(item.asset_id)
                    except KeyError as error:
                        raise RenderValidationError(f"timeline item {item.id} references a missing asset") from error
                    if asset.intake_status != "observed_valid" or not asset.managed_uri or not asset.sha256:
                        raise RenderValidationError(f"asset {asset.id} is not observed-valid managed media")
                    if item.kind == "video" and asset.kind != "video":
                        raise RenderValidationError(f"video item {item.id} does not reference video media")
                    if item.kind == "audio" and asset.kind != "audio":
                        raise RenderValidationError(f"audio item {item.id} does not reference audio media")
                    if item.kind == "image" and asset.kind != "image":
                        raise RenderValidationError(f"image item {item.id} does not reference image media")
                    source_out = item.source_in_ticks + item.duration_ticks
                    if item.kind != "image" and asset.duration_ticks and source_out > asset.duration_ticks:
                        raise RenderValidationError(f"item {item.id} exceeds the observed asset duration")
                    path = self.media_resolver(project, asset.id)
                    if not path.is_file() or _sha256(path) != asset.sha256:
                        raise RenderValidationError(f"asset {asset.id} bytes are missing or changed")
                    media.append(RenderMediaSpec(
                        item_id=item.id, asset_id=asset.id, kind=item.kind,
                        asset_sha256=asset.sha256, has_audio=bool(asset.audio_codec) or item.kind == "audio",
                        start_seconds=item.start_ticks / TICKS_PER_SECOND,
                        duration_seconds=item.duration_ticks / TICKS_PER_SECOND,
                        source_in_seconds=item.source_in_ticks / TICKS_PER_SECOND,
                        fit_mode=item.fit_mode, x=item.x, y=item.y, scale=item.scale,
                        opacity=item.opacity, rotation=item.rotation,
                        gain_db=item.gain_db, muted=item.muted,
                        source_width=asset.width, source_height=asset.height,
                        crop_keyframes=tuple(entry.model_dump(mode="json") for entry in item.crop_keyframes),
                        output_width=item.width, output_height=item.height,
                    ))
                elif item.kind == "title":
                    titles.append(RenderTitleSpec(
                        item_id=item.id, text=item.text or item.name,
                        start_seconds=item.start_ticks / TICKS_PER_SECOND,
                        end_seconds=(item.start_ticks + item.duration_ticks) / TICKS_PER_SECOND,
                        x=item.x, y=item.y, width=item.width, height=item.height, color=item.color,
                    ))
                elif item.kind == "caption" and item.caption_words:
                    captions.append(RenderCaptionSpec(
                        item_id=item.id,
                        words=tuple(entry.model_dump(mode="json") for entry in item.caption_words),
                        style=(item.caption_style or CaptionStyle()).model_dump(mode="json"),
                    ))
        if not any(entry.kind in {"video", "image"} for entry in media):
            raise RenderValidationError("the timeline needs at least one observed-valid visual item")
        if project.duration_ticks / TICKS_PER_SECOND > 600:
            raise RenderValidationError("phone renders are limited to ten minutes")
        return RenderSpecification(
            project_id=project.id, project_revision=project.revision,
            width=project.canvas.width, height=project.canvas.height,
            fps_numerator=project.canvas.fps_numerator,
            fps_denominator=project.canvas.fps_denominator,
            duration_seconds=project.duration_ticks / TICKS_PER_SECOND,
            media=tuple(media), titles=tuple(titles), captions=tuple(captions),
        )

    def _persist_qc_report(
        self, *, spec: RenderSpecification, artifact: ArtifactRecord, observation: Any,
    ) -> QCReport:
        result = observation.model_dump(mode="json")
        findings = {entry["code"]: entry for entry in result.get("findings", [])}

        def check(code: str, finding_code: str, detail: str, *, default: bool = False) -> QCCheck:
            finding = findings.get(finding_code)
            return QCCheck(
                code=code, passed=bool(finding["passed"]) if finding else default,
                observed=(finding or {}).get("evidence"), detail=(finding or {}).get("summary", detail),
            )

        has_audio = any(item.has_audio for item in spec.media)
        checks = [
            check("dimensions", "video_stream_contract", "Canvas dimensions were not observed"),
            check("duration", "duration_contract", "Duration was not observed"),
            check("frame_rate", "frame_rate_contract", "Frame rate was not observed"),
            check("representative_decode", "representative_frame_readable", "Representative decoding failed"),
            QCCheck(
                code="scene_coverage", passed=bool(spec.media),
                observed={"rendered_media_items": len(spec.media)}, expected={"minimum": 1},
                detail="Every frozen media item passed source validation before encoding",
            ),
            check("caption_readability", "caption_pixels_present", "Captions were not required", default=not bool(spec.captions)),
            QCCheck(
                code="caption_timing", passed=all(
                    all(int(word["end_ticks"]) > int(word["start_ticks"]) for word in caption.words)
                    for caption in spec.captions
                ),
                observed={"caption_tracks": len(spec.captions)},
                detail="Word timing is ordered and positive in the frozen render specification",
            ),
            check("safe_areas", "title_safe_area", "No title safe-area check required", default=not bool(spec.titles)),
            check("audio_presence", "audio_stream_contract", "Audio stream presence was not observed"),
            check("integrated_loudness", "integrated_loudness", "Integrated loudness was not required", default=not has_audio),
            check("true_peak", "true_peak", "True peak was not required", default=not has_audio),
            check("sha256", "artifact_hash_contract", "Artifact hash was not observed"),
        ]
        report = QCReport(
            id=f"qc_{artifact.id}", project_id=spec.project_id,
            project_revision=spec.project_revision, artifact_id=artifact.id,
            passed=all(entry.passed for entry in checks), checks=checks,
            artifact_sha256=artifact.sha256,
        )
        project = self.store.get_project(spec.project_id)
        try:
            self.store.put_editorial_record(
                record_id=report.id, kind="qc_report", body=report.model_dump(mode="json"),
                expected_revision=0, project_id=spec.project_id,
                workspace_id=project.workspace_id or project.id, append_only=True,
            )
        except ValueError:
            return QCReport.model_validate(self.store.get_editorial_record(report.id, kind="qc_report"))
        return report

    def enqueue(self, spec: RenderSpecification, receipt: Receipt, job_id: str) -> JobRecord:
        return self.store.create_job(JobRecord(
            id=job_id, project_id=spec.project_id, project_revision=spec.project_revision,
            kind="render", state="queued", progress=0,
            frozen_spec={"receipt_id": receipt.id, "render_spec": spec.model_dump(mode="json")},
        ))

    def _command(self, spec: RenderSpecification, project: Project, output: Path, work: Path) -> list[str]:
        command = ["ffmpeg", "-nostdin", "-y", "-v", "error"]
        for item in spec.media:
            if item.kind == "image":
                command.extend([
                    "-loop", "1", "-framerate", f"{spec.fps:.6f}",
                    "-t", f"{item.duration_seconds:.6f}",
                ])
            command.extend(["-i", str(self.media_resolver(project, item.asset_id))])
        filters: list[str] = [
            f"color=c=0x111315:s={spec.width}x{spec.height}:r={spec.fps:.6f}:d={spec.duration_seconds:.6f}[base0]"
        ]
        base = "base0"
        audio_labels: list[str] = []
        for index, item in enumerate(spec.media):
            end = item.source_in_seconds + item.duration_seconds
            if item.kind in {"video", "image"}:
                scaled_w = max(2, round(spec.width * item.scale / 2) * 2)
                scaled_h = max(2, round(spec.height * item.scale / 2) * 2)
                if item.crop_keyframes:
                    output_width = item.output_width or spec.width
                    output_height = item.output_height or spec.height
                    center_x = _keyframe_expression(item.crop_keyframes, "center_x", item.start_seconds)
                    center_y = _keyframe_expression(item.crop_keyframes, "center_y", item.start_seconds)
                    sizing = (
                        f"scale={output_width}:{output_height}:force_original_aspect_ratio=increase,"
                        f"crop={output_width}:{output_height}:"
                        f"x='max(0,min(iw-{output_width},({center_x})*iw-{output_width}/2))':"
                        f"y='max(0,min(ih-{output_height},({center_y})*ih-{output_height}/2))'"
                    )
                elif item.fit_mode == "fill":
                    sizing = f"scale={scaled_w}:{scaled_h}:force_original_aspect_ratio=increase,crop={scaled_w}:{scaled_h}"
                elif item.fit_mode == "stretch":
                    sizing = f"scale={scaled_w}:{scaled_h}"
                else:
                    sizing = f"scale={scaled_w}:{scaled_h}:force_original_aspect_ratio=decrease,pad={scaled_w}:{scaled_h}:(ow-iw)/2:(oh-ih)/2:color=black"
                rotation = "" if abs(item.rotation) < .001 else f",rotate={item.rotation:.6f}*PI/180:fillcolor=black@0"
                trim_start = 0.0 if item.kind == "image" else item.source_in_seconds
                trim_end = item.duration_seconds if item.kind == "image" else end
                filters.append(
                    f"[{index}:v:0]trim=start={trim_start:.6f}:end={trim_end:.6f},"
                    f"setpts=PTS-STARTPTS+{item.start_seconds:.6f}/TB,{sizing},setsar=1{rotation},"
                    f"format=rgba,colorchannelmixer=aa={item.opacity:.6f}[v{index}]"
                )
                next_base = f"base{index + 1}"
                filters.append(
                    f"[{base}][v{index}]overlay=x={item.x}:y={item.y}:eof_action=pass:shortest=0:"
                    f"enable='between(t,{item.start_seconds:.6f},{item.start_seconds + item.duration_seconds:.6f})'[{next_base}]"
                )
                base = next_base
            if item.has_audio:
                gain = -60 if item.muted else item.gain_db
                label = f"a{index}"
                filters.append(
                    f"[{index}:a:0]atrim=start={item.source_in_seconds:.6f}:end={end:.6f},"
                    f"asetpts=PTS-STARTPTS+{item.start_seconds:.6f}/TB,volume={gain:.3f}dB[{label}]"
                )
                audio_labels.append(label)
        for index, title in enumerate(spec.titles):
            text_path = work / f"title-{index}.txt"
            text_path.write_text(title.text, encoding="utf-8")
            next_base = f"titlebase{index}"
            enable = f"between(t,{title.start_seconds:.6f},{title.end_seconds:.6f})"
            filters.append(
                f"[{base}]drawbox=x={title.x}:y={title.y}:w={title.width}:h={title.height}:"
                f"color={title.color}:t=fill:enable='{enable}',"
                f"drawtext=textfile='{_filter_path(text_path)}':x={title.x + 22}:y={title.y + max(8, title.height // 3)}:"
                f"fontsize={max(12, title.height // 3)}:fontcolor=white:enable='{enable}'[{next_base}]"
            )
            base = next_base
        if spec.captions:
            captions_path = work / "captions.ass"
            _write_ass(captions_path, spec.captions, spec.width, spec.height)
            filters.append(f"[{base}]subtitles=filename='{_filter_path(captions_path)}'[captionbase]")
            base = "captionbase"
        if audio_labels:
            filters.append(
                f"{''.join(f'[{label}]' for label in audio_labels)}amix=inputs={len(audio_labels)}:"
                f"duration=longest:dropout_transition=0,atrim=0:{spec.duration_seconds:.6f},"
                "highpass=f=70,loudnorm=I=-16:TP=-1.5:LRA=11[aout]"
            )
        command.extend(["-filter_complex", ";".join(filters), "-map", f"[{base}]"])
        if audio_labels:
            command.extend(["-map", "[aout]", "-c:a", "aac", "-b:a", "160k"])
        else:
            command.append("-an")
        command.extend([
            "-t", f"{spec.duration_seconds:.6f}", "-r", f"{spec.fps:.6f}",
            "-c:v", "libx264", "-preset", "veryfast", "-crf", "21",
            "-pix_fmt", "yuv420p", "-movflags", "+faststart", str(output),
        ])
        return command

    def execute(self, job: JobRecord, *, defer_observation: bool = False) -> ArtifactRecord | None:
        receipt = self.store.get_receipt(str(job.frozen_spec["receipt_id"]))
        spec = RenderSpecification.model_validate(job.frozen_spec["render_spec"])
        project = self.store.get_project_revision(spec.project_id, spec.project_revision)
        artifact_id = f"artifact_{uuid4().hex[:16]}"
        final_path = self.artifact_dir / f"{artifact_id}.mp4"
        with tempfile.TemporaryDirectory(prefix=f"{job.id}-", dir=self.artifact_dir) as directory:
            work = Path(directory)
            temporary = work / "render.mp4"
            command = self._command(spec, project, temporary, work)
            receipt = self.store.update_receipt(receipt, ReceiptStatus.DISPATCHED, {
                "controller": "allowlisted-ffmpeg-controller-v0.2",
                "ffmpeg_arguments_hash": hashlib.sha256("\0".join(command[1:]).encode()).hexdigest(),
            })
            self.store.update_job(job.id, state="rendering", progress=.1)
            receipt = self.store.update_receipt(receipt, ReceiptStatus.RENDERING)
            process = subprocess.Popen(command, stdout=subprocess.DEVNULL, stderr=subprocess.PIPE)
            started = time.monotonic()
            while process.poll() is None:
                current = self.store.get_job(job.id)
                if current.cancellation_requested:
                    process.terminate()
                    try:
                        process.wait(timeout=3)
                    except subprocess.TimeoutExpired:
                        process.kill()
                    self.store.update_job(job.id, state="cancelled", progress=current.progress)
                    self.store.update_receipt(receipt, ReceiptStatus.CANCELLED, {"failure_stage": "controller"})
                    return
                if time.monotonic() - started > self.timeout_seconds:
                    process.kill()
                    self.store.update_job(job.id, state="timeout", error_code="render_timeout")
                    self.store.update_receipt(receipt, ReceiptStatus.TIMEOUT, {
                        "failure_stage": "controller", "timeout_seconds": self.timeout_seconds,
                    })
                    return
                time.sleep(.1)
            stderr = (process.stderr.read() if process.stderr else b"").decode(errors="replace")[-1600:]
            if process.returncode != 0 or not temporary.is_file():
                self.store.update_job(job.id, state="execution_failed", error_code="ffmpeg_nonzero", error_detail=stderr)
                self.store.update_receipt(receipt, ReceiptStatus.EXECUTION_FAILED, {
                    "failure_stage": "controller", "returncode": process.returncode, "stderr": stderr,
                })
                return
            os.replace(temporary, final_path)
        digest = _sha256(final_path)
        stored = self.blob_storage.put_immutable(
            final_path,
            workspace_id=project.workspace_id or spec.project_id,
            project_id=spec.project_id,
            identity=artifact_id,
            category="artifacts",
            content_type="video/mp4",
            expected_sha256=digest,
        )
        title = spec.titles[0] if spec.titles else None
        contract = ObservationContract(
            project_id=spec.project_id, project_revision=spec.project_revision,
            artifact_path=str(final_path), artifact_sha256=digest,
            width=spec.width, height=spec.height, duration_seconds=spec.duration_seconds,
            fps=spec.fps, title_id=title.item_id if title else None,
            title_active_seconds=(title.start_seconds + .2) if title else None,
            title_bounds=(title.x, title.y, title.width, title.height) if title else None,
            safe_margin_x=round(spec.width * .05), safe_margin_y=round(spec.height * .05),
            marker_rgb=_rgb(title.color) if title else None,
            expect_audio=any(item.has_audio for item in spec.media),
            expect_captions=bool(spec.captions),
        )
        artifact = self.store.create_artifact(ArtifactRecord(
            id=artifact_id, project_id=spec.project_id, job_id=job.id, asset_id=None,
            kind="rendered_video", managed_uri=f"sag-artifact://{artifact_id}", sha256=digest,
            byte_size=final_path.stat().st_size, mime_type="video/mp4",
            provenance={
                "project_revision": spec.project_revision,
                "render_contract": spec.contract_version,
                "observation_contract": contract.model_dump(mode="json", exclude={"artifact_path"}),
            },
            storage_backend=stored.locator.backend,
            storage_namespace=stored.locator.namespace,
            storage_key=stored.locator.key,
            storage_version=stored.locator.version,
        ))
        receipt = self.store.update_receipt(receipt, ReceiptStatus.ARTIFACT_WRITTEN, {
            "artifact_id": artifact.id, "artifact_sha256": digest,
            "artifact_url": f"/api/artifacts/{artifact.id}/content",
        })
        self.store.update_job(job.id, state="awaiting_observation", progress=.85, result_artifact_id=artifact.id)
        receipt = self.store.update_receipt(receipt, ReceiptStatus.AWAITING_OBSERVATION)
        if defer_observation:
            return artifact
        try:
            observation = self.observer(contract)
            payload = observation.model_dump(mode="json")
            payload["observer_deployment"] = os.getenv("SAG_VIDEO_OBSERVER_MODE", "in_process_development")
            qc_report = self._persist_qc_report(spec=spec, artifact=artifact, observation=observation)
            terminal = ReceiptStatus.OBSERVED_SUCCESS if observation.passed and qc_report.passed else ReceiptStatus.OBSERVED_FAILURE
            self.store.update_receipt(receipt, terminal, {
                "observation": payload, "qc_report_id": qc_report.id,
                "qc_report": qc_report.model_dump(mode="json"),
            })
            self.store.update_job(job.id, state=terminal.value, progress=1, result_artifact_id=artifact.id)
        except Exception as error:
            self.store.update_receipt(receipt, ReceiptStatus.OBSERVED_FAILURE, {
                "failure_stage": "observer", "observer_error": str(error), "inconclusive": True,
            })
            self.store.update_job(job.id, state="observed_failure", progress=1, error_code="observer_error", error_detail=str(error))
        return artifact


class RenderWorker:
    def __init__(self, store: Store, renderer: RenderService, worker_id: str = "local-phone-renderer"):
        self.store = store
        self.renderer = renderer
        self.worker_id = worker_id
        self._stop = threading.Event()
        self._thread: threading.Thread | None = None

    def start(self) -> None:
        self.store.recover_interrupted_jobs(self.worker_id)
        self._thread = threading.Thread(target=self._run, name=self.worker_id, daemon=True)
        self._thread.start()

    def stop(self) -> None:
        self._stop.set()
        if self._thread:
            self._thread.join(timeout=5)

    def _run(self) -> None:
        while not self._stop.is_set():
            job = self.store.claim_next_job(self.worker_id, ["render"])
            if job is None:
                self._stop.wait(.15)
                continue
            try:
                self.renderer.execute(job)
            except Exception as error:
                self.store.update_job(job.id, state="execution_failed", error_code="worker_error", error_detail=str(error))
                try:
                    receipt = self.store.get_receipt(str(job.frozen_spec["receipt_id"]))
                    self.store.update_receipt(receipt, ReceiptStatus.EXECUTION_FAILED, {
                        "failure_stage": "worker", "error": str(error),
                    })
                except Exception:
                    pass
