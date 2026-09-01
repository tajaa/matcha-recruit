from contextlib import asynccontextmanager
from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock
from uuid import uuid4

import pytest

from app.matcha.services.matcha_work.project_agent import chat
from app.matcha.services.billing import token_budget_service
from app.werk.routes import channels_ws
from app.workers.tasks import project_agent as worker


class _Connection:
    def __init__(self, project, run_id):
        self.project = project
        self.run_id = run_id
        self.insert_args = None
        self.failed_run_id = None
        self.failed_run_query = None
        self.failed_transition_result = run_id

    async def fetchrow(self, query, *_args):
        if "FROM mw_projects p" in query:
            return self.project
        raise AssertionError(query)

    async def fetchval(self, query, *args):
        if "UPDATE mw_project_agent_runs" in query:
            self.failed_run_id = args[0]
            self.failed_run_query = query
            return self.failed_transition_result
        if "FROM mw_project_collaborators" in query:
            return None
        if "FROM clients" in query:
            return self.project["company_id"]
        if "SELECT EXISTS" in query:
            return False
        if "INSERT INTO mw_project_agent_runs" in query:
            self.insert_args = args
            return self.run_id
        raise AssertionError(query)

    async def execute(self, _query, *_args):
        return None

    @asynccontextmanager
    async def transaction(self):
        yield


@pytest.mark.asyncio
async def test_espresso_mention_queues_stripped_repo_question(monkeypatch):
    company_id, project_id, channel_id, user_id, message_id, run_id = (
        uuid4(), uuid4(), uuid4(), uuid4(), uuid4(), uuid4(),
    )
    conn = _Connection({
        "id": project_id,
        "company_id": company_id,
        "github_repo": "example/matcha",
        "enabled_features": {"matcha_work": True},
        "signup_source": "invite",
    }, run_id)

    @asynccontextmanager
    async def get_connection():
        yield conn

    post = AsyncMock()
    delay = Mock()
    monkeypatch.setattr(channels_ws, "get_connection", get_connection)
    monkeypatch.setattr(channels_ws, "check_rate_limit", AsyncMock())
    monkeypatch.setattr(token_budget_service, "check_token_budget", AsyncMock())
    monkeypatch.setattr(chat, "post_as_espresso", post)
    monkeypatch.setattr(worker.run_repo_question, "delay", delay)

    claimed = await channels_ws._bg_dispatch_espresso_mention(
        str(channel_id),
        SimpleNamespace(id=user_id, role="client"),
        "@espresso how do I use project templates?",
        message_id,
    )

    assert claimed is True
    delay.assert_called_once_with(str(run_id))
    assert conn.insert_args[-1] == "how do I use project templates?"
    post.assert_awaited_once()
    assert "source-linked answer" in post.await_args.args[2]


@pytest.mark.asyncio
async def test_espresso_mention_fails_run_and_notifies_when_enqueue_fails(monkeypatch):
    company_id, project_id, channel_id, user_id, message_id, run_id = (
        uuid4(), uuid4(), uuid4(), uuid4(), uuid4(), uuid4(),
    )
    conn = _Connection({
        "id": project_id,
        "company_id": company_id,
        "github_repo": "example/matcha",
        "enabled_features": {"matcha_work": True},
        "signup_source": "invite",
    }, run_id)

    @asynccontextmanager
    async def get_connection():
        yield conn

    post = AsyncMock()
    delay = Mock(side_effect=RuntimeError("broker unavailable"))
    monkeypatch.setattr(channels_ws, "get_connection", get_connection)
    monkeypatch.setattr(channels_ws, "check_rate_limit", AsyncMock())
    monkeypatch.setattr(token_budget_service, "check_token_budget", AsyncMock())
    monkeypatch.setattr(chat, "post_as_espresso", post)
    monkeypatch.setattr(worker.run_repo_question, "delay", delay)

    claimed = await channels_ws._bg_dispatch_espresso_mention(
        str(channel_id),
        SimpleNamespace(id=user_id, role="client"),
        "@espresso how does login work?",
        message_id,
    )

    assert claimed is True
    delay.assert_called_once_with(str(run_id))
    assert conn.failed_run_id == run_id
    assert "status='failed'" in conn.failed_run_query
    assert "completed_at=NOW()" in conn.failed_run_query
    post.assert_awaited_once_with(
        company_id,
        channel_id,
        "I couldn't queue that repository question right now. Please try again.",
    )


@pytest.mark.asyncio
async def test_espresso_enqueue_error_keeps_ack_when_worker_already_claimed(monkeypatch):
    company_id, project_id, channel_id, user_id, message_id, run_id = (
        uuid4(), uuid4(), uuid4(), uuid4(), uuid4(), uuid4(),
    )
    conn = _Connection({
        "id": project_id,
        "company_id": company_id,
        "github_repo": "example/matcha",
        "enabled_features": {"matcha_work": True},
        "signup_source": "invite",
    }, run_id)
    conn.failed_transition_result = None

    @asynccontextmanager
    async def get_connection():
        yield conn

    post = AsyncMock()
    monkeypatch.setattr(channels_ws, "get_connection", get_connection)
    monkeypatch.setattr(channels_ws, "check_rate_limit", AsyncMock())
    monkeypatch.setattr(token_budget_service, "check_token_budget", AsyncMock())
    monkeypatch.setattr(chat, "post_as_espresso", post)
    monkeypatch.setattr(
        worker.run_repo_question,
        "delay",
        Mock(side_effect=RuntimeError("publish confirmation timed out")),
    )

    claimed = await channels_ws._bg_dispatch_espresso_mention(
        str(channel_id),
        SimpleNamespace(id=user_id, role="client"),
        "@espresso how does login work?",
        message_id,
    )

    assert claimed is True
    assert conn.failed_run_id == run_id
    post.assert_awaited_once()
    assert "source-linked answer" in post.await_args.args[2]
