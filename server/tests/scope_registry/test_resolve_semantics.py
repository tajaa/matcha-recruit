"""resolve_scope's pure pieces — disposition matching + coordinate hashing.

No DB: classification_matches and coordinate_hash are pure; the conditional
branch reuses the platform's deterministic evaluate_trigger_conditions.
"""
import pytest

from app.core.services.scope_registry.resolve import (
    classification_matches,
    coordinate_hash,
    jurisdiction_scope_matches,
)

WAREHOUSE = ["warehousing"]
OPHTHALMOLOGY = ["ophthalmology", "medical_offices", "healthcare"]


def _row(disposition, applies=None, excludes=None, condition=None):
    return {
        "disposition": disposition,
        "applies_to_categories": applies or [],
        "excludes_categories": excludes or [],
        "entity_condition": condition,
    }


# ── the plan §9.3 acceptance semantics ───────────────────────────────────────

def test_universal_applies_to_a_warehouse():
    # 1910.147 lockout/tagout: universal in general industry → warehouse gets it.
    assert classification_matches(_row("universal_in_domain"), WAREHOUSE, {})


def test_ab701_applies_to_warehouse_not_manufacturer():
    ab701 = _row("category_specific", applies=["warehousing"])
    assert classification_matches(ab701, WAREHOUSE, {})
    assert not classification_matches(ab701, ["manufacturing"], {})


def test_psm_conditional_on_chemicals():
    psm = _row("conditional", condition={
        "type": "attribute", "key": "psm_covered_chemicals", "operator": "eq", "value": True,
    })
    assert classification_matches(psm, WAREHOUSE, {"psm_covered_chemicals": True})
    assert not classification_matches(psm, WAREHOUSE, {"psm_covered_chemicals": False})
    # Missing attribute → condition doesn't fire (under-scoping made visible
    # elsewhere; silence is not a pass).
    assert not classification_matches(psm, WAREHOUSE, {})


def test_fmla_headcount_threshold():
    fmla = _row("conditional", condition={
        "type": "attribute", "key": "employee_count", "operator": "gte", "value": 50,
    })
    assert not classification_matches(fmla, WAREHOUSE, {"employee_count": 40})
    assert classification_matches(fmla, WAREHOUSE, {"employee_count": 50})


def test_ancestry_match_via_parent_category():
    # A classification on healthcare applies to an ophthalmology practice
    # because resolution walks the ancestry chain.
    row = _row("category_specific", applies=["healthcare"])
    assert classification_matches(row, OPHTHALMOLOGY, {})


def test_excludes_beats_everything():
    row = _row("universal_in_domain", excludes=["healthcare"])
    assert not classification_matches(row, OPHTHALMOLOGY, {})
    assert classification_matches(row, WAREHOUSE, {})


def test_excluded_disposition_never_matches():
    assert not classification_matches(_row("excluded"), WAREHOUSE, {})


def test_conditional_with_category_scope():
    row = _row("conditional", applies=["healthcare"], condition={
        "type": "attribute", "key": "employee_count", "operator": "gte", "value": 15,
    })
    assert classification_matches(row, OPHTHALMOLOGY, {"employee_count": 20})
    assert not classification_matches(row, WAREHOUSE, {"employee_count": 20})


def test_condition_as_json_string_is_parsed():
    row = _row("conditional", condition=None)
    row["entity_condition"] = (
        '{"type": "attribute", "key": "employee_count", "operator": "gte", "value": 50}'
    )
    assert classification_matches(row, WAREHOUSE, {"employee_count": 60})


def test_garbage_condition_is_false_not_crash():
    row = _row("conditional")
    row["entity_condition"] = "{not json"
    assert not classification_matches(row, WAREHOUSE, {"employee_count": 60})


# ── coordinate hash ──────────────────────────────────────────────────────────

def test_hash_stable_and_order_independent():
    a = coordinate_hash(["warehousing"], ["j1", "j2"], {"employee_count": 40, "x": 1})
    b = coordinate_hash(["warehousing"], ["j2", "j1"], {"x": 1, "employee_count": 40})
    assert a == b


def test_hash_differs_on_any_input():
    base = coordinate_hash(["warehousing"], ["j1"], {"employee_count": 40})
    assert base != coordinate_hash(["manufacturing"], ["j1"], {"employee_count": 40})
    assert base != coordinate_hash(["warehousing"], ["j1", "j2"], {"employee_count": 40})
    assert base != coordinate_hash(["warehousing"], ["j1"], {"employee_count": 50})


def test_hash_empty_attributes_equals_none():
    assert coordinate_hash(["warehousing"], ["j1"], {}) == coordinate_hash(
        ["warehousing"], ["j1"], None
    )


# ── JSONB normalization ──────────────────────────────────────────────────────

def test_parse_jsonb_normalizes_strings_and_passes_objects():
    from app.core.services.scope_registry.resolve import parse_jsonb

    assert parse_jsonb('{"op": "and", "conditions": []}') == {"op": "and", "conditions": []}
    assert parse_jsonb({"already": "parsed"}) == {"already": "parsed"}
    assert parse_jsonb(None) is None
    assert parse_jsonb("{broken json") is None


# ── jurisdiction_scope (WS4): sub-index reach ────────────────────────────────

_LA = {"state": "CA", "city": "Los Angeles", "county": "Los Angeles"}
_SF = {"state": "CA", "city": "San Francisco", "county": "San Francisco"}


def test_scope_none_is_whole_index():
    assert jurisdiction_scope_matches(None, _LA) is True
    assert jurisdiction_scope_matches(None, None) is True


def test_scope_city_match_case_insensitive():
    scope = {"level": "city", "names": ["Los Angeles", "Oakland"]}
    assert jurisdiction_scope_matches(scope, _LA) is True
    assert jurisdiction_scope_matches(scope, {"state": "CA", "city": "los angeles"}) is True


def test_scope_city_no_match():
    scope = {"level": "city", "names": ["Los Angeles"]}
    assert jurisdiction_scope_matches(scope, _SF) is False


def test_scope_county_level():
    scope = {"level": "county", "names": ["Cook"]}
    assert jurisdiction_scope_matches(scope, {"state": "IL", "county": "Cook"}) is True
    assert jurisdiction_scope_matches(scope, {"state": "IL", "county": "DuPage"}) is False


def test_scope_no_geo_is_conservative_false():
    scope = {"level": "city", "names": ["Los Angeles"]}
    assert jurisdiction_scope_matches(scope, None) is False
    # geo present but missing the needed name (unresolved city) → False
    assert jurisdiction_scope_matches(scope, {"state": "CA", "city": None}) is False


def test_scope_malformed_never_applies():
    assert jurisdiction_scope_matches({"level": "state", "names": ["CA"]}, _LA) is False
    assert jurisdiction_scope_matches("junk", _LA) is False
    assert jurisdiction_scope_matches({"level": "city", "names": []}, _LA) is False


# ── classification_matches geo integration + back-compat ─────────────────────

def _scoped_row(disposition, scope, applies=None):
    r = _row(disposition, applies=applies)
    r["jurisdiction_scope"] = scope
    return r


def test_classification_matches_scoped_needs_geo():
    row = _scoped_row("universal_in_domain", {"level": "city", "names": ["Los Angeles"]})
    # scoped tag reaches LA
    assert classification_matches(row, WAREHOUSE, {}, _LA)
    # not SF
    assert not classification_matches(row, WAREHOUSE, {}, _SF)
    # geo-blind caller (default None) → scoped tag doesn't match
    assert not classification_matches(row, WAREHOUSE, {})


def test_classification_matches_null_scope_backcompat():
    # a row without jurisdiction_scope behaves exactly as before, 3-arg or 4-arg.
    row = _row("universal_in_domain")
    assert classification_matches(row, WAREHOUSE, {})
    assert classification_matches(row, WAREHOUSE, {}, _LA)


def test_classification_matches_scope_parses_json_string():
    # asyncpg hands jsonb back as a str on this pool.
    import json
    row = _row("universal_in_domain")
    row["jurisdiction_scope"] = json.dumps({"level": "city", "names": ["Los Angeles"]})
    assert classification_matches(row, WAREHOUSE, {}, _LA)
    assert not classification_matches(row, WAREHOUSE, {}, _SF)
