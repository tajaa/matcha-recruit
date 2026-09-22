"""Convert forecast dollars to bounded labor-hour targets."""

from __future__ import annotations

from dataclasses import dataclass, field, replace
from decimal import ROUND_HALF_UP, Decimal

from ..assignment_guard import POLICY_DEFAULT_WEEKLY_CAP_MINUTES
from .availability import SlotAvailability
from .forecast import SalesForecast
from .history import HistoryModel
from .policy import POLICY_MIN_HISTORY_WEEKS
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
    # Weekly minutes the people qualified for each job can give (their own
    # weekly cap, bounded by when they are available). A person qualified for
    # two jobs counts toward both, so this is a ceiling per job, not a sum.
    minutes_by_job: dict[str, int] = field(default_factory=dict)


@dataclass(frozen=True)
class LaborTarget:
    day: object
    hours: Decimal
    method: str
    floor_hours: Decimal
    raw_hours: Decimal
    notes: tuple[str, ...]


def _weekly_cap_minutes(employee: dict) -> int:
    return int(
        employee.get("target_weekly_minutes") or employee.get("max_weekly_minutes")
        or POLICY_DEFAULT_WEEKLY_CAP_MINUTES
    )


def roster_capacity(roster: dict, availability: SlotAvailability) -> RosterCapacity:
    """Capacity of the people the planner can actually schedule this week.

    Only employees with confirmed availability and at least one available
    slot count, and each gives the smaller of their weekly cap and the time
    they are available inside the open windows.
    """
    by_id = {str(e.get("id")): e for e in roster.get("employees") or []}
    minutes: dict[str, int] = {}
    for employee_id in sorted(availability.minutes_by_employee):
        employee = by_id.get(employee_id) or {}
        minutes[employee_id] = min(
            _weekly_cap_minutes(employee), availability.minutes_by_employee[employee_id],
        )
    by_job: dict[str, int] = {}
    for employee_id, jobs in availability.jobs_by_employee.items():
        for job_id in jobs:
            by_job[job_id] = by_job.get(job_id, 0) + minutes.get(employee_id, 0)
    weekly = Decimal(sum(minutes.values())) / 60
    return RosterCapacity(len(minutes), weekly, availability.qualified_by_job(), by_job)


def floor_headcount(profile: dict, leader_seat: bool) -> int:
    return max(0, int(profile.get("min_floor_staff") or 0)) + (1 if leader_seat else 0)


def labor_target(
    window: DayWindow, forecast: SalesForecast, *, history: HistoryModel,
    profile: dict, blended_hourly_rate: Decimal | None, leader_seat: bool,
) -> LaborTarget:
    """Hours for one open day, most specific evidence first.

    1. sales + learned $/labor-hour, capped by the manager's labor % when one
       is set — the target is a budget, so it only ever lowers the pace;
    2. sales + labor % + a pay rate;
    3. sales index scaling the usual published hours;
    4. no sales: repeat the usual published hours for this weekday;
    5. the coverage floor.
    """
    window_hours = Decimal(window.slot_count) / 2
    floor_hours = Decimal(floor_headcount(profile, leader_seat)) * window_hours
    raw = floor_hours
    method = "floor"
    notes: list[str] = []
    weekday_name = window.day.strftime("%A")
    splh = history.splh_by_weekday.get(window.weekday) or history.splh_all
    pct = _d(profile["target_labor_pct"]) if profile.get("target_labor_pct") is not None else None
    pct_hours = (
        forecast.forecast * pct / 100 / blended_hourly_rate
        if forecast.forecast is not None and pct is not None
        and blended_hourly_rate is not None and blended_hourly_rate > 0
        else None
    )
    usual = history.hours_by_weekday.get(window.weekday)
    usual_dates = history.dates_by_weekday.get(window.weekday, 0)
    if forecast.forecast is not None and splh and splh > 0:
        pace_hours = forecast.forecast / splh
        raw = pace_hours
        method = "splh"
        notes.append(
            f"{pace_hours.quantize(Decimal('0.1'))}h from ${forecast.forecast:,.2f} at "
            f"${splh:,.2f}/labor-hour learned from published weeks"
        )
        if pct_hours is not None and pct_hours < pace_hours:
            raw = pct_hours
            method = "splh_capped"
            notes.append(
                f"{pct}% labor target caps the day at {pct_hours.quantize(Decimal('0.1'))}h "
                f"(history pace would staff {pace_hours.quantize(Decimal('0.1'))}h)"
            )
    elif pct_hours is not None:
        raw = pct_hours
        method = "labor_pct"
        notes.append(f"{pct}% labor target at ${blended_hourly_rate:,.2f}/hour")
    elif usual is not None and forecast.index is not None:
        raw = usual * forecast.index
        method = "history_hours"
        notes.append(
            f"no $/labor-hour learned — scaling usual {usual}h by sales index {forecast.index}"
        )
    elif (forecast.forecast is None and usual is not None
          and history.present() and usual_dates >= POLICY_MIN_HISTORY_WEEKS):
        raw = usual
        method = "usual_hours"
        notes.append(
            f"no sales history — repeating the usual {usual}h for {weekday_name}s "
            f"from {usual_dates} published {weekday_name}s"
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
