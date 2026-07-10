"""The <=30-key must-have checklist for manufacturing and healthcare.

The full sweep expects 201 keys for manufacturing and 268 for healthcare. Nobody
can read a 201-row gap list and tell whether the *expectation* is right, so a
wrong expectation set would never be caught. These tests pin the small set: every
key must exist in the registry (a typo would silently never match anything, which
reads as a permanent gap), and the whole thing must stay auditable in one sitting.
"""
import pytest

from app.core.compliance_registry import EXPECTED_REGULATION_KEYS
from app.core.services.compliance_evals import industry_keysets as iks

CORE_INDUSTRIES = ["manufacturing", "healthcare"]


@pytest.mark.parametrize("industry", CORE_INDUSTRIES)
def test_core_is_small_enough_to_audit_by_hand(industry):
    keys = iks.core_keys(industry)
    total = sum(len(v) for v in keys.values())
    assert total <= iks.CORE_MAX_KEYS, f"{industry} core has {total} keys"
    assert total >= 20, f"{industry} core is suspiciously thin ({total})"


@pytest.mark.parametrize("industry", CORE_INDUSTRIES)
def test_every_core_key_exists_in_the_registry(industry):
    """A typo here never matches a catalog row and reads as a permanent gap."""
    for category, keys in iks.core_keys(industry).items():
        known = EXPECTED_REGULATION_KEYS.get(category, frozenset())
        assert known, f"category {category!r} has no registry keys at all"
        unknown = keys - set(known)
        assert not unknown, f"{industry}/{category}: keys not in registry: {sorted(unknown)}"


@pytest.mark.parametrize("industry", CORE_INDUSTRIES)
def test_core_is_a_subset_of_the_full_expectation(industry):
    """Core must never demand something the full sweep would not."""
    full = iks.expected_keys(industry)
    for category, keys in iks.core_keys(industry).items():
        assert keys <= full.get(category, set()), f"{industry}/{category} escapes the full set"


@pytest.mark.parametrize("industry", CORE_INDUSTRIES)
def test_labor_core_is_shared_by_both_industries(industry):
    keys = iks.core_keys(industry)
    assert "state_minimum_wage" in keys["minimum_wage"]
    assert "fmla" in keys["leave"]
    assert "osha_general_duty" in keys["workplace_safety"]


def test_manufacturing_core_covers_the_physical_hazards():
    keys = iks.core_keys("manufacturing")
    assert {"lockout_tagout", "machine_guarding"} <= keys["machine_safety"]
    assert "hazcom_ghs" in keys["chemical_safety"]
    assert "respiratory_protection" in keys["industrial_hygiene"]
    assert "rcra_hazardous_waste" in keys["environmental_compliance"]


def test_healthcare_core_covers_the_federal_spine():
    keys = iks.core_keys("healthcare")
    assert "emtala" in keys["clinical_safety"]
    assert "hipaa_privacy_rule" in keys["hipaa_privacy"]
    assert "false_claims_act" in keys["billing_integrity"]
    assert "oig_exclusion_list_screening" in keys["healthcare_workforce"]


def test_cores_are_distinct_beyond_the_shared_labor_base():
    mfg = iks.core_keys("manufacturing")
    hc = iks.core_keys("healthcare")
    assert "machine_safety" not in hc
    assert "hipaa_privacy" not in mfg


def test_no_state_specific_key_in_core():
    """A core miss must mean the same thing in NY as in TX.

    `healthcare_minimum_wage` is CA SB 525; `local_minimum_wage` is an ordinance.
    Neither belongs in a nationally-applicable must-have list.
    """
    banned = {
        "healthcare_minimum_wage", "local_minimum_wage", "fast_food_minimum_wage",
        "local_sick_leave", "seventh_day_overtime", "double_time",
    }
    for industry in CORE_INDUSTRIES:
        flat = {k for keys in iks.core_keys(industry).values() for k in keys}
        assert not (flat & banned), f"{industry} core contains state-specific keys"


def test_no_international_key_leaks_into_core():
    """Core keys must survive the US country filter, or every US jurisdiction
    fails the checklist on a key that never applied to it."""
    for industry in CORE_INDUSTRIES:
        us_expected = iks.expected_keys(industry, country_code="US")
        for category, keys in iks.core_keys(industry).items():
            assert keys <= us_expected.get(category, set()), (
                f"{industry}/{category}: core keys dropped by the US country filter: "
                f"{sorted(keys - us_expected.get(category, set()))}"
            )


def test_industries_without_a_curated_core_raise():
    """Silently falling back to the labor core would claim an industry verdict
    the checklist cannot support."""
    assert not iks.has_core("retail")
    with pytest.raises(ValueError, match="no core keyset"):
        iks.core_keys("retail")
    with pytest.raises(ValueError):
        iks.core_keys(None)


def test_has_core_only_for_the_two_curated_industries():
    assert iks.has_core("manufacturing")
    assert iks.has_core("healthcare")
    for other in ("retail", "technology", "hospitality", "biotech", "fast food"):
        assert not iks.has_core(other)


# ── checklist shape ───────────────────────────────────────────────────────────

def _graph(present):
    """Minimal jurisdiction graph: one city, no state/federal parents."""
    jid = "j1"
    return {
        "jurisdictions": {jid: {"id": jid, "city": "x", "state": "CA",
                                "country_code": "US", "level": "city"}},
        "keys_by_jurisdiction": {jid: present},
        "federal_id": None,
        "state_ids": {},
    }, jid


def test_checklist_marks_every_key_and_counts_hits():
    from app.core.services.compliance_evals.completeness import core_checklist

    graph, jid = _graph({"machine_safety": {"lockout_tagout"}})
    out = core_checklist(graph, jid, "manufacturing")

    assert out["total"] == sum(len(v) for v in iks.core_keys("manufacturing").values())
    assert out["present"] == 1
    assert not out["complete"]
    assert len(out["items"]) == out["total"]

    lockout = next(i for i in out["items"] if i["key"] == "lockout_tagout")
    assert lockout["present"] is True
    guarding = next(i for i in out["items"] if i["key"] == "machine_guarding")
    assert guarding["present"] is False


def test_checklist_complete_when_everything_present():
    from app.core.services.compliance_evals.completeness import core_checklist

    graph, jid = _graph({c: set(k) for c, k in iks.core_keys("healthcare").items()})
    out = core_checklist(graph, jid, "healthcare")
    assert out["complete"]
    assert out["score"] == 100.0
    assert out["present"] == out["total"]


def _us_uk_graph():
    """`federal` (US) and `national` (UK) coexist — they are not the same bucket."""
    return {
        "jurisdictions": {
            "c": {"id": "c", "city": "la", "state": "CA", "country_code": "US", "level": "city"},
            "s": {"id": "s", "city": None, "state": "CA", "country_code": "US", "level": "state"},
            "f": {"id": "f", "city": None, "state": "US", "country_code": "US", "level": "federal"},
            "uk": {"id": "uk", "city": None, "state": None, "country_code": "GB",
                   "level": "national"},
        },
        "keys_by_jurisdiction": {
            "s": {"machine_safety": {"lockout_tagout"}},
            "f": {"workplace_safety": {"osha_general_duty"}},
            "uk": {"machine_safety": {"machine_guarding"}},
        },
        "federal_id": "f",
        "national_ids": {"GB": "uk"},
        "state_ids": {"CA": "s"},
    }


def test_checklist_inherits_from_state_and_federal():
    """A key held federally counts for the city — same union as the full suite."""
    from app.core.services.compliance_evals.completeness import core_checklist

    out = core_checklist(_us_uk_graph(), "c", "manufacturing")
    by_key = {i["key"]: i["present"] for i in out["items"]}
    assert by_key["lockout_tagout"] is True
    assert by_key["osha_general_duty"] is True


def test_us_city_does_not_inherit_from_a_national_country_root():
    """Regression: `federal` and `national` were collapsed into one `federal_id`,
    so whichever row the query returned last won. A US city could inherit UK law
    — and since the UK row is empty, lose all 50 real federal requirements."""
    from app.core.services.compliance_evals.completeness import core_checklist

    out = core_checklist(_us_uk_graph(), "c", "manufacturing")
    by_key = {i["key"]: i["present"] for i in out["items"]}
    assert by_key["machine_guarding"] is False, "US city inherited a UK requirement"
