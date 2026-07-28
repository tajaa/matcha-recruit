"""Employee invitation send — the connection-scoped core.

Moved from routes/employees/_shared.py (refactor round 2, stage 3).
"""
import logging
import secrets
from datetime import datetime, timedelta
from uuid import UUID

from app.core.services.email import get_email_service

logger = logging.getLogger(__name__)

INVITATION_SEND_FAILED_DETAIL = "Invitation email could not be sent. Check email delivery settings and try again."


class InvitationError(Exception):
    """Domain error for invitation-send failures — this is a services module and
    must not raise FastAPI's HTTPException (see root CLAUDE.md: services/ stays
    FastAPI-free). Carries `status_code` for the one route caller
    (`routes/employees/invitations.py:send_invitation`) that maps it back to an
    HTTP response; every other caller — the bulk/invite-all loops
    (`_exception_message`, which already unwraps `.detail`) and
    `huume/onboarding_skill.py` (`getattr(exc, "detail", None)`) — already treats
    exceptions generically and needs no change.
    """

    def __init__(self, status_code: int, detail: str):
        self.status_code = status_code
        self.detail = detail
        super().__init__(detail)


async def _send_invitation_with_conn(
    employee_id: UUID,
    org_id: UUID,
    invited_by: UUID,
    conn,
    raise_on_email_failure: bool = True,
) -> dict:
    # Lazy: stays in routes/employees/_shared.py (a routes-layer compliance
    # helper) — a module-level import here would pull services back into
    # routes.
    from app.matcha.routes.employees._shared import _sync_employee_location_for_compliance

    async with conn.transaction():
        # Lock the employee row to serialize concurrent invite/resend calls so
        # only one active invitation per employee can be created at a time.
        employee = await conn.fetchrow(
            "SELECT * FROM employees WHERE id = $1 AND org_id = $2 FOR UPDATE",
            employee_id, org_id
        )

        if not employee:
            raise InvitationError(404, "Employee not found")

        if employee["user_id"]:
            raise InvitationError(400, "Employee already has an account")

        # Cancel all existing pending invitations for this employee
        await conn.execute(
            """
            UPDATE employee_invitations SET status = 'cancelled'
            WHERE employee_id = $1 AND status = 'pending'
            """,
            employee_id
        )

        # Generate new invitation token
        token = secrets.token_urlsafe(32)
        expires_at = datetime.utcnow() + timedelta(days=7)

        # Create invitation record
        invitation = await conn.fetchrow(
            """
            INSERT INTO employee_invitations (org_id, employee_id, invited_by, token, expires_at)
            VALUES ($1, $2, $3, $4, $5)
            RETURNING id, employee_id, token, status, expires_at, created_at
            """,
            org_id, employee_id, invited_by, token, expires_at
        )

    # Get company name for email (outside transaction — read-only)
    company = await conn.fetchrow("SELECT name FROM companies WHERE id = $1", org_id)
    company_name = company["name"] if company else "Your Company"

    await _sync_employee_location_for_compliance(
        conn,
        company_id=org_id,
        employee_id=employee_id,
        work_state=employee.get("work_state"),
        work_city=employee.get("work_city"),
    )

    # Send invitation email
    email_service = get_email_service()
    sent = await email_service.send_employee_invitation_email(
        to_email=employee["email"],
        to_name=f"{employee['first_name']} {employee['last_name']}",
        company_name=company_name,
        token=token,
        expires_at=expires_at,
    )
    if not sent:
        if raise_on_email_failure:
            logger.warning(
                "Employee invitation email failed for employee %s in company %s; cancelling invitation %s",
                employee_id,
                org_id,
                invitation["id"],
            )
            await conn.execute(
                "UPDATE employee_invitations SET status = 'cancelled' WHERE id = $1",
                invitation["id"],
            )
            raise InvitationError(503, INVITATION_SEND_FAILED_DETAIL)
        else:
            # Bulk mode: keep invitation pending so admin can resend later,
            # but raise so the caller records an error row for this employee.
            logger.warning(
                "Employee invitation email failed for employee %s in company %s; invitation %s kept pending for retry",
                employee_id,
                org_id,
                invitation["id"],
            )
            raise RuntimeError(INVITATION_SEND_FAILED_DETAIL)

    return {
        "invitation_id": invitation["id"],
        "token": invitation["token"],
        "expires_at": invitation["expires_at"]
    }
