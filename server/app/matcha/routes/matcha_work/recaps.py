"""Personal, owner-only recap API. Media URLs are short-lived bearer links."""
from uuid import UUID

from fastapi import APIRouter, Depends, Query

from app.core.models.auth import CurrentUser
from app.matcha.dependencies import get_client_company_id
from app.matcha.models.matcha_work.recaps import Preferences, Retry, Statuses
from app.matcha.services.matcha_work.recaps import service

from .assistant import require_personal_workspace

router = APIRouter(prefix="/recaps", dependencies=[Depends(require_personal_workspace)])


@router.get("/preferences")
async def preferences(user: CurrentUser = Depends(require_personal_workspace)):
    return await service.preferences(user.id, await get_client_company_id(user))


@router.put("/preferences")
async def save_preferences(body: Preferences, user: CurrentUser = Depends(require_personal_workspace)):
    return await service.set_preferences(user.id, await get_client_company_id(user), body)


@router.post("/statuses")
async def statuses(body: Statuses, user: CurrentUser = Depends(require_personal_workspace)):
    return await service.listing(user.id, await get_client_company_id(user), ids=body.ids, limit=50)


@router.get("")
async def listing(limit: int = Query(25, ge=1, le=50), before: str | None = Query(None, max_length=512),
                  source_id: UUID | None = None, user: CurrentUser = Depends(require_personal_workspace)):
    return await service.listing(user.id, await get_client_company_id(user), limit=limit, before=before, source_id=source_id)


@router.get("/{recap_id}")
async def detail(recap_id: UUID, user: CurrentUser = Depends(require_personal_workspace)):
    return await service.detail(user.id, await get_client_company_id(user), recap_id)


@router.post("/{recap_id}/playback")
async def playback(recap_id: UUID, user: CurrentUser = Depends(require_personal_workspace)):
    return await service.playback(user.id, await get_client_company_id(user), recap_id)


@router.post("/{recap_id}/retry", status_code=202)
async def retry(recap_id: UUID, body: Retry, user: CurrentUser = Depends(require_personal_workspace)):
    return await service.retry(user.id, await get_client_company_id(user), recap_id, body.request_id)


@router.delete("/{recap_id}")
async def delete(recap_id: UUID, user: CurrentUser = Depends(require_personal_workspace)):
    return await service.delete(user.id, await get_client_company_id(user), recap_id)
