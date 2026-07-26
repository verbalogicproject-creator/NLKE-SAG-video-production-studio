from sag_video.model_registry import MODEL_REGISTRY_VERSION, get_model, model_registry, model_registry_hash, validate_model_for


def test_registry_has_omni_veo_audio_and_music() -> None:
    ids = {entry["id"] for entry in model_registry()}
    assert "gemini-omni-flash-preview" in ids
    assert "veo-3.1-generate-preview" in ids
    assert "veo-3.1-lite-generate-preview" in ids
    assert "lyria-3-clip-preview" in ids
    assert "gemini-3.1-flash-tts-preview" in ids
    assert MODEL_REGISTRY_VERSION.startswith("google-gemini-")
    assert len(model_registry_hash()) == 64


def test_omni_is_default_for_conversational_video() -> None:
    model = validate_model_for("gemini-omni-flash-preview", "conversational_video_editing")
    assert "video_editing" in model.default_for


def test_unknown_or_incompatible_models_fail_closed() -> None:
    try:
        get_model("veo-3.0-generate-preview")
    except ValueError as error:
        assert "unsupported" in str(error)
    else:
        raise AssertionError("deprecated Veo 3.0 model unexpectedly accepted")

    try:
        validate_model_for("lyria-3-clip-preview", "video_generation")
    except ValueError as error:
        assert "does not support" in str(error)
    else:
        raise AssertionError("incompatible capability unexpectedly accepted")
