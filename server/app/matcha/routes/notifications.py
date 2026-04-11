"""Matcha Work notification endpoints."""

import logging
from datetime import datetime
from typing import Optional
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

from ..dependencies import require_admin_or_client, get_client_company_id
from ...core.dependencies import get_current_user
from ...core.models.auth import CurrentUser
from ..services import notification_service as notif_svc

logger = logging.getLogger(__name__)

router = APIRouter()


class NotificationResponse(BaseModel):
    id: UUID
    type: str
    title: str
    body: Optional[str] = None
    link: Optional[str] = None
    metadata: Optional[dict] = None
    is_read: bool = False
    created_at: datetime


class MarkReadRequest(BaseModel):
    notification_ids: list[UUID]


@router.get("/notifications")
async def list_notifications(
    unread_only: bool = False,
    limit: int = 30,
    offset: int = 0,
    current_user: CurrentUser = Depends(get_current_user),
):
    """Get notifications for the current user, scoped to their current company."""
    company_id = await get_client_company_id(current_user)
    items = await notif_svc.get_notifications(
        current_user.id, company_id=company_id, unread_only=unread_only, limit=limit, offset=offset,
    )
    return {
        "notifications": [
            {
                "id": str(n["id"]),
                "type": n["type"],
                "title": n["title"],
                "body": n["body"],
                "link": n["link"],
                "metadata": n["metadata"],
                "is_read": n["is_read"],
                "created_at": n["created_at"].isoformat(),
            }
            for n in items
        ],
    }


@router.get("/notifications/unread-count")
async def unread_count(
    current_user: CurrentUser = Depends(get_current_user),
):
    """Get unread notification count, scoped to current company."""
    company_id = await get_client_company_id(current_user)
    count = await notif_svc.get_unread_count(current_user.id, company_id=company_id)
    return {"count": count}


@router.post("/notifications/mark-read")
async def mark_read(
    body: MarkReadRequest,
    current_user: CurrentUser = Depends(get_current_user),
):
    """Mark specific notifications as read."""
    updated = await notif_svc.mark_read(current_user.id, body.notification_ids)
    return {"updated": updated}


@router.post("/notifications/mark-all-read")
async def mark_all_read(
    current_user: CurrentUser = Depends(get_current_user),
):
    """Mark all notifications as read."""
    updated = await notif_svc.mark_all_read(current_user.id)
    return {"updated": updated}
