"""Flight-Risk Composite Score (§3.3 of QSR_RETENTION_PLAN.md).

Mirror of the wage-gap widget pattern (§3.1) but predictive instead of
descriptive: score 0-100 per active employee combining six signals
*we already have*, with per-factor contribution + narrative so the
operator knows *why* the number moved.

Six inputs (initial weights — tunable consts at top of file):
    1. Wage delta vs market p50          → reuses wage_benchmark_service
    2. Tenure × role-typical-quit-curve  → from employees.start_date
    3. Open ER case involvement          → er_cases.involved_employees JSONB
    4. Recent IR incident involvement    → ir_incidents.involved_employee_ids
    5. Cohort baseline deviation         → cohort_analysis_service
    6. Manager flight-risk rollup        → derived inline (peer turnover)

Honest about what it doesn't know:
  - No pulse-survey sentiment (gated by §4.1)
  - No schedule volatility (gated by §3.2 + time-punch ingest)
  - No 1:1 cadence (gated by §4.2)
These are additive when those upstream features ship; the score works
on six signals and a 7th becomes a reweight, not a rewrite.
"""

from __future__ import annotations

import json
import logging
from dataclasses import dataclass, asdict
from datetime import date, datetime, timedelta, timezone
from typing import Any, Optional
from uuid import UUID

from ...database import get_connection
from .wage_benchmark_service import (
    REPLACEMENT_COST_PER_EMPLOYEE,
    classify_title,
    _fetch_benchmark_index,
)

logger = logging.getLogger(__name__)


# ─────────────────────────────────────────────────────────────────────────────
# Tunables — all weights and thresholds in one place for easy backtest tuning
# ─────────────────────────────────────────────────────────────────────────────

# Per-signal max contribution. Sum must equal 100.
W_WAGE = 30
W_TENURE = 20
W_ER = 15
W_IR = 10
W_COHORT = 15
W_MANAGER = 10

if W_WAGE + W_TENURE + W_ER + W_IR + W_COHORT + W_MANAGER != 100:
    raise ValueError("Flight-risk signal weights must sum to 100")

# Tier bands — tunable. Critical = walk away from this person fast.
TIER_LOW_MAX = 39
TIER_ELEVATED_MAX = 59
TIER_HIGH_MAX = 79
# anything ≥80 = critical

# Tenure quit-curve buckets (months → relative quit risk multiplier 0.0-1.0).
# Literature: QSR turnover concentrated in 0-6 months (the "first 90 days"
# cliff), declines through year 1, plateaus thereafter.
TENURE_BUCKETS: list[tuple[int, float]] = [
    (1, 0.50),    # 0-1 month: high but not peak (still in honeymoon)
    (3, 1.00),    # 1-3 months: peak quit window
    (6, 0.85),    # 3-6 months: still high
    (12, 0.55),   # 6-12 months: declining
    (24, 0.30),   # 1-2 years: stable
    (60, 0.15),   # 2-5 years: anchored
]

# Wage signal — fraction below p50 (negative = below). 30% below = full weight.
WAGE_FULL_PENALTY_THRESHOLD = -0.30

# Manager rollup window for peer turnover lookback (days).
MANAGER_ROLLUP_DAYS = 365


# ─────────────────────────────────────────────────────────────────────────────
# Dataclasses
# ─────────────────────────────────────────────────────────────────────────────


@dataclass
class FlightRiskFactor:
    name: str                # 'wage_gap', 'tenure', 'er_case', 'ir_incident', 'cohort', 'manager'
    contribution: int        # 0..max-weight for that signal
    color: str               # 'green' | 'yellow' | 'red'
    narrative: str           # human-readable: "$1.20/hr below market p50 in Denver metro"
    value: Optional[float] = None    # raw signal (e.g. delta_pct, tenure_months)


@dataclass
class FlightRiskResult:
    employee_id: str
    name: str
    score: int                       # 0-100
    tier: str                        # low | elevated | high | critical
    top_factor: str                  # name of highest-contributing factor
    factors: list[FlightRiskFactor]
    expected_replacement_cost: int   # = REPLACEMENT_COST_PER_EMPLOYEE if score≥high else 0
    computed_at: datetime
    # Internal-only (excluded from API responses; used by compute_company_summary
    # to skip a second DB round-trip).
    _start_date: Optional[date] = None
    _manager_id: Optional[UUID] = None


@dataclass
class FlightRiskCompanySummary:
    """Operator-dashboard widget aggregate.

    Companion to wage-gap widget: same dollar-math language. Critical+high
    bucket counts are the actionable headline. `expected_loss_at_replacement`
    is upper-bound (assume every flagged person leaves) — same honest framing
    as wage_benchmark_service.max_replacement_cost_exposure.
    """
    employees_evaluated: int
    critical_count: int
    high_count: int
    elevated_count: int
    low_count: int
    expected_loss_at_replacement: int     # (critical + high) × replacement cost
    top_driver: Optional[str]             # most-common top_factor across high/critical
    top_driver_count: int
    early_tenure_count: int               # of high+critical, how many in 30-180 day window
    manager_hotspots: list[dict[str, Any]]  # [{manager_id, manager_name, count}]


# ─────────────────────────────────────────────────────────────────────────────
# Signal scorers — each returns FlightRiskFactor
# ─────────────────────────────────────────────────────────────────────────────


def _color_from_pct_of_max(contribution: int, weight: int) -> str:
    if weight == 0:
        return "green"
    pct = contribution / weight
    if pct >= 0.66:
        return "red"
    if pct >= 0.33:
        return "yellow"
    return "green"


def _score_wage(
    delta_percent: Optional[float],
    delta_dollars: Optional[float],
    soc_label: Optional[str],
    benchmark_area: Optional[str],
) -> FlightRiskFactor:
    if delta_percent is None:
        return FlightRiskFactor(
            name="wage_gap",
            contribution=0,
            color="green",
            narrative="No wage benchmark available (job title unclassifiable or missing pay rate)",
        )
    # Below market = penalty, at-or-above = 0.
    if delta_percent >= 0:
        return FlightRiskFactor(
            name="wage_gap",
            contribution=0,
            color="green",
            narrative=f"At or above market p50 ({delta_percent * 100:+.1f}%) for {soc_label or 'role'}",
            value=round(delta_percent, 4),
        )
    # Linear penalty between 0 and WAGE_FULL_PENALTY_THRESHOLD.
    severity = min(1.0, delta_percent / WAGE_FULL_PENALTY_THRESHOLD)  # both negative → positive
    contribution = int(round(severity * W_WAGE))
    dollars_str = (
        f"${abs(delta_dollars):.2f}/hr below market p50"
        if delta_dollars is not None else f"{delta_percent * 100:.1f}% below market p50"
    )
    where = f" in {benchmark_area}" if benchmark_area else ""
    return FlightRiskFactor(
        name="wage_gap",
        contribution=contribution,
        color=_color_from_pct_of_max(contribution, W_WAGE),
        narrative=f"{dollars_str}{where} for {soc_label or 'role'}",
        value=round(delta_percent, 4),
    )


def _score_tenure(start_date: Optional[date], today: date) -> FlightRiskFactor:
    if start_date is None:
        return FlightRiskFactor(
            name="tenure",
            contribution=0,
            color="green",
            narrative="No start date on record",
        )
    if isinstance(start_date, datetime):
        start_date = start_date.date()
    months = (today.year - start_date.year) * 12 + (today.month - start_date.month)
    days = (today - start_date).days
    multiplier = 0.10  # tail
    for bucket_max, mult in TENURE_BUCKETS:
        if months < bucket_max:
            multiplier = mult
            break
    contribution = int(round(multiplier * W_TENURE))
    if days < 30:
        narrative = f"{days} days in role — onboarding phase (low quit rate)"
    elif months < 6:
        narrative = f"{months} months in role — peak QSR quit window (30-180 days)"
    elif months < 12:
        narrative = f"{months} months in role — declining quit risk"
    else:
        narrative = f"{months} months tenure — anchored"
    return FlightRiskFactor(
        name="tenure",
        contribution=contribution,
        color=_color_from_pct_of_max(contribution, W_TENURE),
        narrative=narrative,
        value=float(months),
    )


def _score_er(open_count: int, recent_closed_count: int) -> FlightRiskFactor:
    if open_count == 0 and recent_closed_count == 0:
        return FlightRiskFactor(
            name="er_case",
            contribution=0,
            color="green",
            narrative="No ER case involvement in last 12 months",
        )
    # Open case = full weight; recent closed = half.
    contribution = min(W_ER, open_count * W_ER + recent_closed_count * (W_ER // 2))
    if open_count > 0:
        narrative = f"{open_count} open ER case(s) involving employee"
    else:
        narrative = f"{recent_closed_count} ER case(s) closed within last 90 days"
    return FlightRiskFactor(
        name="er_case",
        contribution=contribution,
        color=_color_from_pct_of_max(contribution, W_ER),
        narrative=narrative,
        value=float(open_count + recent_closed_count),
    )


def _score_ir(incident_count_90d: int) -> FlightRiskFactor:
    if incident_count_90d == 0:
        return FlightRiskFactor(
            name="ir_incident",
            contribution=0,
            color="green",
            narrative="No IR incident involvement in last 90 days",
        )
    # 1 incident = half weight, 2+ = full.
    contribution = W_IR if incident_count_90d >= 2 else W_IR // 2
    return FlightRiskFactor(
        name="ir_incident",
        contribution=contribution,
        color=_color_from_pct_of_max(contribution, W_IR),
        narrative=f"{incident_count_90d} IR incident(s) involving employee in last 90 days",
        value=float(incident_count_90d),
    )


def _score_cohort(risk_concentration: float, cohort_label: str) -> FlightRiskFactor:
    # risk_concentration = cohort's % of risk events / cohort's % of headcount.
    # 1.0 = average; >2.0 = hot-spot per cohort_analysis_service flag rules.
    if risk_concentration <= 1.0:
        return FlightRiskFactor(
            name="cohort",
            contribution=0,
            color="green",
            narrative=f"Cohort {cohort_label} at or below average risk concentration",
            value=round(risk_concentration, 2),
        )
    # Linear from 1.0 (0%) → 3.0 (100% of weight). Cap at 3.0.
    severity = min(1.0, (risk_concentration - 1.0) / 2.0)
    contribution = int(round(severity * W_COHORT))
    return FlightRiskFactor(
        name="cohort",
        contribution=contribution,
        color=_color_from_pct_of_max(contribution, W_COHORT),
        narrative=(
            f"Tenure cohort {cohort_label} runs {risk_concentration:.1f}x average "
            f"risk concentration"
        ),
        value=round(risk_concentration, 2),
    )


def _score_manager(
    manager_id: Optional[UUID],
    manager_name: Optional[str],
    peer_turnover_pct: Optional[float],
) -> FlightRiskFactor:
    if manager_id is None or peer_turnover_pct is None:
        return FlightRiskFactor(
            name="manager",
            contribution=0,
            color="green",
            narrative="No manager assigned or insufficient peer data",
        )
    # Annualized turnover %. <50% = green, 50-100% = ramp, ≥100% = full.
    if peer_turnover_pct < 50:
        return FlightRiskFactor(
            name="manager",
            contribution=0,
            color="green",
            narrative=(
                f"Manager {manager_name or 'unassigned'} — {peer_turnover_pct:.0f}% "
                "annualized peer turnover (below industry average)"
            ),
            value=round(peer_turnover_pct, 1),
        )
    severity = min(1.0, (peer_turnover_pct - 50) / 50)
    contribution = int(round(severity * W_MANAGER))
    return FlightRiskFactor(
        name="manager",
        contribution=contribution,
        color=_color_from_pct_of_max(contribution, W_MANAGER),
        narrative=(
            f"Manager {manager_name or 'unassigned'} — {peer_turnover_pct:.0f}% "
            "annualized peer turnover (hot-spot)"
        ),
        value=round(peer_turnover_pct, 1),
    )


# ─────────────────────────────────────────────────────────────────────────────
# Bulk computation — single pass over the company roster
# ─────────────────────────────────────────────────────────────────────────────


def _tier_for_score(score: int) -> str:
    if score <= TIER_LOW_MAX:
        return "low"
    if score <= TIER_ELEVATED_MAX:
        return "elevated"
    if score <= TIER_HIGH_MAX:
        return "high"
    return "critical"


def _quarter_label(dt: date) -> str:
    q = (dt.month - 1) // 3 + 1
    return f"Q{q}-{dt.year}"


def _tenure_band(start_date: date, today: date) -> str:
    months = (today.year - start_date.year) * 12 + (today.month - start_date.month)
    if months < 6:
        return "0-6mo"
    if months < 12:
        return "6-12mo"
    if months < 24:
        return "1-2yr"
    if months < 60:
        return "2-5yr"
    return "5yr+"


async def compute_for_company(company_id: UUID) -> list[FlightRiskResult]:
    """Score every active employee for the company. Single roster query
    plus a handful of aggregate queries — all in-memory after that."""
    today = date.today()
    # er_cases.closed_at and ir_incidents.occurred_at are TIMESTAMP (naive);
    # asyncpg rejects tz-aware values on those columns.
    now = datetime.utcnow()
    ninety_days_ago = now - timedelta(days=90)
    twelve_months_ago = now - timedelta(days=365)

    async with get_connection() as conn:
        emp_rows = await conn.fetch(
            """
            SELECT id, first_name, last_name, job_title, work_city, work_state,
                   pay_rate, pay_classification, start_date, manager_id
            FROM employees
            WHERE org_id = $1 AND termination_date IS NULL
            """,
            company_id,
        )
        if not emp_rows:
            return []

        # ── ER cases: count open + recent-closed per employee ──────────────
        er_open_by_emp: dict[UUID, int] = {}
        er_recent_closed_by_emp: dict[UUID, int] = {}
        er_rows = await conn.fetch(
            """
            SELECT id, status, involved_employees, closed_at
            FROM er_cases
            WHERE company_id = $1
              AND (
                status IN ('open', 'in_review', 'pending_determination')
                OR (status = 'closed' AND closed_at >= $2)
              )
            """,
            company_id, ninety_days_ago,
        )
        for row in er_rows:
            involved = row["involved_employees"]
            if isinstance(involved, str):
                try:
                    involved = json.loads(involved)
                except (json.JSONDecodeError, TypeError):
                    involved = []
            if not isinstance(involved, list):
                continue
            for entry in involved:
                if not isinstance(entry, dict):
                    continue
                eid_raw = entry.get("employee_id")
                if not eid_raw:
                    continue
                try:
                    eid = UUID(str(eid_raw))
                except (ValueError, TypeError):
                    continue
                if row["status"] == "closed":
                    er_recent_closed_by_emp[eid] = er_recent_closed_by_emp.get(eid, 0) + 1
                else:
                    er_open_by_emp[eid] = er_open_by_emp.get(eid, 0) + 1

        # ── IR incidents: count involvement in last 90 days per employee ──
        ir_count_by_emp: dict[UUID, int] = {}
        ir_rows = await conn.fetch(
            """
            SELECT involved_employee_ids
            FROM ir_incidents
            WHERE company_id = $1 AND occurred_at >= $2
            """,
            company_id, ninety_days_ago,
        )
        for row in ir_rows:
            for eid in (row["involved_employee_ids"] or []):
                ir_count_by_emp[eid] = ir_count_by_emp.get(eid, 0) + 1

        # ── Manager peer turnover: terminations in last 365d / active count
        # per manager_id. Counts terminations inside the window divided by
        # current direct-report headcount + terminations (rough proxy for
        # average headcount over the year).
        manager_terms = await conn.fetch(
            """
            SELECT manager_id, COUNT(*) AS term_count
            FROM employees
            WHERE org_id = $1
              AND termination_date >= $2
              AND manager_id IS NOT NULL
            GROUP BY manager_id
            """,
            company_id, twelve_months_ago.date(),
        )
        manager_term_count: dict[UUID, int] = {
            row["manager_id"]: int(row["term_count"]) for row in manager_terms
        }
        manager_active_count: dict[UUID, int] = {}
        for row in emp_rows:
            mid = row["manager_id"]
            if mid:
                manager_active_count[mid] = manager_active_count.get(mid, 0) + 1

        manager_turnover_pct: dict[UUID, float] = {}
        for mid, terms in manager_term_count.items():
            active = manager_active_count.get(mid, 0)
            denom = active + terms  # rough avg headcount
            if denom == 0:
                continue
            manager_turnover_pct[mid] = (terms / denom) * 100.0

        # Manager names lookup
        manager_ids = {row["manager_id"] for row in emp_rows if row["manager_id"]}
        manager_name_by_id: dict[UUID, str] = {}
        if manager_ids:
            mgr_rows = await conn.fetch(
                """
                SELECT id, first_name, last_name FROM employees
                WHERE id = ANY($1::uuid[])
                """,
                list(manager_ids),
            )
            for row in mgr_rows:
                fn = row["first_name"] or ""
                ln = row["last_name"] or ""
                manager_name_by_id[row["id"]] = f"{fn} {ln}".strip() or "Unassigned"

    # ── Wage benchmark prefetch ───────────────────────────────────────────
    classified: dict[UUID, tuple[str, str]] = {}
    needed_socs: set[str] = set()
    needed_states: set[str] = set()
    for row in emp_rows:
        if row["pay_classification"] != "hourly" or not row["pay_rate"]:
            continue
        cls = classify_title(row["job_title"])
        if not cls:
            continue
        soc_code, soc_label = cls
        classified[row["id"]] = (soc_code, soc_label)
        needed_socs.add(soc_code)
        if row["work_state"]:
            needed_states.add(row["work_state"].upper())

    bm_index = await _fetch_benchmark_index(needed_socs, needed_states)

    # ── Cohort risk concentration by tenure band (cheap proxy for full
    # cohort analysis — share signal with what cohort_analysis_service does
    # but compute inline to avoid an extra query path)
    cohort_total_risk = 0
    cohort_headcount: dict[str, int] = {}
    cohort_risk_count: dict[str, int] = {}
    for row in emp_rows:
        if not row["start_date"]:
            label = "Unknown"
        else:
            sd = row["start_date"]
            if isinstance(sd, datetime):
                sd = sd.date()
            label = _tenure_band(sd, today)
        cohort_headcount[label] = cohort_headcount.get(label, 0) + 1
        risk_events = (
            er_open_by_emp.get(row["id"], 0) + ir_count_by_emp.get(row["id"], 0)
        )
        cohort_risk_count[label] = cohort_risk_count.get(label, 0) + risk_events
        cohort_total_risk += risk_events

    total_headcount = len(emp_rows)
    cohort_concentration: dict[str, float] = {}
    for label, hc in cohort_headcount.items():
        if cohort_total_risk == 0 or hc == 0:
            cohort_concentration[label] = 0.0
            continue
        cohort_risk_pct = (cohort_risk_count[label] / cohort_total_risk) * 100.0
        cohort_headcount_pct = (hc / total_headcount) * 100.0
        cohort_concentration[label] = (
            cohort_risk_pct / cohort_headcount_pct if cohort_headcount_pct > 0 else 0.0
        )

    # ── Score every employee ──────────────────────────────────────────────
    results: list[FlightRiskResult] = []
    for row in emp_rows:
        eid = row["id"]
        name = f"{row['first_name'] or ''} {row['last_name'] or ''}".strip() or "Unknown"

        # Wage factor
        wage_factor = _score_wage(None, None, None, None)
        if eid in classified:
            soc_code, soc_label = classified[eid]
            bm = bm_index.pick(soc_code, row["work_city"], row["work_state"])
            if bm and bm.hourly_p50:
                pay = float(row["pay_rate"])
                market = float(bm.hourly_p50)
                delta_dollars = pay - market
                delta_pct = delta_dollars / market if market > 0 else 0.0
                wage_factor = _score_wage(
                    delta_pct, delta_dollars, soc_label,
                    bm.area_name or (bm.state or "national"),
                )

        # Tenure factor
        tenure_factor = _score_tenure(row["start_date"], today)

        # ER factor
        er_factor = _score_er(
            er_open_by_emp.get(eid, 0),
            er_recent_closed_by_emp.get(eid, 0),
        )

        # IR factor
        ir_factor = _score_ir(ir_count_by_emp.get(eid, 0))

        # Cohort factor
        if not row["start_date"]:
            cohort_label = "Unknown"
        else:
            sd = row["start_date"]
            if isinstance(sd, datetime):
                sd = sd.date()
            cohort_label = _tenure_band(sd, today)
        cohort_factor = _score_cohort(
            cohort_concentration.get(cohort_label, 0.0), cohort_label,
        )

        # Manager factor
        mid = row["manager_id"]
        manager_factor = _score_manager(
            mid,
            manager_name_by_id.get(mid) if mid else None,
            manager_turnover_pct.get(mid) if mid else None,
        )

        factors = [
            wage_factor, tenure_factor, er_factor, ir_factor,
            cohort_factor, manager_factor,
        ]
        score = sum(f.contribution for f in factors)
        score = max(0, min(100, score))
        tier = _tier_for_score(score)
        top = max(factors, key=lambda f: f.contribution)

        sd_val = row["start_date"]
        if isinstance(sd_val, datetime):
            sd_val = sd_val.date()
        results.append(FlightRiskResult(
            employee_id=str(eid),
            name=name,
            score=score,
            tier=tier,
            top_factor=top.name,
            factors=factors,
            expected_replacement_cost=(
                REPLACEMENT_COST_PER_EMPLOYEE if tier in ("high", "critical") else 0
            ),
            computed_at=now,
            _start_date=sd_val,
            _manager_id=row["manager_id"],
        ))

    # Highest risk first.
    results.sort(key=lambda r: -r.score)
    return results


# ─────────────────────────────────────────────────────────────────────────────
# Company summary — for the dashboard widget
# ─────────────────────────────────────────────────────────────────────────────


async def compute_company_summary(company_id: UUID) -> FlightRiskCompanySummary:
    results = await compute_for_company(company_id)
    if not results:
        return FlightRiskCompanySummary(
            employees_evaluated=0,
            critical_count=0, high_count=0, elevated_count=0, low_count=0,
            expected_loss_at_replacement=0,
            top_driver=None, top_driver_count=0,
            early_tenure_count=0,
            manager_hotspots=[],
        )

    counts = {"low": 0, "elevated": 0, "high": 0, "critical": 0}
    for r in results:
        counts[r.tier] += 1
    flagged = [r for r in results if r.tier in ("high", "critical")]
    expected_loss = len(flagged) * REPLACEMENT_COST_PER_EMPLOYEE

    # Top driver among flagged employees
    driver_counts: dict[str, int] = {}
    for r in flagged:
        driver_counts[r.top_factor] = driver_counts.get(r.top_factor, 0) + 1
    top_driver = None
    top_driver_count = 0
    if driver_counts:
        top_driver, top_driver_count = max(driver_counts.items(), key=lambda kv: kv[1])

    # Early-tenure window count (for the 30-180 day pitch).
    # Reuse start_date carried on FlightRiskResult — saves a DB round-trip.
    today = date.today()
    early_count = 0
    for r in flagged:
        if r._start_date is None:
            continue
        days = (today - r._start_date).days
        if 30 <= days <= 180:
            early_count += 1

    # Manager hot-spots — managers with ≥2 flagged direct reports
    mgr_flagged: dict[UUID, int] = {}
    for r in flagged:
        if r._manager_id:
            mgr_flagged[r._manager_id] = mgr_flagged.get(r._manager_id, 0) + 1
    hotspots = []
    hotspot_ids = [mid for mid, c in mgr_flagged.items() if c >= 2]
    if hotspot_ids:
        async with get_connection() as conn:
            mgr_rows = await conn.fetch(
                """
                SELECT id, first_name, last_name FROM employees
                WHERE id = ANY($1::uuid[])
                """,
                hotspot_ids,
            )
        name_by_id = {
            row["id"]: f"{row['first_name'] or ''} {row['last_name'] or ''}".strip() or "Unassigned"
            for row in mgr_rows
        }
        for mid in hotspot_ids:
            hotspots.append({
                "manager_id": str(mid),
                "manager_name": name_by_id.get(mid, "Unknown"),
                "flagged_count": mgr_flagged[mid],
            })
        hotspots.sort(key=lambda h: -h["flagged_count"])

    return FlightRiskCompanySummary(
        employees_evaluated=len(results),
        critical_count=counts["critical"],
        high_count=counts["high"],
        elevated_count=counts["elevated"],
        low_count=counts["low"],
        expected_loss_at_replacement=expected_loss,
        top_driver=top_driver,
        top_driver_count=top_driver_count,
        early_tenure_count=early_count,
        manager_hotspots=hotspots[:5],
    )


# ─────────────────────────────────────────────────────────────────────────────
# Snapshot persistence — for trend/backtest
# ─────────────────────────────────────────────────────────────────────────────


async def snapshot_company(company_id: UUID) -> int:
    """Compute + persist scores for every active employee. Returns row count."""
    results = await compute_for_company(company_id)
    if not results:
        return 0
    rows = [
        (
            company_id,
            UUID(r.employee_id),
            r.score,
            r.tier,
            json.dumps([asdict(f) for f in r.factors]),
            r.top_factor,
            r.computed_at,
        )
        for r in results
    ]
    async with get_connection() as conn:
        await conn.executemany(
            """
            INSERT INTO flight_risk_snapshots
              (org_id, employee_id, score, tier, factors, top_factor, computed_at)
            VALUES ($1, $2, $3, $4, $5::jsonb, $6, $7)
            """,
            rows,
        )
    return len(rows)


async def get_employee_history(
    company_id: UUID, employee_id: UUID, limit: int = 30,
) -> list[dict[str, Any]]:
    async with get_connection() as conn:
        rows = await conn.fetch(
            """
            SELECT score, tier, top_factor, computed_at
            FROM flight_risk_snapshots
            WHERE org_id = $1 AND employee_id = $2
            ORDER BY computed_at DESC
            LIMIT $3
            """,
            company_id, employee_id, limit,
        )
    return [
        {
            "score": row["score"],
            "tier": row["tier"],
            "top_factor": row["top_factor"],
            "computed_at": row["computed_at"].isoformat(),
        }
        for row in rows
    ]
