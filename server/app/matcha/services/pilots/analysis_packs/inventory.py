"""Inventory / operational-risk pack — turnover, days-on-hand, demand
variability, stockout exposure, and volume concentration (Herfindahl).

Applies when inventory/units roles are present. Pure/deterministic.
"""

from __future__ import annotations

from . import base, charts
from .base import mean, coefficient_of_variation, slug, fmt_num, fmt_pct, fmt_ratio, nums
from .mapping import series_for_role, has_roles, _INVENTORY_ROLES


def applies(normalized: dict) -> bool:
    return has_roles(normalized, _INVENTORY_ROLES | {"inventory_value"}, minimum=1) and \
        has_roles(normalized, _INVENTORY_ROLES | {"inventory_value", "units_sold", "cogs"}, minimum=2)


def _div(a, b):
    if a is None or b is None or b == 0:
        return None
    return a / b


def _herfindahl(series_map: dict) -> float | None:
    """HHI over item totals — 0 (perfectly diverse) to 1 (single item)."""
    totals = [sum(nums(v)) for v in series_map.values()]
    totals = [t for t in totals if t > 0]
    if len(totals) < 2:
        return None
    grand = sum(totals)
    if grand == 0:
        return None
    return sum((t / grand) ** 2 for t in totals)


def compute(normalized: dict, config: dict, ds_key: str) -> dict:
    series = normalized.get("series") or {}

    def role(r):
        return series_for_role(normalized, r)

    on_hand = role("units_on_hand")
    sold = role("units_sold")
    cogs = role("cogs")
    inv_value = role("inventory_value")
    reorder = role("reorder_point")

    avg_on_hand = mean(on_hand)
    total_sold = sum(nums(sold)) if sold else None
    avg_inv_value = mean(inv_value)

    turnover = _div(sum(nums(cogs)) if cogs else None, avg_inv_value)
    if turnover is None:
        turnover = _div(total_sold, avg_on_hand)
    days_on_hand = _div(365.0, turnover) if turnover else None
    demand_var = coefficient_of_variation(sold) if sold else None

    # Stockout exposure: share of periods where on-hand fell below reorder point
    # (or below that period's demand when no reorder point is recorded).
    stockout = None
    oh = nums(on_hand) if on_hand else []
    ref = nums(reorder) if reorder else (nums(sold) if sold else [])
    if oh and ref:
        pairs = list(zip(oh, ref))
        if pairs:
            stockout = sum(1 for h, r in pairs if h < r) / len(pairs)

    hhi = _herfindahl(series)

    metrics = {
        "inventory_turnover": (turnover, fmt_ratio, "Inventory turnover"),
        "days_on_hand": (days_on_hand, fmt_num, "Days on hand"),
        "demand_variability": (demand_var, fmt_pct, "Demand variability (CoV)"),
        "stockout_exposure": (stockout, fmt_pct, "Stockout exposure (periods)"),
        "concentration_hhi": (hhi, fmt_num, "Volume concentration (HHI)"),
    }

    records: list[dict] = []
    rows = []
    for key, (val, fmt, label) in metrics.items():
        if val is None:
            continue
        rows.append([label, fmt(val)])
        records.append({
            "cid": f"metric:{ds_key}:inventory:{key}",
            "ref": label,
            "summary": f"{label}: {fmt(val)}.",
            "when": "computed",
        })

    tables = [{"title": "Operational risk metrics", "columns": ["Metric", "Value"], "rows": rows}] if rows else []

    chart_blocks = []
    if sold and len(nums(sold)) > 1:
        spark = charts.sparkline_svg(sold)
        if spark:
            chart_blocks.append({"title": "Demand (units sold) trend", "svg": spark})

    tiles = []
    if turnover is not None:
        tiles.append({"label": "Turnover", "value": fmt_ratio(turnover)})
    if days_on_hand is not None:
        tiles.append({"label": "Days on hand", "value": fmt_num(days_on_hand)})
    if demand_var is not None:
        tiles.append({"label": "Demand variability", "value": fmt_pct(demand_var)})
    if stockout is not None:
        tiles.append({"label": "Stockout exposure", "value": fmt_pct(stockout)})

    values = {k: v[0] for k, v in metrics.items() if v[0] is not None}

    return {"label": "Inventory & Operations", "tiles": tiles, "tables": tables,
            "charts": chart_blocks, "records": records, "values": values}


ANALYZER = base.Analyzer("inventory_ops", "Inventory & Operations", applies, compute)
