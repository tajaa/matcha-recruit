"""Risk Assessment API Route.

Returns a live-computed risk score and breakdown across 5 dimensions
for the authenticated company.
"""

import logging
from datetime import date, datetime
from typing import Any, Optional
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Path, Query, status
from pydantic import BaseModel

from ...config import get_settings
from ...database import get_connection
from ..dependencies import require_admin_or_client, get_client_company_id
from ..services.risk_assessment_service import compute_risk_assessment, generate_recommendations

logger = logging.getLogger(__name__)

router = APIRouter()


class DimensionResultResponse(BaseModel):
    score: int
    band: str
    factors: list[str]
    raw_data: dict[str, Any]


class RecommendationResponse(BaseModel):
    dimension: str
    priority: str
    title: str
    guidance: str


class RiskAssessmentResponse(BaseModel):
    overall_score: int
    overall_band: str
    dimensions: dict[str, DimensionResultResponse]
    computed_at: datetime
    report: str | None = None
    recommendations: list[RecommendationResponse] | None = None


@router.get("", response_model=RiskAssessmentResponse)
async def get_risk_assessment(
    current_user=Depends(require_admin_or_client),
    include_recommendations: bool = Query(False),
):
    """Return live-computed risk assessment for the company."""
    company_id = await get_client_company_id(current_user)
    if company_id is None:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="No company associated with this account",
        )

    result = await compute_risk_assessment(company_id)

    report = None
    recommendations = None
    if include_recommendations and current_user.role == "admin":
        settings = get_settings()
        consultation = await generate_recommendations(result, settings)
        report = consultation.get("report")
        recs = consultation.get("recommendations", [])
        if recs:
            recommendations = [RecommendationResponse(**r) for r in recs]

    return RiskAssessmentResponse(
        overall_score=result.overall_score,
        overall_band=result.overall_band,
        dimensions={
            key: DimensionResultResponse(
                score=dim.score,
                band=dim.band,
                factors=dim.factors,
                raw_data=dim.raw_data,
            )
            for key, dim in result.dimensions.items()
        },
        computed_at=result.computed_at,
        report=report,
        recommendations=recommendations,
    )


# ---------------------------------------------------------------------------
# Action Items CRUD
# ---------------------------------------------------------------------------

class ActionItemCreate(BaseModel):
    title: str
    description: str | None = None
    source_type: str
    source_ref: str | None = None
    assigned_to: UUID | None = None
    due_date: date | None = None


class ActionItemUpdate(BaseModel):
    assigned_to: UUID | None = None
    due_date: date | None = None
    status: str | None = None


class ActionItemResponse(BaseModel):
    id: UUID
    title: str
    description: str | None = None
    source_type: str
    source_ref: str | None = None
    assigned_to: UUID | None = None
    assigned_to_name: str | None = None
    due_date: date | None = None
    status: str
    created_by: UUID | None = None
    created_at: datetime | None = None
    closed_at: datetime | None = None


class AssignableUserResponse(BaseModel):
    id: UUID
    name: str
    email: str


@router.get("/action-items", response_model=list[ActionItemResponse])
async def list_action_items(
    current_user=Depends(require_admin_or_client),
    item_status: str = Query("open", alias="status"),
):
    company_id = await get_client_company_id(current_user)
    if company_id is None:
        raise HTTPException(status_code=403, detail="No company associated")

    async with get_connection() as conn:
        if item_status == "all":
            rows = await conn.fetch(
                """
                SELECT r.*, u.email AS assigned_email,
                       COALESCE(c.name, u.email) AS assigned_to_name
                FROM risk_action_items r
                LEFT JOIN users u ON u.id = r.assigned_to
                LEFT JOIN candidates c ON c.user_id = u.id
                WHERE r.company_id = $1
                ORDER BY r.created_at DESC
                """,
                company_id,
            )
        else:
            rows = await conn.fetch(
                """
                SELECT r.*, u.email AS assigned_email,
                       COALESCE(c.name, u.email) AS assigned_to_name
                FROM risk_action_items r
                LEFT JOIN users u ON u.id = r.assigned_to
                LEFT JOIN candidates c ON c.user_id = u.id
                WHERE r.company_id = $1 AND r.status = $2
                ORDER BY r.created_at DESC
                """,
                company_id,
                item_status,
            )

    return [
        ActionItemResponse(
            id=row["id"],
            title=row["title"],
            description=row["description"],
            source_type=row["source_type"],
            source_ref=row["source_ref"],
            assigned_to=row["assigned_to"],
            assigned_to_name=row["assigned_to_name"],
            due_date=row["due_date"],
            status=row["status"],
            created_by=row["created_by"],
            created_at=row["created_at"],
            closed_at=row["closed_at"],
        )
        for row in rows
    ]


@router.post("/action-items", response_model=ActionItemResponse, status_code=201)
async def create_action_item(
    body: ActionItemCreate,
    current_user=Depends(require_admin_or_client),
):
    company_id = await get_client_company_id(current_user)
    if company_id is None:
        raise HTTPException(status_code=403, detail="No company associated")

    if body.source_type not in ("wage_violation", "er_case"):
        raise HTTPException(status_code=422, detail="Invalid source_type")

    async with get_connection() as conn:
        row = await conn.fetchrow(
            """
            INSERT INTO risk_action_items
                (company_id, source_type, source_ref, title, description,
                 assigned_to, due_date, status, created_by)
            VALUES ($1, $2, $3, $4, $5, $6, $7, 'open', $8)
            RETURNING *
            """,
            company_id,
            body.source_type,
            body.source_ref,
            body.title,
            body.description,
            body.assigned_to,
            body.due_date,
            current_user.id,
        )

        assigned_to_name = None
        if row["assigned_to"]:
            name_row = await conn.fetchrow(
                "SELECT COALESCE(c.name, u.email) AS name "
                "FROM users u LEFT JOIN candidates c ON c.user_id = u.id "
                "WHERE u.id = $1",
                row["assigned_to"],
            )
            if name_row:
                assigned_to_name = name_row["name"]

    return ActionItemResponse(
        id=row["id"],
        title=row["title"],
        description=row["description"],
        source_type=row["source_type"],
        source_ref=row["source_ref"],
        assigned_to=row["assigned_to"],
        assigned_to_name=assigned_to_name,
        due_date=row["due_date"],
        status=row["status"],
        created_by=row["created_by"],
        created_at=row["created_at"],
        closed_at=row["closed_at"],
    )


@router.put("/action-items/{item_id}", response_model=ActionItemResponse)
async def update_action_item(
    item_id: UUID = Path(...),
    body: ActionItemUpdate = ...,
    current_user=Depends(require_admin_or_client),
):
    company_id = await get_client_company_id(current_user)
    if company_id is None:
        raise HTTPException(status_code=403, detail="No company associated")

    if body.status and body.status not in ("open", "completed"):
        raise HTTPException(status_code=422, detail="Invalid status")

    async with get_connection() as conn:
        existing = await conn.fetchrow(
            "SELECT id FROM risk_action_items WHERE id = $1 AND company_id = $2",
            item_id,
            company_id,
        )
        if not existing:
            raise HTTPException(status_code=404, detail="Action item not found")

        sets = ["updated_at = NOW()"]
        params: list[Any] = []
        idx = 1

        if body.assigned_to is not None:
            idx += 1
            sets.append(f"assigned_to = ${idx}")
            params.append(body.assigned_to)

        if body.due_date is not None:
            idx += 1
            sets.append(f"due_date = ${idx}")
            params.append(body.due_date)

        if body.status is not None:
            idx += 1
            sets.append(f"status = ${idx}")
            params.append(body.status)
            if body.status == "completed":
                sets.append("closed_at = NOW()")
            else:
                sets.append("closed_at = NULL")

        row = await conn.fetchrow(
            f"UPDATE risk_action_items SET {', '.join(sets)} "
            f"WHERE id = $1 RETURNING *",
            item_id,
            *params,
        )

        assigned_to_name = None
        if row["assigned_to"]:
            name_row = await conn.fetchrow(
                "SELECT COALESCE(c.name, u.email) AS name "
                "FROM users u LEFT JOIN candidates c ON c.user_id = u.id "
                "WHERE u.id = $1",
                row["assigned_to"],
            )
            if name_row:
                assigned_to_name = name_row["name"]

    return ActionItemResponse(
        id=row["id"],
        title=row["title"],
        description=row["description"],
        source_type=row["source_type"],
        source_ref=row["source_ref"],
        assigned_to=row["assigned_to"],
        assigned_to_name=assigned_to_name,
        due_date=row["due_date"],
        status=row["status"],
        created_by=row["created_by"],
        created_at=row["created_at"],
        closed_at=row["closed_at"],
    )


@router.get("/assignable-users", response_model=list[AssignableUserResponse])
async def get_assignable_users(
    current_user=Depends(require_admin_or_client),
):
    company_id = await get_client_company_id(current_user)
    if company_id is None:
        raise HTTPException(status_code=403, detail="No company associated")

    async with get_connection() as conn:
        rows = await conn.fetch(
            """
            SELECT u.id, u.email, COALESCE(c.name, u.email) AS name
            FROM users u
            LEFT JOIN candidates c ON c.user_id = u.id
            WHERE u.role IN ('admin', 'client')
              AND u.is_active = true
              AND (
                u.role = 'admin'
                OR EXISTS (
                    SELECT 1 FROM companies comp
                    WHERE comp.id = $1 AND comp.user_id = u.id
                )
              )
            ORDER BY name
            """,
            company_id,
        )

    return [
        AssignableUserResponse(id=row["id"], name=row["name"], email=row["email"])
        for row in rows
    ]
