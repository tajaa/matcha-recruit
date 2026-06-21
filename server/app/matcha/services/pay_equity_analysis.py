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


async def analyze(conn, company_id: UUID) -> dict:
    """Within-role pay dispersion. Returns roles (≥2 employees) + an excess-dispersion
    headline (% of roles flagged) for the EPL derive."""
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

    roles = []
    for title, pays in by_role.items():
        if len(pays) < 2:
            continue
        med = statistics.median(pays)
        lo, hi = min(pays), max(pays)
        spread = round(100 * (hi - lo) / med, 1) if med else 0.0
        roles.append({"title": title, "n": len(pays), "median": round(med),
                      "min": round(lo), "max": round(hi), "spread_pct": spread})
    roles.sort(key=lambda r: r["spread_pct"], reverse=True)

    flagged = [r for r in roles if r["spread_pct"] >= _EXCESS_SPREAD]
    headline = round(100 * len(flagged) / len(roles)) if roles else 0
    return {
        "employee_count": len(rows),
        "analyzed_roles": len(roles),
        "flagged_roles": len(flagged),
        "headline_gap_pct": headline,          # % of roles with excess dispersion
        "worst": roles[0] if roles else None,
        "roles": roles,
    }


def review_row(a: dict) -> dict:
    """Map an analysis into the pay_equity_reviews insert fields."""
    worst = a.get("worst")
    note = (f"{a['flagged_roles']}/{a['analyzed_roles']} roles exceed {int(_EXCESS_SPREAD)}% spread"
            + (f"; widest: {worst['title']} {worst['spread_pct']}%" if worst else ""))
    return {
        "scope": f"auto: within-role pay dispersion ({a['analyzed_roles']} roles, {a['employee_count']} employees)",
        "methodology": "pay_rate dispersion by job title (screen only; protected-class gap needs HRIS demographics)",
        "gap_pct": a["headline_gap_pct"],
        "note": note,
    }
