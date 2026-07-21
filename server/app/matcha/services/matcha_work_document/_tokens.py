"""matcha_work_document — tokens helpers (L6 split).

Extracted from the monolithic service; re-exported by the package __init__.
"""
from app.database import get_connection
from datetime import datetime, timezone
from typing import Optional
from uuid import UUID
from app.matcha.services.matcha_work_document._coerce import (
    _coerce_bool,
    _coerce_int,
)

import logging
logger = logging.getLogger(__name__)

async def log_token_usage_event(
    company_id: UUID,
    user_id: UUID,
    thread_id: UUID,
    token_usage: Optional[dict],
    operation: str = "send_message",
    cost_dollars: float | None = None,
) -> None:
    if not token_usage:
        return

    model = str(token_usage.get("model") or "unknown").strip() or "unknown"
    prompt_tokens = _coerce_int(token_usage.get("prompt_tokens"))
    completion_tokens = _coerce_int(token_usage.get("completion_tokens"))
    total_tokens = _coerce_int(token_usage.get("total_tokens"))
    if total_tokens is None and (prompt_tokens is not None or completion_tokens is not None):
        total_tokens = (prompt_tokens or 0) + (completion_tokens or 0)

    estimated = _coerce_bool(token_usage.get("estimated"), False)

    async with get_connection() as conn:
        await conn.execute(
            """
            INSERT INTO mw_token_usage_events(
                company_id, user_id, thread_id, model,
                prompt_tokens, completion_tokens, total_tokens,
                estimated, operation, cost_dollars
            )
            VALUES($1, $2, $3, $4, $5, $6, $7, $8, $9, $10)
            """,
            company_id,
            user_id,
            thread_id,
            model,
            prompt_tokens,
            completion_tokens,
            total_tokens,
            estimated,
            operation,
            cost_dollars,
        )

# Last-resort fallback if no mw_token_quotas row exists AND plan resolution
# (incl. the entitlements_service import) fails — normally the per-plan defaults
# in entitlements_service.PLAN_QUOTAS apply. Set to the FREE-tier budget so the
# ultimate failure mode never grants a paid quota (fail closed). Keep in sync
# with entitlements_service.PLAN_QUOTAS[PLAN_FREE].
_DEFAULT_TOKEN_LIMIT = 25_000

_DEFAULT_WINDOW_HOURS = 12

async def check_token_quota(user_id: UUID, company_id: Optional[UUID] = None) -> dict:
    """Check if the user is within their token quota.

    Limit resolution: explicit mw_token_quotas row (user > company > global)
    stays authoritative — admin grants keep working; otherwise the default
    comes from the user's plan (free taste / lite / pro / business).

    Returns dict with: allowed, used, limit, window_hours, resets_at
    """
    async with get_connection() as conn:
        # Get quota: user-specific > company-level > global default
        quota_row = await conn.fetchrow(
            """
            SELECT token_limit, window_hours FROM mw_token_quotas
            WHERE is_active = true
              AND (user_id = $1 OR user_id IS NULL)
              AND (company_id = $2 OR company_id IS NULL)
            ORDER BY user_id NULLS LAST, company_id NULLS LAST
            LIMIT 1
            """,
            user_id, company_id,
        )

    if quota_row:
        token_limit = quota_row["token_limit"]
        window_hours = quota_row["window_hours"]
    else:
        # Plan-based default (resolved outside the connection block — the
        # resolver opens its own connection; don't hold two pool slots).
        # Fail CLOSED: if plan resolution throws, fall back to the FREE-tier
        # quota, never the higher _DEFAULT_TOKEN_LIMIT — a transient resolver
        # error must not hand a free user a paid budget.
        try:
            from . import entitlements_service

            token_limit, window_hours = entitlements_service.PLAN_QUOTAS[
                entitlements_service.PLAN_FREE
            ]
            plan = await entitlements_service.resolve_plan_for_user(user_id)
            token_limit, window_hours = entitlements_service.PLAN_QUOTAS[plan]
        except Exception:
            token_limit, window_hours = _DEFAULT_TOKEN_LIMIT, _DEFAULT_WINDOW_HOURS
            logger.warning(
                "Plan quota resolution failed for user %s; using free-tier quota",
                user_id,
                exc_info=True,
            )

    async with get_connection() as conn:
        # Sum tokens used within the window
        row = await conn.fetchrow(
            """
            SELECT COALESCE(SUM(total_tokens), 0) AS used
            FROM mw_token_usage_events
            WHERE user_id = $1 AND created_at > NOW() - make_interval(hours => $2)
            """,
            user_id, window_hours,
        )
        used = int(row["used"])

        # Calculate when the oldest usage in the window expires
        oldest = await conn.fetchval(
            """
            SELECT MIN(created_at) FROM mw_token_usage_events
            WHERE user_id = $1 AND created_at > NOW() - make_interval(hours => $2)
            """,
            user_id, window_hours,
        )
        from datetime import timedelta, timezone, datetime
        if oldest:
            resets_at = oldest + timedelta(hours=window_hours)
        else:
            resets_at = datetime.now(timezone.utc) + timedelta(hours=window_hours)

    return {
        "allowed": used < token_limit,
        "used": used,
        "limit": token_limit,
        "window_hours": window_hours,
        "remaining": max(0, token_limit - used),
        "resets_at": resets_at.isoformat(),
    }

async def get_token_usage_summary(
    company_id: UUID,
    user_id: UUID,
    period_days: int = 30,
) -> dict:
    async with get_connection() as conn:
        by_model_rows = await conn.fetch(
            """
            SELECT
                model,
                COALESCE(SUM(prompt_tokens), 0) AS prompt_tokens,
                COALESCE(SUM(completion_tokens), 0) AS completion_tokens,
                COALESCE(SUM(total_tokens), 0) AS total_tokens,
                COUNT(*) AS operation_count,
                COUNT(*) FILTER (WHERE estimated) AS estimated_operations,
                COALESCE(SUM(cost_dollars), 0) AS total_cost_dollars,
                MIN(created_at) AS first_seen_at,
                MAX(created_at) AS last_seen_at
            FROM mw_token_usage_events
            WHERE company_id=$1
              AND user_id=$2
              AND created_at >= NOW() - ($3::int * INTERVAL '1 day')
            GROUP BY model
            ORDER BY total_tokens DESC, model ASC
            """,
            company_id,
            user_id,
            period_days,
        )

        totals_row = await conn.fetchrow(
            """
            SELECT
                COALESCE(SUM(prompt_tokens), 0) AS prompt_tokens,
                COALESCE(SUM(completion_tokens), 0) AS completion_tokens,
                COALESCE(SUM(total_tokens), 0) AS total_tokens,
                COUNT(*) AS operation_count,
                COUNT(*) FILTER (WHERE estimated) AS estimated_operations,
                COALESCE(SUM(cost_dollars), 0) AS total_cost_dollars
            FROM mw_token_usage_events
            WHERE company_id=$1
              AND user_id=$2
              AND created_at >= NOW() - ($3::int * INTERVAL '1 day')
            """,
            company_id,
            user_id,
            period_days,
        )

    return {
        "period_days": period_days,
        "generated_at": datetime.now(timezone.utc),
        "totals": {
            "prompt_tokens": totals_row["prompt_tokens"] if totals_row else 0,
            "completion_tokens": totals_row["completion_tokens"] if totals_row else 0,
            "total_tokens": totals_row["total_tokens"] if totals_row else 0,
            "operation_count": totals_row["operation_count"] if totals_row else 0,
            "estimated_operations": totals_row["estimated_operations"] if totals_row else 0,
            "total_cost_dollars": float(totals_row["total_cost_dollars"]) if totals_row else 0,
        },
        "by_model": [
            {
                "model": row["model"],
                "prompt_tokens": row["prompt_tokens"],
                "completion_tokens": row["completion_tokens"],
                "total_tokens": row["total_tokens"],
                "operation_count": row["operation_count"],
                "estimated_operations": row["estimated_operations"],
                "total_cost_dollars": float(row["total_cost_dollars"]),
                "first_seen_at": row["first_seen_at"],
                "last_seen_at": row["last_seen_at"],
            }
            for row in by_model_rows
        ],
    }
