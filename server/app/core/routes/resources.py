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

ASSETS: dict[str, dict[str, str]] = {
    "offer-letter-docx": {"path": "/templates/offer-letter.docx", "name": "Offer Letter (DOCX)"},
    "offer-letter-pdf": {"path": "/templates/offer-letter.pdf", "name": "Offer Letter (PDF)"},
    "job-descriptions-library": {"path": "/templates/job-descriptions-library.docx", "name": "Job Descriptions Library"},
    "pip": {"path": "/templates/pip.docx", "name": "Performance Improvement Plan"},
    "termination-checklist": {"path": "/templates/termination-checklist.pdf", "name": "Termination Checklist"},
    "i9-w4-packet": {"path": "/templates/i9-w4-packet.pdf", "name": "I-9 / W-4 Packet"},
    "interview-scorecard": {"path": "/templates/interview-scorecard.docx", "name": "Interview Scorecard"},
    "interview-guide": {"path": "/templates/interview-guide.docx", "name": "Interview Guide — What You Can & Can't Ask"},
    "pto-policy": {"path": "/templates/pto-policy.docx", "name": "PTO Policy Template"},
    "workplace-investigation-report": {"path": "/templates/workplace-investigation-report.docx", "name": "Workplace Investigation Report"},
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

    asset = ASSETS.get(body.asset_slug)
    if not asset:
        raise HTTPException(status_code=404, detail="Unknown asset")

    async with get_connection() as conn:
        await conn.execute(
            """INSERT INTO lead_captures
               (email, name, asset_slug, source, utm_source, utm_medium, utm_campaign, ip_address)
               VALUES ($1, $2, $3, $4, $5, $6, $7, $8)""",
            body.email.lower().strip(),
            body.name.strip() if body.name else None,
            body.asset_slug,
            body.source or "resources",
            body.utm_source,
            body.utm_medium,
            body.utm_campaign,
            _client_ip(request),
        )

    logger.info("Lead capture: %s -> %s", body.email, body.asset_slug)

    return {
        "ok": True,
        "download_url": asset["path"],
        "asset_name": asset["name"],
    }


@router.get("/assets")
async def list_assets():
    """List available downloadable assets — used by the frontend Templates page."""
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


@router.get("/state-guides/{slug}")
async def get_state_guide(slug: str):
    """Return all state-level compliance requirements for a given state, grouped by category."""
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
            SELECT category, title, summary, current_value, source_url, source_name,
                   effective_date, last_verified_at, statute_citation, canonical_key
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
            "summary": r["summary"],
            "current_value": r["current_value"],
            "source_url": r["source_url"],
            "source_name": r["source_name"],
            "effective_date": r["effective_date"].isoformat() if r["effective_date"] else None,
            "last_verified": r["last_verified_at"].isoformat() if r["last_verified_at"] else None,
            "statute_citation": r["statute_citation"],
            "canonical_key": r["canonical_key"],
        })

    categories = [
        {
            "key": cat,
            "label": _format_category(cat),
            "requirements": grouped[cat],
        }
        for cat in sorted(grouped.keys(), key=_category_sort_key)
    ]

    return {
        "slug": slug,
        "code": meta["code"],
        "name": meta["name"],
        "requirement_count": sum(len(c["requirements"]) for c in categories),
        "last_verified": jurisdiction["last_verified_at"].isoformat() if jurisdiction["last_verified_at"] else None,
        "categories": categories,
    }
