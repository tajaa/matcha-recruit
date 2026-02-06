"""Admin routes for business registration approval workflow and company feature management."""

import asyncio
import json
import logging
from datetime import datetime
from typing import Optional
from uuid import UUID

from fastapi import APIRouter, HTTPException, Depends, Query, status
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field

logger = logging.getLogger(__name__)

from ...database import get_connection
from ..dependencies import require_admin
from ..services.email import get_email_service
from ..models.compliance import AutoCheckSettings
from ..services.compliance_service import (
    update_auto_check_settings,
    _jurisdiction_row_to_dict,
)
from ..services.rate_limiter import get_rate_limiter

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


# =============================================================================
# Scheduler Management
# =============================================================================

class SchedulerUpdateRequest(BaseModel):
    """Request model for updating scheduler settings."""
    enabled: Optional[bool] = None
    max_per_cycle: Optional[int] = None


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

    if task_key == "compliance_checks":
        enqueue_scheduled_compliance_checks.delay()
        return {"status": "triggered", "task_key": task_key, "message": "Compliance checks enqueued"}
    elif task_key == "deadline_escalation":
        run_deadline_escalation.delay()
        return {"status": "triggered", "task_key": task_key, "message": "Deadline escalation enqueued"}
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
