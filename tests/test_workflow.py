import json
import tempfile
from pathlib import Path

import pytest

from src.candidates.models import Candidate
from src.config import AppConfig, ExcelColumnsConfig, ExcelConfig, ValidationConfig
from src.spreadsheets.base import WorkbookReadOnlyError
from src.spreadsheets.mock import MockExcelBackend
from src.validation.audit_log import AuditLog
from src.workflow import ProcessingOutcome, apply_update, process_transcript


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
        Candidate(4, "00304", "Fatma Hamisi", "female", 50),
        Candidate(5, "00030", "Ally Awadhi", "male", 40),  # duplicate name
    ]


def test_set_score_happy_path(tmp_path):
    candidates = make_candidates()
    config = make_config()
    backend = MockExcelBackend(candidates)
    audit_path = tmp_path / "audit.jsonl"
    audit_log = AuditLog(audit_path)

    result = process_transcript(
        "Candidate zero zero three zero three, score thirty.", candidates, config
    )
    assert result.outcome == ProcessingOutcome.NEEDS_CONFIRMATION
    assert result.proposed_update.new_value == 30
    assert result.proposed_update.old_value is None

    applied = apply_update(result.proposed_update, backend, audit_log)
    assert applied.outcome == ProcessingOutcome.INFO_ONLY
    updated = backend.read_cell(3, "E")
    assert updated == 30
    assert backend.write_count == 1

    # Audit log should contain one update record.
    lines = audit_path.read_text(encoding="utf-8").strip().splitlines()
    assert len(lines) == 1
    record = json.loads(lines[0])
    assert record["event"] == "update"
    assert record["new_value"] == "30"
    assert record["old_value"] in (None, "None")


def test_invalid_score_is_rejected_and_nothing_written():
    candidates = make_candidates()
    config = make_config()
    backend = MockExcelBackend(candidates)

    result = process_transcript(
        "Candidate zero zero three zero three, score ninety.", candidates, config
    )
    assert result.outcome == ProcessingOutcome.REJECTED
    assert "outside the allowed range" in result.message
    assert backend.write_count == 0


def test_ambiguous_name_lookup_blocks_update():
    candidates = make_candidates()
    config = make_config()

    result = process_transcript("Find candidate Ally Awadhi.", candidates, config)
    assert result.outcome == ProcessingOutcome.REJECTED
    assert len(result.matches) == 2


def test_duplicate_registration_numbers_block_update():
    # Simulate a data-entry error: two rows share the same reg number.
    candidates = [
        Candidate(2, "00303", "Ally Awadhi", "male", None),
        Candidate(3, "00303", "Imposter Candidate", "male", None),
    ]
    config = make_config()

    result = process_transcript(
        "Candidate zero zero three zero three, score thirty.", candidates, config
    )
    assert result.outcome == ProcessingOutcome.REJECTED
    assert len(result.matches) == 2


def test_readonly_workbook_blocks_write_and_logs_error(tmp_path):
    candidates = make_candidates()
    config = make_config()
    backend = MockExcelBackend(candidates, read_only=True)
    audit_log = AuditLog(tmp_path / "audit.jsonl")

    result = process_transcript(
        "Candidate zero zero three zero three, score thirty.", candidates, config
    )
    assert result.outcome == ProcessingOutcome.NEEDS_CONFIRMATION

    applied = apply_update(result.proposed_update, backend, audit_log)
    assert applied.outcome == ProcessingOutcome.REJECTED
    assert "Failed to write" in applied.message
    # Workbook must be unchanged.
    assert backend.read_cell(3, "E") is None
    assert backend.write_count == 0

    lines = (tmp_path / "audit.jsonl").read_text(encoding="utf-8").strip().splitlines()
    assert len(lines) == 1
    assert json.loads(lines[0])["event"] == "error"


def test_gender_update_happy_path():
    candidates = make_candidates()
    config = make_config()

    result = process_transcript(
        "Candidate zero zero three zero four, gender woman.", candidates, config
    )
    assert result.outcome == ProcessingOutcome.NEEDS_CONFIRMATION
    assert result.proposed_update.new_value == "female"


def test_full_name_update_happy_path():
    candidates = make_candidates()
    config = make_config()

    result = process_transcript(
        "Candidate zero zero three zero one, full name John Doe.",
        candidates,
        config,
    )
    assert result.outcome == ProcessingOutcome.NEEDS_CONFIRMATION
    assert result.proposed_update.new_value == "John Doe"


def test_find_by_registration_info_only():
    candidates = make_candidates()
    config = make_config()

    result = process_transcript(
        "Find candidate zero zero three zero three.", candidates, config
    )
    assert result.outcome == ProcessingOutcome.INFO_ONLY
    assert result.candidate.full_name == "Ally Awadhi"


def test_candidate_not_found_rejected():
    candidates = make_candidates()
    config = make_config()

    result = process_transcript(
        "Candidate nine nine nine nine nine, score thirty.", candidates, config
    )
    assert result.outcome == ProcessingOutcome.REJECTED


def test_unparseable_transcript_never_writes():
    candidates = make_candidates()
    config = make_config()
    backend = MockExcelBackend(candidates)

    result = process_transcript("um, hello there, how are you", candidates, config)
    assert result.outcome == ProcessingOutcome.REJECTED
    assert backend.write_count == 0
