"""Deal Flow pricing engine — pure, IO-free, unit-testable.

Canonical model (the most-recent deal, LA_NonProfit_Pricing_OnePager_v2.1):

    tier PEPM:        Mid $10        Max $13
    tier onboarding:  Mid $4,000     Max $10,000
    subscription_yr = pepm * headcount * 12
    subtotal        = subscription_yr + onboarding
    broker_disc     = subtotal * 0.10   (if broker)
    partner_disc    = subtotal * 0.05   (if partner)
    your_price_yr   = subtotal - broker_disc - partner_disc   # flat off subtotal, NOT compounded
    you_save_yr     = subtotal - your_price_yr

HR Partner add-on ($2,000/mo) is surfaced as an info line, not folded into the yearly total.

Pricing constants live here so a future per-field override is a small add.
"""

from __future__ import annotations

from datetime import date
from typing import Literal, Optional

from pydantic import BaseModel, Field

Tier = Literal["mid", "max"]

# ── Constants ────────────────────────────────────────────────────────────────
TIER_PEPM: dict[str, int] = {"mid": 10, "max": 13}
TIER_ONBOARDING: dict[str, int] = {"mid": 4_000, "max": 10_000}
BROKER_RATE = 0.10
PARTNER_RATE = 0.05
HR_PARTNER_MONTHLY = 2_000
MONTHS = 12

TIER_LABEL: dict[str, str] = {"mid": "Mid", "max": "Max"}


# ── Models ───────────────────────────────────────────────────────────────────
class DealInputs(BaseModel):
    company_name: str = Field(..., min_length=1, max_length=200)
    headcount: int = Field(..., gt=0, le=1_000_000)
    tier: Tier = "max"  # the recommended / highlighted tier
    broker: bool = False
    broker_name: Optional[str] = Field(default=None, max_length=120)
    partner: bool = False
    hr_partner_addon: bool = False
    proposal_date: Optional[date] = None


class DealQuote(BaseModel):
    tier: Tier
    tier_label: str
    pepm: int
    onboarding: int
    subscription_yr: int
    subtotal: int
    broker_disc: int
    partner_disc: int
    discount_pct: int
    your_price_yr: int
    you_save_yr: int


def compute_quote(
    tier: Tier,
    headcount: int,
    broker: bool = False,
    partner: bool = False,
) -> DealQuote:
    """Compute a single tier's quote. Pure function — no IO."""
    pepm = TIER_PEPM[tier]
    onboarding = TIER_ONBOARDING[tier]
    subscription_yr = pepm * headcount * MONTHS
    subtotal = subscription_yr + onboarding

    broker_disc = int(round(subtotal * BROKER_RATE)) if broker else 0
    partner_disc = int(round(subtotal * PARTNER_RATE)) if partner else 0
    discount_pct = (10 if broker else 0) + (5 if partner else 0)

    your_price_yr = subtotal - broker_disc - partner_disc
    you_save_yr = subtotal - your_price_yr

    return DealQuote(
        tier=tier,
        tier_label=TIER_LABEL[tier],
        pepm=pepm,
        onboarding=onboarding,
        subscription_yr=subscription_yr,
        subtotal=subtotal,
        broker_disc=broker_disc,
        partner_disc=partner_disc,
        discount_pct=discount_pct,
        your_price_yr=your_price_yr,
        you_save_yr=you_save_yr,
    )


def compute_both(inp: DealInputs) -> dict[str, DealQuote]:
    """Compute Mid + Max quotes from one set of inputs (same headcount + discounts)."""
    return {
        "mid": compute_quote("mid", inp.headcount, inp.broker, inp.partner),
        "max": compute_quote("max", inp.headcount, inp.broker, inp.partner),
    }
