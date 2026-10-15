"""The REST layer: switched off by default, personal-only, owner-scoped, thin."""
from unittest.mock import AsyncMock
from uuid import uuid4

import pytest
from fastapi import HTTPException

from app.core.models.auth import CurrentUser
from app.matcha.models.matcha_work.agent_tasks import AgentTaskCreate, ItemPatch, RoundCreate
from app.matcha.routes.matcha_work import agent_tasks as routes

USER = CurrentUser(id=uuid4(), email="owner@example.test", role="client")
TID, IID, CID = uuid4(), uuid4(), uuid4()


@pytest.mark.asyncio
async def test_routes_pass_the_caller(monkeypatch):
    monkeypatch.setattr(routes, "get_client_company_id", AsyncMock(return_value=CID))
    for name in ("list_tasks", "summary", "get_task", "status_view", "get_item", "patch_item",
                 "cancel_task", "delete_task"):
        monkeypatch.setattr(routes.service, name, AsyncMock(return_value={"ok": name}))
    monkeypatch.setattr(routes.enqueue, "create_task", AsyncMock(return_value={"id": "new"}))
    monkeypatch.setattr(routes.enqueue, "start_round", AsyncMock(return_value={"id": "round"}))
    monkeypatch.setattr(routes.allowance, "task_usage", AsyncMock(return_value={"limit": 60}))
    monkeypatch.setattr(routes.enqueue, "tasks_enabled", lambda user: True)

    listed = await routes.list_agent_tasks(USER)
    assert listed == {"tasks": {"ok": "list_tasks"}, "usage": {"limit": 60}}
    assert routes.service.list_tasks.await_args.kwargs == {"engines": ("chain", "job_search")}
    assert await routes.tasks_summary(USER) == {"ok": "summary"}
    assert routes.service.summary.await_args.kwargs == {"engines": ("chain", "job_search")}
    books = await routes.list_playbooks(USER)
    assert [p["key"] for p in books["playbooks"]] == ["research", "job_search"]
    assert books["units"]["rounds"]["more"] == 1
    body = AgentTaskCreate(request_id=uuid4(), directive="find me a lamp")
    assert await routes.create_agent_task(body, USER) == {"id": "new"}
    assert routes.enqueue.create_task.await_args.args == (USER, CID, body)
    await routes.get_agent_task(TID, USER)
    await routes.agent_task_status(TID, USER)
    await routes.get_agent_task_item(TID, IID, USER)
    await routes.update_agent_task_item(TID, IID, ItemPatch(user_state="saved"), USER)
    rb = RoundCreate(request_id=uuid4(), kind="more")
    assert await routes.start_agent_task_round(TID, rb, USER) == {"id": "round"}
    await routes.cancel_agent_task(TID, USER)
    await routes.delete_agent_task(TID, USER)
    for name in ("get_task", "status_view", "cancel_task", "delete_task"):
        assert getattr(routes.service, name).await_args.args == (TID, USER.id)
    assert routes.service.patch_item.await_args.kwargs == {"user_state": "saved", "notes": None, "user": USER}


@pytest.mark.asyncio
async def test_errors_and_gates(monkeypatch):
    async def missing():
        raise routes.service.AgentTaskError("Task not found.", 404)

    with pytest.raises(HTTPException) as exc:
        await routes._call(missing())
    assert exc.value.status_code == 404
    monkeypatch.setattr(routes, "get_client_company_id", AsyncMock(return_value=None))
    with pytest.raises(HTTPException):
        await routes.list_agent_tasks(USER)
    from app.matcha.services.matcha_work.job_search import providers

    monkeypatch.setattr(routes.enqueue, "tasks_enabled", lambda user: False)
    monkeypatch.setattr(providers, "configured", lambda: False)
    with pytest.raises(HTTPException) as exc:
        await routes.require_tasks(USER)
    assert exc.value.detail["code"] == "feature_disabled"
    # Job search isn't behind the Tasks switch: its searches are here either way.
    monkeypatch.setattr(providers, "configured", lambda: True)
    assert await routes.require_tasks(USER) is USER
    assert routes._engines(USER) == ("job_search",)
    monkeypatch.setattr(routes.enqueue, "tasks_enabled", lambda user: True)
    assert await routes.require_tasks(USER) is USER
    assert routes._engines(USER) == ("chain", "job_search")


def test_the_router_is_mounted_behind_the_gates():
    import inspect

    from app.matcha.routes import matcha_work

    paths = {r.path for r in routes.router.routes}
    assert "/agent-tasks/{task_id}/rounds" in paths and "/agent-tasks/playbooks" in paths
    assert routes.router.dependencies[0].dependency is routes.require_tasks
    assert "router.include_router(_agent_tasks_router)" in inspect.getsource(matcha_work)


@pytest.mark.asyncio
async def test_a_form_is_submitted_through_intake(monkeypatch):
    from app.matcha.models.matcha_work.agent_tasks import FormAnswer

    answer = AsyncMock(return_value={"id": "task"})
    monkeypatch.setattr(routes.intake, "answer_form", answer)
    body = FormAnswer(values={"location": "SF"})
    assert await routes.answer_agent_task_form(TID, body, USER) == {"id": "task"}
    assert answer.await_args.args == (USER, TID, body)


@pytest.mark.asyncio
async def test_actions_on_a_finding_go_through_the_service(monkeypatch):
    from app.matcha.models.matcha_work.agent_tasks import ActionRequest

    for name in ("propose", "confirm", "cancel"):
        monkeypatch.setattr(routes.task_actions, name, AsyncMock(return_value={"ok": name}))
    monkeypatch.setattr(routes.service, "get_item", AsyncMock(return_value={"ok": "item"}))
    body = ActionRequest(params={"quantity": 2})
    assert await routes.propose_agent_task_action(TID, IID, "buy", body, USER) == {"ok": "propose"}
    assert routes.task_actions.propose.await_args.args == (USER, TID, IID, "buy", {"quantity": 2})
    aid = uuid4()
    assert await routes.confirm_agent_task_action(aid, USER) == {"ok": "confirm"}
    assert routes.task_actions.confirm.await_args.args == (USER, aid)
    assert await routes.cancel_agent_task_action(aid, USER) == {"ok": "cancel"}
    # A finding is read with the person, so its actions are checked for them.
    await routes.get_agent_task_item(TID, IID, USER)
    assert routes.service.get_item.await_args.kwargs == {"user": USER}
    paths = {r.path for r in routes.router.routes}
    assert {"/agent-tasks/{task_id}/items/{item_id}/actions/{action}",
            "/agent-tasks/actions/{action_id}/confirm", "/agent-tasks/actions/{action_id}/cancel"} <= paths
