"""Tell-Us auth dependencies.

Mirrors `cappe.dependencies` but resolves a Tell-Us-scoped bearer token against
`tellus_accounts`. It does NOT touch matcha's RLS contextvars — every Tell-Us
query scopes by `account_id` / `brand_id` in its WHERE clause instead.

Three deps:
  - require_tellus_account — any authenticated Tell-Us account
  - require_consumer       — account_type='consumer'
  - require_brand          — account_type='brand' (brand_id guaranteed populated)
"""
from uuid import UUID

from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials

from ..database import get_connection
from .models.tellus import TellusAccount
from .services.auth import decode_tellus_token, is_tellus_token_revoked

security = HTTPBearer()


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
                      b.id AS brand_id
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
