"""Cross-dataset comparison analyzer — diff the same computed metric across two
or more datasets/periods (e.g. this year's P&L vs last), producing deltas,
percentage change, and per-step CAGR. Pure/deterministic.

Input datasets are the stored dataset dicts, each carrying its per-pack
``metrics`` block (which now includes a machine-readable ``values`` map). The
comparison is keyed by the SHARED metric keys per pack, so it works across any
pack without knowing the pack internals.
"""

from __future__ import annotations

from . import base, charts
from .base import cagr, slug, fmt_num, fmt_pct


def _values(block) -> dict:
    return (block or {}).get("values") or {}


def build_comparison(cmp_id: str, datasets: list[dict]) -> dict:
    """datasets: ordered list of ``{"id", "label", "metrics": {pack: block}}``.
    Order is treated as the comparison axis (period order for CAGR)."""
    labels = [d.get("label") or f"Dataset {i + 1}" for i, d in enumerate(datasets)]
    pack_keys: list[str] = []
    for d in datasets:
        for pk in (d.get("metrics") or {}):
            if pk != "_warnings" and pk not in pack_keys:
                pack_keys.append(pk)

    records: list[dict] = []
    tables: list[dict] = []
    chart_blocks: list[dict] = []
    tiles: list[dict] = []

    for pk in pack_keys:
        blocks = [(d, (d.get("metrics") or {}).get(pk)) for d in datasets]
        present = [(d, b) for d, b in blocks if b]
        if len(present) < 2:
            continue
        # metric keys present in EVERY dataset that has this pack
        common = None
        for _, b in present:
            keys = set(_values(b).keys())
            common = keys if common is None else (common & keys)
        common = sorted(common or [])
        if not common:
            continue

        pack_label = present[0][1].get("label") or pk
        # Values are keyed to the `present` datasets only — the table columns,
        # chart bars, and record labels must all use the same axis, or a
        # dataset that lacks this pack shifts every value one column over.
        p_labels = [d.get("label") or "?" for d, _ in present]
        columns = ["Metric"] + p_labels + ["Δ", "% change", "CAGR"]
        rows = []
        chart_groups = []
        chart_vals = []
        for key in common:
            series_vals = [_values(b).get(key) for _, b in present]
            aligned = [v for v in series_vals if v is not None]
            if len(aligned) < 2:
                continue
            first, last = aligned[0], aligned[-1]
            delta = last - first
            # abs(first): a negative baseline must not invert the direction of
            # the change (a loss→profit swing is a positive % change).
            pct = (delta / abs(first)) if first not in (0, None) else None
            cg = cagr(first, last, len(aligned) - 1)
            rows.append(
                [key.replace("_", " ").title()]
                + [fmt_num(v) if v is not None else "—" for v in series_vals]
                + [fmt_num(delta), fmt_pct(pct), fmt_pct(cg)]
            )
            chart_groups.append(key.replace("_", " ").title()[:12])
            chart_vals.append([abs(v) if v is not None else None for v in series_vals])
            records.append({
                "cid": f"compare:{cmp_id}:{pk}:{slug(key)}",
                "ref": f"{pack_label}: {key} across datasets",
                "summary": f"{pack_label} — {key.replace('_', ' ')}: "
                           + " → ".join(f"{lab} {fmt_num(v)}" for lab, v in zip(p_labels, series_vals) if v is not None)
                           + (f" ({fmt_pct(pct)} change)." if pct is not None else "."),
                "when": "comparison",
            })
        if rows:
            tables.append({"title": f"{pack_label} — compared", "columns": columns, "rows": rows})
            # grouped bar: cluster per metric, bar per dataset
            gb = charts.grouped_bar_svg(chart_groups, [d.get("label") or "?" for d, _ in present],
                                        [[row[i] for i in range(len(present))] for row in chart_vals])
            if gb:
                chart_blocks.append({"title": f"{pack_label} across datasets", "svg": gb})

    tiles.append({"label": "Datasets compared", "value": str(len(datasets))})
    notes = []
    if not tables:
        notes.append("No shared metrics across the selected datasets — pick datasets analyzed by the same pack.")

    return {
        "label": "Comparison",
        "datasets": [{"id": d.get("id"), "label": lab} for d, lab in zip(datasets, labels)],
        "tiles": tiles,
        "tables": tables,
        "charts": chart_blocks,
        "records": records,
        "notes": notes,
    }
