"""
CRUD routes for Phase 2 pre-termination data models:
  - Progressive Discipline
  - Agency Charges
  - Post-Termination Claims
"""
import json
import logging
from datetime import datetime, date
from typing import Any, List, Optional
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field

from ...database import get_connection
from ...core.dependencies import get_current_user
from ..dependencies import require_admin_or_client, get_client_company_id
from ...core.models.auth import CurrentUser

logger = logging.getLogger(__name__)

router = APIRouter()


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _normalize_json(value, default=None):
    """Parse JSONB string from asyncpg if needed."""
    if value is None:
        return default
    if isinstance(value, (dict, list)):
        return value
    if isinstance(value, str):
        try:
            return json.loads(value)
        except (json.JSONDecodeError, ValueError):
            return default
    return default


# ---------------------------------------------------------------------------
# Validation sets
# ---------------------------------------------------------------------------

VALID_DISCIPLINE_TYPES = {"verbal_warning", "written_warning", "pip", "final_warning", "suspension"}
VALID_DISCIPLINE_STATUSES = {"active", "completed", "expired", "escalated"}

VALID_CHARGE_TYPES = {"eeoc", "nlrb", "osha", "state_agency", "other"}
VALID_CHARGE_STATUSES = {"filed", "investigating", "mediation", "resolved", "dismissed", "litigated"}

VALID_CLAIM_STATUSES = {"filed", "investigating", "mediation", "settled", "dismissed", "litigated", "judgment"}


# ---------------------------------------------------------------------------
# Pydantic models — Progressive Discipline
# ---------------------------------------------------------------------------

class DisciplineCreateRequest(BaseModel):
    employee_id: UUID
    discipline_type: str
    issued_date: date
    description: Optional[str] = None
    expected_improvement: Optional[str] = None
    review_date: Optional[date] = None


class DisciplineUpdateRequest(BaseModel):
    status: Optional[str] = None
    outcome_notes: Optional[str] = None
    review_date: Optional[date] = None
    description: Optional[str] = None


class DisciplineResponse(BaseModel):
    id: UUID
    employee_id: UUID
    company_id: UUID
    discipline_type: str
    issued_date: date
    issued_by: UUID
    description: Optional[str]
    expected_improvement: Optional[str]
    review_date: Optional[date]
    status: str
    outcome_notes: Optional[str]
    documents: list[Any] = []
    created_at: datetime
    updated_at: datetime


# ---------------------------------------------------------------------------
# Pydantic models — Agency Charges
# ---------------------------------------------------------------------------

class AgencyChargeCreateRequest(BaseModel):
    employee_id: UUID
    charge_type: str
    filing_date: date
    charge_number: Optional[str] = None
    agency_name: Optional[str] = None
    description: Optional[str] = None


class AgencyChargeUpdateRequest(BaseModel):
    status: Optional[str] = None
    resolution_amount: Optional[float] = None
    resolution_date: Optional[date] = None
    resolution_notes: Optional[str] = None
    description: Optional[str] = None


class AgencyChargeResponse(BaseModel):
    id: UUID
    employee_id: UUID
    company_id: UUID
    charge_type: str
    charge_number: Optional[str]
    filing_date: date
    agency_name: Optional[str]
    status: str
    description: Optional[str]
    resolution_amount: Optional[float]
    resolution_date: Optional[date]
    resolution_notes: Optional[str]
    documents: list[Any] = []
    created_by: UUID
    created_at: datetime
    updated_at: datetime


# ---------------------------------------------------------------------------
# Pydantic models — Post-Termination Claims
# ---------------------------------------------------------------------------

class PostTermClaimCreateRequest(BaseModel):
    employee_id: UUID
    pre_termination_check_id: Optional[UUID] = None
    claim_type: str
    filed_date: date
    description: Optional[str] = None


class PostTermClaimUpdateRequest(BaseModel):
    status: Optional[str] = None
    resolution_amount: Optional[float] = None
    resolution_date: Optional[date] = None
    description: Optional[str] = None


class PostTermClaimResponse(BaseModel):
    id: UUID
    employee_id: UUID
    company_id: UUID
    pre_termination_check_id: Optional[UUID]
    offboarding_case_id: Optional[UUID]
    claim_type: str
    filed_date: date
    status: str
    resolution_amount: Optional[float]
    resolution_date: Optional[date]
    description: Optional[str]
    created_by: UUID
    created_at: datetime
    updated_at: datetime


# ---------------------------------------------------------------------------
# Row → Response helpers
# ---------------------------------------------------------------------------

def _to_discipline_response(row) -> DisciplineResponse:
    return DisciplineResponse(
        id=row["id"],
        employee_id=row["employee_id"],
        company_id=row["company_id"],
        discipline_type=row["discipline_type"],
        issued_date=row["issued_date"],
        issued_by=row["issued_by"],
        description=row.get("description"),
        expected_improvement=row.get("expected_improvement"),
        review_date=row.get("review_date"),
        status=row["status"],
        outcome_notes=row.get("outcome_notes"),
        documents=_normalize_json(row.get("documents"), []),
        created_at=row["created_at"],
        updated_at=row["updated_at"],
    )


def _to_charge_response(row) -> AgencyChargeResponse:
    return AgencyChargeResponse(
        id=row["id"],
        employee_id=row["employee_id"],
        company_id=row["company_id"],
        charge_type=row["charge_type"],
        charge_number=row.get("charge_number"),
        filing_date=row["filing_date"],
        agency_name=row.get("agency_name"),
        status=row["status"],
        description=row.get("description"),
        resolution_amount=float(row["resolution_amount"]) if row.get("resolution_amount") is not None else None,
        resolution_date=row.get("resolution_date"),
        resolution_notes=row.get("resolution_notes"),
        documents=_normalize_json(row.get("documents"), []),
        created_by=row["created_by"],
        created_at=row["created_at"],
        updated_at=row["updated_at"],
    )


def _to_claim_response(row) -> PostTermClaimResponse:
    return PostTermClaimResponse(
        id=row["id"],
        employee_id=row["employee_id"],
        company_id=row["company_id"],
        pre_termination_check_id=row.get("pre_termination_check_id"),
        offboarding_case_id=row.get("offboarding_case_id"),
        claim_type=row["claim_type"],
        filed_date=row["filed_date"],
        status=row["status"],
        resolution_amount=float(row["resolution_amount"]) if row.get("resolution_amount") is not None else None,
        resolution_date=row.get("resolution_date"),
        description=row.get("description"),
        created_by=row["created_by"],
        created_at=row["created_at"],
        updated_at=row["updated_at"],
    )


# ===========================================================================
# Progressive Discipline endpoints
# ===========================================================================

@router.post("/discipline", response_model=DisciplineResponse, status_code=201)
async def create_discipline_record(
    request: DisciplineCreateRequest,
    current_user: CurrentUser = Depends(require_admin_or_client),
):
    """Create a progressive discipline record for an employee."""
    if request.discipline_type not in VALID_DISCIPLINE_TYPES:
        raise HTTPException(
            status_code=400,
            detail=f"Invalid discipline_type. Must be one of: {sorted(VALID_DISCIPLINE_TYPES)}",
        )

    company_id = await get_client_company_id(current_user)

    async with get_connection() as conn:
        # Verify employee belongs to company
        employee = await conn.fetchrow(
            "SELECT id FROM employees WHERE id = $1 AND org_id = $2",
            request.employee_id,
            company_id,
        )
        if not employee:
            raise HTTPException(status_code=404, detail="Employee not found")

        row = await conn.fetchrow(
            """
            INSERT INTO progressive_discipline (
                employee_id, company_id, discipline_type, issued_date, issued_by,
                description, expected_improvement, review_date
            )
            VALUES ($1, $2, $3, $4, $5, $6, $7, $8)
            RETURNING *
            """,
            request.employee_id,
            company_id,
            request.discipline_type,
            request.issued_date,
            current_user.id,
            request.description,
            request.expected_improvement,
            request.review_date,
        )
        return _to_discipline_response(row)


@router.get("/discipline/employee/{employee_id}", response_model=List[DisciplineResponse])
async def list_discipline_records(
    employee_id: UUID,
    current_user: CurrentUser = Depends(require_admin_or_client),
):
    """List all progressive discipline records for an employee, ordered by issued_date DESC."""
    company_id = await get_client_company_id(current_user)

    async with get_connection() as conn:
        # Verify employee belongs to company
        employee = await conn.fetchrow(
            "SELECT id FROM employees WHERE id = $1 AND org_id = $2",
            employee_id,
            company_id,
        )
        if not employee:
            raise HTTPException(status_code=404, detail="Employee not found")

        rows = await conn.fetch(
            """
            SELECT * FROM progressive_discipline
            WHERE employee_id = $1 AND company_id = $2
            ORDER BY issued_date DESC
            """,
            employee_id,
            company_id,
        )
        return [_to_discipline_response(r) for r in rows]


@router.get("/discipline/{record_id}", response_model=DisciplineResponse)
async def get_discipline_record(
    record_id: UUID,
    current_user: CurrentUser = Depends(require_admin_or_client),
):
    """Get a single progressive discipline record."""
    company_id = await get_client_company_id(current_user)

    async with get_connection() as conn:
        row = await conn.fetchrow(
            "SELECT * FROM progressive_discipline WHERE id = $1 AND company_id = $2",
            record_id,
            company_id,
        )
        if not row:
            raise HTTPException(status_code=404, detail="Discipline record not found")
        return _to_discipline_response(row)


@router.patch("/discipline/{record_id}", response_model=DisciplineResponse)
async def update_discipline_record(
    record_id: UUID,
    request: DisciplineUpdateRequest,
    current_user: CurrentUser = Depends(require_admin_or_client),
):
    """Update a progressive discipline record (status, notes, review_date, description)."""
    company_id = await get_client_company_id(current_user)

    async with get_connection() as conn:
        existing = await conn.fetchrow(
            "SELECT * FROM progressive_discipline WHERE id = $1 AND company_id = $2",
            record_id,
            company_id,
        )
        if not existing:
            raise HTTPException(status_code=404, detail="Discipline record not found")

        updates = []
        values = []
        idx = 1

        if request.status is not None:
            if request.status not in VALID_DISCIPLINE_STATUSES:
                raise HTTPException(
                    status_code=400,
                    detail=f"Invalid status. Must be one of: {sorted(VALID_DISCIPLINE_STATUSES)}",
                )
            updates.append(f"status = ${idx}")
            values.append(request.status)
            idx += 1

        if request.outcome_notes is not None:
            updates.append(f"outcome_notes = ${idx}")
            values.append(request.outcome_notes)
            idx += 1

        if request.review_date is not None:
            updates.append(f"review_date = ${idx}")
            values.append(request.review_date)
            idx += 1

        if request.description is not None:
            updates.append(f"description = ${idx}")
            values.append(request.description)
            idx += 1

        if not updates:
            raise HTTPException(status_code=400, detail="No fields to update")

        updates.append("updated_at = NOW()")
        values.append(record_id)

        row = await conn.fetchrow(
            f"""
            UPDATE progressive_discipline
            SET {', '.join(updates)}
            WHERE id = ${idx}
            RETURNING *
            """,
            *values,
        )
        return _to_discipline_response(row)


@router.delete("/discipline/{record_id}", status_code=204)
async def delete_discipline_record(
    record_id: UUID,
    current_user: CurrentUser = Depends(require_admin_or_client),
):
    """Delete a progressive discipline record."""
    company_id = await get_client_company_id(current_user)

    async with get_connection() as conn:
        result = await conn.execute(
            "DELETE FROM progressive_discipline WHERE id = $1 AND company_id = $2",
            record_id,
            company_id,
        )
        if result == "DELETE 0":
            raise HTTPException(status_code=404, detail="Discipline record not found")


# ===========================================================================
# Agency Charges endpoints
# ===========================================================================

@router.post("/agency-charges", response_model=AgencyChargeResponse, status_code=201)
async def create_agency_charge(
    request: AgencyChargeCreateRequest,
    current_user: CurrentUser = Depends(require_admin_or_client),
):
    """Create an agency charge record for an employee."""
    if request.charge_type not in VALID_CHARGE_TYPES:
        raise HTTPException(
            status_code=400,
            detail=f"Invalid charge_type. Must be one of: {sorted(VALID_CHARGE_TYPES)}",
        )

    company_id = await get_client_company_id(current_user)

    async with get_connection() as conn:
        employee = await conn.fetchrow(
            "SELECT id FROM employees WHERE id = $1 AND org_id = $2",
            request.employee_id,
            company_id,
        )
        if not employee:
            raise HTTPException(status_code=404, detail="Employee not found")

        row = await conn.fetchrow(
            """
            INSERT INTO agency_charges (
                employee_id, company_id, charge_type, filing_date,
                charge_number, agency_name, description, created_by
            )
            VALUES ($1, $2, $3, $4, $5, $6, $7, $8)
            RETURNING *
            """,
            request.employee_id,
            company_id,
            request.charge_type,
            request.filing_date,
            request.charge_number,
            request.agency_name,
            request.description,
            current_user.id,
        )
        return _to_charge_response(row)


@router.get("/agency-charges/employee/{employee_id}", response_model=List[AgencyChargeResponse])
async def list_agency_charges(
    employee_id: UUID,
    current_user: CurrentUser = Depends(require_admin_or_client),
):
    """List all agency charges for an employee, ordered by filing_date DESC."""
    company_id = await get_client_company_id(current_user)

    async with get_connection() as conn:
        employee = await conn.fetchrow(
            "SELECT id FROM employees WHERE id = $1 AND org_id = $2",
            employee_id,
            company_id,
        )
        if not employee:
            raise HTTPException(status_code=404, detail="Employee not found")

        rows = await conn.fetch(
            """
            SELECT * FROM agency_charges
            WHERE employee_id = $1 AND company_id = $2
            ORDER BY filing_date DESC
            """,
            employee_id,
            company_id,
        )
        return [_to_charge_response(r) for r in rows]


@router.get("/agency-charges/{charge_id}", response_model=AgencyChargeResponse)
async def get_agency_charge(
    charge_id: UUID,
    current_user: CurrentUser = Depends(require_admin_or_client),
):
    """Get a single agency charge record."""
    company_id = await get_client_company_id(current_user)

    async with get_connection() as conn:
        row = await conn.fetchrow(
            "SELECT * FROM agency_charges WHERE id = $1 AND company_id = $2",
            charge_id,
            company_id,
        )
        if not row:
            raise HTTPException(status_code=404, detail="Agency charge not found")
        return _to_charge_response(row)


@router.patch("/agency-charges/{charge_id}", response_model=AgencyChargeResponse)
async def update_agency_charge(
    charge_id: UUID,
    request: AgencyChargeUpdateRequest,
    current_user: CurrentUser = Depends(require_admin_or_client),
):
    """Update an agency charge record (status, resolution details, description)."""
    company_id = await get_client_company_id(current_user)

    async with get_connection() as conn:
        existing = await conn.fetchrow(
            "SELECT * FROM agency_charges WHERE id = $1 AND company_id = $2",
            charge_id,
            company_id,
        )
        if not existing:
            raise HTTPException(status_code=404, detail="Agency charge not found")

        updates = []
        values = []
        idx = 1

        if request.status is not None:
            if request.status not in VALID_CHARGE_STATUSES:
                raise HTTPException(
                    status_code=400,
                    detail=f"Invalid status. Must be one of: {sorted(VALID_CHARGE_STATUSES)}",
                )
            updates.append(f"status = ${idx}")
            values.append(request.status)
            idx += 1

        if request.resolution_amount is not None:
            updates.append(f"resolution_amount = ${idx}")
            values.append(request.resolution_amount)
            idx += 1

        if request.resolution_date is not None:
            updates.append(f"resolution_date = ${idx}")
            values.append(request.resolution_date)
            idx += 1

        if request.resolution_notes is not None:
            updates.append(f"resolution_notes = ${idx}")
            values.append(request.resolution_notes)
            idx += 1

        if request.description is not None:
            updates.append(f"description = ${idx}")
            values.append(request.description)
            idx += 1

        if not updates:
            raise HTTPException(status_code=400, detail="No fields to update")

        updates.append("updated_at = NOW()")
        values.append(charge_id)

        row = await conn.fetchrow(
            f"""
            UPDATE agency_charges
            SET {', '.join(updates)}
            WHERE id = ${idx}
            RETURNING *
            """,
            *values,
        )
        return _to_charge_response(row)


@router.delete("/agency-charges/{charge_id}", status_code=204)
async def delete_agency_charge(
    charge_id: UUID,
    current_user: CurrentUser = Depends(require_admin_or_client),
):
    """Delete an agency charge record."""
    company_id = await get_client_company_id(current_user)

    async with get_connection() as conn:
        result = await conn.execute(
            "DELETE FROM agency_charges WHERE id = $1 AND company_id = $2",
            charge_id,
            company_id,
        )
        if result == "DELETE 0":
            raise HTTPException(status_code=404, detail="Agency charge not found")


# ===========================================================================
# Post-Termination Claims endpoints
# ===========================================================================

@router.post("/claims", response_model=PostTermClaimResponse, status_code=201)
async def create_post_term_claim(
    request: PostTermClaimCreateRequest,
    current_user: CurrentUser = Depends(require_admin_or_client),
):
    """Create a post-termination claim record for an employee."""
    company_id = await get_client_company_id(current_user)

    async with get_connection() as conn:
        employee = await conn.fetchrow(
            "SELECT id FROM employees WHERE id = $1 AND org_id = $2",
            request.employee_id,
            company_id,
        )
        if not employee:
            raise HTTPException(status_code=404, detail="Employee not found")

        # Validate pre_termination_check_id if provided
        if request.pre_termination_check_id:
            check = await conn.fetchrow(
                "SELECT id FROM pre_termination_checks WHERE id = $1 AND company_id = $2",
                request.pre_termination_check_id,
                company_id,
            )
            if not check:
                raise HTTPException(
                    status_code=404,
                    detail="Pre-termination check not found",
                )

        row = await conn.fetchrow(
            """
            INSERT INTO post_termination_claims (
                employee_id, company_id, pre_termination_check_id,
                claim_type, filed_date, description, created_by
            )
            VALUES ($1, $2, $3, $4, $5, $6, $7)
            RETURNING *
            """,
            request.employee_id,
            company_id,
            request.pre_termination_check_id,
            request.claim_type,
            request.filed_date,
            request.description,
            current_user.id,
        )
        return _to_claim_response(row)


@router.get("/claims/employee/{employee_id}", response_model=List[PostTermClaimResponse])
async def list_post_term_claims(
    employee_id: UUID,
    current_user: CurrentUser = Depends(require_admin_or_client),
):
    """List all post-termination claims for an employee, ordered by filed_date DESC."""
    company_id = await get_client_company_id(current_user)

    async with get_connection() as conn:
        employee = await conn.fetchrow(
            "SELECT id FROM employees WHERE id = $1 AND org_id = $2",
            employee_id,
            company_id,
        )
        if not employee:
            raise HTTPException(status_code=404, detail="Employee not found")

        rows = await conn.fetch(
            """
            SELECT * FROM post_termination_claims
            WHERE employee_id = $1 AND company_id = $2
            ORDER BY filed_date DESC
            """,
            employee_id,
            company_id,
        )
        return [_to_claim_response(r) for r in rows]


@router.get("/claims/company", response_model=List[PostTermClaimResponse])
async def list_company_claims(
    current_user: CurrentUser = Depends(require_admin_or_client),
):
    """List all post-termination claims for the company (for analytics)."""
    company_id = await get_client_company_id(current_user)

    async with get_connection() as conn:
        rows = await conn.fetch(
            """
            SELECT * FROM post_termination_claims
            WHERE company_id = $1
            ORDER BY filed_date DESC
            """,
            company_id,
        )
        return [_to_claim_response(r) for r in rows]


@router.get("/claims/{claim_id}", response_model=PostTermClaimResponse)
async def get_post_term_claim(
    claim_id: UUID,
    current_user: CurrentUser = Depends(require_admin_or_client),
):
    """Get a single post-termination claim record."""
    company_id = await get_client_company_id(current_user)

    async with get_connection() as conn:
        row = await conn.fetchrow(
            "SELECT * FROM post_termination_claims WHERE id = $1 AND company_id = $2",
            claim_id,
            company_id,
        )
        if not row:
            raise HTTPException(status_code=404, detail="Post-termination claim not found")
        return _to_claim_response(row)


@router.patch("/claims/{claim_id}", response_model=PostTermClaimResponse)
async def update_post_term_claim(
    claim_id: UUID,
    request: PostTermClaimUpdateRequest,
    current_user: CurrentUser = Depends(require_admin_or_client),
):
    """Update a post-termination claim (status, resolution details, description)."""
    company_id = await get_client_company_id(current_user)

    async with get_connection() as conn:
        existing = await conn.fetchrow(
            "SELECT * FROM post_termination_claims WHERE id = $1 AND company_id = $2",
            claim_id,
            company_id,
        )
        if not existing:
            raise HTTPException(status_code=404, detail="Post-termination claim not found")

        updates = []
        values = []
        idx = 1

        if request.status is not None:
            if request.status not in VALID_CLAIM_STATUSES:
                raise HTTPException(
                    status_code=400,
                    detail=f"Invalid status. Must be one of: {sorted(VALID_CLAIM_STATUSES)}",
                )
            updates.append(f"status = ${idx}")
            values.append(request.status)
            idx += 1

        if request.resolution_amount is not None:
            updates.append(f"resolution_amount = ${idx}")
            values.append(request.resolution_amount)
            idx += 1

        if request.resolution_date is not None:
            updates.append(f"resolution_date = ${idx}")
            values.append(request.resolution_date)
            idx += 1

        if request.description is not None:
            updates.append(f"description = ${idx}")
            values.append(request.description)
            idx += 1

        if not updates:
            raise HTTPException(status_code=400, detail="No fields to update")

        updates.append("updated_at = NOW()")
        values.append(claim_id)

        row = await conn.fetchrow(
            f"""
            UPDATE post_termination_claims
            SET {', '.join(updates)}
            WHERE id = ${idx}
            RETURNING *
            """,
            *values,
        )
        return _to_claim_response(row)


@router.delete("/claims/{claim_id}")
async def delete_post_term_claim(
    claim_id: UUID,
    current_user: CurrentUser = Depends(require_admin_or_client),
):
    """Delete a post-termination claim record."""
    company_id = await get_client_company_id(current_user)

    async with get_connection() as conn:
        row = await conn.fetchrow(
            "DELETE FROM post_termination_claims WHERE id = $1 AND company_id = $2 RETURNING id",
            claim_id,
            company_id,
        )
        if not row:
            raise HTTPException(status_code=404, detail="Post-termination claim not found")
        return {"message": "Claim deleted", "id": str(row["id"])}
