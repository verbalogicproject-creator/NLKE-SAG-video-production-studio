from __future__ import annotations

import hashlib
import shutil
from dataclasses import dataclass
from pathlib import Path
from typing import Protocol, runtime_checkable
from uuid import uuid4


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as source:
        for chunk in iter(lambda: source.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _safe(value: str) -> str:
    if not value or any(character not in "abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789_-" for character in value):
        raise ValueError("invalid storage identity")
    return value


@dataclass(frozen=True)
class StorageLocator:
    backend: str
    namespace: str
    key: str
    version: str | None = None


@dataclass(frozen=True)
class StoredBlob:
    locator: StorageLocator
    sha256: str
    byte_size: int
    content_type: str | None


@runtime_checkable
class BlobStorage(Protocol):
    def put_immutable(
        self,
        source: Path,
        *,
        workspace_id: str,
        project_id: str,
        identity: str,
        category: str,
        content_type: str | None,
        expected_sha256: str,
    ) -> StoredBlob: ...

    def materialize(self, locator: StorageLocator, *, identity: str, expected_sha256: str) -> Path: ...


class FilesystemBlobStorage:
    def __init__(self, root: str | Path, cache_dir: str | Path | None = None):
        self.root = Path(root).resolve()
        self.cache_dir = Path(cache_dir or self.root / ".cache").resolve()
        self.root.mkdir(parents=True, exist_ok=True)
        self.cache_dir.mkdir(parents=True, exist_ok=True)

    def put_immutable(
        self,
        source: Path,
        *,
        workspace_id: str,
        project_id: str,
        identity: str,
        category: str,
        content_type: str | None,
        expected_sha256: str,
    ) -> StoredBlob:
        digest = sha256_file(source)
        if digest != expected_sha256:
            raise ValueError("source hash changed before storage promotion")
        suffix = source.suffix.lower() or ".bin"
        key = "/".join(
            ("workspaces", _safe(workspace_id), "projects", _safe(project_id), _safe(category), _safe(identity), f"{digest}{suffix}")
        )
        destination = (self.root / key).resolve()
        if not destination.is_relative_to(self.root):
            raise ValueError("storage key escaped filesystem root")
        destination.parent.mkdir(parents=True, exist_ok=True)
        if destination.exists():
            if sha256_file(destination) != digest:
                raise ValueError("immutable filesystem object has different bytes")
        elif source.resolve() != destination:
            temporary = destination.with_suffix(f"{destination.suffix}.partial")
            shutil.copyfile(source, temporary)
            temporary.replace(destination)
        return StoredBlob(
            StorageLocator("filesystem", str(self.root), key, digest),
            digest,
            destination.stat().st_size,
            content_type,
        )

    def materialize(self, locator: StorageLocator, *, identity: str, expected_sha256: str) -> Path:
        if locator.backend != "filesystem" or Path(locator.namespace).resolve() != self.root:
            raise ValueError("storage locator belongs to another filesystem backend")
        path = (self.root / locator.key).resolve()
        if not path.is_relative_to(self.root) or not path.is_file():
            raise FileNotFoundError(identity)
        if sha256_file(path) != expected_sha256:
            raise ValueError("immutable filesystem object hash mismatch")
        return path


class GcsBlobStorage:
    def __init__(self, bucket: str, cache_dir: str | Path):
        try:
            from google.cloud import storage
        except ImportError as error:  # pragma: no cover - deployment dependency guard
            raise RuntimeError("GCS backend requires google-cloud-storage") from error
        self.client = storage.Client()
        self.bucket_name = bucket
        self.bucket = self.client.bucket(bucket)
        self.cache_dir = Path(cache_dir).resolve()
        self.cache_dir.mkdir(parents=True, exist_ok=True)

    def put_immutable(
        self,
        source: Path,
        *,
        workspace_id: str,
        project_id: str,
        identity: str,
        category: str,
        content_type: str | None,
        expected_sha256: str,
    ) -> StoredBlob:
        digest = sha256_file(source)
        if digest != expected_sha256:
            raise ValueError("source hash changed before GCS promotion")
        suffix = source.suffix.lower() or ".bin"
        key = "/".join(
            ("workspaces", _safe(workspace_id), "projects", _safe(project_id), _safe(category), _safe(identity), f"{digest}{suffix}")
        )
        staging_key = f"staging/{_safe(workspace_id)}/{uuid4().hex}"
        staging = self.bucket.blob(staging_key)
        staging.metadata = {"sha256": digest, "targetKey": key}
        try:
            staging.upload_from_filename(
                str(source), content_type=content_type, if_generation_match=0,
                checksum="crc32c",
            )
            staging.reload()
            try:
                blob = self.bucket.copy_blob(
                    staging, self.bucket, new_name=key, if_generation_match=0,
                )
            except Exception as error:
                # A retry may find the immutable destination created by the first attempt.
                if getattr(error, "code", None) != 412:
                    raise
                blob = self.bucket.blob(key)
        finally:
            try:
                if staging.generation:
                    staging.delete(if_generation_match=int(staging.generation))
            except Exception:
                # Lifecycle cleanup is the bounded fallback for abandoned staging objects.
                pass
        blob.reload()
        metadata_hash = (blob.metadata or {}).get("sha256")
        if metadata_hash and metadata_hash != digest:
            raise ValueError("immutable GCS object has different hash metadata")
        if not metadata_hash:
            verification = self.cache_dir / f"verify-{digest}"
            blob.download_to_filename(
                str(verification), if_generation_match=int(blob.generation), checksum="crc32c",
            )
            try:
                if sha256_file(verification) != digest:
                    raise ValueError("immutable GCS object has different bytes")
            finally:
                verification.unlink(missing_ok=True)
            blob.metadata = {**(blob.metadata or {}), "sha256": digest}
            blob.patch(if_generation_match=int(blob.generation))
            blob.reload()
        return StoredBlob(
            StorageLocator("gcs", self.bucket_name, key, str(blob.generation)),
            digest,
            int(blob.size or source.stat().st_size),
            content_type,
        )

    def materialize(self, locator: StorageLocator, *, identity: str, expected_sha256: str) -> Path:
        if locator.backend != "gcs" or locator.namespace != self.bucket_name or not locator.version:
            raise ValueError("storage locator belongs to another GCS backend")
        destination = (self.cache_dir / f"{_safe(identity)}-{expected_sha256}").resolve()
        if not destination.is_relative_to(self.cache_dir):
            raise ValueError("materialization path escaped cache root")
        if not destination.exists():
            temporary = destination.with_suffix(".partial")
            blob = self.bucket.blob(locator.key, generation=int(locator.version))
            blob.download_to_filename(str(temporary), if_generation_match=int(locator.version), checksum="crc32c")
            temporary.replace(destination)
        if sha256_file(destination) != expected_sha256:
            destination.unlink(missing_ok=True)
            raise ValueError("materialized GCS object hash mismatch")
        return destination
