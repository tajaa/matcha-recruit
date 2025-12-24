"""
Celery tasks for interview analysis.

These tasks are queued after a WebSocket interview ends, allowing the server
to return immediately while analysis runs in the background.
"""

import asyncio
import json
from typing import Any, Optional

from ..celery_app import celery_app
from ..notifications import publish_task_complete, publish_task_error
from ..utils import get_db_connection


async def _analyze_interview(
    interview_id: str,
    interview_type: str,
    transcript: str,
    company_id: str,
    culture_profile: Optional[dict[str, Any]] = None,
) -> dict[str, Any]:
    """Run interview analysis and save results to database."""
    from app.services.culture_analyzer import CultureAnalyzer
    from app.services.conversation_analyzer import ConversationAnalyzer
    from app.config import load_settings

    settings = load_settings()

    culture_data = None
    conversation_analysis_data = None
    screening_analysis_data = None

    # Initialize analyzers
    conv_analyzer = ConversationAnalyzer(
        api_key=settings.gemini_api_key,
        vertex_project=settings.vertex_project,
        vertex_location=settings.vertex_location,
        model=settings.analysis_model,
    )

    culture_analyzer = CultureAnalyzer(
        api_key=settings.gemini_api_key,
        vertex_project=settings.vertex_project,
        vertex_location=settings.vertex_location,
        model=settings.analysis_model,
    )

    if interview_type == "screening":
        # Screening interviews: generate screening analysis
        screening_analysis_data = await conv_analyzer.analyze_screening_interview(
            transcript=transcript,
        )
    else:
        # Culture/candidate interviews: extract culture data and generate conversation analysis
        culture_data = await culture_analyzer.extract_culture_from_transcript(transcript)
        conversation_analysis_data = await conv_analyzer.analyze_interview(
            transcript=transcript,
            interview_type=interview_type,
            culture_profile=culture_profile,
        )

    # Save results to database
    conn = await get_db_connection()
    try:
        await conn.execute(
            """
            UPDATE interviews
            SET raw_culture_data = $1, conversation_analysis = $2,
                screening_analysis = $3, status = 'completed'
            WHERE id = $4
            """,
            json.dumps(culture_data) if culture_data else None,
            json.dumps(conversation_analysis_data) if conversation_analysis_data else None,
            json.dumps(screening_analysis_data) if screening_analysis_data else None,
            interview_id,
        )

        # If this was a screening interview from outreach, update the outreach status
        if interview_type == "screening" and screening_analysis_data:
            outreach = await conn.fetchrow(
                "SELECT id, project_id, candidate_id FROM project_outreach WHERE interview_id = $1",
                interview_id,
            )
            if outreach:
                overall_score = screening_analysis_data.get("overall_score", 0)
                recommendation = screening_analysis_data.get("recommendation", "fail")

                # Update outreach record
                await conn.execute(
                    """
                    UPDATE project_outreach
                    SET status = 'screening_complete', screening_score = $1, screening_recommendation = $2
                    WHERE id = $3
                    """,
                    overall_score,
                    recommendation,
                    outreach["id"],
                )

                # Update candidate stage in project based on recommendation
                new_stage = "initial"
                notes_addition = f"Screening score: {overall_score:.0f}% - {recommendation}"

                if recommendation == "strong_pass":
                    new_stage = "interview"
                    notes_addition += " - Advanced to interview round"
                elif recommendation == "pass":
                    new_stage = "screening"
                    notes_addition += " - Passed initial screening"
                elif recommendation == "borderline":
                    new_stage = "initial"
                    notes_addition += " - Needs review"
                else:  # fail
                    new_stage = "rejected"
                    notes_addition += " - Did not pass screening"

                await conn.execute(
                    """
                    UPDATE project_candidates
                    SET stage = $1, notes = COALESCE(notes, '') || E'\\n' || $2, updated_at = NOW()
                    WHERE project_id = $3 AND candidate_id = $4
                    """,
                    new_stage,
                    notes_addition,
                    outreach["project_id"],
                    outreach["candidate_id"],
                )
                print(f"[Worker] Interview {interview_id} outreach screening complete: {recommendation} -> stage {new_stage}")

    finally:
        await conn.close()

    return {
        "interview_id": interview_id,
        "interview_type": interview_type,
        "has_culture_data": culture_data is not None,
        "has_conversation_analysis": conversation_analysis_data is not None,
        "has_screening_analysis": screening_analysis_data is not None,
        "screening_recommendation": screening_analysis_data.get("recommendation") if screening_analysis_data else None,
    }


@celery_app.task(bind=True, max_retries=3)
def analyze_interview_async(
    self,
    interview_id: str,
    interview_type: str,
    transcript: str,
    company_id: str,
    culture_profile: Optional[dict[str, Any]] = None,
) -> dict[str, Any]:
    """
    Analyze interview transcript in background.

    This task is queued after a WebSocket interview session ends.
    It runs analysis and updates the database, then notifies the frontend.

    Args:
        interview_id: UUID of the interview
        interview_type: "culture", "candidate", or "screening"
        transcript: Full transcript text
        company_id: UUID of the company (for notification channel)
        culture_profile: Optional culture profile for candidate interviews
    """
    print(f"[Worker] Starting analysis for interview {interview_id} (type: {interview_type})")

    try:
        result = asyncio.run(
            _analyze_interview(
                interview_id=interview_id,
                interview_type=interview_type,
                transcript=transcript,
                company_id=company_id,
                culture_profile=culture_profile,
            )
        )

        # Notify frontend via Redis pub/sub
        publish_task_complete(
            channel=f"company:{company_id}",
            task_type="interview_analysis",
            entity_id=interview_id,
            result=result,
        )

        print(f"[Worker] Completed analysis for interview {interview_id}")
        return {"status": "success", **result}

    except Exception as e:
        print(f"[Worker] Failed to analyze interview {interview_id}: {e}")

        # Notify frontend of error
        publish_task_error(
            channel=f"company:{company_id}",
            task_type="interview_analysis",
            entity_id=interview_id,
            error=str(e),
        )

        # Retry with exponential backoff
        raise self.retry(exc=e, countdown=60 * (self.request.retries + 1))
