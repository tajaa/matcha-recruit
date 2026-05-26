"""Full multi-page proposal — rack-rate pricing engine + editable block document.

Distinct from the tier one-pager (`deal_pricing.py`). This is the model used by the
~10-page LA_NonProfit_Proposal_v1: a standard PEPM rack rate with stacked discounts
(volume + broker + partner), a flat platform fee, jurisdiction fees, and a one-time
implementation fee. Pure / IO-free.

The document is a list of ordered **blocks**. Prose blocks (headings, paragraphs, notes,
callouts, bullet lists) are fully editable in the UI. "Computed" blocks (cover, the pricing
tables, signatures, disclaimer) are rendered server-side from the pricing inputs and are not
edited as text. `DEFAULT_FULL_BLOCKS` is the standard proposal; the UI loads it, lets the
user edit prose, and sends it back at render time.

Verified against the LA proposal: rack $15 → volume −10% → $13.50 → broker+partner −15%
→ $11.48; platform fee $5,000 → $4,250; implementation $8,000 → $6,800; Year-1 $79,930.
"""

from __future__ import annotations

from datetime import date
from decimal import ROUND_HALF_UP, Decimal
from typing import Literal, Optional

from pydantic import BaseModel, Field

from .deal_pricing import Block


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

# Block kinds that are rendered from computed pricing (not editable as free text).
COMPUTED_KINDS = {"cover", "t_pepm", "t_costs", "hr_rate", "t_savings", "t_jurisdiction", "t_roi", "sign", "disclaimer"}

def _b(id, kind, text="", items=None, new_page=False) -> dict:
    return {"id": id, "kind": kind, "text": text, "items": items or [], "new_page": new_page}


DEFAULT_FULL_BLOCKS: list[dict] = [
    _b("cover", "cover"),
    # Executive Summary + Investment
    _b("exec_h", "h2", "Executive Summary", new_page=True),
    _b("exec_callout", "callout",
       "Matcha is a compliance, employee relations, and workforce risk platform built for organizations that carry "
       "heavy regulatory and funding obligations on lean administrative budgets. Your compliance and HR team stops "
       "manually checking regulatory pages and opens one dashboard. Every requirement that applies to your workforce "
       "is monitored continuously. When something changes, they get an alert with severity, which team is affected, "
       "and what action to take."),
    _b("exec_p1", "p",
       "From employment law and local ordinances to data privacy, ER investigations, pre-termination risk scoring, "
       "and intelligent policy documents, Matcha consolidates fragmented HR operations into a single platform. The "
       "system is configured during implementation with the categories that apply to your operation, alongside your "
       "core labor obligations: minimum wage, local wage ordinances, meal and rest breaks, paid sick leave, and "
       "workers' compensation."),
    _b("exec_p2", "p",
       "When your team has a compliance question, they type it into the system, and it walks through the jurisdiction "
       "hierarchy, identifies which level of law governs, cites the statutes, and shows the penalty range and enforcing "
       "agency. Sourced from government databases with citation links and verification timestamps, not generated from "
       "thin air."),
    _b("exec_p3", "p",
       "What your team owns after go-live: the system. We build it during implementation, then hand it off. Your admins "
       "create onboarding cohorts, modify templates, run compliance scans. The CSM stays assigned, but the platform runs "
       "independently. You're not paying for a service — you're buying infrastructure."),
    _b("inv_h", "h2", "Investment Summary"),
    _b("inv_p", "p",
       "Matcha is priced per employee, per month (PEPM) — one rate that covers full platform access for every person on "
       "your team. Below is exactly how your rate is built, with no hidden steps."),
    _b("inv_s1", "h3", "Step 1 — How your per-employee rate is built"),
    _b("t_pepm", "t_pepm"),
    _b("inv_s2", "h3", "Step 2 — What that costs per year"),
    _b("t_costs", "t_costs"),
    _b("inv_note", "note",
       "All rates locked for the initial 12-month term. Implementation & Configuration is a one-time fee; subsequent "
       "years require only the annual recurring cost."),
    _b("hr_h", "h3", "HR Advisory Rate Card"),
    _b("hr_note", "note",
       "Basic HR Advisory (1 session/month, 45 min each) is included with your Partner Program subscription. Additional "
       "Consulting Services are available at the rates below."),
    _b("hr_rate", "hr_rate"),
    # Savings + Jurisdiction
    _b("sav_h", "h3", "Your Savings — Standard vs. Your Price", new_page=True),
    _b("sav_note", "note", "The table below compares the full standard list price to your final price, line by line."),
    _b("t_savings", "t_savings"),
    _b("sav_n1", "note", "Volume Discount (10% off PEPM) — Applied automatically for organizations with 500 or more employees."),
    _b("sav_n2", "note", "Broker Pricing (10% off) — Applied when purchasing through an authorized Matcha broker partner."),
    _b("sav_n3", "note",
       "Partner Program (additional 5% off) — Requires quarterly business reviews, anonymized benchmarking participation, "
       "logo rights, one public platform review within 90 days of go-live, and annual prepayment or 2-year term commitment."),
    _b("jur_h", "h3", "Jurisdiction Fee Schedule"),
    _b("jur_note", "note",
       "A Jurisdiction is any U.S. state, city, county, or municipality in which Client has employees and which imposes "
       "distinct compliance obligations. Local city/county ordinances are configured within their parent state jurisdiction "
       "at no additional charge; a separate state would be scoped as an additional Jurisdiction."),
    _b("t_jurisdiction", "t_jurisdiction"),
    # Platform Capabilities
    _b("cap_h", "h2", "Platform Capabilities", new_page=True),
    _b("cap_cl", "h3", "Compliance & Legal"),
    _b("cap_ce_h", "h4", "Compliance Engine"),
    _b("cap_ce_p", "p",
       "Agentic jurisdiction research across federal, state, and local levels. Multi-location and multi-site support with "
       "preemption rule analysis. The engine continuously tracks employment law together with applicable city and county "
       "ordinances — minimum-wage indexing, paid-sick-leave ordinances, fair-workweek rules, meal and rest break "
       "requirements, and background-check and mandated-reporter obligations. When a jurisdiction raises its minimum wage or "
       "a new ordinance changes scheduling or sick-leave accrual, the engine surfaces the change mapped to the affected staff "
       "before it becomes a back-pay liability."),
    _b("cap_ph_h", "h4", "Policies & Handbooks"),
    _b("cap_ph_p", "p",
       "Intelligent policy documents tailored to specific jurisdictions and program environments. Electronic signature "
       "collection with audit trails. Auto-research fills jurisdiction-specific topics during handbook creation — data-privacy "
       "acknowledgments, code-of-conduct policies, mandated-reporter policies, and jurisdiction-specific wage, leave, and "
       "harassment-prevention policies. When a new site comes online or a requirement updates, the handbook auto-updates the "
       "affected sections and triggers bulk re-acknowledgment for impacted staff."),
    _b("cap_lt_h", "h4", "Legislative Tracker"),
    _b("cap_lt_p", "p",
       "Intelligent monitoring of regulatory changes across jurisdictions with pattern detection for coordinated legislative "
       "activity — real-time alerts on minimum-wage changes, paid-sick-leave and fair-workweek updates, and new requirements "
       "affecting your workforce. When a jurisdiction advances an ordinance governing scheduling, wage, or worker protections, "
       "your HR and finance teams receive an immediate alert mapped to the affected staff."),
    _b("cap_ra_h", "h4", "Enterprise Risk Assessment & Quantitative Analytics"),
    _b("cap_ra_p", "p",
       "Multi-method organizational risk modeling that translates abstract HR metrics into tangible financial exposure, with "
       "three analytical workspaces (Overview, Analytics, and Quantitative)."),
    _b("cap_ra_b", "bullets", items=[
        "5-Dimension Live Risk Scoring: Continuous evaluation across compliance, incidents, ER cases, workforce, and legislative metrics, with 4-week trend lines and real-time delta tracking.",
        "Cost of Risk Calculation: Translates risk scores into estimated dollar exposure (wage-and-hour back pay, meal/rest-break penalties, data-privacy fines, lapsed-credential penalties, ER litigation defense, OSHA penalties).",
        "NAICS Dynamic Calibration: Cost estimates calibrated using your NAICS code against public federal enforcement data (DOL WHD, OSHA, EEOC).",
        "Quantitative & Tail Risk Analysis: Monte Carlo simulations across 10,000 iterations producing probability distributions of annual loss exposure.",
        "Peer & Cohort Intelligence: NAICS-benchmarked peer comparisons and cohort heat maps across departments, sites, and tenure.",
        "Separation & Pre-Termination Risk: Every involuntary termination is scored and factored into your overall organizational exposure.",
        "Executive Reporting & Action Items: AI-generated narrative reports, prioritized recommendations, and an Action Items tracker.",
    ]),
    _b("cap_ra_p2", "p",
       "This provides a defensible, board-ready loss-probability range for EPLI renewal discussions and lets your finance team "
       "set litigation reserves based on rigorous statistical modeling rather than gut instinct."),
    _b("cap_ir_h", "h3", "Investigations & Risk", new_page=True),
    _b("cap_inc_h", "h4", "Incident Reports"),
    _b("cap_inc_p", "p",
       "Intelligent safety and behavioral incident reporting. OSHA 300 and 300A log generation with CSV export. Anonymous "
       "reporting support. Each incident record automatically evaluates OSHA 300 recordability, and trend analytics surface "
       "whether incidents cluster around a specific site, shift, or program — enabling targeted safety-protocol improvements "
       "before an incident escalates to a workers' comp claim, an OSHA citation, or a funder report."),
    _b("cap_er_h", "h4", "ER Copilot"),
    _b("cap_er_p", "p",
       "Employment relations case management that acts as an active guide and a “second set of eyes” throughout complex "
       "investigations. Powered by AI-driven document analysis, it constructs timelines, flags discrepancies, and instantly "
       "identifies specific policy violations while surfacing relevant jurisdictional laws. When a case requires outside "
       "counsel or a litigation hold, secure encrypted PDF export delivers a complete, date-stamped record attorneys can "
       "immediately use."),
    _b("cap_ada_h", "h4", "ADA Accommodations"),
    _b("cap_ada_p", "p",
       "Interactive process workflow management with intelligent accommodation suggestions, undue hardship assessment, and job "
       "function analysis. The platform's job function analysis integrates the real physical and operational requirements of "
       "each role to identify feasible modifications — producing documentation that satisfies both EEOC and state-law standards "
       "simultaneously."),
    _b("cap_pt_h", "h4", "Pre-Termination Intelligence"),
    _b("cap_pt_p", "p",
       "9-dimension agentic risk assessment scanning legal, compliance, and organizational factors before separation decisions, "
       "with an AI-generated narrative memo suitable for counsel review. The system flags when a proposed termination involves a "
       "staff member who recently raised a safety concern, filed a complaint, requested accommodation, or engaged in protected "
       "concerted activity — categories that trigger retaliation protection."),
    _b("cap_wf_h", "h3", "Workforce Management", new_page=True),
    _b("cap_dir_h", "h4", "Employee Directory & Bulk Import"),
    _b("cap_dir_p", "p",
       "Centralized employee records with CSV bulk upload, batch creation, and Google Workspace and Slack account provisioning "
       "for new hires."),
    _b("cap_onb_h", "h4", "Onboarding"),
    _b("cap_onb_p", "p",
       "Task-based onboarding templates organized by category, supporting role-specific workflows — including background-check "
       "verification, required training, and confidentiality acknowledgments. Progress analytics with funnel metrics, bottleneck "
       "identification, and completion tracking."),
    _b("cap_dash_h", "h4", "Compliance & Operations Dashboard"),
    _b("cap_dash_p", "p",
       "A centralized, real-time view of your team's status. At a glance, monitor upcoming regulatory changes affecting your "
       "sites, track when an employee's leave of absence is ending, and review outstanding incident reports or ER Copilot action "
       "items. A dual-alert system pushes proactive notifications to your dashboard and straight to your email."),
    _b("cap_lic_h", "h4", "Automated License & Training Tracking"),
    _b("cap_lic_p", "p",
       "A dedicated tracking engine for employee licenses, certifications, and mandatory compliance training. Matcha monitors "
       "every expiry date and acts as an early-warning system: as a credential approaches expiration, it emails the staff member "
       "and their manager with a secure upload link, sends automated follow-ups, and alerts compliance personnel if a credential "
       "lapses."),
    _b("cap_mw_h", "h3", "Agentic Document Workspace (Matcha Work)"),
    _b("cap_mw_p", "p",
       "A full AI-powered workspace for creating, researching, and collaborating on HR and compliance documents — an agentic "
       "system that browses the web, extracts structured data, queries your internal records, and produces publication-ready "
       "deliverables."),
    _b("cap_mw_dg_h", "h4", "Document Generation"),
    _b("cap_mw_dg_p", "p",
       "Create performance reviews, handbooks, onboarding plans, policies, offer letters, board presentations, and reporting "
       "narratives from conversational prompts. Iterative drafting with threading. Export to PDF, DOCX, or Markdown."),
    _b("cap_mw_cd_h", "h4", "Chat with Your Data"),
    _b("cap_mw_cd_p", "p",
       "Query your live employee records, incident logs, compliance requirements, ER cases, and policy documents directly. Ask "
       "questions like “which staff have background checks or licenses expiring in the next 90 days?” and get immediate, "
       "sourced answers."),
    _b("cap_mw_cr_h", "h4", "Chain of Reasoning Compliance Querying"),
    _b("cap_mw_cr_p", "p",
       "Multi-step compliance analysis that walks through regulatory logic step by step — citing sources, applying preemption "
       "rules, and surfacing gaps — before returning a final answer. Monthly usage credits included."),
    # Implementation & Security
    _b("impl_h", "h2", "Implementation Timeline", new_page=True),
    _b("impl_p", "p", "Total duration: 7–8 weeks. Your dedicated Customer Success Manager guides every phase."),
    _b("impl_b", "bullets", items=[
        "Discovery & Gap Analysis (Weeks 1–2): Organizational mapping, HRIS audit, site inventory, regulatory gap analysis of wage and leave coverage, background-check programs, licensure tracking, and data-confidentiality practices.",
        "Configuration & Templating (Weeks 3–4): Jurisdiction setup, compliance baseline scan, role-specific onboarding templates, credential and license expiration workflows, handbook and policy document ingestion.",
        "Data Migration & Manual Run (Weeks 5–6): Employee data import, training-record migration, first onboarding cohort run manually to validate completeness.",
        "UAT & Automation (Week 7): Admin training, user acceptance testing, convert validated manual workflows to automated pipelines.",
        "Go-Live (Week 8): Production cutover, CSM handoff, post-launch monitoring.",
    ]),
    _b("sec_h", "h3", "Security & Infrastructure"),
    _b("sec_b", "bullets", items=[
        "SSO / SAML 2.0 — Enterprise single sign-on compatible with Okta, Azure AD, OneLogin, and any SAML-compliant identity provider.",
        "Role-Based Access — Granular controls across admin, HR, supervisor, and employee roles, with department and site-scoped visibility.",
        "Uptime — 99.5% target platform availability with automated health monitoring and incident alerting.",
        "Data Security — All data encrypted in transit (TLS 1.2+) and at rest (AES-256). AWS hosting with US-based data residency.",
        "Data Retention — Full data export available at any time. Data deleted within 30 days of contract termination upon written request.",
    ]),
    # Contract Terms
    _b("terms_h", "h2", "Contract Terms", new_page=True),
    _b("terms_b", "bullets", items=[
        "Initial Term — 12 months from go-live date.",
        "Auto-Renewal — Automatic 12-month renewal periods.",
        "Opt-Out Notice — 60-day written notice required before any renewal period.",
        "Employee True-Up — Quarterly adjustment based on active employee headcount.",
        "Matcha Work Credits — Monthly credits included.",
        "Dedicated CSM — Assigned at contract signing through go-live and beyond.",
        "Value Validation — 90-day post-go-live review to confirm platform adoption and ROI.",
    ]),
    # ROI
    _b("roi_h", "h2", "Return on Investment", new_page=True),
    _b("roi_intro", "p",
       "Organizations in regulated, multi-site environments carry a disproportionately high compliance burden relative to their "
       "administrative budgets — and a disproportionately high consequence when something goes wrong. A single wage-and-hour "
       "class action can run well into six figures in back pay and penalties before defense costs. A retaliation or "
       "wrongful-termination claim can generate $150,000+ in defense costs. The hard savings below reflect what the platform "
       "replaces. The risk-reduction value reflects what it prevents."),
    _b("t_roi", "t_roi"),
    _b("sup_h", "h2", "Dedicated Support"),
    _b("sup_b", "bullets", items=[
        "Customer Success Manager assigned at contract signing through go-live and beyond.",
        "Admin and manager training sessions included in implementation.",
        "Ongoing CSM check-ins post go-live.",
        "Platform support for configuration changes, new site rollouts, and feature adoption.",
    ]),
    _b("sign", "sign"),
    _b("disclaimer", "disclaimer"),
]


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
    broker_pct: int = Field(default=10, ge=0, le=100)
    partner: bool = False
    partner_pct: int = Field(default=5, ge=0, le=100)

    roi_hard_savings: int = Field(default=DEFAULT_ROI_HARD_SAVINGS, ge=0, le=100_000_000)
    roi_risk_reduction: int = Field(default=DEFAULT_ROI_RISK_REDUCTION, ge=0, le=100_000_000)

    # Editable document. None → DEFAULT_FULL_BLOCKS.
    blocks: Optional[list[Block]] = None

    def resolved_blocks(self) -> list[Block]:
        return self.blocks if self.blocks is not None else [Block(**b) for b in DEFAULT_FULL_BLOCKS]


class FullQuote(BaseModel):
    headcount: int
    rack_pepm: float
    volume_applied: bool
    volume_pepm_cut: float
    subtotal_pepm: float
    bp_rate_pct: int
    bp_pepm_cut: float
    your_pepm: float
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
    pepm_save: float
    annual_employee_save: int
    platform_save: int
    recurring_save: int
    implementation_save: int
    year1_save: int
    juris_tier: str
    juris_fee: int
    jurisdictions_extra: int
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

    bp_rate = (inp.broker_pct / 100 if inp.broker else 0.0) + (inp.partner_pct / 100 if inp.partner else 0.0)
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
    payback = max(1, -(-year1_your * 12 // total_value)) if total_value else 0

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
        jurisdictions_extra=inp.jurisdictions_extra,
        roi_hard_savings=inp.roi_hard_savings,
        roi_risk_reduction=inp.roi_risk_reduction,
        roi_total_value=total_value,
        roi_net_year1=net_y1,
        roi_net_year2=net_y2,
        roi_net_3yr=net_3yr,
        roi_multiple=multiple,
        roi_payback_month=int(payback),
    )
