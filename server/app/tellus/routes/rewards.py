"""Tell-Us consumer rewards — balance, ledger, redemptions, notifications.

The actual redeem action lives in marketplace.py (it operates on a listing).
"""
from typing import Optional
from uuid import UUID

from fastapi import APIRouter, Depends, Query, status

from ...database import get_connection
from ..dependencies import require_consumer, require_tellus_account
from ..models.tellus import (
    TellusAccount,
    TellusLedgerEntry,
    TellusNotification,
    TellusPointsBalance,
    TellusRedemption,
)
from ..services.points_service import level_progress
from ..services.marketplace_service import serialize_redemption

router = APIRouter()


@router.get("/rewards/balance", response_model=TellusPointsBalance)
async def get_balance(account: TellusAccount = Depends(require_consumer)):
    async with get_connection() as conn:
        row = await conn.fetchrow(
            "SELECT * FROM tellus_points_balances WHERE account_id = $1", account.id
        )
        if row is None:
            await conn.execute(
                "INSERT INTO tellus_points_balances (account_id) VALUES ($1) ON CONFLICT DO NOTHING",
                account.id,
            )
            row = await conn.fetchrow(
                "SELECT * FROM tellus_points_balances WHERE account_id = $1", account.id
            )
    prog = level_progress(row["lifetime_points"])
    return TellusPointsBalance(
        account_id=account.id,
        points_balance=row["points_balance"],
        lifetime_points=row["lifetime_points"],
        level=prog["level"],
        current_streak=row["current_streak"],
        longest_streak=row["longest_streak"],
        last_activity_date=row["last_activity_date"],
        points_to_next_level=prog["points_to_next_level"],
        level_floor=prog["level_floor"],
        level_ceiling=prog["level_ceiling"],
    )


@router.get("/rewards/ledger", response_model=list[TellusLedgerEntry])
async def get_ledger(
    account: TellusAccount = Depends(require_consumer),
    limit: int = Query(default=50, ge=1, le=200),
    offset: int = Query(default=0, ge=0),
):
    async with get_connection() as conn:
        rows = await conn.fetch(
            """SELECT id, delta, balance_after, reason, reference_type, reference_id, description, created_at
               FROM tellus_points_ledger WHERE account_id = $1
               ORDER BY created_at DESC LIMIT $2 OFFSET $3""",
            account.id, limit, offset,
        )
    return [TellusLedgerEntry(**dict(r)) for r in rows]


@router.get("/redemptions", response_model=list[TellusRedemption])
async def list_redemptions(account: TellusAccount = Depends(require_consumer)):
    async with get_connection() as conn:
        rows = await conn.fetch(
            """SELECT r.*, l.title AS listing_title
               FROM tellus_redemptions r
               JOIN tellus_reward_listings l ON l.id = r.listing_id
               WHERE r.account_id = $1 ORDER BY r.created_at DESC""",
            account.id,
        )
    return [serialize_redemption(r) for r in rows]


# ── Notifications (both sides) ──────────────────────────────────────────────────

@router.get("/notifications", response_model=list[TellusNotification])
async def list_notifications(
    account: TellusAccount = Depends(require_tellus_account),
    unread_only: bool = Query(default=False),
    limit: int = Query(default=30, ge=1, le=100),
):
    async with get_connection() as conn:
        rows = await conn.fetch(
            """SELECT id, kind, title, body, reference_type, reference_id, is_read, created_at
               FROM tellus_notifications
               WHERE account_id = $1 AND ($2 = FALSE OR is_read = FALSE)
               ORDER BY created_at DESC LIMIT $3""",
            account.id, unread_only, limit,
        )
    return [TellusNotification(**dict(r)) for r in rows]


@router.post("/notifications/read", status_code=status.HTTP_204_NO_CONTENT)
async def mark_notifications_read(
    account: TellusAccount = Depends(require_tellus_account),
    notification_id: Optional[UUID] = Query(default=None),
):
    """Mark one notification read (notification_id) or all of them (omit it)."""
    async with get_connection() as conn:
        if notification_id is not None:
            await conn.execute(
                "UPDATE tellus_notifications SET is_read = TRUE WHERE id = $1 AND account_id = $2",
                notification_id, account.id,
            )
        else:
            await conn.execute(
                "UPDATE tellus_notifications SET is_read = TRUE WHERE account_id = $1 AND is_read = FALSE",
                account.id,
            )
