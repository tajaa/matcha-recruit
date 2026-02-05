"""
Campaign platform models for the limit order deal system.
Includes campaigns, offers, payments, affiliates, valuations, and templates.
"""
from datetime import datetime, date
from decimal import Decimal
from typing import Optional, Literal
from uuid import UUID
from pydantic import BaseModel, Field


# Type definitions
CampaignStatus = Literal["draft", "open", "active", "completed", "cancelled"]
OfferStatus = Literal["pending", "viewed", "accepted", "declined", "expired", "taken"]
PaymentType = Literal["upfront", "completion", "milestone", "affiliate"]
PaymentStatus = Literal["pending", "held", "released", "refunded", "failed"]
AffiliateEventType = Literal["click", "conversion"]
TemplateType = Literal["sponsorship", "affiliate", "content", "ambassador", "custom"]


# =============================================================================
# Campaign Models
# =============================================================================

class CampaignDeliverable(BaseModel):
    """A single deliverable in a campaign."""
    type: str  # e.g., "instagram_post", "youtube_video", "tiktok"
    quantity: int = 1
    description: Optional[str] = None
    due_date: Optional[date] = None


class CampaignTimeline(BaseModel):
    """Timeline for a campaign."""
    start_date: Optional[date] = None
    end_date: Optional[date] = None
    milestones: Optional[list[dict]] = None


class CampaignCreate(BaseModel):
    """Create a new campaign."""
    brand_name: str
    title: str
    description: Optional[str] = None
    deliverables: list[CampaignDeliverable] = []
    timeline: Optional[CampaignTimeline] = None
    total_budget: Decimal
    upfront_percent: int = Field(default=30, ge=0, le=100)
    completion_percent: int = Field(default=70, ge=0, le=100)
    platform_fee_percent: Decimal = Field(default=Decimal("10.00"))
    max_creators: int = Field(default=1, ge=1)
    contract_template_id: Optional[UUID] = None
    expires_at: Optional[datetime] = None


class CampaignUpdate(BaseModel):
    """Update an existing campaign."""
    brand_name: Optional[str] = None
    title: Optional[str] = None
    description: Optional[str] = None
    deliverables: Optional[list[CampaignDeliverable]] = None
    timeline: Optional[CampaignTimeline] = None
    total_budget: Optional[Decimal] = None
    upfront_percent: Optional[int] = None
    completion_percent: Optional[int] = None
    max_creators: Optional[int] = None
    contract_template_id: Optional[UUID] = None
    expires_at: Optional[datetime] = None


class CampaignResponse(BaseModel):
    """Campaign response for agency."""
    id: UUID
    agency_id: UUID
    agency_name: Optional[str] = None
    brand_name: str
    title: str
    description: Optional[str]
    deliverables: list[dict]
    timeline: dict
    total_budget: Decimal
    upfront_percent: int
    completion_percent: int
    platform_fee_percent: Decimal
    max_creators: int
    accepted_count: int
    status: CampaignStatus
    contract_template_id: Optional[UUID]
    expires_at: Optional[datetime]
    created_at: datetime
    updated_at: datetime


class CampaignWithOffersResponse(CampaignResponse):
    """Campaign response with offer details."""
    offers: list["CampaignOfferResponse"] = []
    pending_offers_count: int = 0
    viewed_offers_count: int = 0


# =============================================================================
# Campaign Offer Models
# =============================================================================

class CampaignOfferCreate(BaseModel):
    """Create an offer to a creator."""
    creator_id: UUID
    offered_amount: Decimal
    custom_message: Optional[str] = None


class CampaignOfferBulkCreate(BaseModel):
    """Create multiple offers at once."""
    offers: list[CampaignOfferCreate]


class CampaignOfferResponse(BaseModel):
    """Campaign offer response."""
    id: UUID
    campaign_id: UUID
    campaign_title: Optional[str] = None
    brand_name: Optional[str] = None
    creator_id: UUID
    creator_name: Optional[str] = None
    creator_profile_image: Optional[str] = None
    offered_amount: Decimal
    custom_message: Optional[str]
    status: OfferStatus
    creator_counter_amount: Optional[Decimal]
    creator_notes: Optional[str]
    viewed_at: Optional[datetime]
    responded_at: Optional[datetime]
    created_at: datetime


class CreatorOfferResponse(BaseModel):
    """Campaign offer as seen by the creator (with valuation context)."""
    id: UUID
    campaign_id: UUID
    campaign_title: str
    brand_name: str
    agency_name: str
    agency_verified: bool
    description: Optional[str]
    deliverables: list[dict]
    timeline: dict
    offered_amount: Decimal
    custom_message: Optional[str]
    status: OfferStatus
    creator_counter_amount: Optional[Decimal]
    creator_notes: Optional[str]
    # Valuation context
    estimated_value_min: Optional[Decimal] = None
    estimated_value_max: Optional[Decimal] = None
    offer_vs_value_ratio: Optional[float] = None  # offered_amount / estimated_value_mid
    viewed_at: Optional[datetime]
    responded_at: Optional[datetime]
    created_at: datetime
    expires_at: Optional[datetime]


class OfferAcceptRequest(BaseModel):
    """Request to accept an offer."""
    notes: Optional[str] = None


class OfferDeclineRequest(BaseModel):
    """Request to decline an offer."""
    reason: Optional[str] = None


class OfferCounterRequest(BaseModel):
    """Request to counter an offer."""
    counter_amount: Decimal
    notes: Optional[str] = None


# =============================================================================
# Campaign Payment Models
# =============================================================================

class CampaignPaymentResponse(BaseModel):
    """Campaign payment/escrow response."""
    id: UUID
    campaign_id: UUID
    creator_id: UUID
    creator_name: Optional[str] = None
    payment_type: PaymentType
    amount: Decimal
    platform_fee: Optional[Decimal]
    status: PaymentStatus
    stripe_payment_intent_id: Optional[str]
    stripe_transfer_id: Optional[str]
    charged_at: Optional[datetime]
    released_at: Optional[datetime]
    created_at: datetime


class PaymentReleaseRequest(BaseModel):
    """Request to release held payment to creator."""
    notes: Optional[str] = None


# =============================================================================
# Affiliate Link Models
# =============================================================================

class AffiliateLinkCreate(BaseModel):
    """Create an affiliate tracking link."""
    campaign_id: Optional[UUID] = None
    creator_id: UUID
    destination_url: str
    product_name: Optional[str] = None
    commission_percent: Decimal = Field(default=Decimal("10.00"))
    platform_percent: Decimal = Field(default=Decimal("5.00"))


class AffiliateLinkUpdate(BaseModel):
    """Update an affiliate link."""
    destination_url: Optional[str] = None
    product_name: Optional[str] = None
    commission_percent: Optional[Decimal] = None
    is_active: Optional[bool] = None


class AffiliateLinkResponse(BaseModel):
    """Affiliate link response."""
    id: UUID
    campaign_id: Optional[UUID]
    creator_id: UUID
    creator_name: Optional[str] = None
    agency_id: UUID
    agency_name: Optional[str] = None
    short_code: str
    tracking_url: str  # Full URL for sharing
    destination_url: str
    product_name: Optional[str]
    commission_percent: Decimal
    platform_percent: Decimal
    click_count: int
    conversion_count: int
    total_sales: Decimal
    total_commission: Decimal
    is_active: bool
    created_at: datetime
    updated_at: datetime


class AffiliateEventResponse(BaseModel):
    """Affiliate event (click or conversion)."""
    id: UUID
    link_id: UUID
    event_type: AffiliateEventType
    sale_amount: Optional[Decimal]
    commission_amount: Optional[Decimal]
    ip_address: Optional[str]
    referrer: Optional[str]
    created_at: datetime


class AffiliateStats(BaseModel):
    """Aggregate affiliate statistics."""
    total_clicks: int
    total_conversions: int
    conversion_rate: float
    total_sales: Decimal
    total_commission: Decimal
    pending_commission: Decimal


class ConversionWebhookPayload(BaseModel):
    """Webhook payload for recording a conversion."""
    short_code: str
    sale_amount: Decimal
    order_id: Optional[str] = None
    metadata: Optional[dict] = None


# =============================================================================
# Creator Valuation Models
# =============================================================================

class ValuationFactors(BaseModel):
    """Factors used in valuation calculation."""
    follower_count: Optional[int] = None
    engagement_rate: Optional[float] = None
    niche_multiplier: Optional[float] = None
    platform_rates: Optional[dict] = None  # e.g., {"instagram": 100, "youtube": 500}
    audience_quality: Optional[float] = None
    content_quality: Optional[float] = None
    historical_deal_value: Optional[Decimal] = None


class CreatorValuationResponse(BaseModel):
    """Creator valuation estimate."""
    id: UUID
    creator_id: UUID
    creator_name: Optional[str] = None
    estimated_value_min: Decimal
    estimated_value_max: Decimal
    estimated_value_mid: Decimal  # Calculated field
    factors: ValuationFactors
    data_sources: list[str]
    confidence_score: Optional[float]
    calculated_at: datetime


class ValuationRefreshRequest(BaseModel):
    """Request to recalculate valuation."""
    include_platform_data: bool = True
    manual_overrides: Optional[ValuationFactors] = None


# =============================================================================
# Contract Template Models
# =============================================================================

class ContractTemplateCreate(BaseModel):
    """Create a contract template."""
    name: str
    template_type: TemplateType
    content: str
    variables: Optional[list[str]] = None


class ContractTemplateUpdate(BaseModel):
    """Update a contract template."""
    name: Optional[str] = None
    template_type: Optional[TemplateType] = None
    content: Optional[str] = None
    variables: Optional[list[str]] = None
    is_default: Optional[bool] = None


class ContractTemplateResponse(BaseModel):
    """Contract template response."""
    id: UUID
    agency_id: Optional[UUID]
    name: str
    template_type: Optional[TemplateType]
    content: str
    variables: list[str]
    is_default: bool
    created_at: datetime
    updated_at: datetime


class GeneratedContractResponse(BaseModel):
    """Generated contract from template with variables filled."""
    template_id: UUID
    template_name: str
    content: str  # Filled template content
    variables_used: dict


# =============================================================================
# Dashboard/Summary Models
# =============================================================================

class CampaignDashboardStats(BaseModel):
    """Campaign statistics for agency dashboard."""
    total_campaigns: int
    active_campaigns: int
    total_spent: Decimal
    pending_payments: Decimal
    total_creators_engaged: int
    acceptance_rate: float


class CreatorCampaignStats(BaseModel):
    """Campaign statistics for creator dashboard."""
    total_offers_received: int
    pending_offers: int
    accepted_offers: int
    total_earnings: Decimal
    pending_earnings: Decimal
    affiliate_earnings: Decimal


# Forward reference update
CampaignWithOffersResponse.model_rebuild()
