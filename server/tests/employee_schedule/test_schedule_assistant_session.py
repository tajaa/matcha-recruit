"""DB-free coverage for schedule assistant session identity and state."""

import json
from datetime import date
from uuid import uuid4

import pytest
from fastapi import HTTPException

from app.matcha.services.scheduling import schedule_assistant_session as session


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
    def __init__(self, existing=None):
        self.existing = existing
        self.fetchrow_calls = []
        self.execute_calls = []

    def transaction(self):
        return _Transaction()

    async def execute(self, query, *params):
        self.execute_calls.append((query, params))
        return None

    async def fetchrow(self, query, *params):
        self.fetchrow_calls.append(query)
        if "FROM business_locations" in query:
            return {"is_active": True}
        if "FROM schedule_assistant_sessions" in query:
            return self.existing
        if "FROM schedule_generation_runs" in query:
            return None
        if "INSERT INTO mw_threads" in query:
            return {
                "id": uuid4(),
                "current_state": json.dumps({"huume_surface": {"kind": "schedule_assistant"}}),
                "version": 1,
            }
        if "INSERT INTO schedule_assistant_sessions" in query:
            return {"id": uuid4()}
        raise AssertionError(f"unexpected fetchrow query: {query}")

    async def fetchval(self, *_args):
        return None


class _AllowedScope:
    def permits(self, location_id):
        return True


class _DeniedScope:
    def permits(self, location_id):
        return False


@pytest.mark.asyncio
async def test_new_session_returns_persisted_session_id_and_json_state(monkeypatch):
    company_id, user_id, location_id = uuid4(), uuid4(), uuid4()
    thread_id = uuid4()
    session_id = uuid4()
    conn = _Conn()

    async def allow_scope(*args, **kwargs):
        return _AllowedScope()

    original_fetchrow = conn.fetchrow

    async def fetchrow(query, *params):
        if "INSERT INTO mw_threads" in query:
            return {"id": thread_id, "current_state": json.dumps({"ready": True}), "version": 4}
        if "INSERT INTO schedule_assistant_sessions" in query:
            return {"id": session_id}
        return await original_fetchrow(query, *params)

    conn.fetchrow = fetchrow
    monkeypatch.setattr(session, "get_connection", lambda: _ConnectionContext(conn))
    monkeypatch.setattr(session, "resolve_eligibility_manager_scope", allow_scope)
    monkeypatch.setattr(session, "get_thread_messages", lambda thread_id, limit: _empty_messages())

    result = await session.get_or_create_schedule_assistant_session(
        company_id=company_id, user_id=user_id, actor_role="manager",
        location_id=location_id, week_start=date(2026, 8, 23),
    )

    assert result["session_id"] == str(session_id)
    assert result["thread_id"] == str(thread_id)
    assert result["current_state"] == {"ready": True}
    assert result["version"] == 4


async def _empty_messages():
    return []


@pytest.mark.asyncio
async def test_existing_session_uses_existing_id_and_coerces_json_state(monkeypatch):
    company_id, user_id, location_id = uuid4(), uuid4(), uuid4()
    existing_session_id, thread_id = uuid4(), uuid4()
    conn = _Conn({
        "id": existing_session_id,
        "thread_id": thread_id,
        "current_state": json.dumps({"huume_action": {"status": "proposed"}}),
        "version": 7,
    })
    monkeypatch.setattr(session, "get_connection", lambda: _ConnectionContext(conn))
    monkeypatch.setattr(session, "resolve_eligibility_manager_scope", lambda *args, **kwargs: _allow_scope())
    monkeypatch.setattr(session, "get_thread_messages", lambda thread_id, limit: _empty_messages())

    result = await session.get_or_create_schedule_assistant_session(
        company_id=company_id, user_id=user_id, actor_role="manager",
        location_id=location_id, week_start=date(2026, 8, 23),
    )

    assert result["session_id"] == str(existing_session_id)
    assert result["current_state"]["huume_action"]["status"] == "proposed"
    assert result["version"] == 7
    assert not any("INSERT INTO mw_threads" in query for query in conn.fetchrow_calls)


@pytest.mark.asyncio
async def test_session_adopts_automatic_week_proposal_for_review(monkeypatch):
    company_id, user_id, location_id = uuid4(), uuid4(), uuid4()
    existing_session_id, thread_id, generation_id = uuid4(), uuid4(), uuid4()
    week_start = date(2026, 8, 30)
    conn = _Conn({
        "id": existing_session_id,
        "thread_id": thread_id,
        "current_state": json.dumps({
            "huume_surface": {"kind": "schedule_assistant"},
        }),
        "version": 7,
    })
    original_fetchrow = conn.fetchrow

    async def fetchrow(query, *params):
        if "FROM schedule_generation_runs" in query:
            return {
                "id": generation_id,
                "location_id": location_id,
                "week_start": week_start,
                "source_mode": "template",
                "week_template_id": uuid4(),
                "proposal": json.dumps({
                    "metrics": {"shift_count": 2},
                    "unfilled": [],
                    "review": {
                        "summary": "Prepared two shifts.",
                        "schedule_preview": [{"shift_key": "one"}],
                        "preview_truncated": False,
                    },
                }),
                "metrics": json.dumps({"shift_count": 2}),
            }
        return await original_fetchrow(query, *params)

    conn.fetchrow = fetchrow
    monkeypatch.setattr(session, "get_connection", lambda: _ConnectionContext(conn))
    monkeypatch.setattr(session, "resolve_eligibility_manager_scope", lambda *args, **kwargs: _allow_scope())
    monkeypatch.setattr(session, "get_thread_messages", lambda thread_id, limit: _empty_messages())

    result = await session.get_or_create_schedule_assistant_session(
        company_id=company_id, user_id=user_id, actor_role="manager",
        location_id=location_id, week_start=week_start,
    )

    action = result["current_state"]["huume_action"]
    assert action["generation_run_id"] == str(generation_id)
    assert action["auto_generated"] is True
    assert action["summary"] == "Prepared two shifts."
    assert action["schedule_preview"] == [{"shift_key": "one"}]
    assert action["confirm_id"]
    assert result["version"] == 8
    assert any("UPDATE mw_threads" in query for query, _params in conn.execute_calls)


@pytest.mark.asyncio
async def test_session_refreshes_proposal_applied_by_another_manager(monkeypatch):
    company_id, user_id, location_id = uuid4(), uuid4(), uuid4()
    existing_session_id, thread_id, generation_id = uuid4(), uuid4(), uuid4()
    conn = _Conn({
        "id": existing_session_id,
        "thread_id": thread_id,
        "current_state": json.dumps({
            "huume_action": {
                "type": "schedule_week_draft",
                "status": "proposed",
                "generation_run_id": str(generation_id),
            },
        }),
        "version": 3,
    })

    async def fetchval(*_args):
        return "applied"

    conn.fetchval = fetchval
    monkeypatch.setattr(session, "get_connection", lambda: _ConnectionContext(conn))
    monkeypatch.setattr(session, "resolve_eligibility_manager_scope", lambda *args, **kwargs: _allow_scope())
    monkeypatch.setattr(session, "get_thread_messages", lambda thread_id, limit: _empty_messages())

    result = await session.get_or_create_schedule_assistant_session(
        company_id=company_id, user_id=user_id, actor_role="manager",
        location_id=location_id, week_start=date(2026, 8, 30),
    )

    assert result["current_state"]["huume_action"]["status"] == "applied"
    assert result["version"] == 4


async def _allow_scope():
    return _AllowedScope()


@pytest.mark.asyncio
async def test_manager_location_auth_returns_not_found_for_inactive_location():
    conn = _Conn()
    conn.fetchrow = lambda query, *params: _inactive_location()

    with pytest.raises(HTTPException) as exc_info:
        await session._assert_manager_location(
            conn, company_id=uuid4(), user_id=uuid4(), actor_role="employee", location_id=uuid4(),
        )

    assert exc_info.value.status_code == 404


@pytest.mark.asyncio
async def test_manager_location_auth_returns_forbidden_for_other_location(monkeypatch):
    conn = _Conn()
    monkeypatch.setattr(session, "resolve_eligibility_manager_scope", lambda *args, **kwargs: _denied_scope())

    with pytest.raises(HTTPException) as exc_info:
        await session._assert_manager_location(
            conn, company_id=uuid4(), user_id=uuid4(), actor_role="employee", location_id=uuid4(),
        )

    assert exc_info.value.status_code == 403


async def _inactive_location():
    return {"is_active": False}


async def _denied_scope():
    return _DeniedScope()
