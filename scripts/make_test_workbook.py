"""Build a temporary synthetic Excel workbook for Stage 2 integration
testing. Creates a workbook with the standard B/C/D/E layout (header
row 1, data starting row 2) and a handful of fake candidates.

Usage:
    python scripts/make_test_workbook.py <output_path.xlsx>
"""
from __future__ import annotations

import sys
from pathlib import Path

import xlwings as xw


def build_workbook(path: str) -> None:
    app = xw.App(visible=True)
    try:
        book = app.books.add()
        sheet = book.sheets.active
        sheet.name = "Candidates"

        headers = ["", "Registration Number", "Full Name", "Gender", "Score"]
        for col_idx, header in enumerate(headers, start=1):
            if header:
                sheet.cells(1, col_idx).value = header

        rows = [
            ("00301", "Juma Said", "Male", 25),
            ("00303", "Ally Awadhi", "Male", None),
            ("00304", "Fatma Hamisi", "Female", 50),
            ("00030", "Imposter Duplicate Name", "Male", 10),
        ]
        # Registration numbers must stay text so leading zeros survive.
        reg_col_letter = "B"
        for row_idx, (regno, name, gender, score) in enumerate(rows, start=2):
            reg_cell = sheet.range(f"{reg_col_letter}{row_idx}")
            reg_cell.number_format = "@"
            reg_cell.value = regno
            sheet.cells(row_idx, 3).value = name
            sheet.cells(row_idx, 4).value = gender
            sheet.cells(row_idx, 5).value = score

        book.save(str(Path(path).resolve()))
        print(f"Saved test workbook to {path}")
    finally:
        pass  # leave Excel + workbook open for the caller to use/inspect


if __name__ == "__main__":
    out_path = sys.argv[1] if len(sys.argv) > 1 else "test_workbook.xlsx"
    build_workbook(out_path)
