"""penalty_schedules — parsing the CFR's own civil-monetary-penalty tables.

The fixture is the REAL body of 29 CFR 1903.15, ingested from the eCFR versioner
API. Tests run against it offline, so a parser change is checked against the text
the law actually uses rather than a paraphrase of it.

What these defend: the catalog held four vintages of the OSHA serious-violation
maximum at once (16,131 / 15,873 / 165,514 / 161,323) because the figures came
from model recall. A parse is only worth trusting if it is all-or-nothing and
never guesses — most of these tests are about the refusing.
"""
from datetime import date
from pathlib import Path

import pytest

from app.core.services.scope_registry.penalty_schedules import (
    TIERS,
    mapped_agencies,
    parse_osha_schedule,
    parse_schedule,
    penalties_payload,
    schedule_source_for_agency,
)

FIXTURE = Path(__file__).parent / "fixtures" / "osha_1903_15.txt"
BODY = FIXTURE.read_text()


@pytest.fixture(scope="module")
def schedule():
    s = parse_osha_schedule(BODY, source_url="https://example.com/1903.15")
    assert s is not None
    return s


# ── the figures, against the real text ──────────────────────────────────────

def test_serious_is_16550_not_the_16131_we_were_showing():
    """The whole point. Maria's tenant was being shown $16,131 — the 2024
    figure — for an OSHA violation. The statute says $16,550."""
    s = parse_osha_schedule(BODY)
    assert s.tier("serious").max_usd == 16_550.0


def test_willful_carries_a_floor_and_a_ceiling():
    """'shall not be less than $11,823 and shall not exceed $165,514' — the only
    tier with a floor. Blending this floor with the serious ceiling is how the
    incoherent min/max pairs were born."""
    t = parse_osha_schedule(BODY).tier("willful")
    assert (t.min_usd, t.max_usd) == (11_823.0, 165_514.0)


def test_repeated_matches_willfuls_ceiling_but_has_no_floor():
    t = parse_osha_schedule(BODY).tier("repeated")
    assert t.max_usd == 165_514.0
    assert t.min_usd is None


def test_willful_is_ten_times_serious():
    """The escalation signal compliance_risk_dims promises, now sourced."""
    s = parse_osha_schedule(BODY)
    assert s.tier("willful").max_usd == pytest.approx(s.tier("serious").max_usd * 10, rel=0.01)


def test_failure_to_correct_is_the_only_per_day_tier():
    s = parse_osha_schedule(BODY)
    assert s.tier("failure_to_correct").per_day is True
    for other in ("willful", "repeated", "serious", "other_than_serious", "posting"):
        assert s.tier(other).per_day is False, other


def test_every_tier_in_the_statute_is_found(schedule):
    assert {t.tier for t in schedule.tiers} == set(TIERS)


def test_effective_date_comes_from_the_text_not_from_amendment_date(schedule):
    """Load-bearing: eCFR reports amendment_date 2017-01-01 for this section
    while the body states the January 15, 2025 adjustment. Trusting the metadata
    date would peg the schedule eight years stale and drift would never fire."""
    assert schedule.effective_date == date(2025, 1, 15)


def test_each_tier_cites_its_own_subsection(schedule):
    assert schedule.tier("serious").citation == "29 CFR 1903.15(d)(3)"
    assert schedule.tier("willful").citation == "29 CFR 1903.15(d)(1)"
    assert schedule.citation == "29 CFR 1903.15(d)"


def test_each_tier_quotes_the_statute_verbatim(schedule):
    """The quote is what makes a number defensible to an underwriter."""
    q = schedule.tier("serious").quote
    assert "29 U.S.C. 666(b)" in q
    assert "$16,550" in q


def test_the_amendment_history_bracket_is_not_parsed_as_a_tier(schedule):
    """The section ends '[36 FR 17850, Sept. 4, 1971, as amended at ...]' —
    full of numbers that must not be mistaken for penalties."""
    for t in schedule.tiers:
        assert "FR" not in t.quote or "$" in t.quote
        assert t.max_usd < 1_000_000


# ── refusing to guess ───────────────────────────────────────────────────────

def test_a_body_without_the_d_block_yields_nothing():
    """All-or-nothing. A body that changed shape must produce NO schedule — a
    half-parse silently prices a violation wrong, an absent one is visible."""
    assert parse_osha_schedule("§ 1903.15 Proposed penalties. (a) Some prose.") is None


def test_empty_body_yields_nothing():
    for empty in ("", None):
        assert parse_osha_schedule(empty) is None


def test_a_tier_with_no_ceiling_is_skipped_not_invented():
    body = (
        "(d) Adjusted civil monetary penalties. The adjusted civil penalties for "
        "penalties proposed after January 15, 2025 are as follows: "
        "(3) Serious violation. The penalty shall be determined by the Secretary. "
        "(1) Willful violation. The penalty shall not exceed $165,514."
    )
    s = parse_osha_schedule(body)
    assert {t.tier for t in s.tiers} == {"willful"}


def test_an_unknown_tier_label_is_skipped_not_coerced():
    """If OSHA adds a tier, it must show up as absent rather than mislabelled
    into an existing bucket."""
    body = (
        "(d) Adjusted civil monetary penalties. The adjusted civil penalties for "
        "penalties proposed after January 15, 2025 are as follows: "
        "(7) Novel future violation. The penalty shall not exceed $99,999. "
        "(3) Serious violation. The penalty shall not exceed $16,550."
    )
    s = parse_osha_schedule(body)
    assert {t.tier for t in s.tiers} == {"serious"}


def test_a_missing_effective_date_does_not_sink_the_parse():
    body = (
        "(d) Adjusted civil monetary penalties. The adjusted civil penalties are as follows: "
        "(3) Serious violation. The penalty shall not exceed $16,550."
    )
    s = parse_osha_schedule(body)
    assert s.effective_date is None
    assert s.tier("serious").max_usd == 16_550.0


# ── agency mapping: exact, never fuzzy ──────────────────────────────────────

def test_federal_osha_maps():
    src = schedule_source_for_agency("OSHA")
    assert src.slug == "ecfr-29-1903"
    assert src.default_tier == "serious"


def test_agency_matching_is_case_and_whitespace_tolerant():
    assert schedule_source_for_agency("  osha ") is not None


@pytest.mark.parametrize("agency", [
    "Cal/OSHA",                                    # California sets its OWN amounts
    "California State Board of Pharmacy / Cal/OSHA",
    "CMS / State Licensing Boards / OSHA",         # a mush of three agencies
    "OSHA / State Pharmacy Boards / NRC",
])
def test_substring_lookalikes_never_match_federal_osha(agency):
    """All four strings are live in the catalog. A substring match on 'OSHA'
    would stamp federal dollars onto state-plan and multi-agency rows —
    the same class of bug match_codifications' state/country guards exist for."""
    assert schedule_source_for_agency(agency) is None


def test_unmapped_and_empty_agencies_get_nothing():
    for a in (None, "", "EPA", "HHS OCR", "unknown"):
        assert schedule_source_for_agency(a) is None


def test_mapped_agencies_is_stable():
    assert "osha" in mapped_agencies()


def test_parse_schedule_dispatch_rejects_an_unknown_parser():
    assert parse_schedule("nope", BODY, citation="x") is None
    assert parse_schedule("osha", BODY, citation="29 CFR 1903.15") is not None


# ── wire shape ──────────────────────────────────────────────────────────────

def test_payload_fills_the_flat_pair_from_the_default_tier(schedule):
    """tiers[] is additive: every existing reader (RiskPenalty, compute_exposure,
    the cockpit tile) keeps working off civil_penalty_min/max."""
    p = penalties_payload(schedule, schedule_source_for_agency("OSHA"))
    assert p["civil_penalty_max"] == 16_550.0
    assert p["default_tier"] == "serious"
    assert p["per_violation"] is True
    assert p["grounding"] == "grounded"
    assert p["effective_date"] == "2025-01-15"
    assert len(p["tiers"]) == len(TIERS)


def test_serious_has_no_floor_so_min_is_null_not_borrowed(schedule):
    """'shall not exceed $X' is a ceiling with no floor. compute_exposure's
    lo-borrows-hi rule then reports $16,550-$16,550 rather than inventing a
    minimum — and must never inherit willful's $11,823."""
    p = penalties_payload(schedule, schedule_source_for_agency("OSHA"))
    assert p["civil_penalty_min"] is None


def test_payload_keeps_model_prose_but_not_model_numbers(schedule):
    p = penalties_payload(
        schedule, schedule_source_for_agency("OSHA"),
        keep={
            "summary": "Willful violations carry higher penalties.",
            "criminal": "Up to 6 months imprisonment.",
            "enforcing_agency": "OSHA",
            "civil_penalty_max": 16_131.0,   # the stale model number
        },
    )
    assert p["summary"].startswith("Willful")
    assert p["criminal"].startswith("Up to")
    assert p["enforcing_agency"] == "OSHA"
    assert p["civil_penalty_max"] == 16_550.0  # parsed wins


def test_payload_tiers_carry_their_quotes_and_citations(schedule):
    p = penalties_payload(schedule, schedule_source_for_agency("OSHA"))
    serious = next(t for t in p["tiers"] if t["tier"] == "serious")
    assert serious["citation"] == "29 CFR 1903.15(d)(3)"
    assert "$16,550" in serious["quote"]
    ftc = next(t for t in p["tiers"] if t["tier"] == "failure_to_correct")
    assert ftc["per_day"] is True
