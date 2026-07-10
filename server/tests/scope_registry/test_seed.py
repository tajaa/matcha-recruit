"""Seed integrity — every seed row is citation-anchored and gate-clean. No DB."""
import re

import pytest

from app.core.services.scope_registry.classify import validate_proposal
from app.core.services.scope_registry.curated_ca import CURATED_ROWS
from app.core.services.scope_registry.seed import SEED_CLASSIFICATIONS

_CURATED_CITATIONS = {r["citation"] for rows in CURATED_ROWS.values() for r in rows}
# Federal citations from authority_parse: "29 CFR 1910.147" / "29 CFR 825 Subpart A"
_FEDERAL_RE = re.compile(r"^\d{2} CFR (?:\d+ Subpart [A-Z]+|\d+\.\d+)$")

# Synthetic RKD covering the keys the seed cites (all confirmed present in the
# real regulation_key_definitions). The real gate runs at apply time against
# the live table; here we assert the proposals are well-formed + keyed right.
_RKD = {
    "leave": {"fmla"},
    "workplace_safety": {"osha_general_duty", "injury_illness_recordkeeping"},
    "minimum_wage": {"state_minimum_wage", "national_minimum_wage", "exempt_salary_threshold"},
    "overtime": {"daily_weekly_overtime", "exempt_salary_threshold"},
    "meal_breaks": {"meal_break", "rest_break", "missed_break_penalty"},
    "final_pay": {"final_pay_termination", "final_pay_resignation", "waiting_time_penalty"},
    "sick_leave": {"state_paid_sick_leave"},
    "workers_comp": {"mandatory_coverage"},
    # pay_frequency intentionally has no key for §204/§226 (uncodified by design).
    "pay_frequency": set(),
}


def test_every_citation_is_anchored():
    """A seed row must reference something the ingest actually produces."""
    for citation in SEED_CLASSIFICATIONS:
        assert citation in _CURATED_CITATIONS or _FEDERAL_RE.match(citation), citation


def test_every_proposal_passes_the_gates():
    for citation, proposal in SEED_CLASSIFICATIONS.items():
        normalized, warnings = validate_proposal(proposal, _RKD)
        assert normalized is not None, f"{citation}: {warnings}"


def test_seed_cites_no_unknown_keys():
    """Under the synthetic RKD, no seed key should degrade to NULL."""
    for citation, proposal in SEED_CLASSIFICATIONS.items():
        _, warnings = validate_proposal(proposal, _RKD)
        assert not warnings, f"{citation}: {warnings}"


def test_ab701_is_warehousing_only():
    for citation, proposal in SEED_CLASSIFICATIONS.items():
        if citation.startswith("Cal. Lab. Code § 21"):
            assert proposal["disposition"] == "category_specific"
            assert proposal["applies_to_categories"] == ["warehousing"], citation


def test_fmla_condition_uses_the_established_attribute():
    """employee_count is the runtime-injected roster attribute — the FMLA
    threshold must key on it, not an invented name."""
    fmla_rows = [
        p for c, p in SEED_CLASSIFICATIONS.items() if c.startswith("29 CFR 825")
    ]
    assert fmla_rows
    for p in fmla_rows:
        cond = p["entity_condition"]
        assert cond == {"type": "attribute", "key": "employee_count",
                        "operator": "gte", "value": 50}


def test_psm_is_conditional_not_universal():
    p = SEED_CLASSIFICATIONS["29 CFR 1910.119"]
    assert p["disposition"] == "conditional"
    assert p["entity_condition"]["key"] == "psm_covered_chemicals"


def test_lockout_tagout_is_universal_in_domain():
    """The plan's correction: 1910.147 applies across general industry —
    a warehouse gets it (conveyors, dock levelers, balers)."""
    p = SEED_CLASSIFICATIONS["29 CFR 1910.147"]
    assert p["disposition"] == "universal_in_domain"
    assert p["applies_to_categories"] == []


def test_title16_rows_are_ophthalmology():
    t16 = {r["citation"] for r in CURATED_ROWS["ca-title-16"]}
    for citation in t16:
        assert citation in SEED_CLASSIFICATIONS, f"{citation} unseeded"
        assert SEED_CLASSIFICATIONS[citation]["applies_to_categories"] == ["ophthalmology"]


def test_every_curated_row_is_seeded():
    """Curated slices are small and hand-picked — an unseeded curated row is
    an authoring gap, not a choice."""
    unseeded = _CURATED_CITATIONS - set(SEED_CLASSIFICATIONS)
    assert not unseeded, f"curated rows without a seed classification: {unseeded}"


# ── basic labor law: the "solid" assertions ──────────────────────────────────

# The core wage-hour + WC spine — each maps a citation to its RKD key.
_CA_LABOR_SPINE = {
    "Cal. Lab. Code § 1182.12": "state_minimum_wage",
    "Cal. Lab. Code § 515": "exempt_salary_threshold",
    "Cal. Lab. Code § 510": "daily_weekly_overtime",
    "Cal. Lab. Code § 512": "meal_break",
    "Cal. Lab. Code § 226.7": "rest_break",
    "Cal. Lab. Code § 201": "final_pay_termination",
    "Cal. Lab. Code § 202": "final_pay_resignation",
    "Cal. Lab. Code § 203": "waiting_time_penalty",
    "Cal. Lab. Code § 246": "state_paid_sick_leave",
    "Cal. Lab. Code § 3700": "mandatory_coverage",
}
_FLSA_SPINE = {
    "29 U.S.C. § 206": "national_minimum_wage",
    "29 U.S.C. § 207": "daily_weekly_overtime",
    "29 U.S.C. § 213": "exempt_salary_threshold",
    "29 CFR § 541.600": "exempt_salary_threshold",
}


@pytest.mark.parametrize("citation,key", {**_CA_LABOR_SPINE, **_FLSA_SPINE}.items())
def test_labor_spine_keys_are_exactly_as_confirmed(citation, key):
    """Regression pin (like the Title 16 test) — a citation's key can't drift
    without re-confirming it against the RKD."""
    assert citation in SEED_CLASSIFICATIONS, citation
    assert SEED_CLASSIFICATIONS[citation]["regulation_key"] == key


def test_the_labor_spine_is_universal():
    """The 'basic labor law is solid' core assertion: min wage, OT, meal/rest,
    final pay, sick leave, WC apply to a GENERIC employer — universal_in_domain,
    no category, no attributes. Verified through the real matcher."""
    from app.core.services.scope_registry.resolve import classification_matches

    for citation in {**_CA_LABOR_SPINE, **_FLSA_SPINE}:
        proposal = SEED_CLASSIFICATIONS[citation]
        assert proposal["disposition"] == "universal_in_domain", citation
        # A generic employer: empty category chain, no facility attributes.
        row = {
            "disposition": proposal["disposition"],
            "applies_to_categories": proposal["applies_to_categories"],
            "excludes_categories": proposal["excludes_categories"],
            "entity_condition": None,
        }
        assert classification_matches(row, [], {}), citation


def test_uncodified_labor_rows_are_in_scope_but_keyless():
    """§204 (pay frequency) and §226 (wage statements) have no RKD key yet —
    mapped universal (in scope, fetch queue), key=None."""
    for citation in ("Cal. Lab. Code § 204", "Cal. Lab. Code § 226"):
        p = SEED_CLASSIFICATIONS[citation]
        assert p["disposition"] == "universal_in_domain"
        assert p["regulation_key"] is None


# CORE keys not newly mapped here, with why (already-seeded or a cross-code pass).
_DEFERRED_CORE_KEYS = {"harassment_prevention_training", "osha_general_duty"}


def test_all_core_labor_keys_are_mapped_or_explicitly_deferred():
    """No CORE_LABOR key silently unmapped: every one is either cited by a seed
    classification or in the deferred allowlist (with a documented reason)."""
    from app.core.services.compliance_evals.industry_keysets import CORE_LABOR_KEYS

    seeded_keys = {
        p["regulation_key"] for p in SEED_CLASSIFICATIONS.values() if p.get("regulation_key")
    }
    core_keys = {k for keys in CORE_LABOR_KEYS.values() for k in keys}
    unmapped = core_keys - seeded_keys - _DEFERRED_CORE_KEYS
    # injury_illness_recordkeeping is seeded (29 CFR 1904 Subpart C).
    assert not unmapped, f"CORE_LABOR keys neither mapped nor deferred: {unmapped}"
