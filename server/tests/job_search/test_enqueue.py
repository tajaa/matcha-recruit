"""Starting a search: every gate, the atomic monthly cap, and a broker that is down."""
import json
from types import SimpleNamespace
from unittest.mock import AsyncMock
from uuid import uuid4

import asyncpg
import pytest
from fastapi import HTTPException

from app.matcha.models.matcha_work.job_search import JobCriteria, JobSearchCreate, JobWeights
from app.matcha.services.matcha_work.agent_runtime import enqueue as assistant_enqueue, grants
from app.matcha.services.matcha_work.agent_tasks import allowance
from app.matcha.services.matcha_work.job_search import enqueue
from tests.agent_runtime.helpers import FakeConn, connection

from ._fixtures import COMPANY, SEARCH, USER, search_row

CLIENT = SimpleNamespace(id=USER, role="client")
ADMIN = SimpleNamespace(id=USER, role="admin")


@pytest.fixture(autouse=True)
def no_bonus(monkeypatch):
    """The limit reads the person's admin top-up from the database; none here."""
    monkeypatch.setattr(allowance, "bonus_units", AsyncMock(return_value=0))


@pytest.fixture
def gates(monkeypatch):
    from app.core.services import redis_cache
    from app.matcha.services.billing import token_budget_service

    g = SimpleNamespace(
        workspace=AsyncMock(return_value=True),
        plan=AsyncMock(return_value="pro"),
        usage=AsyncMock(return_value={"limit": 4, "used": 1, "remaining": 3}),
        consent=AsyncMock(return_value=True),
        enable=AsyncMock(return_value={}),
        budget=AsyncMock(return_value={}),
        rate=AsyncMock(return_value=None),
        dispatch=AsyncMock(return_value=None),
    )
    monkeypatch.setattr(assistant_enqueue, "workspace_enabled", g.workspace)
    monkeypatch.setattr(enqueue, "require_plan", g.plan)
    monkeypatch.setattr(enqueue, "job_search_usage", g.usage)
    monkeypatch.setattr(enqueue, "consent_granted", g.consent)
    monkeypatch.setattr(grants, "enable", g.enable)
    monkeypatch.setattr(token_budget_service, "check_token_budget", g.budget)
    monkeypatch.setattr(redis_cache, "check_rate_limit", g.rate)
    monkeypatch.setattr(enqueue, "dispatch", g.dispatch)
    return g


def test_queue_env_precedence(monkeypatch):
    for name in ("AGENT_JOBS_QUEUE", "AGENT_CARD_QUEUE"):
        monkeypatch.delenv(name, raising=False)
    assert enqueue.queue_for() is None
    monkeypatch.setenv("AGENT_CARD_QUEUE", "agent_cards")
    assert enqueue.queue_for() == "agent_cards"
    monkeypatch.setenv("AGENT_JOBS_QUEUE", "agent_jobs")
    assert enqueue.queue_for() == "agent_jobs"


@pytest.mark.asyncio
async def test_preflight_refusals(gates, monkeypatch):
    assert await enqueue.preflight(CLIENT, COMPANY) == "pro"
    gates.budget.assert_awaited_once_with(COMPANY)
    assert gates.rate.await_args.args == (str(USER), "espresso_job_search_user", 6, 86400)

    gates.workspace.return_value = False
    with pytest.raises(HTTPException) as exc:
        await enqueue.preflight(CLIENT, COMPANY)
    assert exc.value.status_code == 403 and exc.value.detail["code"] == "feature_disabled"
    gates.workspace.return_value = True

    gates.usage.return_value = {"limit": 4, "used": 4, "remaining": 0}
    with pytest.raises(HTTPException) as exc:
        await enqueue.preflight(CLIENT, COMPANY)
    assert exc.value.status_code == 429 and exc.value.detail["code"] == "job_search_limit"
    gates.usage.return_value = {"limit": 4, "used": 0, "remaining": 4}

    gates.plan.side_effect = HTTPException(status_code=403, detail={"code": "plan_required", "feature": "job_search"})
    with pytest.raises(HTTPException) as exc:
        await enqueue.preflight(CLIENT, COMPANY)
    assert exc.value.detail["feature"] == "job_search"
    gates.plan.side_effect = None


@pytest.mark.asyncio
async def test_consent_is_asked_for_once_then_granted(gates):
    gates.consent.return_value = False
    gates.enable.side_effect = HTTPException(status_code=409, detail={"code": "consent_required"})
    with pytest.raises(HTTPException) as exc:
        await enqueue.preflight(CLIENT, COMPANY)
    assert exc.value.status_code == 409
    gates.enable.side_effect = None
    await enqueue.preflight(CLIENT, COMPANY, consent_version="jobs-2")
    assert gates.enable.await_args.args == (USER, COMPANY, "jobs")
    assert gates.enable.await_args.kwargs == {"consent_version": "jobs-2"}


@pytest.mark.asyncio
async def test_admins_skip_plan_and_budget_but_not_consent(gates):
    gates.consent.return_value = False
    assert await enqueue.preflight(ADMIN, COMPANY, consent_version="jobs-2") is None
    gates.plan.assert_not_awaited()
    gates.budget.assert_not_awaited()
    gates.enable.assert_awaited_once()


def body(**over):
    return JobSearchCreate(request_id=uuid4(), ask="COO roles across the US, salary bonus equity",
                           criteria=JobCriteria(titles=["Chief Operating Officer"]), **over)


@pytest.fixture
def conn(monkeypatch):
    conn = FakeConn()
    monkeypatch.setattr(enqueue, "connection_or_direct", connection(conn))
    monkeypatch.setattr(enqueue, "find_by_request", AsyncMock(return_value=None))
    return conn


@pytest.mark.asyncio
async def test_create_inserts_then_dispatches(gates, conn):
    conn.on("INSERT INTO mw_job_searches", search_row(status="queued"))
    conn.on("SELECT COUNT(*) FROM mw_job_searches", 1)
    out = await enqueue.create_search(CLIENT, COMPANY, body(weights=JobWeights(base=1, bonus=0, equity=0, fit=0)))
    assert out["status"] == "queued"
    [insert] = conn.ran("INSERT INTO mw_job_searches")
    args = insert[2]
    assert args[3] == "Chief Operating Officer"  # title from the first title
    assert json.loads(args[6])["base"] == 1.0 and args[7] == "user"
    token = args[9]
    gates.dispatch.assert_awaited_once()
    assert gates.dispatch.await_args.args[1] == token
    # The shared allowance's lock: a card run started at the same moment waits too.
    assert conn.ran("pg_advisory_xact_lock")[0][2] == (f"{USER}:task_allowance",)
    assert conn.ran("updated_at < NOW() - INTERVAL '2 hours'")  # the stale sweep ran first
    # Its row in Tasks, in the same transaction: the search's id is its request id.
    [pointer] = conn.ran("INSERT INTO mw_agent_tasks")
    assert pointer[2][0] == SEARCH and pointer[2][3:5] == ("job_search", "job_search")
    assert pointer[2][7:9] == (None, None)  # not started from a conversation


@pytest.mark.asyncio
async def test_a_retried_create_is_answered_before_any_gate(gates, conn):
    # The first answer was lost; this person is now at the cap and over the
    # rate limit. The retry still gets the search it started.
    enqueue.find_by_request.return_value = {"id": "s1", "status": "enriching"}
    gates.usage.return_value = {"limit": 4, "used": 4, "remaining": 0}
    gates.rate.side_effect = HTTPException(status_code=429, detail="slow down")
    out = await enqueue.create_search(CLIENT, COMPANY, body())
    assert out == {"id": "s1", "status": "enriching"}
    gates.plan.assert_not_awaited()
    gates.rate.assert_not_awaited()
    assert not conn.calls


@pytest.mark.asyncio
async def test_create_is_idempotent_and_capped(gates, conn):
    conn.on("WHERE user_id = $1 AND request_id = $2", search_row(status="enriching"))
    out = await enqueue.create_search(CLIENT, COMPANY, body())
    assert out["status"] == "enriching" and not conn.ran("INSERT INTO")
    gates.dispatch.assert_not_awaited()

    conn.on("WHERE user_id = $1 AND request_id = $2", None)
    # 56 of Pro's 60 units used: a search (5) doesn't fit, so in searches the
    # month reads 12 of 12 used.
    conn.on("SELECT COUNT(*) FROM mw_job_searches", 56)
    with pytest.raises(HTTPException) as exc:
        await enqueue.create_search(CLIENT, COMPANY, body())
    assert exc.value.status_code == 429 and exc.value.detail["code"] == "job_search_limit"
    assert (exc.value.detail["limit"], exc.value.detail["used"], exc.value.detail["remaining"]) == (12, 12, 0)


@pytest.mark.asyncio
async def test_one_live_search_and_a_broker_that_is_down(gates, conn):
    conn.on("SELECT COUNT(*) FROM mw_job_searches", 0)
    conn.on("INSERT INTO mw_job_searches", asyncpg.UniqueViolationError("one live"))
    with pytest.raises(HTTPException) as exc:
        await enqueue.create_search(CLIENT, COMPANY, body())
    assert exc.value.status_code == 409 and exc.value.detail["code"] == "job_search_running"

    conn.on("INSERT INTO mw_job_searches", search_row(status="queued"))
    gates.dispatch.side_effect = RuntimeError("broker down")
    with pytest.raises(HTTPException) as exc:
        await enqueue.create_search(CLIENT, COMPANY, body())
    assert exc.value.status_code == 503
    # Failed is free, and frees the one-live-search slot.
    assert conn.ran("SET status = 'failed', error = 'Could not be queued.'")


@pytest.mark.asyncio
async def test_dispatch_routes_to_the_configured_queue(monkeypatch):
    from app.workers.tasks import job_search as task_module

    calls = []
    monkeypatch.setattr(task_module.run_job_search_phase, "apply_async", lambda **kw: calls.append(kw))
    monkeypatch.setenv("AGENT_JOBS_QUEUE", "agent_jobs")
    sid, token = uuid4(), uuid4()
    await enqueue.dispatch(sid, token, countdown=30)
    assert calls == [{"args": [str(sid), str(token)], "queue": "agent_jobs", "countdown": 30}]


@pytest.mark.asyncio
async def test_quota_counts_everything_but_failed(monkeypatch):
    """Job searches are the shared monthly allowance, counted in searches."""
    from app.matcha.services.matcha_work.agent_tasks import allowance
    from app.matcha.services.matcha_work.job_search import quota

    conn = FakeConn().on("FROM mw_job_searches", 23)  # units used, of Pro's 60
    monkeypatch.setattr(allowance, "connection_or_direct", connection(conn))
    usage = await quota.job_search_usage(USER, plan="pro")
    assert (usage["limit"], usage["used"], usage["remaining"]) == (12, 5, 7)
    assert "s.status <> 'failed'" in conn.calls[0][1]
    assert (await quota.job_search_usage(USER, plan="lite"))["limit"] == 0


@pytest.mark.asyncio
async def test_consent_granted_reads_the_grant(monkeypatch):
    monkeypatch.setattr(grants, "list_rows", AsyncMock(return_value={
        "jobs": {"enabled": True, "consent_version": "jobs-2"}}))
    assert await enqueue.consent_granted(USER) is True
    monkeypatch.setattr(grants, "list_rows", AsyncMock(return_value={
        "jobs": {"enabled": True, "consent_version": "jobs-0"}}))
    assert await enqueue.consent_granted(USER) is False
