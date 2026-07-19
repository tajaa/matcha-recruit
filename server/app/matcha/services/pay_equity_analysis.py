"""Pay-equity analysis from comp data — replaces the manual study log with a real
computation over employees.pay_rate. Writes a pay_equity_reviews row so the EPL
factor derives from data, not a hand-entered date.

Two measurements, deliberately kept apart:

  * DISPERSION (always available) — within-role pay spread by job title. A screen,
    not a finding: legitimate drivers like seniority are included. Reported as
    `dispersion_pct` = the share of roles whose spread exceeds the threshold.
  * PROTECTED-CLASS GAP (needs HRIS demographics) — within-role median pay by
    gender/ethnicity. Reported as `class_gap_pct`, and the only thing that may be
    called a "gap".

Those are different quantities and conflating them was a live defect: the auto path
wrote the dispersion share into `pay_equity_reviews.gap_pct` — documented as
"adjusted pay gap %" and rendered to brokers as "{x}% gap, remediation pending" —
so a company with 40% of roles showing spread reported a "40.0% gap" to an
underwriter. Demographics now come from the HRIS `individual` payload
(employee_demographics), so `gap_pct` can mean what it says, and is left NULL when
we haven't measured one.
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

# Protected-class gap thresholds.
_MIN_CLASS_CELL = 5    # per-class headcount below this is suppressed (see class_gap_stats)
_MIN_COVERAGE = 50.0   # % of analyzed employees needing a demographic before we report a gap
_MATERIAL_GAP = 5.0    # a measured gap at/above this is worth naming in the summary


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


def class_gap_stats(title: str, pays_by_class: dict[str, list[float]]) -> dict | None:
    """Within-role median pay gap between protected classes. Pure (no DB).

    The real thing `role_stats` explicitly is not: it compares medians ACROSS groups
    within one role, so it measures difference attributable to class rather than
    spread attributable to anything.

    Two rules keep it honest:

    * SMALL-CELL SUPPRESSION — a class with fewer than _MIN_CLASS_CELL people in the
      role is dropped. At n=1 a "median" is one person's salary, so the "gap" is just
      that individual, and reporting it both invents a statistic and re-identifies
      them (a 1-person cell names whoever it is to anyone who knows the team).
    * Fewer than two surviving classes → None. A gap needs something to compare to;
      with one group there is no comparison, and 0.0 would read as "no gap found"
      when the truth is "not measurable here".

    Gap is signed-free: the magnitude between the highest- and lowest-paid class
    medians, as a % of the highest. `reference` names the top-paid class so the
    direction is legible without the caller re-deriving it.
    """
    cells = {
        cls: sorted(float(p) for p in pays)
        for cls, pays in pays_by_class.items()
        if cls and len(pays) >= _MIN_CLASS_CELL
    }
    if len(cells) < 2:
        return None

    medians = {cls: statistics.median(pays) for cls, pays in cells.items()}
    top_class = max(medians, key=lambda c: medians[c])
    low_class = min(medians, key=lambda c: medians[c])
    top, low = medians[top_class], medians[low_class]
    gap_pct = round(100 * (top - low) / top, 1) if top else 0.0

    return {
        "title": title,
        "gap_pct": gap_pct,
        "reference": top_class,
        "lowest": low_class,
        "n": sum(len(p) for p in cells.values()),
        "classes": [
            {"class": cls, "n": len(cells[cls]), "median": round(med)}
            for cls, med in sorted(medians.items(), key=lambda kv: -kv[1])
        ],
        # Suppressed cells are reported as a count, never as members: the caller can
        # say "3 employees excluded as too few to compare" without naming a group of
        # one. Excluding them silently would make coverage look better than it is.
        "suppressed_n": sum(
            len(p) for cls, p in pays_by_class.items() if cls and len(p) < _MIN_CLASS_CELL
        ),
    }


def posture_band(roles: list[dict], employees_below_band: int) -> dict:
    """Overall pay-equity posture headline from the per-role severities. Pure.

    'action' when anyone sits below their role's pay band or a quarter-plus of
    roles show excess dispersion; 'watch' when some dispersion exists but no one
    is below band; 'equitable' when every role is within range."""
    if not roles:
        return {"band": "insufficient", "label": "Insufficient data"}
    flagged = sum(1 for r in roles if r["severity"] == "flag")
    watch = sum(1 for r in roles if r["severity"] == "watch")
    if employees_below_band > 0 or flagged / len(roles) >= 0.25:
        return {"band": "action", "label": "Action recommended"}
    if flagged or watch:
        return {"band": "watch", "label": "Monitor"}
    return {"band": "equitable", "label": "Within range"}


def priority_actions(roles: list[dict], limit: int = 5) -> list[dict]:
    """Ranked 'fix first' list — the roles to act on, biggest remediation dollars
    first. Pure (unit-tested). Roles with employees below band rank ahead of merely
    high-spread roles, since those carry real dollars to close."""
    candidates = [r for r in roles if r["below_band_n"] > 0 or r["severity"] == "flag"]
    candidates.sort(key=lambda r: (r["below_band_n"] == 0, -r["remediation_cost"], -r["spread_pct"]))
    out: list[dict] = []
    for r in candidates[:limit]:
        if r["below_band_n"] > 0:
            people = f"{r['below_band_n']} employee{'' if r['below_band_n'] == 1 else 's'}"
            action = f"Lift {people} in {r['title']} to the pay floor (~${r['remediation_cost']:,})"
        else:
            action = f"Review {r['spread_pct']}% spread across {r['n']} {r['title']} — document drivers or compress"
        out.append({
            "title": r["title"], "severity": r["severity"],
            "below_band_n": r["below_band_n"], "remediation_cost": r["remediation_cost"],
            "spread_pct": r["spread_pct"], "action": action,
        })
    return out


async def analyze(conn, company_id: UUID) -> dict:
    """Within-role pay dispersion, plus a protected-class gap where HRIS demographics
    reach far enough to measure one.

    The demographics LEFT JOIN is the ONLY read of employee_demographics in the
    codebase, and deliberately so — the table is separate from `employees` precisely
    so protected-class fields can't ride along in roster reads, exports, or broker
    payloads. Nothing here returns a per-employee demographic; only aggregates that
    survive small-cell suppression leave this function."""
    rows = await conn.fetch(
        f"""
        SELECT COALESCE(NULLIF(TRIM(e.job_title), ''), '(untitled)') AS title,
               {_ANNUALIZE} AS pay,
               d.gender
        FROM employees e
        LEFT JOIN employee_demographics d ON d.employee_id = e.id
        WHERE e.org_id = $1 AND e.pay_rate IS NOT NULL
          AND COALESCE(e.employment_status, 'active') NOT ILIKE 'term%'
        """,
        company_id,
    )
    by_role: dict[str, list[float]] = defaultdict(list)
    by_role_class: dict[str, dict[str, list[float]]] = defaultdict(lambda: defaultdict(list))
    with_gender = 0
    for r in rows:
        if r["pay"] and float(r["pay"]) > 0:
            by_role[r["title"]].append(float(r["pay"]))
            gender = (r["gender"] or "").strip().lower()
            # "decline_to_specify" is an answer about privacy, not a class to compare —
            # treating it as a group would manufacture a cohort out of non-responses.
            if gender and gender != "decline_to_specify":
                by_role_class[r["title"]][gender].append(float(r["pay"]))
                with_gender += 1

    roles = [role_stats(title, pays) for title, pays in by_role.items() if len(pays) >= 2]
    roles.sort(key=lambda r: r["spread_pct"], reverse=True)

    flagged = [r for r in roles if r["severity"] == "flag"]
    headline = round(100 * len(flagged) / len(roles)) if roles else 0

    total_payroll = round(sum(p for pays in by_role.values() for p in pays))
    flagged_titles = {r["title"] for r in flagged}
    flagged_payroll = sum(p for t, pays in by_role.items() for p in pays if t in flagged_titles)
    employees_below_band = sum(r["below_band_n"] for r in roles)

    # ── protected-class gap (only where demographics reach) ──────────────────
    analyzed_pop = sum(len(pays) for pays in by_role.values())
    coverage = round(100 * with_gender / analyzed_pop, 1) if analyzed_pop else 0.0
    class_gaps = [
        g for g in (
            class_gap_stats(title, by_role_class.get(title, {}))
            for title, pays in by_role.items() if len(pays) >= 2
        ) if g
    ]
    class_gaps.sort(key=lambda g: g["gap_pct"], reverse=True)
    # Headline gap is weighted by the population each role's comparison covers, so a
    # 40-person role isn't outvoted by a 5-person one. Withheld entirely below the
    # coverage floor: a gap computed from a fifth of the roster is a number about
    # that fifth, and publishing it as the company's gap would be the same
    # over-claim this module exists to undo.
    measurable = coverage >= _MIN_COVERAGE and bool(class_gaps)
    if measurable:
        weight = sum(g["n"] for g in class_gaps)
        class_gap_pct = round(sum(g["gap_pct"] * g["n"] for g in class_gaps) / weight, 1)
    else:
        class_gap_pct = None

    return {
        "employee_count": len(rows),
        "analyzed_roles": len(roles),
        "flagged_roles": len(flagged),
        "headline_gap_pct": headline,          # % of roles with excess dispersion
        # None = not measured (no/insufficient demographics), never 0.0 — "we didn't
        # look" and "we looked and found parity" must not collapse into one value.
        "class_gap_pct": class_gap_pct,
        "class_gaps": class_gaps,
        "demographics_coverage_pct": coverage,
        "class_gap_measurable": measurable,
        "min_class_cell": _MIN_CLASS_CELL,
        "worst": roles[0] if roles else None,
        "roles": roles,
        # --- company-wide actionable rollups (client report depth) ---
        "total_payroll": total_payroll,
        "median_spread_pct": round(statistics.median([r["spread_pct"] for r in roles]), 1) if roles else 0.0,
        "employees_below_band": employees_below_band,
        "flagged_payroll_pct": round(100 * flagged_payroll / total_payroll, 1) if total_payroll else 0.0,
        "remediation_estimate": round(sum(r["remediation_cost"] for r in roles)),
        "band_floor_pct": int(_BAND_FLOOR * 100),
        # --- actionable layer: overall posture + ranked fixes ---
        "posture": posture_band(roles, employees_below_band),
        "priority_actions": priority_actions(roles),
    }


def review_row(a: dict) -> dict:
    """Map an analysis into the pay_equity_reviews insert fields.

    `gap_pct` carries a measured protected-class gap or NOTHING. It used to carry the
    dispersion share, which downstream (`workforce_compliance.derive_pay_equity`)
    reports to brokers as "{gap}% gap" — so the number in the underwriter's hands
    described a different quantity than its label claimed. Dispersion now has its own
    column, and the methodology string states per-row which measurement actually ran
    rather than one hardcoded disclaimer for both cases.
    """
    worst = a.get("worst")
    measured = a.get("class_gap_pct") is not None
    note = (f"{a['flagged_roles']}/{a['analyzed_roles']} roles exceed {int(_EXCESS_SPREAD)}% spread"
            + (f"; widest: {worst['title']} {worst['spread_pct']}%" if worst else "")
            + (f"; ~${a['remediation_estimate']:,} to lift {a['employees_below_band']} below-band"
               if a.get("remediation_estimate") else ""))
    if measured:
        top = a["class_gaps"][0] if a.get("class_gaps") else None
        note += (f"; measured {a['class_gap_pct']}% gender pay gap across "
                 f"{a['demographics_coverage_pct']}% of the roster")
        if top and top["gap_pct"] >= _MATERIAL_GAP:
            note += f"; widest in {top['title']} ({top['gap_pct']}%, {top['reference']} highest paid)"
        methodology = (f"within-role gender pay gap from HRIS demographics "
                       f"(n≥{_MIN_CLASS_CELL}/class; {a['demographics_coverage_pct']}% coverage) "
                       f"+ pay dispersion by job title")
    else:
        methodology = ("pay_rate dispersion by job title "
                       "(screen only; protected-class gap needs HRIS demographics)")

    return {
        "scope": f"auto: within-role pay dispersion ({a['analyzed_roles']} roles, {a['employee_count']} employees)",
        "methodology": methodology,
        "gap_pct": a.get("class_gap_pct"),
        "dispersion_pct": a["headline_gap_pct"],
        "note": note,
    }
