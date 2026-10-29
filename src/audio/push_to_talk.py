"""Push-to-talk microphone recording using the F8 key.

Behaviour (per project spec section 3):
- Hold F8 to record, release to stop.
- Recording must stop reliably on key release.
- Microphone errors, empty recordings, and failures are handled safely
  (never raise into the caller - return a RecordingResult instead).

This module is deliberately decoupled from Whisper/UI: it only knows
how to capture raw float32 mono audio at the configured sample rate
and return it (or report why it couldn't).
"""
from __future__ import annotations

import queue
import threading
import time
from dataclasses import dataclass
from typing import Optional

import numpy as np

try:
    import sounddevice as sd
except Exception:  # pragma: no cover - exercised only without a working audio stack
    sd = None

try:
    import keyboard as kb
except Exception:  # pragma: no cover - exercised only without the keyboard lib
    kb = None


@dataclass(frozen=True)
class RecordingResult:
    success: bool
    audio: Optional[np.ndarray] = None  # float32, mono, shape (n_samples,)
    sample_rate: int = 16000
    error_message: str = ""
    duration_seconds: float = 0.0


class MicrophoneError(Exception):
    pass


class PushToTalkRecorder:
    """Records audio from the microphone while a key is held down.

    Two usage modes:
    1. `record_while_key_held(key)` - blocks until the key (held, then
       released) produces a complete recording. Intended for a
       dedicated listener thread/loop.
    2. Manual `start()` / `stop()` - for callers (e.g. a UI) that
       already have their own key-down/key-up event handling and just
       want to control the recording boundaries directly.
    """

    def __init__(self, sample_rate: int = 16000, channels: int = 1):
        self.sample_rate = sample_rate
        self.channels = channels
        self._stream = None
        self._frames: "queue.Queue[np.ndarray]" = queue.Queue()
        self._recording = False
        self._lock = threading.Lock()
        self._start_time = 0.0

    # -- manual start/stop API ------------------------------------------

    def start(self) -> None:
        """Begin capturing audio. Safe to call again while already
        recording (no-op)."""
        with self._lock:
            if self._recording:
                return
            if sd is None:
                raise MicrophoneError(
                    "sounddevice is not installed. Run: pip install -r requirements.txt"
                )
            self._frames = queue.Queue()
            try:
                self._stream = sd.InputStream(
                    samplerate=self.sample_rate,
                    channels=self.channels,
                    dtype="float32",
                    callback=self._on_audio_block,
                )
                self._stream.start()
            except Exception as exc:
                self._stream = None
                raise MicrophoneError(f"Failed to open microphone: {exc}") from exc
            self._recording = True
            self._start_time = time.monotonic()

    def stop(self) -> RecordingResult:
        """Stop capturing and return the recorded audio. Always safe
        to call, even if start() failed or was never called."""
        with self._lock:
            if not self._recording or self._stream is None:
                return RecordingResult(
                    success=False,
                    error_message="No active recording to stop.",
                    sample_rate=self.sample_rate,
                )
            duration = time.monotonic() - self._start_time
            try:
                self._stream.stop()
                self._stream.close()
            except Exception as exc:
                self._recording = False
                self._stream = None
                return RecordingResult(
                    success=False,
                    error_message=f"Error while stopping microphone: {exc}",
                    sample_rate=self.sample_rate,
                    duration_seconds=duration,
                )
            self._recording = False
            self._stream = None

        blocks = []
        while not self._frames.empty():
            blocks.append(self._frames.get_nowait())

        if not blocks:
            return RecordingResult(
                success=False,
                error_message="Recording was empty (no audio captured).",
                sample_rate=self.sample_rate,
                duration_seconds=duration,
            )

        audio = np.concatenate(blocks, axis=0).flatten().astype(np.float32)
        if audio.size == 0 or not np.any(audio):
            return RecordingResult(
                success=False,
                error_message="Recording contained only silence.",
                sample_rate=self.sample_rate,
                duration_seconds=duration,
            )

        return RecordingResult(
            success=True,
            audio=audio,
            sample_rate=self.sample_rate,
            duration_seconds=duration,
        )

    @property
    def is_recording(self) -> bool:
        return self._recording

    def _on_audio_block(self, indata, frames, time_info, status) -> None:
        # Called on the sounddevice audio thread; keep it fast and
        # never raise (exceptions here are swallowed by sounddevice).
        self._frames.put(indata.copy())


def record_while_key_held(
    key: str,
    sample_rate: int = 16000,
    poll_interval: float = 0.02,
    max_duration_seconds: float = 30.0,
) -> RecordingResult:
    """Block until `key` is pressed, record until it is released (or
    `max_duration_seconds` elapses as a safety cap), then return the
    result. Requires the `keyboard` package and (on Windows) usually
    admin privileges to hook global key state reliably.
    """
    if kb is None:
        return RecordingResult(
            success=False,
            error_message=(
                "keyboard package is not installed. Run: pip install -r requirements.txt"
            ),
            sample_rate=sample_rate,
        )

    try:
        while not kb.is_pressed(key):
            time.sleep(poll_interval)
    except Exception as exc:
        return RecordingResult(
            success=False,
            error_message=f"Failed to read keyboard state: {exc}",
            sample_rate=sample_rate,
        )

    recorder = PushToTalkRecorder(sample_rate=sample_rate)
    try:
        recorder.start()
    except MicrophoneError as exc:
        return RecordingResult(
            success=False, error_message=str(exc), sample_rate=sample_rate
        )

    start = time.monotonic()
    try:
        while kb.is_pressed(key):
            if time.monotonic() - start > max_duration_seconds:
                break
            time.sleep(poll_interval)
    except Exception as exc:
        result = recorder.stop()
        return RecordingResult(
            success=False,
            error_message=f"Error while monitoring key state: {exc}",
            sample_rate=sample_rate,
            duration_seconds=result.duration_seconds,
        )

    return recorder.stop()
