from __future__ import annotations

import hashlib
import json
import mimetypes
import os
import re
import shutil
import subprocess
from pathlib import Path
from typing import BinaryIO, Any
from uuid import uuid4

from .models import Asset, MediaImportResult, Project, Receipt, ReceiptStatus, TICKS_PER_SECOND, utc_now
from .store import Store
from .repository import MediaBlobRecord
from .blob_storage import BlobStorage, FilesystemBlobStorage, StorageLocator, StoredBlob


ALLOWED_SUFFIXES = {
    ".mp4", ".m4v", ".mov", ".webm", ".mkv",
    ".m4a", ".mp3", ".wav", ".ogg", ".opus", ".aac",
}
DURATION_ERROR = "media duration is missing, zero, or exceeds the configured limit"


class MediaIntakeError(ValueError):
    pass


def sanitize_filename(value: str) -> str:
    name = Path(value or "upload").name
    name = re.sub(r"[^A-Za-z0-9._() -]+", "_", name).strip(" .")
    return name[:180] or "upload"


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as source:
        for chunk in iter(lambda: source.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _ratio(value: str | None) -> float:
    if not value or value in {"0/0", "N/A"}:
        return 0.0
    numerator, _, denominator = value.partition("/")
    try:
        return float(numerator) / float(denominator or 1)
    except (ValueError, ZeroDivisionError):
        return 0.0


class MediaService:
    def __init__(
        self,
        store: Store,
        media_dir: str | Path,
        proxy_dir: str | Path,
        *,
        upload_limit_bytes: int,
        blob_storage: BlobStorage | None = None,
        max_duration_seconds: float = 7200,
        max_pixels: int = 33_177_600,
        timeout_seconds: float = 90,
    ):
        self.store = store
        self.media_dir = Path(media_dir).resolve()
        self.proxy_dir = Path(proxy_dir).resolve()
        self.media_dir.mkdir(parents=True, exist_ok=True)
        self.proxy_dir.mkdir(parents=True, exist_ok=True)
        self.blob_storage = blob_storage or FilesystemBlobStorage(self.media_dir.parent / "storage")
        self.upload_limit_bytes = upload_limit_bytes
        self.max_duration_seconds = max_duration_seconds
        self.max_pixels = max_pixels
        self.timeout_seconds = timeout_seconds

    @staticmethod
    def _validate_id(value: str) -> str:
        if not re.fullmatch(r"[A-Za-z0-9_-]{1,120}", value):
            raise MediaIntakeError("invalid managed-media identity")
        return value

    def _asset_dir(self, root: Path, project_id: str, asset_id: str) -> Path:
        project_id = self._validate_id(project_id)
        asset_id = self._validate_id(asset_id)
        candidate = (root / project_id / asset_id).resolve()
        if not candidate.is_relative_to(root):
            raise MediaIntakeError("managed-media path escaped its configured root")
        return candidate

    def _managed_path(self, project_id: str, asset: Asset) -> Path:
        root = self.proxy_dir if asset.source_kind == "derived" else self.media_dir
        directory = self._asset_dir(root, project_id, asset.id)
        candidates = [entry for entry in directory.iterdir() if entry.is_file()] if directory.exists() else []
        if len(candidates) != 1:
            raise MediaIntakeError("managed artifact is missing or ambiguous")
        return candidates[0]

    def path_for_asset(self, project: Project, asset_id: str) -> Path:
        asset = project.asset(asset_id)
        if not asset.managed_uri:
            raise MediaIntakeError("asset has no managed media")
        if asset.blob_id:
            try:
                blob = self.store.get_media_blob(asset.blob_id)
                owner = self.store.get_project(blob.storage_project_id)
                owner_asset = owner.asset(blob.storage_asset_id)
            except KeyError as error:
                raise MediaIntakeError("content-addressed media blob is missing") from error
            if blob.storage_backend and blob.storage_namespace and blob.storage_key:
                try:
                    path = self.blob_storage.materialize(
                        StorageLocator(
                            blob.storage_backend, blob.storage_namespace, blob.storage_key, blob.storage_version,
                        ),
                        identity=blob.id,
                        expected_sha256=blob.sha256,
                    )
                except (FileNotFoundError, ValueError) as error:
                    raise MediaIntakeError("content-addressed media bytes are unavailable") from error
            else:
                path = self._managed_path(owner.id, owner_asset)
            if _sha256(path) != blob.sha256:
                raise MediaIntakeError("content-addressed media bytes changed")
            return path
        expected = f"sag-media://{asset.id}"
        if asset.managed_uri != expected:
            raise MediaIntakeError("invalid managed URI")
        return self._managed_path(project.id, asset)

    def _stage_stream(self, project_id: str, source: BinaryIO, suffix: str) -> tuple[Path, str, int]:
        staging = self._asset_dir(self.media_dir, project_id, "staging")
        staging.mkdir(parents=True, exist_ok=True)
        path = staging / f"upload-{uuid4().hex}{suffix}"
        digest = hashlib.sha256()
        byte_size = 0
        try:
            with path.open("xb") as destination:
                while True:
                    chunk = source.read(1024 * 1024)
                    if not chunk:
                        break
                    byte_size += len(chunk)
                    if byte_size > self.upload_limit_bytes:
                        raise MediaIntakeError(f"upload exceeds {self.upload_limit_bytes} byte limit")
                    digest.update(chunk)
                    destination.write(chunk)
            if byte_size == 0:
                raise MediaIntakeError("upload is empty")
            return path, digest.hexdigest(), byte_size
        except Exception:
            path.unlink(missing_ok=True)
            raise

    def _probe(self, path: Path) -> dict[str, Any]:
        try:
            result = subprocess.run(
                [
                    "ffprobe", "-v", "error", "-show_streams", "-show_format",
                    "-of", "json", str(path),
                ],
                capture_output=True,
                check=False,
                timeout=20,
                text=True,
            )
        except (OSError, subprocess.TimeoutExpired) as error:
            raise MediaIntakeError(f"ffprobe unavailable or timed out: {error}") from error
        if result.returncode != 0:
            raise MediaIntakeError("ffprobe could not read the uploaded media")
        try:
            probe = json.loads(result.stdout)
        except json.JSONDecodeError as error:
            raise MediaIntakeError("ffprobe returned malformed metadata") from error
        streams = probe.get("streams") or []
        if not streams or len(streams) > 8:
            raise MediaIntakeError("media must contain between one and eight readable streams")
        videos = [stream for stream in streams if stream.get("codec_type") == "video"]
        audios = [stream for stream in streams if stream.get("codec_type") == "audio"]
        if not videos and not audios:
            raise MediaIntakeError("media contains no supported video or audio stream")
        duration = 0.0
        for value in [probe.get("format", {}).get("duration"), *[stream.get("duration") for stream in streams]]:
            try:
                duration = max(duration, float(value or 0))
            except (TypeError, ValueError):
                continue
        if duration <= 0 or duration > self.max_duration_seconds:
            raise MediaIntakeError(DURATION_ERROR)
        if videos:
            width, height = int(videos[0].get("width") or 0), int(videos[0].get("height") or 0)
            if width <= 0 or height <= 0 or width * height > self.max_pixels:
                raise MediaIntakeError("video dimensions are missing or exceed the configured pixel limit")
        return {"probe": probe, "videos": videos, "audios": audios, "duration": duration}

    def _normalize_browser_webm(self, path: Path) -> None:
        """Finalize a bounded live WebM so ffprobe can observe its duration."""
        normalized = path.with_name(f"{path.stem}-normalized.webm")
        try:
            try:
                result = subprocess.run(
                    [
                        "ffmpeg", "-nostdin", "-y", "-v", "error", "-fflags", "+genpts",
                        "-i", str(path), "-map", "0:v:0?", "-map", "0:a:0?", "-c", "copy",
                        "-avoid_negative_ts", "make_zero", str(normalized),
                    ],
                    capture_output=True,
                    check=False,
                    timeout=self.timeout_seconds,
                    text=True,
                )
            except (OSError, subprocess.TimeoutExpired) as error:
                raise MediaIntakeError(f"browser capture normalization failed: {error}") from error
            if result.returncode != 0 or not normalized.is_file():
                raise MediaIntakeError("browser capture normalization failed")
            if normalized.stat().st_size > self.upload_limit_bytes:
                raise MediaIntakeError(f"upload exceeds {self.upload_limit_bytes} byte limit")
            os.replace(normalized, path)
        finally:
            normalized.unlink(missing_ok=True)

    def _run_ffmpeg(self, command: list[str]) -> None:
        try:
            result = subprocess.run(command, capture_output=True, check=False, timeout=self.timeout_seconds, text=True)
        except (OSError, subprocess.TimeoutExpired) as error:
            raise MediaIntakeError(f"media derivative generation failed: {error}") from error
        if result.returncode != 0:
            raise MediaIntakeError("media derivative generation failed")

    def _create_derivatives(
        self,
        project_id: str,
        source: Path,
        source_asset: Asset,
        has_video: bool,
    ) -> tuple[Asset, Asset]:
        proxy_id = f"asset_{uuid4().hex[:16]}"
        thumb_id = f"asset_{uuid4().hex[:16]}"
        proxy_dir = self._asset_dir(self.proxy_dir, project_id, proxy_id)
        thumb_dir = self._asset_dir(self.proxy_dir, project_id, thumb_id)
        proxy_dir.mkdir(parents=True)
        thumb_dir.mkdir(parents=True)
        proxy_path = proxy_dir / ("proxy.mp4" if has_video else "proxy.m4a")
        thumb_path = thumb_dir / "thumbnail.jpg"
        try:
            if has_video:
                self._run_ffmpeg([
                    "ffmpeg", "-nostdin", "-y", "-v", "error", "-i", str(source),
                    "-map", "0:v:0", "-map", "0:a:0?",
                    "-vf", "scale=960:540:force_original_aspect_ratio=decrease,scale=trunc(iw/2)*2:trunc(ih/2)*2",
                    "-c:v", "libx264", "-preset", "veryfast", "-crf", "27",
                    "-c:a", "aac", "-b:a", "128k", "-movflags", "+faststart", str(proxy_path),
                ])
                self._run_ffmpeg([
                    "ffmpeg", "-nostdin", "-y", "-v", "error", "-ss", "0",
                    "-i", str(source), "-frames:v", "1",
                    "-vf", "scale=480:270:force_original_aspect_ratio=decrease", str(thumb_path),
                ])
            else:
                self._run_ffmpeg([
                    "ffmpeg", "-nostdin", "-y", "-v", "error", "-i", str(source),
                    "-vn", "-c:a", "aac", "-b:a", "128k", str(proxy_path),
                ])
                self._run_ffmpeg([
                    "ffmpeg", "-nostdin", "-y", "-v", "error", "-i", str(source),
                    "-filter_complex", "showwavespic=s=480x270:colors=51e6c5",
                    "-frames:v", "1", str(thumb_path),
                ])
        except Exception:
            shutil.rmtree(proxy_dir, ignore_errors=True)
            shutil.rmtree(thumb_dir, ignore_errors=True)
            raise
        proxy_kind = "video" if has_video else "audio"
        proxy_asset = Asset(
            id=proxy_id,
            kind=proxy_kind,
            name=f"{source_asset.name} proxy",
            source_kind="derived",
            managed_uri=f"sag-media://{proxy_id}",
            sha256=_sha256(proxy_path),
            byte_size=proxy_path.stat().st_size,
            mime_type="video/mp4" if has_video else "audio/mp4",
            duration_ticks=source_asset.duration_ticks,
            parent_asset_id=source_asset.id,
        )
        thumbnail_asset = Asset(
            id=thumb_id,
            kind="image",
            name=f"{source_asset.name} thumbnail",
            source_kind="derived",
            managed_uri=f"sag-media://{thumb_id}",
            sha256=_sha256(thumb_path),
            byte_size=thumb_path.stat().st_size,
            mime_type="image/jpeg",
            parent_asset_id=source_asset.id,
        )
        return proxy_asset, thumbnail_asset

    def _failed(self, receipt: Receipt, reason: str) -> MediaImportResult:
        receipt = self.store.update_receipt(
            receipt,
            ReceiptStatus.OBSERVED_FAILURE,
            {
                "failure_stage": "media_intake",
                "observation": {
                    "kind": "managed_media_intake",
                    "independent_failure_domain": False,
                    "passed": False,
                    "findings": [{"code": "media_readable", "passed": False, "summary": reason}],
                },
            },
        )
        return MediaImportResult(receipt=receipt)

    def import_file(
        self,
        project_id: str,
        source: BinaryIO,
        original_filename: str,
        claimed_mime: str | None,
        request_id: str,
        actor: str,
        asset_id_override: str | None = None,
        source_storage_override: StoredBlob | None = None,
    ) -> MediaImportResult:
        duplicate = self.store.receipt_for_request(project_id, request_id)
        if duplicate:
            asset_id = duplicate.payload.get("asset_id")
            project = self.store.get_project(project_id)
            asset = project.asset(asset_id) if asset_id else None
            return MediaImportResult(receipt=duplicate, asset=asset)
        project = self.store.get_project(project_id)
        safe_name = sanitize_filename(original_filename)
        suffix = Path(safe_name).suffix.lower()
        if suffix not in ALLOWED_SUFFIXES:
            raise MediaIntakeError("unsupported media filename extension")
        receipt = self.store.create_receipt(
            project_id=project_id,
            command="asset.import",
            status=ReceiptStatus.ACCEPTED,
            request_id=request_id,
            actor=actor,
            project_revision=project.revision,
            payload={"original_filename": safe_name},
        )
        staged: Path | None = None
        source_dir: Path | None = None
        try:
            staged, digest, byte_size = self._stage_stream(project_id, source, suffix)
            incoming_sha256 = digest
            container_normalized = False
            try:
                details = self._probe(staged)
            except MediaIntakeError as error:
                if suffix != ".webm" or str(error) != DURATION_ERROR:
                    raise
                self._normalize_browser_webm(staged)
                digest = _sha256(staged)
                byte_size = staged.stat().st_size
                details = self._probe(staged)
                container_normalized = True
            video = details["videos"][0] if details["videos"] else None
            audio = details["audios"][0] if details["audios"] else None
            duplicate_asset = next(
                (
                    existing
                    for existing in project.assets
                    if existing.source_kind != "derived"
                    and existing.sha256 == digest
                    and existing.intake_status == "observed_valid"
                ),
                None,
            )
            if duplicate_asset:
                staged.unlink(missing_ok=True)
                staged = None
                receipt = self.store.update_receipt(
                    receipt,
                    ReceiptStatus.AWAITING_OBSERVATION,
                    {"asset_id": duplicate_asset.id, "artifact_sha256": digest, "deduplicated": True},
                )
                receipt = self.store.update_receipt(
                    receipt,
                    ReceiptStatus.OBSERVED_SUCCESS,
                    {
                        "asset_id": duplicate_asset.id,
                        "deduplicated": True,
                        "observation": {
                            "kind": "managed_media_intake",
                            "independent_failure_domain": False,
                            "passed": True,
                            "findings": [
                                {
                                    "code": "content_already_managed",
                                    "passed": True,
                                    "summary": "The exact SHA-256 bytes already belong to an observed-valid project asset.",
                                    "evidence": {"sha256": digest, "asset_id": duplicate_asset.id},
                                }
                            ],
                        },
                    },
                )
                return MediaImportResult(receipt=receipt, asset=duplicate_asset)
            asset_id = self._validate_id(asset_id_override) if asset_id_override else f"asset_{uuid4().hex[:16]}"
            kind = "video" if video else "audio"
            asset = Asset(
                id=asset_id,
                kind=kind,
                name=Path(safe_name).stem[:120] or "Imported media",
                source_kind="upload",
                managed_uri=f"sag-media://{asset_id}",
                original_filename=safe_name,
                sha256=digest,
                byte_size=byte_size,
                mime_type=mimetypes.guess_type(safe_name)[0] or ("video/mp4" if video else "audio/mp4"),
                duration_ticks=round(details["duration"] * TICKS_PER_SECOND),
                width=int(video.get("width")) if video else None,
                height=int(video.get("height")) if video else None,
                frame_rate=(video.get("avg_frame_rate") or video.get("r_frame_rate")) if video else None,
                video_codec=video.get("codec_name") if video else None,
                rotation=int((video.get("tags") or {}).get("rotate", 0)) if video else None,
                audio_codec=audio.get("codec_name") if audio else None,
                audio_channels=int(audio.get("channels")) if audio and audio.get("channels") else None,
                audio_sample_rate=int(audio.get("sample_rate")) if audio and audio.get("sample_rate") else None,
                intake_status="observed_valid",
                observation_summary={
                    "stream_count": len(details["probe"]["streams"]),
                    "duration_seconds": round(details["duration"], 6),
                    "has_video": bool(video),
                    "has_audio": bool(audio),
                    "claimed_mime_type": claimed_mime,
                    "container_normalized": container_normalized,
                    "incoming_sha256": incoming_sha256,
                },
            )
            source_dir = self._asset_dir(self.media_dir, project_id, asset_id)
            source_dir.mkdir(parents=True)
            final_source = source_dir / f"source{suffix}"
            os.replace(staged, final_source)
            staged = None
            proxy_asset, thumbnail_asset = self._create_derivatives(project_id, final_source, asset, bool(video))
            for managed_asset in (asset, proxy_asset, thumbnail_asset):
                managed_path = self._managed_path(project_id, managed_asset)
                stored = source_storage_override if managed_asset is asset and source_storage_override else self.blob_storage.put_immutable(
                    managed_path, workspace_id=project.workspace_id or project_id,
                    project_id=project_id, identity=managed_asset.id,
                    category="derived" if managed_asset.source_kind == "derived" else "media",
                    content_type=managed_asset.mime_type, expected_sha256=managed_asset.sha256 or "",
                )
                if stored.sha256 != managed_asset.sha256 or stored.byte_size != managed_asset.byte_size:
                    raise MediaIntakeError("promoted source storage differs from independently inspected bytes")
                blob = self.store.register_media_blob(MediaBlobRecord(
                    id=f"blob_{managed_asset.sha256[:24]}", sha256=managed_asset.sha256 or "",
                    byte_size=managed_asset.byte_size or 0, mime_type=managed_asset.mime_type,
                    storage_project_id=project_id, storage_asset_id=managed_asset.id,
                    storage_kind=managed_asset.source_kind,
                    storage_backend=stored.locator.backend,
                    storage_namespace=stored.locator.namespace,
                    storage_key=stored.locator.key,
                    storage_version=stored.locator.version,
                ))
                managed_asset.blob_id = blob.id
                managed_asset.managed_uri = f"sag-blob://{blob.id}"
                if (blob.storage_project_id,blob.storage_asset_id) != (project_id,managed_asset.id):
                    duplicate_path = self._managed_path(project_id,managed_asset)
                    duplicate_path.unlink(missing_ok=True)
                    duplicate_path.parent.rmdir()
            asset.proxy_asset_id = proxy_asset.id
            asset.thumbnail_asset_id = thumbnail_asset.id
            before = project.model_copy(deep=True)
            project.assets.extend([asset, proxy_asset, thumbnail_asset])
            project.revision += 1
            project.updated_at = utc_now()
            receipt.project_revision = project.revision
            with self.store._lock, self.store.transaction():
                self.store.put_project(project)
                self.store.append_event(
                    before=before,
                    after=project,
                    request_id=request_id,
                    actor=actor,
                    command="asset.import",
                    arguments={"asset_id": asset.id, "sha256": asset.sha256},
                )
                receipt = self.store.update_receipt(
                    receipt,
                    ReceiptStatus.AWAITING_OBSERVATION,
                    {"asset_id": asset.id, "artifact_sha256": asset.sha256},
                )
                receipt = self.store.update_receipt(
                    receipt,
                    ReceiptStatus.OBSERVED_SUCCESS,
                    {
                        "before_revision": before.revision,
                        "after_revision": project.revision,
                        "asset_id": asset.id,
                        "proxy_asset_id": proxy_asset.id,
                        "thumbnail_asset_id": thumbnail_asset.id,
                        "observation": {
                            "kind": "managed_media_intake",
                            "independent_failure_domain": False,
                            "passed": True,
                            "findings": [
                                {"code": "artifact_hash", "passed": True, "summary": "Uploaded bytes were hashed while copying.", "evidence": {"sha256": asset.sha256, "byte_size": byte_size}},
                                {"code": "media_readable", "passed": True, "summary": "ffprobe found supported readable streams.", "evidence": asset.observation_summary},
                                {"code": "derivatives_created", "passed": True, "summary": "A proxy and thumbnail were generated and hashed."},
                            ],
                        },
                    },
                )
            return MediaImportResult(receipt=receipt, asset=asset)
        except MediaIntakeError as error:
            if source_dir:
                shutil.rmtree(source_dir, ignore_errors=True)
            return self._failed(receipt, str(error))
        finally:
            if staged:
                staged.unlink(missing_ok=True)
