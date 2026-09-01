"""auth/login.py (split of the pre-2026-07-25 auth.py monolith)."""


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
from app.core.services.session_tokens import refresh_session_expired
from app.config import get_settings


from app.core.routes.auth._shared import *  # noqa: F401,F403


_LOGIN_MINUTE_LIMIT = 10
_LOGIN_MINUTE_WINDOW = 60  # seconds
_LOGIN_HOUR_LIMIT = 40
_LOGIN_HOUR_WINDOW = 3600  # seconds
_login_attempts: dict[str, list[float]] = defaultdict(list)



def _check_login_rate_limit(ip: str) -> None:
    """Raise 429 if IP exceeds login attempt limits."""
    now = time.monotonic()
    # Prune entries older than the hour window
    _login_attempts[ip] = [t for t in _login_attempts[ip] if t > now - _LOGIN_HOUR_WINDOW]

    minute_count = sum(1 for t in _login_attempts[ip] if t > now - _LOGIN_MINUTE_WINDOW)
    hour_count = len(_login_attempts[ip])

    if minute_count >= _LOGIN_MINUTE_LIMIT:
        raise HTTPException(
            status_code=429,
            detail="Too many login attempts. Please try again in a minute.",
            headers={"Retry-After": "60"},
        )

    if hour_count >= _LOGIN_HOUR_LIMIT:
        raise HTTPException(
            status_code=429,
            detail="Too many login attempts. Please try again later.",
            headers={"Retry-After": "3600"},
        )

    _login_attempts[ip].append(now)



async def _touch_user_last_login(user_id: UUID) -> None:
    try:
        async with get_connection() as conn:
            await conn.execute("UPDATE users SET last_login = NOW() WHERE id = $1", user_id)
    except Exception:
        logger.exception("Failed to update last_login for user_id=%s", user_id)



@router.post("/login", response_model=TokenResponse)
async def login(request: LoginRequest, req: Request):
    """Authenticate user and return tokens."""
    client_ip = req.client.host if req.client else "unknown"
    _check_login_rate_limit(client_ip)

    async with get_connection() as conn:
        user = await conn.fetchrow(
            """SELECT u.id, u.email, u.password_hash, u.role, u.is_active, u.is_suspended,
                      u.created_at, u.last_login,
                      (
                        SELECT MIN(c.deleted_at)
                          FROM clients cl
                          JOIN companies c ON c.id = cl.company_id
                         WHERE cl.user_id = u.id
                           AND c.deleted_at IS NOT NULL
                      ) AS company_deleted_at,
                      (
                        SELECT comp.name
                          FROM clients cl
                          JOIN companies comp ON comp.id = cl.company_id
                         WHERE cl.user_id = u.id
                           AND comp.is_personal = false
                         LIMIT 1
                      ) AS company_name
                 FROM users u
                WHERE lower(u.email) = lower($1)""",
            request.email
        )

        if not user or not await verify_password_async(request.password, user["password_hash"]):
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Invalid email or password"
            )

        if not user["is_active"]:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Account is disabled"
            )

        if user["is_suspended"]:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Account is suspended. Contact support@hey-matcha.com.",
            )

        if user["company_deleted_at"]:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="This account's company has been deactivated.",
            )

        # Non-critical analytics write; keep login response path lean.
        asyncio.create_task(_touch_user_last_login(user["id"]))

        settings = get_settings()
        access_token = create_access_token(user["id"], user["email"], user["role"])
        refresh_token = create_refresh_token(user["id"], user["email"], user["role"])

        return TokenResponse(
            access_token=access_token,
            refresh_token=refresh_token,
            expires_in=settings.jwt_access_token_expire_minutes * 60,
            user=UserResponse(
                id=user["id"],
                email=user["email"],
                role=user["role"],
                is_active=user["is_active"],
                created_at=user["created_at"],
                last_login=user["last_login"],
                company_name=user["company_name"],
            )
        )



@router.post("/refresh", response_model=TokenResponse)
async def refresh_token(request: RefreshTokenRequest):
    """Refresh access token using refresh token."""
    payload = decode_token(request.refresh_token, expected_type="refresh")

    if payload is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or expired refresh token"
        )

    async with get_connection() as conn:
        user = await conn.fetchrow(
            """SELECT id, email, role, is_active, created_at, last_login,
                      (
                        SELECT comp.name
                          FROM clients cl
                          JOIN companies comp ON comp.id = cl.company_id
                         WHERE cl.user_id = users.id
                           AND comp.is_personal = false
                         LIMIT 1
                      ) AS company_name
                 FROM users WHERE id = $1""",
            payload.sub
        )

        if not user or not user["is_active"]:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="User not found or inactive"
            )

        if refresh_session_expired(payload.iat, payload.session_started_at):
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Session expired. Please log in again.",
            )

        # A revoked refresh token (logout / password change) can't mint new tokens.
        if await session_revoked(conn, user["id"], payload.iat, payload.iat_ms):
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Refresh token has been revoked. Please log in again."
            )

        settings = get_settings()
        access_token = create_access_token(user["id"], user["email"], user["role"])
        new_refresh_token = create_refresh_token(
            user["id"], user["email"], user["role"],
            session_started_at=payload.session_started_at or payload.iat,
        )

        return TokenResponse(
            access_token=access_token,
            refresh_token=new_refresh_token,
            expires_in=settings.jwt_access_token_expire_minutes * 60,
            user=UserResponse(
                id=user["id"],
                email=user["email"],
                role=user["role"],
                is_active=user["is_active"],
                created_at=user["created_at"],
                last_login=user["last_login"],
                company_name=user["company_name"],
            )
        )



@router.post("/logout")
async def logout(current_user: CurrentUser = Depends(get_current_user)):
    """Logout — revoke all of this user's existing access + refresh tokens."""
    async with get_connection() as conn:
        await revoke_user_sessions(conn, current_user.id)
    return {"status": "logged_out"}
