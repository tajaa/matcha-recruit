"""Exercise saved-proposal adoption/resume and local current-week discovery."""

import json
from contextlib import asynccontextmanager
from datetime import date, datetime, timezone
from unittest.mock import AsyncMock, MagicMock
from uuid import uuid4

import pytest

from app.matcha.services.scheduling import labor_cost_service as costs
from app.matcha.services.scheduling import schedule_assistant_session as sessions
from app.matcha.services.scheduling import schedule_automation
from app.matcha.services.scheduling import schedule_cost_projection as projection
from tests.employee_schedule.projection_fixtures import (
    compact_week_state, connection, full_week_review, patch_preview_connection,
)


def _connection():
    conn = AsyncMock()
    conn.transaction = MagicMock(side_effect=lambda: AsyncMock())
    return conn


def _patch_connection(monkeypatch, conn):
    @asynccontextmanager
    async def connection():
        yield conn
    monkeypatch.setattr(sessions, "get_connection", connection)
    monkeypatch.setattr(sessions, "_assert_manager_location", AsyncMock())
    monkeypatch.setattr(sessions, "resolve_week_start_weekday", AsyncMock(return_value=0))


@pytest.mark.asyncio
@pytest.mark.parametrize("role,has_cost,resume", [
    ("employee", True, False), ("employee", True, True),
    ("client", False, False), ("client", False, True),
])
async def test_employee_manager_or_revoked_flag_never_gets_saved_admin_wages(monkeypatch, role, has_cost, resume):
    conn = _connection()
    company_id, location_id, user_id, thread_id, session_id, run_id = [uuid4() for _ in range(6)]
    week_start = date(2026, 10, 4)
    run = {
        "id": run_id, "location_id": location_id, "week_start": week_start, "source_mode": "autopilot",
        "week_template_id": None, "metrics": {}, "proposal": {
            "schedule_review": {"kind": "week_draft", "cost": {"by_employee": {"crew": 80}}},
            "demand_model": {"forecast_sales_week": 400, "labor": {"scheduled_cost_after": 80, "labor_pct": 20}},
        },
    }
    action = sessions._automatic_action(run, include_cost=True)
    original_state = {"huume_action": action} if resume else {}
    existing = {"id": session_id, "thread_id": thread_id, "version": 3,
                "current_state": json.dumps(original_state)}

    async def fetchrow(query, *params):
        if "FROM schedule_assistant_sessions" in query:
            return existing
        if "FROM schedule_generation_runs" in query:
            return run
        raise AssertionError(query)

    async def fetchval(query, *params):
        return "proposed" if "SELECT status" in query else None

    conn.fetchrow.side_effect, conn.fetchval.side_effect = fetchrow, fetchval
    _patch_connection(monkeypatch, conn)
    monkeypatch.setattr(costs, "get_company_features", AsyncMock(return_value={"labor_cost": has_cost}))
    monkeypatch.setattr(sessions, "get_thread_messages", AsyncMock(return_value=[
        {"role": "assistant", "content": "Payroll $80", "metadata": {"schedule_cost_visible": True}},
        {"role": "user", "content": "Review this", "metadata": None},
    ]))
    pricing_read = AsyncMock(side_effect=AssertionError("Unauthorized pricing read"))
    monkeypatch.setattr(projection, "load_week_assignment_rows", pricing_read)
    result = await sessions.get_or_create_schedule_assistant_session(
        company_id=company_id, user_id=user_id, actor_role=role,
        location_id=location_id, week_start=week_start, session_id=session_id if resume else None,
    )
    state = result["current_state"]
    assert "cost" not in state["huume_action"]["review"]
    assert "labor" not in state["huume_action"]["demand_model"]
    assert [message["content"] for message in result["messages"]] == ["Review this"]
    if resume:
        assert state["huume_action"]["confirm_id"] == action["confirm_id"]
    for call in conn.execute.call_args_list:
        if "UPDATE mw_threads" in call.args[0]:
            persisted = json.loads(call.args[1])
            assert "cost" not in persisted["huume_action"]["review"]
            assert "labor" not in persisted["huume_action"]["demand_model"]
    pricing_read.assert_not_awaited()


@pytest.mark.asyncio
async def test_resumed_automatic_proposal_gains_cost_without_new_confirmation(monkeypatch):
    conn = _connection()
    company_id, location_id, user_id, thread_id, session_id, run_id, employee_id = [uuid4() for _ in range(7)]
    action = {
        "type": "schedule_week_draft", "status": "proposed", "origin": "automatic",
        "generation_run_id": str(run_id), "confirm_id": "same-consent", "metrics": {"open_positions": 0},
        "review": {"kind": "week_draft"}, "demand_model": {"forecast_sales_week": 400},
    }
    existing = {"id": session_id, "thread_id": thread_id, "version": 3,
                "current_state": json.dumps({"huume_action": action})}
    proposal = {"shifts": [{"starts_at": "2026-10-04T08:00:00+00:00", "worked_minutes": 240,
                            "proposed_assignments": [{"employee_id": str(employee_id)}]}]}

    conn.fetchrow.return_value = existing
    conn.fetchval.side_effect = lambda query, *params: (
        "proposed" if "SELECT status" in query
        else json.dumps(proposal) if "SELECT proposal FROM schedule_generation_runs" in query else None
    )
    _patch_connection(monkeypatch, conn)
    monkeypatch.setattr(costs, "get_company_features", AsyncMock(return_value={"labor_cost": True}))
    monkeypatch.setattr(sessions, "get_thread_messages", AsyncMock(return_value=[]))
    monkeypatch.setattr(projection, "load_week_assignment_rows", AsyncMock(return_value=([], False)))
    monkeypatch.setattr(projection, "cost_delta_for_rows", AsyncMock(return_value={"after": 80, "before": 0, "delta": 80}))
    result = await sessions.get_or_create_schedule_assistant_session(
        company_id=company_id, user_id=user_id, actor_role="client", location_id=location_id,
        week_start=date(2026, 10, 4), session_id=session_id,
    )
    priced = result["current_state"]["huume_action"]
    assert priced["review"]["cost"]["after"] == 80
    assert priced["demand_model"]["labor"]["labor_pct"] == 20
    assert priced["confirm_id"] == "same-consent" and result["version"] == 4


@pytest.mark.asyncio
async def test_resuming_chat_generated_week_restores_preview_without_persisting_full_rows(monkeypatch):
    conn = _connection()
    company_id, location_id, user_id, thread_id, session_id = [uuid4() for _ in range(5)]
    review = full_week_review()
    state = compact_week_state(review)
    existing = {"id": session_id, "thread_id": thread_id, "version": 3, "current_state": json.dumps(state)}
    conn.fetchrow.return_value = existing
    conn.fetchval.side_effect = lambda query, *params: "proposed" if "SELECT status" in query else None
    _patch_connection(monkeypatch, conn)
    # The preview is read on its own connection, after the session's locked
    # transaction has committed.
    preview = patch_preview_connection(monkeypatch, connection(review))
    monkeypatch.setattr(sessions, "schedule_cost_visible", AsyncMock(return_value=False))
    monkeypatch.setattr(sessions, "get_thread_messages", AsyncMock(return_value=[]))
    result = await sessions.get_or_create_schedule_assistant_session(
        company_id=company_id, user_id=user_id, actor_role="client", location_id=location_id,
        week_start=date(2026, 10, 11), session_id=session_id,
    )
    action = result["current_state"]["huume_action"]
    assert len(action["review"]["assignments"]) == 28
    assert action["confirm_id"] == state["huume_action"]["confirm_id"]
    assert "cost" not in action["review"]
    preview.fetchval.assert_awaited_once()
    assert all("schedule_review" not in call.args[0] for call in conn.fetchval.call_args_list)
    for call in conn.execute.call_args_list:
        if "UPDATE mw_threads" in call.args[0]:
            assert "assignments" not in json.loads(call.args[1])["huume_action"]["review"]


@pytest.mark.asyncio
@pytest.mark.parametrize("now,weekday,expected", [
    (datetime(2026, 10, 7, 12, tzinfo=timezone.utc), 0, date(2026, 10, 4)),
    (datetime(2026, 10, 7, 12, tzinfo=timezone.utc), 1, date(2026, 10, 5)),
    (datetime(2026, 10, 4, 1, tzinfo=timezone.utc), 0, date(2026, 9, 27)),
])
async def test_suggestion_query_includes_location_current_week_midweek(monkeypatch, now, weekday, expected):
    conn = _connection()
    _patch_connection(monkeypatch, conn)
    monkeypatch.setattr(sessions, "resolve_week_start_weekday", AsyncMock(return_value=weekday))
    monkeypatch.setattr(sessions, "location_today", lambda zone: schedule_automation.location_today(zone, now=now))
    conn.fetchval.return_value = "America/Los_Angeles"
    conn.fetchrow.return_value = {"id": uuid4(), "week_start": expected, "created_at": now}
    requested = date(2026, 10, 12)
    result = await sessions.get_automatic_suggestion_status(
        company_id=uuid4(), user_id=uuid4(), actor_role="client", location_id=uuid4(), week_start=requested,
    )
    query, _company, _location, preferred, lower = conn.fetchrow.call_args.args
    assert preferred == requested and lower == expected
    assert "week_start >= $4" in query and "ORDER BY (week_start=$3) DESC" in query
    assert result["available"] is True and result["week_start"] == expected.isoformat()
