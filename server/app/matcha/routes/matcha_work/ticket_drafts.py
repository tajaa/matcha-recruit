"""Ticket drafts -- repo-grounded chat that promotes into a kanban task.

Split out of `tasks.py` (2026-07-19). Handlers moved verbatim -- no path,
signature, or response-shape change.
"""
from typing import Optional
from uuid import UUID

from fastapi import APIRouter, Body, Depends, HTTPException, Query

from app.core.models.auth import CurrentUser
from app.matcha.dependencies import require_admin_or_client, get_client_company_id
from app.matcha.routes.matcha_work._shared import (
    _can_edit_project,
    _project_company_id,
    _verify_project_access,
)

router = APIRouter()

@router.get("/projects/{project_id}/ticket-drafts")
async def list_ticket_drafts_endpoint(
    project_id: UUID,
    status: Optional[str] = Query(None),
    current_user: CurrentUser = Depends(require_admin_or_client),
):
    await _verify_project_access(project_id, current_user)
    from app.matcha.services import ticket_draft_service as td_svc
    return await td_svc.list_drafts(project_id, status)

@router.post("/projects/{project_id}/ticket-drafts", status_code=201)
async def create_ticket_draft_endpoint(
    project_id: UUID,
    body: dict = Body(...),
    current_user: CurrentUser = Depends(require_admin_or_client),
):
    project, _role = await _verify_project_access(project_id, current_user)
    company_id = _project_company_id(project) or await get_client_company_id(current_user)
    if not company_id:
        raise HTTPException(status_code=400, detail="No company context")
    from app.matcha.services import ticket_draft_service as td_svc
    try:
        return await td_svc.create_draft(
            project_id, company_id, current_user.id,
            kind=body.get("kind") or "feat",
            title=(body.get("title") or None),
            element_id=body.get("element_id") or None,
        )
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))

@router.get("/projects/{project_id}/ticket-drafts/{draft_id}")
async def get_ticket_draft_endpoint(
    project_id: UUID,
    draft_id: UUID,
    current_user: CurrentUser = Depends(require_admin_or_client),
):
    await _verify_project_access(project_id, current_user)
    from app.matcha.services import ticket_draft_service as td_svc
    draft = await td_svc.get_draft(project_id, draft_id)
    if not draft:
        raise HTTPException(status_code=404, detail="Draft not found")
    return draft

@router.patch("/projects/{project_id}/ticket-drafts/{draft_id}")
async def update_ticket_draft_endpoint(
    project_id: UUID,
    draft_id: UUID,
    body: dict = Body(...),
    current_user: CurrentUser = Depends(require_admin_or_client),
):
    await _verify_project_access(project_id, current_user)
    from app.matcha.services import ticket_draft_service as td_svc
    draft = await td_svc.update_draft(project_id, draft_id, body)
    if not draft:
        raise HTTPException(status_code=404, detail="Draft not found")
    return draft

@router.delete("/projects/{project_id}/ticket-drafts/{draft_id}")
async def delete_ticket_draft_endpoint(
    project_id: UUID,
    draft_id: UUID,
    current_user: CurrentUser = Depends(require_admin_or_client),
):
    await _verify_project_access(project_id, current_user)
    from app.matcha.services import ticket_draft_service as td_svc
    if not await td_svc.delete_draft(project_id, draft_id):
        raise HTTPException(status_code=404, detail="Draft not found")
    return {"deleted": True}

@router.get("/projects/{project_id}/ticket-drafts/{draft_id}/messages")
async def list_ticket_draft_messages_endpoint(
    project_id: UUID,
    draft_id: UUID,
    current_user: CurrentUser = Depends(require_admin_or_client),
):
    await _verify_project_access(project_id, current_user)
    from app.matcha.services import ticket_draft_service as td_svc
    return await td_svc.list_messages(project_id, draft_id)

@router.post("/projects/{project_id}/ticket-drafts/{draft_id}/messages")
async def post_ticket_draft_message_endpoint(
    project_id: UUID,
    draft_id: UUID,
    body: dict = Body(...),
    current_user: CurrentUser = Depends(require_admin_or_client),
):
    project, _role = await _verify_project_access(project_id, current_user)
    company_id = _project_company_id(project) or await get_client_company_id(current_user)
    content = (body.get("content") or "").strip()
    if not content:
        raise HTTPException(status_code=400, detail="content is required")
    from app.matcha.services import ticket_draft_service as td_svc
    result = await td_svc.chat(
        project_id, draft_id, company_id, user_content=content, actor_user_id=current_user.id,
    )
    if not result:
        raise HTTPException(status_code=404, detail="Draft not found")
    return result

@router.post("/projects/{project_id}/ticket-drafts/{draft_id}/generate")
async def generate_ticket_draft_fields_endpoint(
    project_id: UUID,
    draft_id: UUID,
    current_user: CurrentUser = Depends(require_admin_or_client),
):
    project, _role = await _verify_project_access(project_id, current_user)
    company_id = _project_company_id(project) or await get_client_company_id(current_user)
    from app.matcha.services import ticket_draft_service as td_svc
    draft = await td_svc.generate_fields(project_id, draft_id, company_id)
    if not draft:
        raise HTTPException(status_code=404, detail="Draft not found")
    return draft

@router.post("/projects/{project_id}/ticket-drafts/{draft_id}/promote")
async def promote_ticket_draft_endpoint(
    project_id: UUID,
    draft_id: UUID,
    body: dict = Body(default={}),
    current_user: CurrentUser = Depends(require_admin_or_client),
):
    project, role = await _verify_project_access(project_id, current_user)
    if not _can_edit_project(role):
        raise HTTPException(status_code=403, detail="You don't have edit access to this project")
    company_id = _project_company_id(project) or await get_client_company_id(current_user)
    from app.matcha.services import ticket_draft_service as td_svc
    try:
        task = await td_svc.promote(
            project_id, draft_id, company_id,
            actor_user_id=current_user.id, overrides=body or {},
        )
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    if not task:
        raise HTTPException(status_code=404, detail="Draft not found or already promoted")
    return task
