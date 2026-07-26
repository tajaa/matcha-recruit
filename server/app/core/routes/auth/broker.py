"""auth/broker.py (split of the pre-2026-07-25 auth.py monolith)."""


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


BROKER_BRANDING_KEY_RE = re.compile(r"^[a-z0-9-]{2,120}$")



@router.get("/broker-branding/{broker_key}", response_model=BrokerBrandingRuntimeResponse)
async def get_broker_branding_runtime(broker_key: str):
    """Resolve broker branding config by broker slug or login subdomain."""
    key = (broker_key or "").strip().lower()
    if not BROKER_BRANDING_KEY_RE.fullmatch(key):
        raise HTTPException(status_code=400, detail="broker_key must be 2-120 chars [a-z0-9-]")

    async with get_connection() as conn:
        row = await conn.fetchrow(
            """
            SELECT
                b.id as broker_id,
                b.slug as broker_slug,
                b.name as broker_name,
                COALESCE(cfg.branding_mode, 'direct') as branding_mode,
                COALESCE(NULLIF(cfg.brand_display_name, ''), b.name) as brand_display_name,
                cfg.brand_legal_name,
                cfg.logo_url,
                cfg.favicon_url,
                cfg.primary_color,
                cfg.secondary_color,
                cfg.login_subdomain,
                cfg.custom_login_url,
                cfg.support_email,
                cfg.support_phone,
                cfg.support_url,
                cfg.email_from_name,
                cfg.email_from_address,
                COALESCE(cfg.powered_by_badge, true) as powered_by_badge,
                COALESCE(cfg.hide_matcha_identity, false) as hide_matcha_identity,
                COALESCE(cfg.mobile_branding_enabled, false) as mobile_branding_enabled,
                COALESCE(cfg.theme, '{}'::jsonb) as theme,
                CASE WHEN cfg.login_subdomain = $1 THEN 'subdomain' ELSE 'slug' END as resolved_by
            FROM brokers b
            LEFT JOIN broker_branding_configs cfg ON cfg.broker_id = b.id
            WHERE b.status = 'active'
              AND (b.slug = $1 OR cfg.login_subdomain = $1)
            ORDER BY CASE WHEN cfg.login_subdomain = $1 THEN 0 ELSE 1 END, b.created_at ASC
            LIMIT 1
            """,
            key,
        )

    if not row:
        raise HTTPException(status_code=404, detail="Broker branding not found")

    return BrokerBrandingRuntimeResponse(
        broker_id=row["broker_id"],
        broker_slug=row["broker_slug"],
        broker_name=row["broker_name"],
        branding_mode=row["branding_mode"],
        brand_display_name=row["brand_display_name"],
        brand_legal_name=row["brand_legal_name"],
        logo_url=row["logo_url"],
        favicon_url=row["favicon_url"],
        primary_color=row["primary_color"],
        secondary_color=row["secondary_color"],
        login_subdomain=row["login_subdomain"],
        custom_login_url=row["custom_login_url"],
        support_email=row["support_email"],
        support_phone=row["support_phone"],
        support_url=row["support_url"],
        email_from_name=row["email_from_name"],
        email_from_address=row["email_from_address"],
        powered_by_badge=bool(row["powered_by_badge"]),
        hide_matcha_identity=bool(row["hide_matcha_identity"]),
        mobile_branding_enabled=bool(row["mobile_branding_enabled"]),
        theme=_json_object(row["theme"]),
        resolved_by="subdomain" if row["resolved_by"] == "subdomain" else "slug",
    )



@router.get("/broker-client-invite/{token}", response_model=BrokerClientInviteDetailsResponse)
async def validate_broker_client_invite(token: str):
    """Validate a broker-generated client onboarding invite token."""
    async with get_connection() as conn:
        row = await conn.fetchrow(
            """
            SELECT
                s.id, s.broker_id, s.company_id, s.status, s.invite_expires_at, s.contact_email,
                c.name as company_name,
                b.name as broker_name
            FROM broker_client_setups s
            JOIN companies c ON c.id = s.company_id
            JOIN brokers b ON b.id = s.broker_id
            WHERE s.invite_token = $1
            """,
            token,
        )
        if not row:
            raise HTTPException(status_code=404, detail="Invite not found or invalid")

        if row["status"] != "invited":
            raise HTTPException(status_code=400, detail=f"Invite is no longer valid (status: {row['status']})")

        if not row["invite_expires_at"] or row["invite_expires_at"] < datetime.now(timezone.utc):
            await conn.execute(
                """
                UPDATE broker_client_setups
                SET status = 'expired',
                    expired_at = NOW(),
                    updated_at = NOW()
                WHERE id = $1
                """,
                row["id"],
            )
            await conn.execute(
                """
                UPDATE broker_company_links
                SET status = 'terminated',
                    terminated_at = COALESCE(terminated_at, NOW()),
                    updated_at = NOW()
                WHERE broker_id = $1
                  AND company_id = $2
                  AND status = 'pending'
                """,
                row["broker_id"],
                row["company_id"],
            )
            raise HTTPException(status_code=400, detail="Invite has expired")

        if not row["contact_email"]:
            raise HTTPException(status_code=400, detail="Invite is missing contact email")

        return BrokerClientInviteDetailsResponse(
            valid=True,
            broker_name=row["broker_name"],
            company_name=row["company_name"],
            contact_email=row["contact_email"],
            invite_expires_at=row["invite_expires_at"],
        )



@router.post("/broker-client-invite/{token}/accept")
async def accept_broker_client_invite(token: str, request: BrokerClientInviteAcceptRequest, http_request: Request):
    """Accept a broker client invite and provision the first company client admin user."""
    ip = client_ip(http_request)
    await check_rate_limit(ip, "broker_invite_accept", 10, 3600)
    async with get_connection() as conn:
        async with conn.transaction():
            invite = await conn.fetchrow(
                """
                SELECT
                    s.id, s.broker_id, s.company_id, s.status, s.invite_expires_at,
                    s.contact_name, s.contact_email, s.contact_phone,
                    c.name as company_name,
                    b.name as broker_name
                FROM broker_client_setups s
                JOIN companies c ON c.id = s.company_id
                JOIN brokers b ON b.id = s.broker_id
                WHERE s.invite_token = $1
                FOR UPDATE
                """,
                token,
            )
            if not invite:
                raise HTTPException(status_code=404, detail="Invite not found or invalid")

            if invite["status"] != "invited":
                raise HTTPException(status_code=400, detail=f"Invite is no longer valid (status: {invite['status']})")

            if not invite["invite_expires_at"] or invite["invite_expires_at"] < datetime.now(timezone.utc):
                await conn.execute(
                    """
                    UPDATE broker_client_setups
                    SET status = 'expired',
                        expired_at = NOW(),
                        updated_at = NOW()
                    WHERE id = $1
                    """,
                    invite["id"],
                )
                await conn.execute(
                    """
                    UPDATE broker_company_links
                    SET status = 'terminated',
                        terminated_at = COALESCE(terminated_at, NOW()),
                        updated_at = NOW()
                    WHERE broker_id = $1
                      AND company_id = $2
                      AND status = 'pending'
                    """,
                    invite["broker_id"],
                    invite["company_id"],
                )
                raise HTTPException(status_code=400, detail="Invite has expired")

            email = invite["contact_email"]
            if not email:
                raise HTTPException(status_code=400, detail="Invite is missing contact email")

            existing = await conn.fetchval("SELECT id FROM users WHERE email = $1", email)
            if existing:
                raise HTTPException(
                    status_code=400,
                    detail="An account with this email already exists. Please sign in or contact support.",
                )

            display_name = (request.name or invite["contact_name"] or email.split("@")[0]).strip()
            password_hash = hash_password(request.password)
            user = await conn.fetchrow(
                """
                INSERT INTO users (email, password_hash, role)
                VALUES ($1, $2, 'client')
                RETURNING id, email, role, is_active, created_at
                """,
                email,
                password_hash,
            )

            await conn.execute(
                """
                INSERT INTO clients (user_id, company_id, name, phone, job_title)
                VALUES ($1, $2, $3, $4, $5)
                """,
                user["id"],
                invite["company_id"],
                display_name,
                request.phone or invite["contact_phone"],
                request.job_title,
            )

            await conn.execute(
                """
                UPDATE companies
                SET owner_id = $1,
                    status = 'approved',
                    approved_at = COALESCE(approved_at, NOW()),
                    rejection_reason = NULL
                WHERE id = $2
                """,
                user["id"],
                invite["company_id"],
            )

            await conn.execute(
                """
                UPDATE broker_client_setups
                SET status = 'activated',
                    activated_at = NOW(),
                    updated_at = NOW(),
                    updated_by = $1
                WHERE id = $2
                """,
                user["id"],
                invite["id"],
            )

            await conn.execute(
                """
                INSERT INTO broker_company_links (
                    broker_id, company_id, status, linked_at, activated_at, created_by, updated_at
                )
                VALUES ($1, $2, 'active', NOW(), NOW(), $3, NOW())
                ON CONFLICT (broker_id, company_id)
                DO UPDATE SET
                    status = 'active',
                    activated_at = COALESCE(broker_company_links.activated_at, NOW()),
                    terminated_at = NULL,
                    updated_at = NOW()
                """,
                invite["broker_id"],
                invite["company_id"],
                user["id"],
            )

            settings = get_settings()
            access_token = create_access_token(user["id"], user["email"], user["role"])
            refresh_token = create_refresh_token(user["id"], user["email"], user["role"])

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
                "company_status": "approved",
                "company_name": invite["company_name"],
                "broker_name": invite["broker_name"],
                "message": "Welcome! Your company onboarding has been activated.",
            }



@router.post("/broker/accept-terms", response_model=BrokerTermsAcceptanceResponse)
async def accept_broker_terms(
    payload: BrokerTermsAcceptanceRequest,
    request: Request,
    current_user: CurrentUser = Depends(require_broker),
):
    """Record broker partner terms acceptance for the active broker membership."""
    async with get_connection() as conn:
        membership = await conn.fetchrow(
            """
            SELECT
                bm.broker_id,
                b.status,
                COALESCE(b.terms_required_version, 'v1') as terms_required_version
            FROM broker_members bm
            JOIN brokers b ON bm.broker_id = b.id
            WHERE bm.user_id = $1 AND bm.is_active = true
            ORDER BY bm.created_at ASC
            LIMIT 1
            """,
            current_user.id,
        )

        if not membership:
            raise HTTPException(status_code=404, detail="Broker membership not found")

        if membership["status"] != "active":
            raise HTTPException(status_code=403, detail="Broker account is not active")

        terms_version = (payload.terms_version or membership["terms_required_version"] or "v1").strip() or "v1"
        ip_address = request.client.host if request.client else None
        user_agent = request.headers.get("user-agent")

        accepted_at = await conn.fetchval(
            """
            INSERT INTO broker_terms_acceptances (
                broker_id, user_id, terms_version, ip_address, user_agent
            )
            VALUES ($1, $2, $3, $4, $5)
            ON CONFLICT (broker_id, user_id, terms_version)
            DO UPDATE SET
                accepted_at = NOW(),
                ip_address = EXCLUDED.ip_address,
                user_agent = EXCLUDED.user_agent
            RETURNING accepted_at
            """,
            membership["broker_id"],
            current_user.id,
            terms_version,
            ip_address,
            user_agent,
        )

    return BrokerTermsAcceptanceResponse(
        status="accepted",
        broker_id=membership["broker_id"],
        terms_version=terms_version,
        accepted_at=accepted_at,
    )

