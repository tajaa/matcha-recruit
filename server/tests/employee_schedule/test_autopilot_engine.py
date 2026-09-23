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
    weights, source = slot_weights(window, shape={-1: Decimal(10), 0: Decimal(1)}, hourly_profile=None)
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


def test_hourly_profile_changes_only_that_weekdays_shape():
    monday = WEEK + timedelta(days=1)
    # Keyed by weekday (Sunday=0), learned from past weeks: a profile keyed
    # by the target week's own dates could never have been filled.
    result = _engine(hourly_profile={1: {9: Decimal("0.4"), 10: Decimal("0.6")}})
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


def _history_model(**changes):
    from app.matcha.services.scheduling.autopilot.history import HistoryModel

    fields = {
        "weeks_observed": 0, "dates_by_weekday": {}, "shape_by_weekday": {},
        "hours_by_weekday": {}, "job_share_by_weekday": {}, "job_share_all": {},
        "splh_by_weekday": {}, "splh_all": None,
    }
    fields.update(changes)
    return HistoryModel(**fields)


def test_weather_note_only_when_the_store_is_weather_sensitive():
    assert weather_effect(WEEK, {}, "none").note is None
    assert "unavailable" in weather_effect(WEEK, {}, "rain_helps").note
    result = _engine()
    assert not any("weather unavailable" in note for day in result.demand_model["days"] for note in day["notes"])


def test_labor_ladder_and_floor_note_only_when_floor_binds():
    from dataclasses import replace

    from app.matcha.services.scheduling.autopilot.labor import labor_target

    monday = WEEK + timedelta(days=1)
    window = day_window(monday, _profile())            # 08:00-16:00 = 8h floor at 1 staff
    base = forecast_day(monday, sales_by_day={}, weather_by_day={}, sensitivity="none", anchor=WEEK)
    history = _history_model(splh_all=Decimal(100))

    # 10.3h rounds to 10.5h: rounding is not the floor raising it.
    above = labor_target(window, replace(base, forecast=Decimal(1030)), history=history,
                         profile=_profile(), blended_hourly_rate=None, leader_seat=False)
    assert (above.method, above.hours) == ("splh", Decimal("10.5"))
    assert not any("coverage floor raised" in note for note in above.notes)

    below = labor_target(window, replace(base, forecast=Decimal(500)), history=history,
                         profile=_profile(), blended_hourly_rate=None, leader_seat=False)
    assert below.hours == Decimal("8.0")
    assert any("coverage floor raised" in note for note in below.notes)

    pct = labor_target(window, replace(base, forecast=Decimal(5000)), history=_history_model(),
                       profile=_profile(target_labor_pct=Decimal(28)),
                       blended_hourly_rate=Decimal(20), leader_seat=False)
    assert (pct.method, pct.hours) == ("labor_pct", Decimal("70.0"))

    scaled = labor_target(window, replace(base, forecast=Decimal(10), index=Decimal("1.50")),
                          history=_history_model(hours_by_weekday={1: Decimal(16)}),
                          profile=_profile(), blended_hourly_rate=None, leader_seat=False)
    assert (scaled.method, scaled.hours) == ("history_hours", Decimal("24.0"))


def test_capacity_cap_scales_only_above_the_floor():
    from app.matcha.services.scheduling.autopilot.labor import (
        LaborTarget,
        RosterCapacity,
        cap_week_to_capacity,
    )

    targets = [LaborTarget(WEEK, Decimal(20), "splh", Decimal(8), Decimal(20), ())] * 2
    capped, note = cap_week_to_capacity(targets, RosterCapacity(1, Decimal(28), {}))
    assert [target.hours for target in capped] == [Decimal(14), Decimal(14)]
    assert "caps the plan at 28" in note
    floored, note = cap_week_to_capacity(
        [LaborTarget(WEEK, Decimal(8), "floor", Decimal(8), Decimal(8), ())] * 2,
        RosterCapacity(1, Decimal(10), {}),
    )
    assert [target.hours for target in floored] == [Decimal(8), Decimal(8)]
    assert "below the 16" in note


def test_job_mix_without_history_follows_qualified_headcount():
    from app.matcha.services.scheduling.autopilot.engine import _job_shares

    other = "00000000-0000-4000-8000-000000000003"
    jobs = [{"id": JOB, "name": "Barista"}, {"id": other, "name": "Cashier"}]
    shares = _job_shares(jobs, _history_model(), 1, {JOB: 3, other: 1})
    assert shares == {JOB: Decimal("0.75"), other: Decimal("0.25")}
    assert _job_shares(jobs, _history_model(), 1, {}) == {JOB: Decimal("0.5"), other: Decimal("0.5")}

    roster = _roster(count=4)
    for index, employee in enumerate(roster["employees"]):
        employee["jobs"] = [{"job_id": JOB if index < 3 else other, "qualification_status": "active"}]
    result = _engine(
        profile=_profile(min_floor_staff=4), jobs=jobs, roster=roster, gated_job_ids={JOB, other},
    )
    seats = {JOB: 0, other: 0}
    for row in result.demand:
        seats[row["job_id"]] += row["required_staff"] * row["worked_minutes"]
    assert seats[JOB] > seats[other] > 0


def test_day_table_sums_to_the_week_line_after_breaks_and_cap():
    long_days = _profile(operating_hours={str(day): {"open": "06:00", "close": "22:00"} for day in range(7)},
                         min_floor_staff=3)
    result = _engine(profile=long_days, roster=_roster(count=6))
    days = result.demand_model["days"]
    assert sum(day["shifts_count"] for day in days) == len(result.demand)
    assert sum(day["labor_hours_planned"] for day in days) == pytest.approx(result.demand_model["labor_hours_week"])
    assert any(row["break_minutes"] for row in result.demand)

    jobs = [{"id": f"00000000-0000-4000-8000-00000000001{i}", "name": f"Job{i}"} for i in range(6)]
    rng = random.Random(3)
    hourly = {d: {h: Decimal(rng.randrange(1, 50)) for h in range(24)} for d in range(7)}
    capped = _engine(
        profile=_profile(operating_hours={str(d): {"open": "00:00", "close": "00:00"} for d in range(7)},
                         min_floor_staff=12, autopilot_shift_min_minutes=120, autopilot_shift_max_minutes=180),
        jobs=jobs, roster=_roster(count=60), hourly_profile=hourly,
    )
    assert len(capped.demand) == POLICY_MAX_DEMAND_SHIFTS
    assert any("safety cap removed" in note for note in capped.demand_model["notes"])
    assert sum(day["shifts_count"] for day in capped.demand_model["days"]) == POLICY_MAX_DEMAND_SHIFTS


def test_leader_seat_invalid_bounds_and_roster_clip_are_explained():
    roster = _roster(count=2, jobs=[{"job_id": LEAD, "qualification_status": "active"}])
    result = _engine(
        profile=_profile(leader_required=True, leader_job_ids=[LEAD], min_floor_staff=4,
                         autopilot_shift_min_minutes=600, autopilot_shift_max_minutes=300),
        jobs=[{"id": JOB, "name": "Barista"}, {"id": LEAD, "name": "Lead"}],
        roster=roster, gated_job_ids={LEAD},
    )
    assert result.demand_model["policy"]["leader_seat"] is True
    assert any(row["job_id"] == LEAD for row in result.demand)
    assert any("invalid shift-length overrides" in note for note in result.demand_model["notes"])
    assert any("clipped to the staff available" in note
               for day in result.demand_model["days"] for note in day["notes"])


def test_cutter_overlap_and_staggered_layers():
    overlap = cut_shifts([1] * 20, min_slots=11, max_slots=12)
    assert overlap.over_coverage > 0 and "add" in overlap.notes[0]
    staggered = cut_shifts([2] * 37, min_slots=8, max_slots=18)
    first_layer = staggered.intervals[:3]
    second_layer = staggered.intervals[3:]
    assert [b - a for a, b in first_layer] == [13, 12, 12]
    assert [b - a for a, b in second_layer] == [12, 12, 13]


# ── Review fixes (2026-09-22) ─────────────────────────────────────────────


def _row(day, start_hour, end_hour, seats=1, job=JOB):
    return {
        "starts_at": datetime.combine(day, time(start_hour), tzinfo=timezone.utc),
        "ends_at": datetime.combine(day, time(end_hour), tzinfo=timezone.utc),
        "required_staff": seats, "break_minutes": 0, "job_id": job,
    }


def test_shape_averages_over_every_observed_day_not_only_staffed_ones():
    mondays = [WEEK + timedelta(days=1) - timedelta(days=7 * n) for n in range(1, 5)]
    rows = [_row(day, 8, 16) for day in mondays]
    # One Monday had a 10-person event night; the other three had nobody then.
    rows.append(_row(mondays[0], 18, 22, seats=10))
    history = learn_history(rows, sales_by_day={}, week_start_weekday=0)
    assert history.shape_by_weekday[1][36] == Decimal("2.5000")      # 18:00: 10 people / 4 Mondays
    assert history.shape_by_weekday[1][16] == Decimal("1.0000")      # 08:00: staffed every Monday


def test_history_skips_excluded_holiday_dates():
    mondays = [WEEK + timedelta(days=1) - timedelta(days=7 * n) for n in range(1, 5)]
    rows = [_row(day, 8, 16) for day in mondays] + [_row(mondays[0], 16, 22, seats=6)]
    history = learn_history(
        rows, sales_by_day={}, week_start_weekday=0, exclude_dates=frozenset({mondays[0]}),
    )
    assert history.dates_by_weekday[1] == 3
    assert 40 not in history.shape_by_weekday[1]


def _labor(forecast_value, *, history, profile=None, rate=None, index=None):
    from dataclasses import replace

    from app.matcha.services.scheduling.autopilot.labor import labor_target

    monday = WEEK + timedelta(days=1)
    window = day_window(monday, _profile())
    base = forecast_day(monday, sales_by_day={}, weather_by_day={}, sensitivity="none", anchor=WEEK)
    forecast = replace(base, forecast=forecast_value, index=index)
    return labor_target(window, forecast, history=history, profile=profile or _profile(),
                        blended_hourly_rate=rate, leader_seat=False)


def test_labor_target_is_a_ceiling_on_the_learned_pace():
    history = _history_model(splh_all=Decimal(100))
    # Pace says 30h; 28% of $3,000 at $20/h is 42h — the target doesn't bind.
    loose = _labor(Decimal(3000), history=history, profile=_profile(target_labor_pct=Decimal(28)),
                   rate=Decimal(20))
    assert (loose.method, loose.hours) == ("splh", Decimal("30.0"))
    # At 10% the budget is 15h: it caps the pace, and says by how much.
    tight = _labor(Decimal(3000), history=history, profile=_profile(target_labor_pct=Decimal(10)),
                   rate=Decimal(20))
    assert (tight.method, tight.hours) == ("splh_capped", Decimal("15.0"))
    assert any("10% labor target caps the day at 15.0h (history pace would staff 30.0h)" in note
               for note in tight.notes)


def test_no_sales_repeats_the_usual_published_hours():
    history = _history_model(
        weeks_observed=4, dates_by_weekday={1: 4}, hours_by_weekday={1: Decimal("20.00")},
    )
    usual = _labor(None, history=history)
    assert (usual.method, usual.hours) == ("usual_hours", Decimal("20.0"))
    assert any("repeating the usual 20.00h for Mondays from 4 published Mondays" in note
               for note in usual.notes)
    # Too few Mondays (or too little history) is still the floor.
    thin = _history_model(weeks_observed=4, dates_by_weekday={1: 2}, hours_by_weekday={1: Decimal(20)})
    assert _labor(None, history=thin).method == "floor"
    assert _labor(None, history=_history_model(dates_by_weekday={1: 4},
                                                hours_by_weekday={1: Decimal(20)})).method == "floor"


def _employee(index, *, state="always_available", jobs=None):
    return {
        "id": f"employee-{index}", "name": f"Employee {index}", "availability_state": state,
        "target_weekly_minutes": 2400, "jobs": jobs or [],
    }


def test_a_roster_nobody_can_be_scheduled_from_says_so_once():
    roster = {"employees": [_employee(0, state="unconfirmed"), _employee(1, state="unconfirmed")]}
    result = _engine(roster=roster, profile=_profile(leader_required=True, leader_job_ids=[LEAD]),
                     jobs=[{"id": JOB, "name": "Barista"}, {"id": LEAD, "name": "Lead"}])
    assert result.demand == []
    assert result.demand_model["notes"] == [
        "nobody at this location has confirmed availability or is free this week — nothing to plan",
    ]


def test_unconfirmed_staff_are_not_capacity():
    roster = {"employees": [_employee(0), _employee(1, state="unconfirmed")]}
    result = _engine(roster=roster, profile=_profile(min_floor_staff=2))
    assert result.demand_model["capacity"]["employees"] == 1
    assert all(row["required_staff"] <= 1 for row in result.demand)
    assert any("clipped to the staff available" in note
               for day in result.demand_model["days"] for note in day["notes"])


def test_time_away_and_weekly_windows_clip_only_where_they_apply():
    tuesday = WEEK + timedelta(days=2)
    roster = {
        "employees": [_employee(0), _employee(1)],
        "availability": {"employee-1": {day: [(time(8), time(12))] for day in range(7)}},
        "unavailable_ranges": {"employee-0": [(tuesday, tuesday)]},
    }
    result = _engine(roster=roster, profile=_profile(min_floor_staff=2))
    days = {day["date"]: day for day in result.demand_model["days"]}
    monday_notes = days[(WEEK + timedelta(days=1)).isoformat()]["notes"]
    # Monday: employee-1 leaves at noon, so the second seat stops there.
    assert any("clipped to the staff available 12:00–16:00" in note for note in monday_notes)
    # Tuesday: employee-0 is away, so only employee-1's morning is staffable.
    tuesday_rows = [row for row in result.demand if row["key"].split(":")[1] == tuesday.isoformat()]
    assert sum(row["required_staff"] for row in tuesday_rows) == 1
    # ...one seat short all morning, both seats short all afternoon.
    assert any("clipped to the staff available 08:00–16:00" in note
               for note in days[tuesday.isoformat()]["notes"])


def test_qualification_dates_bound_who_counts_for_a_job():
    lapsed = [{"job_id": JOB, "qualification_status": "active", "qualified_until": WEEK - timedelta(days=1)}]
    result = _engine(roster={"employees": [_employee(0, jobs=lapsed)]}, gated_job_ids={JOB})
    assert result.demand == []
    assert any("no job has a qualified employee" in note for note in result.demand_model["notes"])


OTHER_LEAD = "00000000-0000-4000-8000-000000000004"
OPEN_LEAD = "00000000-0000-4000-8000-000000000005"


def _leader_engine(roster, **changes):
    return _engine(
        profile=_profile(leader_required=True, leader_job_ids=[LEAD, OTHER_LEAD, OPEN_LEAD], min_floor_staff=1,
                         operating_hours={str(d): {"open": "08:00", "close": "16:00"} for d in range(7)}),
        jobs=[{"id": JOB, "name": "Barista"}, {"id": LEAD, "name": "Manager"},
              {"id": OTHER_LEAD, "name": "Shift Lead"}, {"id": OPEN_LEAD, "name": "Assistant"}],
        roster=roster, **changes,
    )


def test_gated_leader_jobs_beat_an_open_one_and_share_the_seats():
    active = lambda job: {"job_id": job, "qualification_status": "active"}  # noqa: E731
    roster = {"employees": [
        _employee(0, jobs=[active(LEAD)]), _employee(1, jobs=[active(OTHER_LEAD)]),
        _employee(2, jobs=[active(OTHER_LEAD)]), _employee(3), _employee(4),
    ]}
    result = _leader_engine(roster, gated_job_ids={LEAD, OTHER_LEAD})
    leader_rows = [row for row in result.demand if row["job_id"] in (LEAD, OTHER_LEAD, OPEN_LEAD)]
    assert {row["job_id"] for row in leader_rows} == {LEAD, OTHER_LEAD}
    counts = {job: sum(1 for row in leader_rows if row["job_id"] == job) for job in (LEAD, OTHER_LEAD)}
    assert counts[OTHER_LEAD] > counts[LEAD] > 0                      # ~2:1 by qualified people
    assert result.demand_model["policy"]["leader_jobs"] == ["Manager", "Shift Lead"]
    assert not any("no qualified list" in note for note in result.demand_model["notes"])


def test_an_open_leader_job_is_used_only_as_a_labelled_fallback():
    roster = {"employees": [_employee(i) for i in range(3)]}
    result = _leader_engine(roster, gated_job_ids={LEAD, OTHER_LEAD})
    assert {row["job_id"] for row in result.demand} >= {OPEN_LEAD}
    assert any("Assistant has no qualified list, so anyone can fill the leader seat" in note
               for note in result.demand_model["notes"])


def test_a_job_never_gets_more_seats_than_it_has_people():
    other = "00000000-0000-4000-8000-000000000003"
    solo = [{"job_id": other, "qualification_status": "active"}]
    crew = [{"job_id": JOB, "qualification_status": "active"}]
    roster = {"employees": [_employee(0, jobs=solo)] + [_employee(i, jobs=crew) for i in range(1, 4)]}
    # History says half the work is the solo job — more than one person can do.
    history = []
    for n in range(1, 5):
        day = WEEK + timedelta(days=1) - timedelta(days=7 * n)
        history += [_row(day, 8, 16, seats=2, job=other), _row(day, 8, 16, seats=2, job=JOB)]
    result = _engine(
        profile=_profile(min_floor_staff=4), roster=roster, gated_job_ids={JOB, other},
        jobs=[{"id": JOB, "name": "Barista"}, {"id": other, "name": "Roaster"}],
        history_shifts=history,
    )
    for day in {row["key"].split(":")[1] for row in result.demand}:
        solo_rows = [row for row in result.demand if row["job_id"] == other and row["key"].split(":")[1] == day]
        for index, row in enumerate(solo_rows):
            overlapping = sum(
                other_row["required_staff"] for other_row in solo_rows
                if other_row["starts_at"] < row["ends_at"] and row["starts_at"] < other_row["ends_at"]
            )
            assert overlapping <= 1


def test_weekly_minutes_overflow_is_said_up_front():
    solo = [{"job_id": LEAD, "qualification_status": "active"}]
    roster = {"employees": [_employee(0, jobs=solo), _employee(1), _employee(2)]}
    result = _engine(
        profile=_profile(leader_required=True, leader_job_ids=[LEAD],
                         operating_hours={str(d): {"open": "06:00", "close": "22:00"} for d in range(7)}),
        jobs=[{"id": JOB, "name": "Barista"}, {"id": LEAD, "name": "Manager"}],
        roster=roster, gated_job_ids={LEAD},
    )
    # One manager (40h) cannot lead 16h x 7 days.
    assert result.demand_model["capacity"]["shifts_beyond_qualified_staff"] > 0
    assert any("the staff qualified and available for Manager" in note
               for day in result.demand_model["days"] for note in day["notes"])


def test_holidays_are_left_out_of_learning_and_labelled_in_the_week():
    thanksgiving = date(2026, 11, 26)
    week = date(2026, 11, 22)
    prior = [thanksgiving - timedelta(days=7 * n) for n in range(1, 5)]
    sales = {day: Decimal(1000) for day in prior}
    sales[prior[0]] = Decimal(100)                     # a holiday-like outlier
    result = _engine(
        week_start=week, sales_by_day=sales, anchor=week,
        profile=_profile(operating_hours={str(d): {"open": "08:00", "close": "16:00"} for d in range(7)}),
        holidays={prior[0]: "Some Holiday", thanksgiving: "Thanksgiving"},
    )
    days = {day["date"]: day for day in result.demand_model["days"]}
    assert days[thanksgiving.isoformat()]["baseline_sales"] == 1000.0
    assert any(note.startswith("Thanksgiving — past holidays are left out") for note in days[thanksgiving.isoformat()]["notes"])
    assert result.demand_model["holidays"] == [{"date": thanksgiving.isoformat(), "name": "Thanksgiving"}]


def test_only_relevant_inputs_are_reported_missing():
    bare = _engine()
    assert bare.demand_model["inputs_missing"] == ["sales_history", "published_history"]
    rainy = _engine(profile=_profile(weather_sensitivity="rain_hurts"))
    assert "weather" in rainy.demand_model["inputs_missing"]
    sold = _engine(sales_by_day={WEEK - timedelta(days=6): Decimal(500)})
    assert {"target_labor_pct", "blended_hourly_rate"} <= set(sold.demand_model["inputs_missing"])
    assert "hourly_sales" not in sold.demand_model["inputs_missing"]
    assert "from 1 day of sales" in sold.demand_model["sentence"]


def test_trailing_mean_note_names_the_days_it_averaged():
    sales = {WEEK - timedelta(days=offset): Decimal(100) for offset in (1, 2, 3)}
    forecast = forecast_day(WEEK + timedelta(days=1), sales_by_day=sales, weather_by_day={},
                            sensitivity="none", anchor=WEEK)
    assert "using the average of all 3 sales days" in forecast.notes[0]
