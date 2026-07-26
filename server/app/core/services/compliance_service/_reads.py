"""compliance_service._reads — read-path queries (impact/location/hierarchical/search), split of _checks.py."""
from contextlib import asynccontextmanager
from typing import Optional, List, AsyncGenerator, Dict, Any, Callable, Tuple
from uuid import UUID
from datetime import date, datetime, timedelta
import asyncio
import json
import logging
import re

import asyncpg
import httpx
from fastapi import HTTPException

from app.core.services.scope_registry.codify import codified_sql
from app.core.services.company_contacts import get_company_name_and_contacts
from app.core.services.jurisdiction_context import (
    get_known_sources,
    record_source,
    extract_domain,
    build_context_prompt,
    get_source_reputations,
    update_source_accuracy,
)
from app.core.models.compliance import (
    BusinessLocation,
    ComplianceRequirement,
    ComplianceAlert,
    LocationCreate,
    LocationUpdate,
    AutoCheckSettings,
    RequirementResponse,
    AlertResponse,
    CheckLogEntry,
    UpcomingLegislationResponse,
    VerificationResult,
    ComplianceSummary,
)
from app.core.compliance_registry import (
    LABOR_CATEGORIES as REQUIRED_LABOR_CATEGORIES,
    HEALTHCARE_CATEGORIES,
    ONCOLOGY_CATEGORIES,
    MEDICAL_COMPLIANCE_CATEGORIES,
    LIFE_SCIENCES_CATEGORIES,
    INDUSTRY_TAGS as MEDICAL_COMPLIANCE_INDUSTRY_TAGS,
)

logger = logging.getLogger(__name__)

from app.core.services.compliance_service._shared import (
    MAX_VERIFICATIONS_PER_CHECK,
    _heartbeat_while,
    _parse_jsonb_list,
)
from app.core.services.compliance_service._normalize import (
    _missing_required_categories,
    _normalize_category,
    _normalize_requirement_categories,
)
from app.core.services.compliance_service._industry import (
    _get_industry_profile,
    _requirement_applicable_industries,
)
from app.core.services.compliance_service._verification import (
    format_corrections_for_prompt,
    get_recent_corrections,
    score_verification_confidence,
)
from app.core.services.compliance_service._jurisdictions import (
    _authority_label,
    _basis_from_metadata,
    _drop_no_rule_placeholders,
    _fill_missing_categories_from_parents,
    _get_or_create_jurisdiction,
    _is_jurisdiction_fresh,
    _jurisdiction_row_to_dict,
    _load_jurisdiction_requirements,
    _lookup_has_local_ordinance,
    _try_load_county_requirements,
    _try_load_state_requirements,
)
from app.core.services.compliance_service._hierarchy import (
    _compute_triggered_by,
    _filter_city_level_requirements,
    _filter_requirements_for_company,
    _filter_with_preemption,
    _project_chain_to_location,
    codified_gate_sql,
    determine_governing_requirement,
    is_codified_row,
    resolve_jurisdiction_stack,
)
from app.core.services.compliance_service._catalog_writes import (
    _compute_requirement_key,
    _upsert_jurisdiction_legislation,
    _upsert_jurisdiction_requirements_routed,
    _upsert_requirements_additive,
)
from app.core.services.compliance_service._alerts import (
    _complete_check_log,
    _create_alert,
    _create_check_log,
    _log_verification_outcome,
    _notify_company_admins_of_compliance_changes,
    _record_change_notification_item,
    _send_bulk_alert_email,
    escalate_upcoming_deadlines,
    process_upcoming_legislation,
)
from app.core.services.compliance_service._research import (
    _fill_from_state_fallback,
    _refresh_repository_missing_categories,
)
from app.core.services.compliance_service._locations import (
    _sync_requirements_to_location,
    get_location,
)




@asynccontextmanager
async def _conn_or_new(conn):
    """Yield the caller's connection, or open a fresh one if none was passed.

    Lets a hot path (e.g. the component-checklist endpoint) thread one
    connection through several service calls instead of each one opening
    its own — the nested-acquire footgun already documented at
    matcha_work_document/__init__.py:189.
    """
    if conn is not None:
        yield conn
        return
    from app.database import get_connection
    async with get_connection() as c:
        yield c


async def get_employee_impact_for_location(
    location_id: UUID, company_id: UUID, *, conn=None
) -> Dict[str, Any]:
    """Calculate employee impact for a compliance location.

    Returns total affected employees plus per-rate_type violation details.

    Primary path: query by work_location_id FK (fast, exact).
    Fallback: heuristic matching for employees with work_location_id IS NULL
    (legacy rows that predate the FK linkage).

    Pass `conn=` to reuse an already-open connection instead of acquiring a
    new one from the pool.
    """
    async with _conn_or_new(conn) as conn:
        # Get location state/city
        loc = await conn.fetchrow(
            "SELECT state, city FROM business_locations WHERE id = $1 AND company_id = $2",
            location_id, company_id,
        )
        if not loc:
            return {"total_affected": 0, "employee_names": [], "violations_by_rate_type": {}}

        loc_state = loc["state"]
        loc_city = loc["city"]

        # Primary path: employees linked via FK
        fk_employees = await conn.fetch(
            """
            SELECT id, first_name, last_name, pay_classification, pay_rate,
                   work_city, work_state
            FROM employees
            WHERE org_id = $1 AND work_location_id = $2 AND termination_date IS NULL
            """,
            company_id, location_id,
        )

        # Fallback: heuristic for legacy employees with work_location_id IS NULL
        if loc_city:
            heuristic_employees = await conn.fetch(
                """
                SELECT id, first_name, last_name, pay_classification, pay_rate,
                       work_city, work_state
                FROM employees
                WHERE org_id = $1
                  AND termination_date IS NULL
                  AND work_location_id IS NULL
                  AND (
                      (LOWER(work_city) = LOWER($2) AND UPPER(work_state) = UPPER($3))
                      OR (work_state IS NULL AND work_city IS NULL
                          AND address IS NOT NULL AND address ILIKE '%' || $2 || '%')
                  )
                """,
                company_id, loc_city, loc_state,
            )
        else:
            heuristic_employees = await conn.fetch(
                """
                SELECT id, first_name, last_name, pay_classification, pay_rate,
                       work_city, work_state
                FROM employees
                WHERE org_id = $1
                  AND termination_date IS NULL
                  AND work_location_id IS NULL
                  AND UPPER(work_state) = UPPER($2)
                  AND (work_city IS NULL OR work_city = '')
                """,
                company_id, loc_state,
            )

        # Deduplicate (in case FK and heuristic overlap during migration)
        seen_ids = {emp["id"] for emp in fk_employees}
        employees = list(fk_employees)
        for emp in heuristic_employees:
            if emp["id"] not in seen_ids:
                employees.append(emp)
                seen_ids.add(emp["id"])

        total_affected = len(employees)

        # Get minimum_wage requirements for this location to check violations
        wage_reqs = await conn.fetch(
            """
            SELECT rate_type, numeric_value, jurisdiction_level
            FROM compliance_requirements
            WHERE location_id = $1 AND category = 'minimum_wage' AND numeric_value IS NOT NULL
            ORDER BY
                CASE jurisdiction_level
                    WHEN 'city' THEN 1
                    WHEN 'county' THEN 2
                    WHEN 'state' THEN 3
                    WHEN 'federal' THEN 4
                    ELSE 5
                END
            """,
            location_id,
        )

        # Build rate_type -> threshold map (first match wins = highest priority jurisdiction)
        thresholds: Dict[str, float] = {}
        for wr in wage_reqs:
            rt = wr["rate_type"] or "general"
            if rt not in thresholds:
                thresholds[rt] = float(wr["numeric_value"])

        # Fallback: check jurisdiction_requirements for missing rate types
        missing_types = {"general", "exempt_salary"} - set(thresholds.keys())
        if missing_types:
            # Try via business_locations.jurisdiction_id first (city-level)
            jr_rows = await conn.fetch(
                """
                SELECT jr.rate_type, jr.numeric_value
                FROM business_locations bl
                JOIN jurisdiction_requirements jr ON jr.jurisdiction_id = bl.jurisdiction_id
                WHERE bl.id = $1
                  AND jr.category = 'minimum_wage'
                  AND jr.numeric_value IS NOT NULL
                  AND jr.rate_type = ANY($2::text[])
                ORDER BY jr.rate_type
                """,
                location_id, list(missing_types),
            )
            for jr in jr_rows:
                rt = jr["rate_type"] or "general"
                if rt not in thresholds:
                    thresholds[rt] = float(jr["numeric_value"])

            # State-level fallback for still-missing types (exempt salary is often state-level)
            still_missing = {"general", "exempt_salary"} - set(thresholds.keys())
            if still_missing and loc_state:
                state_rows = await conn.fetch(
                    """
                    SELECT jr.rate_type, jr.numeric_value
                    FROM jurisdictions j
                    JOIN jurisdiction_requirements jr ON jr.jurisdiction_id = j.id
                    WHERE UPPER(j.state) = UPPER($1)
                      AND (j.city IS NULL OR j.city = '' OR LOWER(j.city) = LOWER(j.state))
                      AND jr.category = 'minimum_wage'
                      AND jr.numeric_value IS NOT NULL
                      AND jr.rate_type = ANY($2::text[])
                    ORDER BY jr.numeric_value DESC
                    """,
                    loc_state, list(still_missing),
                )
                for sr in state_rows:
                    rt = sr["rate_type"] or "general"
                    if rt not in thresholds:
                        thresholds[rt] = float(sr["numeric_value"])

            # Final fallback: check compliance_requirements from other same-company
            # same-state locations at jurisdiction_level='state'. This catches exempt_salary
            # thresholds that the AI populated for a different location in the same state.
            still_missing = {"general", "exempt_salary"} - set(thresholds.keys())
            if still_missing and loc_state:
                peer_rows = await conn.fetch(
                    """
                    SELECT cr.rate_type, MAX(cr.numeric_value) AS numeric_value
                    FROM compliance_requirements cr
                    JOIN business_locations bl ON bl.id = cr.location_id
                    WHERE bl.company_id = $1
                      AND UPPER(bl.state) = UPPER($2)
                      AND bl.id != $3
                      AND cr.category = 'minimum_wage'
                      AND cr.jurisdiction_level = 'state'
                      AND cr.numeric_value IS NOT NULL
                      AND cr.rate_type = ANY($4::text[])
                    GROUP BY cr.rate_type
                    """,
                    company_id, loc_state, location_id, list(still_missing),
                )
                for pr in peer_rows:
                    rt = pr["rate_type"] or "general"
                    if rt not in thresholds:
                        thresholds[rt] = float(pr["numeric_value"])

        # Check each employee for wage violations, bucketed by rate_type
        violations_by_rate_type: Dict[str, list] = {}
        for emp in employees:
            if emp["pay_classification"] is None or emp["pay_rate"] is None:
                continue

            rate = float(emp["pay_rate"])
            classification = emp["pay_classification"]

            if classification == "hourly":
                rate_type_key = "general"
            elif classification == "exempt":
                rate_type_key = "exempt_salary"
            else:
                continue

            threshold = thresholds.get(rate_type_key)
            if threshold is not None and rate < threshold:
                violation = {
                    "employee_id": str(emp["id"]),
                    "employee_name": f"{emp['first_name']} {emp['last_name']}",
                    "pay_classification": classification,
                    "pay_rate": rate,
                    "threshold": threshold,
                    "shortfall": round(threshold - rate, 2),
                }
                violations_by_rate_type.setdefault(rate_type_key, []).append(violation)

        employee_names = [
            f"{e['first_name']} {e['last_name']}" for e in employees[:5]
        ]

        return {
            "total_affected": total_affected,
            "employee_names": employee_names,
            "violations_by_rate_type": violations_by_rate_type,
        }




async def get_location_requirements(
    location_id: UUID, company_id: UUID, category: Optional[str] = None, *, conn=None
) -> List[RequirementResponse]:
    """Pass `conn=` to reuse an already-open connection instead of acquiring a
    new one from the pool (see `_conn_or_new`)."""
    async with _conn_or_new(conn) as conn:
        loc = await conn.fetchrow(
            """SELECT bl.state, jr.has_local_ordinance
               FROM business_locations bl
               LEFT JOIN jurisdiction_reference jr
                 ON LOWER(bl.city) = jr.city AND UPPER(bl.state) = jr.state
               WHERE bl.id = $1 AND bl.company_id = $2""",
            location_id,
            company_id,
        )
        if not loc:
            return []
        state = loc["state"]
        has_local_ordinance = loc["has_local_ordinance"]

        # source_url_status/statute_citation live on the catalog row
        # (jurisdiction_requirements) and are joined through the SSOT FK at
        # read time — never mirrored, so they can't go stale. Null-FK
        # (Gemini-fresh) rows read as NULL = unchecked / uncited.
        # `authority_*` is the issuing jurisdiction resolved through the catalog
        # FK — the trustworthy answer to "who imposes this?". It is deliberately
        # additive: r.jurisdiction_level / r.jurisdiction_name are free text and
        # several filters below still key on them, so this joins alongside rather
        # than overwriting them.
        query = """
            SELECT r.*, cat.source_url_status, cat.statute_citation, cat.citation_verified_at,
                   cat.metadata -> 'jurisdictional_basis' AS jurisdictional_basis,
                   j.level::text AS authority_level,
                   j.display_name AS authority_display_name
            FROM compliance_requirements r
            JOIN business_locations l ON r.location_id = l.id
            LEFT JOIN jurisdiction_requirements cat
              ON cat.id = r.jurisdiction_requirement_id
            LEFT JOIN jurisdictions j ON j.id = cat.jurisdiction_id
            WHERE l.id = $1 AND l.company_id = $2
        """
        query += await codified_gate_sql("cat", conn=conn)
        params = [location_id, company_id]

        if category:
            query += " AND r.category = $3"
            params.append(category)

        query += " ORDER BY r.category, r.jurisdiction_level"

        rows = await conn.fetch(query, *params)
        row_dicts = [dict(row) for row in rows]
        if has_local_ordinance is False:
            row_dicts = _filter_city_level_requirements(row_dicts, state)
        _normalize_requirement_categories(row_dicts)
        row_dicts = await _filter_requirements_for_company(
            conn, company_id, row_dicts
        )
        filtered = await _filter_with_preemption(conn, row_dicts, state)

        # Enrich with employee impact data
        try:
            impact = await get_employee_impact_for_location(location_id, company_id, conn=conn)
            total_affected = impact["total_affected"]
            employee_names = impact["employee_names"]
            violations_by_rt = impact["violations_by_rate_type"]
        except Exception:
            total_affected = None
            employee_names = []
            violations_by_rt = {}

        def _violation_count_for_row(row: dict) -> Optional[int]:
            if row["category"] != "minimum_wage":
                return None
            rt = row.get("rate_type") or "general"
            return len(violations_by_rt.get(rt, []))

        # Batched, not per-row: which of these catalog rows decompose into a
        # component checklist (reqcomp01)? One query for the whole page.
        catalog_ids = {
            row["jurisdiction_requirement_id"]
            for row in filtered
            if row.get("jurisdiction_requirement_id")
        }
        components_present: set = set()
        if catalog_ids:
            components_present = {
                r["jurisdiction_requirement_id"]
                for r in await conn.fetch(
                    "SELECT DISTINCT jurisdiction_requirement_id FROM requirement_components "
                    "WHERE jurisdiction_requirement_id = ANY($1::uuid[])",
                    list(catalog_ids),
                )
            }

        return [
            RequirementResponse(
                id=str(row["id"]),
                category=row["category"],
                rate_type=row.get("rate_type"),
                applicable_industries=sorted(_requirement_applicable_industries(row))
                or None,
                jurisdiction_level=row["jurisdiction_level"],
                jurisdiction_name=row["jurisdiction_name"],
                title=row["title"],
                description=row["description"],
                current_value=row["current_value"],
                numeric_value=float(row["numeric_value"])
                if row.get("numeric_value") is not None
                else None,
                source_url=row["source_url"],
                source_url_status=row.get("source_url_status"),
                statute_citation=row.get("statute_citation"),
                citation_verified_at=row["citation_verified_at"].isoformat()
                if row.get("citation_verified_at")
                else None,
                jurisdictional_basis=_parse_jsonb_list(row.get("jurisdictional_basis")),
                source_name=row["source_name"],
                effective_date=row["effective_date"].isoformat()
                if row["effective_date"]
                else None,
                previous_value=row["previous_value"],
                last_changed_at=row["last_changed_at"].isoformat()
                if row["last_changed_at"]
                else None,
                affected_employee_count=total_affected,
                affected_employee_names=employee_names or None,
                min_wage_violation_count=_violation_count_for_row(row),
                is_pinned=row.get("is_pinned", False),
                jurisdiction_requirement_id=str(row["jurisdiction_requirement_id"])
                if row.get("jurisdiction_requirement_id")
                else None,
                authority_level=row.get("authority_level"),
                authority_name=_authority_label(
                    row.get("authority_level"), row.get("authority_display_name")
                ),
                has_components=row.get("jurisdiction_requirement_id") in components_present,
            )
            for row in filtered
        ]






async def get_hierarchical_requirements(
    location_id: UUID, company_id: UUID, category: Optional[str] = None
) -> Optional[Dict[str, Any]]:
    """Fully resolve compliance requirements for a location using hierarchical precedence.

    This is the main entry point for the hierarchical view. It:
    1. Loads the location and its facility_attributes
    2. Resolves the jurisdiction stack via recursive CTE
    3. Groups by category
    4. Evaluates trigger conditions against facility attributes
    5. Determines governing requirement per category via precedence rules
    6. Returns a fully-resolved response dict — frontend just renders it

    Returns None if location not found.
    """
    from app.database import get_connection

    async with get_connection() as conn:
        # 1. Load location
        loc = await conn.fetchrow(
            """SELECT bl.id, bl.city, bl.state, bl.name,
                      bl.jurisdiction_id, bl.facility_attributes
               FROM business_locations bl
               WHERE bl.id = $1 AND bl.company_id = $2""",
            location_id,
            company_id,
        )
        if not loc:
            return None
        if not loc["jurisdiction_id"]:
            return None

        facility_attrs = loc["facility_attributes"]
        if isinstance(facility_attrs, str):
            try:
                facility_attrs = json.loads(facility_attrs)
            except (json.JSONDecodeError, TypeError):
                facility_attrs = None

        # 2. Resolve jurisdiction stack
        stack_rows = await resolve_jurisdiction_stack(conn, loc["jurisdiction_id"])

        # This view reads the catalog directly rather than the location's
        # projection, so the SQL gate on compliance_requirements never reaches
        # it — filter the rows themselves, or the hierarchical view becomes the
        # hole every uncodified row walks back through.
        from app.core.services.platform_settings import get_tenant_codified_only

        if await get_tenant_codified_only(conn=conn):
            stack_rows = [r for r in stack_rows if is_codified_row(r)]

        # 3. Group by category
        by_category: Dict[str, List[Dict[str, Any]]] = {}
        for row in stack_rows:
            cat = row["category"]
            if category and cat != category:
                continue
            by_category.setdefault(cat, []).append(row)

        # 4-5. Determine governing requirement per category
        resolved = determine_governing_requirement(by_category, facility_attrs)

        # 6. Look up category labels
        cat_labels = {}
        if resolved:
            cat_ids = [r["category_id"] for r in resolved if r.get("category_id")]
            if cat_ids:
                label_rows = await conn.fetch(
                    "SELECT id, slug, name, domain::text, \"group\" FROM compliance_categories WHERE id = ANY($1)",
                    cat_ids,
                )
                for lr in label_rows:
                    cat_labels[str(lr["id"])] = {
                        "name": lr["name"],
                        "domain": lr["domain"],
                        "group": lr["group"],
                        "slug": lr["slug"],
                    }

        # 7. Get employee impact
        try:
            impact = await get_employee_impact_for_location(location_id, company_id)
            total_affected = impact["total_affected"]
        except Exception:
            total_affected = None

        # 8. Build response
        categories_out = []
        total_requirements = 0
        for item in resolved:
            gov = item["governing_requirement"]
            cat_id_str = str(item.get("category_id", ""))
            cat_info = cat_labels.get(cat_id_str, {})

            all_levels = []
            for row in item["all_levels"]:
                all_levels.append({
                    "id": str(row["id"]),
                    "jurisdiction_level": row.get("jur_level") or row.get("jurisdiction_level", ""),
                    "jurisdiction_name": row.get("jur_display_name") or row.get("jurisdiction_name", ""),
                    "title": row.get("title", ""),
                    "description": row.get("description"),
                    "current_value": row.get("current_value"),
                    "previous_value": row.get("previous_value"),
                    "previous_description": row.get("previous_description"),
                    "change_status": row.get("change_status"),
                    "last_changed_at": row["last_changed_at"].isoformat() if row.get("last_changed_at") else None,
                    "numeric_value": float(row["numeric_value"]) if row.get("numeric_value") is not None else None,
                    "source_url": row.get("source_url"),
                    "source_url_status": row.get("source_url_status"),
                    "statute_citation": row.get("statute_citation"),
                    # A row demoted to a floor relation has NO statute_citation
                    # (citing the floor would be false provenance). Without the
                    # basis here the hierarchical view just loses the citation
                    # with nothing explaining why.
                    "jurisdictional_basis": _basis_from_metadata(row.get("metadata")),
                    "status": row.get("req_status", "active"),
                    "canonical_key": row.get("canonical_key"),
                    "triggered_by": _compute_triggered_by(row.get("trigger_conditions"), facility_attrs),
                })
                total_requirements += 1

            precedence = None
            if item.get("precedence_type"):
                precedence = {
                    "precedence_type": item["precedence_type"],
                    "reasoning_text": item.get("reasoning_text"),
                    "legal_citation": item.get("legal_citation"),
                    "trigger_condition": item.get("rule_trigger_condition"),
                }

            categories_out.append({
                "category": item["category"],
                "category_label": cat_info.get("name", item["category"]),
                "domain": cat_info.get("domain"),
                "authority_type": "geographic",  # v2: from jurisdiction row
                "governing_level": item.get("governing_level", ""),
                "governing_requirement": {
                    "id": str(gov["id"]),
                    "jurisdiction_level": gov.get("jur_level") or gov.get("jurisdiction_level", ""),
                    "jurisdiction_name": gov.get("jur_display_name") or gov.get("jurisdiction_name", ""),
                    "title": gov.get("title", ""),
                    "description": gov.get("description"),
                    "current_value": gov.get("current_value"),
                    "previous_value": gov.get("previous_value"),
                    "previous_description": gov.get("previous_description"),
                    "change_status": gov.get("change_status"),
                    "last_changed_at": gov["last_changed_at"].isoformat() if gov.get("last_changed_at") else None,
                    "numeric_value": float(gov["numeric_value"]) if gov.get("numeric_value") is not None else None,
                    "source_url": gov.get("source_url"),
                    "source_url_status": gov.get("source_url_status"),
                    "statute_citation": gov.get("statute_citation"),
                    "jurisdictional_basis": _basis_from_metadata(gov.get("metadata")),
                    "status": gov.get("req_status", "active"),
                    "canonical_key": gov.get("canonical_key"),
                    "triggered_by": _compute_triggered_by(gov.get("trigger_conditions"), facility_attrs),
                },
                "precedence": precedence,
                "all_levels": all_levels,
                "affected_employee_count": total_affected,
            })

        return {
            "location_id": str(loc["id"]),
            "location_name": loc["name"] or "",
            "city": loc["city"],
            "state": loc["state"],
            "facility_attributes": facility_attrs,
            "categories": categories_out,
            "total_categories": len(categories_out),
            "total_requirements": total_requirements,
        }




async def search_company_requirements(
    conn,
    company_id: UUID,
    query: str,
    location_id: UUID | None = None,
    limit: int = 50,
) -> list[dict]:
    """Full-text search across a company's compliance requirements."""
    pattern = f"%{query}%"
    rows = await conn.fetch(
        """
        SELECT cr.*, bl.city, bl.state, bl.name AS location_name
        FROM compliance_requirements cr
        JOIN business_locations bl ON cr.location_id = bl.id
        LEFT JOIN jurisdiction_requirements cat
          ON cat.id = cr.jurisdiction_requirement_id
        WHERE bl.company_id = $1
          AND ($2::uuid IS NULL OR bl.id = $2)
          AND (
            cr.title ILIKE $3 OR cr.description ILIKE $3
            OR cr.current_value ILIKE $3 OR cr.jurisdiction_name ILIKE $3
            OR cr.category ILIKE $3
          )
        """
        # Search must not be a back door to rows the tab won't show.
        + await codified_gate_sql("cat", conn=conn)
        + """
        ORDER BY
          CASE WHEN cr.title ILIKE $3 THEN 0
               WHEN cr.current_value ILIKE $3 THEN 1
               WHEN cr.category ILIKE $3 THEN 2
               ELSE 3
          END,
          cr.category, cr.jurisdiction_level
        LIMIT $4
        """,
        company_id,
        location_id,
        pattern,
        limit,
    )
    return [dict(row) for row in rows]
