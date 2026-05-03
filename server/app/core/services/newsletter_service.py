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
from typing import Optional
from urllib.parse import quote
from uuid import UUID

import bleach

from ...config import get_settings
from ...database import get_connection

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
               VALUES ($1, $2, $3, $4, $5, $6::jsonb, $7, $8,
                       CASE WHEN $7 = 'active' THEN NOW() ELSE NULL END)
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


async def unsubscribe(token: str) -> bool:
    sub_id = verify_unsubscribe_token(token)
    if not sub_id:
        return False
    async with get_connection() as conn:
        result = await conn.execute(
            """UPDATE newsletter_subscribers
               SET status = 'unsubscribed', unsubscribed_at = NOW()
               WHERE id = $1 AND status IN ('active', 'pending')""",
            sub_id,
        )
        return "UPDATE 1" in result


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
    return dict(row)


async def update_newsletter(newsletter_id: UUID, updates: dict) -> dict:
    allowed = {"title", "subject", "content_html", "curated_article_ids", "scheduled_at", "preheader"}
    sets = []
    params: list = []
    idx = 1
    for key, val in updates.items():
        if key not in allowed:
            continue
        if key == "content_html" and val:
            val = sanitize_html(val)
        sets.append(f"{key} = ${idx}")
        params.append(val)
        idx += 1
    if not sets:
        raise ValueError("No valid fields to update")
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
    return dict(row)


async def get_newsletter(newsletter_id: UUID) -> Optional[dict]:
    async with get_connection() as conn:
        row = await conn.fetchrow(
            "SELECT * FROM newsletters WHERE id = $1 AND is_deleted = FALSE",
            newsletter_id,
        )
        if not row:
            return None
        result = dict(row)
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
    return [dict(r) for r in rows]


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


def _render_email(
    newsletter: dict,
    subscriber: dict,
    unsubscribe_url: str,
    *,
    base_url: str = "",
    send_id: Optional[UUID] = None,
) -> str:
    """Render newsletter HTML with branded template, tracking, and CAN-SPAM
    footer. content_html is already sanitized at write time.

    `send_id` is the newsletter_sends row id — used to build the open-pixel
    URL and click-tracking redirect targets. When omitted (test send) tracking
    is skipped so we don't pollute the analytics with previews.
    """
    settings = get_settings()
    if not base_url:
        base_url = (settings.app_base_url or "https://hey-matcha.com").rstrip("/")

    content = newsletter.get("content_html") or ""
    preheader = (newsletter.get("preheader") or "").strip()

    # Click-tracking — wrap external links once, before any tracking pixels
    # are spliced in (the pixel src must NOT be wrapped).
    if send_id:
        content = _rewrite_links_for_tracking(
            content,
            base_url=base_url,
            send_id=send_id,
            skip_urls={unsubscribe_url},
        )

    # CAN-SPAM postal address. Newlines in the env-configured value become
    # <br> so admins can format multi-line addresses.
    mailing_address = (settings.newsletter_mailing_address or "").strip()
    address_html = mailing_address.replace("\n", "<br>") if mailing_address else ""

    # Preheader — hidden text right after <body> open. Email clients show
    # this as the inbox preview snippet alongside the subject. Hidden via
    # a stack of CSS tricks to defeat both Gmail and Outlook preview scrapers.
    preheader_html = ""
    if preheader:
        preheader_html = (
            f'<div style="display:none;max-height:0;overflow:hidden;'
            f'mso-hide:all;visibility:hidden;opacity:0;color:transparent;'
            f'height:0;width:0;">{preheader}</div>'
        )

    # Open-tracking pixel — placed at the end of content so most clients
    # have already rendered the rest before fetching it.
    pixel_html = ""
    if send_id:
        pixel_url = f"{base_url}/api/newsletter/track/open/{send_id}.gif"
        pixel_html = (
            f'<img src="{pixel_url}" width="1" height="1" alt="" '
            f'style="display:none;border:0;" />'
        )

    return f"""
    {preheader_html}
    <div style="max-width:600px;margin:0 auto;font-family:-apple-system,system-ui,sans-serif;background:#1e1e1e;color:#d4d4d4;padding:32px 24px;">
        <div style="text-align:center;margin-bottom:24px;">
            <span style="font-size:20px;font-weight:700;color:#ce9178;">Matcha</span>
        </div>
        <h1 style="font-size:22px;color:#e4e4e7;margin-bottom:16px;">{newsletter['title']}</h1>
        <div style="font-size:15px;line-height:1.7;color:#d4d4d4;">
            {content}
        </div>
        <hr style="border:none;border-top:1px solid #333;margin:32px 0;" />
        <div style="text-align:center;font-size:12px;color:#6a737d;line-height:1.6;">
            <p style="margin:0 0 8px 0;">You received this because you subscribed to Matcha updates.</p>
            <p style="margin:0 0 12px 0;">
                <a href="{unsubscribe_url}" style="color:#569cd6;text-decoration:underline;">Unsubscribe</a>
            </p>
            {f'<p style="margin:0;color:#6a737d;">{address_html}</p>' if address_html else ''}
        </div>
        {pixel_html}
    </div>
    """


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
            "SELECT id, name, description, preheader, created_at, updated_at FROM newsletter_templates ORDER BY name"
        )
    return [dict(r) for r in rows]


async def create_template(
    name: str,
    description: Optional[str],
    content_html: Optional[str],
    preheader: Optional[str],
    created_by: Optional[UUID],
) -> dict:
    sanitized = sanitize_html(content_html or "")
    async with get_connection() as conn:
        row = await conn.fetchrow(
            """INSERT INTO newsletter_templates (name, description, content_html, preheader, created_by)
               VALUES ($1, $2, $3, $4, $5)
               RETURNING *""",
            name.strip(), description, sanitized, preheader, created_by,
        )
    return dict(row)


async def update_template(template_id: UUID, updates: dict) -> Optional[dict]:
    allowed = {"name", "description", "content_html", "preheader"}
    sets = []
    params: list = []
    idx = 1
    for k, v in updates.items():
        if k not in allowed:
            continue
        if k == "content_html" and v:
            v = sanitize_html(v)
        sets.append(f"{k} = ${idx}")
        params.append(v)
        idx += 1
    if not sets:
        return None
    sets.append("updated_at = NOW()")
    params.append(template_id)
    async with get_connection() as conn:
        row = await conn.fetchrow(
            f"UPDATE newsletter_templates SET {', '.join(sets)} WHERE id = ${idx} RETURNING *",
            *params,
        )
    return dict(row) if row else None


async def get_template(template_id: UUID) -> Optional[dict]:
    async with get_connection() as conn:
        row = await conn.fetchrow(
            "SELECT * FROM newsletter_templates WHERE id = $1",
            template_id,
        )
    return dict(row) if row else None


async def delete_template(template_id: UUID) -> bool:
    async with get_connection() as conn:
        result = await conn.execute("DELETE FROM newsletter_templates WHERE id = $1", template_id)
    return "DELETE 1" in result


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
