import html
import logging
import mimetypes
import base64
import secrets
from datetime import timedelta, timezone
from datetime import datetime as dt
from io import BytesIO
from typing import List
from urllib.parse import quote
from uuid import UUID

from fastapi import APIRouter, HTTPException, Depends, File, UploadFile, Request
from fastapi.responses import StreamingResponse

from ...database import get_connection
from ..models.offer_letter import (
    OfferGuidanceRequest,
    OfferGuidanceResponse,
    OfferLetter,
    OfferLetterCreate,
    OfferLetterUpdate,
    CandidateOfferView,
    SendRangeRequest,
    CandidateRangeSubmit,
    RangeNegotiateResult,
    ReNegotiateRequest,
)
from ..dependencies import require_admin_or_client, get_client_company_id, require_feature
from ...core.models.auth import CurrentUser
from ...core.services.storage import get_storage
from ...core.services.email import EmailService
from ...config import get_settings

logger = logging.getLogger(__name__)

router = APIRouter()
# Public (no-auth) router for candidate magic-link endpoints
candidate_router = APIRouter()

# Explicit allowlist of columns that can be updated via PATCH
ALLOWED_UPDATE_COLUMNS = {
    "candidate_name", "position_title", "company_name", "status",
    "salary", "bonus", "stock_options", "start_date", "employment_type",
    "location", "benefits", "manager_name", "manager_title", "expiration_date",
    "benefits_medical", "benefits_medical_coverage", "benefits_medical_waiting_days",
    "benefits_dental", "benefits_vision", "benefits_401k", "benefits_401k_match",
    "benefits_wellness", "benefits_pto_vacation", "benefits_pto_sick",
    "benefits_holidays", "benefits_other",
    "contingency_background_check", "contingency_credit_check", "contingency_drug_screening",
    "salary_range_min", "salary_range_max", "candidate_email", "max_negotiation_rounds",
}

ROLE_BASE_RANGES = {
    "software_engineering": (130_000, 205_000),
    "data_analytics": (95_000, 155_000),
    "product_management": (120_000, 195_000),
    "design": (95_000, 165_000),
    "sales": (85_000, 150_000),
    "marketing": (90_000, 150_000),
    "operations": (90_000, 155_000),
    "human_resources": (95_000, 160_000),
    "finance": (100_000, 170_000),
    "customer_success": (85_000, 145_000),
    "general_professional": (90_000, 145_000),
}

ROLE_KEYWORDS = {
    "software_engineering": ("software", "engineer", "developer", "backend", "frontend", "full stack", "sre", "devops"),
    "data_analytics": ("data", "analytics", "analyst", "bi", "machine learning", "ml", "scientist"),
    "product_management": ("product manager", "product owner"),
    "design": ("designer", "ux", "ui", "product design"),
    "sales": ("sales", "account executive", "business development representative", "sales development representative", "partnership"),
    "marketing": ("marketing", "growth", "content", "demand gen"),
    "operations": ("operations", "ops", "program manager", "project manager"),
    "human_resources": ("hr", "human resources", "people ops", "talent"),
    "finance": ("finance", "accounting", "controller", "fp&a"),
    "customer_success": ("customer success", "customer support", "support", "implementation"),
}

ROLE_BONUS_TARGETS = {
    "software_engineering": (8, 15),
    "data_analytics": (8, 15),
    "product_management": (10, 20),
    "design": (8, 15),
    "sales": (20, 45),
    "marketing": (8, 18),
    "operations": (8, 15),
    "human_resources": (8, 15),
    "finance": (10, 20),
    "customer_success": (8, 18),
    "general_professional": (8, 15),
}

ROLE_EQUITY_GUIDANCE = {
    "software_engineering": "Commonly 0.02%-0.10% equity depending on seniority and company stage.",
    "data_analytics": "Commonly 0.01%-0.06% equity for IC and analytics leadership tracks.",
    "product_management": "Commonly 0.02%-0.10% equity; higher at smaller growth-stage companies.",
    "design": "Commonly 0.01%-0.07% equity depending on scope and level.",
    "sales": "Equity is often lighter than engineering/product; prioritize cash + variable comp clarity.",
    "marketing": "Typically 0.01%-0.05% equity, with higher grants for growth leadership roles.",
    "operations": "Typically 0.01%-0.05% equity for senior operations ownership roles.",
    "human_resources": "Typically 0.01%-0.05% equity, often weighted toward cash compensation.",
    "finance": "Typically 0.01%-0.06% equity for strategic finance and leadership paths.",
    "customer_success": "Typically 0.01%-0.05% equity for post-sales leadership or strategic ownership.",
    "general_professional": "Use a balanced cash-focused package with selective long-term equity grants.",
}

CITY_COST_MULTIPLIERS = {
    "Atlanta": 1.00,
    "Austin": 1.03,
    "Boston": 1.16,
    "Chicago": 1.08,
    "Dallas": 1.00,
    "Denver": 1.04,
    "Los Angeles": 1.15,
    "Miami": 1.04,
    "New York City": 1.27,
    "Philadelphia": 1.05,
    "Phoenix": 0.97,
    "San Diego": 1.10,
    "San Francisco": 1.33,
    "San Jose": 1.30,
    "Seattle": 1.18,
    "Salt Lake City": 0.98,
    "Washington": 1.14,
}

CITY_ALIASES = {
    "nyc": "New York City",
    "new york": "New York City",
    "new york city": "New York City",
    "sf": "San Francisco",
    "san fran": "San Francisco",
    "la": "Los Angeles",
    "washington dc": "Washington",
    "washington d.c.": "Washington",
    "sfo": "San Francisco",
}

EMPLOYMENT_TYPE_MULTIPLIERS = {
    "full-time exempt": 1.00,
    "full-time hourly": 1.00,
    "part-time hourly": 0.55,
    "contract": 1.08,
    "internship": 0.45,
}


def _normalize_city(city: str) -> str:
    value = " ".join(city.strip().split())
    if not value:
        return ""
    lowered = value.lower()
    if lowered in CITY_ALIASES:
        return CITY_ALIASES[lowered]
    return " ".join(part.capitalize() for part in value.split(" "))


def _normalize_state(state: str | None) -> str | None:
    if not state:
        return None
    value = state.strip()
    if not value:
        return None
    return value.upper() if len(value) <= 3 else value.title()


def _infer_role_family(role_title: str) -> str:
    lowered = role_title.lower()
    for family, keywords in ROLE_KEYWORDS.items():
        if any(keyword in lowered for keyword in keywords):
            return family
    return "general_professional"


def _experience_multiplier(years_experience: int) -> float:
    # Keeps guidance conservative at low tenure and progressively raises comp bands.
    return max(0.82, min(1.45, 0.82 + (years_experience * 0.04)))


def _employment_type_multiplier(employment_type: str | None) -> float:
    if not employment_type:
        return 1.0
    return EMPLOYMENT_TYPE_MULTIPLIERS.get(employment_type.strip().lower(), 1.0)


def _round_to_thousand(value: float) -> int:
    return int(round(value / 1000.0) * 1000)


@router.get("", response_model=List[OfferLetter])
async def list_offer_letters(
    current_user: CurrentUser = Depends(require_admin_or_client),
):
    """List offer letters scoped to the user's company."""
    company_id = await get_client_company_id(current_user)
    if company_id is None:
        return []
    is_admin = current_user.role == "admin"
    async with get_connection() as conn:
        if is_admin:
            rows = await conn.fetch(
                """
                SELECT * FROM offer_letters
                WHERE (company_id = $1 OR company_id IS NULL)
                ORDER BY created_at DESC
                """,
                company_id,
            )
        else:
            rows = await conn.fetch(
                """
                SELECT * FROM offer_letters
                WHERE company_id = $1
                ORDER BY created_at DESC
                """,
                company_id,
            )
        return [OfferLetter(**dict(row)) for row in rows]


@router.post("", response_model=OfferLetter)
async def create_offer_letter(
    offer: OfferLetterCreate,
    current_user: CurrentUser = Depends(require_admin_or_client),
):
    """Create a new offer letter draft."""
    company_id = await get_client_company_id(current_user)
    if company_id is None:
        raise HTTPException(status_code=400, detail="No company found")
    async with get_connection() as conn:
        # Look up company name from companies table (authoritative source)
        company_name = await conn.fetchval(
            "SELECT name FROM companies WHERE id = $1", company_id
        )
        row = await conn.fetchrow(
            """
            INSERT INTO offer_letters (
                candidate_name, position_title, company_name, company_id,
                salary, bonus,
                stock_options, start_date, employment_type, location, benefits,
                manager_name, manager_title, expiration_date,
                benefits_medical, benefits_medical_coverage, benefits_medical_waiting_days,
                benefits_dental, benefits_vision, benefits_401k, benefits_401k_match,
                benefits_wellness, benefits_pto_vacation, benefits_pto_sick,
                benefits_holidays, benefits_other,
                contingency_background_check, contingency_credit_check, contingency_drug_screening,
                company_logo_url,
                salary_range_min, salary_range_max, candidate_email, max_negotiation_rounds
            )
            VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9, $10, $11, $12, $13, $14,
                    $15, $16, $17, $18, $19, $20, $21, $22, $23, $24, $25, $26,
                    $27, $28, $29, $30,
                    $31, $32, $33, $34)
            RETURNING *
            """,
            offer.candidate_name,
            offer.position_title,
            company_name,
            company_id,
            offer.salary,
            offer.bonus,
            offer.stock_options,
            offer.start_date,
            offer.employment_type,
            offer.location,
            offer.benefits,
            offer.manager_name,
            offer.manager_title,
            offer.expiration_date,
            offer.benefits_medical,
            offer.benefits_medical_coverage,
            offer.benefits_medical_waiting_days,
            offer.benefits_dental,
            offer.benefits_vision,
            offer.benefits_401k,
            offer.benefits_401k_match,
            offer.benefits_wellness,
            offer.benefits_pto_vacation,
            offer.benefits_pto_sick,
            offer.benefits_holidays,
            offer.benefits_other,
            offer.contingency_background_check,
            offer.contingency_credit_check,
            offer.contingency_drug_screening,
            offer.company_logo_url,
            offer.salary_range_min,
            offer.salary_range_max,
            offer.candidate_email,
            offer.max_negotiation_rounds,
        )
        return OfferLetter(**dict(row))


@router.post(
    "/plus/recommendation",
    response_model=OfferGuidanceResponse,
    dependencies=[Depends(require_feature("offer_letters_plus")), Depends(require_admin_or_client)],
)
async def get_offer_package_recommendation(
    payload: OfferGuidanceRequest,
):
    """Generate a compensation recommendation using role, location, and experience heuristics."""
    normalized_city = _normalize_city(payload.city)
    normalized_state = _normalize_state(payload.state)
    role_family = _infer_role_family(payload.role_title)
    role_known = role_family != "general_professional"
    city_known = normalized_city in CITY_COST_MULTIPLIERS

    city_multiplier = CITY_COST_MULTIPLIERS.get(normalized_city, 1.0)
    exp_multiplier = _experience_multiplier(payload.years_experience)
    employment_multiplier = _employment_type_multiplier(payload.employment_type)

    base_low, base_high = ROLE_BASE_RANGES.get(
        role_family,
        ROLE_BASE_RANGES["general_professional"],
    )

    salary_low = _round_to_thousand(base_low * city_multiplier * exp_multiplier * employment_multiplier)
    salary_high = _round_to_thousand(base_high * city_multiplier * exp_multiplier * employment_multiplier)
    if salary_high < salary_low:
        salary_high = salary_low
    salary_mid = _round_to_thousand((salary_low + salary_high) / 2.0)

    bonus_low, bonus_high = ROLE_BONUS_TARGETS.get(
        role_family,
        ROLE_BONUS_TARGETS["general_professional"],
    )
    if payload.years_experience >= 10:
        bonus_low += 2
        bonus_high += 3

    normalized_employment_type = (payload.employment_type or "").strip().lower()
    if normalized_employment_type in {"part-time hourly", "internship"}:
        bonus_low = 0
        bonus_high = max(5, bonus_high // 2)

    equity_guidance = ROLE_EQUITY_GUIDANCE.get(
        role_family,
        ROLE_EQUITY_GUIDANCE["general_professional"],
    )
    if normalized_employment_type in {"part-time hourly", "internship"}:
        equity_guidance = "Equity is uncommon for this employment type; focus on hourly/term cash terms."

    confidence = 0.70
    if role_known:
        confidence += 0.12
    if city_known:
        confidence += 0.10
    if normalized_state:
        confidence += 0.03
    confidence = min(0.95, round(confidence, 2))

    rationale = [
        f"Role family inferred as '{role_family.replace('_', ' ')}' from title '{payload.role_title}'.",
        f"Applied a {city_multiplier:.2f} location multiplier for {normalized_city or payload.city}.",
        f"Applied an experience multiplier of {exp_multiplier:.2f} for {payload.years_experience} years.",
    ]
    if payload.employment_type:
        rationale.append(
            f"Applied an employment-type multiplier of {employment_multiplier:.2f} for '{payload.employment_type}'."
        )
    if not city_known:
        rationale.append("City not in curated metro table; fallback national location factor was used.")

    return OfferGuidanceResponse(
        role_family=role_family,
        normalized_city=normalized_city or payload.city.strip(),
        normalized_state=normalized_state,
        salary_low=salary_low,
        salary_mid=salary_mid,
        salary_high=salary_high,
        bonus_target_pct_low=bonus_low,
        bonus_target_pct_high=bonus_high,
        equity_guidance=equity_guidance,
        confidence=confidence,
        rationale=rationale,
    )


def _match_ranges(emp_min, emp_max, cand_min, cand_max):
    overlap_low = max(emp_min, cand_min)
    overlap_high = min(emp_max, cand_max)
    if overlap_low <= overlap_high:
        midpoint = (overlap_low + overlap_high) / 2
        return "matched", round(midpoint, 2)
    elif emp_max < cand_min:
        return "no_match_low", None   # offer too low for candidate
    else:
        return "no_match_high", None  # candidate expects less than employer min


async def _send_candidate_range_email(
    candidate_email: str,
    company_name: str,
    position_title: str,
    token: str,
    negotiation_round: int,
) -> None:
    """Send magic link email to candidate for salary range submission."""
    settings = get_settings()
    email_svc = EmailService()
    if not email_svc.is_configured():
        logger.warning("[OfferLetters] Email not configured, skipping candidate range email")
        return
    frontend_url = getattr(settings, 'app_base_url', 'http://localhost:5174')
    offer_url = f"{frontend_url}/offer/{token}"
    round_text = f" (Round {negotiation_round})" if negotiation_round > 1 else ""
    subject = f"Salary Range Offer from {company_name}{round_text}"
    html_body = f"""
<html><body style="font-family: sans-serif; line-height: 1.6; color: #333; max-width: 600px; margin: 0 auto; padding: 20px;">
<h2 style="color: #16a34a;">You have a salary range offer from {company_name}</h2>
<p>You have been invited to submit your salary range for the <strong>{position_title}</strong> position at <strong>{company_name}</strong>.</p>
<p>The offer uses a blind range matching system — neither party sees the other's exact numbers. The system finds the overlap automatically.</p>
<p style="margin: 24px 0;">
  <a href="{offer_url}" style="background: #16a34a; color: white; padding: 12px 24px; text-decoration: none; border-radius: 6px; font-weight: bold;">
    View Offer &amp; Submit Your Range
  </a>
</p>
<p style="color: #666; font-size: 0.9em;">This link expires in 7 days. If you did not expect this email, you can ignore it.</p>
</body></html>"""
    await email_svc.send_email(
        to_email=candidate_email,
        to_name=None,
        subject=subject,
        html_content=html_body,
    )


async def _send_employer_result_email(
    employer_email: str,
    candidate_name: str,
    position_title: str,
    result: str,
    matched_salary: float | None,
    rounds_remaining: int,
) -> None:
    """Notify employer of candidate range submission result."""
    email_svc = EmailService()
    if not email_svc.is_configured():
        logger.warning("[OfferLetters] Email not configured, skipping employer result email")
        return
    if result == "matched":
        subject = f"Offer Accepted — {position_title}"
        body = f"<p>Great news! Your offer to <strong>{candidate_name}</strong> for <strong>{position_title}</strong> was accepted at <strong>${matched_salary:,.2f}</strong>.</p>"
    elif result == "no_match_low":
        subject = f"Salary Range Not Matched — {position_title}"
        body = f"<p>{candidate_name} submitted their range for <strong>{position_title}</strong>, but the ranges didn't overlap — your offer was below their range.</p>"
        if rounds_remaining > 0:
            body += f"<p>You have <strong>{rounds_remaining}</strong> negotiation round(s) remaining. Log in to re-negotiate.</p>"
        else:
            body += "<p>The maximum number of negotiation rounds has been reached.</p>"
    else:
        subject = f"Salary Range Not Matched — {position_title}"
        body = f"<p>{candidate_name} submitted their range for <strong>{position_title}</strong>, but the ranges didn't overlap — their expectation was below your minimum.</p>"
        if rounds_remaining > 0:
            body += f"<p>You have <strong>{rounds_remaining}</strong> negotiation round(s) remaining. Log in to re-negotiate.</p>"
        else:
            body += "<p>The maximum number of negotiation rounds has been reached.</p>"
    html_body = f"<html><body style='font-family: sans-serif; line-height: 1.6; color: #333; max-width: 600px; margin: 0 auto; padding: 20px;'>{body}</body></html>"
    await email_svc.send_email(
        to_email=employer_email,
        to_name=None,
        subject=subject,
        html_content=html_body,
    )


@router.post("/{offer_id}/send-range", response_model=OfferLetter)
async def send_range_offer(
    offer_id: UUID,
    payload: SendRangeRequest,
    current_user: CurrentUser = Depends(require_admin_or_client),
):
    """Set employer salary range and send magic link to candidate."""
    company_id = await get_client_company_id(current_user)
    if company_id is None:
        raise HTTPException(status_code=404, detail="Offer letter not found")
    is_admin = current_user.role == "admin"
    company_filter = "(company_id = $2 OR company_id IS NULL)" if is_admin else "company_id = $2"
    async with get_connection() as conn:
        row = await conn.fetchrow(
            f"SELECT * FROM offer_letters WHERE id = $1 AND {company_filter}",
            offer_id, company_id,
        )
        if not row:
            raise HTTPException(status_code=404, detail="Offer letter not found")
        offer = dict(row)
        if offer["status"] not in ("draft", "sent"):
            raise HTTPException(status_code=400, detail="Offer must be in draft or sent state")
        token = secrets.token_urlsafe(32)
        expires_at = dt.now(timezone.utc) + timedelta(days=7)
        updated = await conn.fetchrow(
            """
            UPDATE offer_letters
            SET salary_range_min = $1, salary_range_max = $2,
                candidate_email = $3, candidate_token = $4,
                candidate_token_expires_at = $5,
                status = 'sent', range_match_status = 'pending_candidate',
                negotiation_round = COALESCE(negotiation_round, 1),
                updated_at = NOW()
            WHERE id = $6
            RETURNING *
            """,
            payload.salary_range_min, payload.salary_range_max,
            payload.candidate_email, token, expires_at, offer_id,
        )
    # Send email (non-blocking)
    try:
        await _send_candidate_range_email(
            candidate_email=payload.candidate_email,
            company_name=updated["company_name"] or "",
            position_title=updated["position_title"] or "",
            token=token,
            negotiation_round=updated["negotiation_round"] or 1,
        )
    except Exception as e:
        logger.warning("[OfferLetters] Failed to send candidate range email: %s", e)
    return OfferLetter(**dict(updated))


@candidate_router.get("/candidate/{token}", response_model=CandidateOfferView)
async def get_candidate_offer(token: str):
    """Public endpoint — get offer details by candidate magic token."""
    async with get_connection() as conn:
        row = await conn.fetchrow(
            "SELECT * FROM offer_letters WHERE candidate_token = $1", token
        )
        if not row:
            raise HTTPException(status_code=404, detail="Offer not found")
        offer = dict(row)
        expires_at = offer.get("candidate_token_expires_at")
        if expires_at:
            now = dt.now(timezone.utc)
            if expires_at.tzinfo is None:
                expires_at = expires_at.replace(tzinfo=timezone.utc)
            if now > expires_at:
                raise HTTPException(status_code=410, detail="This offer link has expired")
        if not offer.get("salary_range_min") or not offer.get("salary_range_max"):
            raise HTTPException(status_code=400, detail="Offer does not have a salary range set")
        return CandidateOfferView(
            id=offer["id"],
            position_title=offer["position_title"],
            company_name=offer["company_name"],
            company_logo_url=offer.get("company_logo_url"),
            employment_type=offer.get("employment_type"),
            location=offer.get("location"),
            salary_range_min=float(offer["salary_range_min"]),
            salary_range_max=float(offer["salary_range_max"]),
            benefits_medical=offer.get("benefits_medical") or False,
            benefits_dental=offer.get("benefits_dental") or False,
            benefits_vision=offer.get("benefits_vision") or False,
            benefits_401k=offer.get("benefits_401k") or False,
            benefits_401k_match=offer.get("benefits_401k_match"),
            benefits_pto_vacation=offer.get("benefits_pto_vacation") or False,
            benefits_pto_sick=offer.get("benefits_pto_sick") or False,
            benefits_holidays=offer.get("benefits_holidays") or False,
            benefits_other=offer.get("benefits_other"),
            start_date=offer.get("start_date"),
            expiration_date=offer.get("expiration_date"),
            range_match_status=offer.get("range_match_status") or "pending_candidate",
            negotiation_round=offer.get("negotiation_round") or 1,
            max_negotiation_rounds=offer.get("max_negotiation_rounds") or 3,
            matched_salary=float(offer["matched_salary"]) if offer.get("matched_salary") else None,
        )


@candidate_router.post("/candidate/{token}/submit-range", response_model=RangeNegotiateResult)
async def submit_candidate_range(token: str, payload: CandidateRangeSubmit):
    """Public endpoint — candidate submits their desired salary range."""
    async with get_connection() as conn:
        row = await conn.fetchrow(
            "SELECT * FROM offer_letters WHERE candidate_token = $1", token
        )
        if not row:
            raise HTTPException(status_code=404, detail="Offer not found")
        offer = dict(row)
        expires_at = offer.get("candidate_token_expires_at")
        if expires_at:
            now = dt.now(timezone.utc)
            if expires_at.tzinfo is None:
                expires_at = expires_at.replace(tzinfo=timezone.utc)
            if now > expires_at:
                raise HTTPException(status_code=410, detail="This offer link has expired")
        if offer.get("range_match_status") not in ("pending_candidate", None):
            raise HTTPException(status_code=400, detail="Offer is not awaiting candidate range submission")
        result, matched_salary = _match_ranges(
            float(offer["salary_range_min"]),
            float(offer["salary_range_max"]),
            payload.range_min,
            payload.range_max,
        )
        rounds_remaining = (offer.get("max_negotiation_rounds") or 3) - (offer.get("negotiation_round") or 1)
        if result == "matched":
            await conn.execute(
                """
                UPDATE offer_letters
                SET candidate_range_min = $1, candidate_range_max = $2,
                    matched_salary = $3, range_match_status = 'matched',
                    status = 'accepted', updated_at = NOW()
                WHERE candidate_token = $4
                """,
                payload.range_min, payload.range_max, matched_salary, token,
            )
        else:
            await conn.execute(
                """
                UPDATE offer_letters
                SET candidate_range_min = $1, candidate_range_max = $2,
                    range_match_status = $3, updated_at = NOW()
                WHERE candidate_token = $4
                """,
                payload.range_min, payload.range_max, result, token,
            )
        # Look up employer email in the same connection
        employer_email = None
        company_row = await conn.fetchrow(
            "SELECT u.email FROM users u JOIN companies c ON u.id = c.owner_id WHERE c.id = $1",
            offer.get("company_id"),
        )
        if company_row:
            employer_email = company_row["email"]
    # Notify employer
    try:
        if employer_email:
            await _send_employer_result_email(
                employer_email=employer_email,
                candidate_name=offer.get("candidate_name") or "Candidate",
                position_title=offer.get("position_title") or "",
                result=result,
                matched_salary=matched_salary,
                rounds_remaining=rounds_remaining,
            )
    except Exception as e:
        logger.warning("[OfferLetters] Failed to send employer result email: %s", e)
    return RangeNegotiateResult(result=result, matched_salary=matched_salary)


@router.post("/{offer_id}/re-negotiate", response_model=OfferLetter)
async def re_negotiate_offer(
    offer_id: UUID,
    payload: ReNegotiateRequest,
    current_user: CurrentUser = Depends(require_admin_or_client),
):
    """Employer re-initiates negotiation after a no-match result."""
    company_id = await get_client_company_id(current_user)
    if company_id is None:
        raise HTTPException(status_code=404, detail="Offer letter not found")
    is_admin = current_user.role == "admin"
    company_filter = "(company_id = $2 OR company_id IS NULL)" if is_admin else "company_id = $2"
    async with get_connection() as conn:
        row = await conn.fetchrow(
            f"SELECT * FROM offer_letters WHERE id = $1 AND {company_filter}",
            offer_id, company_id,
        )
        if not row:
            raise HTTPException(status_code=404, detail="Offer letter not found")
        offer = dict(row)
        if offer.get("range_match_status") not in ("no_match_low", "no_match_high"):
            raise HTTPException(status_code=400, detail="Offer is not in a no-match state")
        current_round = offer.get("negotiation_round") or 1
        max_rounds = offer.get("max_negotiation_rounds") or 3
        if current_round >= max_rounds:
            raise HTTPException(status_code=400, detail="Maximum negotiation rounds reached")
        new_token = secrets.token_urlsafe(32)
        expires_at = dt.now(timezone.utc) + timedelta(days=7)
        new_min = payload.salary_range_min if payload.salary_range_min is not None else offer.get("salary_range_min")
        new_max = payload.salary_range_max if payload.salary_range_max is not None else offer.get("salary_range_max")
        updated = await conn.fetchrow(
            """
            UPDATE offer_letters
            SET salary_range_min = $1, salary_range_max = $2,
                candidate_range_min = NULL, candidate_range_max = NULL,
                range_match_status = 'pending_candidate',
                candidate_token = $3, candidate_token_expires_at = $4,
                negotiation_round = $5, updated_at = NOW()
            WHERE id = $6
            RETURNING *
            """,
            new_min, new_max, new_token, expires_at, current_round + 1, offer_id,
        )
    candidate_email = offer.get("candidate_email")
    if candidate_email:
        try:
            await _send_candidate_range_email(
                candidate_email=candidate_email,
                company_name=updated["company_name"] or "",
                position_title=updated["position_title"] or "",
                token=new_token,
                negotiation_round=current_round + 1,
            )
        except Exception as e:
            logger.warning("[OfferLetters] Failed to send re-negotiate email: %s", e)
    return OfferLetter(**dict(updated))


@router.get("/{offer_id}", response_model=OfferLetter)
async def get_offer_letter(
    offer_id: UUID,
    current_user: CurrentUser = Depends(require_admin_or_client),
):
    """Get details of a specific offer letter."""
    company_id = await get_client_company_id(current_user)
    if company_id is None:
        raise HTTPException(status_code=404, detail="Offer letter not found")
    is_admin = current_user.role == "admin"
    async with get_connection() as conn:
        if is_admin:
            row = await conn.fetchrow(
                "SELECT * FROM offer_letters WHERE id = $1 AND (company_id = $2 OR company_id IS NULL)",
                offer_id,
                company_id,
            )
        else:
            row = await conn.fetchrow(
                "SELECT * FROM offer_letters WHERE id = $1 AND company_id = $2",
                offer_id,
                company_id,
            )
        if not row:
            raise HTTPException(status_code=404, detail="Offer letter not found")
        return OfferLetter(**dict(row))


@router.patch("/{offer_id}", response_model=OfferLetter)
async def update_offer_letter(
    offer_id: UUID,
    update: OfferLetterUpdate,
    current_user: CurrentUser = Depends(require_admin_or_client),
):
    """Update an offer letter."""
    company_id = await get_client_company_id(current_user)
    if company_id is None:
        raise HTTPException(status_code=404, detail="Offer letter not found")
    is_admin = current_user.role == "admin"
    company_filter = "(company_id = $2 OR company_id IS NULL)" if is_admin else "company_id = $2"

    async with get_connection() as conn:
        # Check if exists and belongs to company
        exists = await conn.fetchval(
            f"SELECT 1 FROM offer_letters WHERE id = $1 AND {company_filter}",
            offer_id,
            company_id,
        )
        if not exists:
            raise HTTPException(status_code=404, detail="Offer letter not found")

        # Build query dynamically (only allow whitelisted columns)
        update_data = {
            k: v for k, v in update.dict(exclude_unset=True).items()
            if k in ALLOWED_UPDATE_COLUMNS
        }
        if not update_data:
            row = await conn.fetchrow(
                f"SELECT * FROM offer_letters WHERE id = $1 AND {company_filter}",
                offer_id,
                company_id,
            )
            return OfferLetter(**dict(row))

        set_clauses = []
        values = []
        idx = 1
        for key, value in update_data.items():
            set_clauses.append(f"{key} = ${idx}")
            values.append(value)
            idx += 1

        values.append(offer_id)
        values.append(company_id)
        where_filter = f"(company_id = ${idx + 1} OR company_id IS NULL)" if is_admin else f"company_id = ${idx + 1}"
        query = f"""
            UPDATE offer_letters
            SET {', '.join(set_clauses)}, updated_at = NOW()
            WHERE id = ${idx} AND {where_filter}
            RETURNING *
        """

        row = await conn.fetchrow(query, *values)
        return OfferLetter(**dict(row))


def _generate_benefits_text(offer: dict) -> str:
    """Generate plain English benefits text from structured data."""
    parts = []

    if offer.get("benefits_medical"):
        medical = "medical insurance"
        if offer.get("benefits_medical_coverage"):
            medical += f" (employer covers {offer['benefits_medical_coverage']}% of premiums)"
        if offer.get("benefits_medical_waiting_days") and offer["benefits_medical_waiting_days"] > 0:
            medical += f" after a {offer['benefits_medical_waiting_days']}-day waiting period"
        parts.append(medical)

    if offer.get("benefits_dental"):
        parts.append("dental insurance")

    if offer.get("benefits_vision"):
        parts.append("vision insurance")

    if offer.get("benefits_401k"):
        k401 = "401(k) retirement plan"
        if offer.get("benefits_401k_match"):
            k401 += f" with {offer['benefits_401k_match']}"
        parts.append(k401)

    if offer.get("benefits_wellness"):
        parts.append(f"wellness benefits ({offer['benefits_wellness']})")

    if offer.get("benefits_pto_vacation") or offer.get("benefits_pto_sick"):
        pto_parts = []
        if offer.get("benefits_pto_vacation"):
            pto_parts.append("vacation")
        if offer.get("benefits_pto_sick"):
            pto_parts.append("sick leave")
        parts.append(f"paid time off ({' and '.join(pto_parts)})")

    if offer.get("benefits_holidays"):
        parts.append("paid holidays")

    if offer.get("benefits_other"):
        parts.append(offer["benefits_other"])

    if not parts:
        return ""

    # Join with proper grammar
    if len(parts) == 1:
        return f"You will be eligible for {parts[0]}."
    elif len(parts) == 2:
        return f"You will be eligible for {parts[0]} and {parts[1]}."
    else:
        return f"You will be eligible for {', '.join(parts[:-1])}, and {parts[-1]}."


def _generate_contingencies_text(offer: dict) -> str:
    """Generate contingencies text for the offer letter."""
    contingencies = []
    if offer.get("contingency_background_check"):
        contingencies.append("background check")
    if offer.get("contingency_credit_check"):
        contingencies.append("credit check")
    if offer.get("contingency_drug_screening"):
        contingencies.append("drug screening")

    base = "This offer of employment is contingent upon your authorization to work in the United States, as required by federal law."

    if contingencies:
        if len(contingencies) == 1:
            contingency_list = contingencies[0]
        elif len(contingencies) == 2:
            contingency_list = f"{contingencies[0]} and {contingencies[1]}"
        else:
            contingency_list = f"{', '.join(contingencies[:-1])}, and {contingencies[-1]}"
        return f"{base} This offer is also contingent upon the successful completion of the following: {contingency_list}."

    return base


def _safe(value: str | None, default: str = "") -> str:
    """HTML-escape a string value for safe embedding in templates."""
    return html.escape(str(value)) if value else default


async def _build_logo_data_uri(logo_path: str | None) -> str | None:
    """Download logo bytes and return a data URI so PDF rendering doesn't depend on external fetches."""
    if not logo_path:
        return None

    if logo_path.startswith("data:image/"):
        return logo_path

    try:
        logo_bytes = await get_storage().download_file(logo_path)
        if not logo_bytes:
            return None
        mime_type = mimetypes.guess_type(logo_path)[0] or "image/png"
        encoded = base64.b64encode(logo_bytes).decode("ascii")
        return f"data:{mime_type};base64,{encoded}"
    except Exception:
        logger.debug("Unable to build logo data URI for %s", logo_path, exc_info=True)
        return None


def _generate_offer_letter_html(offer: dict, logo_src: str | None = None) -> str:
    """Generate HTML for the offer letter PDF."""
    # Format dates
    created_date = offer["created_at"].strftime("%B %d, %Y") if offer.get("created_at") else ""
    start_date = offer["start_date"].strftime("%B %d, %Y") if offer.get("start_date") else "TBD"
    expiration_date = offer["expiration_date"].strftime("%B %d, %Y") if offer.get("expiration_date") else None

    # Generate benefits and contingencies text (already plain text, escape for HTML)
    benefits_text = _safe(_generate_benefits_text(offer))
    contingencies_text = _safe(_generate_contingencies_text(offer))

    # Escape all user-provided fields
    company_name = _safe(offer.get("company_name"))
    candidate_name = _safe(offer.get("candidate_name"))
    position_title = _safe(offer.get("position_title"))
    manager_name = _safe(offer.get("manager_name"), "the Hiring Manager")
    manager_title = _safe(offer.get("manager_title"))
    salary = _safe(offer.get("salary"), "TBD")
    bonus = _safe(offer.get("bonus"), "N/A")
    stock_options = _safe(offer.get("stock_options"), "N/A")
    employment_type = _safe(offer.get("employment_type"), "Full-Time Exempt")
    location = _safe(offer.get("location"), "Remote")

    # Accept-by clause
    accept_by_clause = ""
    if expiration_date:
        accept_by_clause = f"""
        <p style="margin-top: 20px;">
            Please sign and return this offer by <strong>{expiration_date}</strong>.
            If the offer is not accepted by this date, it may be withdrawn.
        </p>
        """

    # Logo section — sanitize URL
    logo_html = ""
    if logo_src:
        safe_url = quote(logo_src, safe=":/?#[]@!$&'()*+,;=,%")
        logo_html = f'<img src="{safe_url}" alt="Company Logo" style="max-height: 60px; max-width: 200px;" />'

    html = f"""
    <!DOCTYPE html>
    <html>
    <head>
        <meta charset="UTF-8">
        <style>
            body {{
                font-family: Georgia, 'Times New Roman', serif;
                font-size: 12pt;
                line-height: 1.6;
                color: #1a1a1a;
                max-width: 700px;
                margin: 40px auto;
                padding: 40px;
            }}
            .header {{
                display: flex;
                justify-content: space-between;
                align-items: flex-start;
                border-bottom: 1px solid #e5e5e5;
                padding-bottom: 20px;
                margin-bottom: 30px;
            }}
            .company-name {{
                font-size: 18pt;
                font-weight: bold;
                margin-bottom: 5px;
            }}
            .subtitle {{
                font-size: 9pt;
                text-transform: uppercase;
                letter-spacing: 2px;
                color: #666;
            }}
            .date-block {{
                text-align: right;
            }}
            .date-label {{
                font-size: 9pt;
                text-transform: uppercase;
                letter-spacing: 1px;
                color: #666;
            }}
            .section-title {{
                font-size: 9pt;
                text-transform: uppercase;
                letter-spacing: 2px;
                color: #666;
                border-bottom: 1px solid #e5e5e5;
                padding-bottom: 8px;
                margin-bottom: 15px;
                margin-top: 30px;
            }}
            .terms-grid {{
                background: #f9f9f9;
                padding: 20px;
                border: 1px solid #e5e5e5;
                margin: 20px 0;
            }}
            .terms-row {{
                display: flex;
                margin-bottom: 15px;
            }}
            .terms-item {{
                flex: 1;
            }}
            .terms-label {{
                font-size: 9pt;
                text-transform: uppercase;
                color: #666;
                margin-bottom: 3px;
            }}
            .terms-value {{
                font-weight: bold;
            }}
            .signature-section {{
                margin-top: 60px;
                padding-top: 30px;
                border-top: 1px solid #e5e5e5;
                display: flex;
                justify-content: space-between;
            }}
            .signature-block {{
                width: 45%;
            }}
            .signature-line {{
                border-bottom: 1px solid #333;
                height: 40px;
                margin-bottom: 8px;
            }}
            .signature-name {{
                font-weight: bold;
            }}
            .signature-title {{
                font-size: 9pt;
                text-transform: uppercase;
                letter-spacing: 1px;
                color: #666;
            }}
            .at-will-section {{
                margin-top: 30px;
            }}
            .at-will-title {{
                font-weight: bold;
                margin-bottom: 10px;
            }}
            .at-will-text {{
                font-size: 11pt;
            }}
        </style>
    </head>
    <body>
        <div class="header">
            <div>
                {logo_html}
                <div class="company-name">{company_name}</div>
                <div class="subtitle">Official Offer of Employment</div>
            </div>
            <div class="date-block">
                <div class="date-label">Date</div>
                <div><strong>{created_date}</strong></div>
            </div>
        </div>

        <p>Dear <strong>{candidate_name}</strong>,</p>

        <p>
            We are pleased to offer you the position of <strong>{position_title}</strong>
            at <strong>{company_name}</strong>. We were very impressed with your background
            and believe your skills and experience will be a valuable addition to our team.
        </p>

        <p>
            Should you accept this offer, you will report to <strong>{manager_name}</strong>{f", {manager_title}" if offer.get('manager_title') else ""}.
        </p>

        <div class="terms-grid">
            <div class="section-title" style="margin-top: 0;">Compensation & Terms</div>
            <div class="terms-row">
                <div class="terms-item">
                    <div class="terms-label">Annual Salary</div>
                    <div class="terms-value">{salary}</div>
                </div>
                <div class="terms-item">
                    <div class="terms-label">Start Date</div>
                    <div class="terms-value">{start_date}</div>
                </div>
            </div>
            <div class="terms-row">
                <div class="terms-item">
                    <div class="terms-label">Bonus Potential</div>
                    <div class="terms-value">{bonus}</div>
                </div>
                <div class="terms-item">
                    <div class="terms-label">Equity / Options</div>
                    <div class="terms-value">{stock_options}</div>
                </div>
            </div>
            <div class="terms-row">
                <div class="terms-item">
                    <div class="terms-label">Employment Type</div>
                    <div class="terms-value">{employment_type}</div>
                </div>
                <div class="terms-item">
                    <div class="terms-label">Location</div>
                    <div class="terms-value">{location}</div>
                </div>
            </div>
        </div>

        <div class="section-title">Benefits</div>
        <p>{benefits_text if benefits_text else 'Standard company benefits package.'}</p>

        <div class="section-title">Contingencies</div>
        <p>{contingencies_text}</p>

        <div class="at-will-section">
            <div class="at-will-title">At-Will Employment</div>
            <p class="at-will-text">
                Your employment with the Company will be on an at-will basis. This means that either you or
                the Company may terminate the employment relationship at any time, with or without cause
                or notice, subject to applicable law. Nothing in this offer letter or in any other Company
                document or policy should be interpreted as creating a contract of employment for any
                definite period of time.
            </p>
        </div>

        {accept_by_clause}

        <div class="signature-section">
            <div class="signature-block">
                <div class="signature-line"></div>
                <div class="signature-name">{manager_name}</div>
                <div class="signature-title">Authorized Signature</div>
            </div>
            <div class="signature-block">
                <div class="signature-line"></div>
                <div class="signature-name">{candidate_name}</div>
                <div class="signature-title">Candidate Acceptance</div>
            </div>
        </div>
    </body>
    </html>
    """
    return html


@router.get("/{offer_id}/pdf")
async def download_offer_letter_pdf(
    offer_id: UUID,
    request: Request,
    current_user: CurrentUser = Depends(require_admin_or_client),
):
    """Generate and download offer letter as PDF."""
    company_id = await get_client_company_id(current_user)
    if company_id is None:
        raise HTTPException(status_code=404, detail="Offer letter not found")
    is_admin = current_user.role == "admin"
    async with get_connection() as conn:
        if is_admin:
            row = await conn.fetchrow(
                "SELECT * FROM offer_letters WHERE id = $1 AND (company_id = $2 OR company_id IS NULL)",
                offer_id,
                company_id,
            )
        else:
            row = await conn.fetchrow(
                "SELECT * FROM offer_letters WHERE id = $1 AND company_id = $2",
                offer_id,
                company_id,
            )
        if not row:
            raise HTTPException(status_code=404, detail="Offer letter not found")

        offer = dict(row)

    # Resolve logo to an embeddable data URI when possible so PDF rendering is reliable.
    logo_src = await _build_logo_data_uri(offer.get("company_logo_url"))
    if not logo_src and offer.get("company_logo_url"):
        raw_logo_url = str(offer["company_logo_url"])
        if raw_logo_url.startswith("/"):
            logo_src = f"{str(request.base_url).rstrip('/')}{raw_logo_url}"
        else:
            logo_src = raw_logo_url

    # Generate HTML
    html_content = _generate_offer_letter_html(offer, logo_src=logo_src)

    # Try to use weasyprint for PDF generation
    try:
        from weasyprint import HTML
        pdf_bytes = HTML(string=html_content).write_pdf()
        return StreamingResponse(
            BytesIO(pdf_bytes),
            media_type="application/pdf",
            headers={
                "Content-Disposition": f'attachment; filename="offer-letter-{(offer.get("candidate_name") or "draft").replace(" ", "-")}.pdf"'
            }
        )
    except ImportError as e:
        # WeasyPrint not installed - cannot generate PDF
        logger.error(f"WeasyPrint not installed - cannot generate PDF: {e}")
        raise HTTPException(
            status_code=500,
            detail="PDF generation not available. WeasyPrint library is not installed."
        )
    except Exception as e:
        logger.error(f"Failed to generate PDF for offer {offer_id}: {e}")
        raise HTTPException(
            status_code=500,
            detail="Failed to generate PDF. Please try again or contact support."
        )


@router.post("/{offer_id}/logo")
async def upload_offer_logo(
    offer_id: UUID,
    file: UploadFile = File(...),
    current_user: CurrentUser = Depends(require_admin_or_client),
):
    """Upload a company logo for an offer letter."""
    company_id = await get_client_company_id(current_user)
    if company_id is None:
        raise HTTPException(status_code=404, detail="Offer letter not found")

    # Validate file type
    if not file.content_type or not file.content_type.startswith("image/"):
        raise HTTPException(status_code=400, detail="Only image files are supported")

    is_admin = current_user.role == "admin"
    company_filter = "(company_id = $2 OR company_id IS NULL)" if is_admin else "company_id = $2"

    async with get_connection() as conn:
        # Check if offer exists and belongs to company
        exists = await conn.fetchval(
            f"SELECT 1 FROM offer_letters WHERE id = $1 AND {company_filter}",
            offer_id,
            company_id,
        )
        if not exists:
            raise HTTPException(status_code=404, detail="Offer letter not found")

        # Upload to storage
        storage = get_storage()
        file_bytes = await file.read()

        try:
            url = await storage.upload_file(
                file_bytes,
                file.filename or "logo.png",
                prefix="offer-logos",
                content_type=file.content_type
            )
        except Exception as e:
            logger.error(f"Failed to upload logo for offer {offer_id}: {e}")
            raise HTTPException(status_code=500, detail="Failed to upload logo. Please try again.")

        # Update offer letter with logo URL
        logo_filter = "(company_id = $3 OR company_id IS NULL)" if is_admin else "company_id = $3"
        await conn.execute(
            f"UPDATE offer_letters SET company_logo_url = $1, updated_at = NOW() WHERE id = $2 AND {logo_filter}",
            url,
            offer_id,
            company_id,
        )

        return {"url": url}
