"""Cappe authentication — signup / login / refresh / me.

Fully separate from matcha's /auth/* (which is hardwired to users+clients).
Backed by `cappe_accounts`; issues Cappe-scoped tokens.
"""
import asyncio
from datetime import datetime, timezone
from uuid import UUID, uuid4

import asyncpg
from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, Request, status

from ...config import get_settings
from ...core.services.email import _is_reserved_test_domain
from ...core.services.redis_cache import check_rate_limit, client_ip
from ...core.services.session_tokens import refresh_session_expired
from ...database import get_connection
from ..dependencies import require_cappe_account
from ..services.commerce import check_recipient_send_ok
from ..services.email import (
    send_cappe_account_exists_email,
    send_cappe_password_reset_email,
    send_cappe_verification_email,
)
from ..models.cappe import (
    CappeAccount,
    CappeForgotPasswordRequest,
    CappeLogin,
    CappeRefreshRequest,
    CappeResendRequest,
    CappeResetPasswordRequest,
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
    hash_reset_token,
    is_cappe_token_revoked,
    make_reset_token,
    verify_password_async,
)

router = APIRouter()

# Verification links are single-use and time-boxed.
_VERIFY_TTL_HOURS = 24
# Reset links are shorter-lived: one grants control of an existing account.
_RESET_TTL_MINUTES = 60

# Precomputed once at import: a throwaway hash to verify against when the login
# email is unknown, so an unknown-email 401 costs the same bcrypt time as a
# wrong-password 401 (closes the timing side-channel that reveals which emails
# have accounts).
_DUMMY_PASSWORD_HASH = hash_password("cappe-login-timing-equalizer")


def _token_response(
    account: CappeAccount,
    session_started_at: int | None = None,
) -> CappeTokenResponse:
    settings = get_settings()
    return CappeTokenResponse(
        access_token=create_cappe_access_token(account.id, account.email),
        refresh_token=create_cappe_refresh_token(
            account.id, account.email, session_started_at=session_started_at
        ),
        expires_in=settings.jwt_access_token_expire_minutes * 60,
        account=account,
    )


@router.post("/auth/signup", response_model=CappeSignupResponse, status_code=status.HTTP_201_CREATED)
async def signup(body: CappeSignup, request: Request, background: BackgroundTasks):
    """Create a new Cappe account behind an email-confirmation gate.

    Real signups get NO tokens — they must click the link we email. This is the
    anti-spam barrier: a bogus or unreachable address never becomes a usable
    account. Reserved test domains (which the email guard won't deliver to)
    auto-verify so dev/seed flows aren't stranded.

    An address that already has an account gets the SAME 201
    `{verification_required: true}` as a fresh one. A 409 here made signup a
    membership oracle for any address an attacker cared to try — the same
    enumeration login and resend already refuse to be. The real owner is told
    by email instead: a confirmed account gets "you already have an account",
    an unconfirmed one gets a fresh confirmation link (signing up again is what
    people do when the first email never arrived)."""
    await check_rate_limit(client_ip(request), "cappe_signup", 5, 3600)
    email = body.email.strip().lower()
    # bcrypt is CPU-blocking (~100ms); run it off the event loop so a burst of
    # signups can't stall every other request on this worker.
    password_hash = await asyncio.to_thread(hash_password, body.password)

    # No deliverable email → no link → would be unverifiable forever. Auto-verify
    # those, outside production only: there it would hand a signed-in, confirmed
    # account to anyone typing an @example.com address.
    auto_verify = _is_reserved_test_domain(email) and not get_settings().is_production
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
            row = None

    if row is None:
        # Duplicate address: answer exactly as a fresh signup would, and tell
        # the real owner out-of-band.
        # Throttled per RECIPIENT (the per-IP signup limit does nothing against
        # rotating addresses) and greeted with the name ON FILE: the name in the
        # request is attacker-typed text, and mailing it to a victim from our
        # domain is a phishing primitive. The cap is checked BEFORE the write so
        # a throttled request can't kill the link already sitting in the inbox.
        if await check_recipient_send_ok(email):
            async with get_connection() as conn:
                existing = await conn.fetchrow(
                    "SELECT id, email, name, email_verified_at FROM cappe_accounts "
                    "WHERE lower(email) = $1",
                    email,
                )
                if existing is not None and existing["email_verified_at"] is None and token is not None:
                    # Still unconfirmed: the first email never arrived or
                    # expired. Issue a fresh link. The password and profile on
                    # file are deliberately left alone: whoever sends this
                    # request has not proven they own the inbox, and letting
                    # them replace the password would hand them the account
                    # the moment the real owner clicks the link.
                    await conn.execute(
                        "UPDATE cappe_accounts SET verification_token = $1, "
                        "verification_sent_at = NOW(), updated_at = NOW() "
                        "WHERE id = $2 AND email_verified_at IS NULL",
                        token,
                        existing["id"],
                    )
                    background.add_task(
                        send_cappe_verification_email, existing["email"], existing["name"], str(token)
                    )
                elif existing is not None:
                    background.add_task(send_cappe_account_exists_email, existing["email"], existing["name"])
        return CappeSignupResponse(verification_required=True, email=email)

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
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail={"code": "verification_invalid", "message": "Invalid confirmation link"},
        )

    async with get_connection() as conn:
        row = await conn.fetchrow(
            """SELECT id, email, name, plan, status, account_type, verification_sent_at
               FROM cappe_accounts WHERE verification_token = $1""",
            token,
        )
        if row is None:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail={
                    "code": "verification_invalid",
                    "message": "This confirmation link is invalid or has already been used.",
                },
            )
        sent_at = row["verification_sent_at"]
        if sent_at is not None:
            # sent_at is TIMESTAMPTZ → tz-aware; compute the age in-process rather
            # than paying a second round-trip just to subtract two timestamps.
            age_hours = (datetime.now(timezone.utc) - sent_at).total_seconds() / 3600
            if age_hours > _VERIFY_TTL_HOURS:
                raise HTTPException(
                    status_code=status.HTTP_410_GONE,
                    detail={
                        "code": "verification_expired",
                        "message": "This confirmation link has expired. Request a new one.",
                    },
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


@router.post("/auth/forgot-password", status_code=status.HTTP_202_ACCEPTED)
async def forgot_password(body: CappeForgotPasswordRequest, request: Request, background: BackgroundTasks):
    """Email a password-reset link. Always 202 (never leaks whether the address
    has an account); only actually sends for a real, active account."""
    ip = client_ip(request)
    await check_rate_limit(ip, "cappe_forgot_min", 2, 60)
    await check_rate_limit(ip, "cappe_forgot_hr", 6, 3600)
    email = body.email.strip().lower()

    # Per-recipient cap checked BEFORE the write: a throttled request must not
    # replace the token behind a link already sitting in the inbox.
    if not _is_reserved_test_domain(email) and await check_recipient_send_ok(email):
        async with get_connection() as conn:
            row = await conn.fetchrow(
                "SELECT id, email, name, status FROM cappe_accounts WHERE lower(email) = $1",
                email,
            )
            if row is not None and row["status"] == "active":
                token = make_reset_token()
                await conn.execute(
                    "UPDATE cappe_accounts SET password_reset_token_hash = $1, "
                    "password_reset_sent_at = NOW(), updated_at = NOW() WHERE id = $2",
                    hash_reset_token(token),
                    row["id"],
                )
                background.add_task(send_cappe_password_reset_email, row["email"], row["name"], token)
    return {"status": "ok"}


@router.post("/auth/reset-password", status_code=status.HTTP_204_NO_CONTENT)
async def reset_password(body: CappeResetPasswordRequest, request: Request):
    """Set a new password from an emailed reset link.

    Single-use and time-boxed. Every existing session is revoked, and the
    account is marked confirmed: reaching this endpoint with a valid token
    proves control of the inbox, which is all email confirmation asks for (and
    it rescues an account whose confirmation email never arrived). No tokens
    are returned; the person signs in with the new password."""
    await check_rate_limit(client_ip(request), "cappe_reset", 10, 3600)
    token_hash = hash_reset_token(body.token)
    invalid = HTTPException(
        status_code=status.HTTP_400_BAD_REQUEST,
        detail={
            "code": "reset_invalid",
            "message": "This reset link is invalid or has already been used. Request a new one.",
        },
    )

    async with get_connection() as conn:
        row = await conn.fetchrow(
            "SELECT id, password_reset_sent_at FROM cappe_accounts "
            "WHERE password_reset_token_hash = $1 AND status = 'active'",
            token_hash,
        )
    if row is None:
        raise invalid
    sent_at = row["password_reset_sent_at"]
    if sent_at is None or (datetime.now(timezone.utc) - sent_at).total_seconds() > _RESET_TTL_MINUTES * 60:
        raise HTTPException(
            status_code=status.HTTP_410_GONE,
            detail={"code": "reset_expired", "message": "This reset link has expired. Request a new one."},
        )

    password_hash = await asyncio.to_thread(hash_password, body.password)
    async with get_connection() as conn:
        # Guarded on the token hash so two requests racing on one link cannot
        # both win, and a link replaced by a newer request stops working.
        # `tokens_valid_after` is the revocation watermark the auth dependency
        # and /auth/refresh already check; unlike logout it is not floored to
        # the second, so a session opened a moment ago dies too.
        updated = await conn.fetchval(
            """UPDATE cappe_accounts
                  SET password_hash = $1,
                      password_reset_token_hash = NULL,
                      password_reset_sent_at = NULL,
                      tokens_valid_after = NOW(),
                      email_verified_at = COALESCE(email_verified_at, NOW()),
                      verification_token = NULL,
                      updated_at = NOW()
                WHERE id = $2 AND password_reset_token_hash = $3
            RETURNING id""",
            password_hash,
            row["id"],
            token_hash,
        )
    if updated is None:
        raise invalid


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

    # Constant-ish failure: same 401 AND same bcrypt cost whether the email is
    # unknown or the password is wrong. When the account doesn't exist we still
    # run a verify against a throwaway hash so response timing can't be used to
    # enumerate which emails have accounts.
    if row is None:
        await verify_password_async(body.password, _DUMMY_PASSWORD_HASH)
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Incorrect email or password",
        )
    if not await verify_password_async(body.password, row["password_hash"]):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Incorrect email or password",
        )
    if row["status"] != "active":
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Account is not active")
    # Email-confirmation gate: only verified accounts can sign in. 403 with a
    # stable code so the UI can offer "resend confirmation". The message text is
    # load-bearing too: the iOS app still matches on "confirm your email".
    if row["email_verified_at"] is None:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail={
                "code": "email_unverified",
                "message": "Please confirm your email before signing in. Check your inbox for the link.",
            },
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

    if refresh_session_expired(payload.get("iat"), payload.get("session_started_at")):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Session expired")

    # Revoked refresh tokens (issued before logout / password change) can't re-mint.
    if is_cappe_token_revoked(payload.get("iat"), row["tokens_valid_after"], payload.get("iat_ms")):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Session has been revoked")

    account = CappeAccount(
        id=row["id"], email=row["email"], name=row["name"], plan=row["plan"],
        status=row["status"], account_type=row["account_type"],
    )
    return _token_response(
        account,
        session_started_at=payload.get("session_started_at") or payload.get("iat"),
    )


@router.get("/auth/me", response_model=CappeAccount)
async def me(account: CappeAccount = Depends(require_cappe_account)):
    """Return the current authenticated Cappe account."""
    return account


@router.post("/auth/logout", status_code=status.HTTP_204_NO_CONTENT)
async def logout(account: CappeAccount = Depends(require_cappe_account)):
    """Revoke all of this account's tokens by advancing its watermark — a real
    server-side logout (every existing access + refresh token stops working)."""
    async with get_connection() as conn:
        # Floored to the second: `iat` claims are whole seconds, so a
        # microsecond-precision watermark can outrun a same-second login's
        # token and lock it out immediately. See is_token_revoked's docstring.
        await conn.execute(
            "UPDATE cappe_accounts SET tokens_valid_after = date_trunc('second', NOW()), "
            "updated_at = NOW() WHERE id = $1",
            account.id,
        )
