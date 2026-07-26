import pytest

from sag_video.generative import GenerativeAudioRequest, GenerativeVideoRequest, GoogleGenerativeAdapter, ProviderOperation, _SdkClient, _media_output


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


def test_missing_credentials_fail_closed():
    with pytest.raises(RuntimeError, match="not configured"):
        GoogleGenerativeAdapter(api_key="").start_video(GenerativeVideoRequest(prompt="test"))


def test_music_model_is_not_accepted_as_video():
    with pytest.raises(ValueError, match="does not support"):
        GoogleGenerativeAdapter(client=FakeClient()).start_video(GenerativeVideoRequest(prompt="test", model="lyria-3-clip-preview"))


class SdkValue:
    def __init__(self, **values):
        self.__dict__.update(values)

    def model_dump(self, **_kwargs):
        return dict(self.__dict__)


def test_sdk_client_uses_preview_interaction_shapes():
    interaction_calls = []
    interaction = SdkValue(id="interaction-1", status="completed", output_text="READY")
    interactions = SdkValue(create=lambda **kwargs: interaction_calls.append(kwargs) or interaction, get=lambda **_kwargs: interaction)
    operations = SdkValue(get=lambda **_kwargs: SdkValue(done=True, error=None, response=SdkValue(uri="https://media.example/video.mp4")))
    models = SdkValue(generate_videos=lambda **_kwargs: SdkValue(name="operations/video-1"))
    client = _SdkClient(SdkValue(interactions=interactions, operations=operations, models=models))
    assert client.plan_text(model="gemini-omni-flash-preview", prompt="test") == "READY"
    assert client.start_audio(model="lyria-3-clip-preview", request=GenerativeAudioRequest(model="lyria-3-clip-preview", text="music")) == "interactions/interaction-1"
    assert client.start_video(model="veo-3.1-lite-generate-preview", request=GenerativeVideoRequest(prompt="video")) == "operations/video-1"
    assert client.poll(operation_name="operations/video-1")["output"] == {"uri": "https://media.example/video.mp4"}
    client.start_video(model="gemini-omni-flash-preview", request=GenerativeVideoRequest(prompt="video", aspect_ratio="9:16"))
    assert interaction_calls[-1]["response_format"] == {"type": "video", "aspect_ratio": "9:16", "delivery": "uri"}
    assert interaction_calls[-1]["generation_config"] == {"video_config": {"task": "text_to_video"}}


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


def test_media_output_normalizes_inline_bytes():
    assert _media_output({"candidate": {"inline_data": {"data": b"media"}}}) == {"data_base64": "bWVkaWE="}
