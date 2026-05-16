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


class BulkEmployeeCSVUpload(BaseModel):
    """Model for CSV upload response."""
    total_rows: int
    created: int
    failed: int
    errors: list[dict]  # [{row: int, email: str, error: str}]
    employee_ids: list[UUID]
    credentials_created: int = 0


class BulkCredentialsUploadResponse(BaseModel):
    """Model for credential-only CSV upload response."""
    total_rows: int
    updated: int
    failed: int
    not_found: int
    errors: list[dict]


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
        'email', 'personal_email', 'first_name', 'last_name', 'work_state',
        'employment_type', 'start_date', 'manager_email', 'job_title', 'department',
        'phone', 'uid', 'pay_classification', 'pay_rate', 'work_city',
        'license_type', 'license_number', 'license_state', 'license_expiration',
        'npi_number', 'dea_number', 'dea_expiration',
        'board_certification', 'board_certification_expiration', 'clinical_specialty',
        'malpractice_carrier', 'malpractice_policy_number', 'malpractice_expiration',
        'health_clearances',
    ])
    writer.writeheader()

    # Add example row (medical employee)
    writer.writerow({
        'email': 'jane.doe@hospital.test',
        'personal_email': 'jane.doe@gmail.com',
        'first_name': 'Jane',
        'last_name': 'Doe',
        'work_state': 'CA',
        'employment_type': 'full_time',
        'start_date': '2026-02-01',
        'manager_email': 'manager@example.com',
        'job_title': 'Registered Nurse',
        'department': 'Emergency',
        'phone': '555-1234',
        'uid': 'EMP-001',
        'pay_classification': 'hourly',
        'pay_rate': '45.00',
        'work_city': 'San Francisco',
        'license_type': 'RN',
        'license_number': 'RN123456',
        'license_state': 'CA',
        'license_expiration': '2027-06-30',
        'npi_number': '1234567890',
        'dea_number': '',
        'dea_expiration': '',
        'board_certification': '',
        'board_certification_expiration': '',
        'clinical_specialty': 'Emergency Medicine',
        'malpractice_carrier': '',
        'malpractice_policy_number': '',
        'malpractice_expiration': '',
        'health_clearances': '{"tb_test": "2026-01-10", "hep_b": "cleared"}',
    })

    output.seek(0)
    return StreamingResponse(
        io.BytesIO(output.getvalue().encode()),
        media_type="text/csv",
        headers={"Content-Disposition": "attachment; filename=employee_bulk_upload_template.csv"}
    )


@router.post("/bulk-upload", response_model=BulkEmployeeCSVUpload)
async def bulk_upload_employees_csv(
    background_tasks: BackgroundTasks,
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
    - personal_email (personal/non-work email)
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
    credentials_created = 0
    errors = []
    employee_ids = []

    logger.info("[BulkUpload] Starting bulk CSV upload for company %s by user %s (send_invitations=%s)",
                company_id, current_user.id, send_invitations)

    async with get_connection() as conn:
        compensation_fields_available = await _employee_compensation_fields_available(conn)
        external_uid_available = await _column_exists(conn, "employees", "external_uid")

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

        logger.info("[BulkUpload] Integration flags: google_auto_provision=%s, slack_auto_provision=%s",
                    google_workspace_auto_provision, slack_auto_provision)

        for row_num, row in enumerate(csv_reader, start=2):  # Start at 2 to account for header
            try:
                # Validate email format
                email = row.get('email', '').strip()
                personal_email = row.get('personal_email', '').strip() or None
                if not email:
                    errors.append({
                        "row": row_num,
                        "email": email,
                        "error": "Email is required"
                    })
                    failed += 1
                    continue

                # Basic email validation
                if not re.match(r'^[\w\.\-\+]+@[\w\.-]+\.\w+$', email):
                    errors.append({
                        "row": row_num,
                        "email": email,
                        "error": "Invalid email format"
                    })
                    failed += 1
                    continue

                if personal_email and not re.match(r'^[\w\.\-\+]+@[\w\.-]+\.\w+$', personal_email):
                    errors.append({
                        "row": row_num,
                        "email": email,
                        "error": "Invalid personal_email format"
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
                department_val = row.get('department', '').strip() or None
                phone = row.get('phone', '').strip() or None

                # Parse compensation fields
                pay_classification = row.get('pay_classification', '').strip().lower() or None
                if pay_classification and pay_classification not in ('hourly', 'exempt'):
                    errors.append({
                        "row": row_num,
                        "email": email,
                        "error": f"Invalid pay_classification '{pay_classification}'. Must be 'hourly' or 'exempt'"
                    })
                    failed += 1
                    continue

                pay_rate = None
                pay_rate_str = row.get('pay_rate', '').strip()
                if pay_rate_str:
                    try:
                        pay_rate = Decimal(pay_rate_str)
                        if pay_rate < 0:
                            raise ValueError("negative")
                    except (ValueError, Exception):
                        errors.append({
                            "row": row_num,
                            "email": email,
                            "error": f"Invalid pay_rate '{pay_rate_str}'. Must be a non-negative number"
                        })
                        failed += 1
                        continue

                if pay_rate is not None and pay_classification is None:
                    errors.append({
                        "row": row_num,
                        "email": email,
                        "error": "pay_classification is required when pay_rate is provided"
                    })
                    failed += 1
                    continue

                work_city = row.get('work_city', '').strip() or None

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

                # Optional HR-internal badge/employee number for IR-only
                # tenants. Skipped silently if column doesn't exist yet
                # (pre-migration). Empty strings → None.
                external_uid = (row.get('uid') or row.get('external_uid') or '').strip() or None

                # Create employee record
                bulk_cols = [
                    "org_id", "email", "personal_email", "first_name", "last_name",
                    "work_state", "employment_type", "start_date", "manager_id", "phone",
                ]
                bulk_vals: list = [
                    company_id, email, personal_email, first_name, last_name,
                    work_state, employment_type, start_date, manager_id, phone,
                ]
                if compensation_fields_available:
                    bulk_cols.extend(["pay_classification", "pay_rate", "work_city"])
                    bulk_vals.extend([pay_classification, pay_rate, work_city])
                org_fields_avail = await _employee_org_fields_available(conn)
                if org_fields_avail:
                    bulk_cols.extend(["job_title", "department"])
                    bulk_vals.extend([job_title, department_val])
                if external_uid is not None and external_uid_available:
                    bulk_cols.append("external_uid")
                    bulk_vals.append(external_uid)
                bulk_placeholders = ", ".join(f"${i}" for i in range(1, len(bulk_vals) + 1))
                bulk_col_list = ", ".join(bulk_cols)
                employee = await conn.fetchrow(
                    f"INSERT INTO employees ({bulk_col_list}) VALUES ({bulk_placeholders}) RETURNING id",
                    *bulk_vals
                    )

                employee_ids.append(employee['id'])
                created += 1
                logger.info("[BulkUpload] Row %d: created employee %s (%s)", row_num, employee['id'], email)

                # Process credential fields if any are present in the CSV row
                try:
                    cred_license_type = row.get('license_type', '').strip() or None
                    cred_license_number = row.get('license_number', '').strip() or None
                    cred_license_state = row.get('license_state', '').strip() or None
                    cred_license_expiration = _parse_csv_date(row.get('license_expiration', ''))
                    cred_npi_number = row.get('npi_number', '').strip() or None
                    cred_dea_number = row.get('dea_number', '').strip() or None
                    cred_dea_expiration = _parse_csv_date(row.get('dea_expiration', ''))
                    cred_board_certification = row.get('board_certification', '').strip() or None
                    cred_board_certification_expiration = _parse_csv_date(row.get('board_certification_expiration', ''))
                    cred_clinical_specialty = row.get('clinical_specialty', '').strip() or None
                    cred_malpractice_carrier = row.get('malpractice_carrier', '').strip() or None
                    cred_malpractice_policy_number = row.get('malpractice_policy_number', '').strip() or None
                    cred_malpractice_expiration = _parse_csv_date(row.get('malpractice_expiration', ''))

                    health_clearances_str = row.get('health_clearances', '').strip()
                    cred_health_clearances: dict = {}
                    if health_clearances_str:
                        try:
                            parsed_hc = json.loads(health_clearances_str)
                            cred_health_clearances = parsed_hc if isinstance(parsed_hc, dict) else {}
                        except json.JSONDecodeError:
                            logger.warning("[BulkUpload] Row %d: invalid health_clearances JSON for %s, storing {}", row_num, email)

                    scalar_cred_fields = [
                        cred_license_type, cred_license_number, cred_license_state, cred_license_expiration,
                        cred_npi_number, cred_dea_number, cred_dea_expiration,
                        cred_board_certification, cred_board_certification_expiration, cred_clinical_specialty,
                        cred_malpractice_carrier, cred_malpractice_policy_number, cred_malpractice_expiration,
                    ]
                    if any(v is not None for v in scalar_cred_fields) or cred_health_clearances:
                        enc_creds = encrypt_credential_fields({
                            "license_number": cred_license_number,
                            "npi_number": cred_npi_number,
                            "dea_number": cred_dea_number,
                            "malpractice_policy_number": cred_malpractice_policy_number,
                        })
                        await conn.execute("""
                            INSERT INTO employee_credentials (
                                employee_id, org_id,
                                license_type, license_number, license_state, license_expiration,
                                npi_number, dea_number, dea_expiration,
                                board_certification, board_certification_expiration,
                                clinical_specialty,
                                oig_last_checked, oig_status,
                                malpractice_carrier, malpractice_policy_number, malpractice_expiration,
                                health_clearances,
                                updated_at
                            ) VALUES (
                                $1, $2,
                                $3, $4, $5, $6,
                                $7, $8, $9,
                                $10, $11,
                                $12,
                                $13, $14,
                                $15, $16, $17,
                                $18::jsonb,
                                NOW()
                            )
                            ON CONFLICT (employee_id) DO UPDATE SET
                                license_type = COALESCE(EXCLUDED.license_type, employee_credentials.license_type),
                                license_number = COALESCE(EXCLUDED.license_number, employee_credentials.license_number),
                                license_state = COALESCE(EXCLUDED.license_state, employee_credentials.license_state),
                                license_expiration = COALESCE(EXCLUDED.license_expiration, employee_credentials.license_expiration),
                                npi_number = COALESCE(EXCLUDED.npi_number, employee_credentials.npi_number),
                                dea_number = COALESCE(EXCLUDED.dea_number, employee_credentials.dea_number),
                                dea_expiration = COALESCE(EXCLUDED.dea_expiration, employee_credentials.dea_expiration),
                                board_certification = COALESCE(EXCLUDED.board_certification, employee_credentials.board_certification),
                                board_certification_expiration = COALESCE(EXCLUDED.board_certification_expiration, employee_credentials.board_certification_expiration),
                                clinical_specialty = COALESCE(EXCLUDED.clinical_specialty, employee_credentials.clinical_specialty),
                                oig_last_checked = COALESCE(EXCLUDED.oig_last_checked, employee_credentials.oig_last_checked),
                                oig_status = COALESCE(EXCLUDED.oig_status, employee_credentials.oig_status),
                                malpractice_carrier = COALESCE(EXCLUDED.malpractice_carrier, employee_credentials.malpractice_carrier),
                                malpractice_policy_number = COALESCE(EXCLUDED.malpractice_policy_number, employee_credentials.malpractice_policy_number),
                                malpractice_expiration = COALESCE(EXCLUDED.malpractice_expiration, employee_credentials.malpractice_expiration),
                                health_clearances = COALESCE(EXCLUDED.health_clearances, employee_credentials.health_clearances),
                                updated_at = NOW()
                        """,
                            employee['id'], company_id,
                            cred_license_type, enc_creds["license_number"], cred_license_state, cred_license_expiration,
                            enc_creds["npi_number"], enc_creds["dea_number"], cred_dea_expiration,
                            cred_board_certification, cred_board_certification_expiration, cred_clinical_specialty,
                            None, None,
                            cred_malpractice_carrier, enc_creds["malpractice_policy_number"], cred_malpractice_expiration,
                            json.dumps(cred_health_clearances) if cred_health_clearances else None,
                        )
                        credentials_created += 1
                        logger.info("[BulkUpload] Row %d: created credentials for employee %s", row_num, employee['id'])
                except Exception as e:
                    logger.warning("[BulkUpload] Row %d: employee %s created but credential save failed: %s", row_num, email, e)
                    errors.append({
                        "row": row_num,
                        "email": email,
                        "error": f"Employee created but credentials failed: {_exception_message(e)}"
                    })

                await _sync_employee_location_for_compliance(
                    conn,
                    company_id=company_id,
                    employee_id=employee["id"],
                    work_state=work_state,
                    work_city=work_city,
                    background_tasks=background_tasks,
                )

                # Schedule Google Workspace / Slack provisioning
                run_google = google_workspace_auto_provision
                run_slack = slack_auto_provision
                if run_google or run_slack:
                    logger.info("[BulkUpload] Row %d: scheduling provisioning for %s (google=%s, slack=%s)",
                                row_num, email, run_google, run_slack)
                    background_tasks.add_task(
                        _run_provisioning_and_notify,
                        company_id=company_id,
                        employee_id=employee['id'],
                        triggered_by=current_user.id,
                        personal_email=personal_email,
                        employee_name=f"{first_name} {last_name}".strip(),
                        work_email=email,
                        run_google=run_google,
                        run_slack=run_slack,
                    )
                else:
                    logger.info("[BulkUpload] Row %d: no integrations enabled, skipping provisioning for %s",
                                row_num, email)

                # Send invitation if requested
                if send_invitations:
                    try:
                        logger.info("[BulkUpload] Row %d: sending invitation to %s", row_num, email)
                        await send_single_invitation(
                            employee['id'],
                            company_id,
                            current_user.id,
                            conn,
                            raise_on_email_failure=False,
                        )
                        await asyncio.sleep(0.15)  # rate-limit guard for MailerSend
                    except Exception as e:
                        logger.warning("[BulkUpload] Row %d: invitation failed for %s: %s", row_num, email, e)
                        # Log error but don't fail the employee creation
                        errors.append({
                            "row": row_num,
                            "email": email,
                            "error": f"Employee created but invitation failed: {_exception_message(e)}"
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

    logger.info("[BulkUpload] Complete: %d created, %d failed, %d errors, %d background tasks queued",
                created, failed, len(errors), len(background_tasks.tasks) if hasattr(background_tasks, 'tasks') else -1)

    return BulkEmployeeCSVUpload(
        total_rows=created + failed,
        created=created,
        failed=failed,
        errors=errors,
        employee_ids=employee_ids,
        credentials_created=credentials_created,
    )


@router.get("/bulk-upload/credentials-template")
async def download_bulk_credentials_template(
    current_user: CurrentUser = Depends(require_admin_or_client),
):
    """Download CSV template for credential-only bulk upload (for existing employees)."""
    output = io.StringIO()
    writer = csv.DictWriter(output, fieldnames=[
        'email',
        'license_type', 'license_number', 'license_state', 'license_expiration',
        'npi_number', 'dea_number', 'dea_expiration',
        'board_certification', 'board_certification_expiration', 'clinical_specialty',
        'malpractice_carrier', 'malpractice_policy_number', 'malpractice_expiration',
        'health_clearances',
    ])
    writer.writeheader()
    writer.writerow({
        'email': 'jane.doe@hospital.test',
        'license_type': 'RN',
        'license_number': 'RN123456',
        'license_state': 'CA',
        'license_expiration': '2027-06-30',
        'npi_number': '1234567890',
        'dea_number': '',
        'dea_expiration': '',
        'board_certification': '',
        'board_certification_expiration': '',
        'clinical_specialty': 'Emergency Medicine',
        'malpractice_carrier': '',
        'malpractice_policy_number': '',
        'malpractice_expiration': '',
        'health_clearances': '{"tb_test": "2026-01-10", "hep_b": "cleared"}',
    })
    output.seek(0)
    return StreamingResponse(
        io.BytesIO(output.getvalue().encode()),
        media_type="text/csv",
        headers={"Content-Disposition": "attachment; filename=employee_credentials_template.csv"}
    )


@router.post("/bulk-upload/credentials", response_model=BulkCredentialsUploadResponse)
async def bulk_upload_credentials_csv(
    file: UploadFile = File(..., description="CSV file with email + credential columns"),
    current_user: CurrentUser = Depends(require_admin_or_client),
):
    """
    Upload a CSV to create or update credentials for existing employees.

    Requires an 'email' column to identify each employee, plus any credential columns.
    Use this to load credentialing data from a credentialing software export without
    re-creating employee records.
    """
    company_id = await get_client_company_id(current_user)

    if not file.filename.endswith('.csv'):
        raise HTTPException(status_code=400, detail="File must be a CSV")

    contents = await file.read()
    if len(contents) > 10 * 1024 * 1024:
        raise HTTPException(status_code=413, detail="File too large (max 10MB)")

    try:
        csv_content = contents.decode('utf-8')
        csv_reader = csv.DictReader(io.StringIO(csv_content))
    except Exception as e:
        raise HTTPException(status_code=400, detail=f"Invalid CSV format: {str(e)}")

    if not csv_reader.fieldnames or 'email' not in csv_reader.fieldnames:
        raise HTTPException(status_code=400, detail="CSV must include an 'email' column")

    updated = 0
    failed = 0
    not_found = 0
    errors = []

    async with get_connection() as conn:
        for row_num, row in enumerate(csv_reader, start=2):
            email = row.get('email', '').strip()
            if not email:
                errors.append({"row": row_num, "email": "", "error": "Email is required"})
                failed += 1
                continue

            emp_id = await conn.fetchval(
                "SELECT id FROM employees WHERE org_id = $1 AND email = $2",
                company_id, email,
            )
            if not emp_id:
                errors.append({"row": row_num, "email": email, "error": "Employee not found"})
                not_found += 1
                continue

            try:
                health_clearances_str = row.get('health_clearances', '').strip()
                health_clearances: dict = {}
                if health_clearances_str:
                    try:
                        parsed_hc = json.loads(health_clearances_str)
                        health_clearances = parsed_hc if isinstance(parsed_hc, dict) else {}
                    except json.JSONDecodeError:
                        logger.warning("[BulkCredentials] Row %d: invalid health_clearances JSON for %s, storing {}", row_num, email)

                enc_creds = encrypt_credential_fields({
                    "license_number": row.get('license_number', '').strip() or None,
                    "npi_number": row.get('npi_number', '').strip() or None,
                    "dea_number": row.get('dea_number', '').strip() or None,
                    "malpractice_policy_number": row.get('malpractice_policy_number', '').strip() or None,
                })
                await conn.execute("""
                    INSERT INTO employee_credentials (
                        employee_id, org_id,
                        license_type, license_number, license_state, license_expiration,
                        npi_number, dea_number, dea_expiration,
                        board_certification, board_certification_expiration,
                        clinical_specialty,
                        oig_last_checked, oig_status,
                        malpractice_carrier, malpractice_policy_number, malpractice_expiration,
                        health_clearances,
                        updated_at
                    ) VALUES (
                        $1, $2,
                        $3, $4, $5, $6,
                        $7, $8, $9,
                        $10, $11,
                        $12,
                        $13, $14,
                        $15, $16, $17,
                        $18::jsonb,
                        NOW()
                    )
                    ON CONFLICT (employee_id) DO UPDATE SET
                        license_type = COALESCE(EXCLUDED.license_type, employee_credentials.license_type),
                        license_number = COALESCE(EXCLUDED.license_number, employee_credentials.license_number),
                        license_state = COALESCE(EXCLUDED.license_state, employee_credentials.license_state),
                        license_expiration = COALESCE(EXCLUDED.license_expiration, employee_credentials.license_expiration),
                        npi_number = COALESCE(EXCLUDED.npi_number, employee_credentials.npi_number),
                        dea_number = COALESCE(EXCLUDED.dea_number, employee_credentials.dea_number),
                        dea_expiration = COALESCE(EXCLUDED.dea_expiration, employee_credentials.dea_expiration),
                        board_certification = COALESCE(EXCLUDED.board_certification, employee_credentials.board_certification),
                        board_certification_expiration = COALESCE(EXCLUDED.board_certification_expiration, employee_credentials.board_certification_expiration),
                        clinical_specialty = COALESCE(EXCLUDED.clinical_specialty, employee_credentials.clinical_specialty),
                        oig_last_checked = COALESCE(EXCLUDED.oig_last_checked, employee_credentials.oig_last_checked),
                        oig_status = COALESCE(EXCLUDED.oig_status, employee_credentials.oig_status),
                        malpractice_carrier = COALESCE(EXCLUDED.malpractice_carrier, employee_credentials.malpractice_carrier),
                        malpractice_policy_number = COALESCE(EXCLUDED.malpractice_policy_number, employee_credentials.malpractice_policy_number),
                        malpractice_expiration = COALESCE(EXCLUDED.malpractice_expiration, employee_credentials.malpractice_expiration),
                        health_clearances = COALESCE(EXCLUDED.health_clearances, employee_credentials.health_clearances),
                        updated_at = NOW()
                """,
                    emp_id, company_id,
                    row.get('license_type', '').strip() or None,
                    enc_creds["license_number"],
                    row.get('license_state', '').strip() or None,
                    _parse_csv_date(row.get('license_expiration', '')),
                    enc_creds["npi_number"],
                    enc_creds["dea_number"],
                    _parse_csv_date(row.get('dea_expiration', '')),
                    row.get('board_certification', '').strip() or None,
                    _parse_csv_date(row.get('board_certification_expiration', '')),
                    row.get('clinical_specialty', '').strip() or None,
                    None, None,
                    row.get('malpractice_carrier', '').strip() or None,
                    enc_creds["malpractice_policy_number"],
                    _parse_csv_date(row.get('malpractice_expiration', '')),
                    json.dumps(health_clearances) if health_clearances else None,
                )
                updated += 1
            except Exception as e:
                errors.append({"row": row_num, "email": email, "error": str(e)})
                failed += 1

    if updated == 0 and failed == 0 and not_found == 0:
        raise HTTPException(status_code=400, detail="No data rows found in CSV")

    logger.info("[BulkCredentials] Complete: %d updated, %d not_found, %d failed", updated, not_found, failed)

    return BulkCredentialsUploadResponse(
        total_rows=updated + failed + not_found,
        updated=updated,
        failed=failed,
        not_found=not_found,
        errors=errors,
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


# ---------------------------------------------------------------------------
# Healthcare Employee Credentials
# ---------------------------------------------------------------------------

class EmployeeCredentialsRequest(BaseModel):
    license_type: Optional[str] = None
    license_number: Optional[str] = None
    license_state: Optional[str] = None
    license_expiration: Optional[str] = None  # YYYY-MM-DD
    npi_number: Optional[str] = None
    dea_number: Optional[str] = None
    dea_expiration: Optional[str] = None
    board_certification: Optional[str] = None
    board_certification_expiration: Optional[str] = None
    clinical_specialty: Optional[str] = None
    oig_last_checked: Optional[str] = None
    oig_status: Optional[str] = None
    malpractice_carrier: Optional[str] = None
    malpractice_policy_number: Optional[str] = None
    malpractice_expiration: Optional[str] = None
    health_clearances: Optional[dict] = None


class EmployeeCredentialsResponse(BaseModel):
    id: Optional[UUID] = None
    employee_id: UUID
    license_type: Optional[str] = None
    license_number: Optional[str] = None
    license_state: Optional[str] = None
    license_expiration: Optional[str] = None
    npi_number: Optional[str] = None
    dea_number: Optional[str] = None
    dea_expiration: Optional[str] = None
    board_certification: Optional[str] = None
    board_certification_expiration: Optional[str] = None
    clinical_specialty: Optional[str] = None
    oig_last_checked: Optional[str] = None
    oig_status: Optional[str] = None
    malpractice_carrier: Optional[str] = None
    malpractice_policy_number: Optional[str] = None
    malpractice_expiration: Optional[str] = None
    health_clearances: Optional[dict] = None


@router.get("/{employee_id}/credentials", response_model=EmployeeCredentialsResponse)
async def get_employee_credentials(
    employee_id: UUID,
    current_user: CurrentUser = Depends(require_admin_or_client),
):
    """Get healthcare credentials for an employee."""
    company_id = await get_client_company_id(current_user)

    async with get_connection() as conn:
        # Verify employee belongs to company
        emp = await conn.fetchval(
            "SELECT id FROM employees WHERE id = $1 AND org_id = $2",
            employee_id, company_id,
        )
        if not emp:
            raise HTTPException(status_code=404, detail="Employee not found")

        row = await conn.fetchrow(
            "SELECT * FROM employee_credentials WHERE employee_id = $1",
            employee_id,
        )
        if not row:
            return EmployeeCredentialsResponse(employee_id=employee_id)

        decrypted = decrypt_credential_fields(dict(row))

        def _date_str(val):
            return val.isoformat() if val else None

        return EmployeeCredentialsResponse(
            id=row["id"],
            employee_id=row["employee_id"],
            license_type=row["license_type"],
            license_number=decrypted["license_number"],
            license_state=row["license_state"],
            license_expiration=_date_str(row["license_expiration"]),
            npi_number=decrypted["npi_number"],
            dea_number=decrypted["dea_number"],
            dea_expiration=_date_str(row["dea_expiration"]),
            board_certification=row["board_certification"],
            board_certification_expiration=_date_str(row["board_certification_expiration"]),
            clinical_specialty=row["clinical_specialty"],
            oig_last_checked=_date_str(row["oig_last_checked"]),
            oig_status=row["oig_status"],
            malpractice_carrier=row["malpractice_carrier"],
            malpractice_policy_number=decrypted["malpractice_policy_number"],
            malpractice_expiration=_date_str(row["malpractice_expiration"]),
            health_clearances=row["health_clearances"] if isinstance(row["health_clearances"], dict) else None,
        )


@router.put("/{employee_id}/credentials", response_model=EmployeeCredentialsResponse)
async def upsert_employee_credentials(
    employee_id: UUID,
    body: EmployeeCredentialsRequest,
    current_user: CurrentUser = Depends(require_admin_or_client),
):
    """Create or update healthcare credentials for an employee."""
    company_id = await get_client_company_id(current_user)

    async with get_connection() as conn:
        emp = await conn.fetchval(
            "SELECT id FROM employees WHERE id = $1 AND org_id = $2",
            employee_id, company_id,
        )
        if not emp:
            raise HTTPException(status_code=404, detail="Employee not found")

        def _parse_date(val):
            if not val:
                return None
            return date.fromisoformat(val)

        encrypted = encrypt_credential_fields({
            "license_number": body.license_number,
            "npi_number": body.npi_number,
            "dea_number": body.dea_number,
            "malpractice_policy_number": body.malpractice_policy_number,
        })

        await conn.execute("""
            INSERT INTO employee_credentials (
                employee_id, org_id,
                license_type, license_number, license_state, license_expiration,
                npi_number, dea_number, dea_expiration,
                board_certification, board_certification_expiration,
                clinical_specialty,
                oig_last_checked, oig_status,
                malpractice_carrier, malpractice_policy_number, malpractice_expiration,
                health_clearances,
                updated_at
            ) VALUES (
                $1, $2,
                $3, $4, $5, $6,
                $7, $8, $9,
                $10, $11,
                $12,
                $13, $14,
                $15, $16, $17,
                $18::jsonb,
                NOW()
            )
            ON CONFLICT (employee_id) DO UPDATE SET
                license_type = EXCLUDED.license_type,
                license_number = EXCLUDED.license_number,
                license_state = EXCLUDED.license_state,
                license_expiration = EXCLUDED.license_expiration,
                npi_number = EXCLUDED.npi_number,
                dea_number = EXCLUDED.dea_number,
                dea_expiration = EXCLUDED.dea_expiration,
                board_certification = EXCLUDED.board_certification,
                board_certification_expiration = EXCLUDED.board_certification_expiration,
                clinical_specialty = EXCLUDED.clinical_specialty,
                oig_last_checked = EXCLUDED.oig_last_checked,
                oig_status = EXCLUDED.oig_status,
                malpractice_carrier = EXCLUDED.malpractice_carrier,
                malpractice_policy_number = EXCLUDED.malpractice_policy_number,
                malpractice_expiration = EXCLUDED.malpractice_expiration,
                health_clearances = EXCLUDED.health_clearances,
                updated_at = NOW()
        """,
            employee_id, company_id,
            body.license_type, encrypted["license_number"], body.license_state, _parse_date(body.license_expiration),
            encrypted["npi_number"], encrypted["dea_number"], _parse_date(body.dea_expiration),
            body.board_certification, _parse_date(body.board_certification_expiration),
            body.clinical_specialty,
            _parse_date(body.oig_last_checked), body.oig_status or "not_checked",
            body.malpractice_carrier, encrypted["malpractice_policy_number"], _parse_date(body.malpractice_expiration),
            json.dumps(body.health_clearances) if body.health_clearances else "{}",
        )

    # Return updated data
    return await get_employee_credentials(employee_id, current_user)


# ===========================================
# Credential Documents (upload + AI extraction)
# ===========================================

MAX_CREDENTIAL_UPLOAD_SIZE = 10 * 1024 * 1024  # 10 MB
ALLOWED_CREDENTIAL_EXTENSIONS = {".pdf", ".png", ".jpg", ".jpeg", ".gif", ".tiff"}
VALID_DOCUMENT_TYPES = {"medical_license", "dea", "npi", "board_cert", "malpractice", "health_clearance", "other"}


class CredentialDocumentResponse(BaseModel):
    id: str
    company_id: str
    employee_id: str
    document_type: str
    filename: str
    file_path: Optional[str] = None
    mime_type: Optional[str] = None
    file_size: Optional[int] = None
    extracted_data: Optional[dict] = None
    extraction_status: str = "pending"
    review_status: str = "pending"
    reviewed_by: Optional[str] = None
    reviewed_at: Optional[str] = None
    review_notes: Optional[str] = None
    uploaded_by: Optional[str] = None
    uploaded_via: str = "admin"
    created_at: Optional[str] = None
    updated_at: Optional[str] = None


def _cred_doc_from_row(row) -> dict:
    return {
        "id": str(row["id"]),
        "company_id": str(row["company_id"]),
        "employee_id": str(row["employee_id"]),
        "document_type": row["document_type"],
        "filename": row["filename"],
        "file_path": row.get("file_path"),
        "mime_type": row.get("mime_type"),
        "file_size": row.get("file_size"),
        "extracted_data": json.loads(row["extracted_data"]) if isinstance(row.get("extracted_data"), str) else row.get("extracted_data"),
        "extraction_status": row.get("extraction_status", "pending"),
        "review_status": row.get("review_status", "pending"),
        "reviewed_by": str(row["reviewed_by"]) if row.get("reviewed_by") else None,
        "reviewed_at": row["reviewed_at"].isoformat() if row.get("reviewed_at") else None,
        "review_notes": row.get("review_notes"),
        "uploaded_by": str(row["uploaded_by"]) if row.get("uploaded_by") else None,
        "uploaded_via": row.get("uploaded_via", "admin"),
        "created_at": row["created_at"].isoformat() if row.get("created_at") else None,
        "updated_at": row["updated_at"].isoformat() if row.get("updated_at") else None,
    }


async def _run_credential_extraction(document_id: UUID, file_bytes: bytes, mime_type: str, document_type: str):
    """Background task: run Gemini extraction and update the DB row."""
    try:
        from app.core.services.credential_extraction import extract_credential_info
        result = await extract_credential_info(file_bytes, mime_type, document_type)
        extraction_status = "extracted" if result.get("fields") else "failed"
        async with get_connection() as conn:
            await conn.execute(
                """UPDATE credential_documents
                   SET extracted_data = $1::jsonb, extraction_status = $2, updated_at = NOW()
                   WHERE id = $3""",
                json.dumps(result), extraction_status, document_id,
            )
    except Exception as e:
        logger.error(f"Credential extraction failed for document {document_id}: {e}")
        async with get_connection() as conn:
            await conn.execute(
                """UPDATE credential_documents
                   SET extraction_status = 'failed', extracted_data = $1::jsonb, updated_at = NOW()
                   WHERE id = $2""",
                json.dumps({"error": str(e)}), document_id,
            )


@router.post("/{employee_id}/credential-documents", response_model=CredentialDocumentResponse)
async def upload_credential_document(
    employee_id: UUID,
    background_tasks: BackgroundTasks,
    file: UploadFile = File(...),
    document_type: str = Query(..., description="Document type"),
    current_user: CurrentUser = Depends(require_admin_or_client),
):
    """Upload a credential document for an employee. Triggers AI extraction."""
    company_id = await get_client_company_id(current_user)

    if document_type not in VALID_DOCUMENT_TYPES:
        raise HTTPException(status_code=400, detail=f"Invalid document_type. Must be one of: {sorted(VALID_DOCUMENT_TYPES)}")

    filename = file.filename or "document"
    ext = ("." + filename.rsplit(".", 1)[-1].lower()) if "." in filename else ""
    if ext not in ALLOWED_CREDENTIAL_EXTENSIONS:
        raise HTTPException(status_code=400, detail=f"Unsupported file type. Allowed: {sorted(ALLOWED_CREDENTIAL_EXTENSIONS)}")

    file_bytes = await file.read()
    if len(file_bytes) > MAX_CREDENTIAL_UPLOAD_SIZE:
        raise HTTPException(status_code=413, detail=f"File too large. Maximum size is {MAX_CREDENTIAL_UPLOAD_SIZE // (1024 * 1024)}MB")

    async with get_connection() as conn:
        emp = await conn.fetchval(
            "SELECT id FROM employees WHERE id = $1 AND org_id = $2",
            employee_id, company_id,
        )
        if not emp:
            raise HTTPException(status_code=404, detail="Employee not found")

    storage = get_storage()
    file_path = await storage.upload_private_file(
        file_bytes, filename,
        prefix=f"employee-credentials/{company_id}/{employee_id}",
        content_type=file.content_type,
    )

    async with get_connection() as conn:
        row = await conn.fetchrow(
            """INSERT INTO credential_documents
               (company_id, employee_id, document_type, filename, file_path, mime_type, file_size, uploaded_by, uploaded_via)
               VALUES ($1, $2, $3, $4, $5, $6, $7, $8, 'admin')
               RETURNING *""",
            company_id, employee_id, document_type, filename, file_path,
            file.content_type, len(file_bytes), current_user.id,
        )

    background_tasks.add_task(_run_credential_extraction, row["id"], file_bytes, file.content_type or "application/octet-stream", document_type)

    return _cred_doc_from_row(row)


@router.get("/{employee_id}/credential-documents")
async def list_credential_documents(
    employee_id: UUID,
    current_user: CurrentUser = Depends(require_admin_or_client),
):
    """List all credential documents for an employee."""
    company_id = await get_client_company_id(current_user)

    async with get_connection() as conn:
        emp = await conn.fetchval(
            "SELECT id FROM employees WHERE id = $1 AND org_id = $2",
            employee_id, company_id,
        )
        if not emp:
            raise HTTPException(status_code=404, detail="Employee not found")

        rows = await conn.fetch(
            """SELECT * FROM credential_documents
               WHERE employee_id = $1 AND company_id = $2
               ORDER BY created_at DESC""",
            employee_id, company_id,
        )

    return [_cred_doc_from_row(r) for r in rows]


@router.delete("/{employee_id}/credential-documents/{document_id}")
async def delete_credential_document(
    employee_id: UUID,
    document_id: UUID,
    current_user: CurrentUser = Depends(require_admin_or_client),
):
    """Delete a credential document."""
    company_id = await get_client_company_id(current_user)

    async with get_connection() as conn:
        row = await conn.fetchrow(
            """SELECT file_path FROM credential_documents
               WHERE id = $1 AND employee_id = $2 AND company_id = $3""",
            document_id, employee_id, company_id,
        )
        if not row:
            raise HTTPException(status_code=404, detail="Document not found")

        storage = get_storage()
        await storage.delete_private_file(row["file_path"])

        await conn.execute("DELETE FROM credential_documents WHERE id = $1", document_id)

    return {"message": "Document deleted"}


class ApproveRequest(BaseModel):
    apply_to_credentials: bool = False
    notes: Optional[str] = None


@router.post("/{employee_id}/credential-documents/{document_id}/approve")
async def approve_credential_document(
    employee_id: UUID,
    document_id: UUID,
    body: ApproveRequest,
    current_user: CurrentUser = Depends(require_admin_or_client),
):
    """Approve a credential document. Optionally apply extracted data to employee credentials."""
    company_id = await get_client_company_id(current_user)

    async with get_connection() as conn:
        row = await conn.fetchrow(
            """SELECT * FROM credential_documents
               WHERE id = $1 AND employee_id = $2 AND company_id = $3""",
            document_id, employee_id, company_id,
        )
        if not row:
            raise HTTPException(status_code=404, detail="Document not found")

        await conn.execute(
            """UPDATE credential_documents
               SET review_status = 'approved', reviewed_by = $1, reviewed_at = NOW(),
                   review_notes = $2, updated_at = NOW()
               WHERE id = $3""",
            current_user.id, body.notes, document_id,
        )

        if body.apply_to_credentials and row.get("extracted_data"):
            extracted = row["extracted_data"] if isinstance(row["extracted_data"], dict) else json.loads(row["extracted_data"])
            fields = extracted.get("fields", {})

            # Map extracted fields to employee_credentials columns
            updates = {}
            doc_type = row["document_type"]

            for field_name, field_data in fields.items():
                if not isinstance(field_data, dict):
                    continue
                val = field_data.get("value")
                if val is None:
                    continue

                # Only map known credential fields
                if field_name in (
                    "license_type", "license_number", "license_state", "license_expiration",
                    "npi_number", "dea_number", "dea_expiration",
                    "board_certification", "board_certification_expiration",
                    "clinical_specialty",
                    "malpractice_carrier", "malpractice_policy_number", "malpractice_expiration",
                ):
                    updates[field_name] = val

            if updates:
                encrypted = encrypt_credential_fields(updates)
                # Use upsert to write extracted data into employee_credentials
                set_clauses = []
                values = [employee_id, company_id]
                insert_cols = ["employee_id", "org_id"]
                insert_placeholders = ["$1", "$2"]
                idx = 3

                for col, val in encrypted.items():
                    insert_cols.append(col)
                    insert_placeholders.append(f"${idx}")
                    set_clauses.append(f"{col} = ${idx}")
                    values.append(val)
                    idx += 1

                set_clauses.append("updated_at = NOW()")
                sql = f"""
                    INSERT INTO employee_credentials ({', '.join(insert_cols)})
                    VALUES ({', '.join(insert_placeholders)})
                    ON CONFLICT (employee_id) DO UPDATE SET {', '.join(set_clauses)}
                """
                await conn.execute(sql, *values)

        # Auto-complete matching credential onboarding task
        try:
            await conn.execute(
                """UPDATE employee_onboarding_tasks
                   SET status = 'completed', completed_at = NOW(), completed_by = $1, updated_at = NOW()
                   WHERE employee_id = $2 AND document_type = $3 AND status = 'pending'""",
                current_user.id, employee_id, row["document_type"],
            )
        except Exception:
            logger.exception("Failed to auto-complete onboarding task for credential doc %s", document_id)

    return {"message": "Document approved", "applied_to_credentials": body.apply_to_credentials}


class RejectRequest(BaseModel):
    notes: str


@router.post("/{employee_id}/credential-documents/{document_id}/reject")
async def reject_credential_document(
    employee_id: UUID,
    document_id: UUID,
    body: RejectRequest,
    current_user: CurrentUser = Depends(require_admin_or_client),
):
    """Reject a credential document."""
    company_id = await get_client_company_id(current_user)

    async with get_connection() as conn:
        exists = await conn.fetchval(
            """SELECT id FROM credential_documents
               WHERE id = $1 AND employee_id = $2 AND company_id = $3""",
            document_id, employee_id, company_id,
        )
        if not exists:
            raise HTTPException(status_code=404, detail="Document not found")

        await conn.execute(
            """UPDATE credential_documents
               SET review_status = 'rejected', reviewed_by = $1, reviewed_at = NOW(),
                   review_notes = $2, updated_at = NOW()
               WHERE id = $3""",
            current_user.id, body.notes, document_id,
        )

    return {"message": "Document rejected"}


@router.get("/{employee_id}/credential-documents/{document_id}/download")
async def download_credential_document(
    employee_id: UUID,
    document_id: UUID,
    current_user: CurrentUser = Depends(require_admin_or_client),
):
    """Get a presigned download URL for a credential document."""
    company_id = await get_client_company_id(current_user)

    async with get_connection() as conn:
        row = await conn.fetchrow(
            """SELECT file_path, filename, mime_type FROM credential_documents
               WHERE id = $1 AND employee_id = $2 AND company_id = $3""",
            document_id, employee_id, company_id,
        )
        if not row:
            raise HTTPException(status_code=404, detail="Document not found")

    storage = get_storage()
    presigned = storage.get_presigned_download_url(row["file_path"])
    if not presigned:
        raise HTTPException(status_code=500, detail="Unable to generate download URL")
    return {"url": presigned, "filename": row["filename"]}
