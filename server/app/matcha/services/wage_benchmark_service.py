"""Hourly wage benchmarking against BLS OEWS data.

Implements §3.1 of QSR_RETENTION_PLAN.md — surface "this barista is
$1.50/hr below market" alerts and roll them up into a dashboard widget
that frames the dollar bet:

    Closing the gap = $X/hr in raises
    vs.
    Replacing them at $5,864/quit fully-loaded (Restroworks) = $Y max exposure

Lookup is 3-tier with fallback:
    1. metro    — match BLS area_name ILIKE the employee's work_city
    2. state    — fall back to state-level p50
    3. national — last resort (US-wide)

Free-text job-title → SOC mapping is loaded once from
server/app/matcha/data/title_to_soc.json. No DB hit per classify call.

The pay_rate column on employees is a single snapshot (no history).
For MVP, only `pay_classification = 'hourly'` rows are evaluated — exempt
benchmarking is out of scope until we have proper FT-hours signal.
"""

from __future__ import annotations

import json
import logging
import os
from dataclasses import dataclass
from decimal import Decimal
from typing import Optional
from uuid import UUID

from ...database import get_connection

logger = logging.getLogger(__name__)

# Replacement-cost anchor from QSR_RETENTION_PLAN.md (Restroworks 2024).
# Used in the dashboard ROI math: avoiding a single quit ≈ saving this much.
REPLACEMENT_COST_PER_EMPLOYEE = 5864

# An employee at or below this market percentile delta triggers a
# "below market" alert. -10% means: their pay_rate is 10%+ under p50.
BELOW_MARKET_THRESHOLD = -0.10

# Reasonable annual hours assumption for hourly → annual conversion.
# Matches BLS OEWS convention (52 weeks × 40 hours).
ANNUAL_HOURS = 2080

_DATA_DIR = os.path.join(os.path.dirname(os.path.dirname(__file__)), "data")
_TITLE_MAP_PATH = os.path.join(_DATA_DIR, "title_to_soc.json")

# Module-level cache for the title→SOC map. Loaded lazily.
_title_rules: Optional[list[dict]] = None


def _load_title_rules() -> list[dict]:
    global _title_rules
    if _title_rules is None:
        try:
            with open(_TITLE_MAP_PATH) as f:
                payload = json.load(f)
            _title_rules = payload.get("rules", [])
        except FileNotFoundError:
            logger.warning("title_to_soc.json not found at %s — title classification will return None", _TITLE_MAP_PATH)
            _title_rules = []
    return _title_rules


def classify_title(title: Optional[str]) -> Optional[tuple[str, str]]:
    """Map a free-text job title to (soc_code, soc_label).

    Returns None when no rule matches — caller should treat as
    "not benchmarkable" rather than guessing. We'd rather show 0
    benchmarked employees than mis-categorize a barista as a chef.
    """
    if not title:
        return None
    lower = title.lower().strip()
    for rule in _load_title_rules():
        for kw in rule.get("keywords", []):
            if kw in lower:
                return (rule["soc_code"], rule.get("label", rule["soc_code"]))
    return None


# ─────────────────────────────────────────────────────────────────────────────
# Models
# ─────────────────────────────────────────────────────────────────────────────


@dataclass
class WageBenchmark:
    soc_code: str
    soc_label: str
    area_type: str          # 'metro' | 'state' | 'national'
    area_code: str
    area_name: str
    state: Optional[str]
    hourly_p10: Optional[Decimal]
    hourly_p25: Optional[Decimal]
    hourly_p50: Decimal
    hourly_p75: Optional[Decimal]
    hourly_p90: Optional[Decimal]
    period: str
    source: str


@dataclass
class CompanyWageGapSummary:
    """Aggregate for the operator-dashboard widget.

    Pitch math (per QSR_RETENTION_PLAN.md §3.1):
      - `dollars_per_hour_to_close_gap` × ANNUAL_HOURS = annual cost to lift
      - `max_replacement_cost_exposure` = below-market headcount × $5,864
        Honest framing: this is the upper-bound assuming 100% of below-market
        employees quit. Actual quit rate will be lower; the number is the
        worst-case exposure, not an expected loss.
    """
    hourly_employees_count: int      # active hourly employees with pay_rate set
    employees_evaluated: int         # of those, ones we could classify + benchmark
    employees_below_market: int
    employees_at_or_above_market: int
    employees_unclassified: int      # hourly emps we couldn't map to a SOC code
    median_delta_percent: Optional[float]
    dollars_per_hour_to_close_gap: float
    annual_cost_to_lift: int
    max_replacement_cost_exposure: int


# ─────────────────────────────────────────────────────────────────────────────
# Lookup — single benchmark (used by future per-employee endpoints)
# ─────────────────────────────────────────────────────────────────────────────


_SELECT_COLS = """soc_code, soc_label, area_type, area_code, area_name, state,
                  hourly_p10, hourly_p25, hourly_p50, hourly_p75, hourly_p90,
                  period, source"""


def _row_to_benchmark(row) -> WageBenchmark:
    return WageBenchmark(
        soc_code=row["soc_code"],
        soc_label=row["soc_label"] or row["soc_code"],
        area_type=row["area_type"],
        area_code=row["area_code"],
        area_name=row["area_name"] or "",
        state=row["state"],
        hourly_p10=row["hourly_p10"],
        hourly_p25=row["hourly_p25"],
        hourly_p50=row["hourly_p50"],
        hourly_p75=row["hourly_p75"],
        hourly_p90=row["hourly_p90"],
        period=row["period"],
        source=row["source"],
    )


async def lookup_benchmark(
    soc_code: str,
    work_city: Optional[str],
    work_state: Optional[str],
    period: Optional[str] = None,
) -> Optional[WageBenchmark]:
    """3-tier fallback: metro (city ILIKE area_name) → state → national."""
    if not soc_code:
        return None

    async with get_connection() as conn:
        if work_city and work_state:
            row = await conn.fetchrow(
                f"""
                SELECT {_SELECT_COLS}
                FROM wage_benchmarks
                WHERE soc_code = $1 AND area_type = 'metro'
                  AND state = $2 AND area_name ILIKE '%' || $3 || '%'
                  AND ($4::text IS NULL OR period = $4)
                ORDER BY refreshed_at DESC LIMIT 1
                """,
                soc_code, work_state.upper(), work_city, period,
            )
            if row:
                return _row_to_benchmark(row)

        if work_state:
            row = await conn.fetchrow(
                f"""
                SELECT {_SELECT_COLS}
                FROM wage_benchmarks
                WHERE soc_code = $1 AND area_type = 'state' AND state = $2
                  AND ($3::text IS NULL OR period = $3)
                ORDER BY refreshed_at DESC LIMIT 1
                """,
                soc_code, work_state.upper(), period,
            )
            if row:
                return _row_to_benchmark(row)

        row = await conn.fetchrow(
            f"""
            SELECT {_SELECT_COLS}
            FROM wage_benchmarks
            WHERE soc_code = $1 AND area_type = 'national'
              AND ($2::text IS NULL OR period = $2)
            ORDER BY refreshed_at DESC LIMIT 1
            """,
            soc_code, period,
        )
        return _row_to_benchmark(row) if row else None


# ─────────────────────────────────────────────────────────────────────────────
# Bulk: in-memory index for batch dashboard computation
# ─────────────────────────────────────────────────────────────────────────────


@dataclass
class _BenchmarkIndex:
    """Pre-fetched benchmarks indexed for in-memory 3-tier lookup."""
    national: dict[str, WageBenchmark]                          # soc → bm
    state: dict[tuple[str, str], WageBenchmark]                 # (soc, state) → bm
    metro: dict[tuple[str, str], list[WageBenchmark]]           # (soc, state) → [bm]

    def pick(
        self, soc_code: str, work_city: Optional[str], work_state: Optional[str]
    ) -> Optional[WageBenchmark]:
        state_u = (work_state or "").upper()
        # Tier 1: metro by case-insensitive city substring match against area_name
        if work_city and state_u:
            city_l = work_city.lower()
            for bm in self.metro.get((soc_code, state_u), []):
                if city_l in bm.area_name.lower():
                    return bm
        # Tier 2: state-level
        if state_u:
            bm = self.state.get((soc_code, state_u))
            if bm:
                return bm
        # Tier 3: national
        return self.national.get(soc_code)


async def _fetch_benchmark_index(
    soc_codes: set[str], states: set[str]
) -> _BenchmarkIndex:
    """Single query to pre-fetch every benchmark we might need for one company.

    Replaces the previous N-query loop where every (soc, city, state) cache
    miss triggered a fresh `lookup_benchmark` round-trip + connection acquire.
    """
    if not soc_codes:
        return _BenchmarkIndex(national={}, state={}, metro={})

    async with get_connection() as conn:
        rows = await conn.fetch(
            f"""
            SELECT {_SELECT_COLS}
            FROM wage_benchmarks
            WHERE soc_code = ANY($1::text[])
              AND (
                area_type = 'national'
                OR (state = ANY($2::text[]) AND area_type IN ('state', 'metro'))
              )
            """,
            list(soc_codes),
            list(states) if states else [""],
        )

    national: dict[str, WageBenchmark] = {}
    state_map: dict[tuple[str, str], WageBenchmark] = {}
    metro_map: dict[tuple[str, str], list[WageBenchmark]] = {}

    for row in rows:
        bm = _row_to_benchmark(row)
        if bm.area_type == "national":
            national[bm.soc_code] = bm
        elif bm.area_type == "state" and bm.state:
            state_map[(bm.soc_code, bm.state)] = bm
        elif bm.area_type == "metro" and bm.state:
            metro_map.setdefault((bm.soc_code, bm.state), []).append(bm)

    return _BenchmarkIndex(national=national, state=state_map, metro=metro_map)


# ─────────────────────────────────────────────────────────────────────────────
# Company-aggregate computation
# ─────────────────────────────────────────────────────────────────────────────


async def compute_company_wage_gap(company_id: UUID) -> CompanyWageGapSummary:
    """Run the gap analysis across all hourly employees for a company.

    Two DB hits total: one for the employee roster, one for all relevant
    benchmarks. Everything else runs in memory.
    """
    async with get_connection() as conn:
        rows = await conn.fetch(
            """
            SELECT id, job_title, work_city, work_state, pay_rate
            FROM employees
            WHERE org_id = $1
              AND termination_date IS NULL
              AND pay_classification = 'hourly'
              AND pay_rate IS NOT NULL
              AND pay_rate > 0
            """,
            company_id,
        )

    hourly_employees_count = len(rows)
    if hourly_employees_count == 0:
        return _empty_summary(0)

    # Pass 1: classify titles, collect distinct (soc, state) tuples for the
    # one-shot benchmark fetch.
    classified: list[tuple[dict, str]] = []
    unclassified = 0
    needed_socs: set[str] = set()
    needed_states: set[str] = set()

    for row in rows:
        cls = classify_title(row["job_title"])
        if not cls:
            unclassified += 1
            continue
        soc_code, _ = cls
        classified.append((dict(row), soc_code))
        needed_socs.add(soc_code)
        if row["work_state"]:
            needed_states.add(row["work_state"].upper())

    # One query to rule them all.
    index = await _fetch_benchmark_index(needed_socs, needed_states)

    # Pass 2: in-memory delta computation.
    deltas: list[float] = []
    below_market_count = 0
    at_or_above_count = 0
    total_dollar_gap_per_hour = 0.0

    for row, soc_code in classified:
        bm = index.pick(soc_code, row["work_city"], row["work_state"])
        if not bm or not bm.hourly_p50:
            unclassified += 1  # benchmark missing → can't evaluate
            continue

        pay_rate = float(row["pay_rate"])
        market = float(bm.hourly_p50)
        delta_dollars = pay_rate - market
        delta_pct = delta_dollars / market if market > 0 else 0.0
        deltas.append(delta_pct)

        if delta_pct <= BELOW_MARKET_THRESHOLD:
            below_market_count += 1
            total_dollar_gap_per_hour += abs(delta_dollars)
        else:
            at_or_above_count += 1

    evaluated = below_market_count + at_or_above_count
    annual_cost_to_lift = int(round(total_dollar_gap_per_hour * ANNUAL_HOURS))
    max_replacement_cost_exposure = below_market_count * REPLACEMENT_COST_PER_EMPLOYEE

    return CompanyWageGapSummary(
        hourly_employees_count=hourly_employees_count,
        employees_evaluated=evaluated,
        employees_below_market=below_market_count,
        employees_at_or_above_market=at_or_above_count,
        employees_unclassified=unclassified,
        median_delta_percent=_median(deltas) if deltas else None,
        dollars_per_hour_to_close_gap=round(total_dollar_gap_per_hour, 2),
        annual_cost_to_lift=annual_cost_to_lift,
        max_replacement_cost_exposure=max_replacement_cost_exposure,
    )


def _empty_summary(hourly_count: int) -> CompanyWageGapSummary:
    return CompanyWageGapSummary(
        hourly_employees_count=hourly_count,
        employees_evaluated=0,
        employees_below_market=0,
        employees_at_or_above_market=0,
        employees_unclassified=0,
        median_delta_percent=None,
        dollars_per_hour_to_close_gap=0.0,
        annual_cost_to_lift=0,
        max_replacement_cost_exposure=0,
    )


def _median(values: list[float]) -> float:
    n = len(values)
    if n == 0:
        return 0.0
    s = sorted(values)
    mid = n // 2
    if n % 2 == 1:
        return s[mid]
    return (s[mid - 1] + s[mid]) / 2.0
