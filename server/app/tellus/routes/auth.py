"""Tell-Us authentication — signup / login / verify / refresh / me / logout.

Fully separate from matcha's and cappe's /auth. Backed by `tellus_accounts`;
issues Tell-Us-scoped tokens. A brand signup provisions a `tellus_brands` row;
a consumer signup geocodes its city (best-effort) for the marketplace.
"""
from uuid import UUID, uuid4

import asyncpg
from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, Request, status

from ...config import get_settings
from ...core.services.email import _is_reserved_test_domain
from ...core.services.redis_cache import check_rate_limit, client_ip
from ...database import get_connection
from ..dependencies import require_tellus_account
from ..models.tellus import (
    TellusAccount,
    TellusLocationUpdate,
    TellusLogin,
    TellusProfileUpdate,
    TellusRefreshRequest,
    TellusResendRequest,
    TellusSignup,
    TellusSignupResponse,
    TellusTokenResponse,
    TellusVerifyRequest,
)
from ..services.auth import (
    create_tellus_access_token,
    create_tellus_refresh_token,
    decode_tellus_token,
    hash_password,
    is_tellus_token_revoked,
    verify_password_async,
)
from ..services.email import send_tellus_verification_email
from ..services.geo import geocode_location

router = APIRouter()

_VERIFY_TTL_HOURS = 24


async def _load_account(conn, account_id: UUID) -> TellusAccount:
    row = await conn.fetchrow(
        """SELECT a.id, a.email, a.display_name, a.account_type, a.status,
                  a.city, a.state, a.leaderboard_opt_in, b.id AS brand_id
           FROM tellus_accounts a
           LEFT JOIN tellus_brands b ON b.owner_account_id = a.id
           WHERE a.id = $1""",
        account_id,
    )
    return TellusAccount(
        id=row["id"], email=row["email"], display_name=row["display_name"],
        account_type=row["account_type"], status=row["status"], city=row["city"],
        state=row["state"], leaderboard_opt_in=row["leaderboard_opt_in"], brand_id=row["brand_id"],
    )


def _token_response(account: TellusAccount) -> TellusTokenResponse:
    settings = get_settings()
    return TellusTokenResponse(
        access_token=create_tellus_access_token(account.id, account.email),
        refresh_token=create_tellus_refresh_token(account.id, account.email),
        expires_in=settings.jwt_access_token_expire_minutes * 60,
        account=account,
    )


@router.post("/auth/signup", response_model=TellusSignupResponse, status_code=status.HTTP_201_CREATED)
async def signup(body: TellusSignup, request: Request, background: BackgroundTasks):
    """Create a consumer or brand account behind an email-confirmation gate.

    Reserved test domains auto-verify (the email guard won't deliver to them) so
    dev/seed flows still work. Brand signups provision a brand row; consumer
    signups geocode their city."""
    await check_rate_limit(client_ip(request), "tellus_signup", 5, 3600)
    email = body.email.strip().lower()
    password_hash = hash_password(body.password)
    auto_verify = _is_reserved_test_domain(email)
    token = None if auto_verify else uuid4()

    geo = None
    if body.account_type == "consumer" and body.city:
        geo = await geocode_location(body.city, body.state)

    async with get_connection() as conn:
        async with conn.transaction():
            try:
                row = await conn.fetchrow(
                    """INSERT INTO tellus_accounts
                           (email, password_hash, display_name, account_type, city, state,
                            latitude, longitude, county, geo_updated_at,
                            email_verified_at, verification_token, verification_sent_at)
                       VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9,
                            CASE WHEN $10 THEN NOW() ELSE NULL END,
                            CASE WHEN $11 THEN NOW() ELSE NULL END, $12,
                            CASE WHEN $11 THEN NULL ELSE NOW() END)
                       RETURNING id""",
                    email, password_hash, body.display_name, body.account_type,
                    body.city, body.state,
                    geo["lat"] if geo else None, geo["lng"] if geo else None,
                    geo["county"] if geo else None, geo is not None,
                    auto_verify, token,
                )
            except asyncpg.UniqueViolationError:
                raise HTTPException(
                    status_code=status.HTTP_409_CONFLICT,
                    detail="An account with this email already exists",
                )
            account_id = row["id"]

            if body.account_type == "brand":
                brand_name = (body.brand_name or body.display_name or "My Brand").strip() or "My Brand"
                await conn.execute(
                    "INSERT INTO tellus_brands (owner_account_id, name) VALUES ($1, $2)",
                    account_id, brand_name,
                )
            else:
                await conn.execute(
                    "INSERT INTO tellus_points_balances (account_id) VALUES ($1) ON CONFLICT DO NOTHING",
                    account_id,
                )

        account = await _load_account(conn, account_id)

    if auto_verify:
        tokens = _token_response(account)
        return TellusSignupResponse(
            verification_required=False, email=account.email,
            access_token=tokens.access_token, refresh_token=tokens.refresh_token,
            expires_in=tokens.expires_in, account=account,
        )

    background.add_task(send_tellus_verification_email, account.email, account.display_name, str(token))
    return TellusSignupResponse(verification_required=True, email=account.email)


@router.post("/auth/verify", response_model=TellusTokenResponse)
async def verify_email(body: TellusVerifyRequest, request: Request):
    """Confirm an account via its emailed token, then auto-sign-in."""
    await check_rate_limit(client_ip(request), "tellus_verify", 20, 3600)
    try:
        token = UUID(body.token)
    except (ValueError, TypeError):
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Invalid confirmation link")

    async with get_connection() as conn:
        row = await conn.fetchrow(
            "SELECT id, verification_sent_at FROM tellus_accounts WHERE verification_token = $1",
            token,
        )
        if row is None:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="This confirmation link is invalid or has already been used.",
            )
        sent_at = row["verification_sent_at"]
        if sent_at is not None:
            age_hours = await conn.fetchval("SELECT EXTRACT(EPOCH FROM (NOW() - $1))/3600", sent_at)
            if age_hours is not None and age_hours > _VERIFY_TTL_HOURS:
                raise HTTPException(
                    status_code=status.HTTP_410_GONE,
                    detail="This confirmation link has expired. Request a new one.",
                )
        await conn.execute(
            "UPDATE tellus_accounts SET email_verified_at = NOW(), verification_token = NULL, "
            "updated_at = NOW() WHERE id = $1",
            row["id"],
        )
        account = await _load_account(conn, row["id"])
    return _token_response(account)


@router.post("/auth/resend-verification", status_code=status.HTTP_202_ACCEPTED)
async def resend_verification(body: TellusResendRequest, request: Request, background: BackgroundTasks):
    """Re-send the confirmation email. Always 202 (never leaks existence)."""
    ip = client_ip(request)
    await check_rate_limit(ip, "tellus_resend_min", 2, 60)
    await check_rate_limit(ip, "tellus_resend_hr", 6, 3600)
    email = body.email.strip().lower()

    async with get_connection() as conn:
        row = await conn.fetchrow(
            "SELECT id, email, display_name, email_verified_at FROM tellus_accounts WHERE lower(email) = $1",
            email,
        )
        if row is not None and row["email_verified_at"] is None and not _is_reserved_test_domain(email):
            token = uuid4()
            await conn.execute(
                "UPDATE tellus_accounts SET verification_token = $1, verification_sent_at = NOW(), "
                "updated_at = NOW() WHERE id = $2",
                token, row["id"],
            )
            background.add_task(send_tellus_verification_email, row["email"], row["display_name"], str(token))
    return {"status": "ok"}


@router.post("/auth/login", response_model=TellusTokenResponse)
async def login(body: TellusLogin, request: Request):
    """Authenticate a Tell-Us account by email + password."""
    ip = client_ip(request)
    await check_rate_limit(ip, "tellus_login_min", 10, 60)
    await check_rate_limit(ip, "tellus_login_hr", 60, 3600)
    email = body.email.strip().lower()

    async with get_connection() as conn:
        row = await conn.fetchrow(
            "SELECT id, status, password_hash, email_verified_at "
            "FROM tellus_accounts WHERE lower(email) = $1",
            email,
        )
        if row is None or not await verify_password_async(body.password, row["password_hash"]):
            raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Incorrect email or password")
        if row["status"] != "active":
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Account is not active")
        if row["email_verified_at"] is None:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Please confirm your email before signing in. Check your inbox for the link.",
            )
        account = await _load_account(conn, row["id"])
    return _token_response(account)


@router.post("/auth/refresh", response_model=TellusTokenResponse)
async def refresh(body: TellusRefreshRequest, request: Request):
    """Exchange a valid Tell-Us refresh token for a fresh token pair."""
    await check_rate_limit(client_ip(request), "tellus_refresh", 60, 3600)
    payload = decode_tellus_token(body.refresh_token, expected_type="refresh")
    if payload is None:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid refresh token")
    try:
        account_id = UUID(payload["sub"])
    except (KeyError, ValueError, TypeError):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid refresh token")

    async with get_connection() as conn:
        row = await conn.fetchrow(
            "SELECT status, tokens_valid_after FROM tellus_accounts WHERE id = $1", account_id
        )
        if row is None or row["status"] != "active":
            raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Account not found or inactive")
        if is_tellus_token_revoked(payload.get("iat"), row["tokens_valid_after"]):
            raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Session has been revoked")
        account = await _load_account(conn, account_id)
    return _token_response(account)


@router.get("/auth/me", response_model=TellusAccount)
async def me(account: TellusAccount = Depends(require_tellus_account)):
    return account


@router.post("/auth/logout", status_code=status.HTTP_204_NO_CONTENT)
async def logout(account: TellusAccount = Depends(require_tellus_account)):
    """Server-side logout — advance the revocation watermark."""
    async with get_connection() as conn:
        await conn.execute(
            "UPDATE tellus_accounts SET tokens_valid_after = NOW(), updated_at = NOW() WHERE id = $1",
            account.id,
        )


@router.post("/me/location", response_model=TellusAccount)
async def set_location(
    body: TellusLocationUpdate, account: TellusAccount = Depends(require_tellus_account)
):
    """Set the consumer's city (geocoded) — drives the marketplace filter."""
    geo = await geocode_location(body.city, body.state, body.zipcode)
    async with get_connection() as conn:
        await conn.execute(
            """UPDATE tellus_accounts
               SET city = $2, state = $3, latitude = $4, longitude = $5, county = $6,
                   geo_updated_at = CASE WHEN $7 THEN NOW() ELSE geo_updated_at END,
                   updated_at = NOW()
               WHERE id = $1""",
            account.id, body.city, body.state,
            geo["lat"] if geo else None, geo["lng"] if geo else None,
            geo["county"] if geo else None, geo is not None,
        )
        return await _load_account(conn, account.id)


@router.patch("/me", response_model=TellusAccount)
async def update_profile(
    body: TellusProfileUpdate, account: TellusAccount = Depends(require_tellus_account)
):
    """Update display name / leaderboard opt-in."""
    async with get_connection() as conn:
        await conn.execute(
            """UPDATE tellus_accounts
               SET display_name = COALESCE($2, display_name),
                   leaderboard_opt_in = COALESCE($3, leaderboard_opt_in),
                   updated_at = NOW()
               WHERE id = $1""",
            account.id, body.display_name, body.leaderboard_opt_in,
        )
        return await _load_account(conn, account.id)
