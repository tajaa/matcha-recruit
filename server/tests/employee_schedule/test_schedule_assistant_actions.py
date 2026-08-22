"""Regression tests for schedule-scoped assignment-note writes."""

from datetime import date, datetime, timezone
from uuid import uuid4

import pytest

from app.matcha.services.scheduling import schedule_assistant_actions as actions


class _Transaction:
    async def __aenter__(self):
        return self

    async def __aexit__(self, exc_type, exc, tb):
        return False


class _ConnectionContext:
    def __init__(self, conn):
        self.conn = conn

    async def __aenter__(self):
        return self.conn

    async def __aexit__(self, exc_type, exc, tb):
        return False


class _Conn:
    def __init__(self, row):
        self.row = row
        self.execute_calls = []

    def transaction(self):
        return _Transaction()

    async def fetchrow(self, query, *params):
        assert "s.starts_at" in query
        return self.row

    async def execute(self, query, *params):
        self.execute_calls.append(query)


@pytest.mark.asyncio
async def test_assignment_note_refuses_a_shift_outside_selected_week(monkeypatch):
    company_id, actor_id, location_id = uuid4(), uuid4(), uuid4()
    conn = _Conn({
        "manager_note": None,
        "manager_note_visible_to_employee": True,
        "manager_note_include_in_location_digest": True,
        "manager_note_send_employee_notice": True,
        "location_id": location_id,
        "starts_at": datetime(2026, 9, 1, 8, tzinfo=timezone.utc),
    })
    monkeypatch.setattr(actions, "get_connection", lambda: _ConnectionContext(conn))

    result = await actions.update_assignment_note_core(
        company_id=company_id, actor_user_id=actor_id, location_id=location_id,
        shift_id=uuid4(), employee_id=uuid4(), note="Call out sick",
        week_start=date(2026, 8, 23), week_end=date(2026, 8, 29),
    )

    assert result["status"] == "refused"
    assert "outside this schedule workspace" in result["message"]
    assert conn.execute_calls == []
