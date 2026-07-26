"""Employee onboarding / return-to-work task checklist."""
from datetime import date, datetime
from typing import Optional
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel

from app.database import get_connection
from app.matcha.dependencies import require_employee_record

from ._shared import CompleteTaskRequest

router = APIRouter()


class OnboardingTaskResponse(BaseModel):
    id: UUID
    leave_request_id: Optional[UUID] = None
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
                "leave_request_id": str(row["leave_request_id"]) if row["leave_request_id"] else None,
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
