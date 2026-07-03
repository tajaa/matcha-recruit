from fastapi import APIRouter, Depends

from app.core.models.auth import CurrentUser
from app.database import get_connection
from app.matcha.dependencies import require_admin_or_client

router = APIRouter()

_PRESENCE_NAME_EXPR = "COALESCE(c.name, CONCAT(e.first_name, ' ', e.last_name), a.name, u.email)"

@router.post("/heartbeat", status_code=204)
async def presence_heartbeat(current_user: CurrentUser = Depends(require_admin_or_client)):
    """Update the user's Matcha Work last-active timestamp."""
    async with get_connection() as conn:
        await conn.execute(
            "UPDATE users SET mw_last_active = NOW() WHERE id = $1",
            current_user.id,
        )

@router.get("/online")
async def get_online_users(current_user: CurrentUser = Depends(require_admin_or_client)):
    """Return users active on Matcha Work within the last 2 minutes."""
    async with get_connection() as conn:
        rows = await conn.fetch(
            f"""
            SELECT u.id, u.email, u.avatar_url, u.mw_last_active,
                   {_PRESENCE_NAME_EXPR} AS name
            FROM users u
            LEFT JOIN clients c ON c.user_id = u.id
            LEFT JOIN employees e ON e.user_id = u.id
            LEFT JOIN admins a ON a.user_id = u.id
            WHERE u.mw_last_active > NOW() - INTERVAL '2 minutes'
              AND u.id != $1
              AND u.is_active = true
            ORDER BY u.mw_last_active DESC
            """,
            current_user.id,
        )
    return [
        {
            "id": str(r["id"]),
            "name": r["name"] or r["email"],
            "email": r["email"],
            "avatar_url": r["avatar_url"],
            "last_active": r["mw_last_active"].isoformat() if r["mw_last_active"] else None,
        }
        for r in rows
    ]
