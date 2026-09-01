"""Persist and fan out ordinary Espresso chat messages from API or Celery."""
from __future__ import annotations

from uuid import UUID

from app.database import connection_or_direct

from .identity import ensure_espresso_bot_user


async def post_as_espresso(company_id: UUID, channel_id: UUID, content: str) -> None:
    message = (content or "").strip()[:4000]
    if not message:
        return
    async with connection_or_direct() as conn:
        bot_id = await ensure_espresso_bot_user(conn, company_id)
        row = await conn.fetchrow(
            """INSERT INTO channel_messages (channel_id, sender_id, content)
               VALUES ($1, $2, $3) RETURNING id, created_at""",
            channel_id,
            bot_id,
            message,
        )
    # Reuse the established Matcha Work -> Werk fan-out bridge. This avoids a
    # new cross-package manager import and keeps REST/WS message shapes aligned.
    from app.matcha.services.matcha_work.project_task_notifications import broadcast_channel_message

    await broadcast_channel_message(channel_id, {
        "id": str(row["id"]),
        "channel_id": str(channel_id),
        "sender_id": str(bot_id),
        "sender_name": "Espresso",
        "sender_avatar_url": None,
        "content": message,
        "attachments": [],
        "reply_to_id": None,
        "reply_preview": None,
        "reactions": [],
        "created_at": row["created_at"].isoformat(),
        "edited_at": None,
        "mentioned_user_ids": [],
        "client_message_id": None,
        "message_type": "message",
    })
