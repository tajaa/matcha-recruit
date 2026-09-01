from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, EmailStr, Field

from app.core.dependencies import require_admin, revoke_user_sessions
from app.core.models.auth import CurrentUser
from app.core.services.auth import create_access_token, create_refresh_token, hash_password, verify_password_async
from app.database import get_connection
from app.config import get_settings

router = APIRouter(tags=["oceanlab-auth"])


class LoginRequest(BaseModel):
    email: EmailStr
    password: str


class PasswordChangeRequest(BaseModel):
    current_password: str
    new_password: str = Field(min_length=8)


@router.post("/auth/login")
async def login(request: LoginRequest):
    async with get_connection() as conn:
        user = await conn.fetchrow(
            "SELECT id, email, password_hash, role, is_active FROM users WHERE lower(email) = lower($1)",
            request.email,
        )
        if not user or user["role"] != "admin" or not await verify_password_async(request.password, user["password_hash"]):
            raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid email or password")
        if not user["is_active"]:
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Account is disabled")
        settings = get_settings()
        return {
            "access_token": create_access_token(user["id"], user["email"], user["role"]),
            "refresh_token": create_refresh_token(user["id"], user["email"], user["role"]),
            "expires_in": settings.jwt_access_token_expire_minutes * 60,
            "user": {"email": user["email"], "role": user["role"]},
        }


@router.get("/auth/me")
async def me(user: CurrentUser = Depends(require_admin)):
    return {"email": user.email, "role": user.role}


@router.post("/auth/logout", status_code=status.HTTP_204_NO_CONTENT)
async def logout(user: CurrentUser = Depends(require_admin)):
    async with get_connection() as conn:
        await revoke_user_sessions(conn, user.id)


@router.post("/auth/change-password")
async def change_password(request: PasswordChangeRequest, user: CurrentUser = Depends(require_admin)):
    async with get_connection() as conn:
        row = await conn.fetchrow("SELECT password_hash FROM users WHERE id = $1", user.id)
        if not row or not await verify_password_async(request.current_password, row["password_hash"]):
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Current password is incorrect")
        await conn.execute("UPDATE users SET password_hash = $1 WHERE id = $2", hash_password(request.new_password), user.id)
        await revoke_user_sessions(conn, user.id)
    return {"status": "password_changed"}
