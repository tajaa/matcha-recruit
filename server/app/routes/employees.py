"""
Admin routes for employee management.
Allows admins/clients to create, update, delete employees and send invitations.
"""
import secrets
from datetime import datetime, timedelta
from typing import List, Optional
from uuid import UUID

from fastapi import APIRouter, HTTPException, Depends
from pydantic import BaseModel, EmailStr

from ..database import get_connection
from ..dependencies import get_current_user, require_admin_or_client, get_client_company_id
from ..models.auth import CurrentUser
from ..services.email import EmailService

router = APIRouter()


# Request/Response Models
class EmployeeCreateRequest(BaseModel):
    email: EmailStr
    first_name: str
    last_name: str
    work_state: Optional[str] = None
    employment_type: Optional[str] = None
    start_date: Optional[str] = None
    manager_id: Optional[UUID] = None


class EmployeeUpdateRequest(BaseModel):
    first_name: Optional[str] = None
    last_name: Optional[str] = None
    work_state: Optional[str] = None
    employment_type: Optional[str] = None
    start_date: Optional[str] = None
    termination_date: Optional[str] = None
    manager_id: Optional[UUID] = None
    phone: Optional[str] = None
    address: Optional[str] = None


class EmployeeListResponse(BaseModel):
    id: UUID
    email: str
    first_name: str
    last_name: str
    work_state: Optional[str]
    employment_type: Optional[str]
    start_date: Optional[str]
    termination_date: Optional[str]
    manager_id: Optional[UUID]
    manager_name: Optional[str]
    user_id: Optional[UUID]
    invitation_status: Optional[str]
    created_at: datetime

    class Config:
        from_attributes = True


class EmployeeDetailResponse(EmployeeListResponse):
    phone: Optional[str]
    address: Optional[str]
    emergency_contact: Optional[dict]
    updated_at: datetime


class InvitationResponse(BaseModel):
    id: UUID
    employee_id: UUID
    token: str
    status: str
    expires_at: datetime
    created_at: datetime


@router.get("", response_model=List[EmployeeListResponse])
async def list_employees(
    status: Optional[str] = None,  # active, terminated, invited
    current_user: CurrentUser = Depends(require_admin_or_client),
):
    """List all employees for the company."""
    company_id = await get_client_company_id(current_user)

    async with get_connection() as conn:
        # Build query based on status filter
        base_query = """
            SELECT
                e.id, e.email, e.first_name, e.last_name, e.work_state,
                e.employment_type, e.start_date, e.termination_date,
                e.manager_id, e.user_id, e.created_at,
                m.first_name || ' ' || m.last_name as manager_name,
                (
                    SELECT status FROM employee_invitations
                    WHERE employee_id = e.id
                    ORDER BY created_at DESC LIMIT 1
                ) as invitation_status
            FROM employees e
            LEFT JOIN employees m ON e.manager_id = m.id
            WHERE e.org_id = $1
        """

        if status == "active":
            base_query += " AND e.termination_date IS NULL AND e.user_id IS NOT NULL"
        elif status == "terminated":
            base_query += " AND e.termination_date IS NOT NULL"
        elif status == "invited":
            base_query += " AND e.user_id IS NULL"

        base_query += " ORDER BY e.created_at DESC"

        rows = await conn.fetch(base_query, company_id)

        return [
            EmployeeListResponse(
                id=row["id"],
                email=row["email"],
                first_name=row["first_name"],
                last_name=row["last_name"],
                work_state=row["work_state"],
                employment_type=row["employment_type"],
                start_date=str(row["start_date"]) if row["start_date"] else None,
                termination_date=str(row["termination_date"]) if row["termination_date"] else None,
                manager_id=row["manager_id"],
                manager_name=row["manager_name"],
                user_id=row["user_id"],
                invitation_status=row["invitation_status"],
                created_at=row["created_at"],
            )
            for row in rows
        ]


@router.post("", response_model=EmployeeDetailResponse)
async def create_employee(
    request: EmployeeCreateRequest,
    current_user: CurrentUser = Depends(require_admin_or_client),
):
    """Create a new employee record (without user account yet)."""
    company_id = await get_client_company_id(current_user)

    async with get_connection() as conn:
        # Check if email already exists for this company
        existing = await conn.fetchval(
            "SELECT id FROM employees WHERE org_id = $1 AND email = $2",
            company_id, request.email
        )
        if existing:
            raise HTTPException(status_code=400, detail="Employee with this email already exists")

        # Parse start_date if provided
        start_date = None
        if request.start_date:
            try:
                start_date = datetime.strptime(request.start_date, "%Y-%m-%d").date()
            except ValueError:
                raise HTTPException(status_code=400, detail="Invalid start_date format. Use YYYY-MM-DD")

        # Create employee record
        row = await conn.fetchrow(
            """
            INSERT INTO employees (org_id, email, first_name, last_name, work_state, employment_type, start_date, manager_id)
            VALUES ($1, $2, $3, $4, $5, $6, $7, $8)
            RETURNING id, org_id, email, first_name, last_name, work_state, employment_type,
                      start_date, termination_date, manager_id, user_id, phone, address,
                      emergency_contact, created_at, updated_at
            """,
            company_id, request.email, request.first_name, request.last_name,
            request.work_state, request.employment_type, start_date, request.manager_id
        )

        return EmployeeDetailResponse(
            id=row["id"],
            email=row["email"],
            first_name=row["first_name"],
            last_name=row["last_name"],
            work_state=row["work_state"],
            employment_type=row["employment_type"],
            start_date=str(row["start_date"]) if row["start_date"] else None,
            termination_date=str(row["termination_date"]) if row["termination_date"] else None,
            manager_id=row["manager_id"],
            manager_name=None,
            user_id=row["user_id"],
            invitation_status=None,
            phone=row["phone"],
            address=row["address"],
            emergency_contact=row["emergency_contact"],
            created_at=row["created_at"],
            updated_at=row["updated_at"],
        )


@router.get("/{employee_id}", response_model=EmployeeDetailResponse)
async def get_employee(
    employee_id: UUID,
    current_user: CurrentUser = Depends(require_admin_or_client),
):
    """Get employee details."""
    company_id = await get_client_company_id(current_user)

    async with get_connection() as conn:
        row = await conn.fetchrow(
            """
            SELECT
                e.*,
                m.first_name || ' ' || m.last_name as manager_name,
                (
                    SELECT status FROM employee_invitations
                    WHERE employee_id = e.id
                    ORDER BY created_at DESC LIMIT 1
                ) as invitation_status
            FROM employees e
            LEFT JOIN employees m ON e.manager_id = m.id
            WHERE e.id = $1 AND e.org_id = $2
            """,
            employee_id, company_id
        )

        if not row:
            raise HTTPException(status_code=404, detail="Employee not found")

        return EmployeeDetailResponse(
            id=row["id"],
            email=row["email"],
            first_name=row["first_name"],
            last_name=row["last_name"],
            work_state=row["work_state"],
            employment_type=row["employment_type"],
            start_date=str(row["start_date"]) if row["start_date"] else None,
            termination_date=str(row["termination_date"]) if row["termination_date"] else None,
            manager_id=row["manager_id"],
            manager_name=row["manager_name"],
            user_id=row["user_id"],
            invitation_status=row["invitation_status"],
            phone=row["phone"],
            address=row["address"],
            emergency_contact=row["emergency_contact"],
            created_at=row["created_at"],
            updated_at=row["updated_at"],
        )


@router.put("/{employee_id}", response_model=EmployeeDetailResponse)
async def update_employee(
    employee_id: UUID,
    request: EmployeeUpdateRequest,
    current_user: CurrentUser = Depends(require_admin_or_client),
):
    """Update employee details."""
    company_id = await get_client_company_id(current_user)

    async with get_connection() as conn:
        # Check employee exists
        existing = await conn.fetchval(
            "SELECT id FROM employees WHERE id = $1 AND org_id = $2",
            employee_id, company_id
        )
        if not existing:
            raise HTTPException(status_code=404, detail="Employee not found")

        # Build update query dynamically
        updates = []
        values = []
        param_num = 1

        if request.first_name is not None:
            updates.append(f"first_name = ${param_num}")
            values.append(request.first_name)
            param_num += 1

        if request.last_name is not None:
            updates.append(f"last_name = ${param_num}")
            values.append(request.last_name)
            param_num += 1

        if request.work_state is not None:
            updates.append(f"work_state = ${param_num}")
            values.append(request.work_state)
            param_num += 1

        if request.employment_type is not None:
            updates.append(f"employment_type = ${param_num}")
            values.append(request.employment_type)
            param_num += 1

        if request.start_date is not None:
            try:
                start_date = datetime.strptime(request.start_date, "%Y-%m-%d").date()
            except ValueError:
                raise HTTPException(status_code=400, detail="Invalid start_date format")
            updates.append(f"start_date = ${param_num}")
            values.append(start_date)
            param_num += 1

        if request.termination_date is not None:
            try:
                termination_date = datetime.strptime(request.termination_date, "%Y-%m-%d").date()
            except ValueError:
                raise HTTPException(status_code=400, detail="Invalid termination_date format")
            updates.append(f"termination_date = ${param_num}")
            values.append(termination_date)
            param_num += 1

        if request.manager_id is not None:
            updates.append(f"manager_id = ${param_num}")
            values.append(request.manager_id)
            param_num += 1

        if request.phone is not None:
            updates.append(f"phone = ${param_num}")
            values.append(request.phone)
            param_num += 1

        if request.address is not None:
            updates.append(f"address = ${param_num}")
            values.append(request.address)
            param_num += 1

        if not updates:
            raise HTTPException(status_code=400, detail="No fields to update")

        updates.append("updated_at = NOW()")

        query = f"""
            UPDATE employees
            SET {', '.join(updates)}
            WHERE id = ${param_num} AND org_id = ${param_num + 1}
            RETURNING *
        """
        values.extend([employee_id, company_id])

        row = await conn.fetchrow(query, *values)

        # Get manager name
        manager_name = None
        if row["manager_id"]:
            manager = await conn.fetchrow(
                "SELECT first_name, last_name FROM employees WHERE id = $1",
                row["manager_id"]
            )
            if manager:
                manager_name = f"{manager['first_name']} {manager['last_name']}"

        # Get invitation status
        invitation_status = await conn.fetchval(
            "SELECT status FROM employee_invitations WHERE employee_id = $1 ORDER BY created_at DESC LIMIT 1",
            employee_id
        )

        return EmployeeDetailResponse(
            id=row["id"],
            email=row["email"],
            first_name=row["first_name"],
            last_name=row["last_name"],
            work_state=row["work_state"],
            employment_type=row["employment_type"],
            start_date=str(row["start_date"]) if row["start_date"] else None,
            termination_date=str(row["termination_date"]) if row["termination_date"] else None,
            manager_id=row["manager_id"],
            manager_name=manager_name,
            user_id=row["user_id"],
            invitation_status=invitation_status,
            phone=row["phone"],
            address=row["address"],
            emergency_contact=row["emergency_contact"],
            created_at=row["created_at"],
            updated_at=row["updated_at"],
        )


@router.delete("/{employee_id}")
async def delete_employee(
    employee_id: UUID,
    current_user: CurrentUser = Depends(require_admin_or_client),
):
    """Delete an employee record."""
    company_id = await get_client_company_id(current_user)

    async with get_connection() as conn:
        result = await conn.execute(
            "DELETE FROM employees WHERE id = $1 AND org_id = $2",
            employee_id, company_id
        )

        if result == "DELETE 0":
            raise HTTPException(status_code=404, detail="Employee not found")

        return {"message": "Employee deleted successfully"}


@router.post("/{employee_id}/invite", response_model=InvitationResponse)
async def send_invitation(
    employee_id: UUID,
    current_user: CurrentUser = Depends(require_admin_or_client),
):
    """Send an invitation email to an employee to set up their account."""
    company_id = await get_client_company_id(current_user)

    async with get_connection() as conn:
        # Get employee
        employee = await conn.fetchrow(
            "SELECT * FROM employees WHERE id = $1 AND org_id = $2",
            employee_id, company_id
        )

        if not employee:
            raise HTTPException(status_code=404, detail="Employee not found")

        if employee["user_id"]:
            raise HTTPException(status_code=400, detail="Employee already has an account")

        # Check for existing pending invitation
        existing = await conn.fetchrow(
            """
            SELECT * FROM employee_invitations
            WHERE employee_id = $1 AND status = 'pending' AND expires_at > NOW()
            """,
            employee_id
        )

        if existing:
            # Cancel existing invitation
            await conn.execute(
                "UPDATE employee_invitations SET status = 'cancelled' WHERE id = $1",
                existing["id"]
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
            company_id, employee_id, current_user.id, token, expires_at
        )

        # Get company name for email
        company = await conn.fetchrow("SELECT name FROM companies WHERE id = $1", company_id)
        company_name = company["name"] if company else "Your Company"

        # Send invitation email
        email_service = EmailService()
        await email_service.send_employee_invitation_email(
            to_email=employee["email"],
            to_name=f"{employee['first_name']} {employee['last_name']}",
            company_name=company_name,
            token=token,
            expires_at=expires_at,
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
