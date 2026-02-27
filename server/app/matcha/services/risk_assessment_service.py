"""Risk Assessment Service.

Computes a live risk score across 5 dimensions for a company:
- Compliance (30%)
- Incidents (25%)
- ER Cases (25%)
- Workforce (15%)
- Legislative (5%)
"""

import json
import logging
from dataclasses import dataclass, field, asdict
from datetime import datetime, timezone, timedelta
from typing import Any, Optional
from uuid import UUID

from google import genai

from ...database import get_connection

logger = logging.getLogger(__name__)


def _band(score: int) -> str:
    if score <= 25:
        return "low"
    elif score <= 50:
        return "moderate"
    elif score <= 75:
        return "high"
    else:
        return "critical"


@dataclass
class DimensionResult:
    score: int
    band: str
    factors: list[str]
    raw_data: dict[str, Any]


@dataclass
class RiskAssessmentResult:
    overall_score: int
    overall_band: str
    dimensions: dict[str, DimensionResult]
    computed_at: datetime


async def compute_compliance_dimension(company_id: UUID, conn) -> DimensionResult:
    """Score compliance risk based on unread alerts and check recency."""
    row = await conn.fetchrow(
        """
        SELECT
          COUNT(*) FILTER (WHERE ca.severity = 'critical' AND ca.status = 'unread') AS critical_unread,
          COUNT(*) FILTER (WHERE ca.severity = 'warning'  AND ca.status = 'unread') AS warning_unread,
          MAX(cl.completed_at) AS last_check
        FROM compliance_alerts ca
        JOIN business_locations bl ON bl.id = ca.location_id
        LEFT JOIN compliance_check_log cl ON cl.company_id = $1
        WHERE ca.company_id = $1
        """,
        company_id,
    )

    critical_unread = int(row["critical_unread"] or 0)
    warning_unread = int(row["warning_unread"] or 0)
    last_check: Optional[datetime] = row["last_check"]

    score = 0
    factors = []

    critical_points = min(critical_unread * 35, 70)
    if critical_points > 0:
        score += critical_points
        factors.append(f"{critical_unread} unread critical alert{'s' if critical_unread != 1 else ''} (+{critical_points})")

    warning_points = min(warning_unread * 15, 30)
    if warning_points > 0:
        score += warning_points
        factors.append(f"{warning_unread} unread warning alert{'s' if warning_unread != 1 else ''} (+{warning_points})")

    stale_points = 0
    if last_check is None:
        stale_points = 20
        score += stale_points
        factors.append(f"No compliance check on record (+{stale_points})")
    else:
        if last_check.tzinfo is None:
            last_check = last_check.replace(tzinfo=timezone.utc)
        days_since = (datetime.now(timezone.utc) - last_check).days
        if days_since >= 30:
            stale_points = 20
            score += stale_points
            factors.append(f"Last compliance check {days_since} days ago (+{stale_points})")

    score = min(score, 100)
    if not factors:
        factors.append("No compliance issues detected")

    return DimensionResult(
        score=score,
        band=_band(score),
        factors=factors,
        raw_data={
            "critical_unread": critical_unread,
            "warning_unread": warning_unread,
            "last_check": last_check.isoformat() if last_check else None,
        },
    )


async def compute_incident_dimension(company_id: UUID, conn) -> DimensionResult:
    """Score incident risk based on open IR incidents by severity."""
    rows = await conn.fetch(
        """
        SELECT severity, COUNT(*) AS cnt
        FROM ir_incidents
        WHERE company_id = $1
          AND status NOT IN ('resolved', 'closed')
        GROUP BY severity
        """,
        company_id,
    )

    counts: dict[str, int] = {row["severity"]: int(row["cnt"]) for row in rows}
    critical = counts.get("critical", 0)
    high = counts.get("high", 0)
    medium = counts.get("medium", 0)
    low = counts.get("low", 0)

    score = 0
    factors = []

    points = min(critical * 25, 100)
    if critical > 0:
        score += min(critical * 25, 100 - score)
        factors.append(f"{critical} open critical incident{'s' if critical != 1 else ''} (+{critical * 25})")

    if high > 0:
        pts = min(high * 15, max(0, 100 - score))
        score += pts
        factors.append(f"{high} open high severity incident{'s' if high != 1 else ''} (+{high * 15})")

    if medium > 0:
        pts = min(medium * 8, max(0, 100 - score))
        score += pts
        factors.append(f"{medium} open medium severity incident{'s' if medium != 1 else ''} (+{medium * 8})")

    if low > 0:
        pts = min(low * 3, max(0, 100 - score))
        score += pts
        factors.append(f"{low} open low severity incident{'s' if low != 1 else ''} (+{low * 3})")

    score = min(score, 100)
    if not factors:
        factors.append("No open incidents")

    return DimensionResult(
        score=score,
        band=_band(score),
        factors=factors,
        raw_data={
            "open_critical": critical,
            "open_high": high,
            "open_medium": medium,
            "open_low": low,
        },
    )


async def compute_er_dimension(company_id: UUID, conn) -> DimensionResult:
    """Score ER risk based on open cases and analysis findings."""
    status_rows = await conn.fetch(
        """
        SELECT status, COUNT(*) AS cnt
        FROM er_cases
        WHERE company_id = $1 AND status != 'closed'
        GROUP BY status
        """,
        company_id,
    )

    status_counts: dict[str, int] = {row["status"]: int(row["cnt"]) for row in status_rows}
    pending = status_counts.get("pending_determination", 0)
    in_review = status_counts.get("in_review", 0)
    open_cases = status_counts.get("open", 0)

    analysis_rows = await conn.fetch(
        """
        SELECT analysis_type, analysis_data
        FROM er_case_analysis
        WHERE case_id IN (SELECT id FROM er_cases WHERE company_id = $1)
          AND analysis_type IN ('policy_check', 'discrepancies')
        """,
        company_id,
    )

    has_major_policy_violation = False
    has_high_discrepancy = False

    import json as _json
    for row in analysis_rows:
        data = row["analysis_data"]
        if isinstance(data, str):
            try:
                data = _json.loads(data)
            except Exception:
                continue
        if not isinstance(data, dict):
            continue

        if row["analysis_type"] == "policy_check":
            violation_level = data.get("violation_level", "") or data.get("severity", "")
            if isinstance(violation_level, str) and "major" in violation_level.lower():
                has_major_policy_violation = True
        elif row["analysis_type"] == "discrepancies":
            severity = data.get("severity", "") or data.get("overall_severity", "")
            if isinstance(severity, str) and severity.lower() == "high":
                has_high_discrepancy = True

    score = 0
    factors = []

    if pending > 0:
        pts = min(pending * 30, 100)
        score += pts
        factors.append(f"{pending} case{'s' if pending != 1 else ''} pending determination (+{pts})")

    if in_review > 0:
        pts = min(in_review * 20, max(0, 100 - score))
        score += pts
        factors.append(f"{in_review} case{'s' if in_review != 1 else ''} in review (+{pts})")

    if open_cases > 0:
        pts = min(open_cases * 10, max(0, 100 - score))
        score += pts
        factors.append(f"{open_cases} open case{'s' if open_cases != 1 else ''} (+{pts})")

    if has_major_policy_violation and score < 100:
        pts = min(15, 100 - score)
        score += pts
        factors.append(f"Major policy violation found in analysis (+{pts})")

    if has_high_discrepancy and score < 100:
        pts = min(10, 100 - score)
        score += pts
        factors.append(f"High severity discrepancy in analysis (+{pts})")

    score = min(score, 100)
    if not factors:
        factors.append("No open ER cases")

    return DimensionResult(
        score=score,
        band=_band(score),
        factors=factors,
        raw_data={
            "pending_determination": pending,
            "in_review": in_review,
            "open": open_cases,
            "major_policy_violation": has_major_policy_violation,
            "high_discrepancy": has_high_discrepancy,
        },
    )


async def compute_workforce_dimension(company_id: UUID, conn) -> DimensionResult:
    """Score workforce risk based on multi-jurisdictional exposure and workforce composition."""
    rows = await conn.fetch(
        """
        SELECT work_state, employment_type, COUNT(*) AS cnt
        FROM employees
        WHERE org_id = $1 AND termination_date IS NULL
        GROUP BY work_state, employment_type
        """,
        company_id,
    )

    total_employees = sum(int(row["cnt"]) for row in rows)
    unique_states = len({row["work_state"] for row in rows if row["work_state"]})

    contractor_intern_count = sum(
        int(row["cnt"])
        for row in rows
        if row["employment_type"] in ("contractor", "intern")
    )

    score = 0
    factors = []

    state_pts = unique_states * 5
    if unique_states > 0:
        score += min(state_pts, 100)
        factors.append(f"{unique_states} state{'s' if unique_states != 1 else ''} with active employees (+{state_pts})")

    if total_employees > 10:
        over_10 = total_employees - 10
        scale_pts = min((over_10 // 10) * 3, 30)
        if scale_pts > 0:
            score += min(scale_pts, max(0, 100 - score))
            factors.append(f"{total_employees} total employees (scale factor +{scale_pts})")

    if total_employees > 0:
        pct_contingent = contractor_intern_count / total_employees
        if pct_contingent > 0.20:
            pts = min(15, max(0, 100 - score))
            score += pts
            pct_display = int(pct_contingent * 100)
            factors.append(f"{pct_display}% contingent workforce (contractors/interns) (+{pts})")

    score = min(score, 100)
    if not factors:
        factors.append("No workforce risk indicators")

    return DimensionResult(
        score=score,
        band=_band(score),
        factors=factors,
        raw_data={
            "total_employees": total_employees,
            "unique_states": unique_states,
            "contractor_intern_count": contractor_intern_count,
        },
    )


async def compute_legislative_dimension(company_id: UUID, conn) -> DimensionResult:
    """Score legislative risk based on upcoming legislation affecting company locations."""
    rows = await conn.fetch(
        """
        SELECT jl.expected_effective_date
        FROM jurisdiction_legislation jl
        JOIN business_locations bl ON bl.jurisdiction_id = jl.jurisdiction_id
        WHERE bl.company_id = $1
          AND jl.current_status IN ('passed', 'signed', 'effective_soon')
          AND jl.expected_effective_date > NOW()
        """,
        company_id,
    )

    now = datetime.now(timezone.utc)
    within_30 = 0
    within_90 = 0
    within_180 = 0

    for row in rows:
        effective_date = row["expected_effective_date"]
        if effective_date is None:
            continue
        if hasattr(effective_date, 'tzinfo') and effective_date.tzinfo is None:
            effective_date = effective_date.replace(tzinfo=timezone.utc)
        days_until = (effective_date - now).days
        if days_until < 30:
            within_30 += 1
        elif days_until < 90:
            within_90 += 1
        elif days_until < 180:
            within_180 += 1

    score = 0
    factors = []

    if within_30 > 0:
        pts = min(within_30 * 40, 100)
        score += pts
        factors.append(f"{within_30} legislation item{'s' if within_30 != 1 else ''} effective within 30 days (+{pts})")

    if within_90 > 0:
        pts = min(within_90 * 20, max(0, 100 - score))
        score += pts
        factors.append(f"{within_90} legislation item{'s' if within_90 != 1 else ''} effective within 31–90 days (+{pts})")

    if within_180 > 0:
        pts = min(within_180 * 5, max(0, 100 - score))
        score += pts
        factors.append(f"{within_180} legislation item{'s' if within_180 != 1 else ''} effective within 91–180 days (+{pts})")

    score = min(score, 100)
    if not factors:
        factors.append("No upcoming legislation changes")

    return DimensionResult(
        score=score,
        band=_band(score),
        factors=factors,
        raw_data={
            "within_30_days": within_30,
            "within_90_days": within_90,
            "within_180_days": within_180,
        },
    )


RISK_RECOMMENDATION_PROMPT = """You are a senior HR risk consultant and employment attorney with 20 years advising mid-market and enterprise companies. You are reviewing a client's automated HR risk dashboard before a quarterly board briefing. Your job is to produce the kind of written memo a senior HR law firm would deliver — legally specific, citing real fine amounts and enforcement precedents, grounded in actual employment law.

## Platform Context

This dashboard aggregates live data from an HR platform across 5 risk dimensions. Scores are 0–100 per dimension (weighted into an overall score). Bands: 0–25 = Low, 26–50 = Moderate, 51–75 = High, 76–100 = Critical.

Dimension weights: Compliance 30%, Incidents 25%, ER Cases 25%, Workforce 15%, Legislative 5%.

## What Each Dimension Means

**compliance** — Regulatory compliance alerts across all business locations. Unread alerts represent known regulatory exposure the company has not responded to. Critical alerts typically involve wage/hour violations, leave law non-compliance, or workplace posting failures. Every day an unread alert sits open is a day of documented, willful non-compliance. `last_check` is when the company last ran a compliance audit scan.

**incidents** — Open workplace incident reports (safety incidents, behavioral misconduct, harassment, discrimination complaints). Open incidents are unresolved legal exposure. OSHA willful violations carry penalties up to $156,259 per violation (2024 rates). Title VII harassment claims average $40,000–$300,000 in EEOC settlements; jury verdicts frequently exceed $1M. Delay in investigation is a primary factor in punitive damages awards.

**er_cases** — Employment Relations cases: disputes, disciplinary matters, accommodation requests, investigations. `pending_determination` cases are the most dangerous — open investigations without documented conclusions expose the company to EEOC complaints, wrongful termination suits, and failure-to-accommodate claims under the ADA (average EEOC resolution: $25,000–$75,000; litigation costs typically 3–5x settlement value). States like California, New York, and Illinois impose additional obligations beyond federal law.

**workforce** — Multi-state and workforce composition risk. Each state with employees creates a separate compliance jurisdiction with its own wage/hour, leave, and classification rules. Contingent workforce ratios above 20% trigger IRS/DOL worker misclassification scrutiny — the DOL recovered $274M in back wages in FY2023 alone. States like California (AB5), New Jersey, and Massachusetts apply the strictest misclassification tests; exposure includes back taxes, benefits liability, and per-worker civil penalties.

**legislative** — Upcoming laws affecting the company's locations that require policy, process, or handbook changes before their effective dates. Items effective within 30 days are in the emergency window — the company may already be non-compliant if it hasn't acted. State-level paid leave, pay transparency, and non-compete laws have been the most active legislative areas in 2023–2024.

## Risk Assessment Data

{assessment_json}

## Instructions

Produce 5–10 strategic consulting recommendations based on this data.

Rules:
- Only produce recommendations for dimensions where score > 0.
- Order by severity: critical first, then high, medium, low.
- Every recommendation must cite the specific numbers from the data AND specific legal/financial stakes (e.g. actual fine ranges, named statutes, enforcement agency, historical penalty amounts).
- Name the specific states from `unique_states` where relevant — multi-state exposure means multi-jurisdiction liability.
- Explain the trajectory risk: what does the current score mean, and what happens if it climbs one band higher?
- Give concrete next steps (not "address the issue" but "assign an owner, set a 48-hour deadline, document the response in writing").
- Write in the voice of a senior advisor briefing a CHRO or CEO — authoritative, direct, no filler.
- priority must be one of: critical, high, medium, low.
- dimension must be one of: compliance, incidents, er_cases, workforce, legislative.

Return ONLY a valid JSON object (no markdown fences) with two fields:

1. "report": A 2-3 paragraph executive summary written as a senior HR consultant addressing the company's leadership. Requirements:
   - State the overall score and band upfront, and what it means in plain terms for the company's legal exposure today
   - Name specific risks tied to the actual dimension scores — include real dollar amounts for fines, settlements, and penalties relevant to each active risk area (e.g. OSHA per-violation amounts, EEOC average settlements, DOL back-wage recovery figures, state-specific penalty structures)
   - Address trajectory: at a moderate score of 34, the company is one bad quarter away from high-risk territory — cite what has historically happened to companies that allowed similar profiles to deteriorate (named enforcement actions, class actions, DOL audits)
   - If doing well in some areas, acknowledge it specifically — but make clear that moderate risk is not safe, it is deferred liability
   - Tone: authoritative, grounded, zero filler — the kind of memo a CHRO would forward to the board
   - Do NOT use bullet points or lists — write in flowing narrative paragraphs

2. "recommendations": A JSON array of 5-10 objects, each with:
   - "dimension": string
   - "priority": "critical" | "high" | "medium" | "low"
   - "title": concise heading (6-10 words)
   - "guidance": 4-5 sentences — current situation with specific numbers, exact legal/financial consequence (statute name, fine range, enforcement agency), and concrete next steps"""

FALLBACK_MODELS = ["gemini-2.5-flash", "gemini-2.0-flash"]


def _parse_json_response(text: str) -> Any:
    """Parse JSON from LLM response, handling markdown code blocks."""
    text = text.strip()
    if text.startswith("```json"):
        text = text[7:]
    elif text.startswith("```"):
        text = text[3:]
    if text.endswith("```"):
        text = text[:-3]
    return json.loads(text.strip())


def _is_model_unavailable_error(error: Exception) -> bool:
    message = str(error).lower()
    if "model" not in message:
        return False
    return (
        "not found" in message
        or "does not have access" in message
        or "unsupported model" in message
        or "404" in message
    )


async def generate_recommendations(result: RiskAssessmentResult, settings) -> dict:
    """Generate executive report and strategic HR consulting recommendations via Gemini."""
    empty = {"report": None, "recommendations": []}
    try:
        if settings.use_vertex:
            client = genai.Client(
                vertexai=True,
                project=settings.vertex_project,
                location=settings.vertex_location,
            )
        elif settings.gemini_api_key:
            client = genai.Client(api_key=settings.gemini_api_key)
        else:
            logger.warning("No Gemini credentials configured — skipping recommendations")
            return empty

        assessment_dict = {
            "overall_score": result.overall_score,
            "overall_band": result.overall_band,
            "dimensions": {
                key: asdict(dim) for key, dim in result.dimensions.items()
            },
            "computed_at": result.computed_at.isoformat(),
        }
        prompt = RISK_RECOMMENDATION_PROMPT.format(
            assessment_json=json.dumps(assessment_dict, indent=2, default=str)
        )

        models_to_try = [settings.analysis_model] + [
            m for m in FALLBACK_MODELS if m != settings.analysis_model
        ]

        last_error = None
        for model in models_to_try:
            try:
                response = await client.aio.models.generate_content(
                    model=model,
                    contents=prompt,
                )
                break
            except Exception as e:
                last_error = e
                if _is_model_unavailable_error(e):
                    logger.warning("Model %s unavailable, trying next: %s", model, e)
                    continue
                raise
        else:
            raise last_error  # type: ignore[misc]

        parsed = _parse_json_response(response.text)
        if not isinstance(parsed, dict):
            logger.error("Gemini returned non-object for consultation")
            return empty

        report = parsed.get("report") or None
        recs = parsed.get("recommendations", [])
        if not isinstance(recs, list):
            recs = []

        valid_priorities = {"critical", "high", "medium", "low"}
        valid_dims = {"compliance", "incidents", "er_cases", "workforce", "legislative"}
        validated = []
        for r in recs:
            if (
                isinstance(r, dict)
                and r.get("priority") in valid_priorities
                and r.get("dimension") in valid_dims
                and r.get("title")
                and r.get("guidance")
            ):
                validated.append({
                    "dimension": r["dimension"],
                    "priority": r["priority"],
                    "title": r["title"],
                    "guidance": r["guidance"],
                })
        return {"report": report, "recommendations": validated}

    except Exception:
        logger.exception("Failed to generate Gemini consultation — returning empty")
        return empty


async def compute_risk_assessment(company_id: UUID) -> RiskAssessmentResult:
    """Compute full risk assessment for a company across all 5 dimensions."""
    async with get_connection() as conn:
        compliance = await compute_compliance_dimension(company_id, conn)
        incidents = await compute_incident_dimension(company_id, conn)
        er = await compute_er_dimension(company_id, conn)
        workforce = await compute_workforce_dimension(company_id, conn)
        legislative = await compute_legislative_dimension(company_id, conn)

    # Weighted overall score
    overall = int(
        compliance.score * 0.30
        + incidents.score * 0.25
        + er.score * 0.25
        + workforce.score * 0.15
        + legislative.score * 0.05
    )
    overall = min(overall, 100)

    return RiskAssessmentResult(
        overall_score=overall,
        overall_band=_band(overall),
        dimensions={
            "compliance": compliance,
            "incidents": incidents,
            "er_cases": er,
            "workforce": workforce,
            "legislative": legislative,
        },
        computed_at=datetime.now(timezone.utc),
    )
