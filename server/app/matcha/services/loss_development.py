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
import math
import re
from datetime import date
from typing import Optional

from app.core.services.pdf import safe_url_fetcher

logger = logging.getLogger(__name__)

LINE_LABELS = {"wc": "Workers' Comp", "gl": "General Liability", "auto": "Commercial Auto",
               "property": "Commercial Property"}

# Reserve-variance modeling (Mack's-method-style) — hand-rolled, no scipy, matching
# the rest of this codebase's stats (see monte_carlo_service.py's own variance math).
Z_75 = 1.15  # normal-approx two-sided z for a ~75% CI on the projected ultimate
_CONF_RANK = {"low": 0, "moderate": 1, "high": 2}
_RANK_TO_CONF = {v: k for k, v in _CONF_RANK.items()}


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


def _factor_stats(rs: list[float]) -> dict:
    """Mean + sample variance of one maturity bucket's individual age-to-age
    factor observations. ``variance``/``std_error`` are None below n=2 —
    dispersion isn't estimable from a single observation, and a fabricated
    number there would be presented with false confidence."""
    n = len(rs)
    mean = sum(rs) / n if n else 0.0
    if n < 2:
        return {"mean": round(mean, 4), "n": n, "variance": None, "std_error": None}
    variance = sum((r - mean) ** 2 for r in rs) / (n - 1)
    # variance stays UNROUNDED — it feeds _mack_reserve_variance arithmetic, and
    # rounding tiny-but-real dispersion to 0.0 would fabricate a zero-width CI
    # (the exact failure the n<2 → None guard exists to prevent). Round only at
    # the reporting boundary (the factors[] output list).
    return {"mean": round(mean, 4), "n": n, "variance": variance,
            "std_error": round(math.sqrt(variance / n), 6)}


def _mack_reserve_variance(latest_incurred: float, latest_maturity: int,
                            atf: dict, factor_stats: dict) -> float | None:
    """Mack's-method-style propagated variance of the projected ultimate (==
    the reserve's variance, since latest incurred is treated as a known
    constant). Walks the same maturity chain as ``cdf_from``, at each step
    adding that step's factor sampling variance (sigma^2/n, from the CLT) on
    the projection accumulated so far, then compounding by the factor for the
    next step. Returns None the moment any remaining step's factor rests on
    fewer than 2 observations — a partial variance built on an unknown term
    would be a fabricated number, not a conservative one."""
    steps = sorted(m for m in atf if m >= latest_maturity)
    if not steps:
        return 0.0
    proj = latest_incurred
    var = 0.0
    for m in steps:
        stats = factor_stats.get(m)
        if not stats or stats["variance"] is None:
            return None
        f = atf[m]
        sampling_var = stats["variance"] / stats["n"]
        var = var * f * f + proj * proj * sampling_var
        proj *= f
    return var


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
    factor_stats = {m: _factor_stats(rs) for m, rs in ratios.items() if rs}

    def cdf_from(maturity: int) -> float:
        f = 1.0
        for m, factor in atf.items():
            if m >= maturity:
                f *= factor
        return round(f, 4)

    # project each period to ultimate, plus its Mack's-method reserve variance
    tot_latest = tot_ult = tot_var = 0.0
    tot_var_known = True
    conf_ranks: list[int] = []
    for p in periods:
        if not p["points"]:
            # no scoreable points (unparseable period label / null valuation dates)
            # — still counts toward the summary's worst-of, matching the "low"
            # this row itself renders.
            conf_ranks.append(_CONF_RANK["low"])
            p.update(latest_maturity=None, latest_incurred=0.0, cdf=1.0, ultimate=0.0, adverse_development=0.0,
                      reserve_std_error=None, ultimate_low=None, ultimate_high=None, reserve_confidence="low")
            continue
        latest = p["points"][-1]
        cdf = cdf_from(latest["maturity"])
        ult = round(latest["incurred"] * cdf, 2)
        remaining = sorted(m for m in atf if m >= latest["maturity"])
        # a hole in the development chain (a factor bucket missing between the
        # period's latest maturity and the last observed transition) means
        # cdf_from silently treats that step as 1.0 — the projection is a floor
        # and no CI over it is defensible.
        chain_intact = (not remaining) or (
            remaining[0] == latest["maturity"]
            and all(b == a + 12 for a, b in zip(remaining, remaining[1:]))
        )
        if not remaining:
            var = 0.0
        elif not chain_intact:
            var = None
        else:
            var = _mack_reserve_variance(latest["incurred"], latest["maturity"], atf, factor_stats)
        if var is not None:
            se = math.sqrt(var)
            ult_low, ult_high, se_out = round(max(0.0, ult - Z_75 * se), 2), round(ult + Z_75 * se, 2), round(se, 2)
        else:
            ult_low = ult_high = se_out = None
        if not remaining:
            conf = "high"
        elif p["maturity_gap"] or var is None:
            conf = "low"
        elif min(factor_stats[m]["n"] for m in remaining) < 4:
            conf = "moderate"
        else:
            conf = "high"
        conf_ranks.append(_CONF_RANK[conf])
        p.update(latest_maturity=latest["maturity"], latest_incurred=round(latest["incurred"], 2),
                 cdf=cdf, ultimate=ult, adverse_development=round(ult - latest["incurred"], 2),
                 reserve_std_error=se_out, ultimate_low=ult_low, ultimate_high=ult_high, reserve_confidence=conf)
        tot_latest += latest["incurred"]
        tot_ult += ult
        if var is not None:
            tot_var += var
        else:
            tot_var_known = False

    if conf_ranks and tot_var_known:
        total_se = math.sqrt(tot_var)
        total_ult_low, total_ult_high = round(max(0.0, tot_ult - Z_75 * total_se), 2), round(tot_ult + Z_75 * total_se, 2)
        total_se = round(total_se, 2)
    else:
        total_se = total_ult_low = total_ult_high = None
    worst_conf = _RANK_TO_CONF[min(conf_ranks)] if conf_ranks else "low"

    periods.sort(key=lambda p: p["period_label"])
    valuations = len({pt["valuation_date"] for p in periods for pt in p["points"]})
    max_mat = max((pt["maturity"] for p in periods for pt in p["points"]), default=0)
    return {
        "line": line, "label": LINE_LABELS.get(line, line.upper()),
        "periods": periods,
        "factors": [{"from_maturity": m, "to_maturity": m + 12, "factor": atf[m],
                     "n": len(ratios[m]),
                     "variance": round(factor_stats[m]["variance"], 6)
                     if factor_stats[m]["variance"] is not None else None} for m in sorted(atf)],
        "summary": {
            "total_latest_incurred": round(tot_latest, 2),
            "total_ultimate": round(tot_ult, 2),
            "total_adverse_development": round(tot_ult - tot_latest, 2),
            "adverse_pct": round(100 * (tot_ult - tot_latest) / tot_latest, 1) if tot_latest > 0 else 0.0,
            "periods": len(periods), "valuations": valuations, "max_maturity": max_mat,
            "has_maturity_gap": any(p["maturity_gap"] for p in periods),
            "total_reserve_std_error": total_se,
            "total_ultimate_low": total_ult_low,
            "total_ultimate_high": total_ult_high,
            "reserve_confidence": worst_conf,
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


async def list_company_snapshots(conn, company_id, line: str | None = None) -> list[dict]:
    """Broker-agnostic snapshot fetch for the tenant risk-profile path, which has
    no ``broker_id`` (a company's loss runs may have been entered by more than one
    broker over time) — scopes solely by ``subject_id``, unlike ``list_snapshots``'
    broker-keyed read for the broker surface."""
    if line:
        rows = await conn.fetch(
            """SELECT id, line, policy_period_label, policy_period_start, valuation_date,
                      claim_count, open_count, paid, reserved, source, note, created_at
               FROM wc_loss_runs
               WHERE subject_kind = 'company' AND subject_id = $1 AND line = $2
               ORDER BY line, policy_period_label, valuation_date""",
            company_id, line,
        )
    else:
        rows = await conn.fetch(
            """SELECT id, line, policy_period_label, policy_period_start, valuation_date,
                      claim_count, open_count, paid, reserved, source, note, created_at
               FROM wc_loss_runs
               WHERE subject_kind = 'company' AND subject_id = $1
               ORDER BY line, policy_period_label, valuation_date""",
            company_id,
        )
    out = []
    for r in rows:
        d = dict(r)
        d["id"] = str(d["id"])
        out.append(d)
    return out


def property_loss_signal(tri: dict) -> Optional[dict]:
    """Property-line adverse-development penalty from a ``build_triangle()``
    result. Pure (unit-tested). None when there's no property loss-run history
    to judge from, or when the ramp below rounds to zero.

    Linear ramp: 0 penalty at <=10% adverse development, capped at 15 points
    around 60%+ — a judgment call (WC and other lines don't get an equivalent
    hit; property's cat/ITV exposure already dominates that score, so this is a
    secondary nudge, not a primary signal)."""
    lines = {ln["line"]: ln for ln in tri.get("lines", [])}
    line = lines.get("property")
    if not line or not line.get("periods"):
        return None
    summary = line["summary"]
    if summary.get("total_latest_incurred", 0) <= 0:
        return None
    adverse_pct = summary.get("adverse_pct", 0.0)
    penalty = min(15, max(0, round((adverse_pct - 10) / 50 * 15)))
    if penalty == 0:
        return None
    ult_low, ult_high = summary.get("total_ultimate_low"), summary.get("total_ultimate_high")
    total_latest = summary.get("total_latest_incurred") or 0
    ci_width_pct = (round((ult_high - ult_low) / total_latest * 100, 1)
                    if ult_low is not None and ult_high is not None and total_latest > 0 else None)
    return {"adverse_penalty": penalty, "adverse_pct": adverse_pct,
            "detail": f"{adverse_pct}% adverse development",
            "confidence": summary.get("reserve_confidence", "low"),
            "ci_width_pct": ci_width_pct}


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


# --- loss ratio (projected ultimate ÷ paid premium) -------------------------
#
# Underwriters price on the loss ratio and target < 60% for profitability. The
# projected ultimate already comes out of build_development per (line, policy
# year); the broker enters the premium the client paid the carrier (per line per
# year) and we divide. Status: favorable (< target) / adverse (>= target) / na
# (no premium entered yet).

LOSS_RATIO_TARGET = 60  # percent — underwriter profitability threshold


def _ratio_status(ratio) -> str:
    if ratio is None:
        return "na"
    return "favorable" if ratio < LOSS_RATIO_TARGET else "adverse"


def _ratio(ultimate: float, premium) -> float | None:
    if not premium or premium <= 0:
        return None
    return round(ultimate / premium * 100, 1)


def _merge_loss_ratio(dev: dict, premiums: dict) -> dict:
    """Pure merge of a build_development() result + a {(line, period_label):
    paid_premium} map → per-(line, year) rows + per-year account rollups."""
    rows: list[dict] = []
    year_acc: dict[str, dict] = {}
    for ln in dev.get("lines", []):
        for p in ln.get("periods", []):
            ult = float(p.get("ultimate") or 0)
            prem = premiums.get((ln["line"], p["period_label"]))
            ratio = _ratio(ult, prem)
            rows.append({
                "line": ln["line"],
                "label": ln.get("label", ln["line"]),
                "period_label": p["period_label"],
                "period_start": p.get("period_start"),
                "projected_ultimate": round(ult, 2),
                "paid_premium": prem,
                "loss_ratio": ratio,
                "status": _ratio_status(ratio),
            })
            acc = year_acc.setdefault(p["period_label"], {
                "ultimate": 0.0, "premium": 0.0, "has_premium": False,
                "period_start": p.get("period_start"),
            })
            acc["ultimate"] += ult
            if prem and prem > 0:
                acc["premium"] += prem
                acc["has_premium"] = True

    years = []
    for label, a in year_acc.items():
        ratio = _ratio(a["ultimate"], a["premium"]) if a["has_premium"] else None
        years.append({
            "period_label": label,
            "period_start": a["period_start"],
            "total_ultimate": round(a["ultimate"], 2),
            "total_premium": round(a["premium"], 2) if a["has_premium"] else None,
            "loss_ratio": ratio,
            "status": _ratio_status(ratio),
        })
    years.sort(key=lambda y: y["period_label"])
    rows.sort(key=lambda r: (r["line"], r["period_label"]))
    return {"rows": rows, "years": years}


async def _list_premiums(conn, broker_id, subject_kind: str, subject_id) -> dict:
    rows = await conn.fetch(
        """SELECT line, policy_period_label, paid_premium FROM broker_loss_premiums
           WHERE broker_id = $1 AND subject_kind = $2 AND subject_id = $3""",
        broker_id, subject_kind, subject_id,
    )
    out: dict = {}
    for r in rows:
        prem = r["paid_premium"]
        out[(r["line"], r["policy_period_label"])] = float(prem) if prem is not None else None
    return out


async def compute_loss_ratio(conn, broker_id, subject_kind: str, subject_id, *,
                             subject_name: str = "Client") -> dict:
    """build_development + broker-entered premiums → loss-ratio table. Never raises."""
    dev = await build_development(conn, broker_id, subject_kind, subject_id, subject_name=subject_name)
    premiums: dict = {}
    try:
        premiums = await _list_premiums(conn, broker_id, subject_kind, subject_id)
    except Exception as exc:  # pragma: no cover - defensive
        logger.warning("loss_development.compute_loss_ratio premium fetch failed: %s", exc)
    merged = _merge_loss_ratio(dev, premiums)
    return {
        **merged,
        "target": LOSS_RATIO_TARGET,
        "has_data": dev["has_data"],
        "subject_kind": subject_kind,
        "subject_id": str(subject_id),
        "subject_name": subject_name,
    }


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
