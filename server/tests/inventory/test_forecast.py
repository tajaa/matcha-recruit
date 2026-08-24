from datetime import date, timedelta
from decimal import Decimal

from app.matcha.services.inventory.forecast import (
    calculate_replenishment,
    forecast_daily_demand,
    forecast_item,
)
from app.matcha.services.inventory.forecast_ai import _coerce_adjustments, _parse_json


def test_weekday_median_is_used_after_four_comparable_weeks():
    forecast_start = date(2026, 2, 2)  # Monday
    history_start = forecast_start - timedelta(days=28)
    sales = {}
    for index in range(28):
        day = history_start + timedelta(days=index)
        if day.weekday() == 0:
            sales[day] = Decimal(str(index // 7 + 1))

    demand = forecast_daily_demand(
        sales_by_day=sales,
        forecast_start=forecast_start,
        horizon_days=1,
        history_days=28,
    )

    assert demand == [Decimal("2.5")]


def test_sparse_history_suppresses_reorder_quantity():
    result = forecast_item(
        sales_by_day={date(2026, 1, 30): Decimal("2")},
        forecast_start=date(2026, 2, 2),
        horizon_days=28,
        history_days=28,
        current_quantity=Decimal("1"),
        lead_time_days=7,
        safety_stock_days=3,
    )

    assert result["status"] == "insufficient_history"
    assert result["suggested_quantity"] is None


def test_unknown_count_never_produces_order_quantity():
    result = calculate_replenishment(
        current_quantity=None,
        daily_demand=[Decimal("2")] * 14,
        forecast_start=date(2026, 2, 2),
        lead_time_days=7,
        safety_stock_days=3,
    )

    assert result["status"] == "count_required"
    assert result["suggested_quantity"] is None


def test_replenishment_accounts_for_lead_time_safety_stock_and_case_pack():
    result = calculate_replenishment(
        current_quantity=Decimal("2"),
        on_order_quantity=Decimal("1"),
        daily_demand=[Decimal("2")] * 14,
        forecast_start=date(2026, 2, 2),
        lead_time_days=3,
        safety_stock_days=2,
        case_pack_quantity=Decimal("6"),
        minimum_order_quantity=Decimal("10"),
    )

    # Target is 6 lead-time units + 4 safety units. Existing + inbound = 3,
    # and the minimum order is rounded up to two six-packs.
    assert result["target_quantity"] == Decimal("10")
    assert result["suggested_quantity"] == Decimal("12")


def test_shelf_life_caps_target_quantity():
    result = calculate_replenishment(
        current_quantity=Decimal("0"), daily_demand=[Decimal("2")] * 14,
        forecast_start=date(2026, 2, 2), lead_time_days=2, safety_stock_days=5,
        shelf_life_days=5,
    )
    assert result["shelf_cap"] == Decimal("10")
    assert result["target_quantity"] == Decimal("10")
    assert result["shelf_life_capped"] is True


def test_case_pack_cannot_reinflate_past_shelf_cap():
    result = calculate_replenishment(
        current_quantity=Decimal("0"), daily_demand=[Decimal("2")] * 14,
        forecast_start=date(2026, 2, 2), lead_time_days=2, safety_stock_days=5,
        shelf_life_days=5, case_pack_quantity=Decimal("12"),
    )
    assert result["suggested_quantity"] == Decimal("10")


def test_case_pack_still_rounds_when_shelf_life_does_not_cap():
    result = calculate_replenishment(
        current_quantity=Decimal("0"), daily_demand=[Decimal("2")] * 56,
        forecast_start=date(2026, 2, 2), lead_time_days=2, safety_stock_days=5,
        shelf_life_days=30, case_pack_quantity=Decimal("12"),
    )
    assert result["shelf_life_capped"] is False
    assert result["suggested_quantity"] == Decimal("24")


def test_shelf_life_cap_falls_back_when_window_is_past_horizon():
    result = calculate_replenishment(
        current_quantity=Decimal("0"), daily_demand=[Decimal("2")] * 3,
        forecast_start=date(2026, 2, 2), lead_time_days=20, safety_stock_days=5,
        shelf_life_days=2,
    )
    assert result["shelf_cap"] == Decimal("4")


def test_week_override_changes_only_its_forecast_week():
    start = date(2026, 2, 2)
    demand = forecast_daily_demand(
        sales_by_day={start - timedelta(days=index): Decimal("1") for index in range(1, 29)},
        forecast_start=start,
        horizon_days=14,
        history_days=28,
        overrides=[{
            "week_start": start,
            "demand_multiplier": Decimal("1.5"),
            "reason": "promotion",
        }],
    )

    assert demand[:7] == [Decimal("1.5")] * 7
    assert demand[7:] == [Decimal("1")] * 7


def test_ai_adjustments_are_clamped_to_mondays_inside_horizon():
    start = date(2026, 2, 2)
    adjustments = _coerce_adjustments(
        {
            "adjustments": [
                {"week_start": "2026-02-02", "demand_multiplier": 1.25,
                 "reason": "promotion", "confidence": "medium"},
                {"week_start": "2026-02-03", "demand_multiplier": 1.25,
                 "reason": "not a Monday", "confidence": "high"},
                {"week_start": "2026-03-02", "demand_multiplier": 9,
                 "reason": "too large", "confidence": "high"},
            ]
        },
        horizon_start=start,
        horizon_days=14,
    )

    assert adjustments == [{
        "week_start": start,
        "demand_multiplier": Decimal("1.25"),
        "reason": "promotion",
        "confidence": "medium",
        "source": "ai_accepted",
    }]


def test_ai_json_parser_removes_json_fence():
    assert _parse_json('```json\n{"adjustments": []}\n```') == {"adjustments": []}
