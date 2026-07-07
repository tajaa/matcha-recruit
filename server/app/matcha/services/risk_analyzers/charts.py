"""Pure-Python inline SVG charts for the analyzer packs and the report PDF.

No matplotlib / no external assets — every chart is a small self-contained
``<svg>`` string embedded directly in the report HTML (WeasyPrint renders inline
SVG; the SSRF-guarded url_fetcher never fires because there are no URLs). All
label text is escaped. Coordinates are computed in Python.
"""

from __future__ import annotations

import html

from .base import nums

_ACCENT = "#166534"
_ACCENT_LT = "#22c55e"
_MUTED = "#9ca3af"
_GRID = "#e5e7eb"


def _esc(v) -> str:
    # Deliberately local (NOT claims_readiness._esc, which renders None as "—"):
    # this package stays stdlib-pure, and inside SVG markup a missing value
    # must collapse to nothing, not an em-dash glyph.
    return html.escape(str(v)) if v is not None else ""


def _scale(vals, lo, hi, out_lo, out_hi):
    span = (hi - lo) or 1.0
    return [out_lo + (out_hi - out_lo) * ((v - lo) / span) for v in vals]


def sparkline_svg(values, width: int = 220, height: int = 44) -> str:
    xs = nums(values)
    if len(xs) < 2:
        return ""
    lo, hi = min(xs), max(xs)
    px = _scale(list(range(len(xs))), 0, len(xs) - 1, 4, width - 4)
    py = _scale(xs, lo, hi, height - 5, 5)  # invert: high value = top
    pts = " ".join(f"{x:.1f},{y:.1f}" for x, y in zip(px, py))
    return (
        f'<svg viewBox="0 0 {width} {height}" width="{width}" height="{height}" '
        f'xmlns="http://www.w3.org/2000/svg">'
        f'<polyline fill="none" stroke="{_ACCENT}" stroke-width="1.5" points="{pts}"/>'
        f'<circle cx="{px[-1]:.1f}" cy="{py[-1]:.1f}" r="2.2" fill="{_ACCENT}"/>'
        f"</svg>"
    )


def bar_svg(labels, values, width: int = 360, height: int = 150, *, pct: bool = False) -> str:
    pairs = [(str(l), v) for l, v in zip(labels or [], values or []) if v is not None]
    if not pairs:
        return ""
    vals = [p[1] for p in pairs]
    hi = max(vals + [0.0]) or 1.0
    n = len(pairs)
    pad, top, bottom = 6, 8, 30
    bw = (width - 2 * pad) / n
    bars = []
    for i, (lab, v) in enumerate(pairs):
        h = (height - top - bottom) * (max(0.0, v) / hi)
        x = pad + i * bw + bw * 0.15
        y = height - bottom - h
        val_txt = f"{v * 100:.1f}%" if pct else f"{v:,.2f}".rstrip("0").rstrip(".")
        bars.append(
            f'<rect x="{x:.1f}" y="{y:.1f}" width="{bw * 0.7:.1f}" height="{h:.1f}" '
            f'rx="2" fill="{_ACCENT}"/>'
            f'<text x="{x + bw * 0.35:.1f}" y="{y - 3:.1f}" font-size="7" '
            f'fill="{_ACCENT}" text-anchor="middle">{_esc(val_txt)}</text>'
            f'<text x="{x + bw * 0.35:.1f}" y="{height - 8:.1f}" font-size="7" '
            f'fill="{_MUTED}" text-anchor="middle">{_esc(lab[:10])}</text>'
        )
    return (
        f'<svg viewBox="0 0 {width} {height}" width="{width}" height="{height}" '
        f'xmlns="http://www.w3.org/2000/svg">'
        f'<line x1="{pad}" y1="{height - bottom}" x2="{width - pad}" '
        f'y2="{height - bottom}" stroke="{_GRID}"/>{"".join(bars)}</svg>'
    )


def drawdown_svg(index_series, width: int = 360, height: int = 120) -> str:
    xs = nums(index_series)
    if len(xs) < 2:
        return ""
    peak = xs[0]
    dd = []
    for x in xs:
        peak = max(peak, x)
        dd.append((peak - x) / peak if peak > 0 else 0.0)
    worst = max(dd) or 1.0
    px = _scale(list(range(len(dd))), 0, len(dd) - 1, 4, width - 4)
    py = _scale(dd, 0, worst, 6, height - 6)  # 0 drawdown at top
    top_line = " ".join(f"{x:.1f},6" for x in px)
    area = f"M {px[0]:.1f},6 " + " ".join(f"L {x:.1f},{y:.1f}" for x, y in zip(px, py)) + \
        f" L {px[-1]:.1f},6 Z"
    return (
        f'<svg viewBox="0 0 {width} {height}" width="{width}" height="{height}" '
        f'xmlns="http://www.w3.org/2000/svg">'
        f'<path d="{area}" fill="#fca5a5" fill-opacity="0.5" stroke="#dc2626" stroke-width="1"/>'
        f'<polyline points="{top_line}" fill="none" stroke="{_GRID}"/></svg>'
    )


def _corr_color(v) -> str:
    # diverging blue(-1) ↔ white(0) ↔ red(+1)
    if v is None:
        return "#f3f4f6"
    v = max(-1.0, min(1.0, v))
    if v >= 0:
        return f"rgb(255,{int(255 - 120 * v)},{int(255 - 160 * v)})"
    return f"rgb({int(255 + 160 * v)},{int(255 + 120 * v)},255)"


def heatmap_svg(labels, matrix, cell: int = 34) -> str:
    if not labels or not matrix:
        return ""
    n = len(labels)
    pad_l, pad_t = 70, 60
    w = pad_l + n * cell + 6
    h = pad_t + n * cell + 6
    parts = []
    for i, lab in enumerate(labels):
        parts.append(
            f'<text x="{pad_l - 4}" y="{pad_t + i * cell + cell / 2 + 3:.0f}" '
            f'font-size="7" fill="{_MUTED}" text-anchor="end">{_esc(str(lab)[:12])}</text>'
        )
        parts.append(
            f'<text x="{pad_l + i * cell + cell / 2:.0f}" y="{pad_t - 4}" '
            f'font-size="7" fill="{_MUTED}" text-anchor="middle" '
            f'transform="rotate(-40 {pad_l + i * cell + cell / 2:.0f} {pad_t - 4})">'
            f'{_esc(str(lab)[:12])}</text>'
        )
    for i in range(n):
        for j in range(n):
            v = matrix[i][j] if i < len(matrix) and j < len(matrix[i]) else None
            x = pad_l + j * cell
            y = pad_t + i * cell
            txt = "—" if v is None else f"{v:.2f}"
            parts.append(
                f'<rect x="{x}" y="{y}" width="{cell - 2}" height="{cell - 2}" rx="2" '
                f'fill="{_corr_color(v)}" stroke="{_GRID}"/>'
                f'<text x="{x + (cell - 2) / 2:.0f}" y="{y + (cell - 2) / 2 + 3:.0f}" '
                f'font-size="7" fill="#374151" text-anchor="middle">{_esc(txt)}</text>'
            )
    return (
        f'<svg viewBox="0 0 {w} {h}" width="{w}" height="{h}" '
        f'xmlns="http://www.w3.org/2000/svg">{"".join(parts)}</svg>'
    )


def grouped_bar_svg(groups, series_labels, values, width: int = 420, height: int = 170) -> str:
    """values[g][s] — one cluster per group, one bar per series. For side-by-side
    dataset/period comparisons."""
    if not groups or not series_labels:
        return ""
    flat = [v for row in values for v in row if v is not None]
    hi = max(flat + [0.0]) or 1.0
    palette = [_ACCENT, _ACCENT_LT, "#065f46", "#4ade80", "#14532d"]
    pad, top, bottom = 8, 10, 28
    gw = (width - 2 * pad) / len(groups)
    bw = (gw * 0.8) / max(1, len(series_labels))
    parts = []
    for gi, g in enumerate(groups):
        for si, _s in enumerate(series_labels):
            v = values[gi][si] if gi < len(values) and si < len(values[gi]) else None
            if v is None:
                continue
            bh = (height - top - bottom) * (max(0.0, v) / hi)
            x = pad + gi * gw + gw * 0.1 + si * bw
            y = height - bottom - bh
            parts.append(
                f'<rect x="{x:.1f}" y="{y:.1f}" width="{bw * 0.85:.1f}" height="{bh:.1f}" '
                f'rx="1.5" fill="{palette[si % len(palette)]}"/>'
            )
        parts.append(
            f'<text x="{pad + gi * gw + gw / 2:.1f}" y="{height - 8:.1f}" font-size="7" '
            f'fill="{_MUTED}" text-anchor="middle">{_esc(str(g)[:12])}</text>'
        )
    legend = []
    for si, s in enumerate(series_labels):
        lx = pad + si * 90
        legend.append(
            f'<rect x="{lx}" y="2" width="8" height="8" rx="1.5" fill="{palette[si % len(palette)]}"/>'
            f'<text x="{lx + 11}" y="9" font-size="7" fill="{_MUTED}">{_esc(str(s)[:14])}</text>'
        )
    return (
        f'<svg viewBox="0 0 {width} {height}" width="{width}" height="{height}" '
        f'xmlns="http://www.w3.org/2000/svg">{"".join(legend)}'
        f'<line x1="{pad}" y1="{height - bottom}" x2="{width - pad}" y2="{height - bottom}" '
        f'stroke="{_GRID}"/>{"".join(parts)}</svg>'
    )
