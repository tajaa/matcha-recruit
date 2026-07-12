"""Analytics + risk endpoints for IR Incidents.

Covers:
- Summary  (counts by type/severity/status)
- Trends   (time-series)
- Locations (hotspot heatmap)
- WC metrics  (workers-comp benchmarks)
- Risk matrix
- Risk insights (themed dashboards)
- Consistency analytics

Also exposes the `compute_wc_metrics` service-style function used by
`broker_portfolio.py`.
"""
import json
import logging
from datetime import datetime, timedelta, timezone
from typing import Optional
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from fastapi.responses import StreamingResponse

from app.config import get_settings
from app.database import get_connection
from app.matcha.dependencies import require_admin_or_client, get_client_company_id
from app.matcha.models.ir_incident import (
    AnalyticsSummary,
    ConsistencyAnalytics,
    LeadingIndicators,
    LocationAnalysis,
    LocationHotspot,
    RiskInsightsResponse,
    RiskMatrixCell,
    RiskMatrixResponse,
    RiskMatrixRow,
    RiskTheme,
    TrendDataPoint,
    TrendsAnalysis,
    WcByLocationResponse,
    WcLocationScorecard,
)

# Helpers still living in _legacy.py; will move to _shared.py in step 10.
from ._shared import (
    _safe_json_loads,
    _utc_now_naive,
)

logger = logging.getLogger(__name__)

router = APIRouter()


@router.get("/analytics/summary", response_model=AnalyticsSummary)
async def get_analytics_summary(
    current_user=Depends(require_admin_or_client),
):
    """Get summary analytics for the dashboard."""
    company_id = await get_client_company_id(current_user)
    empty = AnalyticsSummary(
        total=0, open=0, investigating=0, resolved=0, closed=0,
        critical=0, high=0, medium=0, low=0, by_type={},
    )
    if company_id is None:
        return empty
    co_filter = "company_id = $1"

    async with get_connection() as conn:
        total = await conn.fetchval(f"SELECT COUNT(*) FROM ir_incidents WHERE {co_filter}", company_id)

        status_rows = await conn.fetch(
            f"SELECT status, COUNT(*) as count FROM ir_incidents WHERE {co_filter} GROUP BY status", company_id
        )
        by_status = {row["status"]: row["count"] for row in status_rows}

        type_rows = await conn.fetch(
            f"SELECT incident_type, COUNT(*) as count FROM ir_incidents WHERE {co_filter} GROUP BY incident_type", company_id
        )
        by_type = {row["incident_type"]: row["count"] for row in type_rows}

        severity_rows = await conn.fetch(
            f"SELECT severity, COUNT(*) as count FROM ir_incidents WHERE {co_filter} GROUP BY severity", company_id
        )
        by_severity = {row["severity"]: row["count"] for row in severity_rows}

        return AnalyticsSummary(
            total=total or 0,
            open=by_status.get("reported", 0) + by_status.get("action_required", 0),
            investigating=by_status.get("investigating", 0),
            resolved=by_status.get("resolved", 0),
            closed=by_status.get("closed", 0),
            critical=by_severity.get("critical", 0),
            high=by_severity.get("high", 0),
            medium=by_severity.get("medium", 0),
            low=by_severity.get("low", 0),
            by_type=by_type,
        )


@router.get("/analytics/trends", response_model=TrendsAnalysis)
async def get_analytics_trends(
    period: str = Query("daily", enum=["daily", "weekly", "monthly"]),
    days: int = Query(30, ge=7, le=365),
    current_user=Depends(require_admin_or_client),
):
    """Get incident trends over time."""
    company_id = await get_client_company_id(current_user)
    if company_id is None:
        return TrendsAnalysis(data=[], period=period, start_date="", end_date="")
    co_filter = "company_id = $2"

    # Map validated period to SQL DATE_TRUNC argument (never from user input)
    trunc_map = {"daily": "day", "weekly": "week", "monthly": "month"}
    date_trunc = trunc_map[period]

    async with get_connection() as conn:
        start_date = _utc_now_naive() - timedelta(days=days)

        rows = await conn.fetch(
            f"""
            SELECT
                DATE_TRUNC('{date_trunc}', occurred_at) as period_start,
                COUNT(*) as count,
                COALESCE(SUM(CASE WHEN osha_recordable = true THEN 1 ELSE 0 END), 0) AS recordable_count,
                incident_type,
                severity
            FROM ir_incidents
            WHERE {co_filter} AND occurred_at >= $1
            GROUP BY period_start, incident_type, severity
            ORDER BY period_start
            """,
            start_date,
            company_id,
        )

        # Aggregate by period across both type + severity dims.
        data_map: dict[str, dict] = {}
        for row in rows:
            date_str = row["period_start"].strftime("%Y-%m-%d")
            entry = data_map.setdefault(date_str, {
                "count": 0,
                "recordable_count": 0,
                "by_type": {},
                "by_severity": {},
            })
            cnt = int(row["count"])
            entry["count"] += cnt
            entry["recordable_count"] += int(row["recordable_count"] or 0)
            t = row["incident_type"] or "other"
            s = row["severity"] or "medium"
            entry["by_type"][t] = entry["by_type"].get(t, 0) + cnt
            entry["by_severity"][s] = entry["by_severity"].get(s, 0) + cnt

        data = [
            TrendDataPoint(
                date=date,
                count=info["count"],
                by_type=info["by_type"],
                by_severity=info["by_severity"],
                recordable_count=info["recordable_count"],
            )
            for date, info in sorted(data_map.items())
        ]

        return TrendsAnalysis(
            data=data,
            period=period,
            start_date=start_date.strftime("%Y-%m-%d"),
            end_date=_utc_now_naive().strftime("%Y-%m-%d"),
        )


@router.get("/analytics/locations", response_model=LocationAnalysis)
async def get_analytics_locations(
    limit: int = Query(10, ge=1, le=50),
    current_user=Depends(require_admin_or_client),
):
    """Get incident hotspots by location.

    Now groups by `location_id` (joined to business_locations) so the
    same physical site doesn't double-count when its free-text label
    drifted across edits. Legacy rows with NULL location_id roll up
    under a single "Unassigned (legacy)" bucket; rows whose location_id
    points at a deleted location use the legacy free-text label as
    fallback.
    """
    company_id = await get_client_company_id(current_user)
    if company_id is None:
        return LocationAnalysis(hotspots=[], total_locations=0)

    async with get_connection() as conn:
        rows = await conn.fetch(
            """
            SELECT
                i.location_id,
                i.location AS legacy_location,
                bl.name AS bl_name,
                bl.city AS bl_city,
                bl.state AS bl_state,
                COUNT(*) AS cnt,
                i.incident_type,
                AVG(CASE
                    WHEN i.severity = 'critical' THEN 4
                    WHEN i.severity = 'high' THEN 3
                    WHEN i.severity = 'medium' THEN 2
                    ELSE 1
                END) AS severity_score
            FROM ir_incidents i
            LEFT JOIN business_locations bl ON bl.id = i.location_id
            WHERE i.company_id = $1
            GROUP BY i.location_id, i.location, bl.name, bl.city, bl.state, i.incident_type
            """,
            company_id,
        )

        # Aggregate by location: prefer location_id grouping; fall back to
        # free-text under a single "Unassigned" bucket for legacy rows.
        location_map: dict = {}
        for row in rows:
            loc_id = row["location_id"]
            if loc_id is None:
                key = ("__unassigned__", UNASSIGNED_LOCATION_LABEL)
            else:
                label = (row["bl_name"] or "").strip()
                if not label:
                    place = ", ".join([p for p in (row["bl_city"], row["bl_state"]) if p])
                    label = place or (row["legacy_location"] or str(loc_id)[:8])
                key = (str(loc_id), label)

            bucket = location_map.setdefault(
                key, {"count": 0, "by_type": {}, "severity_scores": []},
            )
            cnt = int(row["cnt"] or 0)
            bucket["count"] += cnt
            bucket["by_type"][row["incident_type"]] = bucket["by_type"].get(row["incident_type"], 0) + cnt
            bucket["severity_scores"].append(float(row["severity_score"] or 0))

        sorted_locations = sorted(
            location_map.items(), key=lambda x: x[1]["count"], reverse=True,
        )[:limit]

        hotspots = [
            LocationHotspot(
                location=label,
                count=info["count"],
                by_type=info["by_type"],
                avg_severity_score=round(
                    sum(info["severity_scores"]) / len(info["severity_scores"]), 2,
                ) if info["severity_scores"] else 0.0,
            )
            for (_, label), info in sorted_locations
        ]

        return LocationAnalysis(
            hotspots=hotspots,
            total_locations=len(location_map),
        )


# ===========================================
# Risk Insights — locations × type matrix + Gemini themes
#
# Cross-tier: gated by the `incidents` feature flag (the existing IR gate),
# so both Matcha Cap (ir_only_self_serve) and full Matcha (bespoke) tenants
# get this. Auto-derived business_locations rows from compliance only show
# up here when they have ≥1 incident — they fall out naturally via JOIN.
# ===========================================


SEVERITY_WEIGHT = {"critical": 4.0, "high": 3.0, "medium": 2.0, "low": 1.0}

INCIDENT_TYPES_ORDER = ["safety", "behavioral", "property", "near_miss", "other"]

UNASSIGNED_LOCATION_LABEL = "Unassigned (legacy)"


def _build_risk_scope_key(location_id: Optional[UUID], period_days: int) -> str:
    """Deterministic cache key for ir_company_analysis.scope_key."""
    loc_part = str(location_id) if location_id else "all"
    return f"loc={loc_part}:days={period_days}"


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
    see `_compute_wc_metrics_by_location`, which pulls the same aggregates for
    every establishment in one grouped pass and shares `_assemble_wc_metrics`.
    """
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
    from app.matcha.services.wc_benchmarks import (
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


@router.get("/analytics/wc-metrics")
async def get_wc_metrics(
    period_days: int = Query(365, ge=30, le=1095),
    current_user=Depends(require_admin_or_client),
):
    """OSHA-style frequency + severity metrics for Workers Comp framing.

    Returns TRIR, DART rate, lost-day totals, claims-free streak, prior-period
    deltas, NAICS-sector benchmark, premium-impact estimate, and trailing
    8-quarter recordable bars. Used by P&C brokers to frame an employer's
    E-Mod posture. See compute_wc_metrics() for the math + caveats.
    """
    company_id = await get_client_company_id(current_user)
    if company_id is None:
        raise HTTPException(status_code=400, detail="No company associated with user")
    async with get_connection() as conn:
        return await compute_wc_metrics(conn, company_id, period_days)


async def _batch_active_headcounts(conn, company_id, loc_rows) -> dict:
    """Active-employee count per establishment, in ONE query.

    Mirrors osha.py:_active_headcount exactly — sole-location short-circuit, then
    FK match OR the work_city/work_state heuristic (HRIS sync populates the city
    but never the location FK) — but resolves every location at once instead of
    one query per site.
    """
    if len(loc_rows) == 1:
        total = await conn.fetchval(
            "SELECT COUNT(*) FROM employees WHERE org_id = $1 AND termination_date IS NULL",
            company_id,
        ) or 0
        return {loc_rows[0]["id"]: int(total)}

    rows = await conn.fetch(
        """
        SELECT bl.id AS location_id, COUNT(e.id) AS headcount
        FROM business_locations bl
        LEFT JOIN employees e
          ON e.org_id = bl.company_id
         AND e.termination_date IS NULL
         AND (
              e.work_location_id = bl.id
              OR (
                   e.work_location_id IS NULL
                   AND bl.city IS NOT NULL
                   AND LOWER(e.work_city) = LOWER(bl.city)
                   AND UPPER(e.work_state) = UPPER(bl.state)
                 )
             )
        WHERE bl.id = ANY($1::uuid[])
        GROUP BY bl.id
        """,
        [lr["id"] for lr in loc_rows],
    )
    return {r["location_id"]: int(r["headcount"] or 0) for r in rows}


async def _compute_wc_metrics_by_location(
    conn, company_id: UUID, period_days: int, loc_rows, *, industry
) -> dict:
    """WC metrics for every establishment, in a fixed number of queries.

    The three aggregates compute_wc_metrics runs company-wide are re-run ONCE
    each, grouped by location_id, and sliced per site — so a 50-location tenant
    costs 4 queries instead of the ~200 a per-location compute_wc_metrics loop
    would issue. Assembly is shared with the company-wide path.
    """
    period_start = _utc_now_naive() - timedelta(days=period_days)
    prior_start = period_start - timedelta(days=period_days)
    quarter_start = _utc_now_naive() - timedelta(days=730)
    loc_ids = [lr["id"] for lr in loc_rows]

    headcounts = await _batch_active_headcounts(conn, company_id, loc_rows)

    bucket_rows = await conn.fetch(
        f"""
        SELECT
            location_id,
            CASE WHEN occurred_at >= $2 THEN 'current' ELSE 'prior' END AS bucket,
            {_WC_AGG_COLUMNS}
        FROM ir_incidents
        WHERE company_id = $1
          AND osha_recordable = true
          AND occurred_at >= $3
          AND location_id = ANY($4::uuid[])
        GROUP BY location_id, bucket
        """,
        company_id, period_start, prior_start, loc_ids,
    )

    quarter_rows = await conn.fetch(
        f"""
        SELECT
            location_id,
            DATE_TRUNC('quarter', occurred_at) AS quarter_start,
            {_WC_QUARTER_COLUMNS}
        FROM ir_incidents
        WHERE company_id = $1
          AND osha_recordable = true
          AND occurred_at >= $2
          AND location_id = ANY($3::uuid[])
        GROUP BY location_id, quarter_start
        ORDER BY quarter_start
        """,
        company_id, quarter_start, loc_ids,
    )

    last_rows = await conn.fetch(
        """
        SELECT location_id, MAX(occurred_at) AS last_recordable
        FROM ir_incidents
        WHERE company_id = $1
          AND osha_recordable = true
          AND location_id = ANY($2::uuid[])
        GROUP BY location_id
        """,
        company_id, loc_ids,
    )
    last_by_loc = {r["location_id"]: r["last_recordable"] for r in last_rows}

    out = {}
    for lid in loc_ids:
        cur = next(
            (r for r in bucket_rows if r["location_id"] == lid and r["bucket"] == "current"), None
        )
        prv = next(
            (r for r in bucket_rows if r["location_id"] == lid and r["bucket"] == "prior"), None
        )
        out[lid] = _assemble_wc_metrics(
            period_days=period_days,
            location_id=lid,
            industry=industry,
            headcount=headcounts.get(lid, 0),
            cur=cur,
            prv=prv,
            quarter_rows=[r for r in quarter_rows if r["location_id"] == lid],
            last_recordable=last_by_loc.get(lid),
        )
    return out


@router.get("/analytics/wc-metrics/by-location", response_model=WcByLocationResponse)
async def get_wc_metrics_by_location(
    period_days: int = Query(365, ge=30, le=1095),
    current_user=Depends(require_admin_or_client),
):
    """Per-establishment TRIR/DART scorecards + the company roll-up.

    Fans compute_wc_metrics out over each active business_location (scoped
    incidents + a location-specific headcount so the rates are meaningful),
    alongside the company-wide block. Large multi-site buyers use this to see
    which site drives the composite number. Capped at 50 locations.
    """
    company_id = await get_client_company_id(current_user)
    if company_id is None:
        raise HTTPException(status_code=400, detail="No company associated with user")

    async with get_connection() as conn:
        company_metrics = await compute_wc_metrics(conn, company_id, period_days)

        loc_rows = await conn.fetch(
            """
            SELECT id, name, city, state
            FROM business_locations
            WHERE company_id = $1 AND is_active = true
            ORDER BY name ASC
            LIMIT 50
            """,
            company_id,
        )
        if not loc_rows:
            return WcByLocationResponse(
                period_days=period_days,
                company=company_metrics,
                locations=[],
                generated_at=_utc_now_naive().isoformat(),
            )

        per_location = await _compute_wc_metrics_by_location(
            conn, company_id, period_days, loc_rows,
            industry=company_metrics.get("industry"),
        )

    scorecards = [
        WcLocationScorecard(
            location_id=lr["id"],
            location_name=lr["name"] or "Unnamed location",
            city=lr["city"],
            state=lr["state"],
            metrics=per_location[lr["id"]],
        )
        for lr in loc_rows
    ]

    return WcByLocationResponse(
        period_days=period_days,
        company=company_metrics,
        locations=scorecards,
        generated_at=_utc_now_naive().isoformat(),
    )


@router.get("/analytics/leading-indicators", response_model=LeadingIndicators)
async def get_leading_indicators(
    period_days: int = Query(365, ge=30, le=1095),
    current_user=Depends(require_admin_or_client),
):
    """Leading (predictive) safety signals: near-miss volume + CAPA follow-through.

    Lagging metrics (TRIR/DART) tell you what already happened; near-miss volume,
    the near-miss-to-recordable ratio, and corrective-action close-rate are the
    forward-looking counterparts. Pure SQL over ir_incidents + ir_corrective_actions.
    """
    company_id = await get_client_company_id(current_user)
    generated_at = _utc_now_naive().isoformat()
    if company_id is None:
        return LeadingIndicators(
            period_days=period_days, near_miss_count=0, recordable_count=0,
            generated_at=generated_at,
        )

    period_start = _utc_now_naive() - timedelta(days=period_days)
    prior_start = period_start - timedelta(days=period_days)

    async with get_connection() as conn:
        inc = await conn.fetchrow(
            """
            SELECT
                COALESCE(SUM(CASE WHEN incident_type = 'near_miss'
                                   AND occurred_at >= $2 THEN 1 ELSE 0 END), 0) AS near_miss,
                COALESCE(SUM(CASE WHEN incident_type = 'near_miss'
                                   AND occurred_at >= $3 AND occurred_at < $2 THEN 1 ELSE 0 END), 0) AS near_miss_prior,
                COALESCE(SUM(CASE WHEN osha_recordable = true
                                   AND occurred_at >= $2 THEN 1 ELSE 0 END), 0) AS recordable,
                COALESCE(SUM(CASE WHEN occurred_at >= $2 THEN 1 ELSE 0 END), 0) AS total
            FROM ir_incidents
            WHERE company_id = $1
            """,
            company_id, period_start, prior_start,
        )

        capa = await conn.fetchrow(
            """
            SELECT
                COALESCE(SUM(CASE WHEN status IN ('open', 'in_progress') THEN 1 ELSE 0 END), 0) AS open,
                COALESCE(SUM(CASE WHEN status IN ('open', 'in_progress')
                                   AND due_date IS NOT NULL AND due_date < CURRENT_DATE
                                  THEN 1 ELSE 0 END), 0) AS overdue,
                COALESCE(SUM(CASE WHEN status IN ('completed', 'verified') THEN 1 ELSE 0 END), 0) AS completed,
                COUNT(*) AS total,
                AVG(CASE WHEN status IN ('completed', 'verified') AND completed_at IS NOT NULL
                         THEN EXTRACT(EPOCH FROM (completed_at - created_at)) / 86400.0 END) AS avg_days_to_close
            FROM ir_corrective_actions
            WHERE company_id = $1
            """,
            company_id,
        )

    near_miss = int(inc["near_miss"])
    near_miss_prior = int(inc["near_miss_prior"])
    recordable = int(inc["recordable"])
    total = int(inc["total"])
    ratio = round(near_miss / recordable, 2) if recordable > 0 else None
    delta = (
        round(((near_miss - near_miss_prior) / near_miss_prior) * 100, 1)
        if near_miss_prior > 0 else None
    )

    ca_open = int(capa["open"])
    ca_overdue = int(capa["overdue"])
    ca_completed = int(capa["completed"])
    ca_total = int(capa["total"])
    close_rate = round(ca_completed / ca_total, 2) if ca_total > 0 else None
    avg_close = round(float(capa["avg_days_to_close"]), 1) if capa["avg_days_to_close"] is not None else None

    return LeadingIndicators(
        period_days=period_days,
        near_miss_count=near_miss,
        recordable_count=recordable,
        near_miss_to_recordable_ratio=ratio,
        near_miss_prior_count=near_miss_prior,
        near_miss_delta_pct=delta,
        total_incident_count=total,
        corrective_actions_open=ca_open,
        corrective_actions_overdue=ca_overdue,
        corrective_actions_completed=ca_completed,
        capa_close_rate=close_rate,
        avg_days_to_close=avg_close,
        generated_at=generated_at,
    )


@router.get("/analytics/risk-matrix", response_model=RiskMatrixResponse)
async def get_analytics_risk_matrix(
    days: int = Query(90, ge=7, le=365),
    location_id: Optional[UUID] = Query(None),
    current_user=Depends(require_admin_or_client),
):
    """SQL-driven Risk Matrix: locations × incident_type with deviation flags."""
    company_id = await get_client_company_id(current_user)
    generated_at_iso = _utc_now_naive().isoformat()
    if company_id is None:
        return RiskMatrixResponse(
            period_days=days, generated_at=generated_at_iso,
            company_total=0, location_count=0, rows=[],
        )

    start_date = _utc_now_naive() - timedelta(days=days)

    async with get_connection() as conn:
        # Optional location-scope check — if the caller filtered to a specific
        # location, ensure it belongs to their company before any query work.
        if location_id is not None:
            owns = await conn.fetchval(
                "SELECT 1 FROM business_locations WHERE id = $1 AND company_id = $2",
                location_id, company_id,
            )
            if not owns:
                raise HTTPException(status_code=404, detail="Location not found")

        loc_filter = "AND i.location_id = $3" if location_id else ""
        params: list = [company_id, start_date]
        if location_id:
            params.append(location_id)

        rows = await conn.fetch(
            f"""
            SELECT
                i.location_id,
                i.location AS legacy_location,
                bl.name AS bl_name,
                bl.city AS bl_city,
                bl.state AS bl_state,
                i.incident_type,
                COUNT(*) AS cnt,
                AVG(CASE
                    WHEN i.severity = 'critical' THEN 4
                    WHEN i.severity = 'high' THEN 3
                    WHEN i.severity = 'medium' THEN 2
                    ELSE 1
                END) AS severity_score
            FROM ir_incidents i
            LEFT JOIN business_locations bl ON bl.id = i.location_id
            WHERE i.company_id = $1
              AND i.occurred_at >= $2
              {loc_filter}
            GROUP BY i.location_id, i.location, bl.name, bl.city, bl.state, i.incident_type
            """,
            *params,
        )

    # Aggregate per (location_id-or-Unassigned) and per incident_type.
    per_location: dict = {}  # key: (loc_id_str_or_None, label) -> {totals, by_type}
    company_by_type: dict = {t: 0 for t in INCIDENT_TYPES_ORDER}
    company_total = 0

    for row in rows:
        loc_id = row["location_id"]
        if loc_id is None:
            # Legacy free-text fallback. Roll all NULL-location_id rows under
            # one synthesized bucket so the matrix stays compact.
            key = (None, UNASSIGNED_LOCATION_LABEL)
        else:
            label = (row["bl_name"] or "").strip()
            if not label:
                place = ", ".join([p for p in (row["bl_city"], row["bl_state"]) if p])
                label = place or str(loc_id)[:8]
            key = (str(loc_id), label)

        bucket = per_location.setdefault(key, {"total": 0, "by_type": {}})
        cnt = int(row["cnt"] or 0)
        itype = row["incident_type"] or "other"
        bucket["total"] += cnt
        # Multiple severity buckets can exist per type — aggregate weighted score.
        prev = bucket["by_type"].get(itype, {"count": 0, "score_sum": 0.0})
        prev["count"] += cnt
        prev["score_sum"] += float(row["severity_score"] or 0) * cnt
        bucket["by_type"][itype] = prev

        company_by_type[itype] = company_by_type.get(itype, 0) + cnt
        company_total += cnt

    # Baseline rates compare a single location to the average location. When the
    # caller has filtered to one location, the company total still includes only
    # that location's incidents (because of loc_filter) — so deviation in that
    # case is always 1.0 and the matrix reads as a single-location report.
    location_count = len(per_location) or 1

    matrix_rows: list[RiskMatrixRow] = []
    for (loc_id_str, label), info in sorted(per_location.items(), key=lambda kv: -kv[1]["total"]):
        cells: list[RiskMatrixCell] = []
        for itype in INCIDENT_TYPES_ORDER:
            agg = info["by_type"].get(itype, {"count": 0, "score_sum": 0.0})
            count = int(agg["count"])
            severity_score = round(agg["score_sum"] / count, 2) if count else 0.0
            company_count = company_by_type.get(itype, 0)
            baseline_rate = (company_count / location_count / days) if days > 0 else 0.0
            location_rate = (count / days) if days > 0 else 0.0
            deviation_ratio = (location_rate / baseline_rate) if baseline_rate > 0 else (0.0 if count == 0 else float("inf"))
            # Cap infinite ratios for JSON safety; a value > 999 is functionally "way above baseline".
            if deviation_ratio == float("inf") or deviation_ratio > 999.0:
                deviation_ratio = 999.0
            flagged = bool(deviation_ratio >= 2.0 and count >= 3)
            cells.append(RiskMatrixCell(
                incident_type=itype,
                count=count,
                severity_score=severity_score,
                baseline_rate=round(baseline_rate, 4),
                location_rate=round(location_rate, 4),
                deviation_ratio=round(deviation_ratio, 2),
                flagged=flagged,
            ))
        matrix_rows.append(RiskMatrixRow(
            location_id=UUID(loc_id_str) if loc_id_str else None,
            location_name=label,
            total_incidents=info["total"],
            cells=cells,
        ))

    return RiskMatrixResponse(
        period_days=days,
        generated_at=generated_at_iso,
        company_total=company_total,
        location_count=len(per_location),
        rows=matrix_rows,
    )


@router.get("/analytics/risk-insights", response_model=RiskInsightsResponse)
async def get_analytics_risk_insights(
    days: int = Query(30, ge=7, le=180),
    location_id: Optional[UUID] = Query(None),
    regenerate: bool = Query(False),
    current_user=Depends(require_admin_or_client),
):
    """Gemini-driven theme detection across recent IR corpus. 24h cache."""
    from app.matcha.services.ir_analysis import get_ir_analyzer

    company_id = await get_client_company_id(current_user)
    generated_at_iso = _utc_now_naive().isoformat()
    if company_id is None:
        return RiskInsightsResponse(
            period_days=days, generated_at=generated_at_iso,
            location_id=None, themes=[], from_cache=False,
        )

    scope_key = _build_risk_scope_key(location_id, days)
    start_date = _utc_now_naive() - timedelta(days=days)

    async with get_connection() as conn:
        if location_id is not None:
            owns = await conn.fetchval(
                "SELECT 1 FROM business_locations WHERE id = $1 AND company_id = $2",
                location_id, company_id,
            )
            if not owns:
                raise HTTPException(status_code=404, detail="Location not found")

        # Cache check (24h TTL) unless caller asked to regenerate.
        if not regenerate:
            cached = await conn.fetchrow(
                """
                SELECT analysis_data, generated_at FROM ir_company_analysis
                WHERE company_id = $1 AND analysis_type = 'risk_insights' AND scope_key = $2
                """,
                company_id, scope_key,
            )
            if cached:
                payload = _safe_json_loads(cached["analysis_data"])
                # Themes are cached 24h, but a *successful-but-empty* result is
                # usually Gemini variance (the model is non-deterministic — the
                # same corpus that yields 8 themes one run can yield 0 the next).
                # Pin empties for only 1h so an unlucky run self-heals on the
                # next load instead of showing "no patterns" for a whole day.
                ttl = timedelta(hours=1) if not payload.get("themes") else timedelta(hours=24)
                if (_utc_now_naive() - cached["generated_at"]) < ttl:
                    payload["from_cache"] = True
                    payload["generated_at"] = cached["generated_at"].isoformat()
                    return RiskInsightsResponse(**payload)

        # Pull the corpus. Cap at 200 most recent so the prompt stays focused.
        loc_clause = "AND i.location_id = $3" if location_id else ""
        params: list = [company_id, start_date]
        if location_id:
            params.append(location_id)

        incident_rows = await conn.fetch(
            f"""
            SELECT i.id, i.occurred_at, i.incident_type, i.severity, i.location_id,
                   i.description, i.root_cause, i.witnesses, i.involved_employee_ids,
                   i.er_case_id
            FROM ir_incidents i
            WHERE i.company_id = $1 AND i.occurred_at >= $2 {loc_clause}
            ORDER BY i.occurred_at DESC
            LIMIT 200
            """,
            *params,
        )

        # Locations registry — every active location for this company so themes
        # can attribute patterns by location name even if a location had zero
        # incidents in the window (Gemini picks from this registry).
        location_rows = await conn.fetch(
            """
            SELECT id, name, city, state
            FROM business_locations
            WHERE company_id = $1 AND is_active = true
            """,
            company_id,
        )
        location_lookup: dict[str, str] = {}
        for lr in location_rows:
            label = (lr["name"] or "").strip()
            if not label:
                place = ", ".join([p for p in (lr["city"], lr["state"]) if p])
                label = place or str(lr["id"])[:8]
            location_lookup[str(lr["id"])] = label

        # Employees registry — only when full-platform tenant has employees data.
        # Resolve names for IDs that appear in the corpus' involved_employee_ids;
        # if `employees` table is unreachable or empty for this tenant we just
        # pass None and the prompt degrades gracefully.
        employee_lookup: Optional[dict[str, str]] = None
        involved_ids: set[str] = set()
        for ir in incident_rows:
            for eid in (ir["involved_employee_ids"] or []):
                involved_ids.add(str(eid))
        if involved_ids:
            try:
                emp_rows = await conn.fetch(
                    """
                    SELECT id, first_name, last_name
                    FROM employees
                    WHERE org_id = $1 AND id = ANY($2::uuid[])
                    """,
                    company_id, list(involved_ids),
                )
                if emp_rows:
                    employee_lookup = {}
                    for er in emp_rows:
                        name = " ".join([s for s in (er["first_name"], er["last_name"]) if s]).strip()
                        employee_lookup[str(er["id"])] = name or str(er["id"])[:8]
            except Exception as e:
                # Cap tenants don't have employees populated; the table may exist
                # but the org_id filter returns empty. Don't fail the analysis.
                logger.info("[IR risk-insights] employees lookup skipped: %s", e)
                employee_lookup = None

        company_row = await conn.fetchrow(
            "SELECT name, industry FROM companies WHERE id = $1",
            company_id,
        )

    company_context = None
    if company_row:
        bits = [company_row["name"]]
        if company_row["industry"]:
            bits.append(f"Industry: {company_row['industry']}")
        company_context = " — ".join(bits)

    # Empty corpus short-circuit — don't burn a Gemini call.
    incidents_payload = [dict(r) for r in incident_rows]
    if not incidents_payload:
        empty = RiskInsightsResponse(
            period_days=days,
            generated_at=generated_at_iso,
            location_id=location_id,
            themes=[],
            from_cache=False,
        )
        async with get_connection() as conn:
            await conn.execute(
                """
                INSERT INTO ir_company_analysis (company_id, analysis_type, scope_key, analysis_data)
                VALUES ($1, 'risk_insights', $2, $3)
                ON CONFLICT (company_id, analysis_type, scope_key)
                DO UPDATE SET analysis_data = $3, generated_at = NOW()
                """,
                company_id, scope_key,
                json.dumps(empty.model_dump(mode="json"), default=str),
            )
        return empty

    analyzer = get_ir_analyzer()
    gemini_failed = False
    try:
        themes_result = await analyzer.detect_risk_themes(
            incidents=incidents_payload,
            location_lookup=location_lookup,
            employee_lookup=employee_lookup,
            company_context=company_context,
        )
    except Exception as e:
        logger.warning("[IR risk-insights] Gemini theme detection failed: %s", e)
        themes_result = {"themes": []}
        gemini_failed = True

    themes: list[RiskTheme] = []
    for t in themes_result.get("themes", []):
        loc_id_str = t.get("location_id")
        loc_name = location_lookup.get(loc_id_str) if loc_id_str else None
        try:
            themes.append(RiskTheme(
                label=t["label"],
                severity=t["severity"],
                location_id=UUID(loc_id_str) if loc_id_str else None,
                location_name=loc_name,
                incident_count=int(t["incident_count"]),
                evidence_incident_ids=[UUID(eid) for eid in t.get("evidence_incident_ids", [])],
                insight=t["insight"],
                recommendation=t["recommendation"],
            ))
        except (KeyError, ValueError, TypeError) as e:
            # Skip malformed theme rather than 500 the whole response.
            logger.info("[IR risk-insights] dropping malformed theme: %s", e)

    response = RiskInsightsResponse(
        period_days=days,
        generated_at=generated_at_iso,
        location_id=location_id,
        themes=themes,
        from_cache=False,
    )

    # Only cache on success. A Gemini outage shouldn't pin "no themes" for 24h.
    if not gemini_failed:
        async with get_connection() as conn:
            await conn.execute(
                """
                INSERT INTO ir_company_analysis (company_id, analysis_type, scope_key, analysis_data)
                VALUES ($1, 'risk_insights', $2, $3)
                ON CONFLICT (company_id, analysis_type, scope_key)
                DO UPDATE SET analysis_data = $3, generated_at = NOW()
                """,
                company_id, scope_key,
                json.dumps(response.model_dump(mode="json"), default=str),
            )

    return response


@router.get("/analytics/consistency", response_model=ConsistencyAnalytics)
async def get_analytics_consistency(
    request: Request,
    current_user=Depends(require_admin_or_client),
):
    """Get company-wide consistency analytics across all resolved incidents."""
    from app.matcha.services.ir_consistency import compute_consistency_analytics

    company_id = await get_client_company_id(current_user)
    if company_id is None:
        return ConsistencyAnalytics(
            total_resolved=0, total_with_actions=0,
            action_distribution=[], by_incident_type=[], by_severity=[],
            avg_resolution_by_action={}, generated_at=_utc_now_naive().isoformat(),
        )

    async with get_connection() as conn:
        # Fetch all resolved/closed incidents
        rows = await conn.fetch(
            """
            SELECT id, incident_type, severity, corrective_actions,
                   occurred_at, resolved_at
            FROM ir_incidents
            WHERE company_id = $1 AND status IN ('resolved', 'closed')
            ORDER BY resolved_at DESC
            """,
            company_id,
        )

        if not rows:
            return ConsistencyAnalytics(
                total_resolved=0, total_with_actions=0,
                action_distribution=[], by_incident_type=[], by_severity=[],
                avg_resolution_by_action={}, generated_at=_utc_now_naive().isoformat(),
            )

        # Use the most recently resolved incident as cache anchor for writes
        anchor_id = str(rows[0]["id"])

        # Check for cached result (<24h) anywhere in the company (not just anchor)
        cached = await conn.fetchrow(
            """
            SELECT a.analysis_data, a.generated_at FROM ir_incident_analysis a
            JOIN ir_incidents i ON i.id = a.incident_id
            WHERE i.company_id = $1 AND a.analysis_type = 'company_consistency'
            ORDER BY a.generated_at DESC LIMIT 1
            """,
            company_id,
        )

        if cached:
            cache_age = _utc_now_naive() - cached["generated_at"]
            if cache_age < timedelta(hours=24):
                result = _safe_json_loads(cached["analysis_data"])
                result["from_cache"] = True
                return ConsistencyAnalytics(**result)

        incidents = [dict(r) for r in rows]

        settings = get_settings()
        try:
            result = await compute_consistency_analytics(
                incidents,
                api_key=settings.gemini_api_key,
            )
        except Exception as e:
            logger.warning(f"Consistency analytics computation failed: {e}")
            return ConsistencyAnalytics(
                total_resolved=len(incidents),
                total_with_actions=len([i for i in incidents if i.get("corrective_actions")]),
                action_distribution=[], by_incident_type=[], by_severity=[],
                avg_resolution_by_action={}, generated_at=_utc_now_naive().isoformat(),
            )

        # Cache on the anchor incident
        await conn.execute(
            """
            INSERT INTO ir_incident_analysis (incident_id, analysis_type, analysis_data)
            VALUES ($1, 'company_consistency', $2)
            ON CONFLICT (incident_id, analysis_type)
            DO UPDATE SET analysis_data = $2, generated_at = now()
            """,
            anchor_id,
            json.dumps(result, default=str),
        )

        return ConsistencyAnalytics(**result)
