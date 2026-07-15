"""The rate_type vocabulary is duplicated — the copies must not drift.

For minimum_wage, rate_type IS the write identity: `_compute_key_parts` keys the
ON-CONFLICT composite off rate_type and ignores regulation_key entirely. So a
rate_type one layer doesn't recognize is not a cosmetic label loss — the row is
filed under the WRONG OBLIGATION.

That is exactly how it broke: `exempt_salary_regional` was added to
compliance_service.VALID_RATE_TYPES for the NY downstate re-key, but
gemini_compliance keeps its OWN copy, which was not updated. A Gemini-emitted
regional rate_type flattened to "general" there, so a weekly *salary threshold*
figure would have overwritten New York's *general minimum wage* row. And a
producer that instead emitted the correct regulation_key still keyed to the
STATEWIDE threshold, overwriting that row and orphaning the regional one.
"""
from app.core.services import gemini_compliance as gc
from app.core.services.compliance_service import (
    VALID_RATE_TYPES,
    _compute_key_parts,
    _coerce_minimum_wage_rate_type,
)
from app.core.services.compliance_evals.keys import _RATE_TYPE_TO_KEY, normalize_key


def test_the_two_rate_type_vocabularies_agree():
    assert gc.VALID_RATE_TYPES == VALID_RATE_TYPES, (
        "gemini_compliance.VALID_RATE_TYPES has drifted from "
        "compliance_service.VALID_RATE_TYPES. For minimum_wage the rate_type is "
        "the write identity, so an unknown one is flattened to 'general' and the "
        "row overwrites a DIFFERENT obligation."
    )


def test_every_rate_type_dialect_maps_to_a_registry_key():
    """keys._RATE_TYPE_TO_KEY is what turns a rate_type into the registry
    vocabulary. A rate_type with no mapping passes through as itself and lands
    as an `invalid_key` in the tagging suite."""
    for rate_type in _RATE_TYPE_TO_KEY:
        assert rate_type in VALID_RATE_TYPES, (
            f"{rate_type!r} is mapped in keys._RATE_TYPE_TO_KEY but is not a "
            f"valid rate_type — nothing can ever produce it"
        )


# ── the NY downstate identity must survive a re-research ────────────────────
#
# The re-key only holds if a PRODUCER can re-emit the identity. Gemini returns
# fresh req dicts; nothing reads the stored row's rate_type back. So each shape a
# producer might plausibly emit must land on the regional row — and, just as
# importantly, must NOT land on the statewide or general rows.

def _key_for(**req):
    base = {
        "category": "minimum_wage",
        "jurisdiction_name": "New York",
        "jurisdiction_level": "state",
        "country_code": "US",
        "current_value": "$1,275.00/week",
        "applicable_entity_types": [],
        "rate_type": None,
        "regulation_key": None,
    }
    return _compute_key_parts({**base, **req})[0]


REGIONAL = "minimum_wage:exempt_salary_threshold_regional"
STATEWIDE = "minimum_wage:exempt_salary_threshold"
GENERAL = "minimum_wage:state_minimum_wage"


def test_regional_row_is_reachable_from_the_regulation_key_alone():
    """The registry key is advertised to Gemini by
    _build_regulation_key_instruction, so this is the likeliest emission."""
    assert _key_for(
        regulation_key="exempt_salary_threshold_regional",
        title="Executive/Administrative Exempt Salary Threshold (Downstate)",
    ) == REGIONAL


def test_regional_row_is_reachable_from_the_rate_type():
    assert _key_for(
        rate_type="exempt_salary_regional",
        title="Executive/Administrative Exempt Salary Threshold (Downstate)",
    ) == REGIONAL


def test_regional_row_is_reachable_from_the_title_alone():
    """Worst case: a producer emits neither key nor rate_type."""
    assert _key_for(
        title="Executive/Administrative Exempt Salary Threshold (Downstate)",
    ) == REGIONAL


def test_the_statewide_row_is_not_hijacked_by_the_regional_obligation():
    assert _key_for(
        regulation_key="exempt_salary_threshold",
        title="NY Exempt Employee Salary Threshold",
    ) == STATEWIDE


def test_a_weekly_salary_figure_never_overwrites_the_general_minimum_wage():
    """The catastrophic case: an unknown rate_type flattening to 'general'."""
    assert _key_for(
        regulation_key="state_minimum_wage", title="New York State Minimum Wage",
        current_value="$16.50/hour",
    ) == GENERAL
    assert _key_for(
        regulation_key="exempt_salary_threshold_regional",
        title="Executive/Administrative Exempt Salary Threshold (Downstate)",
    ) != GENERAL


def test_coerce_derives_the_rate_type_from_the_regulation_key():
    assert _coerce_minimum_wage_rate_type(
        {"regulation_key": "exempt_salary_threshold_regional", "title": "x"}
    ) == "exempt_salary_regional"
    assert _coerce_minimum_wage_rate_type(
        {"regulation_key": "tipped_minimum_wage", "title": "x"}
    ) == "tipped"
    # No key, no hints -> unchanged default.
    assert _coerce_minimum_wage_rate_type({"title": "Minimum Wage"}) == "general"


def test_normalize_key_round_trips_the_new_dialect():
    assert normalize_key(
        "minimum_wage", "exempt_salary_regional", "state", "US",
    ) == "exempt_salary_threshold_regional"
