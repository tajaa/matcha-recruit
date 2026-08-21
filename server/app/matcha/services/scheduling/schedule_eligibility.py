"""Schedule-blocking eligibility checks and manager-decision case creation."""
from __future__ import annotations

import json
from datetime import date
from uuid import UUID


def _basis(value) -> dict:
    if isinstance(value, str):
        try:
            value = json.loads(value)
        except json.JSONDecodeError:
            return {}
    return value if isinstance(value, dict) else {}


async def schedule_eligibility_violations(conn, company_id: UUID, *, employee_id: UUID, shift_date: date) -> list[dict]:
    """Only human-approved requirements explicitly marked schedule-blocking block new assignments."""
    rows = await conn.fetch(
        """
        SELECT ecr.id, ecr.due_date, ct.label, crt.legal_basis
        FROM employee_credential_requirements ecr
        JOIN employees e ON e.id = ecr.employee_id
        JOIN credential_requirement_templates crt ON crt.id = ecr.template_id
        LEFT JOIN credential_types ct ON ct.id = ecr.credential_type_id
        WHERE e.org_id = $1 AND ecr.employee_id = $2
          AND ecr.status NOT IN ('verified', 'waived')
          AND crt.schedule_blocking = true
          AND crt.review_status IN ('approved', 'auto_approved')
          AND ecr.due_date IS NOT NULL AND ecr.due_date < $3
        """, company_id, employee_id, shift_date,
    )
    permits = await conn.fetch(
        """SELECT id, expires_at, legal_basis FROM employee_work_permits
           WHERE company_id = $1 AND employee_id = $2 AND schedule_blocking = true AND expires_at < $3""",
        company_id, employee_id, shift_date,
    )
    out = []
    for row in rows:
        out.append({"check": "schedule_eligibility", "severity": "block", "code": "credential_expired",
                    "message": f"{row['label'] or 'Required credential'} expired {row['due_date'].isoformat()} and blocks new scheduling.",
                    "statute": _basis(row['legal_basis']).get('citation'), "state": ""})
    for row in permits:
        out.append({"check": "schedule_eligibility", "severity": "block", "code": "minor_work_permit_expired",
                    "message": f"Work permit expired {row['expires_at'].isoformat()} and blocks new scheduling.",
                    "statute": _basis(row['legal_basis']).get('citation'), "state": ""})
    return out


async def open_expired_eligibility_cases(conn, company_id: UUID, *, as_of: date) -> list[UUID]:
    """Idempotently create manager-decision cases; never removes assignments."""
    rows = await conn.fetch(
        """
        SELECT ecr.id AS requirement_id, ecr.employee_id, ecr.due_date AS expires_at, crt.legal_basis
        FROM employee_credential_requirements ecr JOIN employees e ON e.id = ecr.employee_id
        JOIN credential_requirement_templates crt ON crt.id = ecr.template_id
        WHERE e.org_id = $1 AND ecr.status NOT IN ('verified','waived')
          AND crt.schedule_blocking AND crt.review_status IN ('approved','auto_approved')
          AND ecr.due_date < $2
        """, company_id, as_of,
    )
    opened: list[UUID] = []
    for row in rows:
        case_id = await conn.fetchval(
            """
            INSERT INTO schedule_eligibility_cases
                (company_id, employee_id, requirement_type, requirement_id, blocking_reason_code, status, expires_at, legal_basis)
            VALUES ($1,$2,'credential',$3,'credential_expired','removal_requested',$4,$5::jsonb)
            ON CONFLICT DO NOTHING RETURNING id
            """, company_id, row['employee_id'], row['requirement_id'], row['expires_at'], json.dumps(row['legal_basis'] or {}),
        )
        if case_id:
            opened.append(case_id)
            await conn.execute(
                """INSERT INTO schedule_eligibility_case_assignments(case_id, shift_id, employee_id, shift_starts_at)
                   SELECT $1, s.id, $2, s.starts_at FROM schedule_shifts s
                   JOIN schedule_shift_assignments a ON a.shift_id=s.id AND a.employee_id=$2
                   WHERE s.company_id=$3 AND s.status <> 'cancelled' AND s.starts_at::date >= $4
                   ON CONFLICT DO NOTHING""",
                case_id, row['employee_id'], company_id, as_of,
            )
    return opened
