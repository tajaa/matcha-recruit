"""Cappe auth dependency.

Mirrors `core.dependencies.get_current_user` but resolves a Cappe-scoped bearer
token against `cappe_accounts`. It does NOT touch matcha's RLS contextvars —
every Cappe query scopes by `account_id` in its WHERE clause instead.
"""
from uuid import UUID

from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials

from ..database import get_connection
from .models.cappe import CappeAccount
from .services.auth import decode_cappe_token, is_cappe_token_revoked

security = HTTPBearer()


async def require_cappe_account(
    credentials: HTTPAuthorizationCredentials = Depends(security),
) -> CappeAccount:
    """Resolve the current authenticated Cappe account from a bearer token."""
    payload = decode_cappe_token(credentials.credentials, expected_type="access")
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
        # Deliberately does NOT join cappe_subscriptions. Every authenticated
        # Cappe request resolves through here, so joining the newest table would
        # make the whole product 500 — login flows and the tenant renderer
        # included — if the code ever ran ahead of its migration. Subscription
        # status is a billing-UI detail; it is served by GET /billing/subscription,
        # which already loads the row. Coupling auth to it buys nothing and risks
        # a total outage.
        row = await conn.fetchrow(
            "SELECT id, email, name, plan, status, account_type, "
            "tokens_valid_after, is_platform_admin "
            "FROM cappe_accounts WHERE id = $1",
            account_id,
        )

    if row is None or row["status"] != "active":
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Account not found or inactive",
        )

    # Session revocation: reject access tokens issued before logout / password change.
    if is_cappe_token_revoked(payload.get("iat"), row["tokens_valid_after"], payload.get("iat_ms")):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Session has been revoked. Please sign in again.",
            headers={"WWW-Authenticate": "Bearer"},
        )

    return CappeAccount(
        id=row["id"],
        email=row["email"],
        name=row["name"],
        plan=row["plan"],
        status=row["status"],
        account_type=row["account_type"],
        is_platform_admin=bool(row["is_platform_admin"]),
    )


async def require_cappe_platform_admin(
    account: CappeAccount = Depends(require_cappe_account),
) -> CappeAccount:
    """Platform staff only — the in-Cappe admin surface (plan catalog, prices,
    take rates, comps).

    A pure function of the already-resolved account, so it costs no extra
    query. Distinct from matcha's `require_admin`: a Cappe platform admin is a
    Cappe identity (`scope=cappe`), not a matcha user.
    """
    if not account.is_platform_admin:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Platform administrator access required",
        )
    return account
