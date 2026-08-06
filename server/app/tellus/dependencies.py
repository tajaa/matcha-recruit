"""Tell-Us auth dependencies.

Mirrors `cappe.dependencies` but resolves a Tell-Us-scoped bearer token against
`tellus_accounts`. It does NOT touch matcha's RLS contextvars — every Tell-Us
query scopes by `account_id` / `brand_id` in its WHERE clause instead.

Deps:
  - require_tellus_account — any authenticated Tell-Us account
  - require_consumer       — account_type='consumer'
  - require_brand          — account_type='brand' (brand_id guaranteed populated)
  - require_tellus_admin   — email in TELLUS_ADMIN_EMAILS (internal changelog only)
"""
from uuid import UUID

from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials

from app.config import get_settings

from ..database import get_connection
from .models.tellus import TellusAccount
from .services.auth import decode_tellus_token, is_tellus_token_revoked

security = HTTPBearer()


def _is_tellus_admin(email: str) -> bool:
    """Case-insensitive allowlist from TELLUS_ADMIN_EMAILS. Empty setting
    means nobody passes — tellus_accounts has no role column, so this env
    allowlist is the whole gate (same fail-closed shape as matcha's
    _is_master_admin)."""
    allowed = {e.strip().lower() for e in get_settings().tellus_admin_emails.split(",") if e.strip()}
    return email.lower() in allowed


async def require_tellus_account(
    credentials: HTTPAuthorizationCredentials = Depends(security),
) -> TellusAccount:
    """Resolve the current authenticated Tell-Us account from a bearer token."""
    payload = decode_tellus_token(credentials.credentials, expected_type="access")
    if payload is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or expired token",
            headers={"WWW-Authenticate": "Bearer"},
        )

    try:
        account_id = UUID(payload["sub"])
    except (KeyError, ValueError, TypeError):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid token subject",
            headers={"WWW-Authenticate": "Bearer"},
        )

    async with get_connection() as conn:
        row = await conn.fetchrow(
            """SELECT a.id, a.email, a.display_name, a.account_type, a.status,
                      a.city, a.state, a.leaderboard_opt_in, a.tokens_valid_after,
                      b.id AS brand_id, b.plan_status, b.location_count, b.slug AS brand_slug
               FROM tellus_accounts a
               LEFT JOIN tellus_brands b ON b.owner_account_id = a.id
               WHERE a.id = $1""",
            account_id,
        )

    if row is None or row["status"] != "active":
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Account not found or inactive",
        )

    if is_tellus_token_revoked(payload.get("iat"), row["tokens_valid_after"]):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Session has been revoked. Please sign in again.",
            headers={"WWW-Authenticate": "Bearer"},
        )

    return TellusAccount(
        id=row["id"],
        email=row["email"],
        display_name=row["display_name"],
        account_type=row["account_type"],
        status=row["status"],
        city=row["city"],
        state=row["state"],
        leaderboard_opt_in=row["leaderboard_opt_in"],
        brand_id=row["brand_id"],
        plan_status=row["plan_status"],
        location_count=row["location_count"],
        brand_slug=row["brand_slug"],
        is_admin=_is_tellus_admin(row["email"]),
    )


async def require_consumer(
    account: TellusAccount = Depends(require_tellus_account),
) -> TellusAccount:
    """Require a consumer account (feedback → points → redeem)."""
    if account.account_type != "consumer":
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="This action is for consumer accounts.",
        )
    return account


async def require_brand(
    account: TellusAccount = Depends(require_tellus_account),
) -> TellusAccount:
    """Require a brand account with a provisioned brand row."""
    if account.account_type != "brand":
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="This action is for brand accounts.",
        )
    if account.brand_id is None:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="No brand is set up for this account yet.",
        )
    return account


async def require_paid_brand(
    account: TellusAccount = Depends(require_brand),
) -> TellusAccount:
    """Require a brand account with an active paid subscription.

    Gates the brand dashboard (stores, feedback, listings) — billing.py and
    the brand profile GET stay on require_brand so a pending brand can still
    see its own status and pay.
    """
    if account.plan_status != "active":
        raise HTTPException(
            status_code=status.HTTP_402_PAYMENT_REQUIRED,
            detail="This brand account does not have an active subscription.",
        )
    return account


async def require_tellus_admin(
    account: TellusAccount = Depends(require_tellus_account),
) -> TellusAccount:
    """Internal Tell-Us admin surface — the changelog at /tellus/admin/updates."""
    if not account.is_admin:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Admin access restricted",
        )
    return account


async def require_dm_account(
    account: TellusAccount = Depends(require_tellus_account),
) -> TellusAccount:
    """Any consumer account, or a brand account with an active subscription.

    DMs are shared brand/consumer surfaces (dms.py branches on
    account_type) — a lapsed brand shouldn't keep DM read/write just because
    it skips the require_paid_brand gate the rest of the dashboard uses.
    """
    if account.account_type == "brand" and account.plan_status != "active":
        raise HTTPException(
            status_code=status.HTTP_402_PAYMENT_REQUIRED,
            detail="This brand account does not have an active subscription.",
        )
    return account
