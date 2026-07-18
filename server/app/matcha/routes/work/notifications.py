"""Matcha Work notification endpoints."""

import json
import logging
from datetime import datetime
from typing import Optional
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

from app.matcha.dependencies import require_admin_or_client, get_client_company_id
from app.core.dependencies import get_current_user
from app.core.models.auth import CurrentUser
from app.matcha.services import notification_service as notif_svc

logger = logging.getLogger(__name__)

router = APIRouter()


def _parse_metadata(raw) -> dict:
    """asyncpg returns JSONB as a string (no codec registered), so coerce it
    to a dict for the client. Tolerate dicts (if a codec is ever added) and
    bad values."""
    if isinstance(raw, dict):
        return raw
    if isinstance(raw, str) and raw:
        try:
            parsed = json.loads(raw)
            return parsed if isinstance(parsed, dict) else {}
        except (ValueError, TypeError):
            return {}
    return {}


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


class MarkReadByRequest(BaseModel):
    """Clear notifications by the entity the user just interacted with.
    Exactly one of these should be set."""
    task_id: Optional[str] = None
    section_id: Optional[str] = None
    channel_id: Optional[str] = None
    project_id: Optional[str] = None


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
                "metadata": _parse_metadata(n["metadata"]),
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


@router.get("/notifications/project-unread-counts")
async def project_unread_counts(
    current_user: CurrentUser = Depends(get_current_user),
):
    """Per-project unread-notification counts — powers the werk tab badge."""
    company_id = await get_client_company_id(current_user)
    counts = await notif_svc.get_project_unread_counts(current_user.id, company_id=company_id)
    return {"counts": counts}


@router.post("/notifications/mark-read-by")
async def mark_read_by(
    body: MarkReadByRequest,
    current_user: CurrentUser = Depends(get_current_user),
):
    """Mark the user's notifications read by the entity they opened (ticket,
    note section, channel, project). Clears matching rows from both the bell
    and the project tab badge."""
    pairs = [
        ("task_id", body.task_id),
        ("section_id", body.section_id),
        ("channel_id", body.channel_id),
        ("project_id", body.project_id),
    ]
    total = 0
    for key, value in pairs:
        if value:
            total += await notif_svc.mark_read_by_metadata(current_user.id, key, value)
    return {"updated": total}


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
