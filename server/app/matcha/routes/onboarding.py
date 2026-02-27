"""
Onboarding template management routes.
Allows admins/clients to create and manage onboarding task templates.
"""
from datetime import datetime
from typing import List, Optional
from uuid import UUID

from fastapi import APIRouter, HTTPException, Depends
from pydantic import BaseModel

from ...database import get_connection
from ..dependencies import require_admin_or_client, get_client_company_id
from ..services.onboarding_state_machine import (
    BLOCK_REASONS,
    all_states,
    event_schema_contract,
    state_machine_map,
)
from ...core.models.auth import CurrentUser

router = APIRouter()


# Request/Response Models
class OnboardingTaskTemplateCreate(BaseModel):
    title: str
    description: Optional[str] = None
    category: str = "admin"  # documents, equipment, training, admin, return_to_work, priority
    is_employee_task: bool = False
    due_days: int = 7
    sort_order: int = 0
    link_type: Optional[str] = None   # 'policy' | 'handbook' | 'url'
    link_id: Optional[UUID] = None
    link_label: Optional[str] = None
    link_url: Optional[str] = None


class OnboardingTaskTemplateUpdate(BaseModel):
    title: Optional[str] = None
    description: Optional[str] = None
    category: Optional[str] = None
    is_employee_task: Optional[bool] = None
    due_days: Optional[int] = None
    is_active: Optional[bool] = None
    sort_order: Optional[int] = None
    link_type: Optional[str] = None
    link_id: Optional[UUID] = None
    link_label: Optional[str] = None
    link_url: Optional[str] = None


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
    link_type: Optional[str] = None
    link_id: Optional[UUID] = None
    link_label: Optional[str] = None
    link_url: Optional[str] = None
    created_at: datetime
    updated_at: datetime

    class Config:
        from_attributes = True


class OnboardingStateMachineResponse(BaseModel):
    states: List[str]
    transitions: dict[str, List[str]]
    block_reasons: List[str]
    event_schema_version: str
    event_required_fields: List[str]
    event_optional_fields: List[str]


class OnboardingFunnelResponse(BaseModel):
    invited: int
    accepted: int
    started: int
    completed: int
    ready_for_day1: int


class OnboardingKPIResponse(BaseModel):
    time_to_ready_p50_days: Optional[float]
    time_to_ready_p90_days: Optional[float]
    completion_before_start_rate: Optional[float]
    automation_success_rate: Optional[float]
    manual_intervention_rate: Optional[float]


class OnboardingBottleneckItem(BaseModel):
    task_title: str
    overdue_count: int
    avg_days_overdue: float


class OnboardingAnalyticsResponse(BaseModel):
    generated_at: datetime
    funnel: OnboardingFunnelResponse
    kpis: OnboardingKPIResponse
    bottlenecks: List[OnboardingBottleneckItem]


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
    # Return-to-work
    {"title": "Fitness-for-Duty Certification", "description": "Submit medical clearance from healthcare provider", "category": "return_to_work", "is_employee_task": True, "due_days": 0, "sort_order": 1},
    {"title": "Modified Duty Agreement", "description": "Review and sign modified duty or accommodation plan", "category": "return_to_work", "is_employee_task": True, "due_days": 1, "sort_order": 2},
    {"title": "Accommodation Review", "description": "Meet with HR to review workplace accommodations", "category": "return_to_work", "is_employee_task": False, "due_days": 3, "sort_order": 3},
    {"title": "Gradual Return Schedule", "description": "Confirm phased return-to-work schedule", "category": "return_to_work", "is_employee_task": False, "due_days": 1, "sort_order": 4},
    {"title": "Benefits Reinstatement Review", "description": "Verify benefits and leave balances are current", "category": "return_to_work", "is_employee_task": False, "due_days": 5, "sort_order": 5},
    {"title": "Manager Check-in", "description": "Schedule return meeting with direct manager", "category": "return_to_work", "is_employee_task": True, "due_days": 3, "sort_order": 6},
]


def _safe_rate(numerator: int, denominator: int) -> Optional[float]:
    if denominator <= 0:
        return None
    return round((numerator / denominator) * 100, 2)


@router.get("/state-machine", response_model=OnboardingStateMachineResponse)
async def get_onboarding_state_machine(
    current_user: CurrentUser = Depends(require_admin_or_client),
):
    """
    Return canonical onboarding lifecycle and event schema contracts.

    This is the phase-1 source of truth for backend/frontend alignment.
    """
    _ = await get_client_company_id(current_user)
    event_contract = event_schema_contract()
    return OnboardingStateMachineResponse(
        states=all_states(),
        transitions=state_machine_map(),
        block_reasons=list(BLOCK_REASONS),
        event_schema_version=event_contract["version"],
        event_required_fields=event_contract["required_fields"],
        event_optional_fields=event_contract["optional_fields"],
    )


@router.get("/analytics", response_model=OnboardingAnalyticsResponse)
async def get_onboarding_analytics(
    current_user: CurrentUser = Depends(require_admin_or_client),
):
    """Return Phase-3 onboarding funnel, KPI, and bottleneck analytics."""
    company_id = await get_client_company_id(current_user)

    async with get_connection() as conn:
        funnel = await conn.fetchrow(
            """
            WITH latest_invites AS (
                SELECT DISTINCT ON (i.employee_id)
                    i.employee_id,
                    i.status
                FROM employee_invitations i
                JOIN employees e ON e.id = i.employee_id
                WHERE e.org_id = $1
                ORDER BY i.employee_id, i.created_at DESC
            ),
            onboarding_progress AS (
                SELECT
                    e.id AS employee_id,
                    COUNT(eot.id)::int AS total_tasks,
                    COUNT(*) FILTER (WHERE eot.status = 'completed')::int AS completed_tasks,
                    COUNT(*) FILTER (WHERE eot.status = 'pending')::int AS pending_tasks
                FROM employees e
                LEFT JOIN employee_onboarding_tasks eot ON eot.employee_id = e.id
                WHERE e.org_id = $1
                GROUP BY e.id
            )
            SELECT
                COUNT(*) FILTER (WHERE li.employee_id IS NOT NULL)::int AS invited,
                COUNT(*) FILTER (WHERE li.status = 'accepted')::int AS accepted,
                COUNT(*) FILTER (WHERE op.total_tasks > 0)::int AS started,
                COUNT(*) FILTER (WHERE op.total_tasks > 0 AND op.pending_tasks = 0)::int AS completed,
                COUNT(*) FILTER (WHERE op.total_tasks > 0 AND op.pending_tasks = 0)::int AS ready_for_day1
            FROM employees e
            LEFT JOIN latest_invites li ON li.employee_id = e.id
            LEFT JOIN onboarding_progress op ON op.employee_id = e.id
            WHERE e.org_id = $1
            """,
            company_id,
        )

        kpi_time = await conn.fetchrow(
            """
            WITH per_employee AS (
                SELECT
                    e.id AS employee_id,
                    e.start_date,
                    first_inv.invited_at,
                    MAX(eot.completed_at) FILTER (WHERE eot.status = 'completed') AS all_completed_at,
                    COUNT(eot.id)::int AS total_tasks,
                    COUNT(*) FILTER (WHERE eot.status = 'completed')::int AS completed_tasks
                FROM employees e
                LEFT JOIN LATERAL (
                    SELECT i.created_at AS invited_at
                    FROM employee_invitations i
                    WHERE i.employee_id = e.id
                    ORDER BY i.created_at ASC
                    LIMIT 1
                ) first_inv ON true
                LEFT JOIN employee_onboarding_tasks eot ON eot.employee_id = e.id
                WHERE e.org_id = $1
                GROUP BY e.id, e.start_date, first_inv.invited_at
            )
            SELECT
                percentile_disc(0.5) WITHIN GROUP (
                    ORDER BY EXTRACT(EPOCH FROM (all_completed_at - invited_at)) / 86400.0
                ) AS p50_days,
                percentile_disc(0.9) WITHIN GROUP (
                    ORDER BY EXTRACT(EPOCH FROM (all_completed_at - invited_at)) / 86400.0
                ) AS p90_days,
                COUNT(*) FILTER (
                    WHERE total_tasks > 0
                      AND completed_tasks = total_tasks
                      AND start_date IS NOT NULL
                      AND all_completed_at::date <= start_date
                )::int AS completed_before_start_count,
                COUNT(*) FILTER (
                    WHERE total_tasks > 0
                      AND completed_tasks = total_tasks
                      AND start_date IS NOT NULL
                )::int AS completed_with_start_date_count
            FROM per_employee
            WHERE invited_at IS NOT NULL
              AND all_completed_at IS NOT NULL
              AND total_tasks > 0
              AND completed_tasks = total_tasks
              AND all_completed_at >= invited_at
            """,
            company_id,
        )

        run_stats = await conn.fetchrow(
            """
            SELECT
                COUNT(*)::int AS total_runs,
                COUNT(*) FILTER (WHERE status = 'completed')::int AS completed_runs,
                COUNT(*) FILTER (WHERE status IN ('failed', 'needs_action'))::int AS intervention_runs
            FROM onboarding_runs
            WHERE company_id = $1
            """,
            company_id,
        )

        bottleneck_rows = await conn.fetch(
            """
            SELECT
                eot.title,
                COUNT(*)::int AS overdue_count,
                AVG((CURRENT_DATE - eot.due_date))::float AS avg_days_overdue
            FROM employee_onboarding_tasks eot
            JOIN employees e ON e.id = eot.employee_id
            WHERE e.org_id = $1
              AND eot.status = 'pending'
              AND eot.due_date IS NOT NULL
              AND eot.due_date < CURRENT_DATE
            GROUP BY eot.title
            ORDER BY overdue_count DESC, avg_days_overdue DESC
            LIMIT 5
            """,
            company_id,
        )

    return OnboardingAnalyticsResponse(
        generated_at=datetime.utcnow(),
        funnel=OnboardingFunnelResponse(
            invited=int(funnel["invited"] or 0),
            accepted=int(funnel["accepted"] or 0),
            started=int(funnel["started"] or 0),
            completed=int(funnel["completed"] or 0),
            ready_for_day1=int(funnel["ready_for_day1"] or 0),
        ),
        kpis=OnboardingKPIResponse(
            time_to_ready_p50_days=float(kpi_time["p50_days"]) if kpi_time and kpi_time["p50_days"] is not None else None,
            time_to_ready_p90_days=float(kpi_time["p90_days"]) if kpi_time and kpi_time["p90_days"] is not None else None,
            completion_before_start_rate=_safe_rate(
                int(kpi_time["completed_before_start_count"] or 0),
                int(kpi_time["completed_with_start_date_count"] or 0),
            ) if kpi_time else None,
            automation_success_rate=_safe_rate(
                int(run_stats["completed_runs"] or 0),
                int(run_stats["total_runs"] or 0),
            ) if run_stats else None,
            manual_intervention_rate=_safe_rate(
                int(run_stats["intervention_runs"] or 0),
                int(run_stats["total_runs"] or 0),
            ) if run_stats else None,
        ),
        bottlenecks=[
            OnboardingBottleneckItem(
                task_title=row["title"],
                overdue_count=int(row["overdue_count"] or 0),
                avg_days_overdue=float(row["avg_days_overdue"] or 0.0),
            )
            for row in bottleneck_rows
        ],
    )


@router.get("/templates", response_model=List[OnboardingTaskTemplateResponse])
async def list_templates(
    category: Optional[str] = None,
    is_active: Optional[bool] = None,
    current_user: CurrentUser = Depends(require_admin_or_client),
):
    """List all onboarding task templates for the company."""
    company_id = await get_client_company_id(current_user)

    async with get_connection() as conn:
        # Bootstrap default templates atomically: acquire a per-company advisory
        # lock inside a transaction so concurrent first-load requests don't each
        # insert the full default set.
        async with conn.transaction():
            await conn.execute(
                "SELECT pg_advisory_xact_lock(hashtext($1::text))",
                str(company_id)
            )
            count = await conn.fetchval(
                "SELECT COUNT(*) FROM onboarding_tasks WHERE org_id = $1",
                company_id
            )
            if count == 0:
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
                link_type=row["link_type"],
                link_id=row["link_id"],
                link_label=row["link_label"],
                link_url=row["link_url"],
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
    valid_categories = ["documents", "equipment", "training", "admin", "return_to_work", "priority"]
    if request.category not in valid_categories:
        raise HTTPException(status_code=400, detail=f"Invalid category. Must be one of: {valid_categories}")

    async with get_connection() as conn:
        row = await conn.fetchrow(
            """
            INSERT INTO onboarding_tasks
                (org_id, title, description, category, is_employee_task, due_days, sort_order,
                 link_type, link_id, link_label, link_url)
            VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9, $10, $11)
            RETURNING *
            """,
            company_id, request.title, request.description,
            request.category, request.is_employee_task,
            request.due_days, request.sort_order,
            request.link_type, request.link_id, request.link_label, request.link_url,
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
            link_type=row["link_type"],
            link_id=row["link_id"],
            link_label=row["link_label"],
            link_url=row["link_url"],
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
            valid_categories = ["documents", "equipment", "training", "admin", "return_to_work", "priority"]
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

        # Link fields — always write when provided (allow clearing with None)
        if request.link_type is not None or "link_type" in request.model_fields_set:
            updates.append(f"link_type = ${param_num}")
            values.append(request.link_type)
            param_num += 1

        if request.link_id is not None or "link_id" in request.model_fields_set:
            updates.append(f"link_id = ${param_num}")
            values.append(request.link_id)
            param_num += 1

        if request.link_label is not None or "link_label" in request.model_fields_set:
            updates.append(f"link_label = ${param_num}")
            values.append(request.link_label)
            param_num += 1

        if request.link_url is not None or "link_url" in request.model_fields_set:
            updates.append(f"link_url = ${param_num}")
            values.append(request.link_url)
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
            link_type=row["link_type"],
            link_id=row["link_id"],
            link_label=row["link_label"],
            link_url=row["link_url"],
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


# ================================
# Notification Settings
# ================================

class NotificationSettingsUpdate(BaseModel):
    email_enabled: bool = True
    hr_escalation_emails: List[str] = []
    reminder_days_before_due: int = 1
    escalate_to_manager_after_days: int = 3
    escalate_to_hr_after_days: int = 5
    timezone: str = "America/New_York"


@router.get("/notification-settings")
async def get_notification_settings(
    current_user: CurrentUser = Depends(require_admin_or_client),
):
    """Get onboarding notification settings for the company."""
    company_id = await get_client_company_id(current_user)

    async with get_connection() as conn:
        row = await conn.fetchrow(
            "SELECT * FROM onboarding_notification_settings WHERE org_id = $1",
            company_id,
        )
        if not row:
            return {
                "email_enabled": True,
                "hr_escalation_emails": [],
                "reminder_days_before_due": 1,
                "escalate_to_manager_after_days": 3,
                "escalate_to_hr_after_days": 5,
                "timezone": "America/New_York",
            }
        return dict(row)


@router.put("/notification-settings")
async def update_notification_settings(
    request: NotificationSettingsUpdate,
    current_user: CurrentUser = Depends(require_admin_or_client),
):
    """Update onboarding notification settings for the company."""
    company_id = await get_client_company_id(current_user)

    async with get_connection() as conn:
        row = await conn.fetchrow(
            """
            INSERT INTO onboarding_notification_settings
                (org_id, email_enabled, hr_escalation_emails, reminder_days_before_due,
                 escalate_to_manager_after_days, escalate_to_hr_after_days, timezone)
            VALUES ($1, $2, $3, $4, $5, $6, $7)
            ON CONFLICT (org_id) DO UPDATE SET
                email_enabled = EXCLUDED.email_enabled,
                hr_escalation_emails = EXCLUDED.hr_escalation_emails,
                reminder_days_before_due = EXCLUDED.reminder_days_before_due,
                escalate_to_manager_after_days = EXCLUDED.escalate_to_manager_after_days,
                escalate_to_hr_after_days = EXCLUDED.escalate_to_hr_after_days,
                timezone = EXCLUDED.timezone,
                updated_at = NOW()
            RETURNING *
            """,
            company_id,
            request.email_enabled,
            request.hr_escalation_emails,
            request.reminder_days_before_due,
            request.escalate_to_manager_after_days,
            request.escalate_to_hr_after_days,
            request.timezone,
        )
        return dict(row)
