"""
Campaign routes for the Creator Campaign & Deal Platform.
Handles campaigns (limit orders), offers, payments, affiliates, valuations, and templates.
"""
import json
import secrets
import string
from datetime import datetime
from decimal import Decimal
from typing import Optional
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from fastapi.responses import RedirectResponse

from ..database import get_connection
from ..dependencies import (
    get_current_user,
    require_creator_record,
    require_agency_membership,
    require_agency_admin,
)
from ..models.auth import CurrentUser
from ..models.campaigns import (
    CampaignCreate,
    CampaignUpdate,
    CampaignResponse,
    CampaignWithOffersResponse,
    CampaignOfferCreate,
    CampaignOfferBulkCreate,
    CampaignOfferResponse,
    CreatorOfferResponse,
    OfferAcceptRequest,
    OfferDeclineRequest,
    OfferCounterRequest,
    CampaignPaymentResponse,
    PaymentReleaseRequest,
    AffiliateLinkCreate,
    AffiliateLinkUpdate,
    AffiliateLinkResponse,
    AffiliateEventResponse,
    AffiliateStats,
    ConversionWebhookPayload,
    CreatorValuationResponse,
    ValuationFactors,
    ValuationRefreshRequest,
    ContractTemplateCreate,
    ContractTemplateUpdate,
    ContractTemplateResponse,
    GeneratedContractResponse,
    CampaignDashboardStats,
    CreatorCampaignStats,
)

router = APIRouter()


def parse_jsonb(value):
    """Parse JSONB value from database."""
    if value is None:
        return [] if isinstance(value, list) else {}
    if isinstance(value, str):
        return json.loads(value)
    return value


def generate_short_code(length: int = 8) -> str:
    """Generate a random short code for affiliate links."""
    chars = string.ascii_letters + string.digits
    return ''.join(secrets.choice(chars) for _ in range(length))


# =============================================================================
# Campaign CRUD Endpoints (Agency)
# =============================================================================

@router.post("/agency/campaigns", response_model=CampaignResponse)
async def create_campaign(
    campaign: CampaignCreate,
    membership: dict = Depends(require_agency_admin),
):
    """Create a new campaign. Requires agency admin/owner role."""
    # Validate percentages sum to 100
    if campaign.upfront_percent + campaign.completion_percent != 100:
        raise HTTPException(
            status_code=400,
            detail="Upfront and completion percentages must sum to 100"
        )

    async with get_connection() as conn:
        # Serialize complex types
        deliverables_json = json.dumps([d.model_dump() for d in campaign.deliverables])
        timeline_json = json.dumps(campaign.timeline.model_dump() if campaign.timeline else {})

        row = await conn.fetchrow(
            """INSERT INTO campaigns
               (agency_id, brand_name, title, description, deliverables, timeline,
                total_budget, upfront_percent, completion_percent, platform_fee_percent,
                max_creators, contract_template_id, expires_at)
               VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9, $10, $11, $12, $13)
               RETURNING *""",
            membership["agency_id"],
            campaign.brand_name,
            campaign.title,
            campaign.description,
            deliverables_json,
            timeline_json,
            campaign.total_budget,
            campaign.upfront_percent,
            campaign.completion_percent,
            campaign.platform_fee_percent,
            campaign.max_creators,
            campaign.contract_template_id,
            campaign.expires_at,
        )

        return CampaignResponse(
            id=row["id"],
            agency_id=row["agency_id"],
            agency_name=membership["agency_name"],
            brand_name=row["brand_name"],
            title=row["title"],
            description=row["description"],
            deliverables=parse_jsonb(row["deliverables"]),
            timeline=parse_jsonb(row["timeline"]),
            total_budget=row["total_budget"],
            upfront_percent=row["upfront_percent"],
            completion_percent=row["completion_percent"],
            platform_fee_percent=row["platform_fee_percent"],
            max_creators=row["max_creators"],
            accepted_count=row["accepted_count"],
            status=row["status"],
            contract_template_id=row["contract_template_id"],
            expires_at=row["expires_at"],
            created_at=row["created_at"],
            updated_at=row["updated_at"],
        )


@router.get("/agency/campaigns", response_model=list[CampaignResponse])
async def list_agency_campaigns(
    status: Optional[str] = None,
    membership: dict = Depends(require_agency_membership),
):
    """List all campaigns for the current agency."""
    async with get_connection() as conn:
        query = "SELECT * FROM campaigns WHERE agency_id = $1"
        params = [membership["agency_id"]]

        if status:
            query += " AND status = $2"
            params.append(status)

        query += " ORDER BY created_at DESC"

        rows = await conn.fetch(query, *params)

        return [
            CampaignResponse(
                id=row["id"],
                agency_id=row["agency_id"],
                agency_name=membership["agency_name"],
                brand_name=row["brand_name"],
                title=row["title"],
                description=row["description"],
                deliverables=parse_jsonb(row["deliverables"]),
                timeline=parse_jsonb(row["timeline"]),
                total_budget=row["total_budget"],
                upfront_percent=row["upfront_percent"],
                completion_percent=row["completion_percent"],
                platform_fee_percent=row["platform_fee_percent"],
                max_creators=row["max_creators"],
                accepted_count=row["accepted_count"],
                status=row["status"],
                contract_template_id=row["contract_template_id"],
                expires_at=row["expires_at"],
                created_at=row["created_at"],
                updated_at=row["updated_at"],
            )
            for row in rows
        ]


@router.get("/agency/campaigns/{campaign_id}", response_model=CampaignWithOffersResponse)
async def get_campaign_with_offers(
    campaign_id: UUID,
    membership: dict = Depends(require_agency_membership),
):
    """Get a campaign with its offers."""
    async with get_connection() as conn:
        campaign = await conn.fetchrow(
            "SELECT * FROM campaigns WHERE id = $1 AND agency_id = $2",
            campaign_id,
            membership["agency_id"],
        )

        if not campaign:
            raise HTTPException(status_code=404, detail="Campaign not found")

        # Get offers for this campaign
        offers = await conn.fetch(
            """SELECT co.*, c.display_name as creator_name, c.profile_image_url
               FROM campaign_offers co
               JOIN creators c ON co.creator_id = c.id
               WHERE co.campaign_id = $1
               ORDER BY co.created_at DESC""",
            campaign_id,
        )

        offer_responses = [
            CampaignOfferResponse(
                id=o["id"],
                campaign_id=o["campaign_id"],
                campaign_title=campaign["title"],
                brand_name=campaign["brand_name"],
                creator_id=o["creator_id"],
                creator_name=o["creator_name"],
                creator_profile_image=o["profile_image_url"],
                offered_amount=o["offered_amount"],
                custom_message=o["custom_message"],
                status=o["status"],
                creator_counter_amount=o["creator_counter_amount"],
                creator_notes=o["creator_notes"],
                viewed_at=o["viewed_at"],
                responded_at=o["responded_at"],
                created_at=o["created_at"],
            )
            for o in offers
        ]

        pending_count = len([o for o in offers if o["status"] == "pending"])
        viewed_count = len([o for o in offers if o["status"] == "viewed"])

        return CampaignWithOffersResponse(
            id=campaign["id"],
            agency_id=campaign["agency_id"],
            agency_name=membership["agency_name"],
            brand_name=campaign["brand_name"],
            title=campaign["title"],
            description=campaign["description"],
            deliverables=parse_jsonb(campaign["deliverables"]),
            timeline=parse_jsonb(campaign["timeline"]),
            total_budget=campaign["total_budget"],
            upfront_percent=campaign["upfront_percent"],
            completion_percent=campaign["completion_percent"],
            platform_fee_percent=campaign["platform_fee_percent"],
            max_creators=campaign["max_creators"],
            accepted_count=campaign["accepted_count"],
            status=campaign["status"],
            contract_template_id=campaign["contract_template_id"],
            expires_at=campaign["expires_at"],
            created_at=campaign["created_at"],
            updated_at=campaign["updated_at"],
            offers=offer_responses,
            pending_offers_count=pending_count,
            viewed_offers_count=viewed_count,
        )


@router.put("/agency/campaigns/{campaign_id}", response_model=CampaignResponse)
async def update_campaign(
    campaign_id: UUID,
    update: CampaignUpdate,
    membership: dict = Depends(require_agency_admin),
):
    """Update a campaign. Only draft campaigns can be fully updated."""
    async with get_connection() as conn:
        existing = await conn.fetchrow(
            "SELECT * FROM campaigns WHERE id = $1 AND agency_id = $2",
            campaign_id,
            membership["agency_id"],
        )

        if not existing:
            raise HTTPException(status_code=404, detail="Campaign not found")

        if existing["status"] != "draft":
            raise HTTPException(
                status_code=400,
                detail="Can only update draft campaigns"
            )

        update_data = update.model_dump(exclude_unset=True)
        if not update_data:
            raise HTTPException(status_code=400, detail="No fields to update")

        # Serialize complex types
        if "deliverables" in update_data and update_data["deliverables"]:
            update_data["deliverables"] = json.dumps([d.model_dump() for d in update_data["deliverables"]])
        if "timeline" in update_data and update_data["timeline"]:
            update_data["timeline"] = json.dumps(update_data["timeline"].model_dump())

        set_clauses = [f"{k} = ${i+1}" for i, k in enumerate(update_data.keys())]
        set_clauses.append("updated_at = NOW()")

        row = await conn.fetchrow(
            f"""UPDATE campaigns
                SET {", ".join(set_clauses)}
                WHERE id = ${len(update_data) + 1}
                RETURNING *""",
            *update_data.values(),
            campaign_id,
        )

        return CampaignResponse(
            id=row["id"],
            agency_id=row["agency_id"],
            agency_name=membership["agency_name"],
            brand_name=row["brand_name"],
            title=row["title"],
            description=row["description"],
            deliverables=parse_jsonb(row["deliverables"]),
            timeline=parse_jsonb(row["timeline"]),
            total_budget=row["total_budget"],
            upfront_percent=row["upfront_percent"],
            completion_percent=row["completion_percent"],
            platform_fee_percent=row["platform_fee_percent"],
            max_creators=row["max_creators"],
            accepted_count=row["accepted_count"],
            status=row["status"],
            contract_template_id=row["contract_template_id"],
            expires_at=row["expires_at"],
            created_at=row["created_at"],
            updated_at=row["updated_at"],
        )


@router.post("/agency/campaigns/{campaign_id}/publish")
async def publish_campaign(
    campaign_id: UUID,
    membership: dict = Depends(require_agency_admin),
):
    """Publish a campaign, making offers visible to creators."""
    async with get_connection() as conn:
        campaign = await conn.fetchrow(
            "SELECT * FROM campaigns WHERE id = $1 AND agency_id = $2",
            campaign_id,
            membership["agency_id"],
        )

        if not campaign:
            raise HTTPException(status_code=404, detail="Campaign not found")

        if campaign["status"] != "draft":
            raise HTTPException(status_code=400, detail="Campaign is not in draft status")

        # Check if there are any offers
        offer_count = await conn.fetchval(
            "SELECT COUNT(*) FROM campaign_offers WHERE campaign_id = $1",
            campaign_id,
        )

        if offer_count == 0:
            raise HTTPException(
                status_code=400,
                detail="Cannot publish campaign without any offers"
            )

        await conn.execute(
            "UPDATE campaigns SET status = 'open', updated_at = NOW() WHERE id = $1",
            campaign_id,
        )

        return {"status": "published", "offers_sent": offer_count}


@router.post("/agency/campaigns/{campaign_id}/cancel")
async def cancel_campaign(
    campaign_id: UUID,
    membership: dict = Depends(require_agency_admin),
):
    """Cancel a campaign and all pending offers."""
    async with get_connection() as conn:
        campaign = await conn.fetchrow(
            "SELECT * FROM campaigns WHERE id = $1 AND agency_id = $2",
            campaign_id,
            membership["agency_id"],
        )

        if not campaign:
            raise HTTPException(status_code=404, detail="Campaign not found")

        if campaign["status"] in ["completed", "cancelled"]:
            raise HTTPException(status_code=400, detail="Campaign already finished")

        # Update campaign status
        await conn.execute(
            "UPDATE campaigns SET status = 'cancelled', updated_at = NOW() WHERE id = $1",
            campaign_id,
        )

        # Mark pending offers as expired
        await conn.execute(
            """UPDATE campaign_offers
               SET status = 'expired', responded_at = NOW()
               WHERE campaign_id = $1 AND status IN ('pending', 'viewed')""",
            campaign_id,
        )

        return {"status": "cancelled"}


@router.delete("/agency/campaigns/{campaign_id}")
async def delete_campaign(
    campaign_id: UUID,
    membership: dict = Depends(require_agency_admin),
):
    """Delete a draft campaign."""
    async with get_connection() as conn:
        campaign = await conn.fetchrow(
            "SELECT status FROM campaigns WHERE id = $1 AND agency_id = $2",
            campaign_id,
            membership["agency_id"],
        )

        if not campaign:
            raise HTTPException(status_code=404, detail="Campaign not found")

        if campaign["status"] != "draft":
            raise HTTPException(status_code=400, detail="Can only delete draft campaigns")

        await conn.execute("DELETE FROM campaigns WHERE id = $1", campaign_id)

        return {"status": "deleted"}


# =============================================================================
# Campaign Offer Endpoints (Agency side)
# =============================================================================

@router.post("/agency/campaigns/{campaign_id}/offers", response_model=CampaignOfferResponse)
async def add_offer_to_campaign(
    campaign_id: UUID,
    offer: CampaignOfferCreate,
    membership: dict = Depends(require_agency_admin),
):
    """Add an offer to a creator for a campaign."""
    async with get_connection() as conn:
        campaign = await conn.fetchrow(
            "SELECT * FROM campaigns WHERE id = $1 AND agency_id = $2",
            campaign_id,
            membership["agency_id"],
        )

        if not campaign:
            raise HTTPException(status_code=404, detail="Campaign not found")

        if campaign["status"] not in ["draft", "open"]:
            raise HTTPException(
                status_code=400,
                detail="Cannot add offers to campaigns that are not draft or open"
            )

        # Check if creator exists
        creator = await conn.fetchrow(
            "SELECT id, display_name, profile_image_url FROM creators WHERE id = $1",
            offer.creator_id,
        )

        if not creator:
            raise HTTPException(status_code=404, detail="Creator not found")

        # Check if offer already exists
        existing = await conn.fetchrow(
            "SELECT id FROM campaign_offers WHERE campaign_id = $1 AND creator_id = $2",
            campaign_id,
            offer.creator_id,
        )

        if existing:
            raise HTTPException(
                status_code=400,
                detail="Offer already exists for this creator"
            )

        # Check max creators limit
        current_offers = await conn.fetchval(
            "SELECT COUNT(*) FROM campaign_offers WHERE campaign_id = $1",
            campaign_id,
        )

        if current_offers >= campaign["max_creators"]:
            raise HTTPException(
                status_code=400,
                detail=f"Campaign already has {campaign['max_creators']} offers (max)"
            )

        row = await conn.fetchrow(
            """INSERT INTO campaign_offers
               (campaign_id, creator_id, offered_amount, custom_message)
               VALUES ($1, $2, $3, $4)
               RETURNING *""",
            campaign_id,
            offer.creator_id,
            offer.offered_amount,
            offer.custom_message,
        )

        return CampaignOfferResponse(
            id=row["id"],
            campaign_id=row["campaign_id"],
            campaign_title=campaign["title"],
            brand_name=campaign["brand_name"],
            creator_id=row["creator_id"],
            creator_name=creator["display_name"],
            creator_profile_image=creator["profile_image_url"],
            offered_amount=row["offered_amount"],
            custom_message=row["custom_message"],
            status=row["status"],
            creator_counter_amount=row["creator_counter_amount"],
            creator_notes=row["creator_notes"],
            viewed_at=row["viewed_at"],
            responded_at=row["responded_at"],
            created_at=row["created_at"],
        )


@router.post("/agency/campaigns/{campaign_id}/offers/bulk", response_model=list[CampaignOfferResponse])
async def add_bulk_offers(
    campaign_id: UUID,
    bulk: CampaignOfferBulkCreate,
    membership: dict = Depends(require_agency_admin),
):
    """Add multiple offers to a campaign at once."""
    results = []
    for offer in bulk.offers:
        try:
            result = await add_offer_to_campaign(campaign_id, offer, membership)
            results.append(result)
        except HTTPException:
            continue  # Skip failed offers
    return results


@router.delete("/agency/campaigns/{campaign_id}/offers/{creator_id}")
async def remove_offer_from_campaign(
    campaign_id: UUID,
    creator_id: UUID,
    membership: dict = Depends(require_agency_admin),
):
    """Remove an offer from a campaign (only pending offers)."""
    async with get_connection() as conn:
        campaign = await conn.fetchrow(
            "SELECT * FROM campaigns WHERE id = $1 AND agency_id = $2",
            campaign_id,
            membership["agency_id"],
        )

        if not campaign:
            raise HTTPException(status_code=404, detail="Campaign not found")

        offer = await conn.fetchrow(
            "SELECT * FROM campaign_offers WHERE campaign_id = $1 AND creator_id = $2",
            campaign_id,
            creator_id,
        )

        if not offer:
            raise HTTPException(status_code=404, detail="Offer not found")

        if offer["status"] not in ["pending", "viewed"]:
            raise HTTPException(
                status_code=400,
                detail="Can only remove pending or viewed offers"
            )

        await conn.execute(
            "DELETE FROM campaign_offers WHERE campaign_id = $1 AND creator_id = $2",
            campaign_id,
            creator_id,
        )

        return {"status": "removed"}


# =============================================================================
# Creator Offer Endpoints
# =============================================================================

@router.get("/creators/me/offers", response_model=list[CreatorOfferResponse])
async def list_my_offers(
    status: Optional[str] = None,
    creator: dict = Depends(require_creator_record),
):
    """List all campaign offers for the current creator."""
    async with get_connection() as conn:
        query = """
            SELECT co.*, c.title as campaign_title, c.brand_name, c.description,
                   c.deliverables, c.timeline, c.expires_at,
                   a.name as agency_name, a.is_verified as agency_verified,
                   cv.estimated_value_min, cv.estimated_value_max
            FROM campaign_offers co
            JOIN campaigns c ON co.campaign_id = c.id
            JOIN agencies a ON c.agency_id = a.id
            LEFT JOIN creator_valuations cv ON cv.creator_id = co.creator_id
            WHERE co.creator_id = $1 AND c.status = 'open'
        """
        params = [creator["id"]]

        if status:
            query += " AND co.status = $2"
            params.append(status)

        query += " ORDER BY co.created_at DESC"

        rows = await conn.fetch(query, *params)

        results = []
        for row in rows:
            # Calculate offer vs value ratio
            ratio = None
            if row["estimated_value_min"] and row["estimated_value_max"]:
                mid_value = (row["estimated_value_min"] + row["estimated_value_max"]) / 2
                if mid_value > 0:
                    ratio = float(row["offered_amount"] / mid_value)

            results.append(CreatorOfferResponse(
                id=row["id"],
                campaign_id=row["campaign_id"],
                campaign_title=row["campaign_title"],
                brand_name=row["brand_name"],
                agency_name=row["agency_name"],
                agency_verified=row["agency_verified"],
                description=row["description"],
                deliverables=parse_jsonb(row["deliverables"]),
                timeline=parse_jsonb(row["timeline"]),
                offered_amount=row["offered_amount"],
                custom_message=row["custom_message"],
                status=row["status"],
                creator_counter_amount=row["creator_counter_amount"],
                creator_notes=row["creator_notes"],
                estimated_value_min=row["estimated_value_min"],
                estimated_value_max=row["estimated_value_max"],
                offer_vs_value_ratio=ratio,
                viewed_at=row["viewed_at"],
                responded_at=row["responded_at"],
                created_at=row["created_at"],
                expires_at=row["expires_at"],
            ))

        return results


@router.get("/creators/me/offers/{offer_id}", response_model=CreatorOfferResponse)
async def get_my_offer(
    offer_id: UUID,
    creator: dict = Depends(require_creator_record),
):
    """Get a specific offer and mark it as viewed."""
    async with get_connection() as conn:
        row = await conn.fetchrow(
            """SELECT co.*, c.title as campaign_title, c.brand_name, c.description,
                      c.deliverables, c.timeline, c.expires_at,
                      a.name as agency_name, a.is_verified as agency_verified,
                      cv.estimated_value_min, cv.estimated_value_max
               FROM campaign_offers co
               JOIN campaigns c ON co.campaign_id = c.id
               JOIN agencies a ON c.agency_id = a.id
               LEFT JOIN creator_valuations cv ON cv.creator_id = co.creator_id
               WHERE co.id = $1 AND co.creator_id = $2""",
            offer_id,
            creator["id"],
        )

        if not row:
            raise HTTPException(status_code=404, detail="Offer not found")

        # Mark as viewed if pending
        if row["status"] == "pending":
            await conn.execute(
                "UPDATE campaign_offers SET status = 'viewed', viewed_at = NOW() WHERE id = $1",
                offer_id,
            )

        ratio = None
        if row["estimated_value_min"] and row["estimated_value_max"]:
            mid_value = (row["estimated_value_min"] + row["estimated_value_max"]) / 2
            if mid_value > 0:
                ratio = float(row["offered_amount"] / mid_value)

        return CreatorOfferResponse(
            id=row["id"],
            campaign_id=row["campaign_id"],
            campaign_title=row["campaign_title"],
            brand_name=row["brand_name"],
            agency_name=row["agency_name"],
            agency_verified=row["agency_verified"],
            description=row["description"],
            deliverables=parse_jsonb(row["deliverables"]),
            timeline=parse_jsonb(row["timeline"]),
            offered_amount=row["offered_amount"],
            custom_message=row["custom_message"],
            status="viewed" if row["status"] == "pending" else row["status"],
            creator_counter_amount=row["creator_counter_amount"],
            creator_notes=row["creator_notes"],
            estimated_value_min=row["estimated_value_min"],
            estimated_value_max=row["estimated_value_max"],
            offer_vs_value_ratio=ratio,
            viewed_at=row["viewed_at"] or datetime.now(),
            responded_at=row["responded_at"],
            created_at=row["created_at"],
            expires_at=row["expires_at"],
        )


@router.post("/creators/me/offers/{offer_id}/accept")
async def accept_offer(
    offer_id: UUID,
    request: OfferAcceptRequest,
    creator: dict = Depends(require_creator_record),
):
    """Accept a campaign offer (triggers escrow)."""
    async with get_connection() as conn:
        # Get offer and campaign
        offer = await conn.fetchrow(
            """SELECT co.*, c.id as campaign_id, c.agency_id, c.status as campaign_status,
                      c.max_creators, c.accepted_count, c.total_budget, c.upfront_percent,
                      c.platform_fee_percent
               FROM campaign_offers co
               JOIN campaigns c ON co.campaign_id = c.id
               WHERE co.id = $1 AND co.creator_id = $2""",
            offer_id,
            creator["id"],
        )

        if not offer:
            raise HTTPException(status_code=404, detail="Offer not found")

        if offer["status"] not in ["pending", "viewed"]:
            raise HTTPException(status_code=400, detail=f"Cannot accept offer with status: {offer['status']}")

        if offer["campaign_status"] != "open":
            raise HTTPException(status_code=400, detail="Campaign is no longer open")

        # Check if campaign is full
        if offer["accepted_count"] >= offer["max_creators"]:
            # Mark this offer as taken
            await conn.execute(
                "UPDATE campaign_offers SET status = 'taken', responded_at = NOW() WHERE id = $1",
                offer_id,
            )
            raise HTTPException(status_code=400, detail="Campaign slots are full")

        # Start transaction
        async with conn.transaction():
            # Accept the offer
            await conn.execute(
                """UPDATE campaign_offers
                   SET status = 'accepted', creator_notes = $2, responded_at = NOW()
                   WHERE id = $1""",
                offer_id,
                request.notes,
            )

            # Update campaign accepted count
            new_count = await conn.fetchval(
                """UPDATE campaigns
                   SET accepted_count = accepted_count + 1, updated_at = NOW()
                   WHERE id = $1
                   RETURNING accepted_count""",
                offer["campaign_id"],
            )

            # If campaign is full, mark other pending offers as 'taken'
            if new_count >= offer["max_creators"]:
                await conn.execute(
                    """UPDATE campaign_offers
                       SET status = 'taken', responded_at = NOW()
                       WHERE campaign_id = $1 AND status IN ('pending', 'viewed')""",
                    offer["campaign_id"],
                )

                # Set campaign to active
                await conn.execute(
                    "UPDATE campaigns SET status = 'active', updated_at = NOW() WHERE id = $1",
                    offer["campaign_id"],
                )

            # Calculate upfront payment
            upfront_amount = offer["offered_amount"] * Decimal(offer["upfront_percent"]) / Decimal("100")
            platform_fee = upfront_amount * offer["platform_fee_percent"] / Decimal("100")

            # Create payment record (escrow)
            await conn.execute(
                """INSERT INTO campaign_payments
                   (campaign_id, creator_id, payment_type, amount, platform_fee, status)
                   VALUES ($1, $2, 'upfront', $3, $4, 'pending')""",
                offer["campaign_id"],
                creator["id"],
                upfront_amount,
                platform_fee,
            )

        return {
            "status": "accepted",
            "upfront_amount": float(upfront_amount),
            "message": "Offer accepted. Payment will be processed."
        }


@router.post("/creators/me/offers/{offer_id}/decline")
async def decline_offer(
    offer_id: UUID,
    request: OfferDeclineRequest,
    creator: dict = Depends(require_creator_record),
):
    """Decline a campaign offer."""
    async with get_connection() as conn:
        offer = await conn.fetchrow(
            "SELECT * FROM campaign_offers WHERE id = $1 AND creator_id = $2",
            offer_id,
            creator["id"],
        )

        if not offer:
            raise HTTPException(status_code=404, detail="Offer not found")

        if offer["status"] not in ["pending", "viewed"]:
            raise HTTPException(status_code=400, detail=f"Cannot decline offer with status: {offer['status']}")

        await conn.execute(
            """UPDATE campaign_offers
               SET status = 'declined', creator_notes = $2, responded_at = NOW()
               WHERE id = $1""",
            offer_id,
            request.reason,
        )

        return {"status": "declined"}


@router.post("/creators/me/offers/{offer_id}/counter")
async def counter_offer(
    offer_id: UUID,
    request: OfferCounterRequest,
    creator: dict = Depends(require_creator_record),
):
    """Submit a counter-offer for a campaign."""
    async with get_connection() as conn:
        offer = await conn.fetchrow(
            "SELECT * FROM campaign_offers WHERE id = $1 AND creator_id = $2",
            offer_id,
            creator["id"],
        )

        if not offer:
            raise HTTPException(status_code=404, detail="Offer not found")

        if offer["status"] not in ["pending", "viewed"]:
            raise HTTPException(status_code=400, detail=f"Cannot counter offer with status: {offer['status']}")

        await conn.execute(
            """UPDATE campaign_offers
               SET creator_counter_amount = $2, creator_notes = $3, responded_at = NOW()
               WHERE id = $1""",
            offer_id,
            request.counter_amount,
            request.notes,
        )

        return {
            "status": "counter_submitted",
            "counter_amount": float(request.counter_amount)
        }


# =============================================================================
# Payment/Escrow Endpoints
# =============================================================================

@router.get("/agency/campaigns/{campaign_id}/payments", response_model=list[CampaignPaymentResponse])
async def list_campaign_payments(
    campaign_id: UUID,
    membership: dict = Depends(require_agency_membership),
):
    """List all payments for a campaign."""
    async with get_connection() as conn:
        campaign = await conn.fetchrow(
            "SELECT * FROM campaigns WHERE id = $1 AND agency_id = $2",
            campaign_id,
            membership["agency_id"],
        )

        if not campaign:
            raise HTTPException(status_code=404, detail="Campaign not found")

        rows = await conn.fetch(
            """SELECT cp.*, c.display_name as creator_name
               FROM campaign_payments cp
               JOIN creators c ON cp.creator_id = c.id
               WHERE cp.campaign_id = $1
               ORDER BY cp.created_at DESC""",
            campaign_id,
        )

        return [
            CampaignPaymentResponse(
                id=row["id"],
                campaign_id=row["campaign_id"],
                creator_id=row["creator_id"],
                creator_name=row["creator_name"],
                payment_type=row["payment_type"],
                amount=row["amount"],
                platform_fee=row["platform_fee"],
                status=row["status"],
                stripe_payment_intent_id=row["stripe_payment_intent_id"],
                stripe_transfer_id=row["stripe_transfer_id"],
                charged_at=row["charged_at"],
                released_at=row["released_at"],
                created_at=row["created_at"],
            )
            for row in rows
        ]


@router.post("/agency/payments/{payment_id}/release")
async def release_payment(
    payment_id: UUID,
    request: PaymentReleaseRequest,
    membership: dict = Depends(require_agency_admin),
):
    """Release a held payment to the creator."""
    async with get_connection() as conn:
        payment = await conn.fetchrow(
            """SELECT cp.*, c.agency_id
               FROM campaign_payments cp
               JOIN campaigns c ON cp.campaign_id = c.id
               WHERE cp.id = $1""",
            payment_id,
        )

        if not payment:
            raise HTTPException(status_code=404, detail="Payment not found")

        if payment["agency_id"] != membership["agency_id"]:
            raise HTTPException(status_code=403, detail="Not authorized")

        if payment["status"] != "held":
            raise HTTPException(status_code=400, detail="Payment is not in held status")

        # In a real implementation, this would trigger a Stripe transfer
        await conn.execute(
            """UPDATE campaign_payments
               SET status = 'released', released_at = NOW()
               WHERE id = $1""",
            payment_id,
        )

        return {"status": "released"}


@router.get("/creators/me/payments", response_model=list[CampaignPaymentResponse])
async def list_my_payments(
    status: Optional[str] = None,
    creator: dict = Depends(require_creator_record),
):
    """List all campaign payments for the current creator."""
    async with get_connection() as conn:
        query = """
            SELECT cp.*, c.display_name as creator_name
            FROM campaign_payments cp
            JOIN creators c ON cp.creator_id = c.id
            WHERE cp.creator_id = $1
        """
        params = [creator["id"]]

        if status:
            query += " AND cp.status = $2"
            params.append(status)

        query += " ORDER BY cp.created_at DESC"

        rows = await conn.fetch(query, *params)

        return [
            CampaignPaymentResponse(
                id=row["id"],
                campaign_id=row["campaign_id"],
                creator_id=row["creator_id"],
                creator_name=row["creator_name"],
                payment_type=row["payment_type"],
                amount=row["amount"],
                platform_fee=row["platform_fee"],
                status=row["status"],
                stripe_payment_intent_id=row["stripe_payment_intent_id"],
                stripe_transfer_id=row["stripe_transfer_id"],
                charged_at=row["charged_at"],
                released_at=row["released_at"],
                created_at=row["created_at"],
            )
            for row in rows
        ]


# =============================================================================
# Affiliate Link Endpoints
# =============================================================================

@router.post("/affiliate/links", response_model=AffiliateLinkResponse)
async def create_affiliate_link(
    link: AffiliateLinkCreate,
    membership: dict = Depends(require_agency_admin),
):
    """Create a new affiliate tracking link."""
    async with get_connection() as conn:
        # Verify creator exists
        creator = await conn.fetchrow(
            "SELECT id, display_name FROM creators WHERE id = $1",
            link.creator_id,
        )

        if not creator:
            raise HTTPException(status_code=404, detail="Creator not found")

        # Generate unique short code
        short_code = generate_short_code()
        while await conn.fetchval("SELECT 1 FROM affiliate_links WHERE short_code = $1", short_code):
            short_code = generate_short_code()

        row = await conn.fetchrow(
            """INSERT INTO affiliate_links
               (campaign_id, creator_id, agency_id, short_code, destination_url,
                product_name, commission_percent, platform_percent)
               VALUES ($1, $2, $3, $4, $5, $6, $7, $8)
               RETURNING *""",
            link.campaign_id,
            link.creator_id,
            membership["agency_id"],
            short_code,
            link.destination_url,
            link.product_name,
            link.commission_percent,
            link.platform_percent,
        )

        return AffiliateLinkResponse(
            id=row["id"],
            campaign_id=row["campaign_id"],
            creator_id=row["creator_id"],
            creator_name=creator["display_name"],
            agency_id=row["agency_id"],
            agency_name=membership["agency_name"],
            short_code=row["short_code"],
            tracking_url=f"/api/r/{row['short_code']}",
            destination_url=row["destination_url"],
            product_name=row["product_name"],
            commission_percent=row["commission_percent"],
            platform_percent=row["platform_percent"],
            click_count=row["click_count"],
            conversion_count=row["conversion_count"],
            total_sales=row["total_sales"],
            total_commission=row["total_commission"],
            is_active=row["is_active"],
            created_at=row["created_at"],
            updated_at=row["updated_at"],
        )


@router.get("/affiliate/links", response_model=list[AffiliateLinkResponse])
async def list_affiliate_links(
    current_user: CurrentUser = Depends(get_current_user),
):
    """List affiliate links (for creator or agency)."""
    async with get_connection() as conn:
        if current_user.role == "creator":
            creator = await conn.fetchrow(
                "SELECT id FROM creators WHERE user_id = $1",
                current_user.id,
            )
            if not creator:
                raise HTTPException(status_code=404, detail="Creator profile not found")

            rows = await conn.fetch(
                """SELECT al.*, c.display_name as creator_name, a.name as agency_name
                   FROM affiliate_links al
                   JOIN creators c ON al.creator_id = c.id
                   JOIN agencies a ON al.agency_id = a.id
                   WHERE al.creator_id = $1
                   ORDER BY al.created_at DESC""",
                creator["id"],
            )

        elif current_user.role == "agency":
            member = await conn.fetchrow(
                "SELECT agency_id FROM agency_members WHERE user_id = $1 AND is_active = true",
                current_user.id,
            )
            if not member:
                raise HTTPException(status_code=404, detail="Agency membership not found")

            rows = await conn.fetch(
                """SELECT al.*, c.display_name as creator_name, a.name as agency_name
                   FROM affiliate_links al
                   JOIN creators c ON al.creator_id = c.id
                   JOIN agencies a ON al.agency_id = a.id
                   WHERE al.agency_id = $1
                   ORDER BY al.created_at DESC""",
                member["agency_id"],
            )
        else:
            raise HTTPException(status_code=403, detail="Not authorized")

        return [
            AffiliateLinkResponse(
                id=row["id"],
                campaign_id=row["campaign_id"],
                creator_id=row["creator_id"],
                creator_name=row["creator_name"],
                agency_id=row["agency_id"],
                agency_name=row["agency_name"],
                short_code=row["short_code"],
                tracking_url=f"/api/r/{row['short_code']}",
                destination_url=row["destination_url"],
                product_name=row["product_name"],
                commission_percent=row["commission_percent"],
                platform_percent=row["platform_percent"],
                click_count=row["click_count"],
                conversion_count=row["conversion_count"],
                total_sales=row["total_sales"],
                total_commission=row["total_commission"],
                is_active=row["is_active"],
                created_at=row["created_at"],
                updated_at=row["updated_at"],
            )
            for row in rows
        ]


@router.get("/affiliate/links/{link_id}/stats", response_model=AffiliateStats)
async def get_affiliate_stats(
    link_id: UUID,
    current_user: CurrentUser = Depends(get_current_user),
):
    """Get statistics for an affiliate link."""
    async with get_connection() as conn:
        link = await conn.fetchrow(
            "SELECT * FROM affiliate_links WHERE id = $1",
            link_id,
        )

        if not link:
            raise HTTPException(status_code=404, detail="Link not found")

        # Verify access
        if current_user.role == "creator":
            creator = await conn.fetchrow(
                "SELECT id FROM creators WHERE user_id = $1",
                current_user.id,
            )
            if not creator or creator["id"] != link["creator_id"]:
                raise HTTPException(status_code=403, detail="Not authorized")
        elif current_user.role == "agency":
            member = await conn.fetchrow(
                "SELECT agency_id FROM agency_members WHERE user_id = $1 AND is_active = true",
                current_user.id,
            )
            if not member or member["agency_id"] != link["agency_id"]:
                raise HTTPException(status_code=403, detail="Not authorized")

        conversion_rate = 0.0
        if link["click_count"] > 0:
            conversion_rate = link["conversion_count"] / link["click_count"]

        return AffiliateStats(
            total_clicks=link["click_count"],
            total_conversions=link["conversion_count"],
            conversion_rate=conversion_rate,
            total_sales=link["total_sales"],
            total_commission=link["total_commission"],
            pending_commission=Decimal("0"),  # Would need payment tracking
        )


# =============================================================================
# Affiliate Redirect & Webhook Endpoints (Public)
# =============================================================================

@router.get("/r/{short_code}")
async def affiliate_redirect(
    short_code: str,
    request: Request,
):
    """Public redirect endpoint for affiliate links."""
    async with get_connection() as conn:
        link = await conn.fetchrow(
            "SELECT * FROM affiliate_links WHERE short_code = $1 AND is_active = true",
            short_code,
        )

        if not link:
            raise HTTPException(status_code=404, detail="Link not found")

        # Record click event
        await conn.execute(
            """INSERT INTO affiliate_events
               (link_id, event_type, ip_address, user_agent, referrer)
               VALUES ($1, 'click', $2, $3, $4)""",
            link["id"],
            request.client.host if request.client else None,
            request.headers.get("user-agent"),
            request.headers.get("referer"),
        )

        # Increment click count
        await conn.execute(
            "UPDATE affiliate_links SET click_count = click_count + 1 WHERE id = $1",
            link["id"],
        )

        return RedirectResponse(url=link["destination_url"], status_code=302)


@router.post("/affiliate/webhook")
async def record_conversion(
    payload: ConversionWebhookPayload,
):
    """Webhook endpoint to record affiliate conversions."""
    async with get_connection() as conn:
        link = await conn.fetchrow(
            "SELECT * FROM affiliate_links WHERE short_code = $1 AND is_active = true",
            payload.short_code,
        )

        if not link:
            raise HTTPException(status_code=404, detail="Link not found")

        # Calculate commission
        commission = payload.sale_amount * link["commission_percent"] / Decimal("100")

        # Record conversion event
        await conn.execute(
            """INSERT INTO affiliate_events
               (link_id, event_type, sale_amount, commission_amount, metadata)
               VALUES ($1, 'conversion', $2, $3, $4)""",
            link["id"],
            payload.sale_amount,
            commission,
            json.dumps(payload.metadata) if payload.metadata else "{}",
        )

        # Update link stats
        await conn.execute(
            """UPDATE affiliate_links
               SET conversion_count = conversion_count + 1,
                   total_sales = total_sales + $2,
                   total_commission = total_commission + $3
               WHERE id = $1""",
            link["id"],
            payload.sale_amount,
            commission,
        )

        return {"status": "recorded", "commission": float(commission)}


# =============================================================================
# Creator Valuation Endpoints
# =============================================================================

@router.get("/creators/{creator_id}/valuation", response_model=CreatorValuationResponse)
async def get_creator_valuation(
    creator_id: UUID,
    current_user: CurrentUser = Depends(get_current_user),
):
    """Get a creator's estimated value."""
    async with get_connection() as conn:
        creator = await conn.fetchrow(
            "SELECT id, display_name FROM creators WHERE id = $1",
            creator_id,
        )

        if not creator:
            raise HTTPException(status_code=404, detail="Creator not found")

        valuation = await conn.fetchrow(
            "SELECT * FROM creator_valuations WHERE creator_id = $1",
            creator_id,
        )

        if not valuation:
            # Calculate on the fly if not cached
            valuation = await calculate_creator_valuation(conn, creator_id)

        factors = parse_jsonb(valuation["factors"])
        data_sources = parse_jsonb(valuation["data_sources"])

        mid_value = (valuation["estimated_value_min"] + valuation["estimated_value_max"]) / 2

        return CreatorValuationResponse(
            id=valuation["id"],
            creator_id=valuation["creator_id"],
            creator_name=creator["display_name"],
            estimated_value_min=valuation["estimated_value_min"],
            estimated_value_max=valuation["estimated_value_max"],
            estimated_value_mid=mid_value,
            factors=ValuationFactors(**factors) if factors else ValuationFactors(),
            data_sources=data_sources if isinstance(data_sources, list) else [],
            confidence_score=valuation["confidence_score"],
            calculated_at=valuation["calculated_at"],
        )


@router.post("/creators/me/valuation/refresh", response_model=CreatorValuationResponse)
async def refresh_my_valuation(
    request: ValuationRefreshRequest,
    creator: dict = Depends(require_creator_record),
):
    """Recalculate the current creator's valuation."""
    async with get_connection() as conn:
        valuation = await calculate_creator_valuation(
            conn,
            creator["id"],
            include_platform_data=request.include_platform_data,
            manual_overrides=request.manual_overrides,
        )

        factors = parse_jsonb(valuation["factors"])
        data_sources = parse_jsonb(valuation["data_sources"])

        mid_value = (valuation["estimated_value_min"] + valuation["estimated_value_max"]) / 2

        return CreatorValuationResponse(
            id=valuation["id"],
            creator_id=valuation["creator_id"],
            creator_name=creator["display_name"],
            estimated_value_min=valuation["estimated_value_min"],
            estimated_value_max=valuation["estimated_value_max"],
            estimated_value_mid=mid_value,
            factors=ValuationFactors(**factors) if factors else ValuationFactors(),
            data_sources=data_sources if isinstance(data_sources, list) else [],
            confidence_score=valuation["confidence_score"],
            calculated_at=valuation["calculated_at"],
        )


async def calculate_creator_valuation(
    conn,
    creator_id: UUID,
    include_platform_data: bool = True,
    manual_overrides: Optional[ValuationFactors] = None,
) -> dict:
    """Calculate and cache creator valuation."""
    # Get creator profile
    creator = await conn.fetchrow(
        "SELECT * FROM creators WHERE id = $1",
        creator_id,
    )

    if not creator:
        raise HTTPException(status_code=404, detail="Creator not found")

    metrics = parse_jsonb(creator["metrics"])
    social_handles = parse_jsonb(creator["social_handles"])
    niches = parse_jsonb(creator["niches"])

    # Base calculation factors
    factors = {
        "follower_count": metrics.get("total_followers", 0),
        "engagement_rate": metrics.get("engagement_rate", 0.02),
        "niche_multiplier": 1.0,
        "platform_rates": {},
    }

    data_sources = ["profile_metrics"]

    # Niche multipliers (some niches command higher rates)
    niche_multipliers = {
        "finance": 1.5,
        "technology": 1.3,
        "business": 1.3,
        "beauty": 1.2,
        "fashion": 1.2,
        "lifestyle": 1.0,
        "gaming": 0.9,
        "entertainment": 0.9,
    }

    if niches:
        max_mult = max(niche_multipliers.get(n.lower(), 1.0) for n in niches)
        factors["niche_multiplier"] = max_mult

    # Platform-specific rates (per 1000 followers)
    platform_cpm = {
        "instagram": 10,
        "tiktok": 8,
        "youtube": 20,
        "twitter": 5,
        "twitch": 15,
    }

    for platform, handle in social_handles.items():
        if handle and platform in platform_cpm:
            factors["platform_rates"][platform] = platform_cpm[platform]

    # Apply manual overrides if provided
    if manual_overrides:
        overrides = manual_overrides.model_dump(exclude_unset=True)
        for k, v in overrides.items():
            if v is not None:
                factors[k] = v
                data_sources.append("manual_override")

    # Calculate estimated value
    follower_count = factors.get("follower_count", 0)
    engagement_rate = factors.get("engagement_rate", 0.02)
    niche_mult = factors.get("niche_multiplier", 1.0)

    # Base CPM calculation
    base_cpm = sum(factors["platform_rates"].values()) / max(len(factors["platform_rates"]), 1)
    if base_cpm == 0:
        base_cpm = 10  # Default

    # Estimated value = followers * CPM/1000 * engagement multiplier * niche multiplier
    engagement_mult = 1 + (engagement_rate * 10)  # Higher engagement = higher value
    base_value = (follower_count / 1000) * base_cpm * engagement_mult * niche_mult

    # Range: 80% to 120% of base value
    value_min = Decimal(str(base_value * 0.8)).quantize(Decimal("0.01"))
    value_max = Decimal(str(base_value * 1.2)).quantize(Decimal("0.01"))

    # Confidence based on data quality
    confidence = 0.5
    if follower_count > 0:
        confidence += 0.2
    if engagement_rate > 0:
        confidence += 0.2
    if len(factors["platform_rates"]) > 0:
        confidence += 0.1

    # Upsert valuation
    row = await conn.fetchrow(
        """INSERT INTO creator_valuations
           (creator_id, estimated_value_min, estimated_value_max, factors, data_sources, confidence_score, calculated_at)
           VALUES ($1, $2, $3, $4, $5, $6, NOW())
           ON CONFLICT (creator_id)
           DO UPDATE SET
               estimated_value_min = EXCLUDED.estimated_value_min,
               estimated_value_max = EXCLUDED.estimated_value_max,
               factors = EXCLUDED.factors,
               data_sources = EXCLUDED.data_sources,
               confidence_score = EXCLUDED.confidence_score,
               calculated_at = NOW()
           RETURNING *""",
        creator_id,
        value_min,
        value_max,
        json.dumps(factors),
        json.dumps(list(set(data_sources))),
        confidence,
    )

    return dict(row)


# =============================================================================
# Contract Template Endpoints
# =============================================================================

@router.get("/contracts/templates", response_model=list[ContractTemplateResponse])
async def list_contract_templates(
    current_user: CurrentUser = Depends(get_current_user),
):
    """List available contract templates (default + agency-specific)."""
    async with get_connection() as conn:
        agency_id = None

        if current_user.role == "agency":
            member = await conn.fetchrow(
                "SELECT agency_id FROM agency_members WHERE user_id = $1 AND is_active = true",
                current_user.id,
            )
            if member:
                agency_id = member["agency_id"]

        # Get default templates and agency-specific templates
        if agency_id:
            rows = await conn.fetch(
                """SELECT * FROM contract_templates
                   WHERE agency_id IS NULL OR agency_id = $1
                   ORDER BY is_default DESC, created_at DESC""",
                agency_id,
            )
        else:
            rows = await conn.fetch(
                """SELECT * FROM contract_templates
                   WHERE agency_id IS NULL
                   ORDER BY is_default DESC, created_at DESC"""
            )

        return [
            ContractTemplateResponse(
                id=row["id"],
                agency_id=row["agency_id"],
                name=row["name"],
                template_type=row["template_type"],
                content=row["content"],
                variables=parse_jsonb(row["variables"]),
                is_default=row["is_default"],
                created_at=row["created_at"],
                updated_at=row["updated_at"],
            )
            for row in rows
        ]


@router.post("/contracts/templates", response_model=ContractTemplateResponse)
async def create_contract_template(
    template: ContractTemplateCreate,
    membership: dict = Depends(require_agency_admin),
):
    """Create a custom contract template for the agency."""
    async with get_connection() as conn:
        row = await conn.fetchrow(
            """INSERT INTO contract_templates
               (agency_id, name, template_type, content, variables)
               VALUES ($1, $2, $3, $4, $5)
               RETURNING *""",
            membership["agency_id"],
            template.name,
            template.template_type,
            template.content,
            json.dumps(template.variables) if template.variables else "[]",
        )

        return ContractTemplateResponse(
            id=row["id"],
            agency_id=row["agency_id"],
            name=row["name"],
            template_type=row["template_type"],
            content=row["content"],
            variables=parse_jsonb(row["variables"]),
            is_default=row["is_default"],
            created_at=row["created_at"],
            updated_at=row["updated_at"],
        )


@router.put("/contracts/templates/{template_id}", response_model=ContractTemplateResponse)
async def update_contract_template(
    template_id: UUID,
    update: ContractTemplateUpdate,
    membership: dict = Depends(require_agency_admin),
):
    """Update an agency's contract template."""
    async with get_connection() as conn:
        template = await conn.fetchrow(
            "SELECT * FROM contract_templates WHERE id = $1 AND agency_id = $2",
            template_id,
            membership["agency_id"],
        )

        if not template:
            raise HTTPException(status_code=404, detail="Template not found")

        update_data = update.model_dump(exclude_unset=True)
        if not update_data:
            raise HTTPException(status_code=400, detail="No fields to update")

        if "variables" in update_data and update_data["variables"]:
            update_data["variables"] = json.dumps(update_data["variables"])

        set_clauses = [f"{k} = ${i+1}" for i, k in enumerate(update_data.keys())]
        set_clauses.append("updated_at = NOW()")

        row = await conn.fetchrow(
            f"""UPDATE contract_templates
                SET {", ".join(set_clauses)}
                WHERE id = ${len(update_data) + 1}
                RETURNING *""",
            *update_data.values(),
            template_id,
        )

        return ContractTemplateResponse(
            id=row["id"],
            agency_id=row["agency_id"],
            name=row["name"],
            template_type=row["template_type"],
            content=row["content"],
            variables=parse_jsonb(row["variables"]),
            is_default=row["is_default"],
            created_at=row["created_at"],
            updated_at=row["updated_at"],
        )


@router.post("/agency/campaigns/{campaign_id}/contract/generate", response_model=GeneratedContractResponse)
async def generate_contract(
    campaign_id: UUID,
    creator_id: UUID,
    membership: dict = Depends(require_agency_membership),
):
    """Generate a contract from the campaign's template."""
    async with get_connection() as conn:
        campaign = await conn.fetchrow(
            """SELECT c.*, ct.id as template_id, ct.name as template_name, ct.content as template_content
               FROM campaigns c
               LEFT JOIN contract_templates ct ON c.contract_template_id = ct.id
               WHERE c.id = $1 AND c.agency_id = $2""",
            campaign_id,
            membership["agency_id"],
        )

        if not campaign:
            raise HTTPException(status_code=404, detail="Campaign not found")

        if not campaign["template_id"]:
            # Use default template
            template = await conn.fetchrow(
                "SELECT * FROM contract_templates WHERE is_default = true AND template_type = 'sponsorship' LIMIT 1"
            )
            if not template:
                raise HTTPException(status_code=400, detail="No contract template configured")
            template_id = template["id"]
            template_name = template["name"]
            template_content = template["content"]
        else:
            template_id = campaign["template_id"]
            template_name = campaign["template_name"]
            template_content = campaign["template_content"]

        # Get creator info
        creator = await conn.fetchrow(
            "SELECT display_name FROM creators WHERE id = $1",
            creator_id,
        )

        if not creator:
            raise HTTPException(status_code=404, detail="Creator not found")

        # Get offer amount
        offer = await conn.fetchrow(
            "SELECT offered_amount FROM campaign_offers WHERE campaign_id = $1 AND creator_id = $2",
            campaign_id,
            creator_id,
        )

        offer_amount = offer["offered_amount"] if offer else campaign["total_budget"]

        # Build variable values
        timeline = parse_jsonb(campaign["timeline"])
        deliverables = parse_jsonb(campaign["deliverables"])

        upfront_amount = offer_amount * Decimal(campaign["upfront_percent"]) / Decimal("100")
        completion_amount = offer_amount * Decimal(campaign["completion_percent"]) / Decimal("100")

        variables = {
            "effective_date": datetime.now().strftime("%Y-%m-%d"),
            "brand_name": campaign["brand_name"],
            "creator_name": creator["display_name"],
            "campaign_title": campaign["title"],
            "campaign_description": campaign["description"] or "",
            "deliverables": "\n".join([f"- {d.get('type', 'deliverable')}: {d.get('description', '')}" for d in deliverables]),
            "total_amount": str(offer_amount),
            "currency": "USD",
            "upfront_percent": str(campaign["upfront_percent"]),
            "upfront_amount": str(upfront_amount),
            "completion_percent": str(campaign["completion_percent"]),
            "completion_amount": str(completion_amount),
            "start_date": timeline.get("start_date", "TBD"),
            "end_date": timeline.get("end_date", "TBD"),
        }

        # Fill template
        filled_content = template_content
        for var, value in variables.items():
            filled_content = filled_content.replace(f"{{{{{var}}}}}", str(value))

        return GeneratedContractResponse(
            template_id=template_id,
            template_name=template_name,
            content=filled_content,
            variables_used=variables,
        )


# =============================================================================
# Dashboard Statistics Endpoints
# =============================================================================

@router.get("/agency/campaigns/stats", response_model=CampaignDashboardStats)
async def get_agency_campaign_stats(
    membership: dict = Depends(require_agency_membership),
):
    """Get campaign statistics for the agency dashboard."""
    async with get_connection() as conn:
        # Total and active campaigns
        campaign_stats = await conn.fetchrow(
            """SELECT
                   COUNT(*) as total,
                   COUNT(*) FILTER (WHERE status = 'active') as active
               FROM campaigns
               WHERE agency_id = $1""",
            membership["agency_id"],
        )

        # Payment stats
        payment_stats = await conn.fetchrow(
            """SELECT
                   COALESCE(SUM(amount) FILTER (WHERE status = 'released'), 0) as total_spent,
                   COALESCE(SUM(amount) FILTER (WHERE status IN ('pending', 'held')), 0) as pending
               FROM campaign_payments cp
               JOIN campaigns c ON cp.campaign_id = c.id
               WHERE c.agency_id = $1""",
            membership["agency_id"],
        )

        # Unique creators engaged
        creator_count = await conn.fetchval(
            """SELECT COUNT(DISTINCT co.creator_id)
               FROM campaign_offers co
               JOIN campaigns c ON co.campaign_id = c.id
               WHERE c.agency_id = $1 AND co.status = 'accepted'""",
            membership["agency_id"],
        )

        # Acceptance rate
        offer_stats = await conn.fetchrow(
            """SELECT
                   COUNT(*) as total,
                   COUNT(*) FILTER (WHERE status = 'accepted') as accepted
               FROM campaign_offers co
               JOIN campaigns c ON co.campaign_id = c.id
               WHERE c.agency_id = $1""",
            membership["agency_id"],
        )

        acceptance_rate = 0.0
        if offer_stats["total"] > 0:
            acceptance_rate = offer_stats["accepted"] / offer_stats["total"]

        return CampaignDashboardStats(
            total_campaigns=campaign_stats["total"],
            active_campaigns=campaign_stats["active"],
            total_spent=payment_stats["total_spent"],
            pending_payments=payment_stats["pending"],
            total_creators_engaged=creator_count,
            acceptance_rate=acceptance_rate,
        )


@router.get("/creators/me/campaigns/stats", response_model=CreatorCampaignStats)
async def get_creator_campaign_stats(
    creator: dict = Depends(require_creator_record),
):
    """Get campaign statistics for the creator dashboard."""
    async with get_connection() as conn:
        # Offer stats
        offer_stats = await conn.fetchrow(
            """SELECT
                   COUNT(*) as total,
                   COUNT(*) FILTER (WHERE status IN ('pending', 'viewed')) as pending,
                   COUNT(*) FILTER (WHERE status = 'accepted') as accepted
               FROM campaign_offers
               WHERE creator_id = $1""",
            creator["id"],
        )

        # Payment stats
        payment_stats = await conn.fetchrow(
            """SELECT
                   COALESCE(SUM(amount) FILTER (WHERE status = 'released'), 0) as total_earnings,
                   COALESCE(SUM(amount) FILTER (WHERE status IN ('pending', 'held')), 0) as pending
               FROM campaign_payments
               WHERE creator_id = $1 AND payment_type != 'affiliate'""",
            creator["id"],
        )

        # Affiliate earnings
        affiliate_earnings = await conn.fetchval(
            """SELECT COALESCE(SUM(total_commission), 0)
               FROM affiliate_links
               WHERE creator_id = $1""",
            creator["id"],
        )

        return CreatorCampaignStats(
            total_offers_received=offer_stats["total"],
            pending_offers=offer_stats["pending"],
            accepted_offers=offer_stats["accepted"],
            total_earnings=payment_stats["total_earnings"],
            pending_earnings=payment_stats["pending"],
            affiliate_earnings=affiliate_earnings,
        )
