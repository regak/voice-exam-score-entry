"""Microsoft Excel backend using xlwings.

Connects to an already-open Excel workbook where possible (per spec
section 6), with the option to open a specific file if no suitable
workbook is open. Column letters, header row, and registration-number
text formatting are all configuration-driven (see src/config.py).

Design notes / safety:
- We NEVER create a new workbook. If no workbook is open and no
  `workbook_path` is configured, callers must prompt the user to pick
  a file explicitly (handled in connect_to_workbook()).
- Registration numbers are always read/written as text so leading
  zeros survive (Excel's own "format as text" + we write Python str).
- All failure modes map onto the SpreadsheetError subclasses from
  src/spreadsheets/base.py so the rest of the app (workflow.py) can
  handle them uniformly regardless of backend.
- Writes go through `write_cell`, which performs the single COM write
  and raises immediately without partially mutating other cells if it
  fails, and never calls wb.save() (the user keeps control over saving
  through Excel itself, or we expose an explicit save() method).
"""
from __future__ import annotations

from pathlib import Path
from typing import List, Optional

from src.candidates.models import Candidate
from src.spreadsheets.base import (
    SaveFailedError,
    SpreadsheetBackend,
    SpreadsheetError,
    WorkbookNotFoundError,
    WorkbookProtectedError,
    WorkbookReadOnlyError,
    WorksheetNotFoundError,
)

try:
    import xlwings as xw
except ImportError:  # pragma: no cover - exercised only when xlwings missing
    xw = None


def _require_xlwings():
    if xw is None:
        raise SpreadsheetError(
            "xlwings is not installed. Run: pip install -r requirements.txt"
        )


def list_open_workbooks() -> List[str]:
    """Return the full names of all workbooks currently open in any
    running Excel instance. Empty list if Excel is not running."""
    _require_xlwings()
    names = []
    try:
        for app in xw.apps:
            for book in app.books:
                names.append(book.fullname)
    except Exception:
        # Excel not running / COM not reachable - treat as "none open".
        return []
    return names


class ExcelBackend(SpreadsheetBackend):
    """Spreadsheet backend that talks to a real Microsoft Excel
    workbook via xlwings.

    Use `connect_to_workbook()` to construct an instance rather than
    calling the constructor directly, since connecting involves
    several fallback rules (already-open vs. explicit path) and
    failure handling that doesn't belong in __init__.
    """

    def __init__(
        self,
        book: "xw.Book",
        worksheet_name: Optional[str],
        header_row: int,
        columns,
        treat_registration_number_as_text: bool = True,
    ):
        self._book = book
        self._header_row = header_row
        self._columns = columns
        self._treat_reg_as_text = treat_registration_number_as_text

        try:
            if worksheet_name:
                self._sheet = book.sheets[worksheet_name]
            else:
                self._sheet = book.sheets.active
        except Exception as exc:
            raise WorksheetNotFoundError(
                f"Worksheet '{worksheet_name}' not found in workbook "
                f"'{book.name}'."
            ) from exc

    # -- SpreadsheetBackend interface -----------------------------------

    def get_workbook_name(self) -> str:
        return self._book.name

    def get_worksheet_name(self) -> str:
        return self._sheet.name

    def read_headers(self) -> List[str]:
        try:
            row = self._header_row
            return [
                self._read_raw(row, self._columns.registration_number),
                self._read_raw(row, self._columns.full_name),
                self._read_raw(row, self._columns.gender),
                self._read_raw(row, self._columns.score),
            ]
        except Exception as exc:
            raise SpreadsheetError(f"Failed to read header row: {exc}") from exc

    def read_candidates(self) -> List[Candidate]:
        try:
            reg_col = self._columns.registration_number
            data_start_row = self._header_row + 1
            # Find the last used row by scanning the registration-number
            # column; stop at the first fully-empty row to avoid
            # sweeping the entire 1M-row sheet. Rows whose "registration
            # number" cell has no digits at all (e.g. a trailing
            # summary/average row using "-" as a placeholder) are
            # skipped rather than treated as a malformed candidate -
            # they are not blank, but they are clearly not real
            # candidate rows either.
            candidates: List[Candidate] = []
            row = data_start_row
            empty_streak = 0
            max_empty_streak = 5  # tolerate a few blank rows, then stop
            while empty_streak < max_empty_streak:
                reg_value = self._read_raw(row, reg_col)
                reg_str = "" if reg_value is None else str(reg_value).strip()
                if reg_str == "":
                    empty_streak += 1
                    row += 1
                    continue
                if not any(ch.isdigit() for ch in reg_str):
                    # Non-candidate row (e.g. "-" / "AVERAGE" summary
                    # row). Don't count it as empty (so we don't stop
                    # scanning early if real rows follow), just skip it.
                    row += 1
                    continue
                empty_streak = 0
                full_name = self._read_raw(row, self._columns.full_name)
                gender = self._read_raw(row, self._columns.gender)
                score_raw = self._read_raw(row, self._columns.score)
                score = _parse_optional_float(score_raw)
                candidates.append(
                    Candidate(
                        row_number=row,
                        registration_number=_normalize_registration(reg_value),
                        full_name=str(full_name).strip() if full_name else "",
                        gender=str(gender).strip() if gender else None,
                        score=score,
                    )
                )
                row += 1
            return candidates
        except SpreadsheetError:
            raise
        except Exception as exc:
            raise SpreadsheetError(f"Failed to read candidate rows: {exc}") from exc

    def read_cell(self, row_number: int, column_letter: str):
        try:
            return self._read_raw(row_number, column_letter)
        except Exception as exc:
            raise SpreadsheetError(
                f"Failed to read cell {column_letter}{row_number}: {exc}"
            ) from exc

    def write_cell(self, row_number: int, column_letter: str, value) -> None:
        cell_ref = f"{column_letter}{row_number}"
        try:
            if self._book.app.api.ActiveProtectedViewWindow is not None:
                pass  # some Excel versions expose this; best-effort, ignore errors
        except Exception:
            pass

        try:
            sheet_protected = bool(self._sheet.api.ProtectContents)
        except Exception:
            sheet_protected = False
        if sheet_protected:
            raise WorkbookProtectedError(
                f"Worksheet '{self._sheet.name}' is protected; cannot write "
                f"to {cell_ref}."
            )

        try:
            cell = self._sheet.range(cell_ref)
            if column_letter == self._columns.registration_number and (
                self._treat_reg_as_text
            ):
                cell.number_format = "@"
                cell.value = str(value)
            else:
                cell.value = value
        except Exception as exc:
            message = str(exc)
            if "read-only" in message.lower() or "read only" in message.lower():
                raise WorkbookReadOnlyError(
                    f"Workbook is read-only; cannot write to {cell_ref}."
                ) from exc
            raise SpreadsheetError(
                f"Failed to write to cell {cell_ref}: {exc}"
            ) from exc

    def save(self) -> None:
        """Explicitly save the workbook. Not called automatically by
        write_cell(), so the user stays in control of when the file
        hits disk (and can review their own undo history in Excel)."""
        try:
            self._book.save()
        except Exception as exc:
            raise SaveFailedError(f"Failed to save workbook: {exc}") from exc

    # -- internal helpers -------------------------------------------------

    def _read_raw(self, row_number: int, column_letter: str):
        return self._sheet.range(f"{column_letter}{row_number}").value


def _normalize_registration(value) -> str:
    """Convert a cell value into the string form we use everywhere
    else, preserving the exact text. Excel may hand back numeric
    registration numbers as floats (e.g. 303.0) if the cell wasn't
    formatted as text - we strip a trailing '.0' in that case, but this
    loses leading zeros, which is exactly why the config defaults to
    treat_registration_number_as_text=True and we write with
    number_format='@'.
    """
    if isinstance(value, float) and value.is_integer():
        return str(int(value))
    return str(value).strip()


def _parse_optional_float(value) -> Optional[float]:
    if value is None or str(value).strip() == "":
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def connect_to_workbook(
    workbook_path: Optional[str],
    worksheet_name: Optional[str],
    header_row: int,
    columns,
    treat_registration_number_as_text: bool = True,
    file_picker=None,
) -> ExcelBackend:
    """Connect to a workbook following the priority rules from the spec:

    1. If `workbook_path` is configured and that workbook is already
       open in a running Excel instance, attach to it (no new Excel
       process, no re-opening).
    2. Else if `workbook_path` is configured but not currently open,
       open it in Excel (visible, so the user sees what's happening).
    3. Else if exactly one workbook is open across all running Excel
       instances, attach to that one.
    4. Else if multiple workbooks are open and none is configured, ask
       the caller to disambiguate (raises WorkbookNotFoundError with a
       descriptive message listing the open workbooks) - we never guess.
    5. Else (no workbook open, none configured) call `file_picker()` if
       provided to let the user choose a file; otherwise raise.

    We never create a new workbook.
    """
    _require_xlwings()

    open_books = {}
    try:
        for app in xw.apps:
            for book in app.books:
                open_books[Path(book.fullname).resolve()] = book
    except Exception:
        open_books = {}

    chosen_book = None

    if workbook_path:
        target = Path(workbook_path).resolve()
        if target in open_books:
            chosen_book = open_books[target]
        else:
            if not target.exists():
                raise WorkbookNotFoundError(f"Workbook not found: {workbook_path}")
            try:
                app = xw.apps.active if xw.apps else xw.App(visible=True)
                chosen_book = app.books.open(str(target))
            except Exception as exc:
                raise WorkbookNotFoundError(
                    f"Failed to open workbook '{workbook_path}': {exc}"
                ) from exc
    elif len(open_books) == 1:
        chosen_book = next(iter(open_books.values()))
    elif len(open_books) > 1:
        names = ", ".join(str(p) for p in open_books)
        raise WorkbookNotFoundError(
            "Multiple workbooks are open and none is configured in "
            f"config.json ('excel.workbook_path'). Open workbooks: {names}. "
            "Please set excel.workbook_path or close the others."
        )
    else:
        if file_picker is not None:
            picked = file_picker()
            if not picked:
                raise WorkbookNotFoundError(
                    "No workbook selected and none is open in Excel."
                )
            picked_path = Path(picked).resolve()
            if not picked_path.exists():
                raise WorkbookNotFoundError(f"Workbook not found: {picked}")
            try:
                app = xw.apps.active if xw.apps else xw.App(visible=True)
                chosen_book = app.books.open(str(picked_path))
            except Exception as exc:
                raise WorkbookNotFoundError(
                    f"Failed to open workbook '{picked}': {exc}"
                ) from exc
        else:
            raise WorkbookNotFoundError(
                "No workbook is open in Excel and none is configured. "
                "Open a workbook in Excel or set 'excel.workbook_path' "
                "in config.json."
            )

    return ExcelBackend(
        book=chosen_book,
        worksheet_name=worksheet_name,
        header_row=header_row,
        columns=columns,
        treat_registration_number_as_text=treat_registration_number_as_text,
    )
