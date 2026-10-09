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

import logging
import math
import re
from datetime import date
from typing import Optional


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


def _effective_variances(atf: dict, factor_stats: dict) -> tuple[dict, set]:
    """Per-maturity factor stats for the variance walk, with the TAIL factor's
    missing variance filled by Mack's-method extrapolation.

    The oldest development factor almost always rests on a single observation
    (only the oldest policy year reaches that maturity), so its sample variance
    is undefined. Nulling the whole projection there would hide the CI on nearly
    every realistic triangle. Mack (1993) instead continues the observed
    sigma^2 decay for the last factor:

        s2_tail = min( s2_a^2 / s2_b ,  s2_a ,  s2_b )

    where s2_a, s2_b are the two nearest lower buckets with a real variance
    (``a`` nearer the tail) — the geometric continuation of the decay, capped at
    the smaller prior so it can't blow up. Needs >=2 estimable lower buckets;
    otherwise the tail stays unmodelable (None). Only the single highest-maturity
    bucket is extrapolated — an interior single-observation bucket is a genuine
    hole, not a tail, and stays None.

    Returns (effective_stats, extrapolated_maturities). ``effective_stats`` is a
    shallow per-bucket copy; the reported ``factors[]`` variance stays the real
    (possibly None) value — extrapolation is internal to the CI only."""
    ms = sorted(atf)
    eff = {m: dict(factor_stats[m]) for m in ms}
    extrapolated: set = set()
    if not ms:
        return eff, extrapolated
    tail = ms[-1]
    if eff[tail]["variance"] is None:
        lower = [m for m in ms[:-1] if eff[m]["variance"] is not None]
        if len(lower) >= 2:
            sa, sb = eff[lower[-1]]["variance"], eff[lower[-2]]["variance"]
            s2 = min(sa * sa / sb, sa, sb) if sb > 0 else min(sa, sb)
            eff[tail]["variance"] = s2
            extrapolated.add(tail)
    return eff, extrapolated


def _mack_reserve_variance(latest_incurred: float, latest_maturity: int,
                            atf: dict, factor_stats: dict) -> float | None:
    """Mack's-method-style propagated variance of the projected ultimate (==
    the reserve's variance, since latest incurred is treated as a known
    constant). Walks the same maturity chain as ``cdf_from``, at each step
    adding that step's factor sampling variance (sigma^2/n, from the CLT) on
    the projection accumulated so far, then compounding by the factor for the
    next step. Returns None the moment any remaining step's factor variance is
    unknown — a partial variance built on an unknown term would be a fabricated
    number, not a conservative one. (Pass the extrapolated stats from
    ``_effective_variances`` to keep the tail factor from nulling realistic
    triangles.)"""
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
    # Fill the single-observation tail factor's variance via Mack extrapolation
    # so a realistic triangle yields a (widened) CI instead of collapsing to
    # "low"; eff_stats feeds the variance walk, factor_stats stays real for the
    # reported factors[] + the observation-count confidence read.
    eff_stats, extrapolated = _effective_variances(atf, factor_stats)

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
            # No development factors apply at/after this maturity. Two very
            # different situations share this branch: (a) genuine run-off — the
            # line HAS a triangle and this period sits at/beyond its last
            # measured step, so cdf=1.0 is evidence-based → exact, high; (b) a
            # greenfield line with NO factors at all (a single loss run), where
            # cdf=1.0 is a default punt, not a measurement — the projected
            # ultimate is just the latest reported, the LEAST certain read, so
            # no CI and "low".
            var = 0.0 if atf else None
        elif not chain_intact:
            var = None
        else:
            var = _mack_reserve_variance(latest["incurred"], latest["maturity"], atf, eff_stats)
        if var is not None:
            se = math.sqrt(var)
            ult_low, ult_high, se_out = round(max(0.0, ult - Z_75 * se), 2), round(ult + Z_75 * se, 2), round(se, 2)
        else:
            ult_low = ult_high = se_out = None
        if not remaining:
            conf = "high" if atf else "low"
        elif p["maturity_gap"] or var is None:
            conf = "low"
        elif any(m in extrapolated for m in remaining):
            # the tail factor's sigma was modeled, not measured — a CI shows, but
            # never claim "high" on an extrapolated tail.
            conf = "moderate"
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
            # the oldest development factor's variability was extrapolated (Mack
            # tail rule), not measured — surface it so the CI isn't over-read.
            "reserve_tail_extrapolated": bool(extrapolated),
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

async def list_company_snapshots(conn, company_id, line: str | None = None) -> list[dict]:
    """Snapshot fetch for the tenant risk-profile path. Scopes solely by
    ``subject_id``: a company's loss runs may have been entered by more than one
    party over time, so ``broker_id`` is deliberately not part of the key."""
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
