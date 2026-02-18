"""
Celery task for AI-powered resume screening against project requirements.

Compares a candidate's resume text against project requirements and description
using Gemini, producing a score and recommendation for admin review.
"""

import asyncio
import json
from typing import Optional

from ..celery_app import celery_app
from ..notifications import publish_task_complete, publish_task_error
from ..utils import get_db_connection

RESUME_SCREENING_PROMPT = """You are an expert recruiter evaluating a job application.

Compare this candidate's resume against the job requirements and provide a structured assessment.

JOB REQUIREMENTS:
{requirements}

JOB DESCRIPTION:
{description}

CANDIDATE RESUME:
{resume_text}

Evaluate fit on these dimensions:
1. Required skills/experience match
2. Years of experience alignment
3. Education and background relevance
4. Overall role fit

Return ONLY a JSON object with this exact structure:
{{
    "score": <integer 0-100>,
    "recommendation": "recommended" or "review_required" or "not_recommended",
    "notes": "<concise 1-2 sentence explanation of the recommendation, max 200 chars>",
    "key_strengths": ["up to 3 brief strengths"],
    "gaps": ["up to 3 brief gaps or concerns"]
}}

Scoring guide:
- 75-100: recommended (strong match, advance to interview)
- 50-74: review_required (partial match, admin should review)
- 0-49: not_recommended (significant gaps)

Return ONLY the JSON object, no other text."""


async def _screen_resume(
    project_id: str,
    application_id: str,
    candidate_id: str,
    resume_text: str,
    requirements: Optional[str],
    description: Optional[str],
) -> dict:
    """Run AI resume screening and update the application record."""
    from app.config import load_settings
    from google import genai

    settings = load_settings()

    # Mark as screening in progress
    conn = await get_db_connection()
    try:
        await conn.execute(
            "UPDATE project_applications SET status = 'ai_screening', updated_at = NOW() WHERE id = $1",
            application_id,
        )
    finally:
        await conn.close()

    # Build Gemini client
    if settings.vertex_project:
        client = genai.Client(
            vertexai=True,
            project=settings.vertex_project,
            location=settings.vertex_location or "us-central1",
        )
    elif settings.gemini_api_key:
        client = genai.Client(api_key=settings.gemini_api_key)
    else:
        raise ValueError("No Gemini API key or Vertex project configured")

    prompt = RESUME_SCREENING_PROMPT.format(
        requirements=requirements or "Not specified",
        description=description or "Not specified",
        resume_text=resume_text[:8000],  # Truncate for token safety
    )

    response = await client.aio.models.generate_content(
        model=settings.analysis_model,
        contents=prompt,
    )

    # Parse JSON from response
    text = response.text.strip()
    if text.startswith("```json"):
        text = text[7:]
    if text.startswith("```"):
        text = text[3:]
    if text.endswith("```"):
        text = text[:-3]
    text = text.strip()

    try:
        result = json.loads(text)
    except json.JSONDecodeError as e:
        print(f"[ResumeScreening] Failed to parse JSON for application {application_id}: {e}")
        result = {
            "score": 50,
            "recommendation": "review_required",
            "notes": "AI screening could not be completed. Please review manually.",
            "key_strengths": [],
            "gaps": [],
        }

    score = result.get("score", 50)
    recommendation = result.get("recommendation", "review_required")
    notes = result.get("notes", "")

    # Validate recommendation value
    if recommendation not in ("recommended", "review_required", "not_recommended"):
        recommendation = "review_required"

    # Map recommendation to status
    status_map = {
        "recommended": "recommended",
        "review_required": "review_required",
        "not_recommended": "not_recommended",
    }
    new_status = status_map[recommendation]

    # Update application with results
    conn = await get_db_connection()
    try:
        await conn.execute(
            """
            UPDATE project_applications
            SET status = $1, ai_score = $2, ai_recommendation = $3, ai_notes = $4, updated_at = NOW()
            WHERE id = $5
            """,
            new_status,
            float(score),
            recommendation,
            notes,
            application_id,
        )
        print(f"[ResumeScreening] Application {application_id}: {recommendation} (score: {score})")
    finally:
        await conn.close()

    return {
        "application_id": application_id,
        "candidate_id": candidate_id,
        "score": score,
        "recommendation": recommendation,
        "notes": notes,
    }


@celery_app.task(bind=True, max_retries=3)
def screen_resume_async(
    self,
    project_id: str,
    application_id: str,
    candidate_id: str,
    resume_text: str,
    requirements: Optional[str] = None,
    description: Optional[str] = None,
):
    """
    Screen a resume against project requirements using Gemini AI.

    Called immediately after a public application is submitted.
    Updates project_applications with score and recommendation.
    Notifies frontend via Redis pub/sub on completion.
    """
    print(f"[ResumeScreening] Screening application {application_id} for project {project_id}")

    try:
        result = asyncio.run(
            _screen_resume(
                project_id=project_id,
                application_id=application_id,
                candidate_id=candidate_id,
                resume_text=resume_text,
                requirements=requirements,
                description=description,
            )
        )

        publish_task_complete(
            channel=f"project:{project_id}",
            task_type="resume_screening",
            entity_id=application_id,
            result=result,
        )

        print(f"[ResumeScreening] Completed screening for application {application_id}")
        return {"status": "success", **result}

    except Exception as e:
        print(f"[ResumeScreening] Failed to screen application {application_id}: {e}")

        publish_task_error(
            channel=f"project:{project_id}",
            task_type="resume_screening",
            entity_id=application_id,
            error=str(e),
        )

        raise self.retry(exc=e, countdown=60 * (self.request.retries + 1))
