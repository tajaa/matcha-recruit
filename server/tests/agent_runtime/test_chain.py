"""The chain engine over a spec that is not job search's: a row whose phase is
its own column, on the agent-task table, with its own budget counter."""
import asyncio
import json
from dataclasses import replace
from unittest.mock import AsyncMock
from uuid import uuid4

import pytest

from app.matcha.services.matcha_work.agent_runtime import chain
from app.matcha.services.matcha_work.agent_runtime.chain import PhaseFailed, PhaseOutcome

from .helpers import FakeConn, connection

TASK, TOKEN = uuid4(), uuid4()
ADVANCE = "UPDATE mw_agent_tasks\n               SET status = $3"


def task_row(**over):
    return {"id": TASK, "status": "running", "phase": "plan", "dispatch_token": TOKEN,
            "attempts": 1, "progress": "{}", "phase_cursor": "{}", **over}


async def _ending(row, message):
    return PhaseOutcome(status="failed", progress={"note": message})


def make_spec(**over):
    base = dict(
        table="mw_agent_tasks",
        live=("queued", "running"),
        start=("queued", "running"),
        phases={"plan": AsyncMock(return_value=PhaseOutcome("running", {"note": "Planned"}, phase="act"))},
        dispatch=AsyncMock(return_value=None),
        ending=AsyncMock(side_effect=_ending),
        on_terminal=AsyncMock(),
        phase_column="phase",
        budget_columns=frozenset({"web_calls"}),
        name="agent task",
        noun="task",
        phase_seconds=5,
        lease_interval="9 minutes",
        max_attempts=2,
        retry_countdown=7,
        idle_interval="3 minutes",
        stale_interval="4 hours",
    )
    base.update(over)
    return chain.ChainSpec(**base)


@pytest.fixture
def wired(monkeypatch):
    conn = FakeConn()
    monkeypatch.setattr(chain, "connection_or_direct", connection(conn))
    conn.on(ADVANCE, {"id": TASK})
    return conn, make_spec()


def advance_args(conn):
    [call] = conn.ran("SET status = $3")
    return call[2]


# ── the spec ─────────────────────────────────────────────────────────────────

@pytest.mark.parametrize("over", [
    {"table": "users"},
    {"table": "mw_job_searches; DROP TABLE users"},
    {"live": ("running'; --",)},
    {"live": ()},
    {"start": ("queued", "Running")},
    {"budget_columns": frozenset({"web_calls = 0, attempts"})},
    {"phase_column": "phase; --"},
    {"lease_interval": "10 minutes'; --"},
    {"idle_interval": "soon"},
    {"stale_interval": "0 hours"},
])
def test_a_spec_is_checked_when_it_is_built(over):
    with pytest.raises(ValueError):
        make_spec(**over)


def test_the_job_search_spec():
    from app.matcha.services.matcha_work.job_search import orchestrator, phases

    spec = orchestrator.JOB_CHAIN
    assert spec.table == "mw_job_searches" and spec.phase_column is None
    assert spec.budget_columns == phases.BUDGET_COLUMNS == {"provider_calls", "fetch_calls"}
    assert spec.phases is orchestrator.PHASES and spec.start == ("queued", "planning")
    assert spec.live_sql.startswith("'queued', 'planning'")


# ── claim ────────────────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_claim_needs_the_token_a_live_row_and_an_expired_lease(wired):
    conn, spec = wired
    assert await chain.claim(spec, TASK, TOKEN) is None  # nothing matched
    conn.on("attempts = attempts + 1", task_row(attempts=2))
    assert await chain.claim(spec, TASK, TOKEN) == task_row(attempts=2)
    [_, (_, sql, args)] = conn.ran("attempts = attempts + 1")
    assert args == (TASK, TOKEN)
    assert sql.startswith("UPDATE mw_agent_tasks")
    for part in ("dispatch_token = $2", "deleted_at IS NULL", "status IN ('queued', 'running')",
                 "(lease_until IS NULL OR lease_until < NOW())", "attempts = attempts + 1",
                 "INTERVAL '9 minutes'", "CASE WHEN status = 'queued' THEN 'running' ELSE status END"):
        assert part in sql


# ── advance ──────────────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_advance_writes_under_the_token_and_hands_on_a_new_one(wired):
    conn, spec = wired
    written, next_token = await chain.advance(spec, TASK, TOKEN, PhaseOutcome("running", {"note": "x"}, phase="act"))
    assert written is True and next_token not in (None, TOKEN)
    [(_, sql, args)] = conn.ran("SET status = $3")
    assert "WHERE id = $1 AND dispatch_token = $2" in sql
    assert "phase = COALESCE($10::text, phase)" in sql
    assert args[:5] == (TASK, TOKEN, "running", next_token, False)  # attempts reset
    assert json.loads(args[5]) == {"note": "x"} and args[8] is False and args[9] == "act"
    spec.on_terminal.assert_not_awaited()


@pytest.mark.asyncio
async def test_a_terminal_outcome_ends_the_chain(wired):
    conn, spec = wired
    written, next_token = await chain.advance(spec, TASK, TOKEN, PhaseOutcome("done"), error="why")
    assert (written, next_token) == (True, None)
    args = advance_args(conn)
    assert args[3] is None and args[7] == "why" and args[8] is True  # completed_at
    spec.on_terminal.assert_awaited_once_with(conn, TASK)


@pytest.mark.asyncio
async def test_a_retired_chain_writes_nothing(wired):
    conn, spec = wired
    conn.on(ADVANCE, None)  # cancelled, deleted, or replaced by a restart
    assert await chain.advance(spec, TASK, TOKEN, PhaseOutcome("done")) == (False, None)
    spec.on_terminal.assert_not_awaited()


@pytest.mark.asyncio
async def test_without_a_phase_column_the_status_is_the_phase(wired):
    conn, spec = wired
    spec = replace(spec, phase_column=None)
    await chain.advance(spec, TASK, TOKEN, PhaseOutcome("running"), retry=True)
    [(_, sql, args)] = conn.ran("SET status = $3")
    assert "COALESCE($10" not in sql and len(args) == 9 and args[4] is True


# ── one task ─────────────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_a_task_that_cannot_claim_does_nothing(wired):
    conn, spec = wired
    await chain.run_phase(spec, TASK, TOKEN)
    spec.phases["plan"].assert_not_awaited()
    spec.dispatch.assert_not_awaited()
    assert not conn.ran("SET status = $3")


@pytest.mark.asyncio
async def test_the_phase_column_picks_the_phase_and_the_next_task_is_dispatched(wired):
    conn, spec = wired
    conn.on("attempts = attempts + 1", task_row(status="running", phase="plan"))
    deps = object()
    await chain.run_phase(spec, TASK, TOKEN, deps=deps)
    row, got_deps, guard = spec.phases["plan"].await_args.args
    assert row["id"] == TASK and got_deps is deps
    assert isinstance(guard, chain.Guard) and (guard.spec, guard.row_id, guard.token) == (spec, TASK, TOKEN)
    args = advance_args(conn)
    assert args[2] == "running" and args[9] == "act"
    spec.dispatch.assert_awaited_once_with(TASK, args[3], countdown=0)


@pytest.mark.asyncio
async def test_a_failure_is_retried_keeping_attempts_then_ends(wired):
    conn, spec = wired
    spec.phases["plan"] = AsyncMock(side_effect=RuntimeError("flaky"))
    conn.on("attempts = attempts + 1", task_row(attempts=1))
    await chain.run_phase(spec, TASK, TOKEN)
    args = advance_args(conn)
    assert args[2] == "running" and args[4] is True  # attempts kept
    assert "trying that step again" in json.loads(args[5])["note"]
    assert spec.dispatch.await_args.kwargs == {"countdown": 7}
    spec.ending.assert_not_awaited()

    conn.calls.clear()
    conn.on("attempts = attempts + 1", task_row(attempts=2))  # the last allowed attempt
    await chain.run_phase(spec, TASK, TOKEN)
    args = advance_args(conn)
    assert args[2] == "failed" and args[7] == "A step kept failing, so the task stopped. (RuntimeError)"
    spec.on_terminal.assert_awaited_once()


@pytest.mark.asyncio
async def test_a_phase_over_its_time_is_a_failure(wired):
    conn, spec = wired

    async def slow(row, deps, guard):
        await asyncio.sleep(5)

    spec = replace(spec, phases={"plan": slow}, phase_seconds=0.01)
    conn.on("attempts = attempts + 1", task_row(attempts=1))
    await chain.run_phase(spec, TASK, TOKEN)
    assert advance_args(conn)[4] is True  # retried


@pytest.mark.asyncio
async def test_attempts_past_the_max_end_the_row_without_running_it(wired):
    """A killed task never reaches advance, so its claim's attempt stands."""
    conn, spec = wired
    conn.on("attempts = attempts + 1", task_row(attempts=3))
    await chain.run_phase(spec, TASK, TOKEN)
    spec.phases["plan"].assert_not_awaited()
    message = "A step kept stopping before it finished, so the task stopped."
    spec.ending.assert_awaited_once_with(task_row(attempts=3), message)
    args = advance_args(conn)
    assert args[2] == "failed" and args[7] == message
    spec.dispatch.assert_not_awaited()


@pytest.mark.asyncio
async def test_phase_failed_and_an_unknown_phase_end_at_once(wired):
    conn, spec = wired
    spec.phases["plan"] = AsyncMock(side_effect=PhaseFailed("Nothing to do."))
    conn.on("attempts = attempts + 1", task_row())
    await chain.run_phase(spec, TASK, TOKEN)
    assert advance_args(conn)[7] == "Nothing to do."

    conn.calls.clear()
    conn.on("attempts = attempts + 1", task_row(phase="missing"))
    await chain.run_phase(spec, TASK, TOKEN)
    assert advance_args(conn)[7] == "Unknown step 'missing'."
    spec.dispatch.assert_not_awaited()


@pytest.mark.asyncio
async def test_a_lost_dispatch_is_left_for_nudge(wired):
    conn, spec = wired
    conn.on("attempts = attempts + 1", task_row())
    spec.dispatch.side_effect = RuntimeError("broker down")
    await chain.run_phase(spec, TASK, TOKEN)  # does not raise
    assert advance_args(conn)[3] is not None


# ── recovery ─────────────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_restart_retokens_only_an_idle_unleased_live_row(wired):
    conn, spec = wired
    assert await chain.nudge(spec, TASK) is False  # nothing idle matched
    spec.dispatch.assert_not_awaited()
    [(_, sql, _args)] = conn.ran("SET dispatch_token = $2, updated_at = NOW()")
    for part in ("UPDATE mw_agent_tasks", "deleted_at IS NULL", "status IN ('queued', 'running')",
                 "(lease_until IS NULL OR lease_until < NOW())", "updated_at < NOW() - INTERVAL '3 minutes'"):
        assert part in sql

    conn.on("SET dispatch_token = $2, updated_at = NOW()", {"id": TASK})
    assert await chain.nudge(spec, TASK) is True
    new_token = conn.ran("SET dispatch_token = $2, updated_at = NOW()")[-1][2][1]
    assert new_token != TOKEN
    spec.dispatch.assert_awaited_once_with(TASK, new_token)

    spec.dispatch.side_effect = RuntimeError("down")
    assert await chain.nudge(spec, TASK) is False
    conn.on("SET dispatch_token = $2", RuntimeError("db"))
    assert await chain.nudge(spec, TASK) is False  # never raises


@pytest.mark.asyncio
async def test_reconcile_ends_stale_rows_and_restarts_idle_ones(wired):
    conn, spec = wired
    idle, dead, orphan = uuid4(), uuid4(), uuid4()
    conn.on("ORDER BY updated_at LIMIT 200", [
        task_row(id=idle), task_row(id=dead), task_row(id=orphan, dispatch_token=None)])
    conn.on("updated_at < NOW() - INTERVAL '4 hours'", [{"id": dead}, {"id": orphan}])
    conn.on("SET dispatch_token = $2, updated_at = NOW()", {"id": idle})
    assert await chain.reconcile(spec) == {"ended": 1, "restarted": 1}
    assert [c.args[1] for c in spec.ending.await_args_list] == ["the task stopped making progress."] * 2
    [(_, _sql, args)] = conn.ran("SET status = $3")
    assert args[0] == dead and args[7] == "Stopped: no progress."
    assert spec.dispatch.await_args.args[0] == idle


# ── inside a phase ───────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_grant_and_refund_touch_only_the_specs_budget_columns(wired):
    conn, spec = wired
    conn.on("RETURNING GREATEST(LEAST($2, $3 - cur.before), 0)", 4)
    assert await chain.grant(spec, TASK, "web_calls", 6, 10) == 4
    [(_, sql, args)] = conn.ran("RETURNING GREATEST")
    assert "UPDATE mw_agent_tasks s SET web_calls = cur.before" in sql and args == (TASK, 6, 10)
    assert await chain.grant(spec, TASK, "web_calls", 0, 10) == 0
    await chain.refund(spec, TASK, "web_calls", 0)
    assert not conn.ran("GREATEST(web_calls - $2, 0)")
    await chain.refund(spec, TASK, "web_calls", 2)
    assert conn.ran("GREATEST(web_calls - $2, 0)")[0][2] == (TASK, 2)
    for column in ("attempts", "provider_calls", "web_calls = 0, attempts"):
        with pytest.raises(AssertionError):
            await chain.grant(spec, TASK, column, 1, 1)
        with pytest.raises(AssertionError):
            await chain.refund(spec, TASK, column, 1)


@pytest.mark.asyncio
async def test_the_guard_checks_and_notes_under_the_token(wired):
    conn, spec = wired
    guard = chain.Guard(spec, TASK, TOKEN)
    assert await guard.current() is False
    conn.on("SELECT 1 FROM mw_agent_tasks WHERE id = $1 AND dispatch_token = $2", 1)
    assert await guard.current() is True
    await guard.note("x" * 300, found=2)
    [(_, sql, args)] = conn.ran("progress = progress || $3::jsonb")
    assert "UPDATE mw_agent_tasks" in sql and "dispatch_token = $2" in sql
    assert args[:2] == (TASK, TOKEN) and json.loads(args[2]) == {"note": "x" * 200, "found": 2}


def test_budget_counts_what_it_hands_out():
    budget = chain.Budget(left=1)
    assert budget.take() is True and budget.take() is False
    assert (budget.left, budget.used, budget.exhausted) == (0, 1, True)
    # Several at once, or none: a search that costs two calls never spends one.
    budget = chain.Budget(left=3)
    assert budget.take(2) is True and budget.take(2) is False and budget.take(0) is True
    assert (budget.left, budget.used, budget.exhausted) == (1, 2, True)


@pytest.mark.asyncio
async def test_a_phases_paid_calls_are_logged_under_the_specs_label(wired):
    from app.core.services import ai_usage

    conn, _ = wired
    seen = []

    async def plan(row, deps, guard):
        await asyncio.sleep(0)
        seen.append(ai_usage._feature_override.get())
        return PhaseOutcome("running", {"note": "Planned"}, phase="act")

    spec = make_spec(phases={"plan": plan}, usage_feature=lambda row: f"matcha.espresso.tasks.{row['phase']}")
    conn.on("attempts = attempts + 1", task_row())
    await chain.run_phase(spec, TASK, TOKEN)
    assert seen == ["matcha.espresso.tasks.plan"]
    assert ai_usage._feature_override.get() is None
    # Without a label the calling module's is used, as before.
    seen.clear()
    await chain.run_phase(make_spec(phases={"plan": plan}), TASK, TOKEN)
    assert seen == [None]


def test_the_owners_label_their_phases():
    from app.matcha.services.matcha_work.agent_tasks import orchestrator as tasks
    from app.matcha.services.matcha_work.job_search import orchestrator as jobs

    assert jobs.JOB_CHAIN.usage_feature({}) == "matcha.espresso.job_search"
    assert tasks.TASK_CHAIN.usage_feature({"playbook": "apartments"}) == "matcha.espresso.tasks.apartments"
    assert tasks.TASK_CHAIN.usage_feature({"playbook": None}) == "matcha.espresso.tasks.research"
