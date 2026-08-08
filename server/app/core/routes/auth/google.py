"""auth/google.py (split of the pre-2026-07-25 auth.py monolith)."""


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


class GoogleAuthRequest(BaseModel):
    id_token: str



@router.post("/google", response_model=TokenResponse)
async def google_auth(request: GoogleAuthRequest, http_request: Request):
    """Sign in or register with Google. Creates an individual account if the user is new."""
    ip = client_ip(http_request)
    await check_rate_limit(ip, "google_auth", 15, 3600)
    from app.core.feature_flags import DEFAULT_COMPANY_FEATURES
    from app.core.services.google_identity import GoogleTokenError, verify_google_id_token
    from app.matcha.services.billing.token_budget_service import FREE_TOKEN_GRANT

    try:
        identity = await verify_google_id_token(request.id_token)
    except GoogleTokenError:
        raise HTTPException(status_code=400, detail="Invalid Google ID token")

    email = identity.email
    name = identity.name or email.split("@")[0]

    async with get_connection() as conn:
        # Check if user exists
        existing = await conn.fetchrow("SELECT id, email, role FROM users WHERE email = $1", email)

        if existing:
            # Login existing user
            access_token = create_access_token(existing["id"], existing["email"], existing["role"])
            refresh_token = create_refresh_token(existing["id"], existing["email"], existing["role"])
            return TokenResponse(access_token=access_token, refresh_token=refresh_token, token_type="bearer")

        # Register new individual user
        async with conn.transaction():
            personal_features = {**DEFAULT_COMPANY_FEATURES, "matcha_work": True}
            company = await conn.fetchrow(
                """INSERT INTO companies (name, status, approved_at, is_personal, enabled_features)
                   VALUES ($1, 'approved', NOW(), true, $2::jsonb)
                   RETURNING id""",
                f"{name}'s Workspace",
                json.dumps(personal_features),
            )
            company_id = company["id"]

            await conn.execute(
                """INSERT INTO mw_token_budgets (company_id, free_tokens_used, free_token_limit)
                   VALUES ($1, 0, $2) ON CONFLICT (company_id) DO NOTHING""",
                company_id, FREE_TOKEN_GRANT,
            )

            # Use a random password since Google users don't need one
            import os as _os
            user = await conn.fetchrow(
                """INSERT INTO users (email, password_hash, role)
                   VALUES ($1, $2, 'individual')
                   RETURNING id, email, role""",
                email, hash_password(_os.urandom(32).hex()),
            )

            await conn.execute(
                "INSERT INTO clients (user_id, company_id, name) VALUES ($1, $2, $3)",
                user["id"], company_id, name,
            )
            await conn.execute("UPDATE companies SET owner_id = $1 WHERE id = $2", user["id"], company_id)

    access_token = create_access_token(user["id"], user["email"], user["role"])
    refresh_token = create_refresh_token(user["id"], user["email"], user["role"])
    return TokenResponse(access_token=access_token, refresh_token=refresh_token, token_type="bearer")

