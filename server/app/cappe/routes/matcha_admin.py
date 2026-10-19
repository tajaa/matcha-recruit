"""Matcha admin (hey-matcha.com/admin/cappe): change an account's plan, and
make signup-grant links.

In the Cappe package but behind matcha's `require_admin` (cappe → core is the
allowed import direction), so a plan change goes through the same
`billing.grant_comp` / `end_comp` the rest of Cappe uses instead of a copy of
them in core. Mounted at /matcha-admin, apart from /admin/*, which is the
in-Cappe platform admin: a Cappe identity, a different auth realm.

Every plan an admin gives is a comp, never a charge: it shows as "free until"
on the account's billing page and in reports, and `cappe_comp_expiry` ends it
on its date. Audited like core's Cappe admin (`admin/cappe_creators.py`):
`actor_account_id` NULL, a `matcha:` action, the admin's email in the payload.
"""
import json
from datetime import datetime, timedelta, timezone
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, status

from ...core.dependencies import require_admin
from ...database import get_connection
from ..models.cappe import (
    CappeAdminPlanChange,
    CappeAdminSignupGrant,
    CappeSignupGrantCreate,
)
from ..services import billing as billing_svc
from ..services import signup_grants

router = APIRouter()


async def _audit(conn, admin, action: str, target: str, payload: dict) -> None:
    await conn.execute(
        "INSERT INTO cappe_admin_audit (actor_account_id, action, target, payload) "
        "VALUES (NULL, $1, $2, $3::jsonb)",
        f"matcha:{action}", target,
        json.dumps({**payload, "admin_email": admin.email}, default=str),
    )


@router.get("/plans")
async def list_plans():
    """Every plan an admin can put an account on, free included. Legacy plans
    are listed so an account on one can be kept there; archived ones aren't."""
    async with get_connection() as conn:
        rows = await conn.fetch(
            "SELECT code, name, status FROM cappe_billing_products "
            "WHERE kind = 'plan' AND status <> 'archived' ORDER BY sort_order, code"
        )
    return [dict(r) for r in rows]


@router.post("/accounts/{account_id}/plan")
async def set_account_plan(
    account_id: UUID, body: CappeAdminPlanChange, admin=Depends(require_admin),
):
    """Upgrade or downgrade an account by hand.

    Free ends any comp and puts the account on free. Any other plan is a comp
    until `until` (or until changed again). Refused with 409 when the account
    pays through Stripe: changing the plan here would leave Stripe billing for
    one plan while the account holds another.
    """
    if body.until is not None and body.until <= datetime.now(timezone.utc):
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="The end date must be in the future.",
        )
    to_free = body.plan_code == billing_svc.FREE_PLAN_CODE
    async with get_connection() as conn:
        plan = await conn.fetchval(
            "SELECT code FROM cappe_billing_products "
            "WHERE code = $1 AND kind = 'plan' AND status <> 'archived'",
            body.plan_code,
        )
        if plan is None:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Unknown plan")
        previous = await conn.fetchval("SELECT plan FROM cappe_accounts WHERE id = $1", account_id)
        if previous is None:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Unknown account")
        try:
            async with conn.transaction():
                if to_free:
                    await billing_svc.end_comp(conn, account_id=account_id)
                else:
                    await billing_svc.grant_comp(
                        conn, account_id=account_id, plan_code=body.plan_code,
                        until=body.until, reason=body.reason or f"Set by {admin.email}",
                    )
                await _audit(conn, admin, "account.plan", str(account_id), {
                    "from": previous, "to": body.plan_code,
                    "until": None if to_free else body.until, "reason": body.reason,
                })
        except billing_svc.LiveSubscriptionExists as exc:
            raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(exc)) from exc
    return {
        "plan": body.plan_code,
        "comped_until": None if to_free else body.until,
    }


_GRANT_LIST = """
    SELECT g.*, p.name AS plan_name,
           COALESCE(json_agg(json_build_object(
               'id', a.id, 'email', a.email, 'plan', a.plan,
               'signed_up_at', a.created_at, 'redeemed_at', a.signup_grant_redeemed_at
           ) ORDER BY a.created_at) FILTER (WHERE a.id IS NOT NULL), '[]') AS accounts
      FROM cappe_signup_grants g
      JOIN cappe_billing_products p ON p.code = g.plan_code
      LEFT JOIN cappe_accounts a ON a.signup_grant_id = g.id
"""


def _grant_out(row) -> CappeAdminSignupGrant:
    data = dict(row)
    accounts = data.pop("accounts", None) or []
    if isinstance(accounts, str):
        accounts = json.loads(accounts)
    return CappeAdminSignupGrant(
        **data, accounts=accounts, signup_url=signup_grants.signup_url(data["token"]),
    )


@router.get("/signup-grants", response_model=list[CappeAdminSignupGrant])
async def list_signup_grants():
    async with get_connection() as conn:
        rows = await conn.fetch(
            f"{_GRANT_LIST} GROUP BY g.id, p.name ORDER BY g.created_at DESC LIMIT 200"
        )
    return [_grant_out(r) for r in rows]


@router.post(
    "/signup-grants", response_model=CappeAdminSignupGrant, status_code=status.HTTP_201_CREATED,
)
async def create_signup_grant(body: CappeSignupGrantCreate, admin=Depends(require_admin)):
    """Make a link that starts new accounts on a paid plan, free for `days`
    from when each confirms its email. No card is asked for; when the days run
    out the account drops to free and has to subscribe to keep the plan."""
    expires_at = (
        datetime.now(timezone.utc) + timedelta(days=body.link_valid_days)
        if body.link_valid_days else None
    )
    async with get_connection() as conn:
        plan = await conn.fetchval(
            "SELECT code FROM cappe_billing_products "
            "WHERE code = $1 AND kind = 'plan' AND status = 'active' AND code <> $2",
            body.plan_code, billing_svc.FREE_PLAN_CODE,
        )
        if plan is None:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Pick a paid plan that is on sale.",
            )
        async with conn.transaction():
            grant_id = await conn.fetchval(
                """
                INSERT INTO cappe_signup_grants
                    (token, plan_code, days, max_redemptions, email, note, expires_at,
                     created_by_email)
                VALUES ($1, $2, $3, $4, $5, $6, $7, $8)
                RETURNING id
                """,
                signup_grants.new_token(), body.plan_code, body.days, body.max_redemptions,
                body.email.lower() if body.email else None, body.note, expires_at, admin.email,
            )
            await _audit(conn, admin, "signup_grant.create", str(grant_id),
                          body.model_dump(mode="json"))
        row = await conn.fetchrow(f"{_GRANT_LIST} WHERE g.id = $1 GROUP BY g.id, p.name", grant_id)
    return _grant_out(row)


@router.post("/signup-grants/{grant_id}/revoke", response_model=CappeAdminSignupGrant)
async def revoke_signup_grant(grant_id: UUID, admin=Depends(require_admin)):
    """Stop a link working. Accounts that already confirmed keep their free
    days; ones still unconfirmed won't get them."""
    async with get_connection() as conn:
        async with conn.transaction():
            revoked = await conn.fetchval(
                "UPDATE cappe_signup_grants SET revoked_at = NOW() "
                "WHERE id = $1 AND revoked_at IS NULL RETURNING id",
                grant_id,
            )
            if revoked is None:
                raise HTTPException(
                    status_code=status.HTTP_404_NOT_FOUND,
                    detail="No such link, or it was already revoked.",
                )
            await _audit(conn, admin, "signup_grant.revoke", str(grant_id), {})
        row = await conn.fetchrow(f"{_GRANT_LIST} WHERE g.id = $1 GROUP BY g.id, p.name", grant_id)
    return _grant_out(row)
