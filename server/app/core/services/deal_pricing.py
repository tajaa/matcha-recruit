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
from typing import Dict, Literal, Optional

from pydantic import BaseModel, Field

Tier = Literal["lite", "mid", "max"]
TIERS: tuple[Tier, ...] = ("lite", "mid", "max")

# ── Default constants (overridable per-deal via DealInputs.overrides) ─────────
TIER_PEPM: dict[str, int] = {"lite": 5, "mid": 10, "max": 13}
TIER_ONBOARDING: dict[str, int] = {"lite": 0, "mid": 4_000, "max": 10_000}


def lite_pepm(headcount: int) -> int:
    """Lite has volume-based PEPM: base $5, −$1 over 100 employees, −$2 over 500."""
    if headcount > 500:
        return 3
    if headcount > 100:
        return 4
    return 5


def default_pepm(tier: Tier, headcount: int) -> int:
    """Default PEPM for a tier at a given headcount (Lite is volume-tiered)."""
    return lite_pepm(headcount) if tier == "lite" else TIER_PEPM[tier]
BROKER_RATE = 0.10
PARTNER_RATE = 0.05
HR_PARTNER_MONTHLY = 2_000
MONTHS = 12

TIER_LABEL: dict[str, str] = {"lite": "Lite", "mid": "Mid", "max": "Max"}


# ── Models ───────────────────────────────────────────────────────────────────
class Block(BaseModel):
    """Generic editable-document block, shared by the Lite Edition + Full Deal docs.

    `kind` is a free string interpreted by each renderer; prose kinds carry `text`/`items`,
    "computed" kinds are rendered from pricing. `column` places a block in a 2-column layout
    (Lite Edition); `new_page` starts a fresh PDF page (Full Deal).
    """
    id: str
    kind: str
    text: str = ""
    items: list[str] = Field(default_factory=list)
    new_page: bool = False
    column: str = ""


class TierOverride(BaseModel):
    """Per-deal override of a tier's PEPM / onboarding fee."""
    pepm: int = Field(..., ge=0, le=10_000)
    onboarding: int = Field(..., ge=0, le=10_000_000)


class DealInputs(BaseModel):
    company_name: str = Field(..., min_length=1, max_length=200)
    headcount: int = Field(..., gt=0, le=1_000_000)
    tier: Tier = "max"  # the recommended / highlighted tier
    broker: bool = False
    broker_name: Optional[str] = Field(default=None, max_length=120)
    partner: bool = False
    hr_partner_addon: bool = False
    proposal_date: Optional[date] = None
    # Optional per-tier PEPM/onboarding overrides, keyed by tier ("lite"/"mid"/"max").
    overrides: Optional[Dict[str, TierOverride]] = None
    # Which proposal layout to render. "standard" = navy 3-tier comparison;
    # "lite_edition" = the green single-tier Lite one-pager.
    template: Literal["standard", "lite_edition"] = "standard"
    # Editable Lite Edition document (None → defaults in deal_proposal_template).
    lite_blocks: Optional[list[Block]] = None


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
    pepm: Optional[int] = None,
    onboarding: Optional[int] = None,
) -> DealQuote:
    """Compute a single tier's quote. Pure function — no IO.

    `pepm` / `onboarding` override the tier defaults when provided.
    """
    pepm = default_pepm(tier, headcount) if pepm is None else pepm
    onboarding = TIER_ONBOARDING[tier] if onboarding is None else onboarding
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


def compute_all(inp: DealInputs) -> dict[str, DealQuote]:
    """Compute Lite + Mid + Max quotes from one set of inputs (same headcount + discounts).

    Applies per-tier PEPM/onboarding overrides from `inp.overrides` when present.
    """
    out: dict[str, DealQuote] = {}
    overrides = inp.overrides or {}
    for t in TIERS:
        ov = overrides.get(t)
        out[t] = compute_quote(
            t,
            inp.headcount,
            inp.broker,
            inp.partner,
            pepm=ov.pepm if ov else None,
            onboarding=ov.onboarding if ov else None,
        )
    return out
