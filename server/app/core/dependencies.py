"""Core authentication and authorization dependencies."""
import logging
from typing import Optional
from uuid import UUID

import asyncpg
from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials

from ..config import get_settings
from ..database import get_connection, set_is_admin, set_user_id

logger = logging.getLogger(__name__)
security = HTTPBearer()


def _is_master_admin(email: Optional[str]) -> bool:
    """The single platform/master-admin identity (settings.master_admin_email).
    Any other role='admin' row is NOT a master admin. Case-insensitive."""
    if not email:
        return False
    allowed = (get_settings().master_admin_email or "").strip().lower()
    return bool(allowed) and email.strip().lower() == allowed

# Cached once per process: does users.tokens_valid_after exist? Lets the session
# revocation check degrade to a no-op if the authsess01 migration isn't applied
# yet, so a deploy-before-migrate can't take down all authentication.
_users_has_valid_after: Optional[bool] = None


async def _has_valid_after_column(conn) -> bool:
    global _users_has_valid_after
    if _users_has_valid_after is None:
        _users_has_valid_after = bool(await conn.fetchval(
            "SELECT EXISTS (SELECT 1 FROM information_schema.columns "
            "WHERE table_name='users' AND column_name='tokens_valid_after')"
        ))
    return _users_has_valid_after


async def session_revoked(conn, user_id, token_iat: Optional[int]) -> bool:
    """True if a token (by its iat) predates the user's session-revocation
    watermark. Returns False (no revocation) for tokens minted before this
    feature shipped (no iat) or before the column exists."""
    if token_iat is None:
        return False
    if not await _has_valid_after_column(conn):
        return False
    valid_after = await conn.fetchval(
        "SELECT tokens_valid_after FROM users WHERE id = $1", user_id
    )
    return valid_after is not None and token_iat < valid_after.timestamp()


async def revoke_user_sessions(conn, user_id) -> None:
    """Invalidate all of a user's existing access + refresh tokens by advancing
    the watermark. Best-effort no-op (logged) until authsess01 is applied."""
    try:
        await conn.execute(
            "UPDATE users SET tokens_valid_after = NOW() WHERE id = $1", user_id
        )
    except asyncpg.UndefinedColumnError:
        logger.warning(
            "revoke_user_sessions: tokens_valid_after column missing — apply migration authsess01"
        )


async def get_token_payload(
    credentials: HTTPAuthorizationCredentials = Depends(security)
):
    """Decode and validate a bearer token payload."""
    # Import here to avoid circular imports
    from .services.auth import decode_token

    token = credentials.credentials
    payload = decode_token(token, expected_type="access")

    if payload is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or expired token",
            headers={"WWW-Authenticate": "Bearer"},
        )

    return payload


async def get_current_user(
    credentials: HTTPAuthorizationCredentials = Depends(security)
):
    """Dependency to get the current authenticated user."""
    from .models.auth import CurrentUser

    payload = await get_token_payload(credentials)

    user_id = UUID(payload.sub)

    async with get_connection() as conn:
        # Verify user exists and is active
        user_row = await conn.fetchrow(
            """SELECT u.id, u.email, u.role, u.is_active, u.is_suspended,
                      COALESCE(u.beta_features, '{}'::jsonb) as beta_features,
                      COALESCE(u.interview_prep_tokens, 0) as interview_prep_tokens,
                      COALESCE(u.allowed_interview_roles, '[]'::jsonb) as allowed_interview_roles,
                      (
                        SELECT MIN(c.deleted_at)
                          FROM clients cl
                          JOIN companies c ON c.id = cl.company_id
                         WHERE cl.user_id = u.id
                           AND c.deleted_at IS NOT NULL
                      ) AS company_deleted_at
                 FROM users u
                WHERE u.id = $1""",
            user_id
        )

        if not user_row or not user_row["is_active"]:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="User not found or inactive"
            )

        if user_row["is_suspended"]:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Account is suspended"
            )

        if user_row["company_deleted_at"]:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="This account's company has been deactivated"
            )

        # Session revocation: reject tokens issued before the user logged out or
        # changed their password.
        if await session_revoked(conn, user_row["id"], payload.iat):
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Session has been revoked. Please log in again.",
                headers={"WWW-Authenticate": "Bearer"},
            )

        beta_features = user_row["beta_features"] if user_row["beta_features"] else {}
        if isinstance(beta_features, str):
            import json
            beta_features = json.loads(beta_features)

        allowed_roles = user_row["allowed_interview_roles"] if user_row["allowed_interview_roles"] else []
        if isinstance(allowed_roles, str):
            import json
            allowed_roles = json.loads(allowed_roles)

        # Propagate identity to contextvars so get_connection() can set
        # the corresponding PostgreSQL session variables for RLS.
        set_user_id(str(user_row["id"]))
        # RLS admin bypass is reserved for the single master admin — a stray
        # role='admin' row gets no elevated DB access.
        if user_row["role"] == "admin" and _is_master_admin(user_row["email"]):
            set_is_admin(True)

        return CurrentUser(
            id=user_row["id"],
            email=user_row["email"],
            role=user_row["role"],
            profile=None,  # Profile loaded on demand
            beta_features=beta_features,
            interview_prep_tokens=user_row["interview_prep_tokens"],
            allowed_interview_roles=allowed_roles
        )


def require_roles(*roles):
    """Dependency factory for role-based access control."""
    async def role_checker(current_user=Depends(get_current_user)):
        if current_user.role not in roles:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=f"Access denied. Required roles: {', '.join(roles)}"
            )
        return current_user
    return role_checker


# Core role dependencies
async def require_admin(current_user=Depends(get_current_user)):
    """Master-admin gate: only the single configured master-admin identity
    (settings.master_admin_email) may reach platform-admin surfaces. Other
    role='admin' rows are rejected — there is exactly one master admin."""
    if current_user.role != "admin" or not _is_master_admin(current_user.email):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Master admin access restricted",
        )
    return current_user
require_candidate = require_roles("candidate")
require_broker = require_roles("broker")


async def get_optional_user(
    credentials: Optional[HTTPAuthorizationCredentials] = Depends(
        HTTPBearer(auto_error=False)
    )
):
    """Optional auth - returns None if no valid token."""
    if credentials is None:
        return None

    try:
        return await get_current_user(credentials)
    except HTTPException:
        return None
