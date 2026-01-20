"""
Onboarding template management routes.
Allows admins/clients to create and manage onboarding task templates.
"""
from datetime import datetime
from typing import List, Optional
from uuid import UUID

from fastapi import APIRouter, HTTPException, Depends
from pydantic import BaseModel

from ..database import get_connection
from ..dependencies import require_admin_or_client, get_client_company_id
from ..models.auth import CurrentUser

router = APIRouter()


# Request/Response Models
class OnboardingTaskTemplateCreate(BaseModel):
    title: str
    description: Optional[str] = None
    category: str = "admin"  # documents, equipment, training, admin
    is_employee_task: bool = False
    due_days: int = 7
    sort_order: int = 0


class OnboardingTaskTemplateUpdate(BaseModel):
    title: Optional[str] = None
    description: Optional[str] = None
    category: Optional[str] = None
    is_employee_task: Optional[bool] = None
    due_days: Optional[int] = None
    is_active: Optional[bool] = None
    sort_order: Optional[int] = None


class OnboardingTaskTemplateResponse(BaseModel):
    id: UUID
    org_id: UUID
    title: str
    description: Optional[str]
    category: str
    is_employee_task: bool
    due_days: int
    is_active: bool
    sort_order: int
    created_at: datetime
    updated_at: datetime

    class Config:
        from_attributes = True


# Default templates to create for new companies
DEFAULT_TEMPLATES = [
    # Documents
    {"title": "Complete I-9 Form", "description": "Employment eligibility verification", "category": "documents", "is_employee_task": True, "due_days": 3, "sort_order": 1},
    {"title": "Submit W-4 Form", "description": "Federal tax withholding form", "category": "documents", "is_employee_task": True, "due_days": 3, "sort_order": 2},
    {"title": "Set up Direct Deposit", "description": "Provide banking information for payroll", "category": "documents", "is_employee_task": True, "due_days": 5, "sort_order": 3},
    {"title": "Emergency Contact Form", "description": "Provide emergency contact information", "category": "documents", "is_employee_task": True, "due_days": 3, "sort_order": 4},
    # Equipment
    {"title": "Laptop Setup", "description": "Configure and distribute work laptop", "category": "equipment", "is_employee_task": False, "due_days": 1, "sort_order": 1},
    {"title": "Badge/Access Card", "description": "Issue building access credentials", "category": "equipment", "is_employee_task": False, "due_days": 1, "sort_order": 2},
    {"title": "Software Accounts", "description": "Set up email, Slack, and other software accounts", "category": "equipment", "is_employee_task": False, "due_days": 1, "sort_order": 3},
    # Training
    {"title": "Security Awareness Training", "description": "Complete mandatory security training", "category": "training", "is_employee_task": True, "due_days": 7, "sort_order": 1},
    {"title": "Company Policies Review", "description": "Review and acknowledge company policies", "category": "training", "is_employee_task": True, "due_days": 7, "sort_order": 2},
    {"title": "Team Introduction", "description": "Meet with team members and manager", "category": "training", "is_employee_task": True, "due_days": 5, "sort_order": 3},
    # Admin
    {"title": "Benefits Enrollment", "description": "Enroll in health insurance and other benefits", "category": "admin", "is_employee_task": True, "due_days": 30, "sort_order": 1},
    {"title": "Parking/Transit Setup", "description": "Set up parking pass or transit benefits", "category": "admin", "is_employee_task": True, "due_days": 14, "sort_order": 2},
]


@router.get("/templates", response_model=List[OnboardingTaskTemplateResponse])
async def list_templates(
    category: Optional[str] = None,
    is_active: Optional[bool] = None,
    current_user: CurrentUser = Depends(require_admin_or_client),
):
    """List all onboarding task templates for the company."""
    company_id = await get_client_company_id(current_user)

    async with get_connection() as conn:
        # Check if company has any templates, if not, create defaults
        count = await conn.fetchval(
            "SELECT COUNT(*) FROM onboarding_tasks WHERE org_id = $1",
            company_id
        )

        if count == 0:
            # Create default templates
            for template in DEFAULT_TEMPLATES:
                await conn.execute(
                    """
                    INSERT INTO onboarding_tasks (org_id, title, description, category, is_employee_task, due_days, sort_order)
                    VALUES ($1, $2, $3, $4, $5, $6, $7)
                    """,
                    company_id, template["title"], template["description"],
                    template["category"], template["is_employee_task"],
                    template["due_days"], template["sort_order"]
                )

        # Build query
        query = "SELECT * FROM onboarding_tasks WHERE org_id = $1"
        params = [company_id]
        param_num = 2

        if category:
            query += f" AND category = ${param_num}"
            params.append(category)
            param_num += 1

        if is_active is not None:
            query += f" AND is_active = ${param_num}"
            params.append(is_active)
            param_num += 1

        query += " ORDER BY category, sort_order, title"

        rows = await conn.fetch(query, *params)

        return [
            OnboardingTaskTemplateResponse(
                id=row["id"],
                org_id=row["org_id"],
                title=row["title"],
                description=row["description"],
                category=row["category"],
                is_employee_task=row["is_employee_task"],
                due_days=row["due_days"],
                is_active=row["is_active"],
                sort_order=row["sort_order"],
                created_at=row["created_at"],
                updated_at=row["updated_at"],
            )
            for row in rows
        ]


@router.post("/templates", response_model=OnboardingTaskTemplateResponse)
async def create_template(
    request: OnboardingTaskTemplateCreate,
    current_user: CurrentUser = Depends(require_admin_or_client),
):
    """Create a new onboarding task template."""
    company_id = await get_client_company_id(current_user)

    # Validate category
    valid_categories = ["documents", "equipment", "training", "admin"]
    if request.category not in valid_categories:
        raise HTTPException(status_code=400, detail=f"Invalid category. Must be one of: {valid_categories}")

    async with get_connection() as conn:
        row = await conn.fetchrow(
            """
            INSERT INTO onboarding_tasks (org_id, title, description, category, is_employee_task, due_days, sort_order)
            VALUES ($1, $2, $3, $4, $5, $6, $7)
            RETURNING *
            """,
            company_id, request.title, request.description,
            request.category, request.is_employee_task,
            request.due_days, request.sort_order
        )

        return OnboardingTaskTemplateResponse(
            id=row["id"],
            org_id=row["org_id"],
            title=row["title"],
            description=row["description"],
            category=row["category"],
            is_employee_task=row["is_employee_task"],
            due_days=row["due_days"],
            is_active=row["is_active"],
            sort_order=row["sort_order"],
            created_at=row["created_at"],
            updated_at=row["updated_at"],
        )


@router.put("/templates/{template_id}", response_model=OnboardingTaskTemplateResponse)
async def update_template(
    template_id: UUID,
    request: OnboardingTaskTemplateUpdate,
    current_user: CurrentUser = Depends(require_admin_or_client),
):
    """Update an onboarding task template."""
    company_id = await get_client_company_id(current_user)

    async with get_connection() as conn:
        # Check template exists and belongs to company
        existing = await conn.fetchrow(
            "SELECT * FROM onboarding_tasks WHERE id = $1 AND org_id = $2",
            template_id, company_id
        )
        if not existing:
            raise HTTPException(status_code=404, detail="Template not found")

        # Validate category if provided
        if request.category:
            valid_categories = ["documents", "equipment", "training", "admin"]
            if request.category not in valid_categories:
                raise HTTPException(status_code=400, detail=f"Invalid category. Must be one of: {valid_categories}")

        # Build update query dynamically
        updates = []
        values = []
        param_num = 1

        if request.title is not None:
            updates.append(f"title = ${param_num}")
            values.append(request.title)
            param_num += 1

        if request.description is not None:
            updates.append(f"description = ${param_num}")
            values.append(request.description)
            param_num += 1

        if request.category is not None:
            updates.append(f"category = ${param_num}")
            values.append(request.category)
            param_num += 1

        if request.is_employee_task is not None:
            updates.append(f"is_employee_task = ${param_num}")
            values.append(request.is_employee_task)
            param_num += 1

        if request.due_days is not None:
            updates.append(f"due_days = ${param_num}")
            values.append(request.due_days)
            param_num += 1

        if request.is_active is not None:
            updates.append(f"is_active = ${param_num}")
            values.append(request.is_active)
            param_num += 1

        if request.sort_order is not None:
            updates.append(f"sort_order = ${param_num}")
            values.append(request.sort_order)
            param_num += 1

        if not updates:
            raise HTTPException(status_code=400, detail="No fields to update")

        updates.append("updated_at = NOW()")

        query = f"""
            UPDATE onboarding_tasks
            SET {', '.join(updates)}
            WHERE id = ${param_num} AND org_id = ${param_num + 1}
            RETURNING *
        """
        values.extend([template_id, company_id])

        row = await conn.fetchrow(query, *values)

        return OnboardingTaskTemplateResponse(
            id=row["id"],
            org_id=row["org_id"],
            title=row["title"],
            description=row["description"],
            category=row["category"],
            is_employee_task=row["is_employee_task"],
            due_days=row["due_days"],
            is_active=row["is_active"],
            sort_order=row["sort_order"],
            created_at=row["created_at"],
            updated_at=row["updated_at"],
        )


@router.delete("/templates/{template_id}")
async def delete_template(
    template_id: UUID,
    current_user: CurrentUser = Depends(require_admin_or_client),
):
    """Delete an onboarding task template."""
    company_id = await get_client_company_id(current_user)

    async with get_connection() as conn:
        result = await conn.execute(
            "DELETE FROM onboarding_tasks WHERE id = $1 AND org_id = $2",
            template_id, company_id
        )

        if result == "DELETE 0":
            raise HTTPException(status_code=404, detail="Template not found")

        return {"message": "Template deleted successfully"}
