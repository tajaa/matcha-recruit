"""auth/credentials.py (split of the pre-2026-07-25 auth.py monolith)."""


import asyncio
import json
import logging
import re
import secrets
import time
from collections import defaultdict
from datetime import datetime, timedelta, timezone

from fastapi import APIRouter, HTTPException, Depends, Request, UploadFile, File, status
from pydantic import BaseModel, EmailStr, Field

from app.database import get_connection
from uuid import UUID

from app.core.models.auth import (
    LoginRequest, TokenResponse, RefreshTokenRequest, UserResponse,
    AdminRegister, ClientRegister, CandidateRegister, EmployeeRegister,
    BusinessRegister, TestAccountRegister, TestAccountProvisionResponse,
    AdminProfile, ClientProfile, CandidateProfile, EmployeeProfile,
    BrokerTermsAcceptanceRequest, BrokerTermsAcceptanceResponse,
    BrokerClientInviteDetailsResponse, BrokerClientInviteAcceptRequest,
    BrokerBrandingRuntimeResponse,
    CurrentUser, TokenPayload,
    ChangePasswordRequest, ChangeEmailRequest, UpdateProfileRequest,
    CandidateBetaInfo, CandidateBetaListResponse, BetaToggleRequest,
    TokenAwardRequest, AllowedRolesRequest, CandidateSessionSummary
)
from app.core.services.auth import (
    hash_password, verify_password, verify_password_async,
    create_access_token, create_refresh_token, decode_token,
    create_email_verify_token, decode_email_verify_token,
)
from app.core.dependencies import (
    get_current_user, require_admin, require_broker, get_token_payload,
    session_revoked, revoke_user_sessions,
)
from app.core.feature_flags import (
    DEFAULT_COMPANY_FEATURES,
    default_company_features_json,
    merge_company_features,
)
from app.core.services.platform_settings import get_visible_features
from app.core.services.redis_cache import check_rate_limit, client_ip
from app.config import get_settings


from app.core.routes.auth._shared import *  # noqa: F401,F403


@router.post("/change-password")
async def change_password(
    request: ChangePasswordRequest,
    current_user: CurrentUser = Depends(get_current_user)
):
    """Change password for current user."""
    from ..services.email import get_email_service
    from ...config import get_settings

    async with get_connection() as conn:
        # Get current password hash
        user = await conn.fetchrow(
            "SELECT password_hash FROM users WHERE id = $1",
            current_user.id
        )

        if not user or not await verify_password_async(request.current_password, user["password_hash"]):
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Current password is incorrect"
            )

        # min_length=8 is enforced by ChangePasswordRequest model

        # Update password
        new_hash = hash_password(request.new_password)
        await conn.execute(
            "UPDATE users SET password_hash = $1 WHERE id = $2",
            new_hash, current_user.id
        )
        # Invalidate all other sessions after a password change.
        await revoke_user_sessions(conn, current_user.id)

    # Security notification — fire after connection is released
    try:
        settings = get_settings()
        reset_url = f"{settings.app_base_url.rstrip('/')}/reset-password"
        to_name = (
            current_user.profile.name
            if current_user.profile and getattr(current_user.profile, "name", None)
            else current_user.email.split("@")[0]
        )
        email_svc = get_email_service()
        await email_svc.send_password_changed_email(
            to_email=current_user.email,
            to_name=to_name,
            reset_url=reset_url,
        )
    except Exception as e:
        logger.warning(f"Failed to send password changed notification: {e}")

    return {"status": "password_changed"}



@router.post("/change-email")
async def change_email(
    request: ChangeEmailRequest,
    current_user: CurrentUser = Depends(get_current_user)
):
    """Change email for current user."""
    async with get_connection() as conn:
        # Verify password
        user = await conn.fetchrow(
            "SELECT password_hash FROM users WHERE id = $1",
            current_user.id
        )

        if not user or not await verify_password_async(request.password, user["password_hash"]):
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Password is incorrect"
            )

        # Check if new email is already taken
        existing = await conn.fetchval(
            "SELECT id FROM users WHERE email = $1 AND id != $2",
            request.new_email, current_user.id
        )
        if existing:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Email is already in use"
            )

        # Update email in users table
        await conn.execute(
            "UPDATE users SET email = $1 WHERE id = $2",
            request.new_email, current_user.id
        )

        # Also update email in role-specific table if applicable
        if current_user.role == "candidate":
            await conn.execute(
                "UPDATE candidates SET email = $1 WHERE user_id = $2",
                request.new_email, current_user.id
            )

        # Generate new tokens with updated email
        settings = get_settings()
        access_token = create_access_token(current_user.id, request.new_email, current_user.role)
        refresh_token = create_refresh_token(current_user.id, request.new_email, current_user.role)

        return {
            "status": "email_changed",
            "access_token": access_token,
            "refresh_token": refresh_token,
            "expires_in": settings.jwt_access_token_expire_minutes * 60
        }



class ForgotPasswordRequest(BaseModel):
    email: EmailStr



class ResetPasswordRequest(BaseModel):
    token: str
    new_password: str = Field(..., min_length=8)



def _validate_password_strength(password: str) -> None:
    errors = []
    if len(password) < 8:
        errors.append("at least 8 characters")
    if not re.search(r"[A-Z]", password):
        errors.append("an uppercase letter")
    if not re.search(r"[a-z]", password):
        errors.append("a lowercase letter")
    if not re.search(r"\d", password):
        errors.append("a digit")
    if not re.search(r"[^A-Za-z0-9]", password):
        errors.append("a special character")
    if errors:
        raise HTTPException(status_code=400, detail=f"Password must include {', '.join(errors)}.")



@router.post("/forgot-password")
async def forgot_password(request: ForgotPasswordRequest, http_request: Request):
    """Send a password reset email. Always returns 200 to avoid email enumeration."""
    ip = client_ip(http_request)
    await check_rate_limit(ip, "forgot_password", 5, 3600)
    from ..services.email import get_email_service
    from ...config import get_settings

    async with get_connection() as conn:
        user = await conn.fetchrow(
            "SELECT id, email FROM users WHERE email = $1 AND is_active = true",
            request.email.lower().strip(),
        )
        if not user:
            return {"status": "ok"}

        token = secrets.token_urlsafe(48)
        # Store token with 1-hour expiry
        await conn.execute(
            """INSERT INTO password_reset_tokens (user_id, token, expires_at)
               VALUES ($1, $2, NOW() + INTERVAL '1 hour')""",
            user["id"], token,
        )

    settings = get_settings()
    base_url = settings.app_base_url.rstrip("/")
    reset_url = f"{base_url}/reset-password?token={token}"

    email_svc = get_email_service()
    try:
        if email_svc.is_configured():
            await email_svc.send_email(
                to_email=user["email"],
                to_name=user["email"].split("@")[0],
                subject="Reset your Matcha password",
                html_content=f"""
                <div style="font-family: -apple-system, BlinkMacSystemFont, sans-serif; max-width: 480px; margin: 0 auto; padding: 32px 0;">
                    <h2 style="color: #e4e4e7; font-size: 20px; margin-bottom: 8px;">Password Reset</h2>
                    <p style="color: #a1a1aa; font-size: 14px; line-height: 1.6; margin-bottom: 24px;">
                        Click the button below to reset your password. This link expires in 1 hour.
                    </p>
                    <a href="{reset_url}"
                       style="display: inline-block; background: #10b981; color: white; padding: 12px 28px;
                              border-radius: 8px; text-decoration: none; font-size: 14px; font-weight: 600;">
                        Reset Password
                    </a>
                    <p style="color: #71717a; font-size: 12px; margin-top: 24px;">
                        If you didn't request this, you can safely ignore this email.
                    </p>
                </div>
                """,
            )
    except Exception as e:
        logger.warning(f"Failed to send password reset email: {e}")

    return {"status": "ok"}



@router.post("/reset-password")
async def reset_password(request: ResetPasswordRequest, http_request: Request):
    """Reset password using a valid reset token."""
    ip = client_ip(http_request)
    await check_rate_limit(ip, "reset_password", 10, 3600)
    async with get_connection() as conn:
        row = await conn.fetchrow(
            """SELECT prt.user_id, u.is_suspended, u.is_active
                 FROM password_reset_tokens prt
                 JOIN users u ON u.id = prt.user_id
                WHERE prt.token = $1
                  AND prt.expires_at > NOW()
                  AND prt.used_at IS NULL""",
            request.token,
        )
        if not row:
            raise HTTPException(status_code=400, detail="Invalid or expired reset link")
        if row["is_suspended"] or not row["is_active"]:
            # Defense in depth — login already blocks these accounts, but a
            # suspended user shouldn't even be able to rotate their password.
            raise HTTPException(status_code=403, detail="Account cannot be reset. Contact support.")

        _validate_password_strength(request.new_password)
        new_hash = hash_password(request.new_password)
        await conn.execute(
            "UPDATE users SET password_hash = $1 WHERE id = $2",
            new_hash, row["user_id"],
        )
        # Invalidate all existing sessions after a password reset.
        await revoke_user_sessions(conn, row["user_id"])
        # Mark token as used
        await conn.execute(
            "UPDATE password_reset_tokens SET used_at = NOW() WHERE token = $1",
            request.token,
        )

    return {"status": "password_reset"}

