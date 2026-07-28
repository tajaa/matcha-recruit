"""Portal dashboard + profile self-service."""
from datetime import datetime
from decimal import Decimal

from fastapi import APIRouter, Depends, HTTPException, status

from app.database import get_connection
from app.core.feature_flags import default_company_features_json
from app.matcha.models.employees.employee import (
    EmployeeResponse, ProfileUpdateRequest,
    PTOBalanceResponse,
    PortalDashboard, PortalTasks, PendingTask,
)
from app.matcha.dependencies import require_employee_record

router = APIRouter()


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
                job_title=employee.get("job_title"),
                department=employee.get("department"),
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
    import json as _json
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

        # Include pending onboarding / return-to-work tasks assigned to the employee
        onboarding_rows = await conn.fetch(
            """SELECT id, title, description, category, due_date, created_at
               FROM employee_onboarding_tasks
               WHERE employee_id = $1
                 AND status = 'pending'
                 AND is_employee_task = true
               ORDER BY due_date ASC NULLS LAST, created_at DESC""",
            employee["id"],
        )

        for task in onboarding_rows:
            task_type = "return_to_work_task" if task["category"] == "return_to_work" else "onboarding_task"
            tasks.append(PendingTask(
                id=task["id"],
                task_type=task_type,
                title=task["title"],
                description=task["description"],
                due_date=task["due_date"],
                created_at=task["created_at"],
            ))

        # Only show PTO approval tasks if time_off feature is enabled
        features_row = await conn.fetchval(
            """SELECT COALESCE(comp.enabled_features, $2::jsonb)
               FROM companies comp WHERE comp.id = $1""",
            employee["org_id"],
            default_company_features_json(),
        )
        features = _json.loads(features_row) if isinstance(features_row, str) else (features_row or {})

        if features.get("time_off", False):
            # Get pending PTO requests awaiting manager approval (for managers)
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
