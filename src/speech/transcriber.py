"""Local speech-to-text transcription using faster-whisper.

Design notes:
- Model is loaded once and reused (loading is the expensive part).
- Transcription failures (corrupt audio, model errors, OOM) are
  caught and reported as a TranscriptionResult rather than raised,
  so callers can show a safe error message instead of crashing.
- No raw audio is persisted here; callers decide whether/where to
  keep audio, and the project default is to never store it.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Optional

import numpy as np

try:
    from faster_whisper import WhisperModel
except Exception:  # pragma: no cover - exercised only without faster-whisper installed
    WhisperModel = None


@dataclass(frozen=True)
class TranscriptionResult:
    success: bool
    text: str = ""
    error_message: str = ""
    language: Optional[str] = None


class TranscriptionError(Exception):
    pass


class WhisperTranscriber:
    """Wraps a faster-whisper model for transcribing push-to-talk
    recordings. Thread-unsafe to call concurrently on the same
    instance (faster-whisper models aren't guaranteed reentrant); the
    app should only transcribe one recording at a time anyway, which
    matches the push-to-talk UX.
    """

    def __init__(
        self,
        model_size: str = "base",
        language: Optional[str] = "en",
        device: str = "cpu",
        compute_type: str = "int8",
    ):
        if WhisperModel is None:
            raise TranscriptionError(
                "faster-whisper is not installed. Run: pip install -r requirements.txt"
            )
        self.language = language
        try:
            self._model = WhisperModel(
                model_size, device=device, compute_type=compute_type
            )
        except Exception as exc:
            raise TranscriptionError(
                f"Failed to load Whisper model '{model_size}': {exc}"
            ) from exc

    def transcribe(
        self, audio: np.ndarray, sample_rate: int = 16000
    ) -> TranscriptionResult:
        """Transcribe a float32 mono audio array. Returns a result
        object rather than raising, so UI/workflow code can always
        display *something* safely."""
        if audio is None or audio.size == 0:
            return TranscriptionResult(
                success=False, error_message="No audio provided to transcribe."
            )
        if not np.any(audio):
            return TranscriptionResult(
                success=False, error_message="Audio contains only silence."
            )

        try:
            segments, info = self._model.transcribe(
                audio,
                language=self.language,
                beam_size=5,
                vad_filter=True,
            )
            text_parts = [segment.text.strip() for segment in segments]
            text = " ".join(part for part in text_parts if part).strip()
        except Exception as exc:
            return TranscriptionResult(
                success=False, error_message=f"Transcription failed: {exc}"
            )

        if not text:
            return TranscriptionResult(
                success=False,
                error_message="Transcription produced no recognizable speech.",
            )

        detected_language = getattr(info, "language", None)
        return TranscriptionResult(
            success=True, text=text, language=detected_language
        )
