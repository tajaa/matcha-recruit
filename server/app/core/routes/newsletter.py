"""Newsletter routes — public subscribe/unsubscribe + admin management."""

import logging
from typing import Optional
from uuid import UUID

import os

from fastapi import APIRouter, Depends, File, HTTPException, Query, UploadFile
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


@public_router.get("/view/{newsletter_id}")
async def view_newsletter(newsletter_id: UUID):
    """Public 'View in browser' endpoint for sent newsletters."""
    from fastapi.responses import HTMLResponse
    from ...database import get_connection

    async with get_connection() as conn:
        row = await conn.fetchrow(
            "SELECT title, subject, content_html, sent_at FROM newsletters WHERE id = $1 AND status = 'sent'",
            newsletter_id,
        )
    CDN = "https://cdn.jsdelivr.net/npm/@tailwindcss/cdn@4"
    if not row or not row["content_html"]:
        return HTMLResponse(
            f'<!DOCTYPE html><html><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">'
            f'<script src="{CDN}"></script>'
            f'<title>Not Found — Matcha</title></head>'
            f'<body class="bg-zinc-950 text-zinc-300 font-sans min-h-screen flex items-center justify-center">'
            f'<div class="text-center px-6"><h2 class="text-2xl font-semibold text-zinc-100 mb-2">Newsletter not found</h2>'
            f'<p class="text-zinc-500">This newsletter doesn\'t exist or hasn\'t been published yet.</p></div></body></html>',
            status_code=404,
        )
    title = row["title"] or row["subject"] or "Newsletter"
    sent_at = row["sent_at"].strftime("%B %d, %Y") if row.get("sent_at") else ""
    return HTMLResponse(
        f'<!DOCTYPE html><html><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">'
        f'<script src="{CDN}"></script>'
        f'<title>{title} — Matcha</title></head>'
        f'<body class="bg-zinc-950 text-zinc-200 font-sans min-h-screen">'
        f'<header class="border-b border-zinc-800">'
        f'<div class="max-w-2xl mx-auto px-6 py-4 flex items-center justify-between">'
        f'<span class="text-sm font-semibold tracking-wide text-emerald-500">matcha</span>'
        f'<span class="text-xs text-zinc-600">{sent_at}</span></div></header>'
        f'<main class="max-w-2xl mx-auto px-6 py-10">'
        f'<h1 class="text-3xl font-bold text-zinc-100 mb-8">{title}</h1>'
        f'<article class="prose prose-invert prose-zinc prose-sm max-w-none '
        f'prose-headings:text-zinc-100 prose-a:text-emerald-400 prose-strong:text-zinc-100 '
        f'prose-img:rounded-lg prose-img:border prose-img:border-zinc-800">'
        f'{row["content_html"]}</article></main>'
        f'<footer class="border-t border-zinc-800 mt-16">'
        f'<div class="max-w-2xl mx-auto px-6 py-6 text-center text-xs text-zinc-600">'
        f'Sent with Matcha</div></footer></body></html>'
    )


# ---------------------------------------------------------------------------
# Admin endpoints
# ---------------------------------------------------------------------------


@admin_router.post("/subscribers/sync")
async def sync_platform_users(
    current_user: CurrentUser = Depends(require_admin),
):
    """Sync all active platform users into newsletter subscribers."""
    count = await svc.sync_platform_users()
    return {"synced": count}


@admin_router.get("/subscribers")
async def list_subscribers(
    status: Optional[str] = None,
    source: Optional[str] = None,
    search: Optional[str] = None,
    limit: int = Query(50, ge=1, le=200),
    offset: int = Query(0, ge=0),
    current_user: CurrentUser = Depends(require_admin),
):
    """List newsletter subscribers with filters. Auto-syncs platform users."""
    # Auto-sync platform users on each load (idempotent, fast)
    await svc.sync_platform_users()

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


_ALLOWED_MEDIA_EXT = {".jpg", ".jpeg", ".png", ".gif", ".webp", ".svg", ".mp4", ".mov", ".pdf"}
_MAX_MEDIA_SIZE = 10 * 1024 * 1024  # 10 MB


@admin_router.post("/media/upload")
async def upload_newsletter_media(
    file: UploadFile = File(...),
    current_user: CurrentUser = Depends(require_admin),
):
    """Upload an image/video/file for use in newsletter content. Returns the CDN URL."""
    from ..services.storage import get_storage

    file_bytes = await file.read()
    filename = file.filename or "upload"
    ct = file.content_type or "application/octet-stream"
    ext = os.path.splitext(filename)[1].lower()

    if ext not in _ALLOWED_MEDIA_EXT:
        raise HTTPException(status_code=400, detail=f"File type not allowed: {ext}")
    if len(file_bytes) > _MAX_MEDIA_SIZE:
        raise HTTPException(status_code=400, detail="File too large (max 10MB)")

    storage = get_storage()
    url = await storage.upload_file(file_bytes, filename, prefix="newsletter", content_type=ct)
    return {"url": url, "filename": filename, "content_type": ct, "size": len(file_bytes)}


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
