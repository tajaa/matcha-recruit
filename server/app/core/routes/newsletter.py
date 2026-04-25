"""Newsletter routes — public subscribe/confirm/unsubscribe + admin management."""

import logging
import os
import time
from typing import Optional
from uuid import UUID

from fastapi import APIRouter, Depends, File, HTTPException, Query, Request, UploadFile
from fastapi.responses import HTMLResponse, PlainTextResponse
from pydantic import BaseModel, EmailStr

from ..dependencies import get_current_user, require_admin
from ..models.auth import CurrentUser
from ..services import newsletter_service as svc

logger = logging.getLogger(__name__)

public_router = APIRouter()
admin_router = APIRouter()


# ---------------------------------------------------------------------------
# In-process rate limit for /subscribe (mirrors client_errors.py pattern).
# Keyed by client IP. Resets on backend restart.
# ---------------------------------------------------------------------------

_SUBSCRIBE_WINDOW_SECONDS = 60
_SUBSCRIBE_MAX_PER_WINDOW = 10
_subscribe_state: dict[str, list[float]] = {}


def _subscribe_rate_limited(client_ip: str) -> bool:
    now = time.monotonic()
    cutoff = now - _SUBSCRIBE_WINDOW_SECONDS
    timestamps = [t for t in _subscribe_state.get(client_ip, []) if t >= cutoff]
    if len(timestamps) >= _SUBSCRIBE_MAX_PER_WINDOW:
        _subscribe_state[client_ip] = timestamps
        return True
    timestamps.append(now)
    _subscribe_state[client_ip] = timestamps
    if len(_subscribe_state) > 1000:
        for ip in list(_subscribe_state.keys()):
            if not _subscribe_state[ip] or _subscribe_state[ip][-1] < cutoff:
                _subscribe_state.pop(ip, None)
    return False


def _client_ip(request: Request) -> str:
    fwd = request.headers.get("x-forwarded-for")
    if fwd:
        return fwd.split(",")[0].strip()
    return request.client.host if request.client else "unknown"


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


def _confirmation_url(token: str) -> str:
    from ...config import get_settings
    base = (get_settings().app_base_url or "https://hey-matcha.com").rstrip("/")
    return f"{base}/api/newsletter/confirm?token={token}"


async def _send_confirmation_email(to_email: str, to_name: Optional[str], confirm_url: str) -> None:
    from ..services.email import get_email_service
    html = f"""
    <div style="max-width:600px;margin:0 auto;font-family:-apple-system,system-ui,sans-serif;
                background:#1e1e1e;color:#d4d4d4;padding:32px 24px;">
      <div style="text-align:center;margin-bottom:24px;">
        <span style="font-size:20px;font-weight:700;color:#ce9178;">Matcha</span>
      </div>
      <h1 style="font-size:20px;color:#e4e4e7;">Confirm your subscription</h1>
      <p style="font-size:15px;line-height:1.6;">
        Tap the button below to confirm you want to receive the Matcha newsletter.
        If this wasn't you, ignore this email — nothing will happen.
      </p>
      <p style="text-align:center;margin:32px 0;">
        <a href="{confirm_url}" style="display:inline-block;background:#ce9178;color:#1e1e1e;
           padding:12px 24px;border-radius:6px;text-decoration:none;font-weight:600;">
          Confirm subscription
        </a>
      </p>
      <p style="font-size:12px;color:#6a737d;">If the button doesn't work, paste this link:<br>
        <span style="word-break:break-all;color:#569cd6;">{confirm_url}</span>
      </p>
    </div>
    """
    try:
        await get_email_service().send_email(
            to_email=to_email, to_name=to_name,
            subject="Confirm your Matcha newsletter subscription",
            html_content=html,
        )
    except Exception:
        logger.exception("Failed to send confirmation email to %s", to_email)


@public_router.post("/subscribe")
async def subscribe(body: SubscribeRequest, request: Request):
    """Public subscribe — starts double-opt-in unless email already active."""
    if _subscribe_rate_limited(_client_ip(request)):
        raise HTTPException(status_code=429, detail="Too many subscribe attempts. Please wait a minute.")

    metadata = {}
    if body.utm_source: metadata["utm_source"] = body.utm_source
    if body.utm_medium: metadata["utm_medium"] = body.utm_medium
    if body.utm_campaign: metadata["utm_campaign"] = body.utm_campaign

    result = await svc.subscribe(
        email=body.email, name=body.name, source=body.source,
        metadata=metadata if metadata else None,
    )

    if result.get("confirmation_token"):
        confirm_url = _confirmation_url(result["confirmation_token"])
        await _send_confirmation_email(body.email, body.name, confirm_url)

    # Don't return the confirmation token to the public endpoint — it's only
    # delivered via email so an attacker who learns the email can't auto-confirm.
    return {
        "ok": True,
        "id": result["id"],
        "status": result["status"],
        "already_subscribed": result["already_subscribed"],
        "needs_confirmation": result["status"] == "pending",
    }


@public_router.get("/confirm")
async def confirm(token: str = Query(...)):
    """Click target from the confirmation email — flips pending → active."""
    row = await svc.confirm_subscription(token)
    if not row:
        return HTMLResponse(
            '<html><body style="background:#1e1e1e;color:#d4d4d4;font-family:sans-serif;'
            'display:flex;align-items:center;justify-content:center;height:100vh;">'
            '<div style="text-align:center"><h2>Already confirmed or expired</h2>'
            '<p>This confirmation link is invalid or has already been used.</p></div></body></html>',
            status_code=400,
        )
    return HTMLResponse(
        '<html><body style="background:#1e1e1e;color:#d4d4d4;font-family:sans-serif;'
        'display:flex;align-items:center;justify-content:center;height:100vh;">'
        '<div style="text-align:center"><h2 style="color:#ce9178;">Subscription confirmed</h2>'
        '<p>Welcome aboard. You\'ll start receiving the Matcha newsletter.</p>'
        '<p style="color:#6a737d;font-size:13px;margin-top:16px;">You can close this tab.</p>'
        '</div></body></html>'
    )


@public_router.get("/unsubscribe")
async def unsubscribe_get(token: str = Query(...)):
    success = await svc.unsubscribe(token)
    if not success:
        return HTMLResponse(
            '<html><body style="background:#1e1e1e;color:#d4d4d4;font-family:sans-serif;'
            'display:flex;align-items:center;justify-content:center;height:100vh;">'
            '<div style="text-align:center"><h2>Invalid link</h2>'
            '<p>This unsubscribe link is invalid, already used, or expired.</p></div></body></html>',
            status_code=400,
        )
    return HTMLResponse(
        '<html><body style="background:#1e1e1e;color:#d4d4d4;font-family:sans-serif;'
        'display:flex;align-items:center;justify-content:center;height:100vh;">'
        '<div style="text-align:center"><h2 style="color:#ce9178;">Unsubscribed</h2>'
        '<p>You have been unsubscribed from Matcha newsletters.</p>'
        '<p style="color:#6a737d;font-size:13px;margin-top:16px;">You can close this tab.</p>'
        '</div></body></html>'
    )


@public_router.post("/unsubscribe")
async def unsubscribe_post(token: str = Query(...)):
    """RFC 8058 List-Unsubscribe-Post one-click endpoint. Gmail/Outlook hit
    this directly when the user clicks the inbox unsubscribe button."""
    await svc.unsubscribe(token)
    return PlainTextResponse("OK")


# ---------------------------------------------------------------------------
# Bounce webhook — provider posts JSON; we mark the subscriber bounced.
# ---------------------------------------------------------------------------


class BounceEvent(BaseModel):
    email: Optional[EmailStr] = None
    subscriber_id: Optional[UUID] = None
    reason: Optional[str] = None
    type: Optional[str] = None  # "hard" | "soft" — only hard bounces auto-unsubscribe


@public_router.post("/bounce")
async def bounce_webhook(body: BounceEvent, request: Request):
    """Email-provider bounce callback. Soft bounces are logged but don't
    deactivate; hard bounces flip the subscriber to bounced."""
    # Soft bounces — log + ack, don't flip status. Sender retries naturally.
    if body.type == "soft":
        logger.info("Soft bounce: %s (%s)", body.email or body.subscriber_id, body.reason)
        return {"ok": True, "action": "logged"}

    target = body.subscriber_id or body.email
    if not target:
        raise HTTPException(status_code=400, detail="email or subscriber_id required")
    flipped = await svc.mark_bounced(target, reason=body.reason)
    return {"ok": True, "action": "bounced" if flipped else "no_match"}


@public_router.get("/view/{newsletter_id}")
async def view_newsletter(newsletter_id: UUID):
    """Public 'View in browser' for sent newsletters."""
    from ...database import get_connection

    async with get_connection() as conn:
        row = await conn.fetchrow(
            """SELECT title, subject, content_html, sent_at FROM newsletters
               WHERE id = $1 AND status = 'sent' AND is_deleted = FALSE""",
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
    request: Request,
    current_user: CurrentUser = Depends(require_admin),
):
    count = await svc.sync_platform_users()
    await svc.log_admin_action(
        current_user.id, "subscribers_sync", "subscribers", None,
        {"synced": count}, _client_ip(request),
    )
    return {"synced": count}


@admin_router.get("/subscribers")
async def list_subscribers(
    request: Request,
    status: Optional[str] = None,
    source: Optional[str] = None,
    search: Optional[str] = None,
    limit: int = Query(50, ge=1, le=200),
    offset: int = Query(0, ge=0),
    export: bool = Query(False),
    current_user: CurrentUser = Depends(require_admin),
):
    """List subscribers. `export=true` writes an audit row (GDPR)."""
    await svc.sync_platform_users()
    rows, total = await svc.get_subscribers(
        status=status, source=source, search=search, limit=limit, offset=offset,
    )
    stats = await svc.get_subscriber_stats()
    if export:
        await svc.log_admin_action(
            current_user.id, "subscribers_export", "subscribers", None,
            {"count": len(rows), "filters": {"status": status, "source": source, "search": search}},
            _client_ip(request),
        )
    return {"subscribers": rows, "total": total, "stats": stats}


@admin_router.delete("/subscribers/{subscriber_id}")
async def delete_subscriber(
    subscriber_id: UUID,
    current_user: CurrentUser = Depends(require_admin),
):
    """GDPR right-to-erasure — hard delete + audit row."""
    deleted = await svc.delete_subscriber(subscriber_id, current_user.id)
    if not deleted:
        raise HTTPException(status_code=404, detail="Subscriber not found")
    return {"ok": True}


@admin_router.post("/subscribers/import")
async def import_subscribers(
    body: dict,
    request: Request,
    current_user: CurrentUser = Depends(require_admin),
):
    """Bulk import emails. auto_confirm=True since admin vouches for the list."""
    emails = body.get("emails", [])
    if not emails:
        raise HTTPException(status_code=400, detail="No emails provided")

    imported = 0
    for entry in emails[:500]:
        email = entry.get("email", "").strip().lower() if isinstance(entry, dict) else str(entry).strip().lower()
        name = entry.get("name") if isinstance(entry, dict) else None
        if "@" in email:
            await svc.subscribe(email=email, name=name, source="import", auto_confirm=True)
            imported += 1

    await svc.log_admin_action(
        current_user.id, "subscribers_import", "subscribers", None,
        {"imported": imported}, _client_ip(request),
    )
    return {"imported": imported}


@admin_router.get("/audit")
async def list_audit(
    limit: int = Query(100, ge=1, le=500),
    offset: int = Query(0, ge=0),
    current_user: CurrentUser = Depends(require_admin),
):
    """Read newsletter admin audit log (subscriber exports, deletes, sends)."""
    from ...database import get_connection
    async with get_connection() as conn:
        rows = await conn.fetch(
            """SELECT a.*, COALESCE(adm.name, u.email, 'Unknown') AS actor_name
               FROM newsletter_admin_audit a
               LEFT JOIN users u ON u.id = a.actor_id
               LEFT JOIN admins adm ON adm.user_id = a.actor_id
               ORDER BY a.created_at DESC
               LIMIT $1 OFFSET $2""",
            limit, offset,
        )
    return {"items": [dict(r) for r in rows]}


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
    return await svc.list_newsletters(limit=limit, offset=offset)


@admin_router.post("/newsletters")
async def create_newsletter(
    body: CreateNewsletterRequest,
    current_user: CurrentUser = Depends(require_admin),
):
    return await svc.create_newsletter(
        title=body.title.strip(), subject=body.subject.strip(),
        created_by=current_user.id,
    )


@admin_router.get("/newsletters/{newsletter_id}")
async def get_newsletter(
    newsletter_id: UUID,
    current_user: CurrentUser = Depends(require_admin),
):
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
    updates = {k: v for k, v in body.model_dump().items() if v is not None}
    if not updates:
        raise HTTPException(status_code=400, detail="No updates provided")
    try:
        return await svc.update_newsletter(newsletter_id, updates)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


class TestSendRequest(BaseModel):
    to_email: EmailStr
    to_name: Optional[str] = None


@admin_router.post("/newsletters/{newsletter_id}/test-send")
async def test_send(
    newsletter_id: UUID,
    body: TestSendRequest,
    current_user: CurrentUser = Depends(require_admin),
):
    """Render + send a single test email to a chosen address. Doesn't
    update newsletter state or write to newsletter_sends."""
    try:
        ok = await svc.send_test_email(newsletter_id, body.to_email, body.to_name)
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))
    if not ok:
        raise HTTPException(status_code=500, detail="Email send failed (provider not configured?)")
    return {"ok": True}


@admin_router.post("/newsletters/{newsletter_id}/send")
async def send_newsletter(
    newsletter_id: UUID,
    request: Request,
    current_user: CurrentUser = Depends(require_admin),
):
    """Broadcast to all active subscribers. Idempotent — second call 409s."""
    try:
        result = await svc.send_newsletter(newsletter_id, actor_id=current_user.id)
        return result
    except ValueError as e:
        raise HTTPException(status_code=409, detail=str(e))


_ALLOWED_MEDIA_EXT = {".jpg", ".jpeg", ".png", ".gif", ".webp", ".svg", ".mp4", ".mov", ".pdf"}
_MAX_MEDIA_SIZE = 10 * 1024 * 1024  # 10 MB


@admin_router.post("/media/upload")
async def upload_newsletter_media(
    file: UploadFile = File(...),
    current_user: CurrentUser = Depends(require_admin),
):
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
    """Soft-delete (sets is_deleted=TRUE + audit row). Refuses already-sent."""
    deleted = await svc.soft_delete_newsletter(newsletter_id, current_user.id)
    if not deleted:
        raise HTTPException(status_code=400, detail="Newsletter not found, already deleted, or not in draft")
    return {"ok": True}
