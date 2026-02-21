import json
from typing import Any, Optional
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, status

from ...core.models.auth import CurrentUser
from ...database import get_connection
from ..dependencies import get_client_company_id, require_admin_or_client
from ..models.internal_mobility import (
    InternalMobilityApplicationAdminResponse,
    InternalMobilityApplicationUpdateRequest,
    InternalOpportunityCreateRequest,
    InternalOpportunityResponse,
    InternalOpportunityUpdateRequest,
)

router = APIRouter()


def _parse_json_array(value: Any) -> list[str]:
    if value is None:
        return []
    if isinstance(value, str):
        try:
            value = json.loads(value)
        except json.JSONDecodeError:
            return []
    if not isinstance(value, list):
        return []
    result: list[str] = []
    for item in value:
        if isinstance(item, str):
            trimmed = item.strip()
            if trimmed:
                result.append(trimmed)
    return result


def _normalize_string_list(values: Optional[list[str]]) -> list[str]:
    if not values:
        return []
    deduped: list[str] = []
    seen: set[str] = set()
    for value in values:
        if not isinstance(value, str):
            continue
        trimmed = value.strip()
        if not trimmed:
            continue
        key = trimmed.lower()
        if key in seen:
            continue
        seen.add(key)
        deduped.append(trimmed)
    return deduped


def _normalize_required_title(value: str) -> str:
    normalized = value.strip()
    if not normalized:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="title cannot be empty",
        )
    return normalized


def _row_to_opportunity(row: Any) -> InternalOpportunityResponse:
    return InternalOpportunityResponse(
        id=row["id"],
        org_id=row["org_id"],
        type=row["type"],
        position_id=row["position_id"],
        title=row["title"],
        department=row["department"],
        description=row["description"],
        required_skills=_parse_json_array(row["required_skills"]),
        preferred_skills=_parse_json_array(row["preferred_skills"]),
        duration_weeks=row["duration_weeks"],
        status=row["status"],
        created_by=row["created_by"],
        created_at=row["created_at"],
        updated_at=row["updated_at"],
    )


def _row_to_application(row: Any) -> InternalMobilityApplicationAdminResponse:
    return InternalMobilityApplicationAdminResponse(
        id=row["id"],
        employee_id=row["employee_id"],
        employee_name=row["employee_name"],
        employee_email=row["employee_email"],
        opportunity_id=row["opportunity_id"],
        opportunity_title=row["opportunity_title"],
        opportunity_type=row["opportunity_type"],
        status=row["status"],
        employee_notes=row["employee_notes"],
        submitted_at=row["submitted_at"],
        reviewed_by=row["reviewed_by"],
        reviewed_at=row["reviewed_at"],
        manager_notified_at=row["manager_notified_at"],
        created_at=row["created_at"],
        updated_at=row["updated_at"],
    )


@router.post("/opportunities", response_model=InternalOpportunityResponse)
async def create_internal_opportunity(
    request: InternalOpportunityCreateRequest,
    current_user: CurrentUser = Depends(require_admin_or_client),
    org_id: Optional[UUID] = Depends(get_client_company_id),
):
    if not org_id:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Company not found")

    if request.duration_weeks is not None and request.duration_weeks <= 0:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="duration_weeks must be greater than 0",
        )
    title = _normalize_required_title(request.title)

    async with get_connection() as conn:
        row = await conn.fetchrow(
            """
            INSERT INTO internal_opportunities (
                org_id, type, position_id, title, department, description,
                required_skills, preferred_skills, duration_weeks, status, created_by
            )
            VALUES ($1, $2, $3, $4, $5, $6, $7::jsonb, $8::jsonb, $9, $10, $11)
            RETURNING id, org_id, type, position_id, title, department, description,
                      required_skills, preferred_skills, duration_weeks, status, created_by,
                      created_at, updated_at
            """,
            org_id,
            request.type,
            request.position_id,
            title,
            request.department.strip() if request.department else None,
            request.description.strip() if request.description else None,
            json.dumps(_normalize_string_list(request.required_skills)),
            json.dumps(_normalize_string_list(request.preferred_skills)),
            request.duration_weeks,
            request.status,
            current_user.id,
        )

    return _row_to_opportunity(row)


@router.get("/opportunities", response_model=list[InternalOpportunityResponse])
async def list_internal_opportunities(
    status_filter: Optional[str] = Query(None, alias="status"),
    type_filter: Optional[str] = Query(None, alias="type"),
    current_user: CurrentUser = Depends(require_admin_or_client),
    org_id: Optional[UUID] = Depends(get_client_company_id),
):
    _ = current_user
    if not org_id:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Company not found")

    if status_filter and status_filter not in {"draft", "active", "closed"}:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Invalid status filter")
    if type_filter and type_filter not in {"role", "project"}:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Invalid type filter")

    query = """
        SELECT id, org_id, type, position_id, title, department, description,
               required_skills, preferred_skills, duration_weeks, status, created_by,
               created_at, updated_at
        FROM internal_opportunities
        WHERE org_id = $1
    """
    params: list[Any] = [org_id]
    param_idx = 2
    if status_filter:
        query += f" AND status = ${param_idx}"
        params.append(status_filter)
        param_idx += 1
    if type_filter:
        query += f" AND type = ${param_idx}"
        params.append(type_filter)
        param_idx += 1
    query += " ORDER BY created_at DESC"

    async with get_connection() as conn:
        rows = await conn.fetch(query, *params)
    return [_row_to_opportunity(row) for row in rows]


@router.patch("/opportunities/{opportunity_id}", response_model=InternalOpportunityResponse)
async def update_internal_opportunity(
    opportunity_id: UUID,
    request: InternalOpportunityUpdateRequest,
    current_user: CurrentUser = Depends(require_admin_or_client),
    org_id: Optional[UUID] = Depends(get_client_company_id),
):
    _ = current_user
    if not org_id:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Company not found")

    payload = request.model_dump(exclude_unset=True)
    if not payload:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="No fields to update")

    if "duration_weeks" in payload and payload["duration_weeks"] is not None and payload["duration_weeks"] <= 0:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="duration_weeks must be greater than 0",
        )
    if "title" in payload:
        if payload["title"] is None:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="title cannot be null")
        payload["title"] = _normalize_required_title(payload["title"])

    updates: list[str] = []
    values: list[Any] = []
    param_idx = 1

    if "type" in payload:
        updates.append(f"type = ${param_idx}")
        values.append(payload["type"])
        param_idx += 1
    if "position_id" in payload:
        updates.append(f"position_id = ${param_idx}")
        values.append(payload["position_id"])
        param_idx += 1
    if "title" in payload:
        updates.append(f"title = ${param_idx}")
        values.append(payload["title"])
        param_idx += 1
    if "department" in payload:
        updates.append(f"department = ${param_idx}")
        values.append(payload["department"].strip() if payload["department"] else None)
        param_idx += 1
    if "description" in payload:
        updates.append(f"description = ${param_idx}")
        values.append(payload["description"].strip() if payload["description"] else None)
        param_idx += 1
    if "required_skills" in payload:
        updates.append(f"required_skills = ${param_idx}::jsonb")
        values.append(json.dumps(_normalize_string_list(payload["required_skills"])))
        param_idx += 1
    if "preferred_skills" in payload:
        updates.append(f"preferred_skills = ${param_idx}::jsonb")
        values.append(json.dumps(_normalize_string_list(payload["preferred_skills"])))
        param_idx += 1
    if "duration_weeks" in payload:
        updates.append(f"duration_weeks = ${param_idx}")
        values.append(payload["duration_weeks"])
        param_idx += 1
    if "status" in payload:
        updates.append(f"status = ${param_idx}")
        values.append(payload["status"])
        param_idx += 1

    updates.append("updated_at = NOW()")
    values.extend([opportunity_id, org_id])

    async with get_connection() as conn:
        row = await conn.fetchrow(
            f"""
            UPDATE internal_opportunities
            SET {", ".join(updates)}
            WHERE id = ${param_idx} AND org_id = ${param_idx + 1}
            RETURNING id, org_id, type, position_id, title, department, description,
                      required_skills, preferred_skills, duration_weeks, status, created_by,
                      created_at, updated_at
            """,
            *values,
        )

    if not row:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Opportunity not found")
    return _row_to_opportunity(row)


@router.get("/applications", response_model=list[InternalMobilityApplicationAdminResponse])
async def list_internal_mobility_applications(
    status_filter: Optional[str] = Query(None, alias="status"),
    current_user: CurrentUser = Depends(require_admin_or_client),
    org_id: Optional[UUID] = Depends(get_client_company_id),
):
    _ = current_user
    if not org_id:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Company not found")
    if status_filter and status_filter not in {"new", "in_review", "shortlisted", "aligned", "closed"}:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Invalid status filter")

    query = """
        SELECT
            ia.id,
            ia.employee_id,
            (e.first_name || ' ' || e.last_name) AS employee_name,
            e.email AS employee_email,
            ia.opportunity_id,
            io.title AS opportunity_title,
            io.type AS opportunity_type,
            ia.status,
            ia.employee_notes,
            ia.submitted_at,
            ia.reviewed_by,
            ia.reviewed_at,
            ia.manager_notified_at,
            ia.created_at,
            ia.updated_at
        FROM internal_opportunity_applications ia
        JOIN internal_opportunities io ON io.id = ia.opportunity_id
        JOIN employees e ON e.id = ia.employee_id
        WHERE io.org_id = $1
    """
    params: list[Any] = [org_id]
    if status_filter:
        query += " AND ia.status = $2"
        params.append(status_filter)
    query += " ORDER BY ia.submitted_at DESC"

    async with get_connection() as conn:
        rows = await conn.fetch(query, *params)
    return [_row_to_application(row) for row in rows]


@router.patch("/applications/{application_id}", response_model=InternalMobilityApplicationAdminResponse)
async def update_internal_mobility_application(
    application_id: UUID,
    request: InternalMobilityApplicationUpdateRequest,
    current_user: CurrentUser = Depends(require_admin_or_client),
    org_id: Optional[UUID] = Depends(get_client_company_id),
):
    if not org_id:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Company not found")

    payload = request.model_dump(exclude_unset=True)
    if not payload:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="No fields to update")

    updates: list[str] = []
    values: list[Any] = []
    param_idx = 1

    if "status" in payload:
        updates.append(f"status = ${param_idx}")
        values.append(payload["status"])
        param_idx += 1
        updates.append(f"reviewed_by = ${param_idx}")
        values.append(current_user.id)
        param_idx += 1
        updates.append("reviewed_at = NOW()")

    if "manager_notified" in payload:
        if payload["manager_notified"]:
            updates.append("manager_notified_at = NOW()")
        else:
            updates.append("manager_notified_at = NULL")

    updates.append("updated_at = NOW()")
    values.extend([application_id, org_id])

    async with get_connection() as conn:
        updated = await conn.fetchval(
            f"""
            UPDATE internal_opportunity_applications ia
            SET {", ".join(updates)}
            FROM internal_opportunities io
            WHERE ia.id = ${param_idx}
              AND ia.opportunity_id = io.id
              AND io.org_id = ${param_idx + 1}
            RETURNING ia.id
            """,
            *values,
        )

        if not updated:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Application not found")

        row = await conn.fetchrow(
            """
            SELECT
                ia.id,
                ia.employee_id,
                (e.first_name || ' ' || e.last_name) AS employee_name,
                e.email AS employee_email,
                ia.opportunity_id,
                io.title AS opportunity_title,
                io.type AS opportunity_type,
                ia.status,
                ia.employee_notes,
                ia.submitted_at,
                ia.reviewed_by,
                ia.reviewed_at,
                ia.manager_notified_at,
                ia.created_at,
                ia.updated_at
            FROM internal_opportunity_applications ia
            JOIN internal_opportunities io ON io.id = ia.opportunity_id
            JOIN employees e ON e.id = ia.employee_id
            WHERE ia.id = $1 AND io.org_id = $2
            """,
            application_id,
            org_id,
        )

    if not row:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Application not found")
    return _row_to_application(row)
