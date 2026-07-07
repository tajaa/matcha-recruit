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

from . import base, charts
from .base import cagr, slug, fmt_num, fmt_pct

KEY = "general_stats"
LABEL = "Data Overview"

_MAX_RANKED = 8


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
