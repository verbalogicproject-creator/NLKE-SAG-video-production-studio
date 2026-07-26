import base64

import pytest

from sag_video.generation_materializer import provider_bytes


def test_materializer_accepts_bounded_inline_bytes():
    data, filename = provider_bytes({"data_base64": base64.b64encode(b"media").decode()})
    assert data == b"media"
    assert filename.endswith(".mp4")


def test_materializer_preserves_encoded_audio_type_and_wraps_pcm():
    mp3, mp3_name = provider_bytes({
        "data_base64": base64.b64encode(b"encoded-mp3").decode(), "mime_type": "audio/mpeg",
    })
    assert mp3 == b"encoded-mp3"
    assert mp3_name.endswith(".mp3")
    wav, wav_name = provider_bytes({
        "data_base64": base64.b64encode(b"\x00\x00" * 240).decode(),
        "mime_type": "audio/L16;codec=pcm;rate=24000",
    })
    assert wav.startswith(b"RIFF")
    assert wav_name.endswith(".wav")


def test_materializer_rejects_non_https_urls():
    with pytest.raises(ValueError, match="HTTPS"):
        provider_bytes({"uri": "file:///tmp/media.mp4"})


def test_materializer_rejects_malformed_base64():
    with pytest.raises(ValueError, match="base64"):
        provider_bytes({"data_base64": "not base64"})
