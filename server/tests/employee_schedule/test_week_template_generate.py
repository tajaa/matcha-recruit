"""Multi-block week-template generation — pure arithmetic, no DB.

generate_from_week_template (routes/employee_schedule/week_templates.py) loops
every block through template_windows and unions the results under one
series_id. These tests pin the per-block window math the route relies on:
disjoint weekday coverage across blocks, a block with no weekdays configured
producing zero windows (the route `continue`s rather than 422ing), and an
overnight block rolling to the next day alongside a same-day block — a
theatre's "Standard Week" needs all three at once.
"""

import asyncio
from datetime import date, time, timedelta
from uuid import uuid4

from app.matcha.services.scheduling.schedule_rules import template_windows
from app.matcha.services.scheduling import (
    schedule_breaks, schedule_guidance, shift_compliance, shift_writes,
)


def test_two_blocks_cover_disjoint_weekdays():
    # Standard Week: Box Office Mon-Fri 9-22, Weekend Crew Sat+Sun 9-23.
    # One 7-day range must produce 5 + 2 = 7 windows, none overlapping days.
    weekday_starts, _ = template_windows(date(2026, 7, 12), date(2026, 7, 18), {1, 2, 3, 4, 5}, time(9), time(22))
    weekend_starts, _ = template_windows(date(2026, 7, 12), date(2026, 7, 18), {0, 6}, time(9), time(23))
    assert len(weekday_starts) == 5 and len(weekend_starts) == 2
    assert not {s.date() for s in weekday_starts} & {s.date() for s in weekend_starts}


def test_block_with_no_weekdays_yields_nothing():
    # The route `continue`s on an empty day_set — an empty mask is zero
    # windows, not an error.
    assert template_windows(date(2026, 7, 12), date(2026, 7, 18), set(), time(9), time(17)) == ([], [])


def test_overnight_block_alongside_a_day_block():
    # A theatre's late block (22:00-02:00) rolls to the next day while the day
    # block does not — both can live in the same week template.
    _, day_ends = template_windows(date(2026, 7, 13), date(2026, 7, 13), {1}, time(9), time(17))
    late_starts, late_ends = template_windows(date(2026, 7, 13), date(2026, 7, 13), {1}, time(22), time(2))
    assert day_ends[0].date() == date(2026, 7, 13)
    assert late_ends[0].date() == date(2026, 7, 14) and late_ends[0] > late_starts[0]


def test_apply_range_spans_requested_weeks():
    # The chat "apply" flow multiplies weeks into the end date
    # (start + 7*weeks - 1 days) before calling template_windows — a
    # Mon-Fri block over 2 requested weeks must yield 10 windows, not 5.
    start = date(2026, 7, 12)  # a Sunday
    weeks = 2
    end = start + timedelta(days=7 * weeks - 1)
    starts, _ = template_windows(start, end, {1, 2, 3, 4, 5}, time(9), time(17))
    assert len(starts) == 10


def test_materialized_template_shift_uses_generated_minimum(monkeypatch):
    captured = {}

    async def resolve(*_args, **_kwargs):
        return object()

    async def compliance(*_args, **_kwargs):
        return []

    async def resolve_many(_conn, _company_id, *, location_id, windows):
        return [await resolve() for _ in windows]

    monkeypatch.setattr(schedule_guidance, "resolve_open_shift_break_plans", resolve_many)
    monkeypatch.setattr(schedule_breaks, "minimum_meal_break_minutes", lambda _plan: 30)
    monkeypatch.setattr(shift_compliance, "check_shift_compliance", compliance)

    class Connection:
        async def fetch(self, query, *args):
            assert "w.break_minutes" in query
            captured["breaks"] = args[8]
            return [{"id": uuid4()} for _ in args[6]]

    block = {
        "id": uuid4(), "name": "Day", "role": None, "department": None,
        "location_id": uuid4(), "start_time": time(9), "end_time": time(17),
        "break_minutes": 0, "required_staff": 1, "days_of_week": [1],
        "color": None, "notes": None, "job_id": None,
    }
    result = asyncio.run(shift_writes.generate_week_template_shifts(
        Connection(), uuid4(), blocks=[block], start_date=date(2026, 7, 13),
        end_date=date(2026, 7, 13), created_by=uuid4(),
    ))

    assert result["created"] == 1
    assert captured["breaks"] == [30]


def test_materialized_template_batches_rule_resolution(monkeypatch):
    calls = []

    async def resolve_many(_conn, _company_id, *, location_id, windows):
        calls.append((location_id, list(windows)))
        return [object() for _ in windows]

    async def compliance(*_args, **_kwargs):
        return []

    monkeypatch.setattr(schedule_guidance, "resolve_open_shift_break_plans", resolve_many)
    monkeypatch.setattr(schedule_breaks, "minimum_meal_break_minutes", lambda _plan: 30)
    monkeypatch.setattr(shift_compliance, "check_shift_compliance", compliance)

    class Connection:
        async def fetch(self, query, *args):
            return [{"id": uuid4()} for _ in args[6]]

    location_id = uuid4()
    blocks = [
        {
            "id": uuid4(), "name": name, "role": None, "department": None,
            "location_id": location_id, "start_time": start_time, "end_time": time(17),
            "break_minutes": 0, "required_staff": 1, "days_of_week": [1, 2],
            "color": None, "notes": None, "job_id": None,
        }
        for name, start_time in (("Early", time(8)), ("Late", time(9)))
    ]
    result = asyncio.run(shift_writes.generate_week_template_shifts(
        Connection(), uuid4(), blocks=blocks, start_date=date(2026, 7, 13),
        end_date=date(2026, 7, 14), created_by=uuid4(),
    ))

    assert result["created"] == 4
    assert len(calls) == 1
    assert len(calls[0][1]) == 4
