"""A person's private conversation with Espresso.

One channel per person per company, `channel_scope = 'assistant'`, with that
person as its only member. It is written here with the scope as a literal:
this package never imports `werk` (the matcha → werk boundary allows exactly
the two fan-out imports that already exist).
"""
from __future__ import annotations

from uuid import UUID

import asyncpg

ASSISTANT_SCOPE = "assistant"
CHANNEL_NAME = "Espresso"


def _slug(user_id: UUID) -> str:
    return f"espresso-{user_id.hex}"


async def ensure_assistant_channel(conn, *, user_id: UUID, company_id: UUID) -> UUID:
    """The person's private conversation, created on first use. Idempotent."""
    existing = await conn.fetchval(
        """SELECT id FROM channels
           WHERE company_id = $1 AND assistant_user_id = $2 AND channel_scope = 'assistant'""",
        company_id, user_id,
    )
    if existing:
        return existing
    try:
        async with conn.transaction():
            channel_id = await conn.fetchval(
                """INSERT INTO channels
                       (company_id, name, slug, description, created_by, visibility,
                        channel_scope, assistant_user_id, is_paid, currency)
                   VALUES ($1, $2, $3, $4, $5, 'private', 'assistant', $5, FALSE, 'usd')
                   RETURNING id""",
                company_id, CHANNEL_NAME, _slug(user_id),
                "Your private conversation with Espresso.", user_id,
            )
            await conn.execute(
                """INSERT INTO channel_members (channel_id, user_id, role, last_contributed_at)
                   VALUES ($1, $2, 'owner', NOW())""",
                channel_id, user_id,
            )
        return channel_id
    except asyncpg.UniqueViolationError:
        # Two first opens at once: the other one made it.
        return await conn.fetchval(
            """SELECT id FROM channels
               WHERE company_id = $1 AND assistant_user_id = $2 AND channel_scope = 'assistant'""",
            company_id, user_id,
        )


async def is_private_conversation(conn, *, channel_id: UUID, user_id: UUID) -> bool:
    """Whether this channel is `user_id`'s own private conversation, with
    nobody else in it. The second half is the belt: the routes refuse to add
    anyone, and abilities that touch a person's own data still check."""
    row = await conn.fetchrow(
        """SELECT ch.channel_scope, ch.assistant_user_id,
                  (SELECT COUNT(*) FROM channel_members cm
                    WHERE cm.channel_id = ch.id AND cm.removed_for_inactivity IS NOT TRUE) AS members,
                  (SELECT COUNT(*) FROM channel_members cm
                    WHERE cm.channel_id = ch.id AND cm.user_id = $2
                      AND cm.removed_for_inactivity IS NOT TRUE) AS mine
           FROM channels ch WHERE ch.id = $1""",
        channel_id, user_id,
    )
    return bool(
        row
        and row["channel_scope"] == ASSISTANT_SCOPE
        and row["assistant_user_id"] == user_id
        and row["members"] == 1
        and row["mine"] == 1
    )
