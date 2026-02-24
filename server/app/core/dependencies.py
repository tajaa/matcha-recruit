"""Core authentication and authorization dependencies."""
from typing import Optional
from uuid import UUID

from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials

from ..database import get_connection

security = HTTPBearer()


async def get_token_payload(
    credentials: HTTPAuthorizationCredentials = Depends(security)
):
    """Decode and validate a bearer token payload."""
    # Import here to avoid circular imports
    from .services.auth import decode_token

    token = credentials.credentials
    payload = decode_token(token)

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
            """SELECT id, email, role, is_active,
                      COALESCE(beta_features, '{}'::jsonb) as beta_features,
                      COALESCE(interview_prep_tokens, 0) as interview_prep_tokens,
                      COALESCE(allowed_interview_roles, '[]'::jsonb) as allowed_interview_roles
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

        allowed_roles = user_row["allowed_interview_roles"] if user_row["allowed_interview_roles"] else []
        if isinstance(allowed_roles, str):
            import json
            allowed_roles = json.loads(allowed_roles)

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
require_admin = require_roles("admin")
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
