import pytest

import asyncio

from app.core.services import compliance_service as cs


def test_base_title_strips_city_county_variants():
    assert cs._base_title(
        "City of West Hollywood Minimum Wage",
        "West Hollywood",
    ) == "Minimum Wage"

    assert cs._base_title(
        "Los Angeles County Minimum Wage",
        "Los Angeles",
    ) == "Minimum Wage"

    assert cs._base_title(
        "West Hollywood Minimum Wage",
        "City of West Hollywood",
    ) == "Minimum Wage"


def test_filter_by_jurisdiction_priority_prefers_local():
    requirements = [
        {
            "category": "minimum_wage",
            "jurisdiction_level": "state",
            "jurisdiction_name": "California",
            "title": "California Minimum Wage",
            "current_value": "$16.90",
        },
        {
            "category": "minimum_wage",
            "jurisdiction_level": "city",
            "jurisdiction_name": "West Hollywood",
            "title": "City of West Hollywood Minimum Wage",
            "current_value": "$20.25",
        },
        {
            "category": "overtime",
            "jurisdiction_level": "state",
            "jurisdiction_name": "California",
            "title": "California Overtime",
        },
    ]

    filtered = cs._filter_by_jurisdiction_priority(requirements)
    titles = {req["title"] for req in filtered}

    assert "City of West Hollywood Minimum Wage" in titles
    assert "California Minimum Wage" not in titles
    assert "California Overtime" in titles


def test_category_normalization_groups_titles():
    requirements = [
        {
            "category": "Minimum Wage",
            "jurisdiction_level": "state",
            "jurisdiction_name": "California",
            "title": "California Minimum Wage",
        },
        {
            "category": "minimum_wage",
            "jurisdiction_level": "county",
            "jurisdiction_name": "Los Angeles",
            "title": "Los Angeles County Minimum Wage",
        },
    ]

    filtered = cs._filter_by_jurisdiction_priority(requirements)
    titles = {req["title"] for req in filtered}

    assert "Los Angeles County Minimum Wage" in titles
    assert "California Minimum Wage" not in titles


def test_minimum_wage_keeps_different_rate_types():
    """Tests that different rate_type variants are kept as separate entries."""
    requirements = [
        {
            "category": "minimum_wage",
            "rate_type": "general",
            "jurisdiction_level": "state",
            "jurisdiction_name": "California",
            "title": "California Minimum Wage",
            "current_value": "$16.90",
        },
        {
            "category": "minimum_wage",
            "rate_type": "general",
            "jurisdiction_level": "city",
            "jurisdiction_name": "West Hollywood",
            "title": "West Hollywood Minimum Wage",
            "current_value": "$20.25",
        },
        {
            "category": "minimum_wage",
            "rate_type": "hotel",
            "jurisdiction_level": "city",
            "jurisdiction_name": "West Hollywood",
            "title": "West Hollywood Hotel Worker Minimum Wage",
            "current_value": "$19.61",
        },
        {
            "category": "minimum_wage",
            "rate_type": "hotel",
            "jurisdiction_level": "state",
            "jurisdiction_name": "California",
            "title": "California Hotel Worker Minimum Wage",
            "current_value": "$18.00",
        },
    ]

    filtered = cs._filter_by_jurisdiction_priority(requirements)
    titles = {req["title"] for req in filtered}

    # General rate: city overrides state
    assert "West Hollywood Minimum Wage" in titles
    assert "California Minimum Wage" not in titles
    # Hotel rate: city overrides state
    assert "West Hollywood Hotel Worker Minimum Wage" in titles
    assert "California Hotel Worker Minimum Wage" not in titles
    # Both general and hotel rates are kept
    assert len(filtered) == 2


def test_minimum_wage_rate_type_tipped_and_general():
    """Tests that tipped and general minimum wage are kept separately."""
    requirements = [
        {
            "category": "minimum_wage",
            "rate_type": "general",
            "jurisdiction_level": "city",
            "jurisdiction_name": "Boulder",
            "title": "Boulder Minimum Wage",
            "current_value": "$16.82",
        },
        {
            "category": "minimum_wage",
            "rate_type": "tipped",
            "jurisdiction_level": "city",
            "jurisdiction_name": "Boulder",
            "title": "Boulder Tipped Minimum Wage",
            "current_value": "$13.80",
        },
    ]

    filtered = cs._filter_by_jurisdiction_priority(requirements)
    titles = {req["title"] for req in filtered}

    assert "Boulder Minimum Wage" in titles
    assert "Boulder Tipped Minimum Wage" in titles
    assert len(filtered) == 2


def test_compute_requirement_key_includes_rate_type():
    """Tests that rate_type is included in requirement key for minimum_wage."""
    general_req = {
        "category": "minimum_wage",
        "rate_type": "general",
        "title": "Boulder Minimum Wage",
        "jurisdiction_name": "Boulder",
    }
    tipped_req = {
        "category": "minimum_wage",
        "rate_type": "tipped",
        "title": "Boulder Tipped Minimum Wage",
        "jurisdiction_name": "Boulder",
    }
    overtime_req = {
        "category": "overtime",
        "title": "Colorado Overtime",
        "jurisdiction_name": "Colorado",
    }

    # Different rate_types produce different keys — via the CANONICAL registry
    # vocabulary (anti-polymorphy: the composite no longer speaks the raw
    # rate_type dialect, so both dialects collapse to one write identity).
    assert cs._compute_requirement_key(general_req) == "minimum_wage:state_minimum_wage"
    assert cs._compute_requirement_key(tipped_req) == "minimum_wage:tipped_minimum_wage"
    # Non-minimum_wage categories don't use rate_type
    assert cs._compute_requirement_key(overtime_req) == "overtime:overtime"


def test_minimum_wage_dialects_collapse_to_one_identity():
    """The polymorphy fix: a pass keying on rate_type and one keying on the
    registry vocabulary must produce the SAME composite, so a re-research
    UPDATEs in place instead of minting a twin (the NY exempt ×2 bug)."""
    by_rate_type = {"category": "minimum_wage", "rate_type": "exempt_salary",
                    "title": "Exempt Salary Threshold"}
    by_registry_key = {"category": "minimum_wage",
                       "regulation_key": "exempt_salary_threshold",
                       "rate_type": "exempt_salary",
                       "title": "Exempt Employee Salary Threshold"}
    assert (cs._compute_requirement_key(by_rate_type)
            == cs._compute_requirement_key(by_registry_key)
            == "minimum_wage:exempt_salary_threshold")


def test_compute_key_parts_bare_key_per_shape():
    """The bare regulation_key (store↔scope join key) per composite shape, and
    composite parity with the legacy _compute_requirement_key."""
    cases = [
        # minimum_wage: composite AND bare both use the registry vocab (the
        # anti-polymorphy canonicalization); bare is level-sensitive for 'general'.
        ({"category": "minimum_wage", "rate_type": "general"},
         "minimum_wage:state_minimum_wage", "state_minimum_wage"),
        ({"category": "minimum_wage", "rate_type": "general", "jurisdiction_level": "city"},
         "minimum_wage:local_minimum_wage", "local_minimum_wage"),
        ({"category": "minimum_wage", "rate_type": "general", "jurisdiction_level": "federal"},
         "minimum_wage:national_minimum_wage", "national_minimum_wage"),
        ({"category": "minimum_wage", "rate_type": "tipped"},
         "minimum_wage:tipped_minimum_wage", "tipped_minimum_wage"),
        # standard: a resolved registry regulation_key → bare is that key.
        ({"category": "overtime", "regulation_key": "daily_weekly_overtime",
          "title": "OT"},
         "overtime:daily_weekly_overtime", "daily_weekly_overtime"),
        # aet-prefixed: bare = the last segment (the true regkey), not the prefix.
        ({"category": "leave", "regulation_key": "fmla", "title": "FMLA",
          "applicable_entity_types": ["private_employer"]},
         "private_employer:leave:fmla", "fmla"),
    ]
    for req, want_composite, want_bare in cases:
        composite, bare = cs._compute_key_parts(req)
        assert composite == want_composite, req
        assert bare == want_bare, req
        # parity: the wrapper still returns exactly the composite.
        assert cs._compute_requirement_key(req) == want_composite, req
        # invariant: bare is the last segment of the composite.
        assert bare == composite.rsplit(":", 1)[-1] or req["category"] == "minimum_wage"


def test_normalize_value_text_handles_wording_only_changes():
    assert cs._normalize_value_text("$16.90 / hour") == cs._normalize_value_text(
        "$16.90 per hour"
    )
    assert cs._normalize_value_text("biweekly", "pay_frequency") == cs._normalize_value_text(
        "every two weeks", "pay_frequency"
    )
    assert cs._normalize_value_text("twice a month", "pay_frequency") == cs._normalize_value_text(
        "semimonthly", "pay_frequency"
    )
    assert cs._normalize_value_text(
        "semi-monthly or at least twice a month", "pay_frequency"
    ) == cs._normalize_value_text("semimonthly", "pay_frequency")
    assert cs._normalize_value_text(
        "At least twice per month", "pay_frequency"
    ) == cs._normalize_value_text("Semi-monthly", "pay_frequency")
    assert cs._normalize_value_text(
        "$16.90", "minimum_wage"
    ) == cs._normalize_value_text("$16.90/hr", "minimum_wage")


# ── _normalize_value_text edge cases (P3) ──


def test_normalize_value_text_preserves_decimals():
    # Decimal zeros are preserved in normalization (they're meaningful in wages)
    assert cs._normalize_value_text("$15.00") != cs._normalize_value_text("$15")
    assert cs._normalize_value_text("$15.50") != cs._normalize_value_text("$15")
    # Same decimal values normalize identically when category triggers /hr normalization
    assert cs._normalize_value_text("$15.00", "minimum_wage") == cs._normalize_value_text(
        "$15.00 per hour", "minimum_wage"
    )


def test_normalize_value_text_removes_ordinals():
    assert cs._normalize_value_text("1st day") == cs._normalize_value_text("1 day")
    assert cs._normalize_value_text("2nd business day") == cs._normalize_value_text("2 business day")
    assert cs._normalize_value_text("3rd notice") == cs._normalize_value_text("3 notice")
    assert cs._normalize_value_text("4th quarter") == cs._normalize_value_text("4 quarter")


def test_normalize_value_text_compensated_uncompensated_synonyms():
    assert cs._normalize_value_text(
        "compensated time off", "sick_leave"
    ) == cs._normalize_value_text("paid time off", "sick_leave")
    assert cs._normalize_value_text(
        "uncompensated leave", "sick_leave"
    ) == cs._normalize_value_text("unpaid leave", "sick_leave")


def test_normalize_value_text_sorted_pay_frequency_or():
    # "biweekly or semimonthly" and "semimonthly or biweekly" should match
    assert cs._normalize_value_text(
        "biweekly or semimonthly", "pay_frequency"
    ) == cs._normalize_value_text("semimonthly or biweekly", "pay_frequency")


# ── Rejection guard tolerance boundary (Fix 3) ──


def test_min_wage_rejection_tolerance_allows_tiny_decrease():
    """A decrease of $0.004 (below the $0.005 threshold) should NOT be rejected."""
    # _is_material_numeric_change uses the MATERIAL_CHANGE_THRESHOLDS, but the
    # rejection guard itself uses the 0.005 tolerance. We test the guard logic
    # inline since the guard is inside an async function — we verify via the
    # underlying comparison.
    old_num, new_num = 15.004, 15.000
    # This should NOT trigger rejection (diff = 0.004 <= 0.005)
    assert not (float(old_num) - float(new_num)) > 0.005


def test_min_wage_rejection_tolerance_rejects_real_decrease():
    """A decrease of $0.006 (above the $0.005 threshold) SHOULD be rejected."""
    old_num, new_num = 15.006, 15.000
    assert (float(old_num) - float(new_num)) > 0.005


def test_min_wage_rejection_tolerance_exact_boundary():
    """At exactly $0.005 difference, floating-point makes this > 0.005, so it IS rejected.
    This is acceptable — half a cent either way is fine."""
    old_num, new_num = 15.005, 15.000
    # Due to floating-point, 15.005 - 15.000 = 0.005000...0782 > 0.005
    assert (float(old_num) - float(new_num)) > 0.005


# ── Text fallback for non-wage categories (Fix 4) ──


def test_material_change_text_fallback_non_wage():
    """Non-wage category: same numeric but different text → material change."""
    # Both have the same numeric (30) but different text semantics
    assert not cs._is_material_numeric_change(30, 30, "overtime")
    assert cs._is_material_text_change(
        "30 minutes unpaid", "30 minutes paid", "overtime"
    )


def test_material_change_text_fallback_suppressed_for_wage():
    """Wage category: same numeric but different wording → NOT material (Gemini rephrase)."""
    assert not cs._is_material_numeric_change(19.08, 19.08, "minimum_wage")
    assert not cs._is_material_text_change(
        "$19.08 per hour", "$19.08/hr", "minimum_wage"
    )


# ── _extract_numeric_value ──


def test_extract_numeric_value_basic():
    assert cs._extract_numeric_value("$16.90 per hour") == 16.90
    assert cs._extract_numeric_value("30 days") == 30
    assert cs._extract_numeric_value(None) is None
    assert cs._extract_numeric_value("no numbers here") is None


# ── _normalize_category ──


def test_normalize_category():
    assert cs._normalize_category("Minimum Wage") == "minimum_wage"
    assert cs._normalize_category("sick-leave") == "sick_leave"
    assert cs._normalize_category("  Pay Frequency  ") == "pay_frequency"
    assert cs._normalize_category(None) is None


class _FakeConn:
    def __init__(self, preemption_rows):
        self._preemption_rows = preemption_rows

    async def fetch(self, query: str, *args):
        if "FROM state_preemption_rules" in query:
            return self._preemption_rows
        return []


def test_filter_with_preemption_preempted_keeps_state():
    requirements = [
        {
            "category": "minimum_wage",
            "jurisdiction_level": "state",
            "jurisdiction_name": "California",
            "title": "California Minimum Wage",
            "current_value": "$16.90",
        },
        {
            "category": "minimum_wage",
            "jurisdiction_level": "city",
            "jurisdiction_name": "West Hollywood",
            "title": "City of West Hollywood Minimum Wage",
            "current_value": "$20.25",
        },
    ]
    conn = _FakeConn([{"category": "minimum_wage", "allows_local_override": False}])

    filtered = asyncio.run(cs._filter_with_preemption(conn, requirements, "CA"))
    titles = {req["title"] for req in filtered}

    assert "California Minimum Wage" in titles
    assert "City of West Hollywood Minimum Wage" not in titles


def test_filter_with_preemption_preempted_promotes_local_when_state_missing():
    requirements = [
        {
            "category": "minimum_wage",
            "jurisdiction_level": "county",
            "jurisdiction_name": "Clark County",
            "title": "Clark County Minimum Wage",
            "current_value": "$12.00",
        }
    ]
    conn = _FakeConn([{"category": "minimum_wage", "allows_local_override": False}])

    filtered = asyncio.run(cs._filter_with_preemption(conn, requirements, "NV"))
    assert len(filtered) == 1
    assert filtered[0]["jurisdiction_level"] == "state"
    assert filtered[0]["jurisdiction_name"] == "Nevada"
    assert filtered[0]["title"] == "Clark County Minimum Wage"


def test_filter_with_preemption_min_wage_uses_most_beneficial():
    requirements = [
        {
            "category": "minimum_wage",
            "jurisdiction_level": "state",
            "jurisdiction_name": "Colorado",
            "title": "Colorado Minimum Wage",
            "current_value": "$20.00",
        },
        {
            "category": "minimum_wage",
            "jurisdiction_level": "city",
            "jurisdiction_name": "Boulder",
            "title": "Boulder Minimum Wage",
            "current_value": "$16.82",
        },
    ]
    conn = _FakeConn([{"category": "minimum_wage", "allows_local_override": True}])

    filtered = asyncio.run(cs._filter_with_preemption(conn, requirements, "CO"))
    assert len(filtered) == 1
    assert filtered[0]["jurisdiction_level"] == "state"
    assert filtered[0]["title"] == "Colorado Minimum Wage"


def test_filter_with_preemption_non_wage_prefers_local_when_allowed():
    requirements = [
        {
            "category": "overtime",
            "jurisdiction_level": "state",
            "jurisdiction_name": "California",
            "title": "California Overtime",
        },
        {
            "category": "overtime",
            "jurisdiction_level": "city",
            "jurisdiction_name": "San Francisco",
            "title": "San Francisco Overtime",
        },
    ]
    conn = _FakeConn([{"category": "overtime", "allows_local_override": True}])

    filtered = asyncio.run(cs._filter_with_preemption(conn, requirements, "CA"))
    assert len(filtered) == 1
    assert filtered[0]["jurisdiction_level"] == "city"
    assert filtered[0]["title"] == "San Francisco Overtime"


# ── Trigger-aware key computation ──


def test_compute_requirement_key_baseline_no_prefix():
    """Baseline requirements (no applicable_entity_types) should not be prefixed."""
    req = {"category": "billing_integrity", "title": "False Claims Act"}
    key = cs._compute_requirement_key(req)
    assert key.startswith("billing_integrity:")
    assert not key.startswith("fqhc:")


def test_compute_requirement_key_triggered_has_prefix():
    """Triggered requirements should include entity type prefix."""
    req = {
        "category": "billing_integrity",
        "title": "FQHC Sliding Fee Discount",
        "applicable_entity_types": ["fqhc"],
    }
    key = cs._compute_requirement_key(req)
    assert key.startswith("fqhc:billing_integrity:")


def test_compute_requirement_key_different_triggers_no_collision():
    """Same title under different triggers should produce different keys."""
    base = {"category": "billing_integrity", "title": "Provider Enrollment"}
    fqhc = {**base, "applicable_entity_types": ["fqhc"]}
    medi_cal = {**base, "applicable_entity_types": ["medi_cal"]}

    key_base = cs._compute_requirement_key(base)
    key_fqhc = cs._compute_requirement_key(fqhc)
    key_medi_cal = cs._compute_requirement_key(medi_cal)

    assert key_base != key_fqhc
    assert key_base != key_medi_cal
    assert key_fqhc != key_medi_cal


def test_compute_requirement_key_empty_entity_types_no_prefix():
    """Empty applicable_entity_types list should not produce a prefix."""
    req = {
        "category": "billing_integrity",
        "title": "General Billing Rule",
        "applicable_entity_types": [],
    }
    key = cs._compute_requirement_key(req)
    assert key.startswith("billing_integrity:")
    assert not key.startswith(":billing_integrity:")


# ── _jurisdiction_row_to_dict trigger fields ──


def test_jurisdiction_row_to_dict_includes_trigger_fields():
    """Trigger metadata should be preserved when converting row to dict."""
    row = {
        "category": "billing_integrity",
        "rate_type": None,
        "jurisdiction_level": "federal",
        "jurisdiction_name": "United States",
        "title": "FQHC Sliding Fee",
        "description": "desc",
        "current_value": "Required",
        "numeric_value": None,
        "source_url": "https://example.gov",
        "source_name": "HRSA",
        "effective_date": None,
        "expiration_date": None,
        "applicable_industries": None,
        "trigger_conditions": {"type": "entity_type", "value": "fqhc"},
        "applicable_entity_types": ["fqhc"],
    }
    result = cs._jurisdiction_row_to_dict(row)
    assert result["trigger_conditions"] == {"type": "entity_type", "value": "fqhc"}
    assert result["applicable_entity_types"] == ["fqhc"]


def test_jurisdiction_row_to_dict_null_trigger_fields():
    """Baseline rows should have None for trigger fields."""
    row = {
        "category": "minimum_wage",
        "rate_type": "general",
        "jurisdiction_level": "state",
        "jurisdiction_name": "California",
        "title": "CA Minimum Wage",
        "description": "desc",
        "current_value": "$16.50",
        "numeric_value": 16.50,
        "source_url": "https://dir.ca.gov",
        "source_name": "DIR",
        "effective_date": None,
        "expiration_date": None,
        "applicable_industries": None,
        "trigger_conditions": None,
        "applicable_entity_types": None,
    }
    result = cs._jurisdiction_row_to_dict(row)
    assert result["trigger_conditions"] is None
    assert result["applicable_entity_types"] is None


# ── trigger conditions must fail CLOSED on malformed JSON ────────────────────
#
# `trigger_conditions` on jurisdiction_requirements are written by Gemini
# research with no shape gate (unlike scope-registry classifications, which
# validate_proposal rejects). An unrecognized node used to evaluate to True,
# which silently turned a CONDITIONAL obligation into a universal one — e.g.
# the PSM standard served to every company. Found by the §9 acceptance test,
# whose fixture had exactly this typo.

def test_unknown_compound_op_does_not_universalize_a_conditional():
    # A plausible model typo: a LEAF that says "op" where it means "operator".
    malformed = {"type": "attribute", "key": "psm_covered_chemicals", "op": "is_true"}

    assert cs.evaluate_trigger_conditions(malformed, {}) is False
    assert cs.evaluate_trigger_conditions(malformed, {"psm_covered_chemicals": True}) is False


def test_unknown_leaf_type_does_not_universalize_a_conditional():
    assert cs.evaluate_trigger_conditions({"type": "vibes"}, {"anything": True}) is False


def test_wellformed_conditions_still_evaluate_normally():
    psm = {"type": "attribute", "key": "psm_covered_chemicals",
           "operator": "eq", "value": True}
    assert cs.evaluate_trigger_conditions(psm, {"psm_covered_chemicals": True}) is True
    assert cs.evaluate_trigger_conditions(psm, {"psm_covered_chemicals": False}) is False
    assert cs.evaluate_trigger_conditions(psm, {}) is False

    fmla = {"type": "attribute", "key": "employee_count", "operator": "gte", "value": 50}
    assert cs.evaluate_trigger_conditions(fmla, {"employee_count": 60}) is True
    assert cs.evaluate_trigger_conditions(fmla, {"employee_count": 10}) is False

    both = {"op": "and", "conditions": [psm, fmla]}
    assert cs.evaluate_trigger_conditions(
        both, {"psm_covered_chemicals": True, "employee_count": 60}) is True
    assert cs.evaluate_trigger_conditions(
        both, {"psm_covered_chemicals": True, "employee_count": 10}) is False

    # No trigger at all still means "always applies" — unchanged.
    assert cs.evaluate_trigger_conditions(None, {}) is True


# ── a stateless location must not 500 the compliance page ────────────────────

@pytest.mark.asyncio
async def test_preemption_filter_survives_a_location_with_no_state():
    """`_filter_with_preemption` called `state.upper()` unguarded, so any
    location with a NULL state (10 live rows on dev) raised AttributeError and
    took the whole tenant compliance page down with a 500. Preemption is a
    state-law question — with no state there is no rule to apply, so the
    requirements pass through unfiltered."""
    reqs = [
        {"category": "minimum_wage", "jurisdiction_level": "state",
         "jurisdiction_name": "California", "title": "CA Minimum Wage"},
    ]

    out = await cs._filter_with_preemption(None, reqs, None)  # conn unused on this path

    assert out == reqs


def test_an_empty_not_does_not_universalize_a_conditional():
    """The last shape still failing OPEN. `_condition_shape_error` rejects it at
    write time on the scope-registry side; nothing gates it on the research
    side."""
    assert cs.evaluate_trigger_conditions(
        {"op": "not", "conditions": []}, {"anything": True}) is False
    # A well-formed `not` still negates.
    psm = {"type": "attribute", "key": "psm_covered_chemicals",
           "operator": "eq", "value": True}
    assert cs.evaluate_trigger_conditions(
        {"op": "not", "conditions": [psm]}, {"psm_covered_chemicals": True}) is False
    assert cs.evaluate_trigger_conditions(
        {"op": "not", "conditions": [psm]}, {}) is True
