"""Risk Pilot analyzer engine — shared base: the pluggable pack registry, the
unified normalized-data contract, and the pure stdlib math helpers every pack
builds on.

An **analyzer pack** is a pure, deterministic unit that knows how to measure one
family of risk (volatility, financial ratios, insurance loss, inventory). Adding
a domain = add one pack module and append it to ``ANALYZERS`` — nothing else in
the system changes. Each pack is:

    Analyzer(key, label, applies, compute)
      applies(normalized) -> bool                      # do I have the shape/roles I need?
      compute(normalized, config, ds_key) -> dict      # PURE, no DB, no Gemini, unit-tested

``compute`` returns a **renderable, citable** block so the report PDF and the
frontend render every pack uniformly (true extensibility — neither knows the
pack's internals):

    {
      "label":   "Volatility & Risk",
      "tiles":   [{"label": "Volatility (σ)", "value": "18.4%"}, ...],
      "tables":  [{"title": ..., "columns": [...], "rows": [[cell, ...], ...]}],
      "charts":  [{"title": ..., "svg": "<svg .../>"}],
      "records": [{"cid": "metric:<ds>:...", "ref": ..., "summary": ..., "when": ...}],
    }

The ``records`` are the citation corpus — the grounded AI may cite ONLY these ids
(the shared ``legal_defense.validate_citations`` gate drops anything else), so a
statistic that wasn't computed can never reach the user.

All math is Python-stdlib only (``statistics`` gained ``correlation`` /
``covariance`` in 3.10; we're on 3.12). No numpy/pandas/scipy.
"""

from __future__ import annotations

import math
import re
import statistics
from collections import namedtuple

# Unified data model every ingestion path (CSV / XLSX / PDF-extraction) flattens
# into. A P&L line-item over fiscal years is just a named series with periods.
#   normalized = {
#     "series":  {name: [float|None, ...]},   # None = missing/blank cell
#     "periods": [str, ...] | None,           # row/period labels (years, dates)
#     "roles":   {name: canonical_role},      # e.g. revenue | losses_incurred | units_on_hand
#     "kind":    "timeseries|financial_statement|loss_run|inventory|generic",
#     "meta":    {"source_kind", "filename", "truncated", "warnings": [...]},
#   }

Analyzer = namedtuple("Analyzer", "key label applies compute")

_MIN_POINTS = 2  # a variance/volatility needs at least two observations


# --------------------------------------------------------------------------- #
# Slugs / identifiers
# --------------------------------------------------------------------------- #

def slug(s) -> str:
    """Stable lowercase token for cids and chart keys."""
    return re.sub(r"[^a-z0-9]+", "-", str(s or "").lower()).strip("-") or "x"


# --------------------------------------------------------------------------- #
# Numeric coercion + series math (all guard n<2 / zero-variance → None)
# --------------------------------------------------------------------------- #

def to_float(v):
    """Coerce a cell to float, tolerating $, commas, %, and (parenthesized)
    negatives. Returns None when it isn't a number."""
    if v is None:
        return None
    if isinstance(v, (int, float)):
        return None if isinstance(v, float) and math.isnan(v) else float(v)
    s = str(v).strip()
    if not s:
        return None
    neg = s.startswith("(") and s.endswith(")")
    s = s.strip("()").replace(",", "").replace("$", "").replace("%", "").strip()
    if s in ("", "-", "—", "n/a", "na", "nan", "null"):
        return None
    try:
        f = float(s)
    except (TypeError, ValueError):
        return None
    return -f if neg else f


def nums(series) -> list[float]:
    """Non-null floats of a series, in order."""
    return [x for x in (series or []) if isinstance(x, (int, float)) and not (isinstance(x, float) and math.isnan(x))]


def returns(levels: list[float]) -> list[float]:
    """Period-over-period simple returns of a level series. Skips a point when
    the prior level is zero (undefined) rather than producing an infinity."""
    out = []
    for prev, cur in zip(levels, levels[1:]):
        if prev in (0, 0.0):
            continue
        out.append((cur - prev) / prev)
    return out


def percentile(values: list[float], p: float):
    """Linear-interpolated percentile (p in 0..100). Pure — mirrors the
    'inclusive' method so results match hand-computed fixtures."""
    xs = sorted(values)
    n = len(xs)
    if n == 0:
        return None
    if n == 1:
        return xs[0]
    rank = (p / 100.0) * (n - 1)
    lo = int(math.floor(rank))
    hi = int(math.ceil(rank))
    if lo == hi:
        return xs[lo]
    frac = rank - lo
    return xs[lo] + (xs[hi] - xs[lo]) * frac


def stdev(values: list[float]):
    xs = nums(values)
    if len(xs) < _MIN_POINTS:
        return None
    try:
        return statistics.stdev(xs)
    except statistics.StatisticsError:
        return None


def mean(values: list[float]):
    xs = nums(values)
    return statistics.fmean(xs) if xs else None


def coefficient_of_variation(values: list[float]):
    xs = nums(values)
    m = mean(xs)
    sd = stdev(xs)
    if m is None or sd is None or m == 0:
        return None
    return sd / abs(m)


def value_at_risk(rets: list[float], pct: float):
    """Historical VaR as a positive loss magnitude at the given tail pct
    (e.g. 5 for VaR95). None when the sample is too small."""
    xs = nums(rets)
    if len(xs) < _MIN_POINTS:
        return None
    q = percentile(xs, pct)
    return None if q is None else max(0.0, -q)


def expected_shortfall(rets: list[float], pct: float):
    """CVaR — mean of returns at or below the tail percentile, as a positive
    loss magnitude."""
    xs = nums(rets)
    if len(xs) < _MIN_POINTS:
        return None
    cutoff = percentile(xs, pct)
    if cutoff is None:
        return None
    tail = [x for x in xs if x <= cutoff]
    if not tail:
        return None
    return max(0.0, -statistics.fmean(tail))


def max_drawdown(index_series: list[float]):
    """Worst peak-to-trough decline on a cumulative level series, as a fraction
    (0.30 == -30%). None if fewer than two points or no positive peak."""
    xs = nums(index_series)
    if len(xs) < _MIN_POINTS:
        return None
    peak = xs[0]
    worst = 0.0
    for x in xs:
        if x > peak:
            peak = x
        if peak > 0:
            dd = (peak - x) / peak
            if dd > worst:
                worst = dd
    return worst


def cumulative_index(rets: list[float], base: float = 1.0) -> list[float]:
    """Growth-of-1 index synthesized from a return series."""
    idx = [base]
    for r in rets:
        idx.append(idx[-1] * (1.0 + r))
    return idx


def sharpe_like(rets: list[float], risk_free_per_period: float = 0.0):
    """Mean excess return over its own volatility (unitless, per-period)."""
    xs = nums(rets)
    m = mean(xs)
    sd = stdev(xs)
    if m is None or sd is None or sd == 0:
        return None
    return (m - risk_free_per_period) / sd


def downside_deviation(rets: list[float], target: float = 0.0):
    """Std-dev-like measure over only below-target returns."""
    xs = nums(rets)
    if len(xs) < _MIN_POINTS:
        return None
    sq = [min(0.0, x - target) ** 2 for x in xs]
    return math.sqrt(statistics.fmean(sq))


def annualize_vol(vol, periods_per_year):
    if vol is None or not periods_per_year:
        return None
    return vol * math.sqrt(periods_per_year)


def pearson(a: list[float], b: list[float]):
    """Correlation over the index-aligned intersection where both are numeric.
    None when <2 aligned points or either side has zero variance."""
    pairs = [(x, y) for x, y in zip(a or [], b or [])
             if isinstance(x, (int, float)) and isinstance(y, (int, float))
             and not (isinstance(x, float) and math.isnan(x))
             and not (isinstance(y, float) and math.isnan(y))]
    if len(pairs) < _MIN_POINTS:
        return None
    xs = [p[0] for p in pairs]
    ys = [p[1] for p in pairs]
    try:
        return statistics.correlation(xs, ys)
    except statistics.StatisticsError:
        return None


def cagr(first: float, last: float, periods: int):
    """Compound annual (per-period) growth rate over ``periods`` steps."""
    if first is None or last is None or periods < 1 or first <= 0 or last <= 0:
        return None
    return (last / first) ** (1.0 / periods) - 1.0


# --------------------------------------------------------------------------- #
# Display formatting (used for tiles/tables/record summaries — keep terse)
# --------------------------------------------------------------------------- #

def fmt_pct(v, digits: int = 1) -> str:
    if v is None:
        return "—"
    return f"{v * 100:.{digits}f}%"


def fmt_num(v, digits: int = 2) -> str:
    if v is None:
        return "—"
    try:
        f = float(v)
    except (TypeError, ValueError):
        return str(v)
    if abs(f) >= 1000:
        return f"{f:,.0f}"
    s = f"{f:.{digits}f}"
    return s.rstrip("0").rstrip(".") if "." in s else s


def fmt_money(v) -> str:
    if v is None:
        return "—"
    try:
        return f"${float(v):,.0f}"
    except (TypeError, ValueError):
        return str(v)


def fmt_ratio(v, digits: int = 2) -> str:
    if v is None:
        return "—"
    return f"{v:.{digits}f}×"


# --------------------------------------------------------------------------- #
# Registry
# --------------------------------------------------------------------------- #

def _load_analyzers() -> list:
    # Lazy imports keep the pack modules free to import base without a cycle.
    from .volatility import ANALYZER as volatility
    from .financial_ratios import ANALYZER as financial_ratios
    from .insurance import ANALYZER as insurance
    from .inventory import ANALYZER as inventory
    return [volatility, financial_ratios, insurance, inventory]


def run_analyzers(normalized: dict, config: dict | None, ds_key: str) -> dict:
    """Run every applicable pack over one normalized dataset. Returns
    ``{pack_key: block}``. A pack that raises is skipped with a warning stub —
    one bad pack never sinks the analysis (degrade, don't 500)."""
    config = config or {}
    out: dict = {}
    for a in _load_analyzers():
        try:
            if not a.applies(normalized):
                continue
            block = a.compute(normalized, config, ds_key)
            if block and (block.get("tiles") or block.get("tables") or block.get("records")):
                out[a.key] = block
        except Exception as exc:  # noqa: BLE001 — isolation is the point
            out.setdefault("_warnings", []).append(f"{a.label}: {exc}")
    return out
