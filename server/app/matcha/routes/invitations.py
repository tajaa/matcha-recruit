"""
Public routes for accepting employee invitations.
These routes do not require authentication.
"""
from datetime import datetime
from uuid import UUID

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from ...database import get_connection
from ...core.services.auth import hash_password, create_access_token, create_refresh_token
from ...core.services.email import EmailService

router = APIRouter()


class InvitationDetailsResponse(BaseModel):
    employee_id: UUID
    email: str
    first_name: str
    last_name: str
    company_name: str
    expires_at: datetime
    status: str


class AcceptInvitationRequest(BaseModel):
    password: str


class AcceptInvitationResponse(BaseModel):
    access_token: str
    refresh_token: str
    token_type: str = "bearer"
    employee_id: UUID
    message: str


@router.get("/{token}", response_model=InvitationDetailsResponse)
async def get_invitation_details(token: str):
    """Get invitation details by token (public, no auth required)."""
    async with get_connection() as conn:
        # Get invitation with employee and company info
        row = await conn.fetchrow(
            """
            SELECT
                i.id, i.employee_id, i.status, i.expires_at,
                e.email, e.first_name, e.last_name, e.user_id,
                c.name as company_name
            FROM employee_invitations i
            JOIN employees e ON i.employee_id = e.id
            JOIN companies c ON i.org_id = c.id
            WHERE i.token = $1
            """,
            token
        )

        if not row:
            raise HTTPException(status_code=404, detail="Invitation not found")

        if row["status"] == "accepted":
            raise HTTPException(status_code=400, detail="Invitation has already been accepted")

        if row["status"] == "cancelled":
            raise HTTPException(status_code=400, detail="Invitation has been cancelled")

        if row["status"] == "expired" or row["expires_at"] < datetime.utcnow():
            # Mark as expired if not already
            if row["status"] != "expired":
                await conn.execute(
                    "UPDATE employee_invitations SET status = 'expired' WHERE id = $1",
                    row["id"]
                )
            raise HTTPException(status_code=400, detail="Invitation has expired")

        if row["user_id"]:
            raise HTTPException(status_code=400, detail="Account has already been set up")

        return InvitationDetailsResponse(
            employee_id=row["employee_id"],
            email=row["email"],
            first_name=row["first_name"],
            last_name=row["last_name"],
            company_name=row["company_name"],
            expires_at=row["expires_at"],
            status=row["status"],
        )


@router.post("/{token}/accept", response_model=AcceptInvitationResponse)
async def accept_invitation(token: str, request: AcceptInvitationRequest):
    """Accept an invitation and set up user account."""
    if len(request.password) < 8:
        raise HTTPException(status_code=400, detail="Password must be at least 8 characters")

    async with get_connection() as conn:
        async with conn.transaction():
            # Lock the invitation row up front to serialize concurrent accepts for
            # the same token. The second concurrent request will block here, then
            # re-read status='accepted' and receive a clean 400.
            invitation = await conn.fetchrow(
                """
                SELECT
                    i.id, i.employee_id, i.org_id, i.status, i.expires_at,
                    e.email, e.work_email, e.first_name, e.last_name, e.user_id,
                    c.name as company_name
                FROM employee_invitations i
                JOIN employees e ON i.employee_id = e.id
                JOIN companies c ON i.org_id = c.id
                WHERE i.token = $1
                FOR UPDATE OF i
                """,
                token
            )

            if not invitation:
                raise HTTPException(status_code=404, detail="Invitation not found")

            if invitation["status"] == "accepted":
                raise HTTPException(status_code=400, detail="Invitation has already been accepted")

            if invitation["status"] == "cancelled":
                raise HTTPException(status_code=400, detail="Invitation has been cancelled")

            if invitation["status"] == "expired" or invitation["expires_at"] < datetime.utcnow():
                raise HTTPException(status_code=400, detail="Invitation has expired")

            if invitation["user_id"]:
                raise HTTPException(status_code=400, detail="Account has already been set up")

            # Check if email already exists in users table
            existing_user = await conn.fetchval(
                "SELECT id FROM users WHERE email = $1",
                invitation["email"]
            )
            if existing_user:
                raise HTTPException(
                    status_code=400,
                    detail="An account with this email already exists. Please contact your administrator."
                )

            # Create user account
            password_hash = hash_password(request.password)
            user = await conn.fetchrow(
                """
                INSERT INTO users (email, password_hash, role, is_active)
                VALUES ($1, $2, 'employee', true)
                RETURNING id, email, role
                """,
                invitation["email"], password_hash
            )

            # Link user to employee record
            await conn.execute(
                "UPDATE employees SET user_id = $1, updated_at = NOW() WHERE id = $2",
                user["id"], invitation["employee_id"]
            )

            # Mark invitation as accepted
            await conn.execute(
                "UPDATE employee_invitations SET status = 'accepted', accepted_at = NOW() WHERE id = $1",
                invitation["id"]
            )

        # Generate tokens
        access_token = create_access_token(user["id"], user["email"], user["role"])
        refresh_token = create_refresh_token(user["id"], user["email"], user["role"])

        # Send welcome email to work email (company email) — fire and forget
        welcome_to = invitation["work_email"] or invitation["email"]
        employee_name = f"{invitation['first_name']} {invitation['last_name']}"
        try:
            email_service = EmailService()
            await email_service.send_employee_welcome_email(
                to_email=welcome_to,
                to_name=employee_name,
                company_name=invitation["company_name"],
                login_email=invitation["email"],
            )
        except Exception as e:
            print(f"[Email] Failed to send welcome email after invitation acceptance: {e}")

        return AcceptInvitationResponse(
            access_token=access_token,
            refresh_token=refresh_token,
            employee_id=invitation["employee_id"],
            message="Account created successfully. Welcome!",
        )
