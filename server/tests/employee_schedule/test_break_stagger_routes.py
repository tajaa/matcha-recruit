"""Route boundaries for break staggering: tenant scoping, persistence, audit.

Fake connections throughout — none of these touch a database.
"""

import asyncio
import json
from datetime import datetime, timezone
from types import SimpleNamespace
from uuid import uuid4

import pytest
from fastapi import HTTPException

from app.matcha.models.scheduling.employee_schedule import (
    AssignmentBreakPlanUpdate, PlannedBreak,
)
from app.matcha.routes.employee_schedule import assignments as assignments_route
from app.matcha.routes.employee_schedule import shifts as shifts_route
from app.matcha.services.scheduling import schedule_guidance
from app.matcha.services.scheduling.schedule_breaks import BreakPlan, BreakRequirement


def _run(coro):
    return asyncio.run(coro)


def _user():
    return SimpleNamespace(id=uuid4(), role="client")


class _ConnectionContext:
    def __init__(self, conn):
        self._conn = conn

    async def __aenter__(self):
        return self._conn

    async def __aexit__(self, *_exc):
        return False


class _Transaction:
    async def __aenter__(self):
        return None

    async def __aexit__(self, *_exc):
        return False


# ── GET /shifts/{id}/break-stagger ────────────────────────────────────────────


def _requirement() -> BreakRequirement:
    return BreakRequirement(
        kind="meal", ordinal=1, duration_minutes=30, paid=False,
        earliest_local=None, recommended_local=None, deadline_local=None,
        waived=False, waiver_attestation_id=None, citation="",
        rule_set_id=uuid4(),
    )


class _StaggerConnection:
    """A shift the caller's company owns, with two assignees."""

    def __init__(self, *, shift_found=True, planned=None):
        self.shift_found = shift_found
        self.employee_ids = [uuid4(), uuid4()]
        self.planned = planned or {}

    async def fetchrow(self, _query, *_args):
        if not self.shift_found:
            return None
        return {
            "location_id": None,
            "starts_at": datetime(2026, 8, 21, 9, tzinfo=timezone.utc),
            "ends_at": datetime(2026, 8, 21, 17, tzinfo=timezone.utc),
            "required_staff": 2,
        }

    async def fetch(self, query, *_args):
        assert "schedule_shift_assignments" in query
        assert "company_id" in query, "assignment read must be tenant-scoped"
        return [
            {
                "employee_id": employee_id,
                "planned_breaks": self.planned.get(employee_id),
            }
            for employee_id in self.employee_ids
        ]


def test_stagger_route_404s_for_a_shift_another_tenant_owns(monkeypatch):
    conn = _StaggerConnection(shift_found=False)

    async def fake_require_company_id(_user):
        return uuid4()

    monkeypatch.setattr(shifts_route, "require_company_id", fake_require_company_id)
    monkeypatch.setattr(shifts_route, "get_connection", lambda: _ConnectionContext(conn))

    with pytest.raises(HTTPException) as exc:
        _run(shifts_route.get_shift_break_stagger(uuid4(), current_user=_user()))
    assert exc.value.status_code == 404


def test_stagger_route_returns_a_suggestion_per_assignee(monkeypatch):
    conn = _StaggerConnection()

    async def fake_require_company_id(_user):
        return uuid4()

    async def fake_plans(*_args, **kwargs):
        from zoneinfo import ZoneInfo
        plan = BreakPlan(
            status="complete", requirements=(_requirement(),), advisories=(),
            rule_set_ids=(uuid4(),), rule_set_hash="hash",
        )
        return ZoneInfo("UTC"), {
            employee_id: plan for employee_id in kwargs["employee_ids"]
        }

    monkeypatch.setattr(shifts_route, "require_company_id", fake_require_company_id)
    monkeypatch.setattr(shifts_route, "get_connection", lambda: _ConnectionContext(conn))
    # Patch the module that DEFINES the caller, not the route's re-export.
    monkeypatch.setattr(
        schedule_guidance, "resolve_shift_break_plans_localized", fake_plans,
    )

    payload = _run(shifts_route.get_shift_break_stagger(uuid4(), current_user=_user()))

    assert payload["max_concurrent_breaks"] == 1
    assert len(payload["results"]) == 2
    assert {result["status"] for result in payload["results"]} == {"suggested"}
    starts = sorted(result["suggested_start"] for result in payload["results"])
    assert starts[0] != starts[1], "two assignees must not be sent on break together"


def test_stagger_route_treats_a_saved_time_as_fixed(monkeypatch):
    """A reviewed time is real state; everyone else is placed around it."""
    conn = _StaggerConnection()
    saved_employee = conn.employee_ids[0]
    conn.planned = {saved_employee: json.dumps([{
        "kind": "meal", "ordinal": 1,
        "start_local": "2026-08-21T13:00:00+00:00",
        "duration_minutes": 30, "source": "manager",
    }])}

    async def fake_require_company_id(_user):
        return uuid4()

    async def fake_plans(*_args, **kwargs):
        from zoneinfo import ZoneInfo
        plan = BreakPlan(
            status="complete", requirements=(_requirement(),), advisories=(),
            rule_set_ids=(uuid4(),), rule_set_hash="hash",
        )
        return ZoneInfo("UTC"), {
            employee_id: plan for employee_id in kwargs["employee_ids"]
        }

    monkeypatch.setattr(shifts_route, "require_company_id", fake_require_company_id)
    monkeypatch.setattr(shifts_route, "get_connection", lambda: _ConnectionContext(conn))
    monkeypatch.setattr(
        schedule_guidance, "resolve_shift_break_plans_localized", fake_plans,
    )

    payload = _run(shifts_route.get_shift_break_stagger(uuid4(), current_user=_user()))

    by_employee = {result["employee_id"]: result for result in payload["results"]}
    saved = by_employee[str(saved_employee)]
    assert saved["status"] == "saved"
    assert saved["suggested_start"].startswith("2026-08-21T13:00:00")
    other = next(
        result for key, result in by_employee.items() if key != str(saved_employee)
    )
    # Not re-suggested on top of the time the other person will actually take.
    assert other["suggested_start"] != saved["suggested_start"]


# ── PUT /shifts/{id}/assignments/{employee_id}/break-plan ─────────────────────


class _BreakPlanConnection:
    def __init__(self, *, found=True, before=None):
        self.found = found
        self.before = before
        self.updates = []
        self.audits = []

    def transaction(self):
        return _Transaction()

    async def fetchrow(self, query, *_args):
        assert "FOR UPDATE" in query
        assert "s.company_id" in query, "assignment lookup must be tenant-scoped"
        if not self.found:
            return None
        return {
            "planned_breaks": self.before,
            "location_id": None,
            "starts_at": datetime(2026, 8, 21, 9, tzinfo=timezone.utc),
            "ends_at": datetime(2026, 8, 21, 17, tzinfo=timezone.utc),
        }

    async def execute(self, query, *args):
        normalized = " ".join(query.split())
        if normalized.startswith("UPDATE schedule_shift_assignments"):
            self.updates.append(args)
        elif normalized.startswith("INSERT INTO schedule_audit_log"):
            self.audits.append((args[4], json.loads(args[5])))
        else:
            raise AssertionError(f"unexpected execute: {normalized}")
        return "UPDATE 1"


def _break_plan_body():
    return AssignmentBreakPlanUpdate(planned_breaks=[PlannedBreak(
        kind="meal", ordinal=1,
        start_local=datetime(2026, 8, 21, 12, tzinfo=timezone.utc),
        duration_minutes=30, source="manager",
    )])


def _patch_break_plan_route(monkeypatch, conn, *, requirements=None):
    async def fake_require_company_id(_user):
        return uuid4()

    async def fake_fetch_shift_by_id(*_args):
        return {"id": "shift"}

    async def fake_resolve_plan(*_args, **_kwargs):
        return BreakPlan(
            status="complete",
            requirements=tuple(
                (_requirement(),) if requirements is None else requirements
            ),
            advisories=(), rule_set_ids=(uuid4(),), rule_set_hash="hash",
        )

    monkeypatch.setattr(assignments_route, "require_company_id", fake_require_company_id)
    monkeypatch.setattr(assignments_route, "get_connection", lambda: _ConnectionContext(conn))
    monkeypatch.setattr(assignments_route, "fetch_shift_by_id", fake_fetch_shift_by_id)
    # Patch the module that DEFINES the caller, not schedule_guidance itself.
    monkeypatch.setattr(assignments_route, "resolve_shift_break_plan", fake_resolve_plan)


def test_break_plan_404s_when_the_assignment_is_not_the_callers(monkeypatch):
    conn = _BreakPlanConnection(found=False)
    _patch_break_plan_route(monkeypatch, conn)

    with pytest.raises(HTTPException) as exc:
        _run(assignments_route.update_assignment_break_plan(
            uuid4(), uuid4(), _break_plan_body(), current_user=_user(),
        ))
    assert exc.value.status_code == 404
    assert conn.updates == []


def test_break_plan_persists_and_writes_one_audit_row(monkeypatch):
    conn = _BreakPlanConnection(before=json.dumps([{"kind": "meal", "ordinal": 1}]))
    _patch_break_plan_route(monkeypatch, conn)
    employee_id = uuid4()

    _run(assignments_route.update_assignment_break_plan(
        uuid4(), employee_id, _break_plan_body(), current_user=_user(),
    ))

    assert len(conn.updates) == 1
    stored = json.loads(conn.updates[0][0])
    assert stored[0]["kind"] == "meal"
    assert stored[0]["duration_minutes"] == 30
    assert stored[0]["start_local"].startswith("2026-08-21T12:00:00")

    assert len(conn.audits) == 1
    action, details = conn.audits[0]
    assert action == "assignment.break_plan.update"
    assert details["employee_id"] == str(employee_id)
    # The previous value is decoded, not echoed back as a JSON string.
    assert details["before"] == [{"kind": "meal", "ordinal": 1}]
    assert details["after"][0]["ordinal"] == 1


def test_break_plan_clears_with_a_null_body(monkeypatch):
    conn = _BreakPlanConnection(before=json.dumps([{"kind": "meal", "ordinal": 1}]))
    _patch_break_plan_route(monkeypatch, conn)

    _run(assignments_route.update_assignment_break_plan(
        uuid4(), uuid4(), AssignmentBreakPlanUpdate(planned_breaks=None),
        current_user=_user(),
    ))

    assert conn.updates[0][0] is None
    assert conn.audits[0][1]["after"] is None


# ── the PUT is validated against the shift, not just typed ────────────────────


def _body(*entries):
    return AssignmentBreakPlanUpdate(planned_breaks=[
        PlannedBreak(**entry) for entry in entries
    ])


def _entry(**overrides):
    values = {
        "kind": "meal", "ordinal": 1,
        "start_local": datetime(2026, 8, 21, 12, tzinfo=timezone.utc),
        "duration_minutes": 30, "source": "manager",
    }
    values.update(overrides)
    return values


@pytest.mark.parametrize("entries, fragment", [
    # Two rows for one (kind, ordinal): a keyed .find only ever reads the
    # first, so the second would be unreachable and uneditable forever.
    (( _entry(), _entry(start_local=datetime(2026, 8, 21, 13, tzinfo=timezone.utc)) ),
     "Duplicate"),
    # No such requirement on this shift.
    ((_entry(ordinal=2),), "not a required"),
    # 03:00 on a 09:00-17:00 shift — what the employee portal would render.
    ((_entry(start_local=datetime(2026, 8, 21, 3, tzinfo=timezone.utc)),),
     "before the shift"),
    # 480 minutes from noon runs off the end of the shift.
    ((_entry(duration_minutes=480),), "past the end"),
    # Shorter than the legal requirement it claims to satisfy.
    ((_entry(duration_minutes=10),), "at least 30 minutes"),
])
def test_break_plan_422s_on_an_unsaveable_entry(monkeypatch, entries, fragment):
    conn = _BreakPlanConnection()
    _patch_break_plan_route(monkeypatch, conn)

    with pytest.raises(HTTPException) as exc:
        _run(assignments_route.update_assignment_break_plan(
            uuid4(), uuid4(), _body(*entries), current_user=_user(),
        ))
    assert exc.value.status_code == 422
    assert fragment in exc.value.detail
    assert conn.updates == [], "a rejected plan must not be written"


def test_break_plan_422s_when_the_requirement_is_waived(monkeypatch):
    """A waiver is exactly when a saved meal break stops being an answer."""
    conn = _BreakPlanConnection()
    waived = BreakRequirement(
        kind="meal", ordinal=1, duration_minutes=30, paid=False,
        earliest_local=None, recommended_local=None, deadline_local=None,
        waived=True, waiver_attestation_id=uuid4(), citation="",
        rule_set_id=uuid4(),
    )
    _patch_break_plan_route(monkeypatch, conn, requirements=(waived,))

    with pytest.raises(HTTPException) as exc:
        _run(assignments_route.update_assignment_break_plan(
            uuid4(), uuid4(), _body(_entry()), current_user=_user(),
        ))
    assert exc.value.status_code == 422
    assert conn.updates == []


# ── the guidance refresh prunes saved times it has invalidated ────────────────


class _RefreshConnection:
    """One assignment row with a saved break time already on it."""

    def __init__(self, saved):
        self.saved = saved
        self.writes = []

    async def fetchval(self, query, *_args):
        assert "RETURNING planned_breaks" in query
        return self.saved

    async def execute(self, query, *args):
        assert "SET planned_breaks" in " ".join(query.split())
        self.writes.append(args[0])
        return "UPDATE 1"


def _refresh(conn, *, start_hour, end_hour, requirements):
    return _run(schedule_guidance.refresh_assignment_break_guidance(
        conn, uuid4(), shift_id=uuid4(), employee_id=uuid4(),
        location_id=uuid4(),
        starts_at=datetime(2026, 8, 21, start_hour, tzinfo=timezone.utc),
        ends_at=datetime(2026, 8, 21, end_hour, tzinfo=timezone.utc),
        plan=BreakPlan(
            status="complete", requirements=tuple(requirements), advisories=(),
            rule_set_ids=(uuid4(),), rule_set_hash="hash",
        ),
        timezone_name="America/Los_Angeles",
    ))


def _saved_noon():
    return json.dumps([{
        "kind": "meal", "ordinal": 1,
        "start_local": "2026-08-21T12:00:00-07:00",
        "duration_minutes": 30, "source": "manager",
    }])


def test_refresh_leaves_a_still_valid_saved_time_alone():
    conn = _RefreshConnection(_saved_noon())
    _refresh(conn, start_hour=9, end_hour=17, requirements=(_requirement(),))
    assert conn.writes == [], "an unchanged plan must not be rewritten"


def test_refresh_prunes_a_saved_time_the_retimed_shift_dropped():
    # 09:00-17:00 becomes 18:00-23:00; the employee portal would otherwise keep
    # telling this person to take a noon break on an evening shift.
    conn = _RefreshConnection(_saved_noon())
    _refresh(conn, start_hour=18, end_hour=23, requirements=(_requirement(),))
    assert conn.writes == [None]


def test_refresh_prunes_a_saved_time_whose_requirement_was_waived():
    waived = BreakRequirement(
        kind="meal", ordinal=1, duration_minutes=30, paid=False,
        earliest_local=None, recommended_local=None, deadline_local=None,
        waived=True, waiver_attestation_id=uuid4(), citation="",
        rule_set_id=uuid4(),
    )
    conn = _RefreshConnection(_saved_noon())
    _refresh(conn, start_hour=9, end_hour=17, requirements=(waived,))
    assert conn.writes == [None]


def test_refresh_does_not_read_back_when_nothing_was_ever_saved():
    conn = _RefreshConnection(None)
    _refresh(conn, start_hour=18, end_hour=23, requirements=(_requirement(),))
    assert conn.writes == []


# ── the feature gate the new routes inherit ───────────────────────────────────


def test_new_routes_are_mounted_behind_the_unchanged_feature_gate():
    import inspect

    import app.matcha.routes as routes_init
    from app.matcha.routes.employee_schedule import router as schedule_router

    paths = {route.path for route in schedule_router.routes}
    assert "/shifts/{shift_id}/break-stagger" in paths
    assert "/shifts/{shift_id}/assignments/{employee_id}/break-plan" in paths

    source = inspect.getsource(routes_init)
    start = source.index("include_router(employee_schedule_router")
    mount = source[start:start + 400]
    assert 'require_feature("employee_schedule")' in mount
