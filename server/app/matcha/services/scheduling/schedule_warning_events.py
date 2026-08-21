"""Reconcile schedule competency warnings into EMS.

These are operational follow-up records, not channel-reported incidents. The
same source warning has one active EMS row, so repeated schedule writes and the
periodic sweep are safe to run more than once.
"""

from __future__ import annotations

import hashlib
import json
from datetime import date, datetime, timezone
from typing import Optional
from uuid import UUID

from app.core.feature_flags import get_company_features

from .schedule_intelligence import fetch_lapse_items

SOURCE_KIND = "schedule_compliance_warning"


def _warning_ref(shift_id: UUID, employee_id: UUID, item: dict) -> str:
    identity = "|".join(
        str(value or "")
        for value in (
            shift_id,
            employee_id,
            item.get("source"),
            item.get("requirement_id"),
            item.get("item"),
            item.get("date"),
        )
    )
    digest = hashlib.sha256(identity.encode("utf-8")).hexdigest()[:16]
    return f"{shift_id}:{employee_id}:{item.get('source', 'warning')}:{digest}"


def _date_value(value) -> Optional[date]:
    if isinstance(value, datetime):
        return value.astimezone(timezone.utc).date()
    return value if isinstance(value, date) else None


def _warning_label(item: dict) -> str:
    source = item.get("source")
    label = item.get("item") or ("Training" if source == "training" else "Credential")
    prefix = "Overdue training" if source == "training" else "Lapsed credential"
    due_date = _date_value(item.get("date"))
    return f"{prefix}: {label} (due {due_date.isoformat() if due_date else 'unknown date'})"


async def _ems_enabled(conn, company_id: UUID) -> bool:
    features = await get_company_features(company_id, conn=conn)
    return bool(features.get("ems") and features.get("matcha_ops"))


async def reconcile_schedule_warning_events(
    conn,
    company_id: UUID,
    *,
    shift_ids: Optional[list[UUID]] = None,
) -> dict[str, int]:
    """Create/update active warnings and resolve warnings no longer present.

    `shift_ids` scopes the reconciliation after a write. `None` performs the
    full company sweep used by the worker and also repairs warnings from
    deleted/cancelled shifts.
    """
    if not await _ems_enabled(conn, company_id):
        return {"created_or_updated": 0, "resolved": 0}

    params: list = [company_id]
    where = ["s.company_id = $1", "s.status <> 'cancelled'"]
    if shift_ids is not None:
        if not shift_ids:
            return {"created_or_updated": 0, "resolved": 0}
        params.append(shift_ids)
        where.append(f"s.id = ANY(${len(params)}::uuid[])")

    rows = await conn.fetch(
        f"""
        SELECT s.id AS shift_id, s.location_id, s.starts_at, s.ends_at,
               e.id AS employee_id,
               TRIM(COALESCE(e.first_name, '') || ' ' || COALESCE(e.last_name, '')) AS employee_name,
               bl.name AS location_name
        FROM schedule_shifts s
        JOIN schedule_shift_assignments a ON a.shift_id = s.id
        JOIN employees e ON e.id = a.employee_id
        LEFT JOIN business_locations bl ON bl.id = s.location_id
        WHERE {' AND '.join(where)}
        """,
        *params,
    )
    employee_ids = list(dict.fromkeys(row["employee_id"] for row in rows))
    features = await get_company_features(company_id, conn=conn)
    lapse_map = await fetch_lapse_items(
        conn,
        company_id,
        employee_ids,
        credential_templates_enabled=bool(features.get("credential_templates")),
        training_enabled=bool(features.get("training")),
    )
    today = datetime.now(timezone.utc).date()
    active_refs: set[str] = set()
    changed = 0

    for row in rows:
        for item in lapse_map.get(str(row["employee_id"]), []):
            due_date = _date_value(item.get("date"))
            if due_date is None or due_date >= today:
                continue
            warning = _warning_label(item)
            source_ref = _warning_ref(row["shift_id"], row["employee_id"], item)
            active_refs.add(source_ref)
            details = {
                "source": "schedule",
                "warning": warning,
                "employee_id": str(row["employee_id"]),
                "employee_name": row["employee_name"] or "Employee",
                "shift_id": str(row["shift_id"]),
                "shift_starts_at": row["starts_at"].isoformat(),
                "shift_ends_at": row["ends_at"].isoformat(),
                "location_id": str(row["location_id"]) if row["location_id"] else None,
                "location_name": row["location_name"],
                "due_date": due_date.isoformat(),
                "item": item.get("item"),
                "warning_source": item.get("source"),
            }
            inserted = await conn.fetchval(
                """
                INSERT INTO ems_events (
                    company_id, title, category, severity_hint, doc, narrative,
                    incident_recommendation, location_id, status, source_kind, source_ref
                )
                VALUES ($1, $2, 'operational', 'medium', $3::jsonb, $4, false, $5,
                        'logged', $6, $7)
                ON CONFLICT (company_id, source_kind, source_ref)
                    WHERE status = 'logged' AND source_kind IS NOT NULL AND source_ref IS NOT NULL
                DO NOTHING
                RETURNING id
                """,
                company_id,
                f"Schedule warning: {row['employee_name'] or 'Employee'}",
                json.dumps(details),
                f"{row['employee_name'] or 'Employee'} is assigned to a shift while {warning.lower()}.",
                row["location_id"],
                SOURCE_KIND,
                source_ref,
            )
            if inserted:
                await conn.execute(
                    """
                    INSERT INTO ems_event_audit_log (event_id, user_id, action, details)
                    VALUES ($1, NULL, 'created', $2::jsonb)
                    """,
                    inserted,
                    json.dumps({"source_kind": SOURCE_KIND, "source_ref": source_ref}),
                )
            else:
                await conn.execute(
                    """
                    UPDATE ems_events
                    SET title = $2, doc = $3::jsonb, narrative = $4,
                        location_id = $5, updated_at = NOW()
                    WHERE company_id = $1 AND source_kind = $6 AND source_ref = $7
                      AND status = 'logged'
                    """,
                    company_id,
                    f"Schedule warning: {row['employee_name'] or 'Employee'}",
                    json.dumps(details),
                    f"{row['employee_name'] or 'Employee'} is assigned to a shift while {warning.lower()}.",
                    row["location_id"],
                    SOURCE_KIND,
                    source_ref,
                )
            changed += 1

    if shift_ids is None:
        resolved = await conn.fetchval(
            """
            WITH updated AS (
                UPDATE ems_events
                SET status = 'completed', resolution_code = 'informational',
                    resolution_note = 'The schedule warning is no longer active.',
                    resolved_at = COALESCE(resolved_at, NOW()), updated_at = NOW()
                WHERE company_id = $1 AND source_kind = $2 AND status = 'logged'
                  AND NOT (source_ref = ANY($3::text[]))
                RETURNING 1
            )
            SELECT COUNT(*) FROM updated
            """,
            company_id, SOURCE_KIND, list(active_refs),
        )
    else:
        patterns = [f"{shift_id}:%" for shift_id in shift_ids]
        resolved = await conn.fetchval(
            """
            WITH updated AS (
                UPDATE ems_events
                SET status = 'completed', resolution_code = 'informational',
                    resolution_note = 'The schedule warning is no longer active.',
                    resolved_at = COALESCE(resolved_at, NOW()), updated_at = NOW()
                WHERE company_id = $1 AND source_kind = $2 AND status = 'logged'
                  AND source_ref LIKE ANY($3::text[])
                  AND NOT (source_ref = ANY($4::text[]))
                RETURNING 1
            )
            SELECT COUNT(*) FROM updated
            """,
            company_id, SOURCE_KIND, patterns, list(active_refs),
        )
    return {"created_or_updated": changed, "resolved": int(resolved or 0)}
