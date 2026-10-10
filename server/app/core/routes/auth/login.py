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
    LoginRequest, TokenResponse, MobileLogoutRequest, RefreshTokenRequest, UserResponse,
    AdminRegister, ClientRegister, CandidateRegister,
    BusinessRegister, TestAccountRegister, TestAccountProvisionResponse,
    AdminProfile, ClientProfile, CandidateProfile, EmployeeProfile,
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
    get_current_user, require_admin, get_token_payload,
    session_revoked, revoke_user_sessions,
)
from app.core.feature_flags import (
    DEFAULT_COMPANY_FEATURES,
    default_company_features_json,
    merge_company_features,
)
from app.core.services.platform_settings import get_visible_features
from app.core.services.redis_cache import check_rate_limit, client_ip
from app.core.services.session_tokens import MOBILE_SESSION_ROLES, refresh_session_expired
from app.matcha.services.scheduling.schedule_rules import INACTIVE_EMPLOYMENT_STATUSES
from app.config import get_settings


from app.core.routes.auth._shared import *  # noqa: F401,F403


_LOGIN_MINUTE_LIMIT = 10
_LOGIN_MINUTE_WINDOW = 60  # seconds
_LOGIN_HOUR_LIMIT = 40
_LOGIN_HOUR_WINDOW = 3600  # seconds
_login_attempts: dict[str, list[float]] = defaultdict(list)


class _ReplayedRefresh(Exception):
    """A mobile refresh token whose generation no longer matches its session."""

    def __init__(self, sid: UUID, user_id: UUID, generation: int) -> None:
        super().__init__("replayed mobile refresh token")
        self.sid = sid
        self.user_id = user_id
        self.generation = generation


class _EndedMobileSession(Exception):
    """A mobile refresh refused because its session is over (expired, revoked,
    user gone or suspended). Raised out of the refresh transaction so the
    device revoke survives that transaction's rollback."""

    def __init__(self, sid: UUID, user_id: UUID, detail: str) -> None:
        super().__init__(detail)
        self.sid = sid
        self.user_id = user_id
        self.detail = detail


# How long after a rotation the previous generation may be presented once more.
# The server commits the new generation before the client has stored it, so a
# lost response (timeout, app suspended mid-request, a failed Keychain write)
# leaves the phone one generation behind. Without the grace, its next refresh
# reads as a replay and signs the employee out. Re-presenting inside the window
# returns the CURRENT generation without bumping it, so a real replay is still
# caught on the next rotation by whichever holder falls behind.
_MOBILE_REFRESH_GRACE_SECONDS = 60


async def _end_mobile_device(conn, sid: UUID, user_id: UUID) -> None:
    """Revoke one Matcha Schedule device session and drop its push tokens."""
    await conn.execute(
        "UPDATE auth_device_sessions SET revoked_at = NOW() "
        "WHERE id = $1 AND user_id = $2 AND client = 'ios_schedule' "
        "AND revoked_at IS NULL",
        sid, user_id,
    )
    await conn.execute(
        "DELETE FROM device_tokens WHERE device_session_id = $1 AND user_id = $2",
        sid, user_id,
    )


# A business company a phone session may run on: not a personal workspace,
# and not held back by the approval flow (`_ensure_company_is_accessible`).
_CLIENT_COMPANY_OK_SQL = (
    "NOT COALESCE(c.is_personal, false) "
    "AND COALESCE(c.status, 'approved') NOT IN ('pending', 'rejected')"
)

# Who may keep a Matcha Schedule device session, read at every rotation of the
# `auth_device_sessions` row aliased `ds`: an employee with an employee record
# that is not inactive ($3 is INACTIVE_EMPLOYMENT_STATUSES), or a business admin
# on a business company that is still accessible.
_MOBILE_ELIGIBLE_SQL = f"""(
    EXISTS (
        SELECT 1 FROM users u
          JOIN employees e ON e.user_id = u.id
         WHERE u.id = ds.user_id AND u.role = 'employee'
           AND NOT (COALESCE(e.employment_status, 'active') = ANY($3::text[]))
    )
    OR EXISTS (
        SELECT 1 FROM users u
          JOIN clients cl ON cl.user_id = u.id
          JOIN companies c ON c.id = cl.company_id
         WHERE u.id = ds.user_id AND u.role = 'client' AND {_CLIENT_COMPANY_OK_SQL}
    )
)"""


async def _assert_mobile_login_allowed(conn, user, capabilities) -> None:
    """Matcha Schedule admits crew and store managers (employees) and, from a
    build that can manage, business admins (clients). Everyone else is 403."""
    if user["role"] == "employee":
        employee = await conn.fetchrow(
            "SELECT id, employment_status FROM employees WHERE user_id = $1", user["id"]
        )
        if not employee or employee["employment_status"] in INACTIVE_EMPLOYMENT_STATUSES:
            raise HTTPException(status_code=403, detail="Employee account is inactive")
        return
    if user["role"] == "client":
        if "manage" not in capabilities:
            raise HTTPException(
                status_code=403,
                detail="Update Matcha Schedule to sign in with a business account.",
            )
        company_ok = await conn.fetchval(
            "SELECT EXISTS (SELECT 1 FROM clients cl JOIN companies c ON c.id = cl.company_id "
            f"WHERE cl.user_id = $1 AND {_CLIENT_COMPANY_OK_SQL})",
            user["id"],
        )
        if not company_ok:
            raise HTTPException(
                status_code=403,
                detail="Matcha Schedule needs an approved business account.",
            )
        return
    raise HTTPException(
        status_code=403, detail="Matcha Schedule is for employees and business admins",
    )


def _mobile_session_id(payload: TokenPayload) -> UUID:
    if payload.cl != "ios_schedule" or not payload.sid or payload.role not in MOBILE_SESSION_ROLES:
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
                        SELECT MIN(m.deleted_at) FROM (
                          SELECT c.deleted_at
                            FROM clients cl
                            JOIN companies c ON c.id = cl.company_id
                           WHERE cl.user_id = u.id
                          UNION ALL
                          SELECT c.deleted_at
                            FROM employees e
                            JOIN companies c ON c.id = e.org_id
                           WHERE e.user_id = u.id
                        ) AS m
                         WHERE m.deleted_at IS NOT NULL
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
            await _assert_mobile_login_allowed(conn, user, request.capabilities)
            mobile_sid = uuid4()
            await conn.execute(
                "INSERT INTO auth_device_sessions (id, user_id, client, device_name) "
                "VALUES ($1, $2, 'ios_schedule', $3)",
                mobile_sid, user["id"], request.device_name,
            )

        # Non-critical analytics write; keep login response path lean.
        asyncio.create_task(_touch_user_last_login(user["id"]))

        settings = get_settings()
        access_token = create_access_token(
            user["id"], user["email"], user["role"],
            extra_claims={"sid": str(mobile_sid), "cl": "ios_schedule"} if mobile_sid else None,
        )
        if mobile_sid:
            refresh_token = create_refresh_token(
                user["id"], user["email"], user["role"],
                extra_claims={"sid": str(mobile_sid), "cl": "ios_schedule", "gen": 0},
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
    mobile_sid = _mobile_session_id(payload) if payload.sid or payload.cl else None

    def refused(detail: str, user_id=None) -> Exception:
        # A refused mobile refresh ends that device: its pushes must stop even
        # though the phone never gets to call /mobile/logout.
        if mobile_sid:
            try:
                return _EndedMobileSession(mobile_sid, UUID(str(user_id or payload.sub)), detail)
            except (TypeError, ValueError):
                pass
        return HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail=detail)

    async with get_connection() as conn:
        try:
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
                              ) AS company_name,
                              (
                                SELECT MIN(m.deleted_at) FROM (
                                  SELECT c.deleted_at
                                    FROM clients cl
                                    JOIN companies c ON c.id = cl.company_id
                                   WHERE cl.user_id = users.id
                                  UNION ALL
                                  SELECT c.deleted_at
                                    FROM employees e
                                    JOIN companies c ON c.id = e.org_id
                                   WHERE e.user_id = users.id
                                ) AS m
                                 WHERE m.deleted_at IS NOT NULL
                              ) AS company_deleted_at
                         FROM users WHERE id = $1
                         FOR UPDATE OF users""",
                    payload.sub
                )

                if not user or not user["is_active"]:
                    raise refused("User not found or inactive")
                if user["company_deleted_at"]:
                    raise refused("This account's company has been deactivated.", user["id"])

                if mobile_sid and (user["role"] not in MOBILE_SESSION_ROLES or user["is_suspended"]):
                    raise refused("Invalid mobile session", user["id"])
                settings = get_settings()
                if refresh_session_expired(payload.iat, payload.session_started_at):
                    raise refused("Session expired. Please log in again.", user["id"])

                # A revoked refresh token (logout / password change) can't mint new tokens.
                if await session_revoked(conn, user["id"], payload.iat, payload.iat_ms):
                    raise refused("Refresh token has been revoked. Please log in again.", user["id"])

                refresh_claims = None
                if mobile_sid:
                    if payload.gen is None:
                        raise HTTPException(status_code=401, detail="Invalid mobile session")
                    # One statement: bump the generation only if the presented token
                    # carries the current one. Atomic against a concurrent mobile
                    # logout; a stale, revoked, replayed, or no-longer-eligible device
                    # (employee gone, business company no longer accessible) cannot
                    # rotate its token.
                    rotated = await conn.fetchrow(
                        f"""UPDATE auth_device_sessions AS ds
                           SET last_refreshed_at = NOW(),
                               refresh_generation = ds.refresh_generation + 1
                         WHERE ds.id = $1 AND ds.user_id = $2
                           AND ds.client = 'ios_schedule' AND ds.revoked_at IS NULL
                           AND ds.refresh_generation = $4
                           AND {_MOBILE_ELIGIBLE_SQL}
                         RETURNING ds.id, ds.refresh_generation""",
                        mobile_sid, user["id"], list(INACTIVE_EMPLOYMENT_STATUSES), payload.gen,
                    )
                    if not rotated:
                        # The generation just before the current one, presented
                        # again moments after it rotated, is a lost response,
                        # not a replay: hand back the current generation
                        # without bumping it (_MOBILE_REFRESH_GRACE_SECONDS).
                        rotated = await conn.fetchrow(
                            f"""SELECT ds.id, ds.refresh_generation
                                 FROM auth_device_sessions AS ds
                                WHERE ds.id = $1 AND ds.user_id = $2
                                  AND ds.client = 'ios_schedule' AND ds.revoked_at IS NULL
                                  AND ds.refresh_generation = $4 + 1
                                  AND ds.last_refreshed_at > NOW() - make_interval(secs => $5)
                                  AND {_MOBILE_ELIGIBLE_SQL}""",
                            mobile_sid, user["id"], list(INACTIVE_EMPLOYMENT_STATUSES), payload.gen,
                            _MOBILE_REFRESH_GRACE_SECONDS,
                        )
                    if not rotated:
                        # A superseded generation on a live session means an old
                        # refresh token was replayed (stolen or duplicated). The
                        # revoke must survive this transaction's rollback, so it
                        # runs outside it.
                        raise _ReplayedRefresh(mobile_sid, user["id"], payload.gen)
                    refresh_claims = {"sid": str(mobile_sid), "cl": "ios_schedule",
                                      "gen": rotated["refresh_generation"]}

                access_token = create_access_token(
                    user["id"], user["email"], user["role"],
                    extra_claims={"sid": str(mobile_sid), "cl": "ios_schedule"} if mobile_sid else None,
                )
                new_refresh_token = create_refresh_token(
                    user["id"], user["email"], user["role"],
                    session_started_at=payload.session_started_at or payload.iat,
                    extra_claims=refresh_claims,
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

        except _ReplayedRefresh as replay:
            await conn.execute(
                "UPDATE auth_device_sessions SET revoked_at = NOW() "
                "WHERE id = $1 AND user_id = $2 AND client = 'ios_schedule' "
                "AND revoked_at IS NULL AND refresh_generation <> $3",
                replay.sid, replay.user_id, replay.generation,
            )
            # Whatever ended this session (logout elsewhere, termination,
            # replay), the device must stop receiving this user's pushes.
            await conn.execute(
                "DELETE FROM device_tokens WHERE device_session_id = $1 AND user_id = $2",
                replay.sid, replay.user_id,
            )
            raise HTTPException(status_code=401, detail="Mobile session revoked or account inactive")
        except _EndedMobileSession as ended:
            await _end_mobile_device(conn, ended.sid, ended.user_id)
            raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail=ended.detail)


@router.post("/logout")
async def logout(current_user: CurrentUser = Depends(get_current_user)):
    """Logout — revoke all of this user's existing access + refresh tokens."""
    async with get_connection() as conn:
        await revoke_user_sessions(conn, current_user.id)
    return {"status": "logged_out"}


@router.post("/mobile/logout")
async def mobile_logout(request: MobileLogoutRequest):
    """Revoke only the Matcha Schedule device identified by this refresh token,
    and drop its push tokens so the phone stops receiving this user's pushes.

    The expiry is deliberately not enforced here (the signature still is): a
    phone signing out after its 12-hour session lapsed must still be able to
    end it, or it keeps receiving the previous user's pushes until the session
    row is pruned. The token is only ever used to revoke, never to mint."""
    payload = decode_token(request.refresh_token, expected_type="refresh", verify_exp=False)
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
        # Session-bound tokens, plus the client's own token in case it was
        # registered before the binding existed.
        await conn.execute(
            "DELETE FROM device_tokens WHERE user_id = $1 "
            "AND (device_session_id = $2 OR ($3::text IS NOT NULL AND token = $3::text))",
            user_id, sid, request.push_token,
        )
    return {"status": "logged_out"}
