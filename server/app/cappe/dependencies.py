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
        # The LEFT JOIN picks up live subscription status for the billing UI.
        # It rides the partial unique index on (account_id) WHERE status is
        # live, so it stays a single indexed lookup rather than a second query.
        row = await conn.fetchrow(
            """
            SELECT a.id, a.email, a.name, a.plan, a.status, a.account_type,
                   a.tokens_valid_after, a.is_platform_admin,
                   s.status AS subscription_status
              FROM cappe_accounts a
              LEFT JOIN cappe_subscriptions s
                     ON s.account_id = a.id
                    AND s.status IN ('trialing', 'active', 'past_due',
                                     'incomplete', 'unpaid', 'paused')
             WHERE a.id = $1
            """,
            account_id,
        )

    if row is None or row["status"] != "active":
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Account not found or inactive",
        )

    # Session revocation: reject access tokens issued before logout / password change.
    if is_cappe_token_revoked(payload.get("iat"), row["tokens_valid_after"]):
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
        subscription_status=row["subscription_status"],
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
