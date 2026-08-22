import asyncio
from datetime import datetime, timezone
from uuid import uuid4

from app.matcha.services.scheduling import schedule_eligibility, shift_compliance


def test_assigned_shift_keeps_schedule_eligibility_violations(monkeypatch):
    company_id = uuid4()
    employee_id = uuid4()
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

    async def fake_eligibility(*_args, **_kwargs):
        return [eligibility_violation]

    async def fake_week_hours(*_args, **_kwargs):
        return 7.5

    async def fake_min_rest(*_args, **_kwargs):
        return None

    async def fake_employee_age(*_args, **_kwargs):
        return None, False

    monkeypatch.setattr(shift_compliance, "_location_state", fake_location_state)
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
        lapse_items=[],
    ))

    assert eligibility_violation in result
