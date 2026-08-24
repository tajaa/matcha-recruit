"""Deterministic inventory demand and replenishment forecasting.

This module deliberately has no database or model-provider dependency. Sales
history is supplied by the caller, and the result is a recommendation only:
it never creates or approves an inventory order.
"""

from datetime import date, timedelta
from decimal import Decimal, ROUND_CEILING
from typing import Iterable, Mapping


MIN_NONZERO_HISTORY_DAYS = 4


def _decimal(value) -> Decimal:
    return value if isinstance(value, Decimal) else Decimal(str(value))


def _override_value(override, key: str):
    if isinstance(override, Mapping):
        return override.get(key)
    return getattr(override, key, None)


def _week_start(day: date) -> date:
    """Return the Monday containing ``day``."""
    return day - timedelta(days=day.weekday())


def _median(values: list[Decimal]) -> Decimal:
    ordered = sorted(values)
    midpoint = len(ordered) // 2
    if len(ordered) % 2:
        return ordered[midpoint]
    return (ordered[midpoint - 1] + ordered[midpoint]) / Decimal("2")


def forecast_daily_demand(
    *,
    sales_by_day: Mapping[date, Decimal],
    forecast_start: date,
    horizon_days: int,
    history_days: int,
    overrides: Iterable[object] = (),
) -> list[Decimal]:
    """Project one demand value per forecast day.

    Missing history dates are treated as zero sales. If four or more
    same-weekday observations exist, the weekday median is used; otherwise the
    trailing-history average is used. An override applies to the Monday-based
    forecast week containing its ``week_start``.
    """
    if horizon_days < 1:
        return []
    if history_days < 1:
        raise ValueError("history_days must be positive")

    history_start = forecast_start - timedelta(days=history_days)
    history = [
        _decimal(sales_by_day.get(history_start + timedelta(days=index), 0))
        for index in range(history_days)
    ]
    history = [max(value, Decimal("0")) for value in history]
    fallback = sum(history, Decimal("0")) / Decimal(str(history_days))
    by_weekday: dict[int, list[Decimal]] = {weekday: [] for weekday in range(7)}
    for index, value in enumerate(history):
        by_weekday[(history_start + timedelta(days=index)).weekday()].append(value)

    multipliers: dict[date, Decimal] = {}
    for override in overrides:
        week_start = _override_value(override, "week_start")
        multiplier = _override_value(override, "demand_multiplier")
        if week_start is None or multiplier is None:
            continue
        if not isinstance(week_start, date):
            week_start = date.fromisoformat(str(week_start)[:10])
        multipliers[week_start] = _decimal(multiplier)

    projected: list[Decimal] = []
    for index in range(horizon_days):
        day = forecast_start + timedelta(days=index)
        weekday_values = by_weekday[day.weekday()]
        baseline = (
            _median(weekday_values)
            if len(weekday_values) >= 4
            else fallback
        )
        projected.append(max(baseline * multipliers.get(_week_start(day), Decimal("1")), Decimal("0")))
    return projected


def _rounded_order_quantity(
    raw_quantity: Decimal,
    case_pack_quantity: Decimal,
    minimum_order_quantity: Decimal,
) -> Decimal:
    if raw_quantity <= 0:
        return Decimal("0")
    pack = max(case_pack_quantity, Decimal("1"))
    rounded = (raw_quantity / pack).to_integral_value(rounding=ROUND_CEILING) * pack
    if minimum_order_quantity > rounded:
        rounded = (minimum_order_quantity / pack).to_integral_value(rounding=ROUND_CEILING) * pack
    return rounded


def calculate_replenishment(
    *,
    current_quantity,
    daily_demand: list[Decimal],
    forecast_start: date,
    lead_time_days: int,
    safety_stock_days: int,
    case_pack_quantity=Decimal("1"),
    minimum_order_quantity=Decimal("0"),
    on_order_quantity=Decimal("0"),
    shelf_life_days: int | None = None,
) -> dict:
    """Calculate runout and an advisory replenishment quantity."""
    lead_time_days = max(0, int(lead_time_days))
    safety_stock_days = max(0, int(safety_stock_days))
    demand = [_decimal(value) for value in daily_demand]
    positive_demand = [value for value in demand if value > 0]
    average_demand = (
        sum(demand, Decimal("0")) / Decimal(str(len(demand)))
        if demand else Decimal("0")
    )
    projected_demand = sum(demand, Decimal("0"))

    runout_date = None
    if current_quantity is not None and positive_demand:
        remaining = _decimal(current_quantity)
        for index, value in enumerate(demand):
            remaining -= value
            if remaining <= 0:
                runout_date = forecast_start + timedelta(days=index)
                break

    order_by_date = (
        runout_date - timedelta(days=lead_time_days)
        if runout_date is not None else None
    )
    lead_demand = sum(demand[:lead_time_days], Decimal("0"))
    if lead_time_days > len(demand):
        lead_demand += average_demand * Decimal(str(lead_time_days - len(demand)))
    safety_demand = average_demand * Decimal(str(safety_stock_days))
    target_quantity = lead_demand + safety_demand
    shelf_cap = None
    shelf_life_capped = False
    if shelf_life_days:
        shelf_life_days = max(1, int(shelf_life_days))
        window = demand[lead_time_days:lead_time_days + shelf_life_days]
        shelf_cap = sum(window, Decimal("0")) or sum(demand[:shelf_life_days], Decimal("0"))
        if shelf_cap < target_quantity:
            target_quantity = shelf_cap
            shelf_life_capped = True

    status = "ready"
    suggested_quantity = None
    if current_quantity is None:
        status = "count_required"
    elif not positive_demand:
        status = "no_demand"
        suggested_quantity = Decimal("0")
    else:
        raw_quantity = max(
            target_quantity - _decimal(current_quantity) - _decimal(on_order_quantity),
            Decimal("0"),
        )
        suggested_quantity = _rounded_order_quantity(
            raw_quantity,
            _decimal(case_pack_quantity),
            _decimal(minimum_order_quantity),
        )
        # A supplier's pack size is a constraint, not permission to order
        # inventory beyond its usable life. The discrepancy is surfaced as a
        # shelf-life cap for a supplier/pack-size decision.
        if shelf_life_capped:
            suggested_quantity = min(suggested_quantity, max(target_quantity - _decimal(current_quantity) - _decimal(on_order_quantity), Decimal("0")))

    return {
        "status": status,
        "projected_demand": projected_demand,
        "average_daily_demand": average_demand,
        "lead_demand": lead_demand,
        "safety_demand": safety_demand,
        "target_quantity": target_quantity,
        "suggested_quantity": suggested_quantity,
        "runout_date": runout_date,
        "order_by_date": order_by_date,
        "on_order_quantity": _decimal(on_order_quantity),
        "shelf_cap": shelf_cap,
        "shelf_life_capped": shelf_life_capped,
    }


def forecast_item(
    *,
    sales_by_day: Mapping[date, Decimal],
    forecast_start: date,
    horizon_days: int,
    history_days: int,
    current_quantity,
    lead_time_days: int,
    safety_stock_days: int,
    case_pack_quantity=Decimal("1"),
    minimum_order_quantity=Decimal("0"),
    on_order_quantity=Decimal("0"),
    shelf_life_days: int | None = None,
    overrides: Iterable[object] = (),
) -> dict:
    """Forecast one item and suppress ordering when history is too sparse."""
    history_start = forecast_start - timedelta(days=history_days)
    observed = [
        max(_decimal(sales_by_day.get(history_start + timedelta(days=index), 0)), Decimal("0"))
        for index in range(history_days)
    ]
    nonzero_days = sum(value > 0 for value in observed)
    daily_demand = forecast_daily_demand(
        sales_by_day=sales_by_day,
        forecast_start=forecast_start,
        horizon_days=horizon_days,
        history_days=history_days,
        overrides=overrides,
    )
    result = calculate_replenishment(
        current_quantity=current_quantity,
        daily_demand=daily_demand,
        forecast_start=forecast_start,
        lead_time_days=lead_time_days,
        safety_stock_days=safety_stock_days,
        case_pack_quantity=case_pack_quantity,
        minimum_order_quantity=minimum_order_quantity,
        on_order_quantity=on_order_quantity,
        shelf_life_days=shelf_life_days,
    )
    if nonzero_days < MIN_NONZERO_HISTORY_DAYS:
        result.update(
            status="insufficient_history",
            suggested_quantity=None,
            runout_date=None,
            order_by_date=None,
        )
    result.update(
        daily_demand=daily_demand,
        history_nonzero_days=nonzero_days,
        confidence=("high" if nonzero_days >= 8 else "medium" if nonzero_days >= 4 else "low"),
    )
    return result
