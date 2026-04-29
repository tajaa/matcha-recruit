"""Resources hub — public endpoints for HR resource downloads + lead capture."""

import logging
import time
from typing import Optional

from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel, EmailStr

from ...database import get_connection


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

logger = logging.getLogger(__name__)

router = APIRouter()


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
    "offer-letter": {"path": "https://d1ri804v59kjwh.cloudfront.net/resources/templates/c093d74d2fcc48d7b3d160c083e2773a.docx", "name": "Offer Letter", "available": True},
    "pip": {"path": "https://d1ri804v59kjwh.cloudfront.net/resources/templates/2cad0579c92b4835857549c42ab59195.docx", "name": "Performance Improvement Plan", "available": True},
    "termination-checklist": {"path": "https://d1ri804v59kjwh.cloudfront.net/resources/templates/62c51d1ad2534c179e4195bd15fce47f.docx", "name": "Termination Checklist", "available": True},
    "interview-scorecard": {"path": "https://d1ri804v59kjwh.cloudfront.net/resources/templates/d0b6efa9cfb64530a7e34ece13ecbbec.docx", "name": "Interview Scorecard", "available": True},
    "interview-guide": {"path": "https://d1ri804v59kjwh.cloudfront.net/resources/templates/2a7e7ebbd7c04e7d8ab01bcbcf72ce2c.docx", "name": "Interview Guide — What You Can & Can't Ask", "available": True},
    "pto-policy": {"path": "https://d1ri804v59kjwh.cloudfront.net/resources/templates/40a74d49dbe340d9aca6c55c64382470.docx", "name": "PTO Policy Template", "available": True},
    "workplace-investigation-report": {"path": "https://d1ri804v59kjwh.cloudfront.net/resources/templates/a3d51b0794074aadba31cc3624c0ebc3.docx", "name": "Workplace Investigation Report", "available": True},
    "performance-review": {"path": "https://d1ri804v59kjwh.cloudfront.net/resources/templates/cf44966c6c21473f94d8ad933b12ad05.docx", "name": "Performance Review Template", "available": True},
    "disciplinary-action": {"path": "https://d1ri804v59kjwh.cloudfront.net/resources/templates/1cc56d1056a14b45ac1f723edd8dff08.docx", "name": "Disciplinary Action Form", "available": True},
    "remote-work-agreement": {"path": "https://d1ri804v59kjwh.cloudfront.net/resources/templates/fc9340721c1c4011b74081442c9fc809.docx", "name": "Remote Work Agreement", "available": True},
    "expense-reimbursement": {"path": "https://d1ri804v59kjwh.cloudfront.net/resources/templates/b23c734a36da4089a86b5f448dd785ab.docx", "name": "Expense Reimbursement Form", "available": True},
    "severance-agreement": {"path": "https://d1ri804v59kjwh.cloudfront.net/resources/templates/75854b4bc58845d4889a7dd59affc9d7.docx", "name": "Severance Agreement", "available": True},
    "i9-form": {"path": "https://www.uscis.gov/sites/default/files/document/forms/i-9.pdf", "name": "Form I-9 — Employment Eligibility Verification (USCIS)", "available": True},
    "w4-form": {"path": "https://www.irs.gov/pub/irs-pdf/fw4.pdf", "name": "Form W-4 — Employee's Withholding Certificate (IRS)", "available": True},
}


# ---------------------------------------------------------------------------
# In-process rate limit per IP. Mirrors newsletter.py pattern.
# ---------------------------------------------------------------------------

_LEAD_WINDOW_SECONDS = 60
_LEAD_MAX_PER_WINDOW = 15
_lead_state: dict[str, list[float]] = {}


def _rate_limited(client_ip: str) -> bool:
    now = time.monotonic()
    cutoff = now - _LEAD_WINDOW_SECONDS
    timestamps = [t for t in _lead_state.get(client_ip, []) if t >= cutoff]
    if len(timestamps) >= _LEAD_MAX_PER_WINDOW:
        _lead_state[client_ip] = timestamps
        return True
    timestamps.append(now)
    _lead_state[client_ip] = timestamps
    if len(_lead_state) > 1000:
        for ip in list(_lead_state.keys()):
            if not _lead_state[ip] or _lead_state[ip][-1] < cutoff:
                _lead_state.pop(ip, None)
    return False


def _client_ip(request: Request) -> str:
    fwd = request.headers.get("x-forwarded-for")
    if fwd:
        return fwd.split(",")[0].strip()
    return request.client.host if request.client else "unknown"


# ---------------------------------------------------------------------------
# Endpoints
# ---------------------------------------------------------------------------


class LeadCaptureRequest(BaseModel):
    email: EmailStr
    name: Optional[str] = None
    asset_slug: str
    source: Optional[str] = "resources"
    utm_source: Optional[str] = None
    utm_medium: Optional[str] = None
    utm_campaign: Optional[str] = None


@router.post("/lead-capture")
async def lead_capture(body: LeadCaptureRequest, request: Request):
    """Capture an email in exchange for a download URL.

    Single-step (no double opt-in) — these are template downloads, not
    newsletter subscriptions. Returns the public download URL on success.
    """
    if _rate_limited(_client_ip(request)):
        raise HTTPException(status_code=429, detail="Too many requests. Please wait a minute.")

    # Allow capturing a lead for any registered slug, even pseudo-slugs like
    # "job-description:bartender" used by the Job Descriptions browse page.
    asset = ASSETS.get(body.asset_slug)
    is_available = bool(asset and asset.get("available"))

    # Reject totally unknown slugs only if they don't look like a job-desc slug.
    if not asset and not body.asset_slug.startswith("job-description:"):
        raise HTTPException(status_code=404, detail="Unknown asset")

    source = body.source or ("notify_when_ready" if not is_available else "resources")

    async with get_connection() as conn:
        await conn.execute(
            """INSERT INTO lead_captures
               (email, name, asset_slug, source, utm_source, utm_medium, utm_campaign, ip_address)
               VALUES ($1, $2, $3, $4, $5, $6, $7, $8)""",
            body.email.lower().strip(),
            body.name.strip() if body.name else None,
            body.asset_slug,
            source,
            body.utm_source,
            body.utm_medium,
            body.utm_campaign,
            _client_ip(request),
        )

    logger.info("Lead capture: %s -> %s (%s)", body.email, body.asset_slug, source)

    if is_available and asset:
        return {
            "ok": True,
            "status": "download",
            "download_url": asset["path"],
            "asset_name": asset["name"],
        }
    return {
        "ok": True,
        "status": "notify",
        "asset_name": asset["name"] if asset else body.asset_slug,
    }


@router.get("/assets")
async def list_assets():
    """List downloadable assets (with `available` flag) — used by Templates page."""
    return {"assets": [{"slug": k, **v} for k, v in ASSETS.items()]}


# ---------------------------------------------------------------------------
# State Compliance Guides — public surface over jurisdictions data.
# ---------------------------------------------------------------------------


@router.get("/state-guides")
async def list_state_guides():
    """List US states with state-level compliance data available."""
    async with get_connection() as conn:
        rows = await conn.fetch(
            """
            SELECT j.state, COUNT(jr.id) AS req_count, MAX(jr.last_verified_at) AS last_verified
            FROM jurisdictions j
            LEFT JOIN jurisdiction_requirements jr ON jr.jurisdiction_id = j.id
            WHERE j.country_code = 'US' AND j.level = 'state'
            GROUP BY j.state
            HAVING COUNT(jr.id) > 0
            ORDER BY j.state
            """
        )

    out = []
    for r in rows:
        slug = CODE_TO_SLUG.get(r["state"])
        if not slug:
            continue
        meta = STATE_SLUGS[slug]
        out.append({
            "slug": slug,
            "code": meta["code"],
            "name": meta["name"],
            "requirement_count": r["req_count"],
            "last_verified": r["last_verified"].isoformat() if r["last_verified"] else None,
        })
    return {"states": out}


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
    email: Optional[EmailStr] = None
    name: Optional[str] = None
    state_slug: Optional[str] = None
    headcount: Optional[int] = None
    industry: Optional[str] = None
    findings: list[AuditFinding] = []
    score: Optional[int] = None  # 0-100
    answered: Optional[int] = None
    total: Optional[int] = None


@router.post("/audit")
async def submit_audit(body: AuditSubmitRequest, request: Request):
    """Compliance-audit submission. Captures lead + emails the gap report.

    Findings are computed client-side from a static rule set (frontend
    owns the quiz logic). This endpoint persists the submission and
    delivers an HTML email summary so the user has a copy in their inbox.
    """
    if _rate_limited(_client_ip(request)):
        raise HTTPException(status_code=429, detail="Too many requests. Please wait a minute.")

    # Persist as a lead capture so leads show up in the same table.
    if body.email:
        async with get_connection() as conn:
            await conn.execute(
                """INSERT INTO lead_captures
                   (email, name, asset_slug, source, ip_address)
                   VALUES ($1, $2, $3, $4, $5)""",
                body.email.lower().strip(),
                body.name.strip() if body.name else None,
                "compliance-audit",
                "resources_audit",
                _client_ip(request),
            )

        # Fire-and-forget email (best-effort; don't fail the request).
        try:
            from ..services.email import get_email_service
            html = _render_audit_email(body)
            await get_email_service().send_email(
                to_email=body.email,
                to_name=body.name,
                subject="Your HR Compliance Gap Report",
                html_content=html,
            )
        except Exception:
            logger.exception("Failed to send audit email to %s", body.email)

    logger.info(
        "Audit submission: %s findings=%d score=%s state=%s",
        body.email or "anonymous",
        len(body.findings),
        body.score,
        body.state_slug,
    )

    return {"ok": True, "delivered": bool(body.email)}


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


@router.get("/state-guides/{slug}")
async def get_state_guide(slug: str):
    """Public state guide — TEASER ONLY.

    Intentionally limited: returns category list with counts and a small
    number of sample requirement titles per category. Full requirement
    detail (current values, source URLs, statute citations, summaries)
    is gated behind platform signup. This preserves SEO + lead-gen value
    without giving away the proprietary jurisdiction dataset.
    """
    meta = STATE_SLUGS.get(slug)
    if not meta:
        raise HTTPException(status_code=404, detail="Unknown state")

    async with get_connection() as conn:
        jurisdiction = await conn.fetchrow(
            """
            SELECT id, last_verified_at
            FROM jurisdictions
            WHERE state = $1 AND level = 'state' AND country_code = 'US'
            LIMIT 1
            """,
            meta["code"],
        )
        if not jurisdiction:
            raise HTTPException(status_code=404, detail="No data for this state yet")

        rows = await conn.fetch(
            """
            SELECT category, title, current_value
            FROM jurisdiction_requirements
            WHERE jurisdiction_id = $1
            ORDER BY category, COALESCE(sort_order, 9999), title
            """,
            jurisdiction["id"],
        )

    grouped: dict[str, list[dict]] = {}
    for r in rows:
        cat = r["category"] or "other"
        grouped.setdefault(cat, []).append({
            "title": r["title"],
            "current_value": r["current_value"],
        })

    categories = []
    for cat in sorted(grouped.keys(), key=_category_sort_key):
        items = grouped[cat]
        sample_titles = [it["title"] for it in items[:_MAX_SAMPLE_TITLES_PER_CATEGORY]]
        # Show ONE preview value (anchor stat) only for headline categories.
        preview_value = None
        if cat in _PREVIEW_VALUE_CATEGORIES:
            for it in items:
                if it["current_value"]:
                    preview_value = it["current_value"]
                    break
        categories.append({
            "key": cat,
            "label": _format_category(cat),
            "count": len(items),
            "sample_titles": sample_titles,
            "preview_value": preview_value,
        })

    return {
        "slug": slug,
        "code": meta["code"],
        "name": meta["name"],
        "requirement_count": sum(c["count"] for c in categories),
        "category_count": len(categories),
        "last_verified": jurisdiction["last_verified_at"].isoformat() if jurisdiction["last_verified_at"] else None,
        "categories": categories,
    }
