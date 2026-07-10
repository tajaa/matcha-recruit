"""Seed integrity — every seed row is citation-anchored and gate-clean. No DB."""
import re

import pytest

from app.core.services.scope_registry.classify import validate_proposal
from app.core.services.scope_registry.curated_ca import CURATED_ROWS
from app.core.services.scope_registry.seed import SEED_CLASSIFICATIONS

_CURATED_CITATIONS = {r["citation"] for rows in CURATED_ROWS.values() for r in rows}
# Federal citations from authority_parse: "29 CFR 1910.147" / "29 CFR 825 Subpart A"
_FEDERAL_RE = re.compile(r"^\d{2} CFR (?:\d+ Subpart [A-Z]+|\d+\.\d+)$")

# Synthetic RKD covering the keys the seed cites — the real gate runs at apply
# time against the live table; here we assert the proposals are well-formed.
_RKD = {
    "leave": {"fmla"},
    "workplace_safety": {"osha_general_duty", "injury_illness_recordkeeping"},
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
