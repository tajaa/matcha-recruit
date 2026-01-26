"""
Admin routes for employee management.
Allows admins/clients to create, update, delete employees and send invitations.
"""
import asyncio
import csv
import io
import re
import secrets
from datetime import datetime, timedelta
from typing import List, Optional
from uuid import UUID

from fastapi import APIRouter, HTTPException, Depends, UploadFile, File, Query, Body
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, EmailStr

from ...database import get_connection
from ...core.dependencies import get_current_user
from ..dependencies import require_admin_or_client, get_client_company_id
from ...core.models.auth import CurrentUser
from ...core.services.email import EmailService

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


class BulkEmployeeCSVUpload(BaseModel):
    """Model for CSV upload response."""
    total_rows: int
    created: int
    failed: int
    errors: list[dict]  # [{row: int, email: str, error: str}]
    employee_ids: list[UUID]


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


# ================================
# Helper Functions
# ================================

async def send_single_invitation(
    employee_id: UUID,
    org_id: UUID,
    invited_by: UUID,
    conn=None
) -> dict:
    """
    Shared function to send invitation to a single employee.
    Used by both individual invite endpoint and bulk invite endpoint.

    Returns: {"invitation_id": UUID, "token": str, "expires_at": datetime}
    """
    should_close = False
    if conn is None:
        conn = await get_connection().__aenter__()
        should_close = True

    try:
        # Get employee
        employee = await conn.fetchrow(
            "SELECT * FROM employees WHERE id = $1 AND org_id = $2",
            employee_id, org_id
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
            org_id, employee_id, invited_by, token, expires_at
        )

        # Get company name for email
        company = await conn.fetchrow("SELECT name FROM companies WHERE id = $1", org_id)
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

        return {
            "invitation_id": invitation["id"],
            "token": invitation["token"],
            "expires_at": invitation["expires_at"]
        }
    finally:
        if should_close:
            await conn.close()


# ================================
# Endpoints
# ================================

class OnboardingProgressItem(BaseModel):
    employee_id: UUID
    total: int
    completed: int
    pending: int
    has_onboarding: bool


@router.get("/onboarding-progress")
async def get_bulk_onboarding_progress(
    current_user: CurrentUser = Depends(require_admin_or_client),
):
    """Get onboarding progress for all employees in a single query (avoids N+1)."""
    company_id = await get_client_company_id(current_user)

    async with get_connection() as conn:
        rows = await conn.fetch(
            """
            SELECT
                e.id as employee_id,
                COUNT(eot.id)::int as total,
                COUNT(CASE WHEN eot.status = 'completed' THEN 1 END)::int as completed,
                COUNT(CASE WHEN eot.status = 'pending' THEN 1 END)::int as pending
            FROM employees e
            LEFT JOIN employee_onboarding_tasks eot ON eot.employee_id = e.id
            WHERE e.org_id = $1
            GROUP BY e.id
            """,
            company_id
        )

        return {
            str(row["employee_id"]): OnboardingProgressItem(
                employee_id=row["employee_id"],
                total=row["total"],
                completed=row["completed"],
                pending=row["pending"],
                has_onboarding=row["total"] > 0,
            )
            for row in rows
        }


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


# ================================
# Bulk Upload & Invitation Endpoints
# ================================

@router.get("/bulk-upload/template")
async def download_bulk_upload_template(
    current_user: CurrentUser = Depends(require_admin_or_client),
):
    """
    Download CSV template for bulk employee upload.

    Returns CSV file with:
    - Column headers
    - Sample data row
    - Comments explaining each field
    """
    # Create CSV in memory
    output = io.StringIO()
    writer = csv.DictWriter(output, fieldnames=[
        'email', 'first_name', 'last_name', 'work_state',
        'employment_type', 'start_date', 'manager_email', 'job_title', 'phone'
    ])
    writer.writeheader()

    # Add example row
    writer.writerow({
        'email': 'jane.doe@example.com',
        'first_name': 'Jane',
        'last_name': 'Doe',
        'work_state': 'CA',
        'employment_type': 'full_time',
        'start_date': '2026-02-01',
        'manager_email': 'manager@example.com',
        'job_title': 'Software Engineer',
        'phone': '555-1234'
    })

    output.seek(0)
    return StreamingResponse(
        io.BytesIO(output.getvalue().encode()),
        media_type="text/csv",
        headers={"Content-Disposition": "attachment; filename=employee_bulk_upload_template.csv"}
    )


@router.post("/bulk-upload", response_model=BulkEmployeeCSVUpload)
async def bulk_upload_employees_csv(
    file: UploadFile = File(..., description="CSV file with employee data"),
    send_invitations: bool = Query(True, description="Send invitation emails immediately"),
    current_user: CurrentUser = Depends(require_admin_or_client),
):
    """
    Upload CSV file to create employees and optionally send invitations.

    CSV Format (required columns):
    - email (required)
    - first_name (required)
    - last_name (required)

    CSV Format (optional columns):
    - work_state (e.g., "CA", "NY")
    - employment_type (full_time, part_time, contractor)
    - start_date (YYYY-MM-DD format)
    - manager_email (must be existing employee email)
    - job_title
    - phone
    """
    company_id = await get_client_company_id(current_user)

    # Validate file format
    if not file.filename.endswith('.csv'):
        raise HTTPException(status_code=400, detail="File must be a CSV")

    # Check file size (10MB max)
    contents = await file.read()
    if len(contents) > 10 * 1024 * 1024:
        raise HTTPException(status_code=413, detail="File too large (max 10MB)")

    # Parse CSV
    try:
        csv_content = contents.decode('utf-8')
        csv_reader = csv.DictReader(io.StringIO(csv_content))
    except Exception as e:
        raise HTTPException(status_code=400, detail=f"Invalid CSV format: {str(e)}")

    # Validate required columns
    required_columns = ['email', 'first_name', 'last_name']
    if not csv_reader.fieldnames:
        raise HTTPException(status_code=400, detail="CSV file is empty")

    missing_columns = [col for col in required_columns if col not in csv_reader.fieldnames]
    if missing_columns:
        raise HTTPException(
            status_code=400,
            detail=f"Missing required columns: {', '.join(missing_columns)}"
        )

    # Process rows
    created = 0
    failed = 0
    errors = []
    employee_ids = []

    async with get_connection() as conn:
        for row_num, row in enumerate(csv_reader, start=2):  # Start at 2 to account for header
            try:
                # Validate email format
                email = row.get('email', '').strip()
                if not email:
                    errors.append({
                        "row": row_num,
                        "email": email,
                        "error": "Email is required"
                    })
                    failed += 1
                    continue

                # Basic email validation
                if not re.match(r'^[\w\.-]+@[\w\.-]+\.\w+$', email):
                    errors.append({
                        "row": row_num,
                        "email": email,
                        "error": "Invalid email format"
                    })
                    failed += 1
                    continue

                # Check if email already exists
                existing = await conn.fetchval(
                    "SELECT id FROM employees WHERE org_id = $1 AND email = $2",
                    company_id, email
                )
                if existing:
                    errors.append({
                        "row": row_num,
                        "email": email,
                        "error": "Employee with this email already exists"
                    })
                    failed += 1
                    continue

                # Validate required fields
                first_name = row.get('first_name', '').strip()
                last_name = row.get('last_name', '').strip()

                if not first_name or not last_name:
                    errors.append({
                        "row": row_num,
                        "email": email,
                        "error": "First name and last name are required"
                    })
                    failed += 1
                    continue

                # Parse optional fields
                work_state = row.get('work_state', '').strip() or None
                employment_type = row.get('employment_type', '').strip() or None
                job_title = row.get('job_title', '').strip() or None
                phone = row.get('phone', '').strip() or None

                # Parse start_date
                start_date = None
                if row.get('start_date', '').strip():
                    try:
                        start_date = datetime.strptime(row['start_date'].strip(), "%Y-%m-%d").date()
                    except ValueError:
                        # Log warning but continue
                        pass

                # Resolve manager_email to manager_id
                manager_id = None
                if row.get('manager_email', '').strip():
                    manager = await conn.fetchrow(
                        "SELECT id FROM employees WHERE org_id = $1 AND email = $2",
                        company_id, row['manager_email'].strip()
                    )
                    if manager:
                        manager_id = manager['id']

                # Create employee record
                employee = await conn.fetchrow(
                    """
                    INSERT INTO employees (
                        org_id, email, first_name, last_name, work_state,
                        employment_type, start_date, manager_id, phone
                    )
                    VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9)
                    RETURNING id
                    """,
                    company_id, email, first_name, last_name, work_state,
                    employment_type, start_date, manager_id, phone
                )

                employee_ids.append(employee['id'])
                created += 1

                # Send invitation if requested
                if send_invitations:
                    try:
                        await send_single_invitation(
                            employee['id'],
                            company_id,
                            current_user.id,
                            conn
                        )
                    except Exception as e:
                        # Log error but don't fail the employee creation
                        errors.append({
                            "row": row_num,
                            "email": email,
                            "error": f"Employee created but invitation failed: {str(e)}"
                        })

            except Exception as e:
                errors.append({
                    "row": row_num,
                    "email": row.get('email', ''),
                    "error": str(e)
                })
                failed += 1

    # Check if there were any rows
    if created == 0 and failed == 0:
        raise HTTPException(status_code=400, detail="No data rows found in CSV")

    return BulkEmployeeCSVUpload(
        total_rows=created + failed,
        created=created,
        failed=failed,
        errors=errors,
        employee_ids=employee_ids
    )


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
                    await send_single_invitation(employee_id, company_id, current_user.id, conn)
                    sent += 1
                except Exception as e:
                    failed += 1
                    errors.append({
                        "employee_id": str(employee_id),
                        "error": str(e)
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

        # Calculate statistics
        stats = await conn.fetchrow("""
            SELECT
                COUNT(*) FILTER (WHERE status = 'pending') as pending,
                COUNT(*) FILTER (WHERE status = 'accepted') as accepted,
                COUNT(*) FILTER (WHERE status = 'expired') as expired,
                COUNT(*) FILTER (WHERE status = 'cancelled') as cancelled
            FROM employee_invitations i
            JOIN employees e ON i.employee_id = e.id
            WHERE e.org_id = $1
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


# ================================
# Employee Onboarding Tasks
# ================================

class EmployeeOnboardingTaskResponse(BaseModel):
    id: UUID
    employee_id: UUID
    task_id: Optional[UUID]
    title: str
    description: Optional[str]
    category: str
    is_employee_task: bool
    due_date: Optional[str]
    status: str
    completed_at: Optional[datetime]
    completed_by: Optional[UUID]
    notes: Optional[str]
    created_at: datetime

    class Config:
        from_attributes = True


class AssignOnboardingTasksRequest(BaseModel):
    task_ids: Optional[List[UUID]] = None  # Template task IDs to assign
    custom_tasks: Optional[List[dict]] = None  # Custom tasks: {title, description, category, is_employee_task, due_date}


class UpdateOnboardingTaskRequest(BaseModel):
    status: Optional[str] = None  # pending, completed, skipped
    notes: Optional[str] = None


@router.get("/{employee_id}/onboarding", response_model=List[EmployeeOnboardingTaskResponse])
async def get_employee_onboarding_tasks(
    employee_id: UUID,
    current_user: CurrentUser = Depends(require_admin_or_client),
):
    """Get all onboarding tasks for an employee."""
    company_id = await get_client_company_id(current_user)

    async with get_connection() as conn:
        # Verify employee belongs to company
        employee = await conn.fetchrow(
            "SELECT id FROM employees WHERE id = $1 AND org_id = $2",
            employee_id, company_id
        )
        if not employee:
            raise HTTPException(status_code=404, detail="Employee not found")

        rows = await conn.fetch(
            """
            SELECT * FROM employee_onboarding_tasks
            WHERE employee_id = $1
            ORDER BY
                CASE WHEN status = 'pending' THEN 0 ELSE 1 END,
                category, due_date, created_at
            """,
            employee_id
        )

        return [
            EmployeeOnboardingTaskResponse(
                id=row["id"],
                employee_id=row["employee_id"],
                task_id=row["task_id"],
                title=row["title"],
                description=row["description"],
                category=row["category"],
                is_employee_task=row["is_employee_task"],
                due_date=str(row["due_date"]) if row["due_date"] else None,
                status=row["status"],
                completed_at=row["completed_at"],
                completed_by=row["completed_by"],
                notes=row["notes"],
                created_at=row["created_at"],
            )
            for row in rows
        ]


@router.post("/{employee_id}/onboarding", response_model=List[EmployeeOnboardingTaskResponse])
async def assign_onboarding_tasks(
    employee_id: UUID,
    request: AssignOnboardingTasksRequest,
    current_user: CurrentUser = Depends(require_admin_or_client),
):
    """Assign onboarding tasks to an employee from templates or custom tasks."""
    company_id = await get_client_company_id(current_user)

    async with get_connection() as conn:
        # Verify employee belongs to company
        employee = await conn.fetchrow(
            "SELECT id, start_date FROM employees WHERE id = $1 AND org_id = $2",
            employee_id, company_id
        )
        if not employee:
            raise HTTPException(status_code=404, detail="Employee not found")

        start_date = employee["start_date"] or datetime.now().date()
        assigned_tasks = []

        # Assign from template tasks
        if request.task_ids:
            for task_id in request.task_ids:
                template = await conn.fetchrow(
                    "SELECT * FROM onboarding_tasks WHERE id = $1 AND org_id = $2 AND is_active = true",
                    task_id, company_id
                )
                if template:
                    due_date = start_date + timedelta(days=template["due_days"])
                    row = await conn.fetchrow(
                        """
                        INSERT INTO employee_onboarding_tasks
                        (employee_id, task_id, title, description, category, is_employee_task, due_date)
                        VALUES ($1, $2, $3, $4, $5, $6, $7)
                        RETURNING *
                        """,
                        employee_id, task_id, template["title"], template["description"],
                        template["category"], template["is_employee_task"], due_date
                    )
                    assigned_tasks.append(row)

        # Assign custom tasks
        if request.custom_tasks:
            for task in request.custom_tasks:
                due_date = None
                if task.get("due_date"):
                    try:
                        due_date = datetime.strptime(task["due_date"], "%Y-%m-%d").date()
                    except ValueError:
                        pass

                row = await conn.fetchrow(
                    """
                    INSERT INTO employee_onboarding_tasks
                    (employee_id, title, description, category, is_employee_task, due_date)
                    VALUES ($1, $2, $3, $4, $5, $6)
                    RETURNING *
                    """,
                    employee_id, task.get("title", "Custom Task"),
                    task.get("description"), task.get("category", "admin"),
                    task.get("is_employee_task", False), due_date
                )
                assigned_tasks.append(row)

        return [
            EmployeeOnboardingTaskResponse(
                id=row["id"],
                employee_id=row["employee_id"],
                task_id=row["task_id"],
                title=row["title"],
                description=row["description"],
                category=row["category"],
                is_employee_task=row["is_employee_task"],
                due_date=str(row["due_date"]) if row["due_date"] else None,
                status=row["status"],
                completed_at=row["completed_at"],
                completed_by=row["completed_by"],
                notes=row["notes"],
                created_at=row["created_at"],
            )
            for row in assigned_tasks
        ]


@router.post("/{employee_id}/onboarding/assign-all")
async def assign_all_onboarding_templates(
    employee_id: UUID,
    current_user: CurrentUser = Depends(require_admin_or_client),
):
    """Assign all active onboarding templates to an employee."""
    company_id = await get_client_company_id(current_user)

    async with get_connection() as conn:
        # Verify employee belongs to company
        employee = await conn.fetchrow(
            "SELECT id, start_date FROM employees WHERE id = $1 AND org_id = $2",
            employee_id, company_id
        )
        if not employee:
            raise HTTPException(status_code=404, detail="Employee not found")

        start_date = employee["start_date"] or datetime.now().date()

        # Get all active templates
        templates = await conn.fetch(
            "SELECT * FROM onboarding_tasks WHERE org_id = $1 AND is_active = true ORDER BY category, sort_order",
            company_id
        )

        # Check if employee already has tasks
        existing = await conn.fetchval(
            "SELECT COUNT(*) FROM employee_onboarding_tasks WHERE employee_id = $1",
            employee_id
        )
        if existing > 0:
            raise HTTPException(status_code=400, detail="Employee already has onboarding tasks assigned")

        count = 0
        for template in templates:
            due_date = start_date + timedelta(days=template["due_days"])
            await conn.execute(
                """
                INSERT INTO employee_onboarding_tasks
                (employee_id, task_id, title, description, category, is_employee_task, due_date)
                VALUES ($1, $2, $3, $4, $5, $6, $7)
                """,
                employee_id, template["id"], template["title"], template["description"],
                template["category"], template["is_employee_task"], due_date
            )
            count += 1

        return {"message": f"Assigned {count} onboarding tasks", "count": count}


@router.patch("/{employee_id}/onboarding/{task_id}", response_model=EmployeeOnboardingTaskResponse)
async def update_employee_onboarding_task(
    employee_id: UUID,
    task_id: UUID,
    request: UpdateOnboardingTaskRequest,
    current_user: CurrentUser = Depends(require_admin_or_client),
):
    """Update an employee's onboarding task status."""
    company_id = await get_client_company_id(current_user)

    async with get_connection() as conn:
        # Verify employee belongs to company
        employee = await conn.fetchrow(
            "SELECT id FROM employees WHERE id = $1 AND org_id = $2",
            employee_id, company_id
        )
        if not employee:
            raise HTTPException(status_code=404, detail="Employee not found")

        # Verify task exists
        task = await conn.fetchrow(
            "SELECT * FROM employee_onboarding_tasks WHERE id = $1 AND employee_id = $2",
            task_id, employee_id
        )
        if not task:
            raise HTTPException(status_code=404, detail="Onboarding task not found")

        # Build update query
        updates = []
        values = []
        param_num = 1

        if request.status is not None:
            if request.status not in ["pending", "completed", "skipped"]:
                raise HTTPException(status_code=400, detail="Invalid status")
            updates.append(f"status = ${param_num}")
            values.append(request.status)
            param_num += 1

            # Set completed_at and completed_by if marking as completed
            if request.status == "completed":
                updates.append(f"completed_at = NOW()")
                updates.append(f"completed_by = ${param_num}")
                values.append(current_user.id)
                param_num += 1
            elif request.status == "pending":
                updates.append("completed_at = NULL")
                updates.append("completed_by = NULL")

        if request.notes is not None:
            updates.append(f"notes = ${param_num}")
            values.append(request.notes)
            param_num += 1

        if not updates:
            raise HTTPException(status_code=400, detail="No fields to update")

        updates.append("updated_at = NOW()")

        query = f"""
            UPDATE employee_onboarding_tasks
            SET {', '.join(updates)}
            WHERE id = ${param_num}
            RETURNING *
        """
        values.append(task_id)

        row = await conn.fetchrow(query, *values)

        return EmployeeOnboardingTaskResponse(
            id=row["id"],
            employee_id=row["employee_id"],
            task_id=row["task_id"],
            title=row["title"],
            description=row["description"],
            category=row["category"],
            is_employee_task=row["is_employee_task"],
            due_date=str(row["due_date"]) if row["due_date"] else None,
            status=row["status"],
            completed_at=row["completed_at"],
            completed_by=row["completed_by"],
            notes=row["notes"],
            created_at=row["created_at"],
        )


@router.delete("/{employee_id}/onboarding/{task_id}")
async def delete_employee_onboarding_task(
    employee_id: UUID,
    task_id: UUID,
    current_user: CurrentUser = Depends(require_admin_or_client),
):
    """Remove an onboarding task from an employee."""
    company_id = await get_client_company_id(current_user)

    async with get_connection() as conn:
        # Verify employee belongs to company
        employee = await conn.fetchrow(
            "SELECT id FROM employees WHERE id = $1 AND org_id = $2",
            employee_id, company_id
        )
        if not employee:
            raise HTTPException(status_code=404, detail="Employee not found")

        result = await conn.execute(
            "DELETE FROM employee_onboarding_tasks WHERE id = $1 AND employee_id = $2",
            task_id, employee_id
        )

        if result == "DELETE 0":
            raise HTTPException(status_code=404, detail="Onboarding task not found")

        return {"message": "Onboarding task removed"}


# ================================
# Admin PTO Management
# ================================

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


@router.get("/pto/requests", response_model=List[PTORequestAdminResponse])
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


@router.get("/pto/summary", response_model=PTOSummaryStats)
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


@router.patch("/pto/requests/{request_id}")
async def handle_pto_request(
    request_id: UUID,
    request: PTORequestActionRequest,
    current_user: CurrentUser = Depends(require_admin_or_client),
):
    """Approve or deny a PTO request."""
    company_id = await get_client_company_id(current_user)

    if request.action not in ["approve", "deny"]:
        raise HTTPException(status_code=400, detail="Invalid action. Must be 'approve' or 'deny'")

    async with get_connection() as conn:
        # Verify request exists and belongs to company employee
        pto_request = await conn.fetchrow(
            """
            SELECT pr.*, e.org_id FROM pto_requests pr
            JOIN employees e ON pr.employee_id = e.id
            WHERE pr.id = $1 AND e.org_id = $2
            """,
            request_id, company_id
        )

        if not pto_request:
            raise HTTPException(status_code=404, detail="PTO request not found")

        if pto_request["status"] != "pending":
            raise HTTPException(status_code=400, detail="Can only approve/deny pending requests")

        # Get admin's employee ID if they have one
        admin_employee = await conn.fetchrow(
            "SELECT id FROM employees WHERE user_id = $1",
            current_user.id
        )
        approved_by = admin_employee["id"] if admin_employee else None

        if request.action == "approve":
            await conn.execute(
                """
                UPDATE pto_requests
                SET status = 'approved', approved_by = $1, approved_at = NOW(), updated_at = NOW()
                WHERE id = $2
                """,
                approved_by, request_id
            )

            # Update PTO balance used hours
            await conn.execute(
                """
                UPDATE pto_balances
                SET used_hours = used_hours + $1, updated_at = NOW()
                WHERE employee_id = $2 AND year = EXTRACT(YEAR FROM CURRENT_DATE)
                """,
                pto_request["hours"], pto_request["employee_id"]
            )

            return {"message": "PTO request approved", "status": "approved"}
        else:
            if not request.denial_reason:
                raise HTTPException(status_code=400, detail="Denial reason is required")

            await conn.execute(
                """
                UPDATE pto_requests
                SET status = 'denied', denial_reason = $1, approved_by = $2, approved_at = NOW(), updated_at = NOW()
                WHERE id = $3
                """,
                request.denial_reason, approved_by, request_id
            )

            return {"message": "PTO request denied", "status": "denied"}
