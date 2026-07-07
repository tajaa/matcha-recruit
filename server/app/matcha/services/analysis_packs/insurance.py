"""Insurance loss/claims pack — the shape insurance brokers submit.

Loss ratio (incurred / premium), claim frequency (per exposure) and severity
(incurred / claim count), paid-to-incurred development, and open-claim ratio.
Computed on the latest period plus a per-period loss-ratio series where periods
align. Pure/deterministic.
"""

from __future__ import annotations

from . import base, charts
from .base import returns, stdev, slug, fmt_pct, fmt_money, fmt_num, nums
from .mapping import series_for_role, has_roles, _INSURANCE_ROLES


def applies(normalized: dict) -> bool:
    return has_roles(normalized, {"losses_incurred", "premium", "claim_count"}, minimum=1) and \
        has_roles(normalized, _INSURANCE_ROLES, minimum=2)


def _latest(values):
    xs = [x for x in (values or []) if x is not None]
    return xs[-1] if xs else None


def _div(a, b):
    if a is None or b is None or b == 0:
        return None
    return a / b


def compute(normalized: dict, config: dict, ds_key: str) -> dict:
    periods = normalized.get("periods") or []

    def role(r):
        return series_for_role(normalized, r)

    incurred = role("losses_incurred")
    paid = role("losses_paid")
    premium = role("premium")
    exposure = role("exposure")
    claims = role("claim_count")
    open_claims = role("open_claims")

    l_incurred = _latest(incurred)
    l_paid = _latest(paid)
    l_prem = _latest(premium)
    l_expo = _latest(exposure)
    l_claims = _latest(claims)
    l_open = _latest(open_claims)

    metrics = {
        "loss_ratio": (_div(l_incurred, l_prem), fmt_pct, "Loss ratio (incurred/premium)"),
        "paid_ratio": (_div(l_paid, l_prem), fmt_pct, "Paid loss ratio"),
        "paid_to_incurred": (_div(l_paid, l_incurred), fmt_pct, "Paid-to-incurred"),
        "frequency": (_div(l_claims, l_expo) if l_expo else None, fmt_num, "Claim frequency (per exposure)"),
        "severity": (_div(l_incurred, l_claims), fmt_money, "Average severity (incurred/claim)"),
        "open_ratio": (_div(l_open, l_claims), fmt_pct, "Open-claim ratio"),
    }

    records: list[dict] = []
    rows = []
    for key, (val, fmt, label) in metrics.items():
        if val is None:
            continue
        rows.append([label, fmt(val)])
        records.append({
            "cid": f"metric:{ds_key}:insurance:{key}",
            "ref": label,
            "summary": f"{label} (latest period): {fmt(val)}.",
            "when": (periods[-1] if periods else "latest"),
        })

    # Per-period loss ratio (development): pair incurred and premium at the SAME
    # period index — a period is skipped when either side is missing. Stripping
    # Nones from each series independently would silently pair values from
    # different periods.
    lr_points: list[tuple[str, float]] = []  # (period label, loss ratio)
    for idx, (inc, prem) in enumerate(zip(incurred or [], premium or [])):
        if inc is None or prem is None:
            continue
        lr = _div(inc, prem)
        if lr is None:
            continue
        label = periods[idx] if idx < len(periods) else str(idx + 1)
        lr_points.append((label, lr))
    if len(lr_points) >= 2:
        trend = stdev([v for _, v in lr_points])
        if trend is not None:
            records.append({"cid": f"metric:{ds_key}:insurance:loss_ratio_volatility",
                            "ref": "Loss-ratio volatility",
                            "summary": f"Loss-ratio volatility across periods: {fmt_pct(trend)}.",
                            "when": "trend"})

    # Incurred development (period-over-period growth of incurred losses).
    inc_n = nums(incurred)
    if len(inc_n) >= 2:
        dev = returns(inc_n)
        if dev:
            records.append({"cid": f"metric:{ds_key}:insurance:incurred_development",
                            "ref": "Incurred development",
                            "summary": f"Latest period-over-period incurred loss change: {fmt_pct(dev[-1])}.",
                            "when": (periods[-1] if periods else "latest")})

    tables = [{"title": "Loss & claims metrics (latest period)",
               "columns": ["Metric", "Value"], "rows": rows}] if rows else []
    if lr_points:
        tables.append({"title": "Loss ratio by period",
                       "columns": ["Period", "Loss ratio"],
                       "rows": [[label, fmt_pct(v)] for label, v in lr_points]})

    chart_blocks = []
    if len(lr_points) >= 2:
        bar = charts.bar_svg([label for label, _ in lr_points],
                             [v for _, v in lr_points], pct=True)
        if bar:
            chart_blocks.append({"title": "Loss ratio by period", "svg": bar})
    if len(inc_n) >= 2:
        spark = charts.sparkline_svg(inc_n)
        if spark:
            chart_blocks.append({"title": "Incurred losses trend", "svg": spark})

    tiles = []
    if metrics["loss_ratio"][0] is not None:
        tiles.append({"label": "Loss ratio", "value": fmt_pct(metrics["loss_ratio"][0])})
    if metrics["severity"][0] is not None:
        tiles.append({"label": "Avg severity", "value": fmt_money(metrics["severity"][0])})
    if l_claims is not None:
        tiles.append({"label": "Claims (latest)", "value": fmt_num(l_claims)})
    if metrics["open_ratio"][0] is not None:
        tiles.append({"label": "Open-claim ratio", "value": fmt_pct(metrics["open_ratio"][0])})

    values = {k: v[0] for k, v in metrics.items() if v[0] is not None}

    return {"label": "Insurance Loss & Claims", "tiles": tiles, "tables": tables,
            "charts": chart_blocks, "records": records, "values": values}


ANALYZER = base.Analyzer("insurance_loss", "Insurance Loss & Claims", applies, compute)
