"""Separation Agreements API with ADEA period tracking.

Manages separation/severance agreements including OWBPA (Older Workers
Benefit Protection Act) compliance for employees age 40+, with
consideration periods, revocation windows, and group-layoff disclosures.
"""

import json
import logging
from datetime import date, timedelta
from typing import Optional
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel

from ...database import get_connection
from ..dependencies import require_admin_or_client, get_client_company_id

logger = logging.getLogger(__name__)

router = APIRouter()

VALID_STATUSES = {
    "draft", "presented", "consideration_period", "signed",
    "revoked", "effective", "expired", "void",
}


# ---------------------------------------------------------------------------
# Pydantic models
# ---------------------------------------------------------------------------

class SeparationAgreementCreate(BaseModel):
    employee_id: UUID
    offboarding_case_id: Optional[UUID] = None
    pre_term_check_id: Optional[UUID] = None
    severance_amount: Optional[float] = None
    severance_weeks: Optional[int] = None
    severance_description: Optional[str] = None
    additional_terms: Optional[dict] = None
    employee_age_at_separation: Optional[int] = None
    is_group_layoff: bool = False
    decisional_unit: Optional[str] = None
    group_disclosure: Optional[list] = None
    notes: Optional[str] = None


class SeparationAgreementUpdate(BaseModel):
    severance_amount: Optional[float] = None
    severance_weeks: Optional[int] = None
    severance_description: Optional[str] = None
    additional_terms: Optional[dict] = None
    notes: Optional[str] = None


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _row_to_dict(row) -> dict:
    """Convert an asyncpg Record to a JSON-safe dict with string UUIDs."""
    d = dict(row)
    for key in ("id", "company_id", "employee_id", "offboarding_case_id",
                "pre_term_check_id", "created_by"):
        if d.get(key) is not None:
            d[key] = str(d[key])
    # Convert dates to ISO strings for JSON serialization
    for key in ("presented_date", "consideration_deadline", "signed_date",
                "revocation_deadline", "effective_date", "revoked_date"):
        if d.get(key) is not None:
            d[key] = d[key].isoformat()
    for key in ("created_at", "updated_at"):
        if d.get(key) is not None:
            d[key] = d[key].isoformat()
    return d


# ---------------------------------------------------------------------------
# POST / — Create separation agreement
# ---------------------------------------------------------------------------

@router.post("", status_code=201)
async def create_separation_agreement(
    body: SeparationAgreementCreate,
    current_user=Depends(require_admin_or_client),
):
    """Create a new separation agreement for an employee."""
    company_id = await get_client_company_id(current_user)
    if company_id is None:
        raise HTTPException(status_code=403, detail="No company associated with this account")

    async with get_connection() as conn:
        # Verify employee belongs to company
        emp = await conn.fetchrow(
            "SELECT id FROM employees WHERE id = $1 AND org_id = $2",
            body.employee_id,
            company_id,
        )
        if not emp:
            raise HTTPException(status_code=404, detail="Employee not found in your company")

        # Determine ADEA applicability
        is_adea_applicable = False
        if body.employee_age_at_separation is not None and body.employee_age_at_separation >= 40:
            is_adea_applicable = True

        # Determine consideration period
        consideration_period_days = None
        if is_adea_applicable:
            if body.is_group_layoff:
                consideration_period_days = 45
            else:
                consideration_period_days = 21

        # Validate group layoff disclosure requirement
        if body.is_group_layoff and is_adea_applicable and body.group_disclosure is None:
            raise HTTPException(
                status_code=400,
                detail="Group layoff with ADEA requires group_disclosure",
            )

        row = await conn.fetchrow(
            """
            INSERT INTO separation_agreements (
                company_id, employee_id, offboarding_case_id, pre_term_check_id,
                status, severance_amount, severance_weeks, severance_description,
                additional_terms, employee_age_at_separation, is_adea_applicable,
                is_group_layoff, consideration_period_days, decisional_unit,
                group_disclosure, created_by, notes
            )
            VALUES (
                $1, $2, $3, $4,
                'draft', $5, $6, $7,
                $8, $9, $10,
                $11, $12, $13,
                $14, $15, $16
            )
            RETURNING *
            """,
            company_id,
            body.employee_id,
            body.offboarding_case_id,
            body.pre_term_check_id,
            body.severance_amount,
            body.severance_weeks,
            body.severance_description,
            json.dumps(body.additional_terms) if body.additional_terms else None,
            body.employee_age_at_separation,
            is_adea_applicable,
            body.is_group_layoff,
            consideration_period_days,
            body.decisional_unit,
            json.dumps(body.group_disclosure) if body.group_disclosure else None,
            current_user.id,
            body.notes,
        )

    return _row_to_dict(row)


# ---------------------------------------------------------------------------
# GET / — List agreements for company
# ---------------------------------------------------------------------------

@router.get("")
async def list_separation_agreements(
    current_user=Depends(require_admin_or_client),
    status: Optional[str] = Query(None),
    employee_id: Optional[UUID] = Query(None),
):
    """List separation agreements for the company with optional filters."""
    company_id = await get_client_company_id(current_user)
    if company_id is None:
        raise HTTPException(status_code=403, detail="No company associated with this account")

    query = """
        SELECT sa.*,
               e.first_name || ' ' || e.last_name AS employee_name
        FROM separation_agreements sa
        JOIN employees e ON e.id = sa.employee_id
        WHERE sa.company_id = $1
    """
    params: list = [company_id]
    idx = 1

    if status is not None:
        if status not in VALID_STATUSES:
            raise HTTPException(status_code=422, detail=f"Invalid status: {status}")
        idx += 1
        query += f" AND sa.status = ${idx}"
        params.append(status)

    if employee_id is not None:
        idx += 1
        query += f" AND sa.employee_id = ${idx}"
        params.append(employee_id)

    query += " ORDER BY sa.created_at DESC"

    async with get_connection() as conn:
        rows = await conn.fetch(query, *params)

    results = []
    for row in rows:
        d = _row_to_dict(row)
        d["employee_name"] = row["employee_name"]
        results.append(d)
    return results


# ---------------------------------------------------------------------------
# GET /{agreement_id} — Get single agreement with employee name
# ---------------------------------------------------------------------------

@router.get("/{agreement_id}")
async def get_separation_agreement(
    agreement_id: UUID,
    current_user=Depends(require_admin_or_client),
):
    """Get a single separation agreement by ID."""
    company_id = await get_client_company_id(current_user)
    if company_id is None:
        raise HTTPException(status_code=403, detail="No company associated with this account")

    async with get_connection() as conn:
        row = await conn.fetchrow(
            """
            SELECT sa.*,
                   e.first_name || ' ' || e.last_name AS employee_name
            FROM separation_agreements sa
            JOIN employees e ON e.id = sa.employee_id
            WHERE sa.id = $1 AND sa.company_id = $2
            """,
            agreement_id,
            company_id,
        )

    if not row:
        raise HTTPException(status_code=404, detail="Separation agreement not found")

    d = _row_to_dict(row)
    d["employee_name"] = row["employee_name"]
    return d


# ---------------------------------------------------------------------------
# PUT /{agreement_id} — Update basic fields
# ---------------------------------------------------------------------------

@router.put("/{agreement_id}")
async def update_separation_agreement(
    agreement_id: UUID,
    body: SeparationAgreementUpdate,
    current_user=Depends(require_admin_or_client),
):
    """Update severance, terms, and notes on a separation agreement."""
    company_id = await get_client_company_id(current_user)
    if company_id is None:
        raise HTTPException(status_code=403, detail="No company associated with this account")

    async with get_connection() as conn:
        existing = await conn.fetchrow(
            "SELECT id FROM separation_agreements WHERE id = $1 AND company_id = $2",
            agreement_id,
            company_id,
        )
        if not existing:
            raise HTTPException(status_code=404, detail="Separation agreement not found")

        sets = ["updated_at = NOW()"]
        params: list = []
        idx = 1  # $1 is reserved for the WHERE id

        if body.severance_amount is not None:
            idx += 1
            sets.append(f"severance_amount = ${idx}")
            params.append(body.severance_amount)

        if body.severance_weeks is not None:
            idx += 1
            sets.append(f"severance_weeks = ${idx}")
            params.append(body.severance_weeks)

        if body.severance_description is not None:
            idx += 1
            sets.append(f"severance_description = ${idx}")
            params.append(body.severance_description)

        if body.additional_terms is not None:
            idx += 1
            sets.append(f"additional_terms = ${idx}")
            params.append(json.dumps(body.additional_terms))

        if body.notes is not None:
            idx += 1
            sets.append(f"notes = ${idx}")
            params.append(body.notes)

        if len(sets) == 1:
            # Only updated_at — nothing to change
            raise HTTPException(status_code=422, detail="No fields to update")

        row = await conn.fetchrow(
            f"UPDATE separation_agreements SET {', '.join(sets)} "
            f"WHERE id = $1 RETURNING *",
            agreement_id,
            *params,
        )

    return _row_to_dict(row)


# ---------------------------------------------------------------------------
# PUT /{agreement_id}/present — Mark as presented, start consideration
# ---------------------------------------------------------------------------

@router.put("/{agreement_id}/present")
async def present_separation_agreement(
    agreement_id: UUID,
    current_user=Depends(require_admin_or_client),
):
    """Present the agreement to the employee and start the consideration period."""
    company_id = await get_client_company_id(current_user)
    if company_id is None:
        raise HTTPException(status_code=403, detail="No company associated with this account")

    async with get_connection() as conn:
        existing = await conn.fetchrow(
            "SELECT * FROM separation_agreements WHERE id = $1 AND company_id = $2",
            agreement_id,
            company_id,
        )
        if not existing:
            raise HTTPException(status_code=404, detail="Separation agreement not found")

        if existing["status"] != "draft":
            raise HTTPException(
                status_code=400,
                detail=f"Cannot present agreement with status '{existing['status']}'. Must be 'draft'.",
            )

        today = date.today()
        consideration_deadline = None
        if existing["consideration_period_days"] is not None:
            consideration_deadline = today + timedelta(days=existing["consideration_period_days"])

        row = await conn.fetchrow(
            """
            UPDATE separation_agreements
            SET status = 'consideration_period',
                presented_date = $2,
                consideration_deadline = $3,
                updated_at = NOW()
            WHERE id = $1
            RETURNING *
            """,
            agreement_id,
            today,
            consideration_deadline,
        )

    return _row_to_dict(row)


# ---------------------------------------------------------------------------
# PUT /{agreement_id}/sign — Record employee signature
# ---------------------------------------------------------------------------

@router.put("/{agreement_id}/sign")
async def sign_separation_agreement(
    agreement_id: UUID,
    current_user=Depends(require_admin_or_client),
):
    """Record employee signature on the separation agreement."""
    company_id = await get_client_company_id(current_user)
    if company_id is None:
        raise HTTPException(status_code=403, detail="No company associated with this account")

    async with get_connection() as conn:
        existing = await conn.fetchrow(
            "SELECT * FROM separation_agreements WHERE id = $1 AND company_id = $2",
            agreement_id,
            company_id,
        )
        if not existing:
            raise HTTPException(status_code=404, detail="Separation agreement not found")

        today = date.today()

        # ADEA consideration period enforcement
        if existing["is_adea_applicable"] and existing["consideration_deadline"] is not None:
            deadline = existing["consideration_deadline"]
            if today < deadline:
                raise HTTPException(
                    status_code=400,
                    detail=f"Cannot sign before consideration period ends on {deadline.isoformat()}",
                )

        revocation_deadline = None
        if existing["revocation_period_days"] is not None:
            revocation_deadline = today + timedelta(days=existing["revocation_period_days"])

        row = await conn.fetchrow(
            """
            UPDATE separation_agreements
            SET status = 'signed',
                signed_date = $2,
                revocation_deadline = $3,
                updated_at = NOW()
            WHERE id = $1
            RETURNING *
            """,
            agreement_id,
            today,
            revocation_deadline,
        )

    return _row_to_dict(row)


# ---------------------------------------------------------------------------
# PUT /{agreement_id}/revoke — Revoke during revocation period
# ---------------------------------------------------------------------------

@router.put("/{agreement_id}/revoke")
async def revoke_separation_agreement(
    agreement_id: UUID,
    current_user=Depends(require_admin_or_client),
):
    """Revoke the separation agreement during the revocation period."""
    company_id = await get_client_company_id(current_user)
    if company_id is None:
        raise HTTPException(status_code=403, detail="No company associated with this account")

    async with get_connection() as conn:
        existing = await conn.fetchrow(
            "SELECT * FROM separation_agreements WHERE id = $1 AND company_id = $2",
            agreement_id,
            company_id,
        )
        if not existing:
            raise HTTPException(status_code=404, detail="Separation agreement not found")

        if existing["status"] != "signed":
            raise HTTPException(
                status_code=400,
                detail=f"Cannot revoke agreement with status '{existing['status']}'. Must be 'signed'.",
            )

        today = date.today()
        if existing["revocation_deadline"] is not None and today > existing["revocation_deadline"]:
            raise HTTPException(
                status_code=400,
                detail="Revocation period has expired",
            )

        row = await conn.fetchrow(
            """
            UPDATE separation_agreements
            SET status = 'revoked',
                revoked_date = $2,
                updated_at = NOW()
            WHERE id = $1
            RETURNING *
            """,
            agreement_id,
            today,
        )

    return _row_to_dict(row)


# ---------------------------------------------------------------------------
# GET /{agreement_id}/status — Status with period countdown
# ---------------------------------------------------------------------------

@router.get("/{agreement_id}/status")
async def get_separation_agreement_status(
    agreement_id: UUID,
    current_user=Depends(require_admin_or_client),
):
    """Get current status with consideration/revocation period countdown."""
    company_id = await get_client_company_id(current_user)
    if company_id is None:
        raise HTTPException(status_code=403, detail="No company associated with this account")

    async with get_connection() as conn:
        row = await conn.fetchrow(
            "SELECT * FROM separation_agreements WHERE id = $1 AND company_id = $2",
            agreement_id,
            company_id,
        )

    if not row:
        raise HTTPException(status_code=404, detail="Separation agreement not found")

    today = date.today()

    # Consideration period countdown
    days_remaining_consideration = None
    if row["consideration_deadline"] is not None:
        delta = (row["consideration_deadline"] - today).days
        days_remaining_consideration = max(delta, 0)

    # Revocation period countdown
    days_remaining_revocation = None
    if row["revocation_deadline"] is not None:
        delta = (row["revocation_deadline"] - today).days
        days_remaining_revocation = max(delta, 0)

    # Determine if effective
    is_effective = False
    effective_date = row["effective_date"]
    if (
        row["status"] == "signed"
        and row["revocation_deadline"] is not None
        and today > row["revocation_deadline"]
        and row["revoked_date"] is None
    ):
        is_effective = True
        effective_date = row["revocation_deadline"] + timedelta(days=1)

    return {
        "status": row["status"],
        "is_adea_applicable": row["is_adea_applicable"],
        "presented_date": row["presented_date"].isoformat() if row["presented_date"] else None,
        "consideration_deadline": row["consideration_deadline"].isoformat() if row["consideration_deadline"] else None,
        "days_remaining_consideration": days_remaining_consideration,
        "signed_date": row["signed_date"].isoformat() if row["signed_date"] else None,
        "revocation_deadline": row["revocation_deadline"].isoformat() if row["revocation_deadline"] else None,
        "days_remaining_revocation": days_remaining_revocation,
        "effective_date": effective_date.isoformat() if effective_date else None,
        "is_effective": is_effective,
    }
