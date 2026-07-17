"""New-hire jurisdiction packet — the codified obligations owed when someone is
hired in a given state.

On hire (especially a hire in a state the company has never operated in), the
employer owes a bundle of jurisdiction-specific notices/registrations: I-9 /
E-Verify, wage/paystub disclosures, sick-leave notice, background-check
disclosure, workers'-comp notice. Rather than store per-hire rows (employees
arrive via Finch sync, CSV import, or manual add — three ingress paths), the
packet is DERIVED at read time from `employees.work_state`, so every ingress
path gets it for free and nothing drifts.

Same guard set as the schedule/IR grounding reads: codified-gated,
`_filter_requirements_for_company` applied (raw catalog query bypasses the tenant
projection), degrade to empty on failure, optional `conn=`.
"""

from __future__ import annotations

import logging
from typing import Any, Optional
from uuid import UUID

logger = logging.getLogger(__name__)

# Codified catalog categories that represent a new-hire obligation. Every slug is
# verified present in CATEGORY_KEYS (i9_everify, pay_frequency, final_pay,
# sick_leave, background_checks, workers_comp). `new_hire_reporting`/`wage_theft`
# are NOT catalog category slugs — those obligations surface under pay_frequency /
# background_checks prose.
NOTICE_CATEGORIES = [
    "i9_everify", "pay_frequency", "final_pay",
    "sick_leave", "background_checks", "workers_comp",
]


def bucket_for_level(level: Optional[str]) -> str:
    """Map a jurisdiction level to a packet group. county/city → local."""
    lv = (level or "").strip().lower()
    if lv == "federal":
        return "federal"
    if lv in ("county", "city"):
        return "local"
    return "state"


async def _resolve_state(conn, company_id: UUID, employee_id: UUID) -> Optional[str]:
    row = await conn.fetchrow(
        """
        SELECT e.work_state, bl.state AS loc_state
        FROM employees e
        LEFT JOIN business_locations bl ON bl.id = e.work_location_id
        WHERE e.id = $1 AND e.org_id = $2
        """,
        employee_id, company_id,
    )
    if not row:
        return None
    return (row["work_state"] or row["loc_state"] or None)


async def build_packet(conn, company_id, employee_id) -> dict[str, Any]:
    """Grouped new-hire notices for an employee's work state (+ federal).

    Returns ``{employee_id, state, notices: {federal, state, local}, count}``.
    Empty groups when the state has no codified notice rows — never raises."""
    try:
        comp = company_id if isinstance(company_id, UUID) else UUID(str(company_id))
        emp = employee_id if isinstance(employee_id, UUID) else UUID(str(employee_id))
    except (ValueError, TypeError):
        return {"employee_id": str(employee_id), "state": None,
                "notices": {"federal": [], "state": [], "local": []}, "count": 0}

    empty = {"employee_id": str(emp), "state": None,
             "notices": {"federal": [], "state": [], "local": []}, "count": 0}
    try:
        state = await _resolve_state(conn, comp, emp)
        if not state:
            return empty
        state = state.strip().upper()

        from app.core.services.compliance_service import (
            codified_gate_sql, _filter_requirements_for_company,
        )
        gate = await codified_gate_sql("jr", conn=conn)
        rows = await conn.fetch(
            f"""
            SELECT jr.id, j.state, j.level::text AS authority_level,
                   j.display_name AS authority_name, jr.category, jr.title,
                   jr.description, jr.statute_citation, jr.source_url,
                   jr.applicable_industries
            FROM jurisdiction_requirements jr
            JOIN jurisdictions j ON j.id = jr.jurisdiction_id
            WHERE j.state = ANY($1::varchar[])
              AND jr.status = 'active'
              AND (jr.expiration_date IS NULL OR jr.expiration_date >= CURRENT_DATE)
              AND jr.category = ANY($2::varchar[])
              {gate}
            ORDER BY (j.state = 'US') ASC, jr.category
            LIMIT 80
            """,
            sorted({state, "US"}),
            list(NOTICE_CATEGORIES),
        )
        filtered = await _filter_requirements_for_company(conn, comp, [dict(r) for r in rows])
    except Exception:
        logger.exception("new_hire_packet: build failed for employee %s", employee_id)
        return empty

    groups: dict[str, list[dict]] = {"federal": [], "state": [], "local": []}
    for r in filtered:
        bucket = bucket_for_level(r.get("authority_level"))
        groups[bucket].append({
            "requirement_id": str(r["id"]),
            "authority": r.get("authority_name") or r.get("state") or "",
            "category": (r.get("category") or "").strip().lower(),
            "title": r.get("title") or "Requirement",
            "statute_citation": r.get("statute_citation"),
            "source_url": r.get("source_url"),
        })
    return {
        "employee_id": str(emp),
        "state": state,
        "notices": groups,
        "count": sum(len(v) for v in groups.values()),
    }


async def new_state_summary(conn, company_id) -> dict[str, Any]:
    """States where the company has active employees but NO business location —
    the jurisdictions it has obligations in but has never set compliance up for.
    Cheap DISTINCT reads, computed live (no stored state, no drift)."""
    try:
        comp = company_id if isinstance(company_id, UUID) else UUID(str(company_id))
    except (ValueError, TypeError):
        return {"employee_states": [], "location_states": [], "new_jurisdictions": []}
    try:
        emp_rows = await conn.fetch(
            """
            SELECT DISTINCT UPPER(TRIM(work_state)) AS st
            FROM employees
            WHERE org_id = $1 AND work_state IS NOT NULL
              AND COALESCE(employment_status, 'active') NOT IN ('terminated', 'offboarded')
            """,
            comp,
        )
        loc_rows = await conn.fetch(
            """
            SELECT DISTINCT UPPER(TRIM(state)) AS st
            FROM business_locations
            WHERE company_id = $1 AND state IS NOT NULL AND COALESCE(is_active, true) = true
            """,
            comp,
        )
    except Exception:
        logger.exception("new_hire_packet: new_state_summary failed for %s", company_id)
        return {"employee_states": [], "location_states": [], "new_jurisdictions": []}

    emp_states = {r["st"] for r in emp_rows if r["st"]}
    loc_states = {r["st"] for r in loc_rows if r["st"]}
    return {
        "employee_states": sorted(emp_states),
        "location_states": sorted(loc_states),
        "new_jurisdictions": sorted(emp_states - loc_states),
    }
