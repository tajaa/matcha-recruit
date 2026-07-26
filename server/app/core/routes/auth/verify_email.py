"""auth/verify_email.py (split of the pre-2026-07-25 auth.py monolith)."""


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


class EmailVerifyRequest(BaseModel):
    token: str



@router.post("/verify-email")
async def verify_email(request: EmailVerifyRequest, http_request: Request):
    """Complete a deferred-create signup (resources_free).

    Decodes the email-verification JWT issued by /register/business, then
    runs the same user/company/client-profile creation path that the
    immediate-create flow runs for resources_free. Returns access/refresh
    tokens so the client can drop the user straight into /app/resources.
    """
    ip = client_ip(http_request)
    await check_rate_limit(ip, "verify_email", 20, 3600)
    from ..services.email import get_email_service

    payload = decode_email_verify_token(request.token)
    if not payload:
        raise HTTPException(status_code=400, detail="Invalid or expired verification link")

    if payload.get("tier") != "resources_free":
        # Currently only resources_free uses this flow. Reject other tiers
        # explicitly so a stray token can't create the wrong account shape.
        raise HTTPException(status_code=400, detail="Unsupported verification tier")

    email = payload.get("email")
    name = payload.get("name")
    password_hash = payload.get("password_hash")
    company_name = payload.get("company_name")
    if not (email and name and password_hash and company_name):
        raise HTTPException(status_code=400, detail="Verification token is missing required fields")

    industry = payload.get("industry")
    company_size = payload.get("company_size")
    headcount = payload.get("headcount") or 1
    phone = payload.get("phone")
    job_title = payload.get("job_title")

    async with get_connection() as conn:
        async with conn.transaction():
            # Race-guard: someone may have registered with this email between
            # the verification email being sent and the click. Reject — the
            # earlier signup wins.
            existing = await conn.fetchval("SELECT id FROM users WHERE email = $1", email)
            if existing:
                raise HTTPException(status_code=400, detail="Email already registered")

            company_status = "approved"
            signup_source = "resources_free"
            rf_features = {k: False for k in DEFAULT_COMPANY_FEATURES}
            enabled_features_json = json.dumps(rf_features)

            company = await conn.fetchrow(
                """INSERT INTO companies (name, industry, size, status, approved_at, enabled_features, signup_source)
                   VALUES ($1, $2, $3, $4, $5, $6::jsonb, $7)
                   RETURNING id, name""",
                company_name, industry, company_size,
                company_status, datetime.utcnow(),
                enabled_features_json, signup_source,
            )
            company_id = company["id"]

            from ...matcha.services.billing.token_budget_service import FREE_TOKEN_GRANT
            await conn.execute(
                """INSERT INTO mw_token_budgets (company_id, free_tokens_used, free_token_limit)
                   VALUES ($1, 0, $2)
                   ON CONFLICT (company_id) DO NOTHING""",
                company_id, FREE_TOKEN_GRANT,
            )

            user = await conn.fetchrow(
                """INSERT INTO users (email, password_hash, role)
                   VALUES ($1, $2, 'client')
                   RETURNING id, email, role, is_active, created_at""",
                email, password_hash,
            )

            await conn.execute(
                """INSERT INTO clients (user_id, company_id, name, phone, job_title)
                   VALUES ($1, $2, $3, $4, $5)""",
                user["id"], company_id, name, phone, job_title,
            )

            await conn.execute(
                "UPDATE companies SET owner_id = $1 WHERE id = $2",
                user["id"], company_id,
            )

            await _upsert_business_headcount_profile(
                conn,
                company_id=company_id,
                company_name=company_name,
                owner_name=name,
                headcount=headcount,
                updated_by=user["id"],
            )

    settings = get_settings()
    access_token = create_access_token(user["id"], user["email"], user["role"])
    refresh_token = create_refresh_token(user["id"], user["email"], user["role"])

    email_service = get_email_service()
    try:
        await email_service.send_resources_free_welcome_email(
            to_email=email,
            to_name=name,
            company_name=company_name,
        )
    except Exception:
        # Welcome email is best-effort; the account is already provisioned.
        logger.exception("Failed to send resources_free welcome email")

    return {
        "access_token": access_token,
        "refresh_token": refresh_token,
        "expires_in": settings.jwt_access_token_expire_minutes * 60,
        "user": {
            "id": str(user["id"]),
            "email": user["email"],
            "role": user["role"],
            "is_active": user["is_active"],
            "created_at": user["created_at"].isoformat() if user["created_at"] else None,
            "last_login": None,
        },
        "company_status": company_status,
        "signup_source": signup_source,
        "next": "/app/resources",
        "message": "Email confirmed. Resources unlocked.",
    }

