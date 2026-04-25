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
"""

import asyncio
import hashlib
import hmac
import json
import logging
import secrets
from datetime import datetime, timezone
from typing import Optional
from uuid import UUID

import bleach

from ...config import get_settings
from ...database import get_connection

logger = logging.getLogger(__name__)

BATCH_SIZE = 50
BATCH_DELAY = 1.0  # seconds between batches

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
    allowed = {"title", "subject", "content_html", "curated_article_ids", "scheduled_at"}
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

    for i in range(0, len(subscribers), BATCH_SIZE):
        batch = subscribers[i:i + BATCH_SIZE]
        sent_ids: list[UUID] = []
        failed_ids: list[UUID] = []

        for sub in batch:
            unsub_token = generate_unsubscribe_token(sub["id"])
            unsub_url = f"{base_url}/api/newsletter/unsubscribe?token={unsub_token}"
            html = _render_email(nl, sub, unsub_url)

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


def _render_email(newsletter: dict, subscriber: dict, unsubscribe_url: str) -> str:
    """Render newsletter HTML with branded template and unsubscribe footer.
    content_html is already sanitized at write time."""
    content = newsletter.get("content_html") or ""
    return f"""
    <div style="max-width:600px;margin:0 auto;font-family:-apple-system,system-ui,sans-serif;background:#1e1e1e;color:#d4d4d4;padding:32px 24px;">
        <div style="text-align:center;margin-bottom:24px;">
            <span style="font-size:20px;font-weight:700;color:#ce9178;">Matcha</span>
        </div>
        <h1 style="font-size:22px;color:#e4e4e7;margin-bottom:16px;">{newsletter['title']}</h1>
        <div style="font-size:15px;line-height:1.7;color:#d4d4d4;">
            {content}
        </div>
        <hr style="border:none;border-top:1px solid #333;margin:32px 0;" />
        <div style="text-align:center;font-size:12px;color:#6a737d;">
            <p>You received this because you subscribed to Matcha updates.</p>
            <a href="{unsubscribe_url}" style="color:#569cd6;text-decoration:underline;">Unsubscribe</a>
        </div>
    </div>
    """


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
