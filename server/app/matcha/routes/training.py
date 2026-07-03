"""Training Compliance API Routes.

Manage training requirements, assign/track employee training records,
and view compliance dashboards for overdue and completed trainings.
"""

import json
import logging
import os
from datetime import date, datetime, timedelta
from typing import Any, Optional
from uuid import UUID, uuid4

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from pydantic import BaseModel, Field

from ...database import get_connection
from ..dependencies import (
    require_admin_or_client,
    get_client_company_id,
    require_employee_record,
)
from ..services.training_grading import (
    grade_quiz as _grade_quiz_pure,
    parse_jsonb as _parse_jsonb,
    sanitize_lesson_template as _sanitize_lesson_template,
)
from ...core.models.auth import CurrentUser

logger = logging.getLogger(__name__)

router = APIRouter()

VALID_TRAINING_TYPES = {"harassment_prevention", "safety", "food_handler", "osha", "custom"}
VALID_STATUSES = {"assigned", "in_progress", "completed", "expired", "waived"}


# ---------------------------------------------------------------------------
# Pydantic models
# ---------------------------------------------------------------------------

class TrainingRequirementCreate(BaseModel):
    title: str
    description: Optional[str] = None
    training_type: str
    jurisdiction: Optional[str] = None
    frequency_months: Optional[int] = None
    applies_to: str = "all"


class TrainingRequirementUpdate(BaseModel):
    title: Optional[str] = None
    description: Optional[str] = None
    training_type: Optional[str] = None
    jurisdiction: Optional[str] = None
    frequency_months: Optional[int] = None
    applies_to: Optional[str] = None
    is_active: Optional[bool] = None


class TrainingRecordCreate(BaseModel):
    employee_id: UUID
    requirement_id: Optional[UUID] = None
    title: str
    training_type: str
    due_date: Optional[date] = None
    provider: Optional[str] = None
    notes: Optional[str] = None


class TrainingRecordUpdate(BaseModel):
    status: Optional[str] = None
    completed_date: Optional[date] = None
    expiration_date: Optional[date] = None
    provider: Optional[str] = None
    certificate_number: Optional[str] = None
    score: Optional[float] = None
    notes: Optional[str] = None


class BulkAssignRequest(BaseModel):
    requirement_id: UUID


# ---------------------------------------------------------------------------
# Requirements CRUD
# ---------------------------------------------------------------------------

@router.post("/requirements")
async def create_requirement(
    body: TrainingRequirementCreate,
    user: CurrentUser = Depends(require_admin_or_client),
    company_id: UUID = Depends(get_client_company_id),
):
    """Create a new training requirement."""
    if not company_id:
        raise HTTPException(status_code=400, detail="No company found")

    if body.training_type not in VALID_TRAINING_TYPES:
        raise HTTPException(
            status_code=400,
            detail=f"Invalid training_type. Must be one of: {sorted(VALID_TRAINING_TYPES)}",
        )

    async with get_connection() as conn:
        row = await conn.fetchrow(
            """
            INSERT INTO training_requirements
                (company_id, title, description, training_type, jurisdiction, frequency_months, applies_to)
            VALUES ($1, $2, $3, $4, $5, $6, $7)
            RETURNING *
            """,
            company_id,
            body.title,
            body.description,
            body.training_type,
            body.jurisdiction,
            body.frequency_months,
            body.applies_to,
        )
        return _requirement_to_dict(row)


@router.get("/requirements")
async def list_requirements(
    is_active: bool = Query(default=True),
    user: CurrentUser = Depends(require_admin_or_client),
    company_id: UUID = Depends(get_client_company_id),
):
    """List training requirements for the company."""
    if not company_id:
        return []

    async with get_connection() as conn:
        rows = await conn.fetch(
            """
            SELECT * FROM training_requirements
            WHERE company_id = $1 AND is_active = $2
            ORDER BY created_at DESC
            """,
            company_id,
            is_active,
        )
        return [_requirement_to_dict(r) for r in rows]


@router.get("/requirements/{requirement_id}")
async def get_requirement(
    requirement_id: UUID,
    user: CurrentUser = Depends(require_admin_or_client),
    company_id: UUID = Depends(get_client_company_id),
):
    """Get a single training requirement by id."""
    if not company_id:
        raise HTTPException(status_code=404, detail="Requirement not found")
    async with get_connection() as conn:
        row = await conn.fetchrow(
            "SELECT * FROM training_requirements WHERE id = $1 AND company_id = $2",
            requirement_id, company_id,
        )
        if not row:
            raise HTTPException(status_code=404, detail="Requirement not found")
        return _requirement_to_dict(row)


@router.put("/requirements/{requirement_id}")
async def update_requirement(
    requirement_id: UUID,
    body: TrainingRequirementUpdate,
    user: CurrentUser = Depends(require_admin_or_client),
    company_id: UUID = Depends(get_client_company_id),
):
    """Update a training requirement."""
    if not company_id:
        raise HTTPException(status_code=404, detail="Requirement not found")

    if body.training_type is not None and body.training_type not in VALID_TRAINING_TYPES:
        raise HTTPException(
            status_code=400,
            detail=f"Invalid training_type. Must be one of: {sorted(VALID_TRAINING_TYPES)}",
        )

    updates: list[str] = []
    params: list = []
    idx = 1

    for field_name, col_name in [
        ("title", "title"),
        ("description", "description"),
        ("training_type", "training_type"),
        ("jurisdiction", "jurisdiction"),
        ("frequency_months", "frequency_months"),
        ("applies_to", "applies_to"),
        ("is_active", "is_active"),
    ]:
        value = getattr(body, field_name)
        if value is not None:
            updates.append(f"{col_name} = ${idx}")
            params.append(value)
            idx += 1

    if not updates:
        raise HTTPException(status_code=400, detail="No updates provided")

    updates.append("updated_at = NOW()")
    params.append(requirement_id)
    params.append(company_id)

    row = await _execute_update(
        f"""
        UPDATE training_requirements
        SET {', '.join(updates)}
        WHERE id = ${idx} AND company_id = ${idx + 1}
        RETURNING *
        """,
        params,
    )
    if not row:
        raise HTTPException(status_code=404, detail="Requirement not found")

    return _requirement_to_dict(row)


@router.delete("/requirements/{requirement_id}")
async def delete_requirement(
    requirement_id: UUID,
    user: CurrentUser = Depends(require_admin_or_client),
    company_id: UUID = Depends(get_client_company_id),
):
    """Soft-delete a training requirement (set is_active=false)."""
    if not company_id:
        raise HTTPException(status_code=404, detail="Requirement not found")

    async with get_connection() as conn:
        row = await conn.fetchrow(
            """
            UPDATE training_requirements
            SET is_active = false, updated_at = NOW()
            WHERE id = $1 AND company_id = $2
            RETURNING id
            """,
            requirement_id,
            company_id,
        )
        if not row:
            raise HTTPException(status_code=404, detail="Requirement not found")

        return {"status": "deleted", "requirement_id": str(requirement_id)}


# ---------------------------------------------------------------------------
# Records CRUD
# ---------------------------------------------------------------------------

@router.post("/records")
async def create_record(
    body: TrainingRecordCreate,
    user: CurrentUser = Depends(require_admin_or_client),
    company_id: UUID = Depends(get_client_company_id),
):
    """Assign a training record to an employee."""
    if not company_id:
        raise HTTPException(status_code=400, detail="No company found")

    if body.training_type not in VALID_TRAINING_TYPES:
        raise HTTPException(
            status_code=400,
            detail=f"Invalid training_type. Must be one of: {sorted(VALID_TRAINING_TYPES)}",
        )

    async with get_connection() as conn:
        # Verify employee belongs to company
        emp = await conn.fetchval(
            "SELECT id FROM employees WHERE id = $1 AND org_id = $2",
            body.employee_id,
            company_id,
        )
        if not emp:
            raise HTTPException(status_code=404, detail="Employee not found in your organization")

        # If requirement_id provided, verify it belongs to the company
        if body.requirement_id:
            req = await conn.fetchval(
                "SELECT id FROM training_requirements WHERE id = $1 AND company_id = $2",
                body.requirement_id,
                company_id,
            )
            if not req:
                raise HTTPException(status_code=404, detail="Training requirement not found")

        row = await conn.fetchrow(
            """
            INSERT INTO training_records
                (company_id, employee_id, requirement_id, title, training_type, due_date, provider, notes)
            VALUES ($1, $2, $3, $4, $5, $6, $7, $8)
            RETURNING *
            """,
            company_id,
            body.employee_id,
            body.requirement_id,
            body.title,
            body.training_type,
            body.due_date,
            body.provider,
            body.notes,
        )
        return _record_to_dict(row)


@router.post("/records/bulk-assign")
async def bulk_assign(
    body: BulkAssignRequest,
    user: CurrentUser = Depends(require_admin_or_client),
    company_id: UUID = Depends(get_client_company_id),
):
    """Assign a training requirement to active employees who match its `applies_to`
    (supervisor / nonsupervisor / all) and `jurisdiction` (work_state filter).

    Records `assigned_by` for audit. Skips employees with an existing active
    assignment for the same requirement via the partial unique index.
    """
    if not company_id:
        raise HTTPException(status_code=400, detail="No company found")

    async with get_connection() as conn:
        requirement = await conn.fetchrow(
            "SELECT * FROM training_requirements WHERE id = $1 AND company_id = $2 AND is_active = true",
            body.requirement_id,
            company_id,
        )
        if not requirement:
            raise HTTPException(status_code=404, detail="Training requirement not found")

        applies_to = (requirement["applies_to"] or "all").lower()
        jurisdiction = requirement["jurisdiction"]  # may be None or e.g. 'CA'

        employees = await conn.fetch(
            """
            SELECT id FROM employees
            WHERE org_id = $1
              AND (termination_date IS NULL OR termination_date > CURRENT_DATE)
              AND ($2 = 'all'
                   OR ($2 = 'supervisor' AND is_supervisor = TRUE)
                   OR ($2 = 'nonsupervisor' AND is_supervisor = FALSE))
              AND ($3::varchar IS NULL OR work_state = $3)
            """,
            company_id,
            applies_to,
            jurisdiction,
        )

        if not employees:
            return {"assigned_count": 0, "requirement_id": str(body.requirement_id), "message": "No matching active employees found"}

        assigned_date = date.today()
        due_date = None
        if requirement["frequency_months"]:
            due_date = assigned_date + timedelta(days=requirement["frequency_months"] * 30)

        # Build batch VALUES and use ON CONFLICT to skip existing active assignments
        values_parts = []
        params = [
            company_id,
            requirement["id"],
            requirement["title"],
            requirement["training_type"],
            assigned_date,
            due_date,
            user.id,  # assigned_by
        ]
        base_idx = len(params) + 1
        for i, emp in enumerate(employees):
            values_parts.append(f"($1, ${base_idx + i}, $2, $3, $4, $5, $6, $7)")
            params.append(emp["id"])

        result = await conn.execute(
            f"""
            INSERT INTO training_records
                (company_id, employee_id, requirement_id, title, training_type,
                 assigned_date, due_date, assigned_by)
            VALUES {', '.join(values_parts)}
            ON CONFLICT (employee_id, requirement_id)
                WHERE status IN ('assigned', 'in_progress')
            DO NOTHING
            """,
            *params,
        )
        # asyncpg returns "INSERT 0 N" where N is rows inserted
        count = int(result.split()[-1]) if result else 0

        return {"assigned_count": count, "requirement_id": str(body.requirement_id)}


@router.get("/records")
async def list_records(
    employee_id: Optional[UUID] = Query(default=None),
    status: Optional[str] = Query(default=None),
    overdue: Optional[bool] = Query(default=None),
    user: CurrentUser = Depends(require_admin_or_client),
    company_id: UUID = Depends(get_client_company_id),
):
    """List training records with optional filters."""
    if not company_id:
        return []

    if status is not None and status not in VALID_STATUSES:
        raise HTTPException(
            status_code=400,
            detail=f"Invalid status. Must be one of: {sorted(VALID_STATUSES)}",
        )

    query = "SELECT * FROM training_records WHERE company_id = $1"
    params: list = [company_id]
    idx = 2

    if employee_id is not None:
        query += f" AND employee_id = ${idx}"
        params.append(employee_id)
        idx += 1

    if status is not None:
        query += f" AND status = ${idx}"
        params.append(status)
        idx += 1

    if overdue is True:
        query += " AND due_date < CURRENT_DATE AND status NOT IN ('completed', 'waived', 'expired')"

    query += " ORDER BY created_at DESC"

    async with get_connection() as conn:
        rows = await conn.fetch(query, *params)
        return [_record_to_dict(r) for r in rows]


@router.put("/records/{record_id}")
async def update_record(
    record_id: UUID,
    body: TrainingRecordUpdate,
    user: CurrentUser = Depends(require_admin_or_client),
    company_id: UUID = Depends(get_client_company_id),
):
    """Update a training record."""
    if not company_id:
        raise HTTPException(status_code=404, detail="Record not found")

    if body.status is not None and body.status not in VALID_STATUSES:
        raise HTTPException(
            status_code=400,
            detail=f"Invalid status. Must be one of: {sorted(VALID_STATUSES)}",
        )

    async with get_connection() as conn:
        # Fetch current record
        existing = await conn.fetchrow(
            "SELECT * FROM training_records WHERE id = $1 AND company_id = $2",
            record_id,
            company_id,
        )
        if not existing:
            raise HTTPException(status_code=404, detail="Record not found")

        updates: list[str] = []
        params: list = []
        idx = 1

        # If status is being set to 'completed' and no completed_date provided, set it to today
        completed_date = body.completed_date
        if body.status == "completed" and completed_date is None and existing["completed_date"] is None:
            completed_date = date.today()

        for field_name, col_name in [
            ("status", "status"),
            ("provider", "provider"),
            ("certificate_number", "certificate_number"),
            ("score", "score"),
            ("notes", "notes"),
        ]:
            value = getattr(body, field_name)
            if value is not None:
                updates.append(f"{col_name} = ${idx}")
                params.append(value)
                idx += 1

        if completed_date is not None:
            updates.append(f"completed_date = ${idx}")
            params.append(completed_date)
            idx += 1

        if body.expiration_date is not None:
            updates.append(f"expiration_date = ${idx}")
            params.append(body.expiration_date)
            idx += 1

        # Auto-compute expiration_date if completing and linked requirement has frequency_months
        if body.status == "completed" and body.expiration_date is None and existing["requirement_id"]:
            req = await conn.fetchrow(
                "SELECT frequency_months FROM training_requirements WHERE id = $1",
                existing["requirement_id"],
            )
            if req and req["frequency_months"]:
                effective_completed = completed_date or existing["completed_date"] or date.today()
                auto_expiration = effective_completed + timedelta(days=req["frequency_months"] * 30)
                updates.append(f"expiration_date = ${idx}")
                params.append(auto_expiration)
                idx += 1

        if not updates:
            raise HTTPException(status_code=400, detail="No updates provided")

        updates.append("updated_at = NOW()")
        params.append(record_id)
        params.append(company_id)

        row = await conn.fetchrow(
            f"""
            UPDATE training_records
            SET {', '.join(updates)}
            WHERE id = ${idx} AND company_id = ${idx + 1}
            RETURNING *
            """,
            *params,
        )

        if not row:
            raise HTTPException(status_code=404, detail="Record not found")

        return _record_to_dict(row)


# ---------------------------------------------------------------------------
# Compliance dashboard & overdue
# ---------------------------------------------------------------------------

@router.get("/compliance")
async def compliance_dashboard(
    user: CurrentUser = Depends(require_admin_or_client),
    company_id: UUID = Depends(get_client_company_id),
):
    """Return compliance summary for each active training requirement."""
    if not company_id:
        return []

    async with get_connection() as conn:
        rows = await conn.fetch(
            """
            SELECT
                tr.id,
                tr.title,
                tr.training_type,
                tr.jurisdiction,
                tr.frequency_months,
                COUNT(rec.id) AS total_assigned,
                COUNT(rec.id) FILTER (WHERE rec.status = 'completed') AS completed,
                COUNT(rec.id) FILTER (
                    WHERE rec.due_date < CURRENT_DATE
                      AND rec.status IN ('assigned', 'in_progress')
                ) AS overdue
            FROM training_requirements tr
            LEFT JOIN training_records rec ON rec.requirement_id = tr.id
            WHERE tr.company_id = $1 AND tr.is_active = true
            GROUP BY tr.id
            ORDER BY tr.title
            """,
            company_id,
        )

        return [
            {
                "requirement_id": str(r["id"]),
                "title": r["title"],
                "training_type": r["training_type"],
                "jurisdiction": r["jurisdiction"],
                "frequency_months": r["frequency_months"],
                "total_assigned": r["total_assigned"],
                "completed": r["completed"],
                "overdue": r["overdue"],
            }
            for r in rows
        ]


@router.get("/overdue")
async def overdue_trainings(
    user: CurrentUser = Depends(require_admin_or_client),
    company_id: UUID = Depends(get_client_company_id),
):
    """Return employees with overdue training records."""
    if not company_id:
        return []

    async with get_connection() as conn:
        rows = await conn.fetch(
            """
            SELECT
                rec.id AS record_id,
                rec.title AS training_title,
                rec.training_type,
                rec.due_date,
                rec.assigned_date,
                rec.status,
                e.id AS employee_id,
                e.first_name,
                e.last_name,
                e.email
            FROM training_records rec
            JOIN employees e ON e.id = rec.employee_id
            WHERE rec.company_id = $1
              AND rec.due_date < CURRENT_DATE
              AND rec.status IN ('assigned', 'in_progress')
            ORDER BY rec.due_date ASC
            """,
            company_id,
        )

        return [
            {
                "record_id": str(r["record_id"]),
                "training_title": r["training_title"],
                "training_type": r["training_type"],
                "due_date": r["due_date"].isoformat() if r["due_date"] else None,
                "assigned_date": r["assigned_date"].isoformat() if r["assigned_date"] else None,
                "status": r["status"],
                "employee_id": str(r["employee_id"]),
                "first_name": r["first_name"],
                "last_name": r["last_name"],
                "email": r["email"],
            }
            for r in rows
        ]


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _requirement_to_dict(row) -> dict:
    """Convert a training_requirements row to a JSON-friendly dict."""
    return {
        "id": str(row["id"]),
        "company_id": str(row["company_id"]),
        "title": row["title"],
        "description": row["description"],
        "training_type": row["training_type"],
        "jurisdiction": row["jurisdiction"],
        "frequency_months": row["frequency_months"],
        "applies_to": row["applies_to"],
        "is_active": row["is_active"],
        "created_at": row["created_at"].isoformat() if row["created_at"] else None,
        "updated_at": row["updated_at"].isoformat() if row["updated_at"] else None,
    }


def _record_to_dict(row) -> dict:
    """Convert a training_records row to a JSON-friendly dict."""
    return {
        "id": str(row["id"]),
        "company_id": str(row["company_id"]),
        "employee_id": str(row["employee_id"]),
        "requirement_id": str(row["requirement_id"]) if row["requirement_id"] else None,
        "title": row["title"],
        "training_type": row["training_type"],
        "status": row["status"],
        "assigned_date": row["assigned_date"].isoformat() if row["assigned_date"] else None,
        "due_date": row["due_date"].isoformat() if row["due_date"] else None,
        "completed_date": row["completed_date"].isoformat() if row["completed_date"] else None,
        "expiration_date": row["expiration_date"].isoformat() if row["expiration_date"] else None,
        "provider": row["provider"],
        "certificate_number": row["certificate_number"],
        "score": float(row["score"]) if row["score"] is not None else None,
        "notes": row["notes"],
        "created_at": row["created_at"].isoformat() if row["created_at"] else None,
        "updated_at": row["updated_at"].isoformat() if row["updated_at"] else None,
    }


async def _execute_update(query: str, params: list):
    """Run an UPDATE ... RETURNING query and return the row."""
    async with get_connection() as conn:
        return await conn.fetchrow(query, *params)


# ---------------------------------------------------------------------------
# Employee-side endpoints (require_employee_record)
# ---------------------------------------------------------------------------


class QuizSubmitRequest(BaseModel):
    answers: dict[str, str] = Field(..., description="{question_id: chosen_key}")
    elapsed_seconds: Optional[int] = None


class AttestRequest(BaseModel):
    attestation_text: str = Field(
        default=(
            "I attest that I personally completed the training modules and assessment "
            "without assistance, and that the answers I submitted are my own."
        ),
        max_length=2000,
    )


async def _load_record_for_employee(conn, record_id: UUID, employee_id: UUID) -> dict:
    row = await conn.fetchrow(
        """
        SELECT r.*,
               req.template_id, req.required_minutes AS req_required_minutes,
               req.pass_score_percent AS req_pass_score_percent,
               req.frequency_months AS req_frequency_months,
               req.applies_to AS req_applies_to,
               req.jurisdiction AS req_jurisdiction
        FROM training_records r
        LEFT JOIN training_requirements req ON req.id = r.requirement_id
        WHERE r.id = $1 AND r.employee_id = $2
        """,
        record_id, employee_id,
    )
    if not row:
        raise HTTPException(status_code=404, detail="Training record not found")
    return dict(row)


async def _load_template_for_record(conn, record: dict) -> dict:
    template_id = record.get("template_id")
    if not template_id:
        raise HTTPException(
            status_code=409,
            detail="This training record has no lesson template attached. Contact your administrator.",
        )
    row = await conn.fetchrow(
        "SELECT * FROM training_lesson_templates WHERE id = $1 AND is_active = TRUE",
        template_id,
    )
    if not row:
        raise HTTPException(
            status_code=409,
            detail="Lesson template is no longer active.",
        )
    return dict(row)


@router.get("/records/me")
async def list_my_records(
    employee=Depends(require_employee_record),
):
    """List training records assigned to the current employee."""
    async with get_connection() as conn:
        rows = await conn.fetch(
            """
            SELECT r.*, req.required_minutes AS req_required_minutes,
                   req.template_id
            FROM training_records r
            LEFT JOIN training_requirements req ON req.id = r.requirement_id
            WHERE r.employee_id = $1
            ORDER BY
                CASE r.status
                    WHEN 'in_progress' THEN 0
                    WHEN 'assigned' THEN 1
                    WHEN 'completed' THEN 2
                    ELSE 3
                END,
                r.due_date NULLS LAST,
                r.created_at DESC
            """,
            employee["id"],
        )
        out = []
        for r in rows:
            d = _record_to_dict(r)
            d["required_minutes"] = r["req_required_minutes"]
            d["has_lesson"] = r["template_id"] is not None
            d["started_at"] = r["started_at"].isoformat() if r["started_at"] else None
            d["attested_at"] = r["attested_at"].isoformat() if r["attested_at"] else None
            out.append(d)
        return out


@router.get("/records/{record_id}")
async def get_record(
    record_id: UUID,
    user: CurrentUser = Depends(require_admin_or_client),
    company_id: UUID = Depends(get_client_company_id),
):
    """Get a single training record by id. Must be registered after
    /records/me — a variable {record_id} segment would otherwise shadow
    that literal path since both are single-segment GETs."""
    if not company_id:
        raise HTTPException(status_code=404, detail="Record not found")
    async with get_connection() as conn:
        row = await conn.fetchrow(
            "SELECT * FROM training_records WHERE id = $1 AND company_id = $2",
            record_id, company_id,
        )
        if not row:
            raise HTTPException(status_code=404, detail="Record not found")
        return _record_to_dict(row)


@router.get("/records/{record_id}/lesson")
async def get_lesson(
    record_id: UUID,
    employee=Depends(require_employee_record),
):
    """Return sanitized lesson + quiz (no correct_key, no rationale)."""
    async with get_connection() as conn:
        record = await _load_record_for_employee(conn, record_id, employee["id"])
        template = await _load_template_for_record(conn, record)

    sanitized = _sanitize_lesson_template(template["lesson_content"], template["quiz"])
    return {
        "record_id": str(record_id),
        "template_id": str(template["id"]),
        "template_key": template["template_key"],
        "variant": template["variant"],
        "title": sanitized["title"] or template["title"],
        "summary_for_certificate": sanitized["summary_for_certificate"],
        "required_minutes": template["required_minutes"],
        "pass_score_percent": template["pass_score_percent"],
        "sections": sanitized["sections"],
        "quiz": sanitized["quiz"],
        "started_at": record["started_at"].isoformat() if record["started_at"] else None,
        "status": record["status"],
    }


@router.post("/records/{record_id}/start")
async def start_lesson(
    record_id: UUID,
    employee=Depends(require_employee_record),
):
    """Mark training as in_progress + record started_at (idempotent)."""
    async with get_connection() as conn:
        record = await _load_record_for_employee(conn, record_id, employee["id"])

        if record["status"] in ("completed", "expired", "waived"):
            raise HTTPException(
                status_code=400,
                detail=f"Training is {record['status']} and cannot be started again.",
            )

        if record["started_at"]:
            return {
                "started_at": record["started_at"].isoformat(),
                "status": record["status"],
                "already_started": True,
            }

        row = await conn.fetchrow(
            """
            UPDATE training_records
            SET started_at = NOW(),
                status = CASE WHEN status = 'assigned' THEN 'in_progress' ELSE status END,
                updated_at = NOW()
            WHERE id = $1
            RETURNING started_at, status
            """,
            record_id,
        )
        return {
            "started_at": row["started_at"].isoformat(),
            "status": row["status"],
            "already_started": False,
        }


def _grade_quiz(quiz_payload: Any, submitted_answers: dict[str, str]) -> tuple[float, int, int]:
    """Thin alias for the pure-function grader, kept for in-route call sites."""
    return _grade_quiz_pure(quiz_payload, submitted_answers)


@router.post("/records/{record_id}/quiz")
async def submit_quiz(
    record_id: UUID,
    body: QuizSubmitRequest,
    employee=Depends(require_employee_record),
):
    """Submit quiz answers. Enforces minimum seat-time. Writes attempt audit row."""
    async with get_connection() as conn:
        record = await _load_record_for_employee(conn, record_id, employee["id"])
        template = await _load_template_for_record(conn, record)

        if record["status"] in ("completed", "expired", "waived"):
            raise HTTPException(
                status_code=400,
                detail=f"Training is {record['status']}; cannot submit a new attempt.",
            )

        if not record["started_at"]:
            raise HTTPException(
                status_code=400,
                detail="Training has not been started. Call /start first.",
            )

        required_minutes = (
            record.get("req_required_minutes") or template["required_minutes"] or 0
        )
        required_seconds = required_minutes * 60
        elapsed_seconds = (datetime.utcnow() - record["started_at"].replace(tzinfo=None)).total_seconds()

        if not os.getenv("TRAINING_DEV_SKIP_TIMER") and elapsed_seconds < required_seconds:
            remaining = int(required_seconds - elapsed_seconds)
            raise HTTPException(
                status_code=400,
                detail=f"Minimum seat time not met. {remaining} seconds remaining.",
            )

        score_percent, correct, total = _grade_quiz(template["quiz"], body.answers)
        pass_score = (
            record.get("req_pass_score_percent")
            or template["pass_score_percent"]
            or 80
        )
        passed = score_percent >= pass_score

        # Determine attempt_number
        prev_max = await conn.fetchval(
            "SELECT COALESCE(MAX(attempt_number), 0) FROM training_quiz_attempts WHERE record_id = $1",
            record_id,
        )
        attempt_number = int(prev_max) + 1

        await conn.execute(
            """
            INSERT INTO training_quiz_attempts
              (record_id, employee_id, company_id, attempt_number, answers,
               score_percent, passed, elapsed_seconds, started_at)
            VALUES ($1, $2, $3, $4, $5::jsonb, $6, $7, $8, $9)
            """,
            record_id,
            employee["id"],
            record["company_id"],
            attempt_number,
            json.dumps(body.answers),
            score_percent,
            passed,
            int(body.elapsed_seconds) if body.elapsed_seconds is not None else int(elapsed_seconds),
            record["started_at"],
        )

        return {
            "record_id": str(record_id),
            "attempt_number": attempt_number,
            "score_percent": score_percent,
            "correct": correct,
            "total": total,
            "passed": passed,
            "pass_score_percent": pass_score,
        }


@router.post("/records/{record_id}/attest")
async def attest_completion(
    record_id: UUID,
    body: AttestRequest,
    request: Request,
    employee=Depends(require_employee_record),
):
    """Finalize training: requires a passed quiz attempt. Generates PDF cert,
    uploads to S3, sets completion fields, returns presigned cert URL."""
    from ..services.training_pdf import (
        new_certificate_id,
        render_certificate_pdf,
        upload_certificate,
    )

    async with get_connection() as conn:
        record = await _load_record_for_employee(conn, record_id, employee["id"])
        template = await _load_template_for_record(conn, record)

        if record["status"] == "completed" and record["certificate_url"]:
            raise HTTPException(
                status_code=400,
                detail="Training already completed and attested.",
            )

        latest = await conn.fetchrow(
            """
            SELECT score_percent, passed
            FROM training_quiz_attempts
            WHERE record_id = $1
            ORDER BY attempt_number DESC
            LIMIT 1
            """,
            record_id,
        )
        if not latest or not latest["passed"]:
            raise HTTPException(
                status_code=400,
                detail="A passing quiz attempt is required before attestation.",
            )

        company_row = await conn.fetchrow(
            "SELECT name FROM companies WHERE id = $1", record["company_id"],
        )
        company_name = company_row["name"] if company_row else "Your Company"

        completed_date = date.today()
        frequency_months = (
            record.get("req_frequency_months") or template["frequency_months"] or 24
        )
        expiration_date = completed_date + timedelta(days=int(frequency_months) * 30)
        retention_until = date(
            completed_date.year + 4, completed_date.month, completed_date.day
        ) if completed_date.month != 2 or completed_date.day != 29 else date(
            completed_date.year + 4, completed_date.month, 28
        )

        certificate_id = new_certificate_id()
        attested_at = datetime.utcnow()
        attestation_ip = (
            request.headers.get("x-forwarded-for", "").split(",")[0].strip()
            or request.client.host
            if request.client else ""
        ) or "unknown"

        variant_label = (
            "Supervisor (2 hours)"
            if (template["variant"] or "").lower() == "supervisor"
            else "Employee (1 hour)"
        )

        # Render + upload PDF
        try:
            pdf_bytes = await render_certificate_pdf(
                employee_first=employee["first_name"],
                employee_last=employee["last_name"],
                company_name=company_name,
                training_title=template["title"] or record["title"],
                variant_label=variant_label,
                completed_date=completed_date,
                score_percent=float(latest["score_percent"]),
                required_minutes=int(template["required_minutes"]),
                expiration_date=expiration_date,
                attested_at=attested_at,
                attestation_ip=attestation_ip,
                certificate_id=certificate_id,
            )
        except asyncio.TimeoutError:
            raise HTTPException(status_code=504, detail="Certificate generation timed out. Please retry.")
        except Exception as exc:  # pragma: no cover — surface storage/render errors
            logger.exception("Certificate render failed for record %s: %s", record_id, exc)
            raise HTTPException(status_code=500, detail="Failed to generate certificate.")

        try:
            cert_uri = await upload_certificate(
                pdf_bytes=pdf_bytes,
                company_id=record["company_id"],
                employee_id=employee["id"],
                certificate_id=certificate_id,
            )
        except Exception as exc:
            logger.exception("Certificate upload failed for record %s: %s", record_id, exc)
            raise HTTPException(status_code=500, detail="Failed to store certificate.")

        # Persist completion + attestation
        await conn.execute(
            """
            UPDATE training_records
            SET status = 'completed',
                completed_date = $1,
                expiration_date = $2,
                retention_until = $3,
                attested_at = $4,
                attestation_ip = $5,
                attestation_text = $6,
                certificate_id = $7,
                certificate_url = $8,
                score = $9,
                updated_at = NOW()
            WHERE id = $10
            """,
            completed_date,
            expiration_date,
            retention_until,
            attested_at,
            attestation_ip[:45],
            body.attestation_text,
            certificate_id,
            cert_uri,
            float(latest["score_percent"]),
            record_id,
        )

    # Email completion notice with cert attachment (best-effort, non-blocking failure)
    try:
        from ...core.services.email import get_email_service
        email_svc = get_email_service()
        if email_svc.is_configured() and employee.get("email"):
            await email_svc.send_training_completion_email(
                to_email=employee["email"],
                to_name=f"{employee['first_name']} {employee['last_name']}",
                training_title=template["title"] or record["title"],
                score_percent=float(latest["score_percent"]),
                expiration_date=expiration_date,
                pdf_bytes=pdf_bytes,
            )
    except Exception as exc:
        logger.warning("Training completion email failed for record %s: %s", record_id, exc)

    return {
        "record_id": str(record_id),
        "status": "completed",
        "completed_date": completed_date.isoformat(),
        "expiration_date": expiration_date.isoformat(),
        "score_percent": float(latest["score_percent"]),
        "certificate_id": str(certificate_id),
    }


@router.get("/records/{record_id}/certificate-url")
async def get_certificate_url(
    record_id: UUID,
    user: CurrentUser = Depends(require_admin_or_client),
):
    """Admin/client-side certificate fetch. Returns presigned URL."""
    company_id = await get_client_company_id(user) if user.role != "admin" else None

    async with get_connection() as conn:
        if user.role == "admin":
            row = await conn.fetchrow(
                "SELECT certificate_url, company_id FROM training_records WHERE id = $1",
                record_id,
            )
        else:
            row = await conn.fetchrow(
                "SELECT certificate_url FROM training_records WHERE id = $1 AND company_id = $2",
                record_id, company_id,
            )
        if not row or not row["certificate_url"]:
            raise HTTPException(status_code=404, detail="Certificate not found")

    from ...core.services.storage import get_storage
    storage = get_storage()
    presigned = storage.get_presigned_download_url(row["certificate_url"], expires_in=900)
    if not presigned:
        raise HTTPException(status_code=500, detail="Failed to generate download URL")
    return {"url": presigned}


@router.get("/records/me/{record_id}/certificate-url")
async def get_my_certificate_url(
    record_id: UUID,
    employee=Depends(require_employee_record),
):
    """Employee fetches presigned cert URL for their own record."""
    async with get_connection() as conn:
        row = await conn.fetchrow(
            "SELECT certificate_url FROM training_records WHERE id = $1 AND employee_id = $2",
            record_id, employee["id"],
        )
        if not row or not row["certificate_url"]:
            raise HTTPException(status_code=404, detail="Certificate not found")

    from ...core.services.storage import get_storage
    storage = get_storage()
    presigned = storage.get_presigned_download_url(row["certificate_url"], expires_in=900)
    if not presigned:
        raise HTTPException(status_code=500, detail="Failed to generate download URL")
    return {"url": presigned}
