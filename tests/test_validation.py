import pytest

from src.validation.rules import validate_full_name, validate_gender, validate_score

ACCEPTED_GENDERS = {
    "male": ["male", "m", "boy", "man"],
    "female": ["female", "f", "girl", "woman"],
}


def test_valid_score_in_range():
    r = validate_score("30", 0, 60)
    assert r.is_valid
    assert r.normalized_value == 30


def test_score_at_boundaries():
    assert validate_score("0", 0, 60).is_valid
    assert validate_score("60", 0, 60).is_valid


def test_score_below_min():
    r = validate_score("-1", 0, 60)
    assert not r.is_valid


def test_score_above_max():
    r = validate_score("61", 0, 60)
    assert not r.is_valid


def test_score_non_numeric():
    r = validate_score("abc", 0, 60)
    assert not r.is_valid


def test_valid_gender_canonical():
    r = validate_gender("male", ACCEPTED_GENDERS)
    assert r.is_valid
    assert r.normalized_value == "male"


def test_valid_gender_synonym():
    r = validate_gender("boy", ACCEPTED_GENDERS)
    assert r.is_valid
    assert r.normalized_value == "male"


def test_invalid_gender():
    r = validate_gender("robot", ACCEPTED_GENDERS)
    assert not r.is_valid


def test_valid_full_name():
    r = validate_full_name("Ally Awadhi")
    assert r.is_valid
    assert r.normalized_value == "Ally Awadhi"


def test_empty_full_name():
    r = validate_full_name("   ")
    assert not r.is_valid
