"""Deterministic parser: turns a raw transcript string into a Command.

Design goals (see project spec section 4-5):
- No LLM. Pure rule-based parsing so behaviour is predictable and testable.
- Must NOT produce a "valid" write command unless the transcript clearly
  matches one of the supported shapes. Ambiguous/unmatched input becomes
  UnrecognizedCommand rather than guessing.
- Registration numbers are kept as strings, digit-by-digit, preserving
  leading zeros and not assuming a fixed length.
"""
from __future__ import annotations

import re
from typing import List, Optional, Tuple

from src.commands.number_words import (
    tokens_to_digit_string,
    words_to_cardinal_number,
)
from src.commands.schema import (
    Command,
    FindByNameCommand,
    FindByRegistrationCommand,
    SetFullNameCommand,
    SetGenderCommand,
    SetScoreCommand,
    UnrecognizedCommand,
)

# Keywords that introduce the "field" part of a candidate-update command.
_SCORE_KEYWORDS = ("score", "mark", "marks", "grade")
_GENDER_KEYWORDS = ("gender", "sex")
_NAME_KEYWORDS = ("full name", "name")

_FIND_PREFIX = re.compile(r"^\s*find\s+candidate\s+(.*)$", re.IGNORECASE)
_CANDIDATE_PREFIX = re.compile(r"^\s*candidate\s+(.*)$", re.IGNORECASE)


def _normalize(text: str) -> str:
    text = text.strip().lower()
    # Treat commas/periods as soft separators; collapse whitespace.
    text = text.replace(",", " , ")
    text = re.sub(r"[^a-z0-9', ]", " ", text)
    text = re.sub(r"\s+", " ", text).strip()
    return text


def _tokenize(text: str) -> List[str]:
    return [t for t in text.split(" ") if t and t != ","]


def _looks_like_registration_tokens(tokens: List[str]) -> bool:
    """True if every token is a digit literal or a single-digit word."""
    if not tokens:
        return False
    return tokens_to_digit_string(tokens) is not None


def _split_on_first_keyword(
    tokens: List[str], keywords: Tuple[str, ...]
) -> Optional[Tuple[List[str], str, List[str]]]:
    """Find the first occurrence of any keyword (single or two-word) in
    tokens; return (before, matched_keyword, after). None if not found.
    """
    n = len(tokens)
    for i in range(n):
        for kw in keywords:
            kw_parts = kw.split(" ")
            kw_len = len(kw_parts)
            if tokens[i : i + kw_len] == kw_parts:
                return tokens[:i], kw, tokens[i + kw_len :]
    return None


def parse_command(raw_text: str) -> Command:
    """Parse a raw transcript into a Command.

    Never raises for malformed/unexpected input - returns
    UnrecognizedCommand instead, so the caller can safely refuse to act.
    """
    if raw_text is None or not raw_text.strip():
        return UnrecognizedCommand(raw_text=raw_text or "", reason="Empty transcript")

    normalized = _normalize(raw_text)
    tokens = _tokenize(normalized)

    # --- "find candidate ..." ---
    find_match = _FIND_PREFIX.match(normalized)
    if find_match:
        remainder_tokens = _tokenize(find_match.group(1))
        if not remainder_tokens:
            return UnrecognizedCommand(
                raw_text=raw_text, reason="'find candidate' missing a target"
            )
        if _looks_like_registration_tokens(remainder_tokens):
            regno = tokens_to_digit_string(remainder_tokens)
            return FindByRegistrationCommand(registration_number=regno)
        # Otherwise treat as a full name lookup.
        full_name = " ".join(w.capitalize() for w in remainder_tokens)
        return FindByNameCommand(full_name=full_name)

    # --- "candidate <regno>, <field> <value>" ---
    candidate_match = _CANDIDATE_PREFIX.match(normalized)
    if candidate_match:
        remainder_tokens = _tokenize(candidate_match.group(1))
        # Strip a leading stray comma token if present.
        if remainder_tokens and remainder_tokens[0] == ",":
            remainder_tokens = remainder_tokens[1:]

        # Try splitting on each known field keyword set, trying the
        # longest/most-specific keywords first (full name before name).
        for keywords, builder in (
            (_SCORE_KEYWORDS, "score"),
            ((_GENDER_KEYWORDS), "gender"),
            (_NAME_KEYWORDS, "name"),
        ):
            split = _split_on_first_keyword(remainder_tokens, keywords)
            if split is None:
                continue
            before, _kw, after = split
            # Remove any trailing comma token from the registration part.
            before = [t for t in before if t != ","]
            if not before:
                return UnrecognizedCommand(
                    raw_text=raw_text,
                    reason="Missing registration number before field keyword",
                )
            if not _looks_like_registration_tokens(before):
                return UnrecognizedCommand(
                    raw_text=raw_text,
                    reason="Could not interpret registration number",
                )
            regno = tokens_to_digit_string(before)
            value_tokens = [t for t in after if t != ","]
            if not value_tokens:
                return UnrecognizedCommand(
                    raw_text=raw_text, reason=f"Missing value for {builder}"
                )

            if builder == "score":
                number = words_to_cardinal_number(value_tokens)
                if number is None:
                    return UnrecognizedCommand(
                        raw_text=raw_text, reason="Could not interpret score value"
                    )
                return SetScoreCommand(
                    registration_number=regno, score_text=str(number)
                )
            if builder == "gender":
                gender_text = " ".join(value_tokens)
                return SetGenderCommand(
                    registration_number=regno, gender_text=gender_text
                )
            if builder == "name":
                full_name = " ".join(w.capitalize() for w in value_tokens)
                return SetFullNameCommand(
                    registration_number=regno, full_name=full_name
                )

        return UnrecognizedCommand(
            raw_text=raw_text,
            reason="Recognized 'candidate' but no known field keyword "
            "(score/gender/full name) found",
        )

    return UnrecognizedCommand(
        raw_text=raw_text,
        reason="Transcript did not match any known command pattern",
    )
