"""
Employee Self-Service Portal Routes

Provides API endpoints for employees to:
- View their profile and dashboard
- View and sign documents
- Manage PTO requests
- Search company policies
- Update personal information
"""
from datetime import datetime, date
from decimal import Decimal
from typing import Optional
from uuid import UUID

from fastapi import APIRouter, HTTPException, Depends, status, Request
from pydantic import BaseModel

from ..database import get_connection
from ..models.auth import CurrentUser
from ..models.employee import (
    EmployeeResponse, EmployeeUpdate, ProfileUpdateRequest,
    PTOBalanceResponse, PTORequestCreate, PTORequestResponse, PTORequestListResponse,
    PTOSummary,
    EmployeeDocumentResponse, EmployeeDocumentListResponse, SignDocumentRequest,
    PortalDashboard, PortalTasks, PendingTask
)
from ..dependencies import get_current_user, require_employee, require_employee_record

router = APIRouter()


# ================================
# Portal Dashboard
# ================================

@router.get("/me", response_model=PortalDashboard)
async def get_portal_dashboard(
    employee: dict = Depends(require_employee_record)
):
    """Get employee portal dashboard with summary stats."""
    async with get_connection() as conn:
        # Get PTO balance for current year
        current_year = datetime.now().year
        pto_balance = await conn.fetchrow(
            """SELECT id, employee_id, year, balance_hours, accrued_hours,
                      used_hours, carryover_hours, updated_at
               FROM pto_balances
               WHERE employee_id = $1 AND year = $2""",
            employee["id"], current_year
        )

        # Count pending documents
        pending_docs = await conn.fetchval(
            """SELECT COUNT(*) FROM employee_documents
               WHERE employee_id = $1 AND status = 'pending_signature'""",
            employee["id"]
        )

        # Count pending PTO requests
        pending_pto = await conn.fetchval(
            """SELECT COUNT(*) FROM pto_requests
               WHERE employee_id = $1 AND status = 'pending'""",
            employee["id"]
        )

        # Total pending tasks
        pending_tasks = pending_docs + pending_pto

        return PortalDashboard(
            employee=EmployeeResponse(
                id=employee["id"],
                org_id=employee["org_id"],
                user_id=None,  # Don't expose user_id
                email=employee["email"],
                first_name=employee["first_name"],
                last_name=employee["last_name"],
                work_state=employee["work_state"],
                employment_type=employee["employment_type"],
                start_date=employee["start_date"],
                termination_date=employee["termination_date"],
                manager_id=employee["manager_id"],
                phone=employee["phone"],
                address=employee["address"],
                emergency_contact=employee["emergency_contact"],
                created_at=employee["created_at"],
                updated_at=employee["updated_at"]
            ),
            pto_balance=PTOBalanceResponse(
                id=pto_balance["id"],
                employee_id=pto_balance["employee_id"],
                year=pto_balance["year"],
                balance_hours=Decimal(str(pto_balance["balance_hours"])),
                accrued_hours=Decimal(str(pto_balance["accrued_hours"])),
                used_hours=Decimal(str(pto_balance["used_hours"])),
                carryover_hours=Decimal(str(pto_balance["carryover_hours"])),
                updated_at=pto_balance["updated_at"]
            ) if pto_balance else None,
            pending_tasks_count=pending_tasks,
            pending_documents_count=pending_docs,
            pending_pto_requests_count=pending_pto
        )


@router.patch("/me", response_model=EmployeeResponse)
async def update_my_profile(
    request: ProfileUpdateRequest,
    employee: dict = Depends(require_employee_record)
):
    """Update employee's own profile (phone, address, emergency contact)."""
    async with get_connection() as conn:
        updates = []
        values = []
        param_idx = 1

        if request.phone is not None:
            updates.append(f"phone = ${param_idx}")
            values.append(request.phone)
            param_idx += 1

        if request.address is not None:
            updates.append(f"address = ${param_idx}")
            values.append(request.address)
            param_idx += 1

        if request.emergency_contact is not None:
            updates.append(f"emergency_contact = ${param_idx}::jsonb")
            import json
            values.append(json.dumps(request.emergency_contact))
            param_idx += 1

        if not updates:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="No fields to update"
            )

        updates.append(f"updated_at = NOW()")
        values.append(employee["id"])

        query = f"""
            UPDATE employees
            SET {', '.join(updates)}
            WHERE id = ${param_idx}
            RETURNING id, org_id, email, first_name, last_name, work_state,
                      employment_type, start_date, termination_date, manager_id,
                      phone, address, emergency_contact, created_at, updated_at
        """

        updated = await conn.fetchrow(query, *values)

        return EmployeeResponse(
            id=updated["id"],
            org_id=updated["org_id"],
            user_id=None,
            email=updated["email"],
            first_name=updated["first_name"],
            last_name=updated["last_name"],
            work_state=updated["work_state"],
            employment_type=updated["employment_type"],
            start_date=updated["start_date"],
            termination_date=updated["termination_date"],
            manager_id=updated["manager_id"],
            phone=updated["phone"],
            address=updated["address"],
            emergency_contact=updated["emergency_contact"],
            created_at=updated["created_at"],
            updated_at=updated["updated_at"]
        )


@router.get("/me/tasks", response_model=PortalTasks)
async def get_pending_tasks(
    employee: dict = Depends(require_employee_record)
):
    """Get all pending tasks for the employee."""
    tasks = []

    async with get_connection() as conn:
        # Get pending documents to sign
        docs = await conn.fetch(
            """SELECT id, title, description, expires_at, created_at
               FROM employee_documents
               WHERE employee_id = $1 AND status = 'pending_signature'
               ORDER BY expires_at ASC NULLS LAST, created_at DESC""",
            employee["id"]
        )

        for doc in docs:
            tasks.append(PendingTask(
                id=doc["id"],
                task_type="document_signature",
                title=f"Sign: {doc['title']}",
                description=doc["description"],
                due_date=doc["expires_at"],
                created_at=doc["created_at"]
            ))

        # Get pending PTO requests awaiting manager approval (for managers)
        # This would show subordinates' requests if the employee is a manager
        subordinate_requests = await conn.fetch(
            """SELECT pr.id, pr.start_date, pr.end_date, pr.hours,
                      e.first_name, e.last_name, pr.created_at
               FROM pto_requests pr
               JOIN employees e ON pr.employee_id = e.id
               WHERE e.manager_id = $1 AND pr.status = 'pending'
               ORDER BY pr.start_date ASC""",
            employee["id"]
        )

        for req in subordinate_requests:
            tasks.append(PendingTask(
                id=req["id"],
                task_type="pto_approval",
                title=f"Review PTO: {req['first_name']} {req['last_name']}",
                description=f"{req['hours']} hours from {req['start_date']} to {req['end_date']}",
                due_date=req["start_date"],
                created_at=req["created_at"]
            ))

    return PortalTasks(tasks=tasks, total=len(tasks))


# ================================
# PTO Management
# ================================

@router.get("/me/pto", response_model=PTOSummary)
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


@router.post("/me/pto/request", response_model=PTORequestResponse)
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


@router.delete("/me/pto/request/{request_id}")
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


# ================================
# Documents
# ================================

@router.get("/me/documents", response_model=EmployeeDocumentListResponse)
async def get_my_documents(
    status_filter: Optional[str] = None,
    employee: dict = Depends(require_employee_record)
):
    """Get documents assigned to the employee."""
    async with get_connection() as conn:
        if status_filter:
            docs = await conn.fetch(
                """SELECT id, org_id, employee_id, doc_type, title, description,
                          storage_path, status, expires_at, signed_at, assigned_by,
                          created_at, updated_at
                   FROM employee_documents
                   WHERE employee_id = $1 AND status = $2
                   ORDER BY created_at DESC""",
                employee["id"], status_filter
            )
        else:
            docs = await conn.fetch(
                """SELECT id, org_id, employee_id, doc_type, title, description,
                          storage_path, status, expires_at, signed_at, assigned_by,
                          created_at, updated_at
                   FROM employee_documents
                   WHERE employee_id = $1
                   ORDER BY
                       CASE WHEN status = 'pending_signature' THEN 0 ELSE 1 END,
                       created_at DESC""",
                employee["id"]
            )

        return EmployeeDocumentListResponse(
            documents=[
                EmployeeDocumentResponse(
                    id=d["id"],
                    org_id=d["org_id"],
                    employee_id=d["employee_id"],
                    doc_type=d["doc_type"],
                    title=d["title"],
                    description=d["description"],
                    storage_path=d["storage_path"],
                    status=d["status"],
                    expires_at=d["expires_at"],
                    signed_at=d["signed_at"],
                    assigned_by=d["assigned_by"],
                    created_at=d["created_at"],
                    updated_at=d["updated_at"]
                ) for d in docs
            ],
            total=len(docs)
        )


@router.get("/me/documents/{document_id}", response_model=EmployeeDocumentResponse)
async def get_document(
    document_id: UUID,
    employee: dict = Depends(require_employee_record)
):
    """Get a specific document."""
    async with get_connection() as conn:
        doc = await conn.fetchrow(
            """SELECT id, org_id, employee_id, doc_type, title, description,
                      storage_path, status, expires_at, signed_at, assigned_by,
                      created_at, updated_at
               FROM employee_documents
               WHERE id = $1 AND employee_id = $2""",
            document_id, employee["id"]
        )

        if not doc:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Document not found"
            )

        return EmployeeDocumentResponse(
            id=doc["id"],
            org_id=doc["org_id"],
            employee_id=doc["employee_id"],
            doc_type=doc["doc_type"],
            title=doc["title"],
            description=doc["description"],
            storage_path=doc["storage_path"],
            status=doc["status"],
            expires_at=doc["expires_at"],
            signed_at=doc["signed_at"],
            assigned_by=doc["assigned_by"],
            created_at=doc["created_at"],
            updated_at=doc["updated_at"]
        )


@router.post("/me/documents/{document_id}/sign", response_model=EmployeeDocumentResponse)
async def sign_document(
    document_id: UUID,
    request: SignDocumentRequest,
    http_request: Request,
    employee: dict = Depends(require_employee_record)
):
    """Sign a document."""
    async with get_connection() as conn:
        # Verify the document belongs to this employee and is pending signature
        doc = await conn.fetchrow(
            """SELECT id, status FROM employee_documents
               WHERE id = $1 AND employee_id = $2""",
            document_id, employee["id"]
        )

        if not doc:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Document not found"
            )

        if doc["status"] != "pending_signature":
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Document is not pending signature"
            )

        # Get client IP
        client_ip = http_request.client.host if http_request.client else None

        # Update the document as signed
        updated = await conn.fetchrow(
            """UPDATE employee_documents
               SET status = 'signed',
                   signed_at = NOW(),
                   signature_data = $1,
                   signature_ip = $2,
                   updated_at = NOW()
               WHERE id = $3
               RETURNING id, org_id, employee_id, doc_type, title, description,
                         storage_path, status, expires_at, signed_at, assigned_by,
                         created_at, updated_at""",
            request.signature_data, client_ip, document_id
        )

        return EmployeeDocumentResponse(
            id=updated["id"],
            org_id=updated["org_id"],
            employee_id=updated["employee_id"],
            doc_type=updated["doc_type"],
            title=updated["title"],
            description=updated["description"],
            storage_path=updated["storage_path"],
            status=updated["status"],
            expires_at=updated["expires_at"],
            signed_at=updated["signed_at"],
            assigned_by=updated["assigned_by"],
            created_at=updated["created_at"],
            updated_at=updated["updated_at"]
        )


# ================================
# Policy Search
# ================================

@router.get("/policies")
async def search_policies(
    q: Optional[str] = None,
    employee: dict = Depends(require_employee_record)
):
    """Search company policies."""
    async with get_connection() as conn:
        if q:
            # Search by title or content
            policies = await conn.fetch(
                """SELECT id, title, description, content, version, status, created_at
                   FROM policies
                   WHERE company_id = $1
                   AND status = 'active'
                   AND (
                       title ILIKE $2 OR
                       description ILIKE $2 OR
                       content ILIKE $2
                   )
                   ORDER BY title ASC""",
                employee["org_id"], f"%{q}%"
            )
        else:
            # List all active policies
            policies = await conn.fetch(
                """SELECT id, title, description, content, version, status, created_at
                   FROM policies
                   WHERE company_id = $1 AND status = 'active'
                   ORDER BY title ASC""",
                employee["org_id"]
            )

        return {
            "policies": [
                {
                    "id": str(p["id"]),
                    "title": p["title"],
                    "description": p["description"],
                    "content": p["content"][:500] + "..." if p["content"] and len(p["content"]) > 500 else p["content"],
                    "version": p["version"],
                    "created_at": p["created_at"].isoformat() if p["created_at"] else None
                } for p in policies
            ],
            "total": len(policies)
        }


@router.get("/policies/{policy_id}")
async def get_policy(
    policy_id: UUID,
    employee: dict = Depends(require_employee_record)
):
    """Get a specific policy."""
    async with get_connection() as conn:
        policy = await conn.fetchrow(
            """SELECT id, title, description, content, file_url, version, status, created_at
               FROM policies
               WHERE id = $1 AND company_id = $2 AND status = 'active'""",
            policy_id, employee["org_id"]
        )

        if not policy:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Policy not found"
            )

        return {
            "id": str(policy["id"]),
            "title": policy["title"],
            "description": policy["description"],
            "content": policy["content"],
            "file_url": policy["file_url"],
            "version": policy["version"],
            "created_at": policy["created_at"].isoformat() if policy["created_at"] else None
        }


# ================================
# Onboarding
# ================================

class OnboardingTaskResponse(BaseModel):
    id: UUID
    title: str
    description: Optional[str]
    category: str
    is_employee_task: bool
    due_date: Optional[date]
    status: str
    completed_at: Optional[datetime]
    notes: Optional[str]
    created_at: datetime

    class Config:
        from_attributes = True


class OnboardingProgress(BaseModel):
    total: int
    completed: int
    pending: int
    tasks: list


class CompleteTaskRequest(BaseModel):
    notes: Optional[str] = None


@router.get("/onboarding", response_model=OnboardingProgress)
async def get_my_onboarding_tasks(
    employee: dict = Depends(require_employee_record)
):
    """Get all onboarding tasks for the current employee."""
    async with get_connection() as conn:
        rows = await conn.fetch(
            """
            SELECT * FROM employee_onboarding_tasks
            WHERE employee_id = $1
            ORDER BY
                CASE WHEN status = 'pending' THEN 0 ELSE 1 END,
                category, due_date, created_at
            """,
            employee["id"]
        )

        tasks = [
            {
                "id": str(row["id"]),
                "title": row["title"],
                "description": row["description"],
                "category": row["category"],
                "is_employee_task": row["is_employee_task"],
                "due_date": row["due_date"].isoformat() if row["due_date"] else None,
                "status": row["status"],
                "completed_at": row["completed_at"].isoformat() if row["completed_at"] else None,
                "notes": row["notes"],
                "created_at": row["created_at"].isoformat() if row["created_at"] else None,
            }
            for row in rows
        ]

        completed = sum(1 for t in tasks if t["status"] == "completed")
        pending = sum(1 for t in tasks if t["status"] == "pending")

        return OnboardingProgress(
            total=len(tasks),
            completed=completed,
            pending=pending,
            tasks=tasks
        )


@router.patch("/onboarding/{task_id}")
async def complete_onboarding_task(
    task_id: UUID,
    request: CompleteTaskRequest,
    employee: dict = Depends(require_employee_record)
):
    """Mark an onboarding task as complete (employee can only complete their own tasks)."""
    async with get_connection() as conn:
        # Get the task
        task = await conn.fetchrow(
            """
            SELECT * FROM employee_onboarding_tasks
            WHERE id = $1 AND employee_id = $2
            """,
            task_id, employee["id"]
        )

        if not task:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Onboarding task not found"
            )

        # Employee can only complete tasks assigned to them (is_employee_task = true)
        if not task["is_employee_task"]:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="This task must be completed by HR/manager"
            )

        if task["status"] == "completed":
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Task is already completed"
            )

        # Get user_id from employee record
        user_id = employee.get("user_id")

        # Update the task
        notes = request.notes if request.notes else None
        await conn.execute(
            """
            UPDATE employee_onboarding_tasks
            SET status = 'completed', completed_at = NOW(), completed_by = $1, notes = $2, updated_at = NOW()
            WHERE id = $3
            """,
            user_id, notes, task_id
        )

        return {
            "message": "Task marked as complete",
            "task_id": str(task_id),
            "status": "completed"
        }
