"""Newsletter routes — public subscribe/unsubscribe + admin management."""

import logging
from typing import Optional
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, EmailStr

from ..dependencies import get_current_user, require_admin
from ..models.auth import CurrentUser
from ..services import newsletter_service as svc

logger = logging.getLogger(__name__)

public_router = APIRouter()
admin_router = APIRouter()


# ---------------------------------------------------------------------------
# Public endpoints (no auth)
# ---------------------------------------------------------------------------


class SubscribeRequest(BaseModel):
    email: EmailStr
    name: Optional[str] = None
    source: str = "website"
    utm_source: Optional[str] = None
    utm_medium: Optional[str] = None
    utm_campaign: Optional[str] = None


@public_router.post("/subscribe")
async def subscribe(body: SubscribeRequest):
    """Public endpoint — subscribe an email to the newsletter."""
    metadata = {}
    if body.utm_source:
        metadata["utm_source"] = body.utm_source
    if body.utm_medium:
        metadata["utm_medium"] = body.utm_medium
    if body.utm_campaign:
        metadata["utm_campaign"] = body.utm_campaign

    result = await svc.subscribe(
        email=body.email,
        name=body.name,
        source=body.source,
        metadata=metadata if metadata else None,
    )
    return {"ok": True, **result}


@public_router.get("/unsubscribe")
async def unsubscribe(token: str = Query(...)):
    """One-click unsubscribe via signed token. Returns HTML page."""
    from fastapi.responses import HTMLResponse
    success = await svc.unsubscribe(token)
    if not success:
        return HTMLResponse(
            '<html><body style="background:#1e1e1e;color:#d4d4d4;font-family:sans-serif;display:flex;align-items:center;justify-content:center;height:100vh;">'
            '<div style="text-align:center"><h2>Invalid link</h2><p>This unsubscribe link is invalid or expired.</p></div></body></html>',
            status_code=400,
        )
    return HTMLResponse(
        '<html><body style="background:#1e1e1e;color:#d4d4d4;font-family:sans-serif;display:flex;align-items:center;justify-content:center;height:100vh;">'
        '<div style="text-align:center"><h2 style="color:#ce9178;">Unsubscribed</h2><p>You have been unsubscribed from Matcha newsletters.</p>'
        '<p style="color:#6a737d;font-size:13px;margin-top:16px;">You can close this tab.</p></div></body></html>'
    )


# ---------------------------------------------------------------------------
# Admin endpoints
# ---------------------------------------------------------------------------


@admin_router.get("/subscribers")
async def list_subscribers(
    status: Optional[str] = None,
    source: Optional[str] = None,
    search: Optional[str] = None,
    limit: int = Query(50, ge=1, le=200),
    offset: int = Query(0, ge=0),
    current_user: CurrentUser = Depends(require_admin),
):
    """List newsletter subscribers with filters."""
    rows, total = await svc.get_subscribers(
        status=status, source=source, search=search, limit=limit, offset=offset,
    )
    stats = await svc.get_subscriber_stats()
    return {"subscribers": rows, "total": total, "stats": stats}


@admin_router.post("/subscribers/import")
async def import_subscribers(
    body: dict,
    current_user: CurrentUser = Depends(require_admin),
):
    """Bulk import emails. Body: { "emails": [{"email": "...", "name": "..."}] }"""
    emails = body.get("emails", [])
    if not emails:
        raise HTTPException(status_code=400, detail="No emails provided")

    imported = 0
    for entry in emails[:500]:  # cap at 500
        email = entry.get("email", "").strip().lower() if isinstance(entry, dict) else str(entry).strip().lower()
        name = entry.get("name") if isinstance(entry, dict) else None
        if "@" in email:
            await svc.subscribe(email=email, name=name, source="import")
            imported += 1

    return {"imported": imported}


class CreateNewsletterRequest(BaseModel):
    title: str
    subject: str


class UpdateNewsletterRequest(BaseModel):
    title: Optional[str] = None
    subject: Optional[str] = None
    content_html: Optional[str] = None
    curated_article_ids: Optional[list[str]] = None


@admin_router.get("/newsletters")
async def list_newsletters(
    limit: int = Query(20, ge=1, le=100),
    offset: int = Query(0, ge=0),
    current_user: CurrentUser = Depends(require_admin),
):
    """List all newsletters."""
    return await svc.list_newsletters(limit=limit, offset=offset)


@admin_router.post("/newsletters")
async def create_newsletter(
    body: CreateNewsletterRequest,
    current_user: CurrentUser = Depends(require_admin),
):
    """Create a new newsletter draft."""
    return await svc.create_newsletter(
        title=body.title.strip(),
        subject=body.subject.strip(),
        created_by=current_user.id,
    )


@admin_router.get("/newsletters/{newsletter_id}")
async def get_newsletter(
    newsletter_id: UUID,
    current_user: CurrentUser = Depends(require_admin),
):
    """Get newsletter with send stats."""
    result = await svc.get_newsletter(newsletter_id)
    if not result:
        raise HTTPException(status_code=404, detail="Newsletter not found")
    return result


@admin_router.put("/newsletters/{newsletter_id}")
async def update_newsletter(
    newsletter_id: UUID,
    body: UpdateNewsletterRequest,
    current_user: CurrentUser = Depends(require_admin),
):
    """Update a newsletter draft."""
    updates = {k: v for k, v in body.model_dump().items() if v is not None}
    if not updates:
        raise HTTPException(status_code=400, detail="No updates provided")
    try:
        return await svc.update_newsletter(newsletter_id, updates)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


@admin_router.post("/newsletters/{newsletter_id}/send")
async def send_newsletter(
    newsletter_id: UUID,
    current_user: CurrentUser = Depends(require_admin),
):
    """Send a newsletter to all active subscribers."""
    try:
        result = await svc.send_newsletter(newsletter_id)
        return result
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


@admin_router.delete("/newsletters/{newsletter_id}")
async def delete_newsletter(
    newsletter_id: UUID,
    current_user: CurrentUser = Depends(require_admin),
):
    """Delete a newsletter draft."""
    from ...database import get_connection
    async with get_connection() as conn:
        result = await conn.execute(
            "DELETE FROM newsletters WHERE id = $1 AND status = 'draft'",
            newsletter_id,
        )
    if "DELETE 0" in result:
        raise HTTPException(status_code=400, detail="Newsletter not found or already sent")
    return {"ok": True}
