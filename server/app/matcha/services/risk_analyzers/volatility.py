"""Volatility & risk analyzer pack (the flagship, domain-agnostic).

Applies to any dataset with ≥1 numeric series. For each column it derives
period-over-period returns (default: the column is a level series) and computes
volatility, annualized volatility, coefficient of variation, historical VaR95 /
VaR99 + CVaR, max drawdown, a Sharpe-like ratio, and downside deviation — plus a
pairwise Pearson correlation matrix across all numeric columns.

Pure/deterministic. Config knobs (per dataset, user-editable):
  column_kinds:     {col: "level"|"returns"}   default "level"
  periods_per_year: int|None                    annualization factor
  risk_free:        float                        per-period, default 0
"""

from __future__ import annotations

from . import base, charts
from .base import (
    nums, returns, stdev, mean, coefficient_of_variation, value_at_risk,
    expected_shortfall, max_drawdown, cumulative_index, sharpe_like,
    downside_deviation, annualize_vol, pearson, slug, fmt_pct, fmt_num,
)

KEY = "volatility_risk"
LABEL = "Volatility & Risk"


def applies(normalized: dict) -> bool:
    return bool(normalized.get("series"))


def _analysis_series(values, kind: str):
    """(returns_series, index_series). For a level column, returns are the
    pct-change and the index is the levels. For a returns column, the values
    ARE the returns and the index is the growth-of-1 they imply."""
    xs = nums(values)
    if kind == "returns":
        return xs, cumulative_index(xs)
    return returns(xs), xs


def _column_metrics(values, kind, ppy, rf) -> dict:
    xs = nums(values)
    rets, index = _analysis_series(values, kind)
    vol = stdev(rets)
    return {
        "n": len(xs),
        "mean": mean(xs),
        "min": min(xs) if xs else None,
        "max": max(xs) if xs else None,
        "range": (max(xs) - min(xs)) if xs else None,
        "volatility": vol,
        "annualized_volatility": annualize_vol(vol, ppy),
        "coefficient_of_variation": coefficient_of_variation(xs),
        "var95": value_at_risk(rets, 5),
        "var99": value_at_risk(rets, 1),
        "cvar95": expected_shortfall(rets, 5),
        "max_drawdown": max_drawdown(index),
        "sharpe_like": sharpe_like(rets, rf),
        "downside_deviation": downside_deviation(rets),
    }


def compute(normalized: dict, config: dict, ds_key: str) -> dict:
    series = normalized.get("series") or {}
    kinds = (config or {}).get("column_kinds") or {}
    ppy = (config or {}).get("periods_per_year")
    rf = float((config or {}).get("risk_free") or 0.0)

    per_col: dict[str, dict] = {}
    records: list[dict] = []
    for name, values in series.items():
        kind = kinds.get(name, "level")
        m = _column_metrics(values, kind, ppy, rf)
        per_col[name] = m
        sl = slug(name)
        records.append({
            "cid": f"series:{ds_key}:{sl}",
            "ref": f"{name} (series)",
            "summary": f"{name}: {m['n']} points, mean {fmt_num(m['mean'])}, "
                       f"range {fmt_num(m['min'])}–{fmt_num(m['max'])}.",
            "when": "series",
        })

        def rec(key, text):
            records.append({"cid": f"metric:{ds_key}:{sl}:{key}", "ref": f"{name} — {key}",
                            "summary": text, "when": "computed"})

        if m["volatility"] is not None:
            ann = f" (annualized {fmt_pct(m['annualized_volatility'])})" if m["annualized_volatility"] is not None else ""
            rec("volatility", f"{name} — volatility (σ of {kind} returns): {fmt_pct(m['volatility'])} per period{ann}.")
        if m["var95"] is not None:
            rec("var95", f"{name} — historical VaR (95%): {fmt_pct(m['var95'])} one-period loss not exceeded 95% of the time.")
        if m["var99"] is not None:
            rec("var99", f"{name} — historical VaR (99%): {fmt_pct(m['var99'])}.")
        if m["cvar95"] is not None:
            rec("cvar95", f"{name} — expected shortfall (CVaR 95%): {fmt_pct(m['cvar95'])} average loss in the worst 5% of periods.")
        if m["max_drawdown"] is not None:
            rec("max_drawdown", f"{name} — maximum drawdown: {fmt_pct(m['max_drawdown'])} peak-to-trough decline.")
        if m["sharpe_like"] is not None:
            rec("sharpe_like", f"{name} — Sharpe-like ratio (mean/σ of returns): {fmt_num(m['sharpe_like'])}.")
        if m["coefficient_of_variation"] is not None:
            rec("cov", f"{name} — coefficient of variation: {fmt_pct(m['coefficient_of_variation'])} of the mean.")
        if m["downside_deviation"] is not None:
            rec("downside_deviation", f"{name} — downside deviation: {fmt_pct(m['downside_deviation'])}.")

    # Correlation matrix over the raw numeric series (index-aligned).
    names = list(series.keys())
    matrix = [[1.0 if i == j else pearson(series[a], series[b])
               for j, b in enumerate(names)] for i, a in enumerate(names)]
    for i, a in enumerate(names):
        for j in range(i + 1, len(names)):
            v = matrix[i][j]
            if v is None:
                continue
            records.append({
                "cid": f"corr:{ds_key}:{slug(a)}__{slug(names[j])}",
                "ref": f"Correlation {a} / {names[j]}",
                "summary": f"Correlation({a}, {names[j]}): {fmt_num(v)}.",
                "when": "computed",
            })

    # Renderable tables + tiles + charts.
    metric_cols = ["Series", "σ vol", "Ann. vol", "VaR95", "VaR99", "Max DD", "Sharpe-like", "CoV"]
    rows = [[
        name, fmt_pct(m["volatility"]), fmt_pct(m["annualized_volatility"]),
        fmt_pct(m["var95"]), fmt_pct(m["var99"]), fmt_pct(m["max_drawdown"]),
        fmt_num(m["sharpe_like"]), fmt_pct(m["coefficient_of_variation"]),
    ] for name, m in per_col.items()]
    tables = [{"title": "Per-series risk metrics", "columns": metric_cols, "rows": rows}]

    chart_blocks = []
    # Headline column = highest annualized (or raw) volatility.
    def _vol_key(item):
        v = item[1].get("annualized_volatility") or item[1].get("volatility") or 0.0
        return v
    ranked = sorted(per_col.items(), key=_vol_key, reverse=True)
    if ranked:
        top_name, top = ranked[0]
        spark = charts.sparkline_svg(series.get(top_name))
        if spark:
            chart_blocks.append({"title": f"{top_name} — series", "svg": spark})
        rets, index = _analysis_series(series.get(top_name), kinds.get(top_name, "level"))
        dd = charts.drawdown_svg(index)
        if dd:
            chart_blocks.append({"title": f"{top_name} — drawdown profile", "svg": dd})
        vol_bar = charts.bar_svg([n for n, _ in ranked[:8]],
                                 [m.get("annualized_volatility") or m.get("volatility") for _, m in ranked[:8]],
                                 pct=True)
        if vol_bar:
            chart_blocks.append({"title": "Volatility by series", "svg": vol_bar})
    if len(names) > 1:
        hm = charts.heatmap_svg(names, matrix)
        if hm:
            chart_blocks.append({"title": "Correlation matrix", "svg": hm})

    tiles = []
    if ranked:
        top_name, top = ranked[0]
        tiles.append({"label": f"Highest vol — {top_name}",
                      "value": fmt_pct(top.get("annualized_volatility") or top.get("volatility"))})
        worst_dd = max((m.get("max_drawdown") or 0.0, n) for n, m in per_col.items())
        tiles.append({"label": f"Worst drawdown — {worst_dd[1]}", "value": fmt_pct(worst_dd[0])})
        worst_var = max((m.get("var95") or 0.0, n) for n, m in per_col.items())
        tiles.append({"label": f"Worst VaR95 — {worst_var[1]}", "value": fmt_pct(worst_var[0])})
    tiles.append({"label": "Series analyzed", "value": str(len(names))})

    values = {"series_count": float(len(names))}
    if ranked:
        _, top = ranked[0]
        values["top_annualized_volatility"] = top.get("annualized_volatility") or top.get("volatility")
        values["worst_max_drawdown"] = max((m.get("max_drawdown") or 0.0) for m in per_col.values())
        values["worst_var95"] = max((m.get("var95") or 0.0) for m in per_col.values())

    return {"label": LABEL, "tiles": tiles, "tables": tables,
            "charts": chart_blocks, "records": records, "values": values}


ANALYZER = base.Analyzer(KEY, LABEL, applies, compute)
