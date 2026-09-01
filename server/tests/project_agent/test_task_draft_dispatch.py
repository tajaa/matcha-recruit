from contextlib import asynccontextmanager
from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock
from uuid import uuid4

import pytest
from fastapi import HTTPException

from app.core.services import redis_cache
from app.matcha.routes.matcha_work import project_agent_runs
from app.matcha.services.billing import token_budget_service
from app.matcha.services.matcha_work.project_agent import task_draft_agent
from app.workers.tasks import project_agent as worker


class _Connection:
    def __init__(self, run_id):
        self.run_id = run_id
        self.insert_args = None

    async def execute(self, _query, *_args):
        return None

    async def fetchval(self, query, *args):
        if "SELECT id FROM mw_project_agent_runs" in query:
            return None
        if "SELECT EXISTS" in query:
            return False
        if "INSERT INTO mw_project_agent_runs" in query:
            self.insert_args = args
            return self.run_id
        raise AssertionError(query)

    @asynccontextmanager
    async def transaction(self):
        yield


@pytest.mark.asyncio
async def test_enqueue_agent_draft_is_audited_and_queued(monkeypatch):
    run_id, project_id, company_id, user_id, request_key = (
        uuid4(), uuid4(), uuid4(), uuid4(), uuid4(),
    )
    conn = _Connection(run_id)

    @asynccontextmanager
    async def get_connection():
        yield conn

    verify = AsyncMock(return_value=({
        "id": str(project_id),
        "company_id": str(company_id),
        "github_repo": "example/matcha",
    }, "owner"))
    delay = Mock()
    monkeypatch.setattr(project_agent_runs, "_verify_project_access", verify)
    monkeypatch.setattr(project_agent_runs, "get_connection", get_connection)
    monkeypatch.setattr(redis_cache, "check_rate_limit", AsyncMock())
    monkeypatch.setattr(token_budget_service, "check_token_budget", AsyncMock())
    monkeypatch.setattr(task_draft_agent, "resolve_model", AsyncMock(return_value="resolved-model"))
    monkeypatch.setattr(worker.run_task_draft, "delay", delay)

    result = await project_agent_runs.enqueue_agent_task_draft_endpoint(
        project_id,
        {
            "prompt": "Add saved filters",
            "model": "requested-model",
            "request_key": str(request_key),
        },
        SimpleNamespace(id=user_id, role="client"),
    )

    assert result == {"run_id": str(run_id), "status": "queued"}
    assert conn.insert_args[-2] == request_key
    assert conn.insert_args[-1] == "resolved-model"
    delay.assert_called_once_with(str(run_id))


@pytest.mark.asyncio
async def test_agent_draft_requires_repo_before_rate_or_queue(monkeypatch):
    project_id, company_id, user_id = uuid4(), uuid4(), uuid4()
    monkeypatch.setattr(project_agent_runs, "_verify_project_access", AsyncMock(return_value=({
        "id": str(project_id),
        "company_id": str(company_id),
        "github_repo": None,
    }, "owner")))

    with pytest.raises(HTTPException) as exc:
        await project_agent_runs.enqueue_agent_task_draft_endpoint(
            project_id,
            {"prompt": "Add saved filters"},
            SimpleNamespace(id=user_id, role="client"),
        )

    assert exc.value.status_code == 412
    assert exc.value.detail["code"] == "repository_required"
