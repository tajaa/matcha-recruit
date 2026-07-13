"""Newsletter service — subscriber management, newsletter composition, and sending.



Hardened for compliance + ops per the audit:
- Double opt-in: new subscribes start `pending` and require email confirmation
- Full SHA-256 HMAC for unsubscribe and confirmation tokens (no truncation)
- HTML sanitization (bleach) on every content_html write
- Idempotent send (refuses if status != draft|scheduled)
- List-Unsubscribe + List-Unsubscribe-Post headers on every sent email
- Bounce handling marks rows + auto-unsubscribes on hard bounces
- Soft-delete for newsletters
- Admin audit log helper
- P0: open + click tracking (per-send pixel and link rewrite), CAN-SPAM
  postal address footer, soft-bounce counter (3 strikes → suppressed),
  preheader.
"""

import asyncio
import hashlib
import hmac
import html as html_lib
import json
import logging
import re
import secrets
from datetime import datetime, timezone
from typing import Literal, Optional
from urllib.parse import quote
from uuid import UUID

import bleach

from ...config import get_settings
from ...database import get_connection
from . import email_blocks
from .email_blocks import PALETTES as EMAIL_THEMES, resolve_palette, render_blocks

logger = logging.getLogger(__name__)

BATCH_SIZE = 50
BATCH_DELAY = 1.0  # seconds between batches

# Soft bounces above this count flip a subscriber to status='bounced' so
# we stop attempting to deliver to a chronically flaky inbox.
SOFT_BOUNCE_LIMIT = 3

# bleach allowlist for newsletter content_html. Permits the rich-text features
# the admin TipTap editor produces (lists, code, links, images, basic styling)
# while stripping <script>, event handlers, and other XSS vectors.
ALLOWED_TAGS = [
    "p", "br", "hr", "div", "span", "strong", "em", "b", "i", "u", "s",
    "h1", "h2", "h3", "h4", "h5", "h6",
    "ul", "ol", "li", "blockquote", "pre", "code",
    "a", "img", "table", "thead", "tbody", "tr", "th", "td",
    "figure", "figcaption", "video", "source",
]
ALLOWED_ATTRS = {
    "*": ["class", "style"],
    "a": ["href", "title", "target", "rel"],
    "img": ["src", "alt", "title", "width", "height"],
    "video": ["src", "controls", "width", "height", "poster"],
    "source": ["src", "type"],
    "table": ["border", "cellpadding", "cellspacing"],
    "td": ["colspan", "rowspan"],
    "th": ["colspan", "rowspan"],
}
ALLOWED_PROTOCOLS = ["http", "https", "mailto"]


def sanitize_html(html: str) -> str:
    """Strip dangerous tags/attrs/protocols from admin-supplied newsletter HTML."""
    if not html:
        return ""
    return bleach.clean(
        html,
        tags=ALLOWED_TAGS,
        attributes=ALLOWED_ATTRS,
        protocols=ALLOWED_PROTOCOLS,
        strip=True,
    )


def _get_secret() -> bytes:
    """Secret used for HMAC signing. Reuses jwt_secret_key (always populated
    via load_settings) — Settings has no `secret_key` attribute; the previous
    `settings.secret_key` reference would have raised AttributeError."""
    settings = get_settings()
    key = getattr(settings, "jwt_secret_key", None) or "matcha-newsletter-default"
    return key.encode()


def _sign(message: str, prefix: str) -> str:
    """Full SHA-256 HMAC hex digest, namespaced by prefix so confirmation
    tokens can't be replayed as unsubscribe tokens (or vice-versa)."""
    payload = f"{prefix}:{message}".encode()
    return hmac.new(_get_secret(), payload, hashlib.sha256).hexdigest()


def _legacy_sign(message: str) -> str:
    """Pre-hardening signature — first 24 hex chars of unprefixed SHA-256 HMAC.
    Kept ONLY so unsubscribe links already in recipients' inboxes still work
    after deploy. Remove after the legacy-token grace window (e.g. 90 days
    past the rollout)."""
    return hmac.new(_get_secret(), message.encode(), hashlib.sha256).hexdigest()[:24]


def generate_unsubscribe_token(subscriber_id: UUID) -> str:
    sig = _sign(str(subscriber_id), "unsub")
    return f"{subscriber_id}:{sig}"


def verify_unsubscribe_token(token: str) -> Optional[UUID]:
    """Accept new (full-HMAC, namespaced) tokens AND legacy (24-char,
    unprefixed) tokens so previously-sent emails keep working."""
    try:
        sub_id_str, sig = token.split(":", 1)
        # Try new format first
        if hmac.compare_digest(sig, _sign(sub_id_str, "unsub")):
            return UUID(sub_id_str)
        # Fall back to legacy 24-char format for tokens already in the wild
        if hmac.compare_digest(sig, _legacy_sign(sub_id_str)):
            return UUID(sub_id_str)
    except (ValueError, AttributeError):
        pass
    return None


def generate_confirmation_token() -> str:
    """Random opaque token stored in the row; not derivable from email."""
    return secrets.token_urlsafe(32)


# ---------------------------------------------------------------------------
# Subscribe / confirm / unsubscribe
# ---------------------------------------------------------------------------


async def subscribe(
    email: str,
    name: Optional[str] = None,
    source: str = "website",
    metadata: Optional[dict] = None,
    user_id: Optional[UUID] = None,
    company_id: Optional[UUID] = None,
    auto_confirm: bool = False,
) -> dict:
    """Create or refresh a subscriber row.

    Returns {id, status, confirmation_token?, already_subscribed}.
    Default flow: status='pending' + confirmation_token. Caller (route
    handler) is responsible for emailing the confirm link.
    `auto_confirm=True` is reserved for trusted server-side imports
    (sync_platform_users, admin import) where the email has already been
    verified by another channel.
    """
    email = email.strip().lower()
    confirm_token = generate_confirmation_token() if not auto_confirm else None
    initial_status = "active" if auto_confirm else "pending"

    async with get_connection() as conn:
        # Explicit opt-in (website sign-up or admin import) clears any prior
        # admin removal — otherwise a genuine re-subscribe would be silently
        # dropped by sync_platform_users' suppression filter.
        await conn.execute(
            "DELETE FROM newsletter_suppressions WHERE email = $1", email
        )
        existing = await conn.fetchrow(
            "SELECT id, status FROM newsletter_subscribers WHERE email = $1", email
        )
        if existing:
            already = existing["status"] == "active"
            if existing["status"] in ("unsubscribed", "bounced"):
                # Reactivate via the same opt-in flow used for new sign-ups.
                await conn.execute(
                    """UPDATE newsletter_subscribers
                       SET status = $2,
                           unsubscribed_at = NULL,
                           bounced_at = NULL,
                           bounce_reason = NULL,
                           confirmation_token = $3,
                           confirmed_at = CASE WHEN $2 = 'active' THEN NOW() ELSE confirmed_at END,
                           name = COALESCE($4, name),
                           source = COALESCE($5, source),
                           metadata = COALESCE($6::jsonb, metadata),
                           subscribed_at = NOW()
                       WHERE id = $1""",
                    existing["id"], initial_status, confirm_token,
                    name, source, json.dumps(metadata or {}),
                )
                return {
                    "id": str(existing["id"]),
                    "status": initial_status,
                    "confirmation_token": confirm_token,
                    "already_subscribed": False,
                }
            if existing["status"] == "pending" and not auto_confirm:
                # Re-signup of a stuck pending row → rotate token so the
                # caller can re-send the confirmation email. Without this
                # the user can't recover (old token may be lost).
                await conn.execute(
                    "UPDATE newsletter_subscribers SET confirmation_token = $2, subscribed_at = NOW() WHERE id = $1",
                    existing["id"], confirm_token,
                )
                return {
                    "id": str(existing["id"]),
                    "status": "pending",
                    "confirmation_token": confirm_token,
                    "already_subscribed": False,
                }
            return {
                "id": str(existing["id"]),
                "status": existing["status"],
                "confirmation_token": None,
                "already_subscribed": already,
            }

        row = await conn.fetchrow(
            """INSERT INTO newsletter_subscribers
                 (email, name, source, user_id, company_id, metadata, status,
                  confirmation_token, confirmed_at)
               VALUES ($1, $2, $3, $4, $5, $6::jsonb, $7::varchar, $8,
                       CASE WHEN $7::text = 'active' THEN NOW() ELSE NULL END)
               RETURNING id, status""",
            email, name, source, user_id, company_id,
            json.dumps(metadata or {}), initial_status, confirm_token,
        )
        return {
            "id": str(row["id"]),
            "status": row["status"],
            "confirmation_token": confirm_token,
            "already_subscribed": False,
        }


async def confirm_subscription(token: str) -> Optional[dict]:
    """Flip a pending subscriber to active. Returns row dict or None."""
    if not token:
        return None
    async with get_connection() as conn:
        row = await conn.fetchrow(
            """UPDATE newsletter_subscribers
               SET status = 'active', confirmed_at = NOW(), confirmation_token = NULL
               WHERE confirmation_token = $1 AND status = 'pending'
               RETURNING id, email, name""",
            token,
        )
    return dict(row) if row else None


async def unsubscribe(token: str) -> str:
    """Returns 'ok' | 'already_unsubscribed' | 'invalid'."""
    sub_id = verify_unsubscribe_token(token)
    if not sub_id:
        return 'invalid'
    async with get_connection() as conn:
        result = await conn.execute(
            """UPDATE newsletter_subscribers
               SET status = 'unsubscribed', unsubscribed_at = NOW()
               WHERE id = $1 AND status IN ('active', 'pending')""",
            sub_id,
        )
        if "UPDATE 1" in result:
            return 'ok'
        exists = await conn.fetchval(
            "SELECT 1 FROM newsletter_subscribers WHERE id = $1", sub_id
        )
        return 'already_unsubscribed' if exists else 'invalid'


async def record_soft_bounce(email_or_id: str | UUID, reason: Optional[str] = None) -> dict:
    """Record a soft bounce. Returns {subscriber_id, count, suppressed}.

    Each soft bounce increments `soft_bounce_count`. At SOFT_BOUNCE_LIMIT the
    subscriber is flipped to status='bounced' so the next send loop skips
    them — same downstream effect as a hard bounce.
    """
    async with get_connection() as conn:
        if isinstance(email_or_id, UUID):
            row = await conn.fetchrow(
                """UPDATE newsletter_subscribers
                   SET soft_bounce_count = soft_bounce_count + 1,
                       bounce_reason = COALESCE($2, bounce_reason)
                   WHERE id = $1 AND status IN ('active','pending')
                   RETURNING id, soft_bounce_count""",
                email_or_id, reason,
            )
        else:
            email = str(email_or_id).strip().lower()
            row = await conn.fetchrow(
                """UPDATE newsletter_subscribers
                   SET soft_bounce_count = soft_bounce_count + 1,
                       bounce_reason = COALESCE($2, bounce_reason)
                   WHERE email = $1 AND status IN ('active','pending')
                   RETURNING id, soft_bounce_count""",
                email, reason,
            )

        if not row:
            return {"subscriber_id": None, "count": 0, "suppressed": False}

        suppressed = False
        if row["soft_bounce_count"] >= SOFT_BOUNCE_LIMIT:
            await conn.execute(
                """UPDATE newsletter_subscribers
                   SET status = 'bounced', bounced_at = NOW()
                   WHERE id = $1 AND status IN ('active','pending')""",
                row["id"],
            )
            suppressed = True

    return {"subscriber_id": str(row["id"]), "count": row["soft_bounce_count"], "suppressed": suppressed}


async def reset_soft_bounce_count(subscriber_id: UUID) -> None:
    """A confirmed open/click means the inbox accepted our last delivery.
    Reset the soft-bounce counter so transient flakiness doesn't accumulate
    indefinitely."""
    async with get_connection() as conn:
        await conn.execute(
            "UPDATE newsletter_subscribers SET soft_bounce_count = 0 WHERE id = $1 AND soft_bounce_count > 0",
            subscriber_id,
        )


async def record_open(send_id: UUID) -> Optional[UUID]:
    """Mark a send as opened (idempotent). Returns the subscriber_id so the
    caller can reset their soft-bounce counter."""
    async with get_connection() as conn:
        row = await conn.fetchrow(
            """UPDATE newsletter_sends
               SET opened_at = COALESCE(opened_at, NOW())
               WHERE id = $1
               RETURNING subscriber_id""",
            send_id,
        )
    return row["subscriber_id"] if row else None


async def record_click(send_id: UUID) -> Optional[UUID]:
    """Mark a send as clicked. Counts the FIRST click only — subsequent
    clicks update opened_at as a side effect since a click implies an open."""
    async with get_connection() as conn:
        row = await conn.fetchrow(
            """UPDATE newsletter_sends
               SET clicked_at = COALESCE(clicked_at, NOW()),
                   opened_at  = COALESCE(opened_at,  NOW())
               WHERE id = $1
               RETURNING subscriber_id""",
            send_id,
        )
    return row["subscriber_id"] if row else None


async def claim_scheduled_newsletter(newsletter_id: UUID) -> Optional[dict]:
    """Atomically claim a scheduled newsletter for sending.

    Used by the scheduled-send worker. Flips status from 'scheduled' →
    'sending' and stamps scheduled_send_started_at so a second beat that
    wakes up before the first has finished can tell the difference between
    "ready to send" and "already in flight." Returns the row or None."""
    async with get_connection() as conn:
        return await conn.fetchrow(
            """UPDATE newsletters
               SET status = 'sending',
                   scheduled_send_started_at = NOW(),
                   updated_at = NOW()
               WHERE id = $1
                 AND status = 'scheduled'
                 AND scheduled_at IS NOT NULL
                 AND scheduled_at <= NOW()
                 AND is_deleted = FALSE
               RETURNING *""",
            newsletter_id,
        )


async def list_due_scheduled_newsletters(limit: int = 25) -> list[dict]:
    """Return newsletters whose scheduled_at has passed and are still in
    'scheduled' status. The scheduler beat picks each up and calls
    claim_scheduled_newsletter for the actual atomic flip."""
    async with get_connection() as conn:
        rows = await conn.fetch(
            """SELECT id FROM newsletters
               WHERE status = 'scheduled'
                 AND scheduled_at IS NOT NULL
                 AND scheduled_at <= NOW()
                 AND is_deleted = FALSE
               ORDER BY scheduled_at ASC
               LIMIT $1""",
            limit,
        )
    return [dict(r) for r in rows]


async def mark_bounced(email_or_id: str | UUID, reason: Optional[str] = None) -> bool:
    """Bounce-webhook entry point. Hard bounce → status='bounced' and
    auto-unsubscribed. Idempotent — already-bounced or unknown emails return
    True so providers don't retry endlessly."""
    async with get_connection() as conn:
        if isinstance(email_or_id, UUID):
            existing = await conn.fetchval(
                "SELECT status FROM newsletter_subscribers WHERE id = $1",
                email_or_id,
            )
            if existing in ("bounced", "unsubscribed"):
                return True
            row = await conn.fetchrow(
                """UPDATE newsletter_subscribers
                   SET status = 'bounced', bounced_at = NOW(),
                       bounce_reason = $2, unsubscribed_at = NOW()
                   WHERE id = $1 AND status IN ('active','pending')
                   RETURNING id""",
                email_or_id, reason,
            )
        else:
            email = str(email_or_id).strip().lower()
            existing = await conn.fetchval(
                "SELECT status FROM newsletter_subscribers WHERE email = $1",
                email,
            )
            if existing in ("bounced", "unsubscribed"):
                return True
            row = await conn.fetchrow(
                """UPDATE newsletter_subscribers
                   SET status = 'bounced', bounced_at = NOW(),
                       bounce_reason = $2, unsubscribed_at = NOW()
                   WHERE email = $1 AND status IN ('active','pending')
                   RETURNING id""",
                email, reason,
            )
    return True if existing is None else bool(row)


async def delete_subscriber(subscriber_id: UUID, actor_id: Optional[UUID]) -> bool:
    """GDPR-style hard delete. Cascades to newsletter_sends via FK. Audit row
    is written in a separate connection AFTER the delete commits so a failed
    delete doesn't roll the audit row back, and a failed audit insert doesn't
    block the deletion the user requested."""
    async with get_connection() as conn:
        row = await conn.fetchrow(
            "SELECT email FROM newsletter_subscribers WHERE id = $1",
            subscriber_id,
        )
        if not row:
            return False
        await conn.execute(
            "DELETE FROM newsletter_subscribers WHERE id = $1",
            subscriber_id,
        )
        # Suppress the email so sync_platform_users() doesn't re-add it on the
        # next list fetch (platform users are re-synced from the users table).
        await conn.execute(
            """INSERT INTO newsletter_suppressions (email, reason, suppressed_by)
               VALUES (LOWER($1), 'admin_delete', $2)
               ON CONFLICT (email) DO NOTHING""",
            row["email"], actor_id,
        )
    # Best-effort audit — failure here is logged but doesn't fail the request.
    try:
        await log_admin_action(
            actor_id, "subscriber_delete", "subscriber",
            str(subscriber_id), {"email": row["email"]},
        )
    except Exception:
        logger.exception("Audit write failed after subscriber %s deleted", subscriber_id)
    return True


# ---------------------------------------------------------------------------
# Subscriber listing
# ---------------------------------------------------------------------------


async def get_subscribers(
    status: Optional[str] = None,
    source: Optional[str] = None,
    search: Optional[str] = None,
    limit: int = 50,
    offset: int = 0,
) -> tuple[list[dict], int]:
    conditions = []
    params: list = []
    idx = 1

    if status:
        conditions.append(f"status = ${idx}")
        params.append(status)
        idx += 1
    if source:
        conditions.append(f"source = ${idx}")
        params.append(source)
        idx += 1
    if search:
        conditions.append(f"(email ILIKE ${idx} OR name ILIKE ${idx})")
        params.append(f"%{search}%")
        idx += 1

    where = f"WHERE {' AND '.join(conditions)}" if conditions else ""

    async with get_connection() as conn:
        total = await conn.fetchval(f"SELECT COUNT(*) FROM newsletter_subscribers {where}", *params)
        params_with_pagination = [*params, limit, offset]
        rows = await conn.fetch(
            f"""SELECT id, email, name, source, status,
                       subscribed_at, unsubscribed_at, confirmed_at,
                       bounced_at, bounce_reason, metadata
                FROM newsletter_subscribers {where}
                ORDER BY subscribed_at DESC
                LIMIT ${idx} OFFSET ${idx + 1}""",
            *params_with_pagination,
        )
    return [dict(r) for r in rows], total


async def get_subscriber_stats() -> dict:
    async with get_connection() as conn:
        rows = await conn.fetch(
            """SELECT status, source, COUNT(*) AS cnt
               FROM newsletter_subscribers
               GROUP BY status, source"""
        )
    total = sum(r["cnt"] for r in rows)
    active = sum(r["cnt"] for r in rows if r["status"] == "active")
    pending = sum(r["cnt"] for r in rows if r["status"] == "pending")
    bounced = sum(r["cnt"] for r in rows if r["status"] == "bounced")
    by_source: dict[str, int] = {}
    for r in rows:
        by_source.setdefault(r["source"], 0)
        if r["status"] == "active":
            by_source[r["source"]] += r["cnt"]
    return {
        "total": total, "active": active, "pending": pending,
        "bounced": bounced, "by_source": by_source,
    }


async def sync_platform_users() -> int:
    """Sync active platform users into newsletter as 'active' (no double-opt-in
    needed — they've already verified email at signup). Idempotent."""
    async with get_connection() as conn:
        result = await conn.execute(
            """INSERT INTO newsletter_subscribers
                 (email, name, source, user_id, status, confirmed_at)
               SELECT u.email,
                      COALESCE(c.name, CONCAT(e.first_name, ' ', e.last_name), u.email),
                      'platform',
                      u.id,
                      'active',
                      NOW()
               FROM users u
               LEFT JOIN clients c ON c.user_id = u.id
               LEFT JOIN employees e ON e.user_id = u.id
               WHERE u.is_active = true AND u.email IS NOT NULL
                 AND NOT EXISTS (
                     SELECT 1 FROM newsletter_suppressions s
                     WHERE s.email = LOWER(u.email)
                 )
               ON CONFLICT (email) DO NOTHING"""
        )
        count = int(result.split()[-1]) if result else 0
    logger.info("Synced %d platform users to newsletter subscribers", count)
    return count


# ---------------------------------------------------------------------------
# Newsletter composition
# ---------------------------------------------------------------------------


async def create_newsletter(title: str, subject: str, created_by: UUID) -> dict:
    async with get_connection() as conn:
        row = await conn.fetchrow(
            """INSERT INTO newsletters (title, subject, created_by)
               VALUES ($1, $2, $3)
               RETURNING *""",
            title, subject, created_by,
        )
    return _normalize_row(row)


async def update_newsletter(newsletter_id: UUID, updates: dict) -> dict:
    allowed = {"title", "subject", "content_html", "curated_article_ids", "scheduled_at", "preheader", "design_json"}

    # Resolve column → value first so design_json can (a) store canonical JSON
    # and (b) re-render the content_html snapshot in one coherent pass.
    design_provided = "design_json" in updates
    design = _coerce_design(updates.get("design_json")) if design_provided else None

    cols: dict = {}
    for key, val in updates.items():
        if key not in allowed or key == "design_json":
            continue
        if key == "content_html" and val:
            val = sanitize_html(val)
        cols[key] = val
    if design_provided:
        cols["__design_json__"] = design
        if design and design.get("blocks"):
            # Snapshot for /view-in-browser + non-design consumers. Send/preview
            # re-render from design_json, so this can't drift for recipients.
            cols["content_html"] = _render_design_snapshot(design)

    if not cols:
        raise ValueError("No valid fields to update")

    sets: list[str] = []
    params: list = []
    idx = 1
    for key, val in cols.items():
        if key == "__design_json__":
            sets.append(f"design_json = ${idx}::jsonb")
            params.append(json.dumps(val) if val else None)
        else:
            sets.append(f"{key} = ${idx}")
            params.append(val)
        idx += 1
    sets.append("updated_at = NOW()")
    params.append(newsletter_id)
    async with get_connection() as conn:
        row = await conn.fetchrow(
            f"""UPDATE newsletters SET {', '.join(sets)}
                WHERE id = ${idx} AND status = 'draft' AND is_deleted = FALSE
                RETURNING *""",
            *params,
        )
    if not row:
        raise ValueError("Newsletter not found or not in draft status")
    return _normalize_row(row)


async def get_newsletter(newsletter_id: UUID) -> Optional[dict]:
    async with get_connection() as conn:
        row = await conn.fetchrow(
            "SELECT * FROM newsletters WHERE id = $1 AND is_deleted = FALSE",
            newsletter_id,
        )
        if not row:
            return None
        result = _normalize_row(row)
        stats = await conn.fetchrow(
            """SELECT
                 COUNT(*) AS total,
                 COUNT(*) FILTER (WHERE status = 'sent') AS sent,
                 COUNT(*) FILTER (WHERE opened_at IS NOT NULL) AS opened,
                 COUNT(*) FILTER (WHERE clicked_at IS NOT NULL) AS clicked,
                 COUNT(*) FILTER (WHERE status = 'bounced') AS bounced
               FROM newsletter_sends WHERE newsletter_id = $1""",
            newsletter_id,
        )
        result["send_stats"] = dict(stats) if stats else {}
    return result


async def list_newsletters(limit: int = 20, offset: int = 0) -> list[dict]:
    async with get_connection() as conn:
        rows = await conn.fetch(
            """SELECT n.*,
                      (SELECT COUNT(*) FROM newsletter_sends WHERE newsletter_id = n.id) AS total_sends,
                      (SELECT COUNT(*) FROM newsletter_sends WHERE newsletter_id = n.id AND opened_at IS NOT NULL) AS total_opened
               FROM newsletters n
               WHERE n.is_deleted = FALSE
               ORDER BY n.created_at DESC
               LIMIT $1 OFFSET $2""",
            limit, offset,
        )
    return [_normalize_row(r) for r in rows]


async def soft_delete_newsletter(newsletter_id: UUID, actor_id: UUID) -> bool:
    """Soft-delete: marks deleted + writes audit row. Refuses already-sent."""
    async with get_connection() as conn:
        async with conn.transaction():
            row = await conn.fetchrow(
                """UPDATE newsletters
                   SET is_deleted = TRUE, deleted_at = NOW(), deleted_by = $2
                   WHERE id = $1 AND is_deleted = FALSE AND status = 'draft'
                   RETURNING id, title""",
                newsletter_id, actor_id,
            )
            if not row:
                return False
            await conn.execute(
                """INSERT INTO newsletter_admin_audit
                     (actor_id, action, target_type, target_id, metadata)
                   VALUES ($1, 'newsletter_soft_delete', 'newsletter', $2, $3::jsonb)""",
                actor_id, str(newsletter_id), json.dumps({"title": row["title"]}),
            )
    return True


# ---------------------------------------------------------------------------
# Sending
# ---------------------------------------------------------------------------


async def send_newsletter(newsletter_id: UUID, actor_id: Optional[UUID] = None) -> dict:
    """Send a newsletter to all active subscribers. Idempotent against double-send.

    Recovery for stuck 'sending' state: any newsletter stuck in 'sending' for
    >1 hour (background task crashed / process restarted) is treated as
    eligible for a new send attempt. Without this, a one-time crash strands
    the newsletter forever.
    """
    async with get_connection() as conn:
        async with conn.transaction():
            # Atomic status flip — refuses double-send AND auto-recovers from
            # a stale 'sending' lock older than 1 hour.
            nl = await conn.fetchrow(
                """UPDATE newsletters
                   SET status = 'sending', updated_at = NOW()
                   WHERE id = $1
                     AND is_deleted = FALSE
                     AND (
                       status IN ('draft', 'scheduled')
                       OR (status = 'sending' AND updated_at < NOW() - INTERVAL '1 hour')
                     )
                   RETURNING *""",
                newsletter_id,
            )
            if not nl:
                raise ValueError("Newsletter not found, already sent, or in flight")

            subscribers = await conn.fetch(
                "SELECT id, email, name FROM newsletter_subscribers WHERE status = 'active'"
            )

            for sub in subscribers:
                await conn.execute(
                    """INSERT INTO newsletter_sends (newsletter_id, subscriber_id)
                       VALUES ($1, $2)
                       ON CONFLICT (newsletter_id, subscriber_id) DO NOTHING""",
                    newsletter_id, sub["id"],
                )

            await conn.execute(
                """INSERT INTO newsletter_admin_audit
                     (actor_id, action, target_type, target_id, metadata)
                   VALUES ($1, 'newsletter_send', 'newsletter', $2, $3::jsonb)""",
                actor_id, str(newsletter_id),
                json.dumps({"recipient_count": len(subscribers)}),
            )

    asyncio.create_task(_send_emails(newsletter_id, dict(nl), list(subscribers)))
    return {"queued": len(subscribers), "status": "sending"}


def render_preview(
    title: str,
    subject: str,
    preheader: str,
    content_html: str,
    *,
    theme: Literal["dark", "light"] = "dark",
    design_json: Optional[dict] = None,
) -> str:
    """Render a draft body through the same pipeline used at send time.

    Used by the admin compose preview pane so the iframe shows what recipients
    actually see — branded chrome, block layout, theme palette, poster
    fallback, footer. No tracking pixel is injected (send_id=None). When
    `design_json` is provided it drives the render (block builder); otherwise
    the freeform `content_html` is used.
    """
    settings = get_settings()
    base_url = (settings.app_base_url or "https://hey-matcha.com").rstrip("/")
    fake_unsub = f"{base_url}/api/newsletter/unsubscribe?token=preview"
    # Sanitize on read just like the write path does, so the preview can't
    # be spoofed into rendering arbitrary HTML if the input is bypassed.
    sanitized = sanitize_html(content_html or "")
    return _render_email(
        {
            "title": title or "(untitled)",
            "subject": subject or "",
            "preheader": preheader or "",
            "content_html": sanitized,
            "design_json": design_json,
        },
        {"name": "there"},
        fake_unsub,
        theme=theme,
    )


async def send_test_email(newsletter_id: UUID, to_email: str, to_name: Optional[str] = None) -> bool:
    """Send a single test render to an arbitrary address. Doesn't touch
    newsletter_sends or newsletter status."""
    from .email import get_email_service
    async with get_connection() as conn:
        nl = await conn.fetchrow("SELECT * FROM newsletters WHERE id = $1", newsletter_id)
    if not nl:
        raise ValueError("Newsletter not found")
    settings = get_settings()
    base_url = (settings.app_base_url or "https://hey-matcha.com").rstrip("/")
    fake_unsub = f"{base_url}/api/newsletter/unsubscribe?token=preview"
    html = _render_email(dict(nl), {"name": to_name or "there"}, fake_unsub)
    return await get_email_service().send_email(
        to_email=to_email,
        to_name=to_name,
        subject=f"[TEST] {nl['subject']}",
        html_content=html,
    )


async def _send_emails(newsletter_id: UUID, nl: dict, subscribers: list[dict]) -> None:
    from .email import get_email_service

    email_svc = get_email_service()
    settings = get_settings()
    base_url = (settings.app_base_url or "https://hey-matcha.com").rstrip("/")
    sent_count = 0
    failed_count = 0

    # Resolve send_id per subscriber up-front so the rendered HTML can carry
    # a per-recipient open pixel + click-rewrite token. The earlier design
    # did one bulk INSERT then a bulk UPDATE — that left no way to address
    # a specific send row for tracking.
    send_id_by_subscriber: dict[UUID, UUID] = {}
    async with get_connection() as conn:
        for sub in subscribers:
            row = await conn.fetchrow(
                """INSERT INTO newsletter_sends (newsletter_id, subscriber_id)
                   VALUES ($1, $2)
                   ON CONFLICT (newsletter_id, subscriber_id) DO UPDATE
                       SET subscriber_id = EXCLUDED.subscriber_id
                   RETURNING id""",
                newsletter_id, sub["id"],
            )
            if row:
                send_id_by_subscriber[sub["id"]] = row["id"]

    for i in range(0, len(subscribers), BATCH_SIZE):
        batch = subscribers[i:i + BATCH_SIZE]
        sent_ids: list[UUID] = []
        failed_ids: list[UUID] = []

        for sub in batch:
            send_id = send_id_by_subscriber.get(sub["id"])
            unsub_token = generate_unsubscribe_token(sub["id"])
            unsub_url = f"{base_url}/api/newsletter/unsubscribe?token={unsub_token}"
            html = _render_email(nl, sub, unsub_url, base_url=base_url, send_id=send_id)

            # RFC 8058 List-Unsubscribe + List-Unsubscribe-Post enable Gmail's
            # one-click unsubscribe button — required for CAN-SPAM and to keep
            # the sender out of the "report spam" funnel.
            headers = {
                "List-Unsubscribe": f"<{unsub_url}>",
                "List-Unsubscribe-Post": "List-Unsubscribe=One-Click",
            }

            try:
                ok = await email_svc.send_email(
                    to_email=sub["email"],
                    to_name=sub.get("name"),
                    subject=nl["subject"],
                    html_content=html,
                    extra_headers=headers,
                )
                if ok:
                    sent_ids.append(sub["id"])
                    sent_count += 1
                else:
                    failed_ids.append(sub["id"])
                    failed_count += 1
            except Exception as e:
                logger.warning("Failed to send newsletter to %s: %s", sub["email"], e)
                failed_ids.append(sub["id"])
                failed_count += 1

        try:
            async with get_connection() as conn:
                if sent_ids:
                    await conn.execute(
                        "UPDATE newsletter_sends SET status = 'sent', sent_at = NOW() "
                        "WHERE newsletter_id = $1 AND subscriber_id = ANY($2::uuid[])",
                        newsletter_id, sent_ids,
                    )
                if failed_ids:
                    await conn.execute(
                        "UPDATE newsletter_sends SET status = 'failed' "
                        "WHERE newsletter_id = $1 AND subscriber_id = ANY($2::uuid[])",
                        newsletter_id, failed_ids,
                    )
        except Exception as e:
            logger.error("Failed to update send status: %s", e)

        if i + BATCH_SIZE < len(subscribers):
            await asyncio.sleep(BATCH_DELAY)

    try:
        async with get_connection() as conn:
            await conn.execute(
                "UPDATE newsletters SET status = 'sent', sent_at = NOW() WHERE id = $1",
                newsletter_id,
            )
    except Exception as e:
        logger.error("Failed to mark newsletter as sent: %s", e)

    logger.info(
        "Newsletter %s: sent=%d failed=%d total=%d",
        newsletter_id, sent_count, failed_count, len(subscribers),
    )


# A href value is "external" (and therefore eligible for click rewriting) if
# it points to a real http(s) URL. mailto:/tel:/anchor links are skipped.
_HREF_RE = re.compile(r'href=(["\'])(https?://[^"\']+)\1', re.IGNORECASE)


# Email-safe theme palettes live in email_blocks.PALETTES (aliased above as
# EMAIL_THEMES for the legacy freeform + video-poster-fallback callers). Gmail
# and Outlook strip <video> and many CSS rules, so wrapper colors are inlined.


# Match an opening <video> tag (with optional attrs and trailing content
# until the closing </video>). Captures src + poster attributes if present.
# Tolerates the <source> child pattern Tiptap may emit later — we just
# extract the first src or poster and ignore the rest.
_VIDEO_TAG_RE = re.compile(
    r"<video\b([^>]*)>(.*?)</video>",
    re.IGNORECASE | re.DOTALL,
)
_ATTR_RE = re.compile(r"""(\w+)\s*=\s*(?:"([^"]*)"|'([^']*)')""")


def _video_to_poster_fallback(html: str, theme: dict) -> str:
    """Replace every <video> tag with a Gmail/Outlook-safe poster card.

    Most email clients silently drop <video>. Without this transform, video
    newsletters look empty in 80%+ of inboxes. We render a clickable poster
    image (or a generic "Watch video" card if no poster attr) that links to
    the underlying video URL — recipients always see *something* clickable.
    """
    if not html or "<video" not in html.lower():
        return html

    def _replace(match: re.Match) -> str:
        attrs_str = match.group(1) or ""
        inner = match.group(2) or ""
        attrs = {k.lower(): (v1 or v2) for k, v1, v2 in _ATTR_RE.findall(attrs_str)}

        src = attrs.get("src")
        poster = attrs.get("poster")
        # Tiptap / hand-written video tags may use a child <source src="...">
        if not src:
            inner_attrs = {k.lower(): (v1 or v2) for k, v1, v2 in _ATTR_RE.findall(inner)}
            src = inner_attrs.get("src")
        if not src:
            return ""  # nothing to link to — drop the tag entirely

        accent = theme["accent"]
        muted = theme["muted"]
        wrapper_fg = theme["wrapper_fg"]

        if poster:
            inner_card = (
                f'<img src="{poster}" alt="Watch video" '
                f'style="display:block;width:100%;max-width:560px;height:auto;border-radius:6px;margin:0 auto;" />'
                f'<div style="text-align:center;margin-top:8px;color:{accent};font-size:14px;font-weight:600;">'
                f'&#9654; Watch video</div>'
            )
        else:
            inner_card = (
                f'<div style="display:block;width:100%;max-width:560px;margin:0 auto;'
                f'padding:48px 16px;text-align:center;background:#0a0a0a;border-radius:6px;'
                f'border:1px solid {muted};">'
                f'<div style="font-size:32px;color:{accent};line-height:1;">&#9654;</div>'
                f'<div style="margin-top:8px;color:{wrapper_fg};font-size:14px;font-weight:600;">Watch video</div>'
                f'<div style="margin-top:4px;color:{muted};font-size:11px;">Click to play</div>'
                f'</div>'
            )

        return (
            f'<a href="{src}" target="_blank" rel="noopener" '
            f'style="text-decoration:none;display:block;margin:16px 0;">'
            f'{inner_card}'
            f'</a>'
        )

    return _VIDEO_TAG_RE.sub(_replace, html)


def _rewrite_links_for_tracking(
    html: str,
    *,
    base_url: str,
    send_id: UUID,
    skip_urls: set[str],
) -> str:
    """Wrap external <a href="..."> values with the click-tracking endpoint.

    Skips the unsubscribe URL (RFC 8058 requires direct unsubscribe) and any
    other skip_urls passed in.
    """
    if not html or not send_id:
        return html

    def _replace(match: re.Match) -> str:
        quote_char = match.group(1)
        # bleach normalizes attribute values — `&` in the original URL ends
        # up as `&amp;` in the HTML attribute. Decode entities back to the
        # raw URL before forwarding so the click endpoint redirects to the
        # actual target rather than a literal `&amp;`-bearing string.
        raw_target = html_lib.unescape(match.group(2))
        if raw_target in skip_urls or raw_target.startswith(f"{base_url}/api/newsletter/track/"):
            return match.group(0)
        wrapped = f"{base_url}/api/newsletter/track/click/{send_id}?to={quote(raw_target, safe='')}"
        return f"href={quote_char}{wrapped}{quote_char}"

    return _HREF_RE.sub(_replace, html)


def _coerce_design(value) -> Optional[dict]:
    """Normalize a design_json value read from the DB (asyncpg returns JSONB as
    a str) or supplied by a request (already a dict) into a dict or None."""
    if not value:
        return None
    if isinstance(value, dict):
        return value
    if isinstance(value, str):
        try:
            parsed = json.loads(value)
        except (json.JSONDecodeError, ValueError):
            return None
        return parsed if isinstance(parsed, dict) else None
    return None


def _normalize_row(row) -> dict:
    """dict() a DB row and parse its design_json (asyncpg returns JSONB as a
    str) so the API hands the frontend a real object, not a JSON string."""
    d = dict(row)
    if isinstance(d.get("design_json"), str):
        d["design_json"] = _coerce_design(d["design_json"])
    return d


def _resolve_email_content(newsletter: dict, palette: dict, *, base_url: str) -> tuple[str, bool]:
    """Return ``(content_html, is_design)`` — rendered blocks when a design is
    present, else the freeform content_html (both already sanitized)."""
    design = _coerce_design(newsletter.get("design_json"))
    if design and design.get("blocks"):
        return render_blocks(design, palette, base_url=base_url, sanitize=sanitize_html), True
    return (newsletter.get("content_html") or ""), False


def _render_design_snapshot(design: Optional[dict]) -> str:
    """Render a design's blocks to a standalone content-HTML snapshot (no
    chrome), stored in content_html so /view-in-browser and any non-design
    consumer have something to show. Uses the design's own theme preset."""
    theme_cfg = (design or {}).get("theme") or {}
    theme_key = theme_cfg.get("preset") if theme_cfg.get("preset") in EMAIL_THEMES else "light"
    palette = resolve_palette(theme_key, theme_cfg)
    settings = get_settings()
    base_url = (settings.app_base_url or "https://hey-matcha.com").rstrip("/")
    return render_blocks(design, palette, base_url=base_url, sanitize=sanitize_html)


def _render_email(
    newsletter: dict,
    subscriber: dict,
    unsubscribe_url: str,
    *,
    base_url: str = "",
    send_id: Optional[UUID] = None,
    theme: Optional[Literal["dark", "light"]] = None,
) -> str:
    """Render a full, email-client-safe HTML document with branded chrome,
    block/freeform content, click + open tracking, and a CAN-SPAM footer.

    The output is a complete ``<!DOCTYPE html>`` document (the email service
    attaches ``html_content`` verbatim). Layout is table-based with inline
    styles; an MSO ``OfficeDocumentSettings`` block + conditional resets keep
    Outlook honest.

    `theme` is the base palette key; a design's ``theme`` object may override
    brand colour / background / branding. `send_id` (a newsletter_sends id)
    turns on the open pixel + click-rewrite; omit it for previews/tests.
    """
    settings = get_settings()
    if not base_url:
        base_url = (settings.app_base_url or "https://hey-matcha.com").rstrip("/")

    design = _coerce_design(newsletter.get("design_json"))
    theme_cfg = (design or {}).get("theme") or {}
    # Explicit theme (preview toggle) wins; otherwise honor the design's own
    # preset; freeform newsletters fall back to the legacy dark look.
    if theme in EMAIL_THEMES:
        theme_key = theme
    elif theme_cfg.get("preset") in EMAIL_THEMES:
        theme_key = theme_cfg["preset"]
    else:
        theme_key = "dark"
    palette = resolve_palette(theme_key, theme_cfg)

    content, is_design = _resolve_email_content(newsletter, palette, base_url=base_url)

    # Video fallback BEFORE tracking rewrite so the new <a href> can be
    # click-tracked alongside any other external links. (Block designs already
    # render video as a poster card; this only bites freeform content_html.)
    content = _video_to_poster_fallback(content, palette)

    if send_id:
        content = _rewrite_links_for_tracking(
            content, base_url=base_url, send_id=send_id, skip_urls={unsubscribe_url},
        )

    mailing_address = (settings.newsletter_mailing_address or "").strip()
    address_html = mailing_address.replace("\n", "<br>") if mailing_address else ""

    preheader = (newsletter.get("preheader") or "").strip()
    preheader_html = ""
    if preheader:
        # Hidden inbox-preview snippet + whitespace hack that stops the client
        # from pulling body text into the preview line after the preheader.
        preheader_html = (
            f'<div style="display:none;max-height:0px;overflow:hidden;mso-hide:all;'
            f'visibility:hidden;opacity:0;color:transparent;height:0;width:0;">'
            f'{html_lib.escape(preheader)}'
            f'{"&#8203;&nbsp;" * 60}</div>'
        )

    pixel_html = ""
    if send_id:
        pixel_url = f"{base_url}/api/newsletter/track/open/{send_id}.gif"
        pixel_html = f'<img src="{pixel_url}" width="1" height="1" alt="" style="display:none;border:0;height:1px;width:1px;" />'

    # Branding — logo image if provided, else a brand-colour wordmark.
    brand_name = html_lib.escape(str(theme_cfg.get("brandName") or "Matcha"))
    logo_url = email_blocks._safe_image(theme_cfg.get("logoUrl"))
    if logo_url:
        brand_html = f'<img src="{html_lib.escape(logo_url)}" alt="{brand_name}" height="30" style="display:inline-block;height:30px;width:auto;border:0;" />'
    else:
        brand_html = (
            f'<span style="font-size:20px;font-weight:800;letter-spacing:-0.3px;'
            f'color:{palette["brand"]};">{brand_name}</span>'
        )

    # For freeform content, keep the title as an <h1> above the body. Block
    # designs carry their own headings (hero etc.), so the title is omitted.
    title_html = ""
    if not is_design and newsletter.get("title"):
        title_html = (
            f'<h1 style="margin:0 0 18px 0;font-size:24px;line-height:1.3;font-weight:800;'
            f'color:{palette["heading"]};letter-spacing:-0.3px;">{html_lib.escape(str(newsletter["title"]))}</h1>'
        )

    return f"""<!DOCTYPE html PUBLIC "-//W3C//DTD XHTML 1.0 Transitional//EN" "http://www.w3.org/TR/xhtml1/DTD/xhtml1-transitional.dtd">
<html xmlns="http://www.w3.org/1999/xhtml" xmlns:v="urn:schemas-microsoft-com:vml" xmlns:o="urn:schemas-microsoft-com:office:office" lang="en">
<head>
<meta charset="utf-8" />
<meta name="viewport" content="width=device-width, initial-scale=1" />
<meta http-equiv="X-UA-Compatible" content="IE=edge" />
<meta name="x-apple-disable-message-reformatting" />
<meta name="color-scheme" content="light dark" />
<meta name="supported-color-schemes" content="light dark" />
<title>{html_lib.escape(str(newsletter.get('subject') or newsletter.get('title') or 'Newsletter'))}</title>
<!--[if mso]><noscript><xml><o:OfficeDocumentSettings><o:PixelsPerInch>96</o:PixelsPerInch></o:OfficeDocumentSettings></xml></noscript><![endif]-->
<style>
  @import url('https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700;800&display=swap');
  html,body{{margin:0!important;padding:0!important;width:100%!important;-webkit-text-size-adjust:100%;-ms-text-size-adjust:100%;}}
  body,table,td{{-webkit-text-size-adjust:100%;-ms-text-size-adjust:100%;}}
  table,td{{mso-table-lspace:0pt;mso-table-rspace:0pt;border-collapse:collapse;}}
  img{{-ms-interpolation-mode:bicubic;border:0;height:auto;line-height:100%;outline:none;text-decoration:none;}}
  a{{color:{palette['link']};}}
  a[x-apple-data-detectors]{{color:inherit!important;text-decoration:none!important;}}
  @media only screen and (max-width:620px){{
    .nl-container{{width:100%!important;border-radius:0!important;}}
    .nl-pad{{padding-left:20px!important;padding-right:20px!important;}}
  }}
</style>
</head>
<body style="margin:0;padding:0;background-color:{palette['page_bg']};color:{palette['text']};font-family:{email_blocks.FONT_STACK};">
{preheader_html}
<table role="presentation" border="0" cellpadding="0" cellspacing="0" width="100%" style="background-color:{palette['page_bg']};">
  <tr><td align="center" style="padding:24px 12px;">
    <!--[if mso]><table role="presentation" border="0" cellpadding="0" cellspacing="0" width="600"><tr><td><![endif]-->
    <table role="presentation" border="0" cellpadding="0" cellspacing="0" width="600" class="nl-container" style="width:600px;max-width:600px;background-color:{palette['card_bg']};border:1px solid {palette['border']};border-radius:14px;overflow:hidden;">
      <tr><td class="nl-pad" style="padding:26px 32px 8px 32px;text-align:center;">{brand_html}</td></tr>
      <tr><td class="nl-pad" style="padding:14px 32px 8px 32px;font-family:{email_blocks.FONT_STACK};">
        {title_html}
        {content}
      </td></tr>
      <tr><td class="nl-pad" style="padding:8px 32px 28px 32px;">
        <div style="height:1px;line-height:1px;font-size:1px;background:{palette['border']};margin:16px 0 18px 0;">&nbsp;</div>
        <div style="text-align:center;font-size:12px;line-height:1.7;color:{palette['muted']};">
          <p style="margin:0 0 6px 0;">You received this because you subscribed to {brand_name} updates.</p>
          <p style="margin:0 0 10px 0;"><a href="{unsubscribe_url}" style="color:{palette['link']};text-decoration:underline;">Unsubscribe</a></p>
          {f'<p style="margin:0;color:{palette["muted"]};">{address_html}</p>' if address_html else ''}
        </div>
      </td></tr>
    </table>
    <!--[if mso]></td></tr></table><![endif]-->
  </td></tr>
</table>
{pixel_html}
</body>
</html>"""


# ---------------------------------------------------------------------------
# Admin audit helper
# ---------------------------------------------------------------------------


# ---------------------------------------------------------------------------
# Tags + segmentation (P1)
# ---------------------------------------------------------------------------


async def list_tags() -> list[dict]:
    async with get_connection() as conn:
        rows = await conn.fetch(
            """SELECT t.id, t.slug, t.label, t.description, t.created_at,
                      (SELECT COUNT(*) FROM newsletter_subscriber_tags st WHERE st.tag_id = t.id) AS subscriber_count
                 FROM newsletter_tags t
                ORDER BY t.label"""
        )
    return [dict(r) for r in rows]


async def create_tag(slug: str, label: str, description: Optional[str] = None) -> dict:
    slug = slug.strip().lower()
    if not slug or " " in slug:
        raise ValueError("Slug must be non-empty and whitespace-free")
    async with get_connection() as conn:
        row = await conn.fetchrow(
            """INSERT INTO newsletter_tags (slug, label, description)
               VALUES ($1, $2, $3)
               ON CONFLICT (slug) DO UPDATE SET label = EXCLUDED.label, description = EXCLUDED.description
               RETURNING *""",
            slug, label.strip(), description,
        )
    return dict(row)


async def delete_tag(tag_id: UUID) -> bool:
    async with get_connection() as conn:
        result = await conn.execute("DELETE FROM newsletter_tags WHERE id = $1", tag_id)
    return "DELETE 1" in result


async def get_tag_subscribers(tag_id: UUID) -> list[dict]:
    async with get_connection() as conn:
        rows = await conn.fetch(
            """SELECT s.id, s.email, s.name, s.status
                 FROM newsletter_subscribers s
                 JOIN newsletter_subscriber_tags st ON st.subscriber_id = s.id
                WHERE st.tag_id = $1
                ORDER BY s.email""",
            tag_id,
        )
    return [dict(r) for r in rows]


async def attach_tags_to_subscriber(subscriber_id: UUID, tag_slugs: list[str]) -> None:
    """Attach by slug. Unknown slugs are silently ignored — auto-tagging
    paths shouldn't 500 if a slug got renamed."""
    if not tag_slugs:
        return
    async with get_connection() as conn:
        await conn.execute(
            """INSERT INTO newsletter_subscriber_tags (subscriber_id, tag_id)
               SELECT $1, t.id FROM newsletter_tags t
                WHERE t.slug = ANY($2::text[])
               ON CONFLICT DO NOTHING""",
            subscriber_id, tag_slugs,
        )


async def replace_subscriber_tags(subscriber_id: UUID, tag_ids: list[UUID]) -> None:
    """Replace the entire tag set on a subscriber. Used by admin tag editor."""
    async with get_connection() as conn:
        async with conn.transaction():
            await conn.execute(
                "DELETE FROM newsletter_subscriber_tags WHERE subscriber_id = $1",
                subscriber_id,
            )
            if tag_ids:
                await conn.executemany(
                    "INSERT INTO newsletter_subscriber_tags (subscriber_id, tag_id) VALUES ($1, $2)",
                    [(subscriber_id, tag_id) for tag_id in tag_ids],
                )


async def get_subscriber_tags(subscriber_id: UUID) -> list[dict]:
    async with get_connection() as conn:
        rows = await conn.fetch(
            """SELECT t.id, t.slug, t.label
                 FROM newsletter_tags t
                 JOIN newsletter_subscriber_tags st ON st.tag_id = t.id
                WHERE st.subscriber_id = $1
                ORDER BY t.label""",
            subscriber_id,
        )
    return [dict(r) for r in rows]


async def derive_signup_tags(source: str, user_id: Optional[UUID]) -> list[str]:
    """Auto-tag derivation. Returns a list of slugs to attach to a new
    subscriber based on (a) the marketing surface that captured them and
    (b) the tier of the company they belong to (if any)."""
    slugs: list[str] = []

    # Source-bucket tags. Anything starting with `blog_` collapses to
    # 'blog'; calculator pages all collapse to 'calculators'; etc.
    src = (source or "").lower()
    if src.startswith("blog"):
        slugs.append("blog")
    elif src.startswith("calculator") or src.startswith("calc_"):
        slugs.append("calculators")
    elif src.startswith("jd_") or src.startswith("job_desc") or src == "job_descriptions":
        slugs.append("job-descriptions")
    elif src == "glossary":
        slugs.append("glossary")
    elif src.startswith("resources"):
        slugs.append("resources-hub")
    elif src.startswith("footer"):
        slugs.append("footer")

    # Tier tag — only resolvable if the subscriber is logged in.
    if user_id is not None:
        async with get_connection() as conn:
            row = await conn.fetchrow(
                """SELECT c.signup_source, c.is_personal
                     FROM clients cl
                     JOIN companies c ON c.id = cl.company_id
                    WHERE cl.user_id = $1
                    LIMIT 1""",
                user_id,
            )
        if row:
            if row["is_personal"]:
                slugs.append("tier-personal")
            elif row["signup_source"] == "resources_free":
                slugs.append("tier-free")
            elif row["signup_source"] == "matcha_lite":
                slugs.append("tier-lite")
            elif row["signup_source"] == "matcha_x":
                slugs.append("tier-x")
            else:
                slugs.append("tier-platform")

    return slugs


async def send_newsletter_to_segment(
    newsletter_id: UUID,
    tag_slugs: Optional[list[str]] = None,
    actor_id: Optional[UUID] = None,
) -> dict:
    """Variant of send_newsletter that filters subscribers by tag.

    `tag_slugs=None` or `[]` sends to everyone active (full list).
    `tag_slugs=['tier-lite']` only sends to subscribers tagged tier-lite.
    """
    async with get_connection() as conn:
        async with conn.transaction():
            nl = await conn.fetchrow(
                """UPDATE newsletters
                   SET status = 'sending', updated_at = NOW()
                   WHERE id = $1
                     AND is_deleted = FALSE
                     AND (
                       status IN ('draft', 'scheduled')
                       OR (status = 'sending' AND updated_at < NOW() - INTERVAL '1 hour')
                     )
                   RETURNING *""",
                newsletter_id,
            )
            if not nl:
                raise ValueError("Newsletter not found, already sent, or in flight")

            if tag_slugs:
                subscribers = await conn.fetch(
                    """SELECT DISTINCT s.id, s.email, s.name
                         FROM newsletter_subscribers s
                         JOIN newsletter_subscriber_tags st ON st.subscriber_id = s.id
                         JOIN newsletter_tags t ON t.id = st.tag_id
                        WHERE s.status = 'active' AND t.slug = ANY($1::text[])""",
                    tag_slugs,
                )
            else:
                subscribers = await conn.fetch(
                    "SELECT id, email, name FROM newsletter_subscribers WHERE status = 'active'"
                )

            for sub in subscribers:
                await conn.execute(
                    """INSERT INTO newsletter_sends (newsletter_id, subscriber_id)
                       VALUES ($1, $2)
                       ON CONFLICT (newsletter_id, subscriber_id) DO NOTHING""",
                    newsletter_id, sub["id"],
                )

            await conn.execute(
                """INSERT INTO newsletter_admin_audit
                     (actor_id, action, target_type, target_id, metadata)
                   VALUES ($1, 'newsletter_send', 'newsletter', $2, $3::jsonb)""",
                actor_id, str(newsletter_id),
                json.dumps({
                    "recipient_count": len(subscribers),
                    "segment_tags": tag_slugs or [],
                }),
            )

    asyncio.create_task(_send_emails(newsletter_id, dict(nl), list(subscribers)))
    return {"queued": len(subscribers), "status": "sending", "segment_tags": tag_slugs or []}


# ---------------------------------------------------------------------------
# Saved templates (P2)
# ---------------------------------------------------------------------------


async def list_templates() -> list[dict]:
    async with get_connection() as conn:
        rows = await conn.fetch(
            "SELECT id, name, description, preheader, design_json, created_at, updated_at "
            "FROM newsletter_templates ORDER BY name"
        )
    return [_normalize_row(r) for r in rows]


async def create_template(
    name: str,
    description: Optional[str],
    content_html: Optional[str],
    preheader: Optional[str],
    created_by: Optional[UUID],
    design_json: Optional[dict] = None,
) -> dict:
    design = _coerce_design(design_json)
    # A block design renders its own content_html snapshot; otherwise the
    # provided freeform HTML is sanitized as before.
    if design and design.get("blocks"):
        content = _render_design_snapshot(design)
    else:
        content = sanitize_html(content_html or "")
    async with get_connection() as conn:
        row = await conn.fetchrow(
            """INSERT INTO newsletter_templates (name, description, content_html, preheader, design_json, created_by)
               VALUES ($1, $2, $3, $4, $5::jsonb, $6)
               RETURNING *""",
            name.strip(), description, content, preheader,
            json.dumps(design) if design else None, created_by,
        )
    return _normalize_row(row)


async def update_template(template_id: UUID, updates: dict) -> Optional[dict]:
    allowed = {"name", "description", "content_html", "preheader", "design_json"}
    design_provided = "design_json" in updates
    design = _coerce_design(updates.get("design_json")) if design_provided else None

    cols: dict = {}
    for k, v in updates.items():
        if k not in allowed or k == "design_json":
            continue
        if k == "content_html" and v:
            v = sanitize_html(v)
        cols[k] = v
    if design_provided:
        cols["__design_json__"] = design
        if design and design.get("blocks"):
            cols["content_html"] = _render_design_snapshot(design)
    if not cols:
        return None

    sets: list[str] = []
    params: list = []
    idx = 1
    for k, v in cols.items():
        if k == "__design_json__":
            sets.append(f"design_json = ${idx}::jsonb")
            params.append(json.dumps(v) if v else None)
        else:
            sets.append(f"{k} = ${idx}")
            params.append(v)
        idx += 1
    sets.append("updated_at = NOW()")
    params.append(template_id)
    async with get_connection() as conn:
        row = await conn.fetchrow(
            f"UPDATE newsletter_templates SET {', '.join(sets)} WHERE id = ${idx} RETURNING *",
            *params,
        )
    return _normalize_row(row) if row else None


async def get_template(template_id: UUID) -> Optional[dict]:
    async with get_connection() as conn:
        row = await conn.fetchrow(
            "SELECT * FROM newsletter_templates WHERE id = $1",
            template_id,
        )
    return _normalize_row(row) if row else None


async def delete_template(template_id: UUID) -> bool:
    async with get_connection() as conn:
        result = await conn.execute("DELETE FROM newsletter_templates WHERE id = $1", template_id)
    return "DELETE 1" in result


# ---------------------------------------------------------------------------
# Idea scratchpad + template generator
#
# The scratchpad is a quick-capture surface for newsletter concepts. An idea
# holds a title, free-form notes, and (optionally) a captured image. The
# "Create Newsletter" action converts an idea into a structured newsletter
# draft; the generated template ENFORCES at least one visual — a conversion
# with no media is refused so every produced newsletter includes an image.
# ---------------------------------------------------------------------------


async def list_ideas() -> list[dict]:
    async with get_connection() as conn:
        rows = await conn.fetch(
            """SELECT id, title, notes, media_url, status, newsletter_id,
                      created_at, updated_at
               FROM newsletter_ideas
               ORDER BY created_at DESC"""
        )
    return [dict(r) for r in rows]


async def create_idea(
    title: str,
    notes: Optional[str],
    media_url: Optional[str],
    created_by: Optional[UUID],
) -> dict:
    async with get_connection() as conn:
        row = await conn.fetchrow(
            """INSERT INTO newsletter_ideas (title, notes, media_url, created_by)
               VALUES ($1, $2, $3, $4)
               RETURNING id, title, notes, media_url, status, newsletter_id,
                         created_at, updated_at""",
            title.strip(), notes, media_url, created_by,
        )
    return dict(row)


async def update_idea(idea_id: UUID, updates: dict) -> Optional[dict]:
    allowed = {"title", "notes", "media_url"}
    sets = []
    params: list = []
    idx = 1
    for k, v in updates.items():
        if k not in allowed:
            continue
        if k == "title" and isinstance(v, str):
            v = v.strip()
        sets.append(f"{k} = ${idx}")
        params.append(v)
        idx += 1
    if not sets:
        return None
    sets.append("updated_at = NOW()")
    params.append(idea_id)
    async with get_connection() as conn:
        row = await conn.fetchrow(
            f"""UPDATE newsletter_ideas SET {', '.join(sets)}
                WHERE id = ${idx}
                RETURNING id, title, notes, media_url, status, newsletter_id,
                          created_at, updated_at""",
            *params,
        )
    return dict(row) if row else None


async def delete_idea(idea_id: UUID) -> bool:
    async with get_connection() as conn:
        result = await conn.execute("DELETE FROM newsletter_ideas WHERE id = $1", idea_id)
    return "DELETE 1" in result


def _is_video_media(media_url: str) -> bool:
    return media_url.lower().rsplit("?", 1)[0].endswith((".mp4", ".mov", ".webm"))


def build_idea_newsletter_html(
    title: str,
    notes: Optional[str],
    media_url: str,
    media_alt: Optional[str] = None,
) -> str:
    """Assemble a structured newsletter body from a scratchpad idea.

    The template has a fixed skeleton — a **mandatory** hero visual, the idea
    title as an <h1>, and the notes rendered as paragraphs. The media block is
    non-optional: this builder is only reached once a media_url is supplied, so
    the produced HTML always contains at least one <img>/<video>. The result is
    passed through the same `sanitize_html` allowlist as any other body.
    """
    safe_alt = html_lib.escape(media_alt or title or "Newsletter image")
    if _is_video_media(media_url):
        media_block = (
            f'<figure><video controls src="{html_lib.escape(media_url)}" '
            f'width="100%"></video>'
            f'<figcaption>{safe_alt}</figcaption></figure>'
        )
    else:
        media_block = (
            f'<figure><img src="{html_lib.escape(media_url)}" alt="{safe_alt}" '
            f'width="100%" /></figure>'
        )

    heading = f"<h1>{html_lib.escape(title.strip() or 'Untitled newsletter')}</h1>"

    body_parts: list[str] = []
    for para in (notes or "").split("\n\n"):
        para = para.strip()
        if not para:
            continue
        # Preserve single line breaks inside a paragraph.
        para_html = "<br />".join(html_lib.escape(line) for line in para.split("\n"))
        body_parts.append(f"<p>{para_html}</p>")
    if not body_parts:
        body_parts.append(
            "<p>Start writing your newsletter here. This draft was generated "
            "from a captured idea — edit freely.</p>"
        )

    raw = media_block + heading + "".join(body_parts)
    return sanitize_html(raw)


def build_idea_design(
    title: str,
    notes: Optional[str],
    media_url: str,
    media_alt: Optional[str] = None,
) -> dict:
    """Assemble a structured block design from a scratchpad idea.

    Produces a professional starter layout whose first block is the MANDATORY
    visual — a hero (image) or a video card — followed by the notes as body
    text and a divider/footer. Guaranteed to satisfy ``design_has_media``.
    """
    title = (title or "Untitled newsletter").strip()
    is_video = media_url.lower().rsplit("?", 1)[0].endswith((".mp4", ".mov", ".webm"))
    blocks: list[dict] = []
    if is_video:
        blocks.append({"type": "heading", "heading": title, "align": "center"})
        blocks.append({"type": "video", "url": media_url, "caption": media_alt or ""})
    else:
        blocks.append({
            "type": "hero",
            "image": media_url,
            "layout": "overlay",
            "overlay": "dark",
            "align": "center",
            "heading": title,
            "eyebrow": "Newsletter",
        })
    body = (notes or "").strip()
    if body:
        blocks.append({"type": "text", "body": body})
    else:
        blocks.append({
            "type": "text",
            "body": "Start writing your newsletter here. This draft was generated "
                    "from a captured idea — edit the blocks freely.",
        })
    blocks.append({"type": "divider"})
    blocks.append({"type": "footer", "brandName": "Matcha", "tagline": "HR, handled."})
    return {"version": 1, "theme": {"preset": "light"}, "blocks": blocks}


class IdeaMediaRequiredError(ValueError):
    """Raised when an idea is converted without the mandatory visual."""


async def create_newsletter_from_idea(
    idea_id: UUID,
    media_url: Optional[str],
    created_by: UUID,
    media_alt: Optional[str] = None,
) -> dict:
    """Export a scratchpad idea into a structured newsletter draft.

    Enforces the mandatory-media requirement: `media_url` (falling back to any
    media captured on the idea itself) must be present, or the conversion is
    refused. On success a draft newsletter is created with the generated
    structured body and the idea is stamped `converted` + linked to the draft.
    """
    async with get_connection() as conn:
        idea = await conn.fetchrow(
            "SELECT id, title, notes, media_url, status, newsletter_id FROM newsletter_ideas WHERE id = $1",
            idea_id,
        )
        if not idea:
            raise ValueError("Idea not found")

        effective_media = (media_url or idea["media_url"] or "").strip()
        if not effective_media:
            raise IdeaMediaRequiredError(
                "A media/image is required to create a newsletter from an idea."
            )

        design = build_idea_design(
            title=idea["title"],
            notes=idea["notes"],
            media_url=effective_media,
            media_alt=media_alt,
        )
        content_html = _render_design_snapshot(design)

        async with conn.transaction():
            newsletter = await conn.fetchrow(
                """INSERT INTO newsletters (title, subject, content_html, design_json, created_by)
                   VALUES ($1, $2, $3, $4::jsonb, $5)
                   RETURNING *""",
                idea["title"], idea["title"], content_html, json.dumps(design), created_by,
            )
            await conn.execute(
                """UPDATE newsletter_ideas
                   SET status = 'converted', newsletter_id = $2,
                       media_url = COALESCE(media_url, $3), updated_at = NOW()
                   WHERE id = $1""",
                idea_id, newsletter["id"], effective_media,
            )
    return _normalize_row(newsletter)


# ---------------------------------------------------------------------------
# Analytics + growth (P2)
# ---------------------------------------------------------------------------


async def get_subscriber_growth(days: int = 90) -> list[dict]:
    """Return daily new-subscriber counts for the last `days` days. Used by
    the admin overview sparkline."""
    async with get_connection() as conn:
        rows = await conn.fetch(
            """SELECT date_trunc('day', subscribed_at)::date AS day,
                      COUNT(*) AS subscribed,
                      COUNT(*) FILTER (WHERE status IN ('active','unsubscribed','bounced')) AS confirmed
                 FROM newsletter_subscribers
                WHERE subscribed_at >= NOW() - ($1::int * INTERVAL '1 day')
                GROUP BY 1
                ORDER BY 1""",
            days,
        )
    return [
        {
            "day": r["day"].isoformat() if r["day"] else None,
            "subscribed": r["subscribed"],
            "confirmed": r["confirmed"],
        }
        for r in rows
    ]


async def get_newsletter_analytics(newsletter_id: UUID) -> dict:
    """Per-issue analytics — counts + computed rates against eligible
    recipients (sent rows, excluding never-attempted).

    `clicked` here counts unique subscribers who clicked. We don't track
    total click count because `clicked_at` only stamps the FIRST click
    (COALESCE in record_click). To surface total clicks we'd need a
    `click_count INT` column on newsletter_sends — deferred until anyone
    asks.
    """
    async with get_connection() as conn:
        row = await conn.fetchrow(
            """SELECT
                 COUNT(*) FILTER (WHERE status IN ('sent','failed')) AS attempted,
                 COUNT(*) FILTER (WHERE status = 'sent') AS sent,
                 COUNT(*) FILTER (WHERE status = 'failed') AS failed,
                 COUNT(*) FILTER (WHERE opened_at IS NOT NULL) AS opened,
                 COUNT(*) FILTER (WHERE clicked_at IS NOT NULL) AS clicked,
                 COUNT(*) FILTER (WHERE bounced_at IS NOT NULL OR status = 'bounced') AS bounced
               FROM newsletter_sends
              WHERE newsletter_id = $1""",
            newsletter_id,
        )
        # Unsubscribes attributed to this newsletter — heuristic: subscribers
        # who unsubscribed AFTER this newsletter's sent_at and BEFORE the
        # next newsletter went out. Without a direct link from unsub → issue
        # we approximate via a 7-day window from sent_at.
        nl = await conn.fetchrow(
            "SELECT sent_at FROM newsletters WHERE id = $1",
            newsletter_id,
        )
        unsub_count = 0
        if nl and nl["sent_at"]:
            unsub_count = await conn.fetchval(
                """SELECT COUNT(*)
                     FROM newsletter_subscribers
                    WHERE status = 'unsubscribed'
                      AND unsubscribed_at BETWEEN $1 AND $1 + INTERVAL '7 days'""",
                nl["sent_at"],
            ) or 0

    sent = row["sent"] or 0
    opened = row["opened"] or 0
    clicked = row["clicked"] or 0
    bounced = row["bounced"] or 0
    return {
        "attempted": row["attempted"] or 0,
        "sent": sent,
        "failed": row["failed"] or 0,
        "opened": opened,
        "clicked": clicked,
        "bounced": bounced,
        "unsubscribed_window": unsub_count,
        "open_rate": (opened / sent) if sent else 0.0,
        "click_rate": (clicked / sent) if sent else 0.0,
        "bounce_rate": (bounced / (sent + bounced)) if (sent + bounced) else 0.0,
        "unsubscribe_rate": (unsub_count / sent) if sent else 0.0,
    }


async def get_send_progress(newsletter_id: UUID) -> dict:
    """Live progress snapshot for the admin send progress bar."""
    async with get_connection() as conn:
        row = await conn.fetchrow(
            """SELECT
                 COUNT(*) AS queued,
                 COUNT(*) FILTER (WHERE status = 'sent') AS sent,
                 COUNT(*) FILTER (WHERE status = 'failed') AS failed,
                 COUNT(*) FILTER (WHERE status = 'pending') AS pending,
                 COUNT(*) FILTER (WHERE opened_at IS NOT NULL) AS opened,
                 COUNT(*) FILTER (WHERE clicked_at IS NOT NULL) AS clicked,
                 COUNT(*) FILTER (WHERE bounced_at IS NOT NULL OR status = 'bounced') AS bounced
               FROM newsletter_sends
              WHERE newsletter_id = $1""",
            newsletter_id,
        )
        nl_row = await conn.fetchrow(
            "SELECT status FROM newsletters WHERE id = $1",
            newsletter_id,
        )
    return {
        "newsletter_status": nl_row["status"] if nl_row else None,
        "queued": row["queued"] or 0,
        "sent": row["sent"] or 0,
        "failed": row["failed"] or 0,
        "pending": row["pending"] or 0,
        "opened": row["opened"] or 0,
        "clicked": row["clicked"] or 0,
        "bounced": row["bounced"] or 0,
    }


# ---------------------------------------------------------------------------
# Admin audit helper
# ---------------------------------------------------------------------------


async def log_admin_action(
    actor_id: Optional[UUID],
    action: str,
    target_type: Optional[str] = None,
    target_id: Optional[str] = None,
    metadata: Optional[dict] = None,
    client_ip: Optional[str] = None,
) -> None:
    try:
        async with get_connection() as conn:
            await conn.execute(
                """INSERT INTO newsletter_admin_audit
                     (actor_id, action, target_type, target_id, metadata, client_ip)
                   VALUES ($1, $2, $3, $4, $5::jsonb, $6::inet)""",
                actor_id, action, target_type, target_id,
                json.dumps(metadata or {}),
                client_ip,
            )
    except Exception:
        logger.exception("Failed to write newsletter_admin_audit row")
