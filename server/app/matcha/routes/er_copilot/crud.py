"""ER case lifecycle: create, list, metrics, by-employee, get, update, delete."""
import json
from typing import Optional
from uuid import UUID

from fastapi import APIRouter, BackgroundTasks, HTTPException, Depends, Query, Request

from ....database import get_connection
from ...dependencies import require_admin_or_client, get_client_company_id
from ....core.models.auth import CurrentUser
from ...models.er_case import (
    ERCaseCreate,
    ERCaseUpdate,
    ERCaseResponse,
    ERCaseListResponse,
    ERCaseStatus,
)

from ._shared import (
    create_case_core,
    _queue_risk_assessment_refresh,
    log_audit,
    _verify_case_company,
    _normalize_intake_context,
    _normalize_json_list,
)

router = APIRouter()



# ===========================================
# Cases CRUD
# ===========================================

@router.post("", response_model=ERCaseResponse)
async def create_case(
    case: ERCaseCreate,
    request: Request,
    background_tasks: BackgroundTasks,
    current_user: CurrentUser = Depends(require_admin_or_client),
):
    """Create a new ER investigation case."""
    company_id = await get_client_company_id(current_user)
    if company_id is None:
        raise HTTPException(status_code=400, detail="No company found")

    async with get_connection() as conn:
        row, _bg = await create_case_core(
            conn,
            company_id=company_id,
            created_by=str(current_user.id),
            case=case,
            ip_address=request.client.host if request.client else None,
        )

        _queue_risk_assessment_refresh(background_tasks, row["company_id"])

        return ERCaseResponse(
            id=row["id"],
            case_number=row["case_number"],
            title=row["title"],
            description=row["description"],
            intake_context=_normalize_intake_context(row["intake_context"]),
            status=row["status"],
            category=row["category"],
            outcome=row["outcome"],
            company_id=row["company_id"],
            created_by=row["created_by"],
            assigned_to=row["assigned_to"],
            document_count=0,
            involved_employees=_normalize_json_list(row.get("involved_employees")),
            created_at=row["created_at"],
            updated_at=row["updated_at"],
            closed_at=row["closed_at"],
        )


@router.get("", response_model=ERCaseListResponse)
async def list_cases(
    status: Optional[ERCaseStatus] = None,
    current_user: CurrentUser = Depends(require_admin_or_client),
):
    """List ER cases scoped to the user's company."""
    company_id = await get_client_company_id(current_user)
    if company_id is None:
        return ERCaseListResponse(cases=[], total=0)

    is_admin = current_user.role == "admin"
    async with get_connection() as conn:
        company_filter = "(c.company_id = $1 OR c.company_id IS NULL)" if is_admin else "c.company_id = $1"
        base_query = f"""
            SELECT c.*, COUNT(d.id) as document_count
            FROM er_cases c
            LEFT JOIN er_case_documents d ON c.id = d.case_id
            WHERE {company_filter}
        """

        if status:
            query = base_query + " AND c.status = $2 GROUP BY c.id ORDER BY c.updated_at DESC"
            rows = await conn.fetch(query, company_id, status)
        else:
            query = base_query + " GROUP BY c.id ORDER BY c.updated_at DESC"
            rows = await conn.fetch(query, company_id)

        cases = [
            ERCaseResponse(
                id=row["id"],
                case_number=row["case_number"],
                title=row["title"],
                description=row["description"],
                intake_context=_normalize_intake_context(row["intake_context"]),
                status=row["status"],
                category=row.get("category"),
                outcome=row.get("outcome"),
                company_id=row["company_id"],
                created_by=row["created_by"],
                assigned_to=row["assigned_to"],
                document_count=row["document_count"],
                involved_employees=_normalize_json_list(row.get("involved_employees")),
                created_at=row["created_at"],
                updated_at=row["updated_at"],
                closed_at=row["closed_at"],
            )
            for row in rows
        ]

        return ERCaseListResponse(cases=cases, total=len(cases))


@router.get("/metrics")
async def get_case_metrics(
    days: int = Query(30, ge=1, le=365),
    current_user: CurrentUser = Depends(require_admin_or_client),
):
    """Get ER case metrics for the specified period."""
    company_id = await get_client_company_id(current_user)
    if company_id is None:
        return {"period_days": days, "total_cases": 0, "by_status": {}, "by_category": {}, "by_outcome": {}, "trend": []}

    async with get_connection() as conn:
        is_admin = current_user.role == "admin"
        company_filter = "(company_id = $1 OR company_id IS NULL)" if is_admin else "company_id = $1"
        date_filter = f"created_at >= NOW() - interval '{int(days)} days'"

        # Total cases
        total = await conn.fetchval(
            f"SELECT COUNT(*) FROM er_cases WHERE {company_filter} AND {date_filter}",
            company_id,
        )

        # By status
        status_rows = await conn.fetch(
            f"SELECT status, COUNT(*) as cnt FROM er_cases WHERE {company_filter} AND {date_filter} GROUP BY status",
            company_id,
        )
        by_status = {r["status"]: r["cnt"] for r in status_rows}

        # By category
        cat_rows = await conn.fetch(
            f"SELECT category, COUNT(*) as cnt FROM er_cases WHERE {company_filter} AND {date_filter} AND category IS NOT NULL GROUP BY category",
            company_id,
        )
        by_category = {r["category"]: r["cnt"] for r in cat_rows}

        # By outcome
        out_rows = await conn.fetch(
            f"SELECT outcome, COUNT(*) as cnt FROM er_cases WHERE {company_filter} AND {date_filter} AND outcome IS NOT NULL GROUP BY outcome",
            company_id,
        )
        by_outcome = {r["outcome"]: r["cnt"] for r in out_rows}

        # Daily trend
        trend_rows = await conn.fetch(
            f"SELECT created_at::date as d, COUNT(*) as cnt FROM er_cases WHERE {company_filter} AND {date_filter} GROUP BY d ORDER BY d",
            company_id,
        )
        trend = [{"date": str(r["d"]), "count": r["cnt"]} for r in trend_rows]

        return {
            "period_days": days,
            "total_cases": total or 0,
            "by_status": by_status,
            "by_category": by_category,
            "by_outcome": by_outcome,
            "trend": trend,
        }


@router.get("/by-employee/{employee_id}", response_model=ERCaseListResponse)
async def get_cases_by_employee(
    employee_id: UUID,
    status: Optional[ERCaseStatus] = None,
    current_user: CurrentUser = Depends(require_admin_or_client),
):
    """Get all ER cases involving a specific employee."""
    company_id = await get_client_company_id(current_user)
    if company_id is None:
        return ERCaseListResponse(cases=[], total=0)

    is_admin = current_user.role == "admin"
    async with get_connection() as conn:
        company_filter = "(c.company_id = $1 OR c.company_id IS NULL)" if is_admin else "c.company_id = $1"
        containment = json.dumps([{"employee_id": str(employee_id)}])

        base_query = f"""
            SELECT c.*, COUNT(d.id) as document_count
            FROM er_cases c
            LEFT JOIN er_case_documents d ON c.id = d.case_id
            WHERE {company_filter}
              AND c.involved_employees @> $2::jsonb
        """

        if status:
            query = base_query + " AND c.status = $3 GROUP BY c.id ORDER BY c.updated_at DESC"
            rows = await conn.fetch(query, company_id, containment, status)
        else:
            query = base_query + " GROUP BY c.id ORDER BY c.updated_at DESC"
            rows = await conn.fetch(query, company_id, containment)

        cases = [
            ERCaseResponse(
                id=row["id"],
                case_number=row["case_number"],
                title=row["title"],
                description=row["description"],
                intake_context=_normalize_intake_context(row["intake_context"]),
                status=row["status"],
                category=row.get("category"),
                outcome=row.get("outcome"),
                company_id=row["company_id"],
                created_by=row["created_by"],
                assigned_to=row["assigned_to"],
                document_count=row["document_count"],
                involved_employees=_normalize_json_list(row.get("involved_employees")),
                created_at=row["created_at"],
                updated_at=row["updated_at"],
                closed_at=row["closed_at"],
            )
            for row in rows
        ]

        return ERCaseListResponse(cases=cases, total=len(cases))


@router.get("/{case_id}", response_model=ERCaseResponse)
async def get_case(
    case_id: UUID,
    current_user: CurrentUser = Depends(require_admin_or_client),
):
    """Get a case by ID."""
    company_id = await get_client_company_id(current_user)
    if company_id is None:
        raise HTTPException(status_code=404, detail="Case not found")

    is_admin = current_user.role == "admin"
    async with get_connection() as conn:
        company_filter = "(c.company_id = $2 OR c.company_id IS NULL)" if is_admin else "c.company_id = $2"
        row = await conn.fetchrow(
            f"""
            SELECT c.*, COUNT(d.id) as document_count
            FROM er_cases c
            LEFT JOIN er_case_documents d ON c.id = d.case_id
            WHERE c.id = $1 AND {company_filter}
            GROUP BY c.id
            """,
            case_id,
            company_id,
        )

        if not row:
            raise HTTPException(status_code=404, detail="Case not found")

        return ERCaseResponse(
            id=row["id"],
            case_number=row["case_number"],
            title=row["title"],
            description=row["description"],
            intake_context=_normalize_intake_context(row["intake_context"]),
            status=row["status"],
            category=row.get("category"),
            outcome=row.get("outcome"),
            company_id=row["company_id"],
            created_by=row["created_by"],
            assigned_to=row["assigned_to"],
            document_count=row["document_count"],
            involved_employees=_normalize_json_list(row.get("involved_employees")),
            created_at=row["created_at"],
            updated_at=row["updated_at"],
            closed_at=row["closed_at"],
        )


@router.put("/{case_id}", response_model=ERCaseResponse)
async def update_case(
    case_id: UUID,
    case: ERCaseUpdate,
    request: Request,
    background_tasks: BackgroundTasks,
    current_user: CurrentUser = Depends(require_admin_or_client),
):
    """Update a case."""
    company_id = await get_client_company_id(current_user)
    if company_id is None:
        raise HTTPException(status_code=404, detail="Case not found")

    is_admin = current_user.role == "admin"
    async with get_connection() as conn:
        await _verify_case_company(conn, case_id, company_id, is_admin)

        # Build dynamic update
        updates = []
        params = []
        param_count = 1

        if case.title is not None:
            updates.append(f"title = ${param_count}")
            params.append(case.title)
            param_count += 1

        if case.description is not None:
            updates.append(f"description = ${param_count}")
            params.append(case.description)
            param_count += 1

        if case.status is not None:
            updates.append(f"status = ${param_count}")
            params.append(case.status)
            param_count += 1

            if case.status == "closed":
                updates.append("closed_at = NOW()")

        if case.assigned_to is not None:
            updates.append(f"assigned_to = ${param_count}")
            params.append(case.assigned_to)
            param_count += 1

        if case.intake_context is not None:
            updates.append(f"intake_context = ${param_count}::jsonb")
            params.append(json.dumps(case.intake_context))
            param_count += 1

        if case.category is not None:
            updates.append(f"category = ${param_count}")
            params.append(case.category)
            param_count += 1

        if case.outcome is not None:
            updates.append(f"outcome = ${param_count}")
            params.append(case.outcome)
            param_count += 1

        if case.involved_employees is not None:
            updates.append(f"involved_employees = ${param_count}::jsonb")
            params.append(json.dumps([e.model_dump(mode="json") for e in case.involved_employees]))
            param_count += 1

        if not updates:
            raise HTTPException(status_code=400, detail="No updates provided")

        updates.append("updated_at = NOW()")
        params.append(case_id)
        param_count += 1
        params.append(company_id)

        company_filter = f"(company_id = ${param_count} OR company_id IS NULL)" if is_admin else f"company_id = ${param_count}"
        query = f"""
            UPDATE er_cases
            SET {', '.join(updates)}
            WHERE id = ${param_count - 1} AND {company_filter}
            RETURNING id, case_number, title, description, intake_context, status, company_id, created_by, assigned_to, created_at, updated_at, closed_at, category, outcome, involved_employees
        """

        row = await conn.fetchrow(query, *params)

        if not row:
            raise HTTPException(status_code=404, detail="Case not found")

        # Get document count
        doc_count = await conn.fetchval(
            "SELECT COUNT(*) FROM er_case_documents WHERE case_id = $1",
            case_id,
        )

        # Log audit
        await log_audit(
            conn,
            str(case_id),
            str(current_user.id),
            "case_updated",
            "case",
            str(case_id),
            case.model_dump(mode="json", exclude_none=True),
            request.client.host if request.client else None,
        )

        # Any case mutation can change the ER score or open-case list.
        _queue_risk_assessment_refresh(background_tasks, row["company_id"])

        return ERCaseResponse(
            id=row["id"],
            case_number=row["case_number"],
            title=row["title"],
            description=row["description"],
            intake_context=_normalize_intake_context(row["intake_context"]),
            status=row["status"],
            category=row["category"],
            outcome=row["outcome"],
            company_id=row["company_id"],
            created_by=row["created_by"],
            assigned_to=row["assigned_to"],
            document_count=doc_count or 0,
            involved_employees=_normalize_json_list(row.get("involved_employees")),
            created_at=row["created_at"],
            updated_at=row["updated_at"],
            closed_at=row["closed_at"],
        )


@router.delete("/{case_id}")
async def delete_case(
    case_id: UUID,
    request: Request,
    background_tasks: BackgroundTasks,
    current_user: CurrentUser = Depends(require_admin_or_client),
):
    """Delete a case and all associated data."""
    company_id = await get_client_company_id(current_user)
    if company_id is None:
        raise HTTPException(status_code=404, detail="Case not found")

    is_admin = current_user.role == "admin"
    company_filter = "(company_id = $2 OR company_id IS NULL)" if is_admin else "company_id = $2"

    async with get_connection() as conn:
        # Get case info for audit log before deletion
        case = await conn.fetchrow(
            f"SELECT case_number, title FROM er_cases WHERE id = $1 AND {company_filter}",
            case_id,
            company_id,
        )

        if not case:
            raise HTTPException(status_code=404, detail="Case not found")

        # Delete case (cascades to documents, chunks, analysis)
        await conn.execute(
            f"DELETE FROM er_cases WHERE id = $1 AND {company_filter}",
            case_id,
            company_id,
        )

        # Log audit (case_id is null since case is deleted)
        await log_audit(
            conn,
            None,
            str(current_user.id),
            "case_deleted",
            "case",
            str(case_id),
            {"case_number": case["case_number"], "title": case["title"]},
            request.client.host if request.client else None,
        )

        _queue_risk_assessment_refresh(background_tasks, company_id)

        return {"status": "deleted", "case_id": str(case_id)}


# ===========================================
# Case Export
# ===========================================

