import json
from typing import Optional
from uuid import UUID

from fastapi import APIRouter, HTTPException

from ..database import get_connection
from ..models.matching import MatchRequest, MatchResultResponse
from ..services.candidate_matcher import CandidateMatcher
from ..config import get_settings

router = APIRouter()


@router.post("/companies/{company_id}/match")
async def run_matching(company_id: UUID, request: MatchRequest = None):
    """Run matching for a company against candidates."""
    settings = get_settings()
    matcher = CandidateMatcher(
        api_key=settings.gemini_api_key,
        vertex_project=settings.vertex_project,
        vertex_location=settings.vertex_location,
        model=settings.analysis_model,
    )

    async with get_connection() as conn:
        # Get company culture profile
        profile_row = await conn.fetchrow(
            "SELECT profile_data FROM culture_profiles WHERE company_id = $1",
            company_id,
        )
        if not profile_row:
            raise HTTPException(
                status_code=400,
                detail="Company has no culture profile. Complete interviews and aggregate first.",
            )

        culture_profile = json.loads(profile_row["profile_data"]) if isinstance(profile_row["profile_data"], str) else profile_row["profile_data"]

        # Get candidates to match
        if request and request.candidate_ids:
            # Match specific candidates
            placeholders = ", ".join(f"${i+1}" for i in range(len(request.candidate_ids)))
            candidates = await conn.fetch(
                f"SELECT id, name, parsed_data FROM candidates WHERE id IN ({placeholders})",
                *request.candidate_ids,
            )
        else:
            # Match all candidates
            candidates = await conn.fetch(
                "SELECT id, name, parsed_data FROM candidates"
            )

        if not candidates:
            raise HTTPException(status_code=400, detail="No candidates to match")

        results = []
        for candidate in candidates:
            candidate_id = candidate["id"]
            candidate_name = candidate["name"]
            parsed_data = json.loads(candidate["parsed_data"]) if candidate["parsed_data"] else {}

            # Run matching
            match_result = await matcher.match_candidate(culture_profile, parsed_data)

            match_score = match_result.get("match_score", 50)
            match_reasoning = match_result.get("match_reasoning", "")
            culture_fit_breakdown = match_result.get("culture_fit_breakdown", {})

            # Upsert match result
            row = await conn.fetchrow(
                """
                INSERT INTO match_results (company_id, candidate_id, match_score, match_reasoning, culture_fit_breakdown)
                VALUES ($1, $2, $3, $4, $5)
                ON CONFLICT (company_id, candidate_id)
                DO UPDATE SET match_score = $3, match_reasoning = $4, culture_fit_breakdown = $5, created_at = NOW()
                RETURNING id, created_at
                """,
                company_id,
                candidate_id,
                match_score,
                match_reasoning,
                json.dumps(culture_fit_breakdown),
            )

            results.append(MatchResultResponse(
                id=row["id"],
                company_id=company_id,
                candidate_id=candidate_id,
                candidate_name=candidate_name,
                match_score=match_score,
                match_reasoning=match_reasoning,
                culture_fit_breakdown=culture_fit_breakdown,
                created_at=row["created_at"],
            ))

        # Sort by match score descending
        results.sort(key=lambda x: x.match_score, reverse=True)

        return {"status": "completed", "matches": results}


@router.get("/companies/{company_id}/matches", response_model=list[MatchResultResponse])
async def get_matches(company_id: UUID):
    """Get match results for a company."""
    async with get_connection() as conn:
        rows = await conn.fetch(
            """
            SELECT m.id, m.company_id, m.candidate_id, m.match_score, m.match_reasoning,
                   m.culture_fit_breakdown, m.created_at, c.name as candidate_name
            FROM match_results m
            JOIN candidates c ON m.candidate_id = c.id
            WHERE m.company_id = $1
            ORDER BY m.match_score DESC
            """,
            company_id,
        )

        results = []
        for row in rows:
            culture_fit = json.loads(row["culture_fit_breakdown"]) if row["culture_fit_breakdown"] else {}
            results.append(MatchResultResponse(
                id=row["id"],
                company_id=row["company_id"],
                candidate_id=row["candidate_id"],
                candidate_name=row["candidate_name"],
                match_score=row["match_score"],
                match_reasoning=row["match_reasoning"],
                culture_fit_breakdown=culture_fit,
                created_at=row["created_at"],
            ))

        return results
