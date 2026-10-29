"""Utilities for converting spoken number words into digits.

Two distinct use-cases are supported:

1. Registration numbers are typically spoken digit-by-digit
   ("zero zero three zero three" -> "00303"), so leading zeros and
   length are preserved exactly as spoken.
2. Scores are spoken as ordinary cardinal numbers ("thirty five" -> 35),
   so standard word-to-number composition rules apply.
"""
from __future__ import annotations

from typing import List, Optional

SINGLE_DIGIT_WORDS = {
    "zero": 0,
    "oh": 0,
    "o": 0,
    "one": 1,
    "two": 2,
    "three": 3,
    "four": 4,
    "five": 5,
    "six": 6,
    "seven": 7,
    "eight": 8,
    "nine": 9,
}

TEEN_WORDS = {
    "ten": 10,
    "eleven": 11,
    "twelve": 12,
    "thirteen": 13,
    "fourteen": 14,
    "fifteen": 15,
    "sixteen": 16,
    "seventeen": 17,
    "eighteen": 18,
    "nineteen": 19,
}

TENS_WORDS = {
    "twenty": 20,
    "thirty": 30,
    "forty": 40,
    "fourty": 40,  # common misspelling/mishearing
    "fifty": 50,
    "sixty": 60,
    "seventy": 70,
    "eighty": 80,
    "ninety": 90,
}

ALL_NUMBER_WORDS = {**SINGLE_DIGIT_WORDS, **TEEN_WORDS, **TENS_WORDS}


def word_to_single_digit(word: str) -> Optional[int]:
    """Return the digit 0-9 for a single-digit number word, else None."""
    return SINGLE_DIGIT_WORDS.get(word.lower())


def tokens_to_digit_string(tokens: List[str]) -> Optional[str]:
    """Convert a sequence of tokens, each a digit-word or literal digits,
    into a concatenated digit string. Returns None if any token cannot
    be interpreted as digits (so callers can reject the whole sequence
    rather than guess).
    """
    digits: List[str] = []
    for tok in tokens:
        if tok.isdigit():
            digits.append(tok)
            continue
        digit = word_to_single_digit(tok)
        if digit is None:
            return None
        digits.append(str(digit))
    if not digits:
        return None
    return "".join(digits)


def words_to_cardinal_number(tokens: List[str]) -> Optional[float]:
    """Convert a short sequence of number words/digits into a cardinal
    number, e.g. ["thirty", "five"] -> 35, ["forty"] -> 40, ["7"] -> 7.
    Returns None if the tokens do not form a recognizable number.
    """
    if not tokens:
        return None

    # Single pure-digit token, possibly with a decimal point.
    if len(tokens) == 1 and _is_number_literal(tokens[0]):
        return float(tokens[0])

    total = 0
    matched_any = False
    for tok in tokens:
        tok_lower = tok.lower()
        if _is_number_literal(tok):
            total += float(tok)
            matched_any = True
        elif tok_lower in TENS_WORDS:
            total += TENS_WORDS[tok_lower]
            matched_any = True
        elif tok_lower in TEEN_WORDS:
            total += TEEN_WORDS[tok_lower]
            matched_any = True
        elif tok_lower in SINGLE_DIGIT_WORDS:
            total += SINGLE_DIGIT_WORDS[tok_lower]
            matched_any = True
        elif tok_lower == "and":
            continue
        else:
            return None
    if not matched_any:
        return None
    return float(total)


def _is_number_literal(tok: str) -> bool:
    try:
        float(tok)
        return True
    except ValueError:
        return False
