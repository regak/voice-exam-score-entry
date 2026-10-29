"""Validation rules for scores and gender values.

Pure functions, no side effects, easy to unit test.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Dict, List, Optional, Sequence


@dataclass(frozen=True)
class ValidationResult:
    is_valid: bool
    normalized_value: Optional[object] = None
    error_message: str = ""


def validate_score(
    score_text: str, score_min: float, score_max: float
) -> ValidationResult:
    """Validate a score is numeric and within [score_min, score_max]."""
    try:
        value = float(score_text)
    except (TypeError, ValueError):
        return ValidationResult(
            is_valid=False,
            error_message=f"'{score_text}' is not a valid number.",
        )
    if value < score_min or value > score_max:
        return ValidationResult(
            is_valid=False,
            error_message=(
                f"Score {value} is outside the allowed range "
                f"[{score_min}, {score_max}]."
            ),
        )
    # Represent whole numbers without a trailing ".0" since exam scores
    # are typically integers, but allow fractional scores if configured.
    if value == int(value):
        value = int(value)
    return ValidationResult(is_valid=True, normalized_value=value)


def validate_gender(
    gender_text: str, accepted_genders: Dict[str, Sequence[str]]
) -> ValidationResult:
    """Validate gender text against configurable accepted values.

    `accepted_genders` maps a canonical value (e.g. "male") to a list of
    acceptable spoken synonyms (e.g. ["male", "m", "boy", "man"]).
    """
    normalized = gender_text.strip().lower()
    for canonical, synonyms in accepted_genders.items():
        synonyms_lower = [s.strip().lower() for s in synonyms]
        if normalized in synonyms_lower or normalized == canonical.lower():
            return ValidationResult(is_valid=True, normalized_value=canonical)
    valid_options = ", ".join(accepted_genders.keys())
    return ValidationResult(
        is_valid=False,
        error_message=(
            f"'{gender_text}' is not an accepted gender value. "
            f"Accepted values: {valid_options}."
        ),
    )


def validate_full_name(full_name: str) -> ValidationResult:
    """Basic sanity validation for a spoken full name."""
    cleaned = full_name.strip()
    if not cleaned:
        return ValidationResult(is_valid=False, error_message="Full name is empty.")
    if len(cleaned) < 2:
        return ValidationResult(
            is_valid=False, error_message="Full name is too short to be valid."
        )
    return ValidationResult(is_valid=True, normalized_value=cleaned)
