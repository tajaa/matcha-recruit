"""Read-only, deterministic context used by the schedule Huume surface."""

from __future__ import annotations

import json
from datetime import date, datetime, time, timedelta, timezone
from uuid import UUID

from app.database import get_connection

from .schedule_eligibility import (
    _BLOCKING_AUTHORITY_EXPR,
    _credential_problem,
    _job_credential_problem,
    local_date_at,
)


def _iso(value):
    return value.isoformat() if value is not None else None


async def get_schedule_overview(
    *, company_id: UUID, location_id: UUID, week_start: date
) -> dict:
    """Return a bounded overview for one location and one editor week.

    This is intentionally deterministic. Huume may summarize it, but the
    source of truth for staffing, notes, and break guidance stays SQL/domain
    logic rather than a model-generated schedule snapshot.
    """
    start = datetime.combine(week_start, time.min, tzinfo=timezone.utc)
    end = start + timedelta(days=7)
    async with get_connection() as conn:
        location = await conn.fetchrow(
            """
            SELECT id, name, address, city, state, zipcode
            FROM business_locations
            WHERE id=$1 AND company_id=$2 AND is_active IS NOT FALSE
            """,
            location_id,
            company_id,
        )
        if not location:
            return {"status": "not_found", "message": "That location is not available."}
        shifts = await conn.fetch(
            """
            WITH bounded_shifts AS (
                SELECT s.id, s.role, s.department, s.starts_at, s.ends_at,
                       s.required_staff, s.status, s.kind, s.notes,
                       COUNT(*) OVER () AS total_shift_count
                FROM schedule_shifts s
                WHERE s.company_id=$1 AND s.location_id=$2
                  AND s.status <> 'cancelled'
                  AND s.starts_at >= $3 AND s.starts_at < $4
                ORDER BY s.starts_at, s.id
                LIMIT 500
            )
            SELECT b.id, b.role, b.department, b.starts_at, b.ends_at,
                   b.required_staff, b.status, b.kind, b.notes,
                   b.total_shift_count,
                   COALESCE(
                       json_agg(
                           json_build_object(
                               'employee_id', a.employee_id,
                               'name', TRIM(COALESCE(e.first_name, '') || ' ' || COALESCE(e.last_name, '')),
                               'status', a.status,
                               'manager_note', a.manager_note,
                               'manager_note_visible_to_employee', a.manager_note_visible_to_employee,
                               'compliance_guidance', a.compliance_guidance
                           ) ORDER BY e.first_name, e.last_name, a.employee_id
                       ) FILTER (WHERE a.employee_id IS NOT NULL),
                       '[]'::json
                   ) AS assignments
            FROM bounded_shifts b
            LEFT JOIN schedule_shift_assignments a ON a.shift_id=b.id
            LEFT JOIN employees e ON e.id=a.employee_id
            GROUP BY b.id, b.role, b.department, b.starts_at, b.ends_at,
                     b.required_staff, b.status, b.kind, b.notes, b.total_shift_count
            ORDER BY b.starts_at, b.id
            """,
            company_id,
            location_id,
            start,
            end,
        )
    by_shift: dict[str, dict] = {}
    for row in shifts:
        key = str(row["id"])
        assignments = row["assignments"]
        if isinstance(assignments, str):
            try:
                assignments = json.loads(assignments)
            except (TypeError, ValueError):
                assignments = []
        item = by_shift.setdefault(key, {
            "id": key,
            "role": row["role"],
            "department": row["department"],
            "starts_at": _iso(row["starts_at"]),
            "ends_at": _iso(row["ends_at"]),
            "required_staff": row["required_staff"],
            "status": row["status"],
            "kind": row["kind"],
            "notes": row["notes"],
            "assignments": [],
        })
        item["assignments"] = [
            {
                **assignment,
                "employee_id": str(assignment["employee_id"]),
            }
            for assignment in assignments
            if isinstance(assignment, dict) and assignment.get("employee_id")
        ]
    result = list(by_shift.values())
    total_shift_count = int(shifts[0]["total_shift_count"]) if shifts else 0
    return {
        "status": "ok",
        "location": dict(location),
        "week_start": week_start.isoformat(),
        "week_end": (week_start + timedelta(days=6)).isoformat(),
        "shift_count": len(result),
        "total_shift_count": total_shift_count,
        "truncated": total_shift_count > len(result),
        "open_staffing_count": sum(
            max(0, (s["required_staff"] or 0) - len(s["assignments"])) for s in result
        ),
        "shifts": result,
    }


async def list_schedule_eligibility_cases(*, company_id: UUID, location_id: UUID) -> dict:
    async with get_connection() as conn:
        rows = await conn.fetch(
            f"""
            SELECT c.id, c.employee_id, c.requirement_type, c.status, c.job_id,
                   c.expires_at AS case_expires_at, c.blocking_reason_code,
                   c.legal_basis, c.next_escalation_at,
                   e.first_name, e.last_name,
                   e.start_date AS employee_start_date,
                   e.created_at::date AS employee_created_on,
                   ct.label AS credential_label, ct.has_expiration,
                   ecr.status AS current_credential_status,
                   ecr.expires_at AS current_credential_expires_at,
                   location.timezone,
                   jr.effective_from,
                   COALESCE(j.credential_grace_days, comp.default_credential_grace_days) AS grace_days,
                   CASE
                       WHEN c.requirement_type <> 'credential' THEN NULL
                       WHEN c.job_id IS NOT NULL THEN jr.id IS NOT NULL
                       -- _BLOCKING_AUTHORITY_EXPR is written for a WHERE clause,
                       -- where SQL NULL excludes the row (= not blocking). It goes
                       -- NULL routinely here (a requirement with no template makes
                       -- the crt operand NULL), so a SELECT of it has to fold NULL
                       -- down to false or this reads the opposite of the canonical
                       -- checks in schedule_eligibility.
                       ELSE COALESCE((
                           ecr.is_required = true AND ecr.applies_company_wide = true
                           AND {_BLOCKING_AUTHORITY_EXPR}
                       ), false)
                   END AS is_schedule_blocking
            FROM schedule_eligibility_cases c
            JOIN employees e ON e.id=c.employee_id
            LEFT JOIN companies comp ON comp.id=c.company_id
            LEFT JOIN employee_credential_requirements ecr
              ON c.requirement_type='credential' AND ecr.id=c.requirement_id
            LEFT JOIN scoped_credential_types ct ON ct.id=ecr.credential_type_id
            LEFT JOIN credential_requirement_templates crt ON crt.id=ecr.template_id
            LEFT JOIN schedule_jobs j ON j.id=c.job_id AND j.company_id=c.company_id
            LEFT JOIN schedule_job_credential_requirements jr
              ON jr.company_id=c.company_id AND jr.job_id=c.job_id
             AND jr.credential_type_id=ecr.credential_type_id
             AND jr.is_required AND jr.schedule_blocking
            LEFT JOIN business_locations location ON location.id=c.location_id
            WHERE c.company_id=$1 AND c.location_id=$2
              AND c.status IN ('warning_open','removal_requested','keep_acknowledged')
            ORDER BY c.next_escalation_at NULLS FIRST, c.expires_at
            LIMIT 200
            """,
            company_id, location_id,
        )
    cases = []
    instant = datetime.now(timezone.utc)
    for row in rows:
        current_problem = None
        # A case is a remediation record; whether it still BLOCKS is the
        # canonical requirement's answer. Mirror schedule_eligibility_violations
        # exactly — a tenant opt-out template, a cleared is_required/
        # applies_company_wide, or a removed job rule means the assignment path
        # allows the shift, so this must not claim otherwise.
        if (
            row["requirement_type"] == "credential"
            and row["current_credential_status"] is not None
            and row["is_schedule_blocking"] is True
        ):
            evidence = {
                "label": row["credential_label"],
                "has_expiration": row["has_expiration"],
                "status": row["current_credential_status"],
                "expires_at": row["current_credential_expires_at"],
            }
            as_of = local_date_at(instant, row["timezone"])
            if row.get("job_id") is not None and row.get("effective_from") is not None:
                # Job-scoped cases carry the new-hire grace window the
                # assignment path honors via _job_credential_problem.
                current_problem = _job_credential_problem(
                    {
                        **evidence,
                        "effective_from": row["effective_from"],
                        "grace_days": row["grace_days"] or 0,
                        "employee_start_date": row["employee_start_date"],
                        "employee_created_on": row["employee_created_on"],
                    },
                    as_of=as_of,
                )
            else:
                current_problem = _credential_problem(evidence, as_of=as_of)
        cases.append({
            "id": str(row["id"]), "employee_id": str(row["employee_id"]),
            "employee_name": " ".join(filter(None, [row["first_name"], row["last_name"]])),
            "requirement_type": row["requirement_type"], "status": row["status"],
            "blocking_reason_code": row["blocking_reason_code"],
            # This is the historical date that opened the case, not a claim
            # about the current credential. Give it an unambiguous name so a
            # model cannot relabel it as the live expiration.
            "case_expired_on": _iso(row["case_expires_at"]),
            "credential_label": row["credential_label"],
            "current_credential_status": row["current_credential_status"],
            "current_credential_expires_at": _iso(row["current_credential_expires_at"]),
            "currently_blocks_scheduling": (
                current_problem is not None
                if row["requirement_type"] == "credential"
                else None
            ),
            "current_block_reason": current_problem[1] if current_problem else None,
            "legal_basis": row["legal_basis"],
            "next_escalation_at": _iso(row["next_escalation_at"]),
        })
    return {
        "status": "ok",
        "policy": (
            "An eligibility case is a remediation record, not an independent assignment block. "
            "For credentials, currently_blocks_scheduling and current_block_reason come from the "
            "canonical requirement; case_expired_on is historical. Assignment confirmation still "
            "rechecks the canonical requirement for each shift."
        ),
        "cases": cases,
    }
