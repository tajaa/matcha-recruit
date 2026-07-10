"""Golden fixture schema, comparators, and effective-date windowing.

These tests are the guard rail on the curation workflow: a fixture that would
assert nonsense (a fact with no authority URL, an unknown comparator, a window
that never opens) fails here rather than silently scoring the catalog.
"""
from datetime import date

import pytest
from pydantic import ValidationError

from app.core.compliance_registry import CATEGORY_KEYS
from app.core.services.compliance_evals.golden import (
    GoldenFact,
    compare,
    load_fixtures,
    parse_numeric,
)


def _fact(**over) -> GoldenFact:
    base = dict(
        requirement_key="state_minimum_wage",
        category="minimum_wage",
        comparator="numeric_eq",
        expected_numeric=16.50,
        effective_from=date(2025, 1, 1),
        authority_url="https://www.dol.gov/x",
        curated_by="tester",
        curated_at=date(2026, 1, 1),
    )
    base.update(over)
    return GoldenFact(**base)


# ── schema ────────────────────────────────────────────────────────────────────

def test_rejects_unknown_comparator():
    with pytest.raises(ValidationError):
        _fact(comparator="vibes")


def test_rejects_relative_authority_url():
    with pytest.raises(ValidationError):
        _fact(authority_url="/some/path")


def test_rejects_unknown_severity():
    with pytest.raises(ValidationError):
        _fact(severity="catastrophic")


# ── effective-date windowing ──────────────────────────────────────────────────

def test_active_within_window():
    f = _fact(effective_from=date(2025, 7, 1), effective_to=date(2026, 7, 1))
    assert f.active_on(date(2026, 1, 1))
    assert not f.active_on(date(2025, 1, 1))


def test_effective_to_is_exclusive():
    """A wage that reindexes on July 1 must not be asserted on July 1."""
    f = _fact(effective_from=date(2025, 7, 1), effective_to=date(2026, 7, 1))
    assert not f.active_on(date(2026, 7, 1))
    assert f.active_on(date(2026, 6, 30))


def test_open_ended_fact_never_expires():
    f = _fact(effective_from=date(2009, 7, 24), effective_to=None)
    assert f.active_on(date(2026, 7, 9))
    assert not f.expired_on(date(2026, 7, 9))


def test_expired_fact():
    f = _fact(effective_from=date(2024, 7, 1), effective_to=date(2025, 7, 1))
    assert f.expired_on(date(2026, 1, 1))


# ── comparators ───────────────────────────────────────────────────────────────

def test_missing_catalog_row_fails():
    result = compare(_fact(), None)
    assert not result["passed"]
    assert "no catalog row" in result["reason"]


def test_numeric_eq_pass():
    assert compare(_fact(), {"numeric_value": 16.50})["passed"]


def test_numeric_eq_fail_reports_both_values():
    result = compare(_fact(), {"numeric_value": 15.00})
    assert not result["passed"]
    assert "16.5" in result["reason"] and "15.0" in result["reason"]


def test_numeric_falls_back_to_parsing_current_value():
    assert compare(_fact(), {"numeric_value": None, "current_value": "$16.50 per hour"})["passed"]


def test_numeric_within_tolerance():
    f = _fact(comparator="numeric_within", expected_numeric=16.50, tolerance=0.05)
    assert compare(f, {"numeric_value": 16.53})["passed"]
    assert not compare(f, {"numeric_value": 16.70})["passed"]


def test_numeric_row_with_no_number_fails_cleanly():
    result = compare(_fact(), {"numeric_value": None, "current_value": "varies by county"})
    assert not result["passed"]
    assert "no numeric value" in result["reason"]


def test_text_contains_is_case_insensitive_and_scans_description():
    f = _fact(comparator="text_contains", expected_text="Meal Period", expected_numeric=None)
    row = {"current_value": None, "description": "A 30-minute meal period is required", "title": ""}
    assert compare(f, row)["passed"]


def test_text_contains_fail():
    f = _fact(comparator="text_contains", expected_text="seventh day", expected_numeric=None)
    assert not compare(f, {"current_value": "x", "description": "y", "title": "z"})["passed"]


def test_date_eq():
    f = _fact(comparator="date_eq", expected_date=date(2026, 1, 1), expected_numeric=None)
    assert compare(f, {"effective_date": date(2026, 1, 1)})["passed"]
    assert not compare(f, {"effective_date": date(2025, 1, 1)})["passed"]


def test_exists_passes_on_any_row():
    f = _fact(comparator="exists", expected_numeric=None)
    assert compare(f, {"current_value": None})["passed"]


# ── numeric parsing ───────────────────────────────────────────────────────────

@pytest.mark.parametrize("raw,expected", [
    ("$17.87", 17.87),
    ("17.87 per hour", 17.87),
    ("$1,234.56 annually", 1234.56),
    ("$68,640/year", 68640.0),
    ("no number here", None),
    (None, None),
    ("", None),
])
def test_parse_numeric(raw, expected):
    assert parse_numeric(raw) == expected


# ── the shipped corpus ────────────────────────────────────────────────────────

def test_shipped_fixtures_parse():
    """Every fixture in the repo validates. A malformed fixture is a build break."""
    load_fixtures()


def test_shipped_fixture_categories_exist_in_the_registry():
    for fixture in load_fixtures():
        for fact in fixture.facts:
            assert fact.category in CATEGORY_KEYS, (
                f"{fact.requirement_key}: unknown category {fact.category!r}"
            )


def test_shipped_facts_have_windows_that_open():
    for fixture in load_fixtures():
        for fact in fixture.facts:
            if fact.effective_to:
                assert fact.effective_from < fact.effective_to, fact.requirement_key


def test_numeric_facts_carry_a_number():
    for fixture in load_fixtures():
        for fact in fixture.facts:
            if fact.comparator in ("numeric_eq", "numeric_within"):
                assert fact.expected_numeric is not None, fact.requirement_key
            if fact.comparator == "text_contains":
                assert fact.expected_text, fact.requirement_key
