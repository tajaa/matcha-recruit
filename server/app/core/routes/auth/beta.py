"""auth/beta.py (split of the pre-2026-07-25 auth.py monolith)."""


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


class BetaRegisterRequest(BaseModel):
    token: str
    password: str
    name: str



@router.get("/beta-invite/{token}")
async def validate_beta_invite(token: str):
    """Validate a beta invitation token (public, no auth)."""
    async with get_connection() as conn:
        row = await conn.fetchrow(
            "SELECT email, status FROM beta_invitations WHERE token = $1",
            token,
        )
    if not row or row["status"] != "pending":
        return {"valid": False, "email": None}
    return {"valid": True, "email": row["email"]}



@router.post("/register/beta")
async def register_beta(request: BetaRegisterRequest, http_request: Request):
    """Register a new individual account via beta invitation token."""
    ip = client_ip(http_request)
    await check_rate_limit(ip, "register_beta", 10, 3600)
    from ..feature_flags import DEFAULT_COMPANY_FEATURES
    from ...matcha.services.billing.token_budget_service import FREE_TOKEN_GRANT

    async with get_connection() as conn:
        async with conn.transaction():
            invite = await conn.fetchrow(
                "SELECT id, email, status FROM beta_invitations WHERE token = $1 FOR UPDATE",
                request.token,
            )
            if not invite or invite["status"] != "pending":
                raise HTTPException(status_code=400, detail="Invalid or expired invitation")

            email = invite["email"]

            existing = await conn.fetchval("SELECT id FROM users WHERE email = $1", email)
            if existing:
                raise HTTPException(status_code=400, detail="Email already registered")

            # Create personal workspace (same as register_individual)
            personal_features = {**DEFAULT_COMPANY_FEATURES, "matcha_work": True}
            company = await conn.fetchrow(
                """INSERT INTO companies (name, status, approved_at, is_personal, enabled_features)
                   VALUES ($1, 'approved', NOW(), true, $2::jsonb)
                   RETURNING id""",
                f"{request.name}'s Workspace",
                json.dumps(personal_features),
            )
            company_id = company["id"]

            await conn.execute(
                """INSERT INTO mw_token_budgets (company_id, free_tokens_used, free_token_limit)
                   VALUES ($1, 0, $2) ON CONFLICT (company_id) DO NOTHING""",
                company_id, FREE_TOKEN_GRANT,
            )

            password_hash = hash_password(request.password)
            user = await conn.fetchrow(
                """INSERT INTO users (email, password_hash, role)
                   VALUES ($1, $2, 'individual')
                   RETURNING id, email, role""",
                email, password_hash,
            )

            await conn.execute(
                "INSERT INTO clients (user_id, company_id, name) VALUES ($1, $2, $3)",
                user["id"], company_id, request.name,
            )
            await conn.execute("UPDATE companies SET owner_id = $1 WHERE id = $2", user["id"], company_id)

            # Mark invitation as registered
            await conn.execute(
                "UPDATE beta_invitations SET status = 'registered', registered_at = NOW(), user_id = $1 WHERE id = $2",
                user["id"], invite["id"],
            )

    settings = get_settings()
    access_token = create_access_token(user["id"], user["email"], user["role"])
    refresh_token = create_refresh_token(user["id"], user["email"], user["role"])

    return {
        "access_token": access_token,
        "refresh_token": refresh_token,
        "token_type": "bearer",
        "expires_in": settings.jwt_access_token_expire_minutes * 60,
        "user": {"id": str(user["id"]), "email": user["email"], "role": user["role"]},
    }


# ── Individual registration ──

