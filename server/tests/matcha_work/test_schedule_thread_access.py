"""Regression coverage for schedule-thread access through the stream route."""

from uuid import uuid4

import pytest

from app.matcha.services.matcha_work.matcha_work_document import threads


class _ConnectionContext:
    def __init__(self, conn):
        self.conn = conn

    async def __aenter__(self):
        return self.conn

    async def __aexit__(self, exc_type, exc, tb):
        return False


class _Conn:
    query = ""

    async def fetchrow(self, query, *params):
        self.query = query
        return {"current_state": {}}


@pytest.mark.asyncio
async def test_schedule_thread_access_explicitly_types_owner_parameter(monkeypatch):
    """Avoid asyncpg's ambiguous $3 inference before an SSE stream starts."""
    conn = _Conn()
    monkeypatch.setattr(threads, "get_connection", lambda: _ConnectionContext(conn))

    result = await threads.get_thread(
        uuid4(), uuid4(), user_id=uuid4(), allow_schedule_surface=True,
    )

    assert result == {"current_state": {}}
    assert "created_by=$3::uuid" in conn.query
    assert conn.query.count("$3::uuid") == 3
