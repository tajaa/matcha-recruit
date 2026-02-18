import json
from uuid import UUID

from fastapi import APIRouter, HTTPException

from ...database import get_connection
from ..models.ranking import RankingRequest, RankedCandidateResponse
from ..services.ranking_service import RankingService
from ...config import get_settings

router = APIRouter()


def _parse(value):
    if value is None:
        return None
    if isinstance(value, str):
        return json.loads(value)
    return value


@router.post("/companies/{company_id}/rankings/run")
async def run_ranking(company_id: UUID, request: RankingRequest = None):
    """Run multi-signal ranking for a company's candidates."""
    settings = get_settings()
    service = RankingService(
        api_key=settings.gemini_api_key,
        vertex_project=settings.vertex_project,
        vertex_location=settings.vertex_location,
        model=settings.analysis_model,
    )

    async with get_connection() as conn:
        profile_exists = await conn.fetchval(
            "SELECT EXISTS(SELECT 1 FROM culture_profiles WHERE company_id = $1)",
            company_id,
        )
        if not profile_exists:
            raise HTTPException(
                status_code=400,
                detail="Company has no culture profile. Complete culture interviews and aggregate first.",
            )

    candidate_ids = request.candidate_ids if request else None

    try:
        results = await service.run_ranking(company_id, candidate_ids)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))

    return {
        "status": "completed",
        "count": len(results),
        "rankings": [
            RankedCandidateResponse(
                id=r["id"],
                company_id=r["company_id"],
                candidate_id=r["candidate_id"],
                candidate_name=r["candidate_name"],
                overall_rank_score=r["overall_rank_score"],
                screening_score=r["screening_score"],
                conversation_score=r["conversation_score"],
                culture_alignment_score=r["culture_alignment_score"],
                has_interview_data=r["has_interview_data"],
                signal_breakdown=r["signal_breakdown"],
                interview_ids=r["interview_ids"],
                created_at=r["created_at"],
            )
            for r in results
        ],
    }


@router.get("/companies/{company_id}/rankings", response_model=list[RankedCandidateResponse])
async def get_rankings(company_id: UUID):
    """Get stored ranked results for a company, sorted by score descending."""
    async with get_connection() as conn:
        rows = await conn.fetch(
            """
            SELECT r.id, r.company_id, r.candidate_id, r.overall_rank_score,
                   r.screening_score, r.conversation_score, r.culture_alignment_score,
                   r.signal_breakdown, r.has_interview_data, r.interview_ids, r.created_at,
                   c.name as candidate_name
            FROM ranked_results r
            JOIN candidates c ON r.candidate_id = c.id
            WHERE r.company_id = $1
            ORDER BY r.overall_rank_score DESC
            """,
            company_id,
        )

        results = []
        for row in rows:
            interview_ids_raw = _parse(row["interview_ids"])
            results.append(RankedCandidateResponse(
                id=row["id"],
                company_id=row["company_id"],
                candidate_id=row["candidate_id"],
                candidate_name=row["candidate_name"],
                overall_rank_score=row["overall_rank_score"] or 0.0,
                screening_score=row["screening_score"],
                conversation_score=row["conversation_score"],
                culture_alignment_score=row["culture_alignment_score"],
                has_interview_data=row["has_interview_data"],
                signal_breakdown=_parse(row["signal_breakdown"]),
                interview_ids=interview_ids_raw if isinstance(interview_ids_raw, list) else [],
                created_at=row["created_at"],
            ))

        return results
