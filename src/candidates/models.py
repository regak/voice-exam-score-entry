"""Candidate record model and in-memory representation.

A Candidate always carries its source row number (1-indexed spreadsheet
row) so that updates can be written back unambiguously.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Optional


@dataclass(frozen=True)
class Candidate:
    row_number: int
    registration_number: str
    full_name: str
    gender: Optional[str]
    score: Optional[float]
