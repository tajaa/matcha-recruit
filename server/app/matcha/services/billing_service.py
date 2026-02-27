"""Matcha Work credit billing service."""

from __future__ import annotations

from typing import Any, Optional
from uuid import UUID

import asyncpg
from fastapi import HTTPException, status

from ...database import get_connection

INSUFFICIENT_CREDITS_MESSAGE = (
    "Insufficient credits. Purchase more credits to continue using Matcha Work."
)
INSUFFICIENT_CREDITS_CODE = "insufficient_credits"


def _insufficient_credits_exception(credits_remaining: int = 0) -> HTTPException:
    remaining = max(int(credits_remaining or 0), 0)
    return HTTPException(
        status_code=status.HTTP_402_PAYMENT_REQUIRED,
        detail={
            "message": INSUFFICIENT_CREDITS_MESSAGE,
            "detail": INSUFFICIENT_CREDITS_MESSAGE,
            "code": INSUFFICIENT_CREDITS_CODE,
            "credits_remaining": remaining,
        },
    )


def _row_to_transaction(row: asyncpg.Record) -> dict[str, Any]:
    created_by_email = row["created_by_email"] if "created_by_email" in row else None
    return {
        "id": row["id"],
        "company_id": row["company_id"],
        "transaction_type": row["transaction_type"],
        "credits_delta": int(row["credits_delta"]),
        "credits_after": int(row["credits_after"]),
        "description": row["description"],
        "reference_id": row["reference_id"],
        "created_by": row["created_by"],
        "created_by_email": created_by_email,
        "created_at": row["created_at"],
    }


def _row_to_stripe_session(row: asyncpg.Record) -> dict[str, Any]:
    return {
        "id": row["id"],
        "company_id": row["company_id"],
        "stripe_session_id": row["stripe_session_id"],
        "credit_pack_id": row["credit_pack_id"],
        "credits_to_add": int(row["credits_to_add"]),
        "amount_cents": int(row["amount_cents"]),
        "status": row["status"],
        "created_at": row["created_at"],
        "fulfilled_at": row["fulfilled_at"],
    }


async def _ensure_balance_row(conn: asyncpg.Connection, company_id: UUID) -> None:
    await conn.execute(
        """
        INSERT INTO mw_credit_balances (
            company_id,
            credits_remaining,
            total_credits_purchased,
            total_credits_granted
        )
        VALUES ($1, 0, 0, 0)
        ON CONFLICT (company_id) DO NOTHING
        """,
        company_id,
    )


async def get_credit_balance(
    company_id: UUID,
    *,
    conn: Optional[asyncpg.Connection] = None,
) -> dict[str, Any]:
    if conn is None:
        async with get_connection() as new_conn:
            return await get_credit_balance(company_id, conn=new_conn)

    await _ensure_balance_row(conn, company_id)
    row = await conn.fetchrow(
        """
        SELECT
            company_id,
            credits_remaining,
            total_credits_purchased,
            total_credits_granted,
            updated_at
        FROM mw_credit_balances
        WHERE company_id = $1
        """,
        company_id,
    )
    if row is None:
        return {
            "company_id": company_id,
            "credits_remaining": 0,
            "total_credits_purchased": 0,
            "total_credits_granted": 0,
            "updated_at": None,
        }

    return {
        "company_id": row["company_id"],
        "credits_remaining": int(row["credits_remaining"]),
        "total_credits_purchased": int(row["total_credits_purchased"]),
        "total_credits_granted": int(row["total_credits_granted"]),
        "updated_at": row["updated_at"],
    }


async def check_credits(company_id: UUID) -> bool:
    balance = await get_credit_balance(company_id)
    remaining = int(balance.get("credits_remaining") or 0)
    if remaining <= 0:
        raise _insufficient_credits_exception(remaining)
    return True


async def deduct_credit(
    conn: asyncpg.Connection,
    company_id: UUID,
    thread_id: UUID,
    user_id: UUID,
) -> dict[str, Any]:
    await _ensure_balance_row(conn, company_id)

    balance_row = await conn.fetchrow(
        """
        UPDATE mw_credit_balances
        SET credits_remaining = credits_remaining - 1,
            updated_at = NOW()
        WHERE company_id = $1
          AND credits_remaining > 0
        RETURNING credits_remaining
        """,
        company_id,
    )

    if balance_row is None:
        credits_remaining = await conn.fetchval(
            "SELECT COALESCE(credits_remaining, 0) FROM mw_credit_balances WHERE company_id = $1",
            company_id,
        )
        raise _insufficient_credits_exception(int(credits_remaining or 0))

    transaction = await conn.fetchrow(
        """
        INSERT INTO mw_credit_transactions (
            company_id,
            transaction_type,
            credits_delta,
            credits_after,
            description,
            reference_id,
            created_by
        )
        VALUES ($1, 'deduction', -1, $2, $3, $4, $5)
        RETURNING
            id,
            company_id,
            transaction_type,
            credits_delta,
            credits_after,
            description,
            reference_id,
            created_by,
            created_at
        """,
        company_id,
        int(balance_row["credits_remaining"]),
        "Matcha Work AI call",
        thread_id,
        user_id,
    )

    return _row_to_transaction(transaction)


async def grant_credits(
    company_id: UUID,
    credits: int,
    description: Optional[str],
    granted_by: UUID,
) -> dict[str, Any]:
    if credits == 0:
        raise HTTPException(status_code=400, detail="Credits delta must be non-zero")

    normalized_description = (description or "").strip() or None

    async with get_connection() as conn:
        async with conn.transaction():
            company_exists = await conn.fetchval(
                "SELECT EXISTS(SELECT 1 FROM companies WHERE id = $1)",
                company_id,
            )
            if not company_exists:
                raise HTTPException(status_code=404, detail="Company not found")

            await _ensure_balance_row(conn, company_id)

            locked_balance = await conn.fetchrow(
                """
                SELECT credits_remaining, total_credits_purchased, total_credits_granted
                FROM mw_credit_balances
                WHERE company_id = $1
                FOR UPDATE
                """,
                company_id,
            )
            current_remaining = int(locked_balance["credits_remaining"])
            next_remaining = current_remaining + int(credits)
            if next_remaining < 0:
                raise HTTPException(
                    status_code=400,
                    detail="Credit adjustment would make balance negative",
                )

            grant_delta = int(credits) if credits > 0 else 0
            await conn.execute(
                """
                UPDATE mw_credit_balances
                SET credits_remaining = $2,
                    total_credits_granted = total_credits_granted + $3,
                    updated_at = NOW()
                WHERE company_id = $1
                """,
                company_id,
                next_remaining,
                grant_delta,
            )

            transaction_type = "grant" if credits > 0 else "adjustment"
            transaction = await conn.fetchrow(
                """
                INSERT INTO mw_credit_transactions (
                    company_id,
                    transaction_type,
                    credits_delta,
                    credits_after,
                    description,
                    created_by
                )
                VALUES ($1, $2, $3, $4, $5, $6)
                RETURNING
                    id,
                    company_id,
                    transaction_type,
                    credits_delta,
                    credits_after,
                    description,
                    reference_id,
                    created_by,
                    created_at
                """,
                company_id,
                transaction_type,
                int(credits),
                next_remaining,
                normalized_description,
                granted_by,
            )

            balance = await get_credit_balance(company_id, conn=conn)

    return {
        "balance": balance,
        "transaction": _row_to_transaction(transaction),
    }


async def get_transaction_history(
    company_id: UUID,
    limit: int = 50,
    offset: int = 0,
) -> dict[str, Any]:
    safe_limit = max(1, min(int(limit), 200))
    safe_offset = max(0, int(offset))

    async with get_connection() as conn:
        rows = await conn.fetch(
            """
            SELECT
                t.id,
                t.company_id,
                t.transaction_type,
                t.credits_delta,
                t.credits_after,
                t.description,
                t.reference_id,
                t.created_by,
                u.email AS created_by_email,
                t.created_at
            FROM mw_credit_transactions t
            LEFT JOIN users u ON u.id = t.created_by
            WHERE t.company_id = $1
            ORDER BY t.created_at DESC
            LIMIT $2
            OFFSET $3
            """,
            company_id,
            safe_limit,
            safe_offset,
        )
        total = await conn.fetchval(
            "SELECT COUNT(*) FROM mw_credit_transactions WHERE company_id = $1",
            company_id,
        )

    return {
        "items": [_row_to_transaction(r) for r in rows],
        "total": int(total or 0),
        "limit": safe_limit,
        "offset": safe_offset,
    }


async def create_pending_stripe_session(
    company_id: UUID,
    stripe_session_id: str,
    credit_pack_id: str,
    credits_to_add: int,
    amount_cents: int,
) -> dict[str, Any]:
    async with get_connection() as conn:
        row = await conn.fetchrow(
            """
            INSERT INTO mw_stripe_sessions (
                company_id,
                stripe_session_id,
                credit_pack_id,
                credits_to_add,
                amount_cents,
                status
            )
            VALUES ($1, $2, $3, $4, $5, 'pending')
            ON CONFLICT (stripe_session_id) DO UPDATE
            SET
                company_id = EXCLUDED.company_id,
                credit_pack_id = EXCLUDED.credit_pack_id,
                credits_to_add = EXCLUDED.credits_to_add,
                amount_cents = EXCLUDED.amount_cents,
                status = CASE
                    WHEN mw_stripe_sessions.status = 'completed' THEN mw_stripe_sessions.status
                    ELSE 'pending'
                END
            RETURNING
                id,
                company_id,
                stripe_session_id,
                credit_pack_id,
                credits_to_add,
                amount_cents,
                status,
                created_at,
                fulfilled_at
            """,
            company_id,
            stripe_session_id,
            credit_pack_id,
            int(credits_to_add),
            int(amount_cents),
        )

    return _row_to_stripe_session(row)


async def fulfill_checkout_session(stripe_session_id: str) -> Optional[dict[str, Any]]:
    async with get_connection() as conn:
        async with conn.transaction():
            session_row = await conn.fetchrow(
                """
                SELECT
                    id,
                    company_id,
                    stripe_session_id,
                    credit_pack_id,
                    credits_to_add,
                    amount_cents,
                    status,
                    created_at,
                    fulfilled_at
                FROM mw_stripe_sessions
                WHERE stripe_session_id = $1
                FOR UPDATE
                """,
                stripe_session_id,
            )
            if session_row is None:
                return None

            if session_row["status"] == "completed":
                balance = await get_credit_balance(session_row["company_id"], conn=conn)
                return {
                    "already_fulfilled": True,
                    "session": _row_to_stripe_session(session_row),
                    "balance": balance,
                    "transaction": None,
                }

            await _ensure_balance_row(conn, session_row["company_id"])
            locked_balance = await conn.fetchrow(
                """
                SELECT credits_remaining
                FROM mw_credit_balances
                WHERE company_id = $1
                FOR UPDATE
                """,
                session_row["company_id"],
            )

            current_remaining = int(locked_balance["credits_remaining"])
            credits_to_add = int(session_row["credits_to_add"])
            next_remaining = current_remaining + credits_to_add

            await conn.execute(
                """
                UPDATE mw_credit_balances
                SET credits_remaining = $2,
                    total_credits_purchased = total_credits_purchased + $3,
                    updated_at = NOW()
                WHERE company_id = $1
                """,
                session_row["company_id"],
                next_remaining,
                credits_to_add,
            )

            description = f"Stripe purchase ({session_row['credit_pack_id']})"
            transaction = await conn.fetchrow(
                """
                INSERT INTO mw_credit_transactions (
                    company_id,
                    transaction_type,
                    credits_delta,
                    credits_after,
                    description,
                    reference_id,
                    created_by
                )
                VALUES ($1, 'purchase', $2, $3, $4, $5, NULL)
                RETURNING
                    id,
                    company_id,
                    transaction_type,
                    credits_delta,
                    credits_after,
                    description,
                    reference_id,
                    created_by,
                    created_at
                """,
                session_row["company_id"],
                credits_to_add,
                next_remaining,
                description,
                session_row["id"],
            )

            fulfilled_row = await conn.fetchrow(
                """
                UPDATE mw_stripe_sessions
                SET status = 'completed',
                    fulfilled_at = NOW()
                WHERE stripe_session_id = $1
                RETURNING
                    id,
                    company_id,
                    stripe_session_id,
                    credit_pack_id,
                    credits_to_add,
                    amount_cents,
                    status,
                    created_at,
                    fulfilled_at
                """,
                stripe_session_id,
            )

            balance = await get_credit_balance(session_row["company_id"], conn=conn)

    return {
        "already_fulfilled": False,
        "session": _row_to_stripe_session(fulfilled_row),
        "balance": balance,
        "transaction": _row_to_transaction(transaction),
    }


async def get_active_subscription(company_id: UUID) -> Optional[dict[str, Any]]:
    """Return the active subscription for a company, or None."""
    async with get_connection() as conn:
        row = await conn.fetchrow(
            """
            SELECT id, company_id, stripe_subscription_id, stripe_customer_id,
                   pack_id, credits_per_cycle, amount_cents, status,
                   current_period_end, created_at, canceled_at
            FROM mw_subscriptions
            WHERE company_id = $1
              AND status IN ('active', 'past_due')
            ORDER BY created_at DESC
            LIMIT 1
            """,
            company_id,
        )
    if row is None:
        return None
    return dict(row)


async def upsert_subscription(
    company_id: UUID,
    stripe_subscription_id: str,
    stripe_customer_id: str,
    pack_id: str,
    credits_per_cycle: int,
    amount_cents: int,
    current_period_end=None,
) -> dict[str, Any]:
    """Create or update a subscription record."""
    async with get_connection() as conn:
        row = await conn.fetchrow(
            """
            INSERT INTO mw_subscriptions (
                company_id, stripe_subscription_id, stripe_customer_id,
                pack_id, credits_per_cycle, amount_cents, status, current_period_end
            )
            VALUES ($1, $2, $3, $4, $5, $6, 'active', $7)
            ON CONFLICT (stripe_subscription_id) DO UPDATE
            SET status = 'active',
                current_period_end = EXCLUDED.current_period_end,
                canceled_at = NULL
            RETURNING id, company_id, stripe_subscription_id, stripe_customer_id,
                      pack_id, credits_per_cycle, amount_cents, status,
                      current_period_end, created_at, canceled_at
            """,
            company_id,
            stripe_subscription_id,
            stripe_customer_id,
            pack_id,
            credits_per_cycle,
            amount_cents,
            current_period_end,
        )
    return dict(row)


async def cancel_subscription_record(stripe_subscription_id: str) -> bool:
    """Mark a subscription as canceled."""
    async with get_connection() as conn:
        result = await conn.execute(
            """
            UPDATE mw_subscriptions
            SET status = 'canceled', canceled_at = NOW()
            WHERE stripe_subscription_id = $1
              AND status != 'canceled'
            """,
            stripe_subscription_id,
        )
    return result.endswith("1")


async def fulfill_subscription_invoice(
    stripe_subscription_id: str,
    stripe_invoice_id: str,
) -> Optional[dict[str, Any]]:
    """Add credits for a paid subscription invoice. Idempotent via reference_id check."""
    async with get_connection() as conn:
        async with conn.transaction():
            sub_row = await conn.fetchrow(
                """
                SELECT company_id, pack_id, credits_per_cycle, amount_cents
                FROM mw_subscriptions
                WHERE stripe_subscription_id = $1
                """,
                stripe_subscription_id,
            )
            if sub_row is None:
                return None

            # Idempotency: skip if this invoice was already processed
            already = await conn.fetchval(
                """
                SELECT id FROM mw_credit_transactions
                WHERE company_id = $1
                  AND transaction_type = 'purchase'
                  AND description LIKE $2
                LIMIT 1
                """,
                sub_row["company_id"],
                f"%{stripe_invoice_id}%",
            )
            if already:
                return {"already_fulfilled": True}

            company_id = sub_row["company_id"]
            credits_to_add = int(sub_row["credits_per_cycle"])

            await _ensure_balance_row(conn, company_id)
            locked = await conn.fetchrow(
                "SELECT credits_remaining FROM mw_credit_balances WHERE company_id = $1 FOR UPDATE",
                company_id,
            )
            next_remaining = int(locked["credits_remaining"]) + credits_to_add

            await conn.execute(
                """
                UPDATE mw_credit_balances
                SET credits_remaining = $2,
                    total_credits_purchased = total_credits_purchased + $3,
                    updated_at = NOW()
                WHERE company_id = $1
                """,
                company_id,
                next_remaining,
                credits_to_add,
            )

            transaction = await conn.fetchrow(
                """
                INSERT INTO mw_credit_transactions (
                    company_id, transaction_type, credits_delta, credits_after,
                    description, created_by
                )
                VALUES ($1, 'purchase', $2, $3, $4, NULL)
                RETURNING id, company_id, transaction_type, credits_delta,
                          credits_after, description, reference_id, created_by, created_at
                """,
                company_id,
                credits_to_add,
                next_remaining,
                f"Auto-renewal ({sub_row['pack_id']}) — invoice {stripe_invoice_id}",
            )

            balance = await get_credit_balance(company_id, conn=conn)

    return {
        "already_fulfilled": False,
        "balance": balance,
        "transaction": _row_to_transaction(transaction),
    }


async def mark_stripe_session_expired(stripe_session_id: str) -> bool:
    async with get_connection() as conn:
        result = await conn.execute(
            """
            UPDATE mw_stripe_sessions
            SET status = 'expired'
            WHERE stripe_session_id = $1
              AND status = 'pending'
            """,
            stripe_session_id,
        )
    return result.endswith("1")
