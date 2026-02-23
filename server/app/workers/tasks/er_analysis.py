"""
Celery tasks for ER Copilot analysis.

Handles AI-powered analysis:
- Timeline reconstruction
- Discrepancy detection
- Policy violation check
- Report generation
"""

import asyncio
import hashlib
import json
import logging
from datetime import datetime, timezone
from typing import Any, Optional

from ..celery_app import celery_app
from ..notifications import publish_task_complete, publish_task_error, publish_task_progress
from ..utils import get_db_connection

logger = logging.getLogger(__name__)


def _safe_publish_progress(**kwargs) -> None:
    """Publish progress, ignoring errors when Redis is unavailable."""
    try:
        publish_task_progress(**kwargs)
    except Exception:
        logger.debug("Redis unavailable for progress notification, skipping")


def _build_er_analyzer():
    """Create ERAnalyzer using the same credential cascade as GeminiComplianceService."""
    from app.matcha.services.er_analyzer import ERAnalyzer
    from app.config import get_settings
    import os

    settings = get_settings()

    # Same priority as GeminiComplianceService.client:
    # 1. GEMINI_API_KEY env var (explicit override)
    # 2. Vertex AI (if VERTEX_PROJECT configured)
    # 3. LIVE_API via settings.gemini_api_key
    explicit_api_key = os.getenv("GEMINI_API_KEY")

    if explicit_api_key:
        return ERAnalyzer(api_key=explicit_api_key, model=settings.analysis_model)
    elif settings.use_vertex:
        return ERAnalyzer(
            vertex_project=settings.vertex_project,
            vertex_location=settings.vertex_location,
            model=settings.analysis_model,
        )
    elif settings.gemini_api_key:
        return ERAnalyzer(api_key=settings.gemini_api_key, model=settings.analysis_model)
    else:
        raise ValueError("ER analysis requires GEMINI_API_KEY, LIVE_API, or VERTEX_PROJECT configuration")


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
    analyzer = _build_er_analyzer()

    conn = await get_db_connection()
    try:
        # Progress: Loading documents
        _safe_publish_progress(
            channel=f"er_case:{case_id}",
            task_type="timeline_analysis",
            entity_id=case_id,
            progress=1,
            total=3,
            message="Loading documents...",
        )

        # Get all processed documents (transcripts and evidence)
        documents = await _get_documents_for_analysis(conn, case_id, exclude_type="policy")

        if not documents:
            raise ValueError("No processed documents found for timeline analysis")

        # Progress: Analyzing documents
        _safe_publish_progress(
            channel=f"er_case:{case_id}",
            task_type="timeline_analysis",
            entity_id=case_id,
            progress=2,
            total=3,
            message=f"Reconstructing timeline from {len(documents)} documents...",
        )

        # Run analysis (use async method since we're in async context)
        result = await analyzer.reconstruct_timeline(documents)

        # Progress: Saving results
        _safe_publish_progress(
            channel=f"er_case:{case_id}",
            task_type="timeline_analysis",
            entity_id=case_id,
            progress=3,
            total=3,
            message="Saving analysis results...",
        )

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
    analyzer = _build_er_analyzer()

    conn = await get_db_connection()
    try:
        # Progress: Loading documents
        _safe_publish_progress(
            channel=f"er_case:{case_id}",
            task_type="discrepancy_analysis",
            entity_id=case_id,
            progress=1,
            total=3,
            message="Loading documents...",
        )

        # Get all documents except policy
        documents = await _get_documents_for_analysis(conn, case_id, exclude_type="policy")

        if len(documents) < 2:
            raise ValueError("Need at least 2 documents for discrepancy analysis")

        # Progress: Analyzing documents
        _safe_publish_progress(
            channel=f"er_case:{case_id}",
            task_type="discrepancy_analysis",
            entity_id=case_id,
            progress=2,
            total=3,
            message=f"Analyzing {len(documents)} documents for discrepancies...",
        )

        # Run analysis (use async method since we're in async context)
        result = await analyzer.detect_discrepancies(documents)

        # Progress: Saving results
        _safe_publish_progress(
            channel=f"er_case:{case_id}",
            task_type="discrepancy_analysis",
            entity_id=case_id,
            progress=3,
            total=3,
            message="Saving analysis results...",
        )

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

def _text_fingerprint(value: str) -> str:
    normalized = " ".join((value or "").split()).strip().lower()
    return hashlib.sha256(normalized.encode("utf-8")).hexdigest()


async def _extract_text_from_file_url(file_url: str, fallback_filename: str) -> str:
    """Download a file from storage and extract plain text for analysis."""
    from app.core.services.storage import get_storage
    from app.matcha.services.er_document_parser import ERDocumentParser
    from urllib.parse import urlparse, unquote
    import os

    storage = get_storage()
    parser = ERDocumentParser()

    parsed_path = urlparse(file_url).path
    filename = os.path.basename(unquote(parsed_path)) or fallback_filename
    if "." not in filename:
        filename = f"{filename}.txt"

    file_bytes = await storage.download_file(file_url)
    parsed = parser.parse_document(file_bytes, filename)
    return parsed.text.strip()


async def _get_company_policy_records(conn, company_id: str) -> list[dict]:
    """Get all active policies configured in the Policies module."""
    rows = await conn.fetch(
        """
        SELECT id, title, content, file_url
        FROM policies
        WHERE company_id = $1 AND status = 'active'
        ORDER BY title
        """,
        company_id,
    )

    policies: list[dict] = []
    for row in rows:
        text = (row["content"] or "").strip()
        if not text and row["file_url"]:
            file_url = str(row["file_url"])
            try:
                text = await _extract_text_from_file_url(
                    file_url,
                    fallback_filename=f"policy-{row['id']}.txt",
                )
            except Exception as exc:
                logger.warning(
                    "Failed to parse active policy %s (%s) from %s: %s",
                    row["id"],
                    row["title"],
                    file_url,
                    exc,
                )

        if text:
            policies.append(
                {
                    "id": str(row["id"]),
                    "title": row["title"],
                    "text": text,
                    "source_kind": "policy",
                }
            )
        else:
            logger.info(
                "Skipping active policy %s (%s): no usable text content",
                row["id"],
                row["title"],
            )

    return policies


async def _get_active_handbook_record(conn, company_id: str) -> Optional[dict]:
    """Get the currently active handbook content for the company, if any."""
    handbook_row = await conn.fetchrow(
        """
        SELECT id, title, source_type, file_url, file_name, active_version
        FROM handbooks
        WHERE company_id = $1 AND status = 'active'
        ORDER BY published_at DESC NULLS LAST, updated_at DESC, created_at DESC
        LIMIT 1
        """,
        company_id,
    )
    if not handbook_row:
        return None

    handbook_id = str(handbook_row["id"])
    handbook_title = handbook_row["title"] or "Employee Handbook"
    handbook_text = ""

    version_id = await conn.fetchval(
        """
        SELECT id
        FROM handbook_versions
        WHERE handbook_id = $1 AND version_number = $2
        """,
        handbook_row["id"],
        handbook_row["active_version"],
    )
    if version_id is None:
        version_id = await conn.fetchval(
            """
            SELECT id
            FROM handbook_versions
            WHERE handbook_id = $1
            ORDER BY version_number DESC
            LIMIT 1
            """,
            handbook_row["id"],
        )

    if version_id is not None:
        section_rows = await conn.fetch(
            """
            SELECT title, content
            FROM handbook_sections
            WHERE handbook_version_id = $1
            ORDER BY section_order ASC, created_at ASC
            """,
            version_id,
        )
        section_blocks = []
        for row in section_rows:
            content = (row["content"] or "").strip()
            if not content:
                continue
            title = (row["title"] or "").strip()
            if title:
                section_blocks.append(f"{title}\n{content}")
            else:
                section_blocks.append(content)
        handbook_text = "\n\n".join(section_blocks).strip()

    if not handbook_text and handbook_row["file_url"]:
        file_url = str(handbook_row["file_url"])
        try:
            handbook_text = await _extract_text_from_file_url(
                file_url,
                fallback_filename=handbook_row["file_name"] or f"handbook-{handbook_id}.pdf",
            )
        except Exception as exc:
            logger.warning(
                "Failed to parse active handbook %s (%s) from %s: %s",
                handbook_id,
                handbook_title,
                file_url,
                exc,
            )

    if not handbook_text:
        logger.info(
            "Skipping active handbook %s (%s): no usable text content",
            handbook_id,
            handbook_title,
        )
        return None

    return {
        "id": f"handbook:{handbook_id}",
        "title": f"Handbook: {handbook_title}",
        "text": handbook_text,
        "source_kind": "handbook",
    }


async def _get_case_policy_documents(conn, case_id: str) -> list[dict]:
    """Get completed policy documents uploaded directly to this ER case."""
    rows = await conn.fetch(
        """
        SELECT id, filename, scrubbed_text
        FROM er_case_documents
        WHERE case_id = $1 AND document_type = 'policy' AND processing_status = 'completed'
        ORDER BY created_at ASC
        """,
        case_id,
    )

    documents: list[dict] = []
    for row in rows:
        text = (row["scrubbed_text"] or "").strip()
        if not text:
            continue
        documents.append(
            {
                "id": f"erdoc:{row['id']}",
                "title": f"Case Policy: {row['filename'] or row['id']}",
                "text": text,
                "source_kind": "case_policy",
            }
        )
    return documents


async def _get_policy_sources(conn, case_id: str) -> list[dict]:
    """Get all policy text sources relevant for ER policy checks."""
    # Resolve the company from the case itself first (source of truth), then creator fallback.
    company_id = await conn.fetchval(
        """
        SELECT COALESCE(ec.company_id, cl.company_id, (SELECT id FROM companies ORDER BY created_at LIMIT 1))
        FROM er_cases ec
        LEFT JOIN users u ON ec.created_by = u.id
        LEFT JOIN clients cl ON u.id = cl.user_id
        WHERE ec.id = $1
        """,
        case_id,
    )

    if not company_id:
        return []

    source_docs: list[dict] = []
    seen_fingerprints: set[str] = set()

    def add_source(doc: Optional[dict]) -> None:
        if not doc:
            return
        text = (doc.get("text") or "").strip()
        if not text:
            return
        fingerprint = _text_fingerprint(text)
        if fingerprint in seen_fingerprints:
            return
        seen_fingerprints.add(fingerprint)
        source_docs.append(doc)

    for policy_doc in await _get_company_policy_records(conn, str(company_id)):
        add_source(policy_doc)

    add_source(await _get_active_handbook_record(conn, str(company_id)))

    for case_policy_doc in await _get_case_policy_documents(conn, case_id):
        add_source(case_policy_doc)

    return source_docs


async def _run_policy_check(case_id: str) -> dict[str, Any]:
    """Run policy violation check against company policy sources."""
    analyzer = _build_er_analyzer()

    conn = await get_db_connection()
    try:
        # Progress: Loading policy sources
        _safe_publish_progress(
            channel=f"er_case:{case_id}",
            task_type="policy_check",
            entity_id=case_id,
            progress=1,
            total=4,
            message="Loading policy sources...",
        )

        # Get all policy sources (active policies, active handbook, case-uploaded policy docs).
        policies = await _get_policy_sources(conn, case_id)

        if not policies:
            raise ValueError(
                "No policy sources found. Add active policies, publish a handbook, or upload policy documents to this case."
            )

        total_steps = len(policies) + 3  # load sources + load evidence + each source check + save

        # Progress: Loading evidence
        _safe_publish_progress(
            channel=f"er_case:{case_id}",
            task_type="policy_check",
            entity_id=case_id,
            progress=2,
            total=total_steps,
            message=f"Found {len(policies)} policy sources. Loading evidence documents...",
        )

        # Get evidence documents
        evidence_docs = await _get_documents_for_analysis(conn, case_id, exclude_type="policy")

        if not evidence_docs:
            raise ValueError("No evidence documents found for policy check")

        all_violations: list[dict[str, Any]] = []
        applicable_policies: list[str] = []
        policy_summaries: list[str] = []

        # Analyze each policy source individually so all available inputs are checked.
        for idx, policy in enumerate(policies):
            _safe_publish_progress(
                channel=f"er_case:{case_id}",
                task_type="policy_check",
                entity_id=case_id,
                progress=3 + idx,
                total=total_steps,
                message=f"Checking source {idx + 1}/{len(policies)}: {policy['title']}",
            )

            policy_doc = {
                "id": policy["id"],
                "filename": policy["title"],
                "text": policy["text"],
            }
            policy_result = await analyzer.check_policy_violations(policy_doc, evidence_docs)

            violations = policy_result.get("violations", [])
            if isinstance(violations, list):
                all_violations.extend(violations)

            maybe_applicable = policy_result.get("policies_potentially_applicable", [])
            if isinstance(maybe_applicable, list):
                for item in maybe_applicable:
                    if isinstance(item, str) and item not in applicable_policies:
                        applicable_policies.append(item)

            summary = policy_result.get("summary")
            if isinstance(summary, str) and summary.strip():
                policy_summaries.append(f"{policy['title']}: {summary.strip()}")

        if all_violations:
            summary_text = (
                f"Checked {len(policies)} policy source(s) and identified "
                f"{len(all_violations)} potential violation(s)."
            )
        else:
            summary_text = f"Checked {len(policies)} policy source(s). No policy violations identified."

        if policy_summaries:
            preview = " ".join(policy_summaries[:3])
            extra_count = max(len(policy_summaries) - 3, 0)
            if extra_count:
                summary_text = f"{summary_text} {preview} (+{extra_count} more policy summary items)"
            else:
                summary_text = f"{summary_text} {preview}"

        result = {
            "violations": all_violations,
            "policies_potentially_applicable": applicable_policies,
            "summary": summary_text,
            "generated_at": datetime.now(timezone.utc).isoformat(),
        }

        # Progress: Saving results
        _safe_publish_progress(
            channel=f"er_case:{case_id}",
            task_type="policy_check",
            entity_id=case_id,
            progress=total_steps,
            total=total_steps,
            message="Saving analysis results...",
        )

        # Save result with policy IDs as source
        source_doc_ids = [p["id"] for p in policies] + [d["id"] for d in evidence_docs]
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
            "policies_checked": len(policies),
        }

    finally:
        await conn.close()


@celery_app.task(bind=True, max_retries=3)
def run_policy_check(self, case_id: str) -> dict[str, Any]:
    """Celery task for policy check."""
    try:
        result = asyncio.run(_run_policy_check(case_id))

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
    analyzer = _build_er_analyzer()

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
    analyzer = _build_er_analyzer()

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
