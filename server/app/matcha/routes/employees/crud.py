"""Employee CRUD + collection-root endpoints.

Owns the package's main `router`. Other submodules (onboarding, offboarding,
invitations, bulk_upload, leave, incidents, credentials, oig) append their
routes via `router.include_router(...)` in the package `__init__.py`.

Routes:
  GET  /onboarding-progress             — bulk onboarding-progress summary
  GET  ""                               — list employees (collection root)
  GET  /departments                     — list distinct departments
  GET  /locations                       — list distinct locations
  GET  /by-uid/{uid}                    — lookup by HR-internal uid
  POST ""                               — create employee (collection root)
  GET  /{employee_id}                   — get employee (catch-all 1-segment GET)
  PUT  /{employee_id}                   — update employee
  PUT  /{employee_id}/status            — update employment_status
  DELETE /{employee_id}                 — delete employee

`GET /{employee_id}` (and PUT/DELETE) catch any 1-segment static GETs in
sibling submodules (e.g. /oig-summary, /incident-counts, /onboarding-draft) —
shadow is preserved by registering this router BEFORE submodule
`include_router` calls.
"""
import logging
from datetime import date, datetime, timedelta
from decimal import Decimal
from typing import List, Optional
from uuid import UUID

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, Query
from pydantic import BaseModel, EmailStr, model_validator

from app.core.models.auth import CurrentUser
from app.database import get_connection
from app.matcha.dependencies import get_client_company_id, require_admin_or_client
from app.matcha.services.onboarding.onboarding_orchestrator import (
    PROVIDER_GOOGLE_WORKSPACE,
    PROVIDER_SLACK,
)
from app.core.services.roster_jurisdictions import run_jurisdiction_drift_check

from ._shared import (
    _auto_send_invitation,
    _coerce_bool,
    _column_exists,
    _employee_compensation_fields_available,
    _employee_compensation_values,
    _employee_org_fields_available,
    _employee_status_fields_available,
    _json_object,
    _normalize_work_state,
    _perform_oig_screening,
    _refresh_risk_assessment,
    _run_provisioning_and_notify,
    _sync_employee_location_for_compliance,
)

logger = logging.getLogger(__name__)

router = APIRouter()
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
    # Explicit UI intent. Unlike the legacy auto-send preference, this does
    # not depend on onboarding_notification_settings.
    send_invitation: bool = False
    pay_classification: Optional[str] = None
    pay_rate: Optional[Decimal] = None
    work_city: Optional[str] = None
    job_title: Optional[str] = None
    department: Optional[str] = None
    work_location_id: Optional[UUID] = None
    uid: Optional[str] = None  # HR-internal badge / employee number
    meal_break_waiver_on_file: Optional[bool] = None

    @model_validator(mode="after")
    def validate_work_email_present(self):
        if not self.work_email and not self.email:
            raise ValueError("work_email (or legacy email) is required")
        return self


async def _should_send_employee_invitation(
    conn,
    *,
    company_id: UUID,
    send_invitation: bool,
    skip_invitation: bool,
) -> bool:
    """Resolve explicit invite intent before the legacy tenant preference."""
    if send_invitation:
        return True
    if skip_invitation:
        return False
    if not await _column_exists(
        conn, "onboarding_notification_settings", "auto_send_invitation"
    ):
        return False
    settings = await conn.fetchrow(
        "SELECT auto_send_invitation FROM onboarding_notification_settings WHERE org_id = $1",
        company_id,
    )
    return bool(settings and settings["auto_send_invitation"])

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
    work_location_id: Optional[UUID] = None

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
    work_location_id: Optional[UUID] = None
    work_location_name: Optional[str] = None
    created_at: datetime

    class Config:
        from_attributes = True


class EmployeeDetailResponse(EmployeeListResponse):
    phone: Optional[str]
    address: Optional[str]
    emergency_contact: Optional[dict]
    # DOB stays in the PII-segregated employee_demographics table. The profile
    # only receives the derived compliance state, never the date itself.
    date_of_birth_on_file: bool = False
    minor_status: str = "unknown"
    updated_at: datetime


def _minor_status(date_of_birth: Optional[date], *, on: Optional[date] = None) -> str:
    if date_of_birth is None:
        return "unknown"
    today = on or date.today()
    age = today.year - date_of_birth.year - ((today.month, today.day) < (date_of_birth.month, date_of_birth.day))
    return "minor" if age < 18 else "adult"


async def _employee_profile_compliance(conn, employee_id: UUID, company_id: UUID) -> tuple[Optional[str], Optional[date]]:
    row = await conn.fetchrow(
        """
        SELECT bl.name AS work_location_name, ed.date_of_birth
        FROM employees e
        LEFT JOIN business_locations bl ON bl.id = e.work_location_id AND bl.company_id = e.org_id
        LEFT JOIN employee_demographics ed ON ed.employee_id = e.id AND ed.org_id = e.org_id
        WHERE e.id = $1 AND e.org_id = $2
        """,
        employee_id,
        company_id,
    )
    if not row:
        return None, None
    return row["work_location_name"], row["date_of_birth"]


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
    work_location_id: Optional[str] = Query(
        None, description="business_locations.id, or 'none' for unassigned/remote"),
    current_user: CurrentUser = Depends(require_admin_or_client),
):
    """List all employees for the company."""
    company_id = await get_client_company_id(current_user)

    async with get_connection() as conn:
        compensation_fields_available = await _employee_compensation_fields_available(conn)
        org_fields_available = await _employee_org_fields_available(conn)
        status_fields_available = await _employee_status_fields_available(conn)
        location_fields_available = await _column_exists(conn, "employees", "work_location_id")
        location_select = (
            "e.work_location_id, bl.name AS work_location_name,"
            if location_fields_available
            else "NULL::UUID AS work_location_id, NULL::VARCHAR AS work_location_name,"
        )
        location_join = (
            "LEFT JOIN business_locations bl ON bl.id = e.work_location_id"
            if location_fields_available else ""
        )
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
                {location_select}
                m.first_name || ' ' || m.last_name as manager_name,
                (
                    SELECT status FROM employee_invitations
                    WHERE employee_id = e.id
                    ORDER BY created_at DESC LIMIT 1
                ) as invitation_status
            FROM employees e
            LEFT JOIN employees m ON e.manager_id = m.id
            {location_join}
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

        if work_location_id and location_fields_available:
            if work_location_id == "none":
                base_query += " AND e.work_location_id IS NULL"
            else:
                base_query += f" AND e.work_location_id = ${param_num}::uuid"
                params.append(work_location_id)
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
                    work_location_id=row["work_location_id"],
                    work_location_name=row["work_location_name"],
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

        # Validate work_state — blank/None allowed unchanged; a non-blank
        # value that isn't a recognized state/territory is rejected so a
        # typo doesn't silently create an ungrounded compliance jurisdiction.
        normalized_work_state = request.work_state
        if request.work_state is not None:
            normalized_work_state, work_state_valid = _normalize_work_state(request.work_state)
            if not work_state_valid:
                raise HTTPException(
                    status_code=400,
                    detail=f"Invalid work_state '{request.work_state.strip()}' — use a 2-letter US state code",
                )

        org_fields_available = await _employee_org_fields_available(conn)

        if request.work_location_id is not None:
            location_row = await conn.fetchval(
                "SELECT 1 FROM business_locations WHERE id = $1 AND company_id = $2",
                request.work_location_id, company_id,
            )
            if not location_row:
                raise HTTPException(status_code=404, detail="Location not found")

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
            normalized_work_state,
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

        if await _column_exists(conn, "employees", "work_location_id"):
            insert_cols.append("work_location_id")
            insert_vals.append(request.work_location_id)

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

        if request.meal_break_waiver_on_file is not None:
            await conn.execute(
                """
                INSERT INTO employee_compliance_attestations
                    (company_id, employee_id, attestation_type, value, effective_from, confirmed_by)
                VALUES ($1, $2, 'meal_break_waiver_on_file', $3, $4, $5)
                """,
                company_id, row["id"], request.meal_break_waiver_on_file,
                date.today(), current_user.id,
            )

        # D4: cheap post-onboarding drift check — does this roster now imply a
        # jurisdiction the company's tracked locations don't cover? Alert-only,
        # never triggers research.
        if row["work_state"]:
            background_tasks.add_task(run_jurisdiction_drift_check, company_id)

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
                job_title_val = request.job_title
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

        # Auto-assign new-hire training per training_assignment_rules
        try:
            from app.matcha.services.training.training_assignment import evaluate_new_hire_rules

            outcome = await evaluate_new_hire_rules(conn, company_id, row["id"])
            if outcome.assigned:
                logger.info(
                    "Assigned %d new-hire training record(s) for employee %s",
                    outcome.assigned, row["id"],
                )
        except Exception:
            logger.exception("Failed to auto-assign new-hire training for employee %s", row["id"])

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
        work_location_name, date_of_birth = await _employee_profile_compliance(
            conn, row["id"], company_id
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
            work_location_id=row.get("work_location_id"),
            work_location_name=work_location_name,
            phone=row["phone"],
            address=row["address"],
            emergency_contact=row["emergency_contact"],
            date_of_birth_on_file=date_of_birth is not None,
            minor_status=_minor_status(date_of_birth),
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

        # An explicit invite request takes precedence over the legacy tenant
        # auto-send preference. OIG screening is independent and never
        # suppresses portal access based on a possible name match.
        try:
            should_send_invitation = await _should_send_employee_invitation(
                conn,
                company_id=company_id,
                send_invitation=request.send_invitation,
                skip_invitation=request.skip_invitation,
            )
        except Exception:
            should_send_invitation = False
            logger.exception("Auto-invite check failed for employee %s", row["id"])

        if should_send_invitation:
            background_tasks.add_task(
                _auto_send_invitation,
                employee_id=row["id"],
                org_id=company_id,
                invited_by=current_user.id,
            )

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
                bl.name AS work_location_name,
                ed.date_of_birth,
                (
                    SELECT status FROM employee_invitations
                    WHERE employee_id = e.id
                    ORDER BY created_at DESC LIMIT 1
                ) as invitation_status
            FROM employees e
            LEFT JOIN employees m ON e.manager_id = m.id
            LEFT JOIN business_locations bl ON bl.id = e.work_location_id AND bl.company_id = e.org_id
            LEFT JOIN employee_demographics ed ON ed.employee_id = e.id AND ed.org_id = e.org_id
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
            work_location_id=row.get("work_location_id"),
            work_location_name=row.get("work_location_name"),
            phone=row["phone"],
            address=row["address"],
            emergency_contact=row["emergency_contact"],
            date_of_birth_on_file=row.get("date_of_birth") is not None,
            minor_status=_minor_status(row.get("date_of_birth")),
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
        # Check employee exists (also grab work_state so we can tell below
        # whether this update actually changes it, for D4 drift detection).
        existing = await conn.fetchrow(
            "SELECT id, work_state FROM employees WHERE id = $1 AND org_id = $2",
            employee_id, company_id
        )
        if not existing:
            raise HTTPException(status_code=404, detail="Employee not found")
        old_work_state = existing["work_state"]

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
            normalized_work_state, work_state_valid = _normalize_work_state(request.work_state)
            if not work_state_valid:
                raise HTTPException(
                    status_code=400,
                    detail=f"Invalid work_state '{request.work_state.strip()}' — use a 2-letter US state code",
                )
            updates.append(f"work_state = ${param_num}")
            values.append(normalized_work_state)
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

        if "work_location_id" in request.model_fields_set and await _column_exists(conn, "employees", "work_location_id"):
            if request.work_location_id is not None:
                location_row = await conn.fetchval(
                    "SELECT 1 FROM business_locations WHERE id = $1 AND company_id = $2",
                    request.work_location_id, company_id,
                )
                if not location_row:
                    raise HTTPException(status_code=404, detail="Location not found")
            updates.append(f"work_location_id = ${param_num}")
            values.append(request.work_location_id)
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

        async with conn.transaction():
            row = await conn.fetchrow(query, *values)

            # Existing staff can move into a role or jurisdiction that has
            # schedule-blocking credentials. Ensure their requirement rows are
            # created in the same transaction as the profile change so the
            # scheduler never interprets a missing row as eligibility.
            eligibility_scope_changed = (
                request.work_state is not None
                or (compensation_fields_available and request.work_city is not None)
                or (org_fields_available and request.job_title is not None)
            )
            if eligibility_scope_changed:
                from app.core.services.credential_template_service import (
                    assign_credential_requirements_to_employee,
                    resolve_credential_requirements,
                )

                credential_requirements = await resolve_credential_requirements(
                    conn,
                    company_id,
                    row["work_state"],
                    row["work_city"] if compensation_fields_available else None,
                    row["job_title"] if org_fields_available else None,
                )
                await assign_credential_requirements_to_employee(
                    conn,
                    row["id"],
                    company_id,
                    credential_requirements,
                    row["start_date"],
                )

        if request.work_state is not None or (compensation_fields_available and request.work_city is not None):
            await _sync_employee_location_for_compliance(
                conn,
                company_id=company_id,
                employee_id=row["id"],
                work_state=row["work_state"],
                work_city=row["work_city"] if compensation_fields_available else None,
                background_tasks=background_tasks,
            )

        # D4: drift check only when work_state actually changed — alert-only,
        # never triggers research.
        if request.work_state is not None and (row["work_state"] or None) != (old_work_state or None):
            background_tasks.add_task(run_jurisdiction_drift_check, company_id)

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
        work_location_name, date_of_birth = await _employee_profile_compliance(
            conn, row["id"], company_id
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
            work_location_id=row.get("work_location_id"),
            work_location_name=work_location_name,
            phone=row["phone"],
            address=row["address"],
            emergency_contact=row["emergency_contact"],
            date_of_birth_on_file=date_of_birth is not None,
            minor_status=_minor_status(date_of_birth),
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

        work_location_name, date_of_birth = await _employee_profile_compliance(
            conn, row["id"], company_id
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
            work_location_id=row.get("work_location_id"),
            work_location_name=work_location_name,
            phone=row["phone"],
            address=row["address"],
            emergency_contact=row["emergency_contact"],
            date_of_birth_on_file=date_of_birth is not None,
            minor_status=_minor_status(date_of_birth),
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
