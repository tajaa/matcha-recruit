"""Monte Carlo Risk Simulation Service.

Runs N=10,000 iteration simulations over cost-of-risk line items
to produce probability distributions of annual loss exposure.

Consumes the same cost-of-risk line items already computed by
compute_compliance_cost_of_risk, compute_er_cost_of_risk, and
compute_incident_cost_of_risk in risk_assessment_service.py.
"""

import logging
import math
import random
from dataclasses import dataclass, asdict
from datetime import datetime, timezone
from typing import Any

logger = logging.getLogger(__name__)

DEFAULT_ITERATIONS = 10_000

# Line item keys where frequency is deterministic (events already exist).
# Monte Carlo varies severity only.
DETERMINISTIC_KEYS = {
    "hourly_wage_shortfall",
    "exempt_misclassification",
    "pending_determination",
    "in_review",
    "open_cases",
    "critical_incidents",
    "high_incidents",
    "medium_incidents",
}

# Line item keys where frequency is stochastic (events may or may not happen).
# Monte Carlo varies both frequency and severity.
STOCHASTIC_LAMBDA_OVERRIDES: dict[str, float] = {
    # HIPAA breach: ~1-3% probability per year for small facilities (OCR data)
    "hipaa_breach_exposure": 0.02,
    # Lapsed credential: 30% chance of discovery per at-risk employee per year
    "lapsed_credential_risk": 0.30,
}

# z-score for 90th percentile (used to derive lognormal σ from low/high range)
Z_90 = 1.2816


@dataclass
class HistogramBin:
    x: float  # bin midpoint
    count: int
    density: float  # count / total / bin_width

    def to_dict(self) -> dict[str, Any]:
        return {"x": round(self.x, 2), "count": self.count, "density": round(self.density, 6)}


@dataclass
class ExceedanceCurvePoint:
    threshold: float
    probability: float  # P(Loss >= threshold)

    def to_dict(self) -> dict[str, Any]:
        return {"threshold": round(self.threshold, 2), "probability": round(self.probability, 6)}


@dataclass
class DistributionStats:
    mean: float
    median: float
    std_dev: float
    skewness: float
    kurtosis: float  # excess kurtosis
    iqr: float
    tail_ratio: float  # CVaR95 / VaR95

    def to_dict(self) -> dict[str, Any]:
        return {k: round(v, 4) for k, v in asdict(self).items()}


@dataclass
class CategorySimResult:
    key: str
    label: str
    frequency_type: str  # "deterministic" or "stochastic"
    frequency_lambda: float
    expected_loss: float
    percentiles: dict[str, float]
    zero_loss_pct: float
    histogram_bins: list[HistogramBin] | None = None

    def to_dict(self) -> dict[str, Any]:
        d = asdict(self)
        d.pop("histogram_bins", None)
        if self.histogram_bins:
            d["histogram_bins"] = [b.to_dict() for b in self.histogram_bins]
        return d


@dataclass
class AggregateSimResult:
    expected_annual_loss: float
    percentiles: dict[str, float]
    var_95: float
    var_99: float
    cvar_95: float
    max_simulated: float
    histogram_bins: list[HistogramBin] | None = None
    exceedance_curve: list[ExceedanceCurvePoint] | None = None
    distribution_stats: DistributionStats | None = None

    def to_dict(self) -> dict[str, Any]:
        d = {
            "expected_annual_loss": self.expected_annual_loss,
            "percentiles": self.percentiles,
            "var_95": self.var_95,
            "var_99": self.var_99,
            "cvar_95": self.cvar_95,
            "max_simulated": self.max_simulated,
        }
        if self.histogram_bins:
            d["histogram_bins"] = [b.to_dict() for b in self.histogram_bins]
        if self.exceedance_curve:
            d["exceedance_curve"] = [p.to_dict() for p in self.exceedance_curve]
        if self.distribution_stats:
            d["distribution_stats"] = self.distribution_stats.to_dict()
        return d


@dataclass
class MonteCarloResult:
    iterations: int
    categories: dict[str, CategorySimResult]
    aggregate: AggregateSimResult
    computed_at: str

    def to_dict(self) -> dict[str, Any]:
        return {
            "iterations": self.iterations,
            "categories": {k: v.to_dict() for k, v in self.categories.items()},
            "aggregate": self.aggregate.to_dict(),
            "computed_at": self.computed_at,
        }


def _lognormal_params(low: float, high: float) -> tuple[float, float]:
    """Derive lognormal μ, σ from a low/high range.

    Treats low and high as the 10th and 90th percentiles of the distribution.
    """
    if low <= 0 or high <= 0:
        return 0.0, 0.0
    if high <= low:
        # Degenerate range — use minimal spread
        return math.log(low), 0.1

    ln_low = math.log(low)
    ln_high = math.log(high)
    mu = (ln_low + ln_high) / 2.0
    sigma = (ln_high - ln_low) / (2.0 * Z_90)
    return mu, sigma


def _compute_percentiles(values: list[float]) -> dict[str, float]:
    """Compute standard risk percentiles from a sorted list of values."""
    if not values:
        return {k: 0.0 for k in ("p5", "p10", "p25", "p50", "p75", "p90", "p95", "p99")}

    values.sort()
    n = len(values)

    def pct(p: float) -> float:
        idx = p * (n - 1)
        lo = int(idx)
        hi = min(lo + 1, n - 1)
        frac = idx - lo
        return values[lo] * (1 - frac) + values[hi] * frac

    return {
        "p5": round(pct(0.05), 2),
        "p10": round(pct(0.10), 2),
        "p25": round(pct(0.25), 2),
        "p50": round(pct(0.50), 2),
        "p75": round(pct(0.75), 2),
        "p90": round(pct(0.90), 2),
        "p95": round(pct(0.95), 2),
        "p99": round(pct(0.99), 2),
    }


def _simulate_category(
    item: dict[str, Any],
    iterations: int,
    rng: random.Random,
) -> CategorySimResult:
    """Run Monte Carlo simulation for a single cost-of-risk line item."""
    key = item["key"]
    label = item.get("label", key)
    low = item.get("low", 0)
    high = item.get("high", 0)
    affected_count = item.get("affected_count", 0)

    if low <= 0 and high <= 0:
        return CategorySimResult(
            key=key,
            label=label,
            frequency_type="deterministic",
            frequency_lambda=0.0,
            expected_loss=0.0,
            percentiles={k: 0.0 for k in ("p5", "p10", "p25", "p50", "p75", "p90", "p95", "p99")},
            zero_loss_pct=100.0,
        )

    mu, sigma = _lognormal_params(max(low, 1), max(high, 1))
    is_stochastic = key in STOCHASTIC_LAMBDA_OVERRIDES

    if is_stochastic:
        # Stochastic: lambda is a per-unit probability × affected count
        base_rate = STOCHASTIC_LAMBDA_OVERRIDES[key]
        lam = base_rate * max(affected_count, 1)
        frequency_type = "stochastic"
        # For stochastic items, severity per event is derived from
        # the per-unit cost (low/high divided by affected_count)
        per_unit_low = low / max(affected_count, 1)
        per_unit_high = high / max(affected_count, 1)
        mu, sigma = _lognormal_params(max(per_unit_low, 1), max(per_unit_high, 1))
    else:
        # Deterministic: all affected_count events occur, severity varies
        lam = float(affected_count) if affected_count > 0 else 1.0
        frequency_type = "deterministic"
        # Severity per event
        per_unit_low = low / max(affected_count, 1)
        per_unit_high = high / max(affected_count, 1)
        mu, sigma = _lognormal_params(max(per_unit_low, 1), max(per_unit_high, 1))

    totals: list[float] = []
    zero_count = 0

    for _ in range(iterations):
        if is_stochastic:
            n_events = rng.poisson(lam) if hasattr(rng, 'poisson') else _poisson(lam, rng)
        else:
            n_events = int(lam)

        if n_events == 0:
            totals.append(0.0)
            zero_count += 1
            continue

        iteration_total = 0.0
        for _ in range(n_events):
            cost = rng.lognormvariate(mu, sigma) if sigma > 0 else math.exp(mu)
            iteration_total += cost
        totals.append(iteration_total)

    expected_loss = sum(totals) / len(totals) if totals else 0.0
    percentiles = _compute_percentiles(totals)
    zero_loss_pct = round((zero_count / iterations) * 100, 2) if iterations > 0 else 0.0

    return CategorySimResult(
        key=key,
        label=label,
        frequency_type=frequency_type,
        frequency_lambda=round(lam, 4),
        expected_loss=round(expected_loss, 2),
        percentiles=percentiles,
        zero_loss_pct=zero_loss_pct,
    )


def _poisson(lam: float, rng: random.Random) -> int:
    """Generate a Poisson-distributed random variable using Knuth's algorithm."""
    if lam <= 0:
        return 0
    if lam > 30:
        # For large λ, use normal approximation
        return max(0, int(rng.gauss(lam, math.sqrt(lam)) + 0.5))
    L = math.exp(-lam)
    k = 0
    p = 1.0
    while True:
        k += 1
        p *= rng.random()
        if p <= L:
            return k - 1


def _compute_histogram(sorted_values: list[float], n_bins: int = 80) -> list[HistogramBin]:
    """Compute histogram bins from a sorted list of values."""
    if not sorted_values or sorted_values[-1] <= 0:
        return []
    # Use p99 * 1.1 as upper bound to avoid extreme outlier stretching
    p99_idx = int(0.99 * (len(sorted_values) - 1))
    upper = sorted_values[p99_idx] * 1.1
    if upper <= 0:
        return []
    bin_width = upper / n_bins
    bins: list[HistogramBin] = []
    total = len(sorted_values)
    vi = 0  # pointer into sorted values
    for i in range(n_bins):
        lo = i * bin_width
        hi = lo + bin_width
        mid = lo + bin_width / 2
        count = 0
        while vi < total and sorted_values[vi] < hi:
            if sorted_values[vi] >= lo:
                count += 1
            vi += 1
        density = (count / total / bin_width) if bin_width > 0 else 0.0
        bins.append(HistogramBin(x=mid, count=count, density=density))
    return bins


def _compute_exceedance_curve(sorted_values: list[float], n_points: int = 200) -> list[ExceedanceCurvePoint]:
    """Compute empirical survival function P(Loss >= threshold)."""
    if not sorted_values:
        return []
    max_val = sorted_values[-1]
    if max_val <= 0:
        return []
    n = len(sorted_values)
    points: list[ExceedanceCurvePoint] = []
    for i in range(n_points):
        threshold = (i / (n_points - 1)) * max_val if n_points > 1 else 0.0
        # Binary search for first value >= threshold
        lo, hi = 0, n
        while lo < hi:
            mid = (lo + hi) // 2
            if sorted_values[mid] < threshold:
                lo = mid + 1
            else:
                hi = mid
        prob = (n - lo) / n
        points.append(ExceedanceCurvePoint(threshold=threshold, probability=prob))
    return points


def _compute_distribution_stats(
    sorted_values: list[float], var_95: float, cvar_95: float,
) -> DistributionStats:
    """Compute distribution statistics from sorted samples."""
    n = len(sorted_values)
    mean = sum(sorted_values) / n
    median = sorted_values[n // 2]
    variance = sum((v - mean) ** 2 for v in sorted_values) / n
    std_dev = math.sqrt(variance) if variance > 0 else 0.0

    if std_dev > 0:
        skewness = sum((v - mean) ** 3 for v in sorted_values) / (n * std_dev ** 3)
        kurtosis = sum((v - mean) ** 4 for v in sorted_values) / (n * std_dev ** 4) - 3.0
    else:
        skewness = 0.0
        kurtosis = 0.0

    p25_idx = int(0.25 * (n - 1))
    p75_idx = int(0.75 * (n - 1))
    iqr = sorted_values[p75_idx] - sorted_values[p25_idx]
    tail_ratio = (cvar_95 / var_95) if var_95 > 0 else 0.0

    return DistributionStats(
        mean=mean, median=median, std_dev=std_dev,
        skewness=skewness, kurtosis=kurtosis,
        iqr=iqr, tail_ratio=tail_ratio,
    )


def run_monte_carlo(
    cost_of_risk_items: list[dict[str, Any]],
    iterations: int = DEFAULT_ITERATIONS,
    seed: int | None = None,
) -> MonteCarloResult:
    """Run Monte Carlo simulation over cost-of-risk line items.

    Args:
        cost_of_risk_items: List of line item dicts from cost-of-risk computations.
            Each must have: key, label, low, high, affected_count.
        iterations: Number of simulation iterations (default 10,000).
        seed: Optional random seed for reproducibility.

    Returns:
        MonteCarloResult with per-category and aggregate distributions.
    """
    rng = random.Random(seed)

    categories: dict[str, CategorySimResult] = {}

    for item in cost_of_risk_items:
        result = _simulate_category(item, iterations, rng)
        categories[result.key] = result

    # Compute aggregate by summing across categories per iteration
    # Re-run with same seed to get correlated totals
    rng2 = random.Random(seed)
    aggregate_totals: list[float] = [0.0] * iterations

    for item in cost_of_risk_items:
        key = item["key"]
        low = item.get("low", 0)
        high = item.get("high", 0)
        affected_count = item.get("affected_count", 0)

        if low <= 0 and high <= 0:
            continue

        is_stochastic = key in STOCHASTIC_LAMBDA_OVERRIDES

        if is_stochastic:
            base_rate = STOCHASTIC_LAMBDA_OVERRIDES[key]
            lam = base_rate * max(affected_count, 1)
            per_unit_low = low / max(affected_count, 1)
            per_unit_high = high / max(affected_count, 1)
        else:
            lam = float(affected_count) if affected_count > 0 else 1.0
            per_unit_low = low / max(affected_count, 1)
            per_unit_high = high / max(affected_count, 1)

        mu, sigma = _lognormal_params(max(per_unit_low, 1), max(per_unit_high, 1))

        for i in range(iterations):
            if is_stochastic:
                n_events = _poisson(lam, rng2)
            else:
                n_events = int(lam)

            for _ in range(n_events):
                cost = rng2.lognormvariate(mu, sigma) if sigma > 0 else math.exp(mu)
                aggregate_totals[i] += cost

    aggregate_totals.sort()
    expected_annual_loss = sum(aggregate_totals) / len(aggregate_totals) if aggregate_totals else 0.0
    percentiles = _compute_percentiles(aggregate_totals)

    p95_idx = int(0.95 * (len(aggregate_totals) - 1))
    p99_idx = int(0.99 * (len(aggregate_totals) - 1))
    var_95 = aggregate_totals[p95_idx] if aggregate_totals else 0.0
    var_99 = aggregate_totals[p99_idx] if aggregate_totals else 0.0

    # CVaR (Expected Shortfall) at 95%: mean of losses exceeding P95
    tail_values = aggregate_totals[p95_idx:]
    cvar_95 = sum(tail_values) / len(tail_values) if tail_values else 0.0

    max_simulated = aggregate_totals[-1] if aggregate_totals else 0.0

    # Quantitative analytics: histogram, exceedance curve, distribution stats
    hist_bins = _compute_histogram(aggregate_totals, n_bins=80)
    exc_curve = _compute_exceedance_curve(aggregate_totals, n_points=200)
    dist_stats = _compute_distribution_stats(aggregate_totals, var_95, cvar_95) if aggregate_totals else None

    # Per-category sparkline histograms (re-derive sorted totals from percentiles is lossy,
    # so we re-simulate once more with same seed for per-category sorted arrays)
    rng3 = random.Random(seed)
    cat_sorted: dict[str, list[float]] = {}
    for item in cost_of_risk_items:
        cat_totals: list[float] = []
        key = item["key"]
        low = item.get("low", 0)
        high = item.get("high", 0)
        affected_count = item.get("affected_count", 0)
        is_stochastic = key in STOCHASTIC_LAMBDA_OVERRIDES
        if low <= 0 and high <= 0:
            for _ in range(iterations):
                cat_totals.append(0.0)
            cat_sorted[key] = cat_totals
            continue
        if is_stochastic:
            base_rate = STOCHASTIC_LAMBDA_OVERRIDES[key]
            lam = base_rate * max(affected_count, 1)
            per_unit_low = low / max(affected_count, 1)
            per_unit_high = high / max(affected_count, 1)
        else:
            lam = float(affected_count) if affected_count > 0 else 1.0
            per_unit_low = low / max(affected_count, 1)
            per_unit_high = high / max(affected_count, 1)
        mu, sigma = _lognormal_params(max(per_unit_low, 1), max(per_unit_high, 1))
        for _ in range(iterations):
            if is_stochastic:
                n_events = _poisson(lam, rng3)
            else:
                n_events = int(lam)
            it_total = 0.0
            for _ in range(n_events):
                cost = rng3.lognormvariate(mu, sigma) if sigma > 0 else math.exp(mu)
                it_total += cost
            cat_totals.append(it_total)
        cat_totals.sort()
        cat_sorted[key] = cat_totals

    for key, cat_result in categories.items():
        if key in cat_sorted:
            cat_result.histogram_bins = _compute_histogram(cat_sorted[key], n_bins=30)

    aggregate = AggregateSimResult(
        expected_annual_loss=round(expected_annual_loss, 2),
        percentiles=percentiles,
        var_95=round(var_95, 2),
        var_99=round(var_99, 2),
        cvar_95=round(cvar_95, 2),
        max_simulated=round(max_simulated, 2),
        histogram_bins=hist_bins,
        exceedance_curve=exc_curve,
        distribution_stats=dist_stats,
    )

    return MonteCarloResult(
        iterations=iterations,
        categories=categories,
        aggregate=aggregate,
        computed_at=datetime.now(timezone.utc).isoformat(),
    )


def extract_cost_of_risk_items(dimensions: dict[str, Any]) -> list[dict[str, Any]]:
    """Extract all cost-of-risk line items from a risk assessment snapshot's dimensions.

    Walks through each dimension's raw_data.cost_of_risk.line_items and collects them.
    """
    items: list[dict[str, Any]] = []
    for dim_key, dim_data in dimensions.items():
        raw = dim_data if isinstance(dim_data, dict) else {}
        raw_data = raw.get("raw_data", raw)
        cost_of_risk = raw_data.get("cost_of_risk", {})
        if isinstance(cost_of_risk, dict):
            line_items = cost_of_risk.get("line_items", [])
            if isinstance(line_items, list):
                items.extend(line_items)
    return items
