import logging
import mimetypes
import base64
import secrets
from datetime import timedelta, timezone
from datetime import datetime as dt
from io import BytesIO
from typing import List
from uuid import UUID

from fastapi import APIRouter, HTTPException, Depends, File, UploadFile, Request
from fastapi.responses import StreamingResponse, HTMLResponse

from app.database import get_connection
from app.matcha.models.offer_letters.offer_letter import (
    OfferGuidanceRequest,
    OfferGuidanceResponse,
    OfferLetter,
    OfferLetterCreate,
    OfferLetterUpdate,
    CandidateOfferView,
    CandidateOfferDocumentView,
    OfferAcceptRequest,
    OfferDeclineRequest,
    SendRangeRequest,
    CandidateRangeSubmit,
    RangeNegotiateResult,
    ReNegotiateRequest,
)
from app.matcha.dependencies import require_admin_or_client, get_client_company_id, require_feature
from app.core.models.auth import CurrentUser
from app.core.services.storage import get_storage
from app.core.services.email import EmailService
from app.core.services.redis_cache import (
    get_redis_cache, cache_get, cache_set, cache_delete, offer_letters_key,
    check_rate_limit,
)
from app.matcha.services.offer_letters.document import (
    _generate_offer_letter_html,
    _send_candidate_range_email,
)

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

    redis = get_redis_cache()
    if redis and not is_admin:
        cached = await cache_get(redis, offer_letters_key(company_id))
        if cached is not None:
            return [OfferLetter(**r) for r in cached]

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
        result = [OfferLetter(**dict(row)) for row in rows]

    if redis and not is_admin:
        await cache_set(redis, offer_letters_key(company_id), [r.model_dump() for r in result])

    return result


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
        new_offer = OfferLetter(**dict(row))

    redis = get_redis_cache()
    if redis:
        await cache_delete(redis, offer_letters_key(new_offer.company_id))

    return new_offer


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


# ──────────────────────────────────────────────────────────────────────
# Pure helpers for the public sign-flow (/offer/:token) — DB-free so they
# can be unit tested directly. See tests/huume/test_offer_accept_validation.py
# ──────────────────────────────────────────────────────────────────────

def _token_expired(expires_at, now: dt | None = None) -> bool:
    """True if a candidate_token_expires_at timestamp is in the past.

    Tolerates naive timestamps (older rows / sqlite-style test fixtures) by
    treating them as UTC, matching the tz-aware comparisons already used by
    get_candidate_offer / submit_candidate_range.
    """
    if not expires_at:
        return False
    now = now or dt.now(timezone.utc)
    if expires_at.tzinfo is None:
        expires_at = expires_at.replace(tzinfo=timezone.utc)
    return now > expires_at


def _validate_signed_name(name: str) -> str:
    """Normalize + validate a typed-name signature. Raises ValueError."""
    cleaned = (name or "").strip()
    if not cleaned:
        raise ValueError("signed_name cannot be blank")
    if len(cleaned) > 255:
        raise ValueError("signed_name is too long")
    return cleaned


def _acceptable_transition(status: str | None, *, to: str) -> bool:
    """Whether an offer in `status` may transition to accepted/declined.

    Only a 'sent' offer can be signed or declined — draft offers haven't
    been sent to a candidate yet, and accepted/rejected/expired are
    terminal. `to` is accepted for symmetry/readability at call sites even
    though the source-state check is identical for both directions today.
    """
    del to  # both directions require the same source state
    return status == "sent"


def _first_forwarded_ip(request: Request) -> str:
    """Best-effort client IP for the signer_ip audit stamp (first hop of
    X-Forwarded-For behind nginx; falls back to the direct peer)."""
    fwd = request.headers.get("x-forwarded-for")
    if fwd:
        parts = [p.strip() for p in fwd.split(",") if p.strip()]
        if parts:
            return parts[0]
    return request.client.host if request.client else "unknown"


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
    redis = get_redis_cache()
    if redis:
        await cache_delete(redis, offer_letters_key(updated["company_id"]))

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


async def _notify_huume_thread_of_offer_event(
    offer: dict, *, event: str, detail: str,
) -> None:
    """Best-effort: post a system notice into the matcha-work thread that
    originated this offer (reuses `mw_threads.linked_offer_letter_id` — the
    same offer<->thread link the classic `offer_letter` skill sets via
    `save_offer_letter_draft`, so this fires for any thread that drafted the
    offer, Huume or not), and bell-notify the thread's creator. Never raises
    — a candidate's click must not 500 because a thread got deleted or a WS
    push hiccuped.

    `event` is 'accepted' | 'declined'.
    """
    try:
        from app.matcha.services.matcha_work.matcha_work_document import (
            add_message, apply_update,
        )
        from app.matcha.services.notification_service import create_notification

        async with get_connection() as conn:
            thread = await conn.fetchrow(
                "SELECT id, created_by FROM mw_threads WHERE linked_offer_letter_id = $1 AND company_id = $2",
                offer["id"], offer["company_id"],
            )
        if not thread:
            return
        thread_id = thread["id"]

        await apply_update(
            thread_id,
            {"huume_offer": {
                "offer_id": str(offer["id"]),
                "status": offer.get("status"),
                "event": event,
                "signed_name": offer.get("signed_name"),
            }},
            diff_summary=f"Offer {event} by candidate",
        )
        assistant_msg = await add_message(
            thread_id, "assistant", detail,
            metadata={"huume_event": f"offer_{event}", "offer_id": str(offer["id"])},
        )
        try:
            from app.matcha.routes.work.thread_ws import thread_manager
            from app.matcha.routes.matcha_work._shared import _row_to_message
            await thread_manager.broadcast_new_message(
                str(thread_id),
                [_row_to_message(assistant_msg).model_dump(mode="json")],
            )
        except Exception:
            logger.debug("[Huume] thread broadcast skipped for %s", thread_id, exc_info=True)

        creator_id = thread["created_by"]
        if creator_id:
            await create_notification(
                user_id=creator_id,
                company_id=offer["company_id"],
                type="huume_offer",
                title=f"Offer {event}",
                body=detail,
                link=f"/work/threads/{thread_id}",
                metadata={"offer_id": str(offer["id"]), "event": event},
            )
    except Exception:
        logger.exception(
            "[Huume] failed to notify thread %s of offer %s event=%s",
            thread_id, offer.get("id"), event,
        )


@candidate_router.get("/candidate/{token}/document", response_model=CandidateOfferDocumentView)
async def get_candidate_offer_document(token: str, request: Request):
    """Public endpoint — the sign-flow view of an offer at /offer/:token.

    Works for both a fixed-terms offer (mode='sign', typed-name accept) and
    a salary-range offer (mode='range', existing submit-range flow) so the
    one public page can render either. Unlike get_candidate_offer, this
    does NOT require a salary range to be set.
    """
    await check_rate_limit(_first_forwarded_ip(request), "offer_document", 60, 3600)
    async with get_connection() as conn:
        row = await conn.fetchrow("SELECT * FROM offer_letters WHERE candidate_token = $1", token)
        if not row:
            raise HTTPException(status_code=404, detail="Offer not found")
        offer = dict(row)
        if _token_expired(offer.get("candidate_token_expires_at")) and offer.get("status") == "sent":
            raise HTTPException(status_code=410, detail="This offer link has expired")

        is_range = bool(offer.get("salary_range_min") and offer.get("salary_range_max")) and not offer.get("signed_name")
        return CandidateOfferDocumentView(
            id=offer["id"],
            mode="range" if is_range else "sign",
            status=offer["status"],
            position_title=offer["position_title"],
            company_name=offer["company_name"],
            company_logo_url=offer.get("company_logo_url"),
            employment_type=offer.get("employment_type"),
            location=offer.get("location"),
            salary=offer.get("salary"),
            bonus=offer.get("bonus"),
            stock_options=offer.get("stock_options"),
            start_date=offer.get("start_date"),
            expiration_date=offer.get("expiration_date"),
            manager_name=offer.get("manager_name"),
            manager_title=offer.get("manager_title"),
            benefits_medical=offer.get("benefits_medical") or False,
            benefits_dental=offer.get("benefits_dental") or False,
            benefits_vision=offer.get("benefits_vision") or False,
            benefits_401k=offer.get("benefits_401k") or False,
            benefits_401k_match=offer.get("benefits_401k_match"),
            benefits_pto_vacation=offer.get("benefits_pto_vacation") or False,
            benefits_pto_sick=offer.get("benefits_pto_sick") or False,
            benefits_holidays=offer.get("benefits_holidays") or False,
            benefits_other=offer.get("benefits_other"),
            signed_name=offer.get("signed_name"),
            signed_at=offer.get("signed_at"),
            declined_at=offer.get("declined_at"),
            salary_range_min=float(offer["salary_range_min"]) if offer.get("salary_range_min") else None,
            salary_range_max=float(offer["salary_range_max"]) if offer.get("salary_range_max") else None,
            range_match_status=offer.get("range_match_status"),
            negotiation_round=offer.get("negotiation_round"),
            max_negotiation_rounds=offer.get("max_negotiation_rounds"),
            matched_salary=float(offer["matched_salary"]) if offer.get("matched_salary") else None,
        )


@candidate_router.get("/candidate/{token}/pdf")
async def download_candidate_offer_pdf(token: str, request: Request):
    """Public endpoint — the rendered offer PDF, signed if already accepted."""
    await check_rate_limit(_first_forwarded_ip(request), "offer_pdf", 30, 3600)
    async with get_connection() as conn:
        row = await conn.fetchrow("SELECT * FROM offer_letters WHERE candidate_token = $1", token)
        if not row:
            raise HTTPException(status_code=404, detail="Offer not found")
        offer = dict(row)

    logo_src = await _build_logo_data_uri(offer.get("company_logo_url"))
    signature = None
    if offer.get("signed_name") and offer.get("signed_at"):
        signature = {
            "name": offer["signed_name"],
            "signed_at": offer["signed_at"],
            "ip": offer.get("signer_ip"),
        }
    html_content = _generate_offer_letter_html(offer, logo_src=logo_src, signature=signature)
    try:
        from app.core.services.pdf import render_pdf
        pdf_bytes = render_pdf(html_content)
    except ImportError as e:
        logger.error(f"WeasyPrint not installed - cannot generate PDF: {e}")
        raise HTTPException(status_code=500, detail="PDF generation not available.")
    except Exception as e:
        logger.error(f"Failed to generate candidate PDF for offer {offer['id']}: {e}")
        raise HTTPException(status_code=500, detail="Failed to generate PDF. Please try again.")
    return StreamingResponse(
        BytesIO(pdf_bytes),
        media_type="application/pdf",
        headers={"Content-Disposition": f'inline; filename="offer-letter-{(offer.get("candidate_name") or "offer").replace(" ", "-")}.pdf"'},
    )


@candidate_router.post("/candidate/{token}/accept", response_model=OfferLetter)
async def accept_candidate_offer(token: str, payload: OfferAcceptRequest, request: Request):
    """Public endpoint — candidate types their name and accepts the offer.

    Guarded UPDATE (`AND status = 'sent'`) makes a double-click / replay
    safe: a second call sees 0 rows updated and 409s rather than
    re-stamping signed_at or double-firing notifications.
    """
    await check_rate_limit(_first_forwarded_ip(request), "offer_accept", 10, 3600)
    signed_name = _validate_signed_name(payload.signed_name)
    signer_ip = _first_forwarded_ip(request)

    async with get_connection() as conn:
        row = await conn.fetchrow("SELECT * FROM offer_letters WHERE candidate_token = $1", token)
        if not row:
            raise HTTPException(status_code=404, detail="Offer not found")
        offer = dict(row)
        if _token_expired(offer.get("candidate_token_expires_at")):
            raise HTTPException(status_code=410, detail="This offer link has expired")
        if not _acceptable_transition(offer.get("status"), to="accepted"):
            if offer.get("status") == "accepted":
                raise HTTPException(status_code=409, detail="This offer has already been accepted")
            raise HTTPException(status_code=409, detail="This offer is not awaiting a response")

        updated = await conn.fetchrow(
            """
            UPDATE offer_letters
            SET signed_name = $1, signed_at = NOW(), signer_ip = $2,
                status = 'accepted', updated_at = NOW()
            WHERE candidate_token = $3 AND status = 'sent'
            RETURNING *
            """,
            signed_name, signer_ip, token,
        )
        if not updated:
            raise HTTPException(status_code=409, detail="This offer is not awaiting a response")
        updated = dict(updated)

    redis = get_redis_cache()
    if redis:
        await cache_delete(redis, offer_letters_key(updated["company_id"]))

    # Render + store the signed PDF. Best-effort — a storage hiccup must not
    # fail the candidate's acceptance; the unsigned terms are already saved.
    try:
        logo_src = await _build_logo_data_uri(updated.get("company_logo_url"))
        signature = {"name": signed_name, "signed_at": updated["signed_at"], "ip": signer_ip}
        html_content = _generate_offer_letter_html(updated, logo_src=logo_src, signature=signature)
        from app.core.services.pdf import render_pdf
        pdf_bytes = render_pdf(html_content)
        storage_path = await get_storage().upload_private_file(
            pdf_bytes,
            filename=f"offer-signed-{updated['id']}.pdf",
            prefix="offer-letters/signed",
            content_type="application/pdf",
        )
        async with get_connection() as conn:
            await conn.execute(
                "UPDATE offer_letters SET signed_pdf_storage_path = $1 WHERE id = $2",
                storage_path, updated["id"],
            )
        updated["signed_pdf_storage_path"] = storage_path
    except Exception:
        logger.exception("[OfferLetters] failed to render/store signed PDF for offer %s", updated["id"])

    await _notify_huume_thread_of_offer_event(
        updated, event="accepted",
        detail=f"**{updated.get('candidate_name') or 'The candidate'}** accepted the offer for "
               f"**{updated.get('position_title') or 'the role'}** — signed {signed_name} just now. "
               f"Say \"build the onboarding plan\" when you're ready to start onboarding.",
    )

    try:
        async with get_connection() as conn:
            employer_row = await conn.fetchrow(
                "SELECT u.email FROM users u JOIN companies c ON u.id = c.owner_id WHERE c.id = $1",
                updated.get("company_id"),
            )
        if employer_row and employer_row["email"]:
            await _send_employer_result_email(
                employer_email=employer_row["email"],
                candidate_name=updated.get("candidate_name") or "Candidate",
                position_title=updated.get("position_title") or "",
                result="matched",
                matched_salary=None,
                rounds_remaining=0,
            )
    except Exception:
        logger.warning("[OfferLetters] Failed to send offer-accepted employer email", exc_info=True)

    return OfferLetter(**updated)


@candidate_router.post("/candidate/{token}/decline")
async def decline_candidate_offer(token: str, payload: OfferDeclineRequest, request: Request):
    """Public endpoint — candidate declines the offer."""
    await check_rate_limit(_first_forwarded_ip(request), "offer_accept", 10, 3600)

    async with get_connection() as conn:
        row = await conn.fetchrow("SELECT * FROM offer_letters WHERE candidate_token = $1", token)
        if not row:
            raise HTTPException(status_code=404, detail="Offer not found")
        offer = dict(row)
        if not _acceptable_transition(offer.get("status"), to="declined"):
            if offer.get("status") == "rejected":
                raise HTTPException(status_code=409, detail="This offer has already been declined")
            raise HTTPException(status_code=409, detail="This offer is not awaiting a response")

        updated = await conn.fetchrow(
            """
            UPDATE offer_letters
            SET status = 'rejected', declined_at = NOW(), decline_reason = $1, updated_at = NOW()
            WHERE candidate_token = $2 AND status = 'sent'
            RETURNING *
            """,
            payload.reason, token,
        )
        if not updated:
            raise HTTPException(status_code=409, detail="This offer is not awaiting a response")
        updated = dict(updated)

    redis = get_redis_cache()
    if redis:
        await cache_delete(redis, offer_letters_key(updated["company_id"]))

    await _notify_huume_thread_of_offer_event(
        updated, event="declined",
        detail=f"**{updated.get('candidate_name') or 'The candidate'}** declined the offer for "
               f"**{updated.get('position_title') or 'the role'}**"
               + (f" — reason given: “{payload.reason}”" if payload.reason else "") + ".",
    )

    try:
        async with get_connection() as conn:
            employer_row = await conn.fetchrow(
                "SELECT u.email FROM users u JOIN companies c ON u.id = c.owner_id WHERE c.id = $1",
                updated.get("company_id"),
            )
        if employer_row and employer_row["email"]:
            await _send_employer_result_email(
                employer_email=employer_row["email"],
                candidate_name=updated.get("candidate_name") or "Candidate",
                position_title=updated.get("position_title") or "",
                result="no_match_low",
                matched_salary=None,
                rounds_remaining=0,
            )
    except Exception:
        logger.warning("[OfferLetters] Failed to send offer-declined employer email", exc_info=True)

    return {"status": "declined"}


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
    redis = get_redis_cache()
    if redis:
        await cache_delete(redis, offer_letters_key(updated["company_id"]))

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
        updated_offer = OfferLetter(**dict(row))

    redis = get_redis_cache()
    if redis:
        await cache_delete(redis, offer_letters_key(updated_offer.company_id))

    return updated_offer


# _safe / _generate_benefits_text / _generate_contingencies_text /
# _generate_offer_letter_html moved to services/offer_letters/document.py
# (refactor round 2, stage 3) — imported at the top of this file.


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


async def _fetch_offer_scoped(offer_id: UUID, current_user: CurrentUser) -> dict:
    """Company-scoped offer fetch shared by /pdf and /preview.

    Admin also sees legacy company_id IS NULL rows, mirroring GET /{offer_id}.
    Raises 404 on a missing or cross-tenant offer_id.
    """
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
        return dict(row)


async def _render_offer_html(offer: dict, request: Request) -> str:
    """Render the offer letter's HTML — logo resolved to a data URI (falling
    back to an absolute URL off the request) and a signature block included
    once the offer has actually been signed."""
    logo_src = await _build_logo_data_uri(offer.get("company_logo_url"))
    if not logo_src and offer.get("company_logo_url"):
        raw_logo_url = str(offer["company_logo_url"])
        if raw_logo_url.startswith("/"):
            logo_src = f"{str(request.base_url).rstrip('/')}{raw_logo_url}"
        else:
            logo_src = raw_logo_url

    signature = None
    if offer.get("signed_at"):
        signature = {
            "name": offer.get("signed_name"),
            "signed_at": offer["signed_at"],
            "ip": offer.get("signer_ip"),
        }

    return _generate_offer_letter_html(offer, logo_src=logo_src, signature=signature)


@router.get("/{offer_id}/preview", response_class=HTMLResponse)
async def preview_offer_letter_html(
    offer_id: UUID,
    request: Request,
    current_user: CurrentUser = Depends(require_admin_or_client),
):
    """Render the offer letter as HTML for in-app review (e.g. the Huume
    thread panel) — the same document the PDF and candidate signing page
    produce, so there is one source of truth for what the letter says."""
    offer = await _fetch_offer_scoped(offer_id, current_user)
    html_content = await _render_offer_html(offer, request)
    return HTMLResponse(content=html_content, headers={"Cache-Control": "no-store"})


@router.get("/{offer_id}/pdf")
async def download_offer_letter_pdf(
    offer_id: UUID,
    request: Request,
    current_user: CurrentUser = Depends(require_admin_or_client),
):
    """Generate and download offer letter as PDF."""
    offer = await _fetch_offer_scoped(offer_id, current_user)
    html_content = await _render_offer_html(offer, request)

    # Try to use weasyprint for PDF generation
    try:
        from app.core.services.pdf import render_pdf
        pdf_bytes = render_pdf(html_content)
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

    redis = get_redis_cache()
    if redis:
        await cache_delete(redis, offer_letters_key(company_id))

    return {"url": url}
