"""Espresso Tasks: background work Espresso does for a person, and what it found.

Personal Espresso accounts, Pro and up, from the shared monthly allowance
(`services/matcha_work/agent_tasks/allowance.py`). Off until
`ESPRESSO_TASKS_ENABLED` is set, except for admins. The work runs in the
worker (`services/matcha_work/agent_tasks/`); these routes start it, read
it, and take follow-ups. Everything is scoped to the caller: another
person's ids are 404.
"""
from __future__ import annotations

from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException

from app.core.models.auth import CurrentUser
from app.matcha.dependencies import get_client_company_id, require_admin_or_client
from app.matcha.models.matcha_work.agent_tasks import AgentTaskCreate, ItemPatch, RoundCreate
from app.matcha.services.matcha_work.agent_tasks import allowance, enqueue, playbooks, service

from .assistant import require_personal_workspace


async def require_tasks(current_user: CurrentUser = Depends(require_personal_workspace)):
    if not enqueue.tasks_enabled(current_user):
        raise HTTPException(status_code=403, detail={
            "code": "feature_disabled", "message": "Tasks aren't available yet.",
        })
    return current_user


router = APIRouter(prefix="/agent-tasks", dependencies=[Depends(require_tasks)])


async def _company(current_user: CurrentUser) -> UUID:
    company_id = await get_client_company_id(current_user)
    if company_id is None:
        raise HTTPException(status_code=400, detail="No workspace is selected.")
    return company_id


async def _call(operation):
    try:
        return await operation
    except service.AgentTaskError as exc:
        raise HTTPException(status_code=exc.code, detail=exc.detail or str(exc)) from exc


@router.get("/playbooks")
async def list_playbooks(current_user: CurrentUser = Depends(require_admin_or_client)):
    """The kinds of task Espresso can start here, with what each may ask for."""
    return {
        "playbooks": [p.view() for p in playbooks.PLAYBOOKS.values() if p.engine == "chain"],
        "units": {**allowance.WEIGHTS, "rounds": allowance.ROUND_UNITS},
    }


@router.get("/summary")
async def tasks_summary(current_user: CurrentUser = Depends(require_admin_or_client)):
    """The sidebar's counts: running, waiting for you, finished and unseen."""
    company_id = await _company(current_user)
    return await service.summary(current_user.id, company_id)


@router.get("")
async def list_agent_tasks(current_user: CurrentUser = Depends(require_admin_or_client)):
    company_id = await _company(current_user)
    return {
        "tasks": await service.list_tasks(current_user.id, company_id),
        "usage": await allowance.task_usage(current_user.id),
    }


@router.post("", status_code=202)
async def create_agent_task(body: AgentTaskCreate, current_user: CurrentUser = Depends(require_admin_or_client)):
    company_id = await _company(current_user)
    return await _call(enqueue.create_task(current_user, company_id, body))


@router.get("/{task_id}")
async def get_agent_task(task_id: UUID, current_user: CurrentUser = Depends(require_admin_or_client)):
    return await _call(service.get_task(task_id, current_user.id))


@router.get("/{task_id}/status")
async def agent_task_status(task_id: UUID, current_user: CurrentUser = Depends(require_admin_or_client)):
    return await _call(service.status_view(task_id, current_user.id))


@router.get("/{task_id}/items/{item_id}")
async def get_agent_task_item(
    task_id: UUID, item_id: UUID, current_user: CurrentUser = Depends(require_admin_or_client),
):
    return await _call(service.get_item(task_id, item_id, current_user.id))


@router.patch("/{task_id}/items/{item_id}")
async def update_agent_task_item(
    task_id: UUID, item_id: UUID, body: ItemPatch,
    current_user: CurrentUser = Depends(require_admin_or_client),
):
    return await _call(service.patch_item(task_id, item_id, current_user.id,
                                          user_state=body.user_state, notes=body.notes))


@router.post("/{task_id}/rounds", status_code=202)
async def start_agent_task_round(
    task_id: UUID, body: RoundCreate, current_user: CurrentUser = Depends(require_admin_or_client),
):
    """Refine (free), search more (1 unit) or make a document (free)."""
    return await _call(enqueue.start_round(current_user, task_id, body))


@router.post("/{task_id}/cancel")
async def cancel_agent_task(task_id: UUID, current_user: CurrentUser = Depends(require_admin_or_client)):
    return await _call(service.cancel_task(task_id, current_user.id))


@router.delete("/{task_id}")
async def delete_agent_task(task_id: UUID, current_user: CurrentUser = Depends(require_admin_or_client)):
    return await _call(service.delete_task(task_id, current_user.id))
