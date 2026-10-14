"""Monthly job-search allowance, per person.

A search costs real money (Google Jobs calls, page loads, model runs), so the
cap counts whole searches, not re-ranks or redrafts. Only a search the system
failed is free. A cancelled search counts, and so does a deleted one: deleting
leaves a blanked row behind for exactly this reason.
"""
from __future__ import annotations

from uuid import UUID

from app.database import connection_or_direct
from app.matcha.services.billing.entitlements_service import (
    JOB_SEARCH_MONTHLY_RUNS,
    resolve_plan_for_user,
)
from app.matcha.services.matcha_work.agent_card.quota import usage_payload


async def used_this_month(conn, user_id: UUID | str) -> int:
    used = await conn.fetchval(
        """SELECT COUNT(*) FROM mw_job_searches
           WHERE user_id = $1 AND status <> 'failed'
             AND created_at >= date_trunc('month', NOW() AT TIME ZONE 'UTC') AT TIME ZONE 'UTC'""",
        UUID(str(user_id)),
    )
    return int(used or 0)


def limit_for_plan(plan: str) -> int:
    return JOB_SEARCH_MONTHLY_RUNS.get(plan, 0)


async def job_search_usage(user_id: UUID | str, *, plan: str | None = None) -> dict:
    """`{limit, used, remaining, resets_at}` for the current UTC month."""
    plan = plan or await resolve_plan_for_user(user_id)
    async with connection_or_direct() as conn:
        used = await used_this_month(conn, user_id)
    return usage_payload(limit_for_plan(plan), used)
