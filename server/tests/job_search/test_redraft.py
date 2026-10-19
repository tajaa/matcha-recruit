"""Redrafting one job's approach: finished or cancelled searches, capped, free."""
import json
from types import SimpleNamespace
from unittest.mock import AsyncMock
from uuid import uuid4

import asyncpg
import pytest

from app.matcha.services.matcha_work.agent_runtime import chain
from app.matcha.services.matcha_work.job_search import enqueue, phases, service
from tests.agent_runtime.helpers import FakeConn, connection

from ._fixtures import LEAD, SEARCH, USER, lead_row, search_row


@pytest.fixture
def conn(monkeypatch):
    conn = FakeConn()
    monkeypatch.setattr(service, "connection_or_direct", connection(conn))
    return conn


@pytest.mark.asyncio
@pytest.mark.parametrize("status", ["done", "cancelled"])
async def test_requeue_puts_one_job_back_in_the_chain(conn, status):
    """A cancelled search can draft too, and remembers to go back to cancelled."""
    conn.on("FOR UPDATE", search_row(status=status, redrafts=0))
    conn.on("FROM mw_job_leads WHERE id = $1 AND search_id = $2 FOR UPDATE", lead_row())
    conn.on("SET status = 'approaching'", search_row(status="approaching"))
    search, token = await service.requeue_approach(SEARCH, LEAD, USER)
    assert search["status"] == "approaching"
    [update] = conn.ran("SET status = 'approaching'")
    assert update[2][1] == token
    assert json.loads(update[2][2]) == {"approach_queue": [str(LEAD)], "after": status}
    assert "redrafts = redrafts + 1" in update[1] and "error = NULL" in update[1]
    assert conn.ran("SET approach_status = 'queued'")


@pytest.mark.asyncio
async def test_check_redraftable_reads_only(conn):
    conn.on("FROM mw_job_searches s", search_row(status="done", redrafts=0))
    await service.check_redraftable(SEARCH, USER)
    assert not conn.ran("FOR UPDATE") and not conn.ran("UPDATE")
    conn.on("FROM mw_job_searches s", search_row(status="approaching"))
    with pytest.raises(service.JobSearchError) as exc:
        await service.check_redraftable(SEARCH, USER)
    assert exc.value.code == 409


@pytest.mark.asyncio
@pytest.mark.parametrize("over, code", [
    ({"status": "enriching"}, 409), ({"status": "failed"}, 409), ({"status": "done", "redrafts": 20}, 429),
])
async def test_requeue_refusals(conn, over, code):
    conn.on("FOR UPDATE", search_row(**over))
    with pytest.raises(service.JobSearchError) as exc:
        await service.requeue_approach(SEARCH, LEAD, USER)
    assert exc.value.code == code


@pytest.mark.asyncio
async def test_requeue_missing_job_and_another_live_search(conn):
    conn.on("FOR UPDATE", search_row(status="done", redrafts=0))
    conn.on("FROM mw_job_leads WHERE id = $1 AND search_id = $2 FOR UPDATE", None)
    with pytest.raises(service.JobSearchError) as exc:
        await service.requeue_approach(SEARCH, uuid4(), USER)
    assert exc.value.code == 404
    conn.on("FROM mw_job_leads WHERE id = $1 AND search_id = $2 FOR UPDATE", lead_row())
    conn.on("SET status = 'approaching'", asyncpg.UniqueViolationError("one live"))
    with pytest.raises(service.JobSearchError) as exc:
        await service.requeue_approach(SEARCH, LEAD, USER)
    assert exc.value.code == 409


@pytest.mark.asyncio
async def test_redraft_dispatches_and_tolerates_a_down_broker(monkeypatch):
    from app.core.services import redis_cache

    token = uuid4()
    monkeypatch.setattr(service, "requeue_approach", AsyncMock(return_value=({}, token)))
    monkeypatch.setattr(service, "get_search", AsyncMock(return_value={"status": "approaching"}))
    check = AsyncMock()
    monkeypatch.setattr(service, "check_redraftable", check)
    rate = AsyncMock()
    monkeypatch.setattr(redis_cache, "check_rate_limit", rate)
    dispatch = AsyncMock()
    monkeypatch.setattr(enqueue, "dispatch", dispatch)
    user = SimpleNamespace(id=USER, role="client")
    assert await enqueue.redraft_approach(user, SEARCH, LEAD) == {"status": "approaching"}
    dispatch.assert_awaited_once_with(SEARCH, token)
    assert rate.await_args.args[1:] == ("espresso_job_search_redraft", 10, 3600)
    check.assert_awaited_once_with(SEARCH, USER)
    # A refusal spends none of the hour's redrafts.
    check.side_effect = service.JobSearchError("still running", 409)
    with pytest.raises(service.JobSearchError):
        await enqueue.redraft_approach(user, SEARCH, LEAD)
    assert rate.await_count == 1
    check.side_effect = None
    dispatch.side_effect = RuntimeError("down")
    await enqueue.redraft_approach(SimpleNamespace(id=USER, role="admin"), SEARCH, LEAD)
    assert rate.await_count == 1  # admins skip the rate limit


@pytest.mark.asyncio
async def test_enrich_queues_the_top_jobs_for_approaches(monkeypatch):
    conn = FakeConn()
    monkeypatch.setattr(phases, "connection_or_direct", connection(conn))
    # The guard's token check and grant/refund run in agent_runtime.chain.
    monkeypatch.setattr(chain, "connection_or_direct", connection(conn))
    monkeypatch.setattr(phases, "rerank", AsyncMock(return_value=3))
    top = [{"id": uuid4(), "rank": 2}, {"id": uuid4(), "rank": 1}]
    conn.on("SET approach_status = 'queued'", top)
    conn.on("COUNT(*) FILTER", {"total": 3, "posted": 2})
    conn.on("SELECT 1 FROM mw_job_searches WHERE id = $1 AND dispatch_token = $2", 1)
    conn.on("SET progress = progress || $2::jsonb", search_row(status="enriching"))
    token = uuid4()
    out = await phases.enrich(search_row(status="enriching", fetch_calls=phases.MAX_FETCHES),
                              phases.Deps(), phases.Guard(SEARCH, token))
    assert out.status == "approaching"
    assert out.cursor == {"approach_queue": [str(top[1]["id"]), str(top[0]["id"])]}
    [(_m, queued, args)] = conn.ran("SET approach_status = 'queued'")
    # Only matches at the search's fit floor are drafted.
    assert f"LIMIT {phases.APPROACH_TOP}" in queued and "rank_band < 8" in queued
    # Under the token, in the floor write's transaction: a cancel between the
    # two can't leave jobs queued after `release_drafts` ran.
    assert "dispatch_token = $2" in queued and args[1] == token
    assert conn.ran("SET progress = progress || $2::jsonb")[0][2][2] == token


@pytest.mark.asyncio
async def test_rerank_passes_the_pay_law_states():
    conn = FakeConn().on("SELECT id, comp, fit_score", [
        {"id": uuid4(), "comp": "{}", "fit_score": 3, "screen_status": "relevant", "user_state": "new",
         "posted_text": None}])
    await service.rerank(conn, search_row())
    [write] = conn.ran("unnest(")
    assert "MA" in write[2][6] and "CA" in write[2][6] and "pay_law_hint" in write[1]


@pytest.mark.asyncio
async def test_redraft_route(monkeypatch):
    from app.core.models.auth import CurrentUser
    from app.matcha.routes.matcha_work import job_search as routes

    user = CurrentUser(id=USER, email="owner@example.test", role="client")
    monkeypatch.setattr(routes.enqueue, "redraft_approach", AsyncMock(return_value={"ok": True}))
    assert await routes.redraft_job_approach(SEARCH, LEAD, user) == {"ok": True}
    assert routes.enqueue.redraft_approach.await_args.args == (user, SEARCH, LEAD)
