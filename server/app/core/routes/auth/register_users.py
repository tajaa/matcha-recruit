"""auth/register_users.py (split of the pre-2026-07-25 auth.py monolith)."""


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


@router.post("/register/admin", response_model=TokenResponse, dependencies=[Depends(require_admin)])
async def register_admin(request: AdminRegister):
    """Register a new admin (admin only)."""
    async with get_connection() as conn:
        # Check if email exists
        existing = await conn.fetchval("SELECT id FROM users WHERE email = $1", request.email)
        if existing:
            raise HTTPException(status_code=400, detail="Email already registered")

        # Create user
        password_hash = hash_password(request.password)
        user = await conn.fetchrow(
            """
            INSERT INTO users (email, password_hash, role)
            VALUES ($1, $2, 'admin')
            RETURNING id, email, role, is_active, created_at
            """,
            request.email, password_hash
        )

        # Create admin profile
        await conn.execute(
            "INSERT INTO admins (user_id, name) VALUES ($1, $2)",
            user["id"], request.name
        )

        settings = get_settings()
        access_token = create_access_token(user["id"], user["email"], user["role"])
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
                last_login=None
            )
        )



@router.post("/register/client", response_model=TokenResponse)
async def register_client(
    request: ClientRegister,
    http_request: Request,
    _admin: CurrentUser = Depends(require_admin),
):
    """Register a new client linked to a company. Admin-only — used by internal tooling."""
    ip = client_ip(http_request)
    await check_rate_limit(ip, "register_client", 10, 3600)
    async with get_connection() as conn:
        # Check if email exists
        existing = await conn.fetchval("SELECT id FROM users WHERE email = $1", request.email)
        if existing:
            raise HTTPException(status_code=400, detail="Email already registered")

        # Verify company exists
        company = await conn.fetchrow("SELECT id FROM companies WHERE id = $1", request.company_id)
        if not company:
            raise HTTPException(status_code=404, detail="Company not found")

        # Create user
        password_hash = hash_password(request.password)
        user = await conn.fetchrow(
            """
            INSERT INTO users (email, password_hash, role)
            VALUES ($1, $2, 'client')
            RETURNING id, email, role, is_active, created_at
            """,
            request.email, password_hash
        )

        # Create client profile
        await conn.execute(
            """
            INSERT INTO clients (user_id, company_id, name, phone, job_title)
            VALUES ($1, $2, $3, $4, $5)
            """,
            user["id"], request.company_id, request.name, request.phone, request.job_title
        )

        settings = get_settings()
        access_token = create_access_token(user["id"], user["email"], user["role"])
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
                last_login=None
            )
        )



@router.post("/register/employee", response_model=TokenResponse)
async def register_employee(request: EmployeeRegister, http_request: Request):
    """Register a new employee."""
    ip = client_ip(http_request)
    await check_rate_limit(ip, "register_employee", 10, 3600)
    async with get_connection() as conn:
        # Check if email exists
        existing = await conn.fetchval("SELECT id FROM users WHERE email = $1", request.email)
        if existing:
            raise HTTPException(status_code=400, detail="Email already registered")

        # Verify company exists
        company = await conn.fetchrow("SELECT id FROM companies WHERE id = $1", request.company_id)
        if not company:
            raise HTTPException(status_code=404, detail="Company not found")

        # Create user
        password_hash = hash_password(request.password)
        user = await conn.fetchrow(
            """
            INSERT INTO users (email, password_hash, role)
            VALUES ($1, $2, 'employee')
            RETURNING id, email, role, is_active, created_at
            """,
            request.email, password_hash
        )

        # Create employee profile
        await conn.execute(
            """
            INSERT INTO employees (user_id, org_id, email, first_name, last_name, work_state, employment_type, start_date)
            VALUES ($1, $2, $3, $4, $5, $6, $7, $8)
            """,
            user["id"], request.company_id, request.email, request.first_name, request.last_name,
            request.work_state, request.employment_type, request.start_date
        )

        settings = get_settings()
        access_token = create_access_token(user["id"], user["email"], user["role"])
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
                last_login=None
            )
        )



@router.post("/register/candidate", response_model=TokenResponse)
async def register_candidate(request: CandidateRegister, http_request: Request):
    """Register a new candidate."""
    ip = client_ip(http_request)
    await check_rate_limit(ip, "register_candidate", 10, 3600)
    async with get_connection() as conn:
        # Check if email exists in users
        existing = await conn.fetchval("SELECT id FROM users WHERE email = $1", request.email)
        if existing:
            raise HTTPException(status_code=400, detail="Email already registered")

        # Create user
        password_hash = hash_password(request.password)
        user = await conn.fetchrow(
            """
            INSERT INTO users (email, password_hash, role)
            VALUES ($1, $2, 'candidate')
            RETURNING id, email, role, is_active, created_at
            """,
            request.email, password_hash
        )

        # Check if candidate record exists with this email (from resume upload)
        candidate = await conn.fetchrow(
            "SELECT id FROM candidates WHERE email = $1",
            request.email
        )

        if candidate:
            # Link existing candidate to user
            await conn.execute(
                "UPDATE candidates SET user_id = $1, name = COALESCE(name, $2), phone = COALESCE(phone, $3) WHERE id = $4",
                user["id"], request.name, request.phone, candidate["id"]
            )
        else:
            # Create new candidate record
            await conn.execute(
                "INSERT INTO candidates (user_id, name, email, phone) VALUES ($1, $2, $3, $4)",
                user["id"], request.name, request.email, request.phone
            )

        settings = get_settings()
        access_token = create_access_token(user["id"], user["email"], user["role"])
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
                last_login=None
            )
        )



class IndividualRegister(BaseModel):
    email: EmailStr
    password: str
    name: str



@router.post("/register/individual")
async def register_individual(request: IndividualRegister, http_request: Request):
    """Register an individual user with a personal workspace for matcha-work."""
    ip = client_ip(http_request)
    await check_rate_limit(ip, "register_individual", 10, 3600)
    from ..feature_flags import DEFAULT_COMPANY_FEATURES
    from ...matcha.services.billing.token_budget_service import FREE_TOKEN_GRANT

    async with get_connection() as conn:
        async with conn.transaction():
            existing = await conn.fetchval("SELECT id FROM users WHERE email = $1", request.email)
            if existing:
                raise HTTPException(status_code=400, detail="Email already registered")

            # Create personal workspace company
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

            # Create user with 'individual' role
            password_hash = hash_password(request.password)
            user = await conn.fetchrow(
                """INSERT INTO users (email, password_hash, role)
                   VALUES ($1, $2, 'individual')
                   RETURNING id, email, role""",
                request.email, password_hash,
            )

            # Create client record linking user → personal company
            await conn.execute(
                "INSERT INTO clients (user_id, company_id, name) VALUES ($1, $2, $3)",
                user["id"], company_id, request.name,
            )

            # Set owner
            await conn.execute("UPDATE companies SET owner_id = $1 WHERE id = $2", user["id"], company_id)

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

