"""Tell-Us internal admin — account list/detail + lifecycle actions
(suspend/unsuspend/force-logout/verify-email/password-reset/points-adjust).
"""
import secrets
from typing import Optional
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query

from ....database import get_connection
from ...dependencies import require_tellus_admin
from ...models.tellus import TellusAccount
from .._shared import effective_review_state
from ...services.admin_audit import record_admin_action
from ...services.email import app_url
from ...services.marketplace_service import effective_redemption_status
from ...services.points_service import AdjustError, adjust_points
from ...models.admin import (
    TellusAdminAccountDetail,
    TellusAdminAccountList,
    TellusAdminAccountSummary,
    TellusAdminAuditEntry,
    TellusAdminLedgerEntry,
    TellusAdminPasswordResetResponse,
    TellusAdminPointsAdjust,
    TellusAdminSuspendRequest,
)
from ._shared import account_filter_sql, decode_audit_rows

router = APIRouter(dependencies=[Depends(require_tellus_admin)])

_ACCOUNT_SELECT = """
    SELECT a.id, a.email, a.display_name, a.account_type, a.status,
           (a.email_verified_at IS NOT NULL) AS email_verified, a.city, a.state, a.created_at,
           COALESCE(pb.points_balance, 0) AS points_balance,
           (SELECT COUNT(*) FROM tellus_reports r WHERE r.reporter_account_id = a.id) AS report_count,
           b.id AS brand_id, b.name AS brand_name
    FROM tellus_accounts a
    LEFT JOIN tellus_points_balances pb ON pb.account_id = a.id
    LEFT JOIN tellus_brands b ON b.owner_account_id = a.id
"""


def _row_to_summary(row) -> TellusAdminAccountSummary:
    return TellusAdminAccountSummary(**dict(row))


def _report_row_to_dict(row) -> dict:
    """review_state is EFFECTIVE (mirrors /admin/reports' serialize_reports),
    not the raw column — a held-but-past-publish_at review must read the same
    way here as it does on the moderation queue."""
    d = dict(row)
    d["review_state"] = effective_review_state(row)
    d.pop("publish_at", None)
    return d


@router.get("/admin/accounts", response_model=TellusAdminAccountList)
async def list_accounts(
    q: Optional[str] = None,
    account_type: Optional[str] = None,
    status: Optional[str] = None,
    verified: Optional[bool] = None,
    limit: int = Query(50, ge=1, le=100),
    offset: int = Query(0, ge=0),
):
    where, params = account_filter_sql(q=q, account_type=account_type, status=status, verified=verified)
    async with get_connection() as conn:
        rows = await conn.fetch(
            f"{_ACCOUNT_SELECT}{where} ORDER BY a.created_at DESC LIMIT ${len(params) + 1} OFFSET ${len(params) + 2}",
            *params, limit, offset,
        )
        total = await conn.fetchval(f"SELECT COUNT(*) FROM tellus_accounts a{where}", *params)
    return TellusAdminAccountList(
        items=[_row_to_summary(r) for r in rows], total=total, limit=limit, offset=offset,
    )


@router.get("/admin/accounts/{account_id}", response_model=TellusAdminAccountDetail)
async def get_account_detail(account_id: UUID):
    async with get_connection() as conn:
        row = await conn.fetchrow(f"{_ACCOUNT_SELECT} WHERE a.id = $1", account_id)
        if row is None:
            raise HTTPException(404, "Account not found")

        bal = await conn.fetchrow(
            "SELECT lifetime_points, level, current_streak FROM tellus_points_balances WHERE account_id = $1",
            account_id,
        )

        ledger_rows = await conn.fetch(
            "SELECT id, delta, balance_after, reason, event_key, reference_type, reference_id, "
            "description, created_at FROM tellus_points_ledger WHERE account_id = $1 "
            "ORDER BY created_at DESC LIMIT 20",
            account_id,
        )

        report_rows = await conn.fetch(
            "SELECT r.id, b.name AS brand_name, r.title, r.rating, r.review_state, r.publish_at, "
            "r.moderation_status, r.created_at FROM tellus_reports r "
            "LEFT JOIN tellus_brands b ON b.id = r.brand_id "
            "WHERE r.reporter_account_id = $1 ORDER BY r.created_at DESC LIMIT 10",
            account_id,
        )

        redemption_rows = await conn.fetch(
            "SELECT rd.id, l.title AS listing_title, rd.points_spent, rd.status, rd.expires_at, rd.created_at "
            "FROM tellus_redemptions rd JOIN tellus_reward_listings l ON l.id = rd.listing_id "
            "WHERE rd.account_id = $1 ORDER BY rd.created_at DESC LIMIT 10",
            account_id,
        )

        dm_rows = await conn.fetch(
            "SELECT t.id, b.name AS brand_name, (t.blocked_at IS NOT NULL) AS blocked, t.last_message_at "
            "FROM tellus_dm_threads t JOIN tellus_brands b ON b.id = t.brand_id "
            "WHERE t.consumer_account_id = $1 ORDER BY t.last_message_at DESC NULLS LAST LIMIT 10",
            account_id,
        )

        audit_rows = await conn.fetch(
            "SELECT id, actor_email, action, target_type, target_id, detail, created_at "
            "FROM tellus_admin_audit WHERE target_type = 'account' AND target_id = $1 "
            "ORDER BY created_at DESC LIMIT 10",
            str(account_id),
        )

    return TellusAdminAccountDetail(
        account=_row_to_summary(row),
        lifetime_points=bal["lifetime_points"] if bal else 0,
        level=bal["level"] if bal else 1,
        current_streak=bal["current_streak"] if bal else 0,
        ledger=[TellusAdminLedgerEntry(**dict(r)) for r in ledger_rows],
        recent_reports=[_report_row_to_dict(r) for r in report_rows],
        redemptions=[{**dict(r), "status": effective_redemption_status(r)} for r in redemption_rows],
        dm_threads=[dict(r) for r in dm_rows],
        audit=[TellusAdminAuditEntry(**d) for d in decode_audit_rows(audit_rows)],
    )


@router.post("/admin/accounts/{account_id}/suspend")
async def suspend_account(
    account_id: UUID, body: TellusAdminSuspendRequest,
    admin: TellusAccount = Depends(require_tellus_admin),
):
    if account_id == admin.id:
        raise HTTPException(400, "You can't suspend your own account.")
    async with get_connection() as conn:
        async with conn.transaction():
            old = await conn.fetchrow("SELECT status FROM tellus_accounts WHERE id = $1", account_id)
            if old is None:
                raise HTTPException(404, "Account not found")
            await conn.execute(
                "UPDATE tellus_accounts SET status = 'suspended', updated_at = NOW() WHERE id = $1",
                account_id,
            )
            await record_admin_action(
                conn, admin, "account.suspend", "account", account_id,
                {"reason": body.reason, "previous_status": old["status"]},
            )
    return {"status": "suspended"}


@router.post("/admin/accounts/{account_id}/unsuspend")
async def unsuspend_account(
    account_id: UUID, admin: TellusAccount = Depends(require_tellus_admin),
):
    async with get_connection() as conn:
        async with conn.transaction():
            result = await conn.execute(
                "UPDATE tellus_accounts SET status = 'active', updated_at = NOW() WHERE id = $1",
                account_id,
            )
            if result == "UPDATE 0":
                raise HTTPException(404, "Account not found")
            await record_admin_action(conn, admin, "account.unsuspend", "account", account_id, None)
    return {"status": "active"}


@router.post("/admin/accounts/{account_id}/force-logout")
async def force_logout(
    account_id: UUID, admin: TellusAccount = Depends(require_tellus_admin),
):
    async with get_connection() as conn:
        async with conn.transaction():
            result = await conn.execute(
                "UPDATE tellus_accounts SET tokens_valid_after = NOW(), updated_at = NOW() WHERE id = $1",
                account_id,
            )
            if result == "UPDATE 0":
                raise HTTPException(404, "Account not found")
            await record_admin_action(conn, admin, "account.force_logout", "account", account_id, None)
    return {"ok": True}


@router.post("/admin/accounts/{account_id}/verify-email")
async def verify_email(
    account_id: UUID, admin: TellusAccount = Depends(require_tellus_admin),
):
    async with get_connection() as conn:
        async with conn.transaction():
            result = await conn.execute(
                "UPDATE tellus_accounts SET email_verified_at = COALESCE(email_verified_at, NOW()), "
                "verification_token = NULL, updated_at = NOW() WHERE id = $1",
                account_id,
            )
            if result == "UPDATE 0":
                raise HTTPException(404, "Account not found")
            await record_admin_action(conn, admin, "account.verify_email", "account", account_id, None)
    return {"ok": True}


@router.post("/admin/accounts/{account_id}/password-reset", response_model=TellusAdminPasswordResetResponse)
async def issue_password_reset(
    account_id: UUID, admin: TellusAccount = Depends(require_tellus_admin),
):
    token = secrets.token_urlsafe(48)
    async with get_connection() as conn:
        async with conn.transaction():
            exists = await conn.fetchval("SELECT 1 FROM tellus_accounts WHERE id = $1", account_id)
            if not exists:
                raise HTTPException(404, "Account not found")
            await conn.execute(
                """INSERT INTO tellus_password_reset_tokens (account_id, token, expires_at, created_by_email)
                   VALUES ($1, $2, NOW() + INTERVAL '1 hour', $3)""",
                account_id, token, admin.email,
            )
            # Token deliberately excluded from the audit detail.
            await record_admin_action(conn, admin, "account.password_reset_issued", "account", account_id, None)
    return TellusAdminPasswordResetResponse(reset_url=app_url(f"/reset-password?token={token}"))


@router.post("/admin/accounts/{account_id}/points-adjust")
async def points_adjust(
    account_id: UUID, body: TellusAdminPointsAdjust,
    admin: TellusAccount = Depends(require_tellus_admin),
):
    reference_id = f"adm:{body.idempotency_key}" if body.idempotency_key else None
    async with get_connection() as conn:
        async with conn.transaction():
            exists = await conn.fetchval("SELECT 1 FROM tellus_accounts WHERE id = $1", account_id)
            if not exists:
                raise HTTPException(404, "Account not found")
            try:
                result = await adjust_points(
                    conn, account_id, body.delta,
                    description=body.description, reference_id=reference_id, clamp=body.clamp,
                )
            except AdjustError as exc:
                raise HTTPException(409, str(exc))
            except ValueError as exc:
                raise HTTPException(422, str(exc))
            if result["adjusted"]:
                # A replayed idempotency_key is a no-op, not a new admin action.
                await record_admin_action(
                    conn, admin, "account.points_adjust", "account", account_id,
                    {
                        "delta": body.delta, "applied_delta": result["applied_delta"],
                        "description": body.description, "balance_after": result["balance"],
                    },
                )
    return result
