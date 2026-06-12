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
from .services.auth import decode_cappe_token

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
        row = await conn.fetchrow(
            "SELECT id, email, name, plan, status FROM cappe_accounts WHERE id = $1",
            account_id,
        )

    if row is None or row["status"] != "active":
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Account not found or inactive",
        )

    return CappeAccount(
        id=row["id"],
        email=row["email"],
        name=row["name"],
        plan=row["plan"],
        status=row["status"],
    )
