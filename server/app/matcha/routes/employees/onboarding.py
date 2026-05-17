"""Employee onboarding tasks + batch onboarding wizard draft endpoints.

Routes (employee-scoped):
  GET    /{employee_id}/onboarding                                — list tasks
  POST   /{employee_id}/onboarding                                — assign tasks
  POST   /{employee_id}/onboarding/assign-rtw/{leave_request_id}  — RTW (lazy-imports
                                                                    assign_rtw_tasks from .offboarding
                                                                    to break intra-package cycle)
  POST   /{employee_id}/onboarding/assign-all                     — assign all templates
  PATCH  /{employee_id}/onboarding/{task_id}                      — update task
  DELETE /{employee_id}/onboarding/{task_id}                      — remove task

Routes (admin-scoped onboarding-draft, 1-segment paths shadowed by crud's
/{employee_id} GET/PUT/DELETE — preserved by include_router ordering):
  GET    /onboarding-draft
  PUT    /onboarding-draft
  DELETE /onboarding-draft
"""
import json
import logging
from datetime import datetime, timedelta
from typing import List, Optional
from uuid import UUID

from fastapi import APIRouter, Body, Depends, HTTPException, Query
from pydantic import BaseModel

from app.core.models.auth import CurrentUser
from app.database import get_connection
from app.matcha.dependencies import get_client_company_id, require_admin_or_client

logger = logging.getLogger(__name__)

router = APIRouter()


class EmployeeOnboardingTaskResponse(BaseModel):
    id: UUID
    employee_id: UUID
    task_id: Optional[UUID]
    leave_request_id: Optional[UUID]
    title: str
    description: Optional[str]
    category: str
    is_employee_task: bool
    due_date: Optional[str]
    status: str
    completed_at: Optional[datetime]
    completed_by: Optional[UUID]
    notes: Optional[str]
    document_type: Optional[str] = None
    created_at: datetime

    class Config:
        from_attributes = True


class AssignOnboardingTasksRequest(BaseModel):
    task_ids: Optional[List[UUID]] = None  # Template task IDs to assign
    custom_tasks: Optional[List[dict]] = None  # Custom tasks: {title, description, category, is_employee_task, due_date}
    leave_request_id: Optional[UUID] = None


class UpdateOnboardingTaskRequest(BaseModel):
    status: Optional[str] = None  # pending, completed, skipped
    notes: Optional[str] = None


VALID_ONBOARDING_CATEGORIES = ["documents", "equipment", "training", "admin", "return_to_work"]


@router.get("/{employee_id}/onboarding", response_model=List[EmployeeOnboardingTaskResponse])
async def get_employee_onboarding_tasks(
    employee_id: UUID,
    category: Optional[str] = Query(None),
    leave_request_id: Optional[UUID] = Query(None),
    current_user: CurrentUser = Depends(require_admin_or_client),
):
    """Get all onboarding tasks for an employee."""
    company_id = await get_client_company_id(current_user)
    if category and category not in VALID_ONBOARDING_CATEGORIES:
        raise HTTPException(status_code=400, detail=f"Invalid category. Must be one of: {VALID_ONBOARDING_CATEGORIES}")

    async with get_connection() as conn:
        # Verify employee belongs to company
        employee = await conn.fetchrow(
            "SELECT id FROM employees WHERE id = $1 AND org_id = $2",
            employee_id, company_id
        )
        if not employee:
            raise HTTPException(status_code=404, detail="Employee not found")

        query = """
            SELECT * FROM employee_onboarding_tasks
            WHERE employee_id = $1
        """
        params: list = [employee_id]
        idx = 2

        if category:
            query += f" AND category = ${idx}"
            params.append(category)
            idx += 1

        if leave_request_id:
            query += f" AND leave_request_id = ${idx}"
            params.append(leave_request_id)
            idx += 1

        query += """
            ORDER BY
                CASE WHEN status = 'pending' THEN 0 ELSE 1 END,
                category, due_date, created_at
        """

        rows = await conn.fetch(query, *params)

        return [
            EmployeeOnboardingTaskResponse(
                id=row["id"],
                employee_id=row["employee_id"],
                task_id=row["task_id"],
                leave_request_id=row["leave_request_id"],
                title=row["title"],
                description=row["description"],
                category=row["category"],
                is_employee_task=row["is_employee_task"],
                due_date=str(row["due_date"]) if row["due_date"] else None,
                status=row["status"],
                completed_at=row["completed_at"],
                completed_by=row["completed_by"],
                notes=row["notes"],
                document_type=row.get("document_type"),
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

        if request.leave_request_id:
            leave = await conn.fetchrow(
                """
                SELECT id, employee_id
                FROM leave_requests
                WHERE id = $1 AND org_id = $2
                """,
                request.leave_request_id,
                company_id,
            )
            if not leave or leave["employee_id"] != employee_id:
                raise HTTPException(status_code=400, detail="leave_request_id is invalid for this employee")

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
                    if template["category"] == "return_to_work" and not request.leave_request_id:
                        raise HTTPException(
                            status_code=400,
                            detail="return_to_work tasks require leave_request_id",
                        )
                    due_date = start_date + timedelta(days=template["due_days"])
                    # Skip if this template is already assigned to prevent duplicates
                    # on retries — INSERT only when no matching (employee_id, task_id) exists.
                    row = await conn.fetchrow(
                        """
                        INSERT INTO employee_onboarding_tasks
                        (employee_id, task_id, leave_request_id, title, description, category, is_employee_task, due_date)
                        SELECT $1, $2, $3, $4, $5, $6, $7, $8
                        WHERE NOT EXISTS (
                            SELECT 1 FROM employee_onboarding_tasks
                            WHERE employee_id = $1 AND task_id = $2
                        )
                        RETURNING *
                        """,
                        employee_id,
                        task_id,
                        request.leave_request_id,
                        template["title"],
                        template["description"],
                        template["category"],
                        template["is_employee_task"],
                        due_date,
                    )
                    if row:
                        assigned_tasks.append(row)

        # Assign custom tasks
        if request.custom_tasks:
            for task in request.custom_tasks:
                task_category = task.get("category", "admin")
                if task_category not in VALID_ONBOARDING_CATEGORIES:
                    raise HTTPException(
                        status_code=400,
                        detail=f"Invalid category. Must be one of: {VALID_ONBOARDING_CATEGORIES}",
                    )
                if task_category == "return_to_work" and not request.leave_request_id:
                    raise HTTPException(
                        status_code=400,
                        detail="return_to_work tasks require leave_request_id",
                    )

                due_date = None
                if task.get("due_date"):
                    try:
                        due_date = datetime.strptime(task["due_date"], "%Y-%m-%d").date()
                    except ValueError:
                        pass

                row = await conn.fetchrow(
                    """
                    INSERT INTO employee_onboarding_tasks
                    (employee_id, leave_request_id, title, description, category, is_employee_task, due_date)
                    VALUES ($1, $2, $3, $4, $5, $6, $7)
                    RETURNING *
                    """,
                    employee_id,
                    request.leave_request_id,
                    task.get("title", "Custom Task"),
                    task.get("description"),
                    task_category,
                    task.get("is_employee_task", False),
                    due_date,
                )
                assigned_tasks.append(row)

        return [
            EmployeeOnboardingTaskResponse(
                id=row["id"],
                employee_id=row["employee_id"],
                task_id=row["task_id"],
                leave_request_id=row["leave_request_id"],
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


@router.post(
    "/{employee_id}/onboarding/assign-rtw/{leave_request_id}",
    response_model=List[EmployeeOnboardingTaskResponse],
)
async def assign_return_to_work_tasks(
    employee_id: UUID,
    leave_request_id: UUID,
    current_user: CurrentUser = Depends(require_admin_or_client),
):
    """Assign return-to-work tasks linked to a specific leave request."""
    # Lazy import: assign_rtw_tasks lives in the offboarding submodule (split 2026-05-16);
    # importing at module top would create a circular dep since _legacy is imported
    # by employees/__init__.py before .offboarding is loaded into the same package.
    from app.matcha.routes.employees.offboarding import assign_rtw_tasks

    company_id = await get_client_company_id(current_user)

    async with get_connection() as conn:
        employee = await conn.fetchrow(
            "SELECT id FROM employees WHERE id = $1 AND org_id = $2",
            employee_id,
            company_id,
        )
        if not employee:
            raise HTTPException(status_code=404, detail="Employee not found")

        assigned_tasks = await assign_rtw_tasks(
            employee_id=employee_id,
            leave_request_id=leave_request_id,
            company_id=company_id,
            conn=conn,
        )

        return [
            EmployeeOnboardingTaskResponse(
                id=row["id"],
                employee_id=row["employee_id"],
                task_id=row["task_id"],
                leave_request_id=row["leave_request_id"],
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
        async with conn.transaction():
            # Lock the employee row to serialize concurrent assign-all calls.
            employee = await conn.fetchrow(
                "SELECT id, start_date FROM employees WHERE id = $1 AND org_id = $2 FOR UPDATE",
                employee_id, company_id
            )
            if not employee:
                raise HTTPException(status_code=404, detail="Employee not found")

            # Idempotent: if tasks already assigned return current count rather than erroring,
            # so retries (e.g. from the onboarding agent console) succeed cleanly.
            existing = await conn.fetchval(
                "SELECT COUNT(*) FROM employee_onboarding_tasks WHERE employee_id = $1",
                employee_id
            )
            if existing > 0:
                return {"message": f"Onboarding tasks already assigned", "count": int(existing)}

            start_date = employee["start_date"] or datetime.now().date()

            templates = await conn.fetch(
                """SELECT * FROM onboarding_tasks
                   WHERE org_id = $1 AND is_active = true AND category != 'return_to_work'
                   ORDER BY category, sort_order""",
                company_id
            )

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

        # Notify HR when a task is completed
        if request.status == "completed":
            try:
                notif_settings = await conn.fetchrow(
                    "SELECT email_enabled, hr_escalation_emails FROM onboarding_notification_settings WHERE org_id = $1",
                    company_id,
                )
                if notif_settings and notif_settings["email_enabled"] and notif_settings["hr_escalation_emails"]:
                    emp_row = await conn.fetchrow(
                        "SELECT e.first_name, e.last_name, c.name AS company_name "
                        "FROM employees e JOIN companies c ON c.id = e.org_id "
                        "WHERE e.id = $1",
                        employee_id,
                    )
                    if emp_row:
                        email_svc = get_email_service()
                        emp_name = f"{emp_row['first_name']} {emp_row['last_name']}".strip()
                        co_name = emp_row["company_name"] or "Your Company"
                        for hr_email in notif_settings["hr_escalation_emails"]:
                            try:
                                await email_svc.send_task_completion_notification(
                                    to_email=hr_email,
                                    to_name=hr_email.split("@")[0],
                                    company_name=co_name,
                                    employee_name=emp_name,
                                    task_title=row["title"],
                                )
                            except Exception:
                                logger.warning("Failed to send completion notification to %s", hr_email)
            except Exception:
                logger.exception("Error sending task completion notifications for task %s", task_id)

        return EmployeeOnboardingTaskResponse(
            id=row["id"],
            employee_id=row["employee_id"],
            task_id=row["task_id"],
            leave_request_id=row["leave_request_id"],
            title=row["title"],
            description=row["description"],
            category=row["category"],
            is_employee_task=row["is_employee_task"],
            due_date=str(row["due_date"]) if row["due_date"] else None,
            status=row["status"],
            completed_at=row["completed_at"],
            completed_by=row["completed_by"],
            notes=row["notes"],
            document_type=row.get("document_type"),
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


# ---------------------------------------------------------------------------
# Batch Onboarding Wizard Draft endpoints
# ---------------------------------------------------------------------------

@router.get("/onboarding-draft")
async def get_onboarding_draft(
    current_user: CurrentUser = Depends(require_admin_or_client),
    company_id: Optional[UUID] = Depends(get_client_company_id),
):
    """Retrieve the saved batch onboarding wizard draft for this admin/company."""
    if not company_id:
        raise HTTPException(status_code=403, detail="No company context")

    async with get_connection() as conn:
        row = await conn.fetchrow(
            """
            SELECT draft_state
            FROM employee_onboarding_drafts
            WHERE company_id = $1 AND user_id = $2
            """,
            str(company_id),
            str(current_user.id),
        )

    if not row:
        return None

    state = row["draft_state"]
    if isinstance(state, str):
        try:
            state = json.loads(state)
        except Exception:
            state = {}

    return {"draft_state": state or {}}


@router.put("/onboarding-draft")
async def upsert_onboarding_draft(
    body: dict = Body(...),
    current_user: CurrentUser = Depends(require_admin_or_client),
    company_id: Optional[UUID] = Depends(get_client_company_id),
):
    """Save (upsert) the batch onboarding wizard draft state."""
    if not company_id:
        raise HTTPException(status_code=403, detail="No company context")

    state = body.get("state", {})
    if not isinstance(state, dict):
        raise HTTPException(status_code=422, detail="state must be a JSON object")

    async with get_connection() as conn:
        row = await conn.fetchrow(
            """
            INSERT INTO employee_onboarding_drafts (company_id, user_id, draft_state, updated_at)
            VALUES ($1, $2, $3::jsonb, NOW())
            ON CONFLICT (company_id, user_id) DO UPDATE
            SET draft_state = EXCLUDED.draft_state, updated_at = NOW()
            RETURNING draft_state, updated_at
            """,
            str(company_id),
            str(current_user.id),
            json.dumps(state),
        )

    saved_state = row["draft_state"]
    if isinstance(saved_state, str):
        try:
            saved_state = json.loads(saved_state)
        except Exception:
            saved_state = {}

    return {
        "draft_state": saved_state or {},
        "updated_at": row["updated_at"].isoformat() if row["updated_at"] else None,
    }


@router.delete("/onboarding-draft")
async def delete_onboarding_draft(
    current_user: CurrentUser = Depends(require_admin_or_client),
    company_id: Optional[UUID] = Depends(get_client_company_id),
):
    """Delete the batch onboarding wizard draft."""
    if not company_id:
        raise HTTPException(status_code=403, detail="No company context")

    async with get_connection() as conn:
        result = await conn.execute(
            """
            DELETE FROM employee_onboarding_drafts
            WHERE company_id = $1 AND user_id = $2
            """,
            str(company_id),
            str(current_user.id),
        )

    return {"deleted": result == "DELETE 1"}
