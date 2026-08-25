"""Schedule-blocking eligibility checks and manager-decision case creation."""
from __future__ import annotations

import json
from collections import defaultdict
from datetime import date, timedelta
from typing import Any
from uuid import UUID


def _basis(value) -> dict:
    if isinstance(value, str):
        try:
            value = json.loads(value)
        except json.JSONDecodeError:
            return {}
    return value if isinstance(value, dict) else {}


async def _schedule_blocking_requirements(conn, company_id: UUID, employee_ids: list[UUID]):
    if not employee_ids:
        return []
    return await conn.fetch(
        """
        SELECT ecr.id, ecr.employee_id, ecr.status, ecr.expires_at,
               ct.label, ct.has_expiration, crt.warning_days, crt.legal_basis
        FROM employee_credential_requirements ecr
        JOIN employees e ON e.id = ecr.employee_id
        JOIN credential_requirement_templates crt ON crt.id = ecr.template_id
        LEFT JOIN credential_types ct ON ct.id = ecr.credential_type_id
        WHERE e.org_id = $1 AND ecr.employee_id = ANY($2::uuid[])
          AND ecr.is_required = true
          AND crt.schedule_blocking = true
          AND crt.review_status IN ('approved', 'auto_approved')
        """,
        company_id, employee_ids,
    )


def _credential_problem(row, *, as_of: date) -> tuple[str, str] | None:
    """Return a stable reason code/message when a required credential is invalid."""
    label = row["label"] or "Required credential"
    if row["status"] == "waived":
        return None
    if row["status"] != "verified":
        return "credential_missing", f"{label} requires an approved credential document before scheduling."
    if row["has_expiration"] and row["expires_at"] is None:
        return "credential_expiration_unconfirmed", f"{label} requires a confirmed expiration date before scheduling."
    if row["expires_at"] is not None and row["expires_at"] < as_of:
        return "credential_expired", f"{label} expired {row['expires_at'].isoformat()} and blocks new scheduling."
    return None


async def schedule_eligibility_violations(
    conn,
    company_id: UUID,
    *,
    employee_id: UUID,
    shift_date: date,
    location_id: UUID | None = None,
    employee_age: int | None = None,
) -> list[dict]:
    """Human-approved, schedule-blocking requirements cannot be bypassed."""
    rows = await conn.fetch(
        """
        SELECT ecr.id, ecr.status, ecr.expires_at, ct.label, ct.has_expiration, crt.legal_basis
        FROM employee_credential_requirements ecr
        JOIN employees e ON e.id = ecr.employee_id
        JOIN credential_requirement_templates crt ON crt.id = ecr.template_id
        LEFT JOIN credential_types ct ON ct.id = ecr.credential_type_id
        WHERE e.org_id = $1 AND ecr.employee_id = $2
          AND ecr.is_required = true
          AND crt.schedule_blocking = true
          AND crt.review_status IN ('approved', 'auto_approved')
        """, company_id, employee_id,
    )
    permits = await conn.fetch(
        """SELECT id, location_id, issued_at, expires_at, legal_basis FROM employee_work_permits
           WHERE company_id = $1 AND employee_id = $2 AND schedule_blocking = true
             AND status = 'active' AND confirmed_on_file = true
             AND ($3::uuid IS NULL OR location_id = $3)""",
        company_id, employee_id, location_id,
    )
    out = []
    for row in rows:
        problem = _credential_problem(row, as_of=shift_date)
        if problem:
            code, message = problem
            out.append({"check": "schedule_eligibility", "severity": "block", "code": code,
                        "message": message,
                        "statute": _basis(row['legal_basis']).get('citation'), "state": ""})
    # Old direct callers do not provide an age. Preserve their expired-permit
    # behavior while write paths supply age and apply the rule only to minors.
    if employee_age is None:
        expired_permits = [row for row in permits if row["expires_at"] < shift_date]
        for row in expired_permits:
            out.append({"check": "schedule_eligibility", "severity": "block", "code": "minor_work_permit_expired",
                        "message": f"Work permit expired {row['expires_at'].isoformat()} and blocks new scheduling.",
                        "statute": _basis(row['legal_basis']).get('citation'), "state": ""})
    elif employee_age < 18 and location_id is not None:
        valid_permit = next(
            (
                row for row in permits
                if (row.get("issued_at") is None or row["issued_at"] <= shift_date)
                and row["expires_at"] >= shift_date
            ),
            None,
        )
        if valid_permit is None:
            expired = next((row for row in permits if row["expires_at"] < shift_date), None)
            if expired:
                code = "minor_work_permit_expired"
                message = f"Work permit expired {expired['expires_at'].isoformat()} and blocks new scheduling."
                statute = _basis(expired["legal_basis"]).get("citation")
            else:
                code = "minor_work_permit_missing"
                message = "A confirmed work permit is required before scheduling this minor at this location."
                statute = None
            out.append({"check": "schedule_eligibility", "severity": "block", "code": code,
                        "message": message, "statute": statute, "state": ""})
    return out


async def schedule_eligibility_roster_flags(
    conn, company_id: UUID, employee_ids: list[UUID], *, as_of: date,
) -> dict[str, dict[str, list[Any]]]:
    """Blocking and near-expiry credential details for the schedule roster."""
    result: dict[str, dict[str, list[Any]]] = defaultdict(
        lambda: {"blocking_credentials": [], "credential_warnings": [], "credential_expirations": []}
    )
    for row in await _schedule_blocking_requirements(conn, company_id, employee_ids):
        employee_id = str(row["employee_id"])
        problem = _credential_problem(row, as_of=as_of)
        if problem:
            result[employee_id]["blocking_credentials"].append(problem[1])
            continue
        if row["expires_at"] is not None:
            result[employee_id]["credential_expirations"].append({
                "label": row["label"] or "Credential",
                "expires_at": row["expires_at"].isoformat(),
            })
            warning_days = row["warning_days"] or 0
            if row["expires_at"] <= as_of + timedelta(days=warning_days):
                result[employee_id]["credential_warnings"].append(
                    f"{row['label'] or 'Credential'} expires {row['expires_at'].isoformat()}"
                )
    return result


async def open_expired_eligibility_cases(conn, company_id: UUID, *, as_of: date) -> list[UUID]:
    """Idempotently create manager-decision cases; never removes assignments."""
    rows = await conn.fetch(
        """
        SELECT ecr.id AS requirement_id, ecr.employee_id, ecr.status, ecr.expires_at, ct.label, ct.has_expiration,
               crt.legal_basis
        FROM employee_credential_requirements ecr JOIN employees e ON e.id = ecr.employee_id
        JOIN credential_requirement_templates crt ON crt.id = ecr.template_id
        LEFT JOIN credential_types ct ON ct.id = ecr.credential_type_id
        WHERE e.org_id = $1 AND ecr.is_required = true
          AND crt.schedule_blocking AND crt.review_status IN ('approved','auto_approved')
        """, company_id,
    )
    opened: list[UUID] = []
    for row in rows:
        problem = _credential_problem(row, as_of=as_of)
        if not problem:
            continue
        reason_code, _message = problem
        assignments = await conn.fetch(
            """SELECT s.id AS shift_id, s.location_id, s.starts_at
               FROM schedule_shifts s JOIN schedule_shift_assignments a ON a.shift_id=s.id
               WHERE s.company_id=$1 AND a.employee_id=$2 AND s.status <> 'cancelled'
                 AND s.location_id IS NOT NULL AND s.starts_at::date >= $3""",
            company_id, row["employee_id"], as_of,
        )
        by_location: dict[UUID, list] = {}
        for assignment in assignments:
            by_location.setdefault(assignment["location_id"], []).append(assignment)
        for location_id, location_assignments in by_location.items():
            case_id = await conn.fetchval(
                """
                INSERT INTO schedule_eligibility_cases
                    (company_id, employee_id, location_id, requirement_type, requirement_id, blocking_reason_code, status, expires_at, legal_basis)
                VALUES ($1,$2,$3,'credential',$4,$5,'removal_requested',$6,$7::jsonb)
                ON CONFLICT DO NOTHING RETURNING id
                """, company_id, row['employee_id'], location_id, row['requirement_id'], reason_code,
                row['expires_at'], json.dumps(_basis(row['legal_basis'])),
            )
            if case_id:
                opened.append(case_id)
                for assignment in location_assignments:
                    await conn.execute(
                        """INSERT INTO schedule_eligibility_case_assignments(case_id, shift_id, employee_id, shift_starts_at)
                           VALUES ($1,$2,$3,$4) ON CONFLICT DO NOTHING""",
                        case_id, assignment["shift_id"], row["employee_id"], assignment["starts_at"],
                    )
    return opened
