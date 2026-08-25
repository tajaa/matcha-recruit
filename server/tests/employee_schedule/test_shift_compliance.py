import asyncio
from datetime import datetime, timezone
from uuid import uuid4

from app.matcha.services.scheduling import schedule_eligibility, shift_compliance


def test_assigned_shift_keeps_schedule_eligibility_violations(monkeypatch):
    company_id = uuid4()
    employee_id = uuid4()
    job_id = uuid4()
    observed_job_ids: list = []
    eligibility_violation = {
        "check": "schedule_eligibility",
        "severity": "block",
        "code": "credential_expired",
        "message": "Food handler card expired 2026-08-20 and blocks new scheduling.",
        "statute": "Approved state rule",
        "state": "",
    }

    async def fake_location_state(*_args):
        return "CA", "Los Angeles"

    async def fake_location_timezone(*_args):
        return "UTC"

    async def fake_eligibility(*_args, **_kwargs):
        observed_job_ids.append(_kwargs["job_id"])
        return [eligibility_violation]

    async def fake_week_hours(*_args, **_kwargs):
        return 7.5

    async def fake_min_rest(*_args, **_kwargs):
        return None

    async def fake_employee_age(*_args, **_kwargs):
        return None, False

    monkeypatch.setattr(shift_compliance, "_location_state", fake_location_state)
    monkeypatch.setattr(shift_compliance, "_location_timezone", fake_location_timezone)
    monkeypatch.setattr(schedule_eligibility, "schedule_eligibility_violations", fake_eligibility)
    monkeypatch.setattr(shift_compliance, "_week_hours", fake_week_hours)
    monkeypatch.setattr(shift_compliance, "_min_rest_gap", fake_min_rest)
    monkeypatch.setattr(shift_compliance, "_employee_age", fake_employee_age)

    result = asyncio.run(shift_compliance.check_shift_compliance(
        object(),
        company_id,
        location_id=uuid4(),
        starts_at=datetime(2026, 8, 21, 9, tzinfo=timezone.utc),
        ends_at=datetime(2026, 8, 21, 17, 30, tzinfo=timezone.utc),
        break_minutes=30,
        employee_id=employee_id,
        job_id=job_id,
        lapse_items=[],
    ))

    assert eligibility_violation in result
    assert observed_job_ids == [job_id]


def test_eligibility_uses_the_shift_locations_calendar_day(monkeypatch):
    observed: list = []

    async def fake_location_state(*_args):
        return "CA", "Los Angeles"

    async def fake_location_timezone(*_args):
        return "America/Los_Angeles"

    async def fake_eligibility(*_args, **kwargs):
        observed.append(kwargs["shift_date"])
        return []

    async def fake_week_hours(*_args, **_kwargs):
        return 0

    async def fake_min_rest(*_args, **_kwargs):
        return None

    async def fake_employee_age(*_args, **_kwargs):
        return None, False

    monkeypatch.setattr(shift_compliance, "_location_state", fake_location_state)
    monkeypatch.setattr(shift_compliance, "_location_timezone", fake_location_timezone)
    monkeypatch.setattr(schedule_eligibility, "schedule_eligibility_violations", fake_eligibility)
    monkeypatch.setattr(shift_compliance, "_week_hours", fake_week_hours)
    monkeypatch.setattr(shift_compliance, "_min_rest_gap", fake_min_rest)
    monkeypatch.setattr(shift_compliance, "_employee_age", fake_employee_age)

    asyncio.run(shift_compliance.check_shift_compliance(
        object(), uuid4(), location_id=uuid4(), employee_id=uuid4(),
        starts_at=datetime(2026, 8, 26, 5, tzinfo=timezone.utc),
        ends_at=datetime(2026, 8, 26, 13, tzinfo=timezone.utc),
        break_minutes=30, lapse_items=[],
    ))

    assert observed == [datetime(2026, 8, 25).date()]
