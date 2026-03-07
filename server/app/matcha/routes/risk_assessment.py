"""Risk Assessment API Route.

Snapshots are computed by the master admin and stored in risk_assessment_snapshots.
Clients read the last stored snapshot — no live computation on page load.
"""

import json
import logging
from dataclasses import asdict
from datetime import date, datetime
from typing import Any, Optional
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Path, Query, status
from pydantic import BaseModel

from ...config import get_settings
from ...core.dependencies import require_admin
from ...database import get_connection
from ..dependencies import require_admin_or_client, get_client_company_id
from ..services.risk_assessment_service import (
    compute_risk_assessment,
    generate_recommendations,
    DEFAULT_WEIGHTS,
)

logger = logging.getLogger(__name__)

router = APIRouter()

_WEIGHT_KEYS = {"compliance", "incidents", "er_cases", "workforce", "legislative"}


# ─── Response models ──────────────────────────────────────────────────────────

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
    weights: dict[str, float]
    report: str | None = None
    recommendations: list[RecommendationResponse] | None = None


class WeightsResponse(BaseModel):
    compliance: float
    incidents: float
    er_cases: float
    workforce: float
    legislative: float


# ─── Helpers ──────────────────────────────────────────────────────────────────

async def _get_weights(conn) -> dict[str, float]:
    row = await conn.fetchval(
        "SELECT value FROM platform_settings WHERE key = 'risk_assessment_weights'"
    )
    if row:
        raw = json.loads(row) if isinstance(row, str) else row
        if isinstance(raw, dict):
            return {**DEFAULT_WEIGHTS, **{k: float(v) for k, v in raw.items() if k in _WEIGHT_KEYS}}
    return dict(DEFAULT_WEIGHTS)


def _snapshot_to_response(row) -> RiskAssessmentResponse:
    dims_raw = row["dimensions"]
    if isinstance(dims_raw, str):
        dims_raw = json.loads(dims_raw)
    weights_raw = row["weights"]
    if isinstance(weights_raw, str):
        weights_raw = json.loads(weights_raw)
    recs_raw = row["recommendations"]
    if isinstance(recs_raw, str):
        recs_raw = json.loads(recs_raw) if recs_raw else None

    recommendations = None
    if recs_raw:
        try:
            recommendations = [RecommendationResponse(**r) for r in recs_raw]
        except Exception:
            pass

    return RiskAssessmentResponse(
        overall_score=row["overall_score"],
        overall_band=row["overall_band"],
        dimensions={
            key: DimensionResultResponse(**dim)
            for key, dim in dims_raw.items()
        },
        computed_at=row["computed_at"],
        weights=weights_raw,
        report=row["report"],
        recommendations=recommendations,
    )


# ─── Client endpoint ──────────────────────────────────────────────────────────

@router.get("", response_model=RiskAssessmentResponse)
async def get_risk_assessment(
    current_user=Depends(require_admin_or_client),
):
    """Return the last stored risk assessment snapshot for the company."""
    company_id = await get_client_company_id(current_user)
    if company_id is None:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="No company associated with this account")

    async with get_connection() as conn:
        row = await conn.fetchrow(
            "SELECT * FROM risk_assessment_snapshots WHERE company_id = $1",
            company_id,
        )

    if not row:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="No risk assessment has been run for this company yet")

    return _snapshot_to_response(row)


# ─── Admin endpoints ──────────────────────────────────────────────────────────

@router.get("/admin/weights", response_model=WeightsResponse)
async def get_weights(current_user=Depends(require_admin)):
    """Return the current dimension weights used for risk scoring."""
    async with get_connection() as conn:
        weights = await _get_weights(conn)
    return WeightsResponse(**weights)


@router.put("/admin/weights", response_model=WeightsResponse)
async def update_weights(
    body: WeightsResponse,
    current_user=Depends(require_admin),
):
    """Update dimension weights. Values should sum to 1.0."""
    weights = body.model_dump()
    total = sum(weights.values())
    if not (0.99 <= total <= 1.01):
        raise HTTPException(status_code=422, detail=f"Weights must sum to 1.0 (got {total:.3f})")

    async with get_connection() as conn:
        await conn.execute(
            """
            INSERT INTO platform_settings (key, value)
            VALUES ('risk_assessment_weights', $1::jsonb)
            ON CONFLICT (key) DO UPDATE SET value = $1::jsonb, updated_at = now()
            """,
            json.dumps(weights),
        )
    return WeightsResponse(**weights)


@router.post("/admin/run/{company_id}", response_model=RiskAssessmentResponse)
async def run_risk_assessment(
    company_id: UUID = Path(...),
    current_user=Depends(require_admin),
):
    """Compute and store a risk assessment snapshot for a company (admin only)."""
    async with get_connection() as conn:
        exists = await conn.fetchval("SELECT id FROM companies WHERE id = $1", company_id)
        if not exists:
            raise HTTPException(status_code=404, detail="Company not found")
        weights = await _get_weights(conn)

    result = await compute_risk_assessment(company_id, weights=weights)

    settings = get_settings()
    consultation = await generate_recommendations(result, settings)
    report = consultation.get("report")
    recs = consultation.get("recommendations", []) or []

    dims_json = json.dumps(
        {key: asdict(dim) for key, dim in result.dimensions.items()},
        default=str,
    )

    async with get_connection() as conn:
        row = await conn.fetchrow(
            """
            INSERT INTO risk_assessment_snapshots
                (company_id, overall_score, overall_band, dimensions, report,
                 recommendations, weights, computed_at, computed_by)
            VALUES ($1, $2, $3, $4::jsonb, $5, $6::jsonb, $7::jsonb, $8, $9)
            ON CONFLICT (company_id) DO UPDATE SET
                overall_score  = EXCLUDED.overall_score,
                overall_band   = EXCLUDED.overall_band,
                dimensions     = EXCLUDED.dimensions,
                report         = EXCLUDED.report,
                recommendations = EXCLUDED.recommendations,
                weights        = EXCLUDED.weights,
                computed_at    = EXCLUDED.computed_at,
                computed_by    = EXCLUDED.computed_by
            RETURNING *
            """,
            company_id,
            result.overall_score,
            result.overall_band,
            dims_json,
            report,
            json.dumps(recs, default=str),
            json.dumps(weights),
            result.computed_at,
            current_user.id,
        )

    return _snapshot_to_response(row)


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
                    WHERE comp.id = $1 AND comp.owner_id = u.id
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
