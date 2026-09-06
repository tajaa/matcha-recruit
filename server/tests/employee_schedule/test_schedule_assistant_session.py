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
    # This conn answers every fetchval with "applied"; the week-alignment gate
    # has its own lookup and is not what this test is about.
    monkeypatch.setattr(session, "resolve_week_start_weekday", _sunday_weeks)
    monkeypatch.setattr(session, "get_connection", lambda: _ConnectionContext(conn))
    monkeypatch.setattr(session, "resolve_eligibility_manager_scope", lambda *args, **kwargs: _allow_scope())
    monkeypatch.setattr(session, "get_thread_messages", lambda thread_id, limit: _empty_messages())

    result = await session.get_or_create_schedule_assistant_session(
        company_id=company_id, user_id=user_id, actor_role="manager",
        location_id=location_id, week_start=date(2026, 8, 30),
    )

    assert result["current_state"]["huume_action"]["status"] == "applied"
    assert result["version"] == 4


async def _sunday_weeks(*_args, **_kwargs) -> int:
    return 0


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


@pytest.mark.asyncio
async def test_session_rejects_a_week_start_the_location_does_not_use(monkeypatch):
    """Every write on this surface is bounded by the session's week, so a
    Sunday week for a Monday-start store would scope Huume to a window that
    matches no grid the manager can see."""
    conn = _Conn()
    monkeypatch.setattr(session, "get_connection", lambda: _ConnectionContext(conn))
    monkeypatch.setattr(session, "resolve_eligibility_manager_scope", lambda *args, **kwargs: _allow_scope())
    monkeypatch.setattr(session, "resolve_week_start_weekday", _monday_weeks)

    with pytest.raises(HTTPException) as exc:
        await session.get_or_create_schedule_assistant_session(
            company_id=uuid4(), user_id=uuid4(), actor_role="manager",
            location_id=uuid4(), week_start=date(2026, 8, 23),   # a Sunday
        )

    assert exc.value.status_code == 422
    assert "Monday" in exc.value.detail


@pytest.mark.asyncio
async def test_session_accepts_the_week_start_the_location_does_use(monkeypatch):
    conn = _Conn()
    monkeypatch.setattr(session, "get_connection", lambda: _ConnectionContext(conn))
    monkeypatch.setattr(session, "resolve_eligibility_manager_scope", lambda *args, **kwargs: _allow_scope())
    monkeypatch.setattr(session, "resolve_week_start_weekday", _monday_weeks)
    monkeypatch.setattr(session, "get_thread_messages", lambda thread_id, limit: _empty_messages())

    result = await session.get_or_create_schedule_assistant_session(
        company_id=uuid4(), user_id=uuid4(), actor_role="manager",
        location_id=uuid4(), week_start=date(2026, 8, 24),   # the Monday after
    )
    assert result["thread_id"]


async def _monday_weeks(*_args, **_kwargs) -> int:
    return 1


def test_an_automatic_proposal_carries_its_coverage_findings():
    """The worker path rebuilds the staged action from `proposal`, never from
    `review` — an automatic run nobody watched is exactly the one where an
    unreported hole reaches a manager as "prepared this week for review"."""
    run_id = uuid4()
    location_id = uuid4()
    findings = [{
        "kind": "close_buffer_uncovered", "severity": "gap", "day": "2026-08-24",
        "detail": "Nobody is scheduled to close on Monday.",
    }]
    action = session._automatic_action({
        "id": run_id,
        "location_id": location_id,
        "week_start": date(2026, 8, 23),
        "source_mode": "template",
        "week_template_id": None,
        "proposal": json.dumps({
            "unfilled": [],
            "findings": findings,
            "review": {"summary": "Built a draft proposal.", "schedule_preview": []},
        }),
        "metrics": json.dumps({"gap_count": 1, "operating_hours_known": True}),
    })

    assert action["findings"] == findings
    assert action["metrics"]["gap_count"] == 1
