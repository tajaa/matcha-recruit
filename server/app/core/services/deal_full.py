"""Full multi-page proposal — rack-rate pricing engine + inputs.

Distinct from the tier one-pager (`deal_pricing.py`). This is the model used by the
~10-page LA_NonProfit_Proposal_v1: a standard PEPM rack rate with stacked discounts
(volume + broker + partner), a flat platform fee, jurisdiction fees, and a one-time
implementation fee. Pure / IO-free.

Verified against the LA proposal: rack $15 → volume −10% → $13.50 → broker+partner −15%
→ $11.48; platform fee $5,000 → $4,250; implementation $8,000 → $6,800; Year-1 $79,930.
"""

from __future__ import annotations

from datetime import date
from decimal import ROUND_HALF_UP, Decimal
from typing import Optional

from pydantic import BaseModel, Field


def _r2(x: float) -> float:
    """Round half-up to cents (matches how the proposals present PEPM)."""
    return float(Decimal(str(x)).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP))


def _r0(x: float) -> int:
    """Round half-up to whole dollars."""
    return int(Decimal(str(x)).quantize(Decimal("1"), rounding=ROUND_HALF_UP))

# ── Defaults ──────────────────────────────────────────────────────────────────
DEFAULT_RACK_PEPM = 15.00
DEFAULT_PLATFORM_FEE = 5_000
DEFAULT_IMPLEMENTATION = 8_000
VOLUME_RATE = 0.10          # PEPM only, auto at 500+ employees
BROKER_RATE = 0.10
PARTNER_RATE = 0.05
DEFAULT_ROI_HARD_SAVINGS = 223_000
DEFAULT_ROI_RISK_REDUCTION = 60_000

# Jurisdiction fee schedule (per additional jurisdiction / year), by headcount tier.
JURISDICTION_TIERS = [
    (0, 249, "Growth", 3_200),
    (250, 999, "Business", 7_500),
    (1_000, 10_000_000, "Enterprise", 10_000),
]

_DEFAULT_EXEC_SUMMARY = (
    "Matcha is a compliance, employee relations, and workforce risk platform built for "
    "organizations that carry heavy regulatory and funding obligations on lean administrative "
    "budgets. Your compliance and HR team stops manually checking regulatory pages and opens one "
    "dashboard. Every requirement that applies to your workforce is monitored continuously. When "
    "something changes, they get an alert with severity, which team is affected, and what action to "
    "take. They stop hunting for changes and start responding to them.\n\n"
    "From employment law and local ordinances to data privacy, ER investigations, pre-termination "
    "risk scoring, and intelligent policy documents, Matcha consolidates fragmented HR operations "
    "into a single platform. The system is configured during implementation with the categories that "
    "apply to your operation, alongside your core labor obligations: minimum wage, local wage "
    "ordinances, meal and rest breaks, paid sick leave, and workers' compensation.\n\n"
    "When your team has a compliance question, they type it into the system, and it walks through "
    "the jurisdiction hierarchy, identifies which level of law governs, cites the statutes, and shows "
    "the penalty range and enforcing agency. Sourced from government databases with citation links "
    "and verification timestamps, not generated from thin air.\n\n"
    "What your team owns after go-live: the system. We build it during implementation, then hand it "
    "off. Your admins create onboarding cohorts, modify templates, run compliance scans. The CSM "
    "stays assigned, but the platform runs independently. You're not paying for a service — you're "
    "buying infrastructure."
)

_DEFAULT_ROI_INTRO = (
    "Organizations in regulated, multi-site environments carry a disproportionately high compliance "
    "burden relative to their administrative budgets — and a disproportionately high consequence "
    "when something goes wrong. A single wage-and-hour class action can run well into six figures in "
    "back pay and penalties before defense costs. A retaliation or wrongful-termination claim can "
    "generate $150,000+ in defense costs. The hard savings below reflect what the platform replaces. "
    "The risk-reduction value reflects what it prevents."
)


# ── Models ────────────────────────────────────────────────────────────────────
class FullDealInputs(BaseModel):
    company_name: str = Field(..., min_length=1, max_length=200)
    headcount: int = Field(..., gt=0, le=1_000_000)
    location: str = Field(default="", max_length=160)
    proposal_date: Optional[date] = None

    rack_pepm: float = Field(default=DEFAULT_RACK_PEPM, ge=0, le=10_000)
    platform_fee: int = Field(default=DEFAULT_PLATFORM_FEE, ge=0, le=10_000_000)
    implementation: int = Field(default=DEFAULT_IMPLEMENTATION, ge=0, le=10_000_000)
    jurisdictions_included: int = Field(default=1, ge=0, le=1_000)
    jurisdictions_extra: int = Field(default=0, ge=0, le=1_000)

    volume_discount: Optional[bool] = None   # None → auto (headcount >= 500)
    broker: bool = False
    broker_name: Optional[str] = Field(default=None, max_length=120)
    partner: bool = False

    roi_hard_savings: int = Field(default=DEFAULT_ROI_HARD_SAVINGS, ge=0, le=100_000_000)
    roi_risk_reduction: int = Field(default=DEFAULT_ROI_RISK_REDUCTION, ge=0, le=100_000_000)

    # Editable prose (pre-filled defaults). Paragraphs separated by blank lines.
    exec_summary: str = Field(default=_DEFAULT_EXEC_SUMMARY)
    roi_intro: str = Field(default=_DEFAULT_ROI_INTRO)


class FullQuote(BaseModel):
    headcount: int
    # PEPM build-up
    rack_pepm: float
    volume_applied: bool
    volume_pepm_cut: float
    subtotal_pepm: float
    bp_rate_pct: int
    bp_pepm_cut: float
    your_pepm: float
    # Annual
    annual_employee_standard: int
    annual_employee_your: int
    platform_fee_standard: int
    platform_fee_your: int
    extra_jurisdiction_cost: int
    annual_recurring_standard: int
    annual_recurring_your: int
    implementation_standard: int
    implementation_your: int
    year1_standard: int
    year1_your: int
    year2_your: int
    # Savings
    pepm_save: float
    annual_employee_save: int
    platform_save: int
    recurring_save: int
    implementation_save: int
    year1_save: int
    # Jurisdiction
    juris_tier: str
    juris_fee: int
    # ROI
    roi_hard_savings: int
    roi_risk_reduction: int
    roi_total_value: int
    roi_net_year1: int
    roi_net_year2: int
    roi_net_3yr: int
    roi_multiple: float
    roi_payback_month: int


def _juris_tier(headcount: int) -> tuple[str, int]:
    for lo, hi, name, fee in JURISDICTION_TIERS:
        if lo <= headcount <= hi:
            return name, fee
    return "Enterprise", 10_000


def compute_full_pricing(inp: FullDealInputs) -> FullQuote:
    H = inp.headcount
    rack = _r2(inp.rack_pepm)

    volume_applied = (H >= 500) if inp.volume_discount is None else bool(inp.volume_discount)
    volume_cut = _r2(rack * VOLUME_RATE) if volume_applied else 0.0
    subtotal_pepm = _r2(rack - volume_cut)

    bp_rate = (BROKER_RATE if inp.broker else 0.0) + (PARTNER_RATE if inp.partner else 0.0)
    bp_rate_pct = int(round(bp_rate * 100))
    your_pepm = _r2(subtotal_pepm * (1 - bp_rate))
    bp_pepm_cut = _r2(subtotal_pepm - your_pepm)

    annual_emp_std = _r0(rack * H * 12)
    annual_emp_your = _r0(your_pepm * H * 12)
    pf_std = inp.platform_fee
    pf_your = _r0(pf_std * (1 - bp_rate))
    impl_std = inp.implementation
    impl_your = _r0(impl_std * (1 - bp_rate))

    juris_tier, juris_fee = _juris_tier(H)
    extra_juris_cost = inp.jurisdictions_extra * juris_fee

    recurring_std = annual_emp_std + pf_std
    recurring_your = annual_emp_your + pf_your + extra_juris_cost
    year1_std = recurring_std + impl_std
    year1_your = recurring_your + impl_your

    total_value = inp.roi_hard_savings + inp.roi_risk_reduction
    net_y1 = total_value - year1_your
    net_y2 = total_value - recurring_your
    net_3yr = net_y1 + net_y2 * 2
    multiple = round(total_value / year1_your, 1) if year1_your else 0.0
    payback = max(1, -(-year1_your * 12 // total_value)) if total_value else 0  # ceil(months)

    return FullQuote(
        headcount=H,
        rack_pepm=rack,
        volume_applied=volume_applied,
        volume_pepm_cut=volume_cut,
        subtotal_pepm=subtotal_pepm,
        bp_rate_pct=bp_rate_pct,
        bp_pepm_cut=bp_pepm_cut,
        your_pepm=your_pepm,
        annual_employee_standard=annual_emp_std,
        annual_employee_your=annual_emp_your,
        platform_fee_standard=pf_std,
        platform_fee_your=pf_your,
        extra_jurisdiction_cost=extra_juris_cost,
        annual_recurring_standard=recurring_std,
        annual_recurring_your=recurring_your,
        implementation_standard=impl_std,
        implementation_your=impl_your,
        year1_standard=year1_std,
        year1_your=year1_your,
        year2_your=recurring_your,
        pepm_save=_r2(rack - your_pepm),
        annual_employee_save=annual_emp_std - annual_emp_your,
        platform_save=pf_std - pf_your,
        recurring_save=recurring_std - recurring_your,
        implementation_save=impl_std - impl_your,
        year1_save=year1_std - year1_your,
        juris_tier=juris_tier,
        juris_fee=juris_fee,
        roi_hard_savings=inp.roi_hard_savings,
        roi_risk_reduction=inp.roi_risk_reduction,
        roi_total_value=total_value,
        roi_net_year1=net_y1,
        roi_net_year2=net_y2,
        roi_net_3yr=net_3yr,
        roi_multiple=multiple,
        roi_payback_month=int(payback),
    )
