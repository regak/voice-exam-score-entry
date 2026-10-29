"""Tests for the speech -> command glue layer, using fakes for the
recorder and transcriber so no real microphone/model is involved.
"""
from __future__ import annotations

import numpy as np

from src.audio.push_to_talk import RecordingResult
from src.commands.schema import SetScoreCommand, UnrecognizedCommand
from src.speech import voice_command as vc
from src.speech.transcriber import TranscriptionResult


class FakeTranscriber:
    def __init__(self, result: TranscriptionResult):
        self._result = result

    def transcribe(self, audio, sample_rate=16000):
        return self._result


def test_full_cycle_happy_path(monkeypatch):
    fake_recording = RecordingResult(
        success=True, audio=np.ones(1000, dtype=np.float32) * 0.2, sample_rate=16000
    )
    monkeypatch.setattr(
        vc, "record_while_key_held", lambda key, sample_rate=16000: fake_recording
    )
    transcriber = FakeTranscriber(
        TranscriptionResult(
            success=True,
            text="Candidate zero zero three zero three, score thirty.",
        )
    )

    result = vc.capture_and_parse_command("f8", transcriber)
    assert result.failed_at_stage == ""
    assert isinstance(result.command, SetScoreCommand)
    assert result.command.registration_number == "00303"
    assert result.transcript_text == "Candidate zero zero three zero three, score thirty."


def test_recording_failure_short_circuits(monkeypatch):
    fake_recording = RecordingResult(
        success=False, error_message="Recording was empty (no audio captured)."
    )
    monkeypatch.setattr(
        vc, "record_while_key_held", lambda key, sample_rate=16000: fake_recording
    )
    transcriber = FakeTranscriber(TranscriptionResult(success=True, text="should not be reached"))

    result = vc.capture_and_parse_command("f8", transcriber)
    assert result.failed_at_stage == "recording"
    assert result.command is None
    assert result.transcript_text == ""


def test_transcription_failure_short_circuits(monkeypatch):
    fake_recording = RecordingResult(
        success=True, audio=np.ones(1000, dtype=np.float32) * 0.2, sample_rate=16000
    )
    monkeypatch.setattr(
        vc, "record_while_key_held", lambda key, sample_rate=16000: fake_recording
    )
    transcriber = FakeTranscriber(
        TranscriptionResult(success=False, error_message="Transcription failed: boom")
    )

    result = vc.capture_and_parse_command("f8", transcriber)
    assert result.failed_at_stage == "transcription"
    assert result.command is None


def test_unparseable_transcript_yields_unrecognized_command(monkeypatch):
    fake_recording = RecordingResult(
        success=True, audio=np.ones(1000, dtype=np.float32) * 0.2, sample_rate=16000
    )
    monkeypatch.setattr(
        vc, "record_while_key_held", lambda key, sample_rate=16000: fake_recording
    )
    transcriber = FakeTranscriber(
        TranscriptionResult(success=True, text="the weather is nice today")
    )

    result = vc.capture_and_parse_command("f8", transcriber)
    assert result.failed_at_stage == ""  # recording+transcription succeeded
    assert isinstance(result.command, UnrecognizedCommand)
