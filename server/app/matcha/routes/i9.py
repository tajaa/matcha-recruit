"""I-9 Employment Eligibility Verification Tracking.

Endpoints for managing I-9 records:
- CRUD operations on I-9 records
- Expiring document alerts
- Incomplete I-9 tracking
- Compliance summary dashboard
"""

import logging
from datetime import date, datetime
from typing import Optional
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel

from ...database import get_connection
from ..dependencies import require_admin_or_client, get_client_company_id
from ...core.models.auth import CurrentUser

logger = logging.getLogger(__name__)

router = APIRouter()

VALID_STATUSES = {"pending_section1", "pending_section2", "complete", "reverification_needed", "reverified"}
VALID_LIST_USED = {"list_a", "list_b_c"}


# ---------------------------------------------------------------------------
# Pydantic models
# ---------------------------------------------------------------------------

class I9CreateRequest(BaseModel):
    employee_id: UUID
    notes: Optional[str] = None


class I9UpdateRequest(BaseModel):
    status: Optional[str] = None
    section1_completed_date: Optional[date] = None
    section2_completed_date: Optional[date] = None
    document_title: Optional[str] = None
    list_used: Optional[str] = None
    document_number: Optional[str] = None
    issuing_authority: Optional[str] = None
    expiration_date: Optional[date] = None
    reverification_date: Optional[date] = None
    reverification_document: Optional[str] = None
    reverification_expiration: Optional[date] = None
    everify_case_number: Optional[str] = None
    everify_status: Optional[str] = None
    notes: Optional[str] = None


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _row_to_dict(row) -> dict:
    """Convert an asyncpg Record to a JSON-safe dict with string UUIDs."""
    d = dict(row)
    for key, val in d.items():
        if isinstance(val, UUID):
            d[key] = str(val)
        elif isinstance(val, (date, datetime)):
            d[key] = val.isoformat()
    return d


# ---------------------------------------------------------------------------
# Endpoints
# ---------------------------------------------------------------------------

@router.post("")
async def create_i9(
    body: I9CreateRequest,
    user: CurrentUser = Depends(require_admin_or_client),
    company_id: UUID = Depends(get_client_company_id),
):
    """Create an I-9 record for an employee."""
    if not company_id:
        raise HTTPException(status_code=400, detail="No company associated with this account")

    async with get_connection() as conn:
        # Verify employee belongs to this company (employees use org_id)
        emp = await conn.fetchrow(
            "SELECT id, org_id FROM employees WHERE id = $1",
            body.employee_id,
        )
        if not emp:
            raise HTTPException(status_code=404, detail="Employee not found")
        if emp["org_id"] != company_id:
            raise HTTPException(status_code=404, detail="Employee not found in your organization")

        try:
            row = await conn.fetchrow(
                """
                INSERT INTO i9_records (company_id, employee_id, status, notes)
                VALUES ($1, $2, 'pending_section1', $3)
                RETURNING *
                """,
                company_id,
                body.employee_id,
                body.notes,
            )
        except Exception as e:
            if "unique" in str(e).lower() or "duplicate" in str(e).lower():
                raise HTTPException(status_code=409, detail="I-9 record already exists for this employee")
            raise

        return _row_to_dict(row)


@router.get("")
async def list_i9(
    status: Optional[str] = Query(None),
    expiring_within_days: Optional[int] = Query(None),
    user: CurrentUser = Depends(require_admin_or_client),
    company_id: UUID = Depends(get_client_company_id),
):
    """List I-9 records for the company."""
    if not company_id:
        return []

    if status and status not in VALID_STATUSES:
        raise HTTPException(status_code=400, detail=f"Invalid status. Must be one of: {sorted(VALID_STATUSES)}")

    async with get_connection() as conn:
        query = "SELECT * FROM i9_records WHERE company_id = $1"
        params: list = [company_id]
        idx = 2

        if status:
            query += f" AND status = ${idx}"
            params.append(status)
            idx += 1

        if expiring_within_days is not None:
            query += f" AND expiration_date IS NOT NULL AND expiration_date <= CURRENT_DATE + ${idx} * INTERVAL '1 day'"
            params.append(expiring_within_days)
            idx += 1

        query += " ORDER BY created_at DESC"
        rows = await conn.fetch(query, *params)
        return [_row_to_dict(r) for r in rows]


@router.get("/expiring")
async def get_expiring(
    days: int = Query(90, ge=1),
    user: CurrentUser = Depends(require_admin_or_client),
    company_id: UUID = Depends(get_client_company_id),
):
    """Employees with documents expiring within N days."""
    if not company_id:
        return []

    async with get_connection() as conn:
        rows = await conn.fetch(
            """
            SELECT i9.*, e.first_name, e.last_name
            FROM i9_records i9
            JOIN employees e ON e.id = i9.employee_id
            WHERE i9.company_id = $1
              AND i9.expiration_date IS NOT NULL
              AND i9.expiration_date <= CURRENT_DATE + $2 * INTERVAL '1 day'
              AND i9.status IN ('complete', 'reverified')
            ORDER BY i9.expiration_date ASC
            """,
            company_id,
            days,
        )
        results = []
        for r in rows:
            d = _row_to_dict(r)
            d["first_name"] = r["first_name"]
            d["last_name"] = r["last_name"]
            results.append(d)
        return results


@router.get("/incomplete")
async def get_incomplete(
    user: CurrentUser = Depends(require_admin_or_client),
    company_id: UUID = Depends(get_client_company_id),
):
    """Employees missing I-9 or with incomplete I-9."""
    if not company_id:
        return {"no_record": [], "incomplete": []}

    async with get_connection() as conn:
        # Employees with no I-9 record at all
        no_record = await conn.fetch(
            """
            SELECT e.id, e.first_name, e.last_name, e.email
            FROM employees e
            LEFT JOIN i9_records i9 ON i9.employee_id = e.id
            WHERE e.org_id = $1
              AND i9.id IS NULL
            ORDER BY e.last_name, e.first_name
            """,
            company_id,
        )

        # Employees with incomplete I-9 status
        incomplete = await conn.fetch(
            """
            SELECT i9.*, e.first_name, e.last_name, e.email
            FROM i9_records i9
            JOIN employees e ON e.id = i9.employee_id
            WHERE i9.company_id = $1
              AND i9.status NOT IN ('complete', 'reverified')
            ORDER BY i9.created_at ASC
            """,
            company_id,
        )

        return {
            "no_record": [_row_to_dict(r) for r in no_record],
            "incomplete": [_row_to_dict(r) for r in incomplete],
        }


@router.get("/compliance-summary")
async def get_compliance_summary(
    user: CurrentUser = Depends(require_admin_or_client),
    company_id: UUID = Depends(get_client_company_id),
):
    """Return I-9 compliance summary for the company."""
    if not company_id:
        return {
            "total_employees": 0,
            "complete_count": 0,
            "incomplete_count": 0,
            "expiring_soon_count": 0,
            "overdue_count": 0,
            "completion_rate": 0.0,
        }

    async with get_connection() as conn:
        total_employees = await conn.fetchval(
            "SELECT COUNT(*) FROM employees WHERE org_id = $1",
            company_id,
        )

        complete_count = await conn.fetchval(
            "SELECT COUNT(*) FROM i9_records WHERE company_id = $1 AND status IN ('complete', 'reverified')",
            company_id,
        )

        incomplete_count = total_employees - complete_count

        expiring_soon_count = await conn.fetchval(
            """
            SELECT COUNT(*) FROM i9_records
            WHERE company_id = $1
              AND expiration_date IS NOT NULL
              AND expiration_date <= CURRENT_DATE + 90 * INTERVAL '1 day'
              AND expiration_date > CURRENT_DATE
              AND status IN ('complete', 'reverified')
            """,
            company_id,
        )

        overdue_count = await conn.fetchval(
            """
            SELECT COUNT(*) FROM i9_records
            WHERE company_id = $1
              AND expiration_date IS NOT NULL
              AND expiration_date <= CURRENT_DATE
              AND status IN ('complete', 'reverified')
            """,
            company_id,
        )

        completion_rate = round((complete_count / total_employees * 100), 1) if total_employees > 0 else 0.0

        return {
            "total_employees": total_employees,
            "complete_count": complete_count,
            "incomplete_count": incomplete_count,
            "expiring_soon_count": expiring_soon_count,
            "overdue_count": overdue_count,
            "completion_rate": completion_rate,
        }


@router.get("/{employee_id}")
async def get_i9_by_employee(
    employee_id: UUID,
    user: CurrentUser = Depends(require_admin_or_client),
    company_id: UUID = Depends(get_client_company_id),
):
    """Get I-9 record for a specific employee."""
    if not company_id:
        raise HTTPException(status_code=404, detail="I-9 record not found")

    async with get_connection() as conn:
        row = await conn.fetchrow(
            """
            SELECT i9.*, e.first_name, e.last_name
            FROM i9_records i9
            JOIN employees e ON e.id = i9.employee_id
            WHERE i9.employee_id = $1
              AND i9.company_id = $2
            """,
            employee_id,
            company_id,
        )
        if not row:
            raise HTTPException(status_code=404, detail="I-9 record not found")

        d = _row_to_dict(row)
        d["first_name"] = row["first_name"]
        d["last_name"] = row["last_name"]
        return d


@router.put("/{record_id}")
async def update_i9(
    record_id: UUID,
    body: I9UpdateRequest,
    user: CurrentUser = Depends(require_admin_or_client),
    company_id: UUID = Depends(get_client_company_id),
):
    """Update an I-9 record."""
    if not company_id:
        raise HTTPException(status_code=404, detail="I-9 record not found")

    # Validate enum fields
    if body.status is not None and body.status not in VALID_STATUSES:
        raise HTTPException(status_code=400, detail=f"Invalid status. Must be one of: {sorted(VALID_STATUSES)}")
    if body.list_used is not None and body.list_used not in VALID_LIST_USED:
        raise HTTPException(status_code=400, detail=f"Invalid list_used. Must be one of: {sorted(VALID_LIST_USED)}")

    async with get_connection() as conn:
        # Fetch the current record
        current = await conn.fetchrow(
            "SELECT * FROM i9_records WHERE id = $1 AND company_id = $2",
            record_id,
            company_id,
        )
        if not current:
            raise HTTPException(status_code=404, detail="I-9 record not found")

        current_status = current["status"]

        # Build dynamic update
        updates = []
        params = []
        idx = 1

        update_fields = body.model_dump(exclude_none=True)
        if not update_fields:
            raise HTTPException(status_code=400, detail="No updates provided")

        # Determine effective status after auto-advance logic
        effective_status = body.status if body.status else current_status

        # Auto-advance: section1_completed_date set while pending_section1
        if body.section1_completed_date is not None and effective_status == "pending_section1":
            if "status" not in update_fields:
                update_fields["status"] = "pending_section2"
                effective_status = "pending_section2"

        # Auto-advance: section2_completed_date set while pending_section2
        if body.section2_completed_date is not None and effective_status == "pending_section2":
            if "status" not in update_fields or update_fields["status"] == "pending_section2":
                update_fields["status"] = "complete"
                effective_status = "complete"

        for field, value in update_fields.items():
            updates.append(f"{field} = ${idx}")
            params.append(value)
            idx += 1

        updates.append("updated_at = NOW()")

        params.append(record_id)
        params.append(company_id)

        query = f"""
            UPDATE i9_records
            SET {', '.join(updates)}
            WHERE id = ${idx} AND company_id = ${idx + 1}
            RETURNING *
        """

        row = await conn.fetchrow(query, *params)
        if not row:
            raise HTTPException(status_code=404, detail="I-9 record not found")

        return _row_to_dict(row)
