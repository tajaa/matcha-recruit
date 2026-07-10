"""Scope eval suite — pure condition-attribute extraction + wiring. No DB."""
import pytest

from app.core.services.compliance_evals import scope as scope_suite
from app.core.services.compliance_evals.runner import ALL_SUITES


def test_scope_registered_as_a_suite():
    assert "scope" in ALL_SUITES


def test_scope_is_not_a_network_suite():
    from app.core.services.compliance_evals.runner import NETWORK_SUITES
    assert "scope" not in NETWORK_SUITES  # reads local tables only


# ── _condition_attr_keys ─────────────────────────────────────────────────────

def test_leaf_condition_attr():
    cond = {"type": "attribute", "key": "employee_count", "operator": "gte", "value": 50}
    assert scope_suite._condition_attr_keys(cond) == ["employee_count"]


def test_compound_condition_attrs():
    cond = {
        "op": "and",
        "conditions": [
            {"type": "attribute", "key": "employee_count", "operator": "gte", "value": 50},
            {"type": "attribute", "key": "entity_type", "operator": "eq", "value": "hospital"},
        ],
    }
    assert set(scope_suite._condition_attr_keys(cond)) == {"employee_count", "entity_type"}


def test_condition_as_json_string_is_parsed():
    assert scope_suite._condition_attr_keys(
        '{"type": "attribute", "key": "psm_covered_chemicals", "operator": "eq", "value": true}'
    ) == ["psm_covered_chemicals"]


@pytest.mark.parametrize("bad", [None, "{broken", 42, {}])
def test_bad_condition_yields_no_attrs(bad):
    assert scope_suite._condition_attr_keys(bad) == []


def test_known_facility_attrs_cover_the_seeded_conditionals():
    """Every attribute the scope-registry seed keys a conditional on must be in
    KNOWN_FACILITY_ATTRS, or that conditional would be flagged ungated (dead)."""
    from app.core.services.scope_registry.seed import SEED_CLASSIFICATIONS

    for citation, proposal in SEED_CLASSIFICATIONS.items():
        cond = proposal.get("entity_condition")
        if not cond:
            continue
        for attr in scope_suite._condition_attr_keys(cond):
            assert attr in scope_suite.KNOWN_FACILITY_ATTRS, f"{citation}: {attr}"


def test_ungated_detection_flags_unknown_attribute():
    known = scope_suite.KNOWN_FACILITY_ATTRS
    dead = {"type": "attribute", "key": "moon_phase", "operator": "eq", "value": "full"}
    attrs = scope_suite._condition_attr_keys(dead)
    assert [a for a in attrs if a not in known] == ["moon_phase"]


# ── completeness repoint ─────────────────────────────────────────────────────

def test_completeness_exposes_the_registry_override_hook():
    from app.core.services.compliance_evals import completeness
    assert hasattr(completeness, "registry_expected_keys")
