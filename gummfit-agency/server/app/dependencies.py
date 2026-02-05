"""Core authentication and authorization dependencies."""
from typing import Optional
from uuid import UUID

from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials

from .database import get_connection

security = HTTPBearer()


async def get_current_user(
    credentials: HTTPAuthorizationCredentials = Depends(security)
):
    """Dependency to get the current authenticated user."""
    from .services.auth import decode_token
    from .models.auth import CurrentUser

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
        user_row = await conn.fetchrow(
            "SELECT id, email, role, is_active FROM users WHERE id = $1",
            user_id
        )

        if not user_row or not user_row["is_active"]:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="User not found or inactive"
            )

        return CurrentUser(
            id=user_row["id"],
            email=user_row["email"],
            role=user_row["role"],
            profile=None,
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


require_admin = require_roles("admin", "gumfit_admin")
require_creator = require_roles("creator")
require_agency = require_roles("agency")


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
