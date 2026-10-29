"""Abstract spreadsheet backend interface.

Phase 1 targets Microsoft Excel via xlwings (see spreadsheets/excel.py),
but the interface is kept backend-agnostic so other backends (e.g.
Google Sheets) can be added later without touching command parsing,
validation, or the UI.
"""
from __future__ import annotations

from abc import ABC, abstractmethod
from typing import List, Optional

from src.candidates.models import Candidate


class SpreadsheetError(Exception):
    """Base class for spreadsheet backend errors."""


class WorkbookNotFoundError(SpreadsheetError):
    pass


class WorksheetNotFoundError(SpreadsheetError):
    pass


class WorkbookReadOnlyError(SpreadsheetError):
    pass


class WorkbookProtectedError(SpreadsheetError):
    pass


class SaveFailedError(SpreadsheetError):
    pass


class SpreadsheetBackend(ABC):
    """Interface that all spreadsheet backends must implement."""

    @abstractmethod
    def get_workbook_name(self) -> str:
        ...

    @abstractmethod
    def get_worksheet_name(self) -> str:
        ...

    @abstractmethod
    def read_headers(self) -> List[str]:
        """Return the header row values, in column order, starting at
        the configured registration-number column."""
        ...

    @abstractmethod
    def read_candidates(self) -> List[Candidate]:
        """Return all candidate rows below the header row."""
        ...

    @abstractmethod
    def write_cell(self, row_number: int, column_letter: str, value) -> None:
        """Write a single value into a single cell. Must raise a
        SpreadsheetError subclass on failure, leaving the workbook
        unchanged."""
        ...

    @abstractmethod
    def read_cell(self, row_number: int, column_letter: str):
        """Read a single cell's current value."""
        ...
