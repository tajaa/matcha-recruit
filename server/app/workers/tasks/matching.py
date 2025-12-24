"""
Celery tasks for candidate and position matching.

These tasks run O(N) Gemini API calls for matching candidates against
company culture profiles or position requirements.
"""

import asyncio
import json
import os
from typing import Any, Optional

import asyncpg
from dotenv import load_dotenv

from ..celery_app import celery_app
from ..notifications import publish_task_complete, publish_task_error, publish_task_progress

load_dotenv()


async def get_db_connection() -> asyncpg.Connection:
    """Create a database connection for the worker."""
    database_url = os.getenv("DATABASE_URL", "")
    return await asyncpg.connect(database_url)


def parse_jsonb(value: Any) -> Any:
    """Parse JSONB value from database."""
    if value is None:
        return None
    if isinstance(value, str):
        return json.loads(value)
    return value


async def _match_candidates(
    company_id: str,
    candidate_ids: Optional[list[str]] = None,
) -> dict[str, Any]:
    """Run matching for candidates against company culture profile."""
    from app.services.candidate_matcher import CandidateMatcher
    from app.config import load_settings

    settings = load_settings()
    matcher = CandidateMatcher(
        api_key=settings.gemini_api_key,
        vertex_project=settings.vertex_project,
        vertex_location=settings.vertex_location,
        model=settings.analysis_model,
    )

    conn = await get_db_connection()
    try:
        # Get company culture profile
        profile_row = await conn.fetchrow(
            "SELECT profile_data FROM culture_profiles WHERE company_id = $1",
            company_id,
        )
        if not profile_row:
            return {"status": "error", "error": "Company has no culture profile"}

        culture_profile = parse_jsonb(profile_row["profile_data"])

        # Get candidates to match
        if candidate_ids:
            placeholders = ", ".join(f"${i+1}" for i in range(len(candidate_ids)))
            candidates = await conn.fetch(
                f"SELECT id, name, parsed_data FROM candidates WHERE id IN ({placeholders})",
                *candidate_ids,
            )
        else:
            candidates = await conn.fetch(
                "SELECT id, name, parsed_data FROM candidates"
            )

        if not candidates:
            return {"status": "error", "error": "No candidates to match"}

        results = []
        total = len(candidates)

        for i, candidate in enumerate(candidates):
            candidate_id = str(candidate["id"])
            candidate_name = candidate["name"]
            parsed_data = parse_jsonb(candidate["parsed_data"]) or {}

            # Run matching
            match_result = await matcher.match_candidate(culture_profile, parsed_data)

            match_score = match_result.get("match_score", 50)
            match_reasoning = match_result.get("match_reasoning", "")
            culture_fit_breakdown = match_result.get("culture_fit_breakdown", {})

            # Upsert match result
            await conn.execute(
                """
                INSERT INTO match_results (company_id, candidate_id, match_score, match_reasoning, culture_fit_breakdown)
                VALUES ($1, $2, $3, $4, $5)
                ON CONFLICT (company_id, candidate_id)
                DO UPDATE SET match_score = $3, match_reasoning = $4, culture_fit_breakdown = $5, created_at = NOW()
                """,
                company_id,
                candidate_id,
                match_score,
                match_reasoning,
                json.dumps(culture_fit_breakdown),
            )

            results.append({
                "candidate_id": candidate_id,
                "candidate_name": candidate_name,
                "match_score": match_score,
            })

            # Publish progress update
            publish_task_progress(
                channel=f"company:{company_id}",
                task_type="matching",
                entity_id=company_id,
                progress=i + 1,
                total=total,
                message=f"Matched {candidate_name}",
            )

        # Sort by match score descending
        results.sort(key=lambda x: x["match_score"], reverse=True)

        return {"status": "completed", "match_count": len(results), "results": results}

    finally:
        await conn.close()


async def _match_position_candidates(
    position_id: str,
    candidate_ids: Optional[list[str]] = None,
) -> dict[str, Any]:
    """Run matching for candidates against position requirements."""
    from app.services.position_matcher import PositionMatcher
    from app.config import load_settings

    settings = load_settings()
    matcher = PositionMatcher(
        api_key=settings.gemini_api_key,
        vertex_project=settings.vertex_project,
        vertex_location=settings.vertex_location,
        model=settings.analysis_model,
    )

    conn = await get_db_connection()
    try:
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
            return {"status": "error", "error": "Position not found"}

        company_id = str(position_row["company_id"])

        # Get company culture profile (optional)
        profile_row = await conn.fetchrow(
            "SELECT profile_data FROM culture_profiles WHERE company_id = $1",
            position_row["company_id"],
        )
        culture_profile = parse_jsonb(profile_row["profile_data"]) if profile_row else None

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
        if candidate_ids:
            placeholders = ", ".join(f"${i+1}" for i in range(len(candidate_ids)))
            candidates = await conn.fetch(
                f"""
                SELECT id, name, skills, experience_years, education, parsed_data
                FROM candidates WHERE id IN ({placeholders})
                """,
                *candidate_ids,
            )
        else:
            candidates = await conn.fetch(
                "SELECT id, name, skills, experience_years, education, parsed_data FROM candidates"
            )

        if not candidates:
            return {"status": "error", "error": "No candidates to match"}

        results = []
        total = len(candidates)

        for i, candidate in enumerate(candidates):
            candidate_id = str(candidate["id"])
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
            await conn.execute(
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

            results.append({
                "candidate_id": candidate_id,
                "candidate_name": candidate_name,
                "overall_score": match_result.get("overall_score", 50),
            })

            # Publish progress update
            publish_task_progress(
                channel=f"company:{company_id}",
                task_type="position_matching",
                entity_id=position_id,
                progress=i + 1,
                total=total,
                message=f"Matched {candidate_name}",
            )

        # Sort by overall score descending
        results.sort(key=lambda x: x["overall_score"], reverse=True)

        return {"status": "completed", "match_count": len(results), "results": results, "company_id": company_id}

    finally:
        await conn.close()


@celery_app.task(bind=True, max_retries=3)
def match_candidates_async(
    self,
    company_id: str,
    candidate_ids: Optional[list[str]] = None,
) -> dict[str, Any]:
    """
    Match candidates against company culture profile in background.

    This task runs O(N) Gemini API calls, one per candidate.
    Progress updates are published via Redis pub/sub.

    Args:
        company_id: UUID of the company
        candidate_ids: Optional list of candidate UUIDs to match (matches all if not provided)
    """
    print(f"[Worker] Starting candidate matching for company {company_id}")

    try:
        result = asyncio.run(
            _match_candidates(
                company_id=company_id,
                candidate_ids=candidate_ids,
            )
        )

        # Notify frontend via Redis pub/sub
        publish_task_complete(
            channel=f"company:{company_id}",
            task_type="matching",
            entity_id=company_id,
            result={"match_count": result.get("match_count", 0)},
        )

        print(f"[Worker] Completed candidate matching for company {company_id}: {result.get('match_count', 0)} matches")
        return result

    except Exception as e:
        print(f"[Worker] Failed candidate matching for company {company_id}: {e}")

        publish_task_error(
            channel=f"company:{company_id}",
            task_type="matching",
            entity_id=company_id,
            error=str(e),
        )

        raise self.retry(exc=e, countdown=60 * (self.request.retries + 1))


@celery_app.task(bind=True, max_retries=3)
def match_position_candidates_async(
    self,
    position_id: str,
    candidate_ids: Optional[list[str]] = None,
) -> dict[str, Any]:
    """
    Match candidates against position requirements in background.

    This task runs O(N) Gemini API calls, one per candidate.
    Progress updates are published via Redis pub/sub.

    Args:
        position_id: UUID of the position
        candidate_ids: Optional list of candidate UUIDs to match (matches all if not provided)
    """
    print(f"[Worker] Starting position matching for position {position_id}")

    try:
        result = asyncio.run(
            _match_position_candidates(
                position_id=position_id,
                candidate_ids=candidate_ids,
            )
        )

        company_id = result.get("company_id", "unknown")

        # Notify frontend via Redis pub/sub
        publish_task_complete(
            channel=f"company:{company_id}",
            task_type="position_matching",
            entity_id=position_id,
            result={"match_count": result.get("match_count", 0)},
        )

        print(f"[Worker] Completed position matching for position {position_id}: {result.get('match_count', 0)} matches")
        return result

    except Exception as e:
        print(f"[Worker] Failed position matching for position {position_id}: {e}")

        publish_task_error(
            channel=f"company:{position_id}",
            task_type="position_matching",
            entity_id=position_id,
            error=str(e),
        )

        raise self.retry(exc=e, countdown=60 * (self.request.retries + 1))
