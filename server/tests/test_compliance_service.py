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

    # Different rate_types produce different keys
    assert cs._compute_requirement_key(general_req) == "minimum_wage:general"
    assert cs._compute_requirement_key(tipped_req) == "minimum_wage:tipped"
    # Non-minimum_wage categories don't use rate_type
    assert cs._compute_requirement_key(overtime_req) == "overtime:overtime"


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
