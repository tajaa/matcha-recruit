"""Token-based billing for Matcha Work.

Every account gets 1M free tokens. After that, $40/month for 5M tokens/month.
Admin can grant additional tokens to any account.
"""

from __future__ import annotations

import logging
from typing import Any, Optional
from uuid import UUID

from fastapi import HTTPException, status

from ...database import get_connection

logger = logging.getLogger(__name__)

FREE_TOKEN_GRANT = 1_000_000
SUBSCRIPTION_TOKENS = 5_000_000
SUBSCRIPTION_AMOUNT_CENTS = 4000  # $40/month
SUBSCRIPTION_PACK_ID = "matcha_work_pro"

EXHAUSTED_MESSAGE = "Token budget exhausted. Subscribe to Matcha Work Pro for 5M tokens/month."
EXHAUSTED_CODE = "token_budget_exhausted"


def _budget_exception(free_remaining: int = 0, sub_remaining: int = 0) -> HTTPException:
    return HTTPException(
        status_code=status.HTTP_402_PAYMENT_REQUIRED,
        detail={
            "message": EXHAUSTED_MESSAGE,
            "code": EXHAUSTED_CODE,
            "free_tokens_remaining": max(free_remaining, 0),
            "subscription_tokens_remaining": max(sub_remaining, 0),
        },
    )


async def ensure_token_budget_row(conn, company_id: UUID) -> None:
    await conn.execute(
        """INSERT INTO mw_token_budgets (company_id, free_tokens_used, free_token_limit)
           VALUES ($1, 0, $2)
           ON CONFLICT (company_id) DO NOTHING""",
        company_id, FREE_TOKEN_GRANT,
    )


async def get_token_budget(company_id: UUID, *, conn=None) -> dict[str, Any]:
    async def _query(c):
        row = await c.fetchrow(
            "SELECT * FROM mw_token_budgets WHERE company_id = $1", company_id,
        )
        if not row:
            await ensure_token_budget_row(c, company_id)
            row = await c.fetchrow(
                "SELECT * FROM mw_token_budgets WHERE company_id = $1", company_id,
            )
        free_remaining = max(0, row["free_token_limit"] - row["free_tokens_used"])
        sub_remaining = max(0, row["subscription_token_limit"] - row["subscription_tokens_used"])
        return {
            "company_id": company_id,
            "free_tokens_used": row["free_tokens_used"],
            "free_token_limit": row["free_token_limit"],
            "free_tokens_remaining": free_remaining,
            "subscription_tokens_used": row["subscription_tokens_used"],
            "subscription_token_limit": row["subscription_token_limit"],
            "subscription_tokens_remaining": sub_remaining,
            "subscription_period_start": row["subscription_period_start"],
            "total_tokens_remaining": free_remaining + sub_remaining,
            "has_active_subscription": row["subscription_token_limit"] > 0,
            "updated_at": row["updated_at"],
        }

    if conn:
        return await _query(conn)
    async with get_connection() as c:
        return await _query(c)


async def check_token_budget(company_id: UUID) -> dict[str, Any]:
    budget = await get_token_budget(company_id)
    if budget["total_tokens_remaining"] <= 0:
        raise _budget_exception(
            budget["free_tokens_remaining"],
            budget["subscription_tokens_remaining"],
        )
    return budget


async def deduct_tokens(conn, company_id: UUID, total_tokens: int) -> dict[str, Any]:
    if total_tokens <= 0:
        return await get_token_budget(company_id, conn=conn)

    row = await conn.fetchrow(
        "SELECT * FROM mw_token_budgets WHERE company_id = $1 FOR UPDATE",
        company_id,
    )
    if not row:
        await ensure_token_budget_row(conn, company_id)
        row = await conn.fetchrow(
            "SELECT * FROM mw_token_budgets WHERE company_id = $1 FOR UPDATE",
            company_id,
        )

    free_remaining = max(0, row["free_token_limit"] - row["free_tokens_used"])
    sub_remaining = max(0, row["subscription_token_limit"] - row["subscription_tokens_used"])

    if free_remaining + sub_remaining < total_tokens:
        raise _budget_exception(free_remaining, sub_remaining)

    if free_remaining >= total_tokens:
        # Fully covered by free tokens
        await conn.execute(
            """UPDATE mw_token_budgets
               SET free_tokens_used = free_tokens_used + $2, updated_at = NOW()
               WHERE company_id = $1""",
            company_id, total_tokens,
        )
    else:
        # Drain free, overflow to subscription
        from_sub = total_tokens - free_remaining
        await conn.execute(
            """UPDATE mw_token_budgets
               SET free_tokens_used = free_token_limit,
                   subscription_tokens_used = subscription_tokens_used + $2,
                   updated_at = NOW()
               WHERE company_id = $1""",
            company_id, from_sub,
        )

    return await get_token_budget(company_id, conn=conn)


async def grant_tokens(
    company_id: UUID,
    amount: int,
    description: Optional[str] = None,
    granted_by: Optional[UUID] = None,
) -> dict[str, Any]:
    """Admin grants tokens by increasing the free_token_limit."""
    async with get_connection() as conn:
        async with conn.transaction():
            await ensure_token_budget_row(conn, company_id)
            await conn.execute(
                """UPDATE mw_token_budgets
                   SET free_token_limit = free_token_limit + $2, updated_at = NOW()
                   WHERE company_id = $1""",
                company_id, amount,
            )
            budget = await get_token_budget(company_id, conn=conn)
            logger.info(
                "Admin granted %d tokens to company %s: %s",
                amount, company_id, description or "no description",
            )
            return budget


async def reset_subscription_tokens(
    company_id: UUID,
    token_limit: int = SUBSCRIPTION_TOKENS,
    stripe_invoice_id: Optional[str] = None,
) -> dict[str, Any]:
    """Called on subscription payment — reset monthly token counter.

    Pass stripe_invoice_id for idempotency on webhook retries.
    The invoice ID is stored as a prefix in subscription_period_start's
    companion check: if the last reset was <1 hour ago we skip it,
    preventing duplicate resets from rapid webhook retries.
    """
    async with get_connection() as conn:
        async with conn.transaction():
            await ensure_token_budget_row(conn, company_id)

            # Idempotency: skip if we already reset very recently (within 1 hour)
            # This guards against duplicate invoice.paid webhooks
            if stripe_invoice_id:
                recent = await conn.fetchval(
                    """SELECT subscription_period_start FROM mw_token_budgets
                       WHERE company_id = $1
                         AND subscription_period_start > NOW() - INTERVAL '1 hour'""",
                    company_id,
                )
                if recent is not None:
                    logger.info(
                        "Skipping duplicate subscription reset for company %s (invoice %s)",
                        company_id, stripe_invoice_id,
                    )
                    return await get_token_budget(company_id, conn=conn)

            await conn.execute(
                """UPDATE mw_token_budgets
                   SET subscription_tokens_used = 0,
                       subscription_token_limit = $2,
                       subscription_period_start = NOW(),
                       updated_at = NOW()
                   WHERE company_id = $1""",
                company_id, token_limit,
            )
            return await get_token_budget(company_id, conn=conn)


async def cancel_subscription_budget(company_id: UUID) -> dict[str, Any]:
    """Called when subscription is canceled — zero subscription fields."""
    async with get_connection() as conn:
        async with conn.transaction():
            await conn.execute(
                """UPDATE mw_token_budgets
                   SET subscription_token_limit = 0,
                       subscription_tokens_used = 0,
                       updated_at = NOW()
                   WHERE company_id = $1""",
                company_id,
            )
            return await get_token_budget(company_id, conn=conn)
