"""Candidate lookup with safety rules.

Rules enforced here (see project spec section 5):
- Exact registration-number matching is preferred.
- If a registration number or name search matches more than one record,
  do NOT silently pick one - report ambiguity instead.
- Full-name lookup requires a unique match.

Registration number suffix matching:
- Real registration numbers may include a non-spoken prefix (e.g. a
  year/department code like "2025-04-00303"). Speaking the full
  prefix digit-by-digit every time is impractical, so a spoken
  registration number that doesn't exactly match any candidate is
  also tried as a *suffix* of each candidate's digits-only
  registration number. A suffix match is only accepted if it is
  unique across all candidates - otherwise it's treated exactly like
  any other ambiguous match (refused, not guessed).
"""
from __future__ import annotations

import re
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
    matched_by_suffix: bool = False


def _digits_only(value: str) -> str:
    return re.sub(r"\D", "", value or "")


def find_by_registration_number(
    candidates: Sequence[Candidate], registration_number: str
) -> LookupResult:
    """Lookup by registration number.

    1. Exact string match first (preferred, per spec).
    2. If no exact match, fall back to matching the spoken digits as a
       suffix of each candidate's digits-only registration number
       (e.g. spoken "00303" matches stored "2025-04-00303"). This
       fallback only succeeds if exactly one candidate's registration
       number ends with those digits; multiple matches are reported as
       ambiguous rather than guessed, same as any other ambiguity.
    """
    exact_matches = [
        c for c in candidates if c.registration_number == registration_number
    ]
    if exact_matches:
        return _result_from_matches(
            exact_matches, f"registration number '{registration_number}'"
        )

    spoken_digits = _digits_only(registration_number)
    if spoken_digits:
        suffix_matches = [
            c
            for c in candidates
            if _digits_only(c.registration_number).endswith(spoken_digits)
            and _digits_only(c.registration_number) != spoken_digits
        ]
        if suffix_matches:
            result = _result_from_matches(
                suffix_matches,
                f"registration number ending in '{registration_number}'",
            )
            if result.status == LookupStatus.FOUND:
                return LookupResult(
                    status=result.status,
                    candidate=result.candidate,
                    matches=result.matches,
                    message=(
                        f"Found unique candidate whose registration number "
                        f"ends in '{registration_number}' "
                        f"({result.candidate.registration_number})."
                    ),
                    matched_by_suffix=True,
                )
            return LookupResult(
                status=result.status,
                matches=result.matches,
                message=result.message,
                matched_by_suffix=True,
            )

    return LookupResult(
        status=LookupStatus.NOT_FOUND,
        matches=(),
        message=f"No candidate found matching registration number '{registration_number}'.",
    )


def _normalize_name_words(name: str) -> List[str]:
    """Split a name into lowercase word tokens, ignoring commas and
    punctuation, so names can be compared regardless of word order
    (e.g. "ALLY, ALLY AWADHI" vs spoken "Ally Awadhi")."""
    cleaned = re.sub(r"[^a-zA-Z\s]", " ", name or "")
    return [w.lower() for w in cleaned.split() if w]


def find_by_full_name(
    candidates: Sequence[Candidate], full_name: str
) -> LookupResult:
    """Lookup by full name.

    1. Case-insensitive exact-match first (preferred).
    2. If no exact match, fall back to comparing the *set* of words
       regardless of order (e.g. stored "ALLY, ALLY AWADHI" matches
       spoken "Ally Awadhi" even though the stored format is
       "Lastname, Firstname Middlename" and the spoken form is natural
       order). This only succeeds if exactly one candidate's name has
       the same set of words; ties are reported as ambiguous rather
       than guessed.
    """
    target = full_name.strip().lower()
    exact_matches = [c for c in candidates if c.full_name.strip().lower() == target]
    if exact_matches:
        return _result_from_matches(exact_matches, f"name '{full_name}'")

    target_words = set(_normalize_name_words(full_name))
    if target_words:
        word_set_matches = [
            c
            for c in candidates
            if set(_normalize_name_words(c.full_name)) == target_words
        ]
        if word_set_matches:
            result = _result_from_matches(
                word_set_matches, f"name matching the words in '{full_name}'"
            )
            if result.status == LookupStatus.FOUND:
                return LookupResult(
                    status=result.status,
                    candidate=result.candidate,
                    matches=result.matches,
                    message=(
                        f"Found unique candidate whose name matches the "
                        f"words in '{full_name}' ({result.candidate.full_name})."
                    ),
                    matched_by_suffix=True,
                )
            return LookupResult(
                status=result.status,
                matches=result.matches,
                message=result.message,
                matched_by_suffix=True,
            )

    return LookupResult(
        status=LookupStatus.NOT_FOUND,
        matches=(),
        message=f"No candidate found matching name '{full_name}'.",
    )


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
