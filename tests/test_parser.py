import pytest

from src.commands.parser import parse_command
from src.commands.schema import (
    FindByNameCommand,
    FindByRegistrationCommand,
    SetFullNameCommand,
    SetGenderCommand,
    SetScoreCommand,
    UnrecognizedCommand,
)


def test_set_score_digit_by_digit_registration():
    cmd = parse_command("Candidate zero zero three zero three, score thirty.")
    assert isinstance(cmd, SetScoreCommand)
    assert cmd.registration_number == "00303"
    assert cmd.score_text == "30.0" or cmd.score_text == "30"


def test_set_score_numeric_registration():
    cmd = parse_command("Candidate 00303, score 45.")
    assert isinstance(cmd, SetScoreCommand)
    assert cmd.registration_number == "00303"


def test_set_score_compound_number():
    cmd = parse_command("Candidate zero zero three zero three, score forty five.")
    assert isinstance(cmd, SetScoreCommand)
    assert float(cmd.score_text) == 45.0


def test_set_gender_male():
    cmd = parse_command("Candidate zero zero three zero three, gender male.")
    assert isinstance(cmd, SetGenderCommand)
    assert cmd.registration_number == "00303"
    assert cmd.gender_text == "male"


def test_set_full_name():
    cmd = parse_command("Candidate zero zero three zero three, full name Ally Awadhi.")
    assert isinstance(cmd, SetFullNameCommand)
    assert cmd.registration_number == "00303"
    assert cmd.full_name == "Ally Awadhi"


def test_find_by_registration():
    cmd = parse_command("Find candidate zero zero three zero three.")
    assert isinstance(cmd, FindByRegistrationCommand)
    assert cmd.registration_number == "00303"


def test_find_by_name():
    cmd = parse_command("Find candidate Ally Awadhi.")
    assert isinstance(cmd, FindByNameCommand)
    assert cmd.full_name == "Ally Awadhi"


def test_empty_transcript_is_unrecognized():
    cmd = parse_command("")
    assert isinstance(cmd, UnrecognizedCommand)


def test_gibberish_is_unrecognized():
    cmd = parse_command("the weather is nice today")
    assert isinstance(cmd, UnrecognizedCommand)


def test_candidate_without_field_keyword_is_unrecognized():
    cmd = parse_command("Candidate zero zero three zero three is here")
    assert isinstance(cmd, UnrecognizedCommand)


def test_candidate_missing_registration_is_unrecognized():
    cmd = parse_command("Candidate score thirty")
    assert isinstance(cmd, UnrecognizedCommand)


def test_variation_with_sex_keyword():
    cmd = parse_command("Candidate zero zero three zero three, sex female.")
    assert isinstance(cmd, SetGenderCommand)
    assert cmd.gender_text == "female"


def test_variation_mark_keyword_for_score():
    cmd = parse_command("Candidate zero zero three zero three, mark thirty two.")
    assert isinstance(cmd, SetScoreCommand)
    assert float(cmd.score_text) == 32.0


def test_leading_zeros_preserved():
    cmd = parse_command("Candidate zero zero zero one, score ten.")
    assert isinstance(cmd, SetScoreCommand)
    assert cmd.registration_number == "0001"
    assert len(cmd.registration_number) == 4
