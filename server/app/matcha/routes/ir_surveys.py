"""Security Survey routes for IR (Incident Reporting)."""

import json
import logging
from typing import Optional
from uuid import UUID

from fastapi import APIRouter, HTTPException, Depends
from pydantic import BaseModel

from ...database import get_connection
from ..dependencies import require_admin_or_client, get_client_company_id

logger = logging.getLogger(__name__)

router = APIRouter()


class SecuritySurveyCreate(BaseModel):
    location_id: Optional[str] = None
    responses: dict[str, str]  # question_id → 'yes' | 'no' | 'na'
    score: Optional[float] = None
    notes: Optional[str] = None


class SecuritySurveyResponse(BaseModel):
    id: str
    location_id: Optional[str]
    location_name: Optional[str]
    conducted_at: str
    score: Optional[float]
    notes: Optional[str]
    responses: dict[str, str]


@router.post("", response_model=SecuritySurveyResponse)
async def create_survey(
    payload: SecuritySurveyCreate,
    current_user=Depends(require_admin_or_client),
):
    company_id = await get_client_company_id(current_user)
    if company_id is None:
        raise HTTPException(status_code=403, detail="No company")

    # Validate response values
    valid_vals = {"yes", "no", "na"}
    for qid, val in payload.responses.items():
        if val not in valid_vals:
            raise HTTPException(status_code=422, detail=f"Invalid response value '{val}' for question '{qid}'")

    async with get_connection() as conn:
        # Verify location belongs to company if provided
        location_name: Optional[str] = None
        if payload.location_id:
            loc = await conn.fetchrow(
                "SELECT id, name, city, state FROM business_locations WHERE id = $1 AND company_id = $2",
                payload.location_id,
                company_id,
            )
            if not loc:
                raise HTTPException(status_code=404, detail="Location not found")
            parts = [loc["name"], loc["city"], loc["state"]]
            location_name = " — ".join(p for p in parts if p)

        row = await conn.fetchrow(
            """
            INSERT INTO ir_security_surveys
              (company_id, location_id, conducted_by, responses, score, notes)
            VALUES ($1, $2, $3, $4, $5, $6)
            RETURNING id, location_id, conducted_at, score, notes, responses
            """,
            company_id,
            payload.location_id,
            current_user.id,
            json.dumps(payload.responses),
            payload.score,
            payload.notes,
        )

        return SecuritySurveyResponse(
            id=str(row["id"]),
            location_id=str(row["location_id"]) if row["location_id"] else None,
            location_name=location_name,
            conducted_at=row["conducted_at"].isoformat(),
            score=row["score"],
            notes=row["notes"],
            responses=json.loads(row["responses"]) if isinstance(row["responses"], str) else dict(row["responses"]),
        )


@router.get("", response_model=list[SecuritySurveyResponse])
async def list_surveys(
    current_user=Depends(require_admin_or_client),
):
    company_id = await get_client_company_id(current_user)
    if company_id is None:
        return []

    async with get_connection() as conn:
        rows = await conn.fetch(
            """
            SELECT
              s.id,
              s.location_id,
              s.conducted_at,
              s.score,
              s.notes,
              s.responses,
              bl.name AS bl_name,
              bl.city AS bl_city,
              bl.state AS bl_state
            FROM ir_security_surveys s
            LEFT JOIN business_locations bl ON bl.id = s.location_id
            WHERE s.company_id = $1
            ORDER BY s.conducted_at DESC
            LIMIT 100
            """,
            company_id,
        )

        result = []
        for row in rows:
            loc_parts = [row["bl_name"], row["bl_city"], row["bl_state"]]
            location_name = " — ".join(p for p in loc_parts if p) or None
            responses = row["responses"]
            if isinstance(responses, str):
                responses = json.loads(responses)
            else:
                responses = dict(responses)
            result.append(SecuritySurveyResponse(
                id=str(row["id"]),
                location_id=str(row["location_id"]) if row["location_id"] else None,
                location_name=location_name,
                conducted_at=row["conducted_at"].isoformat(),
                score=row["score"],
                notes=row["notes"],
                responses=responses,
            ))
        return result


@router.get("/{survey_id}", response_model=SecuritySurveyResponse)
async def get_survey(
    survey_id: UUID,
    current_user=Depends(require_admin_or_client),
):
    company_id = await get_client_company_id(current_user)
    if company_id is None:
        raise HTTPException(status_code=403, detail="No company")

    async with get_connection() as conn:
        row = await conn.fetchrow(
            """
            SELECT
              s.id,
              s.location_id,
              s.conducted_at,
              s.score,
              s.notes,
              s.responses,
              bl.name AS bl_name,
              bl.city AS bl_city,
              bl.state AS bl_state
            FROM ir_security_surveys s
            LEFT JOIN business_locations bl ON bl.id = s.location_id
            WHERE s.id = $1 AND s.company_id = $2
            """,
            survey_id,
            company_id,
        )
        if not row:
            raise HTTPException(status_code=404, detail="Survey not found")

        loc_parts = [row["bl_name"], row["bl_city"], row["bl_state"]]
        location_name = " — ".join(p for p in loc_parts if p) or None
        responses = row["responses"]
        if isinstance(responses, str):
            responses = json.loads(responses)
        else:
            responses = dict(responses)
        return SecuritySurveyResponse(
            id=str(row["id"]),
            location_id=str(row["location_id"]) if row["location_id"] else None,
            location_name=location_name,
            conducted_at=row["conducted_at"].isoformat(),
            score=row["score"],
            notes=row["notes"],
            responses=responses,
        )
