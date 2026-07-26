import base64

import pytest

from sag_video.generation_materializer import provider_bytes


def test_materializer_accepts_bounded_inline_bytes():
    data, filename = provider_bytes({"data_base64": base64.b64encode(b"media").decode()})
    assert data == b"media"
    assert filename.endswith(".mp4")


def test_materializer_rejects_non_https_urls():
    with pytest.raises(ValueError, match="HTTPS"):
        provider_bytes({"uri": "file:///tmp/media.mp4"})


def test_materializer_rejects_malformed_base64():
    with pytest.raises(ValueError, match="base64"):
        provider_bytes({"data_base64": "not base64"})
