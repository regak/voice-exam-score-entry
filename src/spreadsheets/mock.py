"""In-memory mock spreadsheet backend used for Stage 1 development and
unit/integration tests, so we can exercise command parsing, candidate
lookup, validation, and update flows without Microsoft Excel installed.
"""
from __future__ import annotations

from typing import Dict, List, Tuple

from src.candidates.models import Candidate
from src.spreadsheets.base import SpreadsheetBackend, WorksheetNotFoundError

_COLUMN_LETTERS = ["registration_number", "full_name", "gender", "score"]


class MockExcelBackend(SpreadsheetBackend):
    """Simulates a worksheet with columns B (reg no), C (name), D
    (gender), E (score), header row 1, data starting row 2 - matching
    the default config - but is configurable for other layouts too.
    """

    def __init__(
        self,
        candidates: List[Candidate],
        workbook_name: str = "mock_workbook.xlsx",
        worksheet_name: str = "Candidates",
        header_row: int = 1,
        columns: Dict[str, str] | None = None,
        headers: Dict[str, str] | None = None,
        read_only: bool = False,
    ):
        self._workbook_name = workbook_name
        self._worksheet_name = worksheet_name
        self._header_row = header_row
        self._columns = columns or {
            "registration_number": "B",
            "full_name": "C",
            "gender": "D",
            "score": "E",
        }
        self._headers = headers or {
            "registration_number": "Registration Number",
            "full_name": "Full Name",
            "gender": "Gender",
            "score": "Score",
        }
        self._read_only = read_only
        # Row number -> Candidate (row_number is 1-indexed as in Excel).
        self._rows: Dict[int, Candidate] = {c.row_number: c for c in candidates}
        self.write_count = 0

    def get_workbook_name(self) -> str:
        return self._workbook_name

    def get_worksheet_name(self) -> str:
        return self._worksheet_name

    def read_headers(self) -> List[str]:
        return [
            self._headers["registration_number"],
            self._headers["full_name"],
            self._headers["gender"],
            self._headers["score"],
        ]

    def read_candidates(self) -> List[Candidate]:
        return [self._rows[r] for r in sorted(self._rows.keys())]

    def read_cell(self, row_number: int, column_letter: str):
        candidate = self._rows.get(row_number)
        if candidate is None:
            return None
        field = self._field_for_column(column_letter)
        return getattr(candidate, field)

    def write_cell(self, row_number: int, column_letter: str, value) -> None:
        if self._read_only:
            from src.spreadsheets.base import WorkbookReadOnlyError

            raise WorkbookReadOnlyError("Mock workbook is read-only.")
        candidate = self._rows.get(row_number)
        if candidate is None:
            raise WorksheetNotFoundError(f"No row {row_number} in mock worksheet.")
        field = self._field_for_column(column_letter)
        updated = _replace_field(candidate, field, value)
        self._rows[row_number] = updated
        self.write_count += 1

    def _field_for_column(self, column_letter: str) -> str:
        for field, letter in self._columns.items():
            if letter == column_letter:
                return field
        raise ValueError(f"Unknown column letter '{column_letter}'")


def _replace_field(candidate: Candidate, field: str, value) -> Candidate:
    kwargs = {
        "row_number": candidate.row_number,
        "registration_number": candidate.registration_number,
        "full_name": candidate.full_name,
        "gender": candidate.gender,
        "score": candidate.score,
    }
    kwargs[field] = value
    return Candidate(**kwargs)
