"""Tests for NAICS → industry-title resolution (OSHA 300A "Industry description").

Pure-helper unit tests — no app boot, no DB. Backs the auto-fill of the
300A PDF industry-description field and the ITA CSV industry_description
column from the establishment's NAICS code.
"""
from app.matcha.services.naics_titles import naics_industry_description


def test_six_digit_resolves_to_subsector():
    # OSHA's own example code. 336 = Transportation Equipment Manufacturing.
    assert naics_industry_description("336212") == "Transportation Equipment Manufacturing"


def test_four_digit_resolves_to_subsector():
    assert naics_industry_description("3361") == "Transportation Equipment Manufacturing"


def test_three_digit_exact_subsector():
    assert naics_industry_description("622") == "Hospitals"
    assert naics_industry_description("623") == "Nursing and Residential Care Facilities"


def test_two_digit_sector():
    assert naics_industry_description("62") == "Health Care and Social Assistance"
    assert naics_industry_description("23") == "Construction"


def test_manufacturing_range_all_prefixes():
    # 31, 32, 33 all → Manufacturing at the 2-digit level.
    assert naics_industry_description("31") == "Manufacturing"
    assert naics_industry_description("32") == "Manufacturing"
    assert naics_industry_description("33") == "Manufacturing"
    # ...and a 6-digit code whose subsector isn't listed still falls back.
    assert naics_industry_description("3259") == "Chemical Manufacturing"  # 325 subsector


def test_retail_and_transport_ranges():
    assert naics_industry_description("455211") == "General Merchandise Retailers"  # 455
    assert naics_industry_description("45") == "Retail Trade"
    assert naics_industry_description("484121") == "Truck Transportation"  # 484
    assert naics_industry_description("49") == "Transportation and Warehousing"


def test_longest_prefix_subsector_beats_sector():
    # 541xxx must resolve to the 541 subsector, not just the 54 sector.
    assert naics_industry_description("541511") == "Professional, Scientific, and Technical Services"


def test_non_digit_characters_stripped():
    assert naics_industry_description("3362-12") == "Transportation Equipment Manufacturing"
    assert naics_industry_description(" 622 ") == "Hospitals"


def test_unknown_or_empty_returns_none():
    assert naics_industry_description(None) is None
    assert naics_industry_description("") is None
    assert naics_industry_description("   ") is None
    assert naics_industry_description("abc") is None
    assert naics_industry_description("3") is None       # < 2 digits
    assert naics_industry_description("99") is None       # unmapped sector
