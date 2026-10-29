from src.candidates.lookup import (
    LookupStatus,
    find_by_full_name,
    find_by_registration_number,
)
from src.candidates.models import Candidate

CANDIDATES = [
    Candidate(2, "00301", "Juma Said", "male", 25),
    Candidate(3, "00303", "Ally Awadhi", "male", None),
    Candidate(4, "00304", "Fatma Hamisi", "female", 50),
    Candidate(5, "00030", "Ally Awadhi", "male", 40),  # duplicate name
]


def test_exact_registration_match():
    result = find_by_registration_number(CANDIDATES, "00303")
    assert result.status == LookupStatus.FOUND
    assert result.candidate.full_name == "Ally Awadhi"


def test_registration_not_found():
    result = find_by_registration_number(CANDIDATES, "99999")
    assert result.status == LookupStatus.NOT_FOUND


def test_registration_leading_zero_distinction():
    # "0303" must NOT match "00303" - exact string match only.
    result = find_by_registration_number(CANDIDATES, "0303")
    assert result.status == LookupStatus.NOT_FOUND


def test_name_lookup_unique():
    result = find_by_full_name(CANDIDATES, "Fatma Hamisi")
    assert result.status == LookupStatus.FOUND
    assert result.candidate.registration_number == "00304"


def test_name_lookup_ambiguous():
    result = find_by_full_name(CANDIDATES, "Ally Awadhi")
    assert result.status == LookupStatus.AMBIGUOUS
    assert len(result.matches) == 2


def test_name_lookup_case_insensitive():
    result = find_by_full_name(CANDIDATES, "fatma hamisi")
    assert result.status == LookupStatus.FOUND
