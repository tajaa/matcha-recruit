"""Route boundaries for break staggering: tenant scoping, persistence, audit.

Fake connections throughout — none of these touch a database.
"""

import asyncio
import json
from datetime import datetime, timedelta, timezone
from types import SimpleNamespace
from uuid import UUID, uuid4

import pytest
from fastapi import HTTPException

from app.matcha.models.scheduling.employee_schedule import (
    AssignmentBreakPlanUpdate,
    BreakRuleApplicabilityDecision,
    PlannedBreak,
)
from app.matcha.routes.employee_schedule import assignments as assignments_route
from app.matcha.routes.employee_schedule import shifts as shifts_route
from app.matcha.services.scheduling import schedule_guidance
from app.workers.tasks import schedule_break_refresh
from app.matcha.services.scheduling.schedule_breaks import BreakPlan, BreakRequirement
from tests._helpers.routes import iter_api_routes


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
        self.shift_id = uuid4()
        self.employee_ids = [uuid4(), uuid4()]
        self.planned = planned or {}

    async def fetchrow(self, _query, *args):
        if not self.shift_found:
            return None
        self.shift_id = args[0]
        return {
            "id": self.shift_id,
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
                "shift_id": self.shift_id,
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
            key: {employee_id: plan for employee_id in employee_ids}
            for key, _starts_at, _ends_at, employee_ids in kwargs["shifts"]
        }, set()

    monkeypatch.setattr(shifts_route, "require_company_id", fake_require_company_id)
    monkeypatch.setattr(shifts_route, "get_connection", lambda: _ConnectionContext(conn))
    # Patch the module that DEFINES the caller, not the route's re-export.
    monkeypatch.setattr(
        schedule_guidance, "resolve_week_break_plans", fake_plans,
    )

    payload = _run(shifts_route.get_shift_break_stagger(uuid4(), current_user=_user()))

    assert payload["max_concurrent_breaks"] == 1
    assert len(payload["results"]) == 2
    assert {result["status"] for result in payload["results"]} == {"suggested"}
    starts = sorted(result["suggested_start"] for result in payload["results"])
    assert starts[0] != starts[1], "two assignees must not be sent on break together"


def test_break_rule_applicability_decision_is_tenant_and_context_scoped(monkeypatch):
    class Connection:
        def transaction(self):
            return _Transaction()

        async def fetchrow(self, query, *_args):
            assert "company_id" in query
            return {
                "id": uuid4(), "location_id": uuid4(),
                "starts_at": datetime(2026, 8, 21, 9, tzinfo=timezone.utc),
            }

    conn = Connection()
    company_id = uuid4()
    rule_set_id = uuid4()
    calls = []

    async def fake_require_company_id(_user):
        return company_id

    async def fake_record(_conn, **kwargs):
        calls.append(kwargs)

    recovery = []
    monkeypatch.setattr(shifts_route, "require_company_id", fake_require_company_id)
    monkeypatch.setattr(shifts_route, "get_connection", lambda: _ConnectionContext(conn))
    monkeypatch.setattr(shifts_route, "record_break_rule_applicability_decision", fake_record)
    monkeypatch.setattr(schedule_break_refresh, "enqueue_schedule_break_recovery", lambda: recovery.append(True))

    result = _run(shifts_route.decide_shift_break_rule_applicability(
        uuid4(),
        BreakRuleApplicabilityDecision(
            rule_set_id=rule_set_id, context_hash="a" * 64, decision="confirmed",
        ),
        current_user=_user(),
    ))

    assert result == {"decision": "confirmed", "rule_set_id": str(rule_set_id)}
    assert calls[0]["company_id"] == company_id
    assert calls[0]["context_hash"] == "a" * 64
    assert recovery == [True]


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
            key: {employee_id: plan for employee_id in employee_ids}
            for key, _starts_at, _ends_at, employee_ids in kwargs["shifts"]
        }, set()

    monkeypatch.setattr(shifts_route, "require_company_id", fake_require_company_id)
    monkeypatch.setattr(shifts_route, "get_connection", lambda: _ConnectionContext(conn))
    monkeypatch.setattr(
        schedule_guidance, "resolve_week_break_plans", fake_plans,
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


def test_separate_same_floor_shifts_do_not_get_the_same_break(monkeypatch):
    """The editor opens one row, but coverage is the location's whole day."""
    location_id = uuid4()
    first_shift = UUID("00000000-0000-0000-0000-000000000001")
    target_shift = UUID("00000000-0000-0000-0000-000000000002")
    first_employee = uuid4()
    target_employee = uuid4()
    window = {
        "location_id": location_id,
        "starts_at": datetime(2026, 8, 21, 6, 30, tzinfo=timezone.utc),
        "ends_at": datetime(2026, 8, 21, 14, 30, tzinfo=timezone.utc),
        "required_staff": 1,
    }
    shifts = [
        {"id": first_shift, **window},
        {"id": target_shift, **window},
    ]

    class DailyConnection:
        async def fetchrow(self, _query, shift_id, _company_id):
            return next(row for row in shifts if row["id"] == shift_id)

        async def fetch(self, query, *_args):
            if "FROM schedule_shifts" in query:
                return shifts
            assert "schedule_shift_assignments" in query
            return [
                {"shift_id": first_shift, "employee_id": first_employee, "planned_breaks": None},
                {"shift_id": target_shift, "employee_id": target_employee, "planned_breaks": None},
            ]

    async def fake_require_company_id(_user):
        return uuid4()

    async def fake_plans(*_args, **kwargs):
        from zoneinfo import ZoneInfo
        plan = BreakPlan(
            status="complete", requirements=(_requirement(),), advisories=(),
            rule_set_ids=(uuid4(),), rule_set_hash="hash",
        )
        return ZoneInfo("UTC"), {
            key: {employee_id: plan for employee_id in employee_ids}
            for key, _starts_at, _ends_at, employee_ids in kwargs["shifts"]
        }, set()

    monkeypatch.setattr(shifts_route, "require_company_id", fake_require_company_id)
    monkeypatch.setattr(
        shifts_route, "get_connection", lambda: _ConnectionContext(DailyConnection()),
    )
    monkeypatch.setattr(schedule_guidance, "resolve_week_break_plans", fake_plans)

    payload = _run(shifts_route.get_shift_break_stagger(target_shift, current_user=_user()))

    assert len(payload["results"]) == 1
    assert payload["results"][0]["employee_id"] == str(target_employee)
    assert payload["results"][0]["suggested_start"].startswith("2026-08-21T09:00:00")


def test_the_openers_and_the_mid_morning_arrival_all_break_apart(monkeypatch):
    """The send-back, row for row: two openers on separate 06:30–14:30 rows
    and a third person on an 08:30–16:30 row.  Whichever row the manager
    opens, the three suggestions never overlap and follow the day's order."""
    location_id = uuid4()
    opener_a = UUID("00000000-0000-0000-0000-00000000000a")
    opener_b = UUID("00000000-0000-0000-0000-00000000000b")
    arrival = UUID("00000000-0000-0000-0000-00000000000c")
    employees = {opener_a: uuid4(), opener_b: uuid4(), arrival: uuid4()}
    opener = {
        "starts_at": datetime(2026, 8, 21, 6, 30, tzinfo=timezone.utc),
        "ends_at": datetime(2026, 8, 21, 14, 30, tzinfo=timezone.utc),
    }
    shifts = [
        {"id": opener_a, "location_id": location_id, "required_staff": 1, **opener},
        {"id": opener_b, "location_id": location_id, "required_staff": 1, **opener},
        {
            "id": arrival, "location_id": location_id, "required_staff": 1,
            "starts_at": datetime(2026, 8, 21, 8, 30, tzinfo=timezone.utc),
            "ends_at": datetime(2026, 8, 21, 16, 30, tzinfo=timezone.utc),
        },
    ]

    class DailyConnection:
        async def fetchrow(self, _query, shift_id, _company_id):
            return next(row for row in shifts if row["id"] == shift_id)

        async def fetch(self, query, *_args):
            if "FROM schedule_shifts" in query:
                return shifts
            assert "schedule_shift_assignments" in query
            return [
                {"shift_id": shift_id, "employee_id": employee_id, "planned_breaks": None}
                for shift_id, employee_id in employees.items()
            ]

    async def fake_require_company_id(_user):
        return uuid4()

    async def fake_plans(*_args, **kwargs):
        from zoneinfo import ZoneInfo
        plan = BreakPlan(
            status="complete", requirements=(_requirement(),), advisories=(),
            rule_set_ids=(uuid4(),), rule_set_hash="hash",
        )
        return ZoneInfo("UTC"), {
            key: {employee_id: plan for employee_id in employee_ids}
            for key, _starts_at, _ends_at, employee_ids in kwargs["shifts"]
        }, set()

    monkeypatch.setattr(shifts_route, "require_company_id", fake_require_company_id)
    monkeypatch.setattr(
        shifts_route, "get_connection", lambda: _ConnectionContext(DailyConnection()),
    )
    monkeypatch.setattr(schedule_guidance, "resolve_week_break_plans", fake_plans)

    suggested = {}
    for shift_id in (arrival, opener_b, opener_a):  # open them in the "wrong" order
        payload = _run(shifts_route.get_shift_break_stagger(shift_id, current_user=_user()))
        assert [result["employee_id"] for result in payload["results"]] == [str(employees[shift_id])]
        assert payload["results"][0]["status"] == "suggested"
        suggested[shift_id] = payload["results"][0]["suggested_start"]

    assert suggested[opener_a].startswith("2026-08-21T08:30:00")
    assert suggested[opener_b].startswith("2026-08-21T09:00:00")
    # Two hours in for the 08:30 arrival, and clear of both openers' breaks.
    assert suggested[arrival].startswith("2026-08-21T10:30:00")


# ── the co-planned set: which rows share this one's floor ────────────────────


class _FloorConnection:
    """The location's shifts, answered the way the service asks for them.

    The window predicate is applied for real: a fake that returns every row
    regardless would pass whatever window the service asked for, which is
    exactly the bug these tests are about.
    """

    def __init__(self, rows, assignments):
        self.rows = rows
        self.assignments = assignments
        self.windows = []

    async def fetchrow(self, _query, shift_id, _company_id):
        return next((row for row in self.rows if row["id"] == shift_id), None)

    async def fetch(self, query, *args):
        if "FROM schedule_shifts" in query:
            _company_id, _location_id, window_start, window_end = args
            self.windows.append((window_start, window_end))
            return [
                row for row in self.rows
                if row["starts_at"] < window_end and row["ends_at"] > window_start
            ]
        assert "schedule_shift_assignments" in query
        assert "company_id" in query, "assignment read must be tenant-scoped"
        shift_ids = set(args[0])
        return [
            entry for entry in self.assignments if entry["shift_id"] in shift_ids
        ]


def _shift(shift_id, location_id, start, end, *, required=1):
    return {
        "id": shift_id, "location_id": location_id, "required_staff": required,
        "starts_at": datetime(2026, 8, 21, tzinfo=timezone.utc) + start,
        "ends_at": datetime(2026, 8, 21, tzinfo=timezone.utc) + end,
    }


def _assignment(shift_id, employee_id, *, saved=None):
    return {
        "shift_id": shift_id, "employee_id": employee_id,
        "planned_breaks": json.dumps([{
            "kind": "meal", "ordinal": 1, "start_local": saved,
            "duration_minutes": 30, "source": "manager",
        }]) if saved else None,
    }


def _patch_stagger_route(monkeypatch, conn, *, planned_keys=None):
    async def fake_require_company_id(_user):
        return uuid4()

    async def fake_plans(*_args, **kwargs):
        from zoneinfo import ZoneInfo
        plan = BreakPlan(
            status="complete", requirements=(_requirement(),), advisories=(),
            rule_set_ids=(uuid4(),), rule_set_hash="hash",
        )
        if planned_keys is not None:
            planned_keys.extend(key for key, _start, _end, _ids in kwargs["shifts"])
        return ZoneInfo("UTC"), {
            key: {employee_id: plan for employee_id in employee_ids}
            for key, _starts_at, _ends_at, employee_ids in kwargs["shifts"]
        }, set()

    monkeypatch.setattr(shifts_route, "require_company_id", fake_require_company_id)
    monkeypatch.setattr(
        shifts_route, "get_connection", lambda: _ConnectionContext(conn),
    )
    monkeypatch.setattr(schedule_guidance, "resolve_week_break_plans", fake_plans)


def test_an_overnight_peer_is_co_planned_from_either_row(monkeypatch):
    """Shifts that share floor time co-plan, whichever one is opened.

    The overnight row (22:00-06:00) and the next morning's (00:00-08:00) share
    six hours of floor, but no calendar day contains both: opening the morning
    row saw the overnighter, opening the overnighter did not see the morning
    row, and it was handed a time the other crew had already saved.
    """
    location_id = uuid4()
    overnight = UUID("00000000-0000-0000-0000-0000000000a1")
    morning = UUID("00000000-0000-0000-0000-0000000000a2")
    rows = [
        _shift(overnight, location_id, timedelta(hours=22), timedelta(hours=30)),
        _shift(morning, location_id, timedelta(hours=24), timedelta(hours=32)),
    ]
    assignments = [
        _assignment(overnight, uuid4()),
        _assignment(morning, uuid4(), saved="2026-08-22T00:00:00+00:00"),
    ]
    conn = _FloorConnection(rows, assignments)
    _patch_stagger_route(monkeypatch, conn)

    payload = _run(shifts_route.get_shift_break_stagger(overnight, current_user=_user()))

    result = payload["results"][0]
    assert result["status"] == "suggested"
    # 00:00 is the morning crew's saved break; the overnighter goes after it.
    assert result["suggested_start"].startswith("2026-08-22T00:30:00")
    assert conn.windows[-1][1] >= rows[1]["starts_at"], "the query grew to reach the peer"


def test_rows_after_the_target_are_not_planned_but_still_hold_the_floor(monkeypatch):
    """Opening the first row of a long day plans one row, not the whole day.

    A row later in the order cannot change what the target is offered — the
    target is placed before it. Its SAVED time is a different thing: that is
    an answer the floor will actually run on, so it still occupies.
    """
    location_id = uuid4()
    first = UUID("00000000-0000-0000-0000-0000000000b1")
    second = UUID("00000000-0000-0000-0000-0000000000b2")
    third = UUID("00000000-0000-0000-0000-0000000000b3")
    rows = [
        _shift(first, location_id, timedelta(hours=6), timedelta(hours=14)),
        _shift(second, location_id, timedelta(hours=7), timedelta(hours=15)),
        _shift(third, location_id, timedelta(hours=8), timedelta(hours=16)),
    ]
    assignments = [
        _assignment(first, uuid4()),
        _assignment(second, uuid4()),
        _assignment(third, uuid4(), saved="2026-08-21T08:00:00+00:00"),
    ]
    conn = _FloorConnection(rows, assignments)
    planned_keys: list[str] = []
    _patch_stagger_route(monkeypatch, conn, planned_keys=planned_keys)

    payload = _run(shifts_route.get_shift_break_stagger(first, current_user=_user()))

    assert planned_keys == [str(first)], "only up to and including the target"
    # Two hours in is 08:00, which the third row already holds; 08:30 is clear.
    assert payload["results"][0]["suggested_start"].startswith("2026-08-21T08:30:00")


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

    paths = {route.path for route in iter_api_routes(schedule_router)}
    assert "/shifts/{shift_id}/break-stagger" in paths
    assert "/shifts/{shift_id}/assignments/{employee_id}/break-plan" in paths

    source = inspect.getsource(routes_init)
    start = source.index("include_router(employee_schedule_router")
    mount = source[start:start + 400]
    assert 'require_feature("employee_schedule")' in mount
