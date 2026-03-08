"""Training Compliance API Routes.

Manage training requirements, assign/track employee training records,
and view compliance dashboards for overdue and completed trainings.
"""

import logging
from datetime import date, timedelta
from typing import Optional
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel

from ...database import get_connection
from ..dependencies import require_admin_or_client, get_client_company_id
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
    """Assign a training requirement to all active employees."""
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

        # Find all active employees (no termination_date or termination_date in the future)
        employees = await conn.fetch(
            """
            SELECT id FROM employees
            WHERE org_id = $1
              AND (termination_date IS NULL OR termination_date > CURRENT_DATE)
            """,
            company_id,
        )

        if not employees:
            return {"assigned_count": 0, "message": "No active employees found"}

        assigned_date = date.today()
        due_date = None
        if requirement["frequency_months"]:
            due_date = assigned_date + timedelta(days=requirement["frequency_months"] * 30)

        count = 0
        for emp in employees:
            await conn.execute(
                """
                INSERT INTO training_records
                    (company_id, employee_id, requirement_id, title, training_type,
                     assigned_date, due_date)
                VALUES ($1, $2, $3, $4, $5, $6, $7)
                """,
                company_id,
                emp["id"],
                requirement["id"],
                requirement["title"],
                requirement["training_type"],
                assigned_date,
                due_date,
            )
            count += 1

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
