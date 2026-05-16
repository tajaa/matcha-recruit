"""Leave admin router — exposed as `leave_admin_router` from the package.

Mounted at `/employees/leave` in `routes/__init__.py:48` with the
`require_feature("time_off")` gate applied at the mount. Compliance
sub-endpoints (eligibility, deadlines, notices) layer an additional
`require_feature("compliance")` dependency in their decorators.
"""
import logging
from datetime import date, datetime
from decimal import Decimal
from typing import List, Optional
from uuid import UUID

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, Query
from pydantic import BaseModel

from app.core.models.auth import CurrentUser
from app.database import get_connection
from app.matcha.dependencies import (
    get_client_company_id,
    require_admin_or_client,
    require_feature,
)

logger = logging.getLogger(__name__)

router = APIRouter()


VALID_LEAVE_STATUSES = {"requested", "approved", "denied", "active", "completed", "cancelled"}


class LeaveActionRequest(BaseModel):
    action: str  # 'approve', 'deny', 'activate', 'complete'
    denial_reason: Optional[str] = None
    end_date: Optional[date] = None
    expected_return_date: Optional[date] = None
    actual_return_date: Optional[date] = None
    hours_approved: Optional[float] = None
    notes: Optional[str] = None


class LeaveRequestAdminResponse(BaseModel):
    id: UUID
    employee_id: UUID
    org_id: UUID
    leave_type: str
    reason: Optional[str]
    start_date: date
    end_date: Optional[date]
    expected_return_date: Optional[date]
    actual_return_date: Optional[date]
    status: str
    intermittent: bool
    intermittent_schedule: Optional[str]
    hours_approved: Optional[Decimal]
    hours_used: Optional[Decimal]
    denial_reason: Optional[str]
    reviewed_by: Optional[UUID]
    reviewed_at: Optional[datetime]
    notes: Optional[str]
    created_at: datetime
    updated_at: datetime
    employee_name: Optional[str] = None


@router.get("/requests", response_model=List[LeaveRequestAdminResponse])
async def list_leave_requests(
    status_filter: Optional[str] = Query(None, alias="status"),
    leave_type: Optional[str] = Query(None),
    current_user: CurrentUser = Depends(require_admin_or_client),
):
    """List all leave requests for the company."""
    company_id = await get_client_company_id(current_user)

    async with get_connection() as conn:
        conditions = ["lr.org_id = $1"]
        params: list = [company_id]
        idx = 2

        if status_filter:
            conditions.append(f"lr.status = ${idx}")
            params.append(status_filter)
            idx += 1

        if leave_type:
            conditions.append(f"lr.leave_type = ${idx}")
            params.append(leave_type)
            idx += 1

        where = " AND ".join(conditions)
        rows = await conn.fetch(
            f"""SELECT lr.*, e.first_name || ' ' || e.last_name AS employee_name
                FROM leave_requests lr
                JOIN employees e ON lr.employee_id = e.id
                WHERE {where}
                ORDER BY lr.created_at DESC""",
            *params,
        )
        return [LeaveRequestAdminResponse(**dict(r)) for r in rows]


@router.get("/requests/{leave_id}", response_model=LeaveRequestAdminResponse)
async def get_leave_request(
    leave_id: UUID,
    current_user: CurrentUser = Depends(require_admin_or_client),
):
    """Get a specific leave request with employee name."""
    company_id = await get_client_company_id(current_user)

    async with get_connection() as conn:
        row = await conn.fetchrow(
            """SELECT lr.*, e.first_name || ' ' || e.last_name AS employee_name
               FROM leave_requests lr
               JOIN employees e ON lr.employee_id = e.id
               WHERE lr.id = $1 AND lr.org_id = $2""",
            leave_id, company_id,
        )
        if not row:
            raise HTTPException(status_code=404, detail="Leave request not found")
        return LeaveRequestAdminResponse(**dict(row))


@router.patch("/requests/{leave_id}")
async def handle_leave_request(
    leave_id: UUID,
    request: LeaveActionRequest,
    background_tasks: BackgroundTasks,
    current_user: CurrentUser = Depends(require_admin_or_client),
):
    """Approve, deny, activate, or complete a leave request."""
    from app.matcha.services.leave_agent import get_leave_agent

    company_id = await get_client_company_id(current_user)

    async with get_connection() as conn:
        row = await conn.fetchrow(
            "SELECT id, status FROM leave_requests WHERE id = $1 AND org_id = $2",
            leave_id, company_id,
        )
        if not row:
            raise HTTPException(status_code=404, detail="Leave request not found")

        current_status = row["status"]
        reviewed_by = current_user.id

        if request.action == "approve":
            if current_status != "requested":
                raise HTTPException(status_code=400, detail="Can only approve requests in 'requested' status")

            sets = ["status = 'approved'", "reviewed_by = $2", "reviewed_at = NOW()", "updated_at = NOW()"]
            params: list = [leave_id, reviewed_by]
            idx = 3

            if request.end_date:
                sets.append(f"end_date = ${idx}")
                params.append(request.end_date)
                idx += 1
            if request.expected_return_date:
                sets.append(f"expected_return_date = ${idx}")
                params.append(request.expected_return_date)
                idx += 1
            if request.hours_approved is not None:
                sets.append(f"hours_approved = ${idx}")
                params.append(request.hours_approved)
                idx += 1
            if request.notes:
                sets.append(f"notes = ${idx}")
                params.append(request.notes)
                idx += 1

            await conn.execute(
                f"UPDATE leave_requests SET {', '.join(sets)} WHERE id = $1",
                *params,
            )

            # Fire deadline creation task for the approved leave
            try:
                from app.workers.tasks.leave_deadline_checks import create_leave_deadlines
                create_leave_deadlines.delay(str(leave_id))
            except Exception:
                logger.warning("Failed to enqueue leave deadline creation for %s", leave_id)

            background_tasks.add_task(get_leave_agent().on_leave_request_approved, leave_id)

            return {"message": "Leave request approved", "status": "approved"}

        elif request.action == "deny":
            if current_status != "requested":
                raise HTTPException(status_code=400, detail="Can only deny requests in 'requested' status")
            if not request.denial_reason:
                raise HTTPException(status_code=400, detail="Denial reason is required")

            await conn.execute(
                """UPDATE leave_requests
                   SET status = 'denied', denial_reason = $1, reviewed_by = $2,
                       reviewed_at = NOW(), updated_at = NOW()
                   WHERE id = $3""",
                request.denial_reason, reviewed_by, leave_id,
            )
            background_tasks.add_task(get_leave_agent().on_leave_status_changed, leave_id, "denied")
            return {"message": "Leave request denied", "status": "denied"}

        elif request.action == "activate":
            if current_status != "approved":
                raise HTTPException(status_code=400, detail="Can only activate approved leave requests")

            await conn.execute(
                "UPDATE leave_requests SET status = 'active', updated_at = NOW() WHERE id = $1",
                leave_id,
            )
            background_tasks.add_task(get_leave_agent().on_leave_status_changed, leave_id, "active")
            return {"message": "Leave activated", "status": "active"}

        elif request.action == "complete":
            if current_status not in ("active", "approved"):
                raise HTTPException(status_code=400, detail="Can only complete active or approved leave requests")

            sets = ["status = 'completed'", "updated_at = NOW()"]
            params = [leave_id]
            idx = 2

            actual_return = request.actual_return_date or date.today()
            sets.append(f"actual_return_date = ${idx}")
            params.append(actual_return)
            idx += 1

            if request.notes:
                sets.append(f"notes = ${idx}")
                params.append(request.notes)
                idx += 1

            await conn.execute(
                f"UPDATE leave_requests SET {', '.join(sets)} WHERE id = $1",
                *params,
            )
            background_tasks.add_task(get_leave_agent().on_leave_status_changed, leave_id, "completed")
            return {"message": "Leave completed", "status": "completed"}

        elif request.action == "extend":
            if current_status not in ("active", "approved"):
                raise HTTPException(status_code=400, detail="Can only extend active or approved leave requests")
            if not request.end_date:
                raise HTTPException(status_code=400, detail="end_date is required for extend action")

            sets = ["end_date = $2", "updated_at = NOW()"]
            params = [leave_id, request.end_date]
            idx = 3

            if request.expected_return_date:
                sets.append(f"expected_return_date = ${idx}")
                params.append(request.expected_return_date)
                idx += 1
            if request.notes:
                sets.append(f"notes = ${idx}")
                params.append(request.notes)
                idx += 1

            await conn.execute(
                f"UPDATE leave_requests SET {', '.join(sets)} WHERE id = $1",
                *params,
            )
            background_tasks.add_task(get_leave_agent().on_leave_extended, leave_id)
            return {"message": "Leave extended", "status": current_status}

        else:
            raise HTTPException(status_code=400, detail=f"Invalid action: {request.action}")


@router.get("/{employee_id}/requests", response_model=List[LeaveRequestAdminResponse])
async def list_employee_leave_requests(
    employee_id: UUID,
    status_filter: Optional[str] = Query(None, alias="status"),
    current_user: CurrentUser = Depends(require_admin_or_client),
):
    """List all leave requests for a specific employee."""
    company_id = await get_client_company_id(current_user)

    async with get_connection() as conn:
        # Verify employee belongs to this company
        emp = await conn.fetchval(
            "SELECT id FROM employees WHERE id = $1 AND org_id = $2",
            employee_id, company_id,
        )
        if not emp:
            raise HTTPException(status_code=404, detail="Employee not found")

        conditions = ["lr.employee_id = $1", "lr.org_id = $2"]
        params: list = [employee_id, company_id]
        idx = 3

        if status_filter:
            conditions.append(f"lr.status = ${idx}")
            params.append(status_filter)

        where = " AND ".join(conditions)
        rows = await conn.fetch(
            f"""SELECT lr.*, e.first_name || ' ' || e.last_name AS employee_name
                FROM leave_requests lr
                JOIN employees e ON lr.employee_id = e.id
                WHERE {where}
                ORDER BY lr.created_at DESC""",
            *params,
        )
        return [LeaveRequestAdminResponse(**dict(r)) for r in rows]


class ReturnCheckinRequest(BaseModel):
    returning: bool
    action: Optional[str] = None  # 'extend' or 'new_leave'
    new_end_date: Optional[date] = None
    new_expected_return_date: Optional[date] = None
    new_leave_type: Optional[str] = None
    new_start_date: Optional[date] = None
    notes: Optional[str] = None


@router.post("/requests/{leave_id}/return-checkin")
async def return_checkin(
    leave_id: UUID,
    request: ReturnCheckinRequest,
    background_tasks: BackgroundTasks,
    current_user: CurrentUser = Depends(require_admin_or_client),
):
    """Process a return-to-work check-in: returning, extending, or starting a new leave."""
    from app.matcha.services.leave_agent import get_leave_agent

    company_id = await get_client_company_id(current_user)

    async with get_connection() as conn:
        leave = await conn.fetchrow(
            "SELECT id, employee_id, org_id, status, leave_type, start_date FROM leave_requests WHERE id = $1 AND org_id = $2",
            leave_id, company_id,
        )
        if not leave:
            raise HTTPException(status_code=404, detail="Leave request not found")
        if leave["status"] not in ("active", "approved"):
            raise HTTPException(status_code=400, detail="Return check-in only applies to active or approved leave")

        if request.returning:
            # Mark leave completed and update employment_status
            await conn.execute(
                """UPDATE leave_requests
                   SET status = 'completed', actual_return_date = CURRENT_DATE, updated_at = NOW()
                   WHERE id = $1""",
                leave_id,
            )
            await conn.execute(
                """UPDATE employees
                   SET employment_status = 'active', status_changed_at = NOW(),
                       status_reason = 'Returned from leave', updated_at = NOW()
                   WHERE id = $1""",
                leave["employee_id"],
            )
            background_tasks.add_task(get_leave_agent().on_leave_status_changed, leave_id, "completed")
            return {"message": "Leave completed, employee marked as returned", "status": "completed"}

        # Not returning
        if request.action == "extend":
            if not request.new_end_date:
                raise HTTPException(status_code=400, detail="new_end_date is required for extend action")

            sets = ["end_date = $2", "updated_at = NOW()"]
            params: list = [leave_id, request.new_end_date]
            idx = 3
            if request.new_expected_return_date:
                sets.append(f"expected_return_date = ${idx}")
                params.append(request.new_expected_return_date)
                idx += 1
            if request.notes:
                sets.append(f"notes = ${idx}")
                params.append(request.notes)

            await conn.execute(
                f"UPDATE leave_requests SET {', '.join(sets)} WHERE id = $1",
                *params,
            )
            background_tasks.add_task(get_leave_agent().on_leave_extended, leave_id)
            return {"message": "Leave extended", "status": leave["status"]}

        elif request.action == "new_leave":
            if not request.new_leave_type:
                raise HTTPException(status_code=400, detail="new_leave_type is required for new_leave action")

            start = request.new_start_date or date.today()

            # Complete current leave
            await conn.execute(
                """UPDATE leave_requests
                   SET status = 'completed', actual_return_date = $2, updated_at = NOW()
                   WHERE id = $1""",
                leave_id, date.today(),
            )

            # Create new auto-approved leave
            new_leave_row = await conn.fetchrow(
                """INSERT INTO leave_requests
                       (employee_id, org_id, leave_type, start_date, end_date, expected_return_date,
                        reason, notes, status, reviewed_by, reviewed_at, intermittent)
                   VALUES ($1, $2, $3, $4, $5, $6, $7, $8, 'approved', $9, NOW(), false)
                   RETURNING id""",
                leave["employee_id"], company_id, request.new_leave_type,
                start, request.new_end_date, request.new_expected_return_date,
                request.notes, request.notes, current_user.id,
            )
            new_leave_id = new_leave_row["id"]

            background_tasks.add_task(get_leave_agent().on_return_declined, leave_id, new_leave_id)
            background_tasks.add_task(get_leave_agent().on_leave_request_approved, new_leave_id)
            return {
                "message": "Current leave completed, new leave created",
                "completed_leave_id": str(leave_id),
                "new_leave_id": str(new_leave_id),
            }

        else:
            raise HTTPException(status_code=400, detail="action must be 'extend' or 'new_leave' when not returning")


@router.get("/requests/{leave_id}/eligibility",
            dependencies=[Depends(require_feature("compliance"))])
async def get_leave_eligibility(
    leave_id: UUID,
    current_user: CurrentUser = Depends(require_admin_or_client),
):
    """Get FMLA + state program eligibility for the employee on a leave request.

    Requires the ``compliance_plus`` feature flag.  Results are cached in
    ``leave_requests.eligibility_data`` so repeated calls are fast.
    """
    import json
    from app.matcha.services.leave_eligibility_service import LeaveEligibilityService

    company_id = await get_client_company_id(current_user)

    async with get_connection() as conn:
        row = await conn.fetchrow(
            "SELECT id, employee_id, eligibility_data FROM leave_requests WHERE id = $1 AND org_id = $2",
            leave_id, company_id,
        )
        if not row:
            raise HTTPException(status_code=404, detail="Leave request not found")

        # Return cached result if present
        cached = row["eligibility_data"]
        if isinstance(cached, str):
            cached = json.loads(cached)
        if cached and cached.get("checked_at"):
            return cached

        # Run fresh eligibility check
        service = LeaveEligibilityService()
        result = await service.get_eligibility_summary(row["employee_id"])

        # Cache on the leave request row
        await conn.execute(
            "UPDATE leave_requests SET eligibility_data = $1, updated_at = NOW() WHERE id = $2",
            json.dumps(result), leave_id,
        )

        return result


class LeaveDeadlineResponse(BaseModel):
    id: UUID
    leave_request_id: UUID
    org_id: UUID
    deadline_type: str
    due_date: date
    status: str
    escalation_level: int
    completed_at: Optional[datetime] = None
    notes: Optional[str] = None
    created_at: datetime
    updated_at: datetime


class LeaveDeadlineActionRequest(BaseModel):
    action: str  # 'complete' or 'waive'
    notes: Optional[str] = None


@router.get("/requests/{leave_id}/deadlines",
            dependencies=[Depends(require_feature("compliance"))],
            response_model=List[LeaveDeadlineResponse])
async def list_leave_deadlines(
    leave_id: UUID,
    current_user: CurrentUser = Depends(require_admin_or_client),
):
    """List all compliance deadlines for a leave request."""
    company_id = await get_client_company_id(current_user)

    async with get_connection() as conn:
        # Verify leave request belongs to this company
        lr = await conn.fetchval(
            "SELECT id FROM leave_requests WHERE id = $1 AND org_id = $2",
            leave_id, company_id,
        )
        if not lr:
            raise HTTPException(status_code=404, detail="Leave request not found")

        rows = await conn.fetch(
            """SELECT * FROM leave_deadlines
               WHERE leave_request_id = $1 AND org_id = $2
               ORDER BY due_date ASC""",
            leave_id, company_id,
        )
        return [LeaveDeadlineResponse(**dict(r)) for r in rows]


@router.patch("/requests/{leave_id}/deadlines/{deadline_id}",
              dependencies=[Depends(require_feature("compliance"))],
              response_model=LeaveDeadlineResponse)
async def update_leave_deadline(
    leave_id: UUID,
    deadline_id: UUID,
    request: LeaveDeadlineActionRequest,
    current_user: CurrentUser = Depends(require_admin_or_client),
):
    """Complete or waive a leave compliance deadline."""
    company_id = await get_client_company_id(current_user)

    if request.action not in ("complete", "waive"):
        raise HTTPException(status_code=400, detail="Action must be 'complete' or 'waive'")

    async with get_connection() as conn:
        row = await conn.fetchrow(
            """SELECT id, status FROM leave_deadlines
               WHERE id = $1 AND leave_request_id = $2 AND org_id = $3""",
            deadline_id, leave_id, company_id,
        )
        if not row:
            raise HTTPException(status_code=404, detail="Deadline not found")
        if row["status"] in ("completed", "waived"):
            raise HTTPException(status_code=400, detail="Deadline already resolved")

        new_status = "completed" if request.action == "complete" else "waived"

        updated = await conn.fetchrow(
            """UPDATE leave_deadlines
               SET status = $1, completed_at = NOW(), notes = $2, updated_at = NOW()
               WHERE id = $3
               RETURNING *""",
            new_status, request.notes, deadline_id,
        )
        return LeaveDeadlineResponse(**dict(updated))


class LeaveNoticeRequest(BaseModel):
    notice_type: str  # fmla_eligibility_notice, fmla_designation_notice, state_leave_notice, return_to_work_notice


@router.post("/requests/{leave_id}/notices",
             dependencies=[Depends(require_feature("compliance"))])
async def create_leave_notice(
    leave_id: UUID,
    request: LeaveNoticeRequest,
    background_tasks: BackgroundTasks,
    current_user: CurrentUser = Depends(require_admin_or_client),
):
    """Generate a compliance leave notice PDF and store it as an employee document.

    Requires the ``compliance_plus`` feature flag.
    """
    from app.matcha.services.leave_notices_service import LeaveNoticeService, VALID_NOTICE_TYPES

    if request.notice_type not in VALID_NOTICE_TYPES:
        raise HTTPException(
            status_code=400,
            detail=f"Invalid notice_type. Must be one of: {', '.join(sorted(VALID_NOTICE_TYPES))}",
        )

    company_id = await get_client_company_id(current_user)

    async with get_connection() as conn:
        leave = await conn.fetchrow(
            "SELECT id, employee_id FROM leave_requests WHERE id = $1 AND org_id = $2",
            leave_id, company_id,
        )
        if not leave:
            raise HTTPException(status_code=404, detail="Leave request not found")

        try:
            service = LeaveNoticeService()
            doc = await service.create_notice(
                conn,
                notice_type=request.notice_type,
                employee_id=leave["employee_id"],
                org_id=company_id,
                leave_request_id=leave_id,
            )
            from app.matcha.services.leave_agent import get_leave_agent

            background_tasks.add_task(get_leave_agent().on_leave_notice_ready, leave_id)
            return doc
        except ValueError as e:
            raise HTTPException(status_code=400, detail=str(e))
        except Exception as e:
            logger.error(f"Failed to generate leave notice: {e}")
            raise HTTPException(
                status_code=500,
                detail="Failed to generate leave notice. Please try again.",
            )
