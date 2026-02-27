"""Risk Assessment API Route.

Returns a live-computed risk score and breakdown across 5 dimensions
for the authenticated company.
"""

import logging
from datetime import datetime
from typing import Any, Optional

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel

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
    action: str


class RiskAssessmentResponse(BaseModel):
    overall_score: int
    overall_band: str
    dimensions: dict[str, DimensionResultResponse]
    computed_at: datetime
    recommendations: list[RecommendationResponse] | None = None


@router.get("", response_model=RiskAssessmentResponse)
async def get_risk_assessment(
    current_user=Depends(require_admin_or_client),
):
    """Return live-computed risk assessment for the company."""
    company_id = await get_client_company_id(current_user)
    if company_id is None:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="No company associated with this account",
        )

    result = await compute_risk_assessment(company_id)

    recommendations = None
    if current_user.role == "admin":
        recommendations = [
            RecommendationResponse(**r) for r in generate_recommendations(result)
        ]

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
        recommendations=recommendations,
    )
