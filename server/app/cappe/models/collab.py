"""Pydantic shapes — Cappe brand<->creator collabs (offers, terms, deliverables, payments)."""
from datetime import date, datetime
from typing import Literal, Optional
from uuid import UUID

from pydantic import BaseModel, Field, model_validator

from .creators import DeliverableType, SocialPlatform

PaymentSchedule = Literal["upfront", "split_50_50", "per_deliverable"]
OfferStatus = Literal["sent", "negotiating", "accepted", "active", "completed",
                      "declined", "withdrawn", "cancelled"]


class TermsDeliverable(BaseModel):
    type: DeliverableType
    platform: SocialPlatform
    quantity: int = Field(ge=1, le=20)
    spec: Optional[str] = Field(default=None, max_length=2000)
    due_date: Optional[date] = None


class TermsUsageRights(BaseModel):
    scope: Literal["organic", "paid"] = "organic"
    # Organic usage may run long (a brand keeping organic posts up indefinitely
    # is normal) — the 24-month ceiling is a paid-usage-only guardrail, enforced
    # below rather than on the field, so it doesn't also cap organic grants.
    duration_months: Optional[int] = Field(default=None, ge=1, le=120)
    whitelisting: bool = False

    @model_validator(mode="after")
    def _paid_usage_guardrails(self):
        # Creator-first protection: perpetual paid usage rights are structurally
        # impossible, and whitelisting (running ads from the creator's handle)
        # IS paid usage — it can't hide under an "organic" label.
        if self.scope == "paid":
            if self.duration_months is None:
                raise ValueError("Paid usage rights require duration_months (max 24)")
            if self.duration_months > 24:
                raise ValueError("Paid usage rights are capped at 24 months")
        if self.whitelisting and self.scope != "paid":
            raise ValueError("Whitelisting requires usage_rights.scope='paid'")
        return self


class TermsExclusivity(BaseModel):
    category: str = Field(min_length=1, max_length=120)
    duration_months: int = Field(ge=1, le=12)


class CollabTerms(BaseModel):
    """The negotiable object. One immutable snapshot per revision."""
    compensation_cents: int = Field(ge=0, le=1_000_000_000)
    payment_schedule: PaymentSchedule
    deliverables: list[TermsDeliverable] = Field(min_length=1, max_length=20)
    usage_rights: TermsUsageRights = Field(default_factory=TermsUsageRights)
    exclusivity: Optional[TermsExclusivity] = None
    revision_rounds: int = Field(default=1, ge=0, le=5)
    approval_required: bool = True
    ftc_disclosure: bool = True
    start_date: Optional[date] = None
    end_date: Optional[date] = None
    notes: Optional[str] = Field(default=None, max_length=4000)

    @model_validator(mode="after")
    def _dates_ordered(self):
        if self.start_date and self.end_date and self.end_date < self.start_date:
            raise ValueError("end_date before start_date")
        return self

    @model_validator(mode="after")
    def _creator_first_guardrails(self):
        # Exclusivity must be paid — no gifting-only category lockouts.
        if self.exclusivity is not None and self.compensation_cents <= 0:
            raise ValueError("Exclusivity requires compensation_cents > 0")
        # FTC disclosure is non-waivable. Field stays in the schema for
        # stability; the frontend renders it as a static "always on" line,
        # not a checkbox a brand could uncheck.
        if not self.ftc_disclosure:
            raise ValueError("FTC disclosure cannot be waived")
        # A per_deliverable schedule splits compensation_cents evenly across
        # every deliverable (services/collab.py:build_payment_rows); a total
        # below the deliverable count divides to $0 per row, which then fails
        # the payments table's amount_cents > 0 CHECK at accept time — reject
        # it here instead, at offer create/counter, where it's a normal 422.
        if (self.payment_schedule == "per_deliverable" and self.compensation_cents > 0
                and self.compensation_cents < self.deliverable_count):
            raise ValueError(
                f"Compensation ({self.compensation_cents}c) is too low to split across "
                f"{self.deliverable_count} deliverables — each row would be $0"
            )
        return self

    @property
    def deliverable_count(self) -> int:
        return sum(d.quantity for d in self.deliverables)


class CampaignUpsert(BaseModel):
    title: str = Field(min_length=1, max_length=200)
    description: Optional[str] = Field(default=None, max_length=4000)
    budget_min_cents: Optional[int] = Field(default=None, ge=0)
    budget_max_cents: Optional[int] = Field(default=None, ge=0)
    deliverable_notes: Optional[str] = Field(default=None, max_length=2000)
    status: Optional[Literal["active", "archived"]] = None


class CampaignPatch(BaseModel):
    """Partial update — CampaignUpsert.title is required (create-only), so
    PATCH needs its own all-optional shape rather than reusing it."""
    title: Optional[str] = Field(default=None, min_length=1, max_length=200)
    description: Optional[str] = Field(default=None, max_length=4000)
    budget_min_cents: Optional[int] = Field(default=None, ge=0)
    budget_max_cents: Optional[int] = Field(default=None, ge=0)
    deliverable_notes: Optional[str] = Field(default=None, max_length=2000)
    status: Optional[Literal["active", "archived"]] = None


class Campaign(BaseModel):
    id: UUID
    title: str
    description: Optional[str] = None
    budget_min_cents: Optional[int] = None
    budget_max_cents: Optional[int] = None
    deliverable_notes: Optional[str] = None
    status: str
    offer_count: int = 0
    created_at: datetime


class OfferCreate(BaseModel):
    creator_profile_id: UUID
    campaign_id: Optional[UUID] = None
    title: str = Field(min_length=1, max_length=200)
    terms: CollabTerms
    message: Optional[str] = Field(default=None, max_length=4000)


class OfferCounter(BaseModel):
    terms: CollabTerms
    message: Optional[str] = Field(default=None, max_length=4000)


class OfferDecline(BaseModel):
    reason: Optional[str] = Field(default=None, max_length=2000)


class OfferCancel(BaseModel):
    reason: str = Field(min_length=1, max_length=2000)


class OfferMessageCreate(BaseModel):
    body: str = Field(min_length=1, max_length=8000)


class DeliverableSubmit(BaseModel):
    submission_url: str = Field(min_length=8, max_length=500)
    submission_note: Optional[str] = Field(default=None, max_length=2000)
    proof_media_url: Optional[str] = None


class DeliverableRevision(BaseModel):
    review_note: str = Field(min_length=1, max_length=2000)


# ── Response shapes ─────────────────────────────────────────────────────────

class OfferRevisionOut(BaseModel):
    id: UUID
    revision_no: int
    proposed_by: str
    terms: CollabTerms
    message: Optional[str] = None
    created_at: datetime


class OfferMessageOut(BaseModel):
    id: UUID
    sender: str
    body: str
    revision_id: Optional[UUID] = None
    created_at: datetime


class DeliverableOut(BaseModel):
    id: UUID
    idx: int
    type: str
    platform: str
    spec: Optional[str] = None
    due_date: Optional[date] = None
    status: str
    submission_url: Optional[str] = None
    submission_note: Optional[str] = None
    proof_media_url: Optional[str] = None
    submitted_at: Optional[datetime] = None
    revision_count: int
    review_note: Optional[str] = None
    approved_at: Optional[datetime] = None


class PaymentOut(BaseModel):
    id: UUID
    idx: int
    label: str
    amount_cents: int
    currency: str
    trigger: str
    deliverable_id: Optional[UUID] = None
    status: str
    fee_cents: Optional[int] = None
    due_at: Optional[datetime] = None
    paid_at: Optional[datetime] = None


class OfferListItem(BaseModel):
    id: UUID
    title: str
    status: str
    payment_schedule: Optional[str] = None
    total_cents: Optional[int] = None
    currency: str
    campaign_id: Optional[UUID] = None
    # counterpart display
    brand_name: Optional[str] = None
    creator_handle: str
    creator_display_name: str
    creator_avatar_url: Optional[str] = None
    last_action_at: datetime
    created_at: datetime


# ── Deal Check — deterministic creator-side deal review (no LLM) ────────────
# Mirrors the discipline module's deterministic-gate philosophy: fixed rules,
# fixed thresholds, no model call. Computed server-side in services/collab.py
# and returned ONLY on the creator's side of OfferDetail — a brand never sees
# the creator's private analysis of its own offer.

DealCheckSeverity = Literal["good", "caution", "warning"]


class DealCheckItem(BaseModel):
    key: str
    severity: DealCheckSeverity
    title: str
    detail: str


class BrandStats(BaseModel):
    """Brand track record, shown only on the creator's side — transparency
    so a creator can weigh a new/unproven brand before accepting terms."""
    completed_collabs: int = 0
    brand_cancelled: int = 0
    in_progress: int = 0
    avg_hours_to_pay: Optional[float] = None


class OfferDetail(OfferListItem):
    side: Literal["brand", "creator"]        # the CALLER's side
    accepted_revision_id: Optional[UUID] = None
    declined_reason: Optional[str] = None
    cancelled_by: Optional[str] = None
    cancel_reason: Optional[str] = None
    revisions: list[OfferRevisionOut]
    messages: list[OfferMessageOut]
    deliverables: list[DeliverableOut]
    payments: list[PaymentOut]
    creator_payouts_ready: bool              # brand UI: explains why accept may 409
    deal_check: Optional[list[DealCheckItem]] = None   # creator side only
    brand_stats: Optional[BrandStats] = None            # creator side only
    auto_approve_days: int                   # both sides: countdown on submitted deliverables


class OfferPage(BaseModel):
    offers: list[OfferListItem]
    total: int


class EarningsRow(BaseModel):
    offer_id: UUID
    offer_title: str
    brand_name: Optional[str] = None
    label: str
    amount_cents: int
    fee_cents: Optional[int] = None
    status: str
    paid_at: Optional[datetime] = None
