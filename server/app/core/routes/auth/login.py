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
from uuid import UUID, uuid4

from app.core.models.auth import (
    LoginRequest, TokenResponse, RefreshTokenRequest, UserResponse,
    AdminRegister, ClientRegister, CandidateRegister,
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
from app.core.services.session_tokens import SessionLifetimes, refresh_session_expired
from app.matcha.services.scheduling.schedule_rules import INACTIVE_EMPLOYMENT_STATUSES
from app.config import get_settings


from app.core.routes.auth._shared import *  # noqa: F401,F403


_LOGIN_MINUTE_LIMIT = 10
_LOGIN_MINUTE_WINDOW = 60  # seconds
_LOGIN_HOUR_LIMIT = 40
_LOGIN_HOUR_WINDOW = 3600  # seconds
_login_attempts: dict[str, list[float]] = defaultdict(list)


def _mobile_lifetimes(settings) -> SessionLifetimes:
    return SessionLifetimes(
        settings.mobile_refresh_idle_days * 1440,
        settings.mobile_refresh_absolute_days * 1440,
    )


def _mobile_session_id(payload: TokenPayload) -> UUID:
    if payload.cl != "ios_schedule" or not payload.sid or payload.role != "employee":
        raise HTTPException(status_code=401, detail="Invalid mobile session")
    try:
        return UUID(payload.sid)
    except (TypeError, ValueError):
        raise HTTPException(status_code=401, detail="Invalid mobile session") from None



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

        mobile_sid = None
        if request.client == "ios_schedule":
            if user["role"] != "employee":
                raise HTTPException(status_code=403, detail="Matcha Schedule is for employees")
            employee = await conn.fetchrow(
                "SELECT id, employment_status FROM employees WHERE user_id = $1", user["id"]
            )
            if not employee or employee["employment_status"] in INACTIVE_EMPLOYMENT_STATUSES:
                raise HTTPException(status_code=403, detail="Employee account is inactive")
            mobile_sid = uuid4()
            await conn.execute(
                "INSERT INTO auth_device_sessions (id, user_id, client, device_name) "
                "VALUES ($1, $2, 'ios_schedule', $3)",
                mobile_sid, user["id"], request.device_name,
            )

        # Non-critical analytics write; keep login response path lean.
        asyncio.create_task(_touch_user_last_login(user["id"]))

        settings = get_settings()
        access_token = create_access_token(user["id"], user["email"], user["role"])
        if mobile_sid:
            refresh_token = create_refresh_token(
                user["id"], user["email"], user["role"],
                extra_claims={"sid": str(mobile_sid), "cl": "ios_schedule"},
                lifetimes=_mobile_lifetimes(settings),
            )
        else:
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
        async with conn.transaction():
            user = await conn.fetchrow(
                """SELECT id, email, role, is_active, is_suspended, created_at, last_login,
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

            mobile_sid = _mobile_session_id(payload) if payload.sid or payload.cl else None
            if mobile_sid and (user["role"] != "employee" or user["is_suspended"]):
                raise HTTPException(status_code=401, detail="Invalid mobile session")
            settings = get_settings()
            if refresh_session_expired(
                payload.iat, payload.session_started_at,
                lifetimes=_mobile_lifetimes(settings) if mobile_sid else None,
            ):
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

            if mobile_sid:
                # The update is atomic against a concurrent mobile logout. A stale,
                # revoked, or no-longer-employed device cannot rotate its token.
                active_sid = await conn.fetchval(
                    """UPDATE auth_device_sessions AS ds
                       SET last_refreshed_at = NOW()
                     WHERE ds.id = $1 AND ds.user_id = $2
                       AND ds.client = 'ios_schedule' AND ds.revoked_at IS NULL
                       AND EXISTS (
                           SELECT 1 FROM employees e
                            WHERE e.user_id = ds.user_id
                              AND NOT (COALESCE(e.employment_status, 'active') = ANY($3::text[]))
                       )
                     RETURNING ds.id""",
                    mobile_sid, user["id"], list(INACTIVE_EMPLOYMENT_STATUSES),
                )
                if not active_sid:
                    raise HTTPException(status_code=401, detail="Mobile session revoked or employee inactive")

            access_token = create_access_token(user["id"], user["email"], user["role"])
            new_refresh_token = create_refresh_token(
                user["id"], user["email"], user["role"],
                session_started_at=payload.session_started_at or payload.iat,
                extra_claims={"sid": str(mobile_sid), "cl": "ios_schedule"} if mobile_sid else None,
                lifetimes=_mobile_lifetimes(settings) if mobile_sid else None,
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


@router.post("/mobile/logout")
async def mobile_logout(request: RefreshTokenRequest):
    """Revoke only the Matcha Schedule device identified by this refresh token."""
    payload = decode_token(request.refresh_token, expected_type="refresh")
    if payload is None:
        raise HTTPException(status_code=401, detail="Invalid or expired refresh token")
    sid = _mobile_session_id(payload)
    try:
        user_id = UUID(payload.sub)
    except (TypeError, ValueError):
        raise HTTPException(status_code=401, detail="Invalid mobile session") from None
    async with get_connection() as conn:
        await conn.execute(
            "UPDATE auth_device_sessions SET revoked_at = NOW() "
            "WHERE id = $1 AND user_id = $2 AND client = 'ios_schedule' "
            "AND revoked_at IS NULL",
            sid, user_id,
        )
    return {"status": "logged_out"}
