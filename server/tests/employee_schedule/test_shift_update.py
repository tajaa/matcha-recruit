"""Regression tests for the shift update write path."""

import asyncio
import json
from datetime import datetime, timezone
from types import SimpleNamespace
from uuid import uuid4

import pytest

from app.matcha.models.scheduling.employee_schedule import ShiftUpdate
from app.matcha.routes.employee_schedule import shifts as route


COMPANY_ID = uuid4()
SHIFT_ID = uuid4()
ACTOR_ID = uuid4()


def _run(coro):
    return asyncio.run(coro)


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


class _ConnectionContext:
    def __init__(self, conn):
        self.conn = conn

    async def __aenter__(self):
        return self.conn

    async def __aexit__(self, exc_type, exc, traceback):
        return False
