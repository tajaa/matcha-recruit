"""
Celery tasks for ER Copilot analysis.

Handles AI-powered analysis:
- Timeline reconstruction
- Discrepancy detection
- Policy violation check
- Report generation
"""

import asyncio
import json
from datetime import datetime, timezone
from typing import Any, Optional

from ..celery_app import celery_app
from ..notifications import publish_task_complete, publish_task_error
from ..utils import get_db_connection


async def _get_documents_for_analysis(
    conn,
    case_id: str,
    document_type: Optional[str] = None,
    exclude_type: Optional[str] = None,
) -> list[dict]:
    """Get processed documents for analysis."""
    query = """
        SELECT id, filename, document_type, scrubbed_text
        FROM er_case_documents
        WHERE case_id = $1 AND processing_status = 'completed' AND scrubbed_text IS NOT NULL
    """
    params = [case_id]

    if document_type:
        query += " AND document_type = $2"
        params.append(document_type)
    elif exclude_type:
        query += " AND document_type != $2"
        params.append(exclude_type)

    rows = await conn.fetch(query, *params)

    return [
        {
            "id": str(row["id"]),
            "filename": row["filename"],
            "document_type": row["document_type"],
            "text": row["scrubbed_text"],
        }
        for row in rows
    ]


async def _save_analysis_result(
    conn,
    case_id: str,
    analysis_type: str,
    analysis_data: dict,
    source_documents: list[str],
    generated_by: Optional[str] = None,
):
    """Save or update analysis result."""
    await conn.execute(
        """
        INSERT INTO er_case_analysis (case_id, analysis_type, analysis_data, source_documents, generated_by, generated_at)
        VALUES ($1, $2, $3, $4, $5, NOW())
        ON CONFLICT (case_id, analysis_type)
        DO UPDATE SET analysis_data = $3, source_documents = $4, generated_by = $5, generated_at = NOW()
        """,
        case_id,
        analysis_type,
        json.dumps(analysis_data),
        json.dumps(source_documents),
        generated_by,
    )


# ===========================================
# Timeline Analysis
# ===========================================

async def _run_timeline_analysis(case_id: str) -> dict[str, Any]:
    """Run timeline reconstruction analysis."""
    from app.services.er_analyzer import ERAnalyzer
    from app.config import load_settings

    settings = load_settings()
    analyzer = ERAnalyzer(
        api_key=settings.gemini_api_key,
        vertex_project=settings.vertex_project,
        vertex_location=settings.vertex_location,
        model="gemini-2.5-flash",
    )

    conn = await get_db_connection()
    try:
        # Get all processed documents (transcripts and evidence)
        documents = await _get_documents_for_analysis(conn, case_id, exclude_type="policy")

        if not documents:
            raise ValueError("No processed documents found for timeline analysis")

        # Run analysis
        result = analyzer.reconstruct_timeline_sync(documents)

        # Save result
        source_doc_ids = [d["id"] for d in documents]
        await _save_analysis_result(
            conn,
            case_id,
            "timeline",
            result,
            source_doc_ids,
        )

        return {
            "case_id": case_id,
            "events_found": len(result.get("events", [])),
            "gaps_identified": len(result.get("gaps_identified", [])),
        }

    finally:
        await conn.close()


@celery_app.task(bind=True, max_retries=3)
def run_timeline_analysis(self, case_id: str) -> dict[str, Any]:
    """Celery task for timeline analysis."""
    try:
        result = asyncio.run(_run_timeline_analysis(case_id))

        publish_task_complete(
            channel=f"er_case:{case_id}",
            task_type="timeline_analysis",
            entity_id=case_id,
            result=result,
        )

        return {"status": "success", **result}

    except Exception as e:
        publish_task_error(
            channel=f"er_case:{case_id}",
            task_type="timeline_analysis",
            entity_id=case_id,
            error=str(e),
        )
        raise self.retry(exc=e, countdown=60 * (self.request.retries + 1))


# ===========================================
# Discrepancy Analysis
# ===========================================

async def _run_discrepancy_analysis(case_id: str) -> dict[str, Any]:
    """Run discrepancy detection analysis."""
    from app.services.er_analyzer import ERAnalyzer
    from app.config import load_settings

    settings = load_settings()
    analyzer = ERAnalyzer(
        api_key=settings.gemini_api_key,
        vertex_project=settings.vertex_project,
        vertex_location=settings.vertex_location,
        model="gemini-2.5-flash",
    )

    conn = await get_db_connection()
    try:
        # Get transcript documents only
        documents = await _get_documents_for_analysis(conn, case_id, document_type="transcript")

        if len(documents) < 2:
            raise ValueError("Need at least 2 transcript documents for discrepancy analysis")

        # Run analysis
        result = analyzer.detect_discrepancies_sync(documents)

        # Save result
        source_doc_ids = [d["id"] for d in documents]
        await _save_analysis_result(
            conn,
            case_id,
            "discrepancies",
            result,
            source_doc_ids,
        )

        return {
            "case_id": case_id,
            "discrepancies_found": len(result.get("discrepancies", [])),
            "witnesses_analyzed": len(result.get("credibility_notes", [])),
        }

    finally:
        await conn.close()


@celery_app.task(bind=True, max_retries=3)
def run_discrepancy_analysis(self, case_id: str) -> dict[str, Any]:
    """Celery task for discrepancy analysis."""
    try:
        result = asyncio.run(_run_discrepancy_analysis(case_id))

        publish_task_complete(
            channel=f"er_case:{case_id}",
            task_type="discrepancy_analysis",
            entity_id=case_id,
            result=result,
        )

        return {"status": "success", **result}

    except Exception as e:
        publish_task_error(
            channel=f"er_case:{case_id}",
            task_type="discrepancy_analysis",
            entity_id=case_id,
            error=str(e),
        )
        raise self.retry(exc=e, countdown=60 * (self.request.retries + 1))


# ===========================================
# Policy Check
# ===========================================

async def _run_policy_check(case_id: str, policy_document_id: str) -> dict[str, Any]:
    """Run policy violation check."""
    from app.services.er_analyzer import ERAnalyzer
    from app.config import load_settings

    settings = load_settings()
    analyzer = ERAnalyzer(
        api_key=settings.gemini_api_key,
        vertex_project=settings.vertex_project,
        vertex_location=settings.vertex_location,
        model="gemini-2.5-flash",
    )

    conn = await get_db_connection()
    try:
        # Get policy document
        policy_row = await conn.fetchrow(
            """
            SELECT id, filename, scrubbed_text
            FROM er_case_documents
            WHERE id = $1 AND processing_status = 'completed'
            """,
            policy_document_id,
        )

        if not policy_row:
            raise ValueError("Policy document not found or not processed")

        policy_doc = {
            "id": str(policy_row["id"]),
            "filename": policy_row["filename"],
            "text": policy_row["scrubbed_text"],
        }

        # Get evidence documents
        evidence_docs = await _get_documents_for_analysis(conn, case_id, exclude_type="policy")

        if not evidence_docs:
            raise ValueError("No evidence documents found for policy check")

        # Run analysis
        result = analyzer.check_policy_violations_sync(policy_doc, evidence_docs)

        # Save result
        source_doc_ids = [policy_document_id] + [d["id"] for d in evidence_docs]
        await _save_analysis_result(
            conn,
            case_id,
            "policy_check",
            result,
            source_doc_ids,
        )

        return {
            "case_id": case_id,
            "violations_found": len(result.get("violations", [])),
            "policies_applicable": len(result.get("policies_potentially_applicable", [])),
        }

    finally:
        await conn.close()


@celery_app.task(bind=True, max_retries=3)
def run_policy_check(self, case_id: str, policy_document_id: str) -> dict[str, Any]:
    """Celery task for policy check."""
    try:
        result = asyncio.run(_run_policy_check(case_id, policy_document_id))

        publish_task_complete(
            channel=f"er_case:{case_id}",
            task_type="policy_check",
            entity_id=case_id,
            result=result,
        )

        return {"status": "success", **result}

    except Exception as e:
        publish_task_error(
            channel=f"er_case:{case_id}",
            task_type="policy_check",
            entity_id=case_id,
            error=str(e),
        )
        raise self.retry(exc=e, countdown=60 * (self.request.retries + 1))


# ===========================================
# Report Generation
# ===========================================

async def _generate_summary_report(case_id: str, generated_by: str) -> dict[str, Any]:
    """Generate investigation summary report."""
    from app.services.er_analyzer import ERAnalyzer
    from app.config import load_settings

    settings = load_settings()
    analyzer = ERAnalyzer(
        api_key=settings.gemini_api_key,
        vertex_project=settings.vertex_project,
        vertex_location=settings.vertex_location,
        model="gemini-2.5-flash",
    )

    conn = await get_db_connection()
    try:
        # Get case info
        case = await conn.fetchrow(
            "SELECT case_number, title, description, status, created_at FROM er_cases WHERE id = $1",
            case_id,
        )

        if not case:
            raise ValueError("Case not found")

        case_info = {
            "case_number": case["case_number"],
            "title": case["title"],
            "description": case["description"],
            "status": case["status"],
            "created_at": case["created_at"].isoformat() if case["created_at"] else None,
        }

        # Get existing analyses
        timeline = None
        discrepancies = None
        policy_analysis = None

        timeline_row = await conn.fetchrow(
            "SELECT analysis_data FROM er_case_analysis WHERE case_id = $1 AND analysis_type = 'timeline'",
            case_id,
        )
        if timeline_row:
            timeline = timeline_row["analysis_data"]

        disc_row = await conn.fetchrow(
            "SELECT analysis_data FROM er_case_analysis WHERE case_id = $1 AND analysis_type = 'discrepancies'",
            case_id,
        )
        if disc_row:
            discrepancies = disc_row["analysis_data"]

        policy_row = await conn.fetchrow(
            "SELECT analysis_data FROM er_case_analysis WHERE case_id = $1 AND analysis_type = 'policy_check'",
            case_id,
        )
        if policy_row:
            policy_analysis = policy_row["analysis_data"]

        # Generate report (using sync version in async context via run_in_executor)
        import asyncio
        loop = asyncio.get_event_loop()
        report_content = await loop.run_in_executor(
            None,
            lambda: asyncio.run(
                analyzer.generate_summary_report(case_info, timeline, discrepancies, policy_analysis)
            ),
        )

        # Save result
        documents = await _get_documents_for_analysis(conn, case_id)
        source_doc_ids = [d["id"] for d in documents]

        await _save_analysis_result(
            conn,
            case_id,
            "summary",
            {"content": report_content, "generated_at": datetime.now(timezone.utc).isoformat()},
            source_doc_ids,
            generated_by,
        )

        return {
            "case_id": case_id,
            "report_type": "summary",
            "content_length": len(report_content),
        }

    finally:
        await conn.close()


@celery_app.task(bind=True, max_retries=3)
def generate_summary_report(self, case_id: str, generated_by: str) -> dict[str, Any]:
    """Celery task for summary report generation."""
    try:
        result = asyncio.run(_generate_summary_report(case_id, generated_by))

        publish_task_complete(
            channel=f"er_case:{case_id}",
            task_type="summary_report",
            entity_id=case_id,
            result=result,
        )

        return {"status": "success", **result}

    except Exception as e:
        publish_task_error(
            channel=f"er_case:{case_id}",
            task_type="summary_report",
            entity_id=case_id,
            error=str(e),
        )
        raise self.retry(exc=e, countdown=60 * (self.request.retries + 1))


async def _generate_determination_letter(
    case_id: str,
    determination: str,
    generated_by: str,
) -> dict[str, Any]:
    """Generate determination letter."""
    from app.services.er_analyzer import ERAnalyzer
    from app.config import load_settings

    settings = load_settings()
    analyzer = ERAnalyzer(
        api_key=settings.gemini_api_key,
        vertex_project=settings.vertex_project,
        vertex_location=settings.vertex_location,
        model="gemini-2.5-flash",
    )

    conn = await get_db_connection()
    try:
        # Get case info
        case = await conn.fetchrow(
            "SELECT case_number, title, description FROM er_cases WHERE id = $1",
            case_id,
        )

        if not case:
            raise ValueError("Case not found")

        case_info = {
            "case_number": case["case_number"],
            "title": case["title"],
            "description": case["description"],
        }

        # Get summary if available
        summary_row = await conn.fetchrow(
            "SELECT analysis_data FROM er_case_analysis WHERE case_id = $1 AND analysis_type = 'summary'",
            case_id,
        )
        findings = ""
        if summary_row and summary_row["analysis_data"]:
            findings = summary_row["analysis_data"].get("content", "")[:2000]  # Limit length

        # Generate letter
        import asyncio
        loop = asyncio.get_event_loop()
        letter_content = await loop.run_in_executor(
            None,
            lambda: asyncio.run(
                analyzer.generate_determination_letter(case_info, determination, findings)
            ),
        )

        # Save result
        await _save_analysis_result(
            conn,
            case_id,
            "determination",
            {
                "content": letter_content,
                "determination": determination,
                "generated_at": datetime.now(timezone.utc).isoformat(),
            },
            [],
            generated_by,
        )

        return {
            "case_id": case_id,
            "report_type": "determination",
            "determination": determination,
            "content_length": len(letter_content),
        }

    finally:
        await conn.close()


@celery_app.task(bind=True, max_retries=3)
def generate_determination_letter(
    self,
    case_id: str,
    determination: str,
    generated_by: str,
) -> dict[str, Any]:
    """Celery task for determination letter generation."""
    try:
        result = asyncio.run(_generate_determination_letter(case_id, determination, generated_by))

        publish_task_complete(
            channel=f"er_case:{case_id}",
            task_type="determination_letter",
            entity_id=case_id,
            result=result,
        )

        return {"status": "success", **result}

    except Exception as e:
        publish_task_error(
            channel=f"er_case:{case_id}",
            task_type="determination_letter",
            entity_id=case_id,
            error=str(e),
        )
        raise self.retry(exc=e, countdown=60 * (self.request.retries + 1))
