"""Workers Comp + behavioral-friction metrics — extracted so the broker
portfolio endpoints and workers can reuse the same calc per linked client.

Moved from routes/ir_incidents/analytics.py (refactor round 2, stage 3).

The aggregate SQL fragments (`_WC_AGG_COLUMNS` / `_WC_QUARTER_COLUMNS`) and
`_assemble_wc_metrics` are also used by
`routes/ir_incidents/analytics.py:_compute_wc_metrics_by_location` (the
per-location fan-out, which stays a route-layer helper) — that function
imports them back from here.
"""
from datetime import datetime, timedelta
from typing import Optional
from uuid import UUID

# The aggregate expressions are identical for the company-wide roll-up and the
# per-location fan-out — only the GROUP BY differs — so they live here once.
_WC_AGG_COLUMNS = """
            COUNT(*) AS recordable_cases,
            COALESCE(SUM(CASE WHEN COALESCE(days_away_from_work, 0) > 0
                               OR COALESCE(days_restricted_duty, 0) > 0
                              THEN 1 ELSE 0 END), 0) AS dart_cases,
            COALESCE(SUM(COALESCE(days_away_from_work, 0)), 0) AS lost_days,
            COALESCE(SUM(COALESCE(days_restricted_duty, 0)), 0) AS restricted_days,
            COALESCE(SUM(CASE WHEN osha_classification = 'death' THEN 1 ELSE 0 END), 0) AS deaths,
            -- WC claim-depth (wcdeep01): taxonomy + post-term + return-to-work.
            COALESCE(SUM(CASE WHEN wc_claim_type = 'cumulative_trauma' THEN 1 ELSE 0 END), 0) AS ct_cases,
            COALESCE(SUM(CASE WHEN wc_claim_type = 'acute' THEN 1 ELSE 0 END), 0) AS acute_cases,
            COALESCE(SUM(CASE WHEN COALESCE(post_termination, false) THEN 1 ELSE 0 END), 0) AS post_term_cases,
            COALESCE(SUM(CASE WHEN COALESCE(days_away_from_work, 0) > 0 THEN 1 ELSE 0 END), 0) AS lost_time_cases,
            COALESCE(SUM(CASE WHEN COALESCE(days_away_from_work, 0) > 0
                               AND return_to_work_date IS NULL THEN 1 ELSE 0 END), 0) AS lost_time_open,
            COALESCE(SUM(CASE WHEN COALESCE(days_away_from_work, 0) > 0
                               AND return_to_work_date IS NOT NULL THEN 1 ELSE 0 END), 0) AS lost_time_resolved,
            AVG(CASE WHEN return_to_work_date IS NOT NULL AND COALESCE(days_away_from_work, 0) > 0
                     THEN (return_to_work_date - occurred_at::date) END) AS avg_days_to_rtw
"""

_WC_QUARTER_COLUMNS = """
            COUNT(*) AS recordable_cases,
            COALESCE(SUM(CASE WHEN COALESCE(days_away_from_work, 0) > 0
                               OR COALESCE(days_restricted_duty, 0) > 0
                              THEN 1 ELSE 0 END), 0) AS dart_cases,
            COALESCE(SUM(COALESCE(days_away_from_work, 0)), 0) AS lost_days
"""


async def compute_wc_metrics(conn, company_id: UUID, period_days: int = 365) -> dict:
    """Per-company Workers Comp metrics — extracted so the broker portfolio
    endpoint can reuse the same calc per linked client.

    Company-wide only. The per-location scorecard does NOT call this in a loop —
    see `_compute_wc_metrics_by_location` in routes/ir_incidents/analytics.py,
    which pulls the same aggregates for every establishment in one grouped pass
    and shares `_assemble_wc_metrics`.
    """
    # Lazy: stays in routes/ir_incidents/_shared.py (used widely by other
    # route submodules too) — a module-level import here would pull services
    # back into routes.
    from app.matcha.routes.ir_incidents._shared import _utc_now_naive

    period_start = _utc_now_naive() - timedelta(days=period_days)
    prior_start = period_start - timedelta(days=period_days)
    quarter_start = _utc_now_naive() - timedelta(days=730)  # 8 quarters back

    profile = await conn.fetchrow(
        """
        SELECT comp.industry, hp.headcount
        FROM companies comp
        LEFT JOIN company_handbook_profiles hp ON hp.company_id = comp.id
        WHERE comp.id = $1
        """,
        company_id,
    )
    industry = profile["industry"] if profile else None
    headcount = int(profile["headcount"]) if profile and profile["headcount"] else 0

    # Current + prior period totals.
    rows = await conn.fetch(
        f"""
        SELECT
            CASE WHEN occurred_at >= $2 THEN 'current' ELSE 'prior' END AS bucket,
            {_WC_AGG_COLUMNS}
        FROM ir_incidents
        WHERE company_id = $1
          AND osha_recordable = true
          AND occurred_at >= $3
        GROUP BY bucket
        """,
        company_id, period_start, prior_start,
    )

    # Quarterly bucketing — 8 quarters trailing.
    quarter_rows = await conn.fetch(
        f"""
        SELECT
            DATE_TRUNC('quarter', occurred_at) AS quarter_start,
            {_WC_QUARTER_COLUMNS}
        FROM ir_incidents
        WHERE company_id = $1
          AND osha_recordable = true
          AND occurred_at >= $2
        GROUP BY quarter_start
        ORDER BY quarter_start
        """,
        company_id, quarter_start,
    )

    last_recordable = await conn.fetchval(
        """
        SELECT MAX(occurred_at) FROM ir_incidents
        WHERE company_id = $1 AND osha_recordable = true
        """,
        company_id,
    )

    cur = next((r for r in rows if r["bucket"] == "current"), None)
    prv = next((r for r in rows if r["bucket"] == "prior"), None)

    return _assemble_wc_metrics(
        period_days=period_days,
        location_id=None,
        industry=industry,
        headcount=headcount,
        cur=cur,
        prv=prv,
        quarter_rows=quarter_rows,
        last_recordable=last_recordable,
    )


def _assemble_wc_metrics(
    *,
    period_days: int,
    location_id: Optional[UUID],
    industry: Optional[str],
    headcount: int,
    cur,
    prv,
    quarter_rows,
    last_recordable,
) -> dict:
    """Turn already-fetched aggregate rows into the WC metrics block.

    Pure (no DB) so the company-wide path and the per-location fan-out produce
    byte-identical shapes from differently-grouped queries.
    """
    from app.matcha.routes.ir_incidents._shared import _utc_now_naive
    from app.matcha.services.insurance.wc_benchmarks import (
        lookup_benchmark, estimate_premium_impact, severity_band,
    )

    annualization = 365.0 / period_days

    def _g(row, key):
        return int(row[key]) if row else 0

    recordable_cases = _g(cur, "recordable_cases")
    dart_cases = _g(cur, "dart_cases")
    lost_days = _g(cur, "lost_days")
    restricted_days = _g(cur, "restricted_days")
    deaths = _g(cur, "deaths")
    prior_recordable = _g(prv, "recordable_cases")
    prior_dart = _g(prv, "dart_cases")
    prior_lost_days = _g(prv, "lost_days")

    # WC claim-depth (wcdeep01) — current period only.
    ct_cases = _g(cur, "ct_cases")
    acute_cases = _g(cur, "acute_cases")
    unknown_type_cases = max(recordable_cases - ct_cases - acute_cases, 0)
    post_term_cases = _g(cur, "post_term_cases")
    lost_time_cases = _g(cur, "lost_time_cases")
    lost_time_open = _g(cur, "lost_time_open")
    lost_time_resolved = _g(cur, "lost_time_resolved")
    avg_days_to_rtw = (
        round(float(cur["avg_days_to_rtw"]), 1)
        if cur and cur["avg_days_to_rtw"] is not None else None
    )

    # Approximate hours worked over the period.
    hours_worked = float(headcount) * 2000.0 / annualization if headcount > 0 else 0.0
    insufficient = hours_worked < 50_000

    if hours_worked > 0:
        trir = round((recordable_cases * 200_000) / hours_worked, 2)
        dart_rate = round((dart_cases * 200_000) / hours_worked, 2)
        prior_trir = round((prior_recordable * 200_000) / hours_worked, 2)
        prior_dart_rate = round((prior_dart * 200_000) / hours_worked, 2)
    else:
        trir = None
        dart_rate = None
        prior_trir = None
        prior_dart_rate = None

    if last_recordable:
        days_since = (datetime.utcnow() - last_recordable).days
    else:
        days_since = None

    def _delta_pct(curr, prior):
        if prior is None or prior == 0:
            return None
        return round(((curr - prior) / prior) * 100, 1)

    benchmark = lookup_benchmark(industry)
    bench_trir = benchmark["trir"] if benchmark else None
    bench_sector = benchmark["sector"] if benchmark else None

    premium_impact = estimate_premium_impact(
        trir=trir, benchmark_trir=bench_trir,
        headcount=headcount or None, sector=bench_sector,
    )

    quarterly = []
    for qrow in quarter_rows:
        qstart = qrow["quarter_start"]
        q_label = f"{qstart.year}-Q{((qstart.month - 1) // 3) + 1}"
        quarterly.append({
            "quarter": q_label,
            "recordable": int(qrow["recordable_cases"]),
            "dart": int(qrow["dart_cases"]),
            "non_dart": int(qrow["recordable_cases"]) - int(qrow["dart_cases"]),
            "lost_days": int(qrow["lost_days"]),
        })

    return {
        "period_days": period_days,
        "location_id": str(location_id) if location_id else None,
        "industry": industry,
        "headcount": headcount or None,
        "hours_worked_assumed": int(hours_worked) if hours_worked > 0 else None,
        "recordable_cases": recordable_cases,
        "dart_cases": dart_cases,
        "lost_days": lost_days,
        "restricted_days": restricted_days,
        "deaths": deaths,
        "trir": trir,
        "dart_rate": dart_rate,
        "days_since_last_recordable": days_since,
        "ever_recordable": last_recordable is not None,
        "benchmark": benchmark,
        "premium_impact": premium_impact,
        "severity_band": severity_band(trir, bench_trir),
        # WC claim-depth (wcdeep01) — taxonomy, post-termination, return-to-work.
        "claim_breakdown": {
            "cumulative_trauma": ct_cases,
            "acute": acute_cases,
            "unknown": unknown_type_cases,
        },
        "post_termination_cases": post_term_cases,
        "rtw": {
            "lost_time_cases": lost_time_cases,
            "open": lost_time_open,
            "resolved": lost_time_resolved,
            "avg_days_to_rtw": avg_days_to_rtw,
        },
        "quarterly": quarterly,
        "prior": {
            "recordable_cases": prior_recordable,
            "dart_cases": prior_dart,
            "lost_days": prior_lost_days,
            "trir": prior_trir,
            "dart_rate": prior_dart_rate,
            "trir_delta_pct": _delta_pct(trir, prior_trir),
            "dart_delta_pct": _delta_pct(dart_rate, prior_dart_rate),
            "lost_days_delta_pct": _delta_pct(lost_days, prior_lost_days),
            "recordable_delta_pct": _delta_pct(recordable_cases, prior_recordable),
        },
        "data_quality": {
            "insufficient_population": insufficient,
            "headcount_missing": headcount == 0,
        },
        "generated_at": _utc_now_naive().isoformat(),
    }


async def compute_behavioral_friction(conn, company_id: UUID, window_days: int = 90) -> dict:
    """Per-company behavioral-incident spike metrics for the broker
    "Behavioral Friction & Retention Risk" alert.

    A short recent window (default 90d) vs the equal-length window before it,
    so a *sudden* surge in behavioral incidents (incl. insubordination /
    attendance) trips the alert — distinct from the trailing-12mo WC trend in
    ``compute_wc_metrics``. Count-based: no headcount / hours estimate needed.

    The attendance / insubordination sub-counts come from
    ``category_data->>'policy_violated'`` (with a title fallback) — the
    taxonomy has no distinct types for them; they live under ``behavioral``.

    Returns the current/prior counts, % delta, subtype sub-counts (current
    window), and the single location with the most behavioral incidents this
    window so the alert message can name where the friction is concentrated.
    """
    from app.matcha.routes.ir_incidents._shared import _utc_now_naive

    window_start = _utc_now_naive() - timedelta(days=window_days)
    prior_start = window_start - timedelta(days=window_days)

    rows = await conn.fetch(
        """
        SELECT
            CASE WHEN occurred_at >= $2 THEN 'current' ELSE 'prior' END AS bucket,
            COUNT(*) AS behavioral_count,
            COALESCE(SUM(CASE
                WHEN category_data->>'policy_violated' ILIKE '%attendance%'
                  OR title ILIKE '%attendance%'
                THEN 1 ELSE 0 END), 0) AS attendance_count,
            COALESCE(SUM(CASE
                WHEN category_data->>'policy_violated' ILIKE '%insubordinat%'
                  OR title ILIKE '%insubordinat%'
                THEN 1 ELSE 0 END), 0) AS insubordination_count
        FROM ir_incidents
        WHERE company_id = $1
          AND incident_type = 'behavioral'
          AND occurred_at >= $3
        GROUP BY bucket
        """,
        company_id, window_start, prior_start,
    )

    current_count = prior_count = 0
    attendance_count = insubordination_count = 0
    for r in rows:
        if r["bucket"] == "current":
            current_count = int(r["behavioral_count"])
            attendance_count = int(r["attendance_count"])
            insubordination_count = int(r["insubordination_count"])
        else:
            prior_count = int(r["behavioral_count"])

    hot = await conn.fetchrow(
        """
        SELECT COALESCE(bl.name, NULLIF(i.location, ''), 'Unspecified location') AS loc_name,
               COUNT(*) AS cnt
        FROM ir_incidents i
        LEFT JOIN business_locations bl ON bl.id = i.location_id
        WHERE i.company_id = $1
          AND i.incident_type = 'behavioral'
          AND i.occurred_at >= $2
        GROUP BY loc_name
        ORDER BY cnt DESC
        LIMIT 1
        """,
        company_id, window_start,
    )

    def _delta_pct(curr, prior):
        if prior is None or prior == 0:
            return None
        return round(((curr - prior) / prior) * 100, 1)

    return {
        "window_days": window_days,
        "current_count": current_count,
        "prior_count": prior_count,
        "delta_pct": _delta_pct(current_count, prior_count),
        "attendance_count": attendance_count,
        "insubordination_count": insubordination_count,
        "hot_location": (
            {"name": hot["loc_name"], "count": int(hot["cnt"])} if hot and hot["cnt"] else None
        ),
        "generated_at": _utc_now_naive().isoformat(),
    }
