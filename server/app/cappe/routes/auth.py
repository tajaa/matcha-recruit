"""Cappe authentication — signup / login / refresh / me.

Fully separate from matcha's /auth/* (which is hardwired to users+clients).
Backed by `cappe_accounts`; issues Cappe-scoped tokens.
"""
from uuid import UUID

import asyncpg
from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, Request, status

from ...config import get_settings
from ...core.services.redis_cache import check_rate_limit, client_ip
from ...database import get_connection
from ..dependencies import require_cappe_account
from ..services.email import send_cappe_welcome_email
from ..models.cappe import (
    CappeAccount,
    CappeLogin,
    CappeRefreshRequest,
    CappeSignup,
    CappeTokenResponse,
)
from ..services.auth import (
    create_cappe_access_token,
    create_cappe_refresh_token,
    decode_cappe_token,
    hash_password,
    is_cappe_token_revoked,
    verify_password_async,
)

router = APIRouter()


def _token_response(account: CappeAccount) -> CappeTokenResponse:
    settings = get_settings()
    return CappeTokenResponse(
        access_token=create_cappe_access_token(account.id, account.email),
        refresh_token=create_cappe_refresh_token(account.id, account.email),
        expires_in=settings.jwt_access_token_expire_minutes * 60,
        account=account,
    )


@router.post("/auth/signup", response_model=CappeTokenResponse, status_code=status.HTTP_201_CREATED)
async def signup(body: CappeSignup, request: Request, background: BackgroundTasks):
    """Create a new Cappe account and return tokens."""
    await check_rate_limit(client_ip(request), "cappe_signup", 5, 3600)
    email = body.email.strip().lower()
    password_hash = hash_password(body.password)

    async with get_connection() as conn:
        try:
            row = await conn.fetchrow(
                """INSERT INTO cappe_accounts (email, password_hash, name, account_type)
                   VALUES ($1, $2, $3, $4)
                   RETURNING id, email, name, plan, status, account_type""",
                email,
                password_hash,
                body.name,
                body.account_type,
            )
        except asyncpg.UniqueViolationError:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="An account with this email already exists",
            )

    account = CappeAccount(**dict(row))
    # Confirmation email, after the response is sent. Reserved test domains are
    # skipped by the email service's guard, so seed accounts won't bounce.
    background.add_task(send_cappe_welcome_email, account.email, account.name)
    return _token_response(account)


@router.post("/auth/login", response_model=CappeTokenResponse)
async def login(body: CappeLogin, request: Request):
    """Authenticate a Cappe account by email + password."""
    # Two windows: burst (per-minute) + sustained (per-hour) per IP.
    ip = client_ip(request)
    await check_rate_limit(ip, "cappe_login_min", 10, 60)
    await check_rate_limit(ip, "cappe_login_hr", 60, 3600)
    email = body.email.strip().lower()

    async with get_connection() as conn:
        row = await conn.fetchrow(
            """SELECT id, email, name, plan, status, account_type, password_hash
               FROM cappe_accounts WHERE lower(email) = $1""",
            email,
        )

    # Constant-ish failure: same 401 whether the email is unknown or the
    # password is wrong.
    if row is None or not await verify_password_async(body.password, row["password_hash"]):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Incorrect email or password",
        )
    if row["status"] != "active":
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Account is not active")

    account = CappeAccount(
        id=row["id"], email=row["email"], name=row["name"], plan=row["plan"],
        status=row["status"], account_type=row["account_type"],
    )
    return _token_response(account)


@router.post("/auth/refresh", response_model=CappeTokenResponse)
async def refresh(body: CappeRefreshRequest, request: Request):
    """Exchange a valid Cappe refresh token for a fresh token pair."""
    await check_rate_limit(client_ip(request), "cappe_refresh", 60, 3600)
    payload = decode_cappe_token(body.refresh_token, expected_type="refresh")
    if payload is None:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid refresh token")

    try:
        account_id = UUID(payload["sub"])
    except (KeyError, ValueError, TypeError):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid refresh token")

    async with get_connection() as conn:
        row = await conn.fetchrow(
            "SELECT id, email, name, plan, status, account_type, tokens_valid_after "
            "FROM cappe_accounts WHERE id = $1",
            account_id,
        )

    if row is None or row["status"] != "active":
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Account not found or inactive")

    # Revoked refresh tokens (issued before logout / password change) can't re-mint.
    if is_cappe_token_revoked(payload.get("iat"), row["tokens_valid_after"]):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Session has been revoked")

    account = CappeAccount(
        id=row["id"], email=row["email"], name=row["name"], plan=row["plan"],
        status=row["status"], account_type=row["account_type"],
    )
    return _token_response(account)


@router.get("/auth/me", response_model=CappeAccount)
async def me(account: CappeAccount = Depends(require_cappe_account)):
    """Return the current authenticated Cappe account."""
    return account


@router.post("/auth/logout", status_code=status.HTTP_204_NO_CONTENT)
async def logout(account: CappeAccount = Depends(require_cappe_account)):
    """Revoke all of this account's tokens by advancing its watermark — a real
    server-side logout (every existing access + refresh token stops working)."""
    async with get_connection() as conn:
        await conn.execute(
            "UPDATE cappe_accounts SET tokens_valid_after = NOW(), updated_at = NOW() WHERE id = $1",
            account.id,
        )
