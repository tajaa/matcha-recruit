"""Cappe auth dependency.

Mirrors `core.dependencies.get_current_user` but resolves a Cappe-scoped bearer
token against `cappe_accounts`. It does NOT touch matcha's RLS contextvars —
every Cappe query scopes by `account_id` in its WHERE clause instead.
"""
import json
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
        row = await conn.fetchrow(
            "SELECT id, email, name, plan, status, account_type, tokens_valid_after, "
            "       matcha_features "
            "FROM cappe_accounts WHERE id = $1",
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

    matcha_features = row["matcha_features"]
    if isinstance(matcha_features, str):
        matcha_features = json.loads(matcha_features or "{}")

    return CappeAccount(
        id=row["id"],
        email=row["email"],
        name=row["name"],
        plan=row["plan"],
        status=row["status"],
        account_type=row["account_type"],
        matcha_features=matcha_features or {},
    )
