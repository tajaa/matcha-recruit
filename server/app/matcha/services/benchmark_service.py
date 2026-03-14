"""Risk-Adjusted Benchmarking Service.

Compares company metrics against NAICS industry peers using
public data from BLS SOII, OSHA, EEOC, and QCEW.
"""

import json
import logging
from dataclasses import dataclass, asdict
from pathlib import Path
from typing import Any
from uuid import UUID

from ...database import get_connection

logger = logging.getLogger(__name__)

# Load NAICS benchmarks from static JSON
_BENCHMARKS_PATH = Path(__file__).parent.parent / "data" / "naics_benchmarks.json"
_NAICS_BENCHMARKS: dict[str, Any] = {}


def _load_benchmarks() -> dict[str, Any]:
    """Load NAICS benchmarks from JSON file (cached after first load)."""
    global _NAICS_BENCHMARKS
    if not _NAICS_BENCHMARKS:
        try:
            with open(_BENCHMARKS_PATH, "r") as f:
                _NAICS_BENCHMARKS = json.load(f)
        except FileNotFoundError:
            logger.warning("NAICS benchmarks file not found at %s", _BENCHMARKS_PATH)
            _NAICS_BENCHMARKS = {}
    return _NAICS_BENCHMARKS


@dataclass
class BenchmarkMetric:
    metric: str
    company_value: float
    industry_median: float
    ratio: float
    percentile: int  # 0-100
    interpretation: str

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass
class BenchmarkResult:
    naics_code: str
    naics_label: str
    metrics: list[BenchmarkMetric]

    def to_dict(self) -> dict[str, Any]:
        return {
            "naics_code": self.naics_code,
            "naics_label": self.naics_label,
            "metrics": [m.to_dict() for m in self.metrics],
        }


def _estimate_percentile(value: float, median: float, p25: float, p75: float) -> int:
    """Estimate percentile rank using quartile-based interpolation.

    Assumes roughly normal distribution between quartiles.
    """
    if median <= 0:
        return 50
    if value <= p25:
        # Below 25th percentile
        if p25 > 0:
            return max(0, int(25 * (value / p25)))
        return 0
    elif value <= median:
        # Between 25th and 50th
        if median > p25:
            frac = (value - p25) / (median - p25)
            return int(25 + 25 * frac)
        return 37
    elif value <= p75:
        # Between 50th and 75th
        if p75 > median:
            frac = (value - median) / (p75 - median)
            return int(50 + 25 * frac)
        return 62
    else:
        # Above 75th
        if p75 > 0:
            frac = min((value - p75) / p75, 1.0)
            return min(99, int(75 + 25 * frac))
        return 90


def _interpret_ratio(ratio: float, metric_name: str) -> str:
    """Generate human-readable interpretation of a benchmark ratio."""
    if ratio < 0.5:
        return f"Significantly below industry average ({ratio:.1f}x)"
    elif ratio < 0.8:
        return f"Below industry average ({ratio:.1f}x)"
    elif ratio <= 1.2:
        return f"In line with industry average ({ratio:.1f}x)"
    elif ratio <= 2.0:
        return f"Above industry average ({ratio:.1f}x)"
    elif ratio <= 3.0:
        return f"{ratio:.1f}x above industry average — elevated risk"
    else:
        return f"{ratio:.1f}x above industry average — critical outlier"


async def compute_benchmarks(
    company_id: UUID,
    snapshot_dimensions: dict[str, Any] | None = None,
) -> BenchmarkResult:
    """Compare company risk metrics against NAICS industry peers.

    Args:
        company_id: Company to benchmark.
        snapshot_dimensions: Optional pre-loaded dimensions from a risk snapshot.
            If not provided, will fetch from latest snapshot.

    Returns:
        BenchmarkResult with per-metric comparisons.
    """
    benchmarks = _load_benchmarks()

    async with get_connection() as conn:
        # Get company info — naics_code may not exist on all schemas
        company = await conn.fetchrow(
            "SELECT name FROM companies WHERE id = $1",
            company_id,
        )
        if not company:
            return BenchmarkResult(
                naics_code="unknown",
                naics_label="Unknown",
                metrics=[],
            )

        # naics_code column may not exist yet
        try:
            naics_code = await conn.fetchval(
                "SELECT naics_code FROM companies WHERE id = $1",
                company_id,
            ) or ""
        except Exception:
            naics_code = ""
        # Try progressively shorter NAICS codes for best match
        naics_data = None
        naics_match = naics_code
        for length in [6, 4, 3, 2]:
            prefix = naics_code[:length] if len(naics_code) >= length else naics_code
            if prefix in benchmarks:
                naics_data = benchmarks[prefix]
                naics_match = prefix
                break

        if not naics_data:
            # Fall back to broad industry defaults
            naics_data = benchmarks.get("default", {})
            naics_match = "default"

        naics_label = naics_data.get("label", f"NAICS {naics_match}")

        # Get company metrics
        employee_count = await conn.fetchval(
            "SELECT COUNT(*) FROM employees WHERE org_id = $1 AND termination_date IS NULL",
            company_id,
        )
        employee_count = int(employee_count or 0)

        # Open incidents
        incident_count = await conn.fetchval(
            """
            SELECT COUNT(*) FROM ir_incidents
            WHERE company_id = $1 AND status NOT IN ('resolved', 'closed')
            """,
            company_id,
        )
        incident_count = int(incident_count or 0)

        # ER case count
        er_case_count = await conn.fetchval(
            "SELECT COUNT(*) FROM er_cases WHERE company_id = $1 AND status != 'closed'",
            company_id,
        )
        er_case_count = int(er_case_count or 0)

        # Load snapshot dimensions if not provided
        if snapshot_dimensions is None:
            snap_row = await conn.fetchrow(
                "SELECT dimensions FROM risk_assessment_snapshots WHERE company_id = $1",
                company_id,
            )
            if snap_row:
                dims = snap_row["dimensions"]
                if isinstance(dims, str):
                    dims = json.loads(dims)
                snapshot_dimensions = dims

    # Compute metrics
    metrics: list[BenchmarkMetric] = []
    fte = max(employee_count, 1)

    # 1. Incident rate per 100 FTE
    company_incident_rate = (incident_count / fte) * 100
    industry = naics_data.get("incident_rate_per_100", {})
    if industry:
        ind_median = industry.get("median", 3.0)
        ind_p25 = industry.get("p25", 1.5)
        ind_p75 = industry.get("p75", 5.0)
        ratio = company_incident_rate / ind_median if ind_median > 0 else 0
        metrics.append(BenchmarkMetric(
            metric="incident_rate_per_100",
            company_value=round(company_incident_rate, 2),
            industry_median=ind_median,
            ratio=round(ratio, 2),
            percentile=_estimate_percentile(company_incident_rate, ind_median, ind_p25, ind_p75),
            interpretation=_interpret_ratio(ratio, "incident rate"),
        ))

    # 2. ER case rate per 1000 employees
    company_er_rate = (er_case_count / fte) * 1000
    industry = naics_data.get("er_case_rate_per_1000", {})
    if industry:
        ind_median = industry.get("median", 15.0)
        ind_p25 = industry.get("p25", 8.0)
        ind_p75 = industry.get("p75", 25.0)
        ratio = company_er_rate / ind_median if ind_median > 0 else 0
        metrics.append(BenchmarkMetric(
            metric="er_case_rate_per_1000",
            company_value=round(company_er_rate, 2),
            industry_median=ind_median,
            ratio=round(ratio, 2),
            percentile=_estimate_percentile(company_er_rate, ind_median, ind_p25, ind_p75),
            interpretation=_interpret_ratio(ratio, "ER case rate"),
        ))

    # 3. OSHA TRC (Total Recordable Cases) rate
    # We approximate TRC from our incident data (incidents ≈ recordable cases)
    company_trc = (incident_count / fte) * 100  # same as incident rate for now
    industry = naics_data.get("osha_trc_rate", {})
    if industry:
        ind_median = industry.get("median", 2.8)
        ind_p25 = industry.get("p25", 1.2)
        ind_p75 = industry.get("p75", 4.5)
        ratio = company_trc / ind_median if ind_median > 0 else 0
        metrics.append(BenchmarkMetric(
            metric="osha_trc_rate",
            company_value=round(company_trc, 2),
            industry_median=ind_median,
            ratio=round(ratio, 2),
            percentile=_estimate_percentile(company_trc, ind_median, ind_p25, ind_p75),
            interpretation=_interpret_ratio(ratio, "OSHA TRC rate"),
        ))

    # 4. DART (Days Away, Restricted, Transferred) rate
    industry = naics_data.get("osha_dart_rate", {})
    if industry:
        # Approximate DART as ~60% of TRC (industry typical ratio)
        company_dart = company_trc * 0.6
        ind_median = industry.get("median", 1.7)
        ind_p25 = industry.get("p25", 0.8)
        ind_p75 = industry.get("p75", 2.8)
        ratio = company_dart / ind_median if ind_median > 0 else 0
        metrics.append(BenchmarkMetric(
            metric="osha_dart_rate",
            company_value=round(company_dart, 2),
            industry_median=ind_median,
            ratio=round(ratio, 2),
            percentile=_estimate_percentile(company_dart, ind_median, ind_p25, ind_p75),
            interpretation=_interpret_ratio(ratio, "OSHA DART rate"),
        ))

    # 5. EEOC charge rate per 1000 employees
    industry = naics_data.get("eeoc_charge_rate_per_1000", {})
    if industry:
        company_eeoc_rate = company_er_rate  # ER cases approximate EEOC-type charges
        ind_median = industry.get("median", 5.0)
        ind_p25 = industry.get("p25", 2.0)
        ind_p75 = industry.get("p75", 10.0)
        ratio = company_eeoc_rate / ind_median if ind_median > 0 else 0
        metrics.append(BenchmarkMetric(
            metric="eeoc_charge_rate_per_1000",
            company_value=round(company_eeoc_rate, 2),
            industry_median=ind_median,
            ratio=round(ratio, 2),
            percentile=_estimate_percentile(company_eeoc_rate, ind_median, ind_p25, ind_p75),
            interpretation=_interpret_ratio(ratio, "EEOC charge rate"),
        ))

    return BenchmarkResult(
        naics_code=naics_match,
        naics_label=naics_label,
        metrics=metrics,
    )
