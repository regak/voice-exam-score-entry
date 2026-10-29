"""Candidate lookup with safety rules.

Rules enforced here (see project spec section 5):
- Exact registration-number matching is preferred.
- If a registration number or name search matches more than one record,
  do NOT silently pick one - report ambiguity instead.
- Full-name lookup requires a unique match.
"""
from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from typing import List, Optional, Sequence

from src.candidates.models import Candidate


class LookupStatus(str, Enum):
    FOUND = "found"
    NOT_FOUND = "not_found"
    AMBIGUOUS = "ambiguous"


@dataclass(frozen=True)
class LookupResult:
    status: LookupStatus
    candidate: Optional[Candidate] = None
    matches: Sequence[Candidate] = ()
    message: str = ""


def find_by_registration_number(
    candidates: Sequence[Candidate], registration_number: str
) -> LookupResult:
    """Exact-match lookup by registration number (string comparison, so
    leading zeros matter)."""
    matches = [c for c in candidates if c.registration_number == registration_number]
    return _result_from_matches(matches, f"registration number '{registration_number}'")


def find_by_full_name(
    candidates: Sequence[Candidate], full_name: str
) -> LookupResult:
    """Case-insensitive exact-match lookup by full name. Requires a
    unique match."""
    target = full_name.strip().lower()
    matches = [c for c in candidates if c.full_name.strip().lower() == target]
    return _result_from_matches(matches, f"name '{full_name}'")


def _result_from_matches(matches: List[Candidate], description: str) -> LookupResult:
    if len(matches) == 0:
        return LookupResult(
            status=LookupStatus.NOT_FOUND,
            matches=(),
            message=f"No candidate found matching {description}.",
        )
    if len(matches) > 1:
        return LookupResult(
            status=LookupStatus.AMBIGUOUS,
            matches=tuple(matches),
            message=(
                f"{len(matches)} candidates match {description}; "
                "refusing to guess. Please use a more specific identifier."
            ),
        )
    return LookupResult(
        status=LookupStatus.FOUND,
        candidate=matches[0],
        matches=tuple(matches),
        message=f"Found unique candidate matching {description}.",
    )
