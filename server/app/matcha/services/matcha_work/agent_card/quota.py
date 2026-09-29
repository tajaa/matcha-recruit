"""Monthly agent-card run allowance, per user."""
from __future__ import annotations

from datetime import datetime, timezone
from uuid import UUID

from app.database import connection_or_direct
from app.matcha.services.billing.entitlements_service import (
    AGENT_CARD_MONTHLY_RUNS,
    resolve_plan_for_user,
)


def _next_month_start(now: datetime) -> datetime:
    if now.month == 12:
        return datetime(now.year + 1, 1, 1, tzinfo=timezone.utc)
    return datetime(now.year, now.month + 1, 1, tzinfo=timezone.utc)


async def card_agent_usage(user_id: UUID | str, *, plan: str | None = None) -> dict:
    """`{limit, used, remaining, resets_at}` for the current UTC month.

    A failed run is free: it counts only while queued/running or once done.
    """
    plan = plan or await resolve_plan_for_user(user_id)
    limit = AGENT_CARD_MONTHLY_RUNS.get(plan, 0)
    async with connection_or_direct() as conn:
        used = await conn.fetchval(
            """SELECT COUNT(*) FROM mw_project_agent_runs
               WHERE kind = 'card_agent' AND requested_by = $1
                 AND status IN ('queued', 'running', 'done')
                 AND created_at >= date_trunc('month', NOW() AT TIME ZONE 'UTC') AT TIME ZONE 'UTC'""",
            UUID(str(user_id)),
        )
    used = int(used or 0)
    return {
        "limit": limit,
        "used": used,
        "remaining": max(0, limit - used),
        "resets_at": _next_month_start(datetime.now(timezone.utc)).isoformat(),
    }
