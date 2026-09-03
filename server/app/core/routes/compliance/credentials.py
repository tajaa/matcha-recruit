"""credentials routes (L9 split)."""
from datetime import date, timedelta
from typing import List, Optional

from fastapi import Depends, HTTPException, Query

from app.core.models.auth import CurrentUser
from app.core.models.compliance import (
    CompanyCertificationResponse,
    CompanyLicenseResponse,
    EmployeeDocumentExpiryResponse,
)
from app.database import get_connection
from app.matcha.dependencies import require_admin_or_client, require_feature
from app.matcha.services.scheduling.schedule_eligibility import WARNING_DAYS_SQL

from ._shared import _fetch_company_credentials, resolve_company_id, router, shared_router


_DOCUMENT_STATUS_PRIORITY = {
    "expired": 0,
    "expiring_soon": 1,
    "unknown": 2,
    "current": 3,
}

# Employee rollup ordering: most urgent first, so an expired credential is never
# buried under alphabetically-earlier employees who need nothing.
_EMPLOYEE_STATUS_PRIORITY = {
    "expired": 0,
    "expiring_soon": 1,
    "unknown": 2,
    "no_actionable_expiry": 3,
}

# Work permits carry no per-type window; 14 days matches the `validity` field
# routes/employees/work_permits.py already returns for the same permit.
_WORK_PERMIT_WARNING_DAYS = 14


def _expiry_status(
    *, expiry_date: date | None, stored_status: str, warning_days: int | None, today: date,
) -> str:
    if stored_status == "expired" or (expiry_date is not None and expiry_date < today):
        return "expired"
    if expiry_date is None:
        return "unknown"
    if expiry_date <= today + timedelta(days=warning_days or _WORK_PERMIT_WARNING_DAYS):
        return "expiring_soon"
    return "current"



@router.get("/certifications", response_model=List[CompanyCertificationResponse])
async def list_company_certifications(
    company_id: Optional[str] = Query(None),
    current_user: CurrentUser = Depends(require_admin_or_client),
):
    """Per-company certifications, joined to the catalog (admins may pass ?company_id=)."""
    cid = await resolve_company_id(current_user, company_id)
    if cid is None:
        raise HTTPException(status_code=403, detail="Access denied")
    async with get_connection() as conn:
        return await _fetch_company_credentials(conn, cid, kind="certification")




@router.get("/licenses", response_model=List[CompanyLicenseResponse])
async def list_company_licenses(
    company_id: Optional[str] = Query(None),
    current_user: CurrentUser = Depends(require_admin_or_client),
):
    """Per-company licenses, joined to the catalog (admins may pass ?company_id=)."""
    cid = await resolve_company_id(current_user, company_id)
    if cid is None:
        raise HTTPException(status_code=403, detail="Access denied")
    async with get_connection() as conn:
        return await _fetch_company_credentials(conn, cid, kind="license")


@shared_router.get(
    "/employee-document-expiries",
    response_model=List[EmployeeDocumentExpiryResponse],
    # shared_router's mount only asks for compliance OR compliance_lite. Employee
    # credential data belongs to the credentialing product, so gate it here rather
    # than at the mount — the sibling compliance readers stay reachable without it.
    dependencies=[Depends(require_feature("credential_templates"))],
)
async def list_employee_document_expiries(
    company_id: Optional[str] = Query(None),
    current_user: CurrentUser = Depends(require_admin_or_client),
):
    """Read-only employee credential and work-permit expiry roster."""
    cid = await resolve_company_id(current_user, company_id)
    if cid is None:
        raise HTTPException(status_code=403, detail="Access denied")

    async with get_connection() as conn:
        rows = await conn.fetch(
            f"""
            WITH active_employees AS (
                SELECT id, first_name, last_name
                FROM employees
                WHERE org_id = $1
                  AND termination_date IS NULL
                  AND COALESCE(employment_status, 'active')
                      NOT IN ('terminated', 'offboarded', 'inactive')
            ), document_expiries AS (
                SELECT ecr.employee_id, ecr.id AS document_id,
                       'credential'::text AS kind,
                       ct.label AS document_type,
                       ecr.expires_at AS expiry_date,
                       ecr.status AS stored_status,
                       NULL::text AS location_name,
                       ({WARNING_DAYS_SQL})::int AS warning_days
                FROM employee_credential_requirements ecr
                JOIN active_employees ae ON ae.id = ecr.employee_id
                JOIN scoped_credential_types ct ON ct.id = ecr.credential_type_id
                LEFT JOIN credential_requirement_templates crt ON crt.id = ecr.template_id
                WHERE ecr.is_required = true
                  AND ct.has_expiration = true
                  AND ecr.status NOT IN ('waived', 'not_applicable')
                  AND (
                      ecr.applies_company_wide = true
                      OR EXISTS (
                          SELECT 1
                          FROM schedule_job_employees sje
                          JOIN schedule_job_credential_requirements jr
                            ON jr.job_id = sje.job_id
                           AND jr.company_id = sje.company_id
                          WHERE sje.company_id = $1
                            AND sje.employee_id = ecr.employee_id
                            AND jr.credential_type_id = ecr.credential_type_id
                            AND jr.is_required
                      )
                  )

                UNION ALL

                SELECT p.employee_id, p.id AS document_id,
                       'work_permit'::text AS kind,
                       'Work permit'::text AS document_type,
                       p.expires_at AS expiry_date,
                       p.status AS stored_status,
                       bl.name AS location_name,
                       {_WORK_PERMIT_WARNING_DAYS}::int AS warning_days
                FROM employee_work_permits p
                JOIN active_employees ae ON ae.id = p.employee_id
                LEFT JOIN business_locations bl
                  ON bl.id = p.location_id AND bl.company_id = $1
                WHERE p.company_id = $1
                  AND p.status = 'active'
                  AND p.confirmed_on_file = true
            )
            SELECT ae.id AS employee_id, ae.first_name, ae.last_name,
                   de.document_id, de.kind, de.document_type, de.expiry_date,
                   de.stored_status, de.location_name, de.warning_days
            FROM active_employees ae
            LEFT JOIN document_expiries de ON de.employee_id = ae.id
            ORDER BY LOWER(ae.last_name), LOWER(ae.first_name), de.document_type
            """,
            cid,
        )

    today = date.today()
    employees: dict[str, dict] = {}
    # Name keys kept beside the payload so the final ordering can break ties
    # alphabetically without leaking sort-only fields into the response.
    sort_names: dict[str, tuple[str, str]] = {}
    for row in rows:
        employee_id = str(row["employee_id"])
        sort_names.setdefault(
            employee_id,
            ((row["last_name"] or "").lower(), (row["first_name"] or "").lower()),
        )
        employee = employees.setdefault(
            employee_id,
            {
                "employee_id": employee_id,
                "employee_name": f"{row['first_name']} {row['last_name']}".strip(),
                "status": "no_actionable_expiry",
                "documents": [],
            },
        )
        if row["document_id"] is None:
            continue
        status = _expiry_status(
            expiry_date=row["expiry_date"],
            stored_status=row["stored_status"],
            warning_days=row["warning_days"],
            today=today,
        )
        employee["documents"].append({
            "id": str(row["document_id"]),
            "kind": row["kind"],
            "document_type": row["document_type"],
            "expiry_date": row["expiry_date"],
            "expiry_status": status,
            "location_name": row["location_name"],
        })

    for employee in employees.values():
        employee["documents"].sort(
            key=lambda item: (_DOCUMENT_STATUS_PRIORITY[item["expiry_status"]], item["document_type"])
        )
        actionable = [
            item["expiry_status"]
            for item in employee["documents"]
            if item["expiry_status"] != "current"
        ]
        if actionable:
            employee["status"] = min(actionable, key=_DOCUMENT_STATUS_PRIORITY.__getitem__)

    return sorted(
        employees.values(),
        key=lambda employee: (
            _EMPLOYEE_STATUS_PRIORITY[employee["status"]],
            sort_names[employee["employee_id"]],
        ),
    )
