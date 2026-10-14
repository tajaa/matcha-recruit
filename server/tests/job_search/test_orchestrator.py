"""The task chain: claims, new tokens per phase, retries, endings, restarts."""
import json
from unittest.mock import AsyncMock
from uuid import uuid4

import pytest

from app.matcha.services.matcha_work.job_search import orchestrator
from app.matcha.services.matcha_work.job_search.phases import PhaseFailed, PhaseOutcome
from tests.agent_runtime.helpers import FakeConn, connection

from ._fixtures import LEAD, SEARCH, TOKEN, search_row


@pytest.fixture
def wired(monkeypatch):
    conn = FakeConn()
    dispatch = AsyncMock(return_value=None)
    rerank = AsyncMock(return_value=3)
    monkeypatch.setattr(orchestrator, "connection_or_direct", connection(conn))
    monkeypatch.setattr(orchestrator, "dispatch", dispatch)
    monkeypatch.setattr(orchestrator, "rerank", rerank)
    conn.on("UPDATE mw_job_searches\n               SET status = $3", {"id": SEARCH})
    return conn, dispatch, rerank


def advance_args(conn):
    [call] = conn.ran("SET status = $3")
    return call[2]


@pytest.mark.asyncio
async def test_a_task_that_cannot_claim_does_nothing(wired, monkeypatch):
    conn, dispatch, _ = wired
    phase = AsyncMock()
    monkeypatch.setitem(orchestrator.PHASES, "planning", phase)
    await orchestrator.run_phase(SEARCH, TOKEN)
    phase.assert_not_awaited()
    dispatch.assert_not_awaited()
    claim = conn.calls[0][1]
    assert "dispatch_token = $2" in claim and "lease_until < NOW()" in claim


@pytest.mark.asyncio
async def test_a_finished_phase_hands_the_next_task_a_new_token(wired, monkeypatch):
    conn, dispatch, _ = wired
    conn.on("attempts = attempts + 1", search_row(status="planning", attempts=1))
    monkeypatch.setitem(orchestrator.PHASES, "planning",
                        AsyncMock(return_value=PhaseOutcome("discovering", {"note": "Searching"})))
    await orchestrator.run_phase(SEARCH, TOKEN)
    args = advance_args(conn)
    assert args[:3] == (SEARCH, TOKEN, "discovering")
    new_token = args[3]
    assert new_token not in (None, TOKEN) and args[4] is False  # attempts reset
    dispatch.assert_awaited_once_with(SEARCH, new_token, countdown=0)


@pytest.mark.asyncio
async def test_terminal_outcome_and_a_retired_chain(wired, monkeypatch):
    conn, dispatch, _ = wired
    conn.on("attempts = attempts + 1", search_row(status="enriching", attempts=1))
    monkeypatch.setitem(orchestrator.PHASES, "enriching", AsyncMock(return_value=PhaseOutcome("done")))
    await orchestrator.run_phase(SEARCH, TOKEN)
    args = advance_args(conn)
    assert args[2] == "done" and args[3] is None and args[8] is True  # completed_at
    # Anything still waiting for an approach can be redrafted, not "drafting" forever.
    assert conn.ran("SET approach_status = 'failed'")[0][2] == (SEARCH,)
    dispatch.assert_not_awaited()

    conn.on("UPDATE mw_job_searches\n               SET status = $3", None)  # cancelled meanwhile
    monkeypatch.setitem(orchestrator.PHASES, "enriching", AsyncMock(return_value=PhaseOutcome("enriching")))
    await orchestrator.run_phase(SEARCH, TOKEN)
    dispatch.assert_not_awaited()


@pytest.mark.asyncio
async def test_a_failing_step_is_retried_then_the_search_ends(wired, monkeypatch):
    conn, dispatch, rerank = wired
    conn.on("attempts = attempts + 1", search_row(status="discovering", attempts=1))
    monkeypatch.setitem(orchestrator.PHASES, "discovering", AsyncMock(side_effect=RuntimeError("flaky")))
    await orchestrator.run_phase(SEARCH, TOKEN)
    args = advance_args(conn)
    assert args[2] == "discovering" and args[4] is True  # attempts kept
    assert dispatch.await_args.kwargs == {"countdown": orchestrator.RETRY_COUNTDOWN}

    # Third attempt, nothing found yet: failed, which is free.
    conn.calls.clear()
    conn.on("attempts = attempts + 1", search_row(status="discovering", attempts=3))
    conn.on("SELECT COUNT(*) FROM mw_job_leads", 0)
    await orchestrator.run_phase(SEARCH, TOKEN)
    args = advance_args(conn)
    assert args[2] == "failed" and "kept failing" in args[7]
    rerank.assert_not_awaited()

    # With jobs already found, it ends `done` and ranks them.
    conn.calls.clear()
    conn.on("SELECT COUNT(*) FROM mw_job_leads", 12)
    conn.on("SELECT * FROM mw_job_searches WHERE id = $1", search_row())
    monkeypatch.setitem(orchestrator.PHASES, "discovering", AsyncMock(side_effect=TimeoutError()))
    await orchestrator.run_phase(SEARCH, TOKEN)
    assert advance_args(conn)[2] == "done"
    rerank.assert_awaited_once()


@pytest.mark.asyncio
async def test_a_phase_whose_task_keeps_getting_killed_ends(wired, monkeypatch):
    """A killed task never reaches advance, so its claim's attempt stands; the
    claim past MAX_ATTEMPTS ends the search instead of running the phase."""
    conn, dispatch, rerank = wired
    phase = AsyncMock()
    monkeypatch.setitem(orchestrator.PHASES, "enriching", phase)
    conn.on("attempts = attempts + 1", search_row(status="enriching", attempts=orchestrator.MAX_ATTEMPTS + 1))
    conn.on("SELECT COUNT(*) FROM mw_job_leads", 9)
    conn.on("SELECT * FROM mw_job_searches WHERE id = $1", search_row())
    await orchestrator.run_phase(SEARCH, TOKEN)
    phase.assert_not_awaited()
    args = advance_args(conn)
    assert args[2] == "done" and "kept stopping" in args[7]  # found jobs: ranked, counted
    rerank.assert_awaited_once()
    dispatch.assert_not_awaited()
    assert "'10 minutes'" in conn.ran("attempts = attempts + 1")[0][1]


@pytest.mark.asyncio
async def test_a_cancelled_search_that_cannot_draft_stays_cancelled(wired, monkeypatch):
    """A redraft on a cancelled search that keeps dying ends `cancelled`,
    not `done`: it was never a finished search."""
    conn, dispatch, rerank = wired
    monkeypatch.setitem(orchestrator.PHASES, "approaching", AsyncMock())
    cursor = json.dumps({"approach_queue": [str(LEAD)], "after": "cancelled"})
    conn.on("attempts = attempts + 1", search_row(status="approaching", phase_cursor=cursor,
                                                  attempts=orchestrator.MAX_ATTEMPTS + 1))
    await orchestrator.run_phase(SEARCH, TOKEN)
    args = advance_args(conn)
    assert args[2] == "cancelled" and "Couldn't draft the approach" in args[5]
    rerank.assert_not_awaited()
    dispatch.assert_not_awaited()


@pytest.mark.asyncio
async def test_phase_failed_and_unknown_steps_end_at_once(wired, monkeypatch):
    conn, dispatch, _ = wired
    conn.on("attempts = attempts + 1", search_row(status="discovering", attempts=1))
    conn.on("SELECT COUNT(*) FROM mw_job_leads", 0)
    monkeypatch.setitem(orchestrator.PHASES, "discovering",
                        AsyncMock(side_effect=PhaseFailed("No postings matched.")))
    await orchestrator.run_phase(SEARCH, TOKEN)
    args = advance_args(conn)
    assert args[2] == "failed" and args[7] == "No postings matched."

    conn.calls.clear()
    conn.on("attempts = attempts + 1", search_row(status="screening", attempts=1))
    monkeypatch.delitem(orchestrator.PHASES, "screening")  # a status with no phase
    await orchestrator.run_phase(SEARCH, TOKEN)
    assert advance_args(conn)[2] == "failed"
    dispatch.assert_not_awaited()


@pytest.mark.asyncio
async def test_a_lost_dispatch_is_left_for_nudge(wired, monkeypatch):
    conn, dispatch, _ = wired
    conn.on("attempts = attempts + 1", search_row(status="planning", attempts=1))
    monkeypatch.setitem(orchestrator.PHASES, "planning", AsyncMock(return_value=PhaseOutcome("discovering")))
    dispatch.side_effect = RuntimeError("broker down")
    assert set(orchestrator.PHASES) == {"planning", "discovering", "screening", "enriching", "approaching"}
    await orchestrator.run_phase(SEARCH, TOKEN)  # does not raise


@pytest.mark.asyncio
async def test_nudge_and_reconcile(wired):
    conn, dispatch, _ = wired
    assert await orchestrator.nudge(SEARCH) is False  # not idle: nothing returned
    conn.on("SET dispatch_token = $2, updated_at = NOW()", {"id": SEARCH})
    assert await orchestrator.nudge(SEARCH) is True
    new_token = dispatch.await_args.args[1]
    assert new_token != TOKEN
    dispatch.side_effect = RuntimeError("down")
    assert await orchestrator.nudge(SEARCH) is False
    dispatch.side_effect = None

    idle, dead = uuid4(), uuid4()
    conn.on("ORDER BY updated_at LIMIT 200", [search_row(id=idle), search_row(id=dead, status="enriching")])
    conn.on("updated_at < NOW() - INTERVAL '2 hours'", [{"id": dead}])
    conn.on("SELECT COUNT(*) FROM mw_job_leads", 0)
    out = await orchestrator.reconcile()
    assert out == {"ended": 1, "restarted": 1}

    broken = FakeConn().on("SET dispatch_token = $2", RuntimeError("db"))
    orchestrator.connection_or_direct = connection(broken)
    assert await orchestrator.nudge(SEARCH) is False


def test_worker_tasks_run_the_orchestrator(monkeypatch):
    from app.workers.celery_app import celery_app
    from app.workers.tasks import job_search as tasks

    run_phase, reconcile = AsyncMock(), AsyncMock(return_value={})
    monkeypatch.setattr(orchestrator, "run_phase", run_phase)
    monkeypatch.setattr(orchestrator, "reconcile", reconcile)
    tasks.run_job_search_phase(str(SEARCH), str(TOKEN))
    run_phase.assert_awaited_once_with(SEARCH, TOKEN)
    tasks.reconcile_job_searches()
    reconcile.assert_awaited_once()
    assert "app.workers.tasks.job_search" in celery_app.conf.include
    # Under Celery's soft limit, with the phase's own 420s budget inside it.
    assert tasks.run_job_search_phase.soft_time_limit > orchestrator.PHASE_SECONDS
