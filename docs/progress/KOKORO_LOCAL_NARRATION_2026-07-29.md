# Local Kokoro narration checkpoint

**Date:** 2026-07-29
**Scope:** the narration branch of `repo-to-video-1`; not a final mixed video

## Outcome

SAG Video now has a local, provider-neutral `kokoro-82m-onnx` narration path.
It is based on the proven AI-LAB lifecycle pattern, but it does not copy that
implementation's hard-coded path, stale embedded vocabulary, silent voice
fallback, raw-text phoneme fallback, or base64 pipeline payload.

The adapter:

- resolves `SAG_KOKORO_MODEL_DIR`, defaulting to
  `/storage/emulated/0/models/onnx/kokoro-82m-onnx`;
- lazily loads ONNX Runtime and NumPy so ordinary engine startup stays light;
- derives its vocabulary from the model's own tokenizer and fails closed on
  incompatible phoneme code points;
- validates the selected voice and compact `(511, 256)` voice-vector shape;
- applies the documented 510-phoneme-token context limit with pad tokens;
- creates 24 kHz mono PCM16 WAV bytes and sends them directly through canonical
  managed intake, never through JSON/base64;
- records input/model/tokenizer/voice/output hashes, byte size, duration,
  chunk/token counts, sample format, and bounded runtime metadata without
  recording the narration script;
- registers the observed-valid narration asset on the canonical Narration
  track during the exact human-confirmed repo-to-video generation flow.

## Independent smoke evidence

The on-device model synthesized:

> SAG Video turns repository evidence into a verified edit.

Observed output:

- output SHA-256:
  `124c904f76f351b952a70f4312ab1aa38b70f2e21f98e3c4980d4c37267fdd26`
- 264,044 bytes
- 5.500 seconds
- PCM s16le, 24,000 Hz, mono
- one chunk / 72 phoneme tokens
- 7,706 ms ONNX inference on the target Android/Termux device
- mean volume `-23.1 dB`; peak `-4.3 dB`
- detected silence only at the natural leading 0.594 seconds and trailing
  0.769 seconds

The temporary WAV was used only for local verification and is not a tracked
repository artifact.

## Regression protection

The first implementation draft exposed a critical float-to-PCM conversion
error: values in `[-1, 1]` were cast directly to `int16`, producing an almost
silent waveform even though the WAV container was valid. The accepted adapter
scales by 32767 before conversion. Its unit test now asserts substantial
positive and negative sample amplitude, so stream presence alone cannot hide
this failure again.

The full SAG Engine test suite passes. Focused coverage also proves:

- malformed tokenizers, unknown voices, unknown phonemes, non-finite output,
  empty output, and incompatible voice vectors fail closed;
- local HTTP synthesis creates an observed-valid managed asset without script
  or audio bytes in JSON;
- the repo-to-video dispatch records `provider=local`, materializes the exact
  narration asset, and inserts it on the canonical Narration track;
- the model registry and resolved prompt hash identify the local narration
  model explicitly.

## Still open for the 30-second acceptance video

This checkpoint fixes narration generation; it does not yet complete final
audio finishing. The next production slice must add:

1. voice, speed, pronunciation, and take-selection controls in Studio;
2. sentence-aware chunk boundaries and reviewed narration duration fitting;
3. word timestamps/captions or independent ASR transcript agreement;
4. a separately licensed and receipt-backed music asset;
5. semantic narration/music/ambience tracks with deterministic ducking;
6. final integrated loudness, true-peak, dropout, transcript, and human
   playback gates on the complete 30-second render.
