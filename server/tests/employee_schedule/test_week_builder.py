"""Pure tests for Huume's deterministic whole-week assignment planner."""

from datetime import date, datetime, time, timezone

import pytest

from app.matcha.services.scheduling.week_builder import _coerce_constraints, build_plan


UTC = timezone.utc


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
