"""Newsletter service — subscriber management, newsletter composition, and sending."""

import asyncio
import hashlib
import hmac
import json
import logging
from datetime import datetime, timezone
from typing import Optional
from uuid import UUID

from ...config import get_settings
from ...database import get_connection

logger = logging.getLogger(__name__)

BATCH_SIZE = 50
BATCH_DELAY = 1.0  # seconds between batches


def _get_secret() -> bytes:
    settings = get_settings()
    return (settings.secret_key or "matcha-newsletter-default").encode()


def generate_unsubscribe_token(subscriber_id: UUID) -> str:
    """HMAC-signed token for one-click unsubscribe."""
    msg = str(subscriber_id).encode()
    sig = hmac.new(_get_secret(), msg, hashlib.sha256).hexdigest()[:24]
    return f"{subscriber_id}:{sig}"


def verify_unsubscribe_token(token: str) -> Optional[UUID]:
    """Verify token and return subscriber_id, or None if invalid."""
    try:
        sub_id_str, sig = token.split(":", 1)
        expected = hmac.new(_get_secret(), sub_id_str.encode(), hashlib.sha256).hexdigest()[:24]
        if hmac.compare_digest(sig, expected):
            return UUID(sub_id_str)
    except (ValueError, AttributeError):
        pass
    return None


async def subscribe(
    email: str,
    name: Optional[str] = None,
    source: str = "website",
    metadata: Optional[dict] = None,
    user_id: Optional[UUID] = None,
    company_id: Optional[UUID] = None,
) -> dict:
    """Subscribe an email. Idempotent — reactivates if previously unsubscribed."""
    email = email.strip().lower()
    async with get_connection() as conn:
        existing = await conn.fetchrow(
            "SELECT id, status FROM newsletter_subscribers WHERE email = $1", email
        )
        if existing:
            if existing["status"] == "unsubscribed":
                await conn.execute(
                    """UPDATE newsletter_subscribers
                       SET status = 'active', unsubscribed_at = NULL,
                           name = COALESCE($2, name), source = COALESCE($3, source),
                           metadata = COALESCE($4::jsonb, metadata),
                           subscribed_at = NOW()
                       WHERE id = $1""",
                    existing["id"], name, source,
                    json.dumps(metadata or {}),
                )
            return {"id": str(existing["id"]), "status": "active", "already_subscribed": existing["status"] == "active"}

        row = await conn.fetchrow(
            """INSERT INTO newsletter_subscribers (email, name, source, user_id, company_id, metadata)
               VALUES ($1, $2, $3, $4, $5, $6::jsonb)
               RETURNING id, status""",
            email, name, source, user_id, company_id,
            json.dumps(metadata or {}),
        )
        return {"id": str(row["id"]), "status": "active", "already_subscribed": False}


async def unsubscribe(token: str) -> bool:
    """Unsubscribe via signed token. Returns True if successful."""
    sub_id = verify_unsubscribe_token(token)
    if not sub_id:
        return False
    async with get_connection() as conn:
        result = await conn.execute(
            "UPDATE newsletter_subscribers SET status = 'unsubscribed', unsubscribed_at = NOW() WHERE id = $1 AND status = 'active'",
            sub_id,
        )
        return "UPDATE 1" in result


async def get_subscribers(
    status: Optional[str] = None,
    source: Optional[str] = None,
    search: Optional[str] = None,
    limit: int = 50,
    offset: int = 0,
) -> tuple[list[dict], int]:
    """List subscribers with optional filters. Returns (rows, total_count)."""
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
            f"""SELECT id, email, name, source, status, subscribed_at, unsubscribed_at, metadata
                FROM newsletter_subscribers {where}
                ORDER BY subscribed_at DESC
                LIMIT ${idx} OFFSET ${idx + 1}""",
            *params_with_pagination,
        )
    return [dict(r) for r in rows], total


async def get_subscriber_stats() -> dict:
    """Get aggregate subscriber stats."""
    async with get_connection() as conn:
        rows = await conn.fetch(
            """SELECT status, source, COUNT(*) AS cnt
               FROM newsletter_subscribers
               GROUP BY status, source"""
        )
    total = sum(r["cnt"] for r in rows)
    active = sum(r["cnt"] for r in rows if r["status"] == "active")
    by_source = {}
    for r in rows:
        by_source.setdefault(r["source"], 0)
        if r["status"] == "active":
            by_source[r["source"]] += r["cnt"]
    return {"total": total, "active": active, "by_source": by_source}


async def sync_platform_users() -> int:
    """Sync all active platform users into newsletter_subscribers. Idempotent."""
    async with get_connection() as conn:
        result = await conn.execute(
            """INSERT INTO newsletter_subscribers (email, name, source, user_id)
               SELECT u.email,
                      COALESCE(c.name, CONCAT(e.first_name, ' ', e.last_name), u.email),
                      'platform',
                      u.id
               FROM users u
               LEFT JOIN clients c ON c.user_id = u.id
               LEFT JOIN employees e ON e.user_id = u.id
               WHERE u.is_active = true AND u.email IS NOT NULL
               ON CONFLICT (email) DO NOTHING"""
        )
        count = int(result.split()[-1]) if result else 0
    logger.info("Synced %d platform users to newsletter subscribers", count)
    return count


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
        if key in allowed:
            sets.append(f"{key} = ${idx}")
            params.append(val)
            idx += 1
    if not sets:
        raise ValueError("No valid fields to update")
    sets.append(f"updated_at = NOW()")
    params.append(newsletter_id)
    async with get_connection() as conn:
        row = await conn.fetchrow(
            f"UPDATE newsletters SET {', '.join(sets)} WHERE id = ${idx} AND status = 'draft' RETURNING *",
            *params,
        )
    if not row:
        raise ValueError("Newsletter not found or not in draft status")
    return dict(row)


async def get_newsletter(newsletter_id: UUID) -> Optional[dict]:
    async with get_connection() as conn:
        row = await conn.fetchrow("SELECT * FROM newsletters WHERE id = $1", newsletter_id)
        if not row:
            return None
        result = dict(row)
        # Get send stats
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
               ORDER BY n.created_at DESC
               LIMIT $1 OFFSET $2""",
            limit, offset,
        )
    return [dict(r) for r in rows]


async def send_newsletter(newsletter_id: UUID) -> dict:
    """Queue and send a newsletter to all active subscribers."""
    from .email import get_email_service

    async with get_connection() as conn:
        nl = await conn.fetchrow(
            "SELECT * FROM newsletters WHERE id = $1 AND status IN ('draft', 'scheduled')",
            newsletter_id,
        )
        if not nl:
            raise ValueError("Newsletter not found or already sent")

        # Mark as sending
        await conn.execute(
            "UPDATE newsletters SET status = 'sending' WHERE id = $1", newsletter_id
        )

        # Get all active subscribers
        subscribers = await conn.fetch(
            "SELECT id, email, name FROM newsletter_subscribers WHERE status = 'active'"
        )

        # Create send records
        for sub in subscribers:
            await conn.execute(
                """INSERT INTO newsletter_sends (newsletter_id, subscriber_id)
                   VALUES ($1, $2)
                   ON CONFLICT (newsletter_id, subscriber_id) DO NOTHING""",
                newsletter_id, sub["id"],
            )

    # Launch sending in background so the API response returns immediately
    asyncio.create_task(_send_emails(newsletter_id, dict(nl), list(subscribers)))

    return {"queued": len(subscribers), "status": "sending"}


async def _send_emails(newsletter_id: UUID, nl: dict, subscribers: list[dict]) -> None:
    """Background task — sends emails in batches and updates send status."""
    from .email import get_email_service

    email_svc = get_email_service()
    settings = get_settings()
    base_url = (settings.app_base_url or "https://hey-matcha.com").rstrip("/")
    sent_count = 0
    failed_count = 0

    for i in range(0, len(subscribers), BATCH_SIZE):
        batch = subscribers[i:i + BATCH_SIZE]
        sent_ids = []
        failed_ids = []

        for sub in batch:
            unsub_token = generate_unsubscribe_token(sub["id"])
            unsub_url = f"{base_url}/api/newsletter/unsubscribe?token={unsub_token}"

            html = _render_email(nl, sub, unsub_url)

            try:
                await email_svc.send_email(
                    to_email=sub["email"],
                    to_name=sub["name"],
                    subject=nl["subject"],
                    html_content=html,
                )
                sent_ids.append(sub["id"])
                sent_count += 1
            except Exception as e:
                logger.warning("Failed to send newsletter to %s: %s", sub["email"], e)
                failed_ids.append(sub["id"])
                failed_count += 1

        # Batch-update send status
        try:
            async with get_connection() as conn:
                if sent_ids:
                    await conn.execute(
                        "UPDATE newsletter_sends SET status = 'sent', sent_at = NOW() WHERE newsletter_id = $1 AND subscriber_id = ANY($2::uuid[])",
                        newsletter_id, sent_ids,
                    )
                if failed_ids:
                    await conn.execute(
                        "UPDATE newsletter_sends SET status = 'failed' WHERE newsletter_id = $1 AND subscriber_id = ANY($2::uuid[])",
                        newsletter_id, failed_ids,
                    )
        except Exception as e:
            logger.error("Failed to update send status: %s", e)

        if i + BATCH_SIZE < len(subscribers):
            await asyncio.sleep(BATCH_DELAY)

    # Mark newsletter as sent
    try:
        async with get_connection() as conn:
            await conn.execute(
                "UPDATE newsletters SET status = 'sent', sent_at = NOW() WHERE id = $1",
                newsletter_id,
            )
    except Exception as e:
        logger.error("Failed to mark newsletter as sent: %s", e)

    logger.info("Newsletter %s: sent=%d failed=%d total=%d", newsletter_id, sent_count, failed_count, len(subscribers))


def _render_email(newsletter: dict, subscriber: dict, unsubscribe_url: str) -> str:
    """Render newsletter HTML with branded template and unsubscribe footer."""
    name = subscriber.get("name") or "there"
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
