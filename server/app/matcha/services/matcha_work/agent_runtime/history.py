"""The conversation so far, replayed as context for one run.

A run has no memory of its own: each message starts a fresh one, and what came
before is read back from the channel. Two things come out of that read and
they are deliberately separate:

  * the replay: every recent message, so the model follows the conversation;
  * the requester's own texts: the only words that can ground an outward
    action (see `policy`).

In a shared project chat a coworker's message is context. It is never
grounding: someone else naming an address does not make it one the requester
asked to write to.
"""
from __future__ import annotations

from uuid import UUID

from app.matcha.services.huume.luna_client import text_item

DEFAULT_LIMIT = 20
DEFAULT_MAX_CHARS = 8000
_PER_MESSAGE_CHARS = 2000


async def build_history(
    conn,
    *,
    channel_id: UUID,
    requester_id: UUID,
    trigger_message_id: UUID | None = None,
    limit: int = DEFAULT_LIMIT,
    max_chars: int = DEFAULT_MAX_CHARS,
) -> tuple[list[dict], tuple[str, ...]]:
    """(replay items oldest first, the requester's own texts).

    The trigger message itself is left out of the replay (the caller sends it
    as the run's request) but counts among the requester's texts.
    """
    rows = await conn.fetch(
        """SELECT m.id, m.sender_id, m.content,
                  (u.email LIKE 'espresso@%.invalid') AS from_espresso,
                  COALESCE(c.name, NULLIF(BTRIM(CONCAT(e.first_name, ' ', e.last_name)), ''), 'Someone') AS sender_name
           FROM channel_messages m
           LEFT JOIN users u ON u.id = m.sender_id
           LEFT JOIN clients c ON c.user_id = m.sender_id
           LEFT JOIN employees e ON e.user_id = m.sender_id
           WHERE m.channel_id = $1 AND m.deleted_at IS NULL
             -- The column holds 'user' or 'system' (ems01); anything that is
             -- not a system notice is part of the conversation.
             AND m.message_type IS DISTINCT FROM 'system'
             -- "On it." is a progress card, not something that was said.
             AND COALESCE(m.metadata->>'kind', '') <> 'agent_progress'
           ORDER BY m.created_at DESC
           LIMIT $2""",
        channel_id, limit + 1,
    )
    items: list[dict] = []
    own: list[str] = []
    used = 0
    full = False
    for row in rows:  # newest first: the budget keeps the most recent
        content = (row["content"] or "").strip()
        if not content:
            continue
        mine = row["sender_id"] == requester_id
        if mine:
            own.append(content)
        if trigger_message_id is not None and row["id"] == trigger_message_id:
            continue
        text = content[:_PER_MESSAGE_CHARS]
        if full or len(items) >= limit or used + len(text) > max_chars:
            # Stop at the first message that does not fit, so the replay is an
            # unbroken run of the latest messages rather than whichever fit.
            full = True
            continue
        used += len(text)
        if row["from_espresso"]:
            items.append(text_item("assistant", text))
        elif mine:
            items.append(text_item("user", text))
        else:
            items.append(text_item("user", f"[{row['sender_name']}, another person in this chat]: {text}"))
    items.reverse()
    own.reverse()
    return items, tuple(own)
