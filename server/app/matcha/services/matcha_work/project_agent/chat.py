"""Persist and fan out ordinary Espresso chat messages from API or Celery."""
from __future__ import annotations

import json
from uuid import UUID

from app.database import connection_or_direct

from .identity import ensure_espresso_bot_user


async def persist_espresso_message(
    conn,
    company_id: UUID,
    channel_id: UUID,
    content: str,
    *,
    metadata: dict | None = None,
) -> dict | None:
    """Insert an Espresso message on a caller-owned transaction."""
    message = (content or "").strip()[:4000]
    if not message:
        return None
    bot_id = await ensure_espresso_bot_user(conn, company_id)
    row = await conn.fetchrow(
        """INSERT INTO channel_messages
               (channel_id, sender_id, content, metadata)
           VALUES ($1, $2, $3, $4::jsonb)
           RETURNING id, created_at""",
        channel_id,
        bot_id,
        message,
        json.dumps(metadata or {}),
    )
    return {
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
        "metadata": metadata or {},
    }


async def broadcast_espresso_message(payload: dict | None) -> None:
    if payload is None:
        return
    from app.matcha.services.matcha_work.project_task_notifications import broadcast_channel_message

    await broadcast_channel_message(UUID(payload["channel_id"]), payload)


async def post_as_espresso(
    company_id: UUID,
    channel_id: UUID,
    content: str,
    *,
    metadata: dict | None = None,
) -> None:
    async with connection_or_direct() as conn:
        payload = await persist_espresso_message(
            conn,
            company_id,
            channel_id,
            content,
            metadata=metadata,
        )
    # Broadcast only after the insert's connection/transaction has completed.
    await broadcast_espresso_message(payload)
