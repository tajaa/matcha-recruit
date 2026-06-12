"""Cappe authentication — signup / login / refresh / me.

Fully separate from matcha's /auth/* (which is hardwired to users+clients).
Backed by `cappe_accounts`; issues Cappe-scoped tokens.
"""
from uuid import UUID

import asyncpg
from fastapi import APIRouter, Depends, HTTPException, status

from ...config import get_settings
from ...database import get_connection
from ..dependencies import require_cappe_account
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
async def signup(body: CappeSignup):
    """Create a new Cappe account and return tokens."""
    email = body.email.strip().lower()
    password_hash = hash_password(body.password)

    async with get_connection() as conn:
        try:
            row = await conn.fetchrow(
                """INSERT INTO cappe_accounts (email, password_hash, name)
                   VALUES ($1, $2, $3)
                   RETURNING id, email, name, plan, status""",
                email,
                password_hash,
                body.name,
            )
        except asyncpg.UniqueViolationError:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="An account with this email already exists",
            )

    account = CappeAccount(**dict(row))
    return _token_response(account)


@router.post("/auth/login", response_model=CappeTokenResponse)
async def login(body: CappeLogin):
    """Authenticate a Cappe account by email + password."""
    email = body.email.strip().lower()

    async with get_connection() as conn:
        row = await conn.fetchrow(
            """SELECT id, email, name, plan, status, password_hash
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
        id=row["id"], email=row["email"], name=row["name"], plan=row["plan"], status=row["status"]
    )
    return _token_response(account)


@router.post("/auth/refresh", response_model=CappeTokenResponse)
async def refresh(body: CappeRefreshRequest):
    """Exchange a valid Cappe refresh token for a fresh token pair."""
    payload = decode_cappe_token(body.refresh_token, expected_type="refresh")
    if payload is None:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid refresh token")

    try:
        account_id = UUID(payload["sub"])
    except (KeyError, ValueError, TypeError):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid refresh token")

    async with get_connection() as conn:
        row = await conn.fetchrow(
            "SELECT id, email, name, plan, status FROM cappe_accounts WHERE id = $1",
            account_id,
        )

    if row is None or row["status"] != "active":
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Account not found or inactive")

    account = CappeAccount(**dict(row))
    return _token_response(account)


@router.get("/auth/me", response_model=CappeAccount)
async def me(account: CappeAccount = Depends(require_cappe_account)):
    """Return the current authenticated Cappe account."""
    return account
