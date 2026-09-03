"""Regression tests for the shift update write path."""

import asyncio
import json
from datetime import datetime, timezone
from types import SimpleNamespace
from uuid import uuid4

import pytest
from fastapi import HTTPException

from app.matcha.models.scheduling.employee_schedule import ShiftCreate, ShiftUpdate
from app.matcha.routes.employee_schedule import shifts as route


COMPANY_ID = uuid4()
SHIFT_ID = uuid4()
ACTOR_ID = uuid4()


def _run(coro):
    return asyncio.run(coro)


def test_break_mode_preserves_legacy_payloads_and_requires_manual_value():
    starts_at = datetime(2026, 8, 12, 8, 0, tzinfo=timezone.utc)
    legacy = ShiftCreate(
        starts_at=starts_at,
        ends_at=datetime(2026, 8, 12, 16, 0, tzinfo=timezone.utc),
        job_id=uuid4(),
        break_minutes=0,
    )
    assert legacy.break_mode is None

    with pytest.raises(ValueError, match="manual break_mode requires break_minutes"):
        ShiftUpdate(break_mode="manual")
    with pytest.raises(ValueError, match="break_minutes cannot be null"):
        ShiftUpdate(break_minutes=None)


def test_automatic_break_write_preserves_a_concurrent_manager_increase():
    assert route._locked_break_write(
        requested=45, locked=60, existing=30, minimum=45,
        manual=False, legacy_value=False,
    ) == 60


def test_manual_break_write_detects_a_concurrent_change():
    with pytest.raises(HTTPException) as exc:
        route._locked_break_write(
            requested=45, locked=60, existing=30, minimum=30,
            manual=True, legacy_value=False,
        )
    assert exc.value.status_code == 409
    assert exc.value.detail["code"] == "shift_changed"


class _Transaction:
    async def __aenter__(self):
        return self

    async def __aexit__(self, exc_type, exc, traceback):
        return False


class _Connection:
    def __init__(self):
        starts_at = datetime(2026, 8, 12, 8, 0, tzinfo=timezone.utc)
        self.existing = {
            "starts_at": starts_at,
            "ends_at": datetime(2026, 8, 12, 16, 0, tzinfo=timezone.utc),
            "status": "draft",
            "published_at": None,
            "break_minutes": 30,
            "location_id": None,
            "kind": "work",
            "training_requirement_id": None,
            "updated_at": datetime(2026, 8, 1, tzinfo=timezone.utc),
        }
        self.updates = []
        self.audits = []

    def transaction(self):
        return _Transaction()

    async def fetchrow(self, query, *args):
        assert "FROM schedule_shifts" in query
        return self.existing

    async def fetch(self, query, *args):
        raise AssertionError("non-compliance update unexpectedly fetched assignees")

    async def execute(self, query, *args):
        normalized = " ".join(query.split())
        if normalized.startswith("UPDATE schedule_shifts"):
            self.updates.append((query, args))
            return "UPDATE 1"
        if normalized.startswith("INSERT INTO schedule_audit_log"):
            self.audits.append({
                "action": args[4],
                "details": json.loads(args[5]),
            })
            return "INSERT 0 1"
        raise AssertionError(f"unexpected query: {normalized[:100]}")


@pytest.mark.parametrize(
    "body",
    [
        ShiftUpdate(color="#123456"),
        ShiftUpdate(status="cancelled"),
    ],
    ids=["non_compliance_field", "cancel_draft"],
)
def test_update_without_assignment_checks_has_override_map(monkeypatch, body):
    conn = _Connection()

    async def require_company_id(_user):
        return COMPANY_ID

    async def fetch_shift_by_id(_conn, _company_id, shift_id):
        return {"id": str(shift_id)}

    monkeypatch.setattr(route, "get_connection", lambda: _ConnectionContext(conn))
    monkeypatch.setattr(route, "require_company_id", require_company_id)
    monkeypatch.setattr(route, "fetch_shift_by_id", fetch_shift_by_id)

    result = _run(route.update_shift(
        SHIFT_ID,
        body,
        force=False,
        current_user=SimpleNamespace(id=ACTOR_ID),
    ))

    assert result == {"id": str(SHIFT_ID)}
    assert len(conn.updates) == 1
    assert [audit["action"] for audit in conn.audits] == ["shift.update"]


def test_auto_break_only_is_noop_for_cancelled_shift(monkeypatch):
    conn = _Connection()
    conn.existing.update({
        "status": "cancelled",
        "location_id": uuid4(),
        "updated_at": datetime(2026, 8, 1, tzinfo=timezone.utc),
    })

    async def require_company_id(_user):
        return COMPANY_ID

    async def fetch_shift_by_id(_conn, _company_id, shift_id):
        return {"id": str(shift_id), "status": "cancelled"}

    monkeypatch.setattr(route, "get_connection", lambda: _ConnectionContext(conn))
    monkeypatch.setattr(route, "require_company_id", require_company_id)
    monkeypatch.setattr(route, "fetch_shift_by_id", fetch_shift_by_id)

    result = _run(route.update_shift(
        SHIFT_ID, ShiftUpdate(break_mode="auto"), force=False,
        current_user=SimpleNamespace(id=ACTOR_ID),
    ))

    assert result["status"] == "cancelled"
    assert conn.updates == []


class _ConnectionContext:
    def __init__(self, conn):
        self.conn = conn

    async def __aenter__(self):
        return self.conn

    async def __aexit__(self, exc_type, exc, traceback):
        return False
