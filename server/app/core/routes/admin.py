"""Admin routes for business registration approval workflow and company feature management."""

import asyncio
import difflib
import json
import logging
import re
import secrets
from datetime import datetime, timedelta
from typing import Dict, List, Optional, Any, AsyncGenerator
from uuid import UUID

import asyncpg
from fastapi import APIRouter, BackgroundTasks, Body, HTTPException, Depends, Query, status
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, EmailStr, Field

logger = logging.getLogger(__name__)

from ...database import get_connection
from ..dependencies import require_admin
from ..services.credential_crypto import decrypt_credential_fields
from ..feature_flags import merge_company_features
from ..services.email import get_email_service
from ..models.compliance import AutoCheckSettings, LocationCreate
from ..compliance_registry import (
    TRIGGER_PROFILES,
    LABOR_CATEGORIES, HEALTHCARE_CATEGORIES, ONCOLOGY_CATEGORIES,
    MEDICAL_COMPLIANCE_CATEGORIES, SUPPLEMENTARY_CATEGORIES,
)
from ..services.compliance_service import (
    update_auto_check_settings,
    _jurisdiction_row_to_dict,
    run_compliance_check_background,
    run_compliance_check_stream,
    research_jurisdiction_repo_only,
    get_locations,
    get_location_requirements,
    create_location,
    admin_add_requirement_to_location,
)
from ..services.redis_cache import (
    get_redis_cache, cache_get, cache_set, cache_delete, cache_delete_pattern,
    admin_jurisdictions_list_key, admin_jurisdiction_detail_key,
    admin_jurisdiction_data_overview_key, admin_jurisdiction_policy_overview_key,
    admin_bookmarked_requirements_key,
)
from ..services.rate_limiter import get_rate_limiter
from ..services.auth import hash_password
from ..services.platform_settings import (
    get_visible_features, prime_visible_features_cache,
    get_matcha_work_model_mode, prime_matcha_work_model_mode_cache,
    get_jurisdiction_research_model_mode, prime_jurisdiction_research_model_mode_cache,
    get_er_similarity_weights, prime_er_similarity_weights_cache,
    DEFAULT_ER_SIMILARITY_WEIGHTS, EXPECTED_WEIGHT_KEYS,
)
from ...matcha.services import billing_service as mw_billing_service
from ...config import get_settings
from ..services.stripe_service import StripeService, StripeServiceError
from ..feature_flags import DEFAULT_COMPANY_FEATURES

router = APIRouter()

KNOWN_PLATFORM_ITEMS = {
    "admin_overview", "client_management", "company_features", "industry_handbooks", "admin_import",
    "projects", "interviewer", "candidate_metrics", "interview_prep", "test_bot",
    "onboarding", "employees", "policies", "handbooks", "time_off",
    "accommodations", "er_copilot", "incidents", "risk_assessment",
    "compliance", "jurisdictions", "blog", "hr_news", "matcha_work",
    "offer_letters", "discipline",
}

class PlatformFeaturesUpdate(BaseModel):
    visible_features: list[str]


class MatchaWorkModelModeUpdate(BaseModel):
    mode: str = Field(..., pattern="^(light|heavy)$")


class JurisdictionResearchModelModeUpdate(BaseModel):
    mode: str = Field(..., pattern="^(lite|light|heavy)$")


class ERSimilarityWeightsUpdate(BaseModel):
    weights: dict[str, float]


class JurisdictionProcessRequest(BaseModel):
    """Request model for processing a jurisdiction coverage request."""
    has_local_ordinance: bool = False
    county: Optional[str] = None
    admin_notes: Optional[str] = None


class PlatformSettingsResponse(BaseModel):
    visible_features: list[str]
    matcha_work_model_mode: str
    jurisdiction_research_model_mode: str
    er_similarity_weights: dict[str, float]


STRICT_CONFIDENCE_THRESHOLD = 0.95
MAX_CONFIDENCE_REFETCH_ATTEMPTS = 2

# Hardcoded metro preset by design: this keeps execution simple and deterministic.
TOP_15_METROS: list[dict[str, str]] = [
    {"city": "new york", "state": "NY", "label": "New York City"},
    {"city": "los angeles", "state": "CA", "label": "Los Angeles"},
    {"city": "chicago", "state": "IL", "label": "Chicago"},
    {"city": "houston", "state": "TX", "label": "Houston"},
    {"city": "phoenix", "state": "AZ", "label": "Phoenix"},
    {"city": "philadelphia", "state": "PA", "label": "Philadelphia"},
    {"city": "san antonio", "state": "TX", "label": "San Antonio"},
    {"city": "san diego", "state": "CA", "label": "San Diego"},
    {"city": "dallas", "state": "TX", "label": "Dallas"},
    {"city": "jacksonville", "state": "FL", "label": "Jacksonville"},
    {"city": "austin", "state": "TX", "label": "Austin"},
    {"city": "fort worth", "state": "TX", "label": "Fort Worth"},
    {"city": "san jose", "state": "CA", "label": "San Jose"},
    {"city": "columbus", "state": "OH", "label": "Columbus"},
    {"city": "charlotte", "state": "NC", "label": "Charlotte"},
]

# Fallback allowlist for environments where jurisdiction_reference is unavailable.
# Keep this intentionally constrained and canonical.
FALLBACK_ALLOWED_CITIES_BY_STATE: dict[str, set[str]] = {
    "NY": {"new york"},
    "CA": {"los angeles", "san diego", "san jose"},
    "IL": {"chicago"},
    "TX": {"houston", "san antonio", "dallas", "austin", "fort worth"},
    "AZ": {"phoenix"},
    "PA": {"philadelphia"},
    "FL": {"jacksonville"},
    "OH": {"columbus"},
    "NC": {"charlotte"},
    "UT": {"salt lake city"},
}

FALLBACK_CITY_ALIASES: dict[tuple[str, str], str] = {
    ("NY", "new york city"): "new york",
    ("NY", "nyc"): "new york",
    ("UT", "salt lake"): "salt lake city",
}


@router.get("/api-usage", dependencies=[Depends(require_admin)])
async def get_api_usage():
    """Return current Gemini API usage stats for rate limiting monitoring."""
    limiter = get_rate_limiter()
    return await limiter.get_usage()


# ── Token Quota Management ──

@router.get("/token-quotas", dependencies=[Depends(require_admin)])
async def list_token_quotas():
    """List all token quotas with user/company info."""
    async with get_connection() as conn:
        rows = await conn.fetch("""
            SELECT q.id, q.user_id, q.company_id, q.token_limit, q.window_hours, q.is_active, q.created_at,
                   u.email as user_email,
                   c.name as company_name
            FROM mw_token_quotas q
            LEFT JOIN users u ON q.user_id = u.id
            LEFT JOIN companies c ON q.company_id = c.id
            ORDER BY q.user_id NULLS LAST, q.created_at DESC
        """)
        return [dict(r) for r in rows]


@router.get("/token-usage", dependencies=[Depends(require_admin)])
async def list_token_usage():
    """Per-user token usage in the current window."""
    async with get_connection() as conn:
        rows = await conn.fetch("""
            SELECT u.id as user_id, u.email, c.name as company_name,
                   COALESCE(SUM(e.total_tokens), 0)::bigint as tokens_used,
                   COUNT(e.id)::int as call_count,
                   COALESCE(SUM(e.cost_dollars), 0)::numeric as cost_dollars,
                   MAX(e.created_at) as last_active
            FROM users u
            LEFT JOIN companies c ON u.company_id = c.id
            LEFT JOIN mw_token_usage_events e ON e.user_id = u.id AND e.created_at > NOW() - interval '12 hours'
            WHERE u.is_active = true
            GROUP BY u.id, u.email, c.name
            HAVING COALESCE(SUM(e.total_tokens), 0) > 0
            ORDER BY tokens_used DESC
        """)
        return [dict(r) for r in rows]


@router.post("/token-quotas", dependencies=[Depends(require_admin)])
async def create_token_quota(body: dict):
    """Create a new token quota."""
    user_id = body.get("user_id")
    company_id = body.get("company_id")
    token_limit = body.get("token_limit", 100000)
    window_hours = body.get("window_hours", 12)

    async with get_connection() as conn:
        row = await conn.fetchrow("""
            INSERT INTO mw_token_quotas (user_id, company_id, token_limit, window_hours)
            VALUES ($1, $2, $3, $4)
            RETURNING *
        """, user_id, company_id, token_limit, window_hours)
        return dict(row)


@router.put("/token-quotas/{quota_id}", dependencies=[Depends(require_admin)])
async def update_token_quota(quota_id: str, body: dict):
    """Update an existing token quota."""
    from uuid import UUID
    async with get_connection() as conn:
        sets = []
        vals = []
        idx = 1
        for key in ("token_limit", "window_hours", "is_active"):
            if key in body:
                sets.append(f"{key} = ${idx}")
                vals.append(body[key])
                idx += 1
        if not sets:
            return {"detail": "No changes"}
        vals.append(UUID(quota_id))
        row = await conn.fetchrow(
            f"UPDATE mw_token_quotas SET {', '.join(sets)}, updated_at = NOW() WHERE id = ${idx} RETURNING *",
            *vals,
        )
        if not row:
            from fastapi import HTTPException
            raise HTTPException(status_code=404, detail="Quota not found")
        return dict(row)


@router.delete("/token-quotas/{quota_id}", dependencies=[Depends(require_admin)])
async def delete_token_quota(quota_id: str):
    """Delete a token quota."""
    from uuid import UUID
    async with get_connection() as conn:
        await conn.execute("DELETE FROM mw_token_quotas WHERE id = $1", UUID(quota_id))
        return {"deleted": True}


@router.get("/overview", dependencies=[Depends(require_admin)])
async def admin_overview():
    """Get platform overview with company and employee stats."""
    async with get_connection() as conn:
        rows = await conn.fetch(
            """
            SELECT
                comp.id,
                comp.name,
                comp.industry,
                comp.size,
                comp.status,
                comp.created_at,
                comp.approved_at,
                COUNT(e.id) AS total_employees,
                COUNT(CASE WHEN e.user_id IS NOT NULL AND e.termination_date IS NULL THEN 1 END) AS active_employees,
                COUNT(CASE WHEN e.termination_date IS NOT NULL THEN 1 END) AS terminated_employees,
                COUNT(CASE WHEN e.id IS NOT NULL AND e.user_id IS NULL AND e.termination_date IS NULL THEN 1 END) AS pending_employees
            FROM companies comp
            LEFT JOIN employees e ON e.org_id = comp.id
            WHERE comp.owner_id IS NOT NULL
            GROUP BY comp.id
            ORDER BY comp.created_at DESC
            """
        )

        companies = [
            {
                "id": str(row["id"]),
                "name": row["name"],
                "industry": row["industry"],
                "size": row["size"],
                "status": row["status"] or "approved",
                "created_at": row["created_at"].isoformat() if row["created_at"] else None,
                "approved_at": row["approved_at"].isoformat() if row["approved_at"] else None,
                "total_employees": row["total_employees"],
                "active_employees": row["active_employees"],
                "terminated_employees": row["terminated_employees"],
                "pending_employees": row["pending_employees"],
            }
            for row in rows
        ]

        totals = {
            "total_companies": len(companies),
            "total_employees": sum(c["total_employees"] for c in companies),
            "active_employees": sum(c["active_employees"] for c in companies),
            "pending_employees": sum(c["pending_employees"] for c in companies),
            "terminated_employees": sum(c["terminated_employees"] for c in companies),
        }

        return {"companies": companies, "totals": totals}


# Known feature keys that can be toggled
KNOWN_FEATURES = {
    "policies", "handbooks", "compliance",
    "employees", "offer_letters",
    "er_copilot", "incidents", "time_off", "accommodations", "interview_prep",
    "matcha_work", "risk_assessment",
    "training", "i9", "cobra", "separation_agreements", "hris_import",
    "paid_channel_creator", "discipline",
}


class SubscriptionSummary(BaseModel):
    """Lite snapshot of an mw_subscriptions row, surfaced in admin views."""
    pack_id: str
    status: str
    amount_cents: int
    stripe_subscription_id: str
    stripe_customer_id: str
    current_period_end: Optional[datetime] = None
    canceled_at: Optional[datetime] = None


class BusinessRegistrationResponse(BaseModel):
    """Response model for a business registration."""
    id: UUID
    company_name: str
    industry: Optional[str]
    healthcare_specialties: Optional[list[str]] = None
    company_size: Optional[str]
    owner_user_id: Optional[UUID] = None
    owner_email: str
    owner_name: str
    owner_phone: Optional[str]
    owner_job_title: Optional[str]
    status: str
    rejection_reason: Optional[str]
    approved_at: Optional[datetime]
    approved_by_email: Optional[str]
    created_at: datetime
    signup_source: Optional[str] = None
    is_personal: bool = False
    is_suspended: bool = False
    deleted_at: Optional[datetime] = None
    subscription: Optional[SubscriptionSummary] = None


class BusinessRegistrationListResponse(BaseModel):
    """List response for business registrations."""
    registrations: list[BusinessRegistrationResponse]
    total: int


class RejectRequest(BaseModel):
    """Request model for rejecting a business registration."""
    reason: str


class UpdateBusinessRegistrationRequest(BaseModel):
    """Request model for updating business registration details."""
    company_name: Optional[str] = Field(default=None, min_length=1, max_length=255)
    industry: Optional[str] = Field(default=None, max_length=100)
    company_size: Optional[str] = Field(default=None, max_length=50)
    owner_email: Optional[EmailStr] = None
    owner_name: Optional[str] = Field(default=None, min_length=1, max_length=255)
    owner_phone: Optional[str] = Field(default=None, max_length=50)
    owner_job_title: Optional[str] = Field(default=None, max_length=100)


def _row_to_registration(row) -> BusinessRegistrationResponse:
    sub: Optional[SubscriptionSummary] = None
    if row["sub_pack_id"]:
        sub = SubscriptionSummary(
            pack_id=row["sub_pack_id"],
            status=row["sub_status"],
            amount_cents=row["sub_amount_cents"],
            stripe_subscription_id=row["sub_stripe_sub_id"],
            stripe_customer_id=row["sub_stripe_customer_id"],
            current_period_end=row["sub_current_period_end"],
            canceled_at=row["sub_canceled_at"],
        )
    return BusinessRegistrationResponse(
        id=row["id"],
        company_name=row["company_name"],
        industry=row["industry"],
        healthcare_specialties=list(row["healthcare_specialties"] or []) or None,
        company_size=row["company_size"],
        owner_user_id=row["owner_user_id"],
        owner_email=row["owner_email"],
        owner_name=row["owner_name"],
        owner_phone=row["owner_phone"],
        owner_job_title=row["owner_job_title"],
        status=row["status"] or "approved",
        rejection_reason=row["rejection_reason"],
        approved_at=row["approved_at"],
        approved_by_email=row["approved_by_email"],
        created_at=row["created_at"],
        signup_source=row["signup_source"],
        is_personal=bool(row["is_personal"]),
        is_suspended=bool(row["is_suspended"]),
        deleted_at=row["deleted_at"],
        subscription=sub,
    )


_BUSINESS_REGISTRATION_SELECT = """
    SELECT
        comp.id,
        comp.name as company_name,
        comp.industry,
        comp.healthcare_specialties,
        comp.size as company_size,
        comp.signup_source,
        comp.is_personal,
        comp.deleted_at,
        u.id as owner_user_id,
        u.email as owner_email,
        u.is_suspended as is_suspended,
        c.name as owner_name,
        c.phone as owner_phone,
        c.job_title as owner_job_title,
        comp.status,
        comp.rejection_reason,
        comp.approved_at,
        approver.email as approved_by_email,
        comp.created_at,
        sub.pack_id as sub_pack_id,
        sub.status as sub_status,
        sub.amount_cents as sub_amount_cents,
        sub.stripe_subscription_id as sub_stripe_sub_id,
        sub.stripe_customer_id as sub_stripe_customer_id,
        sub.current_period_end as sub_current_period_end,
        sub.canceled_at as sub_canceled_at
    FROM companies comp
    JOIN clients c ON c.company_id = comp.id
    JOIN users u ON c.user_id = u.id
    LEFT JOIN users approver ON comp.approved_by = approver.id
    LEFT JOIN LATERAL (
        SELECT pack_id, status, amount_cents, stripe_subscription_id,
               stripe_customer_id, current_period_end, canceled_at
        FROM mw_subscriptions
        WHERE company_id = comp.id
        ORDER BY (status = 'active') DESC, created_at DESC
        LIMIT 1
    ) sub ON TRUE
"""


def _tier_filter_clause(tier: Optional[str]) -> tuple[str, list]:
    """Translate a tier chip ('free'|'lite'|'platform'|'personal') to SQL.

    Personal is by `is_personal=true` (lives on companies). The other three
    are by `signup_source` value; platform covers bespoke + legacy NULL rows
    AND excludes personal workspaces.
    """
    if tier == "free":
        return " AND comp.signup_source = 'resources_free'", []
    if tier == "lite":
        return " AND comp.signup_source = 'matcha_lite'", []
    if tier == "platform":
        return " AND (comp.signup_source IN ('bespoke') OR comp.signup_source IS NULL) AND comp.is_personal IS NOT TRUE", []
    if tier == "personal":
        return " AND comp.is_personal = TRUE", []
    return "", []


@router.get("/business-registrations", response_model=BusinessRegistrationListResponse, dependencies=[Depends(require_admin)])
async def list_business_registrations(
    status_filter: Optional[str] = Query(None, alias="status", description="Filter by status: pending, approved, rejected"),
    signup_source: Optional[str] = Query(None, description="Filter by signup_source value (resources_free, matcha_lite, bespoke, ir_only_self_serve)"),
    tier: Optional[str] = Query(None, description="Tier chip: free | lite | platform | personal"),
    include_deleted: bool = Query(False, description="Include soft-deleted companies"),
):
    """List all business registrations with optional status/tier filters."""
    async with get_connection() as conn:
        query = _BUSINESS_REGISTRATION_SELECT + " WHERE comp.owner_id IS NOT NULL"
        params: list = []

        if not include_deleted:
            query += " AND comp.deleted_at IS NULL"

        if status_filter:
            params.append(status_filter)
            query += f" AND comp.status = ${len(params)}"

        if signup_source:
            params.append(signup_source)
            query += f" AND comp.signup_source = ${len(params)}"

        tier_clause, tier_params = _tier_filter_clause(tier)
        if tier_clause:
            query += tier_clause
            params.extend(tier_params)

        query += " ORDER BY comp.created_at DESC"

        rows = await conn.fetch(query, *params)
        registrations = [_row_to_registration(row) for row in rows]
        return BusinessRegistrationListResponse(
            registrations=registrations,
            total=len(registrations),
        )


@router.get("/business-registrations/{company_id}", response_model=BusinessRegistrationResponse, dependencies=[Depends(require_admin)])
async def get_business_registration(company_id: UUID):
    """Get details of a specific business registration."""
    async with get_connection() as conn:
        row = await conn.fetchrow(
            _BUSINESS_REGISTRATION_SELECT + " WHERE comp.id = $1 AND comp.owner_id IS NOT NULL",
            company_id,
        )

        if not row:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Business registration not found",
            )

        return _row_to_registration(row)


@router.patch("/business-registrations/{company_id}", response_model=BusinessRegistrationResponse, dependencies=[Depends(require_admin)])
async def update_business_registration(
    company_id: UUID,
    request: UpdateBusinessRegistrationRequest,
):
    """Update business registration company and owner details."""
    payload = request.model_dump(exclude_unset=True)
    if not payload:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="At least one field must be provided",
        )

    def _clean_optional_text(value: Optional[str]) -> Optional[str]:
        if value is None:
            return None
        cleaned = value.strip()
        return cleaned or None

    async with get_connection() as conn:
        async with conn.transaction():
            owner_row = await conn.fetchrow(
                """
                SELECT comp.id, comp.owner_id
                FROM companies comp
                WHERE comp.id = $1 AND comp.owner_id IS NOT NULL
                """,
                company_id,
            )
            if not owner_row:
                raise HTTPException(
                    status_code=status.HTTP_404_NOT_FOUND,
                    detail="Business registration not found",
                )

            owner_id = owner_row["owner_id"]

            if "company_name" in payload:
                company_name = (request.company_name or "").strip()
                if not company_name:
                    raise HTTPException(
                        status_code=status.HTTP_400_BAD_REQUEST,
                        detail="Company name cannot be empty",
                    )
                await conn.execute(
                    "UPDATE companies SET name = $1 WHERE id = $2",
                    company_name,
                    company_id,
                )

            if "industry" in payload:
                await conn.execute(
                    "UPDATE companies SET industry = $1 WHERE id = $2",
                    _clean_optional_text(request.industry),
                    company_id,
                )

            if "company_size" in payload:
                await conn.execute(
                    "UPDATE companies SET size = $1 WHERE id = $2",
                    _clean_optional_text(request.company_size),
                    company_id,
                )

            if "owner_email" in payload:
                owner_email = str(request.owner_email).strip().lower() if request.owner_email else ""
                if not owner_email:
                    raise HTTPException(
                        status_code=status.HTTP_400_BAD_REQUEST,
                        detail="Owner email cannot be empty",
                    )

                existing_user_id = await conn.fetchval(
                    "SELECT id FROM users WHERE lower(email) = lower($1) AND id <> $2",
                    owner_email,
                    owner_id,
                )
                if existing_user_id:
                    raise HTTPException(
                        status_code=status.HTTP_400_BAD_REQUEST,
                        detail="Another user already uses this email",
                    )

                await conn.execute(
                    "UPDATE users SET email = $1 WHERE id = $2",
                    owner_email,
                    owner_id,
                )

            client_fields: list[str] = []
            client_params: list[Any] = []
            idx = 1

            if "owner_name" in payload:
                owner_name = (request.owner_name or "").strip()
                if not owner_name:
                    raise HTTPException(
                        status_code=status.HTTP_400_BAD_REQUEST,
                        detail="Owner name cannot be empty",
                    )
                client_fields.append(f"name = ${idx}")
                client_params.append(owner_name)
                idx += 1

            if "owner_phone" in payload:
                client_fields.append(f"phone = ${idx}")
                client_params.append(_clean_optional_text(request.owner_phone))
                idx += 1

            if "owner_job_title" in payload:
                client_fields.append(f"job_title = ${idx}")
                client_params.append(_clean_optional_text(request.owner_job_title))
                idx += 1

            if client_fields:
                client_params.extend([owner_id, company_id])
                result = await conn.execute(
                    f"""
                    UPDATE clients
                    SET {", ".join(client_fields)}
                    WHERE user_id = ${idx} AND company_id = ${idx + 1}
                    """,
                    *client_params,
                )
                if result == "UPDATE 0":
                    raise HTTPException(
                        status_code=status.HTTP_400_BAD_REQUEST,
                        detail="Business owner profile not found for this company",
                    )

        row = await conn.fetchrow(
            """
            SELECT
                comp.id,
                comp.name as company_name,
                comp.industry,
                comp.size as company_size,
                u.email as owner_email,
                c.name as owner_name,
                c.phone as owner_phone,
                c.job_title as owner_job_title,
                comp.status,
                comp.rejection_reason,
                comp.approved_at,
                approver.email as approved_by_email,
                comp.created_at
            FROM companies comp
            JOIN users u ON u.id = comp.owner_id
            JOIN clients c ON c.user_id = comp.owner_id AND c.company_id = comp.id
            LEFT JOIN users approver ON comp.approved_by = approver.id
            WHERE comp.id = $1 AND comp.owner_id IS NOT NULL
            """,
            company_id,
        )

        if not row:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Business registration not found",
            )

        from ...matcha.services.matcha_work_document import invalidate_company_profile_cache
        invalidate_company_profile_cache(company_id)

        return BusinessRegistrationResponse(
            id=row["id"],
            company_name=row["company_name"],
            industry=row["industry"],
            company_size=row["company_size"],
            owner_email=row["owner_email"],
            owner_name=row["owner_name"],
            owner_phone=row["owner_phone"],
            owner_job_title=row["owner_job_title"],
            status=row["status"] or "approved",
            rejection_reason=row["rejection_reason"],
            approved_at=row["approved_at"],
            approved_by_email=row["approved_by_email"],
            created_at=row["created_at"],
        )


@router.post("/business-registrations/{company_id}/approve", dependencies=[Depends(require_admin)])
async def approve_business_registration(
    company_id: UUID,
    current_user=Depends(require_admin)
):
    """Approve a pending business registration."""
    async with get_connection() as conn:
        # Get company and owner info
        company = await conn.fetchrow(
            """
            SELECT comp.id, comp.name, comp.status, u.email, c.name as owner_name
            FROM companies comp
            JOIN clients c ON c.company_id = comp.id
            JOIN users u ON c.user_id = u.id
            WHERE comp.id = $1
            """,
            company_id
        )

        if not company:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Business registration not found"
            )

        if company["status"] == "approved":
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Business is already approved"
            )

        # Approve the company
        await conn.execute(
            """
            UPDATE companies
            SET status = 'approved', approved_at = NOW(), approved_by = $1
            WHERE id = $2
            """,
            current_user.id, company_id
        )

        # Send approval email
        email_service = get_email_service()
        await email_service.send_business_approved_email(
            to_email=company["email"],
            to_name=company["owner_name"],
            company_name=company["name"]
        )

        return {"status": "approved", "message": f"Business '{company['name']}' has been approved"}


@router.post("/business-registrations/{company_id}/reject", dependencies=[Depends(require_admin)])
async def reject_business_registration(
    company_id: UUID,
    request: RejectRequest,
    current_user=Depends(require_admin)
):
    """Reject a pending business registration with a reason."""
    if not request.reason or not request.reason.strip():
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Rejection reason is required"
        )

    async with get_connection() as conn:
        # Get company and owner info
        company = await conn.fetchrow(
            """
            SELECT comp.id, comp.name, comp.status, u.email, c.name as owner_name
            FROM companies comp
            JOIN clients c ON c.company_id = comp.id
            JOIN users u ON c.user_id = u.id
            WHERE comp.id = $1
            """,
            company_id
        )

        if not company:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Business registration not found"
            )

        if company["status"] == "rejected":
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Business is already rejected"
            )

        # Reject the company
        await conn.execute(
            """
            UPDATE companies
            SET status = 'rejected', rejection_reason = $1, approved_by = $2
            WHERE id = $3
            """,
            request.reason.strip(), current_user.id, company_id
        )

        # Send rejection email
        email_service = get_email_service()
        await email_service.send_business_rejected_email(
            to_email=company["email"],
            to_name=company["owner_name"],
            company_name=company["name"],
            reason=request.reason.strip()
        )

        return {"status": "rejected", "message": f"Business '{company['name']}' has been rejected"}


# =============================================================================
# Business Invite Links
# =============================================================================

class CreateBusinessInviteRequest(BaseModel):
    note: Optional[str] = None
    expires_days: int = Field(default=7, ge=1, le=90)


class BusinessInviteResponse(BaseModel):
    id: UUID
    token: str
    invite_url: str
    status: str
    note: Optional[str]
    created_by_email: str
    used_by_company_name: Optional[str]
    expires_at: datetime
    used_at: Optional[datetime]
    created_at: datetime


@router.post("/business-invites", dependencies=[Depends(require_admin)])
async def create_business_invite(
    request: CreateBusinessInviteRequest = CreateBusinessInviteRequest(),
    current_user=Depends(require_admin),
):
    """Generate a new business invite link. Businesses registering with this link are auto-approved."""
    token = secrets.token_urlsafe(32)
    expires_at = datetime.utcnow() + timedelta(days=request.expires_days)

    async with get_connection() as conn:
        row = await conn.fetchrow(
            """
            INSERT INTO business_invitations (token, created_by, expires_at, note)
            VALUES ($1, $2, $3, $4)
            RETURNING id, token, status, expires_at, created_at
            """,
            token, current_user.id, expires_at, request.note,
        )

        base_url = get_settings().app_base_url.rstrip("/")
        invite_url = f"{base_url}/register/invite/{token}"

        return {
            "id": str(row["id"]),
            "token": row["token"],
            "invite_url": invite_url,
            "status": row["status"],
            "note": request.note,
            "expires_at": row["expires_at"].isoformat(),
            "created_at": row["created_at"].isoformat(),
        }


@router.get("/business-invites", dependencies=[Depends(require_admin)])
async def list_business_invites():
    """List all business invite links."""
    async with get_connection() as conn:
        rows = await conn.fetch(
            """
            SELECT
                bi.id, bi.token, bi.status, bi.note,
                bi.expires_at, bi.used_at, bi.created_at,
                u.email as created_by_email,
                c.name as used_by_company_name
            FROM business_invitations bi
            JOIN users u ON bi.created_by = u.id
            LEFT JOIN companies c ON bi.used_by_company_id = c.id
            ORDER BY bi.created_at DESC
            """
        )

        invites = []
        for row in rows:
            # Auto-expire if past expiry
            row_status = row["status"]
            if row_status == "pending" and row["expires_at"] < datetime.utcnow():
                row_status = "expired"

            invites.append({
                "id": str(row["id"]),
                "token": row["token"],
                "invite_url": f"{get_settings().app_base_url.rstrip('/')}/register/invite/{row['token']}",
                "status": row_status,
                "note": row["note"],
                "created_by_email": row["created_by_email"],
                "used_by_company_name": row["used_by_company_name"],
                "expires_at": row["expires_at"].isoformat(),
                "used_at": row["used_at"].isoformat() if row["used_at"] else None,
                "created_at": row["created_at"].isoformat(),
            })

        return {"invites": invites, "total": len(invites)}


@router.delete("/business-invites/{invite_id}", dependencies=[Depends(require_admin)])
async def cancel_business_invite(invite_id: UUID):
    """Cancel a pending business invite link."""
    async with get_connection() as conn:
        result = await conn.execute(
            "UPDATE business_invitations SET status = 'cancelled' WHERE id = $1 AND status = 'pending'",
            invite_id,
        )
        rows_affected = int(result.split()[-1])

        if rows_affected == 0:
            row = await conn.fetchrow(
                "SELECT status FROM business_invitations WHERE id = $1",
                invite_id,
            )
            if not row:
                raise HTTPException(status_code=404, detail="Invite not found")
            raise HTTPException(status_code=400, detail=f"Cannot cancel invite with status '{row['status']}'")

        return {"status": "cancelled", "message": "Invite link has been cancelled"}


# =============================================================================
# Company Feature Flags
# =============================================================================

class FeatureToggleRequest(BaseModel):
    """Request model for toggling a company feature."""
    feature: str
    enabled: bool


class CompanyCreditsAdjustRequest(BaseModel):
    credits: int
    description: Optional[str] = Field(default=None, max_length=500)


@router.get("/company-features", dependencies=[Depends(require_admin)])
async def list_company_features():
    """List all companies with their enabled features."""
    async with get_connection() as conn:
        rows = await conn.fetch(
            """
            SELECT id, name as company_name, industry, size, status, enabled_features
            FROM companies
            ORDER BY name
            """
        )

        return [
            {
                "id": str(row["id"]),
                "company_name": row["company_name"],
                "industry": row["industry"],
                "size": row["size"],
                "status": row["status"] or "approved",
                "enabled_features": merge_company_features(row["enabled_features"]),
            }
            for row in rows
        ]


@router.patch("/company-features/{company_id}", dependencies=[Depends(require_admin)])
async def toggle_company_feature(company_id: UUID, request: FeatureToggleRequest):
    """Toggle a single feature on/off for a company."""
    if request.feature not in KNOWN_FEATURES:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Unknown feature: {request.feature}. Valid features: {', '.join(sorted(KNOWN_FEATURES))}"
        )

    async with get_connection() as conn:
        async with conn.transaction():
            row = await conn.fetchrow(
                """
                SELECT enabled_features
                FROM companies
                WHERE id = $1
                FOR UPDATE
                """,
                company_id,
            )
            if row is None:
                raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Company not found")

            features = merge_company_features(row["enabled_features"])
            features[request.feature] = bool(request.enabled)

            await conn.execute(
                """
                UPDATE companies
                SET enabled_features = $1
                WHERE id = $2
                """,
                json.dumps(features),
                company_id,
            )

        return {"enabled_features": features}


@router.patch("/users/{user_id}/beta-flags", dependencies=[Depends(require_admin)])
async def patch_user_beta_flags(user_id: UUID, body: Dict[str, Any] = Body(...)):
    """Set matcha_work_beta_lite / matcha_work_beta_full flags on a user."""
    allowed = {"matcha_work_beta_lite", "matcha_work_beta_full"}
    patch = {k: v for k, v in body.items() if k in allowed and isinstance(v, bool)}
    if not patch:
        raise HTTPException(status_code=400, detail="No valid beta flag keys provided")
    async with get_connection() as conn:
        row = await conn.fetchrow(
            """
            UPDATE users
            SET beta_features = COALESCE(beta_features, '{}'::jsonb) || $1::jsonb
            WHERE id = $2
            RETURNING beta_features
            """,
            json.dumps(patch),
            user_id,
        )
    if not row:
        raise HTTPException(status_code=404, detail="User not found")
    return {"beta_features": dict(row["beta_features"])}


@router.post("/companies/{company_id}/credits")
async def adjust_company_credits(
    company_id: UUID,
    request: CompanyCreditsAdjustRequest,
    current_user=Depends(require_admin),
):
    """Grant or adjust Matcha Work credits for a company."""
    result = await mw_billing_service.grant_credits(
        company_id=company_id,
        credits=int(request.credits),
        description=request.description,
        granted_by=current_user.id,
    )
    balance = result["balance"]
    transaction = result["transaction"]
    return {
        "company_id": str(company_id),
        "credits_remaining": balance["credits_remaining"],
        "total_credits_purchased": balance["total_credits_purchased"],
        "total_credits_granted": balance["total_credits_granted"],
        "transaction": {
            "id": str(transaction["id"]),
            "transaction_type": transaction["transaction_type"],
            "credits_delta": transaction["credits_delta"],
            "credits_after": transaction["credits_after"],
            "description": transaction["description"],
            "created_at": transaction["created_at"].isoformat() if transaction["created_at"] else None,
            "created_by": str(transaction["created_by"]) if transaction["created_by"] else None,
        },
    }


# =============================================================================
# Scheduler Management
# =============================================================================

class SchedulerUpdateRequest(BaseModel):
    """Request model for updating scheduler settings."""
    enabled: Optional[bool] = None
    max_per_cycle: Optional[int] = None


# =============================================================================
# Broker Channel Management
# =============================================================================

VALID_BROKER_STATUSES = {"pending", "active", "suspended", "terminated"}
VALID_BROKER_SUPPORT_ROUTING = {"broker_first", "matcha_first", "shared"}
VALID_BROKER_BILLING_MODES = {"direct", "reseller", "hybrid"}
VALID_INVOICE_OWNERS = {"matcha", "broker"}
VALID_BROKER_CONTRACT_STATUSES = {"draft", "active", "suspended", "terminated"}
VALID_BROKER_LINK_STATUSES = {"pending", "active", "suspending", "grace", "terminated", "transferred"}
VALID_POST_TERMINATION_MODES = {"convert_to_direct", "transfer_to_broker", "sunset", "matcha_managed"}
VALID_BROKER_BRANDING_MODES = {"direct", "co_branded", "white_label"}
VALID_TRANSITION_STATUSES = {"planned", "in_progress", "completed", "cancelled"}
VALID_DATA_HANDOFF_STATUSES = {"not_required", "pending", "in_progress", "completed"}
VALID_LINK_TRANSITION_STATES = {"none", "planned", "in_progress", "matcha_managed", "completed"}


def _slugify_broker_name(name: str) -> str:
    slug = re.sub(r"[^a-z0-9]+", "-", name.strip().lower()).strip("-")
    return slug[:120] or "broker"


class BrokerCreateRequest(BaseModel):
    broker_name: str = Field(..., min_length=2, max_length=255)
    owner_email: EmailStr
    owner_name: str = Field(..., min_length=2, max_length=255)
    owner_password: Optional[str] = Field(default=None, min_length=8)
    slug: Optional[str] = Field(default=None, min_length=2, max_length=120)
    support_routing: str = Field(default="shared")
    billing_mode: str = Field(default="direct")
    invoice_owner: str = Field(default="matcha")
    terms_required_version: str = Field(default="v1", min_length=1, max_length=50)


class BrokerUpdateRequest(BaseModel):
    status: Optional[str] = None
    support_routing: Optional[str] = None
    terms_required_version: Optional[str] = Field(default=None, min_length=1, max_length=50)
    terminated_at: Optional[datetime] = None
    grace_until: Optional[datetime] = None
    post_termination_mode: Optional[str] = None


class BrokerContractRequest(BaseModel):
    status: str = Field(default="active")
    billing_mode: str
    invoice_owner: str
    currency: str = Field(default="USD", min_length=3, max_length=3)
    base_platform_fee: float = 0.0
    pepm_rate: float = 0.0
    minimum_monthly_commit: float = 0.0
    pricing_rules: dict = {}


class BrokerCompanyLinkRequest(BaseModel):
    status: str = Field(default="active")
    permissions: dict = Field(default_factory=dict)
    post_termination_mode: Optional[str] = None
    grace_until: Optional[datetime] = None


class BrokerBrandingRequest(BaseModel):
    branding_mode: str = Field(default="direct")
    brand_display_name: Optional[str] = Field(default=None, max_length=255)
    brand_legal_name: Optional[str] = Field(default=None, max_length=255)
    logo_url: Optional[str] = None
    favicon_url: Optional[str] = None
    primary_color: Optional[str] = Field(default=None, max_length=20)
    secondary_color: Optional[str] = Field(default=None, max_length=20)
    login_subdomain: Optional[str] = Field(default=None, max_length=120)
    custom_login_url: Optional[str] = None
    support_email: Optional[EmailStr] = None
    support_phone: Optional[str] = Field(default=None, max_length=50)
    support_url: Optional[str] = None
    email_from_name: Optional[str] = Field(default=None, max_length=255)
    email_from_address: Optional[EmailStr] = None
    powered_by_badge: bool = True
    hide_matcha_identity: bool = False
    mobile_branding_enabled: bool = False
    theme: dict = Field(default_factory=dict)
    metadata: dict = Field(default_factory=dict)


class BrokerCompanyTransitionRequest(BaseModel):
    mode: str
    status: str = Field(default="planned")
    transfer_target_broker_id: Optional[UUID] = None
    grace_until: Optional[datetime] = None
    matcha_managed_until: Optional[datetime] = None
    data_handoff_status: str = Field(default="pending")
    data_handoff_notes: Optional[str] = None
    metadata: dict = Field(default_factory=dict)


class BrokerCompanyTransitionUpdateRequest(BaseModel):
    status: Optional[str] = None
    grace_until: Optional[datetime] = None
    matcha_managed_until: Optional[datetime] = None
    data_handoff_status: Optional[str] = None
    data_handoff_notes: Optional[str] = None
    completed_at: Optional[datetime] = None
    metadata: Optional[dict] = None


def _validate_broker_enums(*, status_value: Optional[str] = None, support_routing: Optional[str] = None,
                           billing_mode: Optional[str] = None, invoice_owner: Optional[str] = None,
                           contract_status: Optional[str] = None, link_status: Optional[str] = None,
                           post_termination_mode: Optional[str] = None, branding_mode: Optional[str] = None,
                           transition_status: Optional[str] = None,
                           data_handoff_status: Optional[str] = None,
                           link_transition_state: Optional[str] = None):
    if status_value is not None and status_value not in VALID_BROKER_STATUSES:
        raise HTTPException(status_code=400, detail=f"Invalid broker status '{status_value}'")
    if support_routing is not None and support_routing not in VALID_BROKER_SUPPORT_ROUTING:
        raise HTTPException(status_code=400, detail=f"Invalid support_routing '{support_routing}'")
    if billing_mode is not None and billing_mode not in VALID_BROKER_BILLING_MODES:
        raise HTTPException(status_code=400, detail=f"Invalid billing_mode '{billing_mode}'")
    if invoice_owner is not None and invoice_owner not in VALID_INVOICE_OWNERS:
        raise HTTPException(status_code=400, detail=f"Invalid invoice_owner '{invoice_owner}'")
    if contract_status is not None and contract_status not in VALID_BROKER_CONTRACT_STATUSES:
        raise HTTPException(status_code=400, detail=f"Invalid contract status '{contract_status}'")
    if link_status is not None and link_status not in VALID_BROKER_LINK_STATUSES:
        raise HTTPException(status_code=400, detail=f"Invalid link status '{link_status}'")
    if post_termination_mode is not None and post_termination_mode not in VALID_POST_TERMINATION_MODES:
        raise HTTPException(status_code=400, detail=f"Invalid post_termination_mode '{post_termination_mode}'")
    if branding_mode is not None and branding_mode not in VALID_BROKER_BRANDING_MODES:
        raise HTTPException(status_code=400, detail=f"Invalid branding_mode '{branding_mode}'")
    if transition_status is not None and transition_status not in VALID_TRANSITION_STATUSES:
        raise HTTPException(status_code=400, detail=f"Invalid transition status '{transition_status}'")
    if data_handoff_status is not None and data_handoff_status not in VALID_DATA_HANDOFF_STATUSES:
        raise HTTPException(status_code=400, detail=f"Invalid data_handoff_status '{data_handoff_status}'")
    if link_transition_state is not None and link_transition_state not in VALID_LINK_TRANSITION_STATES:
        raise HTTPException(status_code=400, detail=f"Invalid link transition state '{link_transition_state}'")


def _transition_state_for(mode: str, transition_status: str) -> str:
    if transition_status == "cancelled":
        return "none"
    if mode == "matcha_managed":
        return "matcha_managed"
    if transition_status == "planned":
        return "planned"
    if transition_status == "in_progress":
        return "in_progress"
    if transition_status == "completed":
        return "completed"
    return "none"


def _link_status_for(mode: str, transition_status: str, current_status: str) -> str:
    if transition_status == "planned":
        if mode in {"convert_to_direct", "matcha_managed"}:
            return "grace"
        if mode in {"transfer_to_broker", "sunset"}:
            return "suspending"
    if transition_status == "in_progress":
        if mode in {"convert_to_direct", "matcha_managed"}:
            return "grace"
        if mode in {"transfer_to_broker", "sunset"}:
            return "suspending"
    if transition_status == "completed":
        if mode == "transfer_to_broker":
            return "transferred"
        if mode in {"convert_to_direct", "sunset"}:
            return "terminated"
        if mode == "matcha_managed":
            return "grace"
    if transition_status == "cancelled":
        return "active" if current_status in {"grace", "suspending"} else current_status
    return current_status


@router.post("/brokers", dependencies=[Depends(require_admin)])
async def create_broker(
    request: BrokerCreateRequest,
    current_user=Depends(require_admin),
):
    """Create a broker org, owner user, owner membership, and initial active contract."""
    _validate_broker_enums(
        support_routing=request.support_routing,
        billing_mode=request.billing_mode,
        invoice_owner=request.invoice_owner,
    )

    slug_base = _slugify_broker_name(request.slug or request.broker_name)
    generated_password = not bool(request.owner_password and request.owner_password.strip())
    owner_password = request.owner_password.strip() if request.owner_password else secrets.token_urlsafe(12)

    async with get_connection() as conn:
        async with conn.transaction():
            existing = await conn.fetchval("SELECT id FROM users WHERE email = $1", request.owner_email)
            if existing:
                raise HTTPException(status_code=400, detail="Owner email is already registered")

            slug = slug_base
            suffix = 2
            while await conn.fetchval("SELECT EXISTS(SELECT 1 FROM brokers WHERE slug = $1)", slug):
                slug = f"{slug_base}-{suffix}"
                suffix += 1

            user = await conn.fetchrow(
                """
                INSERT INTO users (email, password_hash, role)
                VALUES ($1, $2, 'broker')
                RETURNING id, email, role, created_at
                """,
                request.owner_email,
                hash_password(owner_password),
            )

            broker = await conn.fetchrow(
                """
                INSERT INTO brokers (
                    name, slug, status, support_routing, billing_mode, invoice_owner,
                    terms_required_version, created_by
                )
                VALUES ($1, $2, 'active', $3, $4, $5, $6, $7)
                RETURNING id, name, slug, status, support_routing, billing_mode, invoice_owner, terms_required_version, created_at
                """,
                request.broker_name.strip(),
                slug,
                request.support_routing,
                request.billing_mode,
                request.invoice_owner,
                request.terms_required_version.strip(),
                current_user.id,
            )

            await conn.execute(
                """
                INSERT INTO broker_members (broker_id, user_id, role, permissions, is_active)
                VALUES ($1, $2, 'owner', $3::jsonb, true)
                """,
                broker["id"],
                user["id"],
                json.dumps({"can_manage_team": True, "can_manage_contracts": True, "can_manage_clients": True}),
            )

            contract = await conn.fetchrow(
                """
                INSERT INTO broker_contracts (
                    broker_id, status, billing_mode, invoice_owner, currency,
                    base_platform_fee, pepm_rate, minimum_monthly_commit,
                    pricing_rules, effective_at, created_by
                )
                VALUES ($1, 'active', $2, $3, 'USD', 0, 0, 0, '{}'::jsonb, NOW(), $4)
                RETURNING id
                """,
                broker["id"],
                request.billing_mode,
                request.invoice_owner,
                current_user.id,
            )

            await conn.execute(
                """
                INSERT INTO broker_branding_configs (
                    broker_id, branding_mode, brand_display_name, created_by, updated_by
                )
                VALUES ($1, 'direct', $2, $3, $3)
                ON CONFLICT (broker_id) DO NOTHING
                """,
                broker["id"],
                request.broker_name.strip(),
                current_user.id,
            )

    email_sent = False
    try:
        email_service = get_email_service()
        email_sent = await email_service.send_broker_welcome_email(
            to_email=request.owner_email,
            to_name=request.owner_name,
            broker_name=request.broker_name.strip(),
            broker_slug=slug,
            password=owner_password,
        )
    except Exception as e:
        logger.error("Failed to send broker welcome email to %s: %s", request.owner_email, e)

    return {
        "status": "created",
        "broker": {
            "id": str(broker["id"]),
            "name": broker["name"],
            "slug": broker["slug"],
            "status": broker["status"],
            "support_routing": broker["support_routing"],
            "billing_mode": broker["billing_mode"],
            "invoice_owner": broker["invoice_owner"],
            "terms_required_version": broker["terms_required_version"],
            "created_at": broker["created_at"].isoformat() if broker["created_at"] else None,
        },
        "owner": {
            "user_id": str(user["id"]),
            "email": user["email"],
            "name": request.owner_name,
            "generated_password": generated_password,
            "password": owner_password,
            "email_sent": email_sent,
        },
        "contract_id": str(contract["id"]),
    }


@router.get("/brokers", dependencies=[Depends(require_admin)])
async def list_brokers():
    """List brokers with contract, member, and linked-company counts."""
    async with get_connection() as conn:
        rows = await conn.fetch(
            """
            SELECT
                b.id, b.name, b.slug, b.status, b.support_routing, b.billing_mode,
                b.invoice_owner, b.terms_required_version, b.created_at,
                COALESCE(bb.branding_mode, 'direct') as branding_mode,
                COUNT(DISTINCT bm.user_id) FILTER (WHERE bm.is_active = true) AS active_member_count,
                COUNT(DISTINCT bcl.company_id) FILTER (WHERE bcl.status IN ('active', 'grace')) AS active_company_count,
                bc.id AS active_contract_id,
                bc.currency,
                bc.base_platform_fee,
                bc.pepm_rate,
                bc.minimum_monthly_commit
            FROM brokers b
            LEFT JOIN broker_branding_configs bb ON bb.broker_id = b.id
            LEFT JOIN broker_members bm ON bm.broker_id = b.id
            LEFT JOIN broker_company_links bcl ON bcl.broker_id = b.id
            LEFT JOIN LATERAL (
                SELECT id, currency, base_platform_fee, pepm_rate, minimum_monthly_commit
                FROM broker_contracts
                WHERE broker_id = b.id AND status = 'active'
                ORDER BY effective_at DESC
                LIMIT 1
            ) bc ON true
            GROUP BY
                b.id, b.name, b.slug, b.status, b.support_routing, b.billing_mode,
                b.invoice_owner, b.terms_required_version, b.created_at, bb.branding_mode,
                bc.id, bc.currency, bc.base_platform_fee, bc.pepm_rate, bc.minimum_monthly_commit
            ORDER BY b.created_at DESC
            """
        )

        return {
            "brokers": [
                {
                    "id": str(row["id"]),
                    "name": row["name"],
                    "slug": row["slug"],
                    "status": row["status"],
                    "support_routing": row["support_routing"],
                    "billing_mode": row["billing_mode"],
                    "invoice_owner": row["invoice_owner"],
                    "terms_required_version": row["terms_required_version"],
                    "branding_mode": row["branding_mode"],
                    "active_member_count": row["active_member_count"],
                    "active_company_count": row["active_company_count"],
                    "active_contract": {
                        "id": str(row["active_contract_id"]) if row["active_contract_id"] else None,
                        "currency": row["currency"],
                        "base_platform_fee": float(row["base_platform_fee"]) if row["base_platform_fee"] is not None else None,
                        "pepm_rate": float(row["pepm_rate"]) if row["pepm_rate"] is not None else None,
                        "minimum_monthly_commit": float(row["minimum_monthly_commit"]) if row["minimum_monthly_commit"] is not None else None,
                    },
                    "created_at": row["created_at"].isoformat() if row["created_at"] else None,
                }
                for row in rows
            ],
            "total": len(rows),
        }


@router.patch("/brokers/{broker_id}", dependencies=[Depends(require_admin)])
async def update_broker(broker_id: UUID, request: BrokerUpdateRequest):
    """Update broker governance fields (status, routing, terms, lifecycle controls)."""
    _validate_broker_enums(
        status_value=request.status,
        support_routing=request.support_routing,
        post_termination_mode=request.post_termination_mode,
    )

    updates = []
    values: list = []
    if request.status is not None:
        updates.append(f"status = ${len(values) + 1}")
        values.append(request.status)
    if request.support_routing is not None:
        updates.append(f"support_routing = ${len(values) + 1}")
        values.append(request.support_routing)
    if request.terms_required_version is not None:
        updates.append(f"terms_required_version = ${len(values) + 1}")
        values.append(request.terms_required_version.strip())
    if request.terminated_at is not None:
        updates.append(f"terminated_at = ${len(values) + 1}")
        values.append(request.terminated_at)
    if request.grace_until is not None:
        updates.append(f"grace_until = ${len(values) + 1}")
        values.append(request.grace_until)
    if request.post_termination_mode is not None:
        updates.append(f"post_termination_mode = ${len(values) + 1}")
        values.append(request.post_termination_mode)

    if not updates:
        raise HTTPException(status_code=400, detail="No fields provided for update")

    updates.append("updated_at = NOW()")
    values.append(broker_id)

    async with get_connection() as conn:
        row = await conn.fetchrow(
            f"""
            UPDATE brokers
            SET {', '.join(updates)}
            WHERE id = ${len(values)}
            RETURNING id, name, slug, status, support_routing, billing_mode, invoice_owner, terms_required_version,
                     terminated_at, grace_until, post_termination_mode, updated_at
            """,
            *values,
        )
        if not row:
            raise HTTPException(status_code=404, detail="Broker not found")

    return {
        "status": "updated",
        "broker": {
            "id": str(row["id"]),
            "name": row["name"],
            "slug": row["slug"],
            "status": row["status"],
            "support_routing": row["support_routing"],
            "billing_mode": row["billing_mode"],
            "invoice_owner": row["invoice_owner"],
            "terms_required_version": row["terms_required_version"],
            "terminated_at": row["terminated_at"].isoformat() if row["terminated_at"] else None,
            "grace_until": row["grace_until"].isoformat() if row["grace_until"] else None,
            "post_termination_mode": row["post_termination_mode"],
            "updated_at": row["updated_at"].isoformat() if row["updated_at"] else None,
        },
    }


@router.put("/brokers/{broker_id}/contract", dependencies=[Depends(require_admin)])
async def upsert_broker_contract(
    broker_id: UUID,
    request: BrokerContractRequest,
    current_user=Depends(require_admin),
):
    """Create a new broker contract version and optionally replace active contract."""
    _validate_broker_enums(
        contract_status=request.status,
        billing_mode=request.billing_mode,
        invoice_owner=request.invoice_owner,
    )
    currency = request.currency.upper().strip()
    if len(currency) != 3:
        raise HTTPException(status_code=400, detail="Currency must be a 3-letter ISO code")

    async with get_connection() as conn:
        async with conn.transaction():
            exists = await conn.fetchval("SELECT EXISTS(SELECT 1 FROM brokers WHERE id = $1)", broker_id)
            if not exists:
                raise HTTPException(status_code=404, detail="Broker not found")

            if request.status == "active":
                await conn.execute(
                    """
                    UPDATE broker_contracts
                    SET status = 'suspended', updated_at = NOW()
                    WHERE broker_id = $1 AND status = 'active'
                    """,
                    broker_id,
                )

            contract = await conn.fetchrow(
                """
                INSERT INTO broker_contracts (
                    broker_id, status, billing_mode, invoice_owner, currency,
                    base_platform_fee, pepm_rate, minimum_monthly_commit,
                    pricing_rules, effective_at, created_by
                )
                VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9::jsonb, NOW(), $10)
                RETURNING id, broker_id, status, billing_mode, invoice_owner, currency,
                          base_platform_fee, pepm_rate, minimum_monthly_commit, pricing_rules, effective_at, created_at
                """,
                broker_id,
                request.status,
                request.billing_mode,
                request.invoice_owner,
                currency,
                request.base_platform_fee,
                request.pepm_rate,
                request.minimum_monthly_commit,
                json.dumps(request.pricing_rules or {}),
                current_user.id,
            )

            await conn.execute(
                """
                UPDATE brokers
                SET billing_mode = $1, invoice_owner = $2, updated_at = NOW()
                WHERE id = $3
                """,
                request.billing_mode,
                request.invoice_owner,
                broker_id,
            )

    return {
        "status": "saved",
        "contract": {
            "id": str(contract["id"]),
            "broker_id": str(contract["broker_id"]),
            "status": contract["status"],
            "billing_mode": contract["billing_mode"],
            "invoice_owner": contract["invoice_owner"],
            "currency": contract["currency"],
            "base_platform_fee": float(contract["base_platform_fee"]),
            "pepm_rate": float(contract["pepm_rate"]),
            "minimum_monthly_commit": float(contract["minimum_monthly_commit"]),
            "pricing_rules": contract["pricing_rules"] if isinstance(contract["pricing_rules"], dict) else {},
            "effective_at": contract["effective_at"].isoformat() if contract["effective_at"] else None,
            "created_at": contract["created_at"].isoformat() if contract["created_at"] else None,
        },
    }


@router.put("/brokers/{broker_id}/companies/{company_id}", dependencies=[Depends(require_admin)])
async def upsert_broker_company_link(
    broker_id: UUID,
    company_id: UUID,
    request: BrokerCompanyLinkRequest,
    current_user=Depends(require_admin),
):
    """Create/update broker-to-company linkage and delegated permissions."""
    _validate_broker_enums(link_status=request.status, post_termination_mode=request.post_termination_mode)

    async with get_connection() as conn:
        async with conn.transaction():
            broker_exists = await conn.fetchval("SELECT EXISTS(SELECT 1 FROM brokers WHERE id = $1)", broker_id)
            if not broker_exists:
                raise HTTPException(status_code=404, detail="Broker not found")

            company_exists = await conn.fetchval("SELECT EXISTS(SELECT 1 FROM companies WHERE id = $1)", company_id)
            if not company_exists:
                raise HTTPException(status_code=404, detail="Company not found")

            row = await conn.fetchrow(
                """
                INSERT INTO broker_company_links (
                    broker_id, company_id, status, permissions, linked_at, activated_at,
                    grace_until, post_termination_mode, created_by, updated_at
                )
                VALUES (
                    $1, $2, $3, $4::jsonb, NOW(),
                    CASE WHEN $3 IN ('active', 'grace') THEN NOW() ELSE NULL END,
                    $5, $6, $7, NOW()
                )
                ON CONFLICT (broker_id, company_id)
                DO UPDATE SET
                    status = EXCLUDED.status,
                    permissions = EXCLUDED.permissions,
                    activated_at = CASE
                        WHEN broker_company_links.activated_at IS NULL
                             AND EXCLUDED.status IN ('active', 'grace') THEN NOW()
                        ELSE broker_company_links.activated_at
                    END,
                    grace_until = EXCLUDED.grace_until,
                    post_termination_mode = EXCLUDED.post_termination_mode,
                    updated_at = NOW()
                RETURNING id, broker_id, company_id, status, permissions, linked_at, activated_at, terminated_at,
                          grace_until, post_termination_mode, updated_at
                """,
                broker_id,
                company_id,
                request.status,
                json.dumps(request.permissions or {}),
                request.grace_until,
                request.post_termination_mode,
                current_user.id,
            )

    return {
        "status": "linked",
        "link": {
            "id": str(row["id"]),
            "broker_id": str(row["broker_id"]),
            "company_id": str(row["company_id"]),
            "status": row["status"],
            "permissions": row["permissions"] if isinstance(row["permissions"], dict) else {},
            "linked_at": row["linked_at"].isoformat() if row["linked_at"] else None,
            "activated_at": row["activated_at"].isoformat() if row["activated_at"] else None,
            "terminated_at": row["terminated_at"].isoformat() if row["terminated_at"] else None,
            "grace_until": row["grace_until"].isoformat() if row["grace_until"] else None,
            "post_termination_mode": row["post_termination_mode"],
            "updated_at": row["updated_at"].isoformat() if row["updated_at"] else None,
        },
    }


# =============================================================================
# Broker Branding & Transition Runtime
# =============================================================================


@router.get("/brokers/{broker_id}/client-setups", dependencies=[Depends(require_admin)])
async def get_broker_client_setups_admin(broker_id: UUID):
    """Get all client setups submitted by a broker (admin view)."""
    async with get_connection() as conn:
        rows = await conn.fetch(
            """
            SELECT s.id, s.status, s.contact_name, s.contact_email, s.contact_phone,
                   s.headcount_hint, s.notes, s.locations, s.onboarding_template,
                   s.preconfigured_features, s.created_at, s.updated_at,
                   c.name as company_name, c.industry, c.size as company_size,
                   c.status as company_status
            FROM broker_client_setups s
            JOIN companies c ON c.id = s.company_id
            WHERE s.broker_id = $1
            ORDER BY s.created_at DESC
            """,
            broker_id,
        )
    import json as _json
    setups = []
    for r in rows:
        locs = r.get("locations")
        if isinstance(locs, str):
            try: locs = _json.loads(locs)
            except: locs = []
        template = r.get("onboarding_template")
        if isinstance(template, str):
            try: template = _json.loads(template)
            except: template = {}
        setups.append({
            "id": str(r["id"]),
            "company_name": r["company_name"],
            "company_status": r.get("company_status"),
            "industry": r.get("industry"),
            "company_size": r.get("company_size"),
            "status": r["status"],
            "contact_name": r.get("contact_name"),
            "contact_email": r.get("contact_email"),
            "contact_phone": r.get("contact_phone"),
            "headcount": r.get("headcount_hint"),
            "notes": r.get("notes"),
            "locations": locs if isinstance(locs, list) else [],
            "specialties": (template or {}).get("specialties"),
            "created_at": r["created_at"].isoformat() if r["created_at"] else None,
        })
    return {"setups": setups, "total": len(setups)}


@router.get("/brokers/{broker_id}/branding", dependencies=[Depends(require_admin)])
async def get_broker_branding(broker_id: UUID):
    """Get broker white-label/co-brand branding configuration."""
    async with get_connection() as conn:
        row = await conn.fetchrow(
            """
            SELECT
                b.id as broker_id,
                b.name as broker_name,
                b.slug as broker_slug,
                b.support_routing,
                cfg.id,
                COALESCE(cfg.branding_mode, 'direct') as branding_mode,
                COALESCE(cfg.brand_display_name, b.name) as brand_display_name,
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
                cfg.created_at,
                cfg.updated_at
            FROM brokers b
            LEFT JOIN broker_branding_configs cfg ON cfg.broker_id = b.id
            WHERE b.id = $1
            """,
            broker_id,
        )
        if not row:
            raise HTTPException(status_code=404, detail="Broker not found")

    return {
        "broker_id": str(row["broker_id"]),
        "broker_name": row["broker_name"],
        "broker_slug": row["broker_slug"],
        "support_routing": row["support_routing"],
        "branding_mode": row["branding_mode"],
        "brand_display_name": row["brand_display_name"],
        "brand_legal_name": row["brand_legal_name"],
        "logo_url": row["logo_url"],
        "favicon_url": row["favicon_url"],
        "primary_color": row["primary_color"],
        "secondary_color": row["secondary_color"],
        "login_subdomain": row["login_subdomain"],
        "custom_login_url": row["custom_login_url"],
        "support_email": row["support_email"],
        "support_phone": row["support_phone"],
        "support_url": row["support_url"],
        "email_from_name": row["email_from_name"],
        "email_from_address": row["email_from_address"],
        "powered_by_badge": row["powered_by_badge"],
        "hide_matcha_identity": row["hide_matcha_identity"],
        "mobile_branding_enabled": row["mobile_branding_enabled"],
        "theme": row["theme"] if isinstance(row["theme"], dict) else {},
        "created_at": row["created_at"].isoformat() if row["created_at"] else None,
        "updated_at": row["updated_at"].isoformat() if row["updated_at"] else None,
    }


@router.put("/brokers/{broker_id}/branding", dependencies=[Depends(require_admin)])
async def upsert_broker_branding(
    broker_id: UUID,
    request: BrokerBrandingRequest,
    current_user=Depends(require_admin),
):
    """Upsert broker branding/runtime config for co-branded or white-label delivery."""
    _validate_broker_enums(branding_mode=request.branding_mode)
    if request.login_subdomain and not re.fullmatch(r"[a-z0-9-]{2,120}", request.login_subdomain):
        raise HTTPException(status_code=400, detail="login_subdomain must be 2-120 chars [a-z0-9-]")
    if request.custom_login_url and not request.custom_login_url.startswith(("http://", "https://")):
        raise HTTPException(status_code=400, detail="custom_login_url must start with http:// or https://")

    async with get_connection() as conn:
        broker = await conn.fetchrow("SELECT id, name, slug, support_routing FROM brokers WHERE id = $1", broker_id)
        if not broker:
            raise HTTPException(status_code=404, detail="Broker not found")

        row = await conn.fetchrow(
            """
            INSERT INTO broker_branding_configs (
                broker_id, branding_mode, brand_display_name, brand_legal_name, logo_url, favicon_url,
                primary_color, secondary_color, login_subdomain, custom_login_url,
                support_email, support_phone, support_url,
                email_from_name, email_from_address,
                powered_by_badge, hide_matcha_identity, mobile_branding_enabled,
                theme, metadata, created_by, updated_by, updated_at
            )
            VALUES (
                $1, $2, $3, $4, $5, $6,
                $7, $8, $9, $10,
                $11, $12, $13,
                $14, $15,
                $16, $17, $18,
                $19::jsonb, $20::jsonb, $21, $21, NOW()
            )
            ON CONFLICT (broker_id)
            DO UPDATE SET
                branding_mode = EXCLUDED.branding_mode,
                brand_display_name = EXCLUDED.brand_display_name,
                brand_legal_name = EXCLUDED.brand_legal_name,
                logo_url = EXCLUDED.logo_url,
                favicon_url = EXCLUDED.favicon_url,
                primary_color = EXCLUDED.primary_color,
                secondary_color = EXCLUDED.secondary_color,
                login_subdomain = EXCLUDED.login_subdomain,
                custom_login_url = EXCLUDED.custom_login_url,
                support_email = EXCLUDED.support_email,
                support_phone = EXCLUDED.support_phone,
                support_url = EXCLUDED.support_url,
                email_from_name = EXCLUDED.email_from_name,
                email_from_address = EXCLUDED.email_from_address,
                powered_by_badge = EXCLUDED.powered_by_badge,
                hide_matcha_identity = EXCLUDED.hide_matcha_identity,
                mobile_branding_enabled = EXCLUDED.mobile_branding_enabled,
                theme = EXCLUDED.theme,
                metadata = EXCLUDED.metadata,
                updated_by = EXCLUDED.updated_by,
                updated_at = NOW()
            RETURNING *
            """,
            broker_id,
            request.branding_mode,
            request.brand_display_name,
            request.brand_legal_name,
            request.logo_url,
            request.favicon_url,
            request.primary_color,
            request.secondary_color,
            request.login_subdomain,
            request.custom_login_url,
            request.support_email,
            request.support_phone,
            request.support_url,
            request.email_from_name,
            request.email_from_address,
            request.powered_by_badge,
            request.hide_matcha_identity,
            request.mobile_branding_enabled,
            json.dumps(request.theme or {}),
            json.dumps(request.metadata or {}),
            current_user.id,
        )

    return {
        "status": "saved",
        "branding": {
            "id": str(row["id"]),
            "broker_id": str(row["broker_id"]),
            "branding_mode": row["branding_mode"],
            "brand_display_name": row["brand_display_name"],
            "brand_legal_name": row["brand_legal_name"],
            "logo_url": row["logo_url"],
            "favicon_url": row["favicon_url"],
            "primary_color": row["primary_color"],
            "secondary_color": row["secondary_color"],
            "login_subdomain": row["login_subdomain"],
            "custom_login_url": row["custom_login_url"],
            "support_email": row["support_email"],
            "support_phone": row["support_phone"],
            "support_url": row["support_url"],
            "email_from_name": row["email_from_name"],
            "email_from_address": row["email_from_address"],
            "powered_by_badge": row["powered_by_badge"],
            "hide_matcha_identity": row["hide_matcha_identity"],
            "mobile_branding_enabled": row["mobile_branding_enabled"],
            "theme": row["theme"] if isinstance(row["theme"], dict) else {},
            "created_at": row["created_at"].isoformat() if row["created_at"] else None,
            "updated_at": row["updated_at"].isoformat() if row["updated_at"] else None,
        },
    }


@router.get("/brokers/{broker_id}/companies/{company_id}/transitions", dependencies=[Depends(require_admin)])
async def list_broker_company_transitions(broker_id: UUID, company_id: UUID):
    """List offboarding/transfer transitions for a broker-company relationship."""
    async with get_connection() as conn:
        exists = await conn.fetchval(
            "SELECT EXISTS(SELECT 1 FROM broker_company_links WHERE broker_id = $1 AND company_id = $2)",
            broker_id,
            company_id,
        )
        if not exists:
            raise HTTPException(status_code=404, detail="Broker-company link not found")

        rows = await conn.fetch(
            """
            SELECT
                t.id, t.mode, t.status, t.transfer_target_broker_id, tb.name as transfer_target_broker_name,
                t.grace_until, t.matcha_managed_until,
                t.data_handoff_status, t.data_handoff_notes,
                t.started_at, t.completed_at, t.metadata, t.created_at, t.updated_at
            FROM broker_company_transitions t
            LEFT JOIN brokers tb ON tb.id = t.transfer_target_broker_id
            WHERE t.broker_id = $1 AND t.company_id = $2
            ORDER BY t.created_at DESC
            """,
            broker_id,
            company_id,
        )

    return {
        "transitions": [
            {
                "id": str(row["id"]),
                "mode": row["mode"],
                "status": row["status"],
                "transfer_target_broker_id": str(row["transfer_target_broker_id"]) if row["transfer_target_broker_id"] else None,
                "transfer_target_broker_name": row["transfer_target_broker_name"],
                "grace_until": row["grace_until"].isoformat() if row["grace_until"] else None,
                "matcha_managed_until": row["matcha_managed_until"].isoformat() if row["matcha_managed_until"] else None,
                "data_handoff_status": row["data_handoff_status"],
                "data_handoff_notes": row["data_handoff_notes"],
                "started_at": row["started_at"].isoformat() if row["started_at"] else None,
                "completed_at": row["completed_at"].isoformat() if row["completed_at"] else None,
                "metadata": row["metadata"] if isinstance(row["metadata"], dict) else {},
                "created_at": row["created_at"].isoformat() if row["created_at"] else None,
                "updated_at": row["updated_at"].isoformat() if row["updated_at"] else None,
            }
            for row in rows
        ],
        "total": len(rows),
    }


@router.post("/brokers/{broker_id}/companies/{company_id}/transitions", dependencies=[Depends(require_admin)])
async def create_broker_company_transition(
    broker_id: UUID,
    company_id: UUID,
    request: BrokerCompanyTransitionRequest,
    current_user=Depends(require_admin),
):
    """Create a broker-company transition (convert/transfer/sunset/matcha-managed)."""
    _validate_broker_enums(
        post_termination_mode=request.mode,
        transition_status=request.status,
        data_handoff_status=request.data_handoff_status,
    )
    if request.transfer_target_broker_id and request.mode != "transfer_to_broker":
        raise HTTPException(status_code=400, detail="transfer_target_broker_id is only valid for transfer_to_broker mode")
    if request.mode == "transfer_to_broker" and not request.transfer_target_broker_id:
        raise HTTPException(status_code=400, detail="transfer_target_broker_id is required for transfer_to_broker mode")
    if request.mode == "matcha_managed" and request.matcha_managed_until is None:
        raise HTTPException(status_code=400, detail="matcha_managed_until is required for matcha_managed mode")

    async with get_connection() as conn:
        async with conn.transaction():
            link = await conn.fetchrow(
                """
                SELECT id, status, metadata
                FROM broker_company_links
                WHERE broker_id = $1 AND company_id = $2
                FOR UPDATE
                """,
                broker_id,
                company_id,
            )
            if not link:
                raise HTTPException(status_code=404, detail="Broker-company link not found")

            active_transition = await conn.fetchval(
                """
                SELECT id
                FROM broker_company_transitions
                WHERE broker_id = $1
                  AND company_id = $2
                  AND status IN ('planned', 'in_progress')
                """,
                broker_id,
                company_id,
            )
            if active_transition:
                raise HTTPException(status_code=409, detail="An active transition already exists for this broker-company link")

            if request.transfer_target_broker_id:
                if request.transfer_target_broker_id == broker_id:
                    raise HTTPException(status_code=400, detail="transfer_target_broker_id must be different from broker_id")
                target_exists = await conn.fetchval(
                    "SELECT EXISTS(SELECT 1 FROM brokers WHERE id = $1)",
                    request.transfer_target_broker_id,
                )
                if not target_exists:
                    raise HTTPException(status_code=404, detail="Transfer target broker not found")

            data_handoff_status = request.data_handoff_status
            if request.mode == "sunset" and data_handoff_status == "pending":
                data_handoff_status = "not_required"
            _validate_broker_enums(data_handoff_status=data_handoff_status)

            started_at = datetime.utcnow() if request.status in {"in_progress", "completed"} else None
            completed_at = datetime.utcnow() if request.status == "completed" else None

            transition = await conn.fetchrow(
                """
                INSERT INTO broker_company_transitions (
                    broker_id, company_id, source_link_id, mode, status,
                    transfer_target_broker_id, grace_until, matcha_managed_until,
                    data_handoff_status, data_handoff_notes,
                    started_at, completed_at, metadata, created_by, updated_by, updated_at
                )
                VALUES (
                    $1, $2, $3, $4, $5,
                    $6, $7, $8,
                    $9, $10,
                    $11, $12, $13::jsonb, $14, $14, NOW()
                )
                RETURNING *
                """,
                broker_id,
                company_id,
                link["id"],
                request.mode,
                request.status,
                request.transfer_target_broker_id,
                request.grace_until,
                request.matcha_managed_until,
                data_handoff_status,
                request.data_handoff_notes,
                started_at,
                completed_at,
                json.dumps(request.metadata or {}),
                current_user.id,
            )

            transition_state = _transition_state_for(request.mode, request.status)
            next_link_status = _link_status_for(request.mode, request.status, link["status"])
            _validate_broker_enums(link_status=next_link_status, link_transition_state=transition_state)

            link_metadata_patch = {
                "transition_id": str(transition["id"]),
                "transition_mode": request.mode,
            }
            if request.transfer_target_broker_id:
                link_metadata_patch["transfer_target_broker_id"] = str(request.transfer_target_broker_id)
            if request.matcha_managed_until:
                link_metadata_patch["matcha_managed_until"] = request.matcha_managed_until.isoformat()

            terminated_at = (
                datetime.utcnow()
                if request.status == "completed" and request.mode in {"convert_to_direct", "transfer_to_broker", "sunset"}
                else None
            )
            post_termination_mode = request.mode if request.status != "cancelled" else None

            link_row = await conn.fetchrow(
                """
                UPDATE broker_company_links
                SET status = $3,
                    post_termination_mode = $4,
                    grace_until = COALESCE($5, broker_company_links.grace_until),
                    transition_state = $6,
                    transition_updated_at = NOW(),
                    data_handoff_status = $7,
                    data_handoff_notes = $8,
                    current_transition_id = $9,
                    terminated_at = CASE WHEN $10::timestamptz IS NOT NULL THEN $10 ELSE broker_company_links.terminated_at END,
                    metadata = COALESCE(broker_company_links.metadata, '{}'::jsonb) || $11::jsonb,
                    updated_at = NOW()
                WHERE broker_id = $1 AND company_id = $2
                RETURNING id, broker_id, company_id, status, transition_state, post_termination_mode, current_transition_id,
                          data_handoff_status, data_handoff_notes, grace_until, terminated_at, updated_at
                """,
                broker_id,
                company_id,
                next_link_status,
                post_termination_mode,
                request.grace_until,
                transition_state,
                data_handoff_status,
                request.data_handoff_notes,
                transition["id"],
                terminated_at,
                json.dumps(link_metadata_patch),
            )

    return {
        "status": "created",
        "transition": {
            "id": str(transition["id"]),
            "mode": transition["mode"],
            "status": transition["status"],
            "transfer_target_broker_id": str(transition["transfer_target_broker_id"]) if transition["transfer_target_broker_id"] else None,
            "grace_until": transition["grace_until"].isoformat() if transition["grace_until"] else None,
            "matcha_managed_until": transition["matcha_managed_until"].isoformat() if transition["matcha_managed_until"] else None,
            "data_handoff_status": transition["data_handoff_status"],
            "data_handoff_notes": transition["data_handoff_notes"],
            "started_at": transition["started_at"].isoformat() if transition["started_at"] else None,
            "completed_at": transition["completed_at"].isoformat() if transition["completed_at"] else None,
            "metadata": transition["metadata"] if isinstance(transition["metadata"], dict) else {},
            "created_at": transition["created_at"].isoformat() if transition["created_at"] else None,
            "updated_at": transition["updated_at"].isoformat() if transition["updated_at"] else None,
        },
        "link": {
            "id": str(link_row["id"]),
            "broker_id": str(link_row["broker_id"]),
            "company_id": str(link_row["company_id"]),
            "status": link_row["status"],
            "transition_state": link_row["transition_state"],
            "post_termination_mode": link_row["post_termination_mode"],
            "current_transition_id": str(link_row["current_transition_id"]) if link_row["current_transition_id"] else None,
            "data_handoff_status": link_row["data_handoff_status"],
            "data_handoff_notes": link_row["data_handoff_notes"],
            "grace_until": link_row["grace_until"].isoformat() if link_row["grace_until"] else None,
            "terminated_at": link_row["terminated_at"].isoformat() if link_row["terminated_at"] else None,
            "updated_at": link_row["updated_at"].isoformat() if link_row["updated_at"] else None,
        },
    }


@router.patch("/brokers/{broker_id}/companies/{company_id}/transitions/{transition_id}", dependencies=[Depends(require_admin)])
async def update_broker_company_transition(
    broker_id: UUID,
    company_id: UUID,
    transition_id: UUID,
    request: BrokerCompanyTransitionUpdateRequest,
    current_user=Depends(require_admin),
):
    """Update transition status, handoff progress, or completion markers."""
    _validate_broker_enums(
        transition_status=request.status,
        data_handoff_status=request.data_handoff_status,
    )

    async with get_connection() as conn:
        async with conn.transaction():
            transition = await conn.fetchrow(
                """
                SELECT *
                FROM broker_company_transitions
                WHERE id = $1 AND broker_id = $2 AND company_id = $3
                FOR UPDATE
                """,
                transition_id,
                broker_id,
                company_id,
            )
            if not transition:
                raise HTTPException(status_code=404, detail="Transition not found")

            link = await conn.fetchrow(
                """
                SELECT id, status
                FROM broker_company_links
                WHERE broker_id = $1 AND company_id = $2
                FOR UPDATE
                """,
                broker_id,
                company_id,
            )
            if not link:
                raise HTTPException(status_code=404, detail="Broker-company link not found")

            updated_status = request.status or transition["status"]
            updated_grace_until = request.grace_until if request.grace_until is not None else transition["grace_until"]
            updated_matcha_managed_until = (
                request.matcha_managed_until
                if request.matcha_managed_until is not None
                else transition["matcha_managed_until"]
            )
            updated_data_handoff_status = request.data_handoff_status or transition["data_handoff_status"]
            updated_data_handoff_notes = (
                request.data_handoff_notes
                if request.data_handoff_notes is not None
                else transition["data_handoff_notes"]
            )

            _validate_broker_enums(
                transition_status=updated_status,
                data_handoff_status=updated_data_handoff_status,
            )
            if transition["mode"] == "matcha_managed" and updated_matcha_managed_until is None:
                raise HTTPException(status_code=400, detail="matcha_managed_until is required for matcha_managed transitions")

            started_at = transition["started_at"]
            if updated_status in {"in_progress", "completed"} and started_at is None:
                started_at = datetime.utcnow()

            completed_at = transition["completed_at"]
            if updated_status == "completed":
                completed_at = request.completed_at or datetime.utcnow()
            elif request.completed_at is not None:
                completed_at = request.completed_at

            metadata_update = request.metadata if request.metadata is not None else {}
            transition_row = await conn.fetchrow(
                """
                UPDATE broker_company_transitions
                SET status = $1,
                    grace_until = $2,
                    matcha_managed_until = $3,
                    data_handoff_status = $4,
                    data_handoff_notes = $5,
                    started_at = $6,
                    completed_at = $7,
                    metadata = COALESCE(broker_company_transitions.metadata, '{}'::jsonb) || $8::jsonb,
                    updated_by = $9,
                    updated_at = NOW()
                WHERE id = $10
                RETURNING *
                """,
                updated_status,
                updated_grace_until,
                updated_matcha_managed_until,
                updated_data_handoff_status,
                updated_data_handoff_notes,
                started_at,
                completed_at,
                json.dumps(metadata_update),
                current_user.id,
                transition_id,
            )

            transition_state = _transition_state_for(transition_row["mode"], transition_row["status"])
            next_link_status = _link_status_for(transition_row["mode"], transition_row["status"], link["status"])
            _validate_broker_enums(link_status=next_link_status, link_transition_state=transition_state)

            terminated_at = (
                datetime.utcnow()
                if transition_row["status"] == "completed" and transition_row["mode"] in {"convert_to_direct", "transfer_to_broker", "sunset"}
                else None
            )
            clear_terminated = transition_row["status"] == "cancelled"
            post_termination_mode = transition_row["mode"] if transition_row["status"] != "cancelled" else None
            current_transition_id = transition_row["id"] if transition_row["status"] != "cancelled" else None

            link_metadata_patch = {
                "transition_id": str(transition_row["id"]),
                "transition_mode": transition_row["mode"],
                "transition_status": transition_row["status"],
            }
            if transition_row["transfer_target_broker_id"]:
                link_metadata_patch["transfer_target_broker_id"] = str(transition_row["transfer_target_broker_id"])
            if transition_row["matcha_managed_until"]:
                link_metadata_patch["matcha_managed_until"] = transition_row["matcha_managed_until"].isoformat()

            link_row = await conn.fetchrow(
                """
                UPDATE broker_company_links
                SET status = $3,
                    post_termination_mode = $4,
                    grace_until = COALESCE($5, broker_company_links.grace_until),
                    transition_state = $6,
                    transition_updated_at = NOW(),
                    data_handoff_status = $7,
                    data_handoff_notes = $8,
                    current_transition_id = $9,
                    terminated_at = CASE
                        WHEN $10::timestamptz IS NOT NULL THEN $10
                        WHEN $11::boolean THEN NULL
                        ELSE broker_company_links.terminated_at
                    END,
                    metadata = COALESCE(broker_company_links.metadata, '{}'::jsonb) || $12::jsonb,
                    updated_at = NOW()
                WHERE broker_id = $1 AND company_id = $2
                RETURNING id, broker_id, company_id, status, transition_state, post_termination_mode, current_transition_id,
                          data_handoff_status, data_handoff_notes, grace_until, terminated_at, updated_at
                """,
                broker_id,
                company_id,
                next_link_status,
                post_termination_mode,
                transition_row["grace_until"],
                transition_state,
                transition_row["data_handoff_status"],
                transition_row["data_handoff_notes"],
                current_transition_id,
                terminated_at,
                clear_terminated,
                json.dumps(link_metadata_patch),
            )

    return {
        "status": "updated",
        "transition": {
            "id": str(transition_row["id"]),
            "mode": transition_row["mode"],
            "status": transition_row["status"],
            "transfer_target_broker_id": str(transition_row["transfer_target_broker_id"]) if transition_row["transfer_target_broker_id"] else None,
            "grace_until": transition_row["grace_until"].isoformat() if transition_row["grace_until"] else None,
            "matcha_managed_until": transition_row["matcha_managed_until"].isoformat() if transition_row["matcha_managed_until"] else None,
            "data_handoff_status": transition_row["data_handoff_status"],
            "data_handoff_notes": transition_row["data_handoff_notes"],
            "started_at": transition_row["started_at"].isoformat() if transition_row["started_at"] else None,
            "completed_at": transition_row["completed_at"].isoformat() if transition_row["completed_at"] else None,
            "metadata": transition_row["metadata"] if isinstance(transition_row["metadata"], dict) else {},
            "updated_at": transition_row["updated_at"].isoformat() if transition_row["updated_at"] else None,
        },
        "link": {
            "id": str(link_row["id"]),
            "broker_id": str(link_row["broker_id"]),
            "company_id": str(link_row["company_id"]),
            "status": link_row["status"],
            "transition_state": link_row["transition_state"],
            "post_termination_mode": link_row["post_termination_mode"],
            "current_transition_id": str(link_row["current_transition_id"]) if link_row["current_transition_id"] else None,
            "data_handoff_status": link_row["data_handoff_status"],
            "data_handoff_notes": link_row["data_handoff_notes"],
            "grace_until": link_row["grace_until"].isoformat() if link_row["grace_until"] else None,
            "terminated_at": link_row["terminated_at"].isoformat() if link_row["terminated_at"] else None,
            "updated_at": link_row["updated_at"].isoformat() if link_row["updated_at"] else None,
        },
    }


# =============================================================================
# Jurisdiction Repository
# =============================================================================

class JurisdictionCreateRequest(BaseModel):
    """Request model for creating/upserting a jurisdiction."""
    city: str = Field(..., min_length=1, max_length=100)
    state: str = Field(..., min_length=2, max_length=2)
    county: Optional[str] = Field(None, max_length=100)
    parent_id: Optional[UUID] = None


def _normalize_city_input(city: str) -> str:
    normalized = city.lower().strip()
    normalized = normalized.replace(".", "")
    normalized = re.sub(r"\s+", " ", normalized)
    return normalized


def _is_non_city_jurisdiction(city: Optional[str]) -> bool:
    token = (city or "").strip().lower()
    return token == "" or token.startswith("_county_")


def _city_display(city: str) -> str:
    return " ".join(part.capitalize() for part in city.split())


def _canonicalize_city_fallback(city: str, state: str) -> str:
    state_key = state.upper().strip()[:2]
    city_key = _normalize_city_input(city)
    city_key = FALLBACK_CITY_ALIASES.get((state_key, city_key), city_key)

    allowed = FALLBACK_ALLOWED_CITIES_BY_STATE.get(state_key, set())
    if city_key in allowed:
        return city_key

    suggestion = None
    if allowed:
        suggestion_match = difflib.get_close_matches(city_key, sorted(allowed), n=1, cutoff=0.72)
        suggestion = suggestion_match[0] if suggestion_match else None

    suggestion_msg = f" Did you mean '{_city_display(suggestion)}'?" if suggestion else ""
    raise HTTPException(
        status_code=status.HTTP_400_BAD_REQUEST,
        detail=(
            f"Unsupported city '{city.strip()}' for state {state_key}."
            f"{suggestion_msg}"
        ),
    )


async def _canonicalize_city_from_reference(conn: asyncpg.Connection, city: str, state: str) -> str:
    state_key = state.upper().strip()[:2]
    city_key = _normalize_city_input(city)
    city_key = FALLBACK_CITY_ALIASES.get((state_key, city_key), city_key)

    match = await conn.fetchrow(
        """
        SELECT city
        FROM jurisdiction_reference
        WHERE state = $2
          AND (
            city = $1
            OR EXISTS (
              SELECT 1
              FROM unnest(COALESCE(aliases, ARRAY[]::text[])) AS alias
              WHERE LOWER(alias) = $1
            )
          )
        LIMIT 1
        """,
        city_key,
        state_key,
    )
    if match:
        return match["city"]

    candidates = await conn.fetch(
        "SELECT city FROM jurisdiction_reference WHERE state = $1 ORDER BY city",
        state_key,
    )
    candidate_cities = [row["city"] for row in candidates]
    suggestion = None
    if candidate_cities:
        suggestion_match = difflib.get_close_matches(city_key, candidate_cities, n=1, cutoff=0.72)
        suggestion = suggestion_match[0] if suggestion_match else None

    suggestion_msg = f" Did you mean '{_city_display(suggestion)}'?" if suggestion else ""
    raise HTTPException(
        status_code=status.HTTP_400_BAD_REQUEST,
        detail=(
            f"Unsupported city '{city.strip()}' for state {state_key}."
            f"{suggestion_msg}"
        ),
    )


async def _canonicalize_city(conn: asyncpg.Connection, city: str, state: str) -> str:
    try:
        return await _canonicalize_city_from_reference(conn, city, state)
    except asyncpg.UndefinedTableError:
        return _canonicalize_city_fallback(city, state)


async def _is_supported_city(conn: asyncpg.Connection, city: str, state: str) -> bool:
    state_key = state.upper().strip()[:2]
    city_key = _normalize_city_input(city)
    city_key = FALLBACK_CITY_ALIASES.get((state_key, city_key), city_key)

    try:
        exists = await conn.fetchval(
            """
            SELECT 1
            FROM jurisdiction_reference
            WHERE state = $2
              AND (
                city = $1
                OR EXISTS (
                  SELECT 1
                  FROM unnest(COALESCE(aliases, ARRAY[]::text[])) AS alias
                  WHERE LOWER(alias) = $1
                )
              )
            LIMIT 1
            """,
            city_key,
            state_key,
        )
        return bool(exists)
    except asyncpg.UndefinedTableError:
        return city_key in FALLBACK_ALLOWED_CITIES_BY_STATE.get(state_key, set())


@router.post("/jurisdictions", dependencies=[Depends(require_admin)])
async def create_jurisdiction(request: JurisdictionCreateRequest):
    """Create or upsert a jurisdiction. Idempotent on (city, state)."""
    raw_city = request.city.strip()
    state = request.state.upper().strip()[:2]
    county = request.county.strip() if request.county else None

    if not raw_city or not state:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="City and state are required")

    async with get_connection() as conn:
        city = await _canonicalize_city(conn, raw_city, state)

        if not county:
            try:
                county_from_ref = await conn.fetchval(
                    "SELECT county FROM jurisdiction_reference WHERE city = $1 AND state = $2",
                    city,
                    state,
                )
                if county_from_ref:
                    county = county_from_ref
            except asyncpg.UndefinedTableError:
                pass

        # Validate parent_id if provided
        if request.parent_id is not None:
            parent = await conn.fetchrow("SELECT id FROM jurisdictions WHERE id = $1", request.parent_id)
            if not parent:
                raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Parent jurisdiction not found")

            # Reject self-reference before upserting to avoid mutating existing data
            existing = await conn.fetchrow(
                "SELECT id FROM jurisdictions WHERE city = $1 AND state = $2", city, state
            )
            if existing and existing["id"] == request.parent_id:
                raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="A jurisdiction cannot be its own parent")

        # Use a savepoint so the upsert is rolled back if anything goes wrong,
        # preventing partial mutations on error.
        tr = conn.transaction()
        await tr.start()
        try:
            display_name = f"{raw_city.strip()}, {state}" if city else state
            row = await conn.fetchrow("""
                INSERT INTO jurisdictions (city, state, county, parent_id, display_name)
                VALUES ($1, $2, $3, $4, $5)
                ON CONFLICT (COALESCE(city, ''), state) DO UPDATE SET
                    parent_id = COALESCE(EXCLUDED.parent_id, jurisdictions.parent_id),
                    county = COALESCE(EXCLUDED.county, jurisdictions.county)
                RETURNING *
            """, city, state, county, request.parent_id, display_name)
            await tr.commit()
        except Exception:
            await tr.rollback()
            raise

        # Fetch parent info if set
        parent_city = None
        parent_state = None
        if row["parent_id"]:
            prow = await conn.fetchrow("SELECT city, state FROM jurisdictions WHERE id = $1", row["parent_id"])
            if prow:
                parent_city = prow["city"]
                parent_state = prow["state"]

        def fmt_date(d):
            return d.isoformat() if d else None

        redis = get_redis_cache()
        if redis:
            await cache_delete(redis, admin_jurisdictions_list_key())

        return {
            "id": str(row["id"]),
            "city": row["city"],
            "state": row["state"],
            "county": row["county"],
            "parent_id": str(row["parent_id"]) if row["parent_id"] else None,
            "parent_city": parent_city,
            "parent_state": parent_state,
            "requirement_count": row["requirement_count"] or 0,
            "legislation_count": row["legislation_count"] or 0,
            "last_verified_at": fmt_date(row["last_verified_at"]),
            "created_at": fmt_date(row["created_at"]),
        }


@router.get("/jurisdictions", dependencies=[Depends(require_admin)])
async def list_jurisdictions():
    """List all jurisdictions with requirement/legislation counts and linked locations."""
    redis = get_redis_cache()
    if redis:
        cached = await cache_get(redis, admin_jurisdictions_list_key())
        if cached is not None:
            return cached

    async with get_connection() as conn:
        all_rows = await conn.fetch("""
            SELECT
                j.id,
                j.city,
                j.state,
                j.county,
                j.parent_id,
                pj.city AS parent_city,
                pj.state AS parent_state,
                j.requirement_count,
                j.legislation_count,
                j.last_verified_at,
                j.created_at,
                COUNT(bl.id) AS location_count,
                COUNT(CASE WHEN bl.auto_check_enabled THEN 1 END) AS auto_check_count,
                (SELECT COUNT(*) FROM jurisdictions cj WHERE cj.parent_id = j.id) AS children_count
            FROM jurisdictions j
            LEFT JOIN jurisdictions pj ON pj.id = j.parent_id
            LEFT JOIN business_locations bl ON bl.jurisdiction_id = j.id AND bl.is_active = true
            GROUP BY j.id, pj.city, pj.state
            ORDER BY j.state, j.city
        """)

        # Hide state/county/system rows from the main source-of-truth listing.
        rows = [row for row in all_rows if not _is_non_city_jurisdiction(row["city"])]

        # Collapse duplicate city rows that differ only by casing/alias history.
        duplicate_groups: dict[tuple[str, str], list] = {}
        for row in rows:
            key = (row["state"], _normalize_city_input(row["city"]))
            duplicate_groups.setdefault(key, []).append(row)

        deduped_rows = []
        grouped_rows_by_primary_id: dict[UUID, list] = {}
        for group_rows in duplicate_groups.values():
            def _row_priority(r):
                last_verified_at = r["last_verified_at"]
                created_at = r["created_at"]
                return (
                    (r["requirement_count"] or 0) + (r["legislation_count"] or 0),
                    r["location_count"] or 0,
                    r["auto_check_count"] or 0,
                    1 if last_verified_at is not None else 0,
                    last_verified_at or datetime.min,
                    1 if created_at is not None else 0,
                    created_at or datetime.min,
                )

            primary = max(group_rows, key=_row_priority)
            deduped_rows.append(primary)
            grouped_rows_by_primary_id[primary["id"]] = group_rows

        jurisdiction_ids = [row["id"] for row in rows]
        parent_relationships: dict[UUID, UUID] = {
            row["id"]: row["parent_id"]
            for row in rows
            if row["parent_id"] is not None
        }

        inherits_from_parent_map: dict[UUID, bool] = {}
        if parent_relationships:
            related_jurisdiction_ids = list(set(jurisdiction_ids + list(parent_relationships.values())))

            requirement_rows = await conn.fetch(
                """
                SELECT jurisdiction_id, requirement_key, current_value, numeric_value, effective_date, expiration_date
                FROM jurisdiction_requirements
                WHERE jurisdiction_id = ANY($1::uuid[])
                """,
                related_jurisdiction_ids,
            )
            legislation_rows = await conn.fetch(
                """
                SELECT jurisdiction_id, legislation_key, current_status, expected_effective_date
                FROM jurisdiction_legislation
                WHERE jurisdiction_id = ANY($1::uuid[])
                """,
                related_jurisdiction_ids,
            )

            requirements_by_jurisdiction: dict[UUID, dict[str, tuple[str, str, str, str]]] = {}
            for req in requirement_rows:
                requirements_by_jurisdiction.setdefault(req["jurisdiction_id"], {})[req["requirement_key"]] = (
                    req["current_value"] or "",
                    str(req["numeric_value"]) if req["numeric_value"] is not None else "",
                    req["effective_date"].isoformat() if req["effective_date"] else "",
                    req["expiration_date"].isoformat() if req["expiration_date"] else "",
                )

            legislation_by_jurisdiction: dict[UUID, dict[str, tuple[str, str]]] = {}
            for leg in legislation_rows:
                legislation_by_jurisdiction.setdefault(leg["jurisdiction_id"], {})[leg["legislation_key"]] = (
                    leg["current_status"] or "",
                    leg["expected_effective_date"].isoformat() if leg["expected_effective_date"] else "",
                )

            for child_id, parent_id in parent_relationships.items():
                child_requirements = requirements_by_jurisdiction.get(child_id, {})
                parent_requirements = requirements_by_jurisdiction.get(parent_id, {})
                child_legislation = legislation_by_jurisdiction.get(child_id, {})
                parent_legislation = legislation_by_jurisdiction.get(parent_id, {})

                parent_has_content = bool(parent_requirements) or bool(parent_legislation)
                requirements_match_parent = all(
                    parent_requirements.get(req_key) == req_signature
                    for req_key, req_signature in child_requirements.items()
                )
                legislation_match_parent = all(
                    parent_legislation.get(leg_key) == leg_signature
                    for leg_key, leg_signature in child_legislation.items()
                )

                inherits_from_parent_map[child_id] = (
                    parent_has_content and requirements_match_parent and legislation_match_parent
                )

        # Batch-fetch all locations for all jurisdictions in one query (avoids N+1)
        all_locations = await conn.fetch("""
            SELECT bl.id, bl.jurisdiction_id, bl.name, bl.city, bl.state, bl.company_id,
                   c.name AS company_name, bl.auto_check_enabled, bl.auto_check_interval_days,
                   bl.next_auto_check, bl.last_compliance_check
            FROM business_locations bl
            JOIN companies c ON c.id = bl.company_id
            WHERE bl.jurisdiction_id = ANY($1::uuid[]) AND bl.is_active = true
            ORDER BY c.name, bl.name
        """, jurisdiction_ids)

        # Group locations by jurisdiction_id
        locations_by_jid: dict[UUID, list] = {}
        for loc in all_locations:
            locations_by_jid.setdefault(loc["jurisdiction_id"], []).append(loc)

        jurisdictions = []
        for row in deduped_rows:
            grouped_rows = grouped_rows_by_primary_id.get(row["id"], [row])
            grouped_ids = [r["id"] for r in grouped_rows]

            merged_locations = []
            for gid in grouped_ids:
                merged_locations.extend(locations_by_jid.get(gid, []))

            locations_by_id = {str(loc["id"]): loc for loc in merged_locations}
            locations = list(locations_by_id.values())

            requirement_count = max((r["requirement_count"] or 0) for r in grouped_rows)
            legislation_count = max((r["legislation_count"] or 0) for r in grouped_rows)
            children_count = max((r["children_count"] or 0) for r in grouped_rows)

            parent_row = next((r for r in grouped_rows if r["parent_id"] is not None), row)
            parent_id = parent_row["parent_id"]
            parent_city = parent_row["parent_city"]
            parent_state = parent_row["parent_state"]

            last_verified_values = [r["last_verified_at"] for r in grouped_rows if r["last_verified_at"]]
            last_verified_at = max(last_verified_values) if last_verified_values else None
            created_values = [r["created_at"] for r in grouped_rows if r["created_at"]]
            created_at = min(created_values) if created_values else None

            inherits_from_parent = any(inherits_from_parent_map.get(r["id"], False) for r in grouped_rows)

            jurisdictions.append({
                "id": str(row["id"]),
                "city": row["city"],
                "state": row["state"],
                "county": row["county"],
                "parent_id": str(parent_id) if parent_id else None,
                "parent_city": parent_city,
                "parent_state": parent_state,
                "children_count": children_count,
                "requirement_count": requirement_count,
                "legislation_count": legislation_count,
                "location_count": len(locations),
                "auto_check_count": sum(1 for loc in locations if loc["auto_check_enabled"]),
                "inherits_from_parent": inherits_from_parent,
                "last_verified_at": last_verified_at.isoformat() if last_verified_at else None,
                "created_at": created_at.isoformat() if created_at else None,
                "locations": [
                    {
                        "id": str(loc["id"]),
                        "name": loc["name"],
                        "city": loc["city"],
                        "state": loc["state"],
                        "company_name": loc["company_name"],
                        "auto_check_enabled": loc["auto_check_enabled"],
                        "auto_check_interval_days": loc["auto_check_interval_days"],
                        "next_auto_check": loc["next_auto_check"].isoformat() if loc["next_auto_check"] else None,
                        "last_compliance_check": loc["last_compliance_check"].isoformat() if loc["last_compliance_check"] else None,
                    }
                    for loc in locations
                ],
            })

        total_requirements = sum(int(j["requirement_count"] or 0) for j in jurisdictions)
        total_legislation = sum(int(j["legislation_count"] or 0) for j in jurisdictions)

        result = {
            "jurisdictions": jurisdictions,
            "totals": {
                "total_jurisdictions": len(jurisdictions),
                "total_requirements": total_requirements,
                "total_legislation": total_legislation,
            },
        }

    if redis:
        await cache_set(redis, admin_jurisdictions_list_key(), result, ttl=600)

    return result


@router.post("/jurisdictions/cleanup-duplicates", dependencies=[Depends(require_admin)])
async def cleanup_duplicate_jurisdictions(
    dry_run: bool = Query(True),
):
    """Merge duplicate city jurisdictions by normalized city+state key."""
    async with get_connection() as conn:
        rows = await conn.fetch(
            """
            SELECT id, city, state, county, parent_id, requirement_count, legislation_count,
                   created_at, last_verified_at
            FROM jurisdictions
            ORDER BY state, city, created_at ASC
            """
        )

        city_rows = [row for row in rows if not _is_non_city_jurisdiction(row["city"])]
        grouped: dict[tuple[str, str], list] = {}
        for row in city_rows:
            key = (row["state"], _normalize_city_input(row["city"]))
            grouped.setdefault(key, []).append(row)

        duplicate_groups = [group for group in grouped.values() if len(group) > 1]
        if not duplicate_groups:
            return {
                "status": "ok",
                "dry_run": dry_run,
                "groups_found": 0,
                "groups_merged": 0,
                "duplicates_removed": 0,
                "locations_relinked": 0,
                "children_relinked": 0,
                "details": [],
            }

        def _priority(row) -> tuple:
            return (
                (row["requirement_count"] or 0) + (row["legislation_count"] or 0),
                1 if row["last_verified_at"] is not None else 0,
                row["last_verified_at"] or datetime.min,
                1 if row["created_at"] is not None else 0,
                row["created_at"] or datetime.min,
            )

        details = []
        groups_merged = 0
        duplicates_removed = 0
        locations_relinked = 0
        children_relinked = 0

        for group in duplicate_groups:
            primary = max(group, key=_priority)
            duplicates = [row for row in group if row["id"] != primary["id"]]
            details.append({
                "state": primary["state"],
                "city_key": _normalize_city_input(primary["city"]),
                "primary_id": str(primary["id"]),
                "primary_city": primary["city"],
                "duplicate_ids": [str(row["id"]) for row in duplicates],
                "duplicate_cities": [row["city"] for row in duplicates],
            })

            if dry_run:
                continue

            groups_merged += 1
            primary_parent_id = primary["parent_id"]
            primary_county = primary["county"]

            for dup in duplicates:
                # Preserve hierarchy/county metadata if missing on primary.
                if primary_parent_id is None and dup["parent_id"] is not None:
                    await conn.execute(
                        "UPDATE jurisdictions SET parent_id = $2 WHERE id = $1",
                        primary["id"],
                        dup["parent_id"],
                    )
                    primary_parent_id = dup["parent_id"]

                if not primary_county and dup["county"]:
                    await conn.execute(
                        "UPDATE jurisdictions SET county = $2 WHERE id = $1",
                        primary["id"],
                        dup["county"],
                    )
                    primary_county = dup["county"]

                dup_requirements = await conn.fetch(
                    """
                    SELECT requirement_key, category, rate_type, jurisdiction_level, jurisdiction_name,
                           title, description, current_value, numeric_value, source_url, source_name,
                           effective_date, expiration_date, previous_value, last_changed_at, last_verified_at
                    FROM jurisdiction_requirements
                    WHERE jurisdiction_id = $1
                    """,
                    dup["id"],
                )
                for req in dup_requirements:
                    await conn.execute(
                        """
                        INSERT INTO jurisdiction_requirements
                            (jurisdiction_id, requirement_key, category, rate_type, jurisdiction_level, jurisdiction_name,
                             title, description, current_value, numeric_value, source_url, source_name,
                             effective_date, expiration_date, previous_value, last_changed_at, last_verified_at)
                        VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9, $10, $11, $12, $13, $14, $15, $16, $17)
                        ON CONFLICT (jurisdiction_id, requirement_key) DO NOTHING
                        """,
                        primary["id"],
                        req["requirement_key"],
                        req["category"],
                        req["rate_type"],
                        req["jurisdiction_level"],
                        req["jurisdiction_name"],
                        req["title"],
                        req["description"],
                        req["current_value"],
                        req["numeric_value"],
                        req["source_url"],
                        req["source_name"],
                        req["effective_date"],
                        req["expiration_date"],
                        req["previous_value"],
                        req["last_changed_at"],
                        req["last_verified_at"],
                    )

                dup_legislation = await conn.fetch(
                    """
                    SELECT legislation_key, category, title, description, current_status,
                           expected_effective_date, impact_summary, source_url, source_name,
                           confidence, last_verified_at
                    FROM jurisdiction_legislation
                    WHERE jurisdiction_id = $1
                    """,
                    dup["id"],
                )
                for leg in dup_legislation:
                    await conn.execute(
                        """
                        INSERT INTO jurisdiction_legislation
                            (jurisdiction_id, legislation_key, category, title, description, current_status,
                             expected_effective_date, impact_summary, source_url, source_name, confidence, last_verified_at)
                        VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9, $10, $11, $12)
                        ON CONFLICT (jurisdiction_id, legislation_key) DO NOTHING
                        """,
                        primary["id"],
                        leg["legislation_key"],
                        leg["category"],
                        leg["title"],
                        leg["description"],
                        leg["current_status"],
                        leg["expected_effective_date"],
                        leg["impact_summary"],
                        leg["source_url"],
                        leg["source_name"],
                        leg["confidence"],
                        leg["last_verified_at"],
                    )

                moved_locations = await conn.fetchval(
                    """
                    WITH moved AS (
                        UPDATE business_locations
                        SET jurisdiction_id = $1
                        WHERE jurisdiction_id = $2
                        RETURNING id
                    )
                    SELECT COUNT(*) FROM moved
                    """,
                    primary["id"],
                    dup["id"],
                )
                locations_relinked += int(moved_locations or 0)

                moved_children = await conn.fetchval(
                    """
                    WITH moved AS (
                        UPDATE jurisdictions
                        SET parent_id = $1
                        WHERE parent_id = $2
                        RETURNING id
                    )
                    SELECT COUNT(*) FROM moved
                    """,
                    primary["id"],
                    dup["id"],
                )
                children_relinked += int(moved_children or 0)

                await conn.execute("DELETE FROM jurisdiction_requirements WHERE jurisdiction_id = $1", dup["id"])
                await conn.execute("DELETE FROM jurisdiction_legislation WHERE jurisdiction_id = $1", dup["id"])
                await conn.execute("DELETE FROM jurisdictions WHERE id = $1", dup["id"])
                duplicates_removed += 1

            requirement_count = await conn.fetchval(
                "SELECT COUNT(*) FROM jurisdiction_requirements WHERE jurisdiction_id = $1",
                primary["id"],
            )
            legislation_count = await conn.fetchval(
                "SELECT COUNT(*) FROM jurisdiction_legislation WHERE jurisdiction_id = $1",
                primary["id"],
            )
            await conn.execute(
                """
                UPDATE jurisdictions
                SET requirement_count = $2, legislation_count = $3, updated_at = NOW()
                WHERE id = $1
                """,
                primary["id"],
                requirement_count,
                legislation_count,
            )

        return {
            "status": "ok",
            "dry_run": dry_run,
            "groups_found": len(duplicate_groups),
            "groups_merged": groups_merged,
            "duplicates_removed": duplicates_removed,
            "locations_relinked": locations_relinked,
            "children_relinked": children_relinked,
            "details": details,
        }


@router.post("/jurisdictions/cleanup-duplicate-requirements", dependencies=[Depends(require_admin)])
async def cleanup_duplicate_requirements(
    dry_run: bool = Query(True),
    jurisdiction_id: Optional[UUID] = Query(None, description="Scope to a single jurisdiction"),
):
    """Find and remove semantically duplicate requirements within each jurisdiction+category.

    Uses three safety layers to avoid false positives:
    1. Jaccard token overlap >= 0.7 (strict)
    2. Poison-token pairs block matches between distinct regulation types
    3. When both rows have a regulation_key prefix, they must match

    Default is dry_run=true — returns what WOULD be deleted without touching data.
    """
    import re as _re

    # Pairs of tokens that indicate DIFFERENT regulations — if one title
    # contains the first and the other contains the second, never merge.
    _POISON_PAIRS = [
        ("meal", "rest"), ("rest", "meal"),
        ("tipped", "state"), ("state", "tipped"),
        ("tipped", "general"), ("general", "tipped"),
        ("tipped", "exempt"), ("exempt", "tipped"),
        ("sick", "family"), ("family", "sick"),
        ("sick", "prenatal"), ("prenatal", "sick"),
        ("sick", "disability"), ("disability", "sick"),
        ("sick", "bereavement"), ("bereavement", "sick"),
        ("family", "disability"), ("disability", "family"),
        ("family", "pregnancy"), ("pregnancy", "family"),
        ("family", "bereavement"), ("bereavement", "family"),
        ("termination", "resignation"), ("resignation", "termination"),
        ("termination", "layoff"), ("layoff", "termination"),
        ("resignation", "layoff"), ("layoff", "resignation"),
        ("daily", "weekly"), ("weekly", "daily"),
        ("minimum", "exempt"), ("exempt", "minimum"),
        ("large", "small"), ("small", "large"),
        ("meal", "lactation"), ("lactation", "meal"),
        ("rest", "lactation"), ("lactation", "rest"),
        ("14", "16"), ("16", "14"),
        ("hourly", "salary"), ("salary", "hourly"),
        ("contractor", "private"), ("private", "contractor"),
        ("religion", "disability"), ("disability", "religion"),
    ]
    _POISON_SET = set(_POISON_PAIRS)

    def _title_tokens(title: str) -> set:
        s = title.lower().strip()
        # Remove parentheses but KEEP their content (age groups, employer sizes live here)
        s = s.replace("(", " ").replace(")", " ")
        s = _re.sub(r"\bcalifornia\b|\bnew york\b|\btexas\b|\bflorida\b|\billinois\b|\bchicago\b", " ", s)
        s = _re.sub(r"\bca\b|\bny\b|\btx\b|\bfl\b|\bil\b", " ", s)
        s = _re.sub(r"\bstate\b|\bcity\b|\bcounty\b|\bfederal\b|\bbaseline\b|\bgeneral\b", " ", s)
        s = _re.sub(r"\brequirements?\b|\bregulations?\b|\blaws?\b|\brules?\b|\bact\b", " ", s)
        s = _re.sub(r"[^a-z0-9]+", " ", s)
        return {t for t in s.split() if len(t) > 1}

    def _jaccard(a: set, b: set) -> float:
        if not a or not b:
            return 0.0
        return len(a & b) / len(a | b)

    def _has_poison_conflict(tokens_a: set, tokens_b: set) -> bool:
        for ta in tokens_a:
            for tb in tokens_b:
                if (ta, tb) in _POISON_SET:
                    return True
        return False

    def _regulation_key_prefix(req_key: str) -> str:
        """Extract the category:regulation part, ignoring title-based suffixes."""
        # Keys look like 'leave:fmla' or 'leave:paid sick leave healthy workplaces...'
        # Canonical keys are short: 'leave:fmla', 'leave:state_paid_sick_leave'
        # Title-based keys are long with spaces: 'leave:paid sick leave ...'
        parts = req_key.split(":", 1)
        if len(parts) < 2:
            return ""
        val = parts[1].strip()
        # Title-based keys contain spaces; canonical keys use underscores only
        if " " in val:
            return ""  # title-based, no stable prefix
        return val

    def _is_match(req_a: dict, req_b: dict, tokens_a: set, tokens_b: set) -> bool:
        # Guard 1: Both have canonical regulation_key → must match exactly
        prefix_a = _regulation_key_prefix(req_a.get("requirement_key", ""))
        prefix_b = _regulation_key_prefix(req_b.get("requirement_key", ""))
        if prefix_a and prefix_b:
            return prefix_a == prefix_b

        # Guard 2: Poison token pairs → never merge
        if _has_poison_conflict(tokens_a, tokens_b):
            return False

        # Guard 3: Jaccard >= 0.7
        return _jaccard(tokens_a, tokens_b) >= 0.7

    async with get_connection() as conn:
        where_clause = "WHERE jr.status = 'active'"
        params: list = []
        if jurisdiction_id:
            where_clause += " AND jr.jurisdiction_id = $1"
            params.append(jurisdiction_id)

        rows = await conn.fetch(
            f"""
            SELECT jr.id, jr.jurisdiction_id, jr.category, jr.requirement_key,
                   jr.title, jr.applicable_industries,
                   jr.last_verified_at, jr.updated_at, jr.created_at,
                   j.display_name AS jurisdiction_name
            FROM jurisdiction_requirements jr
            JOIN jurisdictions j ON jr.jurisdiction_id = j.id
            {where_clause}
            ORDER BY jr.jurisdiction_id, jr.category, jr.last_verified_at DESC NULLS LAST
            """,
            *params,
        )

        from collections import defaultdict
        groups: dict[tuple, list] = defaultdict(list)
        for r in rows:
            groups[(r["jurisdiction_id"], r["category"])].append(dict(r))

        total_duplicates = 0
        total_groups_with_dupes = 0
        details = []

        for (jid, cat), reqs in groups.items():
            if len(reqs) < 2:
                continue

            clusters: list[list[dict]] = []
            assigned = set()

            for i, req_a in enumerate(reqs):
                if i in assigned:
                    continue
                cluster = [req_a]
                assigned.add(i)
                tokens_a = _title_tokens(req_a["title"] or "")

                for j, req_b in enumerate(reqs):
                    if j in assigned:
                        continue
                    tokens_b = _title_tokens(req_b["title"] or "")
                    if _is_match(req_a, req_b, tokens_a, tokens_b):
                        cluster.append(req_b)
                        assigned.add(j)

                if len(cluster) > 1:
                    clusters.append(cluster)

            if not clusters:
                continue

            total_groups_with_dupes += 1
            jur_name = reqs[0].get("jurisdiction_name", str(jid))

            for cluster in clusters:
                primary = cluster[0]  # sorted by last_verified_at DESC
                duplicates = cluster[1:]
                total_duplicates += len(duplicates)

                merged_industries = set()
                for r in cluster:
                    for ind in (r.get("applicable_industries") or []):
                        merged_industries.add(ind)

                details.append({
                    "jurisdiction": jur_name,
                    "category": cat,
                    "keep": {
                        "id": str(primary["id"]),
                        "title": primary["title"],
                        "requirement_key": primary["requirement_key"],
                    },
                    "remove": [
                        {
                            "id": str(d["id"]),
                            "title": d["title"],
                            "requirement_key": d["requirement_key"],
                        }
                        for d in duplicates
                    ],
                    "merged_industries": sorted(merged_industries) if merged_industries else None,
                })

                if not dry_run:
                    if merged_industries:
                        await conn.execute(
                            """UPDATE jurisdiction_requirements
                               SET applicable_industries = $2, updated_at = NOW()
                               WHERE id = $1""",
                            primary["id"],
                            sorted(merged_industries),
                        )
                    dup_ids = [d["id"] for d in duplicates]
                    await conn.execute(
                        "DELETE FROM jurisdiction_requirements WHERE id = ANY($1)",
                        dup_ids,
                    )

        if not dry_run and details:
            await conn.execute(
                """
                UPDATE jurisdictions j
                SET requirement_count = sub.cnt, updated_at = NOW()
                FROM (
                    SELECT jurisdiction_id, COUNT(*) AS cnt
                    FROM jurisdiction_requirements
                    GROUP BY jurisdiction_id
                ) sub
                WHERE j.id = sub.jurisdiction_id
                """
            )

        return {
            "status": "ok",
            "dry_run": dry_run,
            "categories_with_duplicates": total_groups_with_dupes,
            "duplicate_rows": total_duplicates,
            "clusters": len(details),
            "details": details[:200],
        }


@router.delete("/jurisdictions/{jurisdiction_id}", dependencies=[Depends(require_admin)])
async def delete_jurisdiction(jurisdiction_id: UUID):
    """Delete a jurisdiction if it has no linked business locations."""
    async with get_connection() as conn:
        jurisdiction = await conn.fetchrow(
            "SELECT id, city, state FROM jurisdictions WHERE id = $1",
            jurisdiction_id,
        )
        if not jurisdiction:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Jurisdiction not found")

        linked_location_count = await conn.fetchval(
            "SELECT COUNT(*) FROM business_locations WHERE jurisdiction_id = $1",
            jurisdiction_id,
        )
        if linked_location_count and linked_location_count > 0:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail=(
                    f"Cannot delete {jurisdiction['city']}, {jurisdiction['state']} while "
                    f"{linked_location_count} location(s) are linked."
                ),
            )

        detached_children = await conn.fetchval(
            "SELECT COUNT(*) FROM jurisdictions WHERE parent_id = $1",
            jurisdiction_id,
        )
        await conn.execute("DELETE FROM jurisdictions WHERE id = $1", jurisdiction_id)

        redis = get_redis_cache()
        if redis:
            await cache_delete(redis, admin_jurisdictions_list_key())
            await cache_delete(redis, admin_jurisdiction_detail_key(jurisdiction_id))

        return {
            "status": "deleted",
            "id": str(jurisdiction["id"]),
            "city": jurisdiction["city"],
            "state": jurisdiction["state"],
            "detached_children": int(detached_children or 0),
        }


# ── Jurisdiction Data Overview (repository dashboard) ────────────────────────

_data_overview_cache: dict | None = None
_data_overview_cached_at: float = 0.0
_DATA_OVERVIEW_CACHE_TTL = 3600  # 1 hour

REQUIRED_CATEGORIES = [
    # Labor
    "minimum_wage", "overtime", "sick_leave", "meal_breaks",
    "pay_frequency", "final_pay", "minor_work_permit", "scheduling_reporting",
    "leave", "workplace_safety", "workers_comp", "anti_discrimination",
    # Supplementary
    "business_license", "tax_rate", "posting_requirements",
    # Healthcare
    "hipaa_privacy", "billing_integrity", "clinical_safety", "healthcare_workforce",
    "corporate_integrity", "research_consent", "state_licensing", "emergency_preparedness",
    # Oncology
    "radiation_safety", "chemotherapy_handling", "tumor_registry",
    "oncology_clinical_trials", "oncology_patient_rights",
    # Medical Compliance
    "health_it", "quality_reporting", "cybersecurity", "environmental_safety",
    "pharmacy_drugs", "payer_relations", "reproductive_behavioral", "pediatric_vulnerable",
    "telehealth", "medical_devices", "transplant_organ", "antitrust",
    "tax_exempt", "language_access", "records_retention", "marketing_comms",
    "emerging_regulatory",
]


@router.get("/jurisdictions/data-overview", dependencies=[Depends(require_admin)])
async def jurisdiction_data_overview(bust: bool = False):
    """Aggregated view of the jurisdiction data repository."""
    import time

    redis = get_redis_cache()
    if not bust and redis:
        cached = await cache_get(redis, admin_jurisdiction_data_overview_key())
        if cached is not None:
            return cached

    # Legacy in-memory fallback
    global _data_overview_cache, _data_overview_cached_at
    now = time.monotonic()
    if not bust and not redis and _data_overview_cache and (now - _data_overview_cached_at) < _DATA_OVERVIEW_CACHE_TTL:
        return _data_overview_cache

    async with get_connection() as conn:
        # ── 1. All jurisdictions with their requirements ──
        rows = await conn.fetch("""
            SELECT
                j.id, j.city, j.state, j.country_code, j.last_verified_at,
                COALESCE(
                    array_agg(DISTINCT jr.category) FILTER (WHERE jr.category IS NOT NULL),
                    '{}'
                ) AS categories,
                COALESCE(
                    json_agg(json_build_object(
                        'tier', COALESCE(jr.source_tier::text, 'tier_3_aggregator'),
                        'category', jr.category,
                        'last_verified', jr.last_verified_at
                    )) FILTER (WHERE jr.id IS NOT NULL),
                    '[]'
                ) AS req_details
            FROM jurisdictions j
            LEFT JOIN jurisdiction_requirements jr ON jr.jurisdiction_id = j.id
            WHERE (j.city IS NULL OR (j.city NOT LIKE '_county_%' AND j.city <> ''))
              AND j.level != 'federal'
            GROUP BY j.id, j.city, j.state, j.country_code, j.last_verified_at
            ORDER BY j.state, j.city
        """)

        # ── 1b. Inherited categories from state + federal jurisdictions ──
        inherited_rows = await conn.fetch("""
            SELECT j.state, j.level::text AS level,
                   COALESCE(
                       array_agg(DISTINCT jr.category) FILTER (WHERE jr.category IS NOT NULL),
                       '{}'
                   ) AS categories
            FROM jurisdictions j
            LEFT JOIN jurisdiction_requirements jr ON jr.jurisdiction_id = j.id
            WHERE j.level IN ('state', 'federal')
            GROUP BY j.state, j.level
        """)

        federal_categories: set = set()
        state_categories: dict[str, set] = {}
        for irow in inherited_rows:
            cats = set(irow["categories"] or [])
            if irow["level"] == "federal":
                federal_categories |= cats
            else:
                state_categories.setdefault(irow["state"], set()).update(cats)

        # ── 2. Preemption rules ──
        try:
            preemption_rows = await conn.fetch("""
                SELECT state, category, allows_local_override, notes
                FROM state_preemption_rules
                ORDER BY state, category
            """)
        except Exception:
            preemption_rows = []

        # ── 3. Structured data sources ──
        try:
            source_rows = await conn.fetch("""
                SELECT source_name, source_type, categories, record_count,
                       last_fetched_at, last_fetch_status, is_active
                FROM structured_data_sources
                ORDER BY source_name
            """)
        except Exception:
            source_rows = []

    # ── Build state → cities map ──
    from datetime import datetime as dt, timezone
    stale_cutoff = dt.now(timezone.utc).replace(tzinfo=None) - timedelta(days=90)
    req_cats = set(REQUIRED_CATEGORIES)

    states_map: dict[str, dict] = {}
    total_cities = 0
    total_requirements = 0
    tier_counts = {1: 0, 2: 0, 3: 0}
    stale_count = 0
    freshness = {"7d": 0, "30d": 0, "90d": 0, "stale": 0}
    now_dt = dt.now(timezone.utc).replace(tzinfo=None)

    for row in rows:
        state = row["state"] or ""
        country_code = row.get("country_code", "US") or "US"
        # Group international jurisdictions by country_code to avoid mixing with US states
        state_group_key = f"{state}:{country_code}" if country_code != "US" else state
        if state_group_key not in states_map:
            states_map[state_group_key] = {"state": state, "country_code": country_code, "cities": []}

        direct_cats = set(c for c in (row["categories"] or []) if c in req_cats)
        # Only inherit from federal/state for US jurisdictions
        if country_code == "US":
            inherited = (federal_categories | state_categories.get(state, set())) & req_cats
        else:
            inherited = set()
        cats_present = sorted(direct_cats | inherited)
        cats_missing = sorted(req_cats - set(cats_present))
        req_list = json.loads(row["req_details"]) if isinstance(row["req_details"], str) else row["req_details"]

        city_tier_counts = {1: 0, 2: 0, 3: 0}
        for r in req_list:
            if r.get("category"):
                t = r.get("tier", 3)
                if t in city_tier_counts:
                    city_tier_counts[t] += 1
                    tier_counts[t] += 1
                total_requirements += 1
                # Freshness
                lv = r.get("last_verified")
                if lv:
                    if isinstance(lv, str):
                        try:
                            lv = dt.fromisoformat(lv.replace("Z", "+00:00")).replace(tzinfo=None)
                        except Exception:
                            lv = None
                    if lv:
                        age = (now_dt - lv).days
                        if age <= 7:
                            freshness["7d"] += 1
                        elif age <= 30:
                            freshness["30d"] += 1
                        elif age <= 90:
                            freshness["90d"] += 1
                        else:
                            freshness["stale"] += 1

        last_v = row["last_verified_at"]
        is_stale = last_v is not None and last_v < stale_cutoff
        if is_stale:
            stale_count += 1

        city_data = {
            "id": str(row["id"]),
            "city": row["city"],
            "country_code": row.get("country_code", "US"),
            "categories_present": sorted(cats_present),
            "categories_missing": cats_missing,
            "tier_breakdown": city_tier_counts,
            "last_verified_at": last_v.isoformat() if last_v else None,
            "is_stale": is_stale,
        }
        states_map[state_group_key]["cities"].append(city_data)
        total_cities += 1

    # Enrich state entries
    states_list = []
    for s_data in states_map.values():
        cities = s_data["cities"]
        all_cats = set()
        for c in cities:
            all_cats.update(c["categories_present"])
        s_data["city_count"] = len(cities)
        s_data["coverage_pct"] = round(len(all_cats) / len(req_cats) * 100) if req_cats else 0
        states_list.append(s_data)

    unique_states = len(states_map)
    total_req_slots = total_cities * len(req_cats)
    category_coverage_pct = round(total_requirements / total_req_slots * 100) if total_req_slots else 0
    tier_total = sum(tier_counts.values())
    tier1_pct = round(tier_counts[1] / tier_total * 100) if tier_total else 0

    # Preemption
    preemption_rules = [
        {
            "state": r["state"],
            "category": r["category"],
            "allows_local_override": r["allows_local_override"],
            "notes": r["notes"],
        }
        for r in preemption_rows
    ]

    # Structured sources
    structured_sources = [
        {
            "source_name": r["source_name"],
            "source_type": r["source_type"],
            "categories": r["categories"],
            "record_count": r["record_count"],
            "last_fetched_at": r["last_fetched_at"].isoformat() if r["last_fetched_at"] else None,
            "last_fetch_status": r["last_fetch_status"],
            "is_active": r["is_active"],
        }
        for r in source_rows
    ]

    result = {
        "summary": {
            "total_states": unique_states,
            "total_cities": total_cities,
            "total_requirements": total_requirements,
            "category_coverage_pct": category_coverage_pct,
            "tier1_pct": tier1_pct,
            "tier_breakdown": tier_counts,
            "stale_count": stale_count,
            "freshness": freshness,
            "required_categories": REQUIRED_CATEGORIES,
        },
        "states": states_list,
        "preemption_rules": preemption_rules,
        "structured_sources": structured_sources,
    }

    _data_overview_cache = result
    _data_overview_cached_at = now

    if redis:
        await cache_set(redis, admin_jurisdiction_data_overview_key(), result, ttl=3600)

    return result


# ── Category → domain mapping (mirrors CATEGORY_GROUPS in complianceCategories.ts) ──
_CATEGORY_DOMAIN: dict[str, str] = {}
for _cat in ["minimum_wage", "overtime", "sick_leave", "meal_breaks", "pay_frequency",
             "final_pay", "minor_work_permit", "scheduling_reporting", "leave",
             "workplace_safety", "workers_comp", "anti_discrimination"]:
    _CATEGORY_DOMAIN[_cat] = "labor"
for _cat in ["business_license", "tax_rate", "posting_requirements"]:
    _CATEGORY_DOMAIN[_cat] = "supplementary"
for _cat in ["hipaa_privacy", "billing_integrity", "clinical_safety", "healthcare_workforce",
             "corporate_integrity", "research_consent", "state_licensing", "emergency_preparedness"]:
    _CATEGORY_DOMAIN[_cat] = "healthcare"
for _cat in ["radiation_safety", "chemotherapy_handling", "tumor_registry",
             "oncology_clinical_trials", "oncology_patient_rights"]:
    _CATEGORY_DOMAIN[_cat] = "oncology"
for _cat in ["health_it", "quality_reporting", "cybersecurity", "environmental_safety",
             "pharmacy_drugs", "payer_relations", "reproductive_behavioral", "pediatric_vulnerable",
             "telehealth", "medical_devices", "transplant_organ", "antitrust",
             "tax_exempt", "language_access", "records_retention", "marketing_comms",
             "emerging_regulatory"]:
    _CATEGORY_DOMAIN[_cat] = "medical_compliance"
for _cat in ["process_safety", "environmental_compliance", "chemical_safety", "machine_safety",
             "industrial_hygiene", "trade_compliance", "product_safety", "labor_relations",
             "quality_systems", "supply_chain"]:
    _CATEGORY_DOMAIN[_cat] = "manufacturing"

_DOMAIN_LABELS: dict[str, str] = {
    "labor": "Labor",
    "supplementary": "Supplementary",
    "healthcare": "Healthcare",
    "oncology": "Oncology",
    "medical_compliance": "Medical Compliance",
    "manufacturing": "Manufacturing",
}

_CATEGORY_LABELS: dict[str, str] = {
    "minimum_wage": "Minimum Wage", "overtime": "Overtime", "sick_leave": "Sick Leave",
    "meal_breaks": "Meal & Rest Breaks", "pay_frequency": "Pay Frequency", "final_pay": "Final Pay",
    "minor_work_permit": "Minor Work Permits", "scheduling_reporting": "Scheduling & Reporting Time",
    "leave": "Leave", "workplace_safety": "Workplace Safety", "workers_comp": "Workers' Comp",
    "anti_discrimination": "Anti-Discrimination", "business_license": "Business License",
    "tax_rate": "Tax Rate", "posting_requirements": "Posting Requirements",
    "hipaa_privacy": "HIPAA Privacy & Security", "billing_integrity": "Billing & Financial Integrity",
    "clinical_safety": "Clinical & Patient Safety", "healthcare_workforce": "Healthcare Workforce",
    "corporate_integrity": "Corporate Integrity & Ethics", "research_consent": "Research & Informed Consent",
    "state_licensing": "State Licensing & Scope", "emergency_preparedness": "Emergency Preparedness",
    "radiation_safety": "Radiation Safety", "chemotherapy_handling": "Chemotherapy & Hazardous Drugs",
    "tumor_registry": "Tumor Registry Reporting", "oncology_clinical_trials": "Oncology Clinical Trials",
    "oncology_patient_rights": "Oncology Patient Rights", "health_it": "Health IT & Interoperability",
    "quality_reporting": "Quality Reporting", "cybersecurity": "Cybersecurity",
    "environmental_safety": "Environmental Safety", "pharmacy_drugs": "Pharmacy & Controlled Substances",
    "payer_relations": "Payer Relations", "reproductive_behavioral": "Reproductive & Behavioral Health",
    "pediatric_vulnerable": "Pediatric & Vulnerable Populations", "telehealth": "Telehealth & Digital Health",
    "medical_devices": "Medical Device Safety", "transplant_organ": "Transplant & Organ Procurement",
    "antitrust": "Healthcare Antitrust", "tax_exempt": "Tax-Exempt Compliance",
    "language_access": "Language Access & Civil Rights", "records_retention": "Records Retention",
    "marketing_comms": "Marketing & Communications", "emerging_regulatory": "Emerging Regulatory",
    "process_safety": "Process Safety Management", "environmental_compliance": "Environmental & Emissions",
    "chemical_safety": "Chemical & Hazardous Materials", "machine_safety": "Machine & Equipment Safety",
    "industrial_hygiene": "Industrial Hygiene & Exposure", "trade_compliance": "Import/Export & Trade",
    "product_safety": "Product Safety & Standards", "labor_relations": "Labor Relations",
    "quality_systems": "Quality Management Systems", "supply_chain": "Supply Chain & Procurement",
}


@router.get("/jurisdictions/policy-overview", dependencies=[Depends(require_admin)])
async def jurisdiction_policy_overview(category: Optional[str] = Query(None)):
    """Policy browser: overview by domain→category, or detail for a single category."""
    redis = get_redis_cache()
    if redis:
        cached = await cache_get(redis, admin_jurisdiction_policy_overview_key(category))
        if cached is not None:
            return cached

    async with get_connection() as conn:
        if category:
            # ── Detail mode: all requirements for one category ──
            rows = await conn.fetch("""
                SELECT jr.id, j.city, j.state, j.level AS jurisdiction_level,
                       jr.jurisdiction_name, jr.title, jr.current_value, jr.numeric_value,
                       jr.source_url, jr.source_name, jr.effective_date,
                       jr.last_verified_at,
                       COALESCE(jr.source_tier::text, 'tier_3_aggregator') AS source_tier,
                       COALESCE(jr.status::text, 'active') AS status,
                       jr.statute_citation
                FROM jurisdiction_requirements jr
                JOIN jurisdictions j ON j.id = jr.jurisdiction_id
                WHERE jr.category = $1
                ORDER BY j.state, j.city NULLS FIRST
            """, category)
            domain = _CATEGORY_DOMAIN.get(category, "unknown")
            result = {
                "category": {
                    "slug": category,
                    "name": _CATEGORY_LABELS.get(category, category),
                    "domain": domain,
                    "group": domain,
                },
                "requirements": [
                    {
                        "id": str(r["id"]),
                        "jurisdiction_name": r["jurisdiction_name"],
                        "jurisdiction_level": r["jurisdiction_level"] or "city",
                        "state": r["state"],
                        "city": r["city"],
                        "title": r["title"],
                        "current_value": r["current_value"],
                        "numeric_value": float(r["numeric_value"]) if r["numeric_value"] is not None else None,
                        "source_tier": r["source_tier"],
                        "status": r["status"],
                        "statute_citation": r.get("statute_citation"),
                        "effective_date": r["effective_date"].isoformat() if r["effective_date"] else None,
                        "last_verified_at": r["last_verified_at"].isoformat() if r["last_verified_at"] else None,
                    }
                    for r in rows
                ],
            }
            if redis:
                await cache_set(redis, admin_jurisdiction_policy_overview_key(category), result, ttl=600)
            return result

        # ── Overview mode: domain → category tree with counts ──
        cat_rows = await conn.fetch("""
            SELECT jr.category,
                   COUNT(*) AS requirement_count,
                   COUNT(DISTINCT j.id) AS jurisdiction_count,
                   COUNT(*) FILTER (WHERE COALESCE(jr.source_tier::text, 'tier_3_aggregator') = 'tier_1_government') AS tier_1,
                   COUNT(*) FILTER (WHERE COALESCE(jr.source_tier::text, 'tier_3_aggregator') = 'tier_2_official_secondary') AS tier_2,
                   COUNT(*) FILTER (WHERE COALESCE(jr.source_tier::text, 'tier_3_aggregator') = 'tier_3_aggregator') AS tier_3,
                   MAX(jr.last_verified_at) AS latest_verified
            FROM jurisdiction_requirements jr
            JOIN jurisdictions j ON j.id = jr.jurisdiction_id
            GROUP BY jr.category
            ORDER BY jr.category
        """)

        total_jurisdictions_row = await conn.fetchval(
            "SELECT COUNT(DISTINCT id) FROM jurisdictions"
        )

        # Build domain → categories structure
        domains_map: dict[str, dict] = {}
        total_requirements = 0
        cats_with_data = 0

        for r in cat_rows:
            cat = r["category"]
            domain = _CATEGORY_DOMAIN.get(cat, "unknown")
            if domain not in domains_map:
                domains_map[domain] = {
                    "domain": domain,
                    "label": _DOMAIN_LABELS.get(domain, domain.replace("_", " ").title()),
                    "category_count": 0,
                    "requirement_count": 0,
                    "categories": [],
                }
            d = domains_map[domain]
            req_count = r["requirement_count"]
            d["category_count"] += 1
            d["requirement_count"] += req_count
            total_requirements += req_count
            cats_with_data += 1
            d["categories"].append({
                "slug": cat,
                "name": _CATEGORY_LABELS.get(cat, cat),
                "group": domain,
                "requirement_count": req_count,
                "jurisdiction_count": r["jurisdiction_count"],
                "tier_breakdown": {
                    "tier_1_government": r["tier_1"],
                    "tier_2_official_secondary": r["tier_2"],
                    "tier_3_aggregator": r["tier_3"],
                },
                "latest_verified": r["latest_verified"].isoformat() if r["latest_verified"] else None,
            })

        # Sort domains by the order they appear in REQUIRED_CATEGORIES
        domain_order = list(dict.fromkeys(_CATEGORY_DOMAIN[c] for c in REQUIRED_CATEGORIES if c in _CATEGORY_DOMAIN))
        domains_list = []
        for d in domain_order:
            if d in domains_map:
                domains_list.append(domains_map[d])
        # Append any extra domains not in the ordering
        for d, val in domains_map.items():
            if d not in domain_order:
                domains_list.append(val)

        result = {
            "summary": {
                "total_requirements": total_requirements,
                "total_categories_with_data": cats_with_data,
                "total_domains": len(domains_map),
                "total_jurisdictions": total_jurisdictions_row or 0,
            },
            "domains": domains_list,
        }

    if redis:
        await cache_set(redis, admin_jurisdiction_policy_overview_key(None), result, ttl=600)

    return result


@router.get("/jurisdictions/penalty-overview", dependencies=[Depends(require_admin)])
async def get_penalty_overview():
    """Get penalty coverage overview across all categories and sample penalty data."""
    async with get_connection() as conn:
        # Coverage by category
        coverage = await conn.fetch("""
            SELECT category,
                   COUNT(*) as total,
                   SUM(CASE WHEN metadata ? 'penalties' THEN 1 ELSE 0 END) as has_penalty
            FROM jurisdiction_requirements WHERE status = 'active'
            GROUP BY category ORDER BY total DESC
        """)

        # Detailed penalty data per category (one sample per category from governing/federal)
        details = await conn.fetch("""
            SELECT DISTINCT ON (category)
                   category, title,
                   metadata->'penalties'->>'enforcing_agency' as enforcing_agency,
                   (metadata->'penalties'->>'civil_penalty_min')::text as penalty_min,
                   (metadata->'penalties'->>'civil_penalty_max')::text as penalty_max,
                   metadata->'penalties'->>'per_violation' as per_violation,
                   metadata->'penalties'->>'annual_cap' as annual_cap,
                   metadata->'penalties'->>'criminal' as criminal,
                   metadata->'penalties'->>'summary' as summary,
                   metadata->'penalties'->>'source_url' as source_url,
                   metadata->'penalties'->>'verified_date' as verified_date
            FROM jurisdiction_requirements
            WHERE status = 'active' AND metadata ? 'penalties'
            ORDER BY category, jurisdiction_level ASC
        """)

        # Requirements with highest max penalties
        top_penalties = await conn.fetch("""
            SELECT category, title, jurisdiction_name, jurisdiction_level,
                   (metadata->'penalties'->>'civil_penalty_max')::numeric as max_penalty,
                   metadata->'penalties'->>'summary' as summary,
                   metadata->'penalties'->>'enforcing_agency' as enforcing_agency
            FROM jurisdiction_requirements
            WHERE status = 'active'
              AND metadata ? 'penalties'
              AND (metadata->'penalties'->>'civil_penalty_max') IS NOT NULL
              AND (metadata->'penalties'->>'civil_penalty_max') != 'null'
            ORDER BY (metadata->'penalties'->>'civil_penalty_max')::numeric DESC
            LIMIT 20
        """)

    return {
        "coverage": [
            {
                "category": r["category"],
                "total": r["total"],
                "has_penalty": r["has_penalty"],
                "pct": round(r["has_penalty"] / r["total"] * 100) if r["total"] > 0 else 0,
            }
            for r in coverage
        ],
        "details": [
            {
                "category": r["category"],
                "title": r["title"],
                "enforcing_agency": r["enforcing_agency"],
                "penalty_min": r["penalty_min"],
                "penalty_max": r["penalty_max"],
                "per_violation": r["per_violation"],
                "annual_cap": r["annual_cap"],
                "criminal": r["criminal"],
                "summary": r["summary"],
                "source_url": r["source_url"],
                "verified_date": r["verified_date"],
            }
            for r in details
        ],
        "top_penalties": [
            {
                "category": r["category"],
                "title": r["title"],
                "jurisdiction": f"{r['jurisdiction_name']} ({r['jurisdiction_level']})",
                "max_penalty": float(r["max_penalty"]) if r["max_penalty"] else None,
                "summary": r["summary"],
                "enforcing_agency": r["enforcing_agency"],
            }
            for r in top_penalties
        ],
    }


@router.get("/jurisdictions/api-sources", dependencies=[Depends(require_admin)])
async def get_api_sources_overview():
    """Get all requirements grouped by research_source with stats."""
    async with get_connection() as conn:
        # Counts by research_source
        source_counts = await conn.fetch("""
            SELECT
                COALESCE(metadata->>'research_source', 'unknown') AS research_source,
                COUNT(*) AS total,
                COUNT(DISTINCT category) AS category_count,
                COUNT(DISTINCT jurisdiction_id) AS jurisdiction_count,
                MIN(created_at) AS earliest,
                MAX(updated_at) AS latest
            FROM jurisdiction_requirements
            GROUP BY COALESCE(metadata->>'research_source', 'unknown')
            ORDER BY total DESC
        """)

        # Recent official_api entries
        recent_api = await conn.fetch("""
            SELECT jr.id, jr.category, jr.title, jr.description, jr.current_value,
                   jr.source_name, jr.source_url,
                   jr.effective_date, jr.created_at, jr.updated_at, jr.jurisdiction_level,
                   jr.jurisdiction_name, jr.last_verified_at,
                   j.city, j.state
            FROM jurisdiction_requirements jr
            JOIN jurisdictions j ON j.id = jr.jurisdiction_id
            WHERE jr.metadata->>'research_source' = 'official_api'
            ORDER BY COALESCE(jr.updated_at, jr.created_at) DESC
            LIMIT 100
        """)

        # Category breakdown for official_api
        api_by_category = await conn.fetch("""
            SELECT category, COUNT(*) AS count
            FROM jurisdiction_requirements
            WHERE metadata->>'research_source' = 'official_api'
            GROUP BY category
            ORDER BY count DESC
        """)

        def fmt(d):
            return d.isoformat() if d else None

        return {
            "source_counts": [
                {
                    "research_source": r["research_source"],
                    "total": r["total"],
                    "category_count": r["category_count"],
                    "jurisdiction_count": r["jurisdiction_count"],
                    "earliest": fmt(r["earliest"]),
                    "latest": fmt(r["latest"]),
                }
                for r in source_counts
            ],
            "recent_api": [
                {
                    "id": str(r["id"]),
                    "category": r["category"],
                    "title": r["title"],
                    "description": r["description"],
                    "current_value": r["current_value"],
                    "source_name": r["source_name"],
                    "source_url": r["source_url"],
                    "effective_date": fmt(r["effective_date"]),
                    "created_at": fmt(r["created_at"]),
                    "updated_at": fmt(r["updated_at"]),
                    "jurisdiction_level": r["jurisdiction_level"],
                    "jurisdiction_name": r["jurisdiction_name"],
                    "last_verified_at": fmt(r["last_verified_at"]),
                    "city": r["city"],
                    "state": r["state"],
                }
                for r in recent_api
            ],
            "api_by_category": [
                {"category": r["category"], "count": r["count"]}
                for r in api_by_category
            ],
        }


@router.get("/jurisdictions/quality-audit", dependencies=[Depends(require_admin)])
async def get_quality_audit(
    state: Optional[str] = None,
    category: Optional[str] = None,
    min_completeness: Optional[int] = None,
    max_completeness: Optional[int] = None,
    stale_only: bool = False,
    tier: Optional[str] = None,
    source: Optional[str] = None,
    limit: int = 200,
    offset: int = 0,
):
    """Data quality audit: requirements with completeness scores, staleness, and provenance."""
    import hashlib

    cache_key = "admin:quality-audit:" + hashlib.md5(
        f"{state}:{category}:{min_completeness}:{max_completeness}:{stale_only}:{tier}:{source}:{limit}:{offset}".encode()
    ).hexdigest()

    redis = get_redis_cache()
    if redis:
        cached = await cache_get(redis, cache_key)
        if cached is not None:
            return cached

    async with get_connection() as conn:
        # Base WHERE conditions for paginated results
        conditions = ["jr.status = 'active'"]
        params: List[Any] = []

        if state:
            params.append(state.upper())
            conditions.append(f"j.state = ${len(params)}")
        if category:
            params.append(category)
            conditions.append(f"jr.category = ${len(params)}")
        if tier:
            params.append(tier)
            conditions.append(f"jr.source_tier::text = ${len(params)}")
        if source:
            if source == "unknown":
                conditions.append("jr.metadata->>'research_source' IS NULL")
            else:
                params.append(source)
                conditions.append(f"jr.metadata->>'research_source' = ${len(params)}")
        if stale_only:
            conditions.append("(jr.last_verified_at IS NULL OR jr.last_verified_at < NOW() - INTERVAL '90 days')")

        where_clause = " AND ".join(conditions)

        # Summary query (no limit/offset)
        summary_sql = f"""
            SELECT
                COUNT(*) AS total,
                AVG(
                    CASE WHEN jr.title IS NOT NULL AND jr.title != '' THEN 25 ELSE 0 END +
                    CASE WHEN jr.description IS NOT NULL AND jr.description != '' THEN 30 ELSE 0 END +
                    CASE WHEN jr.source_url IS NOT NULL AND jr.source_url != '' THEN 20 ELSE 0 END +
                    CASE WHEN jr.effective_date IS NOT NULL THEN 15 ELSE 0 END +
                    CASE WHEN jr.current_value IS NOT NULL AND jr.current_value != '' THEN 10 ELSE 0 END
                )::int AS avg_completeness,
                COUNT(*) FILTER (WHERE jr.last_verified_at IS NULL OR jr.last_verified_at < NOW() - INTERVAL '90 days') AS stale_count,
                COUNT(*) FILTER (WHERE jr.source_url IS NULL OR jr.source_url = '') AS missing_source_url
            FROM jurisdiction_requirements jr
            JOIN jurisdictions j ON j.id = jr.jurisdiction_id
            WHERE {where_clause}
        """
        summary_row = await conn.fetchrow(summary_sql, *params)

        tier_rows = await conn.fetch(f"""
            SELECT COALESCE(jr.source_tier::text, 'unknown') AS tier, COUNT(*) AS cnt
            FROM jurisdiction_requirements jr
            JOIN jurisdictions j ON j.id = jr.jurisdiction_id
            WHERE {where_clause}
            GROUP BY COALESCE(jr.source_tier::text, 'unknown')
        """, *params)

        provenance_rows = await conn.fetch(f"""
            SELECT COALESCE(jr.metadata->>'research_source', 'unknown') AS src, COUNT(*) AS cnt
            FROM jurisdiction_requirements jr
            JOIN jurisdictions j ON j.id = jr.jurisdiction_id
            WHERE {where_clause}
            GROUP BY COALESCE(jr.metadata->>'research_source', 'unknown')
        """, *params)

        # Completeness filter (applied after scoring, so we use a subquery)
        having_conditions: List[str] = []
        post_params = list(params)
        if min_completeness is not None:
            post_params.append(min_completeness)
            having_conditions.append(f"completeness_score >= ${len(post_params)}")
        if max_completeness is not None:
            post_params.append(max_completeness)
            having_conditions.append(f"completeness_score <= ${len(post_params)}")

        post_params.append(limit)
        limit_param = len(post_params)
        post_params.append(offset)
        offset_param = len(post_params)

        having_clause = f"WHERE {' AND '.join(having_conditions)}" if having_conditions else ""

        rows_sql = f"""
            SELECT *
            FROM (
                SELECT
                    jr.id, jr.jurisdiction_id, jr.category, jr.title, jr.description,
                    jr.source_url, jr.source_tier::text AS source_tier, jr.status::text AS status,
                    jr.current_value, jr.effective_date, jr.last_verified_at, jr.is_bookmarked,
                    jr.created_at, jr.updated_at, jr.metadata,
                    j.display_name AS jurisdiction_name, j.state, j.city,
                    (
                        CASE WHEN jr.title IS NOT NULL AND jr.title != '' THEN 25 ELSE 0 END +
                        CASE WHEN jr.description IS NOT NULL AND jr.description != '' THEN 30 ELSE 0 END +
                        CASE WHEN jr.source_url IS NOT NULL AND jr.source_url != '' THEN 20 ELSE 0 END +
                        CASE WHEN jr.effective_date IS NOT NULL THEN 15 ELSE 0 END +
                        CASE WHEN jr.current_value IS NOT NULL AND jr.current_value != '' THEN 10 ELSE 0 END
                    ) AS completeness_score,
                    EXTRACT(DAY FROM NOW() - jr.last_verified_at)::int AS staleness_days
                FROM jurisdiction_requirements jr
                JOIN jurisdictions j ON j.id = jr.jurisdiction_id
                WHERE {where_clause}
            ) scored
            {having_clause}
            ORDER BY completeness_score ASC, staleness_days DESC NULLS FIRST
            LIMIT ${limit_param} OFFSET ${offset_param}
        """
        rows = await conn.fetch(rows_sql, *post_params)

        def fmt(d):
            return d.isoformat() if d else None

        result = {
            "summary": {
                "total": summary_row["total"],
                "avg_completeness": summary_row["avg_completeness"] or 0,
                "stale_count": summary_row["stale_count"],
                "missing_source_url": summary_row["missing_source_url"],
                "tier_breakdown": {r["tier"]: r["cnt"] for r in tier_rows},
                "provenance_breakdown": {r["src"]: r["cnt"] for r in provenance_rows},
            },
            "requirements": [
                {
                    "id": str(r["id"]),
                    "jurisdiction_id": str(r["jurisdiction_id"]),
                    "category": r["category"],
                    "title": r["title"],
                    "description": r["description"],
                    "source_url": r["source_url"],
                    "source_tier": r["source_tier"],
                    "current_value": r["current_value"],
                    "effective_date": fmt(r["effective_date"]),
                    "last_verified_at": fmt(r["last_verified_at"]),
                    "is_bookmarked": r["is_bookmarked"],
                    "created_at": fmt(r["created_at"]),
                    "updated_at": fmt(r["updated_at"]),
                    "jurisdiction_name": r["jurisdiction_name"],
                    "state": r["state"],
                    "city": r["city"],
                    "completeness_score": r["completeness_score"],
                    "staleness_days": r["staleness_days"],
                    "research_source": (r["metadata"] or {}).get("research_source") if r["metadata"] else None,
                }
                for r in rows
            ],
        }

    if redis:
        await cache_set(redis, cache_key, result, ttl=300)

    return result


DOMAIN_CATEGORIES = {
    "healthcare": sorted(HEALTHCARE_CATEGORIES | ONCOLOGY_CATEGORIES | MEDICAL_COMPLIANCE_CATEGORIES),
    "hr": sorted(LABOR_CATEGORIES | SUPPLEMENTARY_CATEGORIES),
}


@router.get("/jurisdictions/coverage-matrix", dependencies=[Depends(require_admin)])
async def get_coverage_matrix(
    state: Optional[str] = None,
    domain: Optional[str] = None,
):
    """Coverage matrix: jurisdiction × category grid with tier, completeness, and staleness."""
    import hashlib

    cache_key = "admin:coverage-matrix:" + hashlib.md5(
        f"{state}:{domain}".encode()
    ).hexdigest()

    redis = get_redis_cache()
    if redis:
        cached = await cache_get(redis, cache_key)
        if cached is not None:
            return cached

    async with get_connection() as conn:
        where_conditions = ["1=1"]
        join_conditions = ["jr.jurisdiction_id = j.id", "jr.status = 'active'"]
        params: List[Any] = []

        if state:
            params.append(state.upper())
            where_conditions.append(f"j.state = ${len(params)}")

        domain_cats = DOMAIN_CATEGORIES.get(domain) if domain else None
        if domain_cats:
            params.append(domain_cats)
            join_conditions.append(f"jr.category = ANY(${len(params)})")

        where_clause = " AND ".join(where_conditions)
        join_clause = " AND ".join(join_conditions)

        rows = await conn.fetch(f"""
            SELECT
                j.id, j.display_name, j.state, j.city,
                jr.category,
                COUNT(jr.id) AS req_count,
                MAX(CASE jr.source_tier::text
                    WHEN 'tier_1_government' THEN 3
                    WHEN 'tier_2_official_secondary' THEN 2
                    WHEN 'tier_3_aggregator' THEN 1
                    ELSE 0 END) AS best_tier,
                AVG(
                    CASE WHEN jr.title IS NOT NULL AND jr.title != '' THEN 25 ELSE 0 END +
                    CASE WHEN jr.description IS NOT NULL AND jr.description != '' THEN 30 ELSE 0 END +
                    CASE WHEN jr.source_url IS NOT NULL AND jr.source_url != '' THEN 20 ELSE 0 END +
                    CASE WHEN jr.effective_date IS NOT NULL THEN 15 ELSE 0 END +
                    CASE WHEN jr.current_value IS NOT NULL AND jr.current_value != '' THEN 10 ELSE 0 END
                )::int AS avg_completeness,
                MAX(EXTRACT(DAY FROM NOW() - jr.last_verified_at))::int AS max_staleness_days
            FROM jurisdictions j
            LEFT JOIN jurisdiction_requirements jr ON {join_clause}
            WHERE {where_clause}
            GROUP BY j.id, j.display_name, j.state, j.city, jr.category
            ORDER BY j.state, j.display_name, jr.category
        """, *params)

        jurisdictions_seen: Dict[str, Any] = {}
        categories_seen: set = set(domain_cats) if domain_cats else set()
        cells: Dict[str, Any] = {}

        for r in rows:
            jid = str(r["id"])
            if jid not in jurisdictions_seen:
                jurisdictions_seen[jid] = {
                    "id": jid,
                    "name": r["display_name"],
                    "state": r["state"],
                    "city": r["city"],
                }
            cat = r["category"]
            if cat is not None:
                categories_seen.add(cat)
                cells[f"{jid}:{cat}"] = {
                    "req_count": r["req_count"],
                    "best_tier": r["best_tier"],
                    "avg_completeness": r["avg_completeness"],
                    "max_staleness_days": r["max_staleness_days"],
                }

        result = {
            "jurisdictions": list(jurisdictions_seen.values()),
            "categories": sorted(categories_seen),
            "cells": cells,
        }

    if redis:
        await cache_set(redis, cache_key, result, ttl=600)

    return result


# ── Regulation Key Integrity & Staleness ─────────────────────────────────


@router.get("/jurisdictions/integrity-check", dependencies=[Depends(require_admin)])
async def jurisdiction_integrity_check(
    jurisdiction_id: Optional[UUID] = None,
    state: Optional[str] = None,
):
    """Bidirectional integrity check: missing keys, orphaned records, stale data, partial groups."""
    async with get_connection() as conn:
        # ── 1. Missing keys: defined in registry but absent from DB ──
        jur_filter = ""
        params: list = []
        if jurisdiction_id:
            params.append(jurisdiction_id)
            jur_filter = f"AND j.id = ${len(params)}"
        elif state:
            params.append(state.upper())
            jur_filter = f"AND j.state = ${len(params)}"

        missing_rows = await conn.fetch(f"""
            SELECT
                j.id AS jurisdiction_id, j.city, j.state,
                rkd.key, rkd.category_slug, rkd.name AS key_name,
                rkd.key_group, rkd.base_weight
            FROM regulation_key_definitions rkd
            CROSS JOIN jurisdictions j
            LEFT JOIN jurisdiction_requirements jr
                ON jr.jurisdiction_id = j.id
                AND jr.category = rkd.category_slug
                AND jr.regulation_key = rkd.key
            WHERE jr.id IS NULL
              AND j.level != 'federal'
              {jur_filter}
            ORDER BY j.state, j.city, rkd.category_slug, rkd.key
            LIMIT 500
        """, *params)

        missing_keys = [
            {
                "jurisdiction_id": str(r["jurisdiction_id"]),
                "city": r["city"],
                "state": r["state"],
                "key": r["key"],
                "category": r["category_slug"],
                "key_name": r["key_name"],
                "key_group": r["key_group"],
                "weight": float(r["base_weight"]),
            }
            for r in missing_rows
        ]

        # ── 2. Orphaned records: in DB but not matching any key definition ──
        orphan_params: list = []
        orphan_filter = ""
        if jurisdiction_id:
            orphan_params.append(jurisdiction_id)
            orphan_filter = f"AND jr.jurisdiction_id = ${len(orphan_params)}"
        elif state:
            orphan_params.append(state.upper())
            orphan_filter = f"AND j.state = ${len(orphan_params)}"

        orphan_rows = await conn.fetch(f"""
            SELECT
                jr.id, jr.jurisdiction_id, j.city, j.state,
                jr.category, jr.regulation_key, jr.title,
                jr.source_tier::text AS source_tier
            FROM jurisdiction_requirements jr
            JOIN jurisdictions j ON j.id = jr.jurisdiction_id
            LEFT JOIN regulation_key_definitions rkd
                ON jr.category = rkd.category_slug
                AND jr.regulation_key = rkd.key
            WHERE rkd.id IS NULL
              AND jr.status = 'active'
              {orphan_filter}
            ORDER BY j.state, j.city, jr.category
            LIMIT 500
        """, *orphan_params)

        orphaned_records = [
            {
                "id": str(r["id"]),
                "jurisdiction_id": str(r["jurisdiction_id"]),
                "city": r["city"],
                "state": r["state"],
                "category": r["category"],
                "regulation_key": r["regulation_key"],
                "title": r["title"],
                "source_tier": r["source_tier"],
            }
            for r in orphan_rows
        ]

        # ── 3. Stale keys: past staleness thresholds ──
        stale_params: list = []
        stale_filter = ""
        if jurisdiction_id:
            stale_params.append(jurisdiction_id)
            stale_filter = f"AND jr.jurisdiction_id = ${len(stale_params)}"
        elif state:
            stale_params.append(state.upper())
            stale_filter = f"AND j.state = ${len(stale_params)}"

        stale_rows = await conn.fetch(f"""
            SELECT
                jr.id, j.city, j.state,
                jr.category, jr.regulation_key, jr.title,
                EXTRACT(DAY FROM NOW() - jr.last_verified_at)::int AS days_since_verified,
                rkd.staleness_warning_days,
                rkd.staleness_critical_days,
                rkd.staleness_expired_days,
                rkd.name AS key_name
            FROM jurisdiction_requirements jr
            JOIN jurisdictions j ON j.id = jr.jurisdiction_id
            JOIN regulation_key_definitions rkd
                ON jr.category = rkd.category_slug
                AND jr.regulation_key = rkd.key
            WHERE jr.status = 'active'
              AND EXTRACT(DAY FROM NOW() - jr.last_verified_at) > rkd.staleness_warning_days
              {stale_filter}
            ORDER BY EXTRACT(DAY FROM NOW() - jr.last_verified_at) DESC
            LIMIT 200
        """, *stale_params)

        stale_keys = []
        for r in stale_rows:
            days = r["days_since_verified"] or 0
            if days >= (r["staleness_expired_days"] or 365):
                level = "expired"
            elif days >= (r["staleness_critical_days"] or 180):
                level = "critical"
            else:
                level = "warning"
            stale_keys.append({
                "id": str(r["id"]),
                "city": r["city"],
                "state": r["state"],
                "category": r["category"],
                "regulation_key": r["regulation_key"],
                "key_name": r["key_name"],
                "days_since_verified": days,
                "staleness_level": level,
            })

        # ── 4. Partial groups: key groups with incomplete coverage ──
        group_params: list = []
        group_filter = ""
        if jurisdiction_id:
            group_params.append(jurisdiction_id)
            group_filter = f"AND j.id = ${len(group_params)}"
        elif state:
            group_params.append(state.upper())
            group_filter = f"AND j.state = ${len(group_params)}"

        group_rows = await conn.fetch(f"""
            WITH expected AS (
                SELECT rkd.key_group, rkd.category_slug, count(*) AS expected_count
                FROM regulation_key_definitions rkd
                WHERE rkd.key_group IS NOT NULL
                GROUP BY rkd.key_group, rkd.category_slug
            ),
            present AS (
                SELECT rkd.key_group, rkd.category_slug, j.id AS jurisdiction_id, j.city, j.state,
                       count(DISTINCT jr.regulation_key) AS present_count
                FROM regulation_key_definitions rkd
                CROSS JOIN jurisdictions j
                LEFT JOIN jurisdiction_requirements jr
                    ON jr.jurisdiction_id = j.id
                    AND jr.category = rkd.category_slug
                    AND jr.regulation_key = rkd.key
                    AND jr.status = 'active'
                WHERE rkd.key_group IS NOT NULL
                  AND j.level != 'federal'
                  {group_filter}
                GROUP BY rkd.key_group, rkd.category_slug, j.id, j.city, j.state
            )
            SELECT p.key_group, p.category_slug, p.city, p.state,
                   p.present_count, e.expected_count
            FROM present p
            JOIN expected e ON e.key_group = p.key_group AND e.category_slug = p.category_slug
            WHERE p.present_count > 0 AND p.present_count < e.expected_count
            ORDER BY (p.present_count::float / e.expected_count), p.key_group
            LIMIT 200
        """, *group_params)

        partial_groups = [
            {
                "key_group": r["key_group"],
                "category": r["category_slug"],
                "city": r["city"],
                "state": r["state"],
                "present": r["present_count"],
                "expected": r["expected_count"],
                "coverage_pct": round(r["present_count"] / r["expected_count"] * 100, 1),
            }
            for r in group_rows
        ]

        # ── 5. Summary counts ──
        total_defined = await conn.fetchval("SELECT count(*) FROM regulation_key_definitions")
        total_records = await conn.fetchval(
            "SELECT count(*) FROM jurisdiction_requirements WHERE status = 'active'"
        )
        linked_count = await conn.fetchval(
            "SELECT count(*) FROM jurisdiction_requirements WHERE key_definition_id IS NOT NULL AND status = 'active'"
        )

    return {
        "missing_keys": missing_keys,
        "missing_count": len(missing_rows),
        "orphaned_records": orphaned_records,
        "orphaned_count": len(orphan_rows),
        "stale_keys": stale_keys,
        "stale_count": len(stale_keys),
        "partial_groups": partial_groups,
        "partial_group_count": len(partial_groups),
        "total_defined_keys": total_defined,
        "total_db_records": total_records,
        "linked_records": linked_count,
        "integrity_score": round(
            (linked_count / total_records * 100) if total_records > 0 else 0, 1
        ),
    }


@router.post("/jurisdictions/run-staleness-check", dependencies=[Depends(require_admin)])
async def run_staleness_check(
    jurisdiction_id: Optional[UUID] = Body(None),
    state: Optional[str] = Body(None),
):
    """Run staleness scan and upsert repository_alerts. Admin-triggered, not scheduled."""
    created = 0
    resolved = 0

    async with get_connection() as conn:
        params: list = []
        jur_filter = ""
        if jurisdiction_id:
            params.append(jurisdiction_id)
            jur_filter = f"AND jr.jurisdiction_id = ${len(params)}"
        elif state:
            params.append(state.upper())
            jur_filter = f"AND j.state = ${len(params)}"

        # ── 1. Stale data detection ──
        stale_rows = await conn.fetch(f"""
            SELECT
                jr.id AS requirement_id, jr.jurisdiction_id,
                jr.category, jr.regulation_key,
                EXTRACT(DAY FROM NOW() - jr.last_verified_at)::int AS days_since_verified,
                rkd.id AS key_definition_id,
                rkd.staleness_warning_days, rkd.staleness_critical_days, rkd.staleness_expired_days,
                rkd.name AS key_name,
                j.city, j.state
            FROM jurisdiction_requirements jr
            JOIN jurisdictions j ON j.id = jr.jurisdiction_id
            JOIN regulation_key_definitions rkd
                ON jr.category = rkd.category_slug AND jr.regulation_key = rkd.key
            WHERE jr.status = 'active'
              AND EXTRACT(DAY FROM NOW() - jr.last_verified_at) > rkd.staleness_warning_days
              {jur_filter}
        """, *params)

        for r in stale_rows:
            days = r["days_since_verified"] or 0
            if days >= (r["staleness_expired_days"] or 365):
                alert_type, severity = "stale_expired", "expired"
            elif days >= (r["staleness_critical_days"] or 180):
                alert_type, severity = "stale_critical", "critical"
            else:
                alert_type, severity = "stale_warning", "warning"

            message = f"{r['key_name']} for {r['city']}, {r['state']} is {days} days past verification"
            result = await conn.execute("""
                INSERT INTO repository_alerts
                    (alert_type, severity, jurisdiction_id, key_definition_id, requirement_id,
                     category, regulation_key, message, days_overdue)
                VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9)
                ON CONFLICT (jurisdiction_id, key_definition_id, alert_type)
                    WHERE status = 'open'
                DO UPDATE SET
                    severity = EXCLUDED.severity,
                    message = EXCLUDED.message,
                    days_overdue = EXCLUDED.days_overdue
            """, alert_type, severity, r["jurisdiction_id"], r["key_definition_id"],
                r["requirement_id"], r["category"], r["regulation_key"], message,
                days - (r["staleness_warning_days"] or 90))
            if "INSERT" in result:
                created += 1

        # ── 2. Never-verified / missing data detection ──
        missing_params: list = []
        missing_filter = ""
        if jurisdiction_id:
            missing_params.append(jurisdiction_id)
            missing_filter = f"AND j.id = ${len(missing_params)}"
        elif state:
            missing_params.append(state.upper())
            missing_filter = f"AND j.state = ${len(missing_params)}"

        missing_rows = await conn.fetch(f"""
            SELECT
                j.id AS jurisdiction_id, j.city, j.state,
                rkd.id AS key_definition_id,
                rkd.key, rkd.category_slug, rkd.name AS key_name
            FROM regulation_key_definitions rkd
            CROSS JOIN (
                SELECT DISTINCT j2.id, j2.city, j2.state
                FROM jurisdictions j2
                JOIN jurisdiction_requirements jr2 ON jr2.jurisdiction_id = j2.id
                WHERE j2.level != 'federal'
                {missing_filter}
            ) j
            LEFT JOIN jurisdiction_requirements jr
                ON jr.jurisdiction_id = j.id
                AND jr.category = rkd.category_slug
                AND jr.regulation_key = rkd.key
            WHERE jr.id IS NULL
        """, *missing_params)

        for r in missing_rows:
            message = f"{r['key_name']} has no data for {r['city']}, {r['state']}"
            result = await conn.execute("""
                INSERT INTO repository_alerts
                    (alert_type, severity, jurisdiction_id, key_definition_id,
                     category, regulation_key, message)
                VALUES ('missing_data', 'missing', $1, $2, $3, $4, $5)
                ON CONFLICT (jurisdiction_id, key_definition_id, alert_type)
                    WHERE status = 'open'
                DO NOTHING
            """, r["jurisdiction_id"], r["key_definition_id"],
                r["category_slug"], r["key"], message)
            if "INSERT" in result:
                created += 1

        # ── 3. Auto-resolve: keys that are now verified/present ──
        resolved_count = await conn.fetchval(f"""
            WITH resolvable AS (
                SELECT ra.id
                FROM repository_alerts ra
                JOIN jurisdiction_requirements jr
                    ON jr.jurisdiction_id = ra.jurisdiction_id
                    AND jr.category = ra.category
                    AND jr.regulation_key = ra.regulation_key
                    AND jr.status = 'active'
                JOIN regulation_key_definitions rkd
                    ON rkd.id = ra.key_definition_id
                WHERE ra.status = 'open'
                  AND ra.alert_type IN ('stale_warning', 'stale_critical', 'stale_expired')
                  AND EXTRACT(DAY FROM NOW() - jr.last_verified_at) <= rkd.staleness_warning_days
            )
            UPDATE repository_alerts
            SET status = 'resolved', resolved_at = NOW()
            WHERE id IN (SELECT id FROM resolvable)
            RETURNING id
        """) or 0
        resolved = resolved_count if isinstance(resolved_count, int) else 0

    return {
        "alerts_created": created,
        "alerts_resolved": resolved,
        "stale_found": len(stale_rows),
        "missing_found": len(missing_rows),
    }


@router.get("/jurisdictions/key-coverage", dependencies=[Depends(require_admin)])
async def jurisdiction_key_coverage(
    jurisdiction_id: Optional[UUID] = None,
    category: Optional[str] = None,
    state: Optional[str] = None,
    gaps_only: bool = False,
):
    """Key-level coverage: per-category breakdown of present/missing regulation keys."""
    from ..compliance_registry import resolve_weight, CATEGORY_MAP

    async with get_connection() as conn:
        # ── 1. All key definitions ──
        def_params: list = []
        def_filter = ""
        if category:
            def_params.append(category)
            def_filter = f"WHERE rkd.category_slug = ${len(def_params)}"

        all_defs = await conn.fetch(f"""
            SELECT rkd.id, rkd.key, rkd.category_slug, rkd.name,
                   rkd.enforcing_agency, rkd.state_variance, rkd.base_weight,
                   rkd.key_group, rkd.staleness_warning_days,
                   rkd.applicable_industries, rkd.applicable_entity_types,
                   cc."group" AS domain_group
            FROM regulation_key_definitions rkd
            JOIN compliance_categories cc ON cc.id = rkd.category_id
            {def_filter}
            ORDER BY rkd.category_slug, rkd.key
        """, *def_params)

        # ── 2. Present keys per jurisdiction ──
        jr_params: list = []
        jr_filter_parts = ["jr.status = 'active'"]
        if jurisdiction_id:
            jr_params.append(jurisdiction_id)
            jr_filter_parts.append(f"jr.jurisdiction_id = ${len(jr_params)}")
        elif state:
            jr_params.append(state.upper())
            jr_filter_parts.append(f"j.state = ${len(jr_params)}")
        if category:
            jr_params.append(category)
            jr_filter_parts.append(f"jr.category = ${len(jr_params)}")

        jr_filter = " AND ".join(jr_filter_parts)

        present_rows = await conn.fetch(f"""
            SELECT
                jr.category,
                jr.regulation_key,
                COUNT(DISTINCT jr.jurisdiction_id) AS jurisdiction_count,
                MAX(CASE jr.source_tier::text
                    WHEN 'tier_1_government' THEN 3
                    WHEN 'tier_2_official_secondary' THEN 2
                    WHEN 'tier_3_aggregator' THEN 1
                    ELSE 0 END) AS best_tier,
                MAX(EXTRACT(DAY FROM NOW() - jr.last_verified_at))::int AS max_staleness_days,
                MAX(jr.current_value) AS newest_value
            FROM jurisdiction_requirements jr
            JOIN jurisdictions j ON j.id = jr.jurisdiction_id
            WHERE {jr_filter}
            GROUP BY jr.category, jr.regulation_key
        """, *jr_params)

        present_set: Dict[str, dict] = {}
        for r in present_rows:
            k = f"{r['category']}:{r['regulation_key']}"
            present_set[k] = {
                "jurisdiction_count": r["jurisdiction_count"],
                "best_tier": r["best_tier"],
                "days_since_verified": r["max_staleness_days"],
                "newest_value": r["newest_value"],
            }

        # ── 3. Build per-category response ──
        categories_data: Dict[str, dict] = {}
        total_expected = 0
        total_present = 0
        total_weight_expected = 0.0
        total_weight_present = 0.0

        for d in all_defs:
            cat = d["category_slug"]
            if cat not in categories_data:
                cat_def = CATEGORY_MAP.get(cat)
                categories_data[cat] = {
                    "category": cat,
                    "group": d["domain_group"],
                    "label": cat_def.label if cat_def else cat,
                    "expected": 0,
                    "present": 0,
                    "coverage_pct": 0,
                    "weighted_score": 0,
                    "keys": [],
                    "partial_groups": {},
                }

            lookup_key = f"{cat}:{d['key']}"
            is_present = lookup_key in present_set
            presence = present_set.get(lookup_key, {})
            weight = float(d["base_weight"])

            staleness_days = presence.get("days_since_verified")
            if staleness_days is not None and is_present:
                warn = d["staleness_warning_days"] or 90
                if staleness_days >= (d.get("staleness_expired_days") or 365):
                    staleness_level = "expired"
                elif staleness_days >= (d.get("staleness_critical_days") or 180):
                    staleness_level = "critical"
                elif staleness_days >= warn:
                    staleness_level = "warning"
                else:
                    staleness_level = "fresh"
            else:
                staleness_level = "no_data" if not is_present else "fresh"

            key_entry = {
                "id": str(d["id"]),
                "key": d["key"],
                "name": d["name"],
                "enforcing_agency": d["enforcing_agency"],
                "base_weight": weight,
                "state_variance": d["state_variance"],
                "key_group": d["key_group"],
                "status": "present" if is_present else "missing",
                "jurisdiction_count": presence.get("jurisdiction_count", 0),
                "best_tier": presence.get("best_tier", 0),
                "days_since_verified": staleness_days,
                "staleness_level": staleness_level,
                "newest_value": presence.get("newest_value"),
            }

            if not gaps_only or not is_present:
                categories_data[cat]["keys"].append(key_entry)

            categories_data[cat]["expected"] += 1
            total_expected += 1
            total_weight_expected += weight

            if is_present:
                categories_data[cat]["present"] += 1
                total_present += 1
                total_weight_present += weight

            # Track group completeness
            grp = d["key_group"]
            if grp:
                pg = categories_data[cat]["partial_groups"]
                if grp not in pg:
                    pg[grp] = {"present": 0, "expected": 0, "missing": []}
                pg[grp]["expected"] += 1
                if is_present:
                    pg[grp]["present"] += 1
                else:
                    pg[grp]["missing"].append(d["key"])

        # ── 4. Finalize categories ──
        by_category = []
        cats_fully_covered = 0
        cats_with_gaps = 0

        for cat_data in categories_data.values():
            exp = cat_data["expected"]
            pres = cat_data["present"]
            cat_data["coverage_pct"] = round(pres / exp * 100, 1) if exp > 0 else 0

            # Convert partial_groups to list, only include incomplete ones
            pg_list = []
            for grp_name, grp_data in cat_data["partial_groups"].items():
                if 0 < grp_data["present"] < grp_data["expected"]:
                    pg_list.append({
                        "group": grp_name,
                        "present": grp_data["present"],
                        "expected": grp_data["expected"],
                        "missing": grp_data["missing"],
                    })
            cat_data["partial_groups"] = pg_list

            if pres == exp and exp > 0:
                cats_fully_covered += 1
            elif pres < exp:
                cats_with_gaps += 1

            if not gaps_only or pres < exp:
                by_category.append(cat_data)

        # Sort: most gaps first
        by_category.sort(key=lambda c: c["coverage_pct"])

        # ── 5. Stale/alert counts ──
        stale_warning = sum(
            1 for c in by_category
            for k in c["keys"]
            if k["staleness_level"] == "warning"
        )
        stale_critical = sum(
            1 for c in by_category
            for k in c["keys"]
            if k["staleness_level"] in ("critical", "expired")
        )

    return {
        "summary": {
            "total_defined_keys": total_expected,
            "total_present": total_present,
            "key_coverage_pct": round(total_present / total_expected * 100, 1) if total_expected > 0 else 0,
            "weighted_score": round(total_weight_present / total_weight_expected * 100, 1) if total_weight_expected > 0 else 0,
            "categories_fully_covered": cats_fully_covered,
            "categories_with_gaps": cats_with_gaps,
            "stale_warning": stale_warning,
            "stale_critical": stale_critical,
        },
        "by_category": by_category,
    }


@router.get("/jurisdictions/categories/{slug}", dependencies=[Depends(require_admin)])
async def get_category_detail(slug: str, state: str = Query(default=None)):
    """Full detail for a compliance category: description, domain, and all regulation key definitions with coverage stats."""
    async with get_connection() as conn:
        # Get category info
        cat = await conn.fetchrow(
            'SELECT id, slug, name, description, domain::text, "group" FROM compliance_categories WHERE slug = $1',
            slug
        )
        if not cat:
            raise HTTPException(status_code=404, detail="Category not found")

        # Get all key definitions for this category with coverage stats
        state_filter = ""
        params = [slug]
        if state:
            state_filter = "AND jr.jurisdiction_id IN (SELECT id FROM jurisdictions WHERE state = $2)"
            params.append(state)

        keys = await conn.fetch(f"""
            SELECT rkd.id, rkd.key, rkd.name, rkd.description,
                   rkd.state_variance, rkd.enforcing_agency, rkd.base_weight,
                   rkd.key_group, rkd.staleness_warning_days, rkd.created_at,
                   COUNT(jr.id) AS jurisdiction_count,
                   COUNT(jr.id) FILTER (WHERE jr.change_status = 'changed') AS changed_count,
                   COUNT(jr.id) FILTER (WHERE jr.change_status = 'new') AS new_count,
                   MIN(jr.last_verified_at) AS oldest_verified,
                   CASE
                       WHEN COUNT(jr.id) = 0 THEN 'no_data'
                       WHEN MIN(jr.last_verified_at) < NOW() - (rkd.staleness_expired_days || ' days')::interval THEN 'expired'
                       WHEN MIN(jr.last_verified_at) < NOW() - (rkd.staleness_critical_days || ' days')::interval THEN 'critical'
                       WHEN MIN(jr.last_verified_at) < NOW() - (rkd.staleness_warning_days || ' days')::interval THEN 'warning'
                       ELSE 'fresh'
                   END AS staleness_level
            FROM regulation_key_definitions rkd
            LEFT JOIN jurisdiction_requirements jr
                ON jr.key_definition_id = rkd.id {state_filter}
            WHERE rkd.category_slug = $1
            GROUP BY rkd.id
            ORDER BY rkd.key
        """, *params)

        total_reqs = sum(r["jurisdiction_count"] for r in keys)

        # Get states that have jurisdictions (for filter dropdown)
        available_states = await conn.fetch(
            "SELECT DISTINCT state FROM jurisdictions WHERE state IS NOT NULL ORDER BY state"
        )

        def fmt_date(d):
            return d.isoformat() if d else None

        return {
            "slug": cat["slug"],
            "name": cat["name"],
            "description": cat["description"],
            "domain": cat["domain"],
            "group": cat["group"],
            "key_count": len(keys),
            "requirement_count": total_reqs,
            "state_filter": state,
            "available_states": [r["state"] for r in available_states],
            "keys": [
                {
                    "id": str(r["id"]),
                    "key": r["key"],
                    "name": r["name"],
                    "description": r["description"],
                    "state_variance": r["state_variance"],
                    "enforcing_agency": r["enforcing_agency"],
                    "base_weight": float(r["base_weight"]) if r["base_weight"] else 1.0,
                    "key_group": r["key_group"],
                    "jurisdiction_count": r["jurisdiction_count"],
                    "changed_count": r["changed_count"],
                    "new_count": r["new_count"],
                    "staleness_level": r["staleness_level"],
                    "created_at": r["created_at"].isoformat() if r["created_at"] else None,
                }
                for r in keys
            ],
        }


@router.get("/jurisdictions/policies/{key_definition_id}", dependencies=[Depends(require_admin)])
async def get_policy_detail(key_definition_id: UUID):
    """Full detail for a regulation key: definition + all jurisdiction instances + change log."""
    async with get_connection() as conn:
        # Key definition
        kd = await conn.fetchrow("""
            SELECT rkd.id, rkd.key, rkd.category_slug, rkd.name, rkd.description,
                   rkd.state_variance, rkd.enforcing_agency, rkd.base_weight,
                   rkd.authority_source_urls, rkd.applies_to_levels,
                   rkd.staleness_warning_days, rkd.staleness_critical_days,
                   rkd.staleness_expired_days, rkd.key_group, rkd.update_frequency,
                   cc.name AS category_name
            FROM regulation_key_definitions rkd
            JOIN compliance_categories cc ON cc.id = rkd.category_id
            WHERE rkd.id = $1
        """, key_definition_id)
        if not kd:
            raise HTTPException(status_code=404, detail="Key definition not found")

        # All jurisdiction instances
        reqs = await conn.fetch("""
            SELECT jr.id, jr.jurisdiction_id, jr.title, jr.description,
                   jr.current_value, jr.previous_value, jr.previous_description,
                   jr.change_status, jr.effective_date, jr.source_url, jr.source_name,
                   jr.last_verified_at, jr.last_changed_at, jr.requires_written_policy,
                   j.city, j.state, j.display_name, j.level::text AS jur_level
            FROM jurisdiction_requirements jr
            JOIN jurisdictions j ON j.id = jr.jurisdiction_id
            WHERE jr.key_definition_id = $1
            ORDER BY j.state, j.city NULLS FIRST
        """, key_definition_id)

        # Recent change log entries
        change_log = await conn.fetch("""
            SELECT pcl.field_changed, pcl.old_value, pcl.new_value,
                   pcl.changed_at, pcl.change_source,
                   j.display_name AS jurisdiction_name
            FROM policy_change_log pcl
            JOIN jurisdiction_requirements jr ON jr.id = pcl.requirement_id
            JOIN jurisdictions j ON j.id = jr.jurisdiction_id
            WHERE jr.key_definition_id = $1
            ORDER BY pcl.changed_at DESC
            LIMIT 50
        """, key_definition_id)

        def fmt_date(d):
            return d.isoformat() if d else None

        return {
            "id": str(kd["id"]),
            "key": kd["key"],
            "category_slug": kd["category_slug"],
            "category_name": kd["category_name"],
            "name": kd["name"],
            "description": kd["description"],
            "state_variance": kd["state_variance"],
            "enforcing_agency": kd["enforcing_agency"],
            "base_weight": float(kd["base_weight"]) if kd["base_weight"] else 1.0,
            "authority_source_urls": kd["authority_source_urls"],
            "applies_to_levels": kd["applies_to_levels"],
            "staleness_warning_days": kd["staleness_warning_days"],
            "staleness_critical_days": kd["staleness_critical_days"],
            "update_frequency": kd["update_frequency"],
            "key_group": kd["key_group"],
            "jurisdictions": [
                {
                    "requirement_id": str(r["id"]),
                    "jurisdiction_id": str(r["jurisdiction_id"]),
                    "state": r["state"],
                    "city": r["city"],
                    "display_name": r["display_name"],
                    "level": r["jur_level"],
                    "title": r["title"],
                    "description": r["description"],
                    "current_value": r["current_value"],
                    "previous_value": r["previous_value"],
                    "previous_description": r["previous_description"],
                    "change_status": r["change_status"],
                    "effective_date": fmt_date(r["effective_date"]),
                    "source_url": r["source_url"],
                    "source_name": r["source_name"],
                    "requires_written_policy": r["requires_written_policy"],
                    "last_verified_at": fmt_date(r["last_verified_at"]),
                    "last_changed_at": fmt_date(r["last_changed_at"]),
                }
                for r in reqs
            ],
            "change_log": [
                {
                    "jurisdiction_name": r["jurisdiction_name"],
                    "field_changed": r["field_changed"],
                    "old_value": r["old_value"],
                    "new_value": r["new_value"],
                    "changed_at": fmt_date(r["changed_at"]),
                    "change_source": r["change_source"],
                }
                for r in change_log
            ],
        }


@router.get("/jurisdictions/{jurisdiction_id}", dependencies=[Depends(require_admin)])
async def get_jurisdiction_detail(jurisdiction_id: UUID):
    """Get full detail for a jurisdiction: requirements, legislation, linked locations."""
    redis = get_redis_cache()
    if redis:
        cached = await cache_get(redis, admin_jurisdiction_detail_key(jurisdiction_id))
        if cached is not None:
            return cached

    async with get_connection() as conn:
        j = await conn.fetchrow("SELECT * FROM jurisdictions WHERE id = $1", jurisdiction_id)
        if not j:
            raise HTTPException(status_code=404, detail="Jurisdiction not found")
        # Only validate city for city-level jurisdictions used in research
        # State/federal/county rows and detail lookups should always be viewable
        j_level = j["level"] if "level" in j.keys() else "city"

        # Fetch children
        children = await conn.fetch(
            "SELECT id, city, state FROM jurisdictions WHERE parent_id = $1 ORDER BY state, city",
            jurisdiction_id
        )

        requirements = await conn.fetch("""
            SELECT id, requirement_key, category, jurisdiction_level, jurisdiction_name,
                   title, description, current_value, numeric_value,
                   source_url, source_name, effective_date, expiration_date,
                   previous_value, previous_description, change_status,
                   last_changed_at, last_verified_at, is_bookmarked,
                   sort_order, created_at, updated_at
            FROM jurisdiction_requirements
            WHERE jurisdiction_id = $1
            ORDER BY category, sort_order, title
        """, jurisdiction_id)

        legislation = await conn.fetch("""
            SELECT id, legislation_key, category, title, description,
                   current_status, expected_effective_date, impact_summary,
                   source_url, source_name, confidence, last_verified_at, created_at, updated_at
            FROM jurisdiction_legislation
            WHERE jurisdiction_id = $1
            ORDER BY expected_effective_date ASC NULLS LAST, title
        """, jurisdiction_id)

        locations = await conn.fetch("""
            SELECT bl.id, bl.name, bl.city, bl.state, bl.company_id, c.name AS company_name,
                   bl.auto_check_enabled, bl.auto_check_interval_days,
                   bl.next_auto_check, bl.last_compliance_check
            FROM business_locations bl
            JOIN companies c ON c.id = bl.company_id
            WHERE bl.jurisdiction_id = $1 AND bl.is_active = true
            ORDER BY c.name, bl.name
        """, jurisdiction_id)

        def fmt_date(d):
            return d.isoformat() if d else None

        def fmt_decimal(v):
            return float(v) if v is not None else None

        result = {
            "id": str(j["id"]),
            "city": j["city"],
            "state": j["state"],
            "county": j["county"],
            "parent_id": str(j["parent_id"]) if j["parent_id"] else None,
            "children": [
                {"id": str(c["id"]), "city": c["city"], "state": c["state"]}
                for c in children
            ],
            "requirement_count": j["requirement_count"] or 0,
            "legislation_count": j["legislation_count"] or 0,
            "last_verified_at": fmt_date(j["last_verified_at"]),
            "created_at": fmt_date(j["created_at"]),
            "requirements": [
                {
                    "id": str(r["id"]),
                    "requirement_key": r["requirement_key"],
                    "category": r["category"],
                    "jurisdiction_level": r["jurisdiction_level"],
                    "jurisdiction_name": r["jurisdiction_name"],
                    "title": r["title"],
                    "description": r["description"],
                    "current_value": r["current_value"],
                    "numeric_value": fmt_decimal(r["numeric_value"]),
                    "source_url": r["source_url"],
                    "source_name": r["source_name"],
                    "effective_date": fmt_date(r["effective_date"]),
                    "expiration_date": fmt_date(r["expiration_date"]),
                    "previous_value": r["previous_value"],
                    "previous_description": r["previous_description"],
                    "change_status": r["change_status"],
                    "last_changed_at": fmt_date(r["last_changed_at"]),
                    "last_verified_at": fmt_date(r["last_verified_at"]),
                    "is_bookmarked": r["is_bookmarked"],
                    "sort_order": r["sort_order"],
                    "updated_at": fmt_date(r["updated_at"]),
                }
                for r in requirements
            ],
            "legislation": [
                {
                    "id": str(l["id"]),
                    "legislation_key": l["legislation_key"],
                    "category": l["category"],
                    "title": l["title"],
                    "description": l["description"],
                    "current_status": l["current_status"],
                    "expected_effective_date": fmt_date(l["expected_effective_date"]),
                    "impact_summary": l["impact_summary"],
                    "source_url": l["source_url"],
                    "source_name": l["source_name"],
                    "confidence": fmt_decimal(l["confidence"]),
                    "last_verified_at": fmt_date(l["last_verified_at"]),
                    "updated_at": fmt_date(l["updated_at"]),
                }
                for l in legislation
            ],
            "locations": [
                {
                    "id": str(loc["id"]),
                    "name": loc["name"],
                    "city": loc["city"],
                    "state": loc["state"],
                    "company_name": loc["company_name"],
                    "auto_check_enabled": loc["auto_check_enabled"],
                    "auto_check_interval_days": loc["auto_check_interval_days"],
                    "next_auto_check": fmt_date(loc["next_auto_check"]),
                    "last_compliance_check": fmt_date(loc["last_compliance_check"]),
                }
                for loc in locations
            ],
        }

    if redis:
        await cache_set(redis, admin_jurisdiction_detail_key(jurisdiction_id), result, ttl=600)

    return result


class RequirementUpdate(BaseModel):
    """Partial update fields for a jurisdiction requirement."""
    title: Optional[str] = None
    description: Optional[str] = None
    current_value: Optional[str] = None
    effective_date: Optional[str] = None
    source_url: Optional[str] = None
    source_name: Optional[str] = None


@router.patch("/jurisdictions/requirements/{requirement_id}", dependencies=[Depends(require_admin)])
async def update_requirement(requirement_id: UUID, body: RequirementUpdate):
    """Partially update a jurisdiction requirement (e.g. add applicability notes)."""
    updates = {k: v for k, v in body.model_dump().items() if v is not None}
    if not updates:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="No fields to update")

    set_parts = []
    params: list[Any] = []
    for i, (col, val) in enumerate(updates.items(), start=1):
        set_parts.append(f"{col} = ${i}")
        params.append(val)

    params.append(requirement_id)
    id_idx = len(params)

    sql = f"""
        UPDATE jurisdiction_requirements
        SET {', '.join(set_parts)}, updated_at = NOW()
        WHERE id = ${id_idx}
        RETURNING id, jurisdiction_id, requirement_key, category, jurisdiction_level, jurisdiction_name,
                  title, description, current_value, numeric_value,
                  source_url, source_name, effective_date, expiration_date,
                  previous_value, last_changed_at, last_verified_at, is_bookmarked,
                  sort_order, created_at, updated_at
    """

    async with get_connection() as conn:
        row = await conn.fetchrow(sql, *params)
        if not row:
            raise HTTPException(status_code=404, detail="Requirement not found")

    redis = get_redis_cache()
    if redis:
        await cache_delete(redis, admin_jurisdiction_detail_key(row["jurisdiction_id"]))
        await cache_delete(redis, admin_jurisdiction_policy_overview_key(row["category"]))
        await cache_delete(redis, admin_jurisdiction_policy_overview_key(None))

    def fmt_date(d):
        return d.isoformat() if d else None

    return {
        "id": str(row["id"]),
        "requirement_key": row["requirement_key"],
        "category": row["category"],
        "jurisdiction_level": row["jurisdiction_level"],
        "jurisdiction_name": row["jurisdiction_name"],
        "title": row["title"],
        "description": row["description"],
        "current_value": row["current_value"],
        "numeric_value": float(row["numeric_value"]) if row["numeric_value"] is not None else None,
        "source_url": row["source_url"],
        "source_name": row["source_name"],
        "effective_date": fmt_date(row["effective_date"]),
        "expiration_date": fmt_date(row["expiration_date"]),
        "previous_value": row["previous_value"],
        "last_changed_at": fmt_date(row["last_changed_at"]),
        "last_verified_at": fmt_date(row["last_verified_at"]),
        "is_bookmarked": row["is_bookmarked"],
        "sort_order": row["sort_order"],
        "updated_at": fmt_date(row["updated_at"]),
    }


@router.post("/jurisdictions/requirements/{requirement_id}/bookmark", dependencies=[Depends(require_admin)])
async def toggle_requirement_bookmark(requirement_id: UUID):
    """Toggle the is_bookmarked flag on a jurisdiction requirement."""
    async with get_connection() as conn:
        row = await conn.fetchrow("""
            UPDATE jurisdiction_requirements
            SET is_bookmarked = NOT is_bookmarked, updated_at = NOW()
            WHERE id = $1
            RETURNING id, is_bookmarked, jurisdiction_id
        """, requirement_id)
        if not row:
            raise HTTPException(status_code=404, detail="Requirement not found")

    redis = get_redis_cache()
    if redis:
        await cache_delete(redis, admin_bookmarked_requirements_key())
        await cache_delete(redis, admin_jurisdiction_detail_key(row["jurisdiction_id"]))

    return {"id": str(row["id"]), "is_bookmarked": row["is_bookmarked"]}


@router.get("/jurisdictions/requirements/bookmarked", dependencies=[Depends(require_admin)])
async def list_bookmarked_requirements():
    """List all bookmarked jurisdiction requirements across all cities."""
    redis = get_redis_cache()
    if redis:
        cached = await cache_get(redis, admin_bookmarked_requirements_key())
        if cached is not None:
            return cached

    async with get_connection() as conn:
        rows = await conn.fetch("""
            SELECT jr.id, jr.requirement_key, jr.category, jr.jurisdiction_level,
                   jr.jurisdiction_name, jr.title, jr.description, jr.current_value,
                   jr.numeric_value, jr.source_url, jr.source_name, jr.effective_date,
                   jr.expiration_date, jr.previous_value, jr.last_changed_at,
                   jr.last_verified_at, jr.is_bookmarked, jr.sort_order,
                   jr.created_at, jr.updated_at,
                   j.id AS jurisdiction_id, j.city, j.state
            FROM jurisdiction_requirements jr
            JOIN jurisdictions j ON j.id = jr.jurisdiction_id
            WHERE jr.is_bookmarked = true
            ORDER BY jr.updated_at DESC
        """)

    def fmt_date(d):
        return d.isoformat() if d else None

    result = [
        {
            "id": str(r["id"]),
            "jurisdiction_id": str(r["jurisdiction_id"]),
            "requirement_key": r["requirement_key"],
            "category": r["category"],
            "jurisdiction_level": r["jurisdiction_level"],
            "jurisdiction_name": r["jurisdiction_name"],
            "title": r["title"],
            "description": r["description"],
            "current_value": r["current_value"],
            "numeric_value": float(r["numeric_value"]) if r["numeric_value"] is not None else None,
            "source_url": r["source_url"],
            "source_name": r["source_name"],
            "effective_date": fmt_date(r["effective_date"]),
            "expiration_date": fmt_date(r["expiration_date"]),
            "previous_value": r["previous_value"],
            "last_changed_at": fmt_date(r["last_changed_at"]),
            "last_verified_at": fmt_date(r["last_verified_at"]),
            "is_bookmarked": r["is_bookmarked"],
            "sort_order": r["sort_order"],
            "updated_at": fmt_date(r["updated_at"]),
            "city": r["city"],
            "state": r["state"],
        }
        for r in rows
    ]

    if redis:
        await cache_set(redis, admin_bookmarked_requirements_key(), result, ttl=600)

    return result


@router.put("/jurisdictions/requirements/reorder", dependencies=[Depends(require_admin)])
async def reorder_requirements(body: dict[str, Any] = Body(...)):
    """Bulk-update sort_order for jurisdiction requirements."""
    order = body.get("order")
    if not order or not isinstance(order, list):
        raise HTTPException(status_code=400, detail="'order' must be a non-empty list")

    async with get_connection() as conn:
        async with conn.transaction():
            updated = 0
            for item in order:
                rid = item.get("id")
                sort_order = item.get("sort_order")
                if rid is None or sort_order is None:
                    continue
                result = await conn.execute(
                    "UPDATE jurisdiction_requirements SET sort_order = $1, updated_at = NOW() WHERE id = $2",
                    sort_order, UUID(rid),
                )
                if result and result.endswith("1"):
                    updated += 1
    return {"updated": updated}


def _to_sse(event: dict[str, Any]) -> str:
    return f"data: {json.dumps(event)}\n\n"


def _format_city_label(city: str) -> str:
    if not city:
        return city
    parts = city.replace("_", " ").split()
    return " ".join(part.capitalize() for part in parts)


def _phase_percent(phase: str) -> int:
    mapping = {
        "started": 5,
        "researching": 20,
        "retrying": 24,
        "confidence_retry": 30,
        "confidence_gate": 38,
        "processing": 48,
        "scanning": 62,
        "legislation": 70,
        "syncing": 82,
        "verifying": 90,
        "poster_updated": 94,
        "poster_alerts": 96,
        "completed": 100,
        "error": 100,
    }
    return mapping.get(phase, 35)


def _source_confidence(source_url: Optional[str], source_name: Optional[str]) -> float:
    from ..services.jurisdiction_context import extract_domain

    domain = extract_domain(source_url or "")
    if not domain:
        return 0.0

    score = 0.7
    if domain.endswith(".gov"):
        score = 0.98
    elif domain.endswith(".us"):
        score = 0.95
    elif domain.endswith(".org"):
        score = 0.8

    source_label = (source_name or "").lower()
    if "department of labor" in source_label or "labor commissioner" in source_label:
        score = max(score, 0.97)
    elif "city of" in source_label or "county of" in source_label or "state of" in source_label:
        score = max(score, 0.93)

    return min(score, 0.99)


def _requirement_confidence(req: dict[str, Any]) -> float:
    return _source_confidence(req.get("source_url"), req.get("source_name"))


def _legislation_confidence(item: dict[str, Any]) -> float:
    raw = item.get("confidence")
    try:
        parsed = float(raw) if raw is not None else 0.0
    except (TypeError, ValueError):
        parsed = 0.0
    return max(parsed, _source_confidence(item.get("source_url"), item.get("source_name")))


async def _run_jurisdiction_check_events(
    jurisdiction_id: UUID,
    inline_healthcare_research: bool = False,
) -> AsyncGenerator[dict[str, Any], None]:
    from ..services.gemini_compliance import get_gemini_compliance_service
    from ..services.compliance_service import (
        _upsert_jurisdiction_requirements,
        _upsert_jurisdiction_legislation,
        _normalize_category,
        _normalize_requirement_categories,
        _filter_city_level_requirements,
        _filter_with_preemption,
        _filter_requirements_for_company,
        _sync_requirements_to_location,
        _create_alert,
        score_verification_confidence,
        _compute_requirement_key,
        _normalize_title_key,
        REQUIRED_LABOR_CATEGORIES,
        _missing_required_categories,
        _lookup_has_local_ordinance,
        _refresh_repository_missing_categories,
        _research_healthcare_requirements_for_jurisdiction,
        _research_oncology_requirements_for_jurisdiction,
        ONCOLOGY_CATEGORIES,
    )
    from ..models.compliance import VerificationResult

    async with get_connection() as conn:
        j = await conn.fetchrow("SELECT * FROM jurisdictions WHERE id = $1", jurisdiction_id)
        if not j:
            raise HTTPException(status_code=404, detail="Jurisdiction not found")

    city, state, county = j["city"], j["state"], j["county"]
    location_label = f"{_format_city_label(city)}, {state}"

    yield {"type": "started", "location": location_label}
    yield {"type": "researching", "message": f"Researching requirements for {location_label}..."}

    service = get_gemini_compliance_service()
    async with get_connection() as conn:
        used_repository = False
        has_local_ordinance = await _lookup_has_local_ordinance(conn, city, state)
        try:
            preemption_rows = await conn.fetch(
                "SELECT category, allows_local_override FROM state_preemption_rules WHERE state = $1",
                state.upper(),
            )
            preemption_rules = {row["category"]: row["allows_local_override"] for row in preemption_rows}
        except asyncpg.UndefinedTableError:
            preemption_rules = {}

        async def _prepare_requirements_for_sync(requirements: list[dict[str, Any]]) -> list[dict[str, Any]]:
            prepared = [dict(req) for req in requirements]
            if has_local_ordinance is False:
                prepared = _filter_city_level_requirements(prepared, state)
            _normalize_requirement_categories(prepared)
            prepared = await _filter_with_preemption(conn, prepared, state)
            return prepared

        city_key = _normalize_city_input(city)
        city_jurisdiction_rows = await conn.fetch(
            """
            SELECT
                j.id,
                j.city,
                j.state,
                j.requirement_count,
                j.legislation_count,
                j.last_verified_at,
                j.created_at,
                COUNT(bl.id) AS location_count
            FROM jurisdictions j
            LEFT JOIN business_locations bl ON bl.jurisdiction_id = j.id AND bl.is_active = true
            WHERE j.state = $1
              AND j.city <> ''
              AND j.city NOT LIKE '_county_%'
            GROUP BY j.id
            """,
            state,
        )
        same_city_rows = [
            row for row in city_jurisdiction_rows
            if _normalize_city_input(row["city"]) == city_key
        ]
        if not same_city_rows:
            j_dict = dict(j)
            same_city_rows = [{
                "id": j_dict["id"],
                "city": j_dict["city"],
                "state": j_dict["state"],
                "requirement_count": j_dict.get("requirement_count", 0),
                "legislation_count": j_dict.get("legislation_count", 0),
                "last_verified_at": j_dict.get("last_verified_at"),
                "created_at": j_dict.get("created_at"),
                "location_count": 0,
            }]

        def _canonical_priority(row):
            return (
                (row["requirement_count"] or 0) + (row["legislation_count"] or 0),
                row["location_count"] or 0,
                1 if row["last_verified_at"] is not None else 0,
                row["last_verified_at"] or datetime.min,
                1 if row["created_at"] is not None else 0,
                row["created_at"] or datetime.min,
            )

        canonical_row = max(same_city_rows, key=_canonical_priority)
        canonical_jurisdiction_id = canonical_row["id"]
        duplicate_jurisdiction_ids = [
            row["id"] for row in same_city_rows
            if row["id"] != canonical_jurisdiction_id
        ]
        city_group_ids = [canonical_jurisdiction_id, *duplicate_jurisdiction_ids]

        if duplicate_jurisdiction_ids:
            moved_locations = await conn.fetchval(
                """
                WITH moved AS (
                    UPDATE business_locations
                    SET jurisdiction_id = $1
                    WHERE jurisdiction_id = ANY($2::uuid[])
                    RETURNING id
                )
                SELECT COUNT(*) FROM moved
                """,
                canonical_jurisdiction_id,
                duplicate_jurisdiction_ids,
            )
            moved_children = await conn.fetchval(
                """
                WITH moved AS (
                    UPDATE jurisdictions
                    SET parent_id = $1
                    WHERE parent_id = ANY($2::uuid[])
                      AND id <> $1
                    RETURNING id
                )
                SELECT COUNT(*) FROM moved
                """,
                canonical_jurisdiction_id,
                duplicate_jurisdiction_ids,
            )
            moved_location_count = int(moved_locations or 0)
            moved_child_count = int(moved_children or 0)
            if moved_location_count or moved_child_count:
                yield {
                    "type": "syncing",
                    "message": (
                        "Aligned duplicate city jurisdictions to canonical source: "
                        f"{moved_location_count} location(s), {moved_child_count} child node(s) relinked."
                    ),
                }
            if canonical_jurisdiction_id != jurisdiction_id:
                yield {
                    "type": "syncing",
                    "message": (
                        f"Using canonical jurisdiction record for {_format_city_label(city)}, {state}."
                    ),
                }

        existing_jurisdiction_rows = await conn.fetch(
            "SELECT * FROM jurisdiction_requirements WHERE jurisdiction_id = ANY($1::uuid[])",
            city_group_ids,
        )
        for row in existing_jurisdiction_rows:
            row_dict = dict(row)
            normalized_category = _normalize_category(row_dict.get("category")) or row_dict.get("category")
            row_dict["category"] = normalized_category
            normalized_key = _compute_requirement_key(row_dict)
            if (
                normalized_category != row["category"]
                or normalized_key != row["requirement_key"]
            ):
                try:
                    await conn.execute(
                        """
                        UPDATE jurisdiction_requirements
                        SET category = $2, requirement_key = $3, updated_at = NOW()
                        WHERE id = $1
                        """,
                        row["id"],
                        normalized_category,
                        normalized_key,
                    )
                except asyncpg.UniqueViolationError:
                    await conn.execute(
                        "DELETE FROM jurisdiction_requirements WHERE id = $1",
                        row["id"],
                    )

        existing_jurisdiction_rows = await conn.fetch(
            "SELECT * FROM jurisdiction_requirements WHERE jurisdiction_id = ANY($1::uuid[])",
            city_group_ids,
        )
        existing_requirements = [_jurisdiction_row_to_dict(dict(row)) for row in existing_jurisdiction_rows]
        existing_requirements = await _prepare_requirements_for_sync(existing_requirements)
        present_categories = {
            _normalize_category(req.get("category")) or req.get("category")
            for req in existing_requirements
            if req.get("category")
        }
        research_categories = sorted(
            cat for cat in REQUIRED_LABOR_CATEGORIES
            if cat not in present_categories
        ) or None
        if research_categories:
            yield {
                "type": "researching",
                "message": (
                    f"Filling missing coverage for {location_label}: "
                    f"{', '.join(research_categories)}."
                ),
            }

        best_requirements: dict[str, tuple[float, dict[str, Any]]] = {}
        for pass_index in range(MAX_CONFIDENCE_REFETCH_ATTEMPTS + 1):
            if pass_index > 0:
                # Only re-research categories that still have low-confidence items
                low_conf_cats = {
                    _normalize_category(req.get("category")) or req.get("category")
                    for confidence, req in best_requirements.values()
                    if confidence < STRICT_CONFIDENCE_THRESHOLD
                }
                if not low_conf_cats:
                    break
                retry_categories = sorted(low_conf_cats)
                yield {
                    "type": "confidence_retry",
                    "message": (
                        f"Low-confidence requirements found. Cross-checking {_format_city_label(city)} "
                        f"against {state} sources — {len(retry_categories)} categor{'y' if len(retry_categories) == 1 else 'ies'} "
                        f"(pass {pass_index + 1}/{MAX_CONFIDENCE_REFETCH_ATTEMPTS + 1})..."
                    ),
                }
            else:
                retry_categories = research_categories

            research_queue: asyncio.Queue[dict[str, Any]] = asyncio.Queue()

            def _on_retry(attempt: int, error_text: str):
                reason = f" Reason: {error_text}" if error_text else ""
                research_queue.put_nowait(
                    {
                        "type": "retrying",
                        "message": (
                            f"Retrying research (attempt {attempt + 1})..."
                            f"{reason[:220]}"
                        ),
                    }
                )

            research_task = asyncio.create_task(
                service.research_location_compliance(
                    city=city,
                    state=state,
                    county=county,
                    categories=retry_categories,
                    preemption_rules=preemption_rules,
                    has_local_ordinance=has_local_ordinance,
                    on_retry=_on_retry,
                )
            )
            try:
                while not research_task.done():
                    while not research_queue.empty():
                        yield research_queue.get_nowait()
                    done, _ = await asyncio.wait({research_task}, timeout=8)
                    if done:
                        break
                    yield {"type": "heartbeat"}
            except asyncio.CancelledError:
                if not research_task.done():
                    research_task.cancel()
                raise

            while not research_queue.empty():
                yield research_queue.get_nowait()

            pass_requirements = research_task.result() or []
            if retry_categories and existing_requirements:
                target_set = set(retry_categories)
                preserved = [
                    req for req in existing_requirements
                    if (_normalize_category(req.get("category")) or req.get("category")) not in target_set
                ]
                pass_requirements = preserved + pass_requirements
            pass_requirements = await _prepare_requirements_for_sync(pass_requirements)

            for req in pass_requirements:
                req_key = _compute_requirement_key(req)
                confidence = _requirement_confidence(req)
                existing = best_requirements.get(req_key)
                if existing is None or confidence > existing[0]:
                    best_requirements[req_key] = (confidence, req)

            if best_requirements:
                low_count = sum(
                    1 for confidence, _ in best_requirements.values() if confidence < STRICT_CONFIDENCE_THRESHOLD
                )
                yield {
                    "type": "confidence_gate",
                    "message": (
                        f"Requirement confidence gate: {low_count} item(s) below "
                        f"{int(STRICT_CONFIDENCE_THRESHOLD * 100)}% after pass {pass_index + 1}."
                    ),
                }
                if low_count == 0:
                    break

        requirements = [req for _, req in best_requirements.values()]
        requirements = await _prepare_requirements_for_sync(requirements)
        missing_categories = _missing_required_categories(requirements)
        if requirements and missing_categories:
            yield {
                "type": "repository_refresh",
                "jurisdiction_id": str(canonical_jurisdiction_id),
                "missing_categories": missing_categories,
                "message": (
                    "Coverage is still missing "
                    f"{', '.join(missing_categories)}. Running source-aware repository refresh for "
                    f"{location_label}."
                ),
            }

            refresh_queue: asyncio.Queue[dict[str, Any]] = asyncio.Queue()

            def _on_partial_refresh_retry(attempt: int, error_text: str):
                reason = f" Reason: {error_text}" if error_text else ""
                refresh_queue.put_nowait(
                    {
                        "type": "retrying",
                        "message": (
                            f"Retrying repository refresh (attempt {attempt + 1})..."
                            f"{reason[:220]}"
                        ),
                    }
                )

            partial_refresh_task = asyncio.create_task(
                _refresh_repository_missing_categories(
                    conn,
                    service,
                    jurisdiction_id=canonical_jurisdiction_id,
                    city=city,
                    state=state,
                    county=county,
                    has_local_ordinance=has_local_ordinance,
                    current_requirements=requirements,
                    missing_categories=missing_categories,
                    on_retry=_on_partial_refresh_retry,
                )
            )
            try:
                while not partial_refresh_task.done():
                    while not refresh_queue.empty():
                        yield refresh_queue.get_nowait()
                    done, _ = await asyncio.wait({partial_refresh_task}, timeout=8)
                    if done:
                        break
                    yield {"type": "heartbeat"}
            except asyncio.CancelledError:
                if not partial_refresh_task.done():
                    partial_refresh_task.cancel()
                raise

            while not refresh_queue.empty():
                yield refresh_queue.get_nowait()

            refreshed_partial = partial_refresh_task.result() or requirements
            requirements = await _prepare_requirements_for_sync(refreshed_partial)
            missing_after_partial = _missing_required_categories(requirements)
            if missing_after_partial:
                yield {
                    "type": "repository_only",
                    "jurisdiction_id": str(canonical_jurisdiction_id),
                    "missing_categories": missing_after_partial,
                    "message": (
                        "Repository is still missing "
                        f"{', '.join(missing_after_partial)} after refresh."
                    ),
                }
            else:
                yield {
                    "type": "repository_refreshed",
                    "jurisdiction_id": str(canonical_jurisdiction_id),
                    "message": f"Repository refresh completed for {location_label}.",
                }

        low_conf_requirement_count = sum(
            1 for confidence, _ in best_requirements.values() if confidence < STRICT_CONFIDENCE_THRESHOLD
        )

        if not requirements:
            missing_categories = sorted(REQUIRED_LABOR_CATEGORIES)
            yield {
                "type": "repository_refresh",
                "jurisdiction_id": str(canonical_jurisdiction_id),
                "missing_categories": missing_categories,
                "message": (
                    "No requirements returned from direct research. Running source-aware repository refresh for "
                    f"{location_label} ({', '.join(missing_categories)})."
                ),
            }

            refresh_queue: asyncio.Queue[dict[str, Any]] = asyncio.Queue()

            def _on_refresh_retry(attempt: int, error_text: str):
                reason = f" Reason: {error_text}" if error_text else ""
                refresh_queue.put_nowait(
                    {
                        "type": "retrying",
                        "message": (
                            f"Retrying repository refresh (attempt {attempt + 1})..."
                            f"{reason[:220]}"
                        ),
                    }
                )

            refresh_task = asyncio.create_task(
                _refresh_repository_missing_categories(
                    conn,
                    service,
                    jurisdiction_id=canonical_jurisdiction_id,
                    city=city,
                    state=state,
                    county=county,
                    has_local_ordinance=has_local_ordinance,
                    current_requirements=existing_requirements,
                    missing_categories=missing_categories,
                    on_retry=_on_refresh_retry,
                )
            )
            try:
                while not refresh_task.done():
                    while not refresh_queue.empty():
                        yield refresh_queue.get_nowait()
                    done, _ = await asyncio.wait({refresh_task}, timeout=8)
                    if done:
                        break
                    yield {"type": "heartbeat"}
            except asyncio.CancelledError:
                if not refresh_task.done():
                    refresh_task.cancel()
                raise

            while not refresh_queue.empty():
                yield refresh_queue.get_nowait()

            refreshed_requirements = refresh_task.result() or []
            if refreshed_requirements:
                requirements = await _prepare_requirements_for_sync(refreshed_requirements)
                yield {
                    "type": "repository_refreshed",
                    "jurisdiction_id": str(canonical_jurisdiction_id),
                    "message": f"Repository refresh produced {len(requirements)} requirement(s).",
                }

        if not requirements:
            cached_rows = await conn.fetch(
                """
                SELECT * FROM jurisdiction_requirements
                WHERE jurisdiction_id = ANY($1::uuid[])
                ORDER BY category
                """,
                city_group_ids,
            )
            if cached_rows:
                requirements = [_jurisdiction_row_to_dict(dict(row)) for row in cached_rows]
                requirements = await _prepare_requirements_for_sync(requirements)
                used_repository = True
                logger.warning(
                    "Falling back to stale repository data (%d cached requirements)", len(requirements)
                )
                yield {"type": "fallback", "message": "Using cached data (live research unavailable)"}

        if not requirements:
            yield {
                "type": "completed",
                "location": location_label,
                "new": 0,
                "updated": 0,
                "alerts": 0,
                "low_confidence": 0,
                "low_confidence_requirements": 0,
                "low_confidence_legislation": 0,
                "low_confidence_changes": 0,
            }
            return

        yield {"type": "processing", "message": f"Processing {len(requirements)} requirements..."}

        if not used_repository:
            await _upsert_jurisdiction_requirements(conn, canonical_jurisdiction_id, requirements)

        new_count = len(requirements)
        for req in requirements:
            req_conf = _requirement_confidence(req)
            yield {
                "type": "result",
                "status": "new",
                "message": req.get("title", ""),
                "confidence": round(req_conf, 2),
            }

        yield {"type": "scanning", "message": "Scanning for upcoming legislation..."}
        best_legislation: dict[str, tuple[float, dict[str, Any]]] = {}
        try:
            for pass_index in range(MAX_CONFIDENCE_REFETCH_ATTEMPTS + 1):
                if pass_index > 0:
                    yield {
                        "type": "confidence_retry",
                        "message": (
                            f"Low-confidence legislation found. Re-scanning authoritative sources "
                            f"(pass {pass_index + 1}/{MAX_CONFIDENCE_REFETCH_ATTEMPTS + 1})..."
                        ),
                    }

                leg_task = asyncio.create_task(
                    service.scan_upcoming_legislation(
                        city=city,
                        state=state,
                        county=county,
                        current_requirements=[dict(req) for req in requirements],
                    )
                )
                try:
                    while not leg_task.done():
                        done, _ = await asyncio.wait({leg_task}, timeout=8)
                        if done:
                            break
                        yield {"type": "heartbeat"}
                except asyncio.CancelledError:
                    if not leg_task.done():
                        leg_task.cancel()
                    raise

                pass_legislation = leg_task.result() or []
                for item in pass_legislation:
                    leg_key = item.get("legislation_key") or _normalize_title_key(item.get("title", ""))
                    if not leg_key:
                        continue
                    item["legislation_key"] = leg_key
                    confidence = _legislation_confidence(item)
                    existing = best_legislation.get(leg_key)
                    if existing is None or confidence > existing[0]:
                        best_legislation[leg_key] = (confidence, item)

                if best_legislation:
                    low_count = sum(
                        1 for confidence, _ in best_legislation.values() if confidence < STRICT_CONFIDENCE_THRESHOLD
                    )
                    yield {
                        "type": "confidence_gate",
                        "message": (
                            f"Legislation confidence gate: {low_count} item(s) below "
                            f"{int(STRICT_CONFIDENCE_THRESHOLD * 100)}% after pass {pass_index + 1}."
                        ),
                    }
                    if low_count == 0:
                        break
        except Exception as exc:
            logger.error("Jurisdiction legislation scan error: %s", exc)

        legislation_items = [item for _, item in best_legislation.values()]
        low_conf_legislation_count = sum(
            1 for confidence, _ in best_legislation.values() if confidence < STRICT_CONFIDENCE_THRESHOLD
        )

        if legislation_items:
            await _upsert_jurisdiction_legislation(conn, canonical_jurisdiction_id, legislation_items)
            yield {
                "type": "legislation",
                "message": (
                    f"Found {len(legislation_items)} upcoming legislative change(s); "
                    f"{low_conf_legislation_count} below confidence gate."
                ),
            }

        linked_locations = await conn.fetch(
            """
            SELECT id, company_id
            FROM business_locations
            WHERE jurisdiction_id = ANY($1::uuid[]) AND is_active = true
            """,
            city_group_ids,
        )

        total_alerts = 0
        total_updated = 0
        verified_changes: dict[tuple[str, Any, Any], tuple[float, VerificationResult]] = {}

        if linked_locations:
            yield {"type": "syncing", "message": f"Syncing to {len(linked_locations)} location(s)..."}
            for loc in linked_locations:
                try:
                    location_requirements = await _filter_requirements_for_company(
                        conn,
                        loc["company_id"],
                        requirements,
                    )
                    sync_result = await _sync_requirements_to_location(
                        conn,
                        loc["id"],
                        loc["company_id"],
                        location_requirements,
                        create_alerts=True,
                    )
                    total_alerts += sync_result["alerts"]
                    total_updated += sync_result["updated"]

                    for change_info in sync_result["changes_to_verify"]:
                        req = change_info["req"]
                        existing = change_info["existing"]
                        old_val = change_info["old_value"]
                        new_val = change_info["new_value"]
                        cat = req.get("category", "")

                        cache_key = (cat, old_val, new_val)
                        if cache_key not in verified_changes:
                            try:
                                verify_task = asyncio.create_task(
                                    service.verify_compliance_change_adaptive(
                                        category=cat,
                                        title=req.get("title", ""),
                                        jurisdiction_name=req.get("jurisdiction_name", ""),
                                        old_value=old_val,
                                        new_value=new_val,
                                    )
                                )
                                try:
                                    while not verify_task.done():
                                        done, _ = await asyncio.wait({verify_task}, timeout=8)
                                        if done:
                                            break
                                        yield {"type": "heartbeat"}
                                except asyncio.CancelledError:
                                    if not verify_task.done():
                                        verify_task.cancel()
                                    raise

                                verification = verify_task.result()
                                confidence = max(
                                    score_verification_confidence(verification.sources),
                                    verification.confidence,
                                )
                                for retry_index in range(MAX_CONFIDENCE_REFETCH_ATTEMPTS):
                                    if confidence >= STRICT_CONFIDENCE_THRESHOLD:
                                        break
                                    yield {
                                        "type": "verifying",
                                        "message": (
                                            f"Confidence {confidence:.2f} for '{req.get('title', 'change')}' "
                                            f"is below {STRICT_CONFIDENCE_THRESHOLD:.2f}; "
                                            f"re-verifying ({retry_index + 1}/{MAX_CONFIDENCE_REFETCH_ATTEMPTS})..."
                                        ),
                                    }
                                    retry_task = asyncio.create_task(
                                        service.verify_compliance_change_adaptive(
                                            category=cat,
                                            title=req.get("title", ""),
                                            jurisdiction_name=req.get("jurisdiction_name", ""),
                                            old_value=old_val,
                                            new_value=new_val,
                                        )
                                    )
                                    try:
                                        while not retry_task.done():
                                            done, _ = await asyncio.wait({retry_task}, timeout=8)
                                            if done:
                                                break
                                            yield {"type": "heartbeat"}
                                    except asyncio.CancelledError:
                                        if not retry_task.done():
                                            retry_task.cancel()
                                        raise

                                    retry_verification = retry_task.result()
                                    retry_confidence = max(
                                        score_verification_confidence(retry_verification.sources),
                                        retry_verification.confidence,
                                    )
                                    if retry_confidence > confidence:
                                        confidence = retry_confidence
                                        verification = retry_verification
                            except Exception as exc:
                                logger.error("Verification failed: %s", exc)
                                verification = VerificationResult(
                                    confirmed=False,
                                    confidence=0.0,
                                    sources=[],
                                    explanation="Verification unavailable",
                                )
                                confidence = 0.5

                            verified_changes[cache_key] = (confidence, verification)

                        confidence, verification = verified_changes[cache_key]
                        change_msg = f"Value changed from {old_val} to {new_val}."
                        if req.get("description"):
                            change_msg += f" {req['description']}"

                        if confidence >= STRICT_CONFIDENCE_THRESHOLD:
                            total_alerts += 1
                            await _create_alert(
                                conn,
                                loc["id"],
                                loc["company_id"],
                                existing["id"],
                                f"Compliance Change: {req.get('title')}",
                                change_msg,
                                "warning",
                                req.get("category"),
                                source_url=req.get("source_url"),
                                source_name=req.get("source_name"),
                                alert_type="change",
                                confidence_score=round(confidence, 2),
                                verification_sources=verification.sources,
                                metadata={
                                    "source": "jurisdiction_sync",
                                    "verification_explanation": verification.explanation,
                                },
                            )
                        elif confidence >= 0.6:
                            total_alerts += 1
                            await _create_alert(
                                conn,
                                loc["id"],
                                loc["company_id"],
                                existing["id"],
                                f"Pending Verification: {req.get('title')}",
                                change_msg,
                                "info",
                                req.get("category"),
                                source_url=req.get("source_url"),
                                source_name=req.get("source_name"),
                                alert_type="change",
                                confidence_score=round(confidence, 2),
                                verification_sources=verification.sources,
                                metadata={
                                    "source": "jurisdiction_sync",
                                    "verification_explanation": verification.explanation,
                                    "unverified": True,
                                },
                            )
                        elif confidence >= 0.3:
                            total_alerts += 1
                            await _create_alert(
                                conn,
                                loc["id"],
                                loc["company_id"],
                                existing["id"],
                                f"Unverified: {req.get('title')}",
                                change_msg,
                                "info",
                                req.get("category"),
                                source_url=req.get("source_url"),
                                source_name=req.get("source_name"),
                                alert_type="change",
                                confidence_score=round(confidence, 2),
                                verification_sources=verification.sources,
                                metadata={
                                    "source": "jurisdiction_sync",
                                    "verification_explanation": verification.explanation,
                                    "unverified": True,
                                },
                            )
                        else:
                            logger.warning(
                                "Low confidence (%.2f) for change: %s, skipping alert",
                                confidence,
                                req.get("title"),
                            )

                    await conn.execute(
                        "UPDATE business_locations SET last_compliance_check = NOW() WHERE id = $1",
                        loc["id"],
                    )
                except Exception as exc:
                    logger.error("Failed to sync location %s: %s", loc["id"], exc)

        low_conf_change_count = sum(
            1 for confidence, _verification in verified_changes.values() if confidence < STRICT_CONFIDENCE_THRESHOLD
        )

        try:
            from ..services.poster_service import check_and_regenerate_poster, create_poster_update_alerts

            poster_result = await check_and_regenerate_poster(conn, canonical_jurisdiction_id)
            if poster_result and poster_result.get("status") == "generated":
                poster_version = poster_result.get("version", "?")
                yield {
                    "type": "poster_updated",
                    "message": f"Poster PDF regenerated (v{poster_version})",
                }
                alert_count = await create_poster_update_alerts(conn, canonical_jurisdiction_id)
                if alert_count:
                    total_alerts += alert_count
                    yield {
                        "type": "poster_alerts",
                        "message": f"Notified {alert_count} company(s) about poster update",
                    }
        except Exception as exc:
            logger.error("Poster regeneration check failed: %s", exc)

        total_low_confidence = low_conf_requirement_count + low_conf_legislation_count + low_conf_change_count
        if total_low_confidence > 0:
            yield {
                "type": "confidence_gate",
                "message": (
                    f"{total_low_confidence} item(s) remain below "
                    f"{int(STRICT_CONFIDENCE_THRESHOLD * 100)}% confidence after retries."
                ),
            }

        if inline_healthcare_research:
            try:
                yield {
                    "type": "repository_refresh",
                    "message": f"Researching healthcare-specific compliance for {location_label}...",
                }
                healthcare_result = await _research_healthcare_requirements_for_jurisdiction(
                    conn, canonical_jurisdiction_id
                )
                if healthcare_result.get("new", 0):
                    rows = await conn.fetch(
                        "SELECT * FROM jurisdiction_requirements WHERE jurisdiction_id = $1",
                        canonical_jurisdiction_id,
                    )
                    requirements = [
                        _jurisdiction_row_to_dict(dict(row)) for row in rows
                    ]
                    requirements = await _prepare_requirements_for_sync(requirements)
                    new_count = len(requirements)
                    if linked_locations:
                        yield {
                            "type": "syncing",
                            "message": (
                                f"Syncing healthcare-specific updates to "
                                f"{len(linked_locations)} location(s)..."
                            ),
                        }
                        for loc in linked_locations:
                            location_requirements = await _filter_requirements_for_company(
                                conn,
                                loc["company_id"],
                                requirements,
                            )
                            sync_result = await _sync_requirements_to_location(
                                conn,
                                loc["id"],
                                loc["company_id"],
                                location_requirements,
                                create_alerts=True,
                            )
                            total_alerts += sync_result["alerts"]
                            total_updated += sync_result["updated"]
                yield {
                    "type": "repository_refresh",
                    "message": (
                        f"Healthcare research completed for {location_label}: "
                        f"{healthcare_result.get('new', 0)} requirement(s) added."
                    ),
                }
            except Exception as exc:
                logger.warning("Healthcare inline research failed: %s", exc)
                yield {
                    "type": "warning",
                    "message": f"Healthcare-specific research failed: {exc}",
                }

            # Oncology research (inline, after healthcare)
            try:
                yield {
                    "type": "repository_refresh",
                    "message": f"Researching oncology-specific compliance for {location_label}...",
                }
                oncology_result = await _research_oncology_requirements_for_jurisdiction(
                    conn, canonical_jurisdiction_id
                )
                if oncology_result.get("new", 0):
                    rows = await conn.fetch(
                        "SELECT * FROM jurisdiction_requirements WHERE jurisdiction_id = $1",
                        canonical_jurisdiction_id,
                    )
                    requirements = [
                        _jurisdiction_row_to_dict(dict(row)) for row in rows
                    ]
                    requirements = await _prepare_requirements_for_sync(requirements)
                    new_count = len(requirements)
                    if linked_locations:
                        yield {
                            "type": "syncing",
                            "message": (
                                f"Syncing oncology-specific updates to "
                                f"{len(linked_locations)} location(s)..."
                            ),
                        }
                        for loc in linked_locations:
                            location_requirements = await _filter_requirements_for_company(
                                conn,
                                loc["company_id"],
                                requirements,
                            )
                            sync_result = await _sync_requirements_to_location(
                                conn,
                                loc["id"],
                                loc["company_id"],
                                location_requirements,
                                create_alerts=True,
                            )
                            total_alerts += sync_result["alerts"]
                            total_updated += sync_result["updated"]
                yield {
                    "type": "repository_refresh",
                    "message": (
                        f"Oncology research completed for {location_label}: "
                        f"{oncology_result.get('new', 0)} requirement(s) added."
                    ),
                }
            except Exception as exc:
                logger.warning("Oncology inline research failed: %s", exc)
                yield {
                    "type": "warning",
                    "message": f"Oncology-specific research failed: {exc}",
                }
        else:
            # Keep top-metro batch fast by queuing healthcare-only work.
            try:
                from ..services.compliance_service import HEALTHCARE_CATEGORIES
                from app.workers.tasks.healthcare_research import run_healthcare_research
                hc_existing = await conn.fetch(
                    "SELECT DISTINCT category FROM jurisdiction_requirements WHERE jurisdiction_id = $1 AND category = ANY($2::text[])",
                    canonical_jurisdiction_id,
                    sorted(HEALTHCARE_CATEGORIES),
                )
                hc_present = {r["category"] for r in hc_existing}
                hc_missing = HEALTHCARE_CATEGORIES - hc_present
                if hc_missing:
                    run_healthcare_research.delay(str(canonical_jurisdiction_id))
                    yield {
                        "type": "repository_refresh",
                        "message": f"Healthcare compliance research queued in background ({len(hc_missing)} categories).",
                    }
            except Exception as exc:
                logger.warning("Could not queue healthcare research: %s", exc)

            # Queue oncology research in background too
            try:
                from app.workers.tasks.oncology_research import run_oncology_research
                onc_existing = await conn.fetch(
                    "SELECT DISTINCT category FROM jurisdiction_requirements WHERE jurisdiction_id = $1 AND category = ANY($2::text[])",
                    canonical_jurisdiction_id,
                    sorted(ONCOLOGY_CATEGORIES),
                )
                onc_present = {r["category"] for r in onc_existing}
                onc_missing = ONCOLOGY_CATEGORIES - onc_present
                if onc_missing:
                    run_oncology_research.delay(str(canonical_jurisdiction_id))
                    yield {
                        "type": "repository_refresh",
                        "message": f"Oncology compliance research queued in background ({len(onc_missing)} categories).",
                    }
            except Exception as exc:
                logger.warning("Could not queue oncology research: %s", exc)

        yield {
            "type": "completed",
            "location": location_label,
            "new": new_count,
            "updated": total_updated,
            "alerts": total_alerts,
            "low_confidence": total_low_confidence,
            "low_confidence_requirements": low_conf_requirement_count,
            "low_confidence_legislation": low_conf_legislation_count,
            "low_confidence_changes": low_conf_change_count,
        }


async def _get_or_create_metro_jurisdiction(city: str, state: str) -> UUID:
    city_key = city.lower().strip()
    state_key = state.upper().strip()[:2]
    async with get_connection() as conn:
        try:
            county = await conn.fetchval(
                "SELECT county FROM jurisdiction_reference WHERE city = $1 AND state = $2",
                city_key,
                state_key,
            )
        except Exception:
            county = None
        display_name = f"{city.strip()}, {state_key}"
        row = await conn.fetchrow(
            """
            INSERT INTO jurisdictions (city, state, county, display_name)
            VALUES ($1, $2, $3, $4)
            ON CONFLICT (COALESCE(city, ''), state) DO UPDATE SET
                county = COALESCE(jurisdictions.county, EXCLUDED.county)
            RETURNING id
            """,
            city_key,
            state_key,
            county,
            display_name,
        )
        return row["id"]


@router.post("/jurisdictions/top-metros/check", dependencies=[Depends(require_admin)])
async def check_top_metros():
    """Run streamed compliance checks for a hardcoded top-15 metro list."""

    async def event_stream():
        total = len(TOP_15_METROS)
        succeeded = 0
        failed = 0
        low_confidence_total = 0

        yield _to_sse(
            {
                "type": "run_started",
                "total": total,
                "metros": [m["label"] for m in TOP_15_METROS],
            }
        )

        for index, metro in enumerate(TOP_15_METROS, start=1):
            city = metro["city"]
            state = metro["state"]
            label = metro["label"]
            overall_percent = int(((index - 1) / total) * 100)

            try:
                jurisdiction_id = await _get_or_create_metro_jurisdiction(city, state)
                yield _to_sse(
                    {
                        "type": "city_started",
                        "city": label,
                        "state": state,
                        "index": index,
                        "total": total,
                        "overall_percent": overall_percent,
                    }
                )

                city_summary = {
                    "new": 0,
                    "updated": 0,
                    "alerts": 0,
                    "low_confidence": 0,
                }
                async for event in _run_jurisdiction_check_events(jurisdiction_id):
                    phase = event.get("type")
                    if phase == "heartbeat":
                        yield ": heartbeat\n\n"
                        continue

                    if phase == "completed":
                        city_summary["new"] = int(event.get("new", 0) or 0)
                        city_summary["updated"] = int(event.get("updated", 0) or 0)
                        city_summary["alerts"] = int(event.get("alerts", 0) or 0)
                        city_summary["low_confidence"] = int(event.get("low_confidence", 0) or 0)
                    elif phase == "error":
                        raise RuntimeError(event.get("message") or "Jurisdiction check failed")

                    yield _to_sse(
                        {
                            "type": "city_progress",
                            "city": label,
                            "state": state,
                            "index": index,
                            "total": total,
                            "phase": phase,
                            "percent": _phase_percent(phase or ""),
                            "message": event.get("message") or event.get("location") or "",
                            "confidence": event.get("confidence"),
                        }
                    )

                succeeded += 1
                low_confidence_total += city_summary["low_confidence"]
                overall_percent = int(((succeeded + failed) / total) * 100)
                yield _to_sse(
                    {
                        "type": "city_completed",
                        "city": label,
                        "state": state,
                        "index": index,
                        "total": total,
                        "overall_percent": overall_percent,
                        "new": city_summary["new"],
                        "updated": city_summary["updated"],
                        "alerts": city_summary["alerts"],
                        "low_confidence": city_summary["low_confidence"],
                    }
                )
            except Exception as exc:
                failed += 1
                overall_percent = int(((succeeded + failed) / total) * 100)
                logger.error("Top metro check failed for %s, %s: %s", label, state, exc, exc_info=True)
                yield _to_sse(
                    {
                        "type": "city_failed",
                        "city": label,
                        "state": state,
                        "index": index,
                        "total": total,
                        "overall_percent": overall_percent,
                        "message": str(exc),
                    }
                )

        yield _to_sse(
            {
                "type": "run_completed",
                "total": total,
                "succeeded": succeeded,
                "failed": failed,
                "low_confidence_total": low_confidence_total,
            }
        )
        yield "data: [DONE]\n\n"

    return StreamingResponse(
        event_stream(),
        media_type="text/event-stream",
        headers={"X-Accel-Buffering": "no"},
    )


@router.post("/jurisdictions/{jurisdiction_id}/check", dependencies=[Depends(require_admin)])
async def check_jurisdiction(jurisdiction_id: UUID):
    """Run a compliance research check for a jurisdiction. Returns SSE stream with progress."""

    async with get_connection() as conn:
        exists = await conn.fetchval("SELECT 1 FROM jurisdictions WHERE id = $1", jurisdiction_id)
        if not exists:
            raise HTTPException(status_code=404, detail="Jurisdiction not found")

    async def event_stream():
        try:
            async for event in _run_jurisdiction_check_events(
                jurisdiction_id,
                inline_healthcare_research=True,
            ):
                if event.get("type") == "heartbeat":
                    yield ": heartbeat\n\n"
                else:
                    yield _to_sse(event)
        except HTTPException as exc:
            yield _to_sse({"type": "error", "message": str(exc.detail)})
        except Exception:
            logger.error("Jurisdiction check failed for %s", jurisdiction_id, exc_info=True)
            yield _to_sse({"type": "error", "message": "Jurisdiction check failed"})
        yield "data: [DONE]\n\n"

    return StreamingResponse(
        event_stream(),
        media_type="text/event-stream",
        headers={"X-Accel-Buffering": "no"},
    )


@router.post("/jurisdictions/{jurisdiction_id}/check-specialty", dependencies=[Depends(require_admin)])
async def check_jurisdiction_specialty(jurisdiction_id: UUID):
    """Run healthcare + oncology specialty research for a jurisdiction. Returns SSE stream."""
    from ..services.compliance_service import (
        _research_healthcare_requirements_for_jurisdiction,
        _research_oncology_requirements_for_jurisdiction,
        _jurisdiction_row_to_dict,
        _filter_requirements_for_company,
        _filter_city_level_requirements,
        _filter_with_preemption,
        _normalize_requirement_categories,
        _sync_requirements_to_location,
        _lookup_has_local_ordinance,
    )

    async with get_connection() as conn:
        j = await conn.fetchrow("SELECT id, city, state FROM jurisdictions WHERE id = $1", jurisdiction_id)
        if not j:
            raise HTTPException(status_code=404, detail="Jurisdiction not found")
        location_label = f"{_format_city_label(j['city'])}, {j['state']}"

    async def event_stream():
        try:
            async with get_connection() as conn:
                yield _to_sse({"type": "started", "location": location_label})

                # Healthcare research
                yield _to_sse({
                    "type": "researching",
                    "message": f"Researching healthcare-specific compliance for {location_label}...",
                })
                try:
                    hc_result = await _research_healthcare_requirements_for_jurisdiction(
                        conn, jurisdiction_id
                    )
                    hc_new = hc_result.get("new", 0)
                    hc_failed = hc_result.get("failed", [])
                    yield _to_sse({
                        "type": "repository_refresh",
                        "message": f"Healthcare: +{hc_new} requirement(s) added."
                            + (f" Failed: {', '.join(hc_failed)}" if hc_failed else ""),
                    })
                except Exception as exc:
                    logger.warning("Healthcare specialty research failed: %s", exc)
                    yield _to_sse({"type": "warning", "message": f"Healthcare research failed: {exc}"})

                # Oncology research
                yield _to_sse({
                    "type": "researching",
                    "message": f"Researching oncology-specific compliance for {location_label}...",
                })
                try:
                    onc_result = await _research_oncology_requirements_for_jurisdiction(
                        conn, jurisdiction_id
                    )
                    onc_new = onc_result.get("new", 0)
                    onc_failed = onc_result.get("failed", [])
                    yield _to_sse({
                        "type": "repository_refresh",
                        "message": f"Oncology: +{onc_new} requirement(s) added."
                            + (f" Failed: {', '.join(onc_failed)}" if onc_failed else ""),
                    })
                except Exception as exc:
                    logger.warning("Oncology specialty research failed: %s", exc)
                    yield _to_sse({"type": "warning", "message": f"Oncology research failed: {exc}"})

                # Sync to linked locations
                linked = await conn.fetch(
                    """SELECT bl.id, bl.company_id
                       FROM business_locations bl
                       JOIN jurisdictions j ON LOWER(bl.city) = LOWER(j.city)
                           AND UPPER(bl.state) = UPPER(j.state)
                       WHERE j.id = $1""",
                    jurisdiction_id,
                )
                if linked:
                    yield _to_sse({
                        "type": "syncing",
                        "message": f"Syncing specialty updates to {len(linked)} location(s)...",
                    })
                    rows = await conn.fetch(
                        "SELECT * FROM jurisdiction_requirements WHERE jurisdiction_id = $1",
                        jurisdiction_id,
                    )
                    requirements = [_jurisdiction_row_to_dict(dict(r)) for r in rows]
                    # Apply same prep as inline research: filter city-level if no local ordinance, normalize, preemption
                    state = j["state"]
                    has_local = await _lookup_has_local_ordinance(conn, j["city"], state)
                    if has_local is False:
                        requirements = _filter_city_level_requirements(requirements, state)
                    _normalize_requirement_categories(requirements)
                    requirements = await _filter_with_preemption(conn, requirements, state)
                    total_synced = 0
                    for loc in linked:
                        loc_reqs = await _filter_requirements_for_company(
                            conn, loc["company_id"], requirements,
                        )
                        sync_result = await _sync_requirements_to_location(
                            conn, loc["id"], loc["company_id"], loc_reqs, create_alerts=True,
                        )
                        total_synced += sync_result.get("updated", 0)
                    yield _to_sse({
                        "type": "syncing",
                        "message": f"Synced to {len(linked)} location(s), {total_synced} update(s).",
                    })

                yield _to_sse({"type": "completed", "message": "Specialty research complete."})
        except Exception:
            logger.error("Specialty check failed for %s", jurisdiction_id, exc_info=True)
            yield _to_sse({"type": "error", "message": "Specialty research failed"})
        yield "data: [DONE]\n\n"

    return StreamingResponse(
        event_stream(),
        media_type="text/event-stream",
        headers={"X-Accel-Buffering": "no"},
    )


@router.post("/jurisdictions/{jurisdiction_id}/check-medical-compliance", dependencies=[Depends(require_admin)])
async def check_jurisdiction_medical_compliance(jurisdiction_id: UUID):
    """Run medical compliance research (17 categories) for a jurisdiction. Returns SSE stream with per-category progress."""
    from ..compliance_registry import MEDICAL_COMPLIANCE_CATEGORIES, INDUSTRY_TAGS as MC_INDUSTRY_TAGS, CATEGORY_LABELS
    from ..services.compliance_service import (
        _lookup_has_local_ordinance,
        _clamp_varchar_fields,
        _upsert_requirements_additive,
        _jurisdiction_row_to_dict,
        _filter_requirements_for_company,
        _filter_city_level_requirements,
        _filter_with_preemption,
        _normalize_requirement_categories,
        _sync_requirements_to_location,
        get_recent_corrections,
        format_corrections_for_prompt,
    )
    from ..services.gemini_compliance import get_gemini_compliance_service
    from ..services.jurisdiction_context import get_known_sources, build_context_prompt, get_global_authority_sources

    async with get_connection() as conn:
        j = await conn.fetchrow("SELECT id, city, state, county FROM jurisdictions WHERE id = $1", jurisdiction_id)
        if not j:
            raise HTTPException(status_code=404, detail="Jurisdiction not found")
        location_label = f"{_format_city_label(j['city'])}, {j['state']}"

    async def event_stream():
        try:
            async with get_connection() as conn:
                yield _to_sse({"type": "started", "location": location_label})

                city = j["city"]
                state = j["state"]
                county = j.get("county")

                # Determine which categories still need research
                all_medical_cats = sorted(MEDICAL_COMPLIANCE_CATEGORIES)
                existing = await conn.fetch(
                    "SELECT DISTINCT category FROM jurisdiction_requirements WHERE jurisdiction_id = $1",
                    jurisdiction_id,
                )
                existing_cats = {r["category"] for r in existing}
                missing = [cat for cat in all_medical_cats if cat not in existing_cats]

                # Emit manifest: every category with its initial status
                yield _to_sse({
                    "type": "category_manifest",
                    "categories": [
                        {
                            "key": cat,
                            "label": CATEGORY_LABELS.get(cat, cat),
                            "status": "pending" if cat in missing else "complete",
                        }
                        for cat in all_medical_cats
                    ],
                })

                if not missing:
                    yield _to_sse({"type": "completed", "message": "All medical compliance categories already present.", "total_new": 0, "failed": []})
                    yield "data: [DONE]\n\n"
                    return

                # Gather context for Gemini prompts
                has_local_ordinance = await _lookup_has_local_ordinance(conn, city, state)
                known_sources = await get_known_sources(conn, jurisdiction_id)
                source_context = build_context_prompt(known_sources)
                source_context += get_global_authority_sources(list(MEDICAL_COMPLIANCE_CATEGORIES))
                corrections = await get_recent_corrections(jurisdiction_id)
                corrections_context = format_corrections_for_prompt(corrections)

                try:
                    preemption_rows = await conn.fetch(
                        "SELECT category, allows_local_override FROM state_preemption_rules WHERE state = $1",
                        state.upper(),
                    )
                    preemption_rules = {row["category"]: row["allows_local_override"] for row in preemption_rows}
                except Exception:
                    preemption_rules = {}

                service = get_gemini_compliance_service()
                total_new = 0
                failed_categories: List[str] = []
                category_counts: Dict[str, int] = {}

                # Mark all as researching — they run in parallel inside
                # research_location_compliance (concurrency 6-8, timeout+retry built in)
                for cat in missing:
                    yield _to_sse({
                        "type": "category_status",
                        "category": cat,
                        "status": "researching",
                    })

                try:
                    reqs = await service.research_location_compliance(
                        city=city,
                        state=state,
                        county=county,
                        categories=missing,
                        source_context=source_context,
                        corrections_context=corrections_context,
                        preemption_rules=preemption_rules,
                        has_local_ordinance=has_local_ordinance,
                    )
                    reqs = reqs or []

                    for req in reqs:
                        _clamp_varchar_fields(req)
                        cat = req.get("category", "")
                        if not req.get("applicable_industries"):
                            tag = MC_INDUSTRY_TAGS.get(cat, "healthcare")
                            req["applicable_industries"] = [tag]

                    # Count results per category
                    for r in reqs:
                        c = r.get("category", "unknown")
                        category_counts[c] = category_counts.get(c, 0) + 1

                    if reqs:
                        await _upsert_requirements_additive(conn, jurisdiction_id, reqs, research_source="manual")
                        total_new = len(reqs)

                    # Emit per-category status
                    for cat in missing:
                        count = category_counts.get(cat, 0)
                        if count > 0:
                            yield _to_sse({
                                "type": "category_status",
                                "category": cat,
                                "status": "complete",
                                "count": count,
                            })
                        else:
                            yield _to_sse({
                                "type": "category_status",
                                "category": cat,
                                "status": "empty",
                            })
                            failed_categories.append(cat)

                except Exception as e:
                    logger.warning("Medical compliance research failed: %s", e)
                    for cat in missing:
                        if cat not in category_counts:
                            yield _to_sse({
                                "type": "category_status",
                                "category": cat,
                                "status": "failed",
                                "error": str(e),
                            })
                    failed_categories = [c for c in missing if c not in category_counts]

                # Sync to linked locations
                linked = await conn.fetch(
                    """SELECT bl.id, bl.company_id
                       FROM business_locations bl
                       JOIN jurisdictions j ON LOWER(bl.city) = LOWER(j.city)
                           AND UPPER(bl.state) = UPPER(j.state)
                       WHERE j.id = $1""",
                    jurisdiction_id,
                )
                if linked:
                    yield _to_sse({
                        "type": "syncing",
                        "message": f"Syncing medical compliance updates to {len(linked)} location(s)...",
                    })
                    rows = await conn.fetch(
                        "SELECT * FROM jurisdiction_requirements WHERE jurisdiction_id = $1",
                        jurisdiction_id,
                    )
                    requirements = [_jurisdiction_row_to_dict(dict(r)) for r in rows]
                    has_local = await _lookup_has_local_ordinance(conn, city, state)
                    if has_local is False:
                        requirements = _filter_city_level_requirements(requirements, state)
                    _normalize_requirement_categories(requirements)
                    requirements = await _filter_with_preemption(conn, requirements, state)
                    total_synced = 0
                    for loc in linked:
                        loc_reqs = await _filter_requirements_for_company(
                            conn, loc["company_id"], requirements,
                        )
                        sync_result = await _sync_requirements_to_location(
                            conn, loc["id"], loc["company_id"], loc_reqs, create_alerts=True,
                        )
                        total_synced += sync_result.get("updated", 0)
                    yield _to_sse({
                        "type": "syncing",
                        "message": f"Synced to {len(linked)} location(s), {total_synced} update(s).",
                    })

                yield _to_sse({
                    "type": "completed",
                    "message": "Medical compliance research complete.",
                    "total_new": total_new,
                    "failed": failed_categories,
                    "category_counts": category_counts,
                })
        except Exception:
            logger.error("Medical compliance check failed for %s", jurisdiction_id, exc_info=True)
            yield _to_sse({"type": "error", "message": "Medical compliance research failed"})
        yield "data: [DONE]\n\n"

    return StreamingResponse(
        event_stream(),
        media_type="text/event-stream",
        headers={"X-Accel-Buffering": "no"},
    )


@router.post("/jurisdictions/{jurisdiction_id}/check-life-sciences", dependencies=[Depends(require_admin)])
async def check_jurisdiction_life_sciences(jurisdiction_id: UUID):
    """Run life sciences research (6 categories) for a jurisdiction. Returns SSE stream."""
    from ..services.compliance_service import (
        _research_life_sciences_requirements_for_jurisdiction,
        _jurisdiction_row_to_dict,
        _filter_requirements_for_company,
        _filter_city_level_requirements,
        _filter_with_preemption,
        _normalize_requirement_categories,
        _sync_requirements_to_location,
        _lookup_has_local_ordinance,
    )

    async with get_connection() as conn:
        j = await conn.fetchrow("SELECT id, city, state FROM jurisdictions WHERE id = $1", jurisdiction_id)
        if not j:
            raise HTTPException(status_code=404, detail="Jurisdiction not found")
        location_label = f"{_format_city_label(j['city'])}, {j['state']}"

    async def event_stream():
        try:
            async with get_connection() as conn:
                yield _to_sse({"type": "started", "location": location_label})

                yield _to_sse({
                    "type": "researching",
                    "message": f"Researching life sciences compliance for {location_label}...",
                })
                try:
                    ls_result = await _research_life_sciences_requirements_for_jurisdiction(
                        conn, jurisdiction_id
                    )
                    ls_new = ls_result.get("new", 0)
                    ls_failed = ls_result.get("failed", [])
                    yield _to_sse({
                        "type": "repository_refresh",
                        "message": f"Life Sciences: +{ls_new} requirement(s) added."
                            + (f" Failed: {', '.join(ls_failed)}" if ls_failed else ""),
                    })
                except Exception as exc:
                    logger.warning("Life sciences research failed: %s", exc)
                    yield _to_sse({"type": "warning", "message": f"Life sciences research failed: {exc}"})

                # Sync to linked locations
                linked = await conn.fetch(
                    """SELECT bl.id, bl.company_id
                       FROM business_locations bl
                       JOIN jurisdictions j ON LOWER(bl.city) = LOWER(j.city)
                           AND UPPER(bl.state) = UPPER(j.state)
                       WHERE j.id = $1""",
                    jurisdiction_id,
                )
                if linked:
                    yield _to_sse({
                        "type": "syncing",
                        "message": f"Syncing life sciences updates to {len(linked)} location(s)...",
                    })
                    rows = await conn.fetch(
                        "SELECT * FROM jurisdiction_requirements WHERE jurisdiction_id = $1",
                        jurisdiction_id,
                    )
                    requirements = [_jurisdiction_row_to_dict(dict(r)) for r in rows]
                    state = j["state"]
                    has_local = await _lookup_has_local_ordinance(conn, j["city"], state)
                    if has_local is False:
                        requirements = _filter_city_level_requirements(requirements, state)
                    _normalize_requirement_categories(requirements)
                    requirements = await _filter_with_preemption(conn, requirements, state)
                    total_synced = 0
                    for loc in linked:
                        loc_reqs = await _filter_requirements_for_company(
                            conn, loc["company_id"], requirements,
                        )
                        sync_result = await _sync_requirements_to_location(
                            conn, loc["id"], loc["company_id"], loc_reqs, create_alerts=True,
                        )
                        total_synced += sync_result.get("updated", 0)
                    yield _to_sse({
                        "type": "syncing",
                        "message": f"Synced to {len(linked)} location(s), {total_synced} update(s).",
                    })

                yield _to_sse({"type": "completed", "message": "Life sciences research complete."})
        except Exception:
            logger.error("Life sciences check failed for %s", jurisdiction_id, exc_info=True)
            yield _to_sse({"type": "error", "message": "Life sciences research failed"})
        yield "data: [DONE]\n\n"

    return StreamingResponse(
        event_stream(),
        media_type="text/event-stream",
        headers={"X-Accel-Buffering": "no"},
    )


@router.post("/jurisdictions/{jurisdiction_id}/check-federal-sources", dependencies=[Depends(require_admin)])
async def check_jurisdiction_federal_sources(jurisdiction_id: UUID):
    """Fetch compliance data from government APIs (Federal Register, CMS, Congress.gov). Returns SSE stream."""
    from ..services.federal_sources import fetch_federal_sources

    async with get_connection() as conn:
        j = await conn.fetchrow("SELECT id, city, state FROM jurisdictions WHERE id = $1", jurisdiction_id)
        if not j:
            raise HTTPException(status_code=404, detail="Jurisdiction not found")

    async def event_stream():
        try:
            async for event in fetch_federal_sources(jurisdiction_id):
                if event.get("type") == "heartbeat":
                    yield ": heartbeat\n\n"
                else:
                    yield _to_sse(event)
        except Exception:
            logger.error("Federal sources check failed for %s", jurisdiction_id, exc_info=True)
            yield _to_sse({"type": "error", "message": "Federal sources check failed"})
        yield "data: [DONE]\n\n"

    return StreamingResponse(
        event_stream(),
        media_type="text/event-stream",
        headers={"X-Accel-Buffering": "no"},
    )


@router.post("/jurisdictions/{jurisdiction_id}/apply-federal-sources", dependencies=[Depends(require_admin)])
async def apply_jurisdiction_federal_sources(jurisdiction_id: UUID, payload: Dict = Body(...)):
    """Apply previously fetched federal source requirements."""
    from ..services.federal_sources import apply_federal_sources

    async with get_connection() as conn:
        exists = await conn.fetchval("SELECT 1 FROM jurisdictions WHERE id = $1", jurisdiction_id)
        if not exists:
            raise HTTPException(status_code=404, detail="Jurisdiction not found")

    requirements = payload.get("requirements", [])
    if not requirements:
        raise HTTPException(status_code=400, detail="No requirements to apply")

    result = await apply_federal_sources(jurisdiction_id, requirements)
    return {"ok": True, **result}



# ──────────────────────────────────────────────────────────────────────────────
# Specialization Research Wizard
# ──────────────────────────────────────────────────────────────────────────────


class SpecializationDiscoverRequest(BaseModel):
    specialization: str
    parent_industry: str = "healthcare"


class SpecializationResearchRequest(BaseModel):
    specialization: str
    parent_industry: str = "healthcare"
    industry_tag: str
    categories: List[str]
    states: List[str]
    cities: List[dict] = []
    industry_context: str


@router.post("/specialization-research/discover", dependencies=[Depends(require_admin)])
async def discover_specialization_categories_endpoint(req: SpecializationDiscoverRequest):
    """Discover regulatory categories for a specialization via Gemini."""
    from ..services.compliance_service import discover_specialization_categories

    result = await discover_specialization_categories(req.specialization, req.parent_industry)
    return result


@router.post("/specialization-research/run", dependencies=[Depends(require_admin)])
async def run_specialization_research(req: SpecializationResearchRequest):
    """Research specialization categories across jurisdictions. Returns SSE stream."""
    from ..services.compliance_service import (
        _get_or_create_jurisdiction,
        research_specialization_for_jurisdiction,
        get_specialization_completeness,
    )

    async def event_stream():
        try:
            async with get_connection() as conn:
                # Phase 1: Resolve jurisdictions — deduplicate states so shared
                # state-level requirements are researched once, not per city.
                yield _to_sse({"type": "status", "message": "Resolving jurisdictions..."})

                # Collect all unique states (explicit + implied by cities)
                state_jurisdictions: dict[str, dict] = {}  # state_norm -> jurisdiction dict
                city_jurisdictions: list[dict] = []

                for state in req.states:
                    state_norm = state.strip().upper()
                    if state_norm not in state_jurisdictions:
                        jid = await _get_or_create_jurisdiction(conn, "", state_norm)
                        state_jurisdictions[state_norm] = {"id": jid, "label": state_norm, "city": "", "state": state_norm}

                for city_entry in req.cities:
                    city = city_entry.get("city", "").strip()
                    state = city_entry.get("state", "").strip().upper()
                    if not city or not state:
                        continue
                    # Ensure parent state is researched first
                    if state not in state_jurisdictions:
                        sid = await _get_or_create_jurisdiction(conn, "", state)
                        state_jurisdictions[state] = {"id": sid, "label": state, "city": "", "state": state}
                    jid = await _get_or_create_jurisdiction(conn, city, state)
                    city_jurisdictions.append({"id": jid, "label": f"{city}, {state}", "city": city, "state": state})

                # Order: states first, then cities — so state-level requirements
                # are in the DB before city research runs. City research will then
                # only add local ordinances (existing_cats check skips duplicates).
                all_jurisdictions = list(state_jurisdictions.values()) + city_jurisdictions
                total_count = len(all_jurisdictions)

                yield _to_sse({
                    "type": "status",
                    "message": f"Resolved {len(state_jurisdictions)} state(s) + {len(city_jurisdictions)} city/cities. Starting research...",
                })

                # Phase 2: Research each jurisdiction (states first, then cities)
                grand_total = 0
                grand_failed = []

                for j_idx, j in enumerate(all_jurisdictions, 1):
                    is_city = bool(j["city"])
                    yield _to_sse({
                        "type": "researching",
                        "jurisdiction": j["label"],
                        "progress": j_idx,
                        "total": total_count,
                    })

                    def progress_cb(cat_idx, cat_total, message):
                        pass  # inner progress handled by category events

                    result = await research_specialization_for_jurisdiction(
                        conn,
                        j["id"],
                        req.categories,
                        req.industry_tag,
                        industry_context=req.industry_context,
                        progress_callback=progress_cb,
                    )

                    grand_total += result.get("new", 0)
                    grand_failed.extend(result.get("failed", []))

                    yield _to_sse({
                        "type": "jurisdiction_complete",
                        "jurisdiction": j["label"],
                        "requirements_found": result.get("new", 0),
                        "categories_researched": len(result.get("categories", [])),
                        "failed": result.get("failed", []),
                        "skipped": result.get("skipped", False),
                        "requirements": [
                            {
                                "category": r.get("category", ""),
                                "title": (r.get("title") or "")[:120],
                                "jurisdiction_level": r.get("jurisdiction_level", ""),
                            }
                            for r in (result.get("requirements") or [])[:40]
                        ],
                    })

                # Phase 3: Completeness summary
                completeness = await get_specialization_completeness(
                    conn, req.industry_tag, expected_categories=req.categories,
                )

                yield _to_sse({
                    "type": "completed",
                    "summary": {
                        "specialization": req.specialization,
                        "industry_tag": req.industry_tag,
                        "total_requirements": grand_total,
                        "jurisdictions_researched": len(all_jurisdictions),
                        "categories_requested": len(req.categories),
                        "failed_categories": list(set(grand_failed)),
                        "completeness": completeness,
                    },
                })
        except Exception:
            logger.error("Specialization research failed", exc_info=True)
            yield _to_sse({"type": "error", "message": "Specialization research failed"})
        yield "data: [DONE]\n\n"

    return StreamingResponse(
        event_stream(),
        media_type="text/event-stream",
        headers={"X-Accel-Buffering": "no"},
    )


@router.get("/specialization-research/completeness", dependencies=[Depends(require_admin)])
async def get_specialization_completeness_endpoint(
    industry_tag: str = Query(...),
    categories: str = Query(""),
):
    """Get completeness data for a specialization across jurisdictions."""
    from ..services.compliance_service import get_specialization_completeness

    expected = [c.strip() for c in categories.split(",") if c.strip()] or None
    async with get_connection() as conn:
        result = await get_specialization_completeness(conn, industry_tag, expected_categories=expected)
    return result


@router.get("/schedulers", dependencies=[Depends(require_admin)])
async def list_schedulers():
    """List all scheduler settings with live stats."""
    async with get_connection() as conn:
        settings = await conn.fetch(
            "SELECT * FROM scheduler_settings ORDER BY created_at"
        )

        result = []
        for row in settings:
            item = {
                "id": str(row["id"]),
                "task_key": row["task_key"],
                "display_name": row["display_name"],
                "description": row["description"],
                "enabled": row["enabled"],
                "max_per_cycle": row["max_per_cycle"],
                "created_at": row["created_at"].isoformat() if row["created_at"] else None,
                "updated_at": row["updated_at"].isoformat() if row["updated_at"] else None,
                "stats": {},
            }

            if row["task_key"] == "compliance_checks":
                stats = await conn.fetchrow("""
                    SELECT
                        (SELECT COUNT(*) FROM business_locations WHERE is_active = true) AS total_locations,
                        (SELECT COUNT(*) FROM business_locations WHERE auto_check_enabled = true AND is_active = true) AS auto_check_enabled,
                        (SELECT MIN(next_auto_check) FROM business_locations WHERE auto_check_enabled = true AND is_active = true) AS next_due,
                        (SELECT COUNT(*) FROM compliance_check_log WHERE started_at > NOW() - INTERVAL '24 hours') AS checks_24h,
                        (SELECT COUNT(*) FROM compliance_check_log WHERE started_at > NOW() - INTERVAL '24 hours' AND status = 'failed') AS failed_24h
                """)
                last_run = await conn.fetchrow(
                    "SELECT started_at, status FROM compliance_check_log ORDER BY started_at DESC LIMIT 1"
                )
                item["stats"] = {
                    "total_locations": stats["total_locations"],
                    "auto_check_enabled": stats["auto_check_enabled"],
                    "next_due": stats["next_due"].isoformat() if stats["next_due"] else None,
                    "checks_24h": stats["checks_24h"],
                    "failed_24h": stats["failed_24h"],
                    "last_run": last_run["started_at"].isoformat() if last_run else None,
                    "last_run_status": last_run["status"] if last_run else None,
                }

            elif row["task_key"] == "deadline_escalation":
                stats = await conn.fetchrow("""
                    SELECT
                        (SELECT COUNT(*) FROM upcoming_legislation
                         WHERE current_status NOT IN ('effective', 'dismissed')
                           AND expected_effective_date IS NOT NULL) AS active_count
                """)
                item["stats"] = {
                    "active_legislation": stats["active_count"],
                }
            elif row["task_key"] == "onboarding_reminders":
                stats = await conn.fetchrow(
                    """
                    SELECT
                        (
                            SELECT COUNT(*)
                            FROM employee_onboarding_tasks eot
                            WHERE eot.status = 'pending'
                              AND eot.due_date IS NOT NULL
                              AND eot.due_date < CURRENT_DATE
                        ) AS overdue_tasks,
                        (
                            SELECT COUNT(*)
                            FROM employee_onboarding_tasks eot
                            WHERE eot.status = 'pending'
                              AND eot.due_date IS NOT NULL
                              AND eot.due_date BETWEEN CURRENT_DATE AND CURRENT_DATE + INTERVAL '3 days'
                        ) AS due_soon_tasks
                    """
                )
                item["stats"] = {
                    "overdue_tasks": stats["overdue_tasks"],
                    "due_soon_tasks": stats["due_soon_tasks"],
                }
            elif row["task_key"] == "risk_assessment":
                ra_stats = await conn.fetchrow("""
                    SELECT
                        (SELECT COUNT(DISTINCT company_id) FROM risk_assessment_history) AS total_assessed,
                        (SELECT COUNT(*) FROM risk_assessment_history WHERE computed_at > NOW() - INTERVAL '7 days') AS assessments_7d,
                        (SELECT COUNT(*) FROM companies WHERE next_risk_assessment IS NOT NULL AND next_risk_assessment <= NOW()) AS due_now
                """)
                last_run = await conn.fetchrow(
                    "SELECT computed_at, source FROM risk_assessment_history ORDER BY computed_at DESC LIMIT 1"
                )
                item["stats"] = {
                    "total_assessed": ra_stats["total_assessed"],
                    "assessments_7d": ra_stats["assessments_7d"],
                    "due_now": ra_stats["due_now"],
                    "last_run": last_run["computed_at"].isoformat() if last_run else None,
                    "last_source": last_run["source"] if last_run else None,
                }

            result.append(item)

        return result


@router.patch("/schedulers/{task_key}", dependencies=[Depends(require_admin)])
async def update_scheduler(task_key: str, request: SchedulerUpdateRequest):
    """Update scheduler settings (enabled, max_per_cycle)."""
    async with get_connection() as conn:
        existing = await conn.fetchrow(
            "SELECT * FROM scheduler_settings WHERE task_key = $1", task_key
        )
        if not existing:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Scheduler not found")

        updates = []
        params = []
        idx = 1

        if request.enabled is not None:
            updates.append(f"enabled = ${idx}")
            params.append(request.enabled)
            idx += 1
        if request.max_per_cycle is not None:
            updates.append(f"max_per_cycle = ${idx}")
            params.append(request.max_per_cycle)
            idx += 1

        if not updates:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="No fields to update")

        updates.append(f"updated_at = NOW()")
        params.append(task_key)

        row = await conn.fetchrow(
            f"UPDATE scheduler_settings SET {', '.join(updates)} WHERE task_key = ${idx} RETURNING *",
            *params,
        )
        return {
            "id": str(row["id"]),
            "task_key": row["task_key"],
            "display_name": row["display_name"],
            "description": row["description"],
            "enabled": row["enabled"],
            "max_per_cycle": row["max_per_cycle"],
            "updated_at": row["updated_at"].isoformat() if row["updated_at"] else None,
        }


@router.post("/schedulers/{task_key}/trigger", dependencies=[Depends(require_admin)])
async def trigger_scheduler(task_key: str):
    """Manually trigger a scheduler task."""
    async with get_connection() as conn:
        existing = await conn.fetchrow(
            "SELECT * FROM scheduler_settings WHERE task_key = $1", task_key
        )
        if not existing:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Scheduler not found")

    from ...workers.tasks.compliance_checks import (
        enqueue_scheduled_compliance_checks,
        run_deadline_escalation,
    )
    from ...workers.tasks.leave_agent_tasks import run_leave_agent_orchestration
    from ...workers.tasks.onboarding_reminders import run_onboarding_reminders

    if task_key == "compliance_checks":
        enqueue_scheduled_compliance_checks.delay()
        return {"status": "triggered", "task_key": task_key, "message": "Compliance checks enqueued"}
    elif task_key == "deadline_escalation":
        run_deadline_escalation.delay()
        return {"status": "triggered", "task_key": task_key, "message": "Deadline escalation enqueued"}
    elif task_key == "leave_agent_orchestration":
        run_leave_agent_orchestration.delay()
        return {"status": "triggered", "task_key": task_key, "message": "Leave agent orchestration enqueued"}
    elif task_key == "onboarding_reminders":
        run_onboarding_reminders.delay()
        return {"status": "triggered", "task_key": task_key, "message": "Onboarding reminders enqueued"}
    elif task_key == "risk_assessment":
        from ...workers.tasks.risk_assessment import enqueue_scheduled_risk_assessments
        enqueue_scheduled_risk_assessments.delay()
        return {"status": "triggered", "task_key": task_key, "message": "Risk assessment enqueued"}
    elif task_key == "auto_archive":
        from ...workers.tasks.auto_archive import run_auto_archive
        run_auto_archive.delay()
        return {"status": "triggered", "task_key": task_key, "message": "Auto-archive enqueued"}
    else:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=f"Unknown task key: {task_key}")


@router.get("/schedulers/stats", dependencies=[Depends(require_admin)])
async def scheduler_stats():
    """Aggregate stats and recent activity for schedulers."""
    async with get_connection() as conn:
        overview = await conn.fetchrow("""
            SELECT
                (SELECT COUNT(*) FROM business_locations WHERE is_active = true) AS total_locations,
                (SELECT COUNT(*) FROM business_locations WHERE auto_check_enabled = true AND is_active = true) AS auto_check_enabled,
                (SELECT COUNT(*) FROM compliance_check_log WHERE started_at > NOW() - INTERVAL '24 hours') AS checks_24h,
                (SELECT COUNT(*) FROM compliance_check_log WHERE started_at > NOW() - INTERVAL '24 hours' AND status = 'failed') AS failed_24h
        """)

        recent_logs = await conn.fetch("""
            SELECT
                cl.id,
                cl.location_id,
                cl.company_id,
                bl.name AS location_name,
                cl.check_type,
                cl.status,
                cl.started_at,
                cl.completed_at,
                cl.new_count,
                cl.updated_count,
                cl.alert_count,
                cl.error_message
            FROM compliance_check_log cl
            LEFT JOIN business_locations bl ON bl.id = cl.location_id
            ORDER BY cl.started_at DESC
            LIMIT 20
        """)

        return {
            "overview": {
                "total_locations": overview["total_locations"],
                "auto_check_enabled": overview["auto_check_enabled"],
                "checks_24h": overview["checks_24h"],
                "failed_24h": overview["failed_24h"],
            },
            "recent_logs": [
                {
                    "id": str(row["id"]),
                    "location_id": str(row["location_id"]),
                    "company_id": str(row["company_id"]),
                    "location_name": row["location_name"],
                    "check_type": row["check_type"],
                    "status": row["status"],
                    "started_at": row["started_at"].isoformat() if row["started_at"] else None,
                    "completed_at": row["completed_at"].isoformat() if row["completed_at"] else None,
                    "duration_seconds": (
                        (row["completed_at"] - row["started_at"]).total_seconds()
                        if row["completed_at"] and row["started_at"] else None
                    ),
                    "new_count": row["new_count"],
                    "updated_count": row["updated_count"],
                    "alert_count": row["alert_count"],
                    "error_message": row["error_message"],
                }
                for row in recent_logs
            ],
        }


# =============================================================================
# Scheduler Location Overrides
# =============================================================================

class LocationScheduleUpdateRequest(BaseModel):
    """Request model for updating a location's auto-check schedule."""
    auto_check_enabled: Optional[bool] = None
    auto_check_interval_days: Optional[int] = None
    next_auto_check_minutes: Optional[int] = None  # override next_auto_check to N minutes from now


@router.get("/schedulers/locations", dependencies=[Depends(require_admin)])
async def list_scheduler_locations():
    """List all business locations grouped by company, with auto-check schedule fields."""
    async with get_connection() as conn:
        rows = await conn.fetch("""
            SELECT
                bl.id AS location_id,
                bl.name AS location_name,
                bl.city,
                bl.state,
                bl.auto_check_enabled,
                bl.auto_check_interval_days,
                bl.next_auto_check,
                bl.company_id,
                c.name AS company_name,
                (SELECT MAX(cl.started_at) FROM compliance_check_log cl WHERE cl.location_id = bl.id) AS last_compliance_check
            FROM business_locations bl
            JOIN companies c ON c.id = bl.company_id
            WHERE bl.is_active = true
            ORDER BY c.name, bl.name
        """)

        grouped: dict[str, dict] = {}
        for row in rows:
            cid = str(row["company_id"])
            if cid not in grouped:
                grouped[cid] = {
                    "company_id": cid,
                    "company_name": row["company_name"],
                    "locations": [],
                }
            grouped[cid]["locations"].append({
                "id": str(row["location_id"]),
                "name": row["location_name"],
                "city": row["city"],
                "state": row["state"],
                "auto_check_enabled": row["auto_check_enabled"],
                "auto_check_interval_days": row["auto_check_interval_days"],
                "next_auto_check": row["next_auto_check"].isoformat() if row["next_auto_check"] else None,
                "last_compliance_check": row["last_compliance_check"].isoformat() if row["last_compliance_check"] else None,
            })

        return list(grouped.values())


@router.patch("/schedulers/locations/{location_id}", dependencies=[Depends(require_admin)])
async def update_scheduler_location(location_id: UUID, request: LocationScheduleUpdateRequest):
    """Admin override: update auto_check_enabled and/or auto_check_interval_days for any location."""
    async with get_connection() as conn:
        loc = await conn.fetchrow(
            "SELECT id, company_id FROM business_locations WHERE id = $1 AND is_active = true",
            location_id,
        )
        if not loc:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Location not found")

        # If next_auto_check_minutes is set, directly override next_auto_check in the DB
        if request.next_auto_check_minutes is not None:
            await conn.execute(
                "UPDATE business_locations SET next_auto_check = NOW() + $1 * INTERVAL '1 minute', auto_check_enabled = true, updated_at = NOW() WHERE id = $2",
                request.next_auto_check_minutes, location_id,
            )

        # Apply normal auto-check settings if provided
        if request.auto_check_enabled is not None or request.auto_check_interval_days is not None:
            settings = AutoCheckSettings(
                auto_check_enabled=request.auto_check_enabled,
                auto_check_interval_days=request.auto_check_interval_days,
            )
            await update_auto_check_settings(location_id, loc["company_id"], settings)

        # Re-read for response
        row = await conn.fetchrow(
            "SELECT id, auto_check_enabled, auto_check_interval_days, next_auto_check FROM business_locations WHERE id = $1",
            location_id,
        )
        return {
            "id": str(row["id"]),
            "auto_check_enabled": row["auto_check_enabled"],
            "auto_check_interval_days": row["auto_check_interval_days"],
            "next_auto_check": row["next_auto_check"].isoformat() if row["next_auto_check"] else None,
        }


# ===========================================
# Admin Poster Management
# ===========================================

def _fmt_dt(dt) -> Optional[str]:
    return dt.isoformat() if dt else None


@router.get("/posters/templates", dependencies=[Depends(require_admin)])
async def list_poster_templates():
    """List all poster templates with jurisdiction info."""
    async with get_connection() as conn:
        rows = await conn.fetch(
            """
            SELECT pt.*, j.city, j.state, j.county
            FROM poster_templates pt
            JOIN jurisdictions j ON pt.jurisdiction_id = j.id
            ORDER BY j.state, j.city
            """
        )
        templates = []
        for r in rows:
            j_name = f"{r['city']}, {r['state']}"
            if r["county"]:
                j_name = f"{r['city']}, {r['county']} County, {r['state']}"
            templates.append({
                "id": str(r["id"]),
                "jurisdiction_id": str(r["jurisdiction_id"]),
                "title": r["title"],
                "description": r["description"],
                "version": r["version"],
                "pdf_url": r["pdf_url"],
                "pdf_generated_at": _fmt_dt(r["pdf_generated_at"]),
                "categories_included": r["categories_included"],
                "requirement_count": r["requirement_count"],
                "status": r["status"],
                "jurisdiction_name": j_name,
                "state": r["state"],
                "created_at": _fmt_dt(r["created_at"]),
                "updated_at": _fmt_dt(r["updated_at"]),
            })
        return {"templates": templates, "total": len(templates)}


@router.post("/posters/templates/{jurisdiction_id}", dependencies=[Depends(require_admin)])
async def generate_poster_template(jurisdiction_id: UUID):
    """Generate or regenerate a compliance poster PDF for a jurisdiction."""
    from ..services.poster_service import generate_poster_pdf

    async with get_connection() as conn:
        j = await conn.fetchrow("SELECT id FROM jurisdictions WHERE id = $1", jurisdiction_id)
        if not j:
            raise HTTPException(status_code=404, detail="Jurisdiction not found")

        result = await generate_poster_pdf(conn, jurisdiction_id)
        return result


@router.post("/posters/generate-all", dependencies=[Depends(require_admin)])
async def generate_all_missing_posters():
    """Generate poster templates for all jurisdictions that have poster-worthy
    requirement data but no template yet."""
    from ..services.poster_service import generate_all_missing_posters as _generate_all

    async with get_connection() as conn:
        result = await _generate_all(conn)
        return result


@router.get("/posters/orders", dependencies=[Depends(require_admin)])
async def list_poster_orders(
    status_filter: Optional[str] = Query(None, alias="status"),
):
    """List all poster orders with optional status filter."""
    async with get_connection() as conn:
        query = """
            SELECT po.*,
                   comp.name AS company_name,
                   bl.name AS location_name, bl.city AS location_city, bl.state AS location_state,
                   u.email AS requested_by_email
            FROM poster_orders po
            JOIN companies comp ON po.company_id = comp.id
            JOIN business_locations bl ON po.location_id = bl.id
            LEFT JOIN users u ON po.requested_by = u.id
        """
        params = []
        if status_filter:
            query += " WHERE po.status = $1"
            params.append(status_filter)
        query += " ORDER BY po.created_at DESC"

        rows = await conn.fetch(query, *params)

        orders = []
        for r in rows:
            # Fetch items for this order
            items = await conn.fetch(
                """
                SELECT poi.*, pt.title AS template_title,
                       j.city || ', ' || j.state AS jurisdiction_name
                FROM poster_order_items poi
                JOIN poster_templates pt ON poi.template_id = pt.id
                JOIN jurisdictions j ON pt.jurisdiction_id = j.id
                WHERE poi.order_id = $1
                """,
                r["id"],
            )
            orders.append({
                "id": str(r["id"]),
                "company_id": str(r["company_id"]),
                "location_id": str(r["location_id"]),
                "status": r["status"],
                "requested_by": str(r["requested_by"]) if r["requested_by"] else None,
                "admin_notes": r["admin_notes"],
                "quote_amount": float(r["quote_amount"]) if r["quote_amount"] else None,
                "shipping_address": r["shipping_address"],
                "tracking_number": r["tracking_number"],
                "shipped_at": _fmt_dt(r["shipped_at"]),
                "delivered_at": _fmt_dt(r["delivered_at"]),
                "metadata": r["metadata"],
                "created_at": _fmt_dt(r["created_at"]),
                "updated_at": _fmt_dt(r["updated_at"]),
                "company_name": r["company_name"],
                "location_name": r["location_name"],
                "location_city": r["location_city"],
                "location_state": r["location_state"],
                "requested_by_email": r["requested_by_email"],
                "items": [
                    {
                        "id": str(i["id"]),
                        "template_id": str(i["template_id"]),
                        "quantity": i["quantity"],
                        "template_title": i["template_title"],
                        "jurisdiction_name": i["jurisdiction_name"],
                    }
                    for i in items
                ],
            })
        return {"orders": orders, "total": len(orders)}


@router.get("/posters/orders/{order_id}", dependencies=[Depends(require_admin)])
async def get_poster_order(order_id: UUID):
    """Get poster order detail."""
    async with get_connection() as conn:
        r = await conn.fetchrow(
            """
            SELECT po.*,
                   comp.name AS company_name,
                   bl.name AS location_name, bl.city AS location_city, bl.state AS location_state,
                   u.email AS requested_by_email
            FROM poster_orders po
            JOIN companies comp ON po.company_id = comp.id
            JOIN business_locations bl ON po.location_id = bl.id
            LEFT JOIN users u ON po.requested_by = u.id
            WHERE po.id = $1
            """,
            order_id,
        )
        if not r:
            raise HTTPException(status_code=404, detail="Order not found")

        items = await conn.fetch(
            """
            SELECT poi.*, pt.title AS template_title,
                   j.city || ', ' || j.state AS jurisdiction_name
            FROM poster_order_items poi
            JOIN poster_templates pt ON poi.template_id = pt.id
            JOIN jurisdictions j ON pt.jurisdiction_id = j.id
            WHERE poi.order_id = $1
            """,
            order_id,
        )
        return {
            "id": str(r["id"]),
            "company_id": str(r["company_id"]),
            "location_id": str(r["location_id"]),
            "status": r["status"],
            "requested_by": str(r["requested_by"]) if r["requested_by"] else None,
            "admin_notes": r["admin_notes"],
            "quote_amount": float(r["quote_amount"]) if r["quote_amount"] else None,
            "shipping_address": r["shipping_address"],
            "tracking_number": r["tracking_number"],
            "shipped_at": _fmt_dt(r["shipped_at"]),
            "delivered_at": _fmt_dt(r["delivered_at"]),
            "metadata": r["metadata"],
            "created_at": _fmt_dt(r["created_at"]),
            "updated_at": _fmt_dt(r["updated_at"]),
            "company_name": r["company_name"],
            "location_name": r["location_name"],
            "location_city": r["location_city"],
            "location_state": r["location_state"],
            "requested_by_email": r["requested_by_email"],
            "items": [
                {
                    "id": str(i["id"]),
                    "template_id": str(i["template_id"]),
                    "quantity": i["quantity"],
                    "template_title": i["template_title"],
                    "jurisdiction_name": i["jurisdiction_name"],
                }
                for i in items
            ],
        }


class PosterOrderUpdateRequest(BaseModel):
    status: Optional[str] = None
    admin_notes: Optional[str] = None
    quote_amount: Optional[float] = None
    tracking_number: Optional[str] = None


VALID_ORDER_STATUSES = {"requested", "quoted", "processing", "shipped", "delivered", "cancelled"}


@router.patch("/posters/orders/{order_id}", dependencies=[Depends(require_admin)])
async def update_poster_order(order_id: UUID, request: PosterOrderUpdateRequest):
    """Update a poster order (status, notes, quote, tracking)."""
    async with get_connection() as conn:
        existing = await conn.fetchrow(
            "SELECT id, status FROM poster_orders WHERE id = $1", order_id,
        )
        if not existing:
            raise HTTPException(status_code=404, detail="Order not found")

        updates = []
        params = []
        idx = 1

        if request.status is not None:
            if request.status not in VALID_ORDER_STATUSES:
                raise HTTPException(status_code=400, detail=f"Invalid status: {request.status}")
            updates.append(f"status = ${idx}")
            params.append(request.status)
            idx += 1

            # Auto-set timestamps
            if request.status == "shipped":
                updates.append(f"shipped_at = NOW()")
            elif request.status == "delivered":
                updates.append(f"delivered_at = NOW()")

        if request.admin_notes is not None:
            updates.append(f"admin_notes = ${idx}")
            params.append(request.admin_notes)
            idx += 1

        if request.quote_amount is not None:
            updates.append(f"quote_amount = ${idx}")
            params.append(request.quote_amount)
            idx += 1

        if request.tracking_number is not None:
            updates.append(f"tracking_number = ${idx}")
            params.append(request.tracking_number)
            idx += 1

        if not updates:
            raise HTTPException(status_code=400, detail="No updates provided")

        updates.append("updated_at = NOW()")
        params.append(order_id)

        await conn.execute(
            f"UPDATE poster_orders SET {', '.join(updates)} WHERE id = ${idx}",
            *params,
        )

        return {"status": "updated", "order_id": str(order_id)}


@router.get("/platform-settings", response_model=PlatformSettingsResponse, dependencies=[Depends(require_admin)])
async def get_all_platform_settings():
    visible = await get_visible_features()
    mw_mode = await get_matcha_work_model_mode()
    jr_mode = await get_jurisdiction_research_model_mode()
    er_weights = await get_er_similarity_weights()
    return {
        "visible_features": visible,
        "matcha_work_model_mode": mw_mode,
        "jurisdiction_research_model_mode": jr_mode,
        "er_similarity_weights": er_weights,
    }


@router.get("/platform-settings/features")
async def get_platform_features(admin=Depends(require_admin)):
    visible = await get_visible_features()
    return {"visible_features": visible}


@router.put("/platform-settings/features")
async def update_platform_features(
    body: PlatformFeaturesUpdate,
    admin=Depends(require_admin)
):
    unknown = [k for k in body.visible_features if k not in KNOWN_PLATFORM_ITEMS]
    if unknown:
        raise HTTPException(status_code=400, detail=f"Unknown feature keys: {unknown}")
    async with get_connection() as conn:
        await conn.execute(
            """
            INSERT INTO platform_settings (key, value, updated_at)
            VALUES ('visible_features', $1::jsonb, NOW())
            ON CONFLICT (key) DO UPDATE SET value = EXCLUDED.value, updated_at = NOW()
            """,
            json.dumps(body.visible_features)
        )
    visible = prime_visible_features_cache(body.visible_features)
    return {"visible_features": visible}


@router.put("/platform-settings/matcha-work-model-mode", dependencies=[Depends(require_admin)])
async def update_matcha_work_model_mode(
    body: MatchaWorkModelModeUpdate,
    admin=Depends(require_admin)
):
    async with get_connection() as conn:
        await conn.execute(
            """
            INSERT INTO platform_settings (key, value, updated_at)
            VALUES ('matcha_work_model_mode', $1::jsonb, NOW())
            ON CONFLICT (key) DO UPDATE SET value = EXCLUDED.value, updated_at = NOW()
            """,
            json.dumps(body.mode)
        )
    mode = prime_matcha_work_model_mode_cache(body.mode)
    return {"matcha_work_model_mode": mode}


@router.put("/platform-settings/jurisdiction-research-model-mode", dependencies=[Depends(require_admin)])
async def update_jurisdiction_research_model_mode(
    body: JurisdictionResearchModelModeUpdate,
    admin=Depends(require_admin)
):
    async with get_connection() as conn:
        await conn.execute(
            """
            INSERT INTO platform_settings (key, value, updated_at)
            VALUES ('jurisdiction_research_model_mode', $1::jsonb, NOW())
            ON CONFLICT (key) DO UPDATE SET value = EXCLUDED.value, updated_at = NOW()
            """,
            json.dumps(body.mode)
        )
    mode = prime_jurisdiction_research_model_mode_cache(body.mode)
    return {"jurisdiction_research_model_mode": mode}


@router.get("/platform-settings/er-similarity-weights", dependencies=[Depends(require_admin)])
async def get_er_similarity_weights_endpoint():
    weights = await get_er_similarity_weights()
    return {"er_similarity_weights": weights}


@router.put("/platform-settings/er-similarity-weights", dependencies=[Depends(require_admin)])
async def update_er_similarity_weights(
    body: ERSimilarityWeightsUpdate,
    admin=Depends(require_admin)
):
    if set(body.weights.keys()) != EXPECTED_WEIGHT_KEYS:
        raise HTTPException(
            status_code=400,
            detail=f"Keys must be exactly: {sorted(EXPECTED_WEIGHT_KEYS)}"
        )
    for k, v in body.weights.items():
        if not (0.0 <= v <= 1.0):
            raise HTTPException(status_code=400, detail=f"Weight '{k}' must be between 0 and 1")
    weight_sum = sum(body.weights.values())
    if abs(weight_sum - 1.0) > 0.05:
        raise HTTPException(status_code=400, detail=f"Weights must sum to ~1.0 (got {weight_sum:.3f})")

    async with get_connection() as conn:
        await conn.execute(
            """
            INSERT INTO platform_settings (key, value, updated_at)
            VALUES ('er_similarity_weights', $1::jsonb, NOW())
            ON CONFLICT (key) DO UPDATE SET value = EXCLUDED.value, updated_at = NOW()
            """,
            json.dumps(body.weights)
        )
    weights = prime_er_similarity_weights_cache(body.weights)
    return {"er_similarity_weights": weights}


# ── Industry Compliance Profiles ──────────────────────────────────────────────

class IndustryProfileCreate(BaseModel):
    name: str = Field(..., max_length=100)
    description: Optional[str] = None
    focused_categories: list[str]
    rate_types: Optional[list[str]] = None
    category_order: list[str]
    category_evidence: Optional[dict] = None


class IndustryProfileUpdate(BaseModel):
    name: Optional[str] = Field(None, max_length=100)
    description: Optional[str] = None
    focused_categories: Optional[list[str]] = None
    rate_types: Optional[list[str]] = None
    category_order: Optional[list[str]] = None
    category_evidence: Optional[dict] = None


def _profile_row_to_dict(r) -> dict:
    evidence = r["category_evidence"]
    if isinstance(evidence, str):
        evidence = json.loads(evidence)
    return {
        "id": str(r["id"]),
        "name": r["name"],
        "description": r["description"],
        "focused_categories": list(r["focused_categories"]),
        "rate_types": list(r["rate_types"]) if r["rate_types"] else [],
        "category_order": list(r["category_order"]),
        "category_evidence": evidence,
        "created_at": r["created_at"].isoformat() if r["created_at"] else None,
        "updated_at": r["updated_at"].isoformat() if r["updated_at"] else None,
    }


@router.get("/industry-profiles", dependencies=[Depends(require_admin)])
async def list_industry_profiles():
    async with get_connection() as conn:
        rows = await conn.fetch(
            "SELECT * FROM industry_compliance_profiles ORDER BY name"
        )
    return [_profile_row_to_dict(r) for r in rows]


@router.post("/industry-profiles", dependencies=[Depends(require_admin)], status_code=201)
async def create_industry_profile(body: IndustryProfileCreate):
    evidence_json = json.dumps(body.category_evidence) if body.category_evidence else None
    async with get_connection() as conn:
        try:
            row = await conn.fetchrow(
                """
                INSERT INTO industry_compliance_profiles (name, description, focused_categories, rate_types, category_order, category_evidence)
                VALUES ($1, $2, $3, $4, $5, $6::jsonb)
                RETURNING *
                """,
                body.name, body.description, body.focused_categories,
                body.rate_types or [], body.category_order, evidence_json,
            )
        except asyncpg.UniqueViolationError:
            raise HTTPException(status_code=409, detail="Profile name already exists")
    return _profile_row_to_dict(row)


@router.put("/industry-profiles/{profile_id}", dependencies=[Depends(require_admin)])
async def update_industry_profile(profile_id: UUID, body: IndustryProfileUpdate):
    sets = []
    vals: list[Any] = []
    idx = 1
    for field in ("name", "description", "focused_categories", "rate_types", "category_order"):
        val = getattr(body, field)
        if val is not None:
            sets.append(f"{field} = ${idx}")
            vals.append(val)
            idx += 1
    if body.category_evidence is not None:
        sets.append(f"category_evidence = ${idx}::jsonb")
        vals.append(json.dumps(body.category_evidence))
        idx += 1
    if not sets:
        raise HTTPException(status_code=400, detail="No fields to update")
    sets.append(f"updated_at = NOW()")
    vals.append(profile_id)
    async with get_connection() as conn:
        row = await conn.fetchrow(
            f"UPDATE industry_compliance_profiles SET {', '.join(sets)} WHERE id = ${idx} RETURNING *",
            *vals,
        )
    if not row:
        raise HTTPException(status_code=404, detail="Profile not found")
    return _profile_row_to_dict(row)


@router.delete("/industry-profiles/{profile_id}", dependencies=[Depends(require_admin)])
async def delete_industry_profile(profile_id: UUID):
    async with get_connection() as conn:
        result = await conn.execute(
            "DELETE FROM industry_compliance_profiles WHERE id = $1", profile_id
        )
    if result == "DELETE 0":
        raise HTTPException(status_code=404, detail="Profile not found")
    return {"deleted": True}


# ---------------------------------------------------------------------------
# Industry requirements matrix
# ---------------------------------------------------------------------------

@router.get("/industry-requirements-matrix", dependencies=[Depends(require_admin)])
async def get_industry_requirements_matrix(
    industry: str = Query("healthcare"),
    specialties: Optional[str] = Query(None),
    entity_type: Optional[str] = Query(None),
    payer_contracts: Optional[str] = Query(None),
):
    """Return a matrix of compliance categories applicable to an industry,
    annotated with jurisdiction data coverage and trigger-profile sourcing."""

    specialty_list = [s.strip() for s in specialties.split(",") if s.strip()] if specialties else []
    payer_list = [p.strip() for p in payer_contracts.split(",") if p.strip()] if payer_contracts else []

    async with get_connection() as conn:
        # 1. Load the industry profile
        profile_row = await conn.fetchrow(
            "SELECT * FROM industry_compliance_profiles WHERE name ILIKE $1",
            industry,
        )
        # 2. Load all compliance categories
        cat_rows = await conn.fetch(
            "SELECT slug, name, description, domain::text, \"group\", industry_tag, sort_order "
            "FROM compliance_categories ORDER BY sort_order, slug"
        )

    if not cat_rows:
        raise HTTPException(status_code=404, detail="No compliance categories found")

    cats_by_slug = {r["slug"]: dict(r) for r in cat_rows}
    focused_categories = list(profile_row["focused_categories"]) if profile_row else []

    # 3. Determine activated trigger profiles
    active_triggers = []
    triggered_cats: dict[str, list[str]] = {}  # slug -> list of trigger keys

    for tp in TRIGGER_PROFILES:
        activated = False
        if tp.attribute_key == "entity_type" and entity_type and tp.attribute_match == entity_type:
            activated = True
        elif tp.attribute_key == "payer_contracts" and tp.attribute_match in payer_list:
            activated = True

        if activated:
            active_triggers.append({
                "key": tp.key,
                "label": tp.label,
                "categories": list(tp.applicable_categories),
            })
            for cat_slug in tp.applicable_categories:
                triggered_cats.setdefault(cat_slug, []).append(tp.key)

    # 4. Classify each category and determine the applicable set
    applicable_slugs: list[str] = []
    source_map: dict[str, str] = {}
    triggered_by_map: dict[str, list[str]] = {}

    for slug, cat in cats_by_slug.items():
        tag = cat.get("industry_tag") or ""
        sources: list[str] = []

        # focused: in the industry profile's focused_categories
        if slug in focused_categories:
            sources.append("focused")

        # base: industry_tag matches industry exactly
        if tag.lower() == industry.lower():
            sources.append("base")

        # specialty: industry_tag starts with "industry:" and suffix matches a selected specialty
        if ":" in tag:
            prefix, suffix = tag.split(":", 1)
            if prefix.lower() == industry.lower() and suffix.lower() in [s.lower() for s in specialty_list]:
                sources.append("specialty")

        # triggered: appears in an activated trigger profile
        if slug in triggered_cats:
            sources.append("triggered")
            triggered_by_map[slug] = triggered_cats[slug]

        if sources:
            applicable_slugs.append(slug)
            # Priority: triggered > specialty > base > focused
            for priority in ("triggered", "specialty", "base", "focused"):
                if priority in sources:
                    source_map[slug] = priority
                    break

    if not applicable_slugs:
        return {
            "summary": {"total": 0, "with_data": 0, "missing_data": 0},
            "industry_profile": {
                "name": profile_row["name"] if profile_row else industry,
                "focused_categories": focused_categories,
            },
            "active_triggers": active_triggers,
            "categories": [],
        }

    # 5. Query jurisdiction data counts for applicable categories
    async with get_connection() as conn:
        data_rows = await conn.fetch(
            "SELECT category, COUNT(*) AS req_count, COUNT(DISTINCT jurisdiction_id) AS jur_count "
            "FROM jurisdiction_requirements "
            "WHERE category = ANY($1::text[]) "
            "GROUP BY category",
            applicable_slugs,
        )

    data_map = {r["category"]: {"req_count": r["req_count"], "jur_count": r["jur_count"]} for r in data_rows}

    # 6. Build response
    categories_out = []
    with_data = 0
    for slug in applicable_slugs:
        cat = cats_by_slug[slug]
        counts = data_map.get(slug, {"req_count": 0, "jur_count": 0})
        has_data = counts["jur_count"] > 0
        if has_data:
            with_data += 1
        categories_out.append({
            "slug": slug,
            "name": cat["name"],
            "domain": cat["domain"],
            "group": cat["group"],
            "industry_tag": cat.get("industry_tag"),
            "source": source_map[slug],
            "triggered_by": triggered_by_map.get(slug, []),
            "jurisdiction_count": counts["jur_count"],
            "requirement_count": counts["req_count"],
            "has_data": has_data,
        })

    return {
        "summary": {
            "total": len(categories_out),
            "with_data": with_data,
            "missing_data": len(categories_out) - with_data,
        },
        "industry_profile": {
            "name": profile_row["name"] if profile_row else industry,
            "focused_categories": focused_categories,
        },
        "active_triggers": active_triggers,
        "categories": categories_out,
    }


# ---------------------------------------------------------------------------
# Admin notifications / activity feed
# ---------------------------------------------------------------------------

class AdminNotification(BaseModel):
    id: str
    type: str  # "incident", "employee", "offer_letter", "er_case", "handbook", "compliance_alert", "registration"
    title: str
    subtitle: Optional[str] = None
    severity: Optional[str] = None
    status: Optional[str] = None
    company_id: Optional[str] = None
    company_name: Optional[str] = None
    created_at: datetime
    link: Optional[str] = None


class AdminNotificationsResponse(BaseModel):
    items: list[AdminNotification]
    total: int


_NOTIFICATION_LINK_MAP: dict[str, str] = {
    "incident": "/app/ir/incidents/{id}",
    "employee": "/app/matcha/employees/{id}",
    "offer_letter": "/app/matcha/offer-letters",
    "er_case": "/app/matcha/er-copilot/{id}",
    "handbook": "/app/matcha/handbook/{id}",
    "compliance_alert": "/app/matcha/compliance",
    "registration": "/app/admin/business-registrations",
}

# Each sub-query is wrapped in a helper so we can gracefully skip tables that
# don't exist in every environment (e.g. dev vs prod schema drift).

_NOTIFICATION_SUBQUERIES: list[str] = [
    # New incidents
    """SELECT id::text, 'incident' AS type,
            title, incident_number AS subtitle,
            severity, status, company_id::text, created_at
       FROM ir_incidents WHERE created_at > NOW() - INTERVAL '30 days'""",
    # New employees
    """SELECT e.id::text, 'employee' AS type,
            e.first_name || ' ' || e.last_name AS title,
            e.job_title AS subtitle,
            NULL AS severity, 'onboarded' AS status, e.org_id::text AS company_id, e.created_at
       FROM employees e WHERE e.created_at > NOW() - INTERVAL '30 days'""",
    # Offer letters
    """SELECT id::text, 'offer_letter' AS type,
            candidate_name || ' - ' || position_title AS title,
            status AS subtitle,
            NULL AS severity, status, company_id::text, created_at
       FROM offer_letters WHERE created_at > NOW() - INTERVAL '30 days'""",
    # ER cases
    """SELECT id::text, 'er_case' AS type,
            title, case_number AS subtitle,
            NULL AS severity, status, company_id::text, created_at
       FROM er_cases WHERE created_at > NOW() - INTERVAL '30 days'""",
    # Handbooks
    """SELECT id::text, 'handbook' AS type,
            title, status AS subtitle,
            NULL AS severity, status, company_id::text, created_at
       FROM handbooks WHERE created_at > NOW() - INTERVAL '30 days'""",
    # Compliance alerts
    """SELECT id::text, 'compliance_alert' AS type,
            title, message AS subtitle,
            severity, status, company_id::text, created_at
       FROM compliance_alerts WHERE created_at > NOW() - INTERVAL '30 days'""",
    # New company registrations
    """SELECT id::text, 'registration' AS type,
            name AS title, status AS subtitle,
            NULL AS severity, status, NULL AS company_id, created_at
       FROM companies WHERE created_at > NOW() - INTERVAL '30 days'""",
]


@router.get(
    "/notifications",
    response_model=AdminNotificationsResponse,
    dependencies=[Depends(require_admin)],
)
async def get_admin_notifications(
    limit: int = Query(30, ge=1, le=100),
    offset: int = Query(0, ge=0),
):
    """Return a chronological activity feed of recent platform events across all companies."""

    # Build the UNION ALL dynamically, skipping any tables that are missing.
    async with get_connection() as conn:
        valid_parts: list[str] = []
        for sq in _NOTIFICATION_SUBQUERIES:
            try:
                # Dry-run with LIMIT 0 to verify the table/columns exist.
                await conn.fetch(f"SELECT * FROM ({sq}) _probe LIMIT 0")
                valid_parts.append(sq)
            except asyncpg.UndefinedTableError:
                logger.debug("Skipping notification subquery (table missing): %s", sq[:60])
            except asyncpg.UndefinedColumnError:
                logger.debug("Skipping notification subquery (column missing): %s", sq[:60])

        if not valid_parts:
            return AdminNotificationsResponse(items=[], total=0)

        union_sql = " UNION ALL ".join(valid_parts)

        # Total count
        count_row = await conn.fetchrow(f"SELECT COUNT(*) AS total FROM ({union_sql}) AS _all")
        total = count_row["total"] if count_row else 0

        # Paginated rows with company name join
        rows = await conn.fetch(
            f"""SELECT n.*, c.name AS company_name
                FROM ({union_sql}) AS n
                LEFT JOIN companies c ON c.id::text = n.company_id
                ORDER BY n.created_at DESC
                LIMIT $1 OFFSET $2""",
            limit,
            offset,
        )

    items: list[AdminNotification] = []
    for row in rows:
        row_type = row["type"]
        row_id = row["id"]
        link_template = _NOTIFICATION_LINK_MAP.get(row_type, "")
        link = link_template.replace("{id}", row_id) if link_template else None

        items.append(
            AdminNotification(
                id=row_id,
                type=row_type,
                title=row["title"] or "",
                subtitle=row["subtitle"],
                severity=row["severity"],
                status=row["status"],
                company_id=row["company_id"],
                company_name=row["company_name"],
                created_at=row["created_at"],
                link=link,
            )
        )

    return AdminNotificationsResponse(items=items, total=total)


# ---------------------------------------------------------------------------
# Jurisdiction coverage requests
# ---------------------------------------------------------------------------

@router.get("/jurisdiction-requests")
async def list_jurisdiction_requests(
    status: str = "pending",
    current_user=Depends(require_admin),
):
    """List jurisdiction coverage requests with company info and employee counts."""
    async with get_connection() as conn:
        if status == "all":
            rows = await conn.fetch(
                """
                SELECT
                    jcr.id, jcr.city, jcr.state, jcr.county, jcr.status,
                    jcr.admin_notes, jcr.created_at, jcr.location_id,
                    c.name AS company_name,
                    COALESCE(emp_count.cnt, 0) AS employee_count
                FROM jurisdiction_coverage_requests jcr
                JOIN companies c ON c.id = jcr.requested_by_company_id
                LEFT JOIN LATERAL (
                    SELECT COUNT(*) AS cnt FROM employees e
                    WHERE e.work_location_id = jcr.location_id AND e.termination_date IS NULL
                ) emp_count ON true
                ORDER BY jcr.created_at DESC
                """
            )
        else:
            rows = await conn.fetch(
                """
                SELECT
                    jcr.id, jcr.city, jcr.state, jcr.county, jcr.status,
                    jcr.admin_notes, jcr.created_at, jcr.location_id,
                    c.name AS company_name,
                    COALESCE(emp_count.cnt, 0) AS employee_count
                FROM jurisdiction_coverage_requests jcr
                JOIN companies c ON c.id = jcr.requested_by_company_id
                LEFT JOIN LATERAL (
                    SELECT COUNT(*) AS cnt FROM employees e
                    WHERE e.work_location_id = jcr.location_id AND e.termination_date IS NULL
                ) emp_count ON true
                WHERE jcr.status = $1
                ORDER BY jcr.created_at DESC
                """,
                status,
            )

        return [
            {
                "id": str(row["id"]),
                "city": row["city"],
                "state": row["state"],
                "county": row["county"],
                "status": row["status"],
                "company_name": row["company_name"],
                "employee_count": row["employee_count"],
                "admin_notes": row["admin_notes"],
                "location_id": str(row["location_id"]) if row["location_id"] else None,
                "created_at": row["created_at"].isoformat() if row["created_at"] else None,
            }
            for row in rows
        ]


@router.post("/jurisdiction-requests/{request_id}/process")
async def process_jurisdiction_request(
    request_id: UUID,
    body: JurisdictionProcessRequest,
    background_tasks: BackgroundTasks,
    current_user=Depends(require_admin),
):
    """Admin processes a jurisdiction coverage request — adds reference data and triggers compliance check."""
    async with get_connection() as conn:
        # 1. Fetch the request row
        req = await conn.fetchrow(
            "SELECT * FROM jurisdiction_coverage_requests WHERE id = $1",
            request_id,
        )
        if not req:
            raise HTTPException(status_code=404, detail="Jurisdiction request not found")

        city = req["city"]
        state = req["state"]
        location_id = req["location_id"]
        company_id = req["requested_by_company_id"]
        county = body.county or req["county"]

        # 2. Optionally upsert into jurisdiction_reference
        await conn.execute(
            """
            INSERT INTO jurisdiction_reference (city, state, county, has_local_ordinance)
            VALUES (LOWER($1), UPPER($2), $3, $4)
            ON CONFLICT (city, state) DO UPDATE
                SET county = COALESCE(EXCLUDED.county, jurisdiction_reference.county),
                    has_local_ordinance = EXCLUDED.has_local_ordinance
            """,
            city,
            state,
            county,
            body.has_local_ordinance,
        )

        # 3. Update the request status
        updated = await conn.fetchrow(
            """
            UPDATE jurisdiction_coverage_requests
            SET status = 'completed',
                processed_by = $2,
                processed_at = NOW(),
                admin_notes = COALESCE($3, admin_notes)
            WHERE id = $1
            RETURNING *
            """,
            request_id,
            current_user.id,
            body.admin_notes,
        )

        # 4. Update the associated business_location
        if location_id:
            await conn.execute(
                "UPDATE business_locations SET coverage_status = 'covered' WHERE id = $1",
                location_id,
            )

        # 5. Update ALL business_locations matching the same (city, state) across companies
        await conn.execute(
            """
            UPDATE business_locations
            SET coverage_status = 'covered'
            WHERE LOWER(city) = LOWER($1) AND UPPER(state) = UPPER($2)
              AND coverage_status != 'covered'
            """,
            city,
            state,
        )

        # 6. Trigger background compliance checks for ALL matching locations
        affected_locations = await conn.fetch(
            """
            SELECT bl.id, bl.company_id
            FROM business_locations bl
            WHERE LOWER(bl.city) = LOWER($1) AND UPPER(bl.state) = UPPER($2)
              AND bl.is_active = true
            """,
            city,
            state,
        )
        for loc in affected_locations:
            background_tasks.add_task(
                run_compliance_check_background, loc["id"], loc["company_id"]
            )

        return {
            "id": str(updated["id"]),
            "city": updated["city"],
            "state": updated["state"],
            "county": updated["county"],
            "status": updated["status"],
            "admin_notes": updated["admin_notes"],
            "processed_by": str(updated["processed_by"]) if updated["processed_by"] else None,
            "processed_at": updated["processed_at"].isoformat() if updated["processed_at"] else None,
            "created_at": updated["created_at"].isoformat() if updated["created_at"] else None,
        }


@router.post("/jurisdiction-requests/{request_id}/dismiss")
async def dismiss_jurisdiction_request(
    request_id: UUID,
    body: dict | None = None,
    current_user=Depends(require_admin),
):
    """Dismiss a jurisdiction coverage request (e.g., invalid city)."""
    async with get_connection() as conn:
        req = await conn.fetchrow(
            "SELECT id FROM jurisdiction_coverage_requests WHERE id = $1",
            request_id,
        )
        if not req:
            raise HTTPException(status_code=404, detail="Jurisdiction request not found")

        admin_notes = body.get("admin_notes") if body else None

        updated = await conn.fetchrow(
            """
            UPDATE jurisdiction_coverage_requests
            SET status = 'dismissed',
                processed_by = $2,
                processed_at = NOW(),
                admin_notes = COALESCE($3, admin_notes)
            WHERE id = $1
            RETURNING *
            """,
            request_id,
            current_user.id,
            admin_notes,
        )

        return {
            "id": str(updated["id"]),
            "city": updated["city"],
            "state": updated["state"],
            "county": updated["county"],
            "status": updated["status"],
            "admin_notes": updated["admin_notes"],
            "processed_by": str(updated["processed_by"]) if updated["processed_by"] else None,
            "processed_at": updated["processed_at"].isoformat() if updated["processed_at"] else None,
            "created_at": updated["created_at"].isoformat() if updated["created_at"] else None,
        }


# ─── Research Queue ────────────────────────────────────────────────────────────

@router.get("/research-queue", dependencies=[Depends(require_admin)])
async def get_research_queue():
    """List city-level jurisdictions with research status."""
    async with get_connection() as conn:
        rows = await conn.fetch("""
            SELECT
                j.id AS jurisdiction_id,
                j.city, j.state, j.county,
                COALESCE(jrc.cnt, 0) AS repo_count,
                COALESCE(lc.location_count, 0) AS location_count,
                COALESCE(lc.company_count, 0) AS company_count,
                j.created_at
            FROM jurisdictions j
            LEFT JOIN LATERAL (
                SELECT COUNT(*) AS cnt
                FROM jurisdiction_requirements jr
                WHERE jr.jurisdiction_id = j.id
            ) jrc ON true
            LEFT JOIN LATERAL (
                SELECT COUNT(*) AS location_count,
                       COUNT(DISTINCT bl.company_id) AS company_count
                FROM business_locations bl
                WHERE bl.jurisdiction_id = j.id
            ) lc ON true
            WHERE j.city IS NOT NULL AND j.city != ''
            ORDER BY
                COALESCE(jrc.cnt, 0) ASC,
                COALESCE(lc.location_count, 0) DESC,
                j.state, j.city
        """)
        return [
            {
                "jurisdiction_id": str(r["jurisdiction_id"]),
                "city": r["city"],
                "state": r["state"],
                "county": r["county"],
                "repo_count": r["repo_count"],
                "location_count": r["location_count"],
                "company_count": r["company_count"],
                "status": "researched" if r["repo_count"] > 0 else "needs_research",
                "created_at": r["created_at"].isoformat() if r["created_at"] else None,
            }
            for r in rows
        ]


@router.post("/research-queue/{jurisdiction_id}/research", dependencies=[Depends(require_admin)])
async def research_jurisdiction(jurisdiction_id: UUID):
    """Trigger Gemini research for a jurisdiction. Returns SSE stream.

    Writes only to jurisdiction_requirements (the shared repo).
    Does NOT mutate any tenant's compliance_requirements, compliance_check_logs,
    or compliance_alerts.
    """
    async with get_connection() as conn:
        j = await conn.fetchrow(
            "SELECT id FROM jurisdictions WHERE id = $1",
            jurisdiction_id,
        )
        if not j:
            raise HTTPException(status_code=404, detail="Jurisdiction not found")

    async def event_stream():
        try:
            async for event in research_jurisdiction_repo_only(jurisdiction_id):
                if event.get("type") == "heartbeat":
                    yield ": heartbeat\n\n"
                else:
                    yield f"data: {json.dumps(event)}\n\n"
        except Exception as e:
            yield f"data: {json.dumps({'type': 'error', 'message': str(e)})}\n\n"
        yield "data: [DONE]\n\n"

    return StreamingResponse(
        event_stream(),
        media_type="text/event-stream",
        headers={"X-Accel-Buffering": "no"},
    )


# ---------------------------------------------------------------------------
# Company Management
# ---------------------------------------------------------------------------

class CompanyProfileUpdate(BaseModel):
    name: Optional[str] = None
    industry: Optional[str] = None
    healthcare_specialties: Optional[list[str]] = None
    size: Optional[str] = None
    headquarters_state: Optional[str] = None
    headquarters_city: Optional[str] = None


@router.get("/companies", dependencies=[Depends(require_admin)])
async def list_companies_admin():
    """List all companies with user counts."""
    async with get_connection() as conn:
        rows = await conn.fetch("""
            SELECT
                c.id, c.name, c.industry, c.healthcare_specialties,
                c.size, c.status, c.headquarters_state, c.headquarters_city,
                c.created_at,
                (SELECT COUNT(*) FROM employees e WHERE e.org_id = c.id AND e.termination_date IS NULL) AS user_count,
                (SELECT COUNT(*) FROM business_locations bl WHERE bl.company_id = c.id) AS location_count
            FROM companies c
            WHERE c.deleted_at IS NULL
            ORDER BY c.name
        """)
        return [
            {
                "id": str(r["id"]),
                "name": r["name"],
                "industry": r["industry"],
                "healthcare_specialties": list(r["healthcare_specialties"] or []),
                "size": r["size"],
                "status": r["status"] or "approved",
                "headquarters_state": r["headquarters_state"],
                "headquarters_city": r["headquarters_city"],
                "created_at": r["created_at"].isoformat() if r["created_at"] else None,
                "user_count": r["user_count"],
                "location_count": r["location_count"],
            }
            for r in rows
        ]


@router.get("/companies/{company_id}", dependencies=[Depends(require_admin)])
async def get_company_admin(company_id: UUID):
    """Get full company details including users."""
    async with get_connection() as conn:
        row = await conn.fetchrow("""
            SELECT id, name, industry, healthcare_specialties, size, status,
                   headquarters_state, headquarters_city, created_at, enabled_features
            FROM companies WHERE id = $1
        """, company_id)
        if not row:
            raise HTTPException(status_code=404, detail="Company not found")

        admins = await conn.fetch("""
            SELECT u.id, u.email, u.role, u.created_at, cl.name, cl.job_title
            FROM clients cl
            JOIN users u ON u.id = cl.user_id
            WHERE cl.company_id = $1
            ORDER BY u.created_at
        """, company_id)

        jurisdictions = await conn.fetch("""
            SELECT
                bl.state,
                array_agg(DISTINCT bl.city ORDER BY bl.city) AS cities,
                COUNT(DISTINCT e.id) AS employee_count
            FROM business_locations bl
            LEFT JOIN employees e ON e.org_id = bl.company_id
                AND e.work_state = bl.state
                AND e.termination_date IS NULL
            WHERE bl.company_id = $1
            GROUP BY bl.state
            ORDER BY bl.state
        """, company_id)

        employee_count = await conn.fetchval(
            "SELECT COUNT(*) FROM employees WHERE org_id = $1 AND termination_date IS NULL",
            company_id,
        )

        return {
            "id": str(row["id"]),
            "name": row["name"],
            "industry": row["industry"],
            "healthcare_specialties": list(row["healthcare_specialties"] or []),
            "size": row["size"],
            "status": row["status"] or "approved",
            "headquarters_state": row["headquarters_state"],
            "headquarters_city": row["headquarters_city"],
            "created_at": row["created_at"].isoformat() if row["created_at"] else None,
            "enabled_features": row["enabled_features"] or {},
            "employee_count": employee_count,
            "users": [
                {
                    "id": str(u["id"]),
                    "email": u["email"],
                    "name": u["name"],
                    "role": u["role"],
                    "job_title": u["job_title"],
                    "created_at": u["created_at"].isoformat() if u["created_at"] else None,
                }
                for u in admins
            ],
            "jurisdictions": [
                {
                    "state": j["state"],
                    "cities": list(j["cities"]),
                    "employee_count": j["employee_count"],
                }
                for j in jurisdictions
            ],
        }


@router.get("/companies/{company_id}/overview", dependencies=[Depends(require_admin)])
async def get_company_overview_admin(company_id: UUID):
    """Comprehensive company overview for admin detail page."""
    async with get_connection() as conn:
        company = await conn.fetchrow("""
            SELECT id, name, industry, healthcare_specialties, size, status,
                   headquarters_state, created_at, enabled_features
            FROM companies WHERE id = $1
        """, company_id)
        if not company:
            raise HTTPException(status_code=404, detail="Company not found")

        # Employees with department/job info
        employees = await conn.fetch("""
            SELECT id, email, first_name, last_name, department, job_title,
                   employment_type, work_state, start_date, termination_date
            FROM employees WHERE org_id = $1
            ORDER BY termination_date NULLS FIRST, first_name
        """, company_id)

        active_count = sum(1 for e in employees if e["termination_date"] is None)

        # Risk assessment snapshot
        risk_row = await conn.fetchrow("""
            SELECT overall_score, overall_band, computed_at
            FROM risk_assessment_snapshots WHERE company_id = $1
        """, company_id)

        # IR summary
        ir_rows = await conn.fetch("""
            SELECT severity, COUNT(*) AS cnt
            FROM ir_incidents
            WHERE company_id = $1 AND status IN ('reported','investigating','action_required')
            GROUP BY severity
        """, company_id)
        ir_map = {r["severity"]: r["cnt"] for r in ir_rows}
        ir_total = sum(ir_map.values())
        ir_recent = await conn.fetchval("""
            SELECT COUNT(*) FROM ir_incidents
            WHERE company_id = $1 AND created_at > NOW() - INTERVAL '30 days'
        """, company_id)

        # ER summary
        er_rows = await conn.fetch("""
            SELECT status, COUNT(*) AS cnt
            FROM er_cases WHERE company_id = $1 AND status NOT IN ('closed','resolved')
            GROUP BY status
        """, company_id)
        er_map = {r["status"]: r["cnt"] for r in er_rows}
        er_total = sum(er_map.values())

        # Compliance summary
        location_count = await conn.fetchval(
            "SELECT COUNT(*) FROM business_locations WHERE company_id = $1 AND is_active = true", company_id)
        req_count = await conn.fetchval("""
            SELECT COUNT(*) FROM compliance_requirements cr
            JOIN business_locations bl ON bl.id = cr.location_id
            WHERE bl.company_id = $1 AND bl.is_active = true
        """, company_id)
        critical_alerts = await conn.fetchval("""
            SELECT COUNT(*) FROM compliance_alerts
            WHERE company_id = $1 AND severity = 'critical' AND status != 'resolved'
        """, company_id)
        warning_alerts = await conn.fetchval("""
            SELECT COUNT(*) FROM compliance_alerts
            WHERE company_id = $1 AND severity = 'warning' AND status != 'resolved'
        """, company_id)

        # Policies
        active_policies = await conn.fetchval(
            "SELECT COUNT(*) FROM policies WHERE company_id = $1 AND status = 'active'", company_id)
        stale_policies = await conn.fetchval("""
            SELECT COUNT(*) FROM policies
            WHERE company_id = $1 AND status = 'active'
              AND updated_at < NOW() - INTERVAL '180 days'
        """, company_id)

        # Recent incidents for table
        recent_incidents = await conn.fetch("""
            SELECT id, incident_number, title, severity, status, created_at
            FROM ir_incidents WHERE company_id = $1
            ORDER BY created_at DESC LIMIT 10
        """, company_id)

        # Recent ER cases for table
        recent_er = await conn.fetch("""
            SELECT id, case_number, title, status, category, created_at
            FROM er_cases WHERE company_id = $1
            ORDER BY created_at DESC LIMIT 10
        """, company_id)

    return {
        "company": {
            "id": str(company["id"]),
            "name": company["name"],
            "industry": company["industry"],
            "healthcare_specialties": list(company["healthcare_specialties"] or []),
            "size": company["size"],
            "status": company["status"] or "approved",
            "headquarters_state": company["headquarters_state"],
            "created_at": company["created_at"].isoformat() if company["created_at"] else None,
            "enabled_features": company["enabled_features"] or {},
            "active_employee_count": active_count,
        },
        "employees": [
            {
                "id": str(e["id"]), "email": e["email"],
                "name": f"{e['first_name']} {e['last_name']}".strip(),
                "department": e["department"], "job_title": e["job_title"],
                "employment_type": e["employment_type"], "work_state": e["work_state"],
                "start_date": e["start_date"].isoformat() if e["start_date"] else None,
                "active": e["termination_date"] is None,
            }
            for e in employees
        ],
        "risk": {
            "overall_score": risk_row["overall_score"],
            "overall_band": risk_row["overall_band"],
            "computed_at": risk_row["computed_at"].isoformat() if risk_row["computed_at"] else None,
        } if risk_row else None,
        "ir_summary": {
            "total_open": ir_total,
            "critical": ir_map.get("critical", 0),
            "high": ir_map.get("high", 0),
            "medium": ir_map.get("medium", 0),
            "low": ir_map.get("low", 0),
            "recent_30_days": ir_recent or 0,
        },
        "er_summary": {
            "total_open": er_total,
            "open": er_map.get("open", 0),
            "in_review": er_map.get("in_review", 0),
            "pending_determination": er_map.get("pending_determination", 0),
        },
        "compliance": {
            "total_locations": location_count or 0,
            "total_requirements": req_count or 0,
            "critical_alerts": critical_alerts or 0,
            "warning_alerts": warning_alerts or 0,
        },
        "policies": {
            "total_active": active_policies or 0,
            "stale_count": stale_policies or 0,
        },
        "recent_incidents": [
            {
                "id": str(r["id"]), "incident_number": r["incident_number"],
                "title": r["title"], "severity": r["severity"],
                "status": r["status"],
                "created_at": r["created_at"].isoformat() if r["created_at"] else None,
            }
            for r in recent_incidents
        ],
        "recent_er_cases": [
            {
                "id": str(r["id"]), "case_number": r["case_number"],
                "title": r["title"], "status": r["status"],
                "category": r["category"],
                "created_at": r["created_at"].isoformat() if r["created_at"] else None,
            }
            for r in recent_er
        ],
    }


@router.get("/companies/{company_id}/employees", dependencies=[Depends(require_admin)])
async def get_company_employees_admin(company_id: UUID):
    """Lazy-load full employee list for a company."""
    async with get_connection() as conn:
        rows = await conn.fetch("""
            SELECT id, email, first_name, last_name, employment_type,
                   work_state, start_date, termination_date
            FROM employees
            WHERE org_id = $1
            ORDER BY termination_date NULLS FIRST, first_name, last_name
        """, company_id)
        return [
            {
                "id": str(r["id"]),
                "email": r["email"],
                "name": f"{r['first_name']} {r['last_name']}".strip(),
                "employment_type": r["employment_type"],
                "work_state": r["work_state"],
                "start_date": r["start_date"].isoformat() if r["start_date"] else None,
                "termination_date": r["termination_date"].isoformat() if r["termination_date"] else None,
                "active": r["termination_date"] is None,
            }
            for r in rows
        ]


@router.get("/employees/{employee_id}", dependencies=[Depends(require_admin)])
async def get_employee_admin(employee_id: UUID):
    """Get full employee profile including credentials."""
    async with get_connection() as conn:
        row = await conn.fetchrow("""
            SELECT
                e.id, e.org_id, e.email, e.personal_email, e.first_name, e.last_name,
                e.phone, e.address, e.job_title, e.department, e.employment_type,
                e.employment_status, e.pay_classification, e.pay_rate,
                e.work_state, e.work_city, e.start_date, e.termination_date,
                e.status_reason, e.emergency_contact, e.created_at,
                mgr.first_name || ' ' || mgr.last_name AS manager_name
            FROM employees e
            LEFT JOIN employees mgr ON mgr.id = e.manager_id
            WHERE e.id = $1
        """, employee_id)
        if not row:
            raise HTTPException(status_code=404, detail="Employee not found")

        creds = await conn.fetchrow("""
            SELECT license_type, license_number, license_state, license_expiration,
                   npi_number, dea_number, dea_expiration,
                   board_certification, board_certification_expiration,
                   clinical_specialty, oig_last_checked, oig_status,
                   malpractice_carrier, malpractice_policy_number, malpractice_expiration,
                   health_clearances
            FROM employee_credentials WHERE employee_id = $1
        """, employee_id)

        ec = dict(row["emergency_contact"] or {})
        creds_data = None
        if creds:
            dc = decrypt_credential_fields(dict(creds))
            creds_data = {
                "license_type": dc["license_type"],
                "license_number": dc["license_number"],
                "license_state": dc["license_state"],
                "license_expiration": creds["license_expiration"].isoformat() if creds["license_expiration"] else None,
                "npi_number": dc["npi_number"],
                "dea_number": dc["dea_number"],
                "dea_expiration": creds["dea_expiration"].isoformat() if creds["dea_expiration"] else None,
                "board_certification": dc["board_certification"],
                "board_certification_expiration": creds["board_certification_expiration"].isoformat() if creds["board_certification_expiration"] else None,
                "clinical_specialty": dc["clinical_specialty"],
                "oig_last_checked": creds["oig_last_checked"].isoformat() if creds["oig_last_checked"] else None,
                "oig_status": dc["oig_status"],
                "malpractice_carrier": dc["malpractice_carrier"],
                "malpractice_policy_number": dc["malpractice_policy_number"],
                "malpractice_expiration": creds["malpractice_expiration"].isoformat() if creds["malpractice_expiration"] else None,
                "health_clearances": creds["health_clearances"] or {},
            }
        result = {
            "id": str(row["id"]),
            "org_id": str(row["org_id"]),
            "email": row["email"],
            "personal_email": row["personal_email"],
            "first_name": row["first_name"],
            "last_name": row["last_name"],
            "phone": row["phone"],
            "address": row["address"],
            "job_title": row["job_title"],
            "department": row["department"],
            "employment_type": row["employment_type"],
            "employment_status": row["employment_status"],
            "pay_classification": row["pay_classification"],
            "pay_rate": str(row["pay_rate"]) if row["pay_rate"] else None,
            "work_state": row["work_state"],
            "work_city": row["work_city"],
            "start_date": row["start_date"].isoformat() if row["start_date"] else None,
            "termination_date": row["termination_date"].isoformat() if row["termination_date"] else None,
            "status_reason": row["status_reason"],
            "manager_name": row["manager_name"],
            "emergency_contact": ec,
            "created_at": row["created_at"].isoformat() if row["created_at"] else None,
            "credentials": creds_data,
        }
        return result


@router.patch("/companies/{company_id}", dependencies=[Depends(require_admin)])
async def update_company_admin(company_id: UUID, body: CompanyProfileUpdate):
    """Update company profile fields."""
    fields = body.model_dump(exclude_none=True)
    if not fields:
        raise HTTPException(status_code=400, detail="No fields to update")

    set_clauses = []
    values = []
    for i, (key, val) in enumerate(fields.items(), start=1):
        set_clauses.append(f"{key} = ${i}")
        values.append(val)
    values.append(company_id)

    async with get_connection() as conn:
        row = await conn.fetchrow(
            f"UPDATE companies SET {', '.join(set_clauses)} WHERE id = ${len(values)} RETURNING id",
            *values,
        )
        if not row:
            raise HTTPException(status_code=404, detail="Company not found")
    from ...matcha.services.matcha_work_document import invalidate_company_profile_cache
    invalidate_company_profile_cache(company_id)
    return {"ok": True}


@router.delete("/companies/{company_id}", dependencies=[Depends(require_admin)])
async def delete_company_admin(company_id: UUID):
    """Soft-delete a company so it no longer appears in lists."""
    async with get_connection() as conn:
        row = await conn.fetchrow(
            "UPDATE companies SET deleted_at = NOW() WHERE id = $1 AND deleted_at IS NULL RETURNING id",
            company_id,
        )
        if not row:
            raise HTTPException(status_code=404, detail="Company not found or already deleted")
        from ...matcha.services.matcha_work_document import invalidate_company_profile_cache
        invalidate_company_profile_cache(company_id)
    return {"ok": True}


# ---------------------------------------------------------------------------
# Error Logs
# ---------------------------------------------------------------------------

class ErrorLogItem(BaseModel):
    id: str
    timestamp: datetime
    method: str
    path: str
    status_code: int
    error_type: str
    error_message: str
    traceback: Optional[str] = None
    user_id: Optional[str] = None
    user_role: Optional[str] = None
    company_id: Optional[str] = None
    query_params: Optional[str] = None


class ErrorLogsResponse(BaseModel):
    items: list[ErrorLogItem]
    total: int


@router.get(
    "/error-logs",
    response_model=ErrorLogsResponse,
    dependencies=[Depends(require_admin)],
)
async def get_error_logs(
    limit: int = Query(50, ge=1, le=200),
    offset: int = Query(0, ge=0),
    path_filter: Optional[str] = Query(None, description="Filter by path substring"),
    error_type: Optional[str] = Query(None, description="Filter by error type"),
):
    """Return recent application error logs."""
    async with get_connection() as conn:
        where_clauses = []
        params: list = []
        idx = 1

        if path_filter:
            where_clauses.append(f"path ILIKE ${idx}")
            params.append(f"%{path_filter}%")
            idx += 1
        if error_type:
            where_clauses.append(f"error_type = ${idx}")
            params.append(error_type)
            idx += 1

        where_sql = ("WHERE " + " AND ".join(where_clauses)) if where_clauses else ""

        total = await conn.fetchval(
            f"SELECT COUNT(*) FROM error_logs {where_sql}", *params
        )

        rows = await conn.fetch(
            f"""SELECT id, timestamp, method, path, status_code,
                       error_type, error_message, traceback,
                       user_id, user_role, company_id, query_params
                FROM error_logs {where_sql}
                ORDER BY timestamp DESC
                LIMIT ${idx} OFFSET ${idx + 1}""",
            *params, limit, offset,
        )

    items = [
        ErrorLogItem(
            id=str(r["id"]),
            timestamp=r["timestamp"],
            method=r["method"],
            path=r["path"],
            status_code=r["status_code"],
            error_type=r["error_type"],
            error_message=r["error_message"],
            traceback=r["traceback"],
            user_id=str(r["user_id"]) if r["user_id"] else None,
            user_role=r["user_role"],
            company_id=str(r["company_id"]) if r["company_id"] else None,
            query_params=r["query_params"],
        )
        for r in rows
    ]
    return ErrorLogsResponse(items=items, total=total or 0)


@router.delete("/error-logs", dependencies=[Depends(require_admin)])
async def clear_error_logs():
    """Delete all error logs."""
    async with get_connection() as conn:
        count = await conn.fetchval("DELETE FROM error_logs RETURNING COUNT(*)")
    return {"deleted": count or 0}


# ── Payer Policy Data Management ─────────────────────────────────────────────


@router.get("/payer-policies/overview", dependencies=[Depends(require_admin)])
async def payer_policies_overview():
    """Aggregated view of payer policy data: counts, staleness, field completeness."""
    async with get_connection() as conn:
        summary = await conn.fetchrow("""
            SELECT
                count(*) AS total,
                count(DISTINCT payer_name) AS payer_count,
                count(CASE WHEN coverage_status = 'covered' THEN 1 END) AS covered,
                count(CASE WHEN coverage_status = 'conditional' THEN 1 END) AS conditional,
                count(CASE WHEN coverage_status = 'not_covered' THEN 1 END) AS not_covered,
                count(CASE WHEN research_source = 'cms_api' THEN 1 END) AS from_cms,
                count(CASE WHEN research_source = 'gemini' THEN 1 END) AS from_gemini,
                count(CASE WHEN clinical_criteria IS NOT NULL AND clinical_criteria != '' THEN 1 END) AS has_criteria,
                count(CASE WHEN procedure_codes IS NOT NULL AND array_length(procedure_codes, 1) > 0 THEN 1 END) AS has_codes,
                count(CASE WHEN source_url IS NOT NULL AND source_url != '' THEN 1 END) AS has_source_url,
                max(last_verified_at) AS last_ingest,
                count(CASE WHEN last_verified_at IS NOT NULL
                    AND EXTRACT(DAY FROM NOW() - last_verified_at) > staleness_warning_days THEN 1 END) AS stale_warning,
                count(CASE WHEN last_verified_at IS NOT NULL
                    AND EXTRACT(DAY FROM NOW() - last_verified_at) > staleness_critical_days THEN 1 END) AS stale_critical
            FROM payer_medical_policies
        """)

        by_payer = await conn.fetch("""
            SELECT payer_name, count(*) AS count,
                   count(CASE WHEN coverage_status = 'covered' THEN 1 END) AS covered,
                   count(CASE WHEN coverage_status = 'conditional' THEN 1 END) AS conditional
            FROM payer_medical_policies
            GROUP BY payer_name ORDER BY count(*) DESC
        """)

    s = dict(summary)
    total = s["total"] or 1
    return {
        "total": s["total"],
        "payer_count": s["payer_count"],
        "coverage": {
            "covered": s["covered"],
            "conditional": s["conditional"],
            "not_covered": s["not_covered"],
        },
        "sources": {
            "cms": s["from_cms"],
            "gemini": s["from_gemini"],
        },
        "field_completeness": {
            "clinical_criteria_pct": round(s["has_criteria"] / total * 100, 1),
            "procedure_codes_pct": round(s["has_codes"] / total * 100, 1),
            "source_url_pct": round(s["has_source_url"] / total * 100, 1),
        },
        "staleness": {
            "warning": s["stale_warning"],
            "critical": s["stale_critical"],
        },
        "last_ingest": s["last_ingest"].isoformat() if s["last_ingest"] else None,
        "by_payer": [{"payer": r["payer_name"], "count": r["count"], "covered": r["covered"], "conditional": r["conditional"]} for r in by_payer],
    }


@router.get("/payer-policies/integrity-check", dependencies=[Depends(require_admin)])
async def payer_policies_integrity_check():
    """Integrity check: stale policies, missing fields, low confidence, recent changes."""
    async with get_connection() as conn:
        # Stale policies
        stale = await conn.fetch("""
            SELECT id, payer_name, policy_number, policy_title, coverage_status,
                   EXTRACT(DAY FROM NOW() - last_verified_at)::int AS days_since_verified,
                   staleness_warning_days, staleness_critical_days
            FROM payer_medical_policies
            WHERE last_verified_at IS NOT NULL
              AND EXTRACT(DAY FROM NOW() - last_verified_at) > staleness_warning_days
            ORDER BY EXTRACT(DAY FROM NOW() - last_verified_at) DESC
            LIMIT 200
        """)

        stale_list = []
        for r in stale:
            days = r["days_since_verified"] or 0
            level = "critical" if days >= (r["staleness_critical_days"] or 180) else "warning"
            stale_list.append({
                "id": str(r["id"]),
                "payer": r["payer_name"],
                "policy_number": r["policy_number"],
                "title": r["policy_title"],
                "coverage_status": r["coverage_status"],
                "days_since_verified": days,
                "level": level,
            })

        # Missing fields
        missing_fields = await conn.fetch("""
            SELECT id, payer_name, policy_number, policy_title,
                   CASE WHEN clinical_criteria IS NULL OR clinical_criteria = '' THEN true ELSE false END AS missing_criteria,
                   CASE WHEN procedure_codes IS NULL OR array_length(procedure_codes, 1) IS NULL THEN true ELSE false END AS missing_codes,
                   CASE WHEN source_url IS NULL OR source_url = '' THEN true ELSE false END AS missing_source
            FROM payer_medical_policies
            WHERE (clinical_criteria IS NULL OR clinical_criteria = '')
               OR (procedure_codes IS NULL OR array_length(procedure_codes, 1) IS NULL)
               OR (source_url IS NULL OR source_url = '')
            ORDER BY payer_name, policy_number
            LIMIT 200
        """)

        missing_list = [
            {
                "id": str(r["id"]),
                "payer": r["payer_name"],
                "policy_number": r["policy_number"],
                "title": r["policy_title"],
                "missing": [f for f, col in [
                    ("clinical_criteria", "missing_criteria"),
                    ("procedure_codes", "missing_codes"),
                    ("source_url", "missing_source"),
                ] if r[col]],
            }
            for r in missing_fields
        ]

        # Low confidence (Gemini research)
        low_conf = await conn.fetch("""
            SELECT id, payer_name, policy_number, policy_title,
                   (metadata->>'confidence')::float AS confidence
            FROM payer_medical_policies
            WHERE research_source = 'gemini'
              AND metadata->>'confidence' IS NOT NULL
              AND (metadata->>'confidence')::float < 0.5
            ORDER BY (metadata->>'confidence')::float
            LIMIT 100
        """)

        low_conf_list = [
            {
                "id": str(r["id"]),
                "payer": r["payer_name"],
                "policy_number": r["policy_number"],
                "title": r["policy_title"],
                "confidence": r["confidence"],
            }
            for r in low_conf
        ]

        # Recent changes
        changes = await conn.fetch("""
            SELECT cl.id, cl.policy_id, cl.field_changed, cl.old_value, cl.new_value,
                   cl.change_source, cl.changed_at,
                   p.payer_name, p.policy_number, p.policy_title
            FROM payer_policy_change_log cl
            JOIN payer_medical_policies p ON p.id = cl.policy_id
            WHERE cl.changed_at > NOW() - INTERVAL '30 days'
            ORDER BY cl.changed_at DESC
            LIMIT 100
        """)

        changes_list = [
            {
                "id": str(r["id"]),
                "payer": r["payer_name"],
                "policy_number": r["policy_number"],
                "title": r["policy_title"],
                "field": r["field_changed"],
                "old_value": r["old_value"],
                "new_value": r["new_value"],
                "source": r["change_source"],
                "changed_at": r["changed_at"].isoformat() if r["changed_at"] else None,
            }
            for r in changes
        ]

    return {
        "stale_policies": stale_list,
        "stale_count": len(stale_list),
        "missing_fields": missing_list,
        "missing_fields_count": len(missing_list),
        "low_confidence": low_conf_list,
        "low_confidence_count": len(low_conf_list),
        "recent_changes": changes_list,
        "recent_changes_count": len(changes_list),
    }


@router.post("/payer-policies/run-staleness-check", dependencies=[Depends(require_admin)])
async def payer_run_staleness_check():
    """Scan payer policies for staleness and upsert repository_alerts."""
    created = 0
    resolved = 0

    async with get_connection() as conn:
        stale_rows = await conn.fetch("""
            SELECT id, payer_name, policy_number, policy_title,
                   EXTRACT(DAY FROM NOW() - last_verified_at)::int AS days_since_verified,
                   staleness_warning_days, staleness_critical_days
            FROM payer_medical_policies
            WHERE last_verified_at IS NOT NULL
              AND EXTRACT(DAY FROM NOW() - last_verified_at) > staleness_warning_days
        """)

        for r in stale_rows:
            days = r["days_since_verified"] or 0
            if days >= (r["staleness_critical_days"] or 180):
                alert_type, severity = "payer_stale_critical", "critical"
            else:
                alert_type, severity = "payer_stale_warning", "warning"

            message = f"{r['policy_title'] or r['policy_number']} ({r['payer_name']}) is {days} days past verification"
            # Check if open alert already exists for this policy
            existing_alert = await conn.fetchval(
                "SELECT id FROM repository_alerts WHERE requirement_id = $1 AND alert_type = $2 AND status = 'open'",
                r["id"], alert_type,
            )
            if existing_alert:
                await conn.execute(
                    "UPDATE repository_alerts SET severity = $1, message = $2, days_overdue = $3 WHERE id = $4",
                    severity, message, days - (r["staleness_warning_days"] or 90), existing_alert,
                )
            else:
                await conn.execute("""
                    INSERT INTO repository_alerts
                        (alert_type, severity, requirement_id, category, message, days_overdue, regulation_key)
                    VALUES ($1, $2, $3, 'payer_policy', $4, $5, $6)
                """, alert_type, severity, r["id"], message,
                    days - (r["staleness_warning_days"] or 90), r["policy_number"])
                created += 1
            if "INSERT" in result:
                created += 1

        # Auto-resolve
        resolved = await conn.fetchval("""
            UPDATE repository_alerts
            SET status = 'resolved', resolved_at = NOW()
            WHERE status = 'open'
              AND alert_type IN ('payer_stale_warning', 'payer_stale_critical')
              AND requirement_id NOT IN (
                  SELECT id FROM payer_medical_policies
                  WHERE EXTRACT(DAY FROM NOW() - last_verified_at) > staleness_warning_days
              )
            RETURNING id
        """) or 0

    return {
        "alerts_created": created,
        "alerts_resolved": resolved if isinstance(resolved, int) else 0,
        "stale_found": len(stale_rows),
    }


# ---------------------------------------------------------------------------
# Admin Compliance Management — per-company location & requirement management
# ---------------------------------------------------------------------------


class AdminAddRequirementRequest(BaseModel):
    jurisdiction_requirement_id: UUID


@router.get("/companies/{company_id}/compliance")
async def admin_company_compliance(
    company_id: UUID,
    current_user=Depends(require_admin),
):
    """Company compliance overview: locations with requirement category counts."""
    async with get_connection() as conn:
        company = await conn.fetchrow(
            "SELECT id, name, industry FROM companies WHERE id = $1",
            company_id,
        )
        if not company:
            raise HTTPException(404, "Company not found")

    locations = await get_locations(company_id)

    # Batch category breakdown for all locations in one query
    loc_ids = [loc["id"] for loc in locations]
    cat_map: dict[str, dict[str, int]] = {str(lid): {} for lid in loc_ids}
    if loc_ids:
        async with get_connection() as conn:
            rows = await conn.fetch(
                "SELECT location_id, category, COUNT(*) AS cnt FROM compliance_requirements WHERE location_id = ANY($1) GROUP BY location_id, category",
                loc_ids,
            )
            for r in rows:
                cat_map.setdefault(str(r["location_id"]), {})[r["category"]] = r["cnt"]
    for loc in locations:
        loc["category_counts"] = cat_map.get(str(loc["id"]), {})

    return {
        "company": {"id": str(company["id"]), "name": company["name"], "industry": company["industry"]},
        "locations": locations,
    }


@router.get("/companies/{company_id}/locations/{location_id}/requirements")
async def admin_location_requirements(
    company_id: UUID,
    location_id: UUID,
    category: Optional[str] = Query(None),
    current_user=Depends(require_admin),
):
    """Full requirement list for a location, including governance_source."""
    reqs = await get_location_requirements(location_id, company_id, category)

    # Enrich with governance_source
    async with get_connection() as conn:
        gov_rows = await conn.fetch(
            "SELECT id, governance_source FROM compliance_requirements WHERE location_id = $1",
            location_id,
        )
        gov_map = {str(r["id"]): r["governance_source"] for r in gov_rows}

    enriched = []
    for r in reqs:
        d = r.dict() if hasattr(r, "dict") else r
        d["governance_source"] = gov_map.get(d["id"], "not_evaluated")
        enriched.append(d)

    return {"requirements": enriched}


@router.post("/companies/{company_id}/locations")
async def admin_create_location(
    company_id: UUID,
    data: LocationCreate,
    background_tasks: BackgroundTasks,
    current_user=Depends(require_admin),
):
    """Admin creates a location for a company, auto-syncs compliance requirements."""
    async with get_connection() as conn:
        exists = await conn.fetchval("SELECT 1 FROM companies WHERE id = $1", company_id)
        if not exists:
            raise HTTPException(404, "Company not found")

    location, has_coverage = await create_location(company_id, data)

    if not has_coverage:
        background_tasks.add_task(run_compliance_check_background, location["id"], company_id)

    return {"location": location, "has_coverage": has_coverage}


@router.post("/companies/{company_id}/locations/{location_id}/requirements")
async def admin_add_requirement(
    company_id: UUID,
    location_id: UUID,
    body: AdminAddRequirementRequest,
    current_user=Depends(require_admin),
):
    """Cherry-pick a jurisdiction requirement into a company location."""
    try:
        row = await admin_add_requirement_to_location(
            location_id, company_id, body.jurisdiction_requirement_id,
        )
        return {"requirement": row}
    except ValueError as e:
        raise HTTPException(400, str(e))


@router.delete("/companies/{company_id}/locations/{location_id}/requirements/{requirement_id}")
async def admin_remove_requirement(
    company_id: UUID,
    location_id: UUID,
    requirement_id: UUID,
    current_user=Depends(require_admin),
):
    """Remove an admin-added requirement from a location."""
    async with get_connection() as conn:
        deleted = await conn.fetchval(
            """
            DELETE FROM compliance_requirements
            WHERE id = $1 AND location_id = $2 AND governance_source = 'admin_override'
            RETURNING id
            """,
            requirement_id, location_id,
        )
    if not deleted:
        raise HTTPException(404, "Requirement not found or not admin-added")
    return {"deleted": True}


@router.get("/companies/{company_id}/locations/{location_id}/repository")
async def admin_browse_repository(
    company_id: UUID,
    location_id: UUID,
    current_user=Depends(require_admin),
):
    """Browse jurisdiction requirements not yet assigned to this location."""
    async with get_connection() as conn:
        jurisdiction_id = await conn.fetchval(
            "SELECT jurisdiction_id FROM business_locations WHERE id = $1 AND company_id = $2",
            location_id, company_id,
        )
        if not jurisdiction_id:
            raise HTTPException(404, "Location not found")

        rows = await conn.fetch(
            """
            SELECT jr.id, jr.category, jr.regulation_key, jr.jurisdiction_level,
                   jr.jurisdiction_name, jr.title, jr.description,
                   jr.current_value, jr.source_url, jr.effective_date
            FROM jurisdiction_requirements jr
            WHERE jr.jurisdiction_id = $1
              AND NOT EXISTS (
                  SELECT 1 FROM compliance_requirements cr
                  WHERE cr.location_id = $2
                    AND cr.requirement_key = jr.category || ':' || COALESCE(jr.regulation_key, jr.title)
              )
            ORDER BY jr.category, jr.title
            """,
            jurisdiction_id, location_id,
        )

    return {"requirements": [dict(r) for r in rows]}


# ==========================================================================
# Beta Invitations
# ==========================================================================

class BetaInviteRequest(BaseModel):
    emails: list[EmailStr] = Field(..., min_length=1, max_length=50)


@router.post("/beta-invitations")
async def send_beta_invitations(
    body: BetaInviteRequest,
    current_user=Depends(require_admin),
):
    """Send private beta invitations for Matcha Work."""
    from ...config import get_settings
    settings = get_settings()
    base_url = settings.app_base_url.rstrip("/")

    email_svc = get_email_service()
    sent = 0
    skipped: list[str] = []

    async with get_connection() as conn:
        for email in body.emails:
            email_lower = email.lower().strip()
            # Skip if already invited (pending) or already registered
            existing = await conn.fetchrow(
                "SELECT status FROM beta_invitations WHERE email = $1 AND status IN ('pending', 'registered') LIMIT 1",
                email_lower,
            )
            if existing:
                skipped.append(email_lower)
                continue

            token = secrets.token_hex(32)
            await conn.execute(
                """INSERT INTO beta_invitations (email, token, invited_by)
                   VALUES ($1, $2, $3)""",
                email_lower, token, current_user.id,
            )

            invite_url = f"{base_url}/register/beta?token={token}"
            html = f"""
            <div style="font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif; max-width: 480px; margin: 0 auto; padding: 32px 0;">
                <h2 style="color: #e4e4e7; font-size: 20px; margin-bottom: 8px;">You're invited to Matcha Work</h2>
                <p style="color: #a1a1aa; font-size: 14px; line-height: 1.6; margin-bottom: 24px;">
                    You've been selected for the private beta of Matcha Work — an AI-powered workspace
                    for HR, compliance, and recruiting professionals.
                </p>
                <a href="{invite_url}"
                   style="display: inline-block; background: #10b981; color: white; padding: 12px 28px;
                          border-radius: 8px; text-decoration: none; font-size: 14px; font-weight: 600;">
                    Create Your Account
                </a>
                <p style="color: #71717a; font-size: 12px; margin-top: 24px;">
                    This invitation is for <strong>{email_lower}</strong> and can only be used once.
                </p>
            </div>
            """
            try:
                if email_svc.is_configured():
                    await email_svc.send_email(
                        to_email=email_lower,
                        to_name=email_lower.split("@")[0],
                        subject="You're invited to Matcha Work (Private Beta)",
                        html_content=html,
                    )
            except Exception as e:
                logger.warning(f"Failed to send beta invite to {email_lower}: {e}")
                # Remove the invite row so admin can retry
                await conn.execute("DELETE FROM beta_invitations WHERE token = $1", token)
                skipped.append(email_lower)
                continue

            sent += 1

    return {"sent": sent, "skipped": skipped}


class IndividualInviteRequest(BaseModel):
    email: EmailStr


@router.post("/individual-invites")
async def create_individual_invite(
    body: IndividualInviteRequest,
    current_user=Depends(require_admin),
):
    """Generate a matcha-work individual signup URL without sending email.

    Creates a beta_invitation row and returns the invite URL for the admin
    to copy and share manually. The invited user registers at /register/beta
    which provisions a personal workspace (auth.py register_individual flow).
    """
    from ...config import get_settings
    settings = get_settings()
    base_url = settings.app_base_url.rstrip("/")

    email_lower = body.email.lower().strip()

    async with get_connection() as conn:
        existing = await conn.fetchrow(
            "SELECT id, token, status FROM beta_invitations WHERE email = $1 AND status IN ('pending', 'registered') LIMIT 1",
            email_lower,
        )
        if existing:
            if existing["status"] == "registered":
                raise HTTPException(status_code=409, detail="Already registered")
            # Reuse the pending invite
            return {
                "email": email_lower,
                "invite_url": f"{base_url}/register/beta?token={existing['token']}",
                "reused": True,
            }

        token = secrets.token_hex(32)
        await conn.execute(
            """INSERT INTO beta_invitations (email, token, invited_by)
               VALUES ($1, $2, $3)""",
            email_lower, token, current_user.id,
        )

    return {
        "email": email_lower,
        "invite_url": f"{base_url}/register/beta?token={token}",
        "reused": False,
    }


@router.get("/beta-invitations")
async def list_beta_invitations(current_user=Depends(require_admin)):
    """List all beta invitations."""
    async with get_connection() as conn:
        rows = await conn.fetch(
            """SELECT id, email, status, created_at, registered_at
               FROM beta_invitations
               ORDER BY created_at DESC
               LIMIT 200"""
        )
    return [
        {
            "id": str(r["id"]),
            "email": r["email"],
            "status": r["status"],
            "created_at": r["created_at"].isoformat() if r["created_at"] else None,
            "registered_at": r["registered_at"].isoformat() if r["registered_at"] else None,
        }
        for r in rows
    ]


@router.delete("/beta-invitations/{invite_id}")
async def revoke_beta_invitation(invite_id: UUID, current_user=Depends(require_admin)):
    """Revoke a pending beta invitation."""
    async with get_connection() as conn:
        deleted = await conn.execute(
            "DELETE FROM beta_invitations WHERE id = $1 AND status = 'pending'",
            invite_id,
        )
    if deleted == "DELETE 0":
        raise HTTPException(status_code=404, detail="Invitation not found or already used")
    return {"ok": True}


# =============================================================================
# Master-admin lifecycle controls (Phase B of admin user-management work)
# =============================================================================
# Suspend/unsuspend, password reset, cancel subscription, refund, change tier,
# soft-delete. Each action is a single explicit endpoint so the frontend can
# call it without scaffolding extra logic. All gated by require_admin.
# =============================================================================


_TIER_FEATURE_PRESETS: dict[str, dict] = {
    # Free / Resources tier: no paid features.
    "resources_free": {k: False for k in DEFAULT_COMPANY_FEATURES},
    # Matcha Lite: incidents only (matches what stripe_webhook flips on
    # checkout.session.completed for matcha_lite — see stripe_webhook.py
    # line ~214). Don't add `employees` here or the post-tier-change shape
    # diverges from a real Lite signup.
    "matcha_lite": {**{k: False for k in DEFAULT_COMPANY_FEATURES}, "incidents": True},
    # Bespoke / Platform: full feature set per DEFAULT_COMPANY_FEATURES.
    "bespoke": dict(DEFAULT_COMPANY_FEATURES),
    # IR self-serve (Cap): incidents + employees + discipline.
    "ir_only_self_serve": {
        **{k: False for k in DEFAULT_COMPANY_FEATURES},
        "incidents": True, "employees": True, "discipline": True,
    },
}


class SuspendBody(BaseModel):
    reason: Optional[str] = Field(default=None, max_length=500)


@router.post("/users/{user_id}/suspend", dependencies=[Depends(require_admin)])
async def admin_suspend_user(user_id: UUID, body: SuspendBody = Body(default=SuspendBody())):
    """Mark a user is_suspended. Login + bearer auth refuse them."""
    async with get_connection() as conn:
        result = await conn.execute(
            "UPDATE users SET is_suspended = TRUE WHERE id = $1",
            user_id,
        )
    if result == "UPDATE 0":
        raise HTTPException(status_code=404, detail="User not found")
    logger.info("Admin suspended user %s reason=%s", user_id, body.reason or "—")
    return {"ok": True}


@router.post("/users/{user_id}/unsuspend", dependencies=[Depends(require_admin)])
async def admin_unsuspend_user(user_id: UUID):
    async with get_connection() as conn:
        result = await conn.execute(
            "UPDATE users SET is_suspended = FALSE WHERE id = $1",
            user_id,
        )
    if result == "UPDATE 0":
        raise HTTPException(status_code=404, detail="User not found")
    return {"ok": True}


class PasswordResetResponse(BaseModel):
    reset_url: str
    expires_in_minutes: int


@router.post("/users/{user_id}/password-reset", response_model=PasswordResetResponse, dependencies=[Depends(require_admin)])
async def admin_issue_password_reset(user_id: UUID):
    """Issue a 1-hour password-reset link for a user.

    The link is RETURNED to the admin (not emailed) so they can hand it off
    out-of-band when the customer's inbox is broken or they're on a call.
    Uses the same `password_reset_tokens` table as the user-facing forgot
    flow, so either path works to consume it.
    """
    settings = get_settings()
    async with get_connection() as conn:
        user = await conn.fetchrow("SELECT id FROM users WHERE id = $1", user_id)
        if not user:
            raise HTTPException(status_code=404, detail="User not found")
        token = secrets.token_urlsafe(48)
        await conn.execute(
            """INSERT INTO password_reset_tokens (user_id, token, expires_at)
               VALUES ($1, $2, NOW() + INTERVAL '1 hour')""",
            user_id, token,
        )
    base_url = settings.app_base_url.rstrip("/")
    return PasswordResetResponse(
        reset_url=f"{base_url}/reset-password?token={token}",
        expires_in_minutes=60,
    )


class TierChangeBody(BaseModel):
    tier: str  # 'resources_free' | 'matcha_lite' | 'bespoke' | 'ir_only_self_serve'


@router.patch("/companies/{company_id}/tier", dependencies=[Depends(require_admin)])
async def admin_change_tier(company_id: UUID, body: TierChangeBody):
    """Switch a company's tier — rewrites signup_source + enabled_features.

    Tier mutation is destructive: features get stomped to the target tier's
    preset, so a Free → Lite move loses any one-off flags that were toggled
    individually.

    Stripe sub side-effects:
    - **Lite → non-Lite**: cancels the active Stripe subscription
      immediately. Otherwise the customer keeps getting charged for a tier
      they no longer have.
    - **non-Lite → Lite**: refused. Activating Lite requires a Stripe
      checkout (or a broker-pays referral) so payment is established;
      admin should not bypass that. Use the customer's signup link.
    - **Bespoke ↔ IR Cap**: no Stripe coupling, just preset rewrite.
    """
    preset = _TIER_FEATURE_PRESETS.get(body.tier)
    if preset is None:
        raise HTTPException(
            status_code=400,
            detail=f"Unknown tier '{body.tier}'. Valid: {', '.join(_TIER_FEATURE_PRESETS)}",
        )
    async with get_connection() as conn:
        current = await conn.fetchrow(
            "SELECT signup_source FROM companies WHERE id = $1",
            company_id,
        )
        if not current:
            raise HTTPException(status_code=404, detail="Company not found")
        current_tier = current["signup_source"]

        # Refuse upgrades into Lite — payment isn't established.
        if body.tier == "matcha_lite" and current_tier != "matcha_lite":
            raise HTTPException(
                status_code=400,
                detail="Activating Matcha Lite requires Stripe checkout. Send the customer to /lite/signup or use a broker referral token; admin cannot promote into Lite without payment.",
            )

        # Lite → anything else: cancel the active Stripe sub first.
        if current_tier == "matcha_lite" and body.tier != "matcha_lite":
            sub_row = await conn.fetchrow(
                """SELECT stripe_subscription_id
                     FROM mw_subscriptions
                    WHERE company_id = $1 AND status = 'active'
                    ORDER BY created_at DESC
                    LIMIT 1""",
                company_id,
            )
            if sub_row:
                stripe_service = StripeService()
                try:
                    await stripe_service.cancel_subscription(
                        sub_row["stripe_subscription_id"],
                        at_period_end=False,
                    )
                except StripeServiceError as exc:
                    raise HTTPException(
                        status_code=502,
                        detail=f"Cannot change tier: Stripe cancellation failed: {exc}",
                    )

        result = await conn.execute(
            """UPDATE companies
                  SET signup_source = $1,
                      enabled_features = $2::jsonb
                WHERE id = $3""",
            body.tier, json.dumps(preset), company_id,
        )
    if result == "UPDATE 0":
        raise HTTPException(status_code=404, detail="Company not found")
    logger.info(
        "Admin changed tier: company=%s from=%s to=%s",
        company_id, current_tier, body.tier,
    )
    return {"ok": True, "tier": body.tier, "previous_tier": current_tier}


@router.post("/companies/{company_id}/cancel-subscription", dependencies=[Depends(require_admin)])
async def admin_cancel_subscription(
    company_id: UUID,
    immediate: bool = Query(False, description="If true, end the sub now instead of at period end"),
):
    """Cancel the active mw_subscriptions row for a company via Stripe."""
    async with get_connection() as conn:
        sub_row = await conn.fetchrow(
            """SELECT stripe_subscription_id, status
                 FROM mw_subscriptions
                WHERE company_id = $1 AND status = 'active'
                ORDER BY created_at DESC
                LIMIT 1""",
            company_id,
        )
    if not sub_row:
        raise HTTPException(status_code=404, detail="No active subscription on this company")
    stripe_service = StripeService()
    try:
        await stripe_service.cancel_subscription(
            sub_row["stripe_subscription_id"],
            at_period_end=not immediate,
        )
    except StripeServiceError as exc:
        raise HTTPException(status_code=502, detail=str(exc))
    return {"ok": True, "stripe_subscription_id": sub_row["stripe_subscription_id"], "immediate": immediate}


class ChargeSummary(BaseModel):
    id: str
    amount: int
    amount_refunded: int
    currency: str
    created: int
    status: str
    description: Optional[str] = None


@router.get("/companies/{company_id}/charges", dependencies=[Depends(require_admin)])
async def admin_list_company_charges(company_id: UUID):
    """List recent Stripe charges for the company's customer (refund modal)."""
    async with get_connection() as conn:
        sub_row = await conn.fetchrow(
            """SELECT stripe_customer_id
                 FROM mw_subscriptions
                WHERE company_id = $1
                ORDER BY (status = 'active') DESC, created_at DESC
                LIMIT 1""",
            company_id,
        )
    if not sub_row:
        return {"charges": []}
    stripe_service = StripeService()
    try:
        charges = await stripe_service.list_charges(sub_row["stripe_customer_id"])
    except StripeServiceError as exc:
        raise HTTPException(status_code=502, detail=str(exc))
    return {
        "charges": [
            ChargeSummary(
                id=c["id"],
                amount=c["amount"],
                amount_refunded=c.get("amount_refunded", 0),
                currency=c["currency"],
                created=c["created"],
                status=c["status"],
                description=c.get("description"),
            ).model_dump()
            for c in charges.get("data", [])
        ]
    }


class RefundBody(BaseModel):
    charge_id: str
    amount_cents: Optional[int] = Field(default=None, ge=1)
    reason: Optional[str] = Field(default=None, max_length=500)


@router.post("/companies/{company_id}/refund", dependencies=[Depends(require_admin)])
async def admin_refund_charge(company_id: UUID, body: RefundBody):
    """Issue a (partial or full) Stripe refund for a charge belonging to this company."""
    # We don't enforce that charge_id belongs to the company at the DB level,
    # but the admin chose it from the company's listed charges so the linkage
    # is implicit. Stripe enforces ownership on the server side anyway.
    stripe_service = StripeService()
    try:
        refund = await stripe_service.create_refund(
            body.charge_id,
            amount_cents=body.amount_cents,
            reason=body.reason,
        )
    except StripeServiceError as exc:
        raise HTTPException(status_code=502, detail=str(exc))
    logger.info(
        "Admin refunded charge=%s company=%s amount=%s reason=%s",
        body.charge_id, company_id, body.amount_cents, body.reason,
    )
    return {
        "ok": True,
        "refund_id": refund["id"],
        "amount": refund["amount"],
        "status": refund["status"],
    }


@router.delete("/companies/{company_id}", dependencies=[Depends(require_admin)])
async def admin_soft_delete_company(company_id: UUID):
    """Soft-delete a company. Sets deleted_at; rows stay for audit."""
    async with get_connection() as conn:
        result = await conn.execute(
            "UPDATE companies SET deleted_at = NOW() WHERE id = $1 AND deleted_at IS NULL",
            company_id,
        )
    if result == "UPDATE 0":
        raise HTTPException(status_code=404, detail="Company not found or already deleted")
    return {"ok": True}


@router.post("/companies/{company_id}/restore", dependencies=[Depends(require_admin)])
async def admin_restore_company(company_id: UUID):
    """Reverse a soft-delete."""
    async with get_connection() as conn:
        result = await conn.execute(
            "UPDATE companies SET deleted_at = NULL WHERE id = $1 AND deleted_at IS NOT NULL",
            company_id,
        )
    if result == "UPDATE 0":
        raise HTTPException(status_code=404, detail="Company not deleted")
    return {"ok": True}


@router.delete("/users/{user_id}", dependencies=[Depends(require_admin)])
async def admin_soft_delete_user(user_id: UUID):
    """Soft-delete a user via is_active=false (used for individuals with no company)."""
    async with get_connection() as conn:
        result = await conn.execute(
            "UPDATE users SET is_active = FALSE WHERE id = $1",
            user_id,
        )
    if result == "UPDATE 0":
        raise HTTPException(status_code=404, detail="User not found")
    return {"ok": True}
