"""Behavioral checks for the deterministic Autopilot demand engine."""

import json
import random
from datetime import date, datetime, time, timedelta, timezone
from decimal import Decimal

import pytest

from app.matcha.services.scheduling.autopilot.curve import (
    largest_remainder,
    slot_weights,
)
from app.matcha.services.scheduling.autopilot.cutter import (
    break_minutes_for,
    cut_shifts,
)
from app.matcha.services.scheduling.autopilot.engine import generate_autopilot_demand
from app.matcha.services.scheduling.autopilot.forecast import (
    attach_index,
    forecast_day,
    weather_effect,
    weekday_baseline,
)
from app.matcha.services.scheduling.autopilot.history import learn_history
from app.matcha.services.scheduling.autopilot.policy import POLICY_MAX_DEMAND_SHIFTS
from app.matcha.services.scheduling.autopilot.windows import day_window
from app.matcha.services.scheduling.week_builder import _MAX_DEMAND_SHIFTS, build_plan

WEEK = date(2026, 9, 20)
JOB = "00000000-0000-4000-8000-000000000001"
LEAD = "00000000-0000-4000-8000-000000000002"


def _profile(**changes):
    profile = {
        "week_start_weekday": 0,
        "operating_hours": {
            str(day): {"open": "08:00", "close": "16:00"} for day in range(1, 6)
        },
        "min_floor_staff": 1,
        "weather_sensitivity": "none",
        "leader_required": False,
    }
    profile.update(changes)
    return profile


def _roster(*, count=2, jobs=None):
    return {
        "employees": [
            {
                "id": f"employee-{index}", "name": f"Employee {index}",
                "target_weekly_minutes": 2400,
                "jobs": jobs or [],
            }
            for index in range(count)
        ]
    }


def _engine(**changes):
    args = {
        "week_start": WEEK,
        "profile": _profile(),
        "jobs": [{"id": JOB, "name": "Barista"}],
        "roster": _roster(),
        "gated_job_ids": set(),
        "sales_by_day": {},
        "weather_by_day": {},
        "history_shifts": [],
    }
    args.update(changes)
    return generate_autopilot_demand(**args)


def test_windows_cover_buffers_overnight_and_closed_days():
    daytime = day_window(date(2026, 9, 21), _profile(
        operating_hours={"1": {"open": "06:45", "close": "20:45"}},
        open_buffer_minutes=30, close_buffer_minutes=60,
    ))
    assert daytime.starts_at.hour == 6 and daytime.starts_at.minute == 0
    assert daytime.ends_at.hour == 22 and daytime.ends_at.minute == 0
    assert daytime.slot_count == 32
    overnight = day_window(date(2026, 9, 21), _profile(
        operating_hours={"1": {"open": "22:00", "close": "03:30"}},
    ))
    assert overnight.ends_at.date() == date(2026, 9, 22)
    assert overnight.overnight
    assert day_window(WEEK, _profile()).closed


def test_history_needs_three_weeks_and_uses_only_imported_sales():
    rows = []
    sales = {}
    for offset in (7, 14, 21):
        day = WEEK - timedelta(days=offset)
        rows.append({
            "starts_at": datetime.combine(day, time(8), tzinfo=timezone.utc),
            "ends_at": datetime.combine(day, time(12), tzinfo=timezone.utc),
            "required_staff": 2, "break_minutes": 0, "job_id": JOB,
        })
        if offset != 14:
            sales[day] = Decimal(400)
    history = learn_history(rows, sales_by_day=sales, week_start_weekday=0)
    assert history.present()
    assert history.splh_all is None  # only two paired sales days
    assert history.hours_by_weekday[0] == Decimal("8.00")
    assert history.job_share_all[JOB] == Decimal("1.0000")


def test_baseline_uses_known_days_and_weather_policy_is_labelled():
    prior = [WEEK - timedelta(days=7 * offset) for offset in range(1, 5)]
    sales = {day: Decimal(value) for day, value in zip(prior, (100, 200, 300, 900))}
    baseline, observations, method = weekday_baseline(WEEK, sales_by_day=sales, anchor=WEEK)
    assert (baseline, observations, method) == (Decimal(250), 4, "weekday_median")
    assert weather_effect(WEEK, {WEEK: {"precip_probability": 65}}, "rain_hurts").modifier == Decimal("0.90")
    assert weather_effect(WEEK, {WEEK: {"precip_probability": 85}}, "rain_helps").modifier == Decimal("1.15")
    missing = weather_effect(WEEK, {}, "rain_hurts")
    assert missing.modifier == 1 and "unavailable" in missing.note
    forecast = forecast_day(WEEK, sales_by_day=sales, weather_by_day={}, sensitivity="none", anchor=WEEK)
    assert forecast.forecast == Decimal("250.00")
    assert forecast.confidence == "medium"


def test_sales_index_is_bounded_and_zero_is_known():
    days = [WEEK + timedelta(days=i) for i in range(3)]
    values = [Decimal(0), Decimal(100), Decimal(1000)]
    forecasts = [
        forecast_day(day, sales_by_day={day - timedelta(days=7): value},
                     weather_by_day={}, sensitivity="none", anchor=WEEK)
        for day, value in zip(days, values)
    ]
    indexed = attach_index(forecasts, set(days))
    assert indexed[0].forecast == 0
    assert indexed[0].index == Decimal("0.50")
    assert indexed[-1].index == Decimal("2.00")


def test_curve_rounding_and_preopening_history_alignment():
    assert largest_remainder([Decimal("1.4"), Decimal("1.4"), Decimal("1.2")], 4) == [2, 1, 1]
    day = date(2026, 9, 21)
    window = day_window(day, _profile(
        operating_hours={"1": {"open": "00:15", "close": "02:15"}},
        open_buffer_minutes=30,
    ))
    weights, source = slot_weights(window, shape={-1: Decimal(10), 0: Decimal(1)}, hourly_sales=None)
    assert source == "history"
    assert weights[0] > weights[1]


def test_cutter_preserves_coverage_for_random_curves():
    rng = random.Random(1701)
    for _ in range(200):
        curve = [rng.randrange(0, 5) for _ in range(rng.randrange(4, 49))]
        result = cut_shifts(curve, min_slots=8, max_slots=18)
        coverage = [0] * len(curve)
        for start, end in result.intervals:
            assert 0 <= start < end <= len(curve)
            assert 8 <= end - start <= 18 or end - start == len(curve)
            for index in range(start, end):
                coverage[index] += 1
        assert all(have >= want for have, want in zip(coverage, curve))
    assert break_minutes_for(359) == 0
    assert break_minutes_for(360) == 30


def test_short_window_has_explicit_drop_instead_of_internal_error():
    result = cut_shifts([1, 1, 1], min_slots=8, max_slots=18)
    assert result.intervals == []
    assert result.dropped == 3
    assert "sub-two-hour" in result.notes[0]


def test_golden_week_is_deterministic_and_build_plan_accepts_rows():
    first = _engine()
    second = _engine(jobs=[{"id": JOB, "name": "Barista"}])
    assert first.to_dict() == second.to_dict()
    assert len(first.demand) == 5
    assert len(first.demand_model["days"]) == 7
    assert first.demand_model["confidence"] == "none"
    assert first.demand_model["forecast_sales_week"] is None
    assert "sales_history" in first.demand_model["inputs_missing"]
    assert all(row["starts_at"].tzinfo == timezone.utc for row in first.demand)
    assert len({row["key"] for row in first.demand}) == len(first.demand)
    json.dumps(first.demand_model)
    assert POLICY_MAX_DEMAND_SHIFTS == _MAX_DEMAND_SHIFTS
    plan = build_plan(
        demand=first.demand, employees=[], availability={}, existing_assignments=[],
        unavailable_ranges={}, exclude_employee_ids=set(), employee_hour_caps={},
        gated_job_ids=set(),
    )
    assert len(plan["shifts"]) == len(first.demand)


def test_no_qualified_job_and_missing_leader_are_explained():
    gated = _engine(gated_job_ids={JOB}, roster=_roster())
    assert gated.demand == []
    assert any("no job has a qualified employee" in note for note in gated.demand_model["notes"])
    lead = _engine(
        profile=_profile(leader_required=True, leader_job_ids=[LEAD]),
        jobs=[{"id": JOB, "name": "Barista"}, {"id": LEAD, "name": "Lead"}],
        gated_job_ids={LEAD},
    )
    assert any("nobody is qualified" in note for note in lead.demand_model["notes"])
    assert all(row["job_id"] != LEAD for row in lead.demand)


def test_hourly_sales_changes_only_that_days_shape():
    monday = WEEK + timedelta(days=1)
    result = _engine(hourly_sales={(monday, 9): Decimal(200)})
    days = {item["date"]: item for item in result.demand_model["days"]}
    assert days[monday.isoformat()]["shape_source"] == "hourly_sales"
    assert days[(monday + timedelta(days=1)).isoformat()]["shape_source"] == "flat"


def test_closed_days_do_not_inflate_forecast_total():
    sales = {WEEK - timedelta(days=7): Decimal(700)}
    result = _engine(sales_by_day=sales)
    assert result.demand_model["forecast_sales_week"] == 3500.0
    assert result.demand_model["days"][0]["closed"]


@pytest.mark.parametrize("count", (0, 1, 4))
def test_capacity_and_floor_remain_bounded(count):
    result = _engine(roster=_roster(count=count))
    assert all(row["required_staff"] <= count for row in result.demand)
    assert len(result.demand) <= POLICY_MAX_DEMAND_SHIFTS
