"""Stage 3 glue: push-to-talk recording -> Whisper transcription ->
deterministic command parsing.

This module has no UI. It's the layer Stage 4's UI will call into:
`capture_and_parse_command()` does one full F8 hold-and-release cycle
and returns everything the UI needs to display (raw audio metadata,
transcript, parsed command) without ever touching the spreadsheet.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Optional

from src.audio.push_to_talk import RecordingResult, record_while_key_held
from src.commands.parser import parse_command
from src.commands.schema import Command, UnrecognizedCommand
from src.speech.transcriber import TranscriptionResult, WhisperTranscriber


@dataclass(frozen=True)
class VoiceCommandResult:
    recording: RecordingResult
    transcription: Optional[TranscriptionResult]
    command: Optional[Command]

    @property
    def transcript_text(self) -> str:
        if self.transcription and self.transcription.success:
            return self.transcription.text
        return ""

    @property
    def failed_at_stage(self) -> str:
        """Which stage failed, for display purposes: '' if nothing
        failed (a Command, possibly Unrecognized, was produced)."""
        if not self.recording.success:
            return "recording"
        if self.transcription is None or not self.transcription.success:
            return "transcription"
        return ""


def capture_and_parse_command(
    push_to_talk_key: str,
    transcriber: WhisperTranscriber,
    sample_rate: int = 16000,
) -> VoiceCommandResult:
    """Block until the push-to-talk key is held and released, then
    transcribe and parse the result. Never raises - every failure mode
    (mic error, empty/silent recording, transcription failure,
    unparseable command) is represented in the returned result so the
    caller can show a clear message and decline to touch the
    spreadsheet.
    """
    recording = record_while_key_held(push_to_talk_key, sample_rate=sample_rate)
    if not recording.success:
        return VoiceCommandResult(recording=recording, transcription=None, command=None)

    transcription = transcriber.transcribe(recording.audio, sample_rate=recording.sample_rate)
    if not transcription.success:
        return VoiceCommandResult(
            recording=recording, transcription=transcription, command=None
        )

    command = parse_command(transcription.text)
    return VoiceCommandResult(
        recording=recording, transcription=transcription, command=command
    )
