"""Simple Tkinter desktop UI for voice-based exam score entry.

Per the project spec (section 7), this interface shows:
- Current workbook and worksheet
- Push-to-talk status
- Transcribed speech
- Parsed command
- Candidate found
- Proposed cell update
- Confirm and Cancel controls
- Success or error message
- Recent operations

Deliberately simple (ttk widgets, single window, no styling framework)
- correctness and clarity over visual polish, per the spec.

Threading model: the F8 push-to-talk listener runs on a background
thread (recording + transcription are blocking calls). It communicates
back to the Tkinter main thread via a thread-safe queue, which the UI
drains on a periodic `after()` poll - Tkinter widgets must only be
touched from the main thread.
"""
from __future__ import annotations

import queue
import threading
import tkinter as tk
from dataclasses import dataclass
from tkinter import filedialog, messagebox, ttk
from typing import Callable, List, Optional

from src.candidates.models import Candidate
from src.commands.schema import UnrecognizedCommand
from src.config import AppConfig
from src.spreadsheets.base import SpreadsheetBackend, SpreadsheetError
from src.spreadsheets.excel import connect_to_workbook
from src.speech.transcriber import TranscriptionError, WhisperTranscriber
from src.speech.voice_command import VoiceCommandResult, capture_and_parse_command
from src.validation.audit_log import AuditLog
from src.workflow import ProcessingOutcome, ProcessingResult, apply_update, process_transcript

_MAX_HISTORY_ROWS = 20


@dataclass
class _UIEvent:
    kind: str  # "status" | "result" | "error"
    payload: object


class VoiceExamApp:
    def __init__(self, root: tk.Tk, config: AppConfig):
        self.root = root
        self.config = config
        self.root.title("Voice Exam Score Entry")
        self.root.geometry("760x640")

        self._event_queue: "queue.Queue[_UIEvent]" = queue.Queue()
        self._listener_thread: Optional[threading.Thread] = None
        self._stop_listener = threading.Event()

        self.backend: Optional[SpreadsheetBackend] = None
        self.candidates: List[Candidate] = []
        self.audit_log = AuditLog(config.audit_log.path)
        self.transcriber: Optional[WhisperTranscriber] = None

        self._pending_result: Optional[ProcessingResult] = None

        self._build_widgets()
        self._poll_events()

    # -- UI construction --------------------------------------------------

    def _build_widgets(self) -> None:
        pad = {"padx": 8, "pady": 4}

        top = ttk.Frame(self.root)
        top.pack(fill="x", **pad)

        self.workbook_var = tk.StringVar(value="(not connected)")
        self.worksheet_var = tk.StringVar(value="")
        ttk.Label(top, text="Workbook:").grid(row=0, column=0, sticky="w")
        ttk.Label(top, textvariable=self.workbook_var).grid(row=0, column=1, sticky="w")
        ttk.Label(top, text="Worksheet:").grid(row=1, column=0, sticky="w")
        ttk.Label(top, textvariable=self.worksheet_var).grid(row=1, column=1, sticky="w")

        ttk.Button(top, text="Connect to Workbook", command=self._on_connect_clicked).grid(
            row=0, column=2, rowspan=2, padx=8
        )

        status_frame = ttk.LabelFrame(self.root, text="Push-to-Talk")
        status_frame.pack(fill="x", **pad)
        self.ptt_status_var = tk.StringVar(
            value=f"Idle - hold {self.config.speech.push_to_talk_key} to speak"
        )
        ttk.Label(status_frame, textvariable=self.ptt_status_var).pack(
            anchor="w", padx=8, pady=4
        )

        transcript_frame = ttk.LabelFrame(self.root, text="Transcribed Speech")
        transcript_frame.pack(fill="x", **pad)
        self.transcript_text = tk.Text(transcript_frame, height=2, wrap="word")
        self.transcript_text.pack(fill="x", padx=8, pady=4)
        self.transcript_text.configure(state="disabled")

        command_frame = ttk.LabelFrame(self.root, text="Parsed Command")
        command_frame.pack(fill="x", **pad)
        self.command_var = tk.StringVar(value="(none yet)")
        ttk.Label(command_frame, textvariable=self.command_var, wraplength=700).pack(
            anchor="w", padx=8, pady=4
        )

        candidate_frame = ttk.LabelFrame(self.root, text="Candidate")
        candidate_frame.pack(fill="x", **pad)
        self.candidate_var = tk.StringVar(value="(none)")
        ttk.Label(candidate_frame, textvariable=self.candidate_var, wraplength=700).pack(
            anchor="w", padx=8, pady=4
        )

        update_frame = ttk.LabelFrame(self.root, text="Proposed Update")
        update_frame.pack(fill="x", **pad)
        self.update_var = tk.StringVar(value="(none)")
        ttk.Label(update_frame, textvariable=self.update_var, wraplength=700).pack(
            anchor="w", padx=8, pady=4
        )

        button_frame = ttk.Frame(self.root)
        button_frame.pack(fill="x", **pad)
        self.confirm_button = ttk.Button(
            button_frame, text="Confirm", command=self._on_confirm_clicked, state="disabled"
        )
        self.confirm_button.pack(side="left", padx=4)
        self.cancel_button = ttk.Button(
            button_frame, text="Cancel", command=self._on_cancel_clicked, state="disabled"
        )
        self.cancel_button.pack(side="left", padx=4)

        message_frame = ttk.LabelFrame(self.root, text="Message")
        message_frame.pack(fill="x", **pad)
        self.message_var = tk.StringVar(value="")
        self.message_label = ttk.Label(
            message_frame, textvariable=self.message_var, wraplength=700
        )
        self.message_label.pack(anchor="w", padx=8, pady=4)

        history_frame = ttk.LabelFrame(self.root, text="Recent Operations")
        history_frame.pack(fill="both", expand=True, **pad)
        self.history_list = tk.Listbox(history_frame)
        self.history_list.pack(fill="both", expand=True, padx=8, pady=4)

    # -- Workbook connection -----------------------------------------------

    def _on_connect_clicked(self) -> None:
        def file_picker() -> Optional[str]:
            return filedialog.askopenfilename(
                title="Select Excel Workbook",
                filetypes=[("Excel Workbooks", "*.xlsx *.xlsm *.xls")],
            )

        try:
            self.backend = connect_to_workbook(
                workbook_path=self.config.excel.workbook_path,
                worksheet_name=self.config.excel.worksheet_name,
                header_row=self.config.excel.header_row,
                columns=self.config.excel.columns,
                treat_registration_number_as_text=(
                    self.config.excel.treat_registration_number_as_text
                ),
                file_picker=file_picker,
            )
        except SpreadsheetError as exc:
            messagebox.showerror("Connection failed", str(exc))
            return

        self.workbook_var.set(self.backend.get_workbook_name())
        self.worksheet_var.set(self.backend.get_worksheet_name())

        try:
            headers = self.backend.read_headers()
        except SpreadsheetError as exc:
            messagebox.showerror("Failed to read headers", str(exc))
            return

        expected = ["Registration Number", "Full Name", "Gender", "Score"]
        if not all(h for h in headers):
            messagebox.showwarning(
                "Header check",
                f"Some header cells are empty: {headers}. Please verify "
                "excel.columns / excel.header_row in config.json match "
                "your workbook.",
            )

        try:
            self.candidates = self.backend.read_candidates()
        except SpreadsheetError as exc:
            messagebox.showerror("Failed to read candidates", str(exc))
            return

        self._set_message(
            f"Connected. Headers: {headers}. Loaded {len(self.candidates)} "
            "candidate rows."
        )
        self._start_listener_if_needed()

    # -- Push-to-talk listener thread --------------------------------------

    def _start_listener_if_needed(self) -> None:
        if self._listener_thread is not None and self._listener_thread.is_alive():
            return
        if self.backend is None:
            return

        try:
            if self.transcriber is None:
                self.ptt_status_var.set("Loading speech model...")
                self.root.update_idletasks()
                self.transcriber = WhisperTranscriber(
                    model_size=self.config.speech.whisper_model_size,
                    language=self.config.speech.language,
                )
        except TranscriptionError as exc:
            messagebox.showerror("Speech model failed to load", str(exc))
            self.ptt_status_var.set("Speech recognition unavailable.")
            return

        self._stop_listener.clear()
        self._listener_thread = threading.Thread(
            target=self._listener_loop, daemon=True
        )
        self._listener_thread.start()
        self.ptt_status_var.set(
            f"Ready - hold {self.config.speech.push_to_talk_key} to speak"
        )

    def _listener_loop(self) -> None:
        key = self.config.speech.push_to_talk_key.lower()
        while not self._stop_listener.is_set():
            self._event_queue.put(_UIEvent("status", f"Waiting for {key.upper()}..."))
            result = capture_and_parse_command(
                key, self.transcriber, sample_rate=self.config.speech.sample_rate
            )
            self._event_queue.put(_UIEvent("voice_result", result))

    # -- Event pump (runs on the Tk main thread) ---------------------------

    def _poll_events(self) -> None:
        try:
            while True:
                event = self._event_queue.get_nowait()
                self._handle_event(event)
        except queue.Empty:
            pass
        self.root.after(100, self._poll_events)

    def _handle_event(self, event: _UIEvent) -> None:
        if event.kind == "status":
            self.ptt_status_var.set(str(event.payload))
        elif event.kind == "voice_result":
            self._handle_voice_result(event.payload)

    def _handle_voice_result(self, result: VoiceCommandResult) -> None:
        if result.failed_at_stage == "recording":
            self.ptt_status_var.set("Ready - recording issue, see message below")
            self._set_message(f"Recording error: {result.recording.error_message}")
            return
        if result.failed_at_stage == "transcription":
            self.ptt_status_var.set("Ready - transcription issue, see message below")
            self._set_message(
                f"Transcription error: {result.transcription.error_message}"
            )
            return

        self.ptt_status_var.set(f"Ready - hold {self.config.speech.push_to_talk_key} to speak")
        self._set_transcript(result.transcript_text)

        command = result.command
        self.command_var.set(self._describe_command(command))

        if isinstance(command, UnrecognizedCommand):
            self.candidate_var.set("(none)")
            self.update_var.set("(none)")
            self._disable_confirmation()
            self._set_message(f"Not understood: {command.reason}")
            return

        processing_result = process_transcript(
            result.transcript_text, self.candidates, self.config
        )
        self._apply_processing_result(processing_result)

    def _apply_processing_result(self, result: ProcessingResult) -> None:
        if result.candidate is not None:
            self.candidate_var.set(
                f"{result.candidate.full_name} "
                f"(reg# {result.candidate.registration_number}, "
                f"row {result.candidate.row_number})"
            )
        else:
            self.candidate_var.set("(none)")

        if result.outcome == ProcessingOutcome.NEEDS_CONFIRMATION and result.proposed_update:
            proposed = result.proposed_update
            self.update_var.set(
                f"{proposed.field_name}: '{proposed.old_value}' -> "
                f"'{proposed.new_value}' (cell {proposed.column_letter}"
                f"{proposed.candidate.row_number})"
            )
            self._pending_result = result
            self._enable_confirmation()
            self._set_message(result.message)
        elif result.outcome == ProcessingOutcome.INFO_ONLY:
            self.update_var.set("(none - lookup only)")
            self._disable_confirmation()
            self._set_message(result.message)
        else:  # REJECTED
            self.update_var.set("(none)")
            self._disable_confirmation()
            self._set_message(result.message)

    def _describe_command(self, command) -> str:
        if command is None:
            return "(none)"
        return f"{command.type.value}: {command}"

    # -- Confirm / Cancel ---------------------------------------------------

    def _enable_confirmation(self) -> None:
        self.confirm_button.configure(state="normal")
        self.cancel_button.configure(state="normal")

    def _disable_confirmation(self) -> None:
        self.confirm_button.configure(state="disabled")
        self.cancel_button.configure(state="disabled")
        self._pending_result = None

    def _on_confirm_clicked(self) -> None:
        if self._pending_result is None or self._pending_result.proposed_update is None:
            return
        if self.backend is None:
            messagebox.showerror("No workbook", "Not connected to a workbook.")
            return

        applied = apply_update(
            self._pending_result.proposed_update, self.backend, self.audit_log
        )
        self._set_message(applied.message)
        self._add_history_entry(applied.message)

        if applied.outcome == ProcessingOutcome.INFO_ONLY:
            # Refresh our in-memory candidate list to reflect the write.
            try:
                self.candidates = self.backend.read_candidates()
            except SpreadsheetError:
                pass

        self.update_var.set("(none)")
        self._disable_confirmation()

    def _on_cancel_clicked(self) -> None:
        self._set_message("Update cancelled; nothing was written.")
        self.update_var.set("(none)")
        self._disable_confirmation()

    # -- Small helpers -------------------------------------------------------

    def _set_transcript(self, text: str) -> None:
        self.transcript_text.configure(state="normal")
        self.transcript_text.delete("1.0", "end")
        self.transcript_text.insert("1.0", text)
        self.transcript_text.configure(state="disabled")

    def _set_message(self, text: str) -> None:
        self.message_var.set(text)

    def _add_history_entry(self, text: str) -> None:
        self.history_list.insert(0, text)
        while self.history_list.size() > _MAX_HISTORY_ROWS:
            self.history_list.delete(self.history_list.size() - 1)

    def on_close(self) -> None:
        self._stop_listener.set()
        self.root.destroy()


def run_app(config: AppConfig) -> None:
    root = tk.Tk()
    app = VoiceExamApp(root, config)
    root.protocol("WM_DELETE_WINDOW", app.on_close)
    root.mainloop()
