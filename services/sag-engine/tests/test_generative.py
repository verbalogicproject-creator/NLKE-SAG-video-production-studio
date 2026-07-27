import pytest

from sag_video.generative import GenerativeAudioRequest, GenerativeVideoRequest, GoogleGenerativeAdapter, HFInferenceVideoAdapter, ProviderOperation, _SdkClient, _inline_json_schema, _media_output, _text_output
from sag_video.repo_to_video import RepoStoryboard


class FakeClient:
    def start_video(self, *, model, request):
        assert model == "gemini-omni-flash-preview"
        return "operations/video-1"

    def start_audio(self, *, model, request):
        return "interactions/audio-1"

    def poll(self, *, operation_name):
        return {"state": "completed", "output": {"provider_uri": "provider://asset-1"}}


def test_omni_video_is_real_operation_not_fake_completion():
    adapter = GoogleGenerativeAdapter(client=FakeClient())
    operation = adapter.start_video(GenerativeVideoRequest(prompt="a quiet studio", model="gemini-omni-flash-preview"))
    assert operation.state == "pending"
    assert operation.operation_name == "operations/video-1"
    assert adapter.poll(operation).state == "completed"


def test_completed_inline_operation_is_returned_without_losing_media():
    class InlineClient(FakeClient):
        def start_video(self, *, model, request):
            return {
                "operation_name": "interactions/video-inline",
                "state": "completed",
                "output": {"data_base64": "bWVkaWE=", "mime_type": "video/mp4"},
            }

    operation = GoogleGenerativeAdapter(client=InlineClient()).start_video(
        GenerativeVideoRequest(prompt="a quiet studio", model="gemini-omni-flash-preview")
    )
    assert operation.state == "completed"
    assert operation.output == {"data_base64": "bWVkaWE=", "mime_type": "video/mp4"}


def test_missing_credentials_fail_closed():
    with pytest.raises(RuntimeError, match="not configured"):
        GoogleGenerativeAdapter(api_key="", backend="developer").start_video(GenerativeVideoRequest(prompt="test"))


def test_provider_quota_failure_is_classified_without_leaking_full_detail():
    class QuotaClient(FakeClient):
        def plan_text(self, *, model, prompt, response_schema=None):
            raise Exception("429 quota exceeded with verbose provider internals")

    with pytest.raises(RuntimeError, match="quota_failure") as failure:
        GoogleGenerativeAdapter(client=QuotaClient()).plan_text(model="gemini-omni-flash-preview", prompt="test")
    assert "verbose provider internals" not in str(failure.value)


def test_music_model_is_not_accepted_as_video():
    with pytest.raises(ValueError, match="does not support"):
        GoogleGenerativeAdapter(client=FakeClient()).start_video(GenerativeVideoRequest(prompt="test", model="lyria-3-clip-preview"))


def test_hf_fal_returns_bytes_with_hash_and_never_serializes_content():
    class HFClient:
        def text_to_video(self, prompt, *, model):
            assert prompt == "abstract evidence graph"
            assert model == "Wan-AI/Wan2.2-TI2V-5B"
            return b"video-bytes"

    result = HFInferenceVideoAdapter(client=HFClient()).generate_video(GenerativeVideoRequest(
        model="Wan-AI/Wan2.2-TI2V-5B", prompt="abstract evidence graph",
        duration_seconds=5, aspect_ratio="9:16",
    ))
    assert result.content == b"video-bytes"
    assert result.byte_size == 11
    assert "content" not in result.model_dump(mode="json")


def test_hf_fal_fails_closed_without_credentials(monkeypatch):
    monkeypatch.delenv("HF_TOKEN", raising=False)
    adapter = HFInferenceVideoAdapter(token="")
    with pytest.raises(RuntimeError, match="not configured"):
        adapter.generate_video(GenerativeVideoRequest(
            model="Wan-AI/Wan2.2-TI2V-5B", prompt="test", duration_seconds=5,
        ))


class SdkValue:
    def __init__(self, **values):
        self.__dict__.update(values)

    def model_dump(self, **_kwargs):
        return dict(self.__dict__)


def test_sdk_client_uses_preview_interaction_shapes(monkeypatch):
    monkeypatch.delenv("SAG_GOOGLE_VIDEO_GCS_URI", raising=False)
    interaction_calls = []
    interaction = SdkValue(id="interaction-1", status="completed", output_text="READY")
    interactions = SdkValue(create=lambda **kwargs: interaction_calls.append(kwargs) or interaction, get=lambda **_kwargs: interaction)
    operations = SdkValue(get=lambda **_kwargs: SdkValue(done=True, error=None, response=SdkValue(uri="https://media.example/video.mp4")))
    models = SdkValue(generate_videos=lambda **_kwargs: SdkValue(name="operations/video-1"))
    client = _SdkClient(SdkValue(interactions=interactions, operations=operations, models=models))
    assert client.plan_text(model="gemini-omni-flash-preview", prompt="test") == "READY"
    audio_start = client.start_audio(model="lyria-3-clip-preview", request=GenerativeAudioRequest(model="lyria-3-clip-preview", text="music"))
    assert audio_start["operation_name"] == "interactions/interaction-1"
    assert client.start_video(model="veo-3.1-lite-generate-preview", request=GenerativeVideoRequest(prompt="video")) == "operations/video-1"
    assert client.poll(operation_name="operations/video-1")["output"] == {"uri": "https://media.example/video.mp4"}
    omni_start = client.start_video(model="gemini-omni-flash-preview", request=GenerativeVideoRequest(prompt="video", aspect_ratio="9:16"))
    assert omni_start["operation_name"] == "interactions/interaction-1"
    assert interaction_calls[-1]["response_format"] == {"type": "video", "aspect_ratio": "9:16", "duration": "8s"}
    assert interaction_calls[-1]["generation_config"] == {"video_config": {"task": "text_to_video"}}


def test_sdk_client_uses_configured_vertex_gcs_delivery(monkeypatch):
    monkeypatch.setenv("SAG_GOOGLE_VIDEO_GCS_URI", "gs://video-output/acceptance")
    calls = []
    interaction = SdkValue(id="interaction-1", status="pending")
    client = _SdkClient(SdkValue(interactions=SdkValue(create=lambda **kwargs: calls.append(kwargs) or interaction)))
    client.start_video(
        model="gemini-omni-flash-preview",
        request=GenerativeVideoRequest(prompt="video", aspect_ratio="9:16", duration_seconds=6),
    )
    assert calls[-1]["response_format"] == {
        "type": "video", "aspect_ratio": "9:16", "duration": "6s",
        "delivery": "uri", "gcs_uri": "gs://video-output/acceptance/",
    }


def test_sdk_client_uses_structured_output_and_veo_negative_prompt():
    calls = []
    interaction = SdkValue(id="interaction-1", status="completed", output_text='{"ready":true}')
    interactions = SdkValue(create=lambda **kwargs: calls.append(kwargs) or interaction, get=lambda **_kwargs: interaction)
    models = SdkValue(generate_videos=lambda **kwargs: calls.append(kwargs) or SdkValue(name="operations/video-1"))
    client = _SdkClient(SdkValue(interactions=interactions, operations=SdkValue(), models=models))
    assert client.plan_text(model="gemini-omni-flash-preview", prompt="test", response_schema={"type": "object"}) == '{"ready":true}'
    assert calls[-1]["response_format"]["mime_type"] == "application/json"
    client.start_video(
        model="veo-3.1-generate-preview",
        request=GenerativeVideoRequest(prompt="video", negative_prompt="watermark, distorted text"),
    )
    assert calls[-1]["config"]["negative_prompt"] == "watermark, distorted text"


def test_structured_output_schema_inlines_pydantic_definitions():
    schema = _inline_json_schema(RepoStoryboard.model_json_schema())
    serialized = str(schema)
    assert "$defs" not in serialized
    assert "$ref" not in serialized
    assert "default" not in serialized
    assert "pattern" not in schema["properties"]["scenes"]["items"]["properties"]["id"]
    assert "exclusiveMinimum" not in serialized


def test_media_output_normalizes_inline_bytes():
    assert _media_output({"candidate": {"inline_data": {"data": b"media"}}}) == {"data_base64": "bWVkaWE=", "mime_type": ""}
    assert _media_output({"type": "audio", "mime_type": "audio/mpeg", "data": "bWVkaWE="}) == {
        "data_base64": "bWVkaWE=", "mime_type": "audio/mpeg",
    }


def test_text_output_uses_model_step_not_user_or_thought_text():
    value = {"steps": [
        {"type": "user_input", "content": [{"type": "text", "text": "secret prompt"}]},
        {"type": "thought", "content": [{"type": "text", "text": "internal"}]},
        {"type": "model_output", "content": [{"type": "text", "text": '{"ready":true}'}]},
    ]}
    assert _text_output(value) == '{"ready":true}'


def test_plan_text_retries_one_empty_completed_interaction():
    calls = []
    interactions = iter([
        SdkValue(id="empty", status="completed", output_text=""),
        SdkValue(id="ready", status="completed", output_text='{"ready":true}'),
    ])
    client = _SdkClient(SdkValue(interactions=SdkValue(
        create=lambda **kwargs: calls.append(kwargs) or next(interactions),
        get=lambda **_kwargs: SdkValue(id="empty", status="completed", output_text=""),
    )))
    assert client.plan_text(model="gemini-omni-flash-preview", prompt="test") == '{"ready":true}'
    assert len(calls) == 2
    assert "do not return an empty response" in calls[-1]["input"]
