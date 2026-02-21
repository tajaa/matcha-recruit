"""Admin routes for business registration approval workflow and company feature management."""

import asyncio
import json
import logging
import re
import secrets
from datetime import datetime, timedelta
from typing import Optional
from uuid import UUID

from fastapi import APIRouter, HTTPException, Depends, Query, status
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, EmailStr, Field

logger = logging.getLogger(__name__)

from ...database import get_connection
from ..dependencies import require_admin
from ..feature_flags import default_company_features_json, merge_company_features
from ..services.email import get_email_service
from ..models.compliance import AutoCheckSettings
from ..services.compliance_service import (
    update_auto_check_settings,
    _jurisdiction_row_to_dict,
)
from ..services.rate_limiter import get_rate_limiter
from ..services.auth import hash_password
from ...config import get_settings

router = APIRouter()


@router.get("/api-usage", dependencies=[Depends(require_admin)])
async def get_api_usage():
    """Return current Gemini API usage stats for rate limiting monitoring."""
    limiter = get_rate_limiter()
    return await limiter.get_usage()


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
    "offer_letters", "policies", "handbooks", "compliance", "compliance_plus",
    "employees", "vibe_checks", "enps", "performance_reviews",
    "er_copilot", "incidents", "time_off", "accommodations", "interview_prep",
    "internal_mobility",
}


class BusinessRegistrationResponse(BaseModel):
    """Response model for a business registration."""
    id: UUID
    company_name: str
    industry: Optional[str]
    company_size: Optional[str]
    owner_email: str
    owner_name: str
    owner_phone: Optional[str]
    owner_job_title: Optional[str]
    status: str
    rejection_reason: Optional[str]
    approved_at: Optional[datetime]
    approved_by_email: Optional[str]
    created_at: datetime


class BusinessRegistrationListResponse(BaseModel):
    """List response for business registrations."""
    registrations: list[BusinessRegistrationResponse]
    total: int


class RejectRequest(BaseModel):
    """Request model for rejecting a business registration."""
    reason: str


@router.get("/business-registrations", response_model=BusinessRegistrationListResponse, dependencies=[Depends(require_admin)])
async def list_business_registrations(
    status_filter: Optional[str] = Query(None, alias="status", description="Filter by status: pending, approved, rejected")
):
    """List all business registrations with optional status filter."""
    async with get_connection() as conn:
        query = """
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
            JOIN clients c ON c.company_id = comp.id
            JOIN users u ON c.user_id = u.id
            LEFT JOIN users approver ON comp.approved_by = approver.id
            WHERE comp.owner_id IS NOT NULL
        """
        params = []

        if status_filter:
            query += " AND comp.status = $1"
            params.append(status_filter)

        query += " ORDER BY comp.created_at DESC"

        rows = await conn.fetch(query, *params)

        registrations = [
            BusinessRegistrationResponse(
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
                created_at=row["created_at"]
            )
            for row in rows
        ]

        return BusinessRegistrationListResponse(
            registrations=registrations,
            total=len(registrations)
        )


@router.get("/business-registrations/{company_id}", response_model=BusinessRegistrationResponse, dependencies=[Depends(require_admin)])
async def get_business_registration(company_id: UUID):
    """Get details of a specific business registration."""
    async with get_connection() as conn:
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
            JOIN clients c ON c.company_id = comp.id
            JOIN users u ON c.user_id = u.id
            LEFT JOIN users approver ON comp.approved_by = approver.id
            WHERE comp.id = $1 AND comp.owner_id IS NOT NULL
            """,
            company_id
        )

        if not row:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Business registration not found"
            )

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
            created_at=row["created_at"]
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


@router.get("/company-features", dependencies=[Depends(require_admin)])
async def list_company_features():
    """List all companies with their enabled features."""
    async with get_connection() as conn:
        rows = await conn.fetch(
            """
            SELECT id, name as company_name, industry, size, status,
                   COALESCE(enabled_features, '{"offer_letters": true}'::jsonb) as enabled_features
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
        # Atomic JSONB update — no read-modify-write race
        updated = await conn.fetchval(
            """
            UPDATE companies
            SET enabled_features = jsonb_set(
                COALESCE(enabled_features, $4::jsonb),
                $1::text[],
                $2::jsonb
            )
            WHERE id = $3
            RETURNING enabled_features
            """,
            [request.feature],
            json.dumps(request.enabled),
            company_id,
            default_company_features_json(),
        )
        if updated is None:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Company not found")

        features = merge_company_features(updated)
        return {"enabled_features": features}


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


@router.post("/jurisdictions", dependencies=[Depends(require_admin)])
async def create_jurisdiction(request: JurisdictionCreateRequest):
    """Create or upsert a jurisdiction. Idempotent on (city, state)."""
    city = request.city.lower().strip()
    state = request.state.upper().strip()[:2]
    county = request.county.strip() if request.county else None

    if not city or not state:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="City and state are required")

    async with get_connection() as conn:
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
            row = await conn.fetchrow("""
                INSERT INTO jurisdictions (city, state, county, parent_id)
                VALUES ($1, $2, $3, $4)
                ON CONFLICT (city, state) DO UPDATE SET
                    parent_id = COALESCE(EXCLUDED.parent_id, jurisdictions.parent_id),
                    county = COALESCE(EXCLUDED.county, jurisdictions.county)
                RETURNING *
            """, city, state, county, request.parent_id)
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
    async with get_connection() as conn:
        rows = await conn.fetch("""
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

        # Batch-fetch all locations for all jurisdictions in one query (avoids N+1)
        jurisdiction_ids = [row["id"] for row in rows]
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
        for row in rows:
            locations = locations_by_jid.get(row["id"], [])
            jurisdictions.append({
                "id": str(row["id"]),
                "city": row["city"],
                "state": row["state"],
                "county": row["county"],
                "parent_id": str(row["parent_id"]) if row["parent_id"] else None,
                "parent_city": row["parent_city"],
                "parent_state": row["parent_state"],
                "children_count": row["children_count"],
                "requirement_count": row["requirement_count"] or 0,
                "legislation_count": row["legislation_count"] or 0,
                "location_count": row["location_count"],
                "auto_check_count": row["auto_check_count"],
                "last_verified_at": row["last_verified_at"].isoformat() if row["last_verified_at"] else None,
                "created_at": row["created_at"].isoformat() if row["created_at"] else None,
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

        # Summary stats
        totals = await conn.fetchrow("""
            SELECT
                COUNT(*) AS total_jurisdictions,
                COALESCE(SUM(requirement_count), 0) AS total_requirements,
                COALESCE(SUM(legislation_count), 0) AS total_legislation
            FROM jurisdictions
        """)

        return {
            "jurisdictions": jurisdictions,
            "totals": {
                "total_jurisdictions": totals["total_jurisdictions"],
                "total_requirements": totals["total_requirements"],
                "total_legislation": totals["total_legislation"],
            },
        }


@router.get("/jurisdictions/{jurisdiction_id}", dependencies=[Depends(require_admin)])
async def get_jurisdiction_detail(jurisdiction_id: UUID):
    """Get full detail for a jurisdiction: requirements, legislation, linked locations."""
    async with get_connection() as conn:
        j = await conn.fetchrow("SELECT * FROM jurisdictions WHERE id = $1", jurisdiction_id)
        if not j:
            raise HTTPException(status_code=404, detail="Jurisdiction not found")

        # Fetch children
        children = await conn.fetch(
            "SELECT id, city, state FROM jurisdictions WHERE parent_id = $1 ORDER BY state, city",
            jurisdiction_id
        )

        requirements = await conn.fetch("""
            SELECT id, requirement_key, category, jurisdiction_level, jurisdiction_name,
                   title, description, current_value, numeric_value,
                   source_url, source_name, effective_date, expiration_date,
                   previous_value, last_changed_at, last_verified_at, created_at, updated_at
            FROM jurisdiction_requirements
            WHERE jurisdiction_id = $1
            ORDER BY category, title
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

        return {
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
                    "last_changed_at": fmt_date(r["last_changed_at"]),
                    "last_verified_at": fmt_date(r["last_verified_at"]),
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


@router.post("/jurisdictions/{jurisdiction_id}/check", dependencies=[Depends(require_admin)])
async def check_jurisdiction(jurisdiction_id: UUID):
    """Run a compliance research check for a jurisdiction. Returns SSE stream with progress."""
    from ..services.gemini_compliance import get_gemini_compliance_service
    from ..services.compliance_service import (
        _upsert_jurisdiction_requirements,
        _upsert_jurisdiction_legislation,
        _normalize_category,
        _filter_by_jurisdiction_priority,
        _sync_requirements_to_location,
        _create_alert,
        score_verification_confidence,
    )
    from ..models.compliance import VerificationResult

    async with get_connection() as conn:
        j = await conn.fetchrow("SELECT * FROM jurisdictions WHERE id = $1", jurisdiction_id)
        if not j:
            raise HTTPException(status_code=404, detail="Jurisdiction not found")

    jurisdiction_name = f"{j['city']}, {j['state']}"
    city, state, county = j["city"], j["state"], j["county"]

    async def event_stream():
        try:
            yield f"data: {json.dumps({'type': 'started', 'location': jurisdiction_name})}\n\n"
            yield f"data: {json.dumps({'type': 'researching', 'message': f'Researching requirements for {jurisdiction_name}...'})}\n\n"

            service = get_gemini_compliance_service()

            # Acquire connection early and hold it for the entire generator lifecycle
            # to avoid "Database pool not initialized" errors after long Gemini calls
            async with get_connection() as conn:
                used_repository = False
                research_queue = asyncio.Queue()
                def _on_retry(attempt, error):
                    research_queue.put_nowait({"type": "retrying", "message": f"Retrying research (attempt {attempt + 1})..."})

                research_task = asyncio.create_task(
                    service.research_location_compliance(
                        city=city, state=state, county=county,
                        on_retry=_on_retry,
                    )
                )
                try:
                    while not research_task.done():
                        while not research_queue.empty():
                            evt = research_queue.get_nowait()
                            yield f"data: {json.dumps(evt)}\n\n"
                        done, _ = await asyncio.wait({research_task}, timeout=8)
                        if done:
                            break
                        yield ": heartbeat\n\n"
                except asyncio.CancelledError:
                    if not research_task.done():
                        research_task.cancel()
                    raise
                # Final drain of retry events
                while not research_queue.empty():
                    evt = research_queue.get_nowait()
                    yield f"data: {json.dumps(evt)}\n\n"
                requirements = research_task.result()

                # Stale-data fallback: if Gemini returned nothing, try cached data
                if not requirements:
                    j_reqs = await conn.fetch(
                        "SELECT * FROM jurisdiction_requirements WHERE jurisdiction_id = $1 ORDER BY category",
                        jurisdiction_id,
                    )
                    if j_reqs:
                        requirements = [_jurisdiction_row_to_dict(dict(r)) for r in j_reqs]
                        used_repository = True
                        logger.warning("Falling back to stale repository data (%d cached requirements)", len(requirements))
                        yield f"data: {json.dumps({'type': 'fallback', 'message': 'Using cached data (live research unavailable)'})}\n\n"

                if not requirements:
                    yield f"data: {json.dumps({'type': 'completed', 'location': jurisdiction_name, 'new': 0, 'updated': 0, 'alerts': 0})}\n\n"
                    yield "data: [DONE]\n\n"
                    return

                for req in requirements:
                    req["category"] = _normalize_category(req.get("category")) or req.get("category")
                requirements = _filter_by_jurisdiction_priority(requirements)

                yield f"data: {json.dumps({'type': 'processing', 'message': f'Processing {len(requirements)} requirements...'})}\n\n"

                if not used_repository:
                    await _upsert_jurisdiction_requirements(conn, jurisdiction_id, requirements)

                new_count = len(requirements)
                for req in requirements:
                    yield f"data: {json.dumps({'type': 'result', 'status': 'new', 'message': req.get('title', '')})}\n\n"

                # Legislation scan
                yield f"data: {json.dumps({'type': 'scanning', 'message': 'Scanning for upcoming legislation...'})}\n\n"
                try:
                    leg_task = asyncio.create_task(
                        service.scan_upcoming_legislation(
                            city=city, state=state, county=county,
                            current_requirements=[dict(r) for r in requirements],
                        )
                    )
                    try:
                        while not leg_task.done():
                            done, _ = await asyncio.wait({leg_task}, timeout=8)
                            if done:
                                break
                            yield ": heartbeat\n\n"
                    except asyncio.CancelledError:
                        if not leg_task.done():
                            leg_task.cancel()
                        raise
                    legislation_items = leg_task.result()
                    await _upsert_jurisdiction_legislation(conn, jurisdiction_id, legislation_items)
                    leg_count = len(legislation_items)
                    if leg_count > 0:
                        yield f"data: {json.dumps({'type': 'legislation', 'message': f'Found {leg_count} upcoming legislative change(s)'})}\n\n"
                except Exception as e:
                    logger.error("Jurisdiction legislation scan error: %s", e)

                # Sync to all company locations linked to this jurisdiction
                linked_locations = await conn.fetch(
                    "SELECT id, company_id FROM business_locations WHERE jurisdiction_id = $1 AND is_active = true",
                    jurisdiction_id,
                )
                total_alerts = 0
                total_updated = 0
                # Cache Gemini verification results keyed by (category, old_value, new_value)
                # so each unique change is verified only once across all locations.
                verified_changes: dict[tuple, tuple[float, VerificationResult]] = {}

                if linked_locations:
                    yield f"data: {json.dumps({'type': 'syncing', 'message': f'Syncing to {len(linked_locations)} location(s)...'})}\n\n"
                    for loc in linked_locations:
                        try:
                            sync_result = await _sync_requirements_to_location(
                                conn, loc["id"], loc["company_id"], requirements,
                                create_alerts=True,
                            )
                            total_alerts += sync_result["alerts"]
                            total_updated += sync_result["updated"]

                            # Verify material changes with Gemini — same flow
                            # as the regular check in compliance_service.py.
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
                                                yield ": heartbeat\n\n"
                                        except asyncio.CancelledError:
                                            if not verify_task.done():
                                                verify_task.cancel()
                                            raise
                                        verification = verify_task.result()
                                        confidence = max(
                                            score_verification_confidence(verification.sources),
                                            verification.confidence,
                                        )
                                    except Exception as e:
                                        logger.error("Verification failed: %s", e)
                                        verification = VerificationResult(
                                            confirmed=False, confidence=0.0, sources=[],
                                            explanation="Verification unavailable",
                                        )
                                        confidence = 0.5
                                    verified_changes[cache_key] = (confidence, verification)

                                confidence, verification = verified_changes[cache_key]

                                change_msg = f"Value changed from {old_val} to {new_val}."
                                if req.get("description"):
                                    change_msg += f" {req['description']}"

                                if confidence >= 0.6:
                                    total_alerts += 1
                                    await _create_alert(
                                        conn, loc["id"], loc["company_id"], existing["id"],
                                        f"Compliance Change: {req.get('title')}", change_msg,
                                        "warning", req.get("category"),
                                        source_url=req.get("source_url"), source_name=req.get("source_name"),
                                        alert_type="change", confidence_score=round(confidence, 2),
                                        verification_sources=verification.sources,
                                        metadata={"source": "jurisdiction_sync", "verification_explanation": verification.explanation},
                                    )
                                elif confidence >= 0.3:
                                    total_alerts += 1
                                    await _create_alert(
                                        conn, loc["id"], loc["company_id"], existing["id"],
                                        f"Unverified: {req.get('title')}", change_msg,
                                        "info", req.get("category"),
                                        source_url=req.get("source_url"), source_name=req.get("source_name"),
                                        alert_type="change", confidence_score=round(confidence, 2),
                                        verification_sources=verification.sources,
                                        metadata={"source": "jurisdiction_sync", "verification_explanation": verification.explanation, "unverified": True},
                                    )
                                else:
                                    logger.warning("Low confidence (%.2f) for change: %s, skipping alert", confidence, req.get('title'))

                            await conn.execute(
                                "UPDATE business_locations SET last_compliance_check = NOW() WHERE id = $1",
                                loc["id"],
                            )
                        except Exception as e:
                            logger.error("Failed to sync location %s: %s", loc['id'], e)

                # Check if poster template needs regeneration
                try:
                    from ..services.poster_service import check_and_regenerate_poster, create_poster_update_alerts
                    poster_result = await check_and_regenerate_poster(conn, jurisdiction_id)
                    if poster_result and poster_result.get("status") == "generated":
                        poster_ver = poster_result.get("version", "?")
                        yield f"data: {json.dumps({'type': 'poster_updated', 'message': f'Poster PDF regenerated (v{poster_ver})'})}\n\n"
                        alert_count = await create_poster_update_alerts(conn, jurisdiction_id)
                        if alert_count:
                            total_alerts += alert_count
                            yield f"data: {json.dumps({'type': 'poster_alerts', 'message': f'Notified {alert_count} company(s) about poster update'})}\n\n"
                except Exception as e:
                    logger.error("Poster regeneration check failed: %s", e)

                yield f"data: {json.dumps({'type': 'completed', 'location': jurisdiction_name, 'new': new_count, 'updated': total_updated, 'alerts': total_alerts})}\n\n"
        except Exception as e:
            logger.error("Jurisdiction check failed for %s: %s", jurisdiction_id, e, exc_info=True)
            yield f"data: {json.dumps({'type': 'error', 'message': 'Jurisdiction check failed'})}\n\n"
        yield "data: [DONE]\n\n"

    return StreamingResponse(
        event_stream(),
        media_type="text/event-stream",
        headers={"X-Accel-Buffering": "no"},
    )


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
