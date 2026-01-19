"""
Deals routes for the Creator/Influencer Management Platform.
Handles brand deals, applications, contracts, and payments.
"""
from datetime import date
from decimal import Decimal
from typing import Optional
from uuid import UUID
import json

from fastapi import APIRouter, Depends, HTTPException, Query

from ..database import get_connection
from ..dependencies import (
    get_current_user,
    require_creator,
    require_creator_record,
    require_agency,
    require_agency_membership,
    require_agency_admin,
)
from ..models.auth import CurrentUser
from ..models.deals import (
    BrandDealCreate,
    BrandDealUpdate,
    BrandDealResponse,
    BrandDealPublicResponse,
    DealApplicationCreate,
    DealApplicationUpdate,
    DealApplicationResponse,
    ApplicationStatusUpdate,
    ContractCreate,
    ContractResponse,
    ContractStatusUpdate,
    PaymentCreate,
    PaymentUpdate,
    PaymentResponse,
    CreatorDealMatchResponse,
)

router = APIRouter()


def parse_jsonb(value):
    """Parse JSONB value from database."""
    if value is None:
        return [] if isinstance(value, list) else {}
    if isinstance(value, str):
        return json.loads(value)
    return value


# =============================================================================
# Public Marketplace Endpoints (for Creators)
# =============================================================================

@router.get("/marketplace", response_model=list[BrandDealPublicResponse])
async def browse_marketplace(
    niches: Optional[str] = Query(None, description="Comma-separated niches"),
    min_compensation: Optional[int] = None,
    max_compensation: Optional[int] = None,
    platforms: Optional[str] = Query(None, description="Comma-separated platforms"),
    limit: int = Query(20, le=100),
    offset: int = 0,
):
    """Browse open brand deals in the marketplace."""
    async with get_connection() as conn:
        query = """
            SELECT d.*, a.name as agency_name, a.is_verified as agency_verified
            FROM brand_deals d
            JOIN agencies a ON d.agency_id = a.id
            WHERE d.status = 'open' AND d.visibility = 'public'
        """
        params = []
        param_count = 0

        if niches:
            niche_list = [n.strip() for n in niches.split(",")]
            param_count += 1
            query += f" AND d.niches ?| ${param_count}"
            params.append(niche_list)

        if min_compensation:
            param_count += 1
            query += f" AND d.compensation_min >= ${param_count}"
            params.append(min_compensation)

        if max_compensation:
            param_count += 1
            query += f" AND d.compensation_max <= ${param_count}"
            params.append(max_compensation)

        if platforms:
            platform_list = [p.strip() for p in platforms.split(",")]
            param_count += 1
            query += f" AND d.preferred_platforms ?| ${param_count}"
            params.append(platform_list)

        query += " ORDER BY a.is_verified DESC, d.created_at DESC"
        query += f" LIMIT ${param_count + 1} OFFSET ${param_count + 2}"
        params.extend([limit, offset])

        rows = await conn.fetch(query, *params)

        return [
            BrandDealPublicResponse(
                id=row["id"],
                agency_name=row["agency_name"],
                agency_verified=row["agency_verified"],
                title=row["title"],
                brand_name=row["brand_name"],
                description=row["description"],
                deliverables=parse_jsonb(row["deliverables"]),
                compensation_type=row["compensation_type"],
                compensation_min=row["compensation_min"],
                compensation_max=row["compensation_max"],
                compensation_currency=row["compensation_currency"],
                niches=parse_jsonb(row["niches"]),
                min_followers=row["min_followers"],
                max_followers=row["max_followers"],
                preferred_platforms=parse_jsonb(row["preferred_platforms"]),
                timeline_start=row["timeline_start"],
                timeline_end=row["timeline_end"],
                application_deadline=row["application_deadline"],
                created_at=row["created_at"],
            )
            for row in rows
        ]


@router.get("/marketplace/{deal_id}", response_model=BrandDealPublicResponse)
async def get_marketplace_deal(deal_id: UUID):
    """Get a specific deal from the marketplace."""
    async with get_connection() as conn:
        row = await conn.fetchrow(
            """SELECT d.*, a.name as agency_name, a.is_verified as agency_verified
               FROM brand_deals d
               JOIN agencies a ON d.agency_id = a.id
               WHERE d.id = $1 AND d.status = 'open' AND d.visibility = 'public'""",
            deal_id,
        )

        if not row:
            raise HTTPException(status_code=404, detail="Deal not found")

        return BrandDealPublicResponse(
            id=row["id"],
            agency_name=row["agency_name"],
            agency_verified=row["agency_verified"],
            title=row["title"],
            brand_name=row["brand_name"],
            description=row["description"],
            deliverables=parse_jsonb(row["deliverables"]),
            compensation_type=row["compensation_type"],
            compensation_min=row["compensation_min"],
            compensation_max=row["compensation_max"],
            compensation_currency=row["compensation_currency"],
            niches=parse_jsonb(row["niches"]),
            min_followers=row["min_followers"],
            max_followers=row["max_followers"],
            preferred_platforms=parse_jsonb(row["preferred_platforms"]),
            timeline_start=row["timeline_start"],
            timeline_end=row["timeline_end"],
            application_deadline=row["application_deadline"],
            created_at=row["created_at"],
        )


# =============================================================================
# Agency Deal Management Endpoints
# =============================================================================

@router.post("/agency/deals", response_model=BrandDealResponse)
async def create_deal(
    deal: BrandDealCreate,
    membership: dict = Depends(require_agency_admin),
):
    """Create a new brand deal. Requires agency admin/owner role."""
    async with get_connection() as conn:
        row = await conn.fetchrow(
            """INSERT INTO brand_deals
               (agency_id, title, brand_name, description, requirements,
                deliverables, compensation_type, compensation_min, compensation_max,
                compensation_currency, compensation_details, niches, min_followers,
                max_followers, preferred_platforms, audience_requirements,
                timeline_start, timeline_end, application_deadline, visibility)
               VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9, $10, $11, $12, $13,
                       $14, $15, $16, $17, $18, $19, $20)
               RETURNING *""",
            membership["agency_id"],
            deal.title,
            deal.brand_name,
            deal.description,
            json.dumps(deal.requirements) if deal.requirements else "{}",
            json.dumps(deal.deliverables) if deal.deliverables else "[]",
            deal.compensation_type,
            deal.compensation_min,
            deal.compensation_max,
            deal.compensation_currency,
            deal.compensation_details,
            json.dumps(deal.niches) if deal.niches else "[]",
            deal.min_followers,
            deal.max_followers,
            json.dumps(deal.preferred_platforms) if deal.preferred_platforms else "[]",
            json.dumps(deal.audience_requirements) if deal.audience_requirements else "{}",
            deal.timeline_start,
            deal.timeline_end,
            deal.application_deadline,
            deal.visibility,
        )

        return BrandDealResponse(
            id=row["id"],
            agency_id=row["agency_id"],
            agency_name=membership["agency_name"],
            title=row["title"],
            brand_name=row["brand_name"],
            description=row["description"],
            requirements=parse_jsonb(row["requirements"]),
            deliverables=parse_jsonb(row["deliverables"]),
            compensation_type=row["compensation_type"],
            compensation_min=row["compensation_min"],
            compensation_max=row["compensation_max"],
            compensation_currency=row["compensation_currency"],
            compensation_details=row["compensation_details"],
            niches=parse_jsonb(row["niches"]),
            min_followers=row["min_followers"],
            max_followers=row["max_followers"],
            preferred_platforms=parse_jsonb(row["preferred_platforms"]),
            audience_requirements=parse_jsonb(row["audience_requirements"]),
            timeline_start=row["timeline_start"],
            timeline_end=row["timeline_end"],
            application_deadline=row["application_deadline"],
            status=row["status"],
            visibility=row["visibility"],
            applications_count=row["applications_count"],
            created_at=row["created_at"],
            updated_at=row["updated_at"],
        )


@router.get("/agency/deals", response_model=list[BrandDealResponse])
async def list_agency_deals(
    status: Optional[str] = None,
    membership: dict = Depends(require_agency_membership),
):
    """List all deals for the current agency."""
    async with get_connection() as conn:
        query = "SELECT * FROM brand_deals WHERE agency_id = $1"
        params = [membership["agency_id"]]

        if status:
            query += " AND status = $2"
            params.append(status)

        query += " ORDER BY created_at DESC"

        rows = await conn.fetch(query, *params)

        return [
            BrandDealResponse(
                id=row["id"],
                agency_id=row["agency_id"],
                agency_name=membership["agency_name"],
                title=row["title"],
                brand_name=row["brand_name"],
                description=row["description"],
                requirements=parse_jsonb(row["requirements"]),
                deliverables=parse_jsonb(row["deliverables"]),
                compensation_type=row["compensation_type"],
                compensation_min=row["compensation_min"],
                compensation_max=row["compensation_max"],
                compensation_currency=row["compensation_currency"],
                compensation_details=row["compensation_details"],
                niches=parse_jsonb(row["niches"]),
                min_followers=row["min_followers"],
                max_followers=row["max_followers"],
                preferred_platforms=parse_jsonb(row["preferred_platforms"]),
                audience_requirements=parse_jsonb(row["audience_requirements"]),
                timeline_start=row["timeline_start"],
                timeline_end=row["timeline_end"],
                application_deadline=row["application_deadline"],
                status=row["status"],
                visibility=row["visibility"],
                applications_count=row["applications_count"],
                created_at=row["created_at"],
                updated_at=row["updated_at"],
            )
            for row in rows
        ]


@router.get("/agency/deals/{deal_id}", response_model=BrandDealResponse)
async def get_agency_deal(
    deal_id: UUID,
    membership: dict = Depends(require_agency_membership),
):
    """Get a specific deal for the current agency."""
    async with get_connection() as conn:
        row = await conn.fetchrow(
            "SELECT * FROM brand_deals WHERE id = $1 AND agency_id = $2",
            deal_id,
            membership["agency_id"],
        )

        if not row:
            raise HTTPException(status_code=404, detail="Deal not found")

        return BrandDealResponse(
            id=row["id"],
            agency_id=row["agency_id"],
            agency_name=membership["agency_name"],
            title=row["title"],
            brand_name=row["brand_name"],
            description=row["description"],
            requirements=parse_jsonb(row["requirements"]),
            deliverables=parse_jsonb(row["deliverables"]),
            compensation_type=row["compensation_type"],
            compensation_min=row["compensation_min"],
            compensation_max=row["compensation_max"],
            compensation_currency=row["compensation_currency"],
            compensation_details=row["compensation_details"],
            niches=parse_jsonb(row["niches"]),
            min_followers=row["min_followers"],
            max_followers=row["max_followers"],
            preferred_platforms=parse_jsonb(row["preferred_platforms"]),
            audience_requirements=parse_jsonb(row["audience_requirements"]),
            timeline_start=row["timeline_start"],
            timeline_end=row["timeline_end"],
            application_deadline=row["application_deadline"],
            status=row["status"],
            visibility=row["visibility"],
            applications_count=row["applications_count"],
            created_at=row["created_at"],
            updated_at=row["updated_at"],
        )


@router.put("/agency/deals/{deal_id}", response_model=BrandDealResponse)
async def update_deal(
    deal_id: UUID,
    update: BrandDealUpdate,
    membership: dict = Depends(require_agency_admin),
):
    """Update a deal. Requires agency admin/owner role."""
    async with get_connection() as conn:
        existing = await conn.fetchrow(
            "SELECT * FROM brand_deals WHERE id = $1 AND agency_id = $2",
            deal_id,
            membership["agency_id"],
        )

        if not existing:
            raise HTTPException(status_code=404, detail="Deal not found")

        update_data = update.model_dump(exclude_unset=True)
        if not update_data:
            raise HTTPException(status_code=400, detail="No fields to update")

        # Convert complex types to JSON
        for field in ["requirements", "deliverables", "niches", "preferred_platforms", "audience_requirements"]:
            if field in update_data and update_data[field] is not None:
                update_data[field] = json.dumps(update_data[field])

        set_clauses = [f"{k} = ${i+1}" for i, k in enumerate(update_data.keys())]
        set_clauses.append("updated_at = NOW()")

        row = await conn.fetchrow(
            f"""UPDATE brand_deals
                SET {", ".join(set_clauses)}
                WHERE id = ${len(update_data) + 1}
                RETURNING *""",
            *update_data.values(),
            deal_id,
        )

        return BrandDealResponse(
            id=row["id"],
            agency_id=row["agency_id"],
            agency_name=membership["agency_name"],
            title=row["title"],
            brand_name=row["brand_name"],
            description=row["description"],
            requirements=parse_jsonb(row["requirements"]),
            deliverables=parse_jsonb(row["deliverables"]),
            compensation_type=row["compensation_type"],
            compensation_min=row["compensation_min"],
            compensation_max=row["compensation_max"],
            compensation_currency=row["compensation_currency"],
            compensation_details=row["compensation_details"],
            niches=parse_jsonb(row["niches"]),
            min_followers=row["min_followers"],
            max_followers=row["max_followers"],
            preferred_platforms=parse_jsonb(row["preferred_platforms"]),
            audience_requirements=parse_jsonb(row["audience_requirements"]),
            timeline_start=row["timeline_start"],
            timeline_end=row["timeline_end"],
            application_deadline=row["application_deadline"],
            status=row["status"],
            visibility=row["visibility"],
            applications_count=row["applications_count"],
            created_at=row["created_at"],
            updated_at=row["updated_at"],
        )


@router.delete("/agency/deals/{deal_id}")
async def delete_deal(
    deal_id: UUID,
    membership: dict = Depends(require_agency_admin),
):
    """Delete a deal. Requires agency admin/owner role."""
    async with get_connection() as conn:
        result = await conn.execute(
            "DELETE FROM brand_deals WHERE id = $1 AND agency_id = $2",
            deal_id,
            membership["agency_id"],
        )

        if result == "DELETE 0":
            raise HTTPException(status_code=404, detail="Deal not found")

        return {"status": "deleted"}


# =============================================================================
# Creator Application Endpoints
# =============================================================================

@router.post("/apply/{deal_id}", response_model=DealApplicationResponse)
async def apply_to_deal(
    deal_id: UUID,
    application: DealApplicationCreate,
    creator: dict = Depends(require_creator_record),
):
    """Apply to a brand deal as a creator."""
    async with get_connection() as conn:
        # Verify deal exists and is open
        deal = await conn.fetchrow(
            "SELECT * FROM brand_deals WHERE id = $1 AND status = 'open'",
            deal_id,
        )

        if not deal:
            raise HTTPException(status_code=404, detail="Deal not found or not open for applications")

        # Check if already applied
        existing = await conn.fetchrow(
            "SELECT * FROM deal_applications WHERE deal_id = $1 AND creator_id = $2",
            deal_id,
            creator["id"],
        )

        if existing:
            raise HTTPException(status_code=400, detail="You have already applied to this deal")

        # Create application
        row = await conn.fetchrow(
            """INSERT INTO deal_applications
               (deal_id, creator_id, pitch, proposed_rate, proposed_currency,
                proposed_deliverables, portfolio_links, availability_notes)
               VALUES ($1, $2, $3, $4, $5, $6, $7, $8)
               RETURNING *""",
            deal_id,
            creator["id"],
            application.pitch,
            application.proposed_rate,
            application.proposed_currency,
            json.dumps(application.proposed_deliverables) if application.proposed_deliverables else "[]",
            json.dumps(application.portfolio_links) if application.portfolio_links else "[]",
            application.availability_notes,
        )

        # Update application count
        await conn.execute(
            "UPDATE brand_deals SET applications_count = applications_count + 1 WHERE id = $1",
            deal_id,
        )

        return DealApplicationResponse(
            id=row["id"],
            deal_id=row["deal_id"],
            deal_title=deal["title"],
            creator_id=row["creator_id"],
            creator_name=creator["display_name"],
            pitch=row["pitch"],
            proposed_rate=row["proposed_rate"],
            proposed_currency=row["proposed_currency"],
            proposed_deliverables=parse_jsonb(row["proposed_deliverables"]),
            portfolio_links=parse_jsonb(row["portfolio_links"]),
            availability_notes=row["availability_notes"],
            status=row["status"],
            agency_notes=row["agency_notes"],
            match_score=row["match_score"],
            created_at=row["created_at"],
            updated_at=row["updated_at"],
        )


@router.get("/my-applications", response_model=list[DealApplicationResponse])
async def list_my_applications(
    status: Optional[str] = None,
    creator: dict = Depends(require_creator_record),
):
    """List all applications for the current creator."""
    async with get_connection() as conn:
        query = """
            SELECT da.*, bd.title as deal_title
            FROM deal_applications da
            JOIN brand_deals bd ON da.deal_id = bd.id
            WHERE da.creator_id = $1
        """
        params = [creator["id"]]

        if status:
            query += " AND da.status = $2"
            params.append(status)

        query += " ORDER BY da.created_at DESC"

        rows = await conn.fetch(query, *params)

        return [
            DealApplicationResponse(
                id=row["id"],
                deal_id=row["deal_id"],
                deal_title=row["deal_title"],
                creator_id=row["creator_id"],
                creator_name=creator["display_name"],
                pitch=row["pitch"],
                proposed_rate=row["proposed_rate"],
                proposed_currency=row["proposed_currency"],
                proposed_deliverables=parse_jsonb(row["proposed_deliverables"]),
                portfolio_links=parse_jsonb(row["portfolio_links"]),
                availability_notes=row["availability_notes"],
                status=row["status"],
                agency_notes=row["agency_notes"],
                match_score=row["match_score"],
                created_at=row["created_at"],
                updated_at=row["updated_at"],
            )
            for row in rows
        ]


@router.put("/my-applications/{application_id}", response_model=DealApplicationResponse)
async def update_my_application(
    application_id: UUID,
    update: DealApplicationUpdate,
    creator: dict = Depends(require_creator_record),
):
    """Update an application. Can only update pending applications."""
    async with get_connection() as conn:
        existing = await conn.fetchrow(
            """SELECT da.*, bd.title as deal_title
               FROM deal_applications da
               JOIN brand_deals bd ON da.deal_id = bd.id
               WHERE da.id = $1 AND da.creator_id = $2""",
            application_id,
            creator["id"],
        )

        if not existing:
            raise HTTPException(status_code=404, detail="Application not found")

        if existing["status"] != "pending":
            raise HTTPException(status_code=400, detail="Can only update pending applications")

        update_data = update.model_dump(exclude_unset=True)
        if not update_data:
            raise HTTPException(status_code=400, detail="No fields to update")

        for field in ["proposed_deliverables", "portfolio_links"]:
            if field in update_data and update_data[field] is not None:
                update_data[field] = json.dumps(update_data[field])

        set_clauses = [f"{k} = ${i+1}" for i, k in enumerate(update_data.keys())]
        set_clauses.append("updated_at = NOW()")

        row = await conn.fetchrow(
            f"""UPDATE deal_applications
                SET {", ".join(set_clauses)}
                WHERE id = ${len(update_data) + 1}
                RETURNING *""",
            *update_data.values(),
            application_id,
        )

        return DealApplicationResponse(
            id=row["id"],
            deal_id=row["deal_id"],
            deal_title=existing["deal_title"],
            creator_id=row["creator_id"],
            creator_name=creator["display_name"],
            pitch=row["pitch"],
            proposed_rate=row["proposed_rate"],
            proposed_currency=row["proposed_currency"],
            proposed_deliverables=parse_jsonb(row["proposed_deliverables"]),
            portfolio_links=parse_jsonb(row["portfolio_links"]),
            availability_notes=row["availability_notes"],
            status=row["status"],
            agency_notes=row["agency_notes"],
            match_score=row["match_score"],
            created_at=row["created_at"],
            updated_at=row["updated_at"],
        )


@router.post("/my-applications/{application_id}/withdraw")
async def withdraw_application(
    application_id: UUID,
    creator: dict = Depends(require_creator_record),
):
    """Withdraw an application."""
    async with get_connection() as conn:
        existing = await conn.fetchrow(
            "SELECT * FROM deal_applications WHERE id = $1 AND creator_id = $2",
            application_id,
            creator["id"],
        )

        if not existing:
            raise HTTPException(status_code=404, detail="Application not found")

        if existing["status"] in ["accepted", "rejected"]:
            raise HTTPException(status_code=400, detail="Cannot withdraw an accepted or rejected application")

        await conn.execute(
            "UPDATE deal_applications SET status = 'withdrawn', updated_at = NOW() WHERE id = $1",
            application_id,
        )

        return {"status": "withdrawn"}


# =============================================================================
# Agency Application Review Endpoints
# =============================================================================

@router.get("/agency/deals/{deal_id}/applications", response_model=list[DealApplicationResponse])
async def list_deal_applications(
    deal_id: UUID,
    status: Optional[str] = None,
    membership: dict = Depends(require_agency_membership),
):
    """List all applications for a deal."""
    async with get_connection() as conn:
        # Verify deal ownership
        deal = await conn.fetchrow(
            "SELECT * FROM brand_deals WHERE id = $1 AND agency_id = $2",
            deal_id,
            membership["agency_id"],
        )

        if not deal:
            raise HTTPException(status_code=404, detail="Deal not found")

        query = """
            SELECT da.*, c.display_name as creator_name
            FROM deal_applications da
            JOIN creators c ON da.creator_id = c.id
            WHERE da.deal_id = $1
        """
        params = [deal_id]

        if status:
            query += " AND da.status = $2"
            params.append(status)

        query += " ORDER BY da.match_score DESC NULLS LAST, da.created_at"

        rows = await conn.fetch(query, *params)

        return [
            DealApplicationResponse(
                id=row["id"],
                deal_id=row["deal_id"],
                deal_title=deal["title"],
                creator_id=row["creator_id"],
                creator_name=row["creator_name"],
                pitch=row["pitch"],
                proposed_rate=row["proposed_rate"],
                proposed_currency=row["proposed_currency"],
                proposed_deliverables=parse_jsonb(row["proposed_deliverables"]),
                portfolio_links=parse_jsonb(row["portfolio_links"]),
                availability_notes=row["availability_notes"],
                status=row["status"],
                agency_notes=row["agency_notes"],
                match_score=row["match_score"],
                created_at=row["created_at"],
                updated_at=row["updated_at"],
            )
            for row in rows
        ]


@router.put("/agency/applications/{application_id}/status", response_model=DealApplicationResponse)
async def update_application_status(
    application_id: UUID,
    update: ApplicationStatusUpdate,
    membership: dict = Depends(require_agency_admin),
):
    """Update an application's status. Requires agency admin/owner role."""
    async with get_connection() as conn:
        # Verify ownership
        existing = await conn.fetchrow(
            """SELECT da.*, bd.agency_id, bd.title as deal_title, c.display_name as creator_name
               FROM deal_applications da
               JOIN brand_deals bd ON da.deal_id = bd.id
               JOIN creators c ON da.creator_id = c.id
               WHERE da.id = $1""",
            application_id,
        )

        if not existing:
            raise HTTPException(status_code=404, detail="Application not found")

        if existing["agency_id"] != membership["agency_id"]:
            raise HTTPException(status_code=403, detail="Not authorized")

        row = await conn.fetchrow(
            """UPDATE deal_applications
               SET status = $1, agency_notes = COALESCE($2, agency_notes), updated_at = NOW()
               WHERE id = $3
               RETURNING *""",
            update.status,
            update.agency_notes,
            application_id,
        )

        return DealApplicationResponse(
            id=row["id"],
            deal_id=row["deal_id"],
            deal_title=existing["deal_title"],
            creator_id=row["creator_id"],
            creator_name=existing["creator_name"],
            pitch=row["pitch"],
            proposed_rate=row["proposed_rate"],
            proposed_currency=row["proposed_currency"],
            proposed_deliverables=parse_jsonb(row["proposed_deliverables"]),
            portfolio_links=parse_jsonb(row["portfolio_links"]),
            availability_notes=row["availability_notes"],
            status=row["status"],
            agency_notes=row["agency_notes"],
            match_score=row["match_score"],
            created_at=row["created_at"],
            updated_at=row["updated_at"],
        )


# =============================================================================
# Contract Endpoints
# =============================================================================

@router.post("/agency/applications/{application_id}/contract", response_model=ContractResponse)
async def create_contract(
    application_id: UUID,
    contract: ContractCreate,
    membership: dict = Depends(require_agency_admin),
):
    """Create a contract from an accepted application."""
    async with get_connection() as conn:
        # Verify application and ownership
        application = await conn.fetchrow(
            """SELECT da.*, bd.agency_id, bd.id as deal_id, bd.title as deal_title,
                      c.display_name as creator_name
               FROM deal_applications da
               JOIN brand_deals bd ON da.deal_id = bd.id
               JOIN creators c ON da.creator_id = c.id
               WHERE da.id = $1""",
            application_id,
        )

        if not application:
            raise HTTPException(status_code=404, detail="Application not found")

        if application["agency_id"] != membership["agency_id"]:
            raise HTTPException(status_code=403, detail="Not authorized")

        if application["status"] != "accepted":
            raise HTTPException(status_code=400, detail="Application must be accepted before creating a contract")

        # Check if contract already exists
        existing_contract = await conn.fetchrow(
            "SELECT * FROM deal_contracts WHERE application_id = $1",
            application_id,
        )

        if existing_contract:
            raise HTTPException(status_code=400, detail="Contract already exists for this application")

        row = await conn.fetchrow(
            """INSERT INTO deal_contracts
               (deal_id, application_id, creator_id, agency_id, agreed_rate,
                agreed_currency, agreed_deliverables, terms, start_date, end_date)
               VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9, $10)
               RETURNING *""",
            application["deal_id"],
            application_id,
            application["creator_id"],
            membership["agency_id"],
            contract.agreed_rate,
            contract.agreed_currency,
            json.dumps(contract.agreed_deliverables),
            contract.terms,
            contract.start_date,
            contract.end_date,
        )

        return ContractResponse(
            id=row["id"],
            deal_id=row["deal_id"],
            deal_title=application["deal_title"],
            application_id=row["application_id"],
            creator_id=row["creator_id"],
            creator_name=application["creator_name"],
            agency_id=row["agency_id"],
            agency_name=membership["agency_name"],
            agreed_rate=row["agreed_rate"],
            agreed_currency=row["agreed_currency"],
            agreed_deliverables=parse_jsonb(row["agreed_deliverables"]),
            terms=row["terms"],
            contract_document_url=row["contract_document_url"],
            start_date=row["start_date"],
            end_date=row["end_date"],
            status=row["status"],
            total_paid=row["total_paid"],
            created_at=row["created_at"],
            updated_at=row["updated_at"],
        )


@router.get("/my-contracts", response_model=list[ContractResponse])
async def list_my_contracts(
    status: Optional[str] = None,
    creator: dict = Depends(require_creator_record),
):
    """List all contracts for the current creator."""
    async with get_connection() as conn:
        query = """
            SELECT dc.*, bd.title as deal_title, a.name as agency_name
            FROM deal_contracts dc
            JOIN brand_deals bd ON dc.deal_id = bd.id
            JOIN agencies a ON dc.agency_id = a.id
            WHERE dc.creator_id = $1
        """
        params = [creator["id"]]

        if status:
            query += " AND dc.status = $2"
            params.append(status)

        query += " ORDER BY dc.created_at DESC"

        rows = await conn.fetch(query, *params)

        return [
            ContractResponse(
                id=row["id"],
                deal_id=row["deal_id"],
                deal_title=row["deal_title"],
                application_id=row["application_id"],
                creator_id=row["creator_id"],
                creator_name=creator["display_name"],
                agency_id=row["agency_id"],
                agency_name=row["agency_name"],
                agreed_rate=row["agreed_rate"],
                agreed_currency=row["agreed_currency"],
                agreed_deliverables=parse_jsonb(row["agreed_deliverables"]),
                terms=row["terms"],
                contract_document_url=row["contract_document_url"],
                start_date=row["start_date"],
                end_date=row["end_date"],
                status=row["status"],
                total_paid=row["total_paid"],
                created_at=row["created_at"],
                updated_at=row["updated_at"],
            )
            for row in rows
        ]


@router.get("/agency/contracts", response_model=list[ContractResponse])
async def list_agency_contracts(
    status: Optional[str] = None,
    membership: dict = Depends(require_agency_membership),
):
    """List all contracts for the current agency."""
    async with get_connection() as conn:
        query = """
            SELECT dc.*, bd.title as deal_title, c.display_name as creator_name
            FROM deal_contracts dc
            JOIN brand_deals bd ON dc.deal_id = bd.id
            JOIN creators c ON dc.creator_id = c.id
            WHERE dc.agency_id = $1
        """
        params = [membership["agency_id"]]

        if status:
            query += " AND dc.status = $2"
            params.append(status)

        query += " ORDER BY dc.created_at DESC"

        rows = await conn.fetch(query, *params)

        return [
            ContractResponse(
                id=row["id"],
                deal_id=row["deal_id"],
                deal_title=row["deal_title"],
                application_id=row["application_id"],
                creator_id=row["creator_id"],
                creator_name=row["creator_name"],
                agency_id=row["agency_id"],
                agency_name=membership["agency_name"],
                agreed_rate=row["agreed_rate"],
                agreed_currency=row["agreed_currency"],
                agreed_deliverables=parse_jsonb(row["agreed_deliverables"]),
                terms=row["terms"],
                contract_document_url=row["contract_document_url"],
                start_date=row["start_date"],
                end_date=row["end_date"],
                status=row["status"],
                total_paid=row["total_paid"],
                created_at=row["created_at"],
                updated_at=row["updated_at"],
            )
            for row in rows
        ]


@router.put("/agency/contracts/{contract_id}/status")
async def update_contract_status(
    contract_id: UUID,
    update: ContractStatusUpdate,
    membership: dict = Depends(require_agency_admin),
):
    """Update a contract's status."""
    async with get_connection() as conn:
        existing = await conn.fetchrow(
            "SELECT * FROM deal_contracts WHERE id = $1 AND agency_id = $2",
            contract_id,
            membership["agency_id"],
        )

        if not existing:
            raise HTTPException(status_code=404, detail="Contract not found")

        await conn.execute(
            "UPDATE deal_contracts SET status = $1, updated_at = NOW() WHERE id = $2",
            update.status,
            contract_id,
        )

        return {"status": "updated", "new_status": update.status}


# =============================================================================
# Payment Endpoints
# =============================================================================

@router.post("/agency/contracts/{contract_id}/payments", response_model=PaymentResponse)
async def add_payment(
    contract_id: UUID,
    payment: PaymentCreate,
    membership: dict = Depends(require_agency_admin),
):
    """Add a payment milestone to a contract."""
    async with get_connection() as conn:
        contract = await conn.fetchrow(
            "SELECT * FROM deal_contracts WHERE id = $1 AND agency_id = $2",
            contract_id,
            membership["agency_id"],
        )

        if not contract:
            raise HTTPException(status_code=404, detail="Contract not found")

        row = await conn.fetchrow(
            """INSERT INTO contract_payments
               (contract_id, amount, currency, milestone_name, due_date)
               VALUES ($1, $2, $3, $4, $5)
               RETURNING *""",
            contract_id,
            payment.amount,
            payment.currency,
            payment.milestone_name,
            payment.due_date,
        )

        return PaymentResponse(**dict(row))


@router.get("/contracts/{contract_id}/payments", response_model=list[PaymentResponse])
async def list_contract_payments(
    contract_id: UUID,
    current_user: CurrentUser = Depends(get_current_user),
):
    """List all payments for a contract (accessible by both creators and agencies)."""
    async with get_connection() as conn:
        # Verify access
        contract = await conn.fetchrow(
            "SELECT * FROM deal_contracts WHERE id = $1",
            contract_id,
        )

        if not contract:
            raise HTTPException(status_code=404, detail="Contract not found")

        # Check if user is creator or agency member
        if current_user.role == "creator":
            creator = await conn.fetchrow(
                "SELECT id FROM creators WHERE user_id = $1",
                current_user.id
            )
            if not creator or creator["id"] != contract["creator_id"]:
                raise HTTPException(status_code=403, detail="Not authorized")
        elif current_user.role == "agency":
            member = await conn.fetchrow(
                "SELECT * FROM agency_members WHERE user_id = $1 AND agency_id = $2 AND is_active = true",
                current_user.id,
                contract["agency_id"],
            )
            if not member:
                raise HTTPException(status_code=403, detail="Not authorized")
        else:
            raise HTTPException(status_code=403, detail="Not authorized")

        rows = await conn.fetch(
            "SELECT * FROM contract_payments WHERE contract_id = $1 ORDER BY due_date",
            contract_id,
        )

        return [PaymentResponse(**dict(row)) for row in rows]


@router.put("/agency/payments/{payment_id}", response_model=PaymentResponse)
async def update_payment(
    payment_id: UUID,
    update: PaymentUpdate,
    membership: dict = Depends(require_agency_admin),
):
    """Update a payment (mark as paid, etc.)."""
    async with get_connection() as conn:
        # Verify ownership through contract
        payment = await conn.fetchrow(
            """SELECT p.*, c.agency_id
               FROM contract_payments p
               JOIN deal_contracts c ON p.contract_id = c.id
               WHERE p.id = $1""",
            payment_id,
        )

        if not payment:
            raise HTTPException(status_code=404, detail="Payment not found")

        if payment["agency_id"] != membership["agency_id"]:
            raise HTTPException(status_code=403, detail="Not authorized")

        update_data = update.model_dump(exclude_unset=True)
        if not update_data:
            raise HTTPException(status_code=400, detail="No fields to update")

        set_clauses = [f"{k} = ${i+1}" for i, k in enumerate(update_data.keys())]

        row = await conn.fetchrow(
            f"""UPDATE contract_payments
                SET {", ".join(set_clauses)}
                WHERE id = ${len(update_data) + 1}
                RETURNING *""",
            *update_data.values(),
            payment_id,
        )

        # Update total_paid on contract if payment status changes to/from paid
        if update.status == "paid" and payment["status"] != "paid":
            await conn.execute(
                "UPDATE deal_contracts SET total_paid = total_paid + $1 WHERE id = $2",
                payment["amount"],
                payment["contract_id"],
            )
        elif payment["status"] == "paid" and update.status and update.status != "paid":
            await conn.execute(
                "UPDATE deal_contracts SET total_paid = total_paid - $1 WHERE id = $2",
                payment["amount"],
                payment["contract_id"],
            )

        return PaymentResponse(**dict(row))
