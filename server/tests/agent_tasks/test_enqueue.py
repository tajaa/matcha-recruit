"""Starting a task and its rounds: every gate, the shared allowance, idempotency."""
import json
from dataclasses import replace
from types import SimpleNamespace
from unittest.mock import AsyncMock
from uuid import uuid4

import pytest
from fastapi import HTTPException

from app.core.services import redis_cache
from app.matcha.models.matcha_work.agent_tasks import AgentTaskCreate, RoundCreate
from app.matcha.services.matcha_work.agent_runtime import enqueue as assistant_enqueue, grants
from app.matcha.services.matcha_work.agent_tasks import allowance, enqueue, playbooks
from tests.agent_runtime.helpers import FakeConn, connection

from ._fixtures import COMPANY, ITEM, TASK, USER, task_row

CLIENT = SimpleNamespace(id=USER, role="client")
ADMIN = SimpleNamespace(id=USER, role="admin")
RESEARCH = playbooks.get("research")


@pytest.fixture
def gates(monkeypatch):
    from app.core.services import redis_cache
    from app.matcha.services.billing import token_budget_service

    conn = FakeConn()
    g = SimpleNamespace(
        conn=conn,
        enabled=True,
        workspace=AsyncMock(return_value=True),
        plan=AsyncMock(return_value="pro"),
        budget=AsyncMock(return_value={}),
        rate=AsyncMock(return_value=None),
        dispatch=AsyncMock(return_value=None),
        stale=AsyncMock(return_value=0),
        used=AsyncMock(return_value=0),
    )
    monkeypatch.setattr(enqueue, "tasks_enabled", lambda user: g.enabled or user.role == "admin")
    monkeypatch.setattr(assistant_enqueue, "workspace_enabled", g.workspace)
    monkeypatch.setattr(enqueue, "require_plan", g.plan)
    monkeypatch.setattr(token_budget_service, "check_token_budget", g.budget)
    monkeypatch.setattr(redis_cache, "check_rate_limit", g.rate)
    monkeypatch.setattr(enqueue, "dispatch", g.dispatch)
    monkeypatch.setattr(enqueue.service, "end_stale", g.stale)
    monkeypatch.setattr(enqueue.service, "find_by_request", AsyncMock(return_value=None))
    monkeypatch.setattr(enqueue.model_run, "default_model", AsyncMock(return_value="luna"))
    monkeypatch.setattr(allowance, "used_units", g.used)
    monkeypatch.setattr(enqueue, "connection_or_direct", connection(conn))
    monkeypatch.setattr(enqueue.service, "connection_or_direct", connection(conn))
    conn.on("INSERT INTO mw_agent_tasks", task_row(status="queued", phase="research.plan"))
    return g


def _body(**over):
    return AgentTaskCreate(request_id=uuid4(), directive="find me a 1bd in SF under 3500, dogs ok",
                           brief={"location": "San Francisco", "budget_max": 3500}, **over)


def test_queue_and_switch(monkeypatch):
    for name in ("AGENT_TASKS_QUEUE", "AGENT_CARD_QUEUE"):
        monkeypatch.delenv(name, raising=False)
    assert enqueue.queue_for() is None
    monkeypatch.setenv("AGENT_CARD_QUEUE", "agent_cards")
    assert enqueue.queue_for() == "agent_cards"
    monkeypatch.setenv("AGENT_TASKS_QUEUE", "agent_tasks")
    assert enqueue.queue_for() == "agent_tasks"
    import app.config

    settings = SimpleNamespace(espresso_tasks_enabled=False)
    monkeypatch.setattr(app.config, "get_settings", lambda: settings)
    assert not enqueue.tasks_enabled(CLIENT) and enqueue.tasks_enabled(ADMIN)
    settings.espresso_tasks_enabled = True
    assert enqueue.tasks_enabled(CLIENT)


@pytest.mark.asyncio
async def test_preflight_refusals(gates, monkeypatch):
    assert await enqueue.preflight(CLIENT, COMPANY, RESEARCH) == "pro"
    assert gates.rate.await_args.args == (str(USER), "espresso_agent_task_user", 10, 86400)
    # The day's cap says what it is, so Espresso doesn't retry or blame a search.
    gates.rate.side_effect = HTTPException(status_code=429, detail="Too many requests. Please try again later.")
    # The 24 hours start at the first task, so it says when they end.
    monkeypatch.setattr(redis_cache, "get_rate_limit_state", AsyncMock(return_value={"resets_in_seconds": 4 * 3600 + 5}))
    with pytest.raises(HTTPException) as refused:
        await enqueue.preflight(CLIENT, COMPANY, RESEARCH)
    assert refused.value.status_code == 429 and refused.value.detail == {
        "code": "daily_limit",
        "message": "That's 10 tasks started in 24 hours, the most allowed. More can start in about 5 hours."}
    assert refused.value.headers == {"Retry-After": "14405"}
    monkeypatch.setattr(redis_cache, "get_rate_limit_state", AsyncMock(return_value=None))
    with pytest.raises(HTTPException) as unknown:
        await enqueue.preflight(CLIENT, COMPANY, RESEARCH)
    assert unknown.value.detail["message"].endswith("More can start within 24 hours.")
    assert unknown.value.headers == {"Retry-After": "86400"}
    assert [enqueue._wait_words(s) for s in (30, 150, 3600, 3601)] == [
        "in about 1 minute", "in about 3 minutes", "in about 1 hour", "in about 2 hours"]
    gates.rate.side_effect = HTTPException(status_code=503, detail="Redis down")
    with pytest.raises(HTTPException) as other:
        await enqueue.preflight(CLIENT, COMPANY, RESEARCH)
    assert other.value.status_code == 503
    gates.rate.side_effect = None
    assert await enqueue.preflight(ADMIN, COMPANY, RESEARCH) is None
    gates.enabled = False
    with pytest.raises(HTTPException) as exc:
        await enqueue.preflight(CLIENT, COMPANY, RESEARCH)
    assert exc.value.detail["code"] == "feature_disabled"
    gates.enabled = True
    gates.workspace.return_value = False
    with pytest.raises(HTTPException) as exc:
        await enqueue.preflight(CLIENT, COMPANY, RESEARCH)
    assert exc.value.status_code == 403
    gates.workspace.return_value = True
    with pytest.raises(HTTPException) as exc:
        await enqueue.preflight(CLIENT, COMPANY, replace(RESEARCH, engine="board"))
    assert exc.value.status_code == 400
    with pytest.raises(HTTPException) as exc:
        await enqueue.preflight(CLIENT, COMPANY, replace(RESEARCH, env_ready=lambda: False))
    assert exc.value.status_code == 503


@pytest.mark.asyncio
async def test_consent_is_asked_once(gates, monkeypatch):
    monkeypatch.setattr(grants, "list_rows", AsyncMock(return_value={}))
    monkeypatch.setattr(grants, "is_active", lambda row, key: bool(row))
    enable = AsyncMock(return_value={})
    monkeypatch.setattr(grants, "enable", enable)
    await enqueue.preflight(CLIENT, COMPANY, replace(RESEARCH, consent="jobs"), consent_version="jobs-1")
    assert enable.await_args.kwargs == {"consent_version": "jobs-1"}
    monkeypatch.setattr(grants, "list_rows", AsyncMock(return_value={"jobs": {"ok": 1}}))
    await enqueue.preflight(CLIENT, COMPANY, replace(RESEARCH, consent="jobs"))
    assert enable.await_count == 1


@pytest.mark.asyncio
async def test_create_inserts_the_task_and_its_first_round(gates):
    view = await enqueue.create_task(CLIENT, COMPANY, _body())
    assert view["status"] == "queued" and view["phase"] == "plan"
    [insert] = gates.conn.ran("INSERT INTO mw_agent_tasks")
    args = insert[2]
    assert args[3] == "research" and json.loads(args[6])["budget_max"] == 3500.0 and args[8] == "research.plan"
    [first] = gates.conn.ran("INSERT INTO mw_agent_task_rounds")
    assert first[2][3] == allowance.WEIGHTS["research"]
    assert gates.conn.ran("pg_advisory_xact_lock") and gates.stale.await_count == 1
    gates.dispatch.assert_awaited_once()


@pytest.mark.asyncio
async def test_create_refusals(gates, monkeypatch):
    with pytest.raises(HTTPException) as exc:
        await enqueue.create_task(CLIENT, COMPANY, _body(playbook="nope"))
    assert exc.value.status_code == 400
    with pytest.raises(HTTPException) as exc:
        await enqueue.create_task(CLIENT, COMPANY, AgentTaskCreate(request_id=uuid4(), directive="abc",
                                                                   brief={"budget_max": -5}))
    assert exc.value.status_code == 422
    with pytest.raises(HTTPException) as exc:
        await enqueue.create_task(CLIENT, COMPANY, AgentTaskCreate(request_id=uuid4(), directive="abc",
                                                                   brief={"must_haves": ["x" * 100] * 10,
                                                                          "avoid": ["y" * 900] * 10}))
    assert exc.value.status_code == 422
    gates.conn.on("SELECT COUNT(*) FROM mw_agent_tasks", 2)
    with pytest.raises(HTTPException) as exc:
        await enqueue.create_task(CLIENT, COMPANY, _body())
    assert exc.value.status_code == 409 and exc.value.detail["code"] == "task_running"
    gates.conn.on("SELECT COUNT(*) FROM mw_agent_tasks", 0)
    gates.used.return_value = 58
    with pytest.raises(HTTPException) as exc:
        await enqueue.create_task(CLIENT, COMPANY, _body())
    assert exc.value.status_code == 429 and exc.value.detail["cost"] == 3 and "2 left" in exc.value.detail["message"]
    gates.used.return_value = 60
    with pytest.raises(HTTPException) as exc:
        await enqueue.create_task(CLIENT, COMPANY, _body())
    assert exc.value.detail["message"] == "You've used this month's tasks."
    gates.used.return_value = 0
    with pytest.raises(HTTPException) as exc:
        await enqueue.create_task(CLIENT, COMPANY, _body(input_ids=[uuid4()]))
    assert exc.value.status_code == 404
    mine = uuid4()
    gates.conn.on("FROM mw_agent_inputs", [{"id": mine}])
    await enqueue.create_task(CLIENT, COMPANY, _body(input_ids=[mine, mine]))
    assert gates.conn.ran("INSERT INTO mw_agent_tasks")[-1][2][7] == [mine]


@pytest.mark.asyncio
async def test_a_retry_returns_the_same_task(gates, monkeypatch):
    monkeypatch.setattr(enqueue.service, "find_by_request", AsyncMock(return_value={"id": "same"}))
    assert await enqueue.create_task(CLIENT, COMPANY, _body()) == {"id": "same"}
    monkeypatch.setattr(enqueue.service, "find_by_request", AsyncMock(return_value=None))
    gates.conn.on("request_id = $2", task_row())
    assert (await enqueue.create_task(CLIENT, COMPANY, _body()))["id"] == str(TASK)
    assert not gates.conn.ran("INSERT INTO mw_agent_tasks")


@pytest.mark.asyncio
async def test_a_broker_that_is_down_fails_the_task_free(gates):
    gates.dispatch.side_effect = RuntimeError("broker")
    with pytest.raises(HTTPException) as exc:
        await enqueue.create_task(CLIENT, COMPANY, _body())
    assert exc.value.status_code == 503
    assert gates.conn.ran("SET status = 'failed', error = 'Could not be queued.'")
    assert gates.conn.ran("UPDATE mw_agent_task_rounds r")


@pytest.fixture
def rounds(gates, monkeypatch):
    gates.conn.on("deleted_at IS NULL FOR UPDATE", task_row(status="done", current_round=1))
    monkeypatch.setattr(enqueue.service, "get_task", AsyncMock(return_value={"ok": True}))
    return gates


def _round(kind, **over):
    return RoundCreate(request_id=uuid4(), kind=kind, **over)


@pytest.mark.asyncio
async def test_refine_and_more_restart_the_chain(rounds):
    rounds.conn.on("SELECT company_id FROM mw_agent_tasks", COMPANY)
    assert await enqueue.start_round(CLIENT, TASK, _round("refine", directive="only the Mission")) == {"ok": True}
    rounds.budget.assert_awaited_once_with(COMPANY)
    assert rounds.rate.await_args.args == (str(USER), "espresso_agent_task_round", 30, 86400)
    [insert] = rounds.conn.ran("INSERT INTO mw_agent_task_rounds")
    assert insert[2][2:4] == (2, "refine") and insert[2][7] == 0
    [restart] = rounds.conn.ran("SET status = 'queued', phase = $2")
    assert restart[2][1] == "research.refine" and restart[2][3] == 2 and json.loads(restart[2][4]) == {}
    rounds.dispatch.assert_awaited_once()

    rounds.conn.calls.clear()
    rounds.conn.on("WHERE task_id = $1 AND kind = 'more'", 1)
    rounds.conn.on("AND id = ANY($2::uuid[])", 1)
    await enqueue.start_round(CLIENT, TASK, _round("more", item_ids=[ITEM]))
    [insert] = rounds.conn.ran("INSERT INTO mw_agent_task_rounds")
    assert insert[2][7] == allowance.ROUND_UNITS["more"]
    [restart] = rounds.conn.ran("SET status = 'queued', phase = $2")
    assert restart[2][1] == "research.fill"  # the next ten from those waiting, before any search
    assert json.loads(restart[2][4]) == {"more": True, "provider_page": 2, "web_runs": 0, "like": [str(ITEM)]}


@pytest.mark.asyncio
async def test_round_refusals(rounds, monkeypatch):
    with pytest.raises(HTTPException) as exc:
        await enqueue.start_round(CLIENT, TASK, _round("refine", directive=" "))
    assert exc.value.status_code == 422
    rounds.enabled = False
    with pytest.raises(HTTPException):
        await enqueue.start_round(CLIENT, TASK, _round("more"))
    rounds.enabled = True
    for row, code in ((task_row(status="running"), 409), (task_row(status="failed"), 409),
                      (task_row(current_round=12), 429), (task_row(engine="board"), 400)):
        rounds.conn.on("deleted_at IS NULL FOR UPDATE", row)
        with pytest.raises(HTTPException) as exc:
            await enqueue.start_round(CLIENT, TASK, _round("more"))
        assert exc.value.status_code == code
    rounds.conn.on("deleted_at IS NULL FOR UPDATE", task_row(status="done"))
    with pytest.raises(HTTPException) as exc:
        await enqueue.start_round(CLIENT, TASK, _round("more", item_ids=[ITEM]))
    assert exc.value.status_code == 404
    rounds.conn.on("SELECT COUNT(*) FROM mw_agent_tasks", 2)
    with pytest.raises(HTTPException) as exc:
        await enqueue.start_round(CLIENT, TASK, _round("more"))
    assert exc.value.status_code == 409
    rounds.conn.on("SELECT COUNT(*) FROM mw_agent_tasks", 0)
    rounds.used.return_value = 60
    with pytest.raises(HTTPException) as exc:
        await enqueue.start_round(CLIENT, TASK, _round("more"))
    assert exc.value.status_code == 429
    # A refine is free, so a full allowance doesn't stop it.
    await enqueue.start_round(CLIENT, TASK, _round("refine", directive="cheaper"))


@pytest.mark.asyncio
async def test_round_retry_and_dispatch_failure(rounds):
    rounds.conn.on("WHERE task_id = $1 AND request_id = $2", 1)
    await enqueue.start_round(CLIENT, TASK, _round("more"))
    assert not rounds.conn.ran("INSERT INTO mw_agent_task_rounds") and rounds.dispatch.await_count == 0
    rounds.conn.on("WHERE task_id = $1 AND request_id = $2", None)
    rounds.dispatch.side_effect = RuntimeError("broker")
    assert await enqueue.start_round(ADMIN, TASK, _round("more")) == {"ok": True}


@pytest.mark.asyncio
async def test_a_document_round_writes_a_note_inline(rounds, monkeypatch):
    write = AsyncMock(return_value={"journal_id": "j", "entry_id": "e", "title": "t", "items": 3})
    monkeypatch.setattr(enqueue.document, "write", write)
    rounds.conn.on("deleted_at IS NULL FOR UPDATE", task_row(status="cancelled"))
    await enqueue.start_round(CLIENT, TASK, _round("document"))
    assert json.loads(rounds.conn.ran("SET status = 'done', document = $3::jsonb")[0][2][2])["journal_id"] == "j"
    assert rounds.conn.ran("SET current_round = $2") and rounds.dispatch.await_count == 0
