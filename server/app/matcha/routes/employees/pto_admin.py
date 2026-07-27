"""PTO admin router — exposed as `pto_admin_router` from the package.

Mounted at `/employees/pto` in `routes/__init__.py:46` with the
`require_feature("time_off")` gate applied at the mount.
"""
import logging
from datetime import datetime
from typing import List, Optional
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

from app.core.models.auth import CurrentUser
from app.database import get_connection
from app.matcha.dependencies import get_client_company_id, require_admin_or_client

from ._shared import decide_pto_request_core

logger = logging.getLogger(__name__)

router = APIRouter()


class PTORequestAdminResponse(BaseModel):
    id: UUID
    employee_id: UUID
    employee_name: str
    employee_email: str
    start_date: str
    end_date: str
    hours: float
    reason: Optional[str]
    request_type: str
    status: str
    approved_by: Optional[UUID]
    approved_at: Optional[datetime]
    denial_reason: Optional[str]
    created_at: datetime

    class Config:
        from_attributes = True


class PTORequestActionRequest(BaseModel):
    action: str  # approve, deny
    denial_reason: Optional[str] = None


class PTOSummaryStats(BaseModel):
    pending_count: int
    upcoming_time_off: int  # Number of approved requests in next 30 days


@router.get("/requests", response_model=List[PTORequestAdminResponse])
async def list_pto_requests(
    status: Optional[str] = None,  # pending, approved, denied, cancelled
    employee_id: Optional[UUID] = None,
    current_user: CurrentUser = Depends(require_admin_or_client),
):
    """List all PTO requests for the company."""
    company_id = await get_client_company_id(current_user)

    async with get_connection() as conn:
        query = """
            SELECT pr.*, e.first_name, e.last_name, e.email
            FROM pto_requests pr
            JOIN employees e ON pr.employee_id = e.id
            WHERE e.org_id = $1
        """
        params = [company_id]
        param_num = 2

        if status:
            query += f" AND pr.status = ${param_num}"
            params.append(status)
            param_num += 1

        if employee_id:
            query += f" AND pr.employee_id = ${param_num}"
            params.append(employee_id)
            param_num += 1

        query += " ORDER BY pr.created_at DESC"

        rows = await conn.fetch(query, *params)

        return [
            PTORequestAdminResponse(
                id=row["id"],
                employee_id=row["employee_id"],
                employee_name=f"{row['first_name']} {row['last_name']}",
                employee_email=row["email"],
                start_date=str(row["start_date"]),
                end_date=str(row["end_date"]),
                hours=float(row["hours"]),
                reason=row["reason"],
                request_type=row["request_type"],
                status=row["status"],
                approved_by=row["approved_by"],
                approved_at=row["approved_at"],
                denial_reason=row.get("denial_reason"),
                created_at=row["created_at"],
            )
            for row in rows
        ]


@router.get("/summary", response_model=PTOSummaryStats)
async def get_pto_summary_stats(
    current_user: CurrentUser = Depends(require_admin_or_client),
):
    """Get PTO summary stats for the dashboard."""
    company_id = await get_client_company_id(current_user)

    async with get_connection() as conn:
        # Count pending requests
        pending_count = await conn.fetchval(
            """
            SELECT COUNT(*) FROM pto_requests pr
            JOIN employees e ON pr.employee_id = e.id
            WHERE e.org_id = $1 AND pr.status = 'pending'
            """,
            company_id
        )

        # Count upcoming approved time off in next 30 days
        upcoming_count = await conn.fetchval(
            """
            SELECT COUNT(*) FROM pto_requests pr
            JOIN employees e ON pr.employee_id = e.id
            WHERE e.org_id = $1
            AND pr.status = 'approved'
            AND pr.start_date BETWEEN CURRENT_DATE AND CURRENT_DATE + INTERVAL '30 days'
            """,
            company_id
        )

        return PTOSummaryStats(
            pending_count=pending_count or 0,
            upcoming_time_off=upcoming_count or 0
        )


@router.patch("/requests/{request_id}")
async def handle_pto_request(
    request_id: UUID,
    request: PTORequestActionRequest,
    current_user: CurrentUser = Depends(require_admin_or_client),
):
    """Approve or deny a PTO request."""
    company_id = await get_client_company_id(current_user)

    if request.action not in ["approve", "deny"]:
        raise HTTPException(status_code=400, detail="Invalid action. Must be 'approve' or 'deny'")

    # The decision logic lives in `_shared.decide_pto_request_core` so Huume's
    # `pto_decision` staged action reaches the same code path; this handler is
    # the HTTP shaping around it. The transaction is new — an approval's two
    # writes (status + balance draw-down) were previously unwrapped.
    async with get_connection() as conn:
        async with conn.transaction():
            result = await decide_pto_request_core(
                conn,
                company_id=company_id,
                request_id=request_id,
                decision=request.action,
                actor_user_id=current_user.id,
                note=request.denial_reason,
            )

    if result["status"] == "not_found":
        raise HTTPException(status_code=404, detail=result["message"])
    if result["status"] != "ok":
        raise HTTPException(status_code=400, detail=result["message"])
    return {"message": result["message"], "status": result["decision"]}
