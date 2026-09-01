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
    # A client-sent model is never consulted; the row audits what actually ran.
    assert conn.insert_args[-1] == task_draft_agent.TASK_DRAFT_MODEL
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


@pytest.mark.asyncio
async def test_agent_draft_rejects_read_only_collaborator(monkeypatch):
    project_id, company_id, user_id = uuid4(), uuid4(), uuid4()
    monkeypatch.setattr(project_agent_runs, "_verify_project_access", AsyncMock(return_value=({
        "id": str(project_id),
        "company_id": str(company_id),
        "github_repo": "example/matcha",
    }, "viewer")))

    with pytest.raises(HTTPException) as exc:
        await project_agent_runs.enqueue_agent_task_draft_endpoint(
            project_id,
            {"prompt": "Add saved filters"},
            SimpleNamespace(id=user_id, role="client"),
        )

    assert exc.value.status_code == 403


@pytest.mark.asyncio
async def test_request_key_lookup_is_scoped_to_project_and_requester(monkeypatch):
    run_id, project_id, company_id, user_id, request_key = (
        uuid4(), uuid4(), uuid4(), uuid4(), uuid4(),
    )

    class _ScopedConnection(_Connection):
        def __init__(self, run_id):
            super().__init__(run_id)
            self.lookup_args = None

        async def fetchval(self, query, *args):
            if "SELECT id FROM mw_project_agent_runs" in query:
                self.lookup_args = args
            return await super().fetchval(query, *args)

    conn = _ScopedConnection(run_id)

    @asynccontextmanager
    async def get_connection():
        yield conn

    monkeypatch.setattr(project_agent_runs, "_verify_project_access", AsyncMock(return_value=({
        "id": str(project_id),
        "company_id": str(company_id),
        "github_repo": "example/matcha",
    }, "owner")))
    monkeypatch.setattr(project_agent_runs, "get_connection", get_connection)
    monkeypatch.setattr(redis_cache, "check_rate_limit", AsyncMock())
    monkeypatch.setattr(token_budget_service, "check_token_budget", AsyncMock())
    monkeypatch.setattr(worker.run_task_draft, "delay", Mock())

    await project_agent_runs.enqueue_agent_task_draft_endpoint(
        project_id,
        {"prompt": "Add saved filters", "request_key": str(request_key)},
        SimpleNamespace(id=user_id, role="client"),
    )

    assert conn.lookup_args == (request_key, project_id, user_id)
