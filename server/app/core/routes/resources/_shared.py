"""resources package — shared models/helpers/constants + router objects (L9 split)."""
import html as _html
import json as _json
import logging
import os
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel, Field

from app.database import get_connection
from app.core.models.auth import CurrentUser
from app.core.dependencies import get_optional_user
from app.matcha.dependencies import require_client, get_client_company_id
from app.core.services.redis_cache import check_rate_limit, client_ip

router = APIRouter()
logger = logging.getLogger(__name__)



# ---------------------------------------------------------------------------
# State slug mapping — URL-friendly slug -> two-letter postal code.
# Drives /resources/states/california etc. Only US states for now.
# ---------------------------------------------------------------------------

STATE_SLUGS: dict[str, dict[str, str]] = {
    "alabama": {"code": "AL", "name": "Alabama"},
    "alaska": {"code": "AK", "name": "Alaska"},
    "arizona": {"code": "AZ", "name": "Arizona"},
    "arkansas": {"code": "AR", "name": "Arkansas"},
    "california": {"code": "CA", "name": "California"},
    "colorado": {"code": "CO", "name": "Colorado"},
    "connecticut": {"code": "CT", "name": "Connecticut"},
    "delaware": {"code": "DE", "name": "Delaware"},
    "district-of-columbia": {"code": "DC", "name": "District of Columbia"},
    "florida": {"code": "FL", "name": "Florida"},
    "georgia": {"code": "GA", "name": "Georgia"},
    "hawaii": {"code": "HI", "name": "Hawaii"},
    "idaho": {"code": "ID", "name": "Idaho"},
    "illinois": {"code": "IL", "name": "Illinois"},
    "indiana": {"code": "IN", "name": "Indiana"},
    "iowa": {"code": "IA", "name": "Iowa"},
    "kansas": {"code": "KS", "name": "Kansas"},
    "kentucky": {"code": "KY", "name": "Kentucky"},
    "louisiana": {"code": "LA", "name": "Louisiana"},
    "maine": {"code": "ME", "name": "Maine"},
    "maryland": {"code": "MD", "name": "Maryland"},
    "massachusetts": {"code": "MA", "name": "Massachusetts"},
    "michigan": {"code": "MI", "name": "Michigan"},
    "minnesota": {"code": "MN", "name": "Minnesota"},
    "mississippi": {"code": "MS", "name": "Mississippi"},
    "missouri": {"code": "MO", "name": "Missouri"},
    "montana": {"code": "MT", "name": "Montana"},
    "nebraska": {"code": "NE", "name": "Nebraska"},
    "nevada": {"code": "NV", "name": "Nevada"},
    "new-hampshire": {"code": "NH", "name": "New Hampshire"},
    "new-jersey": {"code": "NJ", "name": "New Jersey"},
    "new-mexico": {"code": "NM", "name": "New Mexico"},
    "new-york": {"code": "NY", "name": "New York"},
    "north-carolina": {"code": "NC", "name": "North Carolina"},
    "north-dakota": {"code": "ND", "name": "North Dakota"},
    "ohio": {"code": "OH", "name": "Ohio"},
    "oklahoma": {"code": "OK", "name": "Oklahoma"},
    "oregon": {"code": "OR", "name": "Oregon"},
    "pennsylvania": {"code": "PA", "name": "Pennsylvania"},
    "rhode-island": {"code": "RI", "name": "Rhode Island"},
    "south-carolina": {"code": "SC", "name": "South Carolina"},
    "south-dakota": {"code": "SD", "name": "South Dakota"},
    "tennessee": {"code": "TN", "name": "Tennessee"},
    "texas": {"code": "TX", "name": "Texas"},
    "utah": {"code": "UT", "name": "Utah"},
    "vermont": {"code": "VT", "name": "Vermont"},
    "virginia": {"code": "VA", "name": "Virginia"},
    "washington": {"code": "WA", "name": "Washington"},
    "west-virginia": {"code": "WV", "name": "West Virginia"},
    "wisconsin": {"code": "WI", "name": "Wisconsin"},
    "wyoming": {"code": "WY", "name": "Wyoming"},
}



CODE_TO_SLUG = {v["code"]: k for k, v in STATE_SLUGS.items()}



# Human-readable labels for category keys we surface on state guides.
CATEGORY_LABELS: dict[str, str] = {
    "minimum_wage": "Minimum Wage",
    "overtime": "Overtime",
    "meal_breaks": "Meal & Rest Breaks",
    "sick_leave": "Paid Sick Leave",
    "paid_sick_leave": "Paid Sick Leave",
    "leave": "Leave",
    "final_pay": "Final Paycheck",
    "pay_frequency": "Pay Frequency",
    "anti_discrimination": "Anti-Discrimination",
    "scheduling_reporting": "Scheduling & Reporting",
    "workplace_safety": "Workplace Safety",
    "minor_work_permit": "Minor Work Permits",
    "tax_rate": "Tax Rates",
    "workers_comp": "Workers' Compensation",
    "posting_requirements": "Posting Requirements",
    "records_retention": "Records Retention",
    "reproductive_behavioral": "Reproductive & Behavioral Health",
    "healthcare_workforce": "Healthcare Workforce",
    "billing_integrity": "Billing Integrity",
    "clinical_safety": "Clinical Safety",
    "environmental_compliance": "Environmental Compliance",
    "corporate_integrity": "Corporate Integrity",
    "quality_reporting": "Quality Reporting",
    "state_licensing": "State Licensing",
    "pharmacy_drugs": "Pharmacy & Drugs",
    "hipaa_privacy": "HIPAA & Privacy",
    "telehealth": "Telehealth",
    "health_it": "Health IT",
    "payer_relations": "Payer Relations",
    "emergency_preparedness": "Emergency Preparedness",
    "antitrust": "Antitrust",
    "business_license": "Business Licensing",
    "marketing_comms": "Marketing & Communications",
    "reimbursement_vbc": "Reimbursement & VBC",
    "transplant_organ": "Transplant & Organ",
    "research_consent": "Research Consent",
    "cybersecurity": "Cybersecurity",
    "tumor_registry": "Tumor Registry",
    "language_access": "Language Access",
    "tax_exempt": "Tax-Exempt",
    "medical_devices": "Medical Devices",
    "environmental_safety": "Environmental Safety",
    "emerging_regulatory": "Emerging Regulatory",
    "pediatric_vulnerable": "Pediatric & Vulnerable Populations",
    "oncology_clinical_trials": "Oncology Clinical Trials",
}



# Category display priority — surfaces "what HR pros want first" at the top.
CATEGORY_PRIORITY = [
    "minimum_wage",
    "overtime",
    "meal_breaks",
    "sick_leave",
    "paid_sick_leave",
    "leave",
    "final_pay",
    "pay_frequency",
    "anti_discrimination",
    "scheduling_reporting",
    "minor_work_permit",
    "workplace_safety",
    "workers_comp",
    "posting_requirements",
    "records_retention",
    "tax_rate",
]




# ---------------------------------------------------------------------------
# Asset registry — slug -> public download path. Files live in client/public/
# and are served from the static frontend root, so download_url is absolute
# from the site root.
# ---------------------------------------------------------------------------

# Each asset has `available` — when False, the UI shows a "Notify me when
# ready" capture instead of a download button. DOCXs hosted on CloudFront
# (S3 origin), generated via scripts/generate_resource_templates.py.
# I-9 / W-4 link out to authoritative government sources (kept current
# by USCIS/IRS, public-domain).
ASSETS: dict[str, dict] = {
    "offer-letter": {"path": "https://d1ri804v59kjwh.cloudfront.net/resources/templates/c093d74d2fcc48d7b3d160c083e2773a.docx", "name": "Offer Letter", "available": True, "is_free": True},
    "pip": {"path": "https://d1ri804v59kjwh.cloudfront.net/resources/templates/2cad0579c92b4835857549c42ab59195.docx", "name": "Performance Improvement Plan", "available": True, "is_free": True},
    "termination-checklist": {"path": "https://d1ri804v59kjwh.cloudfront.net/resources/templates/62c51d1ad2534c179e4195bd15fce47f.docx", "name": "Termination Checklist", "available": True, "is_free": True},
    "interview-scorecard": {"path": "https://d1ri804v59kjwh.cloudfront.net/resources/templates/d0b6efa9cfb64530a7e34ece13ecbbec.docx", "name": "Interview Scorecard", "available": True, "is_free": True},
    "interview-guide": {"path": "https://d1ri804v59kjwh.cloudfront.net/resources/templates/2a7e7ebbd7c04e7d8ab01bcbcf72ce2c.docx", "name": "Interview Guide — What You Can & Can't Ask", "available": True, "is_free": True},
    "pto-policy": {"path": "https://d1ri804v59kjwh.cloudfront.net/resources/templates/40a74d49dbe340d9aca6c55c64382470.docx", "name": "PTO Policy Template", "available": True, "is_free": True},
    "workplace-investigation-report": {"path": "https://d1ri804v59kjwh.cloudfront.net/resources/templates/a3d51b0794074aadba31cc3624c0ebc3.docx", "name": "Workplace Investigation Report", "available": True, "is_free": False},
    "performance-review": {"path": "https://d1ri804v59kjwh.cloudfront.net/resources/templates/cf44966c6c21473f94d8ad933b12ad05.docx", "name": "Performance Review Template", "available": True, "is_free": False},
    "disciplinary-action": {"path": "https://d1ri804v59kjwh.cloudfront.net/resources/templates/1cc56d1056a14b45ac1f723edd8dff08.docx", "name": "Disciplinary Action Form", "available": True, "is_free": False},
    "remote-work-agreement": {"path": "https://d1ri804v59kjwh.cloudfront.net/resources/templates/fc9340721c1c4011b74081442c9fc809.docx", "name": "Remote Work Agreement", "available": True, "is_free": False},
    "expense-reimbursement": {"path": "https://d1ri804v59kjwh.cloudfront.net/resources/templates/b23c734a36da4089a86b5f448dd785ab.docx", "name": "Expense Reimbursement Form", "available": True, "is_free": False},
    "severance-agreement": {"path": "https://d1ri804v59kjwh.cloudfront.net/resources/templates/75854b4bc58845d4889a7dd59affc9d7.docx", "name": "Severance Agreement", "available": True, "is_free": False},
    "i9-form": {"path": "https://www.uscis.gov/sites/default/files/document/forms/i-9.pdf", "name": "Form I-9 — Employment Eligibility Verification (USCIS)", "available": True, "is_free": False},
    "w4-form": {"path": "https://www.irs.gov/pub/irs-pdf/fw4.pdf", "name": "Form W-4 — Employee's Withholding Certificate (IRS)", "available": True, "is_free": False},
}




# ---------------------------------------------------------------------------
# Upgrade — Stripe checkout to convert resources_free → Matcha IR
# ---------------------------------------------------------------------------


class UpgradeCheckoutRequest(BaseModel):
    success_url: Optional[str] = None
    cancel_url: Optional[str] = None




class UpgradeCheckoutResponse(BaseModel):
    checkout_url: str
    stripe_session_id: str




# ---------------------------------------------------------------------------
# Matcha Lite — headcount-based subscription checkout
# ---------------------------------------------------------------------------


class LiteCheckoutRequest(BaseModel):
    success_url: Optional[str] = None
    cancel_url: Optional[str] = None




class MatchaLitePricingResponse(BaseModel):
    price_per_block_cents: int
    block_size: int
    effective_price_per_block_cents: int
    sale_active: bool
    min_headcount: int
    max_headcount: int




# ---------------------------------------------------------------------------
# Matcha Lite add-ons — each its own Stripe sub on top of the base Lite sub.
# Registry (whitelist + eligibility rules): app/core/services/lite_addons.py.
# ---------------------------------------------------------------------------


class LiteAddonInfo(BaseModel):
    key: str
    name: str
    description: str
    status: str  # 'active' | 'available' | 'not_eligible'
    monthly_price_cents: Optional[int] = None
    # True when the add-on rides a self-purchased Stripe sub (cancellable
    # here); False for admin-granted flags without a sub.
    cancellable: bool = False




class LiteAddonCheckoutRequest(BaseModel):
    addon_key: str
    success_url: Optional[str] = None
    cancel_url: Optional[str] = None




async def _lite_company_context(company_id) -> dict:
    """signup_source + merged features + headcount for the add-on endpoints."""
    import json as _json

    from app.core.feature_flags import merge_company_features

    async with get_connection() as conn:
        row = await conn.fetchrow(
            """
            SELECT c.signup_source, c.enabled_features, COALESCE(chp.headcount, 0) AS headcount
            FROM companies c
            LEFT JOIN company_handbook_profiles chp ON chp.company_id = c.id
            WHERE c.id = $1
            """,
            company_id,
        )
    if not row:
        raise HTTPException(status_code=404, detail="Company not found")
    raw = row["enabled_features"]
    stored = raw if isinstance(raw, dict) else (_json.loads(raw) if raw else {})
    return {
        "signup_source": row["signup_source"],
        "features": merge_company_features(stored, row["signup_source"]),
        "headcount": int(row["headcount"]),
    }




# ---------------------------------------------------------------------------
# Upgrade Inquiry — in-app contact form for Cap → Matcha Platform upgrade.
# Records a lead_captures row + emails sales (best-effort).
# ---------------------------------------------------------------------------


class UpgradeInquiryRequest(BaseModel):
    message: Optional[str] = Field(default=None, max_length=2000)
    source: str = Field(default="ir_detail_upsell", max_length=100)




class UpgradeInquiryResponse(BaseModel):
    ok: bool




# ---------------------------------------------------------------------------
# Free → Matcha Lite upgrade request — notifies admin for manual activation.
# ---------------------------------------------------------------------------


class LiteUpgradeRequest(BaseModel):
    headcount: Optional[int] = Field(default=None, ge=1)




# ---------------------------------------------------------------------------
# Matcha Lite waitlist — fully public capture. No auth.
# ---------------------------------------------------------------------------


class LiteWaitlistRequest(BaseModel):
    email: str = Field(..., min_length=3, max_length=255)
    name: Optional[str] = Field(default=None, max_length=255)
    company_name: Optional[str] = Field(default=None, max_length=255)
    headcount: Optional[int] = Field(default=None, ge=1, le=100_000)
    note: Optional[str] = Field(default=None, max_length=1000)
    website: Optional[str] = Field(default=None)  # honeypot




class LiteWaitlistResponse(BaseModel):
    ok: bool




# ---------------------------------------------------------------------------
# Landing qualification wizard — fully public capture. No auth.
# Work email only; consumer mailboxes are rejected so sales isn't chasing
# personal addresses.
# ---------------------------------------------------------------------------

# Consumer mailbox providers. A lead from one of these isn't a company
# buying HR software, so we bounce them back to the form rather than
# recording a lead nobody will follow up on.
FREE_EMAIL_DOMAINS: frozenset[str] = frozenset({
    "gmail.com", "googlemail.com",
    "yahoo.com", "yahoo.co.uk", "yahoo.co.in", "ymail.com", "rocketmail.com",
    "hotmail.com", "hotmail.co.uk", "outlook.com", "live.com", "msn.com",
    "icloud.com", "me.com", "mac.com",
    "aol.com", "gmx.com", "gmx.net", "mail.com", "mail.ru",
    "protonmail.com", "proton.me", "pm.me",
    "yandex.com", "yandex.ru", "zoho.com",
    "fastmail.com", "hey.com", "tutanota.com", "tuta.io",
    "qq.com", "163.com", "126.com", "naver.com", "hanmail.net",
    "comcast.net", "verizon.net", "att.net", "sbcglobal.net", "cox.net",
    "btinternet.com", "orange.fr", "free.fr", "web.de", "t-online.de",
})



HEADCOUNT_RANGES = ("1-24", "25-99", "100-299", "300-999", "1000+")


LOCATION_RANGES = ("1", "2-4", "5-9", "10+")


PRIMARY_NEEDS = (
    "workplace_safety",
    "compliance",
    "employee_relations",
    "hr_operations",
    "legal_exposure",
    "not_sure",
)




class QualifyRequest(BaseModel):
    email: str = Field(..., min_length=3, max_length=255)
    name: Optional[str] = Field(default=None, max_length=255)
    company_name: Optional[str] = Field(default=None, max_length=255)
    headcount_range: str = Field(..., max_length=20)
    location_range: str = Field(..., max_length=20)
    primary_needs: list[str] = Field(default_factory=list, max_length=6)
    website: Optional[str] = Field(default=None)  # honeypot




class QualifyResponse(BaseModel):
    ok: bool




def _format_category(key: str) -> str:
    if key in CATEGORY_LABELS:
        return CATEGORY_LABELS[key]
    return key.replace("_", " ").title()




def _category_sort_key(key: str) -> tuple[int, str]:
    try:
        return (CATEGORY_PRIORITY.index(key), key)
    except ValueError:
        return (len(CATEGORY_PRIORITY) + 1, key)




class AuditFinding(BaseModel):
    severity: str  # "high" | "medium" | "low"
    category: str
    title: str
    detail: str




class AuditSubmitRequest(BaseModel):
    state_slug: Optional[str] = None
    headcount: Optional[int] = None
    industry: Optional[str] = None
    findings: list[AuditFinding] = []
    score: Optional[int] = None  # 0-100
    answered: Optional[int] = None
    total: Optional[int] = None




def _sev_color(sev: str) -> str:
    return {"high": "#c1543a", "medium": "#c19f3a", "low": "#5a8c5a"}.get(sev, "#6a737d")




def _render_audit_email(body: AuditSubmitRequest) -> str:
    state_name = ""
    if body.state_slug and body.state_slug in STATE_SLUGS:
        state_name = STATE_SLUGS[body.state_slug]["name"]
    score_str = f"{body.score}/100" if body.score is not None else "—"

    findings_html = ""
    for f in body.findings:
        color = _sev_color(f.severity)
        findings_html += f"""
        <div style="border-left:3px solid {color};padding:12px 16px;margin-bottom:12px;background:#1a1a1a;border-radius:4px;">
          <div style="display:flex;justify-content:space-between;align-items:baseline;margin-bottom:6px;">
            <strong style="color:#e4e4e7;font-size:14px;">{f.title}</strong>
            <span style="color:{color};font-size:11px;text-transform:uppercase;letter-spacing:0.05em;">{f.severity}</span>
          </div>
          <div style="color:#a1a1aa;font-size:12px;text-transform:uppercase;letter-spacing:0.05em;margin-bottom:6px;">{f.category}</div>
          <div style="color:#d4d4d8;font-size:13px;line-height:1.5;">{f.detail}</div>
        </div>
        """

    if not findings_html:
        findings_html = '<p style="color:#86efac;">No gaps flagged from your responses. Nice work.</p>'

    state_block = f"<p style='color:#a1a1aa;'>State: <strong style='color:#e4e4e7;'>{state_name}</strong></p>" if state_name else ""

    return f"""
    <div style="max-width:640px;margin:0 auto;font-family:-apple-system,system-ui,sans-serif;
                background:#0f0f0f;color:#d4d4d8;padding:32px 24px;">
      <div style="text-align:center;margin-bottom:24px;">
        <span style="font-size:22px;font-weight:600;color:#86efac;letter-spacing:0.05em;">MATCHA</span>
      </div>
      <h1 style="font-size:22px;color:#fafafa;margin:0 0 4px;">Your HR Compliance Gap Report</h1>
      <p style="color:#a1a1aa;margin:0 0 24px;">Score: <strong style="color:#fafafa;">{score_str}</strong> &middot; {len(body.findings)} gaps flagged</p>
      {state_block}

      <h2 style="font-size:16px;color:#fafafa;margin:24px 0 12px;border-bottom:1px solid #27272a;padding-bottom:8px;">Findings</h2>
      {findings_html}

      <div style="margin-top:32px;padding:20px;background:#1a1a1a;border-radius:8px;">
        <h3 style="color:#fafafa;margin:0 0 8px;font-size:15px;">Want help closing these gaps?</h3>
        <p style="color:#a1a1aa;font-size:13px;margin:0 0 12px;">
          Matcha tracks every state and local rule, generates the missing
          policies, and flags new gaps as laws change.
        </p>
        <a href="https://hey-matcha.com" style="display:inline-block;background:#86efac;color:#0f0f0f;
           padding:10px 20px;border-radius:6px;text-decoration:none;font-weight:600;font-size:13px;">
          See Matcha →
        </a>
      </div>

      <p style="color:#52525b;font-size:11px;margin-top:32px;text-align:center;">
        This report is informational only and not legal advice.
        Consult employment counsel for your specific situation.
      </p>
    </div>
    """




# Public preview: only show 1 sample title per category, and only one
# category gets a "preview value" so visitors see the format. Everything
# else is gated behind signup.
_PREVIEW_VALUE_CATEGORIES = {"minimum_wage", "overtime"}


_MAX_SAMPLE_TITLES_PER_CATEGORY = 2




# ── Resource pins ─────────────────────────────────────────────────────
# Free-tier (and any-tier) per-user favorites. Service layer in
# `core/services/resource_pins_service.py`. Auth gate is the same
# `require_client` used by every other endpoint in this file — free-tier
# users have role=client, so they can pin without an extra feature gate.


class ResourcePinBody(BaseModel):
    kind: str = Field(..., max_length=32)
    id: str = Field(..., max_length=128)

__all__ = [
    "router",
    "logger",
    "ASSETS",
    "AuditFinding",
    "AuditSubmitRequest",
    "CATEGORY_LABELS",
    "CATEGORY_PRIORITY",
    "CODE_TO_SLUG",
    "FREE_EMAIL_DOMAINS",
    "HEADCOUNT_RANGES",
    "LOCATION_RANGES",
    "LiteAddonCheckoutRequest",
    "LiteAddonInfo",
    "LiteCheckoutRequest",
    "LiteUpgradeRequest",
    "LiteWaitlistRequest",
    "LiteWaitlistResponse",
    "MatchaLitePricingResponse",
    "PRIMARY_NEEDS",
    "QualifyRequest",
    "QualifyResponse",
    "ResourcePinBody",
    "STATE_SLUGS",
    "UpgradeCheckoutRequest",
    "UpgradeCheckoutResponse",
    "UpgradeInquiryRequest",
    "UpgradeInquiryResponse",
    "_MAX_SAMPLE_TITLES_PER_CATEGORY",
    "_PREVIEW_VALUE_CATEGORIES",
    "_category_sort_key",
    "_format_category",
    "_lite_company_context",
    "_render_audit_email",
    "_sev_color",
]
