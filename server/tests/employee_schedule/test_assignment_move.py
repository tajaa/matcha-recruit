"""Direct tests for the transactional assignment-move route.

The fake connection models only the asyncpg operations used by the route and
the shared assignment write cores. No live database or schema mutation is
needed.
"""

import asyncio
import json
from copy import deepcopy
from datetime import datetime, timezone
from types import SimpleNamespace
from uuid import UUID, uuid4

import pytest
from fastapi import HTTPException

from app.matcha.models.scheduling.employee_schedule import AssignmentMove
from app.matcha.routes.employee_schedule import assignments as route
from app.matcha.routes.employee_schedule._shared import fetch_shift_for_write


COMPANY_ID = uuid4()
EMPLOYEE_ID = uuid4()
ACTOR_ID = uuid4()


def _run(coro):
    return asyncio.run(coro)


def test_direct_assignment_fetch_shape_includes_shift_id():
    shift_id = uuid4()

    class Connection:
        async def fetchrow(self, query, *args):
            assert "SELECT s.id," in query
            return {"id": args[0]}

    row = _run(fetch_shift_for_write(Connection(), COMPANY_ID, shift_id))
    assert row["id"] == shift_id


def _shift(shift_id: UUID, *, published=False, required_staff=1):
    starts_at = datetime(2026, 8, 12, 8, 0, tzinfo=timezone.utc)
    return {
        "id": shift_id,
        "starts_at": starts_at,
        "ends_at": datetime(2026, 8, 12, 16, 0, tzinfo=timezone.utc),
        "status": "published" if published else "draft",
        "required_staff": required_staff,
        "location_id": None,
        "break_minutes": 30,
        "role": "Cashier",
        "kind": "training",
        "training_requirement_id": None,
        "job_id": None,
        "published_at": starts_at if published else None,
    }


class _Transaction:
    def __init__(self, conn):
        self.conn = conn
        self.snapshot = None

    async def __aenter__(self):
        self.snapshot = (set(self.conn.assignments), deepcopy(self.conn.audits))
        return self

    async def __aexit__(self, exc_type, exc, traceback):
        if exc_type is not None:
            self.conn.assignments, self.conn.audits = self.snapshot
        return False


class _Connection:
    def __init__(self, source, target, *, source_assigned=True, target_employee=None):
        self.shifts = {source["id"]: source, target["id"]: target}
        self.assignments = set()
        if source_assigned:
            self.assignments.add((source["id"], EMPLOYEE_ID))
        if target_employee is not None:
            self.assignments.add((target["id"], target_employee))
        self.audits = []

    def transaction(self):
        return _Transaction(self)

    async def fetchrow(self, query, *args):
        if "SELECT assigned_by" in query:
            shift_id, employee_id = args
            if (shift_id, employee_id) in self.assignments:
                return {"assigned_by": ACTOR_ID}
            return None
        if "FROM schedule_shifts" in query and "FOR UPDATE" in query:
            return self.shifts.get(args[0])
        raise AssertionError(f"unexpected fetchrow: {' '.join(query.split())[:100]}")

    async def fetchval(self, query, *args):
        if "SELECT 1" in query:
            shift_id, employee_id = args
            return 1 if (shift_id, employee_id) in self.assignments else None
        raise AssertionError(f"unexpected fetchval: {' '.join(query.split())[:100]}")

    async def execute(self, query, *args):
        normalized = " ".join(query.split())
        if normalized.startswith("DELETE FROM schedule_shift_assignments"):
            assignment = (args[0], args[1])
            deleted = int(assignment in self.assignments)
            self.assignments.discard(assignment)
            return f"DELETE {deleted}"
        if normalized.startswith("INSERT INTO schedule_shift_assignments"):
            self.assignments.add((args[1], args[2]))
            return "INSERT 0 1"
        if normalized.startswith("INSERT INTO schedule_audit_log"):
            self.audits.append({
                "entity_type": args[1],
                "entity_id": args[2],
                "actor_user_id": args[3],
                "action": args[4],
                "details": json.loads(args[5]),
            })
            return "INSERT 0 1"
        raise AssertionError(f"unexpected execute: {normalized[:100]}")

    def payload(self, shift_id):
        shift = self.shifts[shift_id]
        return {
            "id": str(shift_id),
            "location_id": None,
            "template_id": None,
            "series_id": None,
            "role": shift["role"],
            "department": None,
            "starts_at": shift["starts_at"].isoformat().replace("+00:00", "Z"),
            "ends_at": shift["ends_at"].isoformat().replace("+00:00", "Z"),
            "break_minutes": shift["break_minutes"],
            "required_staff": shift["required_staff"],
            "color": None,
            "notes": None,
            "status": shift["status"],
            "kind": shift["kind"],
            "training_requirement_id": None,
            "job_id": None,
            "published_at": shift["published_at"].isoformat().replace("+00:00", "Z") if shift["published_at"] else None,
            "assignments": [
                {
                    "employee_id": str(employee_id),
                    "name": "Employee",
                    "job_title": None,
                    "status": "assigned",
                }
                for assigned_shift_id, employee_id in self.assignments
                if assigned_shift_id == shift_id
            ],
        }


class _ConnectionContext:
    def __init__(self, conn):
        self.conn = conn

    async def __aenter__(self):
        return self.conn

    async def __aexit__(self, exc_type, exc, traceback):
        return False


def _configure(monkeypatch, conn, *, conflicts=None, availability=None, compliance=None, fair_workweek=None):
    async def require_company_id(_user):
        return COMPANY_ID

    async def fetch_locked_shift_pair(_conn, _company_id, first_id, second_id):
        rows = {}
        for shift_id, row in conn.shifts.items():
            if shift_id in {first_id, second_id}:
                locked_row = dict(row)
                locked_row["assigned_count"] = sum(
                    assigned_shift_id == shift_id for assigned_shift_id, _ in conn.assignments
                )
                rows[str(shift_id)] = locked_row
        return rows

    async def fetch_shift_by_id(_conn, _company_id, shift_id):
        return conn.payload(shift_id)

    async def no_employee_check(*_args):
        return None

    async def find_conflicts(*_args, **_kwargs):
        return conflicts or []

    async def fetch_availability(*_args):
        return {EMPLOYEE_ID: {}}

    def availability_violations(*_args):
        return availability or []

    async def check_shift_compliance(*_args, **_kwargs):
        return compliance or []

    fair_results = fair_workweek or []

    async def fair_workweek_check(*_args, **_kwargs):
        return fair_results

    monkeypatch.setattr(route, "get_connection", lambda: _ConnectionContext(conn))
    monkeypatch.setattr(route, "require_company_id", require_company_id)
    monkeypatch.setattr(route, "fetch_locked_shift_pair", fetch_locked_shift_pair)
    monkeypatch.setattr(route, "fetch_shift_by_id", fetch_shift_by_id)
    monkeypatch.setattr(route, "assert_employee_in_company", no_employee_check)
    monkeypatch.setattr(route, "find_conflicts", find_conflicts)
    monkeypatch.setattr(route, "fetch_availability", fetch_availability)
    monkeypatch.setattr(route, "availability_violations", availability_violations)
    monkeypatch.setattr(route, "check_shift_compliance", check_shift_compliance)
    monkeypatch.setattr(route, "_fair_workweek_advisories", fair_workweek_check)


def _request(source_id, target_id):
    return AssignmentMove(
        employee_id=EMPLOYEE_ID,
        from_shift_id=source_id,
        to_shift_id=target_id,
    )


def _setup(monkeypatch, **kwargs):
    source_id = uuid4()
    target_id = uuid4()
    source = _shift(source_id, published=kwargs.pop("source_published", False))
    target = _shift(target_id, published=kwargs.pop("target_published", False), required_staff=kwargs.pop("required_staff", 1))
    conn = _Connection(
        source,
        target,
        source_assigned=kwargs.pop("source_assigned", True),
        target_employee=kwargs.pop("target_employee", None),
    )
    _configure(monkeypatch, conn, **kwargs)
    return conn, source_id, target_id


def _call(conn, source_id, target_id, *, force=False):
    return _run(route.move_employee_assignment(
        _request(source_id, target_id),
        force=force,
        current_user=SimpleNamespace(id=ACTOR_ID),
    ))


def test_move_is_atomic_and_preserves_audit_context(monkeypatch):
    conn, source_id, target_id = _setup(monkeypatch)

    result = _call(conn, source_id, target_id)

    assert (source_id, EMPLOYEE_ID) not in conn.assignments
    assert (target_id, EMPLOYEE_ID) in conn.assignments
    assert [audit["action"] for audit in conn.audits] == ["assignment.delete", "assignment.create"]
    assert all(audit["details"]["source"] == "schedule_editor_move" for audit in conn.audits)
    assert result["source_shift"]["id"] == str(source_id)
    assert result["target_shift"]["id"] == str(target_id)


def test_missing_source_assignment_returns_409_without_writes(monkeypatch):
    conn, source_id, target_id = _setup(monkeypatch, source_assigned=False)

    with pytest.raises(HTTPException) as caught:
        _call(conn, source_id, target_id)

    assert caught.value.status_code == 409
    assert caught.value.detail["code"] == "assignment_missing"
    assert conn.audits == []


def test_cancelled_destination_returns_409(monkeypatch):
    conn, source_id, target_id = _setup(monkeypatch)
    conn.shifts[target_id]["status"] = "cancelled"

    with pytest.raises(HTTPException) as caught:
        _call(conn, source_id, target_id)

    assert caught.value.status_code == 409
    assert conn.audits == []


def test_existing_destination_assignment_returns_409(monkeypatch):
    conn, source_id, target_id = _setup(monkeypatch, target_employee=EMPLOYEE_ID)

    with pytest.raises(HTTPException) as caught:
        _call(conn, source_id, target_id)

    assert caught.value.status_code == 409
    assert caught.value.detail["code"] == "assignment_exists"
    assert conn.assignments == {(source_id, EMPLOYEE_ID), (target_id, EMPLOYEE_ID)}


def test_conflict_excludes_source_shift(monkeypatch):
    captured = {}

    async def conflicts(*_args, **kwargs):
        captured.update(kwargs)
        return []

    conn, source_id, target_id = _setup(monkeypatch)
    monkeypatch.setattr(route, "find_conflicts", conflicts)

    _call(conn, source_id, target_id)

    assert captured["exclude_shift_id"] == source_id


def test_third_conflicting_shift_blocks_move(monkeypatch):
    conflict = [{"shift_id": str(uuid4()), "starts_at": "2026-08-12T09:00:00Z", "ends_at": "2026-08-12T10:00:00Z", "role": "Closer", "status": "draft"}]
    conn, source_id, target_id = _setup(monkeypatch, conflicts=conflict)

    with pytest.raises(HTTPException) as caught:
        _call(conn, source_id, target_id)

    assert caught.value.status_code == 409
    assert caught.value.detail["code"] == "schedule_conflict"
    assert conn.audits == []


def test_full_destination_blocks_without_force(monkeypatch):
    conn, source_id, target_id = _setup(monkeypatch, required_staff=1, target_employee=uuid4())

    with pytest.raises(HTTPException) as caught:
        _call(conn, source_id, target_id)

    assert caught.value.status_code == 409
    assert caught.value.detail["code"] == "shift_full"
    assert (source_id, EMPLOYEE_ID) in conn.assignments


def test_force_allows_full_destination(monkeypatch):
    conn, source_id, target_id = _setup(monkeypatch, required_staff=1, target_employee=uuid4())

    _call(conn, source_id, target_id, force=True)

    assert (source_id, EMPLOYEE_ID) not in conn.assignments
    assert (target_id, EMPLOYEE_ID) in conn.assignments


def test_availability_violation_blocks_without_force(monkeypatch):
    violation = [{"weekday": 3, "message": "Employee is unavailable"}]
    conn, source_id, target_id = _setup(monkeypatch, availability=violation)

    with pytest.raises(HTTPException) as caught:
        _call(conn, source_id, target_id)

    assert caught.value.status_code == 409
    assert caught.value.detail["code"] == "outside_availability"
    assert conn.audits == []


def test_force_availability_violation_writes_override_audit(monkeypatch):
    violation = [{"weekday": 3, "message": "Employee is unavailable"}]
    conn, source_id, target_id = _setup(monkeypatch, availability=violation)

    _call(conn, source_id, target_id, force=True)

    assert [audit["action"] for audit in conn.audits] == [
        "assignment.delete",
        "assignment.create",
        "assignment.availability_override",
    ]
    assert conn.audits[-1]["details"] == {
        "employee_id": str(EMPLOYEE_ID),
        "violations": violation,
    }


def test_hard_compliance_block_cannot_be_forced(monkeypatch):
    violation = [{"check": "minor_hours", "severity": "block", "message": "Hard limit"}]
    conn, source_id, target_id = _setup(monkeypatch, compliance=violation)

    with pytest.raises(HTTPException) as caught:
        _call(conn, source_id, target_id, force=True)

    assert caught.value.status_code == 422
    assert caught.value.detail["code"] == "schedule_compliance_block"
    assert conn.assignments == {(source_id, EMPLOYEE_ID)}
    assert conn.audits == []


def test_forceable_source_advisory_writes_override_audit(monkeypatch):
    advisory = [{"check": "fair_workweek_notice", "severity": "advisory", "message": "Short notice"}]
    conn, source_id, target_id = _setup(monkeypatch, source_published=True, fair_workweek=advisory)

    _call(conn, source_id, target_id, force=True)

    assert [audit["action"] for audit in conn.audits] == [
        "assignment.delete",
        "assignment.create",
        "assignment.compliance_override",
    ]
    assert conn.audits[-1]["details"]["violations"] == advisory


def test_target_validation_failure_produces_no_writes(monkeypatch):
    violation = [{"check": "meal_break", "severity": "advisory", "message": "Break required"}]
    conn, source_id, target_id = _setup(monkeypatch, compliance=violation)

    with pytest.raises(HTTPException) as caught:
        _call(conn, source_id, target_id)

    assert caught.value.status_code == 409
    assert conn.assignments == {(source_id, EMPLOYEE_ID)}
    assert conn.audits == []


def test_tenant_missing_shift_returns_404_without_writes(monkeypatch):
    conn, source_id, target_id = _setup(monkeypatch)
    missing_id = uuid4()

    with pytest.raises(HTTPException) as caught:
        _call(conn, source_id, missing_id)

    assert caught.value.status_code == 404
    assert conn.assignments == {(source_id, EMPLOYEE_ID)}
    assert conn.audits == []
