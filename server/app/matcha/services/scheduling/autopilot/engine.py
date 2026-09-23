"""Orchestrate forecast -> labor curve -> practical demand rows."""

from __future__ import annotations

import json
from collections import defaultdict
from collections.abc import Mapping, Sequence
from collections.abc import Set as AbstractSet
from dataclasses import dataclass
from datetime import date, timedelta
from decimal import Decimal

from .availability import slot_availability
from .curve import build_curve
from .cutter import break_minutes_for, cut_shifts
from .forecast import attach_index, forecast_day, week_confidence
from .history import HistoryModel, learn_history
from .labor import cap_week_to_capacity, labor_target, roster_capacity
from .policy import (
    POLICY_BREAK_THRESHOLD_MINUTES,
    POLICY_DEFAULT_BREAK_MINUTES,
    POLICY_INDEX_MAX,
    POLICY_INDEX_MIN,
    POLICY_MAX_DEMAND_SHIFTS,
    POLICY_MAX_SHIFT_MINUTES,
    POLICY_MIN_SHIFT_MINUTES,
    POLICY_SHIFT_MINUTES_BOUNDS,
    POLICY_SLOT_MINUTES,
)
from .windows import day_window, slot_start


def _json_number(value: Decimal | None) -> float | None:
    return float(value.quantize(Decimal("0.01"))) if value is not None else None


@dataclass(frozen=True)
class AutopilotResult:
    demand: list[dict]
    demand_model: dict

    def to_dict(self) -> dict:
        return {"demand": self.demand, "demand_model": self.demand_model}


def _shift_bounds(profile: Mapping) -> tuple[int, int, list[str]]:
    low, high = POLICY_SHIFT_MINUTES_BOUNDS
    minimum = int(profile.get("autopilot_shift_min_minutes") or POLICY_MIN_SHIFT_MINUTES)
    maximum = int(profile.get("autopilot_shift_max_minutes") or POLICY_MAX_SHIFT_MINUTES)
    minimum, maximum = max(low, min(high, minimum)), max(low, min(high, maximum))
    notes: list[str] = []
    if minimum > maximum:
        minimum, maximum = POLICY_MIN_SHIFT_MINUTES, POLICY_MAX_SHIFT_MINUTES
        notes.append("invalid shift-length overrides were replaced with the Autopilot defaults")
    return minimum, maximum, notes


def _job_shares(
    jobs: list[dict], history: HistoryModel, weekday: int, qualified_by_job: Mapping[str, int],
) -> dict[str, Decimal]:
    learned = history.job_share_by_weekday.get(weekday) or history.job_share_all
    values = {str(j["id"]): learned.get(str(j["id"]), Decimal(0)) for j in jobs}
    total = sum(values.values(), Decimal(0))
    if total <= 0:
        # No learned mix: weight by who can actually work each job, so a job
        # with one qualified person is not handed as many seats as one with
        # ten (every one of them would come back unfilled).
        values = {str(j["id"]): Decimal(max(0, qualified_by_job.get(str(j["id"]), 0))) for j in jobs}
        total = sum(values.values(), Decimal(0))
        if total <= 0:
            equal = Decimal(1) / len(jobs)
            return {str(j["id"]): equal for j in jobs}
    return {job: value / total for job, value in values.items()}


def _assign_jobs(
    intervals: list[tuple[int, int]], jobs: list[dict], shares: dict[str, Decimal], *,
    slot_capacity: Mapping[str, Sequence[int]], minutes_left: dict[str, int],
    balance: dict[str, Decimal] | None = None,
) -> tuple[list[tuple[int, int, dict]], dict[str, int]]:
    """Hand each cut interval to a job, keeping the mix near `shares`.

    A job only takes an interval while it has a qualified, available person
    for every slot of it (`slot_capacity`) and weekly minutes left among its
    qualified people (`minutes_left`, shared across the week's days and
    decremented here). With no job able to take it, the interval goes to the
    job with the most headroom and is counted in the returned overflow — a
    seat the planner will report unfilled, said up front instead of hidden.

    `balance` carries slots already given out on earlier days, so a mix is
    kept across the WEEK — leader seats are one interval a day, and a per-day
    mix would hand every one of them to the same job.
    """
    assigned: list[tuple[int, int, dict]] = []
    actual: dict[str, Decimal] = balance if balance is not None else {}
    used: dict[str, dict[int, int]] = defaultdict(lambda: defaultdict(int))
    overflow: dict[str, int] = defaultdict(int)
    total_slots = sum(actual.values(), Decimal(0)) + Decimal(sum(end - start for start, end in intervals))
    by_id = {str(job["id"]): job for job in jobs}

    def headroom(key: str, start: int, end: int) -> int:
        capacity = slot_capacity.get(key) or []
        return min(
            (capacity[i] if i < len(capacity) else 0) - used[key][i] for i in range(start, end)
        )

    def deficit(key: str) -> tuple:
        return (
            actual.get(key, Decimal(0)) - shares[key] * total_slots,
            str(by_id[key].get("name") or "").lower(), key,
        )

    for start, end in sorted(intervals, key=lambda pair: (-(pair[1] - pair[0]), pair[0], pair[1])):
        minutes = (end - start) * POLICY_SLOT_MINUTES
        fits = [
            key for key in shares
            if headroom(key, start, end) > 0 and minutes_left.get(key, 0) >= minutes
        ]
        if fits:
            job_id = min(fits, key=deficit)
        else:
            job_id = min(shares, key=lambda key: (-headroom(key, start, end), *deficit(key)))
            overflow[job_id] += 1
        assigned.append((start, end, by_id[job_id]))
        actual[job_id] = actual.get(job_id, Decimal(0)) + Decimal(end - start)
        minutes_left[job_id] = minutes_left.get(job_id, 0) - minutes
        for index in range(start, end):
            used[job_id][index] += 1
    return assigned, dict(overflow)


def _configured_leader_ids(profile: Mapping) -> set[str]:
    ids = {str(value) for value in (profile.get("leader_job_ids") or [])}
    if not ids and profile.get("leader_job_id"):
        ids = {str(profile["leader_job_id"])}
    return ids


def _leader_jobs(
    profile: Mapping, jobs: list[dict], capacity, gated_job_ids: AbstractSet[str],
) -> tuple[list[dict], list[str]]:
    """Every configured leader job someone can work, gated ones first.

    Leader seats are spread across all of them (the rule is "any ONE of these
    jobs on shift"), so one General Manager is not handed every leader seat of
    the week. A leader job with no qualified list is open to the whole roster;
    it is used only when no gated leader job has anyone, and said so — it used
    to win outright because "everyone" outnumbers any real qualified list.
    """
    if profile.get("leader_required") is not True:
        return [], []
    ids = _configured_leader_ids(profile)
    options = [job for job in jobs if str(job["id"]) in ids and capacity.qualified_by_job.get(str(job["id"]), 0) > 0]
    if not options:
        names = [str(job.get("name")) for job in jobs if str(job["id"]) in ids]
        return [], [f"leader required but nobody is qualified for {', '.join(names) or 'the configured leader job'} — no leader seat planned"]
    gated = [job for job in options if str(job["id"]) in gated_job_ids]
    if gated:
        return gated, []
    names = [str(job.get("name") or "the leader job") for job in options]
    verb = "has" if len(names) == 1 else "have"
    return options, [(
        f"{' and '.join(names)} {verb} no qualified list, so anyone can fill the leader seat — "
        "name the qualified leaders in Jobs"
    )]


def _overflow_notes(overflow: Mapping[str, int], jobs: list[dict]) -> list[str]:
    names = {str(job["id"]): str(job.get("name") or "Shift") for job in jobs}
    return [
        f"{count} shift{'s' if count != 1 else ''} exceed{'' if count != 1 else 's'} the staff "
        f"qualified and available for {names.get(job_id, 'a job')}"
        for job_id, count in sorted(overflow.items(), key=lambda item: names.get(item[0], ""))
    ]


def generate_autopilot_demand(
    *, week_start: date, profile: Mapping, jobs: Sequence[Mapping], roster: Mapping,
    gated_job_ids: AbstractSet[str], sales_by_day: Mapping[date, Decimal],
    weather_by_day: Mapping[date, Mapping], history_shifts: Sequence[Mapping],
    blended_hourly_rate: Decimal | None = None,
    hourly_profile: Mapping[int, Mapping[int, Decimal]] | None = None,
    holidays: Mapping[date, str] | None = None,
    anchor: date | None = None,
) -> AutopilotResult:
    profile = dict(profile or {})
    jobs = sorted((dict(job) for job in jobs), key=lambda j: (str(j.get("name") or ""), str(j.get("id"))))
    roster = dict(roster or {})
    sales = {day: Decimal(str(value)) for day, value in sales_by_day.items()}
    weather = {day: dict(value) for day, value in weather_by_day.items()}
    anchor = anchor or week_start
    holiday_names = {day: str(name) for day, name in (holidays or {}).items()}
    excluded = frozenset(holiday_names)
    sensitivity = str(profile.get("weather_sensitivity") or "none")
    minimum, maximum, week_notes = _shift_bounds(profile)
    history = learn_history(
        [dict(row) for row in history_shifts], sales_by_day=sales,
        week_start_weekday=int(profile.get("week_start_weekday") or 0),
        exclude_dates=excluded,
    )
    windows = [day_window(week_start.fromordinal(week_start.toordinal() + index), profile) for index in range(7)]
    gated = {str(v) for v in gated_job_ids}
    availability = slot_availability(windows, roster, [str(job["id"]) for job in jobs], gated)
    capacity = roster_capacity(roster, availability)
    # Nobody schedulable is ONE fact; the leader, capacity and job notes it
    # would otherwise trigger all restate it less clearly.
    nobody_available = bool(roster.get("employees")) and capacity.employees == 0
    leader_jobs, leader_notes = _leader_jobs(profile, jobs, capacity, gated)
    if not nobody_available:
        week_notes.extend(leader_notes)
    leader_ids = _configured_leader_ids(profile) if leader_jobs else set()
    staffable = [job for job in jobs if capacity.qualified_by_job.get(str(job["id"]), 0) > 0]
    # Every configured leader job carries the leader seat, never crew seats —
    # an unused open leader job ("anyone can be Assistant Manager") would
    # otherwise soak up the crew mix. Unless they are the only jobs anyone
    # can work, in which case they are the crew too.
    eligible = [job for job in staffable if str(job["id"]) not in leader_ids] or staffable
    forecasts = [
        forecast_day(
            window.day, sales_by_day=sales, weather_by_day=weather,
            sensitivity=sensitivity, anchor=anchor, exclude_dates=excluded,
        )
        for window in windows
    ]
    forecasts = attach_index(forecasts, {window.day for window in windows if not window.closed})
    targets = [
        labor_target(
            window, forecast, history=history, profile=profile,
            blended_hourly_rate=blended_hourly_rate,
            leader_seat=bool(leader_jobs),
        )
        for window, forecast in zip(windows, forecasts) if not window.closed
    ]
    targets, capacity_note = cap_week_to_capacity(targets, capacity)
    if capacity_note and not nobody_available:
        week_notes.append(capacity_note)
    targets_by_day = {target.day: target for target in targets}
    # Shared across the week so a job's qualified people are not promised
    # the same hours on every day.
    minutes_left = dict(capacity.minutes_by_job)
    overflow: dict[str, int] = defaultdict(int)
    leader_shares = {
        str(job["id"]): Decimal(capacity.qualified_by_job[str(job["id"])]) for job in leader_jobs
    }
    leader_total = sum(leader_shares.values(), Decimal(0))
    leader_shares = {key: value / leader_total for key, value in leader_shares.items()} if leader_total else {}
    leader_balance: dict[str, Decimal] = {}

    rows: list[dict] = []
    days: list[dict] = []
    if nobody_available:
        week_notes.append(
            "nobody at this location has confirmed availability or is free this week — nothing to plan"
        )
    elif not eligible:
        week_notes.append("no job has a qualified employee — nothing to plan")
    for window, forecast in zip(windows, forecasts):
        notes = list(forecast.notes)
        if window.day in holiday_names and not window.closed:
            notes.append(
                f"{holiday_names[window.day]} — past holidays are left out of the forecast, so this "
                f"plans an ordinary {window.day.strftime('%A')}; set holiday staffing by hand"
            )
        if window.note:
            notes.append(window.note)
        day_rows: list[dict] = []
        curve = None
        target = targets_by_day.get(window.day)
        if not window.closed and target and eligible and window.slot_count:
            curve = build_curve(
                window, target,
                min_floor=max(0, int(profile.get("min_floor_staff") or 0)),
                leader_seat=bool(leader_jobs), shape=history.shape_for(window.weekday),
                hourly_profile=hourly_profile,
                max_by_slot=availability.by_day.get(window.day, []),
            )
            notes.extend(target.notes)
            notes.extend(curve.notes)
            staff_cut = cut_shifts(
                curve.staff,
                min_slots=max(1, minimum // POLICY_SLOT_MINUTES),
                max_slots=max(1, maximum // POLICY_SLOT_MINUTES),
            )
            notes.extend(staff_cut.notes)
            slot_capacity = {
                job_id: days_available.get(window.day, [])
                for job_id, days_available in availability.by_job_day.items()
            }
            assignments, day_overflow = _assign_jobs(
                staff_cut.intervals, eligible,
                _job_shares(eligible, history, window.weekday, capacity.qualified_by_job),
                slot_capacity=slot_capacity, minutes_left=minutes_left,
            )
            if leader_jobs:
                leader_cut = cut_shifts(
                    curve.leader,
                    min_slots=max(1, minimum // POLICY_SLOT_MINUTES),
                    max_slots=max(1, maximum // POLICY_SLOT_MINUTES),
                )
                notes.extend(leader_cut.notes)
                leader_assignments, leader_overflow = _assign_jobs(
                    leader_cut.intervals, leader_jobs, leader_shares,
                    slot_capacity=slot_capacity, minutes_left=minutes_left,
                    balance=leader_balance,
                )
                assignments.extend(leader_assignments)
                for job_id, count in leader_overflow.items():
                    day_overflow[job_id] = day_overflow.get(job_id, 0) + count
            for job_id, count in day_overflow.items():
                overflow[job_id] += count
            notes.extend(_overflow_notes(day_overflow, jobs))
            merged: dict[tuple, int] = defaultdict(int)
            for start_index, end_index, job in assignments:
                merged[(start_index, end_index, str(job["id"]), str(job.get("name") or "Shift"))] += 1
            for sequence, ((start_index, end_index, job_id, job_name), seats) in enumerate(sorted(merged.items()), 1):
                starts_at, ends_at = slot_start(window, start_index), slot_start(window, end_index)
                span = int((ends_at - starts_at).total_seconds() // 60)
                break_minutes = break_minutes_for(span)
                day_rows.append({
                    "key": f"autopilot:{window.day.isoformat()}:{job_id}:{sequence}",
                    "source_shift_id": None, "role": job_name, "department": None,
                    "starts_at": starts_at, "ends_at": ends_at,
                    "break_minutes": break_minutes, "required_staff": seats,
                    "color": None, "notes": f"Autopilot — {target.method}", "kind": "work",
                    "template_id": None, "job_id": job_id, "training_requirement_id": None,
                    "fixed_employee_ids": [], "worked_minutes": max(0, span - break_minutes),
                })
            rows.extend(day_rows)
        days.append({
            "date": window.day.isoformat(), "weekday": window.day.strftime("%A"),
            "open": window.open, "close": window.close,
            "window_with_buffers": (
                f"{window.starts_at.strftime('%H:%M')}–{window.ends_at.strftime('%H:%M')}"
                + ("(+1)" if window.ends_at and window.ends_at.date() > window.day else "")
                if window.starts_at and window.ends_at else None
            ),
            "closed": window.closed,
            "forecast_sales": _json_number(forecast.forecast),
            "baseline_sales": _json_number(forecast.baseline),
            "sales_index": _json_number(forecast.index),
            "weather": {
                "condition": forecast.weather.condition,
                "precip_probability": forecast.weather.precip_probability,
                "modifier": float(forecast.weather.modifier),
                "sensitivity": forecast.weather.sensitivity,
            },
            "labor_hours_target": _json_number(target.hours if target else None),
            "labor_hours_planned": _json_number(curve.planned_hours if curve else Decimal(0)),
            "labor_method": target.method if target else None,
            "shape_source": curve.shape_source if curve else None,
            "staffing_curve": curve.runs() if curve else [],
            "shifts_count": len(day_rows), "notes": notes,
        })

    if len(rows) > POLICY_MAX_DEMAND_SHIFTS:
        ranked = sorted(
            rows,
            key=lambda row: (
                row["required_staff"] * row["worked_minutes"],
                -row["starts_at"].toordinal() if hasattr(row["starts_at"], "toordinal") else 0,
                row["starts_at"], row["key"],
            ),
        )
        dropped = {row["key"] for row in ranked[:len(rows) - POLICY_MAX_DEMAND_SHIFTS]}
        rows = [row for row in rows if row["key"] not in dropped]
        week_notes.append(f"the 200-shift safety cap removed {len(dropped)} smallest shifts")
    rows.sort(key=lambda row: (row["starts_at"], row["ends_at"], row["role"], row["job_id"]))
    # Per-day figures come from the FINAL rows (net of breaks, after the
    # safety cap), the same basis as `labor_hours_week`, so the review's day
    # table sums to its week line. The key carries the business date: an
    # early open buffer can start a row on the previous calendar day.
    rows_by_day: dict[str, list[dict]] = defaultdict(list)
    for row in rows:
        rows_by_day[row["key"].split(":")[1]].append(row)
    for block in days:
        final = rows_by_day.get(block["date"], [])
        block["shifts_count"] = len(final)
        block["labor_hours_planned"] = _json_number(sum(
            (Decimal(row["required_staff"] * row["worked_minutes"]) / 60 for row in final), Decimal(0),
        ))
    open_dates = {window.day for window in windows if not window.closed}
    forecast_total_values = [
        f.forecast for f in forecasts if f.day in open_dates and f.forecast is not None
    ]
    forecast_total = sum(forecast_total_values, Decimal(0)) if forecast_total_values else None
    planned_hours = sum(
        (Decimal(row["required_staff"] * row["worked_minutes"]) / 60 for row in rows), Decimal(0),
    )
    target_hours = sum((target.hours for target in targets), Decimal(0))
    confidence = week_confidence(forecasts, {window.day for window in windows if not window.closed})
    inputs_used = ["operating_hours", "roster"]
    inputs_missing: list[str] = []
    # Only inputs that could have changed THIS plan are reported: weather for a
    # store that is not weather-sensitive, or a labor target with no sales to
    # apply it to, is not "missing" — listing it sent managers chasing it.
    checks: list[tuple[str, bool]] = [
        ("sales_history", bool(sales)), ("published_history", history.present()),
    ]
    if sensitivity in ("rain_hurts", "rain_helps"):
        checks.append(("weather", bool(weather)))
    if forecast_total_values:
        checks.extend((
            ("blended_hourly_rate", blended_hourly_rate is not None),
            ("target_labor_pct", profile.get("target_labor_pct") is not None),
        ))
    if hourly_profile:
        checks.append(("hourly_sales", True))
    for name, present in checks:
        (inputs_used if present else inputs_missing).append(name)
    # Counted in days, the unit readiness reports: a Wednesday-to-Tuesday
    # fortnight touches three calendar weeks but is two weeks of sales.
    sales_days = sum(1 for day in sales if day < anchor)
    sentence = (
        (f"Forecast ${forecast_total:,.0f} for the week from {sales_days} day{'s' if sales_days != 1 else ''} "
         f"of sales ({confidence} confidence); " if forecast_total is not None else "No sales forecast was available; ")
        + f"{planned_hours.quantize(Decimal('0.1'))} labor hours planned."
    )
    demand_model = {
        "week_start": week_start.isoformat(), "days": days,
        "forecast_sales_week": _json_number(forecast_total),
        "labor_hours_week": _json_number(planned_hours),
        "labor_hours_target_week": _json_number(target_hours),
        "confidence": confidence, "inputs_used": inputs_used,
        "inputs_missing": inputs_missing,
        "capacity": {
            "employees": capacity.employees, "weekly_hours": _json_number(capacity.weekly_hours),
            "shifts_beyond_qualified_staff": sum(overflow.values()),
        },
        "holidays": [
            {"date": day.isoformat(), "name": name}
            for day, name in holiday_names.items() if week_start <= day < week_start + timedelta(days=7)
        ],
        "policy": {
            "min_shift_minutes": minimum, "max_shift_minutes": maximum,
            "slot_minutes": POLICY_SLOT_MINUTES,
            "floor_staff": int(profile.get("min_floor_staff") or 0),
            "leader_seat": bool(leader_jobs),
            "leader_jobs": [str(job.get("name") or "") for job in leader_jobs],
            "weather": sensitivity,
            "break_placeholder_minutes": POLICY_DEFAULT_BREAK_MINUTES,
            "break_threshold_minutes": POLICY_BREAK_THRESHOLD_MINUTES,
            "index_bounds": [float(POLICY_INDEX_MIN), float(POLICY_INDEX_MAX)],
        },
        "notes": week_notes, "sentence": sentence,
    }
    json.dumps(demand_model)
    return AutopilotResult(rows, demand_model)
