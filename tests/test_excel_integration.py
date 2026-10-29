"""Stage 2 integration tests: drive a REAL Microsoft Excel workbook via
xlwings through src/spreadsheets/excel.py and src/workflow.py.

These tests require Microsoft Excel to be installed and will start/
stop Excel application instances. They are skipped automatically if
xlwings cannot reach Excel (e.g. CI without Office installed).

Each test creates its own temporary workbook so tests don't interfere
with each other or with any workbook you might have open for real work.
"""
from __future__ import annotations

import time
from pathlib import Path

import pytest

xlwings = pytest.importorskip("xlwings")

from src.config import AppConfig, ExcelColumnsConfig, ExcelConfig, ValidationConfig
from src.spreadsheets.base import (
    WorkbookNotFoundError,
    WorkbookProtectedError,
    WorksheetNotFoundError,
)
from src.spreadsheets.excel import connect_to_workbook
from src.validation.audit_log import AuditLog
from src.workflow import ProcessingOutcome, apply_update, process_transcript


def _excel_available() -> bool:
    try:
        app = xlwings.App(visible=False)
        app.quit()
        return True
    except Exception:
        return False


pytestmark = pytest.mark.skipif(
    not _excel_available(), reason="Microsoft Excel is not available on this machine"
)


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


def _build_test_workbook(app, path: Path, protected: bool = False):
    book = app.books.add()
    sheet = book.sheets.active
    sheet.name = "Candidates"
    sheet.cells(1, 2).value = "Registration Number"
    sheet.cells(1, 3).value = "Full Name"
    sheet.cells(1, 4).value = "Gender"
    sheet.cells(1, 5).value = "Score"

    rows = [
        ("00301", "Juma Said", "Male", 25),
        ("00303", "Ally Awadhi", "Male", None),
        ("00304", "Fatma Hamisi", "Female", 50),
    ]
    for row_idx, (regno, name, gender, score) in enumerate(rows, start=2):
        reg_cell = sheet.range(f"B{row_idx}")
        reg_cell.number_format = "@"
        reg_cell.value = regno
        sheet.cells(row_idx, 3).value = name
        sheet.cells(row_idx, 4).value = gender
        sheet.cells(row_idx, 5).value = score

    book.save(str(path))
    if protected:
        sheet.api.Protect()
    return book


@pytest.fixture
def excel_app():
    app = xlwings.App(visible=False)
    yield app
    try:
        for book in list(app.books):
            try:
                for sheet in book.sheets:
                    if bool(sheet.api.ProtectContents):
                        sheet.api.Unprotect()
            except Exception:
                pass
    except Exception:
        pass
    # app.quit() closes all open books itself; calling book.close() first
    # races with quit() over the same COM object and can raise a noisy
    # (harmless) RPC_E_DISCONNECTED on some Excel builds. A short pause
    # before quitting avoids that race in practice.
    time.sleep(0.3)
    try:
        app.quit()
    except Exception:
        pass


def test_read_headers_and_candidates(tmp_path, excel_app):
    path = tmp_path / "stage2_read.xlsx"
    _build_test_workbook(excel_app, path)
    config = make_config()

    backend = connect_to_workbook(
        workbook_path=str(path),
        worksheet_name=config.excel.worksheet_name,
        header_row=config.excel.header_row,
        columns=config.excel.columns,
    )
    headers = backend.read_headers()
    assert headers == ["Registration Number", "Full Name", "Gender", "Score"]

    candidates = backend.read_candidates()
    assert len(candidates) == 3
    regnos = [c.registration_number for c in candidates]
    assert regnos == ["00301", "00303", "00304"]
    # Leading zeros preserved.
    assert all(len(r) == 5 for r in regnos)


def test_full_workflow_write_and_verify(tmp_path, excel_app):
    path = tmp_path / "stage2_write.xlsx"
    _build_test_workbook(excel_app, path)
    config = make_config()
    audit_log = AuditLog(tmp_path / "audit.jsonl")

    backend = connect_to_workbook(
        workbook_path=str(path),
        worksheet_name=config.excel.worksheet_name,
        header_row=config.excel.header_row,
        columns=config.excel.columns,
    )
    candidates = backend.read_candidates()

    result = process_transcript(
        "Candidate zero zero three zero three, score thirty.", candidates, config
    )
    assert result.outcome == ProcessingOutcome.NEEDS_CONFIRMATION

    applied = apply_update(result.proposed_update, backend, audit_log)
    assert applied.outcome == ProcessingOutcome.INFO_ONLY

    # Re-read directly from the live Excel cell to confirm the write
    # actually landed in the real workbook (not just our in-memory model).
    new_value = backend.read_cell(result.proposed_update.candidate.row_number, "E")
    assert new_value == 30


def test_workbook_not_found_raises():
    config = make_config()
    with pytest.raises(WorkbookNotFoundError):
        connect_to_workbook(
            workbook_path="C:/definitely/does/not/exist/nope.xlsx",
            worksheet_name=config.excel.worksheet_name,
            header_row=config.excel.header_row,
            columns=config.excel.columns,
        )


def test_worksheet_missing_raises(tmp_path, excel_app):
    path = tmp_path / "stage2_missing_sheet.xlsx"
    _build_test_workbook(excel_app, path)
    config = make_config()

    with pytest.raises(WorksheetNotFoundError):
        connect_to_workbook(
            workbook_path=str(path),
            worksheet_name="DoesNotExist",
            header_row=config.excel.header_row,
            columns=config.excel.columns,
        )


def test_protected_worksheet_blocks_write(tmp_path, excel_app):
    path = tmp_path / "stage2_protected.xlsx"
    _build_test_workbook(excel_app, path, protected=True)
    config = make_config()
    audit_log = AuditLog(tmp_path / "audit.jsonl")

    backend = connect_to_workbook(
        workbook_path=str(path),
        worksheet_name=config.excel.worksheet_name,
        header_row=config.excel.header_row,
        columns=config.excel.columns,
    )
    candidates = backend.read_candidates()

    result = process_transcript(
        "Candidate zero zero three zero three, score thirty.", candidates, config
    )
    assert result.outcome == ProcessingOutcome.NEEDS_CONFIRMATION

    applied = apply_update(result.proposed_update, backend, audit_log)
    assert applied.outcome == ProcessingOutcome.REJECTED
    assert "protected" in applied.message.lower() or "Failed to write" in applied.message

    # Confirm workbook is unchanged - score cell should still be None/empty.
    unchanged = backend.read_cell(result.proposed_update.candidate.row_number, "E")
    assert unchanged is None
