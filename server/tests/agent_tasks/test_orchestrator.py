"""Tasks on the chain engine: phases by name, endings, settling and telling."""
from dataclasses import replace
from unittest.mock import AsyncMock

import pytest

from app.matcha.services.matcha_work.agent_runtime import chain
from app.matcha.services.matcha_work.agent_runtime.chain import PhaseFailed, PhaseOutcome
from app.matcha.services.matcha_work.agent_tasks import orchestrator
from app.matcha.services.matcha_work.agent_tasks.research import phases
from tests.agent_runtime.helpers import FakeConn, connection

from ._fixtures import TASK, TOKEN, task_row


@pytest.fixture
def wired(monkeypatch):
    conn = FakeConn()
    dispatch = AsyncMock(return_value=None)
    monkeypatch.setattr(chain, "connection_or_direct", connection(conn))
    monkeypatch.setattr(orchestrator, "connection_or_direct", connection(conn))
    monkeypatch.setattr(orchestrator, "TASK_CHAIN", replace(orchestrator.TASK_CHAIN, dispatch=dispatch,
                                                           phases=dict(orchestrator.TASK_CHAIN.phases)))
    conn.on("UPDATE mw_agent_tasks\n               SET status = $3", {"id": TASK})
    return conn, dispatch


def test_the_spec():
    spec = orchestrator.TASK_CHAIN
    assert spec.table == "mw_agent_tasks" and spec.phase_column == "phase"
    assert spec.live == ("queued", "running") and "research.plan" in spec.phases
    assert spec.budget_columns == {"provider_calls", "fetch_calls", "browser_views"}


@pytest.mark.asyncio
async def test_a_phase_runs_by_its_stored_name_and_hands_on(wired):
    conn, dispatch = wired
    conn.on("attempts = attempts + 1", task_row(status="running", phase="research.plan", attempts=1))
    plan = AsyncMock(return_value=PhaseOutcome("running", {"note": "Searching"}, phase="research.providers"))
    orchestrator.TASK_CHAIN.phases["research.plan"] = plan
    await orchestrator.run_phase(TASK, TOKEN, deps=phases.Deps())
    [advance] = conn.ran("SET status = $3")
    assert advance[2][2] == "running" and advance[2][9] == "research.providers"
    dispatch.assert_awaited_once()
    assert isinstance(plan.await_args.args[1], phases.Deps)


@pytest.mark.asyncio
async def test_a_task_that_cannot_go_on(wired, monkeypatch):
    conn, dispatch = wired
    stopped = AsyncMock()
    monkeypatch.setattr(orchestrator, "TASK_CHAIN", replace(orchestrator.TASK_CHAIN, on_terminal=stopped))
    conn.on("attempts = attempts + 1", task_row(status="running", phase="research.discover", attempts=1))
    orchestrator.TASK_CHAIN.phases["research.discover"] = AsyncMock(side_effect=PhaseFailed("Nothing matched."))
    conn.on("SELECT COUNT(*) FROM mw_agent_task_items", 0)
    await orchestrator.run_phase(TASK, TOKEN)
    [advance] = conn.ran("SET status = $3")
    assert advance[2][2] == "failed" and advance[2][7] == "Nothing matched."
    stopped.assert_awaited_once()
    dispatch.assert_not_awaited()


@pytest.mark.asyncio
async def test_ending_keeps_what_was_found(wired, monkeypatch):
    conn, _ = wired
    rerank = AsyncMock(return_value=3)
    monkeypatch.setattr(orchestrator.playbooks, "get", lambda key: type("P", (), {"rerank": rerank})())
    conn.on("SELECT COUNT(*) FROM mw_agent_task_items", 3)
    conn.on("SELECT * FROM mw_agent_tasks WHERE id = $1", task_row())
    out = await orchestrator._ending(task_row(), "time ran out")
    assert out.status == "done" and out.progress["note"] == "Stopped early: time ran out"
    rerank.assert_awaited_once()
    conn.on("SELECT COUNT(*) FROM mw_agent_task_items", 0)
    assert (await orchestrator._ending(task_row(), "x")).status == "failed"


@pytest.mark.asyncio
async def test_stopping_settles_the_round_and_tells_the_person(monkeypatch):
    close, tell = AsyncMock(), AsyncMock()
    monkeypatch.setattr(orchestrator.service, "close_round", close)
    monkeypatch.setattr(orchestrator.notify, "task_stopped", tell)
    await orchestrator._stopped("conn", TASK)
    close.assert_awaited_once_with("conn", TASK)
    tell.assert_awaited_once_with("conn", TASK)


@pytest.mark.asyncio
async def test_nudge_and_reconcile(monkeypatch):
    monkeypatch.setattr(chain, "nudge", AsyncMock(return_value=True))
    monkeypatch.setattr(chain, "reconcile", AsyncMock(return_value={"ended": 1, "restarted": 0}))
    monkeypatch.setattr(orchestrator.service, "expire_waiting", AsyncMock(return_value=2))
    assert await orchestrator.nudge(TASK) is True
    assert await orchestrator.reconcile() == {"ended": 1, "restarted": 0, "expired": 2}


def test_worker_tasks_run_the_orchestrator(monkeypatch):
    from app.workers.tasks import agent_tasks as worker

    run, rec = AsyncMock(), AsyncMock()
    monkeypatch.setattr(orchestrator, "run_phase", run)
    monkeypatch.setattr(orchestrator, "reconcile", rec)
    worker.run_agent_task_phase.run(str(TASK), str(TOKEN))
    run.assert_awaited_once_with(TASK, TOKEN)
    worker.reconcile_agent_tasks.run()
    rec.assert_awaited_once()
