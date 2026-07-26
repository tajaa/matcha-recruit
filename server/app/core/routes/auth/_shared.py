"""auth/_shared.py (split of the pre-2026-07-25 auth.py monolith)."""


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


router = APIRouter()
logger = logging.getLogger(__name__)


def _json_object(value) -> dict:
    if isinstance(value, dict):
        return value
    if isinstance(value, str):
        try:
            parsed = json.loads(value)
            return parsed if isinstance(parsed, dict) else {}
        except json.JSONDecodeError:
            return {}
    return {}



def _json_list(value) -> list:
    if isinstance(value, list):
        return value
    if isinstance(value, str):
        try:
            parsed = json.loads(value)
            return parsed if isinstance(parsed, list) else []
        except json.JSONDecodeError:
            return []
    return []



async def _table_exists(conn, table_name: str) -> bool:
    return bool(await conn.fetchval("SELECT to_regclass($1) IS NOT NULL", table_name))



async def _column_exists(conn, table_name: str, column_name: str) -> bool:
    return bool(
        await conn.fetchval(
            """
            SELECT EXISTS (
                SELECT 1
                FROM information_schema.columns
                WHERE table_name = $1 AND column_name = $2
            )
            """,
            table_name,
            column_name,
        )
    )



async def _upsert_business_headcount_profile(
    conn,
    *,
    company_id: UUID,
    company_name: str,
    owner_name: str,
    headcount: int,
    jurisdiction_count: int | None = None,
    updated_by: UUID,
) -> None:
    if not await _table_exists(conn, "company_handbook_profiles"):
        logger.warning(
            "Skipping headcount profile seed for company %s because company_handbook_profiles table is missing",
            company_id,
        )
        return

    legal_name = company_name.strip() or "Company"
    ceo_or_president = owner_name.strip() or "Company Leadership"

    await conn.execute(
        """
        INSERT INTO company_handbook_profiles (
            company_id, legal_name, dba, ceo_or_president, headcount,
            compliance_jurisdiction_count,
            remote_workers, minors, tipped_employees, union_employees, federal_contracts,
            group_health_insurance, background_checks, hourly_employees,
            salaried_employees, commissioned_employees, tip_pooling, updated_by, updated_at
        )
        VALUES (
            $1, $2, NULL, $3, $4,
            $5,
            false, false, false, false, false,
            false, false, true,
            false, false, false, $6, NOW()
        )
        ON CONFLICT (company_id)
        DO UPDATE SET
            legal_name = EXCLUDED.legal_name,
            headcount = EXCLUDED.headcount,
            compliance_jurisdiction_count = COALESCE(
                EXCLUDED.compliance_jurisdiction_count,
                company_handbook_profiles.compliance_jurisdiction_count
            ),
            updated_by = EXCLUDED.updated_by,
            updated_at = NOW()
        """,
        company_id,
        legal_name,
        ceo_or_president,
        headcount,
        jurisdiction_count,
        updated_by,
    )


__all__ = [
    "router",
    "logger",
    "_json_object",
    "_json_list",
    "_table_exists",
    "_column_exists",
    "_upsert_business_headcount_profile",
]

