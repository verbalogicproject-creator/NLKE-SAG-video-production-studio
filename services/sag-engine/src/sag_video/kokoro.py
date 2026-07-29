"""Lazy, local Kokoro-82M ONNX narration adapter.

The adapter deliberately returns WAV bytes only to its caller.  Receipts use
the accompanying metadata, never the narration text or base64 encoded media.
"""
from __future__ import annotations

import hashlib
import json
import os
import subprocess
import time
import wave
from io import BytesIO
from pathlib import Path
from typing import Any, Callable


KOKORO_MODEL_ID = "kokoro-82m-onnx"
KOKORO_SAMPLE_RATE = 24_000
# The ONNX model accepts 510 phoneme tokens plus one pad token at each edge.
KOKORO_MAX_TOKENS = 510
KOKORO_DEFAULT_MODEL_DIR = "/storage/emulated/0/models/onnx/kokoro-82m-onnx"


def _sha256_bytes(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def _sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as source:
        for chunk in iter(lambda: source.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


class KokoroOnnxAdapter:
    """Synthesize mono PCM16 WAV with on-device Kokoro assets.

    Optional imports happen only at first synthesis, so regular engine startup
    and unit tests do not require either numpy or onnxruntime.
    """

    def __init__(
        self,
        model_dir: str | Path | None = None,
        *,
        session: Any | None = None,
        numpy_module: Any | None = None,
        phonemize: Callable[[str], str] | None = None,
    ):
        self.model_dir = Path(model_dir or os.getenv("SAG_KOKORO_MODEL_DIR") or KOKORO_DEFAULT_MODEL_DIR)
        self._session = session
        self._np = numpy_module
        self._phonemize_override = phonemize
        self._vocab: dict[str, int] | None = None
        self._voices: Any | None = None
        self._voice_names: set[str] | None = None

    @property
    def model_path(self) -> Path:
        return self.model_dir / "model.onnx"

    @property
    def tokenizer_path(self) -> Path:
        candidates = (self.model_dir / "tokenizer.json", self.model_dir / "tokenizer (1).json")
        return next((path for path in candidates if path.is_file()), candidates[0])

    @property
    def voices_path(self) -> Path:
        candidates = (
            self.model_dir / "voices_arrays.npz",
            self.model_dir / "voices.npz",
            self.model_dir / "voices.json",
        )
        return next((path for path in candidates if path.is_file()), candidates[0])

    def _require_assets(self) -> None:
        missing = [str(path) for path in (self.model_path, self.tokenizer_path, self.voices_path) if not path.is_file()]
        if missing:
            raise RuntimeError("Kokoro model assets are unavailable: " + ", ".join(missing))

    def _numpy(self) -> Any:
        if self._np is None:
            try:
                import numpy as np
            except ImportError as error:
                raise RuntimeError("numpy is required for local Kokoro narration") from error
            self._np = np
        return self._np

    def _load(self) -> None:
        self._require_assets()
        if self._vocab is None:
            try:
                payload = json.loads(self.tokenizer_path.read_text(encoding="utf-8"))
                vocab = payload["model"]["vocab"]
            except (OSError, ValueError, KeyError, TypeError) as error:
                raise RuntimeError("Kokoro tokenizer is malformed") from error
            if not isinstance(vocab, dict) or vocab.get("$") != 0 or not all(isinstance(key, str) and isinstance(value, int) for key, value in vocab.items()):
                raise RuntimeError("Kokoro tokenizer vocabulary is incompatible")
            self._vocab = vocab
        np = self._numpy()
        if self._voices is None:
            try:
                if self.voices_path.suffix == ".json":
                    raw_voices = json.loads(self.voices_path.read_text(encoding="utf-8"))
                    if not isinstance(raw_voices, dict):
                        raise ValueError("voice index is not an object")
                    self._voices = {
                        name: np.asarray(value, dtype=np.float32)
                        for name, value in raw_voices.items()
                        if isinstance(name, str)
                    }
                    self._voice_names = set(self._voices)
                else:
                    self._voices = np.load(self.voices_path, allow_pickle=False)
                    self._voice_names = set(self._voices.files)
            except Exception as error:
                raise RuntimeError("Kokoro compact voice vectors are malformed") from error
            if not self._voice_names:
                raise RuntimeError("Kokoro compact voice vectors contain no voices")
        if self._session is None:
            try:
                import onnxruntime as ort
            except ImportError as error:
                raise RuntimeError("onnxruntime is required for local Kokoro narration") from error
            options = ort.SessionOptions()
            options.inter_op_num_threads = 2
            options.intra_op_num_threads = 2
            self._session = ort.InferenceSession(str(self.model_path), options, providers=["CPUExecutionProvider"])

    def list_voices(self) -> list[str]:
        self._load()
        return sorted(self._voice_names or ())

    def _phonemize(self, text: str) -> str:
        if self._phonemize_override is not None:
            result = self._phonemize_override(text)
            if not isinstance(result, str) or not result.strip():
                raise RuntimeError("Kokoro phonemization produced no phonemes")
            return result
        try:
            result = subprocess.run(
                ["espeak-ng", "--ipa", "-q", "--sep=", "--", text], capture_output=True,
                text=True, timeout=10, check=False,
            )
        except (OSError, subprocess.TimeoutExpired) as error:
            raise RuntimeError("Kokoro phonemization failed") from error
        if result.returncode != 0 or not result.stdout.strip():
            raise RuntimeError("Kokoro phonemization failed")
        return " ".join(result.stdout.split())

    def _token_chunks(self, text: str) -> list[list[int]]:
        if not text.strip():
            raise ValueError("narration text must not be empty")
        phonemes = self._phonemize(text)
        assert self._vocab is not None
        unknown = sorted({character for character in phonemes if character not in self._vocab})
        if unknown:
            codepoints = ", ".join(f"U+{ord(character):04X}" for character in unknown[:12])
            raise RuntimeError(f"Kokoro phonemes contain tokenizer-incompatible code points: {codepoints}")
        tokens = [self._vocab[character] for character in phonemes if character != "$"]
        if not tokens:
            raise RuntimeError("Kokoro phonemes have no compatible tokenizer tokens")
        return [
            [0, *tokens[index:index + KOKORO_MAX_TOKENS], 0]
            for index in range(0, len(tokens), KOKORO_MAX_TOKENS)
        ]

    def synthesize(self, text: str, *, voice: str = "af") -> tuple[bytes, dict[str, Any]]:
        self._load()
        assert self._voices is not None and self._voice_names is not None and self._session is not None
        if voice not in self._voice_names:
            raise ValueError(f"unknown Kokoro voice: {voice}")
        voice_data = self._numpy().asarray(self._voices[voice], dtype=self._numpy().float32)
        if voice_data.ndim == 3 and voice_data.shape[1:] == (1, 256):
            voice_data = voice_data[:, 0, :]
        if getattr(voice_data, "ndim", 0) != 2 or voice_data.shape[0] < KOKORO_MAX_TOKENS or voice_data.shape[1] != 256:
            raise RuntimeError("Kokoro voice vector shape is incompatible")
        chunks = self._token_chunks(text)
        np = self._numpy()
        started = time.monotonic()
        pcm_parts: list[bytes] = []
        silence = b"\0\0" * round(KOKORO_SAMPLE_RATE * .1)
        for index, token_ids in enumerate(chunks):
            phoneme_token_count = len(token_ids) - 2
            style = voice_data[phoneme_token_count]
            try:
                output = self._session.run(None, {
                    "tokens": np.asarray([token_ids], dtype=np.int64),
                    "style": np.asarray(style, dtype=np.float32).reshape(1, 256),
                    "speed": np.asarray([1.0], dtype=np.float32),
                })[0]
            except Exception as error:
                raise RuntimeError("Kokoro ONNX inference failed") from error
            samples = np.asarray(output, dtype=np.float32).reshape(-1)
            if not samples.size:
                raise RuntimeError("Kokoro ONNX inference returned no audio")
            if not bool(np.isfinite(samples).all()):
                raise RuntimeError("Kokoro ONNX inference returned non-finite audio")
            if index:
                pcm_parts.append(silence)
            pcm_parts.append((np.clip(samples, -1.0, 1.0) * 32767.0).round().astype("<i2").tobytes())
        pcm = b"".join(pcm_parts)
        wav = BytesIO()
        with wave.open(wav, "wb") as writer:
            writer.setnchannels(1)
            writer.setsampwidth(2)
            writer.setframerate(KOKORO_SAMPLE_RATE)
            writer.writeframes(pcm)
        audio = wav.getvalue()
        duration = len(pcm) / (KOKORO_SAMPLE_RATE * 2)
        return audio, {
            "provider": "local", "model": KOKORO_MODEL_ID, "voice": voice,
            "text_sha256": _sha256_bytes(text.encode("utf-8")), "model_sha256": _sha256_file(self.model_path),
            "tokenizer_sha256": _sha256_file(self.tokenizer_path),
            "voice_sha256": _sha256_bytes(self._numpy().ascontiguousarray(voice_data).tobytes()),
            "output_sha256": _sha256_bytes(audio), "byte_size": len(audio), "duration_seconds": duration,
            "chunk_count": len(chunks), "phoneme_token_count": sum(len(chunk) - 2 for chunk in chunks),
            "sample_rate_hz": KOKORO_SAMPLE_RATE, "channels": 1,
            "runtime": {"engine": "onnxruntime", "inference_ms": round((time.monotonic() - started) * 1000, 1)},
        }
