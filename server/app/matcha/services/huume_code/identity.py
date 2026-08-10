"""The inactive Huume service identity used for ordinary chat rows."""
from __future__ import annotations

from uuid import UUID


async def ensure_huume_bot_user(conn, company_id: UUID) -> UUID:
    """Return this company's inactive, non-login Huume user.

    ``is_active=false`` is intentional and load-bearing: it keeps the bot out
    of login, invite lookup, and people pickers while still satisfying
    ``channel_messages.sender_id``'s foreign key.
    """
    email = f"huume@{company_id}.invalid"
    await conn.execute(
        """INSERT INTO users (email, password_hash, role, is_active)
           VALUES ($1, '!!HUUME-NO-LOGIN!!', 'client', false)
           ON CONFLICT (email) DO NOTHING""",
        email,
    )
    user_id = await conn.fetchval("SELECT id FROM users WHERE email = $1", email)
    await conn.execute(
        """INSERT INTO clients (user_id, company_id, name, job_title)
           VALUES ($1, $2, 'Huume', 'AI agent')
           ON CONFLICT (user_id) DO NOTHING""",
        user_id, company_id,
    )
    return user_id
