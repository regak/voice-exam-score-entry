"""Smoke / logic tests for the Tkinter desktop UI.

These tests create a real Tk root (Tkinter ships with Python and the
host has a working Tk 8.6 install - verified during development) but
drive the app's internal event-handling methods directly rather than
simulating real keyboard/mouse input, since that's the part with
actual logic worth testing. A full visual smoke test (does the window
open at all) is included as its own test.

Skipped automatically if Tk can't initialize (e.g. truly headless CI
with no display driver at all).
"""
from __future__ import annotations

import tkinter as tk
import time

import pytest

pytest.importorskip("tkinter")

from src.candidates.models import Candidate
from src.commands.schema import SetScoreCommand, UnrecognizedCommand
from src.config import AppConfig, ExcelColumnsConfig, ExcelConfig, ValidationConfig
from src.spreadsheets.mock import MockExcelBackend
from src.speech.transcriber import TranscriptionResult
from src.speech.voice_command import VoiceCommandResult
from src.audio.push_to_talk import RecordingResult
from src.ui.desktop_app import VoiceExamApp


def _create_tk_root_with_retry(max_attempts: int = 5, delay_seconds: float = 0.3) -> tk.Tk:
    """Create a Tk root, retrying a few times.

    On this machine, Tk() initialization intermittently fails with a
    spurious 'couldn't read file init.tcl: No error' even though the
    file is present and a standalone script succeeds every time. This
    looks like transient interference (e.g. antivirus briefly locking
    the Tcl library files during the test runner's rapid process/file
    churn) rather than a real Tcl/Tk installation problem - retrying
    resolves it in practice.
    """
    last_exc = None
    for _ in range(max_attempts):
        try:
            return tk.Tk()
        except tk.TclError as exc:
            last_exc = exc
            time.sleep(delay_seconds)
    raise last_exc


def _tk_available() -> bool:
    try:
        root = _create_tk_root_with_retry()
        root.withdraw()
        root.destroy()
        return True
    except Exception:
        return False


_TK_AVAILABLE = _tk_available()
pytestmark = pytest.mark.skipif(not _TK_AVAILABLE, reason="Tk display not available")


@pytest.fixture(scope="module")
def tk_root():
    """A single Tk root shared across this module's tests. Creating
    and destroying many Tk() instances in quick succession in one
    process is flaky on some Windows/Tcl installs, so tests reuse one
    root and only create/destroy the VoiceExamApp's own widgets."""
    root = _create_tk_root_with_retry()
    root.withdraw()
    yield root
    root.destroy()


def make_config() -> AppConfig:
    cfg = AppConfig()
    cfg.excel = ExcelConfig(
        workbook_path=None,
        worksheet_name="Candidates",
        header_row=1,
        columns=ExcelColumnsConfig(
            registration_number="B", full_name="C", gender="D", score="E"
        ),
    )
    cfg.validation = ValidationConfig(
        score_min=0,
        score_max=60,
        accepted_genders={
            "male": ["male", "m", "boy", "man"],
            "female": ["female", "f", "girl", "woman"],
        },
    )
    return cfg


def make_candidates():
    return [
        Candidate(2, "00301", "Juma Said", "male", 25),
        Candidate(3, "00303", "Ally Awadhi", "male", None),
    ]


@pytest.fixture
def app(tmp_path, tk_root):
    window = tk.Toplevel(tk_root)
    config = make_config()
    config.audit_log.path = str(tmp_path / "audit.jsonl")
    application = VoiceExamApp(window, config)
    application.candidates = make_candidates()
    application.backend = MockExcelBackend(application.candidates)
    yield application
    window.destroy()


def test_window_opens_and_closes(tk_root):
    window = tk.Toplevel(tk_root)
    config = make_config()
    app_instance = VoiceExamApp(window, config)
    assert app_instance.workbook_var.get() == "(not connected)"
    app_instance.on_close()


def test_voice_result_happy_path_enables_confirmation(app):
    voice_result = VoiceCommandResult(
        recording=RecordingResult(success=True, audio=None, sample_rate=16000),
        transcription=TranscriptionResult(
            success=True, text="Candidate zero zero three zero three, score thirty."
        ),
        command=SetScoreCommand(registration_number="00303", score_text="30.0"),
    )
    app._handle_voice_result(voice_result)

    assert "Ally Awadhi" in app.candidate_var.get()
    assert "score" in app.update_var.get()
    assert str(app.confirm_button["state"]) == "normal"
    assert str(app.cancel_button["state"]) == "normal"
    assert app._pending_result is not None


def test_voice_result_unrecognized_disables_confirmation(app):
    voice_result = VoiceCommandResult(
        recording=RecordingResult(success=True, audio=None, sample_rate=16000),
        transcription=TranscriptionResult(success=True, text="the weather is nice"),
        command=UnrecognizedCommand(raw_text="the weather is nice", reason="no match"),
    )
    app._handle_voice_result(voice_result)

    assert str(app.confirm_button["state"]) == "disabled"
    assert "Not understood" in app.message_var.get()


def test_recording_failure_shows_message_and_no_confirmation(app):
    voice_result = VoiceCommandResult(
        recording=RecordingResult(success=False, error_message="Recording was empty."),
        transcription=None,
        command=None,
    )
    app._handle_voice_result(voice_result)

    assert "Recording error" in app.message_var.get()
    assert str(app.confirm_button["state"]) == "disabled"


def test_confirm_writes_to_backend_and_records_history(app):
    voice_result = VoiceCommandResult(
        recording=RecordingResult(success=True, audio=None, sample_rate=16000),
        transcription=TranscriptionResult(
            success=True, text="Candidate zero zero three zero three, score thirty."
        ),
        command=SetScoreCommand(registration_number="00303", score_text="30.0"),
    )
    app._handle_voice_result(voice_result)
    assert app._pending_result is not None

    app._on_confirm_clicked()

    assert app.backend.read_cell(3, "E") == 30
    assert app.history_list.size() == 1
    assert str(app.confirm_button["state"]) == "disabled"
    assert app._pending_result is None


def test_cancel_does_not_write(app):
    voice_result = VoiceCommandResult(
        recording=RecordingResult(success=True, audio=None, sample_rate=16000),
        transcription=TranscriptionResult(
            success=True, text="Candidate zero zero three zero three, score thirty."
        ),
        command=SetScoreCommand(registration_number="00303", score_text="30.0"),
    )
    app._handle_voice_result(voice_result)
    app._on_cancel_clicked()

    assert app.backend.write_count == 0
    assert str(app.confirm_button["state"]) == "disabled"


def test_invalid_score_rejected_in_ui(app):
    voice_result = VoiceCommandResult(
        recording=RecordingResult(success=True, audio=None, sample_rate=16000),
        transcription=TranscriptionResult(
            success=True, text="Candidate zero zero three zero three, score ninety."
        ),
        command=SetScoreCommand(registration_number="00303", score_text="90.0"),
    )
    app._handle_voice_result(voice_result)

    assert str(app.confirm_button["state"]) == "disabled"
    assert "outside the allowed range" in app.message_var.get()
    assert app.backend.write_count == 0
