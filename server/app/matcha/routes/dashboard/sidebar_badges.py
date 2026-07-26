"""Sidebar unseen-item badge counts."""
from datetime import datetime
from typing import Optional

import asyncpg
from fastapi import APIRouter, Depends, Query

from app.database import get_connection
from app.matcha.dependencies import require_admin_or_client, get_client_company_id
from app.core.models.auth import CurrentUser

router = APIRouter()


@router.get("/sidebar-badges")
async def get_sidebar_badges(
    since_ir: Optional[str] = Query(None),
    since_er: Optional[str] = Query(None),
    since_escalations: Optional[str] = Query(None),
    current_user: CurrentUser = Depends(require_admin_or_client),
):
    """Return unseen item counts per sidebar section for the current user."""
    company_id = await get_client_company_id(current_user)

    def parse_since(val: Optional[str]) -> Optional[datetime]:
        if not val:
            return None
        try:
            return datetime.fromisoformat(val.replace("Z", "+00:00"))
        except (ValueError, TypeError):
            return None

    since_ir_dt = parse_since(since_ir)
    since_er_dt = parse_since(since_er)
    since_esc_dt = parse_since(since_escalations)

    ir_count = er_count = esc_count = inbox_count = notif_count = 0

    async with get_connection() as conn:
        if since_ir_dt and company_id:
            ir_count = await conn.fetchval(
                "SELECT COUNT(*) FROM ir_incidents WHERE company_id = $1 AND created_at > $2",
                company_id, since_ir_dt,
            ) or 0

        if since_er_dt and company_id:
            er_count = await conn.fetchval(
                "SELECT COUNT(*) FROM er_cases WHERE company_id = $1 AND created_at > $2",
                company_id, since_er_dt,
            ) or 0

        if since_esc_dt and company_id:
            try:
                esc_count = await conn.fetchval(
                    "SELECT COUNT(*) FROM mw_escalated_queries WHERE company_id = $1 AND created_at > $2",
                    company_id, since_esc_dt,
                ) or 0
            except asyncpg.UndefinedTableError:
                pass

        inbox_count = await conn.fetchval(
            """
            SELECT COUNT(DISTINCT ip.conversation_id)
            FROM inbox_participants ip
            WHERE ip.user_id = $1
              AND EXISTS (
                SELECT 1 FROM inbox_messages im
                WHERE im.conversation_id = ip.conversation_id
                  AND im.sender_id != $1
                  AND (ip.last_read_at IS NULL OR im.created_at > ip.last_read_at)
              )
            """,
            current_user.id,
        ) or 0

        notif_count = await conn.fetchval(
            "SELECT COUNT(*) FROM mw_notifications WHERE user_id = $1 AND is_read = FALSE",
            current_user.id,
        ) or 0

    return {
        "ir": int(ir_count),
        "er": int(er_count),
        "escalations": int(esc_count),
        "inbox": int(inbox_count),
        "notifications": int(notif_count),
    }
