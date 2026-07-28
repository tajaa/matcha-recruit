"""Cost-of-risk models -- expected annual loss by dimension (compliance, ER,
incident). Distinct from the dimension scores: these are dollars, those are
0-100.
"""
import logging
import math
from typing import Any

from ._shared import _exempt_threshold_sentence, _stamp_sourcing

logger = logging.getLogger(__name__)


def compute_compliance_cost_of_risk(
    all_violations: list[dict[str, Any]],
    employee_count: int,
    is_healthcare: bool,
    credential_at_risk: list[dict[str, str]] | None = None,
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
            "affected_employees": [
                {"name": v.get("employee_name", "Unknown"), "detail": f"${v.get('shortfall', 0):.2f}/hr below {v.get('location_state', '')} minimum"}
                for v in hourly[:10]
            ],
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
            "affected_employees": [
                {"name": v.get("employee_name", "Unknown"), "detail": f"Salary ${v.get('pay_rate', 0):,.0f} below {v.get('location_state', '')} exempt threshold"}
                for v in exempt[:10]
            ],
            "basis": "FLSA \u00a7 207, overtime liability for misclassified exempt employees",
            "formula": (
                f"{len(exempt)} employees \u00d7 avg salary ${avg_salary:,.0f} \u00f7 2,080 hrs "
                f"\u00d7 1.5x OT rate \u00d7 5\u201310 OT hrs/wk \u00d7 52 wks \u00d7 2\u20133yr \u00d7 2x damages"
            ),
            # The thresholds are stated from the rows the violation was actually
            # DETECTED against, not from a literal. The old copy read "The 2024
            # DOL salary threshold is $43,888 ($58,656 effective Jan 2025). State
            # thresholds may be higher (CA: $66,560, NY: $58,500)" \u2014 hardcoded,
            # two years stale, and contradicted by our own catalog (CA reads
            # $70,304), on a page a customer is asked to act on. A figure that
            # can go stale in a string literal will.
            "statute": (
                "FLSA \u00a7 207 requires overtime pay for non-exempt employees. Enforced by DOL WHD. "
                "Employees misclassified as exempt are owed 1.5x their effective hourly rate for all "
                "overtime worked. "
                + _exempt_threshold_sentence(exempt)
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
            # UNSOURCED — see `sourced` below. These per-record figures and the
            # tier amounts in `statute` are hand-entered literals. The authority
            # is 45 CFR 102.3 ("Table 1 to § 102.3"), which we can reach and
            # which carries a "2025 Maximum adjusted penalty ($)" column, but its
            # <TABLE> shape needs a parser the prose-shaped OSHA one doesn't
            # cover. Until that lands these stay literals and say so, rather than
            # borrowing the credibility of the figures that ARE sourced.
            "low": employee_count * 145,
            "high": employee_count * 1452,
            "affected_count": employee_count,
            "affected_employees": [{"name": "All employees", "detail": f"All {employee_count} employee records contain PHI (benefits, workers' comp, FMLA)"}],
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
        cred_list = credential_at_risk or []
        at_risk = len(cred_list) if cred_list else math.ceil(employee_count * 0.10)
        line_items.append({
            "key": "lapsed_credential_risk",
            "label": "Lapsed Credential Risk",
            "low": at_risk * 1000,
            "high": at_risk * 10000,
            "affected_count": at_risk,
            "affected_employees": cred_list[:10] if cred_list else [{"name": f"~{at_risk} estimated", "detail": "Based on industry 8–12% lapse rate (no credential data uploaded yet)"}],
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
    return {"line_items": _stamp_sourcing(line_items),
            "total_low": total_low, "total_high": total_high}


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
    return {"line_items": _stamp_sourcing(line_items),
            "total_low": total_low, "total_high": total_high}


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
    return {"line_items": _stamp_sourcing(line_items),
            "total_low": total_low, "total_high": total_high}
