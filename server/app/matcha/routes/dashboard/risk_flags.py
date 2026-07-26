"""Flags & Actions — AI-synthesized risk analysis."""
import asyncio as _asyncio
import json as _json
import logging
import re as _loc_re_mod
from datetime import datetime, timezone
from uuid import UUID

import asyncpg
from fastapi import APIRouter, Depends

from app.database import get_connection
from app.matcha.dependencies import require_admin_or_client, get_client_company_id
from app.core.models.auth import CurrentUser
from app.matcha.models.dashboard import (
    WageGapDetailsResponse,
    EmployeeWageGapDetail,
    RoleRollupItem,
    DashboardFlag,
    HeatMapCell,
    BusinessLocationSummary,
    DashboardFlagsResponse,
)

logger = logging.getLogger(__name__)

router = APIRouter()

_SEVERITY_ORDER = {"critical": 0, "high": 1, "medium": 2, "low": 3, "warning": 1, "info": 3}

_RISK_ANALYSIS_PROMPT = """You are a senior HR risk analyst. Below are aggregated risk patterns detected across a company's HR data. Analyze these patterns and produce a prioritized list of actionable flags.

For each flag, provide:
- A specific, concrete description (not generic)
- A plain-English recommendation of exactly what to do
- A severity rating (critical/high/medium/low)
- A category (Compliance, Safety, HR Policy / Legal, Workforce Risk)
- A source_type (pattern, compliance, incident, er_case, wage, policy)
- A link to the relevant page (use /app/ir for incidents, /app/er-copilot for ER cases, /app/compliance for compliance, /app/employees for wage issues, /app/handbooks for policies)

Rules:
- Only surface items that require ACTION — skip informational items
- Connect related patterns (e.g., same department appearing in incidents AND ER cases)
- Do NOT create wage / minimum-wage / exempt-salary flags — those are computed deterministically with exact counts and added automatically. You may reference wage exposure when connecting related patterns, but never emit it as its own flag.
- For trend-based findings, cite the specific timeframe and counts
- Maximum 15 flags — prioritize ruthlessly
- Be specific: name locations, departments, and roles (but not individual employee names in descriptions — use role titles like "Exempt Employee at [Location]")
- If there are no meaningful patterns or issues, return an empty flags array

PATTERNS:
{patterns}

Return ONLY valid JSON with this exact structure:
{{"flags": [{{"priority": 1, "category": "...", "location_subject": "...", "description": "...", "recommendation": "...", "severity": "critical", "source_type": "pattern", "link": "/app/..."}}]}}"""


async def _detect_risk_patterns(company_id: UUID) -> dict:
    """Gather aggregated risk patterns from the database. Returns structured facts, not raw records."""
    patterns: dict = {}

    async with get_connection() as conn:
        # 1. Incidents by location (last 90 days)
        try:
            loc_rows = await conn.fetch(
                """SELECT COALESCE(bl.name, CONCAT(bl.city, ', ', bl.state), i.location, 'Unspecified') AS loc_name,
                          i.severity, COUNT(*) AS cnt
                   FROM ir_incidents i
                   LEFT JOIN business_locations bl ON bl.id = i.location_id
                   WHERE i.company_id = $1 AND i.occurred_at > NOW() - INTERVAL '90 days'
                   GROUP BY loc_name, i.severity
                   ORDER BY cnt DESC
                   LIMIT 20""",
                company_id,
            )
            if loc_rows:
                patterns["incidents_by_location"] = [
                    {"location": r["loc_name"] or "Unspecified", "severity": r["severity"], "count": r["cnt"]}
                    for r in loc_rows
                ]
        except Exception:
            pass

        # 2. Incidents by type (last 90 days)
        try:
            type_rows = await conn.fetch(
                """SELECT incident_type, severity, COUNT(*) AS cnt
                   FROM ir_incidents
                   WHERE company_id = $1 AND occurred_at > NOW() - INTERVAL '90 days'
                     AND status IN ('reported', 'investigating', 'action_required')
                   GROUP BY incident_type, severity
                   ORDER BY cnt DESC""",
                company_id,
            )
            if type_rows:
                patterns["open_incidents_by_type"] = [
                    {"type": r["incident_type"], "severity": r["severity"], "count": r["cnt"]}
                    for r in type_rows
                ]
        except Exception:
            pass

        # 3. Recent incident spike detection (30-day vs prior 60 days)
        try:
            recent_30 = await conn.fetchval(
                "SELECT COUNT(*) FROM ir_incidents WHERE company_id = $1 AND occurred_at > NOW() - INTERVAL '30 days'",
                company_id,
            ) or 0
            prior_60 = await conn.fetchval(
                """SELECT COUNT(*) FROM ir_incidents
                   WHERE company_id = $1
                     AND occurred_at > NOW() - INTERVAL '90 days'
                     AND occurred_at <= NOW() - INTERVAL '30 days'""",
                company_id,
            ) or 0
            avg_monthly_prior = prior_60 / 2 if prior_60 > 0 else 0
            if recent_30 > 0:
                patterns["incident_trend"] = {
                    "last_30_days": recent_30,
                    "avg_monthly_prior_60_days": round(avg_monthly_prior, 1),
                    "spike": recent_30 > avg_monthly_prior * 1.5 if avg_monthly_prior > 0 else False,
                }
        except Exception:
            pass

        # 4. ER cases by category
        try:
            er_rows = await conn.fetch(
                """SELECT category, status, COUNT(*) AS cnt
                   FROM er_cases
                   WHERE company_id = $1 AND status NOT IN ('closed', 'resolved')
                   GROUP BY category, status
                   ORDER BY cnt DESC""",
                company_id,
            )
            if er_rows:
                patterns["open_er_cases"] = [
                    {"category": r["category"] or "uncategorized", "status": r["status"], "count": r["cnt"]}
                    for r in er_rows
                ]
        except Exception:
            pass

        # 5. Compliance alerts (critical/warning unactioned)
        try:
            comp_rows = await conn.fetch(
                """SELECT ca.severity, ca.title, ca.category, bl.city, bl.state, COUNT(*) AS cnt
                   FROM compliance_alerts ca
                   LEFT JOIN business_locations bl ON ca.location_id = bl.id
                   WHERE ca.company_id = $1 AND ca.status NOT IN ('dismissed', 'actioned')
                     AND COALESCE(ca.confidence_score, 1.0) >= 0.6
                   GROUP BY ca.severity, ca.title, ca.category, bl.city, bl.state
                   ORDER BY CASE ca.severity WHEN 'critical' THEN 0 WHEN 'warning' THEN 1 ELSE 2 END
                   LIMIT 30""",
                company_id,
            )
            if comp_rows:
                patterns["compliance_alerts"] = [
                    {
                        "severity": r["severity"],
                        "title": r["title"],
                        "category": r["category"],
                        "location": f"{r['city']}, {r['state']}" if r.get("city") else (r.get("state") or "Company-wide"),
                        "count": r["cnt"],
                    }
                    for r in comp_rows
                ]
        except Exception:
            pass

        # 6. Wage violations — delegate to the same per-location impact
        #    calculator that powers /stats.wage_alerts and the risk assessment
        #    page. Previous version had `e.location_id` (wrong column — real
        #    FK is `work_location_id`) and a hardcoded CA-only threshold, so
        #    the query silently errored out and no wage flags ever appeared.
        try:
            from app.core.services.compliance_service import get_employee_impact_for_location

            location_rows = await conn.fetch(
                "SELECT id, city, state FROM business_locations WHERE company_id = $1 AND is_active = true",
                company_id,
            )
            violations: list[dict] = []
            for loc in location_rows:
                impact = await get_employee_impact_for_location(loc["id"], company_id)
                vbt = impact.get("violations_by_rate_type", {}) or {}
                for rate_type, items in vbt.items():
                    for v in items:
                        violations.append({
                            "employee_id": v.get("employee_id"),
                            "employee_name": v.get("employee_name") or "Employee",
                            "pay_classification": v.get("pay_classification") or rate_type,
                            "salary": float(v.get("pay_rate") or 0),
                            "minimum": float(v.get("threshold") or 0),
                            "shortfall": float(v.get("shortfall") or 0),
                            "state": (loc.get("state") or "").upper(),
                            "location": f"{loc.get('city') or ''}, {loc.get('state') or ''}".strip(", "),
                            "rate_type": rate_type,
                        })
            if violations:
                patterns["wage_violations"] = violations
                # Summary stats (deduped by employee, matching the Risk
                # Assessment module) so the AI sees an explicit total and the
                # deterministic rollup flag can report the true count.
                unique_ids = {v.get("employee_id") for v in violations if v.get("employee_id")}
                hourly_ids = {
                    v.get("employee_id") for v in violations
                    if (v.get("rate_type") == "general" or v.get("pay_classification") == "hourly")
                    and v.get("employee_id")
                }
                salary_ids = {
                    v.get("employee_id") for v in violations
                    if (v.get("rate_type") == "exempt_salary" or v.get("pay_classification") == "exempt")
                    and v.get("employee_id")
                }
                patterns["wage_violations_summary"] = {
                    "total_employees": len(unique_ids) or len(violations),
                    "hourly_count": len(hourly_ids),
                    "salary_count": len(salary_ids),
                    "locations_affected": len(
                        {v.get("location") for v in violations if v.get("location")}
                    ),
                }
        except Exception:
            logger.exception("Failed to compute wage violations for dashboard flags")

        # 7. Stale policies
        try:
            stale_rows = await conn.fetch(
                """SELECT title, EXTRACT(DAY FROM NOW() - updated_at)::int AS days_stale
                   FROM policies
                   WHERE company_id = $1 AND status = 'active'
                     AND updated_at < NOW() - INTERVAL '180 days'
                   ORDER BY updated_at ASC
                   LIMIT 10""",
                company_id,
            )
            if stale_rows:
                patterns["stale_policies"] = [
                    {"title": r["title"] or "Untitled", "days_stale": r["days_stale"] or 0}
                    for r in stale_rows
                ]
        except Exception:
            pass

        # 8. Department risk concentration
        try:
            dept_rows = await conn.fetch(
                """SELECT e.department, COUNT(DISTINCT i.id) AS incident_count
                   FROM ir_incidents i, UNNEST(i.involved_employee_ids) AS eid
                   JOIN employees e ON e.id = eid
                   WHERE i.company_id = $1 AND i.occurred_at > NOW() - INTERVAL '90 days'
                     AND e.department IS NOT NULL
                   GROUP BY e.department
                   HAVING COUNT(DISTINCT i.id) >= 2
                   ORDER BY incident_count DESC
                   LIMIT 5""",
                company_id,
            )
            if dept_rows:
                patterns["departments_with_multiple_incidents"] = [
                    {"department": r["department"], "incident_count": r["incident_count"]}
                    for r in dept_rows
                ]
        except Exception:
            pass

    return patterns


async def _analyze_with_ai(patterns: dict) -> list[dict] | None:
    """Call Gemini to synthesize risk patterns into prioritized flags."""
    if not patterns:
        return []

    try:
        import google.genai as genai
        from app.core.services.genai_client import get_genai_client
        from app.config import get_settings
        settings = get_settings()

        api_key = settings.gemini_api_key
        if not api_key:
            return None

        client = get_genai_client(api_key=api_key)
        prompt = _RISK_ANALYSIS_PROMPT.format(patterns=_json.dumps(patterns, default=str))

        response = await _asyncio.to_thread(
            lambda: client.models.generate_content(
                model="gemini-3-flash-preview",
                contents=prompt,
                config=genai.types.GenerateContentConfig(
                    temperature=0.2,
                    response_mime_type="application/json",
                ),
            )
        )

        raw = response.text or ""
        # Clean markdown fences
        import re as _re
        raw = _re.sub(r"^```(?:json)?\s*", "", raw.strip())
        raw = _re.sub(r"\s*```$", "", raw.strip())

        parsed = _json.loads(raw)
        return parsed.get("flags", [])
    except Exception:
        logger.warning("AI risk analysis failed, falling back to deterministic flags", exc_info=True)
        return None


def _deterministic_flags_from_patterns(patterns: dict) -> list[dict]:
    """Build basic flags from patterns without AI — used as fallback."""
    flags: list[dict] = []

    for v in patterns.get("wage_violations", []):
        name = v.get("employee_name") or "Employee"
        salary = float(v.get("salary") or 0)
        minimum = float(v.get("minimum") or 0)
        state = v.get("state") or ""
        classification = v.get("pay_classification") or ""
        is_exempt = classification == "exempt" or v.get("rate_type") == "exempt_salary"
        label = "exempt minimum salary" if is_exempt else "minimum wage"
        salary_str = f"${salary:,.0f}" if is_exempt else f"${salary:,.2f}/hr"
        minimum_str = f"${minimum:,.0f}" if is_exempt else f"${minimum:,.2f}/hr"
        flags.append({
            "category": "Compliance",
            "location_subject": v.get("location") or state or "Company-wide",
            "description": f"{name} is paid {salary_str} but the {state} {label} is {minimum_str}.",
            "recommendation": (
                f"Raise {name}'s salary to {minimum_str} or reclassify as non-exempt."
                if is_exempt
                else f"Raise {name}'s hourly rate to {minimum_str}."
            ),
            "severity": "critical",
            "source_type": "wage",
            "link": "/app/employees",
        })

    for a in patterns.get("compliance_alerts", []):
        if a["severity"] == "critical":
            flags.append({
                "category": "Compliance",
                "location_subject": a.get("location") or "Company-wide",
                "description": a["title"],
                "recommendation": "Review and address this compliance requirement immediately.",
                "severity": "critical",
                "source_type": "compliance",
                "link": "/app/compliance",
            })

    for inc in patterns.get("open_incidents_by_type", []):
        if inc["severity"] in ("critical", "high"):
            flags.append({
                "category": "Safety",
                "location_subject": inc["type"].replace("_", " ").title(),
                "description": f"{inc['count']} open {inc['severity']} {inc['type'].replace('_', ' ')} incident(s) in last 90 days.",
                "recommendation": "Investigate and resolve open incidents. Consider re-training.",
                "severity": inc["severity"],
                "source_type": "incident",
                "link": "/app/ir",
            })

    for er in patterns.get("open_er_cases", []):
        flags.append({
            "category": "HR Policy / Legal",
            "location_subject": (er["category"] or "ER Case").replace("_", " ").title(),
            "description": f"{er['count']} open {er['category'].replace('_', ' ')} case(s).",
            "recommendation": "Investigate and resolve per company policy.",
            "severity": "high",
            "source_type": "er_case",
            "link": "/app/er-copilot",
        })

    for p in patterns.get("stale_policies", []):
        flags.append({
            "category": "HR Policy / Legal",
            "location_subject": p["title"],
            "description": f"Policy not updated in {p['days_stale']} days.",
            "recommendation": "Review and update policy.",
            "severity": "medium",
            "source_type": "policy",
            "link": "/app/handbooks",
        })

    flags.sort(key=lambda f: _SEVERITY_ORDER.get(f["severity"], 99))
    return flags


def _wage_rollup_flag(patterns: dict) -> dict | None:
    """Single wage-violation flag carrying the TRUE total.

    The AI summarizer collapses many wage violations into a vague "two
    employees" mention, undercounting vs the Risk Assessment module (which
    counts every underpaid employee). This builds one deterministic flag from
    the full violation list so the Command Center count always matches Risk
    Assessment.
    """
    violations = patterns.get("wage_violations") or []
    if not violations:
        return None

    summary = patterns.get("wage_violations_summary") or {}
    unique_ids = {v.get("employee_id") for v in violations if v.get("employee_id")}
    total = summary.get("total_employees") or len(unique_ids) or len(violations)
    hourly_n = summary.get("hourly_count") or 0
    salary_n = summary.get("salary_count") or 0
    locs = summary.get("locations_affected") or len(
        {v.get("location") for v in violations if v.get("location")}
    )

    parts: list[str] = []
    if salary_n:
        parts.append(f"{salary_n} exempt below the salary threshold")
    if hourly_n:
        parts.append(f"{hourly_n} hourly below minimum wage")
    breakdown = "; ".join(parts) if parts else "below the applicable minimum"
    loc_label = f"{locs} location{'s' if locs != 1 else ''}"

    return {
        "category": "Compliance",
        "location_subject": "Company Wide",
        "description": (
            f"{total} employee{'s' if total != 1 else ''} across {loc_label} "
            f"are paid below the applicable minimum ({breakdown}). This is "
            f"documented wage-and-hour exposure under the FLSA and state wage orders."
        ),
        "recommendation": (
            "Open the wage-compliance review on the Employees page, raise each "
            "underpaid employee to the applicable minimum (or reclassify exempt "
            "staff as non-exempt), and record the remediation date for each."
        ),
        "severity": "critical",
        "source_type": "wage",
        "link": "/app/employees",
    }


def _apply_wage_rollup(raw_flags: list[dict], patterns: dict) -> list[dict]:
    """Drop any wage flags and prepend one deterministic rollup.

    Used on every write path (AI + deterministic + auto-rebuild) so the
    Command Center wage count always matches the Risk Assessment total
    instead of whatever subset the AI happened to mention.
    """
    flags = [f for f in raw_flags if f.get("source_type") != "wage"]
    wage_flag = _wage_rollup_flag(patterns)
    if wage_flag:
        flags.insert(0, wage_flag)
    return flags


_LOC_PATTERN = _loc_re_mod.compile(r',\s*[A-Z]{2}')


def _classify_location(name: str, dept_names: set[str] | None = None) -> str:
    """Classify a location_subject into Locations / Departments / Company-wide."""
    if name.lower() in ("company-wide", "company wide"):
        return "Company-wide"
    if dept_names and name in dept_names:
        return "Departments"
    if _LOC_PATTERN.search(name):
        return "Locations"
    return "Locations"


async def _write_flags_to_db(
    company_id: UUID, raw_flags: list[dict], is_ai: bool, dept_names: set[str] | None = None,
) -> int:
    """Delete existing flags and write new ones. Returns count written."""
    now = datetime.now(timezone.utc)
    async with get_connection() as conn:
        async with conn.transaction():
            await conn.execute("DELETE FROM mw_risk_flags WHERE company_id = $1", company_id)
            for i, f in enumerate(raw_flags):
                loc_subj = f.get("location_subject", "")
                await conn.execute(
                    """INSERT INTO mw_risk_flags
                       (company_id, priority, category, location_subject, description,
                        recommendation, severity, source_type, source_id, link,
                        group_label, is_ai_generated, analyzed_at)
                       VALUES ($1,$2,$3,$4,$5,$6,$7,$8,$9,$10,$11,$12,$13)""",
                    company_id, i + 1,
                    f.get("category", ""),
                    loc_subj,
                    f.get("description", ""),
                    f.get("recommendation", ""),
                    f.get("severity", "medium"),
                    f.get("source_type", "pattern"),
                    f.get("source_id"),
                    f.get("link"),
                    _classify_location(loc_subj, dept_names),
                    is_ai,
                    now,
                )
    return len(raw_flags)


async def rebuild_flags_deterministic(company_id: UUID) -> int:
    """Rebuild mw_risk_flags from current data. No AI — fast deterministic scan.

    Call this whenever data changes (incident created, ER case opened, etc.)
    or when the flags table is empty for a company.
    """
    patterns = await _detect_risk_patterns(company_id)
    raw_flags = _apply_wage_rollup(_deterministic_flags_from_patterns(patterns), patterns)
    dept_names = {d["department"] for d in patterns.get("departments_with_multiple_incidents", [])}
    return await _write_flags_to_db(company_id, raw_flags, is_ai=False, dept_names=dept_names)


@router.get("/wage-gap/details", response_model=WageGapDetailsResponse)
async def get_wage_gap_details(
    current_user: CurrentUser = Depends(require_admin_or_client),
):
    """Per-employee + per-role wage-gap breakdown for the drill-down drawer.

    The summary widget surfaces totals; this endpoint surfaces the rows
    the operator can actually act on (name, current pay, target pay,
    annualized raise cost, flight-risk tier).
    """
    company_id = await get_client_company_id(current_user)
    if company_id is None:
        return WageGapDetailsResponse(employees=[], role_rollups=[])

    try:
        from app.matcha.services.workforce.wage_benchmark_service import compute_employee_wage_gaps
        gaps, rollups = await compute_employee_wage_gaps(company_id)
    except asyncpg.UndefinedTableError:
        return WageGapDetailsResponse(employees=[], role_rollups=[])

    return WageGapDetailsResponse(
        employees=[EmployeeWageGapDetail(**g.__dict__) for g in gaps],
        role_rollups=[RoleRollupItem(**r.__dict__) for r in rollups],
    )


@router.get("/wage-gap/export.csv")
async def export_wage_gap_csv(
    current_user: CurrentUser = Depends(require_admin_or_client),
):
    """CSV export so the operator can share a raise plan with payroll/finance.

    Columns match what payroll needs to actually process a pay adjustment:
    employee, title, location, current rate, target rate (p50), $/hr raise,
    annualized cost. No projections, no benchmarks they can't verify.
    """
    import csv
    import io
    from fastapi.responses import Response

    company_id = await get_client_company_id(current_user)
    if company_id is None:
        return Response(content="", media_type="text/csv")

    try:
        from app.matcha.services.workforce.wage_benchmark_service import compute_employee_wage_gaps
        gaps, _ = await compute_employee_wage_gaps(company_id)
    except asyncpg.UndefinedTableError:
        gaps = []

    buf = io.StringIO()
    writer = csv.writer(buf)
    writer.writerow([
        "employee_id", "name", "job_title", "soc_label",
        "work_city", "work_state",
        "current_pay_rate", "market_p25", "market_p50", "market_p75",
        "delta_$/hr", "delta_%",
        "raise_to_p25_annual_cost", "raise_to_p50_annual_cost",
        "benchmark_tier", "benchmark_area", "flight_risk_tier",
    ])
    for g in gaps:
        writer.writerow([
            g.employee_id, g.name, g.job_title or "", g.soc_label,
            g.work_city or "", g.work_state or "",
            f"{g.pay_rate:.2f}",
            f"{g.market_p25:.2f}" if g.market_p25 else "",
            f"{g.market_p50:.2f}",
            f"{g.market_p75:.2f}" if g.market_p75 else "",
            f"{g.delta_dollars_per_hour:.2f}",
            f"{g.delta_percent:.3f}",
            g.annual_cost_to_reach_p25,
            g.annual_cost_to_reach_p50,
            g.benchmark_tier, g.benchmark_area, g.flight_risk_tier,
        ])

    return Response(
        content=buf.getvalue(),
        media_type="text/csv",
        headers={"Content-Disposition": 'attachment; filename="wage-gap.csv"'},
    )


@router.get("/flags", response_model=DashboardFlagsResponse)
async def get_dashboard_flags(
    current_user: CurrentUser = Depends(require_admin_or_client),
):
    """Read pre-computed risk flags from the database. Auto-populates if empty."""
    company_id = await get_client_company_id(current_user)
    if company_id is None:
        return DashboardFlagsResponse(total_flags=0, critical_count=0, flags=[])

    async with get_connection() as conn:
        # Detect stale: any incident or ER case mutated after the last
        # analyze, OR the table is empty. mw_risk_flags is cheap to
        # rebuild (deterministic SQL, no AI), so we eat the cost on read.
        stale_row = await conn.fetchrow(
            """
            WITH last_analyze AS (
                SELECT MAX(analyzed_at) AS analyzed_at,
                       COUNT(*) AS flag_count
                FROM mw_risk_flags
                WHERE company_id = $1
            ),
            last_incident AS (
                SELECT GREATEST(MAX(created_at), MAX(updated_at)) AS touched_at
                FROM ir_incidents
                WHERE company_id = $1
            )
            SELECT
                la.flag_count,
                la.analyzed_at,
                li.touched_at,
                CASE
                    WHEN la.flag_count = 0 THEN true
                    WHEN la.analyzed_at IS NULL THEN true
                    WHEN li.touched_at IS NOT NULL AND li.touched_at > la.analyzed_at THEN true
                    ELSE false
                END AS is_stale
            FROM last_analyze la, last_incident li
            """,
            company_id,
        )
        is_stale = bool(stale_row and stale_row["is_stale"])

    if is_stale:
        await rebuild_flags_deterministic(company_id)

    async with get_connection() as conn:
        rows = await conn.fetch(
            """SELECT id, priority, category, location_subject, description, recommendation,
                      severity, source_type, source_id, link, group_label, is_ai_generated, analyzed_at
               FROM mw_risk_flags
               WHERE company_id = $1
               ORDER BY priority""",
            company_id,
        )
        analyzed_at_val = rows[0]["analyzed_at"] if rows else None

        loc_rows = await conn.fetch(
            """SELECT id::text,
                      COALESCE(name, CONCAT(city, ', ', state)) AS display_name,
                      COALESCE(city, '') AS city,
                      COALESCE(state, '') AS state
               FROM business_locations
               WHERE company_id = $1 AND is_active = true
               ORDER BY state, city""",
            company_id,
        )

    flags = [
        DashboardFlag(
            priority=r["priority"],
            category=r["category"],
            location_subject=r["location_subject"],
            description=r["description"],
            recommendation=r["recommendation"],
            severity=r["severity"],
            source_type=r["source_type"],
            source_id=r["source_id"],
            link=r["link"],
        )
        for r in rows
    ]
    critical_count = sum(1 for f in flags if f.severity == "critical")

    # Build heat map from stored flags
    heat_cells: dict[tuple[str, str], dict] = {}
    for r in rows:
        loc = r["location_subject"] or "Unknown"
        cat = r["category"] or "Other"
        grp = r["group_label"] or _classify_location(loc)
        key = (loc, cat)
        cell = heat_cells.get(key)
        if cell:
            cell["count"] += 1
            if _SEVERITY_ORDER.get(r["severity"], 99) < _SEVERITY_ORDER.get(cell["worst"], 99):
                cell["worst"] = r["severity"]
        else:
            heat_cells[key] = {"count": 1, "worst": r["severity"], "group": grp}

    heat_map = [
        HeatMapCell(location=loc, category=cat, count=v["count"], worst_severity=v["worst"], group=v["group"])
        for (loc, cat), v in heat_cells.items()
    ]

    all_locations = [
        BusinessLocationSummary(id=r["id"], name=r["display_name"], city=r["city"], state=r["state"])
        for r in loc_rows
    ]

    return DashboardFlagsResponse(
        total_flags=len(flags),
        critical_count=critical_count,
        flags=flags,
        heat_map=heat_map,
        locations=all_locations,
        analyzed_at=analyzed_at_val,
    )


@router.post("/flags/analyze")
async def analyze_risk_flags(
    current_user: CurrentUser = Depends(require_admin_or_client),
):
    """Re-analyze with AI: detect patterns, call Gemini for better recommendations, store results."""
    company_id = await get_client_company_id(current_user)
    if company_id is None:
        return {"analyzed": 0}

    patterns = await _detect_risk_patterns(company_id)
    dept_names = {d["department"] for d in patterns.get("departments_with_multiple_incidents", [])}

    # Try AI synthesis, fall back to deterministic.
    ai_flags = await _analyze_with_ai(patterns)
    is_ai = ai_flags is not None
    raw_flags = ai_flags if is_ai else _deterministic_flags_from_patterns(patterns)
    # AI collapses/undercounts wage violations — always inject the deterministic
    # rollup so the count matches the Risk Assessment total.
    raw_flags = _apply_wage_rollup(raw_flags, patterns)
    count = await _write_flags_to_db(company_id, raw_flags, is_ai=is_ai, dept_names=dept_names)
    return {"analyzed": count, "is_ai": is_ai}
