"""Project schedule-eligibility cases into actionable EMS events.

Eligibility cases remain the scheduling source of truth.  EMS is a
location-scoped operational surface for the manager who needs to understand
why an employee is blocked and how to remedy it.
"""
from __future__ import annotations

import json
from uuid import UUID

from app.core.feature_flags import get_company_features


SOURCE_KIND = "schedule_eligibility_case"
_OPEN_CASE_STATUSES = ("warning_open", "removal_requested")


def eligibility_event_mutation_error(source_kind: str | None, *, action: str) -> str | None:
    """Projected eligibility events are controlled solely by their case."""
    if source_kind == SOURCE_KIND:
        return f"Schedule eligibility events cannot be {action}; resolve the underlying credential case instead."
    return None


async def _ems_enabled(conn, company_id: UUID) -> bool:
    features = await get_company_features(company_id, conn=conn)
    return bool(features.get("ems") and features.get("matcha_ops"))


def _event_copy(row) -> tuple[str, str, str, dict[str, str]]:
    employee = row["employee_name"] or "Employee"
    credential = row["credential_label"] or "Required credential"
    expires = row["expires_at"].isoformat() if row["expires_at"] else "an unconfirmed date"
    automatic = str(row["blocking_reason_code"] or "").endswith("_auto_unassigned")
    removed = int(row["removed_assignments"] or 0)
    affected = int(row["affected_assignments"] or 0)
    if row["status"] == "warning_open":
        title = f"Credential expiring: {employee}"
        narrative = f"{credential} expires {expires}. Renew it before expiry to avoid a scheduling block."
        severity = "medium"
    elif automatic:
        title = f"Scheduling blocked: {employee}"
        narrative = (
            f"{credential} expired {expires}. {removed} future shift"
            f"{' was' if removed == 1 else 's were'} removed automatically; new assignments remain blocked until renewal."
        )
        severity = "high"
    else:
        title = f"Scheduling decision required: {employee}"
        narrative = f"{credential} is no longer valid. Review {affected} affected future shift(s)."
        severity = "high"
    details = {
        "eligibility_case_id": str(row["id"]),
        "employee_id": str(row["employee_id"]),
        "employee_name": employee,
        "credential": credential,
        "expires_at": expires,
        "case_status": str(row["status"]),
        "blocking_reason": str(row["blocking_reason_code"] or "credential requirement"),
        "affected_future_shifts": str(affected),
        "removed_future_shifts": str(removed),
        "schedule_link": f"/ops/schedule?tab=requests&location={row['location_id']}" if row["location_id"] else "/ops/schedule?tab=requests",
        "employee_link": f"/app/employees/{row['employee_id']}",
    }
    return title, narrative, severity, details


async def reconcile_schedule_eligibility_events(conn, company_id: UUID) -> dict[str, int]:
    """Idempotently create/update EMS projections and close stale projections."""
    if not await _ems_enabled(conn, company_id):
        return {"created_or_updated": 0, "resolved": 0}
    rows = await conn.fetch(
        """
        SELECT c.id, c.employee_id, c.location_id, c.status, c.expires_at, c.blocking_reason_code,
               TRIM(COALESCE(e.first_name, '') || ' ' || COALESCE(e.last_name, '')) AS employee_name,
               COALESCE(ct.label, 'Required credential') AS credential_label,
               COUNT(a.shift_id) AS affected_assignments,
               COUNT(a.shift_id) FILTER (WHERE a.action_status = 'removed') AS removed_assignments
          FROM schedule_eligibility_cases c
          JOIN employees e ON e.id = c.employee_id
          LEFT JOIN employee_credential_requirements ecr ON ecr.id = c.requirement_id
          LEFT JOIN scoped_credential_types ct ON ct.id = ecr.credential_type_id
          LEFT JOIN schedule_eligibility_case_assignments a ON a.case_id = c.id
         WHERE c.company_id = $1 AND c.status = ANY($2::text[])
         GROUP BY c.id, e.first_name, e.last_name, ct.label
        """,
        company_id, list(_OPEN_CASE_STATUSES),
    )
    active_refs: list[str] = []
    changed = 0
    for row in rows:
        source_ref = str(row["id"])
        active_refs.append(source_ref)
        title, narrative, severity, details = _event_copy(row)
        event = await conn.fetchrow(
            """
            INSERT INTO ems_events (
                company_id, title, category, severity_hint, doc, narrative,
                incident_recommendation, location_id, status, source_kind, source_ref
            )
            VALUES ($1, $2, 'operational', $3, $4::jsonb, $5, false, $6, 'logged', $7, $8)
            ON CONFLICT (company_id, source_kind, source_ref)
                WHERE source_kind = 'schedule_eligibility_case' AND source_ref IS NOT NULL
            DO UPDATE SET
                title=EXCLUDED.title, severity_hint=EXCLUDED.severity_hint,
                doc=EXCLUDED.doc, narrative=EXCLUDED.narrative,
                location_id=EXCLUDED.location_id, status='logged',
                resolved_by=NULL, resolved_at=NULL, resolution_code=NULL,
                resolution_note=NULL, updated_at=NOW()
            RETURNING id, (xmax = 0) AS inserted
            """,
            company_id, title, severity, json.dumps(details), narrative,
            row["location_id"], SOURCE_KIND, source_ref,
        )
        if event and event["inserted"]:
            await conn.execute(
                """INSERT INTO ems_event_audit_log (event_id, user_id, action, details)
                   VALUES ($1, NULL, 'created', $2::jsonb)""",
                event["id"], json.dumps({"source_kind": SOURCE_KIND, "source_ref": source_ref}),
            )
        changed += 1

    resolved = await conn.fetchval(
        """
        WITH closed AS (
            UPDATE ems_events
               SET status='completed', resolution_code='informational',
                   resolution_note='The scheduling eligibility issue is no longer active.',
                   resolved_at=COALESCE(resolved_at, NOW()), updated_at=NOW()
             WHERE company_id=$1 AND source_kind=$2 AND status='logged'
               AND NOT (source_ref = ANY($3::text[]))
            RETURNING 1
        ) SELECT COUNT(*) FROM closed
        """,
        company_id, SOURCE_KIND, active_refs,
    )
    return {"created_or_updated": changed, "resolved": int(resolved or 0)}
