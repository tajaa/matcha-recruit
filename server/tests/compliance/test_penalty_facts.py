"""penalty_facts — the single read API over sourced penalty figures. No DB.

Three engines price non-compliance. This is the one place they ask "what does
breaking this cost, and says who?" — so its refusals matter more than its
answers: an engine that gets a confident wrong figure from here has no way to
know.
"""
from datetime import date

from app.core.services.penalty_facts import (
    PenaltyFact,
    PenaltyTierFact,
    _fact_from_row,
    cite,
)

ECFR = "https://www.ecfr.gov/current/title-29/section-1903.15"


def _row(**kw):
    base = {
        "regulation_key": "injury_illness_recordkeeping",
        "authority_citation": "29 CFR 1903.15",
        "authority_url": ECFR,
        "penalty_effective_date": date(2025, 1, 15),
        "penalties": {
            "default_tier": "serious",
            "enforcing_agency": "OSHA",
            "tiers": [
                {"tier": "willful", "min_usd": 11823.0, "max_usd": 165514.0,
                 "per_day": False, "citation": "29 CFR 1903.15(d)(1)", "quote": "..."},
                {"tier": "serious", "min_usd": None, "max_usd": 16550.0,
                 "per_day": False, "citation": "29 CFR 1903.15(d)(3)", "quote": "..."},
            ],
        },
    }
    base.update(kw)
    return base


# ── building a fact ────────────────────────────────────────────────────────

def test_a_bound_row_yields_the_tiers_with_provenance():
    f = _fact_from_row(_row())
    assert f.citation == "29 CFR 1903.15"
    assert f.source_url == ECFR
    assert f.effective_date == date(2025, 1, 15)
    assert {t.tier for t in f.tiers} == {"willful", "serious"}
    assert f.tier("serious").max_usd == 16_550.0
    assert f.tier("willful").min_usd == 11_823.0


def test_the_headline_tier_is_the_default_not_the_scariest():
    """Willful is an inspector's finding about state of mind, not a property of
    the rule. Quoting $165,514 would be assuming the worst tier."""
    f = _fact_from_row(_row())
    assert f.headline.tier == "serious"
    assert f.headline.max_usd == 16_550.0


def test_a_missing_default_tier_falls_back_to_the_first_not_to_nothing():
    r = _row(penalties={**_row()["penalties"], "default_tier": None})
    assert _fact_from_row(r).headline is not None


def test_provenance_comes_from_the_authority_row_not_the_blob():
    """The blob is authored by a MODEL on the research path. Its own claims about
    where it came from are exactly what a poisoned source_url looks like."""
    r = _row(penalties={
        **_row()["penalties"],
        "source_url": "javascript:alert(1)",
        "citation": "totally made up",
    })
    f = _fact_from_row(r)
    assert f.source_url == ECFR
    assert f.citation == "29 CFR 1903.15"


def test_a_tier_without_its_own_citation_borrows_the_section_never_the_blob():
    r = _row(penalties={
        "default_tier": "serious",
        "tiers": [{"tier": "serious", "max_usd": 16550.0, "citation": None}],
    })
    assert _fact_from_row(r).tier("serious").citation == "29 CFR 1903.15"


# ── refusing ───────────────────────────────────────────────────────────────

def test_a_bound_row_with_no_parsed_tiers_is_not_a_fact():
    """Bound but unparsed: surfacing a figure under a citation that doesn't
    actually state it is worse than saying nothing."""
    assert _fact_from_row(_row(penalties={"civil_penalty_max": 16550.0})) is None
    assert _fact_from_row(_row(penalties={"tiers": []})) is None
    assert _fact_from_row(_row(penalties=None)) is None


def test_malformed_tiers_are_dropped_and_an_all_malformed_row_yields_nothing():
    assert _fact_from_row(_row(penalties={"tiers": [{"max_usd": 1.0}]})) is None  # no tier name
    assert _fact_from_row(_row(penalties={"tiers": ["not-a-dict"]})) is None


def test_a_json_string_blob_parses_like_a_dict():
    """metadata->'penalties' arrives as dict or JSON string depending on driver
    handling — the same defensive parse compliance_risk does."""
    import json
    f = _fact_from_row(_row(penalties=json.dumps(_row()["penalties"])))
    assert f is not None and f.tier("serious").max_usd == 16_550.0


# ── the cite() shape a surface renders from ────────────────────────────────

def test_cite_of_nothing_is_honestly_empty():
    """sourced=False with no url is what tells a UI to render plain text. A
    number that can't be checked must never look checkable."""
    c = cite(None)
    assert c["sourced"] is False
    assert c["source_url"] is None
    assert c["citation"] is None


def test_cite_of_a_fact_carries_the_link_and_the_date():
    c = cite(_fact_from_row(_row()))
    assert c["sourced"] is True
    assert c["source_url"] == ECFR
    assert c["effective_date"] == "2025-01-15"


def test_a_fact_with_no_effective_date_still_cites():
    c = cite(_fact_from_row(_row(penalty_effective_date=None)))
    assert c["sourced"] is True
    assert c["effective_date"] is None


# ── shape guard ────────────────────────────────────────────────────────────

def test_bounds_are_named_so_they_cannot_be_fed_to_the_percentile_fit():
    """monte_carlo treats low/high as 10th/90th percentiles. These are statutory
    bounds and must not be mistakable for that."""
    assert set(PenaltyTierFact.__dataclass_fields__) >= {"min_usd", "max_usd"}
    assert "low" not in PenaltyTierFact.__dataclass_fields__
    assert "high" not in PenaltyFact.__dataclass_fields__
