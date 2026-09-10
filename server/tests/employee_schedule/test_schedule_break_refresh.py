"""Worker paging and recovery contracts for employee break refreshes."""

import asyncio
from datetime import date, datetime, timezone
from unittest.mock import AsyncMock
from uuid import UUID, uuid4

from app.matcha.services.scheduling import schedule_break_rule_store, schedule_guidance
from app.workers.tasks import schedule_break_refresh as worker


class _Transaction:
    async def __aenter__(self):
        return self

    async def __aexit__(self, exc_type, exc, traceback):
        return False


class _Connection:
    def __init__(self, rows):
        self.rows = rows
        self.fetches = []
        self.closed = False

    def transaction(self):
        return _Transaction()

    async def fetch(self, query, *args):
        assert "$4::timestamptz" in query
        assert "s.location_id IS NOT NULL" in query
        assert "pg_timezone_names" in query
        self.fetches.append(args)
        cursor_start, cursor_id = args[3], args[4]
        remaining = [
            row for row in self.rows
            if cursor_start is None
            or (row["starts_at"], row["shift_id"]) > (cursor_start, cursor_id)
        ]
        return remaining[: args[5]]

    async def close(self):
        self.closed = True


def test_worker_cursor_resumes_with_aware_timestamptz(monkeypatch):
    rows = [
        {
            "shift_id": uuid4(),
            "starts_at": datetime(2026, 9, day, 9, tzinfo=timezone.utc),
        }
        for day in (3, 4, 5)
    ]
    connections = []

    async def get_connection():
        conn = _Connection(rows)
        connections.append(conn)
        return conn

    refreshed = []

    async def refresh(*_args, **kwargs):
        refreshed.append(kwargs["shift_id"])

    monkeypatch.setattr(worker, "_PAGE_SIZE", 2)
    monkeypatch.setattr(worker, "get_db_connection", get_connection)
    count_lookup = AsyncMock(return_value=42)
    monkeypatch.setattr(
        schedule_break_rule_store, "get_employer_employee_count", count_lookup,
    )
    monkeypatch.setattr(
        schedule_guidance, "refresh_assignment_break_guidance_and_minimum", refresh,
    )

    company_id, employee_id = uuid4(), uuid4()
    first = asyncio.run(worker._refresh_employee_breaks(
        company_id=company_id, employee_id=employee_id,
        actor_user_id=None, source="test", effective_from=date(2026, 9, 1),
    ))
    second = asyncio.run(worker._refresh_employee_breaks(
        company_id=company_id, employee_id=employee_id,
        actor_user_id=None, source="test", effective_from=date(2026, 9, 1),
        cursor_start=datetime.fromisoformat(first["cursor_start"]),
        cursor_id=UUID(first["cursor_id"]),
    ))

    assert first["has_more"] is True
    assert second["has_more"] is False
    assert second["refreshed"] == 1
    assert refreshed == [row["shift_id"] for row in rows]
    assert count_lookup.await_count == 2, "one headcount read per worker page"
    assert connections[1].fetches[0][3].tzinfo is timezone.utc
    assert all(conn.closed for conn in connections)


def test_dispatch_failure_returns_success_for_durable_fact_recovery(monkeypatch):
    def fail(*_args, **_kwargs):
        raise RuntimeError("broker unavailable")

    monkeypatch.setattr(worker.refresh_employee_schedule_breaks, "delay", fail)

    assert worker.enqueue_employee_schedule_break_refresh(
        company_id=uuid4(), employee_id=uuid4(), actor_user_id=uuid4(),
        source="test",
    ) is False


def test_location_refresh_is_tenant_scoped_and_pages_every_assignment(monkeypatch):
    location_id = uuid4()
    rows = [
        {
            "shift_id": uuid4(),
            "employee_id": uuid4(),
            "starts_at": datetime(2026, 9, day, 9, tzinfo=timezone.utc),
        }
        for day in (3, 4, 5)
    ]
    connections = []

    class Connection:
        def __init__(self):
            self.closed = False

        def transaction(self):
            return _Transaction()

        async def fetch(self, query, *args):
            assert "a.company_id = $1" in query
            assert "s.location_id = $2" in query
            assert "(s.starts_at, s.id, a.employee_id)" in query
            assert args[1] == location_id
            cursor = args[2:5]
            remaining = [
                row for row in rows
                if cursor[0] is None
                or (row["starts_at"], row["shift_id"], row["employee_id"])
                   > tuple(cursor)
            ]
            return remaining[:args[5]]

        async def close(self):
            self.closed = True

    async def get_connection():
        conn = Connection()
        connections.append(conn)
        return conn

    refreshed = []

    async def refresh(*_args, **kwargs):
        refreshed.append((kwargs["shift_id"], kwargs["employee_id"]))

    monkeypatch.setattr(worker, "_PAGE_SIZE", 2)
    monkeypatch.setattr(worker, "get_db_connection", get_connection)
    count_lookup = AsyncMock(return_value=42)
    monkeypatch.setattr(
        schedule_break_rule_store, "get_employer_employee_count", count_lookup,
    )
    monkeypatch.setattr(
        schedule_guidance, "refresh_assignment_break_guidance_and_minimum", refresh,
    )

    company_id = uuid4()
    first = asyncio.run(worker._refresh_location_breaks(
        company_id=company_id,
        location_id=location_id,
        actor_user_id=None,
        source="test",
    ))
    second = asyncio.run(worker._refresh_location_breaks(
        company_id=company_id,
        location_id=location_id,
        actor_user_id=None,
        source="test",
        cursor_start=datetime.fromisoformat(first["cursor_start"]),
        cursor_shift_id=UUID(first["cursor_shift_id"]),
        cursor_employee_id=UUID(first["cursor_employee_id"]),
    ))

    assert first["has_more"] is True
    assert second["has_more"] is False
    assert refreshed == [
        (row["shift_id"], row["employee_id"])
        for row in rows
    ]
    assert count_lookup.await_count == 2, "one headcount read per worker page"
    assert all(conn.closed for conn in connections)


def test_stale_recovery_tracks_company_headcount_inputs(monkeypatch):
    captured = {}

    class Connection:
        async def fetch(self, query):
            captured["query"] = query
            return []

        async def close(self):
            return None

    async def get_connection():
        return Connection()

    monkeypatch.setattr(worker, "get_db_connection", get_connection)

    assert asyncio.run(worker._stale_employee_facts()) == []
    assert "latest_company_headcount_facts" in captured["query"]
    assert "FROM company_handbook_profiles" in captured["query"]
    assert "SELECT e.org_id AS company_id, e.updated_at AS changed_at" in captured["query"]
    assert "hp.headcount IS NOT NULL" in captured["query"]
    assert "current_company_headcounts" in captured["query"]
    assert "a.compliance_guidance ? 'context'" in captured["query"]
    assert "ch.headcount IS DISTINCT FROM CASE" in captured["query"]
