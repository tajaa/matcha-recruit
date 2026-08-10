"""Persist and fan out ordinary Huume chat messages from API or Celery."""
from __future__ import annotations

from uuid import UUID

from app.database import connection_or_direct
from .identity import ensure_huume_bot_user


async def post_as_huume(company_id: UUID, channel_id: UUID, content: str) -> None:
    async with connection_or_direct() as conn:
        bot_id = await ensure_huume_bot_user(conn, company_id)
        row = await conn.fetchrow(
            """INSERT INTO channel_messages (channel_id, sender_id, content)
               VALUES ($1, $2, $3) RETURNING id, created_at""",
            channel_id, bot_id, content[:4000],
        )
    from app.werk.routes.channels_ws import manager
    await manager.broadcast_message(str(channel_id), {
        "id": str(row["id"]), "channel_id": str(channel_id), "sender_id": str(bot_id),
        "sender_name": "Huume", "sender_avatar_url": None, "content": content[:4000],
        "attachments": [], "reply_to_id": None, "reply_preview": None, "reactions": [],
        "created_at": row["created_at"].isoformat(), "edited_at": None,
        "mentioned_user_ids": [], "client_message_id": None, "message_type": "message",
    })
