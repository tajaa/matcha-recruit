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
from dataclasses import replace
from typing import Awaitable, Callable, Optional
from uuid import UUID

from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials

from app.config import get_settings

from ..database import get_connection
from .models.access import BrandCapability
from .models.tellus import TellusAccount
from .services.auth import decode_tellus_token, is_tellus_token_revoked
from .services.access_service import (
    BrandAccessContext,
    StoreAccessContext,
    assert_capability,
    assert_paid_brand,
    resolve_brand_access,
    resolve_store_access,
)

security = HTTPBearer()


async def optional_consumer_account_id(authorization: Optional[str]) -> Optional[UUID]:
    """Resolve a consumer account_id from a bearer token if one is present and
    valid; otherwise None (anonymous). Never raises — auth is optional here.
    Shared by public_intake.py (anonymous feedback submission) and
    community.py (unauthenticated /b/{slug} page, for liked_by_me)."""
    if not authorization or not authorization.lower().startswith("bearer "):
        return None
    payload = decode_tellus_token(authorization.split(" ", 1)[1].strip(), expected_type="access")
    if payload is None:
        return None
    try:
        account_id = UUID(payload["sub"])
    except (KeyError, ValueError, TypeError):
        return None
    async with get_connection() as conn:
        ok = await conn.fetchval(
            "SELECT 1 FROM tellus_accounts WHERE id = $1 AND status = 'active' AND account_type = 'consumer'",
            account_id,
        )
    return account_id if ok else None


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
                      a.consumer_tier, a.consumer_tier_expires_at,
                      a.handle, a.handle_set_at, a.avatar_url,
                      a.profile_visibility, a.discoverable,
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

    if is_tellus_token_revoked(payload.get("iat"), row["tokens_valid_after"], payload.get("iat_ms")):
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
        consumer_tier=row["consumer_tier"],
        consumer_tier_expires_at=row["consumer_tier_expires_at"],
        handle=row["handle"],
        handle_set_at=row["handle_set_at"],
        avatar_url=row["avatar_url"],
        profile_visibility=row["profile_visibility"],
        discoverable=row["discoverable"],
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


async def require_verified_consumer(
    account: TellusAccount = Depends(require_consumer),
) -> TellusAccount:
    """Require a consumer who has verified control of their email address."""
    async with get_connection() as conn:
        verified = await conn.fetchval(
            "SELECT 1 FROM tellus_accounts WHERE id = $1 AND email_verified_at IS NOT NULL",
            account.id,
        )
    if not verified:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Verify your email before using Comms.")
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


async def require_brand_context(
    brand_id: UUID,
    account: TellusAccount = Depends(require_tellus_account),
) -> BrandAccessContext:
    """Resolve a current active membership for an explicit business ID."""
    async with get_connection() as conn:
        context = await resolve_brand_access(conn, account.id, brand_id)
    return replace(context, account=account)


def require_brand_capability(
    capability: BrandCapability,
    *,
    paid: bool = True,
) -> Callable[..., Awaitable[BrandAccessContext]]:
    """Build a FastAPI dependency for one business capability."""
    async def dependency(
        context: BrandAccessContext = Depends(require_brand_context),
    ) -> BrandAccessContext:
        assert_capability(context, capability)
        if paid:
            assert_paid_brand(context)
        return context

    return dependency


async def require_store_context(
    store_id: UUID,
    brand: BrandAccessContext = Depends(require_brand_context),
) -> StoreAccessContext:
    """Resolve an active store that the current membership may access."""
    async with get_connection() as conn:
        return await resolve_store_access(conn, brand, store_id)


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
