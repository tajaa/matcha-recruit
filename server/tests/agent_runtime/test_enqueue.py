from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock
from uuid import uuid4

import asyncpg
import pytest
from fastapi import HTTPException

from app.core.services import redis_cache
from app.matcha.services.billing import entitlements_service, token_budget_service
from app.matcha.services.matcha_work.agent_runtime import enqueue, quota
from app.workers.tasks import assistant as assistant_task

from .helpers import FakeConn, connection


def _user(role="client"):
    return SimpleNamespace(id=uuid4(), role=role)


def _features(is_personal=True, **flags):
    return {"enabled_features": {"matcha_work": True, **flags},
            "signup_source": "bespoke", "is_personal": is_personal}


@pytest.fixture
def wired(monkeypatch):
    conn = FakeConn([("FROM companies", _features()), ("COUNT(*)", 0),
                     ("INSERT INTO mw_project_agent_runs", uuid4())])
    monkeypatch.setattr(enqueue, "get_connection", connection(conn))
    monkeypatch.setattr(entitlements_service, "resolve_plan_for_user", AsyncMock(return_value="pro"))
    monkeypatch.setattr(token_budget_service, "check_token_budget", AsyncMock())
    monkeypatch.setattr(redis_cache, "check_rate_limit", AsyncMock())
    dispatch = Mock()
    monkeypatch.setattr(assistant_task.run_assistant, "apply_async", dispatch)
    for env in ("AGENT_ASSISTANT_QUEUE", "AGENT_CARD_QUEUE", "AGENT_BROWSER_QUEUE"):
        monkeypatch.delenv(env, raising=False)
    return conn, dispatch


def _kwargs(user, **over):
    base = dict(user=user, company_id=uuid4(), channel_id=uuid4(), trigger_message_id=uuid4(),
                project_id=None, surface="assistant", prompt="find a desk", abilities=["web", "shopping"])
    base.update(over)
    return base


# ── preflight ──────────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_preflight_needs_a_personal_workspace(wired, monkeypatch):
    conn, _ = wired
    # A business workspace never has it, whatever its stored flags say.
    for row in (None, _features(is_personal=False, espresso_assistant=True), _features(matcha_work=False)):
        conn.on("FROM companies", row)
        with pytest.raises(HTTPException) as exc:
            await enqueue.preflight(_user(), uuid4())
        assert exc.value.status_code == 403 and exc.value.detail["code"] == "feature_disabled"
    # It gates admins too: it is about the workspace, not a plan.
    with pytest.raises(HTTPException):
        await enqueue.preflight(_user("admin"), uuid4())


@pytest.mark.asyncio
async def test_preflight_requires_pro(wired, monkeypatch):
    monkeypatch.setattr(entitlements_service, "resolve_plan_for_user", AsyncMock(return_value="lite"))
    with pytest.raises(HTTPException) as exc:
        await enqueue.preflight(_user(), uuid4())
    assert exc.value.detail["code"] == "plan_required" and exc.value.detail["feature"] == "assistant"


@pytest.mark.asyncio
async def test_preflight_enforces_the_daily_allowance_then_budget_then_rate(wired, monkeypatch):
    monkeypatch.setattr(enqueue, "assistant_usage", AsyncMock(return_value={
        "limit": 30, "used": 30, "remaining": 0, "resets_at": "2026-09-30T00:00:00+00:00"}))
    with pytest.raises(HTTPException) as exc:
        await enqueue.preflight(_user(), uuid4())
    assert exc.value.status_code == 429 and exc.value.detail["code"] == "assistant_run_limit"
    token_budget_service.check_token_budget.assert_not_awaited()

    monkeypatch.setattr(enqueue, "assistant_usage", AsyncMock(return_value={"limit": 30, "used": 1, "remaining": 29}))
    user, company = _user(), uuid4()
    await enqueue.preflight(user, company)
    token_budget_service.check_token_budget.assert_awaited_once_with(company)
    redis_cache.check_rate_limit.assert_awaited_once_with(str(user.id), "espresso_assistant_user", 30, 3600)


@pytest.mark.asyncio
async def test_an_admin_skips_the_plan_and_the_allowance(wired):
    await enqueue.preflight(_user("admin"), uuid4())
    entitlements_service.resolve_plan_for_user.assert_not_awaited()


# ── enqueue ────────────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_locks_are_user_then_conversation_then_sweep_then_count_then_insert(wired):
    conn, dispatch = wired
    user = _user()
    kwargs = _kwargs(user)
    out = await enqueue.enqueue_assistant_run(**kwargs, skip_preflight=True)
    assert out["status"] == "queued"
    order = [c[1][:60] for c in conn.calls]
    kinds = []
    for method, query, args in conn.calls:
        if "pg_advisory_xact_lock" in query:
            kinds.append(("lock", args[0]))
        elif "SET status = 'failed'" in query:
            kinds.append(("sweep", None))
        elif "COUNT(*)" in query:
            kinds.append(("count", None))
        elif "INSERT INTO mw_project_agent_runs" in query:
            kinds.append(("insert", None))
    assert kinds == [
        ("lock", f"{user.id}:assistant_cap"),
        ("lock", f"{kwargs['channel_id']}:{user.id}:assistant"),
        ("sweep", None), ("count", None), ("insert", None),
    ], order
    sweep = conn.ran("SET status = 'failed'")[0]
    assert "INTERVAL '11 minutes'" in sweep[1] and sweep[2] == (kwargs["channel_id"], user.id)
    insert = conn.ran("INSERT INTO mw_project_agent_runs")[0]
    assert insert[2][:5] == (kwargs["company_id"], None, kwargs["channel_id"], user.id,
                             kwargs["trigger_message_id"])
    assert insert[2][5:] == ("find a desk", enqueue.ASSISTANT_MODEL, "assistant", ["web", "shopping"], None)
    assert "'espresso', 'assistant'" in insert[1]
    dispatch.assert_called_once_with(args=[out["run_id"]], queue=None)


@pytest.mark.asyncio
async def test_a_second_message_while_a_run_is_live_is_refused_not_queued(wired):
    conn, dispatch = wired
    conn.on("INSERT INTO mw_project_agent_runs", asyncpg.UniqueViolationError("live run"))
    with pytest.raises(HTTPException) as exc:
        await enqueue.enqueue_assistant_run(**_kwargs(_user()), skip_preflight=True)
    assert exc.value.status_code == 409 and exc.value.detail == enqueue.STILL_WORKING
    dispatch.assert_not_called()


@pytest.mark.asyncio
async def test_daily_cap_is_atomic_and_a_failed_run_is_free(wired):
    conn, dispatch = wired
    conn.on("COUNT(*)", 30)
    with pytest.raises(HTTPException) as exc:
        await enqueue.enqueue_assistant_run(**_kwargs(_user()), skip_preflight=True)
    assert exc.value.detail["code"] == "assistant_run_limit" and exc.value.detail["limit"] == 30
    assert conn.ran("INSERT INTO mw_project_agent_runs") == [] and conn.in_transaction == 0
    dispatch.assert_not_called()
    count = conn.ran("COUNT(*)")[0][1]
    assert "status IN ('queued', 'running', 'done')" in count and "kind = 'assistant'" in count


@pytest.mark.asyncio
async def test_an_admin_is_not_counted(wired):
    conn, dispatch = wired
    conn.on("COUNT(*)", 999)
    await enqueue.enqueue_assistant_run(**_kwargs(_user("admin")), skip_preflight=True)
    assert conn.ran("COUNT(*)") == [] and dispatch.called


@pytest.mark.asyncio
async def test_broker_down_fails_the_row(wired):
    conn, dispatch = wired
    dispatch.side_effect = RuntimeError("broker down")
    with pytest.raises(HTTPException) as exc:
        await enqueue.enqueue_assistant_run(**_kwargs(_user()), skip_preflight=True)
    assert exc.value.status_code == 503
    failed = conn.ran("error = 'Could not be queued.'")
    assert len(failed) == 1 and "status = 'queued'" in failed[0][1]


@pytest.mark.asyncio
async def test_the_same_trigger_message_never_starts_two_runs(wired):
    conn, dispatch = wired
    conn.on("INSERT INTO mw_project_agent_runs", None)  # ON CONFLICT DO NOTHING returned no row
    out = await enqueue.enqueue_assistant_run(**_kwargs(_user()), skip_preflight=True)
    assert out == {"run_id": None, "status": "duplicate"}
    assert "ON CONFLICT (trigger_message_id, agent_key) DO NOTHING" in conn.ran("INSERT INTO")[0][1]
    dispatch.assert_not_called()


@pytest.mark.asyncio
async def test_enqueue_runs_preflight_unless_told_it_already_ran(wired, monkeypatch):
    checked = AsyncMock()
    monkeypatch.setattr(enqueue, "preflight", checked)
    await enqueue.enqueue_assistant_run(**_kwargs(_user()))
    checked.assert_awaited_once()


def test_only_a_run_that_may_open_a_browser_goes_to_the_browser_worker(monkeypatch):
    for env in ("AGENT_ASSISTANT_QUEUE", "AGENT_CARD_QUEUE", "AGENT_BROWSER_QUEUE"):
        monkeypatch.delenv(env, raising=False)
    assert enqueue.queue_for(["web", "reservations"]) is None
    monkeypatch.setenv("AGENT_CARD_QUEUE", "agent_cards")
    assert enqueue.queue_for(["web"]) == "agent_cards"
    monkeypatch.setenv("AGENT_ASSISTANT_QUEUE", "assistant")
    assert enqueue.queue_for(["web", "email"]) == "assistant"
    monkeypatch.setenv("AGENT_BROWSER_QUEUE", "agent_browser")
    assert enqueue.queue_for(["web", "reservations"]) == "agent_browser"
    assert enqueue.queue_for(["web", "email"]) == "assistant"


# ── quota ──────────────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_the_card_cap_does_not_count_assistant_runs_and_the_reverse(monkeypatch):
    from datetime import datetime, timezone

    from app.matcha.services.matcha_work.agent_card import quota as card_quota

    conn = FakeConn([("COUNT(*)", 4)])
    assert await quota.used_today(conn, uuid4()) == 4
    assert "kind = 'assistant'" in conn.calls[0][1] and "date_trunc('day'" in conn.calls[0][1]
    card_conn = FakeConn([("COUNT(*)", 9)])
    await card_quota.used_this_month(card_conn, uuid4())
    assert "kind = 'card_agent'" in card_conn.calls[0][1]

    assert quota.limit_for_plan("pro") == 30 and quota.limit_for_plan("business") == 60
    assert quota.limit_for_plan("lite") == 0
    now = datetime(2026, 9, 29, 23, 30, tzinfo=timezone.utc)
    assert quota.usage_payload(30, 31, now=now) == {
        "limit": 30, "used": 31, "remaining": 0, "resets_at": "2026-09-30T00:00:00+00:00"}

    monkeypatch.setattr(quota, "connection_or_direct", connection(conn))
    monkeypatch.setattr(quota, "resolve_plan_for_user", AsyncMock(return_value="business"))
    usage = await quota.assistant_usage(uuid4())
    assert usage["limit"] == 60 and usage["used"] == 4 and usage["remaining"] == 56


@pytest.mark.asyncio
async def test_a_dead_run_swept_here_has_its_card_closed(wired, monkeypatch):
    from app.matcha.services.matcha_work.agent_runtime import assistant

    conn, _dispatch = wired
    dead = {"id": uuid4(), "channel_id": uuid4(), "company_id": uuid4()}
    conn.on("SET status = 'failed'", [dead])
    reported = AsyncMock()
    monkeypatch.setattr(assistant, "report_failure", reported)
    await enqueue.enqueue_assistant_run(**_kwargs(_user()), skip_preflight=True)
    # The reconciler never sees this row move, so the sweep reports it.
    reported.assert_awaited_once_with(dead, enqueue.INTERRUPTED)
