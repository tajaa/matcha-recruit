"""Volatility & risk analyzer pack (the flagship, domain-agnostic).

Applies to any dataset with ≥1 numeric series. For each column it derives
period-over-period returns (default: the column is a level series) and computes
volatility, annualized volatility, coefficient of variation, historical VaR95 /
VaR99 + CVaR, max drawdown, a Sharpe-like ratio, and downside deviation — plus a
pairwise Pearson correlation matrix across all numeric columns.

Series whose mapped role belongs to another pack's domain (financial-statement
line items, insurance loss fields, inventory fields) get descriptive stats only:
"Revenue VaR95 from 3 annual points" is statistically meaningless, and emitting
it as a citable record would entitle the grounded AI to quote it.

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
from .mapping import _FINANCIAL_ROLES, _INSURANCE_ROLES, _INVENTORY_ROLES

KEY = "volatility_risk"
LABEL = "Volatility & Risk"

# Correlation records grow O(N²); cap what enters the citable corpus to the
# strongest relationships (the matrix chart still shows everything).
_MAX_CORR_RECORDS = 40

# Roles claimed by domain packs — tail-risk metrics on these series are noise.
_TAIL_EXCLUDED_ROLES = _FINANCIAL_ROLES | _INSURANCE_ROLES | _INVENTORY_ROLES


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


def _column_metrics(values, kind, ppy, rf, *, tail: bool) -> dict:
    xs = nums(values)
    m = {
        "n": len(xs),
        "mean": mean(xs),
        "min": min(xs) if xs else None,
        "max": max(xs) if xs else None,
        "range": (max(xs) - min(xs)) if xs else None,
        "coefficient_of_variation": coefficient_of_variation(xs),
        "volatility": None, "annualized_volatility": None,
        "var95": None, "var99": None, "cvar95": None,
        "max_drawdown": None, "sharpe_like": None, "downside_deviation": None,
    }
    if tail:
        rets, index = _analysis_series(values, kind)
        vol = stdev(rets)
        m.update({
            "volatility": vol,
            "annualized_volatility": annualize_vol(vol, ppy),
            "var95": value_at_risk(rets, 5),
            "var99": value_at_risk(rets, 1),
            "cvar95": expected_shortfall(rets, 5),
            "max_drawdown": max_drawdown(index),
            "sharpe_like": sharpe_like(rets, rf),
            "downside_deviation": downside_deviation(rets),
        })
    return m


def _headline_vol(m: dict):
    """Annualized vol when available, else per-period vol. Explicit None checks
    — `or` would conflate a legitimate 0.0 with missing."""
    av = m.get("annualized_volatility")
    return av if av is not None else m.get("volatility")


def _worst(per_col: dict, key: str):
    """(value, series name) of the max non-None value for `key`, or None."""
    candidates = [(m[key], n) for n, m in per_col.items() if m.get(key) is not None]
    return max(candidates) if candidates else None


def compute(normalized: dict, config: dict, ds_key: str) -> dict:
    series = normalized.get("series") or {}
    roles = normalized.get("roles") or {}
    kinds = (config or {}).get("column_kinds") or {}
    ppy = (config or {}).get("periods_per_year")
    rf = float((config or {}).get("risk_free") or 0.0)

    per_col: dict[str, dict] = {}
    records: list[dict] = []
    notes: list[str] = []
    for name, values in series.items():
        tail = roles.get(name) not in _TAIL_EXCLUDED_ROLES
        m = _column_metrics(values, kinds.get(name, "level"), ppy, rf, tail=tail)
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

        if m["coefficient_of_variation"] is not None:
            rec("cov", f"{name} — coefficient of variation: {fmt_pct(m['coefficient_of_variation'])} of the mean.")
        if not tail:
            continue  # descriptive stats only — tail metrics belong to no series with a domain role
        kind = kinds.get(name, "level")
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
        if m["downside_deviation"] is not None:
            rec("downside_deviation", f"{name} — downside deviation: {fmt_pct(m['downside_deviation'])}.")

    excluded = [n for n in series if roles.get(n) in _TAIL_EXCLUDED_ROLES]
    if excluded:
        notes.append(
            f"Tail-risk metrics (VaR/drawdown/Sharpe) not computed for domain-mapped series "
            f"({', '.join(excluded[:6])}{'…' if len(excluded) > 6 else ''}) — see their domain pack instead."
        )

    # Correlation matrix over the raw numeric series (index-aligned). The full
    # matrix renders as a chart; only the strongest |r| pairs become citable
    # records (O(N²) otherwise floods the corpus and the AI prompt).
    names = list(series.keys())
    matrix = [[1.0 if i == j else pearson(series[a], series[b])
               for j, b in enumerate(names)] for i, a in enumerate(names)]
    pairs = []
    for i, a in enumerate(names):
        for j in range(i + 1, len(names)):
            v = matrix[i][j]
            if v is not None:
                pairs.append((abs(v), a, names[j], v))
    pairs.sort(reverse=True)
    for _, a, b, v in pairs[:_MAX_CORR_RECORDS]:
        records.append({
            "cid": f"corr:{ds_key}:{slug(a)}__{slug(b)}",
            "ref": f"Correlation {a} / {b}",
            "summary": f"Correlation({a}, {b}): {fmt_num(v)}.",
            "when": "computed",
        })
    if len(pairs) > _MAX_CORR_RECORDS:
        notes.append(f"Correlations: {_MAX_CORR_RECORDS} strongest of {len(pairs)} pairs are citable; "
                     "the matrix chart shows all.")

    # Renderable tables + tiles + charts (tail series only in the risk table).
    tail_cols = {n: m for n, m in per_col.items() if roles.get(n) not in _TAIL_EXCLUDED_ROLES}
    metric_cols = ["Series", "σ vol", "Ann. vol", "VaR95", "VaR99", "Max DD", "Sharpe-like", "CoV"]
    rows = [[
        name, fmt_pct(m["volatility"]), fmt_pct(m["annualized_volatility"]),
        fmt_pct(m["var95"]), fmt_pct(m["var99"]), fmt_pct(m["max_drawdown"]),
        fmt_num(m["sharpe_like"]), fmt_pct(m["coefficient_of_variation"]),
    ] for name, m in tail_cols.items()]
    tables = [{"title": "Per-series risk metrics", "columns": metric_cols, "rows": rows}] if rows else []

    # Single aggregation pass shared by tiles and the machine-readable values.
    ranked = sorted(tail_cols.items(),
                    key=lambda item: (_headline_vol(item[1]) is not None, _headline_vol(item[1]) or 0.0),
                    reverse=True)
    top = ranked[0] if ranked and _headline_vol(ranked[0][1]) is not None else None
    worst_dd = _worst(tail_cols, "max_drawdown")
    worst_var = _worst(tail_cols, "var95")

    chart_blocks = []
    if ranked:
        top_name = ranked[0][0]
        spark = charts.sparkline_svg(series.get(top_name))
        if spark:
            chart_blocks.append({"title": f"{top_name} — series", "svg": spark})
        _, index = _analysis_series(series.get(top_name), kinds.get(top_name, "level"))
        dd = charts.drawdown_svg(index)
        if dd:
            chart_blocks.append({"title": f"{top_name} — drawdown profile", "svg": dd})
        vol_pairs = [(n, _headline_vol(m)) for n, m in ranked[:8] if _headline_vol(m) is not None]
        if vol_pairs:
            vol_bar = charts.bar_svg([n for n, _ in vol_pairs], [v for _, v in vol_pairs], pct=True)
            if vol_bar:
                chart_blocks.append({"title": "Volatility by series", "svg": vol_bar})
    if len(names) > 1:
        hm = charts.heatmap_svg(names, matrix)
        if hm:
            chart_blocks.append({"title": "Correlation matrix", "svg": hm})

    tiles = []
    if top is not None:
        tiles.append({"label": f"Highest vol — {top[0]}", "value": fmt_pct(_headline_vol(top[1]))})
    if worst_dd is not None:
        tiles.append({"label": f"Worst drawdown — {worst_dd[1]}", "value": fmt_pct(worst_dd[0])})
    if worst_var is not None:
        tiles.append({"label": f"Worst VaR95 — {worst_var[1]}", "value": fmt_pct(worst_var[0])})
    tiles.append({"label": "Series analyzed", "value": str(len(names))})

    values = {"series_count": float(len(names))}
    if top is not None:
        values["top_annualized_volatility"] = _headline_vol(top[1])
    if worst_dd is not None:
        values["worst_max_drawdown"] = worst_dd[0]
    if worst_var is not None:
        values["worst_var95"] = worst_var[0]

    return {"label": LABEL, "tiles": tiles, "tables": tables,
            "charts": chart_blocks, "records": records, "values": values,
            "notes": notes}


ANALYZER = base.Analyzer(KEY, LABEL, applies, compute)
