"""Celery task: email a user when they're @-mentioned in a channel and offline.

Triggered from `core/routes/channels_ws.py` after a message containing one or
more resolved mentions is broadcast. The task checks Redis for an "online"
heartbeat key (written by the WS server on every receive); only mentioned users
without a fresh heartbeat get an email. A throttle key per (user, channel)
prevents flooding during bursty conversations.
"""

import asyncio
import html as _html
import logging
from typing import Optional

import redis.asyncio as aioredis

from ..celery_app import celery_app
from ..utils import get_db_connection

logger = logging.getLogger(__name__)

ONLINE_KEY_PREFIX = "channels_ws:online:"
THROTTLE_KEY_PREFIX = "mention_email:throttle:"
THROTTLE_TTL_SECONDS = 15 * 60  # 15 min per (user, channel) — tune later via prefs


@celery_app.task(bind=True, max_retries=3, default_retry_delay=30, name="app.workers.tasks.mention_email.send_mention_email")
def send_mention_email(
    self,
    message_id: str,
    channel_id: str,
    sender_id: str,
    sender_name: str,
    content: str,
    mentioned_user_ids: list[str],
):
    """Sync entry-point invoked via .delay() from the WS message handler."""
    try:
        asyncio.run(_send_mention_email_async(
            message_id=message_id,
            channel_id=channel_id,
            sender_id=sender_id,
            sender_name=sender_name,
            content=content,
            mentioned_user_ids=mentioned_user_ids,
        ))
    except Exception as exc:
        logger.exception("send_mention_email failed message_id=%s: %s", message_id, exc)
        raise self.retry(exc=exc)


async def _send_mention_email_async(
    *,
    message_id: str,
    channel_id: str,
    sender_id: str,
    sender_name: str,
    content: str,
    mentioned_user_ids: list[str],
) -> None:
    if not mentioned_user_ids:
        return

    import os
    redis_url = os.getenv("REDIS_URL", "redis://localhost:6379/0")
    redis: aioredis.Redis = aioredis.from_url(redis_url, decode_responses=True)

    conn = await get_db_connection()
    try:
        # Pull channel name + recipient details in one round-trip.
        channel_row = await conn.fetchrow(
            "SELECT name FROM channels WHERE id = $1",
            channel_id,
        )
        if not channel_row:
            return
        channel_name = channel_row["name"]

        recipients = await conn.fetch(
            """
            SELECT u.id,
                   u.email,
                   COALESCE(c.name, CONCAT(e.first_name, ' ', e.last_name), a.name, u.email) AS name
            FROM users u
            LEFT JOIN clients c ON c.user_id = u.id
            LEFT JOIN employees e ON e.user_id = u.id
            LEFT JOIN admins a ON a.user_id = u.id
            WHERE u.id = ANY($1::uuid[])
            """,
            mentioned_user_ids,
        )

        from app.core.services.email import EmailService
        email_service = EmailService()
        if not email_service.is_configured():
            logger.warning("Email not configured; skipping %d mention emails", len(recipients))
            return

        web_base = os.getenv("PUBLIC_WEB_BASE_URL", "https://hey-matcha.com")
        channel_url = f"{web_base}/work/channels/{channel_id}"
        excerpt = (content or "").strip()
        if len(excerpt) > 200:
            excerpt = excerpt[:200].rstrip() + "…"
        excerpt_html = _html.escape(excerpt).replace("\n", "<br>")

        subject = f"[matcha] {sender_name} mentioned you in #{channel_name}"

        html_content = f"""
            <div style="font-family: -apple-system, Helvetica, Arial, sans-serif; color: #1a1a2e; max-width: 560px;">
                <p style="margin: 0 0 12px;"><strong>{_html.escape(sender_name)}</strong> mentioned you in
                <strong>#{_html.escape(channel_name)}</strong>:</p>
                <blockquote style="margin: 0 0 16px; padding: 12px 14px; border-left: 3px solid #6c63ff; background: #f6f5fa; color: #333; font-size: 14px; line-height: 1.5;">
                    {excerpt_html}
                </blockquote>
                <p style="margin: 0 0 24px;">
                    <a href="{channel_url}" style="display: inline-block; padding: 10px 18px; background: #1a1a2e; color: white; text-decoration: none; border-radius: 6px; font-size: 14px;">Open in Matcha</a>
                </p>
                <p style="margin: 0; color: #888; font-size: 11px;">
                    You received this because you're a member of #{_html.escape(channel_name)} and you were offline when this message was sent.
                </p>
            </div>
        """
        text_content = (
            f"{sender_name} mentioned you in #{channel_name}:\n\n"
            f"  {excerpt}\n\n"
            f"Open in Matcha: {channel_url}\n"
        )

        for r in recipients:
            recipient_id = str(r["id"])
            recipient_email = r["email"]
            recipient_name = r["name"] or recipient_email

            # Skip if user is online (any active WS in last 60s).
            online = await redis.get(f"{ONLINE_KEY_PREFIX}{recipient_id}")
            if online:
                logger.info("mention email skip user=%s online", recipient_id)
                continue

            # Skip if throttled for this channel.
            throttle_key = f"{THROTTLE_KEY_PREFIX}{recipient_id}:{channel_id}"
            throttled = await redis.get(throttle_key)
            if throttled:
                logger.info("mention email skip user=%s channel=%s throttled", recipient_id, channel_id)
                continue

            sent = await email_service.send_email(
                to_email=recipient_email,
                to_name=recipient_name,
                subject=subject,
                html_content=html_content,
                text_content=text_content,
            )
            if sent:
                await redis.setex(throttle_key, THROTTLE_TTL_SECONDS, "1")
                logger.info("mention email sent user=%s channel=%s message=%s", recipient_id, channel_id, message_id)
            else:
                logger.warning("mention email failed user=%s message=%s", recipient_id, message_id)
    finally:
        await conn.close()
        await redis.aclose()
