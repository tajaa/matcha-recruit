"""Pure tests for Huume's deterministic whole-week assignment planner."""

import inspect
import json
from datetime import date, datetime, time, timedelta, timezone
from unittest.mock import AsyncMock
from uuid import UUID

import pytest

from app.matcha.services.scheduling import week_builder
from app.matcha.services.scheduling.week_builder import _coerce_constraints, build_plan


UTC = timezone.utc


# A location whose week-set rules are on file. Every test in this module is
# about the planner, not the setup gate — without this the gate refuses first
# and nothing below it ever runs. The gate has its own file,
# `test_week_rules_gate.py`.
ESTABLISHED_BUNDLE = {
    "profile": {
        "operating_hours": {
            "0": None, "6": None,
            **{str(day): {"open": "08:00", "close": "17:00"} for day in range(1, 6)},
        },
        "leader_job_id": None,
        "leader_required": False,
    },
    "template": {"id": "3f6b1c22-2000-4000-8000-000000000009", "name": "Downtown default week",
                 "blocks": [{"name": "Opener"}]},
    "leader_job_name": None,
}


@pytest.fixture(autouse=True)
def _established_week_rules(monkeypatch):
    monkeypatch.setattr(
        week_builder, "load_profile_bundle", AsyncMock(return_value=ESTABLISHED_BUNDLE),
    )


class _AsyncContext:
    def __init__(self, value):
        self.value = value

    async def __aenter__(self):
        return self.value

    async def __aexit__(self, exc_type, exc, tb):
        return False


class _FakeConn:
    def __init__(self, row, *, scalar=None, rows=()):
        self.row = row
        self.scalar = scalar
        # Readiness reads the live week to use published shifts as a coverage
        # baseline; every current caller wants an empty week.
        self.rows = list(rows)
        self.executed = []

    def transaction(self):
        return _AsyncContext(self)

    async def fetchrow(self, *_args):
        return self.row

    async def fetch(self, *_args):
        return self.rows

    async def fetchval(self, *_args):
        return self.scalar

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


def _plan(*, demand, employees, availability, existing=None, unavailable=None, caps=None,
          gated_job_ids=None):
    # Stand-in for the production company-wide "which jobs have any roster row"
    # query: default to every job somebody here is named on, so a fixture that
    # qualifies people is gated and one that names nobody is not.
    if gated_job_ids is None:
        gated_job_ids = {
            job["job_id"]
            for employee in employees
            for job in employee.get("jobs") or []
        }
    return build_plan(
        demand=demand,
        employees=employees,
        availability=availability,
        existing_assignments=existing or [],
        unavailable_ranges=unavailable or {},
        exclude_employee_ids=set(),
        employee_hour_caps=caps or {},
        gated_job_ids=gated_job_ids,
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


def test_a_job_nobody_is_named_on_is_ungated():
    """An empty qualified roster means UNGATED, matching the REST assignment
    gate. The first whole-week build on a tenant that defined jobs but never
    filled in the per-job lists otherwise reports every position open."""
    employees = [_employee("amy", "Amy")]
    plan = _plan(
        demand=[_shift("licensed", 24, job_id="job-1")],
        employees=employees,
        availability={"amy": {1: [(time(8), time(18))]}},
        gated_job_ids=set(),
    )

    assert [item["employee_id"] for item in plan["shifts"][0]["proposed_assignments"]] == ["amy"]
    assert plan["metrics"]["open_positions"] == 0


def test_a_job_with_a_roster_still_gates_someone_not_on_it():
    """Gating is opted into by naming who is qualified — once anyone is named,
    everyone else is refused."""
    employees = [_employee("amy", "Amy")]
    plan = _plan(
        demand=[_shift("licensed", 24, job_id="job-1")],
        employees=employees,
        availability={"amy": {1: [(time(8), time(18))]}},
        gated_job_ids={"job-1"},
    )

    assert plan["shifts"][0]["proposed_assignments"] == []
    assert plan["metrics"]["open_positions"] == 1
    assert plan["unfilled"][0]["reason"] == "not qualified for the shift job"


def test_gating_is_per_job_not_global():
    """A roster on one job must not gate a different, roster-less job."""
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
        demand=[_shift("licensed", 25, job_id="job-1"), _shift("open-job", 25, job_id="job-2")],
        employees=employees,
        availability=availability,
        gated_job_ids={"job-1"},
    )

    assignments = {
        shift["key"]: [item["employee_id"] for item in shift["proposed_assignments"]]
        for shift in plan["shifts"]
    }
    assert assignments["licensed"] == ["amy"]      # gated, only Amy is named
    assert assignments["open-job"] == ["ben"]      # ungated, anyone may work it
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


COMPANY_ID = UUID("3f6b1c22-2000-4000-8000-000000000001")
LOCATION_ID = UUID("3f6b1c22-2000-4000-8000-000000000002")
DEFAULT_TEMPLATE_ID = UUID("3f6b1c22-2000-4000-8000-000000000009")
OTHER_TEMPLATE_ID = UUID("3f6b1c22-2000-4000-8000-00000000000a")


def _empty_week(monkeypatch, conn, templates, *, week_start_weekday=0):
    monkeypatch.setattr(week_builder, "connection_or_direct", lambda: _AsyncContext(conn))
    # This fake answers every fetchval with the same scalar; the week-alignment
    # guard has its own lookup and is exercised on its own below.
    monkeypatch.setattr(
        week_builder, "resolve_week_start_weekday", AsyncMock(return_value=week_start_weekday),
    )
    monkeypatch.setattr(week_builder, "_load_existing_demand", AsyncMock(return_value=[]))
    monkeypatch.setattr(
        week_builder, "_week_shift_counts", AsyncMock(return_value={"draft": 0, "published": 0}),
    )
    monkeypatch.setattr(week_builder, "_list_templates", AsyncMock(return_value=templates))


@pytest.mark.asyncio
async def test_auto_prefers_the_locations_default_template_over_asking(monkeypatch):
    """Two usable templates used to force a "choose one" clarify every single
    week. The location's saved default IS that answer."""
    conn = _FakeConn(None, scalar=DEFAULT_TEMPLATE_ID)
    _empty_week(monkeypatch, conn, [
        {"id": str(OTHER_TEMPLATE_ID), "name": "Holiday week", "block_count": 3},
        {"id": str(DEFAULT_TEMPLATE_ID), "name": "Downtown default week", "block_count": 4},
    ])
    snapshot = AsyncMock(side_effect=ValueError("stop after source selection"))
    monkeypatch.setattr(week_builder, "_planning_snapshot", snapshot)

    result = await week_builder.propose_week_draft(
        company_id=COMPANY_ID, actor_user_id=None, thread_id=None,
        location_id=LOCATION_ID, week_start=date(2026, 8, 23),
    )

    # Reached the planner (not the clarify) with the default selected.
    assert result["status"] == "clarify"
    assert snapshot.await_args.kwargs["source_mode"] == "template"
    assert snapshot.await_args.kwargs["week_template_id"] == DEFAULT_TEMPLATE_ID


@pytest.mark.asyncio
async def test_auto_still_asks_when_the_default_template_has_no_blocks(monkeypatch):
    """An empty default is not an answer — it would build nothing."""
    conn = _FakeConn(None, scalar=DEFAULT_TEMPLATE_ID)
    _empty_week(monkeypatch, conn, [
        {"id": str(OTHER_TEMPLATE_ID), "name": "Holiday week", "block_count": 3},
        {"id": str(DEFAULT_TEMPLATE_ID), "name": "Downtown default week", "block_count": 0},
        {"id": "3f6b1c22-2000-4000-8000-00000000000b", "name": "Summer", "block_count": 2},
    ])

    result = await week_builder.propose_week_draft(
        company_id=COMPANY_ID, actor_user_id=None, thread_id=None,
        location_id=LOCATION_ID, week_start=date(2026, 8, 23),
    )

    assert result["status"] == "clarify"
    assert "Choose which week template" in result["message"]


@pytest.mark.asyncio
async def test_readiness_recommends_the_default_and_drops_the_choose_blocker(monkeypatch):
    conn = _FakeConn({"id": LOCATION_ID, "name": "Downtown"}, scalar=DEFAULT_TEMPLATE_ID)
    _empty_week(monkeypatch, conn, [
        {"id": str(OTHER_TEMPLATE_ID), "name": "Holiday week", "block_count": 3},
        {"id": str(DEFAULT_TEMPLATE_ID), "name": "Downtown default week", "block_count": 4},
    ])
    monkeypatch.setattr(week_builder, "_load_roster_context", AsyncMock(return_value={
        "employees": [{
            "id": "employee-1", "name": "Amy", "availability_state": "windows",
            "target_weekly_minutes": 1200, "max_weekly_minutes": 2400,
        }],
    }))

    result = await week_builder.get_week_build_readiness(
        company_id=COMPANY_ID, location_id=LOCATION_ID, week_start=date(2026, 8, 23),
    )

    assert result["recommended_source"] == "template"
    assert result["default_week_template_id"] == str(DEFAULT_TEMPLATE_ID)
    assert result["ready"] is True
    assert not any("Choose which saved week template" in b for b in result["blockers"])


@pytest.mark.asyncio
async def test_readiness_keeps_the_choose_blocker_without_a_default(monkeypatch):
    conn = _FakeConn({"id": LOCATION_ID, "name": "Downtown"}, scalar=None)
    _empty_week(monkeypatch, conn, [
        {"id": str(OTHER_TEMPLATE_ID), "name": "Holiday week", "block_count": 3},
        {"id": str(DEFAULT_TEMPLATE_ID), "name": "Downtown default week", "block_count": 4},
    ])
    monkeypatch.setattr(week_builder, "_load_roster_context", AsyncMock(return_value={
        "employees": [{
            "id": "employee-1", "name": "Amy", "availability_state": "windows",
            "target_weekly_minutes": 1200, "max_weekly_minutes": 2400,
        }],
    }))

    result = await week_builder.get_week_build_readiness(
        company_id=COMPANY_ID, location_id=LOCATION_ID, week_start=date(2026, 8, 23),
    )

    assert result["default_week_template_id"] is None
    assert any("Choose which saved week template" in b for b in result["blockers"])


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


@pytest.mark.asyncio
async def test_builder_refuses_a_week_that_is_not_the_locations_week_start(monkeypatch):
    """`week_start` IS the first day everywhere downstream (template_windows,
    the demand load, the grid), so a Sunday date for a Monday-start store plans
    a window matching no grid the manager can see."""
    conn = _FakeConn(None)
    _empty_week(monkeypatch, conn, [], week_start_weekday=1)

    result = await week_builder.propose_week_draft(
        company_id=COMPANY_ID, actor_user_id=None, thread_id=None,
        location_id=LOCATION_ID, week_start=date(2026, 8, 23),   # a Sunday
    )

    assert result["status"] == "refused"
    assert "Monday" in result["message"]
    assert "2026-08-17" in result["message"]   # the aligned week it should use


@pytest.mark.asyncio
async def test_readiness_refuses_an_unaligned_week_too(monkeypatch):
    conn = _FakeConn({"id": LOCATION_ID, "name": "Downtown"})
    _empty_week(monkeypatch, conn, [], week_start_weekday=1)
    monkeypatch.setattr(week_builder, "_load_roster_context", AsyncMock(return_value={"employees": []}))

    result = await week_builder.get_week_build_readiness(
        company_id=COMPANY_ID, location_id=LOCATION_ID, week_start=date(2026, 8, 23),
    )

    assert result["status"] == "refused"
    assert "Monday" in result["message"]


@pytest.mark.asyncio
async def test_the_locations_own_week_start_is_accepted(monkeypatch):
    conn = _FakeConn(None)
    _empty_week(monkeypatch, conn, [], week_start_weekday=1)

    result = await week_builder.propose_week_draft(
        company_id=COMPANY_ID, actor_user_id=None, thread_id=None,
        location_id=LOCATION_ID, week_start=date(2026, 8, 24),   # the Monday
    )

    # Falls through to the normal empty-week clarify, not the alignment refusal.
    assert result["status"] == "clarify"


# --- coverage + break findings -------------------------------------------------
#
# The planner reports headcount ("18/18 filled"). These cover the second
# question a manager actually has — is the store covered, and can anyone be
# relieved for a break — which a filled-position count cannot answer.

WEEK_START = date(2026, 8, 23)                      # a Sunday
MONDAY = WEEK_START + timedelta(days=1)
STORE_HOURS = {"1": {"open": "08:00", "close": "17:00"}}


def _profile(**overrides):
    profile = {
        "operating_hours": STORE_HOURS, "open_buffer_minutes": 0,
        "close_buffer_minutes": 0, "leader_job_ids": [], "leader_job_names": [],
    }
    profile.update(overrides)
    return profile


def _demand_shift(start="08:00", end="17:00", *, key="shift-1", required=1, fixed=()):
    starts_at = datetime.fromisoformat(f"{MONDAY.isoformat()}T{start}:00").replace(tzinfo=UTC)
    ends_at = datetime.fromisoformat(f"{MONDAY.isoformat()}T{end}:00").replace(tzinfo=UTC)
    return {
        "key": key, "source_shift_id": key, "role": "Barista", "department": None,
        "starts_at": starts_at, "ends_at": ends_at, "break_minutes": 0,
        "required_staff": required, "color": None, "notes": None, "kind": "work",
        "template_id": None, "job_id": None, "training_requirement_id": None,
        "fixed_employee_ids": list(fixed),
        "worked_minutes": int((ends_at - starts_at).total_seconds() // 60),
    }


def _propose_env(monkeypatch, conn, *, demand, employees=None, profile=None, breaks=None):
    """Everything `propose_week_draft` reads, faked down to the planner."""
    employees = employees if employees is not None else [
        _employee("amy", "Amy", state="windows"),
    ]
    snapshot = {
        "location_id": str(LOCATION_ID), "week_start": WEEK_START.isoformat(),
        "source_mode": "existing", "week_template_id": None, "demand": demand,
        "week_shift_state": [], "employees": employees,
        "availability": {employee["id"]: {} for employee in employees},
        "existing_assignments": [], "unavailable_ranges": {}, "gated_job_ids": set(),
    }
    monkeypatch.setattr(week_builder, "connection_or_direct", lambda: _AsyncContext(conn))
    monkeypatch.setattr(week_builder, "resolve_week_start_weekday", AsyncMock(return_value=0))
    monkeypatch.setattr(week_builder, "_load_existing_demand", AsyncMock(return_value=demand))
    monkeypatch.setattr(
        week_builder, "_week_shift_counts", AsyncMock(return_value={"draft": 1, "published": 0}),
    )
    monkeypatch.setattr(week_builder, "_list_templates", AsyncMock(return_value=[]))
    monkeypatch.setattr(
        week_builder, "_planning_snapshot", AsyncMock(return_value=(snapshot, demand, None)),
    )
    monkeypatch.setattr(
        week_builder, "_preflight_compliance_blocks", AsyncMock(return_value=set()),
    )
    monkeypatch.setattr(
        week_builder, "_coverage_profile", AsyncMock(return_value=profile or _profile()),
    )
    monkeypatch.setattr(
        week_builder, "_break_relief_findings", AsyncMock(return_value=list(breaks or [])),
    )
    return snapshot


async def _propose(monkeypatch, conn, **kwargs):
    _propose_env(monkeypatch, conn, **kwargs)
    return await week_builder.propose_week_draft(
        company_id=COMPANY_ID, actor_user_id=None, thread_id=None,
        location_id=LOCATION_ID, week_start=WEEK_START,
    )


def _persisted_proposal(conn):
    insert = next(call for call in conn.executed if "schedule_generation_runs" in call[0])
    return json.loads(insert[12]), json.loads(insert[13])


@pytest.mark.asyncio
async def test_findings_and_counts_are_persisted_with_the_proposal(monkeypatch):
    """The worker path rebuilds its staged action from `proposal`, never from
    `review` — findings parked anywhere else are invisible on automatic runs."""
    conn = _FakeConn(None)
    # Opens at 09:00 for an 08:00 store: an hour of nobody on.
    result = await _propose(monkeypatch, conn, demand=[_demand_shift("09:00", "17:00")])

    assert result["status"] == "ready"
    proposal, metrics = _persisted_proposal(conn)
    assert [f["kind"] for f in proposal["findings"]] == ["coverage_gap"]
    assert proposal["findings"][0]["minutes"] == 60
    assert metrics["finding_counts"] == {"coverage_gap": 1}
    assert metrics["gap_count"] == 1
    assert metrics["operating_hours_known"] is True
    assert result["findings"] == proposal["findings"]


@pytest.mark.asyncio
async def test_the_summary_names_the_gaps_and_never_claims_compliance(monkeypatch):
    conn = _FakeConn(None)
    result = await _propose(monkeypatch, conn, demand=[_demand_shift("09:00", "17:00")])

    assert "1 coverage/break gap(s)" in result["summary"]
    assert "compliant" not in result["summary"].lower()


@pytest.mark.asyncio
async def test_a_fully_covered_week_says_so_without_the_word_compliant(monkeypatch):
    conn = _FakeConn(None)
    result = await _propose(monkeypatch, conn, demand=[_demand_shift()])

    assert "No coverage gaps found" in result["summary"]
    assert "compliant" not in result["summary"].lower()


@pytest.mark.asyncio
async def test_unknown_hours_say_coverage_was_not_checked(monkeypatch):
    """"No gaps found" and "I could not look" must never read the same."""
    conn = _FakeConn(None)
    result = await _propose(
        monkeypatch, conn, demand=[_demand_shift()],
        profile=_profile(operating_hours={}),
    )

    assert "not saved" in result["summary"]
    assert "coverage at open and close was not checked" in result["summary"]
    assert result["metrics"]["operating_hours_known"] is False


@pytest.mark.asyncio
async def test_the_returned_findings_are_capped_but_the_counts_are_not(monkeypatch):
    """Truncating the list must never make the week look cleaner than it is."""
    conn = _FakeConn(None)
    many = [
        week_builder.make_finding(
            "break_relief_thin", "advisory", f"advisory {index}", day=MONDAY,
        )
        for index in range(30)
    ]
    result = await _propose(
        monkeypatch, conn, demand=[_demand_shift()], breaks=many,
    )

    _proposal, metrics = _persisted_proposal(conn)
    assert metrics["finding_counts"]["break_relief_thin"] == 30
    # ...and the card is not 30 identical amber rows.
    assert len(result["findings"]) == week_builder._MAX_THIN_BREAK_FINDINGS_PER_DAY
    assert metrics["gap_count"] == 0


@pytest.mark.asyncio
async def test_a_week_with_gaps_is_still_ready_to_stage(monkeypatch):
    """The impossible-compliance case: nobody can work the shift and the store
    still has to open. Huume reports it; it does not refuse to produce a week
    the manager can then fix by hand."""
    conn = _FakeConn(None)
    result = await _propose(
        monkeypatch, conn,
        demand=[_demand_shift(required=2)],
        employees=[_employee("amy", "Amy", state="unconfirmed")],
    )

    assert result["status"] == "ready"
    assert result["generation_run_id"]
    assert result["metrics"]["open_positions"] == 2
    assert result["unfilled"][0]["reason"] == "availability unconfirmed"
    assert any(f["kind"] == "coverage_gap" for f in result["findings"])


@pytest.mark.asyncio
async def test_editing_the_profile_after_proposing_does_not_stale_the_run(monkeypatch):
    """`_input_hash` covers the snapshot, and the profile is deliberately NOT
    in it: a manager fixing a buffer minute must not invalidate an otherwise
    good proposal at confirm time."""
    conn = _FakeConn(None)
    snapshot = _propose_env(monkeypatch, conn, demand=[_demand_shift()])

    await week_builder.propose_week_draft(
        company_id=COMPANY_ID, actor_user_id=None, thread_id=None,
        location_id=LOCATION_ID, week_start=WEEK_START,
    )

    # The guard is structural: nothing the profile owns may be in the hashed
    # snapshot, or a buffer edit becomes "the schedule changed, rebuild it".
    assert not {
        "operating_hours", "open_buffer_minutes", "close_buffer_minutes",
        "leader_job_id", "leader_job_ids", "findings",
    } & set(snapshot)
    # And the real builder reads the profile through its own helper, which
    # `apply_week_draft`'s staleness check never calls.
    module_source = inspect.getsource(week_builder)
    body = module_source[module_source.index("async def _planning_snapshot"):]
    body = body[:body.index("async def get_week_build_readiness")]
    assert "_coverage_profile" not in body and "get_location_profile" not in body


@pytest.mark.asyncio
async def test_readiness_reports_pattern_holes_without_blocking_the_build(monkeypatch):
    """A hole in the pattern is something to fix in the interview, not a reason
    to refuse — refusing is the dead end this whole surface exists to end."""
    conn = _FakeConn({"id": LOCATION_ID, "name": "Downtown"})
    _empty_week(monkeypatch, conn, [
        {"id": str(DEFAULT_TEMPLATE_ID), "name": "Downtown default week", "block_count": 2},
    ])
    monkeypatch.setattr(week_builder, "_load_roster_context", AsyncMock(return_value={
        "employees": [{
            "id": "employee-1", "name": "Amy", "availability_state": "windows",
            "target_weekly_minutes": 1200, "max_weekly_minutes": 2400,
        }],
    }))
    monkeypatch.setattr(
        week_builder, "_load_existing_demand",
        AsyncMock(return_value=[_demand_shift("09:00", "17:00")]),
    )
    monkeypatch.setattr(
        week_builder, "_coverage_profile",
        AsyncMock(return_value=_profile(open_buffer_minutes=30)),
    )

    result = await week_builder.get_week_build_readiness(
        company_id=COMPANY_ID, location_id=LOCATION_ID, week_start=WEEK_START,
    )

    kinds = [finding["kind"] for finding in result["pattern_findings"]]
    assert "open_buffer_uncovered" in kinds and "coverage_gap" in kinds
    assert result["operating_hours_known"] is True
    assert result["open_buffer_minutes"] == 30
    assert result["ready"] is True
    assert result["blockers"] == []


@pytest.mark.asyncio
async def test_readiness_says_when_hours_were_never_saved(monkeypatch):
    conn = _FakeConn({"id": LOCATION_ID, "name": "Downtown"})
    _empty_week(monkeypatch, conn, [])
    monkeypatch.setattr(week_builder, "_load_roster_context", AsyncMock(return_value={
        "employees": [{
            "id": "employee-1", "name": "Amy", "availability_state": "windows",
            "target_weekly_minutes": 1200, "max_weekly_minutes": 2400,
        }],
    }))
    monkeypatch.setattr(
        week_builder, "_coverage_profile", AsyncMock(return_value=_profile(operating_hours={})),
    )

    result = await week_builder.get_week_build_readiness(
        company_id=COMPANY_ID, location_id=LOCATION_ID, week_start=WEEK_START,
    )

    assert result["operating_hours_known"] is False
    assert result["pattern_findings"] == []


# --- break relief --------------------------------------------------------------
#
# `stagger_shift_breaks` is pure, so this runs on the in-memory plan: nothing
# has to be written before a manager can be told the crew cannot be relieved.

BREAK_EMPLOYEE = UUID("3f6b1c22-2000-4000-8000-0000000000b1")
SECOND_EMPLOYEE = UUID("3f6b1c22-2000-4000-8000-0000000000b2")


def _break_plan(*, duration=30, earliest=11, deadline=14, status="complete"):
    from app.matcha.services.scheduling.schedule_breaks import BreakPlan, BreakRequirement
    rule_set = UUID("00000000-0000-0000-0000-0000000000ff")
    return BreakPlan(
        status=status,
        requirements=(BreakRequirement(
            kind="meal", ordinal=1, duration_minutes=duration, paid=False,
            earliest_local=datetime(2026, 8, 24, earliest, tzinfo=UTC),
            recommended_local=datetime(2026, 8, 24, earliest + 1, tzinfo=UTC),
            deadline_local=datetime(2026, 8, 24, deadline, tzinfo=UTC),
            waived=False, waiver_attestation_id=None, citation="Cal. Lab. Code § 512",
            rule_set_id=rule_set,
        ),),
        advisories=(), rule_set_ids=(rule_set,), rule_set_hash="hash",
    )


def _plan_with(employee_ids, *, required=1):
    shift = _demand_shift()
    return {
        "shifts": [{
            **{k: v for k, v in shift.items() if k != "fixed_employee_ids"},
            "starts_at": shift["starts_at"].isoformat(),
            "ends_at": shift["ends_at"].isoformat(),
            "required_staff": required,
            "fixed_employee_ids": [],
            "proposed_assignments": [
                {"employee_id": str(value), "employee_name": f"Person {index}"}
                for index, value in enumerate(employee_ids)
            ],
        }],
    }


def _patch_break_loader(monkeypatch, plans, *, unmapped=frozenset()):
    from zoneinfo import ZoneInfo
    monkeypatch.setattr(
        week_builder, "resolve_week_break_plans",
        AsyncMock(return_value=(ZoneInfo("UTC"), plans, set(unmapped))),
    )


@pytest.mark.asyncio
async def test_a_solo_shift_that_owes_a_break_is_a_gap_not_an_advisory(monkeypatch):
    """One person on means the break empties the floor. That is a hole, and it
    is the case a filled-position count is completely blind to."""
    plan = _plan_with([BREAK_EMPLOYEE])
    _patch_break_loader(monkeypatch, {"shift-1": {BREAK_EMPLOYEE: _break_plan()}})

    findings = await week_builder._break_relief_findings(
        object(), company_id=COMPANY_ID, location_id=LOCATION_ID, plan=plan,
        employee_names={str(BREAK_EMPLOYEE): "Amy"},
    )

    assert [f["kind"] for f in findings] == ["break_relief_uncovered"]
    assert findings[0]["severity"] == "gap"
    assert "Amy" in findings[0]["detail"]
    assert findings[0]["kind"] in week_builder.GAP_KINDS


@pytest.mark.asyncio
async def test_a_normally_staffed_shift_is_only_an_advisory(monkeypatch):
    """`coverage_shortfall` fires on nearly every real shift. Reporting each as
    a gap would bury the holes that matter."""
    plan = _plan_with([BREAK_EMPLOYEE, SECOND_EMPLOYEE], required=2)
    _patch_break_loader(monkeypatch, {"shift-1": {
        BREAK_EMPLOYEE: _break_plan(), SECOND_EMPLOYEE: _break_plan(),
    }})

    findings = await week_builder._break_relief_findings(
        object(), company_id=COMPANY_ID, location_id=LOCATION_ID, plan=plan,
        employee_names={},
    )

    assert [f["kind"] for f in findings] == ["break_relief_thin"]
    assert findings[0]["severity"] == "advisory"
    assert findings[0]["kind"] not in week_builder.GAP_KINDS


@pytest.mark.asyncio
async def test_a_break_that_cannot_fit_its_window_is_reported_with_the_reason(monkeypatch):
    plan = _plan_with([BREAK_EMPLOYEE])
    # A 30-minute meal owed inside an 11:00-11:10 window cannot be taken.
    _patch_break_loader(monkeypatch, {"shift-1": {
        BREAK_EMPLOYEE: _break_plan(duration=30, earliest=11, deadline=11),
    }})

    findings = await week_builder._break_relief_findings(
        object(), company_id=COMPANY_ID, location_id=LOCATION_ID, plan=plan,
        employee_names={str(BREAK_EMPLOYEE): "Amy"},
    )

    kinds = {f["kind"] for f in findings}
    assert "break_window_conflict" in kinds
    conflict = next(f for f in findings if f["kind"] == "break_window_conflict")
    assert "deadline" in conflict["detail"] or "does not fit" in conflict["detail"]


@pytest.mark.asyncio
async def test_unmapped_break_rules_are_surfaced_once_not_swallowed(monkeypatch):
    """A jurisdiction with nothing in the catalog must never read as
    "no breaks required"."""
    plan = _plan_with([BREAK_EMPLOYEE])
    _patch_break_loader(
        monkeypatch, {"shift-1": {BREAK_EMPLOYEE: _break_plan(status="unmapped")}},
        unmapped={date(2026, 8, 24)},
    )

    findings = await week_builder._break_relief_findings(
        object(), company_id=COMPANY_ID, location_id=LOCATION_ID, plan=plan,
        employee_names={},
    )

    unmapped = [f for f in findings if f["kind"] == "break_rules_unmapped"]
    assert len(unmapped) == 1
    assert "2026-08-24" in unmapped[0]["detail"]


@pytest.mark.asyncio
async def test_an_unstaffed_shift_owes_no_break_relief(monkeypatch):
    plan = _plan_with([])
    loader = AsyncMock()
    monkeypatch.setattr(week_builder, "resolve_week_break_plans", loader)

    assert await week_builder._break_relief_findings(
        object(), company_id=COMPANY_ID, location_id=LOCATION_ID, plan=plan,
        employee_names={},
    ) == []
    loader.assert_not_awaited()


@pytest.mark.asyncio
async def test_a_failing_break_loader_never_fails_the_build(monkeypatch):
    """Same contract as the compliance preflight: a findings pass that can take
    down a build is worse than the silence it replaces."""
    plan = _plan_with([BREAK_EMPLOYEE])
    monkeypatch.setattr(
        week_builder, "resolve_week_break_plans", AsyncMock(side_effect=RuntimeError("boom")),
    )

    assert await week_builder._break_relief_findings(
        object(), company_id=COMPANY_ID, location_id=LOCATION_ID, plan=plan,
        employee_names={},
    ) == []


@pytest.mark.asyncio
async def test_a_findings_pass_that_blows_up_does_not_fail_the_build(monkeypatch):
    """The guard covers the WHOLE pass, not just its break half: a profile read
    that raises used to turn a week that built fine into a failed Huume turn."""
    conn = _FakeConn(None)
    _propose_env(monkeypatch, conn, demand=[_demand_shift()])
    monkeypatch.setattr(
        week_builder, "_coverage_profile", AsyncMock(side_effect=RuntimeError("boom")),
    )

    result = await week_builder.propose_week_draft(
        company_id=COMPANY_ID, actor_user_id=None, thread_id=None,
        location_id=LOCATION_ID, week_start=WEEK_START,
    )

    assert result["status"] == "ready"
    assert result["findings"] == []
    # ...and it says coverage was NOT checked, never that the week came back clean.
    assert result["metrics"]["operating_hours_known"] is False
    assert "was not checked" in result["summary"]


@pytest.mark.asyncio
async def test_the_cap_keeps_gaps_over_advisories_whatever_day_they_fall_on(monkeypatch):
    """The list is sorted day-then-time, so a plain slice would drop Saturday's
    real holes to make room for Sunday's advisories."""
    conn = _FakeConn(None)
    saturday = WEEK_START + timedelta(days=6)
    advisories = [
        week_builder.make_finding(
            "break_window_conflict", "advisory", f"advisory {index}",
            day=WEEK_START, shift_key=f"sun-{index}",
        )
        for index in range(week_builder._MAX_FINDINGS + 5)
    ]
    gaps = [
        week_builder.make_finding(
            "break_relief_impossible", "gap", f"gap {index}",
            day=saturday, shift_key=f"sat-{index}",
        )
        for index in range(3)
    ]
    result = await _propose(
        monkeypatch, conn, demand=[_demand_shift()], breaks=[*advisories, *gaps],
    )

    # Both boundaries truncate — the persisted list and the shorter one echoed
    # back — and the Saturday gaps have to survive each of them.
    kinds = [finding["kind"] for finding in result["findings"]]
    assert kinds.count("break_relief_impossible") == 3
    assert len(result["findings"]) == week_builder._FINDINGS_RETURNED

    proposal, metrics = _persisted_proposal(conn)
    persisted = [finding["kind"] for finding in proposal["findings"]]
    assert persisted.count("break_relief_impossible") == 3
    assert len(proposal["findings"]) == week_builder._MAX_FINDINGS
    # Counts stay uncapped, so the week never reads cleaner than it is.
    assert metrics["gap_count"] == 3

    # The kept set is still in day order for the card.
    days = [finding["day"] for finding in result["findings"]]
    assert days == sorted(days)


@pytest.mark.asyncio
async def test_a_break_plan_that_never_resolved_for_one_person_is_still_reported(monkeypatch):
    """No date of birth against age-specific rules errors the plan for that
    person alone, so the date never lands in `unmapped_dates`. The unresolved
    requirement places no slot either, which silences the coverage advisory —
    a solo shift owing a meal break would otherwise report NOTHING."""
    plan = _plan_with([BREAK_EMPLOYEE])
    _patch_break_loader(
        monkeypatch, {"shift-1": {BREAK_EMPLOYEE: _break_plan(status="error")}},
    )

    findings = await week_builder._break_relief_findings(
        object(), company_id=COMPANY_ID, location_id=LOCATION_ID, plan=plan,
        employee_names={str(BREAK_EMPLOYEE): "Amy"},
    )

    assert [f["kind"] for f in findings] == ["break_rules_unresolved"]
    assert findings[0]["severity"] == "advisory"
    assert "Amy" in findings[0]["detail"]
    assert findings[0]["minutes"] == 30


@pytest.mark.asyncio
async def test_an_unresolved_plan_is_not_said_twice_on_an_unmapped_date(monkeypatch):
    """`break_rules_unmapped` already says it once for the whole date."""
    plan = _plan_with([BREAK_EMPLOYEE])
    _patch_break_loader(
        monkeypatch, {"shift-1": {BREAK_EMPLOYEE: _break_plan(status="unmapped")}},
        unmapped={date(2026, 8, 24)},
    )

    findings = await week_builder._break_relief_findings(
        object(), company_id=COMPANY_ID, location_id=LOCATION_ID, plan=plan,
        employee_names={},
    )

    assert [f["kind"] for f in findings] == ["break_rules_unmapped"]


# --- input-hash stability across process restarts -----------------------------
#
# Real bug, found live: `_input_hash` must give the SAME answer for the SAME
# underlying data no matter which process computed it. `gated_job_ids` is a
# python `set`, and set iteration order depends on the process's string-hash
# seed (randomized fresh per process start unless PYTHONHASHSEED is pinned).
# `json.dumps(..., sort_keys=True)` only orders dict KEYS, never list
# elements, so an unsorted set-to-list conversion made every confirm racy
# against a dev --reload or a propose/confirm pair landing on different prod
# workers: nothing about the schedule changed, but the hash did, and
# apply_week_draft reported "the schedule changed after this proposal was
# built" on a perfectly good proposal.

def test_input_hash_does_not_depend_on_set_iteration_order():
    """Two sets holding the same job ids, built in different orders (the
    closest same-process proxy for "a different hash seed" — see the
    subprocess proof in the PR/commit for the real cross-seed repro)."""
    built_one_way = {"job-3", "job-1", "job-2"}
    built_another_way = {"job-1", "job-2", "job-3"}
    assert list(built_one_way) != list(built_another_way) or True  # not asserted; sets are unordered by design

    snapshot_a = {"gated_job_ids": built_one_way, "week_start": "2026-08-23"}
    snapshot_b = {"gated_job_ids": built_another_way, "week_start": "2026-08-23"}

    assert week_builder._input_hash(snapshot_a) == week_builder._input_hash(snapshot_b)


def test_iso_serializes_a_set_as_a_sorted_list():
    """Sorted, not just "some list" — the exact ordering has to be
    reproducible, not merely consistent within one accidental run."""
    assert week_builder._iso({"a", "c", "b"}) == ["a", "b", "c"]


# ── policy guardrails + fairness (2026-09-07) ───────────────────────────────
# The reported failure: one leader-job holder, one leader block per open day,
# scarcity-first → that person on every block. `build_plan` now refuses a
# second shift the same day, under-8h rest and a 7th consecutive day as
# `policy:` reasons, and spreads equal work by shift count before minutes.

def _shift_at(key, day, start_hour, end_hour, *, job_id="lead", required=1):
    item = _shift(key, day, job_id=job_id, required=required)
    item["role"] = "Shift Lead"
    item["starts_at"] = datetime(2026, 8, day, start_hour, tzinfo=UTC)
    item["ends_at"] = datetime(2026, 8, day, end_hour, tzinfo=UTC)
    item["worked_minutes"] = (end_hour - start_hour) * 60
    return item


def _existing(employee_id, day, start_hour, end_hour):
    starts = datetime(2026, 8, day, start_hour, tzinfo=UTC)
    ends = datetime(2026, 8, day, end_hour, tzinfo=UTC)
    return {"employee_id": employee_id, "shift_id": f"db-{day}-{start_hour}", "starts_at": starts,
            "ends_at": ends, "worked_minutes": (end_hour - start_hour) * 60,
            "location_id": None, "status": "published"}


def _lead(employee_id, name, **overrides):
    employee = _employee(employee_id, name, jobs=[{
        "job_id": "lead", "qualification_status": "active", "qualified_from": None, "qualified_until": None,
    }])
    employee.update(overrides)
    return employee


def _picks(plan):
    return {shift["key"]: [item["employee_id"] for item in shift["proposed_assignments"]] for shift in plan["shifts"]}


def test_a_second_shift_the_same_day_is_a_policy_refusal_with_its_reason():
    dana = _lead("e1", "Dana")
    demand = [_shift_at("open", 24, 6, 14), _shift_at("close", 24, 14, 22)]
    plan = _plan(demand=demand, employees=[dana], availability={})
    assert plan["metrics"]["filled_positions"] == 1
    assert plan["unfilled"] == [{
        "shift_key": "close", "starts_at": "2026-08-24T14:00:00+00:00", "role": "Shift Lead",
        "reason": "policy: second shift that day", "exclusions": {"policy: second shift that day": 1},
    }]
    assert plan["hours_by_employee"] == {"e1": 480}


def test_a_manager_who_allowed_splits_gets_the_double_and_the_rest_rule_still_holds_across_days():
    dana = _lead("e1", "Dana")
    demand = [_shift_at("am", 24, 6, 10), _shift_at("pm", 24, 16, 20), _shift_at("early", 25, 2, 8)]
    strict = _plan(demand=demand, employees=[dana], availability={})
    assert _picks(strict) == {"am": ["e1"], "pm": [], "early": ["e1"]}
    relaxed = build_plan(
        demand=demand, employees=[dana], availability={}, existing_assignments=[], unavailable_ranges={},
        exclude_employee_ids=set(), employee_hour_caps={}, gated_job_ids={"lead"}, allow_split_shift=True,
    )
    # The split day fills; the 02:00 start six hours after the 20:00 finish
    # is a between-days rest breach and stays refused.
    assert _picks(relaxed) == {"am": ["e1"], "pm": ["e1"], "early": []}
    assert relaxed["unfilled"][0]["reason"] == "policy: less than 8h rest"


def test_under_eight_hours_rest_after_an_existing_shift_is_refused_and_eight_is_allowed():
    dana = _lead("e1", "Dana")
    existing = [_existing("e1", 23, 14, 22)]
    too_soon = _plan(demand=[_shift_at("s", 24, 4, 12)], employees=[dana], availability={}, existing=existing)
    assert too_soon["unfilled"][0]["reason"] == "policy: less than 8h rest"
    just_enough = _plan(demand=[_shift_at("s", 24, 6, 14)], employees=[dana], availability={}, existing=existing)
    assert _picks(just_enough) == {"s": ["e1"]}


def test_seventh_consecutive_day_uses_the_policy_default_when_the_profile_has_no_cap():
    existing = [_existing("e1", day, 9, 13) for day in range(17, 23)]  # six days in a row
    no_cap = _lead("e1", "Dana", max_consecutive_days=None)
    refused = _plan(demand=[_shift_at("s", 23, 9, 13)], employees=[no_cap], availability={}, existing=existing)
    assert refused["unfilled"][0]["reason"] == "maximum consecutive days"
    seven_ok = _lead("e1", "Dana", max_consecutive_days=7)
    allowed = _plan(demand=[_shift_at("s", 23, 9, 13)], employees=[seven_ok], availability={}, existing=existing)
    assert _picks(allowed) == {"s": ["e1"]}


def test_two_leads_split_seven_leader_blocks_instead_of_stacking_one():
    ana, ben = _lead("e1", "Ana"), _lead("e2", "Ben")
    demand = [_shift_at(f"d{day}", day, 9, 13) for day in range(23, 30)]
    plan = _plan(demand=demand, employees=[ana, ben], availability={})
    picks = [item[0] for item in _picks(plan).values()]
    assert plan["unfilled"] == []
    assert sorted((picks.count("e1"), picks.count("e2"))) == [3, 4]
    assert plan["hours_by_employee"] == {"e1": 960, "e2": 720}


def test_fewer_shifts_this_week_wins_before_fewer_minutes():
    # Ana holds two short shifts (2h total); Ben holds one long one (5h).
    # Minutes-first would pick Ana again; the shift-count key picks Ben.
    ana = _lead("e1", "Ana", target_weekly_minutes=None)
    ben = _lead("e2", "Ben", target_weekly_minutes=None)
    existing = [_existing("e1", 17, 9, 10), _existing("e1", 18, 9, 10), _existing("e2", 19, 9, 14)]
    plan = _plan(demand=[_shift_at("s", 24, 9, 13)], employees=[ana, ben], availability={}, existing=existing)
    assert _picks(plan) == {"s": ["e2"]}


def test_a_single_lead_gets_one_block_a_day_and_the_rest_stay_open_with_policy_reasons():
    dana = _lead("e1", "Dana")
    demand = []
    for day in (23, 24, 25):
        demand += [_shift_at(f"am{day}", day, 6, 14), _shift_at(f"pm{day}", day, 14, 22)]
    plan = _plan(demand=demand, employees=[dana], availability={})
    picks = _picks(plan)
    assert all(picks[f"am{day}"] == ["e1"] for day in (23, 24, 25))
    assert all(picks[f"pm{day}"] == [] for day in (23, 24, 25))
    assert {item["reason"] for item in plan["unfilled"]} == {"policy: second shift that day"}
    assert plan["metrics"] == {
        "shift_count": 6, "required_positions": 6, "fixed_positions": 0, "overstaffed_positions": 0,
        "proposed_positions": 3, "filled_positions": 3, "open_positions": 3,
    }
    assert plan["hours_by_employee"] == {"e1": 1440}
