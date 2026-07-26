"""Priority tasks (new-hire to-dos) surfaced on the employee portal home."""
from uuid import UUID

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, status

from app.database import get_connection
from app.matcha.dependencies import require_employee_record

from ._shared import CompleteTaskRequest

router = APIRouter()


@router.get("/priorities")
async def get_my_priority_tasks(
    employee: dict = Depends(require_employee_record)
):
    """Get all priority tasks assigned to the current employee."""
    async with get_connection() as conn:
        rows = await conn.fetch(
            """
            SELECT * FROM employee_onboarding_tasks
            WHERE employee_id = $1 AND category = 'priority'
            ORDER BY
                CASE WHEN status = 'pending' THEN 0 ELSE 1 END,
                due_date NULLS LAST, created_at
            """,
            employee["id"]
        )

        tasks = [
            {
                "id": str(row["id"]),
                "title": row["title"],
                "description": row["description"],
                "due_date": row["due_date"].isoformat() if row["due_date"] else None,
                "status": row["status"],
                "completed_at": row["completed_at"].isoformat() if row["completed_at"] else None,
                "notes": row["notes"],
                "link_type": row["link_type"],
                "link_id": str(row["link_id"]) if row["link_id"] else None,
                "link_label": row["link_label"],
                "link_url": row["link_url"],
                "created_at": row["created_at"].isoformat() if row["created_at"] else None,
            }
            for row in rows
        ]

        completed = sum(1 for t in tasks if t["status"] == "completed")
        pending = sum(1 for t in tasks if t["status"] == "pending")

        return {
            "total": len(tasks),
            "completed": completed,
            "pending": pending,
            "tasks": tasks,
        }


@router.patch("/priorities/{task_id}")
async def complete_priority_task(
    task_id: UUID,
    request: CompleteTaskRequest,
    background_tasks: BackgroundTasks,
    employee: dict = Depends(require_employee_record)
):
    """Mark a priority task as complete and notify HR."""
    async with get_connection() as conn:
        task = await conn.fetchrow(
            """
            SELECT * FROM employee_onboarding_tasks
            WHERE id = $1 AND employee_id = $2 AND category = 'priority'
            """,
            task_id, employee["id"]
        )

        if not task:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Priority task not found"
            )

        if task["status"] == "completed":
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Task is already completed"
            )

        user_id = employee.get("user_id")
        notes = request.notes if request.notes else None

        await conn.execute(
            """
            UPDATE employee_onboarding_tasks
            SET status = 'completed', completed_at = NOW(), completed_by = $1, notes = $2, updated_at = NOW()
            WHERE id = $3
            """,
            user_id, notes, task_id
        )

        # Load notification settings and employee/company info for email
        settings_row = await conn.fetchrow(
            "SELECT hr_escalation_emails, email_enabled FROM onboarding_notification_settings WHERE org_id = $1",
            employee["org_id"]
        )
        company_row = await conn.fetchrow(
            "SELECT name FROM companies WHERE id = $1",
            employee["org_id"]
        )
        company_name = company_row["name"] if company_row else "Your Company"
        employee_name = f"{employee.get('first_name', '')} {employee.get('last_name', '')}".strip()

    # Send email notification in background
    if settings_row and settings_row["email_enabled"] and settings_row["hr_escalation_emails"]:
        from app.core.services.email import EmailService

        async def _send_notifications():
            email_service = EmailService()
            for hr_email in settings_row["hr_escalation_emails"]:
                await email_service.send_task_completion_notification(
                    to_email=hr_email,
                    to_name="HR Team",
                    company_name=company_name,
                    employee_name=employee_name,
                    task_title=task["title"],
                )

        background_tasks.add_task(_send_notifications)

    # Broadcast in-app notification to the company's WebSocket channel
    try:
        from app.core.services.notification_manager import get_notification_manager
        manager = get_notification_manager()
        await manager.broadcast_to_channel(
            f"company:{employee['org_id']}",
            {
                "type": "priority_completed",
                "employee_id": str(employee["id"]),
                "employee_name": employee_name,
                "task_id": str(task_id),
                "task_title": task["title"],
            }
        )
    except Exception:
        pass  # WebSocket broadcast is best-effort

    return {
        "message": "Priority task marked as complete",
        "task_id": str(task_id),
        "status": "completed"
    }
