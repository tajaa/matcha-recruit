"""auth/admin_candidates.py (split of the pre-2026-07-25 auth.py monolith)."""


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


@router.get("/admin/candidates/beta", response_model=CandidateBetaListResponse, dependencies=[Depends(require_admin)])
async def list_candidates_beta():
    """List all candidates with beta access info and interview prep stats."""
    async with get_connection() as conn:
        # Get all candidates with their user info and interview prep stats
        rows = await conn.fetch("""
            SELECT
                u.id as user_id,
                u.email,
                c.name,
                COALESCE(u.beta_features, '{}'::jsonb) as beta_features,
                COALESCE(u.interview_prep_tokens, 0) as interview_prep_tokens,
                COALESCE(u.allowed_interview_roles, '[]'::jsonb) as allowed_interview_roles,
                COUNT(i.id) FILTER (WHERE i.interview_type = 'tutor_interview') as total_sessions,
                AVG(
                    CASE
                        WHEN i.tutor_analysis IS NOT NULL
                        AND i.tutor_analysis->'interview'->>'response_quality_score' IS NOT NULL
                        THEN (i.tutor_analysis->'interview'->>'response_quality_score')::float
                        ELSE NULL
                    END
                ) as avg_score,
                MAX(i.created_at) FILTER (WHERE i.interview_type = 'tutor_interview') as last_session_at
            FROM users u
            JOIN candidates c ON c.user_id = u.id
            LEFT JOIN interviews i ON i.interviewer_name = u.email AND i.interview_type = 'tutor_interview'
            WHERE u.role = 'candidate'
            GROUP BY u.id, u.email, c.name, u.beta_features, u.interview_prep_tokens, u.allowed_interview_roles
            ORDER BY c.name
        """)

        candidates = []
        for row in rows:
            beta_features = row["beta_features"] if row["beta_features"] else {}
            if isinstance(beta_features, str):
                beta_features = json.loads(beta_features)

            allowed_roles = row["allowed_interview_roles"] if row["allowed_interview_roles"] else []
            if isinstance(allowed_roles, str):
                allowed_roles = json.loads(allowed_roles)

            candidates.append(CandidateBetaInfo(
                user_id=row["user_id"],
                email=row["email"],
                name=row["name"],
                beta_features=beta_features,
                interview_prep_tokens=row["interview_prep_tokens"],
                allowed_interview_roles=allowed_roles,
                total_sessions=row["total_sessions"] or 0,
                avg_score=round(row["avg_score"], 1) if row["avg_score"] else None,
                last_session_at=row["last_session_at"]
            ))

        return CandidateBetaListResponse(candidates=candidates, total=len(candidates))



@router.patch("/admin/candidates/{user_id}/beta", dependencies=[Depends(require_admin)])
async def toggle_candidate_beta(user_id: UUID, request: BetaToggleRequest):
    """Toggle a beta feature for a candidate."""
    async with get_connection() as conn:
        # Verify user exists and is a candidate
        user = await conn.fetchrow(
            "SELECT id, role, beta_features FROM users WHERE id = $1",
            user_id
        )
        if not user:
            raise HTTPException(status_code=404, detail="User not found")
        if user["role"] != "candidate":
            raise HTTPException(status_code=400, detail="User is not a candidate")

        # Update beta features
        current_features = user["beta_features"] if user["beta_features"] else {}
        if isinstance(current_features, str):
            current_features = json.loads(current_features)

        if request.enabled:
            current_features[request.feature] = True
        else:
            current_features.pop(request.feature, None)

        await conn.execute(
            "UPDATE users SET beta_features = $1::jsonb WHERE id = $2",
            json.dumps(current_features), user_id
        )

        return {"status": "updated", "beta_features": current_features}



@router.post("/admin/candidates/{user_id}/tokens", dependencies=[Depends(require_admin)])
async def award_tokens(user_id: UUID, request: TokenAwardRequest):
    """Award interview prep tokens to a candidate."""
    if request.amount <= 0:
        raise HTTPException(status_code=400, detail="Amount must be positive")

    async with get_connection() as conn:
        # Verify user exists and is a candidate
        user = await conn.fetchrow(
            "SELECT id, role, interview_prep_tokens FROM users WHERE id = $1",
            user_id
        )
        if not user:
            raise HTTPException(status_code=404, detail="User not found")
        if user["role"] != "candidate":
            raise HTTPException(status_code=400, detail="User is not a candidate")

        new_total = (user["interview_prep_tokens"] or 0) + request.amount
        await conn.execute(
            "UPDATE users SET interview_prep_tokens = $1 WHERE id = $2",
            new_total, user_id
        )

        return {"status": "awarded", "new_total": new_total}



@router.put("/admin/candidates/{user_id}/roles", dependencies=[Depends(require_admin)])
async def update_allowed_roles(user_id: UUID, request: AllowedRolesRequest):
    """Update allowed interview roles for a candidate."""
    async with get_connection() as conn:
        # Verify user exists and is a candidate
        user = await conn.fetchrow(
            "SELECT id, role FROM users WHERE id = $1",
            user_id
        )
        if not user:
            raise HTTPException(status_code=404, detail="User not found")
        if user["role"] != "candidate":
            raise HTTPException(status_code=400, detail="User is not a candidate")

        await conn.execute(
            "UPDATE users SET allowed_interview_roles = $1::jsonb WHERE id = $2",
            json.dumps(request.roles), user_id
        )

        return {"status": "updated", "allowed_interview_roles": request.roles}



@router.get("/admin/candidates/{user_id}/sessions", response_model=list[CandidateSessionSummary], dependencies=[Depends(require_admin)])
async def get_candidate_sessions(user_id: UUID):
    """Get interview prep sessions for a specific candidate."""
    async with get_connection() as conn:
        # Get user email
        user = await conn.fetchrow("SELECT email FROM users WHERE id = $1", user_id)
        if not user:
            raise HTTPException(status_code=404, detail="User not found")

        # Get interview prep sessions (using interviewer_name = email pattern from tutor)
        rows = await conn.fetch("""
            SELECT
                id as session_id,
                interviewer_role as interview_role,
                EXTRACT(EPOCH FROM (COALESCE(completed_at, NOW()) - created_at)) / 60 as duration_minutes,
                status,
                created_at,
                tutor_analysis
            FROM interviews
            WHERE interviewer_name = $1
            AND interview_type = 'tutor_interview'
            ORDER BY created_at DESC
            LIMIT 50
        """, user["email"])

        sessions = []
        for row in rows:
            analysis = row["tutor_analysis"]
            response_score = None
            communication_score = None

            if analysis:
                if isinstance(analysis, str):
                    analysis = json.loads(analysis)
                interview_data = analysis.get("interview", {})
                response_score = interview_data.get("response_quality_score")
                communication_score = interview_data.get("communication_score")

            sessions.append(CandidateSessionSummary(
                session_id=row["session_id"],
                interview_role=row["interview_role"],
                duration_minutes=int(row["duration_minutes"] or 0),
                status=row["status"],
                created_at=row["created_at"],
                response_quality_score=response_score,
                communication_score=communication_score
            ))

        return sessions


# ── Beta invitation registration ──

