"""Unit tests for push-to-talk recording, using fakes for sounddevice
and keyboard so these tests don't require real hardware or admin
privileges and run everywhere (CI, headless).
"""
from __future__ import annotations

import time

import numpy as np
import pytest

from src.audio import push_to_talk as ptt


class FakeStream:
    """Mimics sounddevice.InputStream just enough for our recorder."""

    instances = []

    def __init__(self, samplerate, channels, dtype, callback):
        self.samplerate = samplerate
        self.channels = channels
        self.callback = callback
        self.started = False
        self.closed = False
        FakeStream.instances.append(self)

    def start(self):
        self.started = True

    def stop(self):
        self.started = False

    def close(self):
        self.closed = True

    def push_block(self, block: np.ndarray):
        self.callback(block, len(block), None, None)


class FailingStream(FakeStream):
    def __init__(self, *a, **k):
        raise RuntimeError("no microphone device available")


@pytest.fixture(autouse=True)
def reset_fake_streams():
    FakeStream.instances.clear()
    yield
    FakeStream.instances.clear()


def test_start_stop_produces_audio(monkeypatch):
    monkeypatch.setattr(ptt, "sd", _FakeSoundDevice(FakeStream))
    recorder = ptt.PushToTalkRecorder(sample_rate=16000)
    recorder.start()
    stream = FakeStream.instances[-1]
    stream.push_block(np.ones((100, 1), dtype=np.float32) * 0.5)
    stream.push_block(np.ones((50, 1), dtype=np.float32) * 0.5)
    result = recorder.stop()

    assert result.success
    assert result.audio is not None
    assert result.audio.shape[0] == 150
    assert result.sample_rate == 16000


def test_stop_without_start_is_safe():
    recorder = ptt.PushToTalkRecorder()
    result = recorder.stop()
    assert not result.success
    assert "No active recording" in result.error_message


def test_empty_recording_reported_as_failure(monkeypatch):
    monkeypatch.setattr(ptt, "sd", _FakeSoundDevice(FakeStream))
    recorder = ptt.PushToTalkRecorder()
    recorder.start()
    # No audio pushed at all.
    result = recorder.stop()
    assert not result.success
    assert "empty" in result.error_message.lower()


def test_silent_recording_reported_as_failure(monkeypatch):
    monkeypatch.setattr(ptt, "sd", _FakeSoundDevice(FakeStream))
    recorder = ptt.PushToTalkRecorder()
    recorder.start()
    stream = FakeStream.instances[-1]
    stream.push_block(np.zeros((100, 1), dtype=np.float32))
    result = recorder.stop()
    assert not result.success
    assert "silence" in result.error_message.lower()


def test_microphone_open_failure_raises_microphone_error(monkeypatch):
    monkeypatch.setattr(ptt, "sd", _FakeSoundDevice(FailingStream))
    recorder = ptt.PushToTalkRecorder()
    with pytest.raises(ptt.MicrophoneError):
        recorder.start()


def test_double_start_is_noop(monkeypatch):
    monkeypatch.setattr(ptt, "sd", _FakeSoundDevice(FakeStream))
    recorder = ptt.PushToTalkRecorder()
    recorder.start()
    recorder.start()  # should not raise or open a second stream
    assert len(FakeStream.instances) == 1
    recorder.stop()


class FakeKeyboard:
    """Mimics the `keyboard` module's is_pressed() for F8-hold tests."""

    def __init__(self, press_at: float, release_at: float):
        self._start = time.monotonic()
        self._press_at = press_at
        self._release_at = release_at

    def is_pressed(self, key: str) -> bool:
        elapsed = time.monotonic() - self._start
        return self._press_at <= elapsed < self._release_at


def test_record_while_key_held_full_cycle(monkeypatch):
    monkeypatch.setattr(ptt, "sd", _FakeSoundDevice(FakeStream))
    fake_kb = FakeKeyboard(press_at=0.0, release_at=0.15)
    monkeypatch.setattr(ptt, "kb", fake_kb)

    # Push audio into the stream shortly after it's created, from a
    # background thread, to simulate the mic producing data while the
    # key is held.
    import threading

    def feeder():
        time.sleep(0.02)
        while not FakeStream.instances:
            time.sleep(0.005)
        stream = FakeStream.instances[-1]
        for _ in range(5):
            stream.push_block(np.ones((50, 1), dtype=np.float32) * 0.3)
            time.sleep(0.02)

    t = threading.Thread(target=feeder)
    t.start()
    result = ptt.record_while_key_held("f8", sample_rate=16000, poll_interval=0.01)
    t.join()

    assert result.success
    assert result.audio is not None
    assert result.audio.shape[0] > 0


def test_record_while_key_held_missing_keyboard_module(monkeypatch):
    monkeypatch.setattr(ptt, "kb", None)
    result = ptt.record_while_key_held("f8")
    assert not result.success
    assert "keyboard" in result.error_message.lower()


class _FakeSoundDevice:
    """Minimal stand-in for the `sounddevice` module exposing only
    what PushToTalkRecorder uses."""

    def __init__(self, stream_cls):
        self.InputStream = stream_cls
