"""Newsletter routes — public subscribe/confirm/unsubscribe + admin management."""

import base64
import logging
import os
import time
from datetime import datetime, timezone
from typing import Optional
from uuid import UUID

from fastapi import APIRouter, Depends, File, HTTPException, Query, Request, UploadFile
from fastapi.responses import HTMLResponse, PlainTextResponse, RedirectResponse, Response
from pydantic import BaseModel, EmailStr, Field

from ..dependencies import get_current_user, get_optional_user, require_admin
from ..models.auth import CurrentUser
from ..services import newsletter_service as svc

logger = logging.getLogger(__name__)

public_router = APIRouter()
admin_router = APIRouter()


# ---------------------------------------------------------------------------
# Rate limit for /subscribe — Redis-backed when available, falls back to an
# in-process counter so single-worker dev environments still work.
#
# Redis path: INCR a per-IP key with a 60s EXPIRE. Counter is atomic and
# survives across uvicorn workers, so a deployment behind N workers no
# longer multiplies the effective limit by N.
# ---------------------------------------------------------------------------

_SUBSCRIBE_WINDOW_SECONDS = 60
_SUBSCRIBE_MAX_PER_WINDOW = 10
_subscribe_state: dict[str, list[float]] = {}


async def _subscribe_rate_limited(client_ip: str) -> bool:
    from ..services.redis_cache import get_redis_cache

    redis = get_redis_cache()
    if redis is not None:
        key = f"newsletter:subscribe:rl:{client_ip}"
        try:
            count = await redis.incr(key)
            if count == 1:
                # Only set EXPIRE on the first hit so the window slides
                # naturally — INCR doesn't reset TTL.
                await redis.expire(key, _SUBSCRIBE_WINDOW_SECONDS)
            return count > _SUBSCRIBE_MAX_PER_WINDOW
        except Exception:
            # Redis unreachable — fall through to in-process limiter so a
            # transient infra blip doesn't wedge signups.
            logger.warning("Newsletter subscribe rate limit fell back to in-process — Redis unreachable")

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
async def subscribe(
    body: SubscribeRequest,
    request: Request,
    current_user: Optional[CurrentUser] = Depends(get_optional_user),
):
    """Public subscribe — starts double-opt-in unless email already active.

    If the request is authenticated, the user's id is used to derive a
    tier-tag (tier-free / tier-lite / tier-platform / tier-personal) so
    admin can target segments later. Source-bucket tags ('blog', 'calculators',
    etc.) are also auto-attached based on `source`.
    """
    if await _subscribe_rate_limited(_client_ip(request)):
        raise HTTPException(status_code=429, detail="Too many subscribe attempts. Please wait a minute.")

    metadata = {}
    if body.utm_source: metadata["utm_source"] = body.utm_source
    if body.utm_medium: metadata["utm_medium"] = body.utm_medium
    if body.utm_campaign: metadata["utm_campaign"] = body.utm_campaign

    user_id = current_user.id if current_user else None
    result = await svc.subscribe(
        email=body.email, name=body.name, source=body.source,
        metadata=metadata if metadata else None,
        user_id=user_id,
    )

    # Auto-tag — best effort, never blocks the subscribe response.
    try:
        tag_slugs = await svc.derive_signup_tags(body.source, user_id)
        if tag_slugs:
            await svc.attach_tags_to_subscriber(UUID(result["id"]), tag_slugs)
    except Exception:
        logger.exception("Auto-tag failed for subscriber %s", result.get("id"))

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
async def bounce_webhook(request: Request):
    """Email-provider bounce callback.

    Authenticated EITHER via:
    - X-Bounce-Signature: hex-encoded HMAC-SHA256 of the raw request body
      using NEWSLETTER_BOUNCE_SECRET as the key. (Preferred — protects
      against header replay if logs leak.)
    - X-Bounce-Secret: shared-secret header (legacy / fallback).

    Endpoint stays disabled (503) when NEWSLETTER_BOUNCE_SECRET is unset so
    an open route can't slip into production by default.

    Soft bounces increment the subscriber's soft_bounce_count and flip
    them to 'bounced' at SOFT_BOUNCE_LIMIT. Hard bounces flip immediately.

    NOTE: Body is read directly off `request.body()` BEFORE pydantic parsing
    so the HMAC always sees the exact bytes the provider signed. Declaring a
    Pydantic body parameter would have FastAPI consume the stream first; the
    cached re-read works today but breaks if a custom middleware ever wraps
    the request body. Manual parsing is more robust.
    """
    from ...config import get_settings
    import hmac as _hmac
    import hashlib as _hashlib
    import json as _json

    expected = (get_settings().newsletter_bounce_secret or "").strip()
    if not expected:
        raise HTTPException(status_code=503, detail="Bounce webhook not configured")

    raw_body = await request.body()
    sig_header = request.headers.get("x-bounce-signature", "").strip()
    legacy_header = request.headers.get("x-bounce-secret", "")

    authed = False
    if sig_header:
        expected_sig = _hmac.new(expected.encode(), raw_body, _hashlib.sha256).hexdigest()
        # Strip optional 'sha256=' prefix if the provider includes it.
        provided = sig_header.split("=", 1)[-1].strip().lower()
        if _hmac.compare_digest(provided.encode(), expected_sig.encode()):
            authed = True
    if not authed and legacy_header:
        if _hmac.compare_digest(legacy_header.encode(), expected.encode()):
            authed = True
            logger.info("Newsletter bounce webhook authed via legacy X-Bounce-Secret — migrate to X-Bounce-Signature")
    if not authed:
        raise HTTPException(status_code=401, detail="Bad secret")

    try:
        payload = _json.loads(raw_body or b"{}")
    except _json.JSONDecodeError:
        raise HTTPException(status_code=400, detail="Invalid JSON body")
    try:
        body = BounceEvent.model_validate(payload)
    except Exception as exc:
        raise HTTPException(status_code=400, detail=f"Invalid bounce body: {exc}")

    target = body.subscriber_id or body.email
    if body.type == "soft":
        if not target:
            raise HTTPException(status_code=400, detail="email or subscriber_id required")
        result = await svc.record_soft_bounce(target, reason=body.reason)
        action = "suppressed" if result["suppressed"] else "counted"
        logger.info(
            "Soft bounce: %s count=%s suppressed=%s",
            body.email or body.subscriber_id, result["count"], result["suppressed"],
        )
        return {"ok": True, "action": action, "count": result["count"]}

    if not target:
        raise HTTPException(status_code=400, detail="email or subscriber_id required")
    flipped = await svc.mark_bounced(target, reason=body.reason)
    return {"ok": True, "action": "bounced" if flipped else "no_match"}


# ---------------------------------------------------------------------------
# Open + click tracking
# ---------------------------------------------------------------------------

# 1×1 transparent GIF — bytes are fixed, embedded so we don't need to ship
# a separate asset. Returned for every open-pixel hit; clients that don't
# load images simply never count, which is the natural behavior.
_TRANSPARENT_GIF = base64.b64decode(
    "R0lGODlhAQABAIAAAAAAAP///yH5BAEAAAAALAAAAAABAAEAAAIBRAA7"
)
_TRACKING_NO_CACHE_HEADERS = {
    "Cache-Control": "no-store, no-cache, must-revalidate, max-age=0",
    "Pragma": "no-cache",
    "Expires": "0",
}


def _gif_response() -> Response:
    return Response(
        content=_TRANSPARENT_GIF,
        media_type="image/gif",
        headers=_TRACKING_NO_CACHE_HEADERS,
    )


@public_router.get("/track/open/{send_id}.gif")
async def track_open(send_id: UUID):
    """Open-tracking pixel.

    Always returns a 1×1 transparent GIF — even on unknown send_id — so a
    badly stored / forwarded email can't surface as a broken image. The DB
    write is idempotent (`opened_at = COALESCE(opened_at, NOW())`), so
    multiple clients prefetching the pixel still count as a single open.
    """
    try:
        subscriber_id = await svc.record_open(send_id)
        if subscriber_id:
            # An open is positive proof the inbox accepted our delivery, so
            # any past soft-bounce streak should reset.
            await svc.reset_soft_bounce_count(subscriber_id)
    except Exception:
        logger.exception("Failed to record newsletter open send_id=%s", send_id)
    return _gif_response()


@public_router.get("/track/click/{send_id}")
async def track_click(send_id: UUID, to: str = Query(..., description="Destination URL")):
    """Click-tracking redirect.

    Records the click then 302s to the original target. If the click record
    fails for any reason we still redirect — better to lose the metric than
    to break the user's link.
    """
    if not to.startswith(("http://", "https://")):
        raise HTTPException(status_code=400, detail="Invalid redirect target")
    try:
        subscriber_id = await svc.record_click(send_id)
        if subscriber_id:
            await svc.reset_soft_bounce_count(subscriber_id)
    except Exception:
        logger.exception("Failed to record newsletter click send_id=%s", send_id)
    return RedirectResponse(url=to, status_code=302)


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
    preheader: Optional[str] = Field(default=None, max_length=255)
    scheduled_at: Optional[datetime] = None


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


class ScheduleNewsletterRequest(BaseModel):
    scheduled_at: datetime


@admin_router.post("/newsletters/{newsletter_id}/schedule")
async def schedule_newsletter(
    newsletter_id: UUID,
    body: ScheduleNewsletterRequest,
    request: Request,
    current_user: CurrentUser = Depends(require_admin),
):
    """Move a draft to status='scheduled' with a future send time.

    The newsletter scheduler beat picks it up at scheduled_at and dispatches
    the send. Re-scheduling a draft that's already scheduled is allowed
    (admin can shift the time); reschedule of a sent / sending newsletter
    is refused.
    """
    if body.scheduled_at.tzinfo is None:
        # Treat naive datetimes as UTC so admins from any TZ get predictable
        # behavior — JSON dates without offsets land as UTC by convention.
        scheduled = body.scheduled_at.replace(tzinfo=timezone.utc)
    else:
        scheduled = body.scheduled_at
    if scheduled <= datetime.now(timezone.utc):
        raise HTTPException(status_code=400, detail="scheduled_at must be in the future")

    from ...database import get_connection
    async with get_connection() as conn:
        row = await conn.fetchrow(
            """UPDATE newsletters
               SET status = 'scheduled',
                   scheduled_at = $2,
                   scheduled_send_started_at = NULL,
                   updated_at = NOW()
               WHERE id = $1
                 AND is_deleted = FALSE
                 AND status IN ('draft', 'scheduled')
               RETURNING id, scheduled_at""",
            newsletter_id, scheduled,
        )
    if not row:
        raise HTTPException(status_code=409, detail="Newsletter not found or already sent")

    await svc.log_admin_action(
        current_user.id, "newsletter_scheduled", "newsletter", str(newsletter_id),
        {"scheduled_at": scheduled.isoformat()}, _client_ip(request),
    )
    return {"ok": True, "scheduled_at": row["scheduled_at"].isoformat()}


@admin_router.post("/newsletters/{newsletter_id}/unschedule")
async def unschedule_newsletter(
    newsletter_id: UUID,
    request: Request,
    current_user: CurrentUser = Depends(require_admin),
):
    """Cancel a scheduled send and return the newsletter to draft."""
    from ...database import get_connection
    async with get_connection() as conn:
        row = await conn.fetchrow(
            """UPDATE newsletters
               SET status = 'draft',
                   scheduled_at = NULL,
                   scheduled_send_started_at = NULL,
                   updated_at = NOW()
               WHERE id = $1 AND status = 'scheduled' AND is_deleted = FALSE
               RETURNING id""",
            newsletter_id,
        )
    if not row:
        raise HTTPException(status_code=409, detail="Newsletter not in scheduled state")

    await svc.log_admin_action(
        current_user.id, "newsletter_unscheduled", "newsletter", str(newsletter_id),
        None, _client_ip(request),
    )
    return {"ok": True}


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


# ---------------------------------------------------------------------------
# Tags + segments (P1)
# ---------------------------------------------------------------------------


class TagCreateRequest(BaseModel):
    slug: str
    label: str
    description: Optional[str] = None


class SubscriberTagsRequest(BaseModel):
    tag_ids: list[UUID]


class SegmentSendRequest(BaseModel):
    tag_slugs: Optional[list[str]] = None  # None / [] = whole list


@admin_router.get("/tags")
async def list_tags(current_user: CurrentUser = Depends(require_admin)):
    return {"tags": await svc.list_tags()}


@admin_router.post("/tags")
async def create_tag(
    body: TagCreateRequest,
    current_user: CurrentUser = Depends(require_admin),
):
    try:
        return await svc.create_tag(body.slug, body.label, body.description)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


@admin_router.delete("/tags/{tag_id}")
async def delete_tag(
    tag_id: UUID,
    current_user: CurrentUser = Depends(require_admin),
):
    if not await svc.delete_tag(tag_id):
        raise HTTPException(status_code=404, detail="Tag not found")
    return {"ok": True}


@admin_router.get("/subscribers/{subscriber_id}/tags")
async def get_subscriber_tags_endpoint(
    subscriber_id: UUID,
    current_user: CurrentUser = Depends(require_admin),
):
    return {"tags": await svc.get_subscriber_tags(subscriber_id)}


@admin_router.put("/subscribers/{subscriber_id}/tags")
async def replace_subscriber_tags_endpoint(
    subscriber_id: UUID,
    body: SubscriberTagsRequest,
    current_user: CurrentUser = Depends(require_admin),
):
    await svc.replace_subscriber_tags(subscriber_id, body.tag_ids)
    return {"ok": True}


@admin_router.post("/newsletters/{newsletter_id}/send-segment")
async def send_to_segment(
    newsletter_id: UUID,
    body: SegmentSendRequest,
    request: Request,
    current_user: CurrentUser = Depends(require_admin),
):
    """Variant of /send that filters to subscribers carrying any of the
    given tag slugs. Empty / null tag_slugs falls back to the full list."""
    try:
        return await svc.send_newsletter_to_segment(
            newsletter_id, tag_slugs=body.tag_slugs or None, actor_id=current_user.id,
        )
    except ValueError as e:
        raise HTTPException(status_code=409, detail=str(e))


# ---------------------------------------------------------------------------
# Templates (P2)
# ---------------------------------------------------------------------------


class TemplateCreateRequest(BaseModel):
    name: str
    description: Optional[str] = None
    content_html: Optional[str] = None
    preheader: Optional[str] = Field(default=None, max_length=255)


class TemplateUpdateRequest(BaseModel):
    name: Optional[str] = None
    description: Optional[str] = None
    content_html: Optional[str] = None
    preheader: Optional[str] = Field(default=None, max_length=255)


@admin_router.get("/templates")
async def list_templates(current_user: CurrentUser = Depends(require_admin)):
    return {"templates": await svc.list_templates()}


@admin_router.post("/templates")
async def create_template(
    body: TemplateCreateRequest,
    current_user: CurrentUser = Depends(require_admin),
):
    return await svc.create_template(
        body.name, body.description, body.content_html, body.preheader,
        created_by=current_user.id,
    )


@admin_router.get("/templates/{template_id}")
async def get_template(
    template_id: UUID,
    current_user: CurrentUser = Depends(require_admin),
):
    row = await svc.get_template(template_id)
    if not row:
        raise HTTPException(status_code=404, detail="Template not found")
    return row


@admin_router.put("/templates/{template_id}")
async def update_template(
    template_id: UUID,
    body: TemplateUpdateRequest,
    current_user: CurrentUser = Depends(require_admin),
):
    updates = {k: v for k, v in body.model_dump().items() if v is not None}
    if not updates:
        raise HTTPException(status_code=400, detail="No updates provided")
    row = await svc.update_template(template_id, updates)
    if not row:
        raise HTTPException(status_code=404, detail="Template not found")
    return row


@admin_router.delete("/templates/{template_id}")
async def delete_template(
    template_id: UUID,
    current_user: CurrentUser = Depends(require_admin),
):
    if not await svc.delete_template(template_id):
        raise HTTPException(status_code=404, detail="Template not found")
    return {"ok": True}


# ---------------------------------------------------------------------------
# Analytics + send progress (P2)
# ---------------------------------------------------------------------------


@admin_router.get("/subscribers/growth")
async def subscriber_growth(
    days: int = Query(90, ge=1, le=730),
    current_user: CurrentUser = Depends(require_admin),
):
    return {"days": days, "series": await svc.get_subscriber_growth(days)}


@admin_router.get("/newsletters/{newsletter_id}/analytics")
async def newsletter_analytics(
    newsletter_id: UUID,
    current_user: CurrentUser = Depends(require_admin),
):
    return await svc.get_newsletter_analytics(newsletter_id)


@admin_router.get("/newsletters/{newsletter_id}/progress")
async def newsletter_progress(
    newsletter_id: UUID,
    current_user: CurrentUser = Depends(require_admin),
):
    """Live send-progress snapshot. Frontend polls this every 2-5s while
    a newsletter is in 'sending' status."""
    return await svc.get_send_progress(newsletter_id)
