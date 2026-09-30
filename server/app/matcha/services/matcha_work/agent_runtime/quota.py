"""Daily assistant-run allowance, per person.

Counted apart from the monthly agent-card allowance: an assistant run is one
chat message, a card run is a research errand.
"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone
from uuid import UUID

from app.database import connection_or_direct
from app.matcha.services.billing.entitlements_service import (
    ASSISTANT_DAILY_RUNS,
    resolve_plan_for_user,
)


async def used_today(conn, user_id: UUID | str) -> int:
    """Runs that count against this UTC day. A failed run is free."""
    used = await conn.fetchval(
        """SELECT COUNT(*) FROM mw_project_agent_runs
           WHERE kind = 'assistant' AND requested_by = $1
             AND status IN ('queued', 'running', 'done')
             AND created_at >= date_trunc('day', NOW() AT TIME ZONE 'UTC') AT TIME ZONE 'UTC'""",
        UUID(str(user_id)),
    )
    return int(used or 0)


def limit_for_plan(plan: str) -> int:
    return ASSISTANT_DAILY_RUNS.get(plan, 0)


def usage_payload(limit: int, used: int, *, now: datetime | None = None) -> dict:
    now = now or datetime.now(timezone.utc)
    tomorrow = (now + timedelta(days=1)).replace(hour=0, minute=0, second=0, microsecond=0)
    return {
        "limit": limit,
        "used": used,
        "remaining": max(0, limit - used),
        "resets_at": tomorrow.isoformat(),
    }


async def assistant_usage(user_id: UUID | str, *, plan: str | None = None) -> dict:
    """`{limit, used, remaining, resets_at}` for the current UTC day."""
    plan = plan or await resolve_plan_for_user(user_id)
    async with connection_or_direct() as conn:
        used = await used_today(conn, user_id)
    return usage_payload(limit_for_plan(plan), used)
