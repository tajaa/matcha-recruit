"""Agent cards must never reach AutoPR (it maps unknown categories to the CODE
lane), enforced server-side rather than only in the shell collectors; and a
dedicated -Q agent_cards worker must not re-run the scheduler dispatch."""
from contextlib import asynccontextmanager
from types import SimpleNamespace
from unittest.mock import AsyncMock
from uuid import UUID, uuid4

import pytest

from app.matcha.services.matcha_work import project_task_service as pt

PROJECT = "a0000000-0000-4000-8000-000000000001"
PROJECT_ID = UUID(PROJECT)


class _Conn:
    def __init__(self, category):
        self.category = category
        self.queries = []

    @asynccontextmanager
    async def transaction(self):
        yield

    async def fetchrow(self, query, *args):
        self.queries.append(query)
        return {"id": args[0], "board_column": "todo", "status": "pending",
                "progress_note": "", "category": self.category}

    async def fetchval(self, query, *args):
        self.queries.append(query)
        return None

    async def fetch(self, query, *args):
        self.queries.append((query, args))
        return []


def _wire(monkeypatch, category):
    conn = _Conn(category)

    @asynccontextmanager
    async def gc():
        yield conn

    monkeypatch.setattr(pt, "get_connection", gc)
    monkeypatch.setattr(pt, "KANBAN_AUTOPR_PROJECT_IDS", {PROJECT})
    return conn


@pytest.mark.asyncio
async def test_run_now_is_refused_for_agent_cards(monkeypatch):
    conn = _wire(monkeypatch, "agent")
    with pytest.raises(pt.AutoPRReconsiderationConflict, match="web agent"):
        await pt.request_autopr_run(project_id=PROJECT_ID, task_id=uuid4(), actor_user_id=uuid4())
    assert not any("INSERT INTO mw_task_history" in str(q) for q in conn.queries)


@pytest.mark.asyncio
async def test_reconsideration_is_refused_for_agent_cards(monkeypatch):
    _wire(monkeypatch, "agent")
    with pytest.raises(pt.AutoPRReconsiderationConflict, match="web agent"):
        await pt.request_autopr_reconsideration(
            project_id=PROJECT_ID, task_id=uuid4(), actor_user_id=uuid4(),
            expected_progress_note="x", body="go ahead",
        )


@pytest.mark.asyncio
async def test_the_bot_cannot_claim_an_agent_card(monkeypatch):
    _wire(monkeypatch, "agent")
    monkeypatch.setattr(pt, "KANBAN_AUTOPR_BOT_USER_ID", "bot-user")
    result = await pt.claim_autopr_run(
        project_id=PROJECT_ID, task_id=uuid4(), actor_user_id="bot-user",
    )
    assert result["ok"] is False and "web agent" in result["reason"]


@pytest.mark.asyncio
async def test_run_now_still_works_for_other_categories(monkeypatch):
    conn = _wire(monkeypatch, "bug")
    conn.execute = AsyncMock()
    # Get past the category guard: a normal card proceeds to its lane checks.
    async def fetchrow(query, *args):
        if "INSERT INTO mw_task_history" in query:
            from datetime import datetime, timezone
            return {"id": uuid4(), "created_at": datetime.now(timezone.utc)}
        return {"id": args[0], "board_column": "todo", "status": "pending", "category": "bug"}

    conn.fetchrow = fetchrow
    result = await pt.request_autopr_run(
        project_id=PROJECT_ID, task_id=uuid4(), actor_user_id=uuid4(),
    )
    assert result["ok"] and result["already_pending"] is False


@pytest.mark.asyncio
async def test_pending_run_request_listing_excludes_agent_cards(monkeypatch):
    conn = _wire(monkeypatch, "agent")
    await pt.list_autopr_run_requests([uuid4()])
    query, args = conn.queries[0]
    assert "<> ALL($3::text[])" in query and args[2] == ["agent"]


# ── worker_ready queue awareness ───────────────────────────────────────────

def _consumer(*queue_names):
    return SimpleNamespace(task_consumer=SimpleNamespace(queues=[SimpleNamespace(name=n) for n in queue_names]))


def test_default_queue_worker_runs_the_scheduler_dispatch():
    from app.workers import celery_app as ca

    assert ca._serves_default_queue(_consumer("celery", "agent_cards"))
    assert ca._serves_default_queue(_consumer("celery"))


def test_dedicated_agent_worker_does_not():
    from app.workers import celery_app as ca

    assert not ca._serves_default_queue(_consumer("agent_cards"))


def test_unreadable_queue_set_keeps_the_old_single_worker_behavior():
    from app.workers import celery_app as ca

    assert ca._serves_default_queue(object())


def test_on_worker_ready_returns_before_dispatching_on_a_dedicated_worker(monkeypatch):
    from app.workers import celery_app as ca
    from app.workers.tasks import er_document_processing

    dispatched = []
    monkeypatch.setattr(er_document_processing.reset_stale_er_documents, "delay", lambda: dispatched.append("er"))
    monkeypatch.setattr(ca, "_scheduler_flags", lambda keys: dispatched.append("flags") or {})
    ca.on_worker_ready(sender=_consumer("agent_cards"))
    assert dispatched == []
