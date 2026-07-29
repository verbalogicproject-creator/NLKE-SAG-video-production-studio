import json
import struct
import wave
from io import BytesIO

import numpy as np
import pytest
from fastapi.testclient import TestClient

import sag_video.app as app_module
from sag_video.app import Settings, create_app
from sag_video.generative import ProviderOperation
from sag_video.models import ReceiptStatus
from sag_video.kokoro import KOKORO_MAX_TOKENS, KokoroOnnxAdapter


class FakeSession:
    def __init__(self):
        self.feeds = []

    def run(self, _outputs, feeds):
        self.feeds.append(feeds)
        return [np.array([0.0, 0.5, -0.5], dtype=np.float32)]


def _assets(tmp_path):
    (tmp_path / "model.onnx").write_bytes(b"model")
    (tmp_path / "tokenizer.json").write_text(json.dumps({"model": {"vocab": {"$": 0, "a": 1, "b": 2, " ": 3}}}))
    np.savez(tmp_path / "voices_arrays.npz", af=np.zeros((511, 256), dtype=np.float32))


def _wav_bytes() -> bytes:
    output = BytesIO()
    with wave.open(output, "wb") as wav:
        wav.setnchannels(1)
        wav.setsampwidth(2)
        wav.setframerate(24000)
        wav.writeframes(struct.pack("<2400h", *([4000, -4000] * 1200)))
    return output.getvalue()


class FakeKokoro:
    def synthesize(self, text, *, voice="af"):
        audio = _wav_bytes()
        return audio, {
            "provider": "local", "model": "kokoro-82m-onnx", "voice": voice,
            "text_sha256": "1" * 64, "model_sha256": "2" * 64,
            "tokenizer_sha256": "3" * 64, "voice_sha256": "4" * 64,
            "output_sha256": "5" * 64, "byte_size": len(audio), "duration_seconds": .1,
            "chunk_count": 1, "phoneme_token_count": 4, "sample_rate_hz": 24000,
            "channels": 1, "runtime": {"engine": "onnxruntime", "inference_ms": 1.0},
        }


def test_kokoro_uses_bundled_vocab_compact_voice_and_pcm_wav(tmp_path):
    _assets(tmp_path)
    session = FakeSession()
    adapter = KokoroOnnxAdapter(tmp_path, session=session, phonemize=lambda _text: "a" * 600)
    audio, telemetry = adapter.synthesize("reviewed narration", voice="af")
    with wave.open(BytesIO(audio), "rb") as wav:
        assert (wav.getnchannels(), wav.getsampwidth(), wav.getframerate()) == (1, 2, 24000)
        samples = struct.unpack(f"<{wav.getnframes()}h", wav.readframes(wav.getnframes()))
    assert max(samples) > 16_000
    assert min(samples) < -16_000
    assert telemetry["chunk_count"] == 2
    assert telemetry["phoneme_token_count"] == 600
    assert telemetry["text_sha256"] != "reviewed narration"
    assert "transcript" not in telemetry
    assert all(feed["tokens"].shape[1] <= KOKORO_MAX_TOKENS + 2 for feed in session.feeds)
    assert [feed["style"].shape for feed in session.feeds] == [(1, 256), (1, 256)]


def test_kokoro_rejects_unknown_voice_and_malformed_tokenizer(tmp_path):
    _assets(tmp_path)
    adapter = KokoroOnnxAdapter(tmp_path, session=FakeSession(), phonemize=lambda _text: "ab")
    with pytest.raises(ValueError, match="unknown Kokoro voice"):
        adapter.synthesize("hello", voice="missing")
    (tmp_path / "tokenizer.json").write_text('{"model":{"vocab":{"a":1}}}')
    with pytest.raises(RuntimeError, match="vocabulary is incompatible"):
        KokoroOnnxAdapter(tmp_path, session=FakeSession(), phonemize=lambda _text: "ab").synthesize("hello")


def test_kokoro_fails_closed_on_unknown_phoneme(tmp_path):
    _assets(tmp_path)
    adapter = KokoroOnnxAdapter(tmp_path, session=FakeSession(), phonemize=lambda _text: "a☃")
    with pytest.raises(RuntimeError, match="U\\+2603"):
        adapter.synthesize("hello")


def test_kokoro_supports_upstream_json_voice_fallback(tmp_path):
    (tmp_path / "model.onnx").write_bytes(b"model")
    (tmp_path / "tokenizer.json").write_text(json.dumps({"model": {"vocab": {"$": 0, "a": 1}}}))
    voice = np.zeros((511, 1, 256), dtype=np.float32)
    (tmp_path / "voices.json").write_text(json.dumps({"af": voice.tolist()}))
    adapter = KokoroOnnxAdapter(tmp_path, session=FakeSession(), phonemize=lambda _text: "a")
    audio, telemetry = adapter.synthesize("hello")
    assert audio.startswith(b"RIFF")
    assert telemetry["voice"] == "af"


def test_local_audio_endpoint_uses_managed_intake_without_audio_json(tmp_path, monkeypatch):
    monkeypatch.setattr(app_module, "KokoroOnnxAdapter", lambda _path: FakeKokoro())
    app = create_app(Settings(
        database_path=str(tmp_path / "sag.db"), artifact_dir=str(tmp_path / "artifacts"),
        media_dir=str(tmp_path / "media"), proxy_dir=str(tmp_path / "proxies"),
        start_analysis_worker=False, start_render_worker=False,
    ))
    with TestClient(app) as client:
        response = client.post("/api/projects/demo/generative/audio", json={
            "model": "kokoro-82m-onnx", "text": "Reviewed narration", "voice_name": "af",
        })
        assert response.status_code == 202, response.text
        body = response.json()
        assert body["receipt"]["status"] == "observed_success"
        assert body["asset"]["intake_status"] == "observed_valid"
        serialized = json.dumps(body)
        assert "Reviewed narration" not in serialized
        assert "data_base64" not in serialized


def test_repo_to_video_dispatches_local_narration_to_canonical_track(tmp_path, monkeypatch):
    class PendingGoogle:
        def start_video(self, request):
            return ProviderOperation(
                request_id="video", model=request.model, operation_name="interactions/video",
            )

        def start_audio(self, request):
            return ProviderOperation(
                request_id="music", model=request.model, operation_name="operations/music",
            )

    monkeypatch.setattr(app_module, "GoogleGenerativeAdapter", lambda: PendingGoogle())
    monkeypatch.setattr(app_module, "KokoroOnnxAdapter", lambda _path: FakeKokoro())
    app = create_app(Settings(
        database_path=str(tmp_path / "sag.db"), artifact_dir=str(tmp_path / "artifacts"),
        media_dir=str(tmp_path / "media"), proxy_dir=str(tmp_path / "proxies"),
        service_token="trusted-web", start_analysis_worker=False, start_render_worker=False,
    ))
    project = app.state.store.create_project("Local narration", "vertical_1080p", "workspace-1")
    storyboard = {
        "title": "Demo", "hook": "Hook", "call_to_action": "Inspect it", "evidence_revision": "evidence-1",
        "scenes": [{
            "id": "scene_one", "start_seconds": 0, "duration_seconds": 5, "purpose": "proof",
            "narration": "Reviewed proof", "visual_direction": "Show authentic proof",
            "evidence_refs": ["README.md"], "generation_model": "gemini-omni-flash-preview",
        }],
    }
    approval = app.state.store.create_receipt(
        project_id=project.id, command="media.propose_storyboard", status=ReceiptStatus.COMMITTED,
        request_id="approved_storyboard", actor="browser", project_revision=project.revision,
        payload={"evidence_revision": "evidence-1", "storyboard": storyboard},
    )
    confirmation = "human-confirmation-1234"
    with TestClient(app) as client:
        response = client.post(
            f"/api/projects/{project.id}/repo-to-video/generate",
            headers={
                "x-sag-service-token": "trusted-web", "x-sag-workspace-id": "workspace-1",
                "x-sag-human-confirmation": confirmation,
            },
            json={
                "storyboard_receipt_id": approval.id, "storyboard": storyboard,
                "creative_brief": {
                    "title": "Demo", "logline": "Proof", "audience_promise": "Learn", "tone": "precise",
                    "visual_language": "authentic", "narrative_arc": ["hook", "proof", "cta"],
                    "omni_prompt": "authentic UI", "veo_prompt": "controlled UI", "music_prompt": "pulse",
                    "narration_guidance": "clear", "evidence_revision": "evidence-1",
                },
                "expected_revision": project.revision, "confirmation_id": confirmation, "aspect_ratio": "9:16",
            },
        )
        assert response.status_code == 202, response.text
        narration = next(item for item in response.json()["operations"] if item["kind"] == "narration")
        assert narration["provider"] == "local"
        canonical = app.state.store.get_project(project.id)
        track = next(track for track in canonical.tracks if track.id == "track_audio")
        assert track.name == "Narration"
        assert track.items[0].asset_id == narration["asset_id"]
