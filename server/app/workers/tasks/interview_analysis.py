"""
Celery tasks for interview analysis.

These tasks are queued after a WebSocket interview ends, allowing the server
to return immediately while analysis runs in the background.
"""

import asyncio
import json
from typing import Any, Optional
from uuid import UUID as _UUID

from ..celery_app import celery_app
from ..notifications import publish_task_complete, publish_task_error
from ..utils import get_db_connection


async def _analyze_interview(
    interview_id: str,
    interview_type: str,
    transcript: str,
    company_id: Optional[str] = None,
    culture_profile: Optional[dict[str, Any]] = None,
    language: Optional[str] = None,
    incident_id: Optional[str] = None,
) -> dict[str, Any]:
    """Run interview analysis and save results to database."""
    from app.matcha.services.culture_analyzer import CultureAnalyzer
    from app.matcha.services.conversation_analyzer import ConversationAnalyzer
    from app.config import load_settings

    settings = load_settings()

    culture_data = None
    conversation_analysis_data = None
    screening_analysis_data = None
    tutor_analysis_data = None
    investigation_analysis_data = None

    # Initialize analyzers. Always use direct Gemini API — Vertex lacks the
    # preview models (e.g. gemini-3-flash-preview) that analysis_model points at.
    conv_analyzer = ConversationAnalyzer(
        api_key=settings.gemini_api_key,
        model=settings.analysis_model,
    )

    culture_analyzer = CultureAnalyzer(
        api_key=settings.gemini_api_key,
        model=settings.analysis_model,
    )

    if interview_type == "investigation":
        # Investigation interviews: fetch incident data and analyze
        incident_data = None
        if incident_id:
            conn = await get_db_connection()
            try:
                row = await conn.fetchrow(
                    "SELECT title, description, incident_type, severity, location, occurred_at FROM ir_incidents WHERE id = $1",
                    _UUID(incident_id),
                )
                if row:
                    incident_data = {
                        "title": row["title"],
                        "description": row["description"],
                        "incident_type": row["incident_type"],
                        "severity": row["severity"],
                    }
            finally:
                await conn.close()
        investigation_analysis_data = await conv_analyzer.analyze_investigation_interview(
            transcript=transcript,
            incident_data=incident_data,
        )
    elif interview_type == "tutor_interview":
        # Tutor interview prep: analyze for interview skills feedback
        tutor_analysis_data = await conv_analyzer.analyze_tutor_interview(
            transcript=transcript,
        )
    elif interview_type == "tutor_language":
        # Tutor language practice: analyze for language proficiency feedback
        tutor_analysis_data = await conv_analyzer.analyze_tutor_language(
            transcript=transcript,
            language=language or "en",
        )
    elif interview_type == "screening":
        # Screening interviews: generate screening analysis
        screening_analysis_data = await conv_analyzer.analyze_screening_interview(
            transcript=transcript,
        )
    elif interview_type == "culture":
        # Culture interviews: extract culture data and generate conversation analysis
        culture_data = await culture_analyzer.extract_culture_from_transcript(transcript)
        conversation_analysis_data = await conv_analyzer.analyze_interview(
            transcript=transcript,
            interview_type=interview_type,
            culture_profile=culture_profile,
        )
    else:
        # Candidate interviews: generate conversation analysis only
        conversation_analysis_data = await conv_analyzer.analyze_interview(
            transcript=transcript,
            interview_type=interview_type,
            culture_profile=culture_profile,
        )

    # Save results to database
    conn = await get_db_connection()
    try:
        if interview_type == "investigation":
            await conn.execute(
                """
                UPDATE interviews
                SET investigation_analysis = $1, status = 'completed'
                WHERE id = $2
                """,
                json.dumps(investigation_analysis_data) if investigation_analysis_data else None,
                interview_id,
            )
            # Update junction table status
            await conn.execute(
                """
                UPDATE ir_investigation_interviews
                SET status = 'analyzed', completed_at = NOW()
                WHERE interview_id = $1 AND status = 'completed'
                """,
                interview_id,
            )
            # Phase 2: Link to ER case and upload transcript
            if investigation_analysis_data:
                await _link_to_er_case_and_upload_transcript(
                    conn, interview_id, incident_id, transcript, company_id,
                )
        else:
            await conn.execute(
                """
                UPDATE interviews
                SET raw_culture_data = $1, conversation_analysis = $2,
                    screening_analysis = $3, tutor_analysis = $4, status = 'completed'
                WHERE id = $5
                """,
                json.dumps(culture_data) if culture_data else None,
                json.dumps(conversation_analysis_data) if conversation_analysis_data else None,
                json.dumps(screening_analysis_data) if screening_analysis_data else None,
                json.dumps(tutor_analysis_data) if tutor_analysis_data else None,
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
        "has_tutor_analysis": tutor_analysis_data is not None,
        "has_investigation_analysis": investigation_analysis_data is not None,
        "screening_recommendation": screening_analysis_data.get("recommendation") if screening_analysis_data else None,
    }


async def _link_to_er_case_and_upload_transcript(
    conn,
    interview_id: str,
    incident_id: Optional[str],
    transcript: str,
    company_id: Optional[str],
) -> None:
    """Phase 2: Link investigation interview to ER case and upload transcript as document."""
    if not incident_id:
        return

    # Resolve ER case: check interview -> incident -> auto-create
    er_case_id = await conn.fetchval(
        "SELECT er_case_id FROM interviews WHERE id = $1", interview_id,
    )
    if not er_case_id:
        er_case_id = await conn.fetchval(
            "SELECT er_case_id FROM ir_incidents WHERE id = $1", _UUID(incident_id),
        )

    if not er_case_id:
        # Auto-create ER case from incident
        incident = await conn.fetchrow(
            """
            SELECT title, description, incident_type, involved_employee_ids, company_id, created_by
            FROM ir_incidents WHERE id = $1
            """,
            _UUID(incident_id),
        )
        if not incident:
            return

        # Map incident_type to ER category
        type_to_category = {
            "behavioral": "misconduct",
            "safety": "safety",
            "property": "misconduct",
            "near_miss": "safety",
            "other": "other",
        }
        category = type_to_category.get(incident["incident_type"], "other")

        # Generate case number
        import secrets
        from datetime import datetime as _datetime, timezone as _timezone
        _now = _datetime.now(_timezone.utc)
        case_number = f"ER-{_now.year}-{_now.month:02d}-{secrets.token_hex(2).upper()}"

        # Build involved_employees JSONB from involved_employee_ids
        involved_employees = json.dumps(
            [{"employee_id": str(eid)} for eid in (incident["involved_employee_ids"] or [])]
        )

        er_case_id = await conn.fetchval(
            """
            INSERT INTO er_cases (case_number, title, description, category, company_id, created_by, involved_employees)
            VALUES ($1, $2, $3, $4, $5, $6, $7::jsonb)
            RETURNING id
            """,
            case_number,
            f"Investigation: {incident['title']}",
            incident["description"],
            category,
            incident["company_id"] or (company_id if company_id else None),
            incident["created_by"],
            involved_employees,
        )

    # Update FKs on all related records
    await conn.execute(
        "UPDATE ir_incidents SET er_case_id = $1 WHERE id = $2 AND er_case_id IS NULL",
        er_case_id, incident_id,
    )
    await conn.execute(
        "UPDATE interviews SET er_case_id = $1 WHERE id = $2 AND er_case_id IS NULL",
        er_case_id, interview_id,
    )
    await conn.execute(
        "UPDATE ir_investigation_interviews SET er_case_id = $1 WHERE interview_id = $2 AND er_case_id IS NULL",
        er_case_id, interview_id,
    )

    # Upload transcript as ER case document
    if transcript:
        from app.config import load_settings
        from app.core.services.storage import get_storage

        settings = load_settings()
        storage = get_storage(settings)

        # Format transcript as text file
        transcript_bytes = transcript.encode("utf-8")
        interviewee_name = await conn.fetchval(
            "SELECT interviewee_name FROM ir_investigation_interviews WHERE interview_id = $1",
            interview_id,
        )
        filename = f"investigation_transcript_{interviewee_name or 'unknown'}_{interview_id[:8]}.txt"

        # Upload to S3
        file_path = await storage.upload_file(
            transcript_bytes, filename,
            prefix=f"er-cases/{er_case_id}/documents",
            content_type="text/plain",
        )

        # Insert into er_case_documents
        doc_id = await conn.fetchval(
            """
            INSERT INTO er_case_documents (case_id, filename, file_path, mime_type, file_size, document_type, processing_status, scrubbed_text)
            VALUES ($1, $2, $3, 'text/plain', $4, 'transcript', 'completed', $5)
            RETURNING id
            """,
            er_case_id,
            filename,
            file_path,
            len(transcript_bytes),
            transcript,
        )

        # Queue document processing for RAG chunking
        if doc_id:
            try:
                from app.workers.tasks.er_document_processing import process_er_document
                process_er_document.delay(str(doc_id), str(er_case_id))
            except Exception as e:
                print(f"[Worker] Failed to queue ER document processing: {e}")


@celery_app.task(bind=True, max_retries=3)
def analyze_interview_async(
    self,
    interview_id: str,
    interview_type: str,
    transcript: str,
    company_id: Optional[str] = None,
    culture_profile: Optional[dict[str, Any]] = None,
    language: Optional[str] = None,
    incident_id: Optional[str] = None,
) -> dict[str, Any]:
    """
    Analyze interview transcript in background.

    This task is queued after a WebSocket interview session ends.
    It runs analysis and updates the database, then notifies the frontend.

    Args:
        interview_id: UUID of the interview
        interview_type: "culture", "candidate", "screening", "tutor_interview", "tutor_language", or "investigation"
        transcript: Full transcript text
        company_id: UUID of the company (for notification channel), None for tutor sessions
        culture_profile: Optional culture profile for candidate interviews
        language: Optional language code for tutor_language sessions ("en" or "es")
        incident_id: Optional UUID of the linked IR incident (for investigation interviews)
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
                language=language,
                incident_id=incident_id,
            )
        )

        # Notify frontend via Redis pub/sub (only for company interviews)
        if company_id:
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

        # Notify frontend of error (only for company interviews)
        if company_id:
            publish_task_error(
                channel=f"company:{company_id}",
                task_type="interview_analysis",
                entity_id=interview_id,
                error=str(e),
            )

        # Retry with exponential backoff
        raise self.retry(exc=e, countdown=60 * (self.request.retries + 1))
