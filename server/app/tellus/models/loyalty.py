"""Pydantic models for Tell-Us brand loyalty."""
from datetime import datetime
from typing import Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, model_validator


LoyaltyProgramStatus = Literal["draft", "active", "paused"]
LoyaltyCounterMode = Literal["visit", "purchase"]
LoyaltyEventKey = Literal[
    "visit", "purchase", "review", "board_reply", "follow", "social_post"
]
LoyaltyTierKey = Literal["bronze", "silver", "gold"]
LoyaltySocialPlatform = Literal[
    "instagram", "tiktok", "youtube", "facebook", "x", "other"
]


class LoyaltyEarningRuleIn(BaseModel):
    event_key: LoyaltyEventKey
    award_type: Literal["fixed", "per_dollar"]
    fixed_points: int | None = Field(default=None, ge=1, le=100_000)
    points_per_dollar: int | None = Field(default=None, ge=1, le=100)
    min_purchase_cents: int | None = Field(default=None, ge=1, le=1_000_000)
    max_points_per_event: int | None = Field(default=None, ge=1, le=100_000)
    daily_cap: int | None = Field(default=None, ge=1, le=1_000_000)
    cooldown_seconds: int | None = Field(default=None, ge=0, le=2_592_000)
    is_active: bool = True


class LoyaltyTierIn(BaseModel):
    tier_key: LoyaltyTierKey
    threshold_points: int = Field(ge=0, le=100_000_000)
    benefits: str | None = Field(default=None, max_length=2_000)


class LoyaltyProgramPut(BaseModel):
    name: str = Field(min_length=1, max_length=120)
    point_singular: str = Field(min_length=1, max_length=40)
    point_plural: str = Field(min_length=1, max_length=40)
    terms: str | None = Field(default=None, max_length=10_000)
    status: LoyaltyProgramStatus
    counter_mode: LoyaltyCounterMode
    rules: list[LoyaltyEarningRuleIn] = Field(min_length=6, max_length=6)
    tiers: list[LoyaltyTierIn] = Field(min_length=3, max_length=3)

    @model_validator(mode="after")
    def validate_complete_config(self) -> "LoyaltyProgramPut":
        expected_events = {
            "visit", "purchase", "review", "board_reply", "follow", "social_post"
        }
        event_keys = {rule.event_key for rule in self.rules}
        if event_keys != expected_events or len(self.rules) != len(event_keys):
            raise ValueError("A program needs exactly one rule for every loyalty event.")

        by_event = {rule.event_key: rule for rule in self.rules}
        purchase = by_event["purchase"]
        if purchase.award_type != "per_dollar":
            raise ValueError("The purchase rule must award points per dollar.")
        if any(
            value is None
            for value in (
                purchase.points_per_dollar,
                purchase.min_purchase_cents,
                purchase.max_points_per_event,
            )
        ):
            raise ValueError("The purchase rule requires all purchase fields.")
        for event_key, rule in by_event.items():
            if event_key == "purchase":
                continue
            if rule.award_type != "fixed" or rule.fixed_points is None:
                raise ValueError(f"The {event_key} rule must use fixed points.")

        counter_rule = by_event[self.counter_mode]
        if not counter_rule.is_active:
            raise ValueError("The selected counter earning rule must be active.")
        other_counter = "purchase" if self.counter_mode == "visit" else "visit"
        if by_event[other_counter].is_active:
            raise ValueError("Only the selected counter earning rule may be active.")

        expected_tiers = {"bronze", "silver", "gold"}
        tier_keys = {tier.tier_key for tier in self.tiers}
        if tier_keys != expected_tiers or len(self.tiers) != len(tier_keys):
            raise ValueError("A program needs exactly Bronze, Silver, and Gold tiers.")
        tiers = {tier.tier_key: tier for tier in self.tiers}
        if tiers["bronze"].threshold_points != 0:
            raise ValueError("Bronze must start at zero lifetime points.")
        if not (
            tiers["silver"].threshold_points < tiers["gold"].threshold_points
            and tiers["silver"].threshold_points > 0
        ):
            raise ValueError("Silver and Gold thresholds must be positive and ordered.")
        return self


class LoyaltyRewardCreate(BaseModel):
    title: str = Field(min_length=1, max_length=255)
    description: str | None = Field(default=None, max_length=4_000)
    terms: str | None = Field(default=None, max_length=4_000)
    points_cost: int = Field(ge=1, le=1_000_000)
    redemption_expiry_days: int = Field(default=30, ge=1, le=365)
    active_from: datetime | None = None
    active_to: datetime | None = None
    is_active: bool = True


class LoyaltyRewardPatch(BaseModel):
    title: str | None = Field(default=None, min_length=1, max_length=255)
    description: str | None = Field(default=None, max_length=4_000)
    terms: str | None = Field(default=None, max_length=4_000)
    points_cost: int | None = Field(default=None, ge=1, le=1_000_000)
    redemption_expiry_days: int | None = Field(default=None, ge=1, le=365)
    active_from: datetime | None = None
    active_to: datetime | None = None
    is_active: bool | None = None


class LoyaltyRedemptionCreate(BaseModel):
    reward_id: UUID
    client_request_id: UUID


class LoyaltyVisitIn(BaseModel):
    model_config = ConfigDict(extra="forbid")
    member_token: str = Field(min_length=1, max_length=512)


class LoyaltyPurchaseIn(BaseModel):
    model_config = ConfigDict(extra="forbid")
    member_token: str = Field(min_length=1, max_length=512)
    amount_cents: int = Field(ge=1, le=1_000_000)


class LoyaltyRedeemIn(BaseModel):
    model_config = ConfigDict(extra="forbid")
    redemption_token: str = Field(min_length=1, max_length=512)


class LoyaltySocialSubmissionCreate(BaseModel):
    platform: LoyaltySocialPlatform
    post_url: str = Field(min_length=8, max_length=2_048)
    note: str | None = Field(default=None, max_length=1_000)


class LoyaltySocialDecisionIn(BaseModel):
    note: str | None = Field(default=None, max_length=1_000)


class LoyaltyMemberQrOut(BaseModel):
    token: str
    qr_payload: str
    expires_at: datetime


class LoyaltyEarnOut(BaseModel):
    awarded: bool
    points: int
    points_balance: int
    lifetime_points: int
    tier_key: LoyaltyTierKey
    result_code: Literal["awarded", "cooldown", "daily_cap", "below_minimum", "inactive"]


class LoyaltyRedeemOut(BaseModel):
    reward_title: str
    redeemed_at: datetime
    store_name: str


class LoyaltyProgramOut(BaseModel):
    brand_id: UUID
    brand_name: str
    brand_slug: str
    name: str
    point_singular: str
    point_plural: str
    terms: str | None
    status: LoyaltyProgramStatus
    counter_mode: LoyaltyCounterMode
    rules: list[dict]
    tiers: list[dict]
    balance: dict | None = None
    rewards: list[dict] = Field(default_factory=list)


class LoyaltyProgramSummaryOut(BaseModel):
    brand_id: UUID
    brand_name: str
    brand_slug: str
    name: str
    point_plural: str
    status: LoyaltyProgramStatus
    points_balance: int
    lifetime_points: int
    tier_key: LoyaltyTierKey
