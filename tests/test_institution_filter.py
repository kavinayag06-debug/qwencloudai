"""Tests for the non-commercial-institution discovery filter."""

from app.connectors.institution_filter import (
    is_institution_name_or_domain,
    is_institution_place_type,
)


def test_school_types_are_institutions():
    assert is_institution_place_type("school") is True
    assert is_institution_place_type("primary_school") is True
    assert is_institution_place_type("secondary_school") is True
    assert is_institution_place_type("university") is True


def test_hospital_and_civic_types_are_institutions():
    assert is_institution_place_type("hospital") is True
    assert is_institution_place_type("local_government_office") is True
    assert is_institution_place_type("community_center") is True
    assert is_institution_place_type("place_of_worship") is True
    assert is_institution_place_type("church") is True
    assert is_institution_place_type("library") is True
    assert is_institution_place_type("police") is True


def test_place_type_matching_is_case_insensitive_and_trims():
    assert is_institution_place_type("Primary_School") is True
    assert is_institution_place_type("  school  ") is True


def test_unknown_or_empty_type_is_not_an_institution():
    """Prefer structured type evidence — absence of evidence is not evidence
    of an institution, so an unrecognized/missing type must never be rejected."""
    assert is_institution_place_type("") is False
    assert is_institution_place_type(None) is False
    assert is_institution_place_type("some_new_google_type_we_dont_know") is False


def test_legitimate_commercial_place_types_are_not_institutions():
    """The exact counterexamples ship-instructions.md calls out by name."""
    assert is_institution_place_type("doctor") is False
    assert is_institution_place_type("dentist") is False
    assert is_institution_place_type("hair_salon") is False
    assert is_institution_place_type("bakery") is False
    assert is_institution_place_type("gym") is False


def test_name_domain_filter_catches_schools_and_government_domains():
    assert is_institution_name_or_domain("Ang Mo Kio Primary School", "https://amkps.moe.edu.sg") is True
    assert is_institution_name_or_domain("Some Local University", "https://someuni.example") is True
    assert is_institution_name_or_domain("Community Health Office", "https://example.gov.sg") is True
    assert is_institution_name_or_domain("National Library Board", "https://nlb.example") is True


def test_name_domain_filter_allows_legitimate_small_businesses():
    """Never rejects commercial tuition centres or private clinics — the
    exact protected categories called out in ship-instructions.md."""
    assert is_institution_name_or_domain("ABC Tuition Centre", "https://abctuition.sg") is False
    assert is_institution_name_or_domain("Sunshine Dental Clinic", "https://sunshinedental.sg") is False
    assert is_institution_name_or_domain("Bright Minds Learning Centre", "https://brightminds.sg") is False
    assert is_institution_name_or_domain("Glamour Cuts Salon", "https://example.com/glamour-cuts") is False
    assert is_institution_name_or_domain("The Bake House", "https://example.com/bake-house") is False


def test_name_domain_filter_handles_missing_fields():
    assert is_institution_name_or_domain("", "") is False
    assert is_institution_name_or_domain("Some Business", "") is False
