"""
Admin routes for employee management.
Allows admins/clients to create, update, delete employees and send invitations.
"""
import asyncio
import csv
import io
import json
import logging
import re
import secrets
from datetime import datetime, date, timedelta
from decimal import Decimal
from typing import List, Optional
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, UploadFile, File, Query, Body, BackgroundTasks
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, EmailStr, Field, model_validator

from app.database import get_connection
from app.core.dependencies import get_current_user
from app.matcha.dependencies import require_admin_or_client, get_client_company_id, require_feature
from app.core.models.auth import CurrentUser
from app.core.services.compliance_service import ensure_location_for_employee
from app.core.services.credential_crypto import encrypt_credential_fields, decrypt_credential_fields
from app.core.services.storage import get_storage
from app.core.services.email import get_email_service
from app.matcha.services.onboarding_orchestrator import (
    PROVIDER_GOOGLE_WORKSPACE,
    PROVIDER_SLACK,
    start_google_workspace_onboarding,
    start_slack_onboarding,
)
from app.matcha.services.risk_assessment_service import compute_risk_assessment, generate_recommendations, DEFAULT_WEIGHTS

logger = logging.getLogger(__name__)

router = APIRouter()

from app.matcha.routes.employees._shared import (
    INVITATION_SEND_FAILED_DETAIL,
    _json_object,
    _coerce_bool,
    _exception_message,
    _parse_csv_date,
    _column_exists,
    _employee_compensation_fields_available,
    _employee_status_fields_available,
    _employee_org_fields_available,
    _sync_employee_location_for_compliance,
    _employee_compensation_values,
    send_single_invitation,
    _send_invitation_with_conn,
    _auto_send_invitation,
    _refresh_risk_assessment,
    _perform_oig_screening,
    _run_provisioning_and_notify,
    _send_provisioning_email,
)
# Request/Response Models
class EmployeeCreateRequest(BaseModel):
    email: Optional[EmailStr] = None  # Legacy alias for work_email
    work_email: Optional[EmailStr] = None
    personal_email: Optional[EmailStr] = None
    first_name: str
    last_name: str
    work_state: Optional[str] = None
    address: Optional[str] = None
    employment_type: Optional[str] = None
    start_date: Optional[str] = None
    manager_id: Optional[UUID] = None
    is_supervisor: Optional[bool] = None
    skip_google_workspace_provisioning: bool = False
    skip_invitation: bool = False
    pay_classification: Optional[str] = None
    pay_rate: Optional[Decimal] = None
    work_city: Optional[str] = None
    job_title: Optional[str] = None
    department: Optional[str] = None
    uid: Optional[str] = None  # HR-internal badge / employee number

    @model_validator(mode="after")
    def validate_work_email_present(self):
        if not self.work_email and not self.email:
            raise ValueError("work_email (or legacy email) is required")
        return self

    @model_validator(mode="after")
    def validate_pay_fields(self):
        if self.pay_rate is not None and self.pay_classification is None:
            raise ValueError("pay_classification is required when pay_rate is provided")
        if self.pay_classification is not None and self.pay_classification not in ("hourly", "exempt"):
            raise ValueError("pay_classification must be 'hourly' or 'exempt'")
        if self.pay_rate is not None and self.pay_rate < 0:
            raise ValueError("pay_rate must be >= 0")
        return self

    def resolved_work_email(self) -> str:
        value = self.work_email or self.email
        return str(value).strip().lower() if value else ""


class EmployeeUpdateRequest(BaseModel):
    work_email: Optional[EmailStr] = None
    personal_email: Optional[EmailStr] = None
    first_name: Optional[str] = None
    last_name: Optional[str] = None
    work_state: Optional[str] = None
    employment_type: Optional[str] = None
    start_date: Optional[str] = None
    termination_date: Optional[str] = None
    manager_id: Optional[UUID] = None
    is_supervisor: Optional[bool] = None
    phone: Optional[str] = None
    address: Optional[str] = None
    pay_classification: Optional[str] = None
    pay_rate: Optional[Decimal] = None
    work_city: Optional[str] = None
    job_title: Optional[str] = None
    department: Optional[str] = None

    @model_validator(mode="after")
    def validate_pay_fields(self):
        if self.pay_classification is not None and self.pay_classification not in ("hourly", "exempt"):
            raise ValueError("pay_classification must be 'hourly' or 'exempt'")
        if self.pay_rate is not None and self.pay_rate < 0:
            raise ValueError("pay_rate must be >= 0")
        return self


VALID_EMPLOYMENT_STATUSES = {"active", "on_leave", "suspended", "on_notice", "furloughed", "terminated", "offboarded"}


class EmployeeStatusUpdateRequest(BaseModel):
    employment_status: str  # active, on_leave, suspended, on_notice, furloughed, terminated, offboarded
    reason: Optional[str] = None


class EmployeeListResponse(BaseModel):
    id: UUID
    email: str
    work_email: Optional[str] = None
    personal_email: Optional[str] = None
    first_name: str
    last_name: str
    work_state: Optional[str]
    employment_type: Optional[str]
    start_date: Optional[str]
    termination_date: Optional[str]
    manager_id: Optional[UUID]
    manager_name: Optional[str]
    is_supervisor: bool = False
    user_id: Optional[UUID]
    invitation_status: Optional[str]
    pay_classification: Optional[str] = None
    pay_rate: Optional[float] = None
    work_city: Optional[str] = None
    job_title: Optional[str] = None
    department: Optional[str] = None
    employment_status: Optional[str] = None
    status_changed_at: Optional[datetime] = None
    status_reason: Optional[str] = None
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
    employment_status: Optional[str] = Query(None, description="Filter by employment_status column"),
    search: Optional[str] = Query(None, min_length=1, max_length=200),
    department: Optional[str] = Query(None),
    employment_type: Optional[str] = Query(None),
    work_state: Optional[str] = Query(None),
    work_city: Optional[str] = Query(None),
    manager_id: Optional[UUID] = Query(None),
    current_user: CurrentUser = Depends(require_admin_or_client),
):
    """List all employees for the company."""
    company_id = await get_client_company_id(current_user)

    async with get_connection() as conn:
        compensation_fields_available = await _employee_compensation_fields_available(conn)
        org_fields_available = await _employee_org_fields_available(conn)
        status_fields_available = await _employee_status_fields_available(conn)
        compensation_select = (
            "e.pay_classification, e.pay_rate, e.work_city,"
            if compensation_fields_available
            else "NULL::VARCHAR AS pay_classification, NULL::NUMERIC AS pay_rate, NULL::VARCHAR AS work_city,"
        )
        org_select = (
            "e.job_title, e.department,"
            if org_fields_available
            else "NULL::VARCHAR AS job_title, NULL::VARCHAR AS department,"
        )
        status_select = (
            "e.employment_status, e.status_changed_at, e.status_reason,"
            if status_fields_available
            else "NULL::VARCHAR AS employment_status, NULL::TIMESTAMP AS status_changed_at, NULL::TEXT AS status_reason,"
        )

        # Build query based on status filter
        base_query = f"""
            SELECT
                e.id, e.email, e.personal_email, e.first_name, e.last_name, e.work_state,
                e.employment_type, e.start_date, e.termination_date,
                e.manager_id, e.is_supervisor, e.user_id, e.created_at,
                {compensation_select}
                {org_select}
                {status_select}
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

        params: list = [company_id]
        param_num = 2

        if status == "active":
            base_query += " AND e.termination_date IS NULL AND e.user_id IS NOT NULL"
        elif status == "terminated":
            base_query += " AND e.termination_date IS NOT NULL"
        elif status == "invited":
            base_query += " AND e.user_id IS NULL"

        if employment_status and status_fields_available:
            base_query += f" AND e.employment_status = ${param_num}"
            params.append(employment_status)
            param_num += 1

        if search:
            search_pattern = f"%{search}%"
            search_cols = ["e.first_name", "e.last_name", "e.email"]
            if org_fields_available:
                search_cols.extend(["e.job_title", "e.department"])
            ilike_clauses = " OR ".join(f"{col} ILIKE ${param_num}" for col in search_cols)
            base_query += f" AND ({ilike_clauses})"
            params.append(search_pattern)
            param_num += 1

        if department and org_fields_available:
            base_query += f" AND e.department = ${param_num}"
            params.append(department)
            param_num += 1

        if employment_type:
            base_query += f" AND e.employment_type = ${param_num}"
            params.append(employment_type)
            param_num += 1

        if work_state:
            base_query += f" AND e.work_state = ${param_num}"
            params.append(work_state)
            param_num += 1

        if work_city and compensation_fields_available:
            base_query += f" AND e.work_city = ${param_num}"
            params.append(work_city)
            param_num += 1

        if manager_id:
            base_query += f" AND e.manager_id = ${param_num}"
            params.append(manager_id)
            param_num += 1

        base_query += " ORDER BY e.created_at DESC"

        rows = await conn.fetch(base_query, *params)

        responses = []
        for row in rows:
            pay_classification, pay_rate, _work_city = _employee_compensation_values(
                row, compensation_fields_available
            )
            responses.append(
                EmployeeListResponse(
                    id=row["id"],
                    email=row["email"],
                    work_email=row["email"],
                    personal_email=row["personal_email"],
                    first_name=row["first_name"],
                    last_name=row["last_name"],
                    work_state=row["work_state"],
                    employment_type=row["employment_type"],
                    start_date=str(row["start_date"]) if row["start_date"] else None,
                    termination_date=str(row["termination_date"]) if row["termination_date"] else None,
                    manager_id=row["manager_id"],
                    manager_name=row["manager_name"],
                    is_supervisor=bool(row["is_supervisor"]),
                    user_id=row["user_id"],
                    invitation_status=row["invitation_status"],
                    pay_classification=pay_classification,
                    pay_rate=pay_rate,
                    work_city=_work_city,
                    job_title=row["job_title"],
                    department=row["department"],
                    employment_status=row["employment_status"],
                    status_changed_at=row["status_changed_at"],
                    status_reason=row["status_reason"],
                    created_at=row["created_at"],
                )
            )

        return responses


@router.get("/departments")
async def list_departments(
    current_user: CurrentUser = Depends(require_admin_or_client),
):
    """Return distinct department names for the company."""
    company_id = await get_client_company_id(current_user)
    async with get_connection() as conn:
        if not await _employee_org_fields_available(conn):
            return []
        rows = await conn.fetch(
            "SELECT DISTINCT department FROM employees WHERE org_id = $1 AND department IS NOT NULL ORDER BY department",
            company_id,
        )
        return [row["department"] for row in rows]


@router.get("/locations")
async def list_locations(
    current_user: CurrentUser = Depends(require_admin_or_client),
):
    """Return distinct state/city pairs for the company."""
    company_id = await get_client_company_id(current_user)
    async with get_connection() as conn:
        has_city = await _column_exists(conn, "employees", "work_city")
        if has_city:
            rows = await conn.fetch(
                """
                SELECT DISTINCT work_state, work_city FROM employees
                WHERE org_id = $1 AND work_state IS NOT NULL
                ORDER BY work_state, work_city
                """,
                company_id,
            )
            return [{"state": r["work_state"], "city": r["work_city"]} for r in rows]
        else:
            rows = await conn.fetch(
                """
                SELECT DISTINCT work_state FROM employees
                WHERE org_id = $1 AND work_state IS NOT NULL
                ORDER BY work_state
                """,
                company_id,
            )
            return [{"state": r["work_state"], "city": None} for r in rows]


@router.get("/by-uid/{uid}")
async def get_employee_by_uid(
    uid: str,
    current_user: CurrentUser = Depends(require_admin_or_client),
):
    """Resolve an HR-internal UID to an employee record (id + name + email).

    Used by the IR incident form so HR admins can identify involved
    employees by badge / employee number instead of UUID. Scoped to the
    caller's company.
    """
    company_id = await get_client_company_id(current_user)
    if company_id is None:
        raise HTTPException(status_code=400, detail="No company associated")
    async with get_connection() as conn:
        if not await _column_exists(conn, "employees", "external_uid"):
            raise HTTPException(status_code=404, detail="Employee not found")
        row = await conn.fetchrow(
            """
            SELECT id, first_name, last_name, email, external_uid
            FROM employees
            WHERE org_id = $1 AND external_uid = $2
            LIMIT 1
            """,
            company_id, uid,
        )
    if not row:
        raise HTTPException(status_code=404, detail="Employee not found")
    return {
        "employee_id": str(row["id"]),
        "first_name": row["first_name"],
        "last_name": row["last_name"],
        "email": row["email"],
        "uid": row["external_uid"],
    }


@router.post("", response_model=EmployeeDetailResponse)
async def create_employee(
    request: EmployeeCreateRequest,
    background_tasks: BackgroundTasks,
    current_user: CurrentUser = Depends(require_admin_or_client),
):
    """Create a new employee record (without user account yet)."""
    company_id = await get_client_company_id(current_user)

    async with get_connection() as conn:
        compensation_fields_available = await _employee_compensation_fields_available(conn)
        work_email = request.resolved_work_email()

        # Check if email already exists for this company
        existing = await conn.fetchval(
            "SELECT id FROM employees WHERE org_id = $1 AND email = $2",
            company_id, work_email
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

        org_fields_available = await _employee_org_fields_available(conn)

        # Build dynamic INSERT columns/values based on available schema
        insert_cols = [
            "org_id", "email", "personal_email", "first_name", "last_name",
            "work_state", "employment_type", "start_date", "address", "manager_id",
            "is_supervisor",
        ]
        insert_vals = [
            company_id,
            work_email,
            str(request.personal_email).strip().lower() if request.personal_email else None,
            request.first_name,
            request.last_name,
            request.work_state,
            request.employment_type,
            start_date,
            request.address.strip() if request.address else None,
            request.manager_id,
            bool(request.is_supervisor) if request.is_supervisor is not None else False,
        ]

        if compensation_fields_available:
            insert_cols.extend(["pay_classification", "pay_rate", "work_city"])
            insert_vals.extend([
                request.pay_classification,
                request.pay_rate,
                request.work_city.strip() if request.work_city else None,
            ])
        elif request.pay_classification or request.pay_rate is not None or request.work_city:
            logger.warning(
                "Skipping employee compensation fields until employees schema is migrated for company %s",
                company_id,
            )

        if org_fields_available:
            insert_cols.extend(["job_title", "department"])
            insert_vals.extend([
                request.job_title.strip() if request.job_title else None,
                request.department.strip() if request.department else None,
            ])

        if request.uid and await _column_exists(conn, "employees", "external_uid"):
            insert_cols.append("external_uid")
            insert_vals.append(request.uid.strip())

        placeholders = ", ".join(f"${i}" for i in range(1, len(insert_vals) + 1))
        col_list = ", ".join(insert_cols)

        row = await conn.fetchrow(
            f"""
            INSERT INTO employees ({col_list})
            VALUES ({placeholders})
            RETURNING *
            """,
            *insert_vals,
        )

        await _sync_employee_location_for_compliance(
            conn,
            company_id=company_id,
            employee_id=row["id"],
            work_state=row["work_state"],
            work_city=row["work_city"] if compensation_fields_available else None,
            background_tasks=background_tasks,
        )

        # Auto-assign active onboarding task templates to the new employee
        try:
            template_rows = await conn.fetch(
                "SELECT id, title, description, category, is_employee_task, due_days, "
                "link_type, link_id, link_label, link_url "
                "FROM onboarding_tasks WHERE org_id = $1 AND is_active = TRUE ORDER BY sort_order",
                company_id,
            )
            if template_rows:
                base_date = start_date or date.today()
                for tmpl in template_rows:
                    due = base_date + timedelta(days=tmpl["due_days"])
                    await conn.execute(
                        "INSERT INTO employee_onboarding_tasks "
                        "(id, employee_id, task_id, title, description, category, is_employee_task, due_date, status, "
                        "link_type, link_id, link_label, link_url) "
                        "VALUES (gen_random_uuid(), $1, $2, $3, $4, $5, $6, $7, 'pending', $8, $9, $10, $11)",
                        row["id"],
                        tmpl["id"],
                        tmpl["title"],
                        tmpl["description"],
                        tmpl["category"],
                        tmpl["is_employee_task"],
                        due,
                        tmpl["link_type"],
                        tmpl["link_id"],
                        tmpl["link_label"],
                        tmpl["link_url"],
                    )
        except Exception:
            logger.exception("Failed to auto-assign onboarding tasks for employee %s", row["id"])

        # Auto-create credential onboarding tasks based on job title + jurisdiction
        try:
            from app.core.services.credential_template_service import (
                resolve_credential_requirements,
                assign_credential_requirements_to_employee,
            )
            job_title_val = None
            if org_fields_available:
                job_title_val = row.get("job_title")
            if not job_title_val:
                job_title_val = body.job_title
            work_state = row.get("work_state")
            work_city = row.get("work_city") if compensation_fields_available else None
            cred_reqs = await resolve_credential_requirements(
                conn, company_id, work_state, work_city, job_title_val,
            )
            if cred_reqs:
                count = await assign_credential_requirements_to_employee(
                    conn, row["id"], company_id, cred_reqs, start_date,
                )
                logger.info("Created %d credential requirements for employee %s (%s)", count, row["id"], job_title_val)
        except Exception:
            logger.exception("Failed to auto-create credential tasks for employee %s", row["id"])

        google_workspace_auto_provision = False
        slack_auto_provision = False
        try:
            integration_rows = await conn.fetch(
                """
                SELECT provider, config
                FROM integration_connections
                WHERE company_id = $1
                  AND status = 'connected'
                """,
                company_id,
            )
            for integration_row in integration_rows:
                integration_config = _json_object(integration_row["config"])
                if integration_row["provider"] == PROVIDER_GOOGLE_WORKSPACE:
                    google_workspace_auto_provision = _coerce_bool(
                        integration_config.get("auto_provision_on_employee_create"),
                        True,
                    )
                elif integration_row["provider"] == PROVIDER_SLACK:
                    slack_auto_provision = _coerce_bool(
                        integration_config.get("auto_invite_on_employee_create"),
                        True,
                    )
        except Exception:
            logger.exception("Unable to evaluate integration connection statuses for company %s", company_id)

        pay_classification, pay_rate, work_city = _employee_compensation_values(
            row, compensation_fields_available
        )

        response = EmployeeDetailResponse(
            id=row["id"],
            email=row["email"],
            work_email=row["email"],
            personal_email=row["personal_email"],
            first_name=row["first_name"],
            last_name=row["last_name"],
            work_state=row["work_state"],
            employment_type=row["employment_type"],
            start_date=str(row["start_date"]) if row["start_date"] else None,
            termination_date=str(row["termination_date"]) if row["termination_date"] else None,
            manager_id=row["manager_id"],
            manager_name=None,
            is_supervisor=bool(row.get("is_supervisor", False)) if hasattr(row, "get") else bool(row["is_supervisor"]),
            user_id=row["user_id"],
            invitation_status=None,
            pay_classification=pay_classification,
            pay_rate=pay_rate,
            work_city=work_city,
            job_title=row.get("job_title"),
            department=row.get("department"),
            phone=row["phone"],
            address=row["address"],
            emergency_contact=row["emergency_contact"],
            created_at=row["created_at"],
            updated_at=row["updated_at"],
        )

        run_google = google_workspace_auto_provision and not request.skip_google_workspace_provisioning
        run_slack = slack_auto_provision

        if run_google or run_slack:
            personal_email = str(request.personal_email).strip().lower() if request.personal_email else None
            background_tasks.add_task(
                _run_provisioning_and_notify,
                company_id=row["org_id"],
                employee_id=row["id"],
                triggered_by=current_user.id,
                personal_email=personal_email,
                employee_name=f"{request.first_name} {request.last_name}".strip(),
                work_email=row["email"],
                run_google=run_google,
                run_slack=run_slack,
            )

        # Auto-send invitation if enabled in notification settings
        if not request.skip_invitation:
            try:
                settings = await conn.fetchrow(
                    "SELECT auto_send_invitation FROM onboarding_notification_settings WHERE org_id = $1",
                    company_id,
                )
                if settings and settings["auto_send_invitation"]:
                    background_tasks.add_task(
                        _auto_send_invitation,
                        employee_id=row["id"],
                        org_id=company_id,
                        invited_by=current_user.id,
                    )
            except Exception:
                logger.exception("Auto-invite check failed for employee %s", row["id"])

        # OIG exclusion screening (healthcare companies)
        background_tasks.add_task(
            _perform_oig_screening,
            employee_id=row["id"],
            org_id=company_id,
            first_name=request.first_name,
            last_name=request.last_name,
        )

        return response


@router.get("/{employee_id}", response_model=EmployeeDetailResponse)
async def get_employee(
    employee_id: UUID,
    current_user: CurrentUser = Depends(require_admin_or_client),
):
    """Get employee details."""
    company_id = await get_client_company_id(current_user)

    async with get_connection() as conn:
        compensation_fields_available = await _employee_compensation_fields_available(conn)
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

        pay_classification, pay_rate, work_city = _employee_compensation_values(
            row, compensation_fields_available
        )

        return EmployeeDetailResponse(
            id=row["id"],
            email=row["email"],
            work_email=row["email"],
            personal_email=row["personal_email"],
            first_name=row["first_name"],
            last_name=row["last_name"],
            work_state=row["work_state"],
            employment_type=row["employment_type"],
            start_date=str(row["start_date"]) if row["start_date"] else None,
            termination_date=str(row["termination_date"]) if row["termination_date"] else None,
            manager_id=row["manager_id"],
            manager_name=row["manager_name"],
            is_supervisor=bool(row["is_supervisor"]) if "is_supervisor" in row.keys() else False,
            user_id=row["user_id"],
            invitation_status=row["invitation_status"],
            pay_classification=pay_classification,
            pay_rate=pay_rate,
            work_city=work_city,
            job_title=row.get("job_title"),
            department=row.get("department"),
            employment_status=row.get("employment_status"),
            status_changed_at=row.get("status_changed_at"),
            status_reason=row.get("status_reason"),
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
    background_tasks: BackgroundTasks,
    current_user: CurrentUser = Depends(require_admin_or_client),
):
    """Update employee details."""
    company_id = await get_client_company_id(current_user)

    async with get_connection() as conn:
        compensation_fields_available = await _employee_compensation_fields_available(conn)
        org_fields_available = await _employee_org_fields_available(conn)
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

        if request.work_email is not None:
            normalized_work_email = str(request.work_email).strip().lower()
            duplicate = await conn.fetchval(
                "SELECT id FROM employees WHERE org_id = $1 AND email = $2 AND id <> $3",
                company_id,
                normalized_work_email,
                employee_id,
            )
            if duplicate:
                raise HTTPException(status_code=400, detail="Employee with this email already exists")
            updates.append(f"email = ${param_num}")
            values.append(normalized_work_email)
            param_num += 1

        if request.personal_email is not None:
            updates.append(f"personal_email = ${param_num}")
            values.append(str(request.personal_email).strip().lower() if request.personal_email else None)
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

        if request.is_supervisor is not None:
            updates.append(f"is_supervisor = ${param_num}")
            values.append(bool(request.is_supervisor))
            param_num += 1

        if request.phone is not None:
            updates.append(f"phone = ${param_num}")
            values.append(request.phone)
            param_num += 1

        if request.address is not None:
            updates.append(f"address = ${param_num}")
            values.append(request.address)
            param_num += 1

        if compensation_fields_available and request.pay_classification is not None:
            updates.append(f"pay_classification = ${param_num}")
            values.append(request.pay_classification)
            param_num += 1

        if compensation_fields_available and request.pay_rate is not None:
            updates.append(f"pay_rate = ${param_num}")
            values.append(request.pay_rate)
            param_num += 1

        if compensation_fields_available and request.work_city is not None:
            updates.append(f"work_city = ${param_num}")
            values.append(request.work_city.strip())
            param_num += 1

        if org_fields_available and request.job_title is not None:
            updates.append(f"job_title = ${param_num}")
            values.append(request.job_title.strip() if request.job_title else None)
            param_num += 1

        if org_fields_available and request.department is not None:
            updates.append(f"department = ${param_num}")
            values.append(request.department.strip() if request.department else None)
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

        if request.work_state is not None or (compensation_fields_available and request.work_city is not None):
            await _sync_employee_location_for_compliance(
                conn,
                company_id=company_id,
                employee_id=row["id"],
                work_state=row["work_state"],
                work_city=row["work_city"] if compensation_fields_available else None,
                background_tasks=background_tasks,
            )

        # Refresh risk assessment snapshot when wage data changes
        if compensation_fields_available and (
            request.pay_rate is not None or request.pay_classification is not None
        ):
            background_tasks.add_task(_refresh_risk_assessment, company_id)

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

        pay_classification, pay_rate, work_city = _employee_compensation_values(
            row, compensation_fields_available
        )

        return EmployeeDetailResponse(
            id=row["id"],
            email=row["email"],
            work_email=row["email"],
            personal_email=row["personal_email"],
            first_name=row["first_name"],
            last_name=row["last_name"],
            work_state=row["work_state"],
            employment_type=row["employment_type"],
            start_date=str(row["start_date"]) if row["start_date"] else None,
            termination_date=str(row["termination_date"]) if row["termination_date"] else None,
            manager_id=row["manager_id"],
            manager_name=manager_name,
            is_supervisor=bool(row["is_supervisor"]) if "is_supervisor" in row.keys() else False,
            user_id=row["user_id"],
            invitation_status=invitation_status,
            pay_classification=pay_classification,
            pay_rate=pay_rate,
            work_city=work_city,
            job_title=row.get("job_title"),
            department=row.get("department"),
            employment_status=row.get("employment_status"),
            status_changed_at=row.get("status_changed_at"),
            status_reason=row.get("status_reason"),
            phone=row["phone"],
            address=row["address"],
            emergency_contact=row["emergency_contact"],
            created_at=row["created_at"],
            updated_at=row["updated_at"],
        )


@router.put("/{employee_id}/status")
async def update_employee_status(
    employee_id: UUID,
    request: EmployeeStatusUpdateRequest,
    user: CurrentUser = Depends(require_admin_or_client),
    company_id: UUID = Depends(get_client_company_id),
):
    """Update the employment status of an employee."""
    if request.employment_status not in VALID_EMPLOYMENT_STATUSES:
        raise HTTPException(
            status_code=400,
            detail=f"Invalid employment_status. Must be one of: {sorted(VALID_EMPLOYMENT_STATUSES)}",
        )

    async with get_connection() as conn:
        status_fields_available = await _employee_status_fields_available(conn)
        if not status_fields_available:
            raise HTTPException(
                status_code=500,
                detail="Employment status columns not yet available. Run the migration first.",
            )

        row = await conn.fetchrow(
            """
            UPDATE employees
            SET employment_status = $1, status_changed_at = NOW(), status_reason = $2, updated_at = NOW()
            WHERE id = $3 AND org_id = $4
            RETURNING *
            """,
            request.employment_status,
            request.reason,
            employee_id,
            company_id,
        )

        if not row:
            raise HTTPException(status_code=404, detail="Employee not found")

        compensation_fields_available = await _employee_compensation_fields_available(conn)

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

        pay_classification, pay_rate, work_city = _employee_compensation_values(
            row, compensation_fields_available
        )

        return EmployeeDetailResponse(
            id=row["id"],
            email=row["email"],
            work_email=row["email"],
            personal_email=row["personal_email"],
            first_name=row["first_name"],
            last_name=row["last_name"],
            work_state=row["work_state"],
            employment_type=row["employment_type"],
            start_date=str(row["start_date"]) if row["start_date"] else None,
            termination_date=str(row["termination_date"]) if row["termination_date"] else None,
            manager_id=row["manager_id"],
            manager_name=manager_name,
            is_supervisor=bool(row["is_supervisor"]) if "is_supervisor" in row.keys() else False,
            user_id=row["user_id"],
            invitation_status=invitation_status,
            pay_classification=pay_classification,
            pay_rate=pay_rate,
            work_city=work_city,
            job_title=row.get("job_title"),
            department=row.get("department"),
            employment_status=row.get("employment_status"),
            status_changed_at=row.get("status_changed_at"),
            status_reason=row.get("status_reason"),
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
                    await send_single_invitation(employee_id, company_id, current_user.id, conn, raise_on_email_failure=False)
                    sent += 1
                except Exception as e:
                    failed += 1
                    errors.append({
                        "employee_id": str(employee_id),
                        "error": _exception_message(e)
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


@router.post("/invite-all", response_model=BulkInviteResponse)
async def invite_all_uninvited(
    current_user: CurrentUser = Depends(require_admin_or_client),
):
    """
    Send invitation emails to all uninvited employees in the company.

    Finds all employees who have no user_id and no pending/accepted invitation,
    then sends invitations in batches of 10 with rate limiting.
    """
    company_id = await get_client_company_id(current_user)

    sent = 0
    failed = 0
    errors = []

    BATCH_SIZE = 10

    async with get_connection() as conn:
        # Find all employees who are uninvited:
        # - no user_id (haven't created an account)
        # - no pending or accepted invitation
        rows = await conn.fetch(
            """
            SELECT e.id
            FROM employees e
            WHERE e.org_id = $1
              AND e.user_id IS NULL
              AND e.termination_date IS NULL
              AND NOT EXISTS (
                  SELECT 1 FROM employee_invitations ei
                  WHERE ei.employee_id = e.id
                    AND ei.status IN ('pending', 'accepted')
              )
            ORDER BY e.created_at
            """,
            company_id,
        )

        employee_ids = [row["id"] for row in rows]

        for i in range(0, len(employee_ids), BATCH_SIZE):
            batch = employee_ids[i:i + BATCH_SIZE]

            for employee_id in batch:
                try:
                    await send_single_invitation(employee_id, company_id, current_user.id, conn, raise_on_email_failure=False)
                    sent += 1
                except Exception as e:
                    failed += 1
                    errors.append({
                        "employee_id": str(employee_id),
                        "error": _exception_message(e)
                    })

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

        # Calculate statistics from each employee's latest invitation only,
        # so cancelled/expired historical rows from resends don't inflate counts.
        stats = await conn.fetchrow("""
            SELECT
                COUNT(*) FILTER (WHERE status = 'pending') as pending,
                COUNT(*) FILTER (WHERE status = 'accepted') as accepted,
                COUNT(*) FILTER (WHERE status = 'expired') as expired,
                COUNT(*) FILTER (WHERE status = 'cancelled') as cancelled
            FROM (
                SELECT DISTINCT ON (i.employee_id) i.status
                FROM employee_invitations i
                JOIN employees e ON i.employee_id = e.id
                WHERE e.org_id = $1
                ORDER BY i.employee_id, i.created_at DESC
            ) latest
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
VALID_OFFBOARDING_CASE_STATUS = {"in_progress", "completed", "cancelled"}
VALID_OFFBOARDING_TASK_STATUS = {"pending", "completed", "skipped"}

RETURN_TO_WORK_DEFAULT_TEMPLATES = [
    {
        "title": "Fitness-for-Duty Certification",
        "description": "Submit medical clearance from healthcare provider",
        "category": "return_to_work",
        "is_employee_task": True,
        "due_days": 0,
        "sort_order": 1,
    },
    {
        "title": "Modified Duty Agreement",
        "description": "Review and sign modified duty or accommodation plan",
        "category": "return_to_work",
        "is_employee_task": True,
        "due_days": 1,
        "sort_order": 2,
    },
    {
        "title": "Accommodation Review",
        "description": "Meet with HR to review workplace accommodations",
        "category": "return_to_work",
        "is_employee_task": False,
        "due_days": 3,
        "sort_order": 3,
    },
    {
        "title": "Gradual Return Schedule",
        "description": "Confirm phased return-to-work schedule",
        "category": "return_to_work",
        "is_employee_task": False,
        "due_days": 1,
        "sort_order": 4,
    },
    {
        "title": "Benefits Reinstatement Review",
        "description": "Verify benefits and leave balances are current",
        "category": "return_to_work",
        "is_employee_task": False,
        "due_days": 5,
        "sort_order": 5,
    },
    {
        "title": "Manager Check-in",
        "description": "Schedule return meeting with direct manager",
        "category": "return_to_work",
        "is_employee_task": True,
        "due_days": 3,
        "sort_order": 6,
    },
]

OFFBOARDING_DEFAULT_TASKS = [
    {
        "title": "Disable SaaS and identity access",
        "description": "Disable SSO, email, and application access for the employee.",
        "category": "access_revocation",
        "assignee_type": "it",
        "due_offset_days": 0,
    },
    {
        "title": "Collect company equipment",
        "description": "Retrieve laptop, badge, and any other assigned hardware.",
        "category": "equipment_return",
        "assignee_type": "it",
        "due_offset_days": 3,
    },
    {
        "title": "Run knowledge transfer handoff",
        "description": "Capture handoff notes, docs, and transition ownership.",
        "category": "knowledge_transfer",
        "assignee_type": "manager",
        "due_offset_days": -2,
    },
    {
        "title": "Schedule exit interview",
        "description": "Coordinate and document employee exit interview.",
        "category": "exit_interview",
        "assignee_type": "hr",
        "due_offset_days": 1,
    },
    {
        "title": "Finalize payroll and benefits termination",
        "description": "Process final payroll and confirm benefits termination timing.",
        "category": "final_payroll",
        "assignee_type": "payroll",
        "due_offset_days": 2,
    },
]


class OffboardingCaseCreateRequest(BaseModel):
    last_day: date
    reason: Optional[str] = None
    is_voluntary: bool = True
    assign_default_tasks: bool = True


class OffboardingCaseCompleteRequest(BaseModel):
    force: bool = False


class OffboardingTaskUpdateRequest(BaseModel):
    status: Optional[str] = None
    notes: Optional[str] = None


class OffboardingTaskResponse(BaseModel):
    id: UUID
    case_id: UUID
    employee_id: UUID
    title: str
    description: Optional[str]
    category: str
    assignee_type: str
    due_date: Optional[str]
    status: str
    completed_at: Optional[datetime]
    completed_by: Optional[UUID]
    notes: Optional[str]
    created_at: datetime

    class Config:
        from_attributes = True


class OffboardingCaseResponse(BaseModel):
    id: UUID
    org_id: UUID
    employee_id: UUID
    status: str
    reason: Optional[str]
    is_voluntary: bool
    last_day: str
    started_at: datetime
    completed_at: Optional[datetime]
    created_by: Optional[UUID]
    created_at: datetime
    tasks: list[OffboardingTaskResponse] = Field(default_factory=list)

    class Config:
        from_attributes = True


def _to_offboarding_task_response(row) -> OffboardingTaskResponse:
    return OffboardingTaskResponse(
        id=row["id"],
        case_id=row["case_id"],
        employee_id=row["employee_id"],
        title=row["title"],
        description=row["description"],
        category=row["category"],
        assignee_type=row["assignee_type"],
        due_date=str(row["due_date"]) if row["due_date"] else None,
        status=row["status"],
        completed_at=row["completed_at"],
        completed_by=row["completed_by"],
        notes=row["notes"],
        created_at=row["created_at"],
    )


def _to_offboarding_case_response(case_row, task_rows: list) -> OffboardingCaseResponse:
    return OffboardingCaseResponse(
        id=case_row["id"],
        org_id=case_row["org_id"],
        employee_id=case_row["employee_id"],
        status=case_row["status"],
        reason=case_row["reason"],
        is_voluntary=bool(case_row["is_voluntary"]),
        last_day=str(case_row["last_day"]),
        started_at=case_row["started_at"],
        completed_at=case_row["completed_at"],
        created_by=case_row["created_by"],
        created_at=case_row["created_at"],
        tasks=[_to_offboarding_task_response(row) for row in task_rows],
    )


async def _ensure_rtw_templates(conn, company_id: UUID) -> None:
    """Create default return-to-work templates if they do not exist for the company."""
    count = await conn.fetchval(
        "SELECT COUNT(*) FROM onboarding_tasks WHERE org_id = $1 AND category = 'return_to_work'",
        company_id,
    )
    if count and count > 0:
        return

    for template in RETURN_TO_WORK_DEFAULT_TEMPLATES:
        await conn.execute(
            """
            INSERT INTO onboarding_tasks (org_id, title, description, category, is_employee_task, due_days, sort_order)
            VALUES ($1, $2, $3, $4, $5, $6, $7)
            """,
            company_id,
            template["title"],
            template["description"],
            template["category"],
            template["is_employee_task"],
            template["due_days"],
            template["sort_order"],
        )


async def assign_rtw_tasks(
    employee_id: UUID,
    leave_request_id: UUID,
    company_id: UUID,
    conn,
) -> list:
    """Assign return-to-work onboarding tasks linked to a leave request."""
    leave = await conn.fetchrow(
        """
        SELECT id, employee_id, expected_return_date, end_date
        FROM leave_requests
        WHERE id = $1 AND org_id = $2
        """,
        leave_request_id,
        company_id,
    )
    if not leave or leave["employee_id"] != employee_id:
        raise HTTPException(status_code=404, detail="Leave request not found for employee")

    await _ensure_rtw_templates(conn, company_id)

    templates = await conn.fetch(
        """
        SELECT id, title, description, category, is_employee_task, due_days
        FROM onboarding_tasks
        WHERE org_id = $1 AND is_active = true AND category = 'return_to_work'
        ORDER BY sort_order, title
        """,
        company_id,
    )

    base_date = leave["expected_return_date"] or leave["end_date"] or date.today()
    assigned_tasks = []

    for template in templates:
        due_date = base_date + timedelta(days=template["due_days"] or 0)
        row = await conn.fetchrow(
            """
            INSERT INTO employee_onboarding_tasks
                (employee_id, task_id, leave_request_id, title, description, category, is_employee_task, due_date)
            SELECT $1, $2, $3, $4, $5, $6, $7, $8
            WHERE NOT EXISTS (
                SELECT 1
                FROM employee_onboarding_tasks
                WHERE employee_id = $1
                  AND leave_request_id = $3
                  AND title = $4
            )
            RETURNING *
            """,
            employee_id,
            template["id"],
            leave_request_id,
            template["title"],
            template["description"],
            template["category"],
            template["is_employee_task"],
            due_date,
        )
        if row:
            assigned_tasks.append(row)

    return assigned_tasks


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


# ================================
# Employee Offboarding
# ================================

@router.post("/{employee_id}/offboard", response_model=OffboardingCaseResponse)
async def create_offboarding_case(
    employee_id: UUID,
    request: OffboardingCaseCreateRequest,
    current_user: CurrentUser = Depends(require_admin_or_client),
):
    """Create or return the active offboarding case for an employee."""
    company_id = await get_client_company_id(current_user)

    async with get_connection() as conn:
        async with conn.transaction():
            employee = await conn.fetchrow(
                """
                SELECT id, org_id, start_date
                FROM employees
                WHERE id = $1 AND org_id = $2
                FOR UPDATE
                """,
                employee_id,
                company_id,
            )
            if not employee:
                raise HTTPException(status_code=404, detail="Employee not found")

            if employee["start_date"] and request.last_day < employee["start_date"]:
                raise HTTPException(status_code=400, detail="last_day cannot be before employee start_date")

            existing_case = await conn.fetchrow(
                """
                SELECT *
                FROM offboarding_cases
                WHERE employee_id = $1 AND status = 'in_progress'
                ORDER BY created_at DESC
                LIMIT 1
                FOR UPDATE
                """,
                employee_id,
            )

            if existing_case:
                case_row = existing_case
            else:
                case_row = await conn.fetchrow(
                    """
                    INSERT INTO offboarding_cases
                    (org_id, employee_id, status, reason, is_voluntary, last_day, created_by)
                    VALUES ($1, $2, 'in_progress', $3, $4, $5, $6)
                    RETURNING *
                    """,
                    company_id,
                    employee_id,
                    request.reason,
                    request.is_voluntary,
                    request.last_day,
                    current_user.id,
                )

                await conn.execute(
                    """
                    UPDATE employees
                    SET termination_date = $2, updated_at = NOW()
                    WHERE id = $1
                    """,
                    employee_id,
                    request.last_day,
                )

                # Update employment status to on_notice if status columns exist
                if await _employee_status_fields_available(conn):
                    await conn.execute(
                        """
                        UPDATE employees
                        SET employment_status = 'on_notice', status_changed_at = NOW(),
                            status_reason = 'Offboarding initiated'
                        WHERE id = $1
                        """,
                        employee_id,
                    )

                if request.assign_default_tasks:
                    for template in OFFBOARDING_DEFAULT_TASKS:
                        due_date = request.last_day + timedelta(days=template["due_offset_days"])
                        await conn.execute(
                            """
                            INSERT INTO offboarding_tasks
                            (case_id, employee_id, title, description, category, assignee_type, due_date)
                            VALUES ($1, $2, $3, $4, $5, $6, $7)
                            """,
                            case_row["id"],
                            employee_id,
                            template["title"],
                            template["description"],
                            template["category"],
                            template["assignee_type"],
                            due_date,
                        )

            task_rows = await conn.fetch(
                """
                SELECT *
                FROM offboarding_tasks
                WHERE case_id = $1
                ORDER BY due_date NULLS LAST, created_at
                """,
                case_row["id"],
            )

        return _to_offboarding_case_response(case_row, list(task_rows))


@router.get("/{employee_id}/offboard", response_model=OffboardingCaseResponse)
async def get_offboarding_case(
    employee_id: UUID,
    status: Optional[str] = Query(None, description="Filter case status"),
    current_user: CurrentUser = Depends(require_admin_or_client),
):
    """Get the latest offboarding case for an employee."""
    company_id = await get_client_company_id(current_user)
    if status and status not in VALID_OFFBOARDING_CASE_STATUS:
        raise HTTPException(
            status_code=400,
            detail=f"Invalid status. Must be one of: {sorted(VALID_OFFBOARDING_CASE_STATUS)}",
        )

    async with get_connection() as conn:
        employee = await conn.fetchrow(
            "SELECT id FROM employees WHERE id = $1 AND org_id = $2",
            employee_id,
            company_id,
        )
        if not employee:
            raise HTTPException(status_code=404, detail="Employee not found")

        if status:
            case_row = await conn.fetchrow(
                """
                SELECT *
                FROM offboarding_cases
                WHERE employee_id = $1 AND org_id = $2 AND status = $3
                ORDER BY created_at DESC
                LIMIT 1
                """,
                employee_id,
                company_id,
                status,
            )
        else:
            case_row = await conn.fetchrow(
                """
                SELECT *
                FROM offboarding_cases
                WHERE employee_id = $1 AND org_id = $2
                ORDER BY created_at DESC
                LIMIT 1
                """,
                employee_id,
                company_id,
            )

        if not case_row:
            raise HTTPException(status_code=404, detail="Offboarding case not found")

        task_rows = await conn.fetch(
            """
            SELECT *
            FROM offboarding_tasks
            WHERE case_id = $1
            ORDER BY due_date NULLS LAST, created_at
            """,
            case_row["id"],
        )

        return _to_offboarding_case_response(case_row, list(task_rows))


@router.patch("/{employee_id}/offboard/tasks/{task_id}", response_model=OffboardingTaskResponse)
async def update_offboarding_task(
    employee_id: UUID,
    task_id: UUID,
    request: OffboardingTaskUpdateRequest,
    current_user: CurrentUser = Depends(require_admin_or_client),
):
    """Update offboarding task status/notes."""
    company_id = await get_client_company_id(current_user)

    async with get_connection() as conn:
        task = await conn.fetchrow(
            """
            SELECT t.*
            FROM offboarding_tasks t
            JOIN offboarding_cases c ON c.id = t.case_id
            WHERE t.id = $1 AND t.employee_id = $2 AND c.org_id = $3
            """,
            task_id,
            employee_id,
            company_id,
        )
        if not task:
            raise HTTPException(status_code=404, detail="Offboarding task not found")

        updates = []
        values = []
        idx = 1

        if request.status is not None:
            if request.status not in VALID_OFFBOARDING_TASK_STATUS:
                raise HTTPException(
                    status_code=400,
                    detail=f"Invalid status. Must be one of: {sorted(VALID_OFFBOARDING_TASK_STATUS)}",
                )
            updates.append(f"status = ${idx}")
            values.append(request.status)
            idx += 1

            if request.status == "completed":
                updates.append("completed_at = NOW()")
                updates.append(f"completed_by = ${idx}")
                values.append(current_user.id)
                idx += 1
            elif request.status == "pending":
                updates.append("completed_at = NULL")
                updates.append("completed_by = NULL")

        if request.notes is not None:
            updates.append(f"notes = ${idx}")
            values.append(request.notes)
            idx += 1

        if not updates:
            raise HTTPException(status_code=400, detail="No fields to update")

        updates.append("updated_at = NOW()")
        values.append(task_id)

        row = await conn.fetchrow(
            f"""
            UPDATE offboarding_tasks
            SET {', '.join(updates)}
            WHERE id = ${idx}
            RETURNING *
            """,
            *values,
        )
        return _to_offboarding_task_response(row)


@router.post("/{employee_id}/offboard/{case_id}/complete", response_model=OffboardingCaseResponse)
async def complete_offboarding_case(
    employee_id: UUID,
    case_id: UUID,
    request: OffboardingCaseCompleteRequest,
    current_user: CurrentUser = Depends(require_admin_or_client),
):
    """Complete an offboarding case and finalize access revocation status."""
    company_id = await get_client_company_id(current_user)

    async with get_connection() as conn:
        async with conn.transaction():
            case_row = await conn.fetchrow(
                """
                SELECT *
                FROM offboarding_cases
                WHERE id = $1 AND employee_id = $2 AND org_id = $3
                FOR UPDATE
                """,
                case_id,
                employee_id,
                company_id,
            )
            if not case_row:
                raise HTTPException(status_code=404, detail="Offboarding case not found")

            if case_row["status"] == "completed":
                task_rows = await conn.fetch(
                    "SELECT * FROM offboarding_tasks WHERE case_id = $1 ORDER BY due_date NULLS LAST, created_at",
                    case_id,
                )
                return _to_offboarding_case_response(case_row, list(task_rows))

            pending_count = await conn.fetchval(
                "SELECT COUNT(*) FROM offboarding_tasks WHERE case_id = $1 AND status = 'pending'",
                case_id,
            )
            if pending_count > 0 and not request.force:
                raise HTTPException(
                    status_code=400,
                    detail=f"Cannot complete case with {pending_count} pending tasks unless force=true",
                )

            if pending_count > 0 and request.force:
                await conn.execute(
                    """
                    UPDATE offboarding_tasks
                    SET status = 'skipped',
                        notes = COALESCE(notes || E'\\n', '') || 'Auto-skipped during forced case completion.',
                        updated_at = NOW()
                    WHERE case_id = $1 AND status = 'pending'
                    """,
                    case_id,
                )

            case_row = await conn.fetchrow(
                """
                UPDATE offboarding_cases
                SET status = 'completed', completed_at = NOW(), updated_at = NOW()
                WHERE id = $1
                RETURNING *
                """,
                case_id,
            )

            # Update employment status to offboarded if status columns exist
            if await _employee_status_fields_available(conn):
                await conn.execute(
                    """
                    UPDATE employees
                    SET employment_status = 'offboarded', status_changed_at = NOW(),
                        status_reason = 'Offboarding completed'
                    WHERE id = $1
                    """,
                    employee_id,
                )

            if case_row["last_day"] <= date.today():
                try:
                    identities = await conn.fetch(
                        """
                        SELECT id, provider
                        FROM external_identities
                        WHERE employee_id = $1 AND company_id = $2 AND status <> 'deprovisioned'
                        """,
                        employee_id,
                        company_id,
                    )
                except Exception:
                    identities = []

                for identity in identities:
                    try:
                        await conn.execute(
                            """
                            UPDATE external_identities
                            SET status = 'deprovisioned', updated_at = NOW()
                            WHERE id = $1
                            """,
                            identity["id"],
                        )
                        await conn.execute(
                            """
                            INSERT INTO provisioning_audit_logs (
                                company_id, employee_id, actor_user_id, provider, action, status, detail, payload
                            )
                            VALUES ($1, $2, $3, $4, $5, 'info', $6, $7::jsonb)
                            """,
                            company_id,
                            employee_id,
                            current_user.id,
                            identity["provider"],
                            "offboarding_case_completed",
                            "Marked external identity as deprovisioned during offboarding completion.",
                            json.dumps({"offboarding_case_id": str(case_id)}),
                        )
                    except Exception:
                        continue

            task_rows = await conn.fetch(
                "SELECT * FROM offboarding_tasks WHERE case_id = $1 ORDER BY due_date NULLS LAST, created_at",
                case_id,
            )

        return _to_offboarding_case_response(case_row, list(task_rows))


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
