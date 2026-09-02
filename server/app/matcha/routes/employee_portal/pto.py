"""PTO request self-service."""
from datetime import date, datetime
from decimal import Decimal
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, status

from app.database import get_connection
from app.matcha.models.employees.employee import (
    PTOBalanceResponse, PTORequestCreate, PTORequestResponse, PTOSummary,
)
from app.matcha.dependencies import require_employee_record
from app.matcha.services.scheduling.time_off_guard import (
    PUBLISHED_WEEK_TIME_OFF_DETAIL, has_published_schedule_week,
)

from ._shared import _pto_dep

router = APIRouter()


@router.get("/me/pto", response_model=PTOSummary, dependencies=_pto_dep)
async def get_pto_summary(
    employee: dict = Depends(require_employee_record)
):
    """Get PTO balance and recent requests."""
    async with get_connection() as conn:
        current_year = datetime.now().year

        # Get or create PTO balance for current year
        pto_balance = await conn.fetchrow(
            """SELECT id, employee_id, year, balance_hours, accrued_hours,
                      used_hours, carryover_hours, updated_at
               FROM pto_balances
               WHERE employee_id = $1 AND year = $2""",
            employee["id"], current_year
        )

        if not pto_balance:
            # Create initial PTO balance
            pto_balance = await conn.fetchrow(
                """INSERT INTO pto_balances (employee_id, year, balance_hours, accrued_hours, used_hours, carryover_hours)
                   VALUES ($1, $2, 0, 0, 0, 0)
                   RETURNING id, employee_id, year, balance_hours, accrued_hours, used_hours, carryover_hours, updated_at""",
                employee["id"], current_year
            )

        # Get pending requests
        pending = await conn.fetch(
            """SELECT id, employee_id, start_date, end_date, hours, reason,
                      request_type, status, approved_by, approved_at, denial_reason,
                      created_at, updated_at
               FROM pto_requests
               WHERE employee_id = $1 AND status = 'pending'
               ORDER BY start_date ASC""",
            employee["id"]
        )

        # Get approved requests for current year
        approved = await conn.fetch(
            """SELECT id, employee_id, start_date, end_date, hours, reason,
                      request_type, status, approved_by, approved_at, denial_reason,
                      created_at, updated_at
               FROM pto_requests
               WHERE employee_id = $1
               AND status = 'approved'
               AND EXTRACT(YEAR FROM start_date) = $2
               ORDER BY start_date DESC""",
            employee["id"], current_year
        )

        return PTOSummary(
            balance=PTOBalanceResponse(
                id=pto_balance["id"],
                employee_id=pto_balance["employee_id"],
                year=pto_balance["year"],
                balance_hours=Decimal(str(pto_balance["balance_hours"])),
                accrued_hours=Decimal(str(pto_balance["accrued_hours"])),
                used_hours=Decimal(str(pto_balance["used_hours"])),
                carryover_hours=Decimal(str(pto_balance["carryover_hours"])),
                updated_at=pto_balance["updated_at"]
            ),
            pending_requests=[
                PTORequestResponse(
                    id=r["id"],
                    employee_id=r["employee_id"],
                    start_date=r["start_date"],
                    end_date=r["end_date"],
                    hours=Decimal(str(r["hours"])),
                    reason=r["reason"],
                    request_type=r["request_type"],
                    status=r["status"],
                    approved_by=r["approved_by"],
                    approved_at=r["approved_at"],
                    denial_reason=r["denial_reason"],
                    created_at=r["created_at"],
                    updated_at=r["updated_at"]
                ) for r in pending
            ],
            approved_requests=[
                PTORequestResponse(
                    id=r["id"],
                    employee_id=r["employee_id"],
                    start_date=r["start_date"],
                    end_date=r["end_date"],
                    hours=Decimal(str(r["hours"])),
                    reason=r["reason"],
                    request_type=r["request_type"],
                    status=r["status"],
                    approved_by=r["approved_by"],
                    approved_at=r["approved_at"],
                    denial_reason=r["denial_reason"],
                    created_at=r["created_at"],
                    updated_at=r["updated_at"]
                ) for r in approved
            ]
        )


@router.post("/me/pto/request", response_model=PTORequestResponse, dependencies=_pto_dep)
async def submit_pto_request(
    request: PTORequestCreate,
    employee: dict = Depends(require_employee_record)
):
    """Submit a new PTO request."""
    # Validate dates
    if request.start_date > request.end_date:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Start date must be before or equal to end date"
        )

    if request.start_date < date.today():
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Cannot request PTO for past dates"
        )

    if request.hours <= 0:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Hours must be greater than 0"
        )

    async with get_connection() as conn:
        if await has_published_schedule_week(
            conn, employee["org_id"], request.start_date, request.end_date,
        ):
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail=PUBLISHED_WEEK_TIME_OFF_DETAIL,
            )

        # Check for overlapping requests
        overlap = await conn.fetchval(
            """SELECT COUNT(*) FROM pto_requests
               WHERE employee_id = $1
               AND status IN ('pending', 'approved')
               AND (
                   (start_date <= $2 AND end_date >= $2) OR
                   (start_date <= $3 AND end_date >= $3) OR
                   (start_date >= $2 AND end_date <= $3)
               )""",
            employee["id"], request.start_date, request.end_date
        )

        if overlap > 0:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Request overlaps with existing PTO request"
            )

        # Create the request
        pto_request = await conn.fetchrow(
            """INSERT INTO pto_requests
               (employee_id, start_date, end_date, hours, reason, request_type, status)
               VALUES ($1, $2, $3, $4, $5, $6, 'pending')
               RETURNING id, employee_id, start_date, end_date, hours, reason,
                         request_type, status, approved_by, approved_at, denial_reason,
                         created_at, updated_at""",
            employee["id"], request.start_date, request.end_date,
            request.hours, request.reason, request.request_type
        )

        # TODO: Send notification to manager

        return PTORequestResponse(
            id=pto_request["id"],
            employee_id=pto_request["employee_id"],
            start_date=pto_request["start_date"],
            end_date=pto_request["end_date"],
            hours=Decimal(str(pto_request["hours"])),
            reason=pto_request["reason"],
            request_type=pto_request["request_type"],
            status=pto_request["status"],
            approved_by=pto_request["approved_by"],
            approved_at=pto_request["approved_at"],
            denial_reason=pto_request["denial_reason"],
            created_at=pto_request["created_at"],
            updated_at=pto_request["updated_at"]
        )


@router.delete("/me/pto/request/{request_id}", dependencies=_pto_dep)
async def cancel_pto_request(
    request_id: UUID,
    employee: dict = Depends(require_employee_record)
):
    """Cancel a pending PTO request."""
    async with get_connection() as conn:
        # Verify the request belongs to this employee and is pending
        request = await conn.fetchrow(
            """SELECT id, status FROM pto_requests
               WHERE id = $1 AND employee_id = $2""",
            request_id, employee["id"]
        )

        if not request:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="PTO request not found"
            )

        if request["status"] != "pending":
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Can only cancel pending requests"
            )

        await conn.execute(
            """UPDATE pto_requests SET status = 'cancelled', updated_at = NOW()
               WHERE id = $1""",
            request_id
        )

        return {"status": "cancelled", "request_id": str(request_id)}
