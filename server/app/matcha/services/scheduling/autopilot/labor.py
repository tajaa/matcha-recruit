"""Convert forecast dollars to bounded labor-hour targets."""

from __future__ import annotations

from dataclasses import dataclass, replace
from decimal import ROUND_HALF_UP, Decimal

from ..assignment_guard import POLICY_DEFAULT_WEEKLY_CAP_MINUTES
from .forecast import SalesForecast
from .history import HistoryModel
from .windows import DayWindow


def _d(value) -> Decimal:
    return value if isinstance(value, Decimal) else Decimal(str(value))


def _half_hours(value: Decimal) -> Decimal:
    """Round to the 30-minute grid. `quantize(Decimal("0.5"))` would not: it
    only borrows that exponent, so it rounds to 0.1h."""
    return (value * 2).to_integral_value(rounding=ROUND_HALF_UP) / 2


@dataclass(frozen=True)
class RosterCapacity:
    employees: int
    weekly_hours: Decimal
    qualified_by_job: dict[str, int]


@dataclass(frozen=True)
class LaborTarget:
    day: object
    hours: Decimal
    method: str
    floor_hours: Decimal
    raw_hours: Decimal
    notes: tuple[str, ...]


def roster_capacity(roster: dict, jobs: list[dict], gated_job_ids: set[str]) -> RosterCapacity:
    employees = sorted(roster.get("employees") or [], key=lambda e: str(e.get("id")))
    weekly = sum(
        (Decimal(int(e.get("target_weekly_minutes") or e.get("max_weekly_minutes") or POLICY_DEFAULT_WEEKLY_CAP_MINUTES)) / 60
         for e in employees), Decimal(0),
    )
    qualified: dict[str, int] = {}
    for job in sorted(jobs, key=lambda j: str(j.get("id"))):
        job_id = str(job["id"])
        if job_id not in gated_job_ids:
            qualified[job_id] = len(employees)
            continue
        qualified[job_id] = sum(
            1 for employee in employees
            if any(str(item.get("job_id")) == job_id and item.get("qualification_status") == "active"
                   for item in employee.get("jobs") or [])
        )
    return RosterCapacity(len(employees), weekly, qualified)


def floor_headcount(profile: dict, leader_seat: bool) -> int:
    return max(0, int(profile.get("min_floor_staff") or 0)) + (1 if leader_seat else 0)


def labor_target(
    window: DayWindow, forecast: SalesForecast, *, history: HistoryModel,
    profile: dict, blended_hourly_rate: Decimal | None, leader_seat: bool,
) -> LaborTarget:
    window_hours = Decimal(window.slot_count) / 2
    floor_hours = Decimal(floor_headcount(profile, leader_seat)) * window_hours
    raw = floor_hours
    method = "floor"
    notes: list[str] = []
    splh = history.splh_by_weekday.get(window.weekday) or history.splh_all
    if forecast.forecast is not None and splh and splh > 0:
        raw = forecast.forecast / splh
        method = "splh"
        notes.append(
            f"{raw.quantize(Decimal('0.1'))}h from ${forecast.forecast:,.2f} at "
            f"${splh:,.2f}/labor-hour learned from published weeks"
        )
    elif (forecast.forecast is not None and profile.get("target_labor_pct") is not None
          and blended_hourly_rate is not None and blended_hourly_rate > 0):
        pct = _d(profile["target_labor_pct"])
        raw = forecast.forecast * pct / 100 / blended_hourly_rate
        method = "labor_pct"
        notes.append(f"{pct}% labor target at ${blended_hourly_rate:,.2f}/hour")
    elif history.hours_by_weekday.get(window.weekday) is not None and forecast.index is not None:
        usual = history.hours_by_weekday[window.weekday]
        raw = usual * forecast.index
        method = "history_hours"
        notes.append(
            f"no $/labor-hour learned — scaling usual {usual}h by sales index {forecast.index}"
        )
    else:
        notes.append("coverage floor only — no sales-to-hours conversion")
    hours = _half_hours(max(raw, floor_hours))
    # Compared before rounding: a 31.3h target rounding to 31.5h was not
    # raised by the floor, and must not say so.
    if raw < floor_hours:
        notes.append(f"coverage floor raised the target to {hours}h")
    return LaborTarget(window.day, hours, method, floor_hours, raw, tuple(notes))


def cap_week_to_capacity(
    targets: list[LaborTarget], capacity: RosterCapacity,
) -> tuple[list[LaborTarget], str | None]:
    planned = sum((t.hours for t in targets), Decimal(0))
    floors = sum((t.floor_hours for t in targets), Decimal(0))
    if planned <= capacity.weekly_hours:
        return targets, None
    if planned <= floors:
        return targets, f"roster capacity {capacity.weekly_hours}h is below the {floors}h coverage floor"
    scale = max(Decimal(0), min(Decimal(1), (capacity.weekly_hours - floors) / (planned - floors)))
    out = [
        replace(t, hours=_half_hours(t.floor_hours + (t.hours - t.floor_hours) * scale))
        for t in targets
    ]
    return out, f"roster capacity caps the plan at {capacity.weekly_hours}h (wanted {planned}h)"
