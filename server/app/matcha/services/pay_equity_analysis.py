"""Pay-equity analysis from comp data — replaces the manual study log with a real
computation over employees.pay_rate. Screens within-role pay dispersion (spread
by job title) and writes a pay_equity_reviews row so the EPL factor derives from
data, not a hand-entered date.

Scope note: this is a within-role DISPERSION screen (legit drivers like seniority
are included). True protected-class pay-gap analysis needs gender/race demographics
that aren't in our schema (would come from an HRIS /individual pull) — surfaced in
the stored methodology so it's never over-claimed.
"""

import statistics
from collections import defaultdict
from uuid import UUID

# annualize pay_rate (mirror wc_classmap)
_ANNUALIZE = (
    "CASE WHEN pay_classification ILIKE 'hour%' THEN pay_rate*2080 "
    "WHEN pay_classification ILIKE 'exempt' OR pay_classification ILIKE 'salar%' THEN pay_rate "
    "WHEN pay_rate < 2000 THEN pay_rate*2080 ELSE pay_rate END"
)

_EXCESS_SPREAD = 30.0  # a role's max-min spread over median above this = flagged
_WATCH_SPREAD = 15.0   # between watch and excess
_BAND_FLOOR = 0.80     # employees paid below this fraction of role median = "below band"


def role_stats(title: str, pays: list[float]) -> dict:
    """Per-role pay-dispersion stats. Pure (no DB) so it's unit-testable.

    Beyond the headline spread, surfaces the quartile spread (IQR — robust to a
    single outlier), how many people sit below the role's pay band, the dollars it
    would take to lift them to that band, and a severity tier the UI can colour."""
    pays = sorted(float(p) for p in pays)
    n = len(pays)
    med = statistics.median(pays)
    lo, hi = pays[0], pays[-1]
    spread = round(100 * (hi - lo) / med, 1) if med else 0.0
    # quartiles need ≥2 points (callers already filter n≥2); fall back to median.
    if n >= 2:
        q = statistics.quantiles(pays, n=4)  # [p25, p50, p75]
        p25, p75 = round(q[0]), round(q[2])
    else:
        p25 = p75 = round(med)
    iqr_pct = round(100 * (p75 - p25) / med, 1) if med else 0.0
    floor = _BAND_FLOOR * med
    below = [p for p in pays if p < floor]
    severity = "flag" if spread >= _EXCESS_SPREAD else ("watch" if spread >= _WATCH_SPREAD else "ok")
    return {
        "title": title, "n": n,
        "median": round(med), "min": round(lo), "max": round(hi),
        "p25": p25, "p75": p75,
        "spread_pct": spread, "iqr_pct": iqr_pct,
        "range_ratio": round(hi / lo, 2) if lo else None,
        "below_band_n": len(below),
        "remediation_cost": round(sum(floor - p for p in below)),
        "severity": severity,
    }


async def analyze(conn, company_id: UUID) -> dict:
    """Within-role pay dispersion. Returns per-role stats (≥2 employees) plus
    company-wide actionable rollups — the excess-dispersion headline (% of roles
    flagged) feeds the EPL derive; the rest deepens the client report."""
    rows = await conn.fetch(
        f"""
        SELECT COALESCE(NULLIF(TRIM(job_title), ''), '(untitled)') AS title, {_ANNUALIZE} AS pay
        FROM employees
        WHERE org_id = $1 AND pay_rate IS NOT NULL
          AND COALESCE(employment_status, 'active') NOT ILIKE 'term%'
        """,
        company_id,
    )
    by_role: dict[str, list[float]] = defaultdict(list)
    for r in rows:
        if r["pay"] and float(r["pay"]) > 0:
            by_role[r["title"]].append(float(r["pay"]))

    roles = [role_stats(title, pays) for title, pays in by_role.items() if len(pays) >= 2]
    roles.sort(key=lambda r: r["spread_pct"], reverse=True)

    flagged = [r for r in roles if r["severity"] == "flag"]
    headline = round(100 * len(flagged) / len(roles)) if roles else 0

    total_payroll = round(sum(p for pays in by_role.values() for p in pays))
    flagged_titles = {r["title"] for r in flagged}
    flagged_payroll = sum(p for t, pays in by_role.items() for p in pays if t in flagged_titles)
    return {
        "employee_count": len(rows),
        "analyzed_roles": len(roles),
        "flagged_roles": len(flagged),
        "headline_gap_pct": headline,          # % of roles with excess dispersion (EPL derive)
        "worst": roles[0] if roles else None,
        "roles": roles,
        # --- company-wide actionable rollups (client report depth) ---
        "total_payroll": total_payroll,
        "median_spread_pct": round(statistics.median([r["spread_pct"] for r in roles]), 1) if roles else 0.0,
        "employees_below_band": sum(r["below_band_n"] for r in roles),
        "flagged_payroll_pct": round(100 * flagged_payroll / total_payroll, 1) if total_payroll else 0.0,
        "remediation_estimate": round(sum(r["remediation_cost"] for r in roles)),
        "band_floor_pct": int(_BAND_FLOOR * 100),
    }


def review_row(a: dict) -> dict:
    """Map an analysis into the pay_equity_reviews insert fields."""
    worst = a.get("worst")
    note = (f"{a['flagged_roles']}/{a['analyzed_roles']} roles exceed {int(_EXCESS_SPREAD)}% spread"
            + (f"; widest: {worst['title']} {worst['spread_pct']}%" if worst else "")
            + (f"; ~${a['remediation_estimate']:,} to lift {a['employees_below_band']} below-band"
               if a.get("remediation_estimate") else ""))
    return {
        "scope": f"auto: within-role pay dispersion ({a['analyzed_roles']} roles, {a['employee_count']} employees)",
        "methodology": "pay_rate dispersion by job title (screen only; protected-class gap needs HRIS demographics)",
        "gap_pct": a["headline_gap_pct"],
        "note": note,
    }
