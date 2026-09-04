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

    def __init__(self, *, shift_found=True):
        self.shift_found = shift_found
        self.employee_ids = [uuid4(), uuid4()]

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
        return [{"employee_id": employee_id} for employee_id in self.employee_ids]


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
        return {"planned_breaks": self.before} if self.found else None

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


def _patch_break_plan_route(monkeypatch, conn):
    async def fake_require_company_id(_user):
        return uuid4()

    async def fake_fetch_shift_by_id(*_args):
        return {"id": "shift"}

    monkeypatch.setattr(assignments_route, "require_company_id", fake_require_company_id)
    monkeypatch.setattr(assignments_route, "get_connection", lambda: _ConnectionContext(conn))
    monkeypatch.setattr(assignments_route, "fetch_shift_by_id", fake_fetch_shift_by_id)


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
