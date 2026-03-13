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
import math
from dataclasses import dataclass, field, asdict
from datetime import date, datetime, timezone, timedelta
from typing import Any, Optional
from uuid import UUID

from google import genai

from ...database import get_connection

logger = logging.getLogger(__name__)

COMPLIANCE_CRITICAL_ALERT_POINTS = 35
COMPLIANCE_CRITICAL_ALERT_CAP = 70
COMPLIANCE_WARNING_ALERT_POINTS = 15
COMPLIANCE_WARNING_ALERT_CAP = 30
COMPLIANCE_WAGE_VIOLATION_POINTS = 10
COMPLIANCE_WAGE_VIOLATION_CAP = 80
COMPLIANCE_WAGE_LOCATION_POINTS = 5
COMPLIANCE_WAGE_LOCATION_CAP = 20

ER_PENDING_POINTS = 15
ER_PENDING_CAP = 60
ER_IN_REVIEW_POINTS = 10
ER_IN_REVIEW_CAP = 20
ER_OPEN_POINTS = 5
ER_OPEN_CAP = 25
ER_MAJOR_POLICY_POINTS = 10
ER_HIGH_DISCREPANCY_POINTS = 5


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


async def _collect_minimum_wage_violation_metrics(
    company_id: UUID, conn
) -> dict[str, Any]:
    """Aggregate employee minimum wage violations across active locations."""
    from ...core.services.compliance_service import get_employee_impact_for_location

    location_rows = await conn.fetch(
        """
        SELECT id, name, city, state
        FROM business_locations
        WHERE company_id = $1
          AND COALESCE(is_active, TRUE) = TRUE
        """,
        company_id,
    )

    violating_employee_ids: set[str] = set()
    hourly_employee_ids: set[str] = set()
    salary_employee_ids: set[str] = set()
    location_summaries: list[dict[str, Any]] = []
    employee_violations: list[dict[str, Any]] = []
    seen_employee_violations: set[str] = set()

    for location in location_rows:
        try:
            impact = await get_employee_impact_for_location(location["id"], company_id)
        except Exception:
            logger.exception(
                "Failed to compute employee impact for risk assessment location %s",
                location["id"],
            )
            continue

        location_employee_ids: set[str] = set()
        violations_by_rate_type = impact.get("violations_by_rate_type", {})

        for violation in violations_by_rate_type.get("general", []):
            employee_id = violation.get("employee_id")
            if not employee_id:
                continue
            violating_employee_ids.add(employee_id)
            hourly_employee_ids.add(employee_id)
            location_employee_ids.add(employee_id)
            if employee_id not in seen_employee_violations:
                seen_employee_violations.add(employee_id)
                employee_violations.append({
                    "employee_name": violation.get("employee_name"),
                    "pay_rate": violation.get("pay_rate"),
                    "threshold": violation.get("threshold"),
                    "shortfall": violation.get("shortfall"),
                    "pay_classification": violation.get("pay_classification"),
                    "location_city": location["city"],
                    "location_state": location["state"],
                })

        for violation in violations_by_rate_type.get("exempt_salary", []):
            employee_id = violation.get("employee_id")
            if not employee_id:
                continue
            violating_employee_ids.add(employee_id)
            salary_employee_ids.add(employee_id)
            location_employee_ids.add(employee_id)
            if employee_id not in seen_employee_violations:
                seen_employee_violations.add(employee_id)
                employee_violations.append({
                    "employee_name": violation.get("employee_name"),
                    "pay_rate": violation.get("pay_rate"),
                    "threshold": violation.get("threshold"),
                    "shortfall": violation.get("shortfall"),
                    "pay_classification": violation.get("pay_classification"),
                    "location_city": location["city"],
                    "location_state": location["state"],
                })

        if location_employee_ids:
            location_summaries.append(
                {
                    "location_id": str(location["id"]),
                    "location_name": location["name"],
                    "city": location["city"],
                    "state": location["state"],
                    "violation_count": len(location_employee_ids),
                }
            )

    location_summaries.sort(
        key=lambda item: (
            -int(item["violation_count"]),
            (item["location_name"] or item["city"] or "").lower(),
            (item["state"] or "").lower(),
        )
    )

    employee_violations.sort(key=lambda v: -(v.get("shortfall") or 0))

    return {
        "minimum_wage_violation_employee_count": len(violating_employee_ids),
        "hourly_minimum_wage_violation_count": len(hourly_employee_ids),
        "salary_minimum_wage_violation_count": len(salary_employee_ids),
        "locations_with_minimum_wage_violations": len(location_summaries),
        "top_minimum_wage_violation_locations": location_summaries[:5],
        "employee_violations": employee_violations[:10],
        "all_employee_violations": employee_violations,
    }


def compute_compliance_cost_of_risk(
    all_violations: list[dict[str, Any]],
    employee_count: int,
    is_healthcare: bool,
) -> dict[str, Any]:
    """Estimate dollar exposure from compliance violations."""
    line_items: list[dict[str, Any]] = []

    hourly = [v for v in all_violations if v.get("pay_classification") == "hourly"]
    if hourly:
        total_shortfall = sum((v.get("shortfall") or 0) for v in hourly)
        avg_shortfall = total_shortfall / len(hourly) if hourly else 0
        low = sum((v.get("shortfall") or 0) * 2080 * 2 * 2 for v in hourly)
        high = sum((v.get("shortfall") or 0) * 2080 * 3 * 2 for v in hourly)
        line_items.append({
            "key": "hourly_wage_shortfall",
            "label": "Hourly Wage Shortfall",
            "low": round(low),
            "high": round(high),
            "affected_count": len(hourly),
            "basis": "FLSA \u00a7 216(b), 2\u20133yr lookback + liquidated damages",
            "formula": (
                f"{len(hourly)} employees \u00d7 avg ${avg_shortfall:.2f}/hr shortfall "
                f"\u00d7 2,080 hrs/yr \u00d7 2\u20133yr lookback \u00d7 2x liquidated damages"
            ),
            "statute": (
                "Fair Labor Standards Act \u00a7 216(b). Enforced by DOL Wage and Hour Division. "
                "Employers must pay the difference plus an equal amount in liquidated damages. "
                "Willful violations extend the statute of limitations from 2 to 3 years and "
                "can trigger criminal penalties up to $10,000 per violation."
            ),
            "risk_context": (
                "Active wage shortfalls represent ongoing, compounding liability \u2014 every pay period "
                "adds to the back-pay owed. DOL audits triggered by a single complaint often expand "
                "to company-wide reviews. Prompt correction and documented remediation significantly "
                "reduce liquidated damages exposure."
            ),
            "benchmark": (
                "DOL recovered $274M in back wages in FY2023. Average FLSA collective action "
                "settlement: $6.2M (2023). Median individual recovery: $1,200\u2013$5,800 per employee. "
                "Companies that self-audit and correct typically pay 50\u201370% less than those caught by DOL."
            ),
        })

    exempt = [v for v in all_violations if v.get("pay_classification") == "exempt"]
    if exempt:
        low = 0
        high = 0
        for v in exempt:
            pay_rate = v.get("pay_rate") or 0
            effective_hourly = pay_rate / 2080 if pay_rate > 0 else 0
            ot_rate = effective_hourly * 1.5
            low += ot_rate * 5 * 52 * 2 * 2
            high += ot_rate * 10 * 52 * 3 * 2
        avg_salary = sum((v.get("pay_rate") or 0) for v in exempt) / len(exempt) if exempt else 0
        line_items.append({
            "key": "exempt_misclassification",
            "label": "Exempt Misclassification",
            "low": round(low),
            "high": round(high),
            "affected_count": len(exempt),
            "basis": "FLSA \u00a7 207, overtime liability for misclassified exempt employees",
            "formula": (
                f"{len(exempt)} employees \u00d7 avg salary ${avg_salary:,.0f} \u00f7 2,080 hrs "
                f"\u00d7 1.5x OT rate \u00d7 5\u201310 OT hrs/wk \u00d7 52 wks \u00d7 2\u20133yr \u00d7 2x damages"
            ),
            "statute": (
                "FLSA \u00a7 207 requires overtime pay for non-exempt employees. Enforced by DOL WHD. "
                "Employees misclassified as exempt are owed 1.5x their effective hourly rate for all "
                "overtime worked. The 2024 DOL salary threshold is $43,888 ($58,656 effective Jan 2025). "
                "State thresholds may be higher (CA: $66,560, NY: $58,500)."
            ),
            "risk_context": (
                "Misclassification claims are the #1 FLSA litigation category. A single employee's "
                "claim often triggers collective action covering all similarly situated workers. "
                "Reclassifying proactively and paying overtime going forward eliminates future "
                "liability but does not extinguish existing back-pay claims."
            ),
            "benchmark": (
                "Average FLSA misclassification settlement: $2.1M (Seyfarth 2023). "
                "DOL WHD collected $36M specifically for overtime violations in FY2023. "
                "Typical per-employee recovery: $8,000\u2013$25,000 for 2\u20133 years of unpaid OT. "
                "Class/collective action multiplies individual exposure by headcount."
            ),
        })

    if is_healthcare and employee_count > 0:
        line_items.append({
            "key": "hipaa_breach_exposure",
            "label": "HIPAA Breach Exposure",
            "low": employee_count * 145,
            "high": employee_count * 1452,
            "affected_count": employee_count,
            "basis": "HIPAA penalty tiers, Tier 1\u2013Tier 2 (inflation-adjusted)",
            "formula": (
                f"{employee_count} employee records \u00d7 $145\u2013$1,452 per record "
                f"(Tier 1 lack-of-knowledge through Tier 2 reasonable-cause)"
            ),
            "statute": (
                "HIPAA \u00a7 1176, enforced by HHS Office for Civil Rights (OCR). Four penalty tiers: "
                "Tier 1 (unaware) $137\u2013$68,928/violation, Tier 2 (reasonable cause) $1,379\u2013$68,928, "
                "Tier 3 (willful neglect, corrected) $13,785\u2013$68,928, "
                "Tier 4 (willful neglect, uncorrected) $68,928\u2013$2,067,813. Annual cap: $2.07M per category."
            ),
            "risk_context": (
                "Healthcare employers hold PHI for every employee (benefits, workers\u2019 comp, FMLA). "
                "A breach affecting employee records triggers OCR investigation, state AG notification, "
                "and individual notice requirements. Breach probability increases with headcount and "
                "number of systems storing PHI."
            ),
            "benchmark": (
                "Average healthcare data breach cost: $10.93M (IBM/Ponemon 2023, 13th consecutive year "
                "as highest-cost industry). OCR settlements in 2023: $4.2M (Banner Health), $1.3M "
                "(LA County DHS). Breaches affecting 500+ individuals are posted on the OCR 'Wall of Shame' "
                "and trigger mandatory investigation."
            ),
        })
        at_risk = math.ceil(employee_count * 0.10)
        line_items.append({
            "key": "lapsed_credential_risk",
            "label": "Lapsed Credential Risk",
            "low": at_risk * 1000,
            "high": at_risk * 10000,
            "affected_count": at_risk,
            "basis": "State licensing board penalties + CMS Conditions of Participation",
            "formula": (
                f"{at_risk} employees (10% of {employee_count}) \u00d7 $1,000\u2013$10,000 "
                f"per lapsed credential"
            ),
            "statute": (
                "State licensing boards (nursing, pharmacy, respiratory therapy, etc.) impose fines "
                "for practicing with lapsed credentials. CMS Conditions of Participation (\u00a7 482.12) "
                "require current credentials for all clinical staff. Employing unlicensed practitioners "
                "violates state practice acts and can trigger CMS survey deficiencies."
            ),
            "risk_context": (
                "Industry average lapse rate is 8\u201312% across clinical roles. A single lapsed credential "
                "discovered during a CMS survey can trigger Immediate Jeopardy status, leading to "
                "termination of Medicare/Medicaid participation. Most lapses are administrative (renewal "
                "delays) rather than competency-related, making tracking systems highly effective."
            ),
            "benchmark": (
                "State board fines: $500\u2013$5,000 per incident (varies by state). CMS Immediate Jeopardy "
                "citations: $3,050\u2013$10,000/day until corrected. Malpractice exposure for care delivered "
                "by unlicensed staff: insurer may deny coverage entirely, shifting full liability to employer."
            ),
        })

    total_low = sum(item["low"] for item in line_items)
    total_high = sum(item["high"] for item in line_items)
    return {"line_items": line_items, "total_low": total_low, "total_high": total_high}


def compute_er_cost_of_risk(
    pending: int,
    in_review: int,
    open_count: int,
    has_policy_violation: bool,
    has_discrepancy: bool,
) -> dict[str, Any]:
    """Estimate dollar exposure from open ER cases."""
    line_items: list[dict[str, Any]] = []
    merit_prob = 0.17

    boost_label = ""
    if has_policy_violation and has_discrepancy:
        boost_label = " (1.5x boost: policy violation + high discrepancy)"
    elif has_policy_violation:
        boost_label = " (1.5x boost: policy violation found)"
    elif has_discrepancy:
        boost_label = " (1.5x boost: high discrepancy found)"

    if pending > 0:
        low = round(75_000 * merit_prob * pending)
        high = round(200_000 * merit_prob * pending)
        line_items.append({
            "key": "pending_determination",
            "label": "Pending Determination Cases",
            "low": low,
            "high": high,
            "affected_count": pending,
            "basis": "EEOC median resolution \u00d7 17% merit probability",
            "formula": (
                f"{pending} cases \u00d7 $75K\u2013$200K range \u00d7 17% merit resolution rate"
                f"{boost_label}"
            ),
            "statute": (
                "Title VII, ADA, ADEA \u2014 enforced by EEOC. Pending determination cases have the highest "
                "exposure because no documented conclusion exists. Failure to investigate or delayed "
                "response is a primary factor in punitive damages awards. State FEPAs (e.g., CA DFEH, "
                "NY DHR) may impose additional penalties."
            ),
            "risk_context": (
                "Cases stuck in pending determination signal process failure. Every day without a "
                "documented investigation plan increases the likelihood of an EEOC complaint. "
                "If the complainant files externally before internal resolution, defense costs "
                "typically 3\u20135x the settlement value."
            ),
            "benchmark": (
                "Average EEOC resolution: $40,000\u2013$75,000 (pre-litigation). Average employment "
                "discrimination jury verdict: $217,000 (2023). EEOC secured $665M in monetary "
                "benefits in FY2023. Cases with documented, timely investigations settle for "
                "40\u201360% less than those without."
            ),
        })

    if in_review > 0:
        low = round(50_000 * merit_prob * in_review)
        high = round(150_000 * merit_prob * in_review)
        line_items.append({
            "key": "in_review",
            "label": "In-Review Cases",
            "low": low,
            "high": high,
            "affected_count": in_review,
            "basis": "EEOC median resolution \u00d7 17% merit probability",
            "formula": (
                f"{in_review} cases \u00d7 $50K\u2013$150K range \u00d7 17% merit resolution rate"
                f"{boost_label}"
            ),
            "statute": (
                "Title VII, ADA, ADEA, state equivalents. In-review cases have active investigation, "
                "reducing (but not eliminating) exposure. Key risk: incomplete documentation, "
                "interviewer bias, or failure to preserve evidence can convert a defensible case "
                "into a liability."
            ),
            "risk_context": (
                "In-review status means the process is working, but exposure persists until resolution. "
                "Ensure investigators are trained, interviews are documented, and evidence is preserved. "
                "Average time to resolve should be 30\u201345 days; longer investigations correlate with "
                "higher settlement costs."
            ),
            "benchmark": (
                "Median EEOC mediation settlement: $20,000\u2013$50,000. Cases resolved internally "
                "before EEOC filing cost 60\u201380% less than post-filing resolutions. "
                "Average employer litigation cost (through trial): $125,000\u2013$250,000."
            ),
        })

    if open_count > 0:
        low = round(25_000 * merit_prob * open_count)
        high = round(75_000 * merit_prob * open_count)
        line_items.append({
            "key": "open_cases",
            "label": "Open Cases",
            "low": low,
            "high": high,
            "affected_count": open_count,
            "basis": "EEOC median resolution \u00d7 17% merit probability",
            "formula": (
                f"{open_count} cases \u00d7 $25K\u2013$75K range \u00d7 17% merit resolution rate"
                f"{boost_label}"
            ),
            "statute": (
                "Title VII, ADA, ADEA, state equivalents. Open cases with documented intake and "
                "triage have the lowest individual exposure but aggregate risk scales with volume. "
                "Statutory filing deadlines (180\u2013300 days for EEOC) mean open cases can escalate "
                "to external complaints if not resolved promptly."
            ),
            "risk_context": (
                "Open cases at lower exposure individually, but high volume signals systemic issues "
                "that attract EEOC pattern-or-practice investigations. More than 5 open cases in "
                "similar categories (e.g., harassment, retaliation) is a red flag for class-wide exposure."
            ),
            "benchmark": (
                "EEOC pattern-or-practice settlements average $5M\u2013$20M. Individual open case "
                "resolution (pre-EEOC): $10,000\u2013$25,000 median. Volume of 10+ open cases "
                "increases systemic investigation risk by 3x (EEOC strategic enforcement data)."
            ),
        })

    if line_items and (has_policy_violation or has_discrepancy):
        for item in line_items:
            item["high"] = round(item["high"] * 1.5)

    total_low = sum(item["low"] for item in line_items)
    total_high = sum(item["high"] for item in line_items)
    return {"line_items": line_items, "total_low": total_low, "total_high": total_high}


def compute_incident_cost_of_risk(
    open_critical: int,
    open_high: int,
    open_medium: int,
) -> dict[str, Any]:
    """Estimate dollar exposure from open IR incidents using OSHA 2025 penalty ranges."""
    line_items: list[dict[str, Any]] = []

    if open_critical > 0:
        line_items.append({
            "key": "critical_incidents",
            "label": "Critical Incidents",
            "low": 16_550 * open_critical,
            "high": 165_514 * open_critical,
            "affected_count": open_critical,
            "basis": "OSHA willful/repeat violation penalty range (2025)",
            "formula": (
                f"{open_critical} incidents \u00d7 $16,550\u2013$165,514 per willful/repeat violation"
            ),
            "statute": (
                "OSH Act \u00a7 17, enforced by OSHA. Willful violations carry penalties of $11,524\u2013$165,514 "
                "per violation (2025 inflation-adjusted). Repeat violations within 5 years of a prior "
                "citation carry the same range. Criminal referral possible for willful violations "
                "causing employee death (up to $250K individual / $500K corporate fine + imprisonment)."
            ),
            "risk_context": (
                "Open critical incidents are active, unresolved hazards. OSHA can issue citations "
                "for each day a willful violation continues. A fatality or catastrophic event triggers "
                "mandatory OSHA investigation within 24 hours. Unresolved critical incidents also "
                "increase workers\u2019 compensation experience modification rates."
            ),
            "benchmark": (
                "OSHA's top penalties in 2023: Dollar Tree ($13.3M), Packers Sanitation ($1.5M). "
                "Average willful violation penalty: $145,000 (2023). Companies with open critical "
                "incidents that result in injury face additional negligence lawsuits averaging "
                "$1.2M\u2013$3.5M in settlements."
            ),
        })

    if open_high > 0:
        line_items.append({
            "key": "high_incidents",
            "label": "High Severity Incidents",
            "low": 5_000 * open_high,
            "high": 50_000 * open_high,
            "affected_count": open_high,
            "basis": "OSHA serious violation penalty range (2025)",
            "formula": (
                f"{open_high} incidents \u00d7 $5,000\u2013$50,000 per serious violation"
            ),
            "statute": (
                "OSH Act \u00a7 17(b), OSHA serious violations. Maximum penalty: $16,550 per violation "
                "(2025), but gravity-based adjustments and grouping can push effective cost to $50,000+. "
                "Serious violations are those where the employer knew or should have known of "
                "the hazard and it could cause death or serious harm."
            ),
            "risk_context": (
                "High severity incidents that remain open suggest inadequate hazard abatement. "
                "If OSHA finds the same hazard on a follow-up inspection, it escalates to a repeat "
                "violation (10x penalty increase). Prompt abatement with documented corrective "
                "actions can reduce proposed penalties by 25\u201360%."
            ),
            "benchmark": (
                "Average OSHA serious violation penalty: $4,500\u2013$7,000 (2023). However, "
                "high-gravity serious violations average $14,000+. Repeat serious violations "
                "average $82,000. Total OSHA penalties collected in FY2023: $266M across all violation types."
            ),
        })

    if open_medium > 0:
        line_items.append({
            "key": "medium_incidents",
            "label": "Medium Severity Incidents",
            "low": 1_000 * open_medium,
            "high": 16_550 * open_medium,
            "affected_count": open_medium,
            "basis": "OSHA other-than-serious violation penalty range (2025)",
            "formula": (
                f"{open_medium} incidents \u00d7 $1,000\u2013$16,550 per other-than-serious violation"
            ),
            "statute": (
                "OSH Act \u00a7 17(c), other-than-serious violations. These are hazards that have a "
                "direct relationship to safety/health but would not cause death or serious harm. "
                "Maximum: $16,550 per violation (2025). Failure-to-abate penalties: up to $16,550/day "
                "beyond the abatement deadline."
            ),
            "risk_context": (
                "Medium severity incidents individually carry lower penalties but can indicate "
                "broader safety culture issues. Multiple medium violations in the same inspection "
                "may be grouped into a higher-severity citation. Unabated medium violations escalate "
                "to failure-to-abate with daily penalties."
            ),
            "benchmark": (
                "Average other-than-serious penalty: $1,000\u2013$3,000 (2023). However, failure-to-abate "
                "daily penalties can accumulate to $100K+ if left unresolved. OSHA issues ~30,000 "
                "other-than-serious citations annually. Quick resolution typically reduces penalties 50%+."
            ),
        })

    total_low = sum(item["low"] for item in line_items)
    total_high = sum(item["high"] for item in line_items)
    return {"line_items": line_items, "total_low": total_low, "total_high": total_high}


async def compute_compliance_dimension(company_id: UUID, conn) -> DimensionResult:
    """Score compliance risk based on unread alerts and check recency."""
    row = await conn.fetchrow(
        """
        SELECT
          COUNT(*) FILTER (WHERE ca.severity = 'critical' AND ca.status = 'unread') AS critical_unread,
          COUNT(*) FILTER (WHERE ca.severity = 'warning'  AND ca.status = 'unread') AS warning_unread,
          (SELECT MAX(completed_at) FROM compliance_check_log WHERE company_id = $1) AS last_check
        FROM compliance_alerts ca
        JOIN business_locations bl ON bl.id = ca.location_id
        WHERE ca.company_id = $1
        """,
        company_id,
    )

    critical_unread = int(row["critical_unread"] or 0)
    warning_unread = int(row["warning_unread"] or 0)
    last_check: Optional[datetime] = row["last_check"]
    from ...core.services.compliance_service import _get_company_canonical_industry

    wage_violation_metrics = await _collect_minimum_wage_violation_metrics(company_id, conn)
    all_violations = wage_violation_metrics.pop("all_employee_violations", [])
    total_wage_violations = int(
        wage_violation_metrics["minimum_wage_violation_employee_count"] or 0
    )
    hourly_wage_violations = int(
        wage_violation_metrics["hourly_minimum_wage_violation_count"] or 0
    )
    salary_wage_violations = int(
        wage_violation_metrics["salary_minimum_wage_violation_count"] or 0
    )
    wage_violation_locations = int(
        wage_violation_metrics["locations_with_minimum_wage_violations"] or 0
    )

    score = 0
    factors = []

    critical_points = min(
        critical_unread * COMPLIANCE_CRITICAL_ALERT_POINTS,
        COMPLIANCE_CRITICAL_ALERT_CAP,
    )
    if critical_points > 0:
        score += critical_points
        factors.append(f"{critical_unread} unread critical alert{'s' if critical_unread != 1 else ''} (+{critical_points})")

    warning_points = min(
        warning_unread * COMPLIANCE_WARNING_ALERT_POINTS,
        COMPLIANCE_WARNING_ALERT_CAP,
    )
    if warning_points > 0:
        score += warning_points
        factors.append(f"{warning_unread} unread warning alert{'s' if warning_unread != 1 else ''} (+{warning_points})")

    wage_points = min(
        total_wage_violations * COMPLIANCE_WAGE_VIOLATION_POINTS,
        COMPLIANCE_WAGE_VIOLATION_CAP,
    )
    if wage_points > 0:
        awarded = min(wage_points, max(0, 100 - score))
        score += awarded
        factors.append(
            f"{total_wage_violations} employee{'s' if total_wage_violations != 1 else ''} below minimum wage across "
            f"{wage_violation_locations} location{'s' if wage_violation_locations != 1 else ''} (+{awarded})"
        )

    location_points = min(
        wage_violation_locations * COMPLIANCE_WAGE_LOCATION_POINTS,
        COMPLIANCE_WAGE_LOCATION_CAP,
    )
    if location_points > 0 and score < 100:
        awarded = min(location_points, max(0, 100 - score))
        score += awarded
        factors.append(
            f"{wage_violation_locations} location{'s' if wage_violation_locations != 1 else ''} with active wage violations (+{awarded})"
        )

    if hourly_wage_violations > 0:
        factors.append(
            f"{hourly_wage_violations} hourly employee{'s' if hourly_wage_violations != 1 else ''} below local minimum wage"
        )
    if salary_wage_violations > 0:
        factors.append(
            f"{salary_wage_violations} salaried employee{'s' if salary_wage_violations != 1 else ''} below exempt salary minimum"
        )

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

    canonical_industry = await _get_company_canonical_industry(conn, company_id)
    is_healthcare = canonical_industry == "healthcare"
    total_employees = await conn.fetchval(
        "SELECT COUNT(*) FROM employees WHERE org_id = $1 AND termination_date IS NULL",
        company_id,
    )
    compliance_cost = compute_compliance_cost_of_risk(
        all_violations, int(total_employees or 0), is_healthcare
    )

    return DimensionResult(
        score=score,
        band=_band(score),
        factors=factors,
        raw_data={
            "critical_unread": critical_unread,
            "warning_unread": warning_unread,
            "last_check": last_check.isoformat() if last_check else None,
            **wage_violation_metrics,
            "cost_of_risk": compliance_cost,
            "is_healthcare": is_healthcare,
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

    incident_cost = compute_incident_cost_of_risk(critical, high, medium)

    return DimensionResult(
        score=score,
        band=_band(score),
        factors=factors,
        raw_data={
            "open_critical": critical,
            "open_high": high,
            "open_medium": medium,
            "open_low": low,
            "cost_of_risk": incident_cost,
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
        pts = min(pending * ER_PENDING_POINTS, ER_PENDING_CAP)
        score += pts
        factors.append(f"{pending} case{'s' if pending != 1 else ''} pending determination (+{pts})")

    if in_review > 0:
        pts = min(in_review * ER_IN_REVIEW_POINTS, min(ER_IN_REVIEW_CAP, max(0, 100 - score)))
        score += pts
        factors.append(f"{in_review} case{'s' if in_review != 1 else ''} in review (+{pts})")

    if open_cases > 0:
        pts = min(open_cases * ER_OPEN_POINTS, min(ER_OPEN_CAP, max(0, 100 - score)))
        score += pts
        factors.append(f"{open_cases} open case{'s' if open_cases != 1 else ''} (+{pts})")

    if has_major_policy_violation and score < 100:
        pts = min(ER_MAJOR_POLICY_POINTS, 100 - score)
        score += pts
        factors.append(f"Major policy violation found in analysis (+{pts})")

    if has_high_discrepancy and score < 100:
        pts = min(ER_HIGH_DISCREPANCY_POINTS, 100 - score)
        score += pts
        factors.append(f"High severity discrepancy in analysis (+{pts})")

    score = min(score, 100)
    if not factors:
        factors.append("No open ER cases")

    # Fetch individual non-closed cases for action items
    case_rows = await conn.fetch(
        """
        SELECT id, title, status, category, created_at
        FROM er_cases
        WHERE company_id = $1 AND status != 'closed'
        ORDER BY
            CASE status
                WHEN 'pending_determination' THEN 1
                WHEN 'in_review' THEN 2
                ELSE 3
            END,
            created_at DESC
        LIMIT 10
        """,
        company_id,
    )
    open_case_details = [
        {
            "case_id": str(row["id"]),
            "title": row["title"],
            "status": row["status"],
            "category": row["category"],
            "created_at": row["created_at"].isoformat() if row["created_at"] else None,
        }
        for row in case_rows
    ]

    er_cost = compute_er_cost_of_risk(
        pending, in_review, open_cases,
        has_major_policy_violation, has_high_discrepancy,
    )

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
            "open_cases": open_case_details,
            "cost_of_risk": er_cost,
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
          AND jl.expected_effective_date > CURRENT_DATE
        """,
        company_id,
    )

    today = datetime.now(timezone.utc).date()
    within_30 = 0
    within_90 = 0
    within_180 = 0

    for row in rows:
        effective_date = row["expected_effective_date"]
        if effective_date is None:
            continue
        if isinstance(effective_date, datetime):
            effective_date = effective_date.date()
        if not isinstance(effective_date, date):
            continue

        days_until = (effective_date - today).days
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
    """Parse JSON from LLM response, handling markdown fences and trailing text."""
    text = text.strip()
    if text.startswith("```json"):
        text = text[7:]
    elif text.startswith("```"):
        text = text[3:]
    if text.endswith("```"):
        text = text[:-3]
    text = text.strip()
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        # Gemini sometimes appends extra text after valid JSON — extract first object
        decoder = json.JSONDecoder()
        result, _ = decoder.raw_decode(text)
        return result


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
        import os
        api_key = os.getenv("GEMINI_API_KEY") or settings.gemini_api_key
        if not api_key:
            logger.warning("No Gemini API key configured — skipping recommendations")
            return empty
        client = genai.Client(api_key=api_key)

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


DEFAULT_WEIGHTS: dict[str, float] = {
    "compliance": 0.30,
    "incidents": 0.25,
    "er_cases": 0.25,
    "workforce": 0.15,
    "legislative": 0.05,
}


async def compute_risk_assessment(
    company_id: UUID,
    weights: Optional[dict[str, float]] = None,
) -> RiskAssessmentResult:
    """Compute full risk assessment for a company across all 5 dimensions."""
    w = {**DEFAULT_WEIGHTS, **(weights or {})}

    async with get_connection() as conn:
        compliance = await compute_compliance_dimension(company_id, conn)
        incidents = await compute_incident_dimension(company_id, conn)
        er = await compute_er_dimension(company_id, conn)
        workforce = await compute_workforce_dimension(company_id, conn)
        legislative = await compute_legislative_dimension(company_id, conn)

    overall = int(
        compliance.score * w["compliance"]
        + incidents.score * w["incidents"]
        + er.score * w["er_cases"]
        + workforce.score * w["workforce"]
        + legislative.score * w["legislative"]
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
