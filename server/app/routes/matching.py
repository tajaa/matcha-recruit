import json
from typing import Optional
from uuid import UUID

from fastapi import APIRouter, HTTPException

from ..database import get_connection
from ..models.matching import MatchRequest, MatchResultResponse
from ..models.position import PositionMatchResultResponse
from ..services.candidate_matcher import CandidateMatcher
from ..services.position_matcher import PositionMatcher
from ..config import get_settings

router = APIRouter()


def parse_jsonb(value):
    """Parse JSONB value from database."""
    if value is None:
        return None
    if isinstance(value, str):
        return json.loads(value)
    return value


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


@router.post("/positions/{position_id}/match")
async def run_position_matching(position_id: UUID, request: MatchRequest = None):
    """Run matching for a position against candidates."""
    settings = get_settings()
    matcher = PositionMatcher(
        api_key=settings.gemini_api_key,
        vertex_project=settings.vertex_project,
        vertex_location=settings.vertex_location,
        model=settings.analysis_model,
    )

    async with get_connection() as conn:
        # Get position with company info
        position_row = await conn.fetchrow(
            """
            SELECT p.*, c.name as company_name
            FROM positions p
            JOIN companies c ON p.company_id = c.id
            WHERE p.id = $1
            """,
            position_id,
        )
        if not position_row:
            raise HTTPException(status_code=404, detail="Position not found")

        # Get company culture profile (optional)
        profile_row = await conn.fetchrow(
            "SELECT profile_data FROM culture_profiles WHERE company_id = $1",
            position_row["company_id"],
        )
        culture_profile = None
        if profile_row and profile_row["profile_data"]:
            culture_profile = parse_jsonb(profile_row["profile_data"])

        # Prepare position data
        position_data = {
            "title": position_row["title"],
            "department": position_row["department"],
            "location": position_row["location"],
            "remote_policy": position_row["remote_policy"],
            "employment_type": position_row["employment_type"],
            "experience_level": position_row["experience_level"],
            "salary_min": position_row["salary_min"],
            "salary_max": position_row["salary_max"],
            "salary_currency": position_row["salary_currency"],
            "required_skills": parse_jsonb(position_row["required_skills"]),
            "preferred_skills": parse_jsonb(position_row["preferred_skills"]),
            "requirements": parse_jsonb(position_row["requirements"]),
            "responsibilities": parse_jsonb(position_row["responsibilities"]),
            "benefits": parse_jsonb(position_row["benefits"]),
            "visa_sponsorship": position_row["visa_sponsorship"],
        }

        # Get candidates to match
        if request and request.candidate_ids:
            placeholders = ", ".join(f"${i+1}" for i in range(len(request.candidate_ids)))
            candidates = await conn.fetch(
                f"""
                SELECT id, name, skills, experience_years, education, parsed_data
                FROM candidates WHERE id IN ({placeholders})
                """,
                *request.candidate_ids,
            )
        else:
            candidates = await conn.fetch(
                "SELECT id, name, skills, experience_years, education, parsed_data FROM candidates"
            )

        if not candidates:
            raise HTTPException(status_code=400, detail="No candidates to match")

        results = []
        for candidate in candidates:
            candidate_id = candidate["id"]
            candidate_name = candidate["name"]

            # Prepare candidate data
            candidate_data = {
                "name": candidate_name,
                "skills": parse_jsonb(candidate["skills"]),
                "experience_years": candidate["experience_years"],
                "education": parse_jsonb(candidate["education"]),
                "parsed_data": parse_jsonb(candidate["parsed_data"]),
            }

            # Run matching
            match_result = await matcher.match_candidate_to_position(
                position_data, candidate_data, culture_profile
            )

            # Upsert match result
            row = await conn.fetchrow(
                """
                INSERT INTO position_match_results (
                    position_id, candidate_id, overall_score, skills_match_score,
                    experience_match_score, culture_fit_score, match_reasoning,
                    skills_breakdown, experience_breakdown, culture_fit_breakdown
                )
                VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9, $10)
                ON CONFLICT (position_id, candidate_id)
                DO UPDATE SET
                    overall_score = $3, skills_match_score = $4, experience_match_score = $5,
                    culture_fit_score = $6, match_reasoning = $7, skills_breakdown = $8,
                    experience_breakdown = $9, culture_fit_breakdown = $10, created_at = NOW()
                RETURNING id, created_at
                """,
                position_id,
                candidate_id,
                match_result.get("overall_score", 50),
                match_result.get("skills_match_score", 50),
                match_result.get("experience_match_score", 50),
                match_result.get("culture_fit_score", 70),
                match_result.get("match_reasoning", ""),
                json.dumps(match_result.get("skills_breakdown")) if match_result.get("skills_breakdown") else None,
                json.dumps(match_result.get("experience_breakdown")) if match_result.get("experience_breakdown") else None,
                json.dumps(match_result.get("culture_fit_breakdown")) if match_result.get("culture_fit_breakdown") else None,
            )

            results.append(PositionMatchResultResponse(
                id=row["id"],
                position_id=position_id,
                candidate_id=candidate_id,
                candidate_name=candidate_name,
                overall_score=match_result.get("overall_score", 50),
                skills_match_score=match_result.get("skills_match_score", 50),
                experience_match_score=match_result.get("experience_match_score", 50),
                culture_fit_score=match_result.get("culture_fit_score", 70),
                match_reasoning=match_result.get("match_reasoning"),
                skills_breakdown=match_result.get("skills_breakdown"),
                experience_breakdown=match_result.get("experience_breakdown"),
                culture_fit_breakdown=match_result.get("culture_fit_breakdown"),
                created_at=row["created_at"],
            ))

        # Sort by overall score descending
        results.sort(key=lambda x: x.overall_score, reverse=True)

        return {"status": "completed", "matches": results}


@router.get("/positions/{position_id}/matches", response_model=list[PositionMatchResultResponse])
async def get_position_matches(position_id: UUID):
    """Get match results for a position."""
    async with get_connection() as conn:
        # Verify position exists
        position_exists = await conn.fetchval(
            "SELECT EXISTS(SELECT 1 FROM positions WHERE id = $1)",
            position_id,
        )
        if not position_exists:
            raise HTTPException(status_code=404, detail="Position not found")

        rows = await conn.fetch(
            """
            SELECT m.*, c.name as candidate_name
            FROM position_match_results m
            JOIN candidates c ON m.candidate_id = c.id
            WHERE m.position_id = $1
            ORDER BY m.overall_score DESC
            """,
            position_id,
        )

        results = []
        for row in rows:
            results.append(PositionMatchResultResponse(
                id=row["id"],
                position_id=row["position_id"],
                candidate_id=row["candidate_id"],
                candidate_name=row["candidate_name"],
                overall_score=row["overall_score"],
                skills_match_score=row["skills_match_score"],
                experience_match_score=row["experience_match_score"],
                culture_fit_score=row["culture_fit_score"],
                match_reasoning=row["match_reasoning"],
                skills_breakdown=parse_jsonb(row["skills_breakdown"]),
                experience_breakdown=parse_jsonb(row["experience_breakdown"]),
                culture_fit_breakdown=parse_jsonb(row["culture_fit_breakdown"]),
                created_at=row["created_at"],
            ))

        return results
