"""Orchestrate forecast -> labor curve -> practical demand rows."""

from __future__ import annotations

import json
from collections import defaultdict
from collections.abc import Mapping, Sequence
from collections.abc import Set as AbstractSet
from dataclasses import dataclass
from datetime import date, timedelta
from decimal import Decimal

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


def _job_shares(jobs: list[dict], history: HistoryModel, weekday: int) -> dict[str, Decimal]:
    learned = history.job_share_by_weekday.get(weekday) or history.job_share_all
    values = {str(j["id"]): learned.get(str(j["id"]), Decimal(0)) for j in jobs}
    total = sum(values.values(), Decimal(0))
    if total <= 0:
        equal = Decimal(1) / len(jobs)
        return {str(j["id"]): equal for j in jobs}
    return {job: value / total for job, value in values.items()}


def _assign_jobs(intervals: list[tuple[int, int]], jobs: list[dict], shares: dict[str, Decimal]) -> list[tuple[int, int, dict]]:
    assigned: list[tuple[int, int, dict]] = []
    actual: dict[str, Decimal] = defaultdict(Decimal)
    total_slots = Decimal(sum(end - start for start, end in intervals))
    by_id = {str(job["id"]): job for job in jobs}
    for start, end in sorted(intervals, key=lambda pair: (-(pair[1] - pair[0]), pair[0], pair[1])):
        job_id = min(
            shares,
            key=lambda key: (
                actual[key] - shares[key] * total_slots,
                str(by_id[key].get("name") or "").lower(), key,
            ),
        )
        assigned.append((start, end, by_id[job_id]))
        actual[job_id] += Decimal(end - start)
    return assigned


def _qualified_leader(
    profile: Mapping, jobs: list[dict], capacity,
) -> tuple[dict | None, str | None]:
    if profile.get("leader_required") is not True:
        return None, None
    ids = [str(value) for value in (profile.get("leader_job_ids") or [])]
    if not ids and profile.get("leader_job_id"):
        ids = [str(profile["leader_job_id"])]
    options = [job for job in jobs if str(job["id"]) in ids and capacity.qualified_by_job.get(str(job["id"]), 0) > 0]
    if not options:
        names = [str(job.get("name")) for job in jobs if str(job["id"]) in ids]
        return None, f"leader required but nobody is qualified for {', '.join(names) or 'the configured leader job'} — no leader seat planned"
    return min(options, key=lambda j: (-capacity.qualified_by_job[str(j["id"])], str(j.get("name") or ""), str(j["id"]))), None


def generate_autopilot_demand(
    *, week_start: date, profile: Mapping, jobs: Sequence[Mapping], roster: Mapping,
    gated_job_ids: AbstractSet[str], sales_by_day: Mapping[date, Decimal],
    weather_by_day: Mapping[date, Mapping], history_shifts: Sequence[Mapping],
    blended_hourly_rate: Decimal | None = None,
    hourly_sales: Mapping[tuple[date, int], Decimal] | None = None,
    anchor: date | None = None,
) -> AutopilotResult:
    profile = dict(profile or {})
    jobs = sorted((dict(job) for job in jobs), key=lambda j: (str(j.get("name") or ""), str(j.get("id"))))
    roster = dict(roster or {})
    sales = {day: Decimal(str(value)) for day, value in sales_by_day.items()}
    weather = {day: dict(value) for day, value in weather_by_day.items()}
    anchor = anchor or week_start
    minimum, maximum, week_notes = _shift_bounds(profile)
    history = learn_history(
        [dict(row) for row in history_shifts], sales_by_day=sales,
        week_start_weekday=int(profile.get("week_start_weekday") or 0),
    )
    capacity = roster_capacity(roster, jobs, {str(v) for v in gated_job_ids})
    leader_job, leader_note = _qualified_leader(profile, jobs, capacity)
    if leader_note:
        week_notes.append(leader_note)
    eligible = [
        job for job in jobs
        if capacity.qualified_by_job.get(str(job["id"]), 0) > 0
        and (not leader_job or str(job["id"]) != str(leader_job["id"]))
    ]
    windows = [day_window(week_start.fromordinal(week_start.toordinal() + index), profile) for index in range(7)]
    forecasts = [
        forecast_day(
            window.day, sales_by_day=sales, weather_by_day=weather,
            sensitivity=str(profile.get("weather_sensitivity") or "none"), anchor=anchor,
        )
        for window in windows
    ]
    forecasts = attach_index(forecasts, {window.day for window in windows if not window.closed})
    targets = [
        labor_target(
            window, forecast, history=history, profile=profile,
            blended_hourly_rate=blended_hourly_rate,
            leader_seat=bool(leader_job),
        )
        for window, forecast in zip(windows, forecasts) if not window.closed
    ]
    targets, capacity_note = cap_week_to_capacity(targets, capacity)
    if capacity_note:
        week_notes.append(capacity_note)
    targets_by_day = {target.day: target for target in targets}

    rows: list[dict] = []
    days: list[dict] = []
    if not eligible:
        week_notes.append("no job has a qualified employee — nothing to plan")
    for window, forecast in zip(windows, forecasts):
        notes = list(forecast.notes)
        if window.note:
            notes.append(window.note)
        day_rows: list[dict] = []
        curve = None
        target = targets_by_day.get(window.day)
        if not window.closed and target and eligible and window.slot_count:
            curve = build_curve(
                window, target,
                min_floor=max(0, int(profile.get("min_floor_staff") or 0)),
                leader_seat=bool(leader_job), shape=history.shape_for(window.weekday),
                hourly_sales=dict(hourly_sales or {}), max_headcount=capacity.employees,
            )
            notes.extend(target.notes)
            notes.extend(curve.notes)
            staff_cut = cut_shifts(
                curve.staff,
                min_slots=max(1, minimum // POLICY_SLOT_MINUTES),
                max_slots=max(1, maximum // POLICY_SLOT_MINUTES),
            )
            notes.extend(staff_cut.notes)
            assignments = _assign_jobs(
                staff_cut.intervals, eligible, _job_shares(eligible, history, window.weekday),
            )
            if leader_job:
                leader_cut = cut_shifts(
                    curve.leader,
                    min_slots=max(1, minimum // POLICY_SLOT_MINUTES),
                    max_slots=max(1, maximum // POLICY_SLOT_MINUTES),
                )
                notes.extend(leader_cut.notes)
                assignments.extend((a, b, leader_job) for a, b in leader_cut.intervals)
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
    for name, present in (
        ("sales_history", bool(sales)), ("weather", bool(weather)),
        ("published_history", history.present()),
        ("hourly_sales", bool(hourly_sales)),
        ("blended_hourly_rate", blended_hourly_rate is not None),
        ("target_labor_pct", profile.get("target_labor_pct") is not None),
    ):
        (inputs_used if present else inputs_missing).append(name)
    sales_weeks = len({
        day - timedelta(days=day.weekday()) for day in sales
        if day < anchor
    })
    sentence = (
        (f"Forecast ${forecast_total:,.0f} for the week from {sales_weeks} week(s) of sales "
         f"({confidence} confidence); " if forecast_total is not None else "No sales forecast was available; ")
        + f"{planned_hours.quantize(Decimal('0.1'))} labor hours planned."
    )
    demand_model = {
        "week_start": week_start.isoformat(), "days": days,
        "forecast_sales_week": _json_number(forecast_total),
        "labor_hours_week": _json_number(planned_hours),
        "labor_hours_target_week": _json_number(target_hours),
        "confidence": confidence, "inputs_used": inputs_used,
        "inputs_missing": inputs_missing,
        "capacity": {"employees": capacity.employees, "weekly_hours": _json_number(capacity.weekly_hours)},
        "policy": {
            "min_shift_minutes": minimum, "max_shift_minutes": maximum,
            "slot_minutes": POLICY_SLOT_MINUTES,
            "floor_staff": int(profile.get("min_floor_staff") or 0),
            "leader_seat": bool(leader_job), "weather": profile.get("weather_sensitivity") or "none",
            "break_placeholder_minutes": POLICY_DEFAULT_BREAK_MINUTES,
            "break_threshold_minutes": POLICY_BREAK_THRESHOLD_MINUTES,
            "index_bounds": [float(POLICY_INDEX_MIN), float(POLICY_INDEX_MAX)],
        },
        "notes": week_notes, "sentence": sentence,
    }
    json.dumps(demand_model)
    return AutopilotResult(rows, demand_model)
