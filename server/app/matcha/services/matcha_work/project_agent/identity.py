"""Inactive, non-login identity used for Espresso's ordinary chat rows."""
from __future__ import annotations

from uuid import UUID

# The bot's password hash is this sentinel, never a real hash: it can't log in,
# and it is how a message row is told apart as Espresso's (a person could be
# named "Espresso", or pick a look-alike address; nobody can set this).
ESPRESSO_NO_LOGIN = "!!ESPRESSO-NO-LOGIN!!"


async def ensure_espresso_bot_user(conn, company_id: UUID) -> UUID:
    email = f"espresso@{company_id}.invalid"
    await conn.execute(
        """INSERT INTO users (email, password_hash, role, is_active)
           VALUES ($1, $2, 'client', false)
           ON CONFLICT (email) DO NOTHING""",
        email, ESPRESSO_NO_LOGIN,
    )
    user_id = await conn.fetchval("SELECT id FROM users WHERE email = $1", email)
    await conn.execute(
        """INSERT INTO clients (user_id, company_id, name, job_title)
           VALUES ($1, $2, 'Espresso', 'Repository guide')
           ON CONFLICT (user_id) DO NOTHING""",
        user_id,
        company_id,
    )
    return user_id
