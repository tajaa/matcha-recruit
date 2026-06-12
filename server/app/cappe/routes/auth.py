"""Cappe authentication — signup / login / refresh / me.

Fully separate from matcha's /auth/* (which is hardwired to users+clients).
Backed by `cappe_accounts`; issues Cappe-scoped tokens.
"""
from uuid import UUID, uuid4

import asyncpg
from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, Request, status

from ...config import get_settings
from ...core.services.email import _is_reserved_test_domain
from ...core.services.redis_cache import check_rate_limit, client_ip
from ...database import get_connection
from ..dependencies import require_cappe_account
from ..services.email import send_cappe_verification_email
from ..models.cappe import (
    CappeAccount,
    CappeLogin,
    CappeRefreshRequest,
    CappeResendRequest,
    CappeSignup,
    CappeSignupResponse,
    CappeTokenResponse,
    CappeVerifyRequest,
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

# Verification links are single-use and time-boxed.
_VERIFY_TTL_HOURS = 24


def _token_response(account: CappeAccount) -> CappeTokenResponse:
    settings = get_settings()
    return CappeTokenResponse(
        access_token=create_cappe_access_token(account.id, account.email),
        refresh_token=create_cappe_refresh_token(account.id, account.email),
        expires_in=settings.jwt_access_token_expire_minutes * 60,
        account=account,
    )


@router.post("/auth/signup", response_model=CappeSignupResponse, status_code=status.HTTP_201_CREATED)
async def signup(body: CappeSignup, request: Request, background: BackgroundTasks):
    """Create a new Cappe account behind an email-confirmation gate.

    Real signups get NO tokens — they must click the link we email. This is the
    anti-spam barrier: a bogus or unreachable address never becomes a usable
    account. Reserved test domains (which the email guard won't deliver to)
    auto-verify so dev/seed flows aren't stranded."""
    await check_rate_limit(client_ip(request), "cappe_signup", 5, 3600)
    email = body.email.strip().lower()
    password_hash = hash_password(body.password)

    # No deliverable email → no link → would be unverifiable forever. Auto-verify
    # those (dev/seed only; real users are on deliverable domains).
    auto_verify = _is_reserved_test_domain(email)
    token = None if auto_verify else uuid4()

    async with get_connection() as conn:
        try:
            row = await conn.fetchrow(
                """INSERT INTO cappe_accounts
                       (email, password_hash, name, account_type,
                        email_verified_at, verification_token, verification_sent_at)
                   VALUES ($1, $2, $3, $4,
                        CASE WHEN $5 THEN NOW() ELSE NULL END, $6,
                        CASE WHEN $5 THEN NULL ELSE NOW() END)
                   RETURNING id, email, name, plan, status, account_type""",
                email,
                password_hash,
                body.name,
                body.account_type,
                auto_verify,
                token,
            )
        except asyncpg.UniqueViolationError:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="An account with this email already exists",
            )

    account = CappeAccount(**dict(row))

    if auto_verify:
        tokens = _token_response(account)
        return CappeSignupResponse(
            verification_required=False,
            email=account.email,
            access_token=tokens.access_token,
            refresh_token=tokens.refresh_token,
            expires_in=tokens.expires_in,
            account=account,
        )

    # Confirmation email after the response is sent.
    background.add_task(send_cappe_verification_email, account.email, account.name, str(token))
    return CappeSignupResponse(verification_required=True, email=account.email)


@router.post("/auth/verify", response_model=CappeTokenResponse)
async def verify_email(body: CappeVerifyRequest, request: Request):
    """Confirm an account via its emailed token, then auto-sign-in."""
    await check_rate_limit(client_ip(request), "cappe_verify", 20, 3600)
    try:
        token = UUID(body.token)
    except (ValueError, TypeError):
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Invalid confirmation link")

    async with get_connection() as conn:
        row = await conn.fetchrow(
            """SELECT id, email, name, plan, status, account_type, verification_sent_at
               FROM cappe_accounts WHERE verification_token = $1""",
            token,
        )
        if row is None:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="This confirmation link is invalid or has already been used.",
            )
        sent_at = row["verification_sent_at"]
        if sent_at is not None:
            age_hours = (await conn.fetchval("SELECT EXTRACT(EPOCH FROM (NOW() - $1))/3600", sent_at))
            if age_hours is not None and age_hours > _VERIFY_TTL_HOURS:
                raise HTTPException(
                    status_code=status.HTTP_410_GONE,
                    detail="This confirmation link has expired. Request a new one.",
                )
        # Single-use: clear the token as we verify.
        await conn.execute(
            "UPDATE cappe_accounts SET email_verified_at = NOW(), verification_token = NULL, "
            "updated_at = NOW() WHERE id = $1",
            row["id"],
        )

    account = CappeAccount(
        id=row["id"], email=row["email"], name=row["name"], plan=row["plan"],
        status=row["status"], account_type=row["account_type"],
    )
    return _token_response(account)


@router.post("/auth/resend-verification", status_code=status.HTTP_202_ACCEPTED)
async def resend_verification(body: CappeResendRequest, request: Request, background: BackgroundTasks):
    """Re-send the confirmation email. Always 202 (never leaks whether the
    address exists); only actually sends for a real, still-unverified account."""
    ip = client_ip(request)
    await check_rate_limit(ip, "cappe_resend_min", 2, 60)
    await check_rate_limit(ip, "cappe_resend_hr", 6, 3600)
    email = body.email.strip().lower()

    async with get_connection() as conn:
        row = await conn.fetchrow(
            "SELECT id, email, name, email_verified_at FROM cappe_accounts WHERE lower(email) = $1",
            email,
        )
        if row is not None and row["email_verified_at"] is None and not _is_reserved_test_domain(email):
            token = uuid4()
            await conn.execute(
                "UPDATE cappe_accounts SET verification_token = $1, verification_sent_at = NOW(), "
                "updated_at = NOW() WHERE id = $2",
                token,
                row["id"],
            )
            background.add_task(send_cappe_verification_email, row["email"], row["name"], str(token))
    return {"status": "ok"}


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
            """SELECT id, email, name, plan, status, account_type, password_hash, email_verified_at
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
    # Email-confirmation gate: only verified accounts can sign in. 403 with a
    # distinct marker so the UI can offer "resend confirmation".
    if row["email_verified_at"] is None:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Please confirm your email before signing in. Check your inbox for the link.",
        )

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
