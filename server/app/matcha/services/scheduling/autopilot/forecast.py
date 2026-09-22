"""Sales baselines, labelled weather modifiers, and confidence."""

from __future__ import annotations

from dataclasses import dataclass, replace
from datetime import date, timedelta
from decimal import ROUND_HALF_EVEN, Decimal
from statistics import median

from .policy import (
    POLICY_CONFIDENCE_HIGH_OBS,
    POLICY_CONFIDENCE_MEDIUM_OBS,
    POLICY_INDEX_MAX,
    POLICY_INDEX_MIN,
    POLICY_RAIN_HELPS,
    POLICY_RAIN_HURTS,
    POLICY_SALES_HISTORY_DAYS,
    POLICY_WEEKDAY_MEDIAN_MIN_OBS,
)


def _d(value) -> Decimal:
    return value if isinstance(value, Decimal) else Decimal(str(value))


@dataclass(frozen=True)
class WeatherEffect:
    condition: str | None
    precip_probability: int | None
    sensitivity: str
    modifier: Decimal
    note: str | None


@dataclass(frozen=True)
class SalesForecast:
    day: date
    baseline: Decimal | None
    observations: int
    method: str
    weather: WeatherEffect
    forecast: Decimal | None
    index: Decimal | None
    confidence: str
    notes: tuple[str, ...]


def weekday_baseline(
    day: date, *, sales_by_day: dict[date, Decimal], anchor: date,
) -> tuple[Decimal | None, int, str]:
    start = anchor - timedelta(days=POLICY_SALES_HISTORY_DAYS)
    known = sorted(
        (_d(value) for when, value in sales_by_day.items() if start <= when < anchor),
    )
    same = sorted(
        (_d(value) for when, value in sales_by_day.items()
         if start <= when < anchor and when.weekday() == day.weekday()),
    )
    if len(same) >= POLICY_WEEKDAY_MEDIAN_MIN_OBS:
        return _d(median(same)), len(same), "weekday_median"
    if known:
        return sum(known, Decimal(0)) / len(known), len(same), "trailing_mean"
    return None, 0, "none"


def weather_effect(day: date, weather_by_day: dict[date, dict], sensitivity: str) -> WeatherEffect:
    row = weather_by_day.get(day) or {}
    condition = row.get("condition")
    probability = row.get("precip_probability")
    if probability is None:
        return WeatherEffect(condition, None, sensitivity, Decimal(1),
                             f"weather unavailable for {day.isoformat()} — no weather adjustment")
    probability = int(probability)
    policies = POLICY_RAIN_HURTS if sensitivity == "rain_hurts" else (
        POLICY_RAIN_HELPS if sensitivity == "rain_helps" else ()
    )
    modifier = Decimal(1)
    for threshold, candidate in policies:
        if probability >= threshold:
            modifier = candidate
            break
    note = None
    if modifier != 1:
        direction = "trimmed" if modifier < 1 else "raised"
        note = f"rain {day.strftime('%A')} {direction} demand {abs(int((modifier - 1) * 100))}%"
    return WeatherEffect(condition, probability, sensitivity, modifier, note)


def forecast_day(
    day: date, *, sales_by_day: dict[date, Decimal], weather_by_day: dict[date, dict],
    sensitivity: str, anchor: date,
) -> SalesForecast:
    baseline, observations, method = weekday_baseline(day, sales_by_day=sales_by_day, anchor=anchor)
    effect = weather_effect(day, weather_by_day, sensitivity)
    notes: list[str] = []
    if method == "trailing_mean":
        notes.append(
            f"only {observations} past {day.strftime('%A')}s with sales — using 13-week daily average"
        )
    elif method == "none":
        notes.append("no sales history — coverage floor only")
    if effect.note:
        notes.append(effect.note)
    confidence = "none" if baseline is None else (
        "low" if observations < POLICY_CONFIDENCE_MEDIUM_OBS else
        "medium" if observations < POLICY_CONFIDENCE_HIGH_OBS else "high"
    )
    forecast = None if baseline is None else (
        baseline * effect.modifier
    ).quantize(Decimal("0.01"), rounding=ROUND_HALF_EVEN)
    return SalesForecast(day, baseline, observations, method, effect, forecast, None, confidence, tuple(notes))


def attach_index(forecasts: list[SalesForecast], open_days: set[date]) -> list[SalesForecast]:
    values = [f.forecast for f in forecasts if f.day in open_days and f.forecast is not None]
    norm = sum(values, Decimal(0)) / len(values) if values else None
    out = []
    for item in forecasts:
        index = None
        if item.forecast is not None and norm is not None and norm > 0:
            index = max(POLICY_INDEX_MIN, min(POLICY_INDEX_MAX, item.forecast / norm)).quantize(Decimal("0.01"))
        out.append(replace(item, index=index))
    return out


def week_confidence(forecasts: list[SalesForecast], open_days: set[date]) -> str:
    order = {"none": 0, "low": 1, "medium": 2, "high": 3}
    values = [f.confidence for f in forecasts if f.day in open_days]
    return min(values, key=order.get) if values else "none"
