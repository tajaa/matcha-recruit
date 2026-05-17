"""Employee invitation endpoints.

Routes:
  POST /{employee_id}/invite           — send invitation to one employee
  POST /{employee_id}/resend-invite    — cancel pending + send new invitation
  POST /bulk-invite                    — batch-send invitations by employee_id list
  POST /invite-all                     — invite every uninvited employee
  GET  /invitations/status             — admin summary of invitation states

All endpoints use `send_single_invitation` from ._shared, which locks the
employee row + cancels prior pending invitations + sends via Gmail/MailerSend
with the reserved-domain guard (RFC 2606 / RFC 6761).
"""
import asyncio
import logging
from datetime import datetime
from typing import Optional
from uuid import UUID

from fastapi import APIRouter, Body, Depends, Query
from pydantic import BaseModel

from app.core.models.auth import CurrentUser
from app.database import get_connection
from app.matcha.dependencies import get_client_company_id, require_admin_or_client

from ._shared import _exception_message, send_single_invitation

logger = logging.getLogger(__name__)

router = APIRouter()


class InvitationResponse(BaseModel):
    id: UUID
    employee_id: UUID
    token: str
    status: str
    expires_at: datetime
    created_at: datetime


class BulkInviteResponse(BaseModel):
    """Model for bulk invitation response."""
    sent: int
    failed: int
    total: int
    errors: list[dict]


class InvitationStatusItem(BaseModel):
    """Model for invitation status item."""
    employee_id: UUID
    email: str
    first_name: str
    last_name: str
    invitation_id: Optional[UUID]
    status: Optional[str]
    created_at: Optional[datetime]
    expires_at: Optional[datetime]
    accepted_at: Optional[datetime]
    invited_by_email: Optional[str]


class InvitationStatusSummary(BaseModel):
    """Model for invitation status summary."""
    statistics: dict
    invitations: list[InvitationStatusItem]
    total: int


@router.post("/{employee_id}/invite", response_model=InvitationResponse)
async def send_invitation(
    employee_id: UUID,
    current_user: CurrentUser = Depends(require_admin_or_client),
):
    """Send an invitation email to an employee to set up their account."""
    company_id = await get_client_company_id(current_user)

    async with get_connection() as conn:
        result = await send_single_invitation(employee_id, company_id, current_user.id, conn)

        # Fetch the full invitation record for response
        invitation = await conn.fetchrow(
            "SELECT * FROM employee_invitations WHERE id = $1",
            result["invitation_id"]
        )

        return InvitationResponse(
            id=invitation["id"],
            employee_id=invitation["employee_id"],
            token=invitation["token"],
            status=invitation["status"],
            expires_at=invitation["expires_at"],
            created_at=invitation["created_at"],
        )


@router.post("/{employee_id}/resend-invite", response_model=InvitationResponse)
async def resend_invitation(
    employee_id: UUID,
    current_user: CurrentUser = Depends(require_admin_or_client),
):
    """Resend invitation email (creates new token)."""
    return await send_invitation(employee_id, current_user)


@router.post("/bulk-invite", response_model=BulkInviteResponse)
async def send_bulk_invitations(
    employee_ids: list[UUID] = Body(..., description="List of employee IDs to send invitations to"),
    current_user: CurrentUser = Depends(require_admin_or_client),
):
    """
    Send invitation emails to multiple employees at once.

    Use this to send invitations to employees who were created without immediate invitation,
    or to resend invitations to multiple employees.

    Returns:
    - sent: count of successfully sent invitations
    - failed: count of failed sends
    - errors: list of errors for failed sends
    """
    company_id = await get_client_company_id(current_user)

    sent = 0
    failed = 0
    errors = []

    # Rate limiting: batch in groups of 10, with 1 second delay between batches
    BATCH_SIZE = 10

    async with get_connection() as conn:
        for i in range(0, len(employee_ids), BATCH_SIZE):
            batch = employee_ids[i:i + BATCH_SIZE]

            # Process batch
            for employee_id in batch:
                try:
                    await send_single_invitation(employee_id, company_id, current_user.id, conn, raise_on_email_failure=False)
                    sent += 1
                except Exception as e:
                    failed += 1
                    errors.append({
                        "employee_id": str(employee_id),
                        "error": _exception_message(e)
                    })

            # Delay between batches to avoid overwhelming email service
            if i + BATCH_SIZE < len(employee_ids):
                await asyncio.sleep(1)

    return BulkInviteResponse(
        sent=sent,
        failed=failed,
        total=len(employee_ids),
        errors=errors
    )


@router.post("/invite-all", response_model=BulkInviteResponse)
async def invite_all_uninvited(
    current_user: CurrentUser = Depends(require_admin_or_client),
):
    """
    Send invitation emails to all uninvited employees in the company.

    Finds all employees who have no user_id and no pending/accepted invitation,
    then sends invitations in batches of 10 with rate limiting.
    """
    company_id = await get_client_company_id(current_user)

    sent = 0
    failed = 0
    errors = []

    BATCH_SIZE = 10

    async with get_connection() as conn:
        # Find all employees who are uninvited:
        # - no user_id (haven't created an account)
        # - no pending or accepted invitation
        rows = await conn.fetch(
            """
            SELECT e.id
            FROM employees e
            WHERE e.org_id = $1
              AND e.user_id IS NULL
              AND e.termination_date IS NULL
              AND NOT EXISTS (
                  SELECT 1 FROM employee_invitations ei
                  WHERE ei.employee_id = e.id
                    AND ei.status IN ('pending', 'accepted')
              )
            ORDER BY e.created_at
            """,
            company_id,
        )

        employee_ids = [row["id"] for row in rows]

        for i in range(0, len(employee_ids), BATCH_SIZE):
            batch = employee_ids[i:i + BATCH_SIZE]

            for employee_id in batch:
                try:
                    await send_single_invitation(employee_id, company_id, current_user.id, conn, raise_on_email_failure=False)
                    sent += 1
                except Exception as e:
                    failed += 1
                    errors.append({
                        "employee_id": str(employee_id),
                        "error": _exception_message(e)
                    })

            if i + BATCH_SIZE < len(employee_ids):
                await asyncio.sleep(1)

    return BulkInviteResponse(
        sent=sent,
        failed=failed,
        total=len(employee_ids),
        errors=errors
    )


@router.get("/invitations/status", response_model=InvitationStatusSummary)
async def get_invitation_status_summary(
    status: Optional[str] = Query(None, regex="^(pending|accepted|expired|cancelled)$"),
    current_user: CurrentUser = Depends(require_admin_or_client),
):
    """
    Get summary of all employee invitations with status breakdown.

    Useful for tracking onboarding progress and identifying employees who haven't accepted.
    """
    company_id = await get_client_company_id(current_user)

    async with get_connection() as conn:
        # Base query
        status_filter = ""
        params = [company_id]

        if status:
            status_filter = "AND i.status = $2"
            params.append(status)

        # Get invitation summaries
        rows = await conn.fetch(f"""
            SELECT
                e.id as employee_id,
                e.email,
                e.first_name,
                e.last_name,
                i.id as invitation_id,
                i.status,
                i.created_at,
                i.expires_at,
                i.accepted_at,
                u.email as invited_by_email
            FROM employees e
            LEFT JOIN employee_invitations i ON e.id = i.employee_id
            LEFT JOIN users u ON i.invited_by = u.id
            WHERE e.org_id = $1
            {status_filter}
            ORDER BY i.created_at DESC
        """, *params)

        # Calculate statistics from each employee's latest invitation only,
        # so cancelled/expired historical rows from resends don't inflate counts.
        stats = await conn.fetchrow("""
            SELECT
                COUNT(*) FILTER (WHERE status = 'pending') as pending,
                COUNT(*) FILTER (WHERE status = 'accepted') as accepted,
                COUNT(*) FILTER (WHERE status = 'expired') as expired,
                COUNT(*) FILTER (WHERE status = 'cancelled') as cancelled
            FROM (
                SELECT DISTINCT ON (i.employee_id) i.status
                FROM employee_invitations i
                JOIN employees e ON i.employee_id = e.id
                WHERE e.org_id = $1
                ORDER BY i.employee_id, i.created_at DESC
            ) latest
        """, company_id)

        return InvitationStatusSummary(
            statistics=dict(stats) if stats else {},
            invitations=[
                InvitationStatusItem(
                    employee_id=row["employee_id"],
                    email=row["email"],
                    first_name=row["first_name"],
                    last_name=row["last_name"],
                    invitation_id=row["invitation_id"],
                    status=row["status"],
                    created_at=row["created_at"],
                    expires_at=row["expires_at"],
                    accepted_at=row["accepted_at"],
                    invited_by_email=row["invited_by_email"]
                )
                for row in rows
            ],
            total=len(rows)
        )
