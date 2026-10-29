"""Unit tests for WhisperTranscriber using a fake model, so these run
without downloading real model weights or touching the audio stack.
"""
from __future__ import annotations

import numpy as np
import pytest

from src.speech import transcriber as tr


class FakeSegment:
    def __init__(self, text):
        self.text = text


class FakeInfo:
    def __init__(self, language="en"):
        self.language = language


class FakeWhisperModel:
    def __init__(self, model_size, device, compute_type, fail_on_init=False):
        if fail_on_init:
            raise RuntimeError("simulated model load failure")
        self.model_size = model_size

    def transcribe(self, audio, language, beam_size, vad_filter):
        if getattr(self, "_raise_on_transcribe", False):
            raise RuntimeError("simulated transcription failure")
        segments = getattr(self, "_segments", [FakeSegment("candidate zero zero three zero three score thirty")])
        return segments, FakeInfo(language=language or "en")


def _make_fake_model_cls(segments=None, raise_on_transcribe=False, fail_on_init=False):
    def factory(model_size, device, compute_type):
        model = FakeWhisperModel(model_size, device, compute_type, fail_on_init=fail_on_init)
        if segments is not None:
            model._segments = segments
        model._raise_on_transcribe = raise_on_transcribe
        return model
    return factory


def test_transcribe_happy_path(monkeypatch):
    monkeypatch.setattr(tr, "WhisperModel", _make_fake_model_cls())
    transcriber = tr.WhisperTranscriber(model_size="base")
    audio = np.ones(16000, dtype=np.float32) * 0.1

    result = transcriber.transcribe(audio)
    assert result.success
    assert "candidate" in result.text.lower()
    assert result.language == "en"


def test_transcribe_empty_audio(monkeypatch):
    monkeypatch.setattr(tr, "WhisperModel", _make_fake_model_cls())
    transcriber = tr.WhisperTranscriber(model_size="base")

    result = transcriber.transcribe(np.array([], dtype=np.float32))
    assert not result.success
    assert "no audio" in result.error_message.lower()


def test_transcribe_silent_audio(monkeypatch):
    monkeypatch.setattr(tr, "WhisperModel", _make_fake_model_cls())
    transcriber = tr.WhisperTranscriber(model_size="base")

    result = transcriber.transcribe(np.zeros(16000, dtype=np.float32))
    assert not result.success
    assert "silence" in result.error_message.lower()


def test_transcribe_model_raises_is_caught(monkeypatch):
    monkeypatch.setattr(
        tr, "WhisperModel", _make_fake_model_cls(raise_on_transcribe=True)
    )
    transcriber = tr.WhisperTranscriber(model_size="base")
    audio = np.ones(16000, dtype=np.float32) * 0.1

    result = transcriber.transcribe(audio)
    assert not result.success
    assert "transcription failed" in result.error_message.lower()


def test_transcribe_no_speech_detected(monkeypatch):
    monkeypatch.setattr(tr, "WhisperModel", _make_fake_model_cls(segments=[]))
    transcriber = tr.WhisperTranscriber(model_size="base")
    audio = np.ones(16000, dtype=np.float32) * 0.1

    result = transcriber.transcribe(audio)
    assert not result.success
    assert "no recognizable speech" in result.error_message.lower()


def test_model_load_failure_raises_transcription_error(monkeypatch):
    monkeypatch.setattr(
        tr, "WhisperModel", _make_fake_model_cls(fail_on_init=True)
    )
    with pytest.raises(tr.TranscriptionError):
        tr.WhisperTranscriber(model_size="base")


def test_missing_faster_whisper_raises(monkeypatch):
    monkeypatch.setattr(tr, "WhisperModel", None)
    with pytest.raises(tr.TranscriptionError):
        tr.WhisperTranscriber(model_size="base")
