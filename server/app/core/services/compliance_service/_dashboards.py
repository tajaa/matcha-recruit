"""compliance_service._dashboards — summary + dashboard, split of _checks.py."""
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




async def get_compliance_summary(company_id: UUID) -> ComplianceSummary:
    from app.database import get_connection

    async with get_connection() as conn:
        # Resolved once, outside the per-location loop below.
        gate = await codified_gate_sql("cat", conn=conn)
        locations = await conn.fetch(
            """SELECT bl.*, jr.has_local_ordinance
               FROM business_locations bl
               LEFT JOIN jurisdiction_reference jr
                 ON LOWER(bl.city) = jr.city AND UPPER(bl.state) = jr.state
               WHERE bl.company_id = $1""",
            company_id,
        )

        total_requirements = 0
        unread_alerts = 0
        critical_alerts = 0
        recent_changes = []
        auto_check_count = 0

        for loc in locations:
            if loc.get("auto_check_enabled", True):
                auto_check_count += 1

            reqs = await conn.fetch(
                "SELECT r.* FROM compliance_requirements r "
                "LEFT JOIN jurisdiction_requirements cat "
                "  ON cat.id = r.jurisdiction_requirement_id "
                "WHERE r.location_id = $1" + gate,
                loc["id"],
            )
            req_dicts = [dict(r) for r in reqs]
            if loc.get("has_local_ordinance") is False:
                req_dicts = _filter_city_level_requirements(req_dicts, loc["state"])
            _normalize_requirement_categories(req_dicts)
            req_dicts = await _filter_requirements_for_company(
                conn, loc["company_id"], req_dicts
            )
            filtered_reqs = await _filter_with_preemption(conn, req_dicts, loc["state"])
            total_requirements += len(filtered_reqs)

            for req in filtered_reqs:
                if req["last_changed_at"]:
                    recent_changes.append(
                        {
                            "location": loc["name"] or f"{loc['city']}, {loc['state']}",
                            "category": req["category"],
                            "title": req["title"],
                            "old_value": req["previous_value"],
                            "new_value": req["current_value"],
                            "changed_at": req["last_changed_at"].isoformat(),
                        }
                    )

            alerts = await conn.fetch(
                "SELECT * FROM compliance_alerts WHERE location_id = $1",
                loc["id"],
            )
            for alert in alerts:
                if alert["status"] == "unread":
                    unread_alerts += 1
                    if alert["severity"] == "critical":
                        critical_alerts += 1

        recent_changes.sort(key=lambda x: x["changed_at"], reverse=True)
        recent_changes = recent_changes[:10]

        # Get nearest upcoming deadlines
        upcoming_rows = await conn.fetch(
            """
            SELECT ul.title, ul.expected_effective_date, ul.current_status, ul.category,
                   bl.name AS location_name, bl.city, bl.state
            FROM upcoming_legislation ul
            JOIN business_locations bl ON ul.location_id = bl.id
            WHERE ul.company_id = $1
              AND ul.current_status NOT IN ('effective', 'dismissed')
              AND ul.expected_effective_date IS NOT NULL
              AND ul.expected_effective_date > CURRENT_DATE
            ORDER BY ul.expected_effective_date ASC
            LIMIT 3
            """,
            company_id,
        )
        upcoming_deadlines = []
        now = datetime.utcnow().date()
        for row in upcoming_rows:
            days = (row["expected_effective_date"] - now).days
            upcoming_deadlines.append(
                {
                    "title": row["title"],
                    "effective_date": row["expected_effective_date"].isoformat(),
                    "days_until": days,
                    "status": row["current_status"],
                    "category": row["category"],
                    "location": row["location_name"]
                    or f"{row['city']}, {row['state']}",
                }
            )

        return ComplianceSummary(
            total_locations=len(locations),
            total_requirements=total_requirements,
            unread_alerts=unread_alerts,
            critical_alerts=critical_alerts,
            recent_changes=recent_changes,
            auto_check_locations=auto_check_count,
            upcoming_deadlines=upcoming_deadlines,
        )




async def get_compliance_dashboard(company_id: UUID, horizon_days: int = 90) -> dict:
    """
    Return a compliance dashboard with actionable tasks for each upcoming change.
    """
    from app.database import get_connection

    def _parse_metadata(value: Any) -> dict[str, Any]:
        if isinstance(value, dict):
            return value
        if isinstance(value, str):
            try:
                parsed = json.loads(value)
                return parsed if isinstance(parsed, dict) else {}
            except (json.JSONDecodeError, TypeError):
                return {}
        return {}

    def _parse_iso_date(value: Any) -> Optional[date]:
        if isinstance(value, datetime):
            return value.date()
        if isinstance(value, date):
            return value
        if isinstance(value, str):
            raw = value.strip()
            if not raw:
                return None
            try:
                return date.fromisoformat(raw[:10])
            except ValueError:
                return None
        return None

    def _derive_sla_state(
        action_status: Optional[str],
        due_date: Optional[date],
        has_owner: bool,
        today: date,
    ) -> str:
        if action_status == "actioned":
            return "completed"
        if due_date and due_date < today:
            return "overdue"
        if due_date and (due_date - today).days <= 7:
            return "due_soon"
        if not has_owner:
            return "unassigned"
        return "on_track"

    default_playbooks = {
        "minimum_wage": "Audit pay bands and update payroll before the effective date.",
        "sick_leave": "Update sick leave policy language and accrual settings.",
        "overtime": "Review exempt/non-exempt classifications and overtime rules.",
        "pay_frequency": "Confirm payroll schedule and notice requirements.",
        "final_pay": "Align offboarding checklist with final pay timing rules.",
        "posting_requirements": "Refresh workplace posting packets and manager notices.",
    }

    async with get_connection() as conn:
        # ── 1. Fetch all company locations ──────────────────────────────────
        locations = await conn.fetch(
            """
            SELECT id, name, city, state, company_id
            FROM business_locations
            WHERE company_id = $1 AND is_active = true
            """,
            company_id,
        )
        location_map: dict[UUID, dict] = {row["id"]: dict(row) for row in locations}

        if not location_map:
            return {
                "kpis": {
                    "total_locations": 0,
                    "unread_alerts": 0,
                    "critical_alerts": 0,
                    "employees_at_risk": 0,
                    "overdue_actions": 0,
                    "assigned_actions": 0,
                    "unassigned_actions": 0,
                },
                "coming_up": [],
            }

        # ── 2. Fetch upcoming legislation within horizon ─────────────────────
        cutoff = datetime.utcnow().date() + timedelta(days=horizon_days)
        legislation_rows = await conn.fetch(
            """
            SELECT ul.id, ul.location_id, ul.title, ul.description, ul.category,
                   ul.current_status, ul.expected_effective_date, ul.impact_summary,
                   ul.source_url, ul.confidence, ul.created_at,
                   ca.id AS alert_id,
                   ca.severity,
                   ca.status AS alert_status,
                   ca.action_required,
                   ca.deadline AS alert_deadline,
                   ca.metadata AS alert_metadata
            FROM upcoming_legislation ul
            LEFT JOIN LATERAL (
                SELECT ca.id, ca.severity, ca.status, ca.action_required, ca.deadline, ca.metadata, ca.created_at
                FROM compliance_alerts ca
                WHERE ca.company_id = ul.company_id
                  AND ca.location_id = ul.location_id
                  AND ca.alert_type = 'upcoming_legislation'
                  AND ca.status <> 'dismissed'
                  AND ca.metadata->>'legislation_id' = ul.id::text
                ORDER BY
                    CASE ca.status
                        WHEN 'unread' THEN 0
                        WHEN 'read' THEN 1
                        WHEN 'actioned' THEN 2
                        ELSE 3
                    END,
                    CASE ca.severity
                        WHEN 'critical' THEN 0
                        WHEN 'warning' THEN 1
                        ELSE 2
                    END,
                    ca.created_at DESC
                LIMIT 1
            ) ca ON true
            WHERE ul.company_id = $1
              AND ul.current_status NOT IN ('effective', 'dismissed')
              AND (
                    ul.expected_effective_date IS NULL
                    OR ul.expected_effective_date <= $2
              )
            ORDER BY ul.expected_effective_date ASC NULLS LAST, ul.created_at DESC
            """,
            company_id,
            cutoff,
        )

        # ── 3. Fetch alert KPIs ──────────────────────────────────────────────
        alert_kpi_row = await conn.fetchrow(
            """
            SELECT
                COUNT(*) FILTER (WHERE status = 'unread') AS unread_alerts,
                COUNT(*) FILTER (WHERE status = 'unread' AND severity = 'critical') AS critical_alerts
            FROM compliance_alerts
            WHERE company_id = $1
            """,
            company_id,
        )
        unread_alerts = int(alert_kpi_row["unread_alerts"] or 0)
        critical_alerts = int(alert_kpi_row["critical_alerts"] or 0)

        # ── 4. Build state → employees mapping (state_estimate logic) ────────
        # We gather all active employees for the company grouped by work_state.
        employee_rows = await conn.fetch(
            """
            SELECT id, first_name, last_name, work_state
            FROM employees
            WHERE org_id = $1
              AND termination_date IS NULL
              AND work_state IS NOT NULL
            ORDER BY last_name, first_name
            """,
            company_id,
        )

        # state → list of {id, name}
        state_employee_map: dict[str, list[dict]] = {}
        for emp in employee_rows:
            st = (emp["work_state"] or "").upper().strip()
            if not st:
                continue
            state_employee_map.setdefault(st, []).append(
                {
                    "id": str(emp["id"]),
                    "name": f"{emp['first_name']} {emp['last_name']}",
                }
            )

        # Unique states covered by company locations
        location_states = {loc["state"].upper() for loc in locations}
        # Total employees whose state is a company location state
        employees_at_risk: set[str] = set()
        for st in location_states:
            for emp in state_employee_map.get(st, []):
                employees_at_risk.add(emp["id"])

        # Resolve action owner display names for any owner IDs carried in alert metadata.
        owner_ids: set[UUID] = set()
        for row in legislation_rows:
            metadata = _parse_metadata(row.get("alert_metadata"))
            owner_id_raw = metadata.get("action_owner_id")
            if isinstance(owner_id_raw, str) and owner_id_raw.strip():
                try:
                    owner_ids.add(UUID(owner_id_raw))
                except ValueError:
                    continue

        owner_name_map: dict[str, str] = {}
        if owner_ids:
            owner_rows = await conn.fetch(
                """
                SELECT u.id,
                       COALESCE(c.name, a.name, u.email) AS display_name
                FROM users u
                LEFT JOIN clients c ON c.user_id = u.id AND c.company_id = $2
                LEFT JOIN admins a ON a.user_id = u.id
                WHERE u.id = ANY($1::uuid[])
                """,
                list(owner_ids),
                company_id,
            )
            owner_name_map = {
                str(row["id"]): row["display_name"] for row in owner_rows if row["id"]
            }

        # ── 5. Deduplicate + enrich legislation items ────────────────────────
        now = datetime.utcnow().date()
        seen_leg_ids: set = set()
        coming_up = []

        for row in legislation_rows:
            leg_id = str(row["id"])
            if leg_id in seen_leg_ids:
                continue
            seen_leg_ids.add(leg_id)

            loc = location_map.get(row["location_id"])
            if not loc:
                continue

            loc_state = loc["state"].upper()
            affected = state_employee_map.get(loc_state, [])

            effective_date = row["expected_effective_date"]
            days_until = (effective_date - now).days if effective_date else None

            alert_metadata = _parse_metadata(row.get("alert_metadata"))
            owner_id_raw = alert_metadata.get("action_owner_id")
            owner_id = None
            if isinstance(owner_id_raw, str) and owner_id_raw.strip():
                try:
                    owner_id = str(UUID(owner_id_raw))
                except ValueError:
                    owner_id = None

            owner_name_raw = alert_metadata.get("action_owner_name")
            owner_name = (
                owner_name_raw.strip()
                if isinstance(owner_name_raw, str) and owner_name_raw.strip()
                else (owner_name_map.get(owner_id) if owner_id else None)
            )

            action_due_date = (
                _parse_iso_date(alert_metadata.get("action_due_date"))
                or row.get("alert_deadline")
                or effective_date
            )
            next_action = (
                (alert_metadata.get("next_action") or "").strip()
                if isinstance(alert_metadata.get("next_action"), str)
                else None
            ) or row.get("action_required")
            if not next_action:
                next_action = "Review legal impact and confirm operational changes."

            recommended_playbook = (
                (alert_metadata.get("recommended_playbook") or "").strip()
                if isinstance(alert_metadata.get("recommended_playbook"), str)
                else ""
            )
            if not recommended_playbook:
                recommended_playbook = default_playbooks.get(
                    row["category"], "Review impact, assign owner, and track completion."
                )

            estimated_financial_impact_raw = alert_metadata.get(
                "estimated_financial_impact"
            )
            estimated_financial_impact = None
            if isinstance(estimated_financial_impact_raw, (str, int, float)):
                estimated_financial_impact = str(estimated_financial_impact_raw).strip()
                if not estimated_financial_impact:
                    estimated_financial_impact = None

            action_status = row.get("alert_status") or "untracked"
            sla_state = _derive_sla_state(
                action_status=action_status,
                due_date=action_due_date,
                has_owner=owner_id is not None,
                today=now,
            )
            is_overdue = sla_state == "overdue"

            # Infer severity bucket if no linked alert found
            raw_severity = row["severity"]
            if not raw_severity:
                if days_until is not None and days_until <= 30:
                    raw_severity = "critical"
                elif days_until is not None and days_until <= 60:
                    raw_severity = "warning"
                else:
                    raw_severity = "info"

            coming_up.append(
                {
                    "legislation_id": leg_id,
                    "title": row["title"],
                    "description": row["description"] or row["impact_summary"],
                    "category": row["category"],
                    "severity": raw_severity,
                    "status": row["current_status"],
                    "effective_date": effective_date.isoformat()
                    if effective_date
                    else None,
                    "days_until": days_until,
                    "location_id": str(row["location_id"]),
                    "location_name": loc["name"] or f"{loc['city']}, {loc['state']}",
                    "location_state": loc_state,
                    "alert_id": str(row["alert_id"]) if row.get("alert_id") else None,
                    "action_status": action_status,
                    "next_action": next_action,
                    "action_owner_id": owner_id,
                    "action_owner_name": owner_name,
                    "action_due_date": action_due_date.isoformat()
                    if action_due_date
                    else None,
                    "is_overdue": is_overdue,
                    "sla_state": sla_state,
                    "recommended_playbook": recommended_playbook,
                    "estimated_financial_impact": estimated_financial_impact,
                    "affected_employee_count": len(affected),
                    "affected_employee_sample": [e["name"] for e in affected[:5]],
                    "impact_basis": "state_estimate",
                    "source_url": row["source_url"],
                }
            )

        overdue_actions = 0
        assigned_actions = 0
        unassigned_actions = 0
        for item in coming_up:
            if item.get("action_status") == "actioned":
                continue
            if item.get("is_overdue"):
                overdue_actions += 1
            if item.get("action_owner_id"):
                assigned_actions += 1
            else:
                unassigned_actions += 1

        return {
            "kpis": {
                "total_locations": len(location_map),
                "unread_alerts": unread_alerts,
                "critical_alerts": critical_alerts,
                "employees_at_risk": len(employees_at_risk),
                "overdue_actions": overdue_actions,
                "assigned_actions": assigned_actions,
                "unassigned_actions": unassigned_actions,
            },
            "coming_up": coming_up,
        }




