"""Admin routes for business registration approval workflow and company feature management."""

import json
from datetime import datetime
from typing import Optional
from uuid import UUID

from fastapi import APIRouter, HTTPException, Depends, Query, status
from pydantic import BaseModel

from ...database import get_connection
from ..dependencies import require_admin
from ..services.email import get_email_service

router = APIRouter()


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
    "offer_letters", "policies", "compliance", "employees",
    "vibe_checks", "enps", "performance_reviews",
    "er_copilot", "incidents", "time_off",
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
                "enabled_features": json.loads(row["enabled_features"]) if isinstance(row["enabled_features"], str) else row["enabled_features"],
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
                COALESCE(enabled_features, '{"offer_letters": true}'::jsonb),
                $1::text[],
                $2::jsonb
            )
            WHERE id = $3
            RETURNING enabled_features
            """,
            [request.feature],
            json.dumps(request.enabled),
            company_id,
        )
        if updated is None:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Company not found")

        features = json.loads(updated) if isinstance(updated, str) else updated
        return {"enabled_features": features}
