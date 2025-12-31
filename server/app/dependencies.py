from typing import Optional
from uuid import UUID

from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials

from .services.auth import decode_token
from .models.auth import CurrentUser, UserRole
from .database import get_connection

security = HTTPBearer()


async def get_current_user(
    credentials: HTTPAuthorizationCredentials = Depends(security)
) -> CurrentUser:
    """Dependency to get the current authenticated user."""
    token = credentials.credentials
    payload = decode_token(token)

    if payload is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or expired token",
            headers={"WWW-Authenticate": "Bearer"},
        )

    user_id = UUID(payload.sub)

    async with get_connection() as conn:
        # Verify user exists and is active
        user_row = await conn.fetchrow(
            """SELECT id, email, role, is_active,
                      COALESCE(beta_features, '{}'::jsonb) as beta_features,
                      COALESCE(interview_prep_tokens, 0) as interview_prep_tokens
               FROM users WHERE id = $1""",
            user_id
        )

        if not user_row or not user_row["is_active"]:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="User not found or inactive"
            )

        beta_features = user_row["beta_features"] if user_row["beta_features"] else {}
        if isinstance(beta_features, str):
            import json
            beta_features = json.loads(beta_features)

        return CurrentUser(
            id=user_row["id"],
            email=user_row["email"],
            role=user_row["role"],
            profile=None,  # Profile loaded on demand
            beta_features=beta_features,
            interview_prep_tokens=user_row["interview_prep_tokens"]
        )


def require_roles(*roles: UserRole):
    """Dependency factory for role-based access control."""
    async def role_checker(current_user: CurrentUser = Depends(get_current_user)):
        if current_user.role not in roles:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=f"Access denied. Required roles: {', '.join(roles)}"
            )
        return current_user
    return role_checker


# Convenience dependencies
require_admin = require_roles("admin")
require_client = require_roles("client")
require_candidate = require_roles("candidate")
require_admin_or_client = require_roles("admin", "client")


async def get_optional_user(
    credentials: Optional[HTTPAuthorizationCredentials] = Depends(
        HTTPBearer(auto_error=False)
    )
) -> Optional[CurrentUser]:
    """Optional auth - returns None if no valid token."""
    if credentials is None:
        return None

    try:
        return await get_current_user(credentials)
    except HTTPException:
        return None


async def get_client_company_id(
    current_user: CurrentUser = Depends(get_current_user)
) -> Optional[UUID]:
    """Get the company_id for a client user. Returns None for non-clients."""
    if current_user.role != "client":
        return None

    async with get_connection() as conn:
        company_id = await conn.fetchval(
            "SELECT company_id FROM clients WHERE user_id = $1",
            current_user.id
        )
        return company_id


async def require_interview_prep_access(
    current_user: CurrentUser = Depends(get_current_user)
) -> CurrentUser:
    """
    Dependency for interview prep access control.
    - Admins: always allowed
    - Candidates: need beta access + at least 1 token
    """
    # Admins always have access
    if current_user.role == "admin":
        return current_user

    # Candidates need beta access
    if current_user.role == "candidate":
        has_beta = current_user.beta_features.get("interview_prep", False)
        if not has_beta:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="You don't have access to Interview Prep. Contact support for beta access."
            )
        if current_user.interview_prep_tokens <= 0:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="You have no interview prep tokens remaining."
            )
        return current_user

    # Other roles (client) don't have access
    raise HTTPException(
        status_code=status.HTTP_403_FORBIDDEN,
        detail="Interview prep is not available for your account type."
    )
