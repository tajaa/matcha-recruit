import json
from contextlib import asynccontextmanager
from datetime import datetime, timezone
from unittest.mock import AsyncMock
from uuid import uuid4

import pytest

from app import database
from app.matcha.services.billing import token_budget_service
from app.matcha.services.matcha_work.agent_card import agent, board
from app.matcha.services.matcha_work.project_agent import store
from app.workers.tasks import agent_card as worker


def _task_row(column="in_progress", **over):
    now = datetime.now(timezone.utc)
    row = {
        "id": uuid4(), "project_id": uuid4(), "company_id": uuid4(), "created_by": uuid4(),
        "title": "Find me a balm", "description": None, "due_date": None, "priority": "medium",
        "status": "pending", "board_column": column, "pipeline_column": "lead", "assigned_to": None,
        "completed_at": None, "created_at": now, "updated_at": now, "progress_note": None,
        "category": "agent", "element_id": None, "review_note": None,
    }
    row.update(over)
    return row


class _BoardConn:
    def __init__(self, column):
        self.column = column
        self.history = []
        self.updates = []

    @asynccontextmanager
    async def transaction(self):
        yield

    async def fetchval(self, query, *args):
        assert "FOR UPDATE" in query
        return self.column

    async def fetchrow(self, query, *args):
        self.updates.append((query, args))
        if "SET board_column" in query:
            self.column = args[1]
            return _task_row(column=args[1], id=args[0])
        return _task_row(progress_note=args[1], id=args[0])

    async def execute(self, query, *args):
        if "mw_task_history" in query:
            self.history.append(args)


@pytest.fixture
def board_conn(monkeypatch):
    holder = {}

    @asynccontextmanager
    async def cod():
        yield holder["conn"]

    monkeypatch.setattr(board, "connection_or_direct", cod)
    return holder


@pytest.mark.asyncio
async def test_claim_moves_todo_to_in_progress_and_logs_history(board_conn):
    board_conn["conn"] = conn = _BoardConn("todo")
    row = await board.claim_column(uuid4(), round=1, run_id=uuid4())
    assert row["board_column"] == "in_progress"
    assert conn.history and conn.history[0][4] == "column_change"
    assert conn.history[0][3] is None  # actor: the agent, not a person


@pytest.mark.asyncio
async def test_revision_round_stays_in_changes_requested(board_conn):
    board_conn["conn"] = conn = _BoardConn("changes_requested")
    assert await board.claim_column(uuid4(), round=2, run_id=uuid4()) is None
    assert conn.updates == []


@pytest.mark.asyncio
@pytest.mark.parametrize("column", ["in_progress", "changes_requested"])
async def test_finish_moves_to_review(board_conn, column):
    board_conn["conn"] = _BoardConn(column)
    row = await board.finish_column(uuid4(), run_id=uuid4())
    assert row["board_column"] == "review"


@pytest.mark.asyncio
@pytest.mark.parametrize("column", ["done", "todo", "review"])
async def test_finish_never_yanks_a_card_the_person_moved(board_conn, column):
    board_conn["conn"] = conn = _BoardConn(column)
    assert await board.finish_column(uuid4(), run_id=uuid4()) is None
    assert conn.column == column and conn.history == []


@pytest.mark.asyncio
async def test_progress_is_throttled_unless_forced(board_conn):
    board_conn["conn"] = conn = _BoardConn("in_progress")
    task_id = uuid4()
    assert await board.set_progress(task_id, "one") is not None
    assert await board.set_progress(task_id, "two") is None
    assert await board.set_progress(task_id, "three", force=True) is not None
    assert len(conn.updates) == 2


@pytest.mark.asyncio
async def test_publish_uses_the_project_fanout_envelope(monkeypatch):
    published = {}

    class _Redis:
        async def publish(self, channel, payload):
            published["channel"], published["payload"] = channel, json.loads(payload)

        async def aclose(self):
            published["closed"] = True

    import redis.asyncio as aioredis

    monkeypatch.setattr(aioredis, "from_url", lambda *_a, **_k: _Redis())
    row = _task_row()
    await board.publish_task_updated(row["project_id"], row)
    env = published["payload"]
    assert published["channel"] == "projects:fanout" == board.FANOUT_CHANNEL
    # Exactly what project_ws._project_subscriber_loop dispatches.
    assert env["kind"] == "project" and env["project_id"] == str(row["project_id"])
    assert env["message"]["type"] == "task.updated"
    assert env["message"]["task"]["id"] == str(row["id"])
    assert published["closed"]


def test_fanout_channel_matches_the_ws_subscriber():
    from app.matcha.routes.work import project_ws

    assert project_ws._FANOUT_CHANNEL == board.FANOUT_CHANNEL


class _WorkerConn:
    def __init__(self, run, task, previous=None):
        self.run, self.task, self.previous = run, task, previous

    @asynccontextmanager
    async def transaction(self):
        yield

    async def fetchrow(self, query, *_args):
        if "UPDATE mw_project_agent_runs" in query:
            return self.run
        if "FROM mw_tasks" in query:
            return self.task
        raise AssertionError(query)

    async def fetchval(self, query, *_args):
        assert "status = 'done'" in query
        return self.previous


def _wire_worker(monkeypatch, conn, *, run_result=None, run_error=None):
    @asynccontextmanager
    async def cod():
        yield conn

    monkeypatch.setattr(database, "connection_or_direct", cod)
    calls = {
        "claim": AsyncMock(return_value=_task_row()),
        "finish": AsyncMock(return_value=_task_row(column="review")),
        "progress": AsyncMock(return_value=_task_row(column="review")),
        "publish": AsyncMock(),
        "mark": AsyncMock(),
        "deduct": AsyncMock(),
    }
    monkeypatch.setattr(board, "claim_column", calls["claim"])
    monkeypatch.setattr(board, "finish_column", calls["finish"])
    monkeypatch.setattr(board, "set_progress", calls["progress"])
    monkeypatch.setattr(board, "publish_task_updated", calls["publish"])
    monkeypatch.setattr(store, "mark_run", calls["mark"])
    monkeypatch.setattr(token_budget_service, "deduct_tokens", calls["deduct"])

    async def fake_run(**kwargs):
        calls["run_kwargs"] = kwargs
        kwargs["stats"].update(model_calls=3, search_calls=4, token_usage={"total_tokens": 900})
        if run_error:
            raise run_error
        return run_result or {"result": {}}

    monkeypatch.setattr(agent, "run_card_agent", fake_run)
    return calls


def _run_row(round=1, role="client"):
    return {"company_id": uuid4(), "project_id": uuid4(), "task_id": uuid4(), "round": round,
            "requested_by": uuid4(), "requester_role": role}


@pytest.mark.asyncio
async def test_worker_happy_path_claims_runs_finishes_and_deducts(monkeypatch):
    conn = _WorkerConn(_run_row(), {"title": "Find a balm", "description": "Under $10", "review_note": None, "category": "agent"})
    calls = _wire_worker(monkeypatch, conn)
    await worker._run(uuid4())
    calls["claim"].assert_awaited_once()
    calls["finish"].assert_awaited_once()
    assert calls["run_kwargs"]["ask"] == "Find a balm\n\nUnder $10"
    assert calls["run_kwargs"]["review_note"] is None
    assert calls["publish"].await_count == 2
    assert calls["deduct"].await_args.args[2] == 900
    calls["mark"].assert_not_awaited()  # agent.run_card_agent marks done itself


@pytest.mark.asyncio
async def test_worker_revision_passes_note_and_previous_result(monkeypatch):
    previous = json.dumps({"headline": "old"})
    conn = _WorkerConn(_run_row(round=2), {"title": "Balm", "description": None, "review_note": "vegan only", "category": "agent"}, previous)
    calls = _wire_worker(monkeypatch, conn)
    await worker._run(uuid4())
    assert calls["run_kwargs"]["review_note"] == "vegan only"
    assert calls["run_kwargs"]["previous_result"] == {"headline": "old"}


@pytest.mark.asyncio
async def test_worker_failure_marks_failed_with_spend_and_leaves_card(monkeypatch):
    conn = _WorkerConn(_run_row(), {"title": "x", "description": None, "review_note": None, "category": "agent"})
    calls = _wire_worker(monkeypatch, conn, run_error=agent.CardAgentError("The agent ran out of time."))
    await worker._run(uuid4())
    calls["finish"].assert_not_awaited()
    mark = calls["mark"].await_args.kwargs
    assert mark["status"] == "failed" and mark["search_calls"] == 4 and mark["model_calls"] == 3
    note = calls["progress"].await_args.args[1]
    assert "ran out of time" in note and "Run again" in note
    assert calls["deduct"].await_count == 1  # tokens were spent even though it failed


@pytest.mark.asyncio
async def test_worker_hides_unexpected_error_text_from_the_card(monkeypatch):
    conn = _WorkerConn(_run_row(role="admin"), {"title": "x", "description": None, "review_note": None, "category": "agent"})
    calls = _wire_worker(monkeypatch, conn, run_error=RuntimeError("asyncpg secret detail"))
    await worker._run(uuid4())
    assert "secret" not in calls["progress"].await_args.args[1]
    calls["deduct"].assert_not_awaited()  # admins are not billed


@pytest.mark.asyncio
async def test_worker_skips_already_claimed_run(monkeypatch):
    conn = _WorkerConn(None, None)
    calls = _wire_worker(monkeypatch, conn)
    await worker._run(uuid4())
    calls["claim"].assert_not_awaited()


@pytest.mark.asyncio
async def test_worker_fails_run_whose_card_is_no_longer_agent(monkeypatch):
    conn = _WorkerConn(_run_row(), {"title": "x", "description": None, "review_note": None, "category": "bug"})
    calls = _wire_worker(monkeypatch, conn)
    await worker._run(uuid4())
    assert calls["mark"].await_args.kwargs["status"] == "failed"
    calls["claim"].assert_not_awaited()


@pytest.mark.asyncio
async def test_reconciler_flags_interrupted_agent_cards(monkeypatch):
    from app.workers.tasks import project_agent as pa_worker

    task_id, project_id = uuid4(), uuid4()

    class _Conn:
        async def fetch(self, query, *_a):
            assert "RETURNING kind, project_id, task_id" in query
            return [
                {"kind": "card_agent", "project_id": project_id, "task_id": task_id},
                {"kind": "repo_question", "project_id": uuid4(), "task_id": None},
            ]

    @asynccontextmanager
    async def cod():
        yield _Conn()

    monkeypatch.setattr(database, "connection_or_direct", cod)
    progress = AsyncMock(return_value=_task_row())
    publish = AsyncMock()
    monkeypatch.setattr(board, "set_progress", progress)
    monkeypatch.setattr(board, "publish_task_updated", publish)
    await pa_worker._reconcile()
    progress.assert_awaited_once()
    assert progress.await_args.args[0] == task_id and "interrupted" in progress.await_args.args[1]
    publish.assert_awaited_once()
