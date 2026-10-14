"""A chain's model phase as an ordinary run, for an owner that is not job search."""
from types import SimpleNamespace
from unittest.mock import AsyncMock
from uuid import uuid4

import pytest

from app.matcha.services.huume.luna_client import text_item
from app.matcha.services.matcha_work.agent_runtime import phase_run, runner
from app.matcha.services.matcha_work.agent_runtime.context import RunLimits

from .helpers import FakeClient, FakeConn, call, connection, contract, response, wire_store

TASK, USER, COMPANY = uuid4(), uuid4(), uuid4()


def owner(**over):
    base = dict(
        kind="agent_task", fk_column="agent_task_id", owner_id=TASK, user_id=USER,
        company_id=COMPANY, model="gpt-5.6-luna", usage_feature="matcha.test.agent_task",
        storage_prefix=f"matcha-work/{COMPANY}/tasks/{TASK}", surface="assistant",
        account=AsyncMock(),
    )
    base.update(over)
    return phase_run.RunOwner(**base)


@pytest.fixture
def wired(monkeypatch):
    from app.matcha.services.billing import token_budget_service

    conn = FakeConn()
    monkeypatch.setattr(phase_run, "connection_or_direct", connection(conn))
    wire_store(monkeypatch)
    monkeypatch.setattr(phase_run.store, "mark_run", AsyncMock())
    deduct = AsyncMock()
    monkeypatch.setattr(token_budget_service, "deduct_tokens", deduct)
    conn.on("INSERT INTO mw_project_agent_runs", uuid4())
    return conn, deduct


async def run(the_owner, client, **kw):
    return await phase_run.run_model_phase(
        the_owner, phase="plan", abilities=(), contract=contract(), instructions="sys",
        user_text="find it", limits=RunLimits(max_model_calls=2), progress=phase_run.NoteProgress(AsyncMock()),
        client_factory=lambda _model: client, **kw,
    )


@pytest.mark.parametrize("over", [
    {"kind": "assistant"}, {"fk_column": "project_id"}, {"fk_column": "id; DROP TABLE x"},
    {"surface": "elsewhere"},
])
def test_an_owner_is_checked_when_it_is_built(over):
    with pytest.raises(ValueError):
        owner(**over)


@pytest.mark.asyncio
async def test_the_run_row_points_at_its_owner_and_is_counted(wired):
    conn, deduct = wired
    the_owner = owner()
    client = FakeClient([response(call("finish", {"answer": "ok"}))])
    out = await run(the_owner, client)
    assert out.result == {"answer": "ok"}

    [(_, sql, args)] = conn.ran("INSERT INTO mw_project_agent_runs")
    assert "agent_task_id)" in sql and "'agent_task'" in sql and "'assistant'" in sql
    assert args == (COMPANY, USER, f"plan:{TASK}", "gpt-5.6-luna", [], TASK)
    assert client.calls[0]["store"] is False  # an owner's input is never stored by the provider
    assert client.calls[0]["feature"] == "matcha.test.agent_task"

    phase_run.store.mark_run.assert_awaited_once()
    marked = phase_run.store.mark_run.await_args.kwargs
    assert marked["status"] == "done" and marked["result"]["phase"] == "plan"
    the_owner.account.assert_awaited_once_with({"token_usage": out.token_usage})
    deduct.assert_awaited_once_with(conn, COMPANY, 12)


@pytest.mark.asyncio
async def test_a_failed_run_is_marked_counted_and_raised(wired):
    conn, deduct = wired
    the_owner = owner()
    client = FakeClient([response(text="no tool"), response(text="still no tool")])
    with pytest.raises(runner.AgentRunError):
        await run(the_owner, client)
    assert phase_run.store.mark_run.await_args.kwargs["status"] == "failed"
    the_owner.account.assert_awaited_once()
    assert phase_run.total_tokens(the_owner.account.await_args.args[0]) > 0
    deduct.assert_awaited_once()


@pytest.mark.asyncio
async def test_accounting_never_fails_a_finished_phase(wired):
    conn, deduct = wired
    the_owner = owner(account=AsyncMock(side_effect=RuntimeError("db")))
    out = await run(the_owner, FakeClient([response(call("finish", {"answer": "ok"}))]))
    assert out.result == {"answer": "ok"}
    deduct.assert_not_awaited()  # as before: a failed count skips the charge


@pytest.mark.asyncio
async def test_what_the_caller_passes_reaches_the_run(wired, monkeypatch):
    seen = {}

    async def fake_run_agent(ctx, **kwargs):
        seen.update(ctx=ctx, **kwargs)
        return SimpleNamespace(result={}, warnings=[], model_calls=1, token_usage={}, search_calls=0)

    monkeypatch.setattr(runner, "run_agent", fake_run_agent)
    policy, on_receipt = object(), AsyncMock()
    first_input = [{"role": "user", "content": [{"type": "input_image", "image_url": "https://x.test/a.png"}]}]
    await run(owner(role="individual"), FakeClient([]), first_input=first_input,
              seed_provenance=frozenset({"https://x.test/"}), policy=policy,
              grants={"web": {"on": True}}, commit_modes={"calendar": "live"},
              on_receipt=on_receipt, timezone="America/New_York")
    ctx = seen["ctx"]
    assert seen["first_input"] is first_input and seen["seed_provenance"] == {"https://x.test/"}
    assert ctx.policy is policy and ctx.on_receipt is on_receipt and ctx.timezone == "America/New_York"
    assert ctx.grants == {"web": {"on": True}} and ctx.commit_modes == {"calendar": "live"}
    assert ctx.store_responses is False and ctx.surface == "assistant" and ctx.role == "individual"
    assert ctx.usage_feature == "matcha.test.agent_task" and ctx.storage_prefix.endswith(f"/tasks/{TASK}")

    # Left out, everything is as a job search phase has always run.
    await run(owner(), FakeClient([]))
    ctx = seen["ctx"]
    assert seen["first_input"] == [text_item("user", "find it")] and seen["seed_provenance"] == frozenset()
    assert (ctx.policy, ctx.grants, ctx.commit_modes, ctx.on_receipt, ctx.timezone) == (None, {}, {}, None, None)
    assert ctx.role == "client" and ctx.ask == "find it"


def test_default_client_follows_the_model(monkeypatch):
    from app.matcha.services.huume import claude_client, luna_client

    monkeypatch.setattr(claude_client, "get_claude_client", lambda: "claude")
    monkeypatch.setattr(luna_client, "get_luna_client", lambda: "luna")
    assert phase_run.default_client("gpt-5.6-luna") == "luna"
    assert phase_run.default_client("claude-haiku-5-5") == "claude"
