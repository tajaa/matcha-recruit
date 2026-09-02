"""Pure tests for Huume's deterministic whole-week assignment planner."""

import inspect
from datetime import date, datetime, time, timezone
from unittest.mock import AsyncMock
from uuid import UUID

import pytest

from app.matcha.services.scheduling import week_builder
from app.matcha.services.scheduling.week_builder import _coerce_constraints, build_plan


UTC = timezone.utc


class _AsyncContext:
    def __init__(self, value):
        self.value = value

    async def __aenter__(self):
        return self.value

    async def __aexit__(self, exc_type, exc, tb):
        return False


class _FakeConn:
    def __init__(self, row):
        self.row = row
        self.executed = []

    def transaction(self):
        return _AsyncContext(self)

    async def fetchrow(self, *_args):
        return self.row

    async def execute(self, *args):
        self.executed.append(args)


def _employee(employee_id: str, name: str, *, jobs=None, state="windows", cap=2400):
    return {
        "id": employee_id,
        "name": name,
        "availability_state": state,
        "jobs": jobs or [],
        "target_weekly_minutes": 480,
        "max_weekly_minutes": cap,
        "max_consecutive_days": 6,
        "allow_overtime": False,
        "prefer_extra_hours": False,
    }


def _shift(key: str, day: int, *, job_id=None, fixed=None, required=1):
    starts_at = datetime(2026, 8, day, 9, tzinfo=UTC)
    ends_at = datetime(2026, 8, day, 13, tzinfo=UTC)
    return {
        "key": key,
        "source_shift_id": key,
        "role": "Licensed" if job_id else "Floor",
        "department": None,
        "starts_at": starts_at,
        "ends_at": ends_at,
        "break_minutes": 0,
        "required_staff": required,
        "color": None,
        "notes": None,
        "kind": "work",
        "template_id": None,
        "job_id": job_id,
        "training_requirement_id": None,
        "fixed_employee_ids": fixed or [],
        "worked_minutes": 240,
    }


def _plan(*, demand, employees, availability, existing=None, unavailable=None, caps=None):
    return build_plan(
        demand=demand,
        employees=employees,
        availability=availability,
        existing_assignments=existing or [],
        unavailable_ranges=unavailable or {},
        exclude_employee_ids=set(),
        employee_hour_caps=caps or {},
    )


def test_scarcity_first_preserves_only_qualified_employee_for_later_shift():
    qualified_job = {
        "job_id": "job-1", "qualification_status": "active",
        "qualified_from": None, "qualified_until": None,
    }
    employees = [
        _employee("amy", "Amy", jobs=[qualified_job]),
        _employee("ben", "Ben"),
    ]
    availability = {
        "amy": {1: [(time(8), time(18))], 2: [(time(8), time(18))]},
        "ben": {1: [(time(8), time(18))], 2: [(time(8), time(18))]},
    }
    plan = _plan(
        demand=[_shift("flex", 25), _shift("licensed", 25, job_id="job-1")],
        employees=employees,
        availability=availability,
    )

    assignments = {
        shift["key"]: [item["employee_id"] for item in shift["proposed_assignments"]]
        for shift in plan["shifts"]
    }
    assert assignments == {"flex": ["ben"], "licensed": ["amy"]}
    assert plan["metrics"]["open_positions"] == 0


def test_unconfirmed_availability_time_away_and_caps_leave_explainable_open_slot():
    employees = [
        _employee("unconfirmed", "Unconfirmed", state="unconfirmed"),
        _employee("away", "Away"),
        _employee("capped", "Capped", cap=120),
    ]
    availability = {
        employee["id"]: {1: [(time(8), time(18))]} for employee in employees
    }
    plan = _plan(
        demand=[_shift("monday", 24)],
        employees=employees,
        availability=availability,
        unavailable={"away": [(date(2026, 8, 24), date(2026, 8, 24))]},
    )

    assert plan["metrics"]["open_positions"] == 1
    assert plan["unfilled"][0]["exclusions"] == {
        "approved time away": 1,
        "availability unconfirmed": 1,
        "weekly hour cap": 1,
    }


def test_existing_assignments_are_fixed_and_count_toward_staffing_and_hours():
    employees = [_employee("amy", "Amy"), _employee("ben", "Ben")]
    shift = _shift("draft-1", 24, fixed=["amy"], required=2)
    existing = [{
        "employee_id": "amy",
        "shift_id": "draft-1",
        "starts_at": shift["starts_at"],
        "ends_at": shift["ends_at"],
        "worked_minutes": 240,
    }]
    availability = {
        "amy": {1: [(time(8), time(18))]},
        "ben": {1: [(time(8), time(18))]},
    }
    plan = _plan(
        demand=[shift], employees=employees, availability=availability, existing=existing,
    )

    assert plan["shifts"][0]["fixed_employee_ids"] == ["amy"]
    assert plan["shifts"][0]["proposed_assignments"][0]["employee_id"] == "ben"
    assert plan["metrics"] == {
        "shift_count": 1,
        "required_positions": 2,
        "fixed_positions": 1,
        "overstaffed_positions": 0,
        "proposed_positions": 1,
        "filled_positions": 2,
        "open_positions": 0,
    }


def test_same_inputs_produce_identical_plan():
    employees = [_employee("amy", "Amy"), _employee("ben", "Ben")]
    availability = {
        "amy": {1: [(time(8), time(18))]},
        "ben": {1: [(time(8), time(18))]},
    }
    kwargs = {
        "demand": [_shift("monday", 24, required=2)],
        "employees": employees,
        "availability": availability,
    }
    assert _plan(**kwargs) == _plan(**kwargs)


def test_manager_constraints_fail_closed_instead_of_being_silently_dropped():
    with pytest.raises(ValueError, match="valid employee id"):
        _coerce_constraints(["Amy"], None)
    with pytest.raises(ValueError, match="between 0 and 10,080"):
        _coerce_constraints(None, [{
            "employee_id": "3f6b1c22-2000-4000-8000-000000000001",
            "max_weekly_minutes": 10081,
        }])


def test_apply_week_draft_prelocks_complete_employee_set():
    source = inspect.getsource(week_builder.apply_week_draft)
    employee_set = source.index("employee_ids = sorted({")
    prelock = source.index(
        "await lock_scheduling_employees(conn, company_id, employee_ids)",
    )
    conflict_loop = source.index("elif await find_conflicts(", prelock)
    assert employee_set < prelock < conflict_loop


@pytest.mark.asyncio
async def test_readiness_loads_week_shift_counts(monkeypatch):
    company_id = UUID("3f6b1c22-2000-4000-8000-000000000001")
    location_id = UUID("3f6b1c22-2000-4000-8000-000000000002")
    conn = _FakeConn({"id": location_id, "name": "Main Store"})
    monkeypatch.setattr(week_builder, "connection_or_direct", lambda: _AsyncContext(conn))
    monkeypatch.setattr(week_builder, "_load_roster_context", AsyncMock(return_value={
        "employees": [{
            "id": "employee-1", "name": "Amy", "availability_state": "windows",
            "target_weekly_minutes": 1200, "max_weekly_minutes": 2400,
        }],
    }))
    monkeypatch.setattr(week_builder, "_load_existing_demand", AsyncMock(return_value=[]))
    counts = AsyncMock(return_value={"draft": 0, "published": 1})
    monkeypatch.setattr(week_builder, "_week_shift_counts", counts)
    monkeypatch.setattr(week_builder, "_list_templates", AsyncMock(return_value=[]))

    result = await week_builder.get_week_build_readiness(
        company_id=company_id, location_id=location_id, week_start=date(2026, 8, 23),
    )

    assert result["published_shift_count"] == 1
    assert result["recommended_source"] is None
    assert any("published shifts" in blocker for blocker in result["blockers"])
    counts.assert_awaited_once()


@pytest.mark.asyncio
async def test_template_snapshot_includes_live_week_shift_state(monkeypatch):
    company_id = UUID("3f6b1c22-2000-4000-8000-000000000001")
    location_id = UUID("3f6b1c22-2000-4000-8000-000000000002")
    template_id = UUID("3f6b1c22-2000-4000-8000-000000000003")
    live_state = [{"id": "shift-1", "status": "draft", "employee_ids": []}]
    monkeypatch.setattr(week_builder, "_load_roster_context", AsyncMock(return_value={
        "employees": [], "availability": {}, "existing_assignments": [],
        "unavailable_ranges": {},
    }))
    monkeypatch.setattr(
        week_builder, "_load_week_shift_state", AsyncMock(return_value=live_state),
    )
    monkeypatch.setattr(
        week_builder, "_load_template_demand",
        AsyncMock(return_value=("Standard Week", [{"key": "template-shift"}])),
    )

    snapshot, _demand, _name = await week_builder._planning_snapshot(
        object(), company_id=company_id, location_id=location_id,
        week_start=date(2026, 8, 23), source_mode="template",
        week_template_id=template_id,
    )

    assert snapshot["week_shift_state"] == live_state


@pytest.mark.asyncio
async def test_apply_template_proposal_rechecks_empty_week_guard(monkeypatch):
    company_id = UUID("3f6b1c22-2000-4000-8000-000000000001")
    location_id = UUID("3f6b1c22-2000-4000-8000-000000000002")
    run_id = UUID("3f6b1c22-2000-4000-8000-000000000003")
    week_start = date(2026, 8, 23)
    conn = _FakeConn({
        "id": run_id, "company_id": company_id, "location_id": location_id,
        "week_start": week_start, "status": "proposed", "source_mode": "template",
    })
    monkeypatch.setattr(week_builder, "connection_or_direct", lambda: _AsyncContext(conn))
    monkeypatch.setattr(
        week_builder, "_week_shift_counts",
        AsyncMock(return_value={"draft": 1, "published": 0}),
    )
    planning_snapshot = AsyncMock(side_effect=AssertionError("must stop before rebuilding"))
    monkeypatch.setattr(week_builder, "_planning_snapshot", planning_snapshot)

    result = await week_builder.apply_week_draft(
        company_id=company_id, actor_user_id=None, generation_run_id=run_id,
        location_id=location_id, week_start=week_start,
    )

    assert result["status"] == "error"
    assert "gained shifts" in result["message"]
    planning_snapshot.assert_not_awaited()
    assert any("status='stale'" in call[0] for call in conn.executed)
