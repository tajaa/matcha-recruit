"""auth/profile.py (split of the pre-2026-07-25 auth.py monolith)."""


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


@router.get("/me")
async def get_current_user_profile(token_payload: TokenPayload = Depends(get_token_payload)):
    """Get current user with full profile."""
    try:
        user_id = UUID(token_payload.sub)
    except (ValueError, TypeError):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid token subject")

    async with get_connection() as conn:
        user_row = await conn.fetchrow(
            """SELECT id, email, role, is_active, avatar_url,
                      COALESCE(beta_features, '{}'::jsonb) as beta_features,
                      COALESCE(interview_prep_tokens, 0) as interview_prep_tokens,
                      COALESCE(allowed_interview_roles, '[]'::jsonb) as allowed_interview_roles
               FROM users WHERE id = $1""",
            user_id,
        )
        if not user_row or not user_row["is_active"]:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="User not found or inactive"
            )

        current_user = CurrentUser(
            id=user_row["id"],
            email=user_row["email"],
            role=user_row["role"],
            profile=None,
            beta_features=_json_object(user_row["beta_features"]),
            interview_prep_tokens=user_row["interview_prep_tokens"],
            allowed_interview_roles=_json_list(user_row["allowed_interview_roles"]),
        )

        # Fetch visible platform features for all roles so the client-side
        # sidebar gate can apply platform checks universally, not just for admins.
        visible_features = await get_visible_features(conn=conn)

        _avatar = user_row["avatar_url"]

        if current_user.role == "admin":
            profile = await conn.fetchrow(
                "SELECT id, user_id, name, created_at FROM admins WHERE user_id = $1",
                current_user.id
            )
            return {
                "user": {"id": str(current_user.id), "email": current_user.email, "role": current_user.role, "avatar_url": _avatar, "work_onboarded": bool(current_user.beta_features.get("work_onboarded")), "beta_features": dict(current_user.beta_features)},
                "profile": {
                    "id": str(profile["id"]),
                    "user_id": str(profile["user_id"]),
                    "name": profile["name"],
                    "email": current_user.email,
                    "created_at": profile["created_at"].isoformat()
                } if profile else None,
                "visible_features": visible_features,
            }

        elif current_user.role in ("client", "individual"):
            profile = await conn.fetchrow(
                """
                SELECT c.id, c.user_id, c.company_id, comp.name as company_name,
                       comp.status as company_status, comp.rejection_reason,
                       comp.industry, comp.healthcare_specialties,
                       COALESCE(comp.enabled_features, $2::jsonb) as enabled_features,
                       COALESCE(comp.is_personal, false) as is_personal,
                       comp.signup_source,
                       comp.ir_onboarding_completed_at,
                       c.name, c.phone, c.job_title, c.created_at,
                       COALESCE(chp.headcount, 0) as headcount,
                       COALESCE(chp.compliance_jurisdiction_count, 0) as jurisdiction_count
                FROM clients c
                JOIN companies comp ON c.company_id = comp.id
                LEFT JOIN company_handbook_profiles chp ON chp.company_id = comp.id
                WHERE c.user_id = $1
                """,
                current_user.id,
                default_company_features_json(),
            )

            # Admin-composed product (signup_source = 'product:<slug>') — the
            # frontend needs the row to detect pending payment, price the
            # Subscribe CTA and build the sidebar nav. Archived products are
            # still resolved (published_only=False): the tenant keeps working
            # after we stop selling it.
            product_payload = None
            if profile:
                from app.core.services.product_definitions import get_product_by_signup_source
                _product = await get_product_by_signup_source(
                    conn, profile["signup_source"], published_only=False
                )
                if _product:
                    product_payload = _product.public_dict()

            # Compute which enabled features still need onboarding setup
            onboarding_needed = {}
            if profile:
                enabled_features = merge_company_features(
                    profile["enabled_features"],
                    profile["signup_source"],
                )
                company_id = profile["company_id"]

                # Company profile completeness (always checked)
                has_profile = await conn.fetchval(
                    """SELECT EXISTS(SELECT 1 FROM companies WHERE id = $1
                       AND headquarters_state IS NOT NULL
                       AND default_employment_type IS NOT NULL)""",
                    company_id
                )
                if not has_profile:
                    onboarding_needed["company_profile"] = True

                if enabled_features.get("compliance"):
                    has_locations = await conn.fetchval(
                        "SELECT EXISTS(SELECT 1 FROM business_locations WHERE company_id = $1 AND is_active = true)",
                        company_id
                    )
                    if not has_locations:
                        onboarding_needed["compliance"] = True

                if enabled_features.get("employees"):
                    has_employees = await conn.fetchval(
                        "SELECT EXISTS(SELECT 1 FROM employees WHERE org_id = $1 AND termination_date IS NULL)",
                        company_id
                    )
                    if not has_employees:
                        onboarding_needed["employees"] = True

                if enabled_features.get("policies"):
                    has_policies = await conn.fetchval(
                        "SELECT EXISTS(SELECT 1 FROM policies WHERE company_id = $1)",
                        company_id
                    )
                    if not has_policies:
                        onboarding_needed["policies"] = True

                if enabled_features.get("offer_letters"):
                    has_offers = await conn.fetchval(
                        "SELECT EXISTS(SELECT 1 FROM offer_letters WHERE company_id = $1)",
                        company_id
                    )
                    if not has_offers:
                        onboarding_needed["offer_letters"] = True

                if enabled_features.get("onboarding"):
                    has_integrations = await conn.fetchval(
                        "SELECT EXISTS(SELECT 1 FROM integration_connections WHERE company_id = $1 AND status = 'connected')",
                        company_id
                    )
                    if not has_integrations:
                        onboarding_needed["integrations"] = True

            return {
                "user": {"id": str(current_user.id), "email": current_user.email, "role": current_user.role, "avatar_url": _avatar, "work_onboarded": bool(current_user.beta_features.get("work_onboarded")), "beta_features": dict(current_user.beta_features)},
                "profile": {
                    "id": str(profile["id"]),
                    "user_id": str(profile["user_id"]),
                    "company_id": str(profile["company_id"]),
                    "company_name": profile["company_name"],
                    "company_status": profile["company_status"] or "approved",
                    "rejection_reason": profile["rejection_reason"],
                    "industry": profile["industry"],
                    "healthcare_specialties": list(profile["healthcare_specialties"] or []),
                    "enabled_features": merge_company_features(
                        profile["enabled_features"],
                        profile["signup_source"],
                    ),
                    "is_personal": profile["is_personal"],
                    "signup_source": profile["signup_source"] if "signup_source" in profile.keys() else None,
                    "ir_onboarding_completed_at": (
                        profile["ir_onboarding_completed_at"].isoformat()
                        if "ir_onboarding_completed_at" in profile.keys() and profile["ir_onboarding_completed_at"]
                        else None
                    ),
                    "name": profile["name"],
                    "phone": profile["phone"],
                    "job_title": profile["job_title"],
                    "email": current_user.email,
                    "created_at": profile["created_at"].isoformat(),
                    "headcount": int(profile["headcount"]) if "headcount" in profile.keys() else 0,
                    "jurisdiction_count": int(profile["jurisdiction_count"]) if "jurisdiction_count" in profile.keys() else 0,
                    # Present only for admin-composed products; null otherwise.
                    "product": product_payload,
                } if profile else None,
                "onboarding_needed": onboarding_needed,
                "visible_features": visible_features,
            }

        elif current_user.role == "candidate":
            profile = await conn.fetchrow(
                """
                SELECT id, user_id, name, email, phone, skills, experience_years, created_at
                FROM candidates WHERE user_id = $1
                """,
                current_user.id
            )
            skills_data = json.loads(profile["skills"]) if profile and profile["skills"] else []
            return {
                "user": {
                    "id": str(current_user.id),
                    "email": current_user.email,
                    "role": current_user.role,
                    "avatar_url": _avatar,
                    "beta_features": current_user.beta_features,
                    "interview_prep_tokens": current_user.interview_prep_tokens,
                    "allowed_interview_roles": current_user.allowed_interview_roles
                },
                "profile": {
                    "id": str(profile["id"]),
                    "user_id": str(profile["user_id"]) if profile["user_id"] else None,
                    "name": profile["name"],
                    "email": profile["email"],
                    "phone": profile["phone"],
                    "skills": skills_data,
                    "experience_years": profile["experience_years"],
                    "created_at": profile["created_at"].isoformat()
                } if profile else None,
                "visible_features": visible_features,
            }

        elif current_user.role == "employee":
            profile = await conn.fetchrow(
                """
                SELECT e.id, e.user_id, e.org_id, c.name as company_name,
                       COALESCE(c.enabled_features, $2::jsonb) as enabled_features,
                       c.signup_source,
                       e.first_name, e.last_name, e.email, e.work_state,
                       e.employment_type, e.start_date, e.manager_id, e.created_at
                FROM employees e
                JOIN companies c ON e.org_id = c.id
                WHERE e.user_id = $1
                """,
                current_user.id,
                default_company_features_json(),
            )
            return {
                "user": {"id": str(current_user.id), "email": current_user.email, "role": current_user.role, "avatar_url": _avatar, "work_onboarded": bool(current_user.beta_features.get("work_onboarded"))},
                "profile": {
                    "id": str(profile["id"]),
                    "user_id": str(profile["user_id"]),
                    "company_id": str(profile["org_id"]),
                    "company_name": profile["company_name"],
                    "enabled_features": merge_company_features(
                        profile["enabled_features"],
                        profile["signup_source"],
                    ),
                    "first_name": profile["first_name"],
                    "last_name": profile["last_name"],
                    "email": profile["email"],
                    "work_state": profile["work_state"],
                    "employment_type": profile["employment_type"],
                    "start_date": profile["start_date"].isoformat() if profile["start_date"] else None,
                    "manager_id": str(profile["manager_id"]) if profile["manager_id"] else None,
                    "created_at": profile["created_at"].isoformat()
                } if profile else None,
                "visible_features": visible_features,
            }

        elif current_user.role == "broker":
            profile = await conn.fetchrow(
                """
                SELECT
                    bm.id, bm.user_id, bm.broker_id, bm.role as member_role, bm.created_at,
                    b.name as broker_name, b.slug as broker_slug, b.status as broker_status,
                    b.billing_mode, b.invoice_owner, b.support_routing,
                    COALESCE(b.plan, 'standard') as plan,
                    COALESCE(bb.branding_mode, 'direct') as branding_mode,
                    COALESCE(NULLIF(bb.brand_display_name, ''), b.name) as brand_display_name,
                    COALESCE(b.terms_required_version, 'v1') as terms_required_version,
                    ta.accepted_at as terms_accepted_at
                FROM broker_members bm
                JOIN brokers b ON bm.broker_id = b.id
                LEFT JOIN broker_branding_configs bb ON bb.broker_id = bm.broker_id
                LEFT JOIN broker_terms_acceptances ta
                    ON ta.broker_id = bm.broker_id
                    AND ta.user_id = bm.user_id
                    AND ta.terms_version = COALESCE(b.terms_required_version, 'v1')
                WHERE bm.user_id = $1 AND bm.is_active = true
                ORDER BY bm.created_at ASC
                LIMIT 1
                """,
                current_user.id
            )
            terms_accepted = bool(profile and profile["terms_accepted_at"] is not None)
            return {
                "user": {"id": str(current_user.id), "email": current_user.email, "role": current_user.role, "avatar_url": _avatar, "work_onboarded": bool(current_user.beta_features.get("work_onboarded"))},
                "profile": {
                    "id": str(profile["id"]),
                    "user_id": str(profile["user_id"]),
                    "broker_id": str(profile["broker_id"]),
                    "broker_name": profile["broker_name"],
                    "broker_slug": profile["broker_slug"],
                    "branding_mode": profile["branding_mode"],
                    "brand_display_name": profile["brand_display_name"],
                    "member_role": profile["member_role"],
                    "broker_status": profile["broker_status"],
                    "plan": profile["plan"],
                    "billing_mode": profile["billing_mode"],
                    "invoice_owner": profile["invoice_owner"],
                    "support_routing": profile["support_routing"],
                    "terms_required_version": profile["terms_required_version"],
                    "terms_accepted": terms_accepted,
                    "terms_accepted_at": profile["terms_accepted_at"].isoformat() if profile["terms_accepted_at"] else None,
                    "created_at": profile["created_at"].isoformat(),
                } if profile else None,
                "onboarding_needed": {"broker_terms": not terms_accepted} if profile else {},
                "visible_features": visible_features,
            }

    return {"user": {"id": str(current_user.id), "email": current_user.email, "role": current_user.role, "avatar_url": _avatar, "work_onboarded": bool(current_user.beta_features.get("work_onboarded"))}, "profile": None, "visible_features": visible_features}



_AVATAR_MAX_SIZE = 5 * 1024 * 1024  # 5 MB
_AVATAR_ALLOWED_TYPES = {"image/jpeg", "image/png", "image/webp"}



@router.post("/avatar")
async def upload_avatar(
    file: UploadFile = File(...),
    current_user: CurrentUser = Depends(get_current_user),
):
    """Upload a profile avatar image. Returns the public URL."""
    if file.content_type not in _AVATAR_ALLOWED_TYPES:
        raise HTTPException(status_code=400, detail="Only JPEG, PNG, and WebP images are accepted")

    data = await file.read()
    if len(data) > _AVATAR_MAX_SIZE:
        raise HTTPException(status_code=400, detail="Image must be under 5 MB")

    from app.core.services.storage import get_storage
    storage = get_storage()
    url = await storage.upload_file(data, file.filename or "avatar.jpg", prefix="avatars", content_type=file.content_type)

    async with get_connection() as conn:
        await conn.execute("UPDATE users SET avatar_url = $1 WHERE id = $2", url, current_user.id)

    # Refresh the live channels-WS user object so messages sent after this
    # carry the new avatar without a reconnect — the broadcast reads the
    # in-memory ChannelUser, which would otherwise stay stale until reconnect.
    try:
        from app.werk.routes.channels_ws import manager
        if current_user.id in manager.users:
            manager.users[current_user.id].avatar_url = url
    except Exception:
        pass

    return {"avatar_url": url}



@router.put("/profile")
async def update_profile(
    request: UpdateProfileRequest,
    current_user: CurrentUser = Depends(get_current_user)
):
    """Update profile information for current user."""
    async with get_connection() as conn:
        if current_user.role == "admin":
            if request.name:
                await conn.execute(
                    "UPDATE admins SET name = $1 WHERE user_id = $2",
                    request.name, current_user.id
                )
        elif current_user.role == "client":
            updates = []
            values = []
            if request.name:
                updates.append("name = $" + str(len(values) + 1))
                values.append(request.name)
            if request.phone:
                updates.append("phone = $" + str(len(values) + 1))
                values.append(request.phone)
            if updates:
                values.append(current_user.id)
                await conn.execute(
                    f"UPDATE clients SET {', '.join(updates)} WHERE user_id = ${len(values)}",
                    *values
                )
        elif current_user.role == "candidate":
            updates = []
            values = []
            if request.name:
                updates.append("name = $" + str(len(values) + 1))
                values.append(request.name)
            if request.phone:
                updates.append("phone = $" + str(len(values) + 1))
                values.append(request.phone)
            if updates:
                values.append(current_user.id)
                await conn.execute(
                    f"UPDATE candidates SET {', '.join(updates)} WHERE user_id = ${len(values)}",
                    *values
                )

        return {"status": "profile_updated"}



@router.post("/work-onboarded")
async def mark_work_onboarded(current_user: CurrentUser = Depends(get_current_user)):
    """Mark that the user has completed the Matcha Work onboarding wizard."""
    async with get_connection() as conn:
        await conn.execute(
            """
            UPDATE users
            SET beta_features = COALESCE(beta_features, '{}'::jsonb) || '{"work_onboarded": true}'::jsonb
            WHERE id = $1
            """,
            current_user.id,
        )
    return {"ok": True}


# ===========================================
# Admin Beta Access Management
# ===========================================

