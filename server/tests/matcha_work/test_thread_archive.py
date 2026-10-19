"""`DELETE /matcha-work/threads/{id}` — the generic archive cancels the
thread's proposed week drafts, as the editor's own archive does.

    cd server && ./venv/bin/python -m pytest tests/matcha_work/test_thread_archive.py -q
"""

import asyncio
from types import SimpleNamespace
from unittest.mock import AsyncMock
from uuid import uuid4

import pytest
from fastapi import HTTPException

from app import database
from app.matcha.routes.matcha_work import threads


class _Ctx:
    def __init__(self, value):
        self.value = value

    async def __aenter__(self):
        return self.value

    async def __aexit__(self, *_args):
        return False


class _Conn:
    def __init__(self, *, archived=True):
        self.archived = archived
        self.executed = []
        self.in_transaction = False

    def transaction(self):
        conn = self

        class _Tx:
            async def __aenter__(self):
                conn.in_transaction = True

            async def __aexit__(self, *_args):
                conn.in_transaction = False
                return False

        return _Tx()

    async def execute(self, query, *args):
        self.executed.append((query, args, self.in_transaction))
        if "UPDATE mw_threads" in query:
            return "UPDATE 1" if self.archived else "UPDATE 0"
        return "UPDATE 1"


def _wire(monkeypatch, conn):
    company = uuid4()
    monkeypatch.setattr(threads, "get_client_company_id", AsyncMock(return_value=company))
    # The route imports `get_connection` inside its body, so the module it
    # reads from is app.database, not the route module.
    monkeypatch.setattr(database, "get_connection", lambda: _Ctx(conn))
    sync = AsyncMock()
    monkeypatch.setattr(threads.doc_svc, "sync_element_record", sync)
    return company, sync


def test_archiving_a_thread_cancels_its_proposed_week_drafts(monkeypatch):
    """A schedule chat archived from the thread list refuses every turn, so a
    week draft it staged can never be confirmed — left 'proposed' it blocked
    that week's automatic suggestion with 'already waiting for review'."""
    conn = _Conn()
    company, sync = _wire(monkeypatch, conn)
    thread_id = uuid4()

    asyncio.run(threads.archive_thread(thread_id, current_user=SimpleNamespace(id=uuid4())))

    archive, cancel = conn.executed
    assert "UPDATE mw_threads" in archive[0] and archive[2] is True
    assert "UPDATE schedule_generation_runs" in cancel[0] and cancel[2] is True
    assert "SET status='cancelled'" in cancel[0] and "status='proposed'" in cancel[0]
    assert cancel[1] == (thread_id, company)
    sync.assert_awaited_once_with(thread_id)


def test_an_unknown_thread_is_a_404_and_cancels_nothing(monkeypatch):
    conn = _Conn(archived=False)
    _wire(monkeypatch, conn)

    with pytest.raises(HTTPException) as exc:
        asyncio.run(threads.archive_thread(uuid4(), current_user=SimpleNamespace(id=uuid4())))

    assert exc.value.status_code == 404
    assert [q for q, _, _ in conn.executed if "schedule_generation_runs" in q] == []
