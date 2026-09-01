from contextlib import asynccontextmanager
from unittest.mock import AsyncMock
from uuid import uuid4

import pytest

from app import database
from app.matcha.services.billing import token_budget_service
from app.matcha.services.matcha_work.project_agent import agent
from app.workers.tasks import project_agent as worker


class _Connection:
    def __init__(self, row, project):
        self.row = row
        self.project = project

    async def fetchrow(self, query, *_args):
        if "UPDATE mw_project_agent_runs" in query:
            return self.row
        if "FROM mw_projects p" in query:
            return self.project
        raise AssertionError(query)

    @asynccontextmanager
    async def transaction(self):
        yield


@pytest.mark.asyncio
async def test_worker_deducts_successful_non_admin_usage(monkeypatch):
    run_id, company_id, project_id, channel_id, user_id = (
        uuid4(), uuid4(), uuid4(), uuid4(), uuid4(),
    )
    conn = _Connection(
        {
            "company_id": company_id,
            "project_id": project_id,
            "channel_id": channel_id,
            "requested_by": user_id,
            "prompt": "How does login work?",
        },
        {
            "title": "MATCHA",
            "github_repo": "example/matcha",
            "github_branch": "main",
            "requester_role": "client",
        },
    )

    @asynccontextmanager
    async def connection_or_direct():
        yield conn

    run = AsyncMock(return_value={"token_usage": {"total_tokens": 321}})
    deduct = AsyncMock()
    monkeypatch.setattr(database, "connection_or_direct", connection_or_direct)
    monkeypatch.setattr(agent, "run_repo_question", run)
    monkeypatch.setattr(token_budget_service, "deduct_tokens", deduct)

    await worker._run(run_id)

    run.assert_awaited_once()
    deduct.assert_awaited_once_with(conn, company_id, 321)
