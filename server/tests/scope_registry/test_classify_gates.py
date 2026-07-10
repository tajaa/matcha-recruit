"""validate_proposal — the hard gates on every classification. Pure, no DB."""
import pytest

from app.core.services.scope_registry.classify import (
    _condition_shape_error,
    validate_proposal,
)

RKD = {
    "leave": {"fmla"},
    "workplace_safety": {"osha_general_duty", "injury_illness_recordkeeping"},
}


def _ok(p, rkd=RKD):
    normalized, warnings = validate_proposal(p, rkd)
    assert normalized is not None, warnings
    return normalized, warnings


def _rejected(p, rkd=RKD):
    normalized, warnings = validate_proposal(p, rkd)
    assert normalized is None
    return warnings


# ── disposition ──────────────────────────────────────────────────────────────

def test_unknown_disposition_rejected():
    assert "disposition" in _rejected({"disposition": "sometimes"})[0]


def test_universal_passes():
    normalized, warnings = _ok({"disposition": "universal_in_domain"})
    assert normalized["disposition"] == "universal_in_domain"
    assert warnings == []


# ── taxonomy gates ───────────────────────────────────────────────────────────

def test_unknown_applies_to_slug_rejected():
    _rejected({
        "disposition": "category_specific",
        "applies_to_categories": ["warehousing", "med_spas"],  # med_spas not in taxonomy
    })


def test_unknown_excludes_slug_rejected():
    _rejected({
        "disposition": "universal_in_domain",
        "excludes_categories": ["klingon_shipyards"],
    })


def test_category_specific_requires_applies_to():
    _rejected({"disposition": "category_specific", "applies_to_categories": []})


def test_applies_to_normalized_sorted_deduped():
    normalized, _ = _ok({
        "disposition": "category_specific",
        "applies_to_categories": ["Warehousing", "warehousing", "healthcare"],
    })
    assert normalized["applies_to_categories"] == ["healthcare", "warehousing"]


# ── excluded ─────────────────────────────────────────────────────────────────

def test_excluded_requires_reason():
    _rejected({"disposition": "excluded"})
    normalized, _ = _ok({"disposition": "excluded", "excluded_reason": "definitional only"})
    assert normalized["excluded_reason"] == "definitional only"


# ── entity_condition ─────────────────────────────────────────────────────────

FMLA = {"type": "attribute", "key": "employee_count", "operator": "gte", "value": 50}


def test_conditional_requires_condition():
    _rejected({"disposition": "conditional"})


def test_valid_leaf_condition_passes():
    normalized, _ = _ok({"disposition": "conditional", "entity_condition": FMLA})
    assert normalized["entity_condition"] == FMLA


def test_valid_compound_condition_passes():
    _ok({
        "disposition": "conditional",
        "entity_condition": {"op": "and", "conditions": [FMLA]},
    })


@pytest.mark.parametrize("bad", [
    {"type": "attribute", "key": "x", "operator": "≥", "value": 1},   # unknown operator
    {"type": "attribute", "operator": "gte", "value": 1},              # missing key
    {"type": "attribute", "key": "x", "operator": "gte"},              # missing value
    {"op": "and", "conditions": []},                                   # empty compound
    {"op": "xor", "conditions": [{}]},                                 # unknown op
    "employee_count >= 50",                                            # not an object
])
def test_malformed_conditions_rejected(bad):
    _rejected({"disposition": "conditional", "entity_condition": bad})


def test_exists_operator_needs_no_value():
    assert _condition_shape_error(
        {"type": "attribute", "key": "psm_covered_chemicals", "operator": "exists"}
    ) is None


def test_condition_on_non_conditional_rejected():
    _rejected({"disposition": "universal_in_domain", "entity_condition": FMLA})


# ── regulation_key gate ──────────────────────────────────────────────────────

def test_known_key_in_category_kept():
    normalized, warnings = _ok({
        "disposition": "conditional", "entity_condition": FMLA,
        "regulation_key": "fmla", "category_slug": "leave",
    })
    assert normalized["regulation_key"] == "fmla"
    assert warnings == []


def test_unknown_key_degrades_to_null_with_warning():
    normalized, warnings = _ok({
        "disposition": "universal_in_domain",
        "regulation_key": "totally_invented_key", "category_slug": "leave",
    })
    assert normalized["regulation_key"] is None
    assert any("not in regulation_key_definitions" in w for w in warnings)


def test_key_in_wrong_category_degrades():
    normalized, warnings = _ok({
        "disposition": "universal_in_domain",
        "regulation_key": "fmla", "category_slug": "workplace_safety",
    })
    assert normalized["regulation_key"] is None
    assert warnings


def test_key_without_category_matches_any_category():
    normalized, warnings = _ok({
        "disposition": "universal_in_domain", "regulation_key": "fmla",
    })
    assert normalized["regulation_key"] == "fmla"
    assert warnings == []


# ── inheritance content mapping ──────────────────────────────────────────────

def test_child_classification_copies_everything_except_the_key():
    """Sections inherit the subpart's classification content but never its
    regulation_key — a subpart's key would wrongly claim every section
    codified. materialize_inherited_children's SQL mirrors this mapping."""
    from app.core.services.scope_registry.classify import child_classification_of

    parent = {
        "disposition": "conditional",
        "applies_to_categories": ["healthcare"],
        "excludes_categories": ["retail"],
        "entity_condition": FMLA,
        "excluded_reason": None,
        "regulation_key": "fmla",
        "category_slug": "leave",
    }
    child = child_classification_of(parent)
    assert child["disposition"] == "conditional"
    assert child["applies_to_categories"] == ["healthcare"]
    assert child["excludes_categories"] == ["retail"]
    assert child["entity_condition"] == FMLA
    assert child["regulation_key"] is None
    assert child["category_slug"] is None
    # Defensive copies — mutating the child must not touch the parent.
    child["applies_to_categories"].append("biotech")
    assert parent["applies_to_categories"] == ["healthcare"]
