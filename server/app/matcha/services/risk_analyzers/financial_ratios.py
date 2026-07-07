"""Financial-statement ratio pack — liquidity, leverage, profitability,
efficiency + multi-period growth and trend volatility. For P&Ls, balance sheets,
and 10-K financials (tabular or document-extracted line-items × periods).

Ratios are computed on the LATEST period; growth/trend volatility use the full
period series. Pure/deterministic — divides guard zero denominators to None.
"""

from __future__ import annotations

from . import base, charts
from .base import returns, stdev, cagr, slug, fmt_pct, fmt_ratio, fmt_money, nums
from .mapping import series_for_role, has_roles, _FINANCIAL_ROLES


def applies(normalized: dict) -> bool:
    return has_roles(normalized, _FINANCIAL_ROLES, minimum=2)


def _latest(values):
    for v in reversed(nums(values) or []):
        return v
    xs = [x for x in (values or []) if x is not None]
    return xs[-1] if xs else None


def _div(a, b):
    if a is None or b is None or b == 0:
        return None
    return a / b


def _role(normalized, role):
    return series_for_role(normalized, role)


def compute(normalized: dict, config: dict, ds_key: str) -> dict:
    periods = normalized.get("periods") or []

    def latest_role(r):
        return _latest(_role(normalized, r))

    rev = latest_role("revenue")
    cogs = latest_role("cogs")
    gross = latest_role("gross_profit")
    if gross is None and rev is not None and cogs is not None:
        gross = rev - cogs
    op = latest_role("operating_income")
    net = latest_role("net_income")
    interest = latest_role("interest_expense")
    tot_assets = latest_role("total_assets")
    cur_assets = latest_role("current_assets")
    inv = latest_role("inventory_value")
    cur_liab = latest_role("current_liabilities")
    tot_liab = latest_role("total_liabilities")
    equity = latest_role("total_equity")

    ratios = {
        "current_ratio": (_div(cur_assets, cur_liab), fmt_ratio, "Current ratio", "liquidity"),
        "quick_ratio": (_div((cur_assets - inv) if (cur_assets is not None and inv is not None) else cur_assets, cur_liab),
                        fmt_ratio, "Quick ratio", "liquidity"),
        "debt_to_equity": (_div(tot_liab, equity), fmt_ratio, "Debt-to-equity", "leverage"),
        "interest_coverage": (_div(op, interest), fmt_ratio, "Interest coverage", "leverage"),
        "gross_margin": (_div(gross, rev), fmt_pct, "Gross margin", "profitability"),
        "operating_margin": (_div(op, rev), fmt_pct, "Operating margin", "profitability"),
        "net_margin": (_div(net, rev), fmt_pct, "Net margin", "profitability"),
        "return_on_assets": (_div(net, tot_assets), fmt_pct, "Return on assets", "profitability"),
        "return_on_equity": (_div(net, equity), fmt_pct, "Return on equity", "profitability"),
        "asset_turnover": (_div(rev, tot_assets), fmt_ratio, "Asset turnover", "efficiency"),
    }

    records: list[dict] = []
    ratio_rows = []
    for key, (val, fmt, label, group) in ratios.items():
        if val is None:
            continue
        ratio_rows.append([label, fmt(val), group])
        records.append({
            "cid": f"ratio:{ds_key}:{key}",
            "ref": label,
            "summary": f"{label} (latest period): {fmt(val)}.",
            "when": (periods[-1] if periods else "latest"),
        })

    # Growth + trend volatility on the headline lines.
    growth_rows = []
    for role in ("revenue", "gross_profit", "operating_income", "net_income", "total_assets"):
        series = _role(normalized, role)
        xs = nums(series)
        if len(xs) < 2:
            continue
        g = returns(xs)
        yoy = g[-1] if g else None
        trend_vol = stdev(g)
        multi = cagr(xs[0], xs[-1], len(xs) - 1)
        label = role.replace("_", " ").title()
        growth_rows.append([label, fmt_pct(yoy), fmt_pct(multi), fmt_pct(trend_vol)])
        sl = slug(role)
        if yoy is not None:
            p0 = periods[-2] if len(periods) >= 2 else "prior"
            p1 = periods[-1] if periods else "latest"
            records.append({"cid": f"metric:{ds_key}:{sl}:yoy", "ref": f"{label} YoY",
                            "summary": f"{label} growth {p0}→{p1}: {fmt_pct(yoy)}.", "when": p1})
        if trend_vol is not None:
            records.append({"cid": f"metric:{ds_key}:{sl}:trend_vol", "ref": f"{label} trend volatility",
                            "summary": f"{label} period-over-period growth volatility: {fmt_pct(trend_vol)}.",
                            "when": "trend"})
        if multi is not None:
            records.append({"cid": f"metric:{ds_key}:{sl}:cagr", "ref": f"{label} CAGR",
                            "summary": f"{label} compound growth over {len(xs) - 1} periods: {fmt_pct(multi)}.",
                            "when": "trend"})

    tables = []
    if ratio_rows:
        tables.append({"title": "Financial ratios (latest period)",
                       "columns": ["Ratio", "Value", "Category"], "rows": ratio_rows})
    if growth_rows:
        tables.append({"title": "Growth & trend volatility",
                       "columns": ["Line", "Latest YoY", "CAGR", "Trend σ"], "rows": growth_rows})

    chart_blocks = []
    rev_series = _role(normalized, "revenue")
    if rev_series and len(nums(rev_series)) > 1:
        spark = charts.sparkline_svg(rev_series)
        if spark:
            chart_blocks.append({"title": "Revenue trend", "svg": spark})
    margin_labels = [r for r in ("gross_margin", "operating_margin", "net_margin") if ratios[r][0] is not None]
    if margin_labels:
        bar = charts.bar_svg([ratios[k][2] for k in margin_labels],
                             [ratios[k][0] for k in margin_labels], pct=True)
        if bar:
            chart_blocks.append({"title": "Margin profile", "svg": bar})

    tiles = []
    if rev is not None:
        tiles.append({"label": "Revenue (latest)", "value": fmt_money(rev)})
    if ratios["net_margin"][0] is not None:
        tiles.append({"label": "Net margin", "value": fmt_pct(ratios["net_margin"][0])})
    if ratios["current_ratio"][0] is not None:
        tiles.append({"label": "Current ratio", "value": fmt_ratio(ratios["current_ratio"][0])})
    if ratios["debt_to_equity"][0] is not None:
        tiles.append({"label": "Debt-to-equity", "value": fmt_ratio(ratios["debt_to_equity"][0])})

    values = {k: v[0] for k, v in ratios.items() if v[0] is not None}
    if rev is not None:
        values["revenue"] = rev
    if net is not None:
        values["net_income"] = net

    return {"label": "Financial Ratios", "tiles": tiles, "tables": tables,
            "charts": chart_blocks, "records": records, "values": values}


ANALYZER = base.Analyzer("financial_ratios", "Financial Ratios", applies, compute)
