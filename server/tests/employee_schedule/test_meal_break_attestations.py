"""Contract checks for the employee-profile meal-break waiver surface."""

import asyncio
from datetime import date, datetime, timezone
from pathlib import Path
from uuid import uuid4
from zoneinfo import ZoneInfo

from app.matcha.models.scheduling.employee_schedule import MealWaiverAttestationResponse
from app.matcha.services.scheduling import schedule_guidance
from app.matcha.services.scheduling.schedule_break_rule_store import ResolvedBreakRules
from app.matcha.services.scheduling.schedule_breaks import BreakRule


def test_no_attestation_has_an_explicit_safe_response_shape():
    response = MealWaiverAttestationResponse(employee_id="0f9dc4aa-03fc-4dae-bf04-6c9cde1b6f4b", on_file=False, attested=False)
    assert response.on_file is False
    assert response.attested is False
    assert response.effective_from is None


def test_waiver_endpoint_scopes_to_company_and_returns_only_effective_attestation():
    route = Path(__file__).parents[2] / "app/matcha/routes/employee_schedule/attestations.py"
    source = route.read_text()
    assert '@router.get("/employees/{employee_id}/meal-break-waiver"' in source
    assert "await assert_employee_in_company(conn, company_id, employee_id)" in source
    assert "effective_from <= COALESCE((NOW() AT TIME ZONE l.timezone)::date, CURRENT_DATE)" in source
    assert "FROM employee_compliance_attestations a" in source
    assert "WHERE a.company_id = $1 AND a.employee_id = $2" in source
    assert "ORDER BY a.effective_from DESC, a.confirmed_at DESC" in source
    assert "s.starts_at::date >= GREATEST($3, CURRENT_DATE)" in source
    assert "refresh_assignment_break_guidance_and_minimum" in source


def test_guidance_evaluates_waivers_on_the_location_calendar_day():
    guidance = Path(__file__).parents[2] / "app/matcha/services/scheduling/schedule_guidance.py"
    source = guidance.read_text()
    assert "reinterpret_schedule_wall_time(starts_at, location_timezone).date()" in source
    assert "reinterpret_schedule_wall_time(starts_at, effective_timezone).date()" in source


def test_guidance_uses_schedule_wall_date_near_midnight(monkeypatch):
    captured = {}

    class Connection:
        async def fetchval(self, *_args):
            return "America/Los_Angeles"

    async def resolve_rules(_conn, *, company_id, location_id, shift_date):
        captured["shift_date"] = shift_date
        return ResolvedBreakRules(
            rules=(), rule_set_ids=(), timezone=ZoneInfo("America/Los_Angeles"),
            industry_code=None, source="unmapped", advisories=(),
        )

    monkeypatch.setattr(schedule_guidance, "resolve_break_rules", resolve_rules)
    asyncio.run(schedule_guidance.resolve_shift_break_plan(
        Connection(), uuid4(), location_id=uuid4(),
        starts_at=datetime(2026, 1, 1, 0, 30, tzinfo=timezone.utc),
        ends_at=datetime(2026, 1, 1, 8, 30, tzinfo=timezone.utc),
    ))

    assert captured["shift_date"] == date(2026, 1, 1)


def test_multi_employee_plans_batch_demographics_and_waivers(monkeypatch):
    employee_ids = [uuid4(), uuid4(), uuid4()]
    fetch_calls = []
    rule_id = uuid4()

    class Connection:
        async def fetchval(self, *_args):
            return "America/Los_Angeles"

        async def fetch(self, query, *_args):
            fetch_calls.append(query)
            if "FROM employees e" in query:
                return [
                    {"employee_id": employee_id, "date_of_birth": date(1990, 1, 1)}
                    for employee_id in employee_ids
                ]
            if "FROM employee_compliance_attestations" in query:
                return []
            raise AssertionError(query)

    async def resolve_rules(*_args, **_kwargs):
        return ResolvedBreakRules(
            rules=(BreakRule(
                rule_set_id=rule_id, kind="meal", ordinal=1,
                trigger_after_minutes=300, duration_minutes=30, paid=False,
            ),),
            rule_set_ids=(rule_id,), timezone=ZoneInfo("America/Los_Angeles"),
            industry_code=None, source="approved", advisories=(),
        )

    monkeypatch.setattr(schedule_guidance, "resolve_break_rules", resolve_rules)
    plans = asyncio.run(schedule_guidance.resolve_shift_break_plans(
        Connection(), uuid4(), location_id=uuid4(),
        starts_at=datetime(2026, 1, 1, 9, tzinfo=timezone.utc),
        ends_at=datetime(2026, 1, 1, 17, tzinfo=timezone.utc),
        employee_ids=employee_ids,
    ))

    assert set(plans) == set(employee_ids)
    assert all(plan.requirements[0].duration_minutes == 30 for plan in plans.values())
    assert len(fetch_calls) == 2
