from pathlib import Path

import pytest

from sag_video.blob_storage import FilesystemBlobStorage


def test_filesystem_blob_storage_is_immutable_and_hash_verified(tmp_path: Path):
    source = tmp_path / "source.mp4"
    source.write_bytes(b"durable-media")
    import hashlib

    digest = hashlib.sha256(source.read_bytes()).hexdigest()
    storage = FilesystemBlobStorage(tmp_path / "objects")
    stored = storage.put_immutable(
        source, workspace_id="workspace_1", project_id="project_1", identity="asset_1",
        category="media", content_type="video/mp4", expected_sha256=digest,
    )
    materialized = storage.materialize(stored.locator, identity="asset_1", expected_sha256=digest)
    assert materialized.read_bytes() == b"durable-media"
    materialized.write_bytes(b"tampered")
    with pytest.raises(ValueError, match="hash mismatch"):
        storage.materialize(stored.locator, identity="asset_1", expected_sha256=digest)


def test_filesystem_blob_storage_rejects_caller_controlled_identity(tmp_path: Path):
    source = tmp_path / "source"
    source.write_bytes(b"x")
    import hashlib

    with pytest.raises(ValueError, match="invalid storage identity"):
        FilesystemBlobStorage(tmp_path / "objects").put_immutable(
            source, workspace_id="../escape", project_id="project", identity="asset",
            category="media", content_type=None,
            expected_sha256=hashlib.sha256(b"x").hexdigest(),
        )
