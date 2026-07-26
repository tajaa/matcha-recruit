"""General descriptive analyzer pack — the pack that makes Analysis Pilot a
general-purpose data-analysis chat, not just a risk tool.

Applies to any dataset with ≥1 numeric series and computes what the domain packs
don't: per-series **latest value + latest change**, **trend** (first→last change
+ direction + per-period CAGR), **extremes with period labels**, **totals** and
**share of the combined total**, plus a cross-series **ranking** table. Every
number is a citable ``metric:`` record, so "summarize this", "what's the trend?",
and "which is highest?" get grounded, deterministic answers.

Record suffixes (latest / trend / peak / low / total / share) are disjoint from
every other pack's, so cids never collide (financial owns yoy/trend_vol/cagr;
volatility owns the tail-risk keys). Pure/deterministic, stdlib only.
"""

from __future__ import annotations

import math
import re
import statistics

from . import base, charts
from .base import cagr, slug, fmt_num, fmt_pct, ols_fit, iqr_outliers

KEY = "general_stats"
LABEL = "Data Overview"

_MAX_RANKED = 8
_MAX_OUTLIERS_SHOWN = 4

# Month/quarter cycle detection for seasonality. A period label maps to a
# (cycle_key, phase) — phase is the within-cycle slot (month 1..12, quarter
# 1..4) so we can compare like-with-like across cycles.
_QUARTER_RE = re.compile(r"(\d{4}).*?q\s*([1-4])", re.I)
_MONTH_RE = re.compile(r"(\d{4})[-/](\d{1,2})")


def _phase_of(label: str):
    """(period_len, phase, year) for a label — (4, q, year) for quarterly,
    (12, m, year) for monthly, else None. The year travels with the phase so
    callers can require observations from ≥2 DISTINCT cycles, not just ≥2
    observations in the same phase (which sub-monthly data — weekly/daily —
    can satisfy from a single calendar year alone)."""
    s = str(label or "")
    m = _QUARTER_RE.search(s)
    if m:
        return 4, int(m.group(2)), int(m.group(1))
    m = _MONTH_RE.search(s)
    if m and 1 <= int(m.group(2)) <= 12:
        return 12, int(m.group(2)), int(m.group(1))
    return None


def applies(normalized: dict) -> bool:
    return bool(normalized.get("series"))


def _indexed(values) -> list[tuple[int, float]]:
    """(index, value) pairs for finite numeric points, preserving positions so
    period labels stay aligned (nums() would lose the indices)."""
    out = []
    for i, v in enumerate(values or []):
        if isinstance(v, (int, float)) and not (isinstance(v, float) and math.isnan(v)):
            out.append((i, float(v)))
    return out


def _pct_change(prev: float, cur: float):
    """Sign-correct % change (delta over |base| — same rule as compare.py)."""
    if prev == 0:
        return None
    return (cur - prev) / abs(prev)


def _series_stats(values, periods) -> dict | None:
    pts = _indexed(values)
    if not pts:
        return None

    def label(i: int) -> str:
        if periods and i < len(periods):
            return str(periods[i])
        return f"#{i + 1}"

    first_i, first_v = pts[0]
    last_i, last_v = pts[-1]
    prev_v = pts[-2][1] if len(pts) >= 2 else None
    prev_i = pts[-2][0] if len(pts) >= 2 else None
    peak_i, peak_v = max(pts, key=lambda p: p[1])
    low_i, low_v = min(pts, key=lambda p: p[1])
    steps = last_i - first_i
    return {
        "n": len(pts),
        "latest": last_v, "latest_label": label(last_i),
        "prev": prev_v, "prev_label": (label(prev_i) if prev_i is not None else None),
        "latest_change": (_pct_change(prev_v, last_v) if prev_v is not None else None),
        "first": first_v, "first_label": label(first_i),
        "trend_change": (_pct_change(first_v, last_v) if len(pts) >= 2 else None),
        "direction": ("rising" if last_v > first_v else "falling" if last_v < first_v else "flat")
        if len(pts) >= 2 else None,
        "cagr": (cagr(first_v, last_v, steps) if steps >= 1 else None),
        "peak": peak_v, "peak_label": label(peak_i),
        "low": low_v, "low_label": label(low_i),
        "total": (sum(v for _, v in pts) if len(pts) >= 2 else None),
    }


def _seasonality(values, periods) -> str | None:
    """Same-phase comparison across cycles when the periods are quarterly or
    monthly and span ≥2 full cycles. Returns a one-line summary naming the
    strongest and weakest phase by average, or None when not applicable."""
    if not periods or not values:
        return None
    phased: dict[int, list[float]] = {}
    period_len = None
    years: set[int] = set()
    for lbl, v in zip(periods, values):
        if not isinstance(v, (int, float)) or (isinstance(v, float) and math.isnan(v)):
            continue
        ph = _phase_of(lbl)
        if ph is None:
            return None  # mixed/unparseable labels — not a clean cycle
        plen, slot, year = ph
        if period_len is None:
            period_len = plen
        elif period_len != plen:
            return None
        phased.setdefault(slot, []).append(float(v))
        years.add(year)
    if not phased or period_len is None:
        return None
    # Need ≥2 DISTINCT cycles (calendar years), not just ≥2 observations in the
    # same phase — sub-monthly data (weekly/daily) can rack up multiple same-
    # month observations within a single year alone.
    if len(years) < 2:
        return None
    if len(phased) < max(2, period_len // 2):
        return None
    avgs = {slot: statistics.fmean(vs) for slot, vs in phased.items()}
    hi = max(avgs, key=avgs.get)
    lo = min(avgs, key=avgs.get)
    if avgs[lo] == avgs[hi]:
        return None
    unit = "Q" if period_len == 4 else "month"
    swing = (avgs[hi] - avgs[lo]) / abs(avgs[lo]) if avgs[lo] else None
    swing_txt = f" ({fmt_pct(swing)} above the low)" if swing is not None else ""
    return (f"seasonality across {period_len}-period cycle: strongest {unit} {hi} "
            f"(avg {fmt_num(avgs[hi])}), weakest {unit} {lo} (avg {fmt_num(avgs[lo])}){swing_txt}.")


def compute(normalized: dict, config: dict, ds_key: str) -> dict:
    series = normalized.get("series") or {}
    periods = normalized.get("periods")

    stats: dict[str, dict] = {}
    for name, values in series.items():
        s = _series_stats(values, periods)
        if s:
            stats[name] = s
    if not stats:
        return {}

    records: list[dict] = []

    def rec(sl: str, key: str, name: str, text: str, when: str = "computed"):
        records.append({"cid": f"metric:{ds_key}:{sl}:{key}", "ref": f"{name} — {key}",
                        "summary": text, "when": when})

    def label(i: int) -> str:
        if periods and i < len(periods):
            return str(periods[i])
        return f"#{i + 1}"

    for name, s in stats.items():
        sl = slug(name)
        change = (f" ({'+' if s['latest_change'] >= 0 else ''}{fmt_pct(s['latest_change'])} vs {s['prev_label']})"
                  if s["latest_change"] is not None else "")
        rec(sl, "latest", name,
            f"{name} — latest ({s['latest_label']}): {fmt_num(s['latest'])}{change}.",
            when=s["latest_label"])
        if s["trend_change"] is not None or s["direction"]:
            bits = []
            if s["trend_change"] is not None:
                bits.append(f"{'+' if s['trend_change'] >= 0 else ''}{fmt_pct(s['trend_change'])} "
                            f"{s['first_label']}→{s['latest_label']}")
            if s["direction"]:
                bits.append(s["direction"])
            if s["cagr"] is not None:
                bits.append(f"CAGR {'+' if s['cagr'] >= 0 else ''}{fmt_pct(s['cagr'])}/period")
            rec(sl, "trend", name, f"{name} — trend: {'; '.join(bits)}.")
        if s["n"] >= 2:
            rec(sl, "peak", name, f"{name} — peak: {fmt_num(s['peak'])} in {s['peak_label']}.")
            rec(sl, "low", name, f"{name} — low: {fmt_num(s['low'])} in {s['low_label']}.")
        if s["total"] is not None:
            rec(sl, "total", name, f"{name} — total across {s['n']} points: {fmt_num(s['total'])}.")

        # OLS fit — slope + R² separates a real trend from noise. The first→last
        # trend record says "how much"; this says "how reliable".
        slope, r2 = ols_fit(series.get(name))
        if slope is not None and r2 is not None:
            quality = ("strong linear trend" if r2 >= 0.7 else
                       "moderate trend" if r2 >= 0.4 else "weak/noisy — no reliable linear trend")
            rec(sl, "fit", name,
                f"{name} — linear fit: {'+' if slope >= 0 else ''}{fmt_num(slope)}/period, "
                f"R²={fmt_num(r2)} ({quality}).")

        # IQR outliers — with period labels so the AI can name the anomalous points.
        outs = iqr_outliers(series.get(name))
        if outs:
            shown = outs[:_MAX_OUTLIERS_SHOWN]
            listed = ", ".join(f"{label(i)} ({fmt_num(v)})" for i, v in shown)
            more = f" +{len(outs) - len(shown)} more" if len(outs) > len(shown) else ""
            rec(sl, "outliers", name,
                f"{name} — {len(outs)} outlier(s) beyond 1.5×IQR: {listed}{more}.")

        # Seasonality — same-phase comparison across cycles (quarterly/monthly,
        # ≥2 full cycles). Backs the corp-finance "compare like periods" lens.
        seas = _seasonality(series.get(name), periods)
        if seas:
            rec(sl, "seasonality", name, f"{name} — {seas}")

    # Shares of the combined total — only meaningful when every total is
    # positive (mixed-sign shares are nonsense).
    totals = {n: s["total"] for n, s in stats.items() if s["total"] is not None}
    grand = sum(totals.values()) if totals else 0.0
    if len(totals) > 1 and grand > 0 and all(t > 0 for t in totals.values()):
        for name, t in totals.items():
            rec(slug(name), "share", name,
                f"{name} — share of combined total: {fmt_pct(t / grand)}.")

    # Cross-series ranking (by latest value), rendered + citable via the
    # per-series latest records above.
    ranked = sorted(stats.items(), key=lambda kv: kv[1]["latest"], reverse=True)

    table_rows = [[
        name,
        f"{fmt_num(s['latest'])} ({s['latest_label']})",
        fmt_pct(s["latest_change"]) if s["latest_change"] is not None else "—",
        fmt_pct(s["trend_change"]) if s["trend_change"] is not None else "—",
        fmt_pct(s["cagr"]) if s["cagr"] is not None else "—",
        f"{fmt_num(s['low'])} @ {s['low_label']}",
        f"{fmt_num(s['peak'])} @ {s['peak_label']}",
        fmt_num(s["total"]) if s["total"] is not None else "—",
    ] for name, s in ranked]
    tables = [{"title": "Per-series overview",
               "columns": ["Series", "Latest", "Δ latest", "Trend", "CAGR", "Low", "Peak", "Total"],
               "rows": table_rows}]

    chart_blocks = []
    top_ranked = ranked[:_MAX_RANKED]
    if len(top_ranked) > 1:
        bar = charts.bar_svg([n for n, _ in top_ranked], [s["latest"] for _, s in top_ranked])
        if bar:
            chart_blocks.append({"title": "Latest value by series", "svg": bar})
    top_name = ranked[0][0]
    spark = charts.sparkline_svg(series.get(top_name))
    if spark:
        chart_blocks.append({"title": f"{top_name} — series", "svg": spark})

    tiles = []
    top_s = ranked[0][1]
    tiles.append({"label": f"Highest (latest) — {top_name}", "value": fmt_num(top_s["latest"])})
    if top_s["latest_change"] is not None:
        tiles.append({"label": f"{top_name} — latest change", "value": fmt_pct(top_s["latest_change"])})
    tiles.append({"label": "Series", "value": str(len(stats))})
    if periods:
        tiles.append({"label": "Periods", "value": str(len(periods))})

    # Machine-readable values keyed per column so cross-dataset comparisons
    # diff matching columns (e.g. Revenue latest FY22 vs FY23).
    values: dict[str, float] = {}
    for name, s in stats.items():
        sl = slug(name)
        values[f"{sl}_latest"] = s["latest"]
        if s["total"] is not None:
            values[f"{sl}_total"] = s["total"]

    return {"label": LABEL, "tiles": tiles, "tables": tables,
            "charts": chart_blocks, "records": records, "values": values}


ANALYZER = base.Analyzer(KEY, LABEL, applies, compute)
