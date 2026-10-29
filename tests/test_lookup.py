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

# Real-world-shaped registration numbers (year-dept prefix), as seen in
# the actual exam workbook used for Stage 5 testing.
PREFIXED_CANDIDATES = [
    Candidate(7, "2025-04-00303", "Ally, Ally Awadhi", "M", None),
    Candidate(8, "2025-04-00491", "Assenga, Camillus Isdory", "M", None),
    Candidate(9, "2024-04-00303", "Duplicate Suffix Person", "F", None),  # same suffix, different year
]


def test_exact_registration_match():
    result = find_by_registration_number(CANDIDATES, "00303")
    assert result.status == LookupStatus.FOUND
    assert result.candidate.full_name == "Ally Awadhi"


def test_registration_not_found():
    result = find_by_registration_number(CANDIDATES, "99999")
    assert result.status == LookupStatus.NOT_FOUND


def test_registration_short_suffix_matches_if_unique():
    # "0303" is not an exact match for any candidate, but it IS a
    # unique suffix of "00303" (candidate 3) - our suffix-matching
    # fallback (added so users can speak just the distinguishing part
    # of a longer real-world registration number) should find it.
    result = find_by_registration_number(CANDIDATES, "0303")
    assert result.status == LookupStatus.FOUND
    assert result.candidate.registration_number == "00303"
    assert result.matched_by_suffix


def test_registration_suffix_no_match_when_not_a_suffix():
    # "9999" is not a suffix of any candidate's registration number.
    result = find_by_registration_number(CANDIDATES, "9999")
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


def test_name_lookup_word_order_independent_fallback():
    # Real-world sheet stores "Lastname, Firstname Middlename"; spoken
    # commands use natural order. Word-set fallback should bridge this.
    cands = [
        Candidate(7, "2025-04-00303", "ALLY, ALLY AWADHI", "M", None),
        Candidate(8, "2025-04-00491", "ASSENGA, CAMILLUS ISDORY", "M", None),
    ]
    result = find_by_full_name(cands, "Ally Awadhi")
    assert result.status == LookupStatus.FOUND
    assert result.candidate.registration_number == "2025-04-00303"
    assert result.matched_by_suffix


def test_name_lookup_word_order_fallback_ambiguous_is_refused():
    cands = [
        Candidate(7, "001", "SMITH, JOHN", "M", None),
        Candidate(8, "002", "JOHN, SMITH", "M", None),  # same words, different order
    ]
    result = find_by_full_name(cands, "John Smith")
    assert result.status == LookupStatus.AMBIGUOUS
    assert len(result.matches) == 2


def test_prefixed_registration_exact_match():
    result = find_by_registration_number(PREFIXED_CANDIDATES, "2025-04-00303")
    assert result.status == LookupStatus.FOUND
    assert result.candidate.full_name == "Ally, Ally Awadhi"
    assert not result.matched_by_suffix


def test_prefixed_registration_spoken_suffix_matches_unique_candidate():
    # Spoken as just the distinguishing digits ("00491"), without the
    # year-department prefix that isn't practical to speak every time.
    result = find_by_registration_number(PREFIXED_CANDIDATES, "00491")
    assert result.status == LookupStatus.FOUND
    assert result.candidate.registration_number == "2025-04-00491"
    assert result.matched_by_suffix


def test_prefixed_registration_ambiguous_suffix_is_refused():
    # "00303" is a suffix of BOTH "2025-04-00303" and "2024-04-00303" -
    # must not silently guess which year/department is meant.
    result = find_by_registration_number(PREFIXED_CANDIDATES, "00303")
    assert result.status == LookupStatus.AMBIGUOUS
    assert len(result.matches) == 2
