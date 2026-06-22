"""Loss-run triangulation / chain-ladder development (gap-analysis #5/#23).

A single loss run undervalues claims — they develop (grow) after they're
reported. This lines up the SAME policy years valued at MULTIPLE dates into a
triangle, computes age-to-age development factors, and projects ULTIMATE losses
per period (basic chain-ladder, simple-average link ratios, 1.0 tail). The gap
between latest-reported incurred and projected ultimate = adverse development —
the reserve-adequacy signal underwriters price on.

Pure ``build_triangle`` (unit-tested) + a DB ``build_development`` wrapper (never
raises) + a deterministic PDF. Directional — labelled as such; a company's own
triangle from its own loss runs, no licensed benchmark data needed.
"""

import asyncio
import html
import logging
import re
from datetime import date

from app.core.services.pdf import safe_url_fetcher

logger = logging.getLogger(__name__)

LINE_LABELS = {"wc": "Workers' Comp", "gl": "General Liability", "auto": "Commercial Auto"}


def _period_start(label: str, explicit) -> date | None:
    """Use the explicit policy_period_start, else derive Jan-1 of the period year
    from the label. Prefer an explicit policy-year token (``PY2021``) so a stray
    year inside a claim number (e.g. 'Claim 2019-00042 PY2021') doesn't mis-age the
    whole period; else fall back to the first 4-digit year ('2021', '2021-2022')."""
    if explicit:
        return explicit
    s = str(label or "")
    m = re.search(r"PY\s*((?:19|20)\d{2})", s, re.I) or re.search(r"((?:19|20)\d{2})", s)
    return date(int(m.group(1)), 1, 1) if m else None


def _age_months(start: date | None, val: date) -> int | None:
    if not start or not val:
        return None
    return max(0, (val.year - start.year) * 12 + (val.month - start.month))


def _maturity(age_months: int | None) -> int | None:
    """Bucket an age to the nearest 12-month maturity (min 12)."""
    if age_months is None:
        return None
    return max(12, round(age_months / 12) * 12)


def _num(v) -> float:
    try:
        return float(v) if v is not None else 0.0
    except (TypeError, ValueError):
        return 0.0


def _build_line(line: str, rows: list[dict]) -> dict:
    """Triangle + chain-ladder projection for one coverage line."""
    # group by policy period
    by_period: dict[str, list[dict]] = {}
    starts: dict[str, date | None] = {}
    for r in rows:
        label = r["policy_period_label"]
        by_period.setdefault(label, []).append(r)
        starts[label] = _period_start(label, r.get("policy_period_start"))

    periods = []
    # first pass: per-period points keyed by maturity (latest valuation wins per maturity)
    for label, recs in by_period.items():
        start = starts[label]
        pts: dict[int, dict] = {}
        for r in recs:
            val = r["valuation_date"]
            mat = _maturity(_age_months(start, val))
            if mat is None:
                continue
            paid, reserved = _num(r.get("paid")), _num(r.get("reserved"))
            point = {
                "maturity": mat,
                "valuation_date": val.isoformat() if val else None,
                "paid": paid, "reserved": reserved, "incurred": paid + reserved,
                "claim_count": int(r.get("claim_count") or 0),
                "open_count": int(r.get("open_count") or 0),
            }
            prev = pts.get(mat)
            if prev is None or (point["valuation_date"] or "") >= (prev["valuation_date"] or ""):
                pts[mat] = point
        ordered = [pts[m] for m in sorted(pts)]
        # non-consecutive maturities (a missing intermediate valuation) mean some
        # development steps can't be measured — flag it so the projection isn't
        # silently presented as fully credible.
        maturity_gap = any(b["maturity"] != a["maturity"] + 12 for a, b in zip(ordered, ordered[1:]))
        periods.append({"period_label": label,
                        "period_start": start.isoformat() if start else None,
                        "points": ordered, "maturity_gap": maturity_gap})

    # age-to-age link ratios grouped by from-maturity (simple average across periods).
    # Only pair CONSECUTIVE 12-month maturities: a period valued at e.g. 12mo and
    # 36mo (its 24mo valuation missing) must not book that 24-month-span ratio into
    # the 12->24 bucket — doing so both inflates the 12->24 factor and loses the
    # 24->36 evidence, silently mis-projecting ultimates for every period that
    # chains through it.
    ratios: dict[int, list[float]] = {}
    for p in periods:
        pts = p["points"]
        for a, b in zip(pts, pts[1:]):
            if a["incurred"] > 0 and b["maturity"] == a["maturity"] + 12:
                ratios.setdefault(a["maturity"], []).append(b["incurred"] / a["incurred"])
    atf = {m: round(sum(rs) / len(rs), 4) for m, rs in ratios.items() if rs}

    def cdf_from(maturity: int) -> float:
        f = 1.0
        for m, factor in atf.items():
            if m >= maturity:
                f *= factor
        return round(f, 4)

    # project each period to ultimate
    tot_latest = tot_ult = 0.0
    for p in periods:
        if not p["points"]:
            p.update(latest_maturity=None, latest_incurred=0.0, cdf=1.0, ultimate=0.0, adverse_development=0.0)
            continue
        latest = p["points"][-1]
        cdf = cdf_from(latest["maturity"])
        ult = round(latest["incurred"] * cdf, 2)
        p.update(latest_maturity=latest["maturity"], latest_incurred=round(latest["incurred"], 2),
                 cdf=cdf, ultimate=ult, adverse_development=round(ult - latest["incurred"], 2))
        tot_latest += latest["incurred"]
        tot_ult += ult

    periods.sort(key=lambda p: p["period_label"])
    valuations = len({pt["valuation_date"] for p in periods for pt in p["points"]})
    max_mat = max((pt["maturity"] for p in periods for pt in p["points"]), default=0)
    return {
        "line": line, "label": LINE_LABELS.get(line, line.upper()),
        "periods": periods,
        "factors": [{"from_maturity": m, "to_maturity": m + 12, "factor": atf[m],
                     "n": len(ratios[m])} for m in sorted(atf)],
        "summary": {
            "total_latest_incurred": round(tot_latest, 2),
            "total_ultimate": round(tot_ult, 2),
            "total_adverse_development": round(tot_ult - tot_latest, 2),
            "adverse_pct": round(100 * (tot_ult - tot_latest) / tot_latest, 1) if tot_latest > 0 else 0.0,
            "periods": len(periods), "valuations": valuations, "max_maturity": max_mat,
            "has_maturity_gap": any(p["maturity_gap"] for p in periods),
        },
    }


def build_triangle(snapshots: list[dict]) -> dict:
    """Group snapshots by line → per-line triangle + chain-ladder projection. Pure."""
    by_line: dict[str, list[dict]] = {}
    for s in snapshots:
        by_line.setdefault((s.get("line") or "wc"), []).append(s)
    lines = [_build_line(ln, rows) for ln, rows in sorted(by_line.items())]
    return {"lines": lines, "has_data": bool(snapshots)}


# --- DB wrapper (never raises) ---------------------------------------------

async def list_snapshots(conn, broker_id, subject_kind: str, subject_id) -> list[dict]:
    rows = await conn.fetch(
        """SELECT id, line, policy_period_label, policy_period_start, valuation_date,
                  claim_count, open_count, paid, reserved, source, note, created_at
           FROM wc_loss_runs
           WHERE broker_id = $1 AND subject_kind = $2 AND subject_id = $3
           ORDER BY line, policy_period_label, valuation_date""",
        broker_id, subject_kind, subject_id,
    )
    out = []
    for r in rows:
        d = dict(r)
        d["id"] = str(d["id"])
        out.append(d)
    return out


async def build_development(conn, broker_id, subject_kind: str, subject_id, *,
                            subject_name: str = "Client") -> dict:
    """Fetch loss-run snapshots for a subject → triangle. Never raises."""
    snapshots: list[dict] = []
    try:
        snapshots = await list_snapshots(conn, broker_id, subject_kind, subject_id)
    except Exception as exc:  # pragma: no cover - defensive
        logger.warning("loss_development.build_development fetch failed: %s", exc)
    tri = build_triangle(snapshots)
    tri["subject_kind"] = subject_kind
    tri["subject_id"] = str(subject_id)
    tri["subject_name"] = subject_name
    tri["snapshots"] = snapshots
    return tri


# --- deterministic PDF ------------------------------------------------------

def _esc(v) -> str:
    return html.escape(str(v)) if v is not None else "—"


def _money(v) -> str:
    if v is None:
        return "—"
    try:
        v = float(v)
    except (TypeError, ValueError):
        return "—"
    if abs(v) >= 1_000_000:
        n = v / 1_000_000
        return f"${n:.0f}M" if n == int(n) else f"${n:.2f}M"
    if abs(v) >= 1_000:
        return f"${v / 1_000:.0f}K"
    return f"${v:.0f}"


def _line_section_html(ln: dict) -> str:
    s = ln["summary"]
    # maturity columns present across periods
    mats = sorted({pt["maturity"] for p in ln["periods"] for pt in p["points"]})
    head = "".join(f"<th class='r'>{m}mo</th>" for m in mats)
    body = ""
    for p in ln["periods"]:
        by_mat = {pt["maturity"]: pt for pt in p["points"]}
        cells = "".join(
            f"<td class='r'>{_money(by_mat[m]['incurred']) if m in by_mat else ''}</td>" for m in mats
        )
        adv = p["adverse_development"]
        body += (f"<tr><td>{_esc(p['period_label'])}</td>{cells}"
                 f"<td class='r'>{_money(p['ultimate'])}</td>"
                 f"<td class='r {'bad' if adv > 0 else 'good'}'>{('+' if adv > 0 else '')}{_money(adv)}</td></tr>")
    factors = ", ".join(f"{f['from_maturity']}→{f['to_maturity']}mo: {f['factor']}" for f in ln["factors"]) or "—"
    gap_note = (
        " Note: some policy periods are missing an intermediate valuation "
        "(non-consecutive maturities), so those development steps can't be measured "
        "and default to a 1.0 tail — read the projected ultimate as a floor."
        if s.get("has_maturity_gap") else ""
    )
    return (
        f"<h2>{_esc(ln['label'])} — incurred development triangle</h2>"
        f"<table><thead><tr><th>Policy period</th>{head}<th class='r'>Ultimate</th><th class='r'>Adverse dev.</th></tr></thead>"
        f"<tbody>{body}</tbody></table>"
        f"<p class='fac'>Age-to-age factors (simple avg): {_esc(factors)}. "
        f"Total latest incurred {_money(s['total_latest_incurred'])} → projected ultimate {_money(s['total_ultimate'])} "
        f"({'+' if s['total_adverse_development'] > 0 else ''}{_money(s['total_adverse_development'])}, {s['adverse_pct']}%).{gap_note}</p>"
    )


def _triangle_html(subject_name: str, tri: dict) -> str:
    sections = "".join(_line_section_html(ln) for ln in tri["lines"] if ln["periods"]) or "<p>No loss-run history on file.</p>"
    return f"""<!DOCTYPE html><html><head><meta charset="utf-8"><style>
      body {{ font-family: -apple-system, Helvetica, sans-serif; color:#1a1a2e; padding:30px; font-size:11px; }}
      h1 {{ color:#1f8a5b; margin:0 0 2px; font-size:22px; }}
      .sub {{ color:#666; margin:0 0 16px; }}
      h2 {{ font-size:13px; border-bottom:2px solid #1f8a5b; padding-bottom:4px; margin:18px 0 8px; }}
      table {{ width:100%; border-collapse:collapse; margin-top:4px; }}
      th {{ text-align:left; font-size:8px; text-transform:uppercase; color:#888; border-bottom:1px solid #ddd; padding:4px 6px; }}
      td {{ padding:4px 6px; border-bottom:1px solid #f0f0f0; }}
      td.r, th.r {{ text-align:right; font-family:monospace; }}
      td.bad {{ color:#b23b3b; font-weight:700; }} td.good {{ color:#1f8a5b; }}
      .fac {{ color:#555; font-size:9px; margin:6px 0 0; }}
      .foot {{ margin-top:24px; color:#999; font-size:8px; border-top:1px solid #eee; padding-top:6px; }}
    </style></head><body>
      <h1>Loss Development Triangle</h1>
      <p class="sub">{_esc(subject_name)} — incurred losses by policy period &amp; valuation age</p>
      {sections}
      <div class="foot">Prepared by Matcha. Built by basic chain-ladder (simple-average link ratios, 1.0 tail) from the
      carrier loss runs on file — directional, not an actuarial reserve opinion. Ultimate = latest reported incurred ×
      cumulative development factor. Present alongside the current loss run.</div>
    </body></html>"""


async def render_triangle_pdf(subject_name: str, tri: dict) -> bytes:
    def _render() -> bytes:
        from weasyprint import HTML

        return HTML(string=_triangle_html(subject_name, tri), url_fetcher=safe_url_fetcher).write_pdf()

    return await asyncio.to_thread(_render)
