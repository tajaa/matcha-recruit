"""ER Copilot API Routes.

Employee Relations Investigation management:
- Cases CRUD
- Document upload and processing
- AI analysis (timeline, discrepancies, policy check)
- Report generation
- Evidence search (RAG)
"""

import json
import logging
import secrets
from datetime import datetime, timezone

from typing import Optional
from uuid import UUID

from fastapi import APIRouter, HTTPException, Depends, UploadFile, File, Form, Request

from ...database import get_connection
from ...core.dependencies import require_admin
from ..dependencies import require_admin_or_client
from ...config import get_settings
from ...core.services.storage import get_storage
from ..models.er_case import (
    ERCaseCreate,
    ERCaseUpdate,
    ERCaseResponse,
    ERCaseListResponse,
    ERDocumentResponse,
    ERDocumentUploadResponse,
    TimelineAnalysis,
    DiscrepancyAnalysis,
    PolicyCheckAnalysis,
    EvidenceSearchRequest,
    EvidenceSearchResponse,
    EvidenceSearchResult,
    ReportGenerateRequest,
    ReportResponse,
    TaskStatusResponse,
    AuditLogEntry,
    AuditLogResponse,
)

logger = logging.getLogger(__name__)

router = APIRouter()


# ===========================================
# Helper Functions
# ===========================================

def generate_case_number() -> str:
    """Generate a unique case number."""
    now = datetime.now(timezone.utc)
    random_suffix = secrets.token_hex(2).upper()
    return f"ER-{now.year}-{now.month:02d}-{random_suffix}"


async def log_audit(
    conn,
    case_id: Optional[str],
    user_id: str,
    action: str,
    entity_type: Optional[str] = None,
    entity_id: Optional[str] = None,
    details: Optional[dict] = None,
    ip_address: Optional[str] = None,
):
    """Log an action to the audit trail."""
    await conn.execute(
        """
        INSERT INTO er_audit_log (case_id, user_id, action, entity_type, entity_id, details, ip_address)
        VALUES ($1, $2, $3, $4, $5, $6, $7)
        """,
        case_id,
        user_id,
        action,
        entity_type,
        entity_id,
        json.dumps(details) if details else None,
        ip_address,
    )


# ===========================================
# Cases CRUD
# ===========================================

@router.post("", response_model=ERCaseResponse)
async def create_case(
    case: ERCaseCreate,
    request: Request,
    current_user=Depends(require_admin_or_client),
):
    """Create a new ER investigation case."""
    case_number = generate_case_number()

    async with get_connection() as conn:
        row = await conn.fetchrow(
            """
            INSERT INTO er_cases (case_number, title, description, created_by)
            VALUES ($1, $2, $3, $4)
            RETURNING id, case_number, title, description, status, created_by, assigned_to, created_at, updated_at, closed_at
            """,
            case_number,
            case.title,
            case.description,
            str(current_user.id),
        )

        # Log audit
        await log_audit(
            conn,
            str(row["id"]),
            str(current_user.id),
            "case_created",
            "case",
            str(row["id"]),
            {"title": case.title},
            request.client.host if request.client else None,
        )

        return ERCaseResponse(
            id=row["id"],
            case_number=row["case_number"],
            title=row["title"],
            description=row["description"],
            status=row["status"],
            created_by=row["created_by"],
            assigned_to=row["assigned_to"],
            document_count=0,
            created_at=row["created_at"],
            updated_at=row["updated_at"],
            closed_at=row["closed_at"],
        )


@router.get("", response_model=ERCaseListResponse)
async def list_cases(
    status: Optional[str] = None,
    current_user=Depends(require_admin_or_client),
):
    """List all ER cases with optional status filter."""
    async with get_connection() as conn:
        base_query = """
            SELECT c.*, COUNT(d.id) as document_count
            FROM er_cases c
            LEFT JOIN er_case_documents d ON c.id = d.case_id
        """

        if status:
            query = base_query + " WHERE c.status = $1 GROUP BY c.id ORDER BY c.updated_at DESC"
            rows = await conn.fetch(query, status)
        else:
            query = base_query + " GROUP BY c.id ORDER BY c.updated_at DESC"
            rows = await conn.fetch(query)

        cases = [
            ERCaseResponse(
                id=row["id"],
                case_number=row["case_number"],
                title=row["title"],
                description=row["description"],
                status=row["status"],
                created_by=row["created_by"],
                assigned_to=row["assigned_to"],
                document_count=row["document_count"],
                created_at=row["created_at"],
                updated_at=row["updated_at"],
                closed_at=row["closed_at"],
            )
            for row in rows
        ]

        return ERCaseListResponse(cases=cases, total=len(cases))


@router.get("/{case_id}", response_model=ERCaseResponse)
async def get_case(
    case_id: UUID,
    current_user=Depends(require_admin_or_client),
):
    """Get a case by ID."""
    async with get_connection() as conn:
        row = await conn.fetchrow(
            """
            SELECT c.*, COUNT(d.id) as document_count
            FROM er_cases c
            LEFT JOIN er_case_documents d ON c.id = d.case_id
            WHERE c.id = $1
            GROUP BY c.id
            """,
            case_id,
        )

        if not row:
            raise HTTPException(status_code=404, detail="Case not found")

        return ERCaseResponse(
            id=row["id"],
            case_number=row["case_number"],
            title=row["title"],
            description=row["description"],
            status=row["status"],
            created_by=row["created_by"],
            assigned_to=row["assigned_to"],
            document_count=row["document_count"],
            created_at=row["created_at"],
            updated_at=row["updated_at"],
            closed_at=row["closed_at"],
        )


@router.put("/{case_id}", response_model=ERCaseResponse)
async def update_case(
    case_id: UUID,
    case: ERCaseUpdate,
    request: Request,
    current_user=Depends(require_admin_or_client),
):
    """Update a case."""
    async with get_connection() as conn:
        # Build dynamic update
        updates = []
        params = []
        param_count = 1

        if case.title is not None:
            updates.append(f"title = ${param_count}")
            params.append(case.title)
            param_count += 1

        if case.description is not None:
            updates.append(f"description = ${param_count}")
            params.append(case.description)
            param_count += 1

        if case.status is not None:
            updates.append(f"status = ${param_count}")
            params.append(case.status)
            param_count += 1

            if case.status == "closed":
                updates.append("closed_at = NOW()")

        if case.assigned_to is not None:
            updates.append(f"assigned_to = ${param_count}")
            params.append(case.assigned_to)
            param_count += 1

        if not updates:
            raise HTTPException(status_code=400, detail="No updates provided")

        updates.append("updated_at = NOW()")
        params.append(case_id)

        query = f"""
            UPDATE er_cases
            SET {', '.join(updates)}
            WHERE id = ${param_count}
            RETURNING id, case_number, title, description, status, created_by, assigned_to, created_at, updated_at, closed_at
        """

        row = await conn.fetchrow(query, *params)

        if not row:
            raise HTTPException(status_code=404, detail="Case not found")

        # Get document count
        doc_count = await conn.fetchval(
            "SELECT COUNT(*) FROM er_case_documents WHERE case_id = $1",
            case_id,
        )

        # Log audit
        await log_audit(
            conn,
            str(case_id),
            str(current_user.id),
            "case_updated",
            "case",
            str(case_id),
            case.model_dump(exclude_none=True),
            request.client.host if request.client else None,
        )

        return ERCaseResponse(
            id=row["id"],
            case_number=row["case_number"],
            title=row["title"],
            description=row["description"],
            status=row["status"],
            created_by=row["created_by"],
            assigned_to=row["assigned_to"],
            document_count=doc_count or 0,
            created_at=row["created_at"],
            updated_at=row["updated_at"],
            closed_at=row["closed_at"],
        )


@router.delete("/{case_id}")
async def delete_case(
    case_id: UUID,
    request: Request,
    current_user=Depends(require_admin_or_client),
):
    """Delete a case and all associated data."""
    async with get_connection() as conn:
        # Get case info for audit log before deletion
        case = await conn.fetchrow(
            "SELECT case_number, title FROM er_cases WHERE id = $1",
            case_id,
        )

        if not case:
            raise HTTPException(status_code=404, detail="Case not found")

        # Delete case (cascades to documents, chunks, analysis)
        await conn.execute("DELETE FROM er_cases WHERE id = $1", case_id)

        # Log audit (case_id is null since case is deleted)
        await log_audit(
            conn,
            None,
            str(current_user.id),
            "case_deleted",
            "case",
            str(case_id),
            {"case_number": case["case_number"], "title": case["title"]},
            request.client.host if request.client else None,
        )

        return {"status": "deleted", "case_id": str(case_id)}


# ===========================================
# Documents
# ===========================================

@router.post("/{case_id}/documents", response_model=ERDocumentUploadResponse)
async def upload_document(
    case_id: UUID,
    request: Request,
    file: UploadFile = File(...),
    document_type: str = Form("transcript"),
    current_user=Depends(require_admin_or_client),
):
    """Upload a document to a case. Triggers async processing."""
    # Validate case exists
    async with get_connection() as conn:
        case = await conn.fetchval("SELECT id FROM er_cases WHERE id = $1", case_id)
        if not case:
            raise HTTPException(status_code=404, detail="Case not found")

    # Validate document type
    valid_types = ["transcript", "policy", "email", "other"]
    if document_type not in valid_types:
        raise HTTPException(
            status_code=400,
            detail=f"Invalid document_type. Must be one of: {valid_types}",
        )

    # Validate file type
    allowed_extensions = {".pdf", ".docx", ".doc", ".txt", ".csv", ".json"}
    filename = file.filename or "document"
    ext = "." + filename.rsplit(".", 1)[-1].lower() if "." in filename else ""
    if ext not in allowed_extensions:
        raise HTTPException(
            status_code=400,
            detail=f"Unsupported file type. Allowed: {allowed_extensions}",
        )

    # Read file content
    file_bytes = await file.read()
    file_size = len(file_bytes)

    # Upload to storage
    storage = get_storage()
    file_path = await storage.upload_file(
        file_bytes,
        f"er-documents/{case_id}/{filename}",
    )

    # Create document record
    async with get_connection() as conn:
        row = await conn.fetchrow(
            """
            INSERT INTO er_case_documents
            (case_id, document_type, filename, file_path, mime_type, file_size, uploaded_by)
            VALUES ($1, $2, $3, $4, $5, $6, $7)
            RETURNING id, case_id, document_type, filename, file_path, mime_type, file_size,
                      pii_scrubbed, processing_status, processing_error, parsed_at, uploaded_by, created_at
            """,
            case_id,
            document_type,
            filename,
            file_path,
            file.content_type,
            file_size,
            str(current_user.id),
        )

        # Log audit
        await log_audit(
            conn,
            str(case_id),
            str(current_user.id),
            "document_uploaded",
            "document",
            str(row["id"]),
            {"filename": filename, "document_type": document_type, "file_size": file_size},
            request.client.host if request.client else None,
        )

        # Queue Celery task for processing (with sync fallback)
        task_id = None
        celery_available = False
        try:
            from ..workers.tasks.er_document_processing import process_er_document
            # Check if Celery broker AND workers are available
            from ..workers.celery_app import celery_app
            ping_responses = celery_app.control.ping(timeout=1)
            if not ping_responses:
                raise RuntimeError("No Celery workers responded to ping")
            task = process_er_document.delay(str(row["id"]), str(case_id))
            task_id = task.id
            celery_available = True
            logger.info(f"Queued document {row['id']} for Celery processing, task_id={task_id}")
        except Exception as e:
            logger.warning(f"Celery unavailable ({e}), will process document synchronously")

        # Fallback: process synchronously if Celery not available
        if not celery_available:
            try:
                from ..workers.tasks.er_document_processing import _process_document
                logger.info(f"Starting synchronous processing for document {row['id']}")
                result = await _process_document(str(row["id"]), str(case_id))
                logger.info(f"Document {row['id']} processed successfully: {result}")
                # Refresh document data after processing
                row = await conn.fetchrow(
                    """
                    SELECT id, case_id, document_type, filename, file_path, mime_type, file_size,
                           pii_scrubbed, processing_status, processing_error, parsed_at, uploaded_by, created_at
                    FROM er_case_documents WHERE id = $1
                    """,
                    row["id"],
                )
            except Exception as sync_error:
                logger.error(f"Document {row['id']} processing failed: {sync_error}", exc_info=True)
                await conn.execute(
                    """UPDATE er_case_documents
                       SET processing_status = 'failed', processing_error = $1
                       WHERE id = $2""",
                    str(sync_error),
                    row["id"],
                )
                # Refresh document data after failure
                row = await conn.fetchrow(
                    """
                    SELECT id, case_id, document_type, filename, file_path, mime_type, file_size,
                           pii_scrubbed, processing_status, processing_error, parsed_at, uploaded_by, created_at
                    FROM er_case_documents WHERE id = $1
                    """,
                    row["id"],
                )

        document = ERDocumentResponse(
            id=row["id"],
            case_id=row["case_id"],
            document_type=row["document_type"],
            filename=row["filename"],
            mime_type=row["mime_type"],
            file_size=row["file_size"],
            pii_scrubbed=row["pii_scrubbed"],
            processing_status=row["processing_status"],
            processing_error=row["processing_error"],
            parsed_at=row["parsed_at"],
            uploaded_by=row["uploaded_by"],
            created_at=row["created_at"],
        )

        return ERDocumentUploadResponse(
            document=document,
            task_id=task_id,
            message="Document uploaded and queued for processing",
        )


@router.get("/{case_id}/documents", response_model=list[ERDocumentResponse])
async def list_documents(
    case_id: UUID,
    current_user=Depends(require_admin_or_client),
):
    """List all documents in a case."""
    async with get_connection() as conn:
        rows = await conn.fetch(
            """
            SELECT id, case_id, document_type, filename, mime_type, file_size,
                   pii_scrubbed, processing_status, processing_error, parsed_at, uploaded_by, created_at
            FROM er_case_documents
            WHERE case_id = $1
            ORDER BY created_at DESC
            """,
            case_id,
        )

        return [
            ERDocumentResponse(
                id=row["id"],
                case_id=row["case_id"],
                document_type=row["document_type"],
                filename=row["filename"],
                mime_type=row["mime_type"],
                file_size=row["file_size"],
                pii_scrubbed=row["pii_scrubbed"],
                processing_status=row["processing_status"],
                processing_error=row["processing_error"],
                parsed_at=row["parsed_at"],
                uploaded_by=row["uploaded_by"],
                created_at=row["created_at"],
            )
            for row in rows
        ]


@router.get("/{case_id}/documents/{doc_id}", response_model=ERDocumentResponse)
async def get_document(
    case_id: UUID,
    doc_id: UUID,
    current_user=Depends(require_admin_or_client),
):
    """Get document details."""
    async with get_connection() as conn:
        row = await conn.fetchrow(
            """
            SELECT id, case_id, document_type, filename, mime_type, file_size,
                   pii_scrubbed, processing_status, processing_error, parsed_at, uploaded_by, created_at
            FROM er_case_documents
            WHERE id = $1 AND case_id = $2
            """,
            doc_id,
            case_id,
        )

        if not row:
            raise HTTPException(status_code=404, detail="Document not found")

        return ERDocumentResponse(
            id=row["id"],
            case_id=row["case_id"],
            document_type=row["document_type"],
            filename=row["filename"],
            mime_type=row["mime_type"],
            file_size=row["file_size"],
            pii_scrubbed=row["pii_scrubbed"],
            processing_status=row["processing_status"],
            processing_error=row["processing_error"],
            parsed_at=row["parsed_at"],
            uploaded_by=row["uploaded_by"],
            created_at=row["created_at"],
        )


@router.post("/{case_id}/documents/{doc_id}/reprocess", response_model=TaskStatusResponse)
async def reprocess_document(
    case_id: UUID,
    doc_id: UUID,
    request: Request,
    current_user=Depends(require_admin_or_client),
):
    """Manually reprocess a document that is stuck or failed."""
    async with get_connection() as conn:
        doc = await conn.fetchrow(
            "SELECT id, processing_status FROM er_case_documents WHERE id = $1 AND case_id = $2",
            doc_id,
            case_id,
        )

        if not doc:
            raise HTTPException(status_code=404, detail="Document not found")

        if doc["processing_status"] == "processing":
            raise HTTPException(status_code=400, detail="Document is already being processed")

        # Reset status to pending
        await conn.execute(
            "UPDATE er_case_documents SET processing_status = 'pending', processing_error = NULL WHERE id = $1",
            doc_id,
        )

        # Delete existing chunks (will be regenerated)
        await conn.execute(
            "DELETE FROM er_evidence_chunks WHERE document_id = $1",
            doc_id,
        )

        await log_audit(
            conn,
            str(case_id),
            str(current_user.id),
            "document_reprocessed",
            "document",
            str(doc_id),
            {},
            request.client.host if request.client else None,
        )

    # Queue for processing
    try:
        from ..workers.tasks.er_document_processing import process_er_document
        from ..workers.celery_app import celery_app
        ping_responses = celery_app.control.ping(timeout=1)
        if not ping_responses:
            raise RuntimeError("No Celery workers responded to ping")
        task = process_er_document.delay(str(doc_id), str(case_id))
        return TaskStatusResponse(
            task_id=task.id,
            status="queued",
            message="Document queued for reprocessing",
        )
    except Exception as e:
        logger.warning(f"Celery unavailable ({e}), processing synchronously")
        # Fallback to synchronous processing
        try:
            from ..workers.tasks.er_document_processing import _process_document
            await _process_document(str(doc_id), str(case_id))
            return TaskStatusResponse(
                task_id=None,
                status="completed",
                message="Document reprocessed successfully",
            )
        except Exception as sync_error:
            logger.error(f"Reprocess failed: {sync_error}", exc_info=True)
            async with get_connection() as err_conn:
                await err_conn.execute(
                    """UPDATE er_case_documents
                       SET processing_status = 'failed', processing_error = $1
                       WHERE id = $2""",
                    str(sync_error),
                    doc_id,
                )
            return TaskStatusResponse(
                task_id=None,
                status="failed",
                message=f"Reprocessing failed: {str(sync_error)}",
            )


@router.post("/{case_id}/documents/reprocess-all")
async def reprocess_all_documents(
    case_id: UUID,
    request: Request,
    current_user=Depends(require_admin_or_client),
):
    """Reprocess all pending or failed documents in a case."""
    async with get_connection() as conn:
        # Find all documents that need processing
        docs = await conn.fetch(
            """
            SELECT id, filename, processing_status
            FROM er_case_documents
            WHERE case_id = $1 AND processing_status IN ('pending', 'failed')
            """,
            case_id,
        )

        if not docs:
            return {
                "status": "no_action",
                "message": "No pending or failed documents to reprocess",
                "processed": 0,
            }

        results = []
        for doc in docs:
            doc_id = doc["id"]
            try:
                # Reset status
                await conn.execute(
                    "UPDATE er_case_documents SET processing_status = 'pending', processing_error = NULL WHERE id = $1",
                    doc_id,
                )
                # Delete existing chunks
                await conn.execute("DELETE FROM er_evidence_chunks WHERE document_id = $1", doc_id)

                # Process synchronously (most reliable)
                from ..workers.tasks.er_document_processing import _process_document
                await _process_document(str(doc_id), str(case_id))
                results.append({"id": str(doc_id), "filename": doc["filename"], "status": "completed"})
            except Exception as e:
                logger.error(f"Failed to reprocess document {doc_id}: {e}", exc_info=True)
                await conn.execute(
                    "UPDATE er_case_documents SET processing_status = 'failed', processing_error = $1 WHERE id = $2",
                    str(e),
                    doc_id,
                )
                results.append({"id": str(doc_id), "filename": doc["filename"], "status": "failed", "error": str(e)})

        await log_audit(
            conn,
            str(case_id),
            str(current_user.id),
            "documents_batch_reprocessed",
            "case",
            str(case_id),
            {"count": len(docs), "results": results},
            request.client.host if request.client else None,
        )

        completed = sum(1 for r in results if r["status"] == "completed")
        return {
            "status": "completed",
            "message": f"Reprocessed {completed}/{len(docs)} documents",
            "processed": completed,
            "total": len(docs),
            "results": results,
        }


@router.delete("/{case_id}/documents/{doc_id}")
async def delete_document(
    case_id: UUID,
    doc_id: UUID,
    request: Request,
    current_user=Depends(require_admin_or_client),
):
    """Delete a document and its chunks."""
    async with get_connection() as conn:
        doc = await conn.fetchrow(
            "SELECT filename FROM er_case_documents WHERE id = $1 AND case_id = $2",
            doc_id,
            case_id,
        )

        if not doc:
            raise HTTPException(status_code=404, detail="Document not found")

        await conn.execute("DELETE FROM er_case_documents WHERE id = $1", doc_id)

        await log_audit(
            conn,
            str(case_id),
            str(current_user.id),
            "document_deleted",
            "document",
            str(doc_id),
            {"filename": doc["filename"]},
            request.client.host if request.client else None,
        )

        return {"status": "deleted", "document_id": str(doc_id)}


# ===========================================
# Analysis
# ===========================================

@router.post("/{case_id}/analysis/timeline", response_model=TaskStatusResponse)
async def generate_timeline(
    case_id: UUID,
    request: Request,
    current_user=Depends(require_admin_or_client),
):
    """Generate timeline analysis. Queues async task or runs synchronously."""
    async with get_connection() as conn:
        # Verify case exists and has documents
        doc_count = await conn.fetchval(
            "SELECT COUNT(*) FROM er_case_documents WHERE case_id = $1 AND processing_status = 'completed'",
            case_id,
        )

        if not doc_count:
            raise HTTPException(
                status_code=400,
                detail="No processed documents found. Upload and process documents first.",
            )

        await log_audit(
            conn,
            str(case_id),
            str(current_user.id),
            "analysis_requested",
            "timeline",
            None,
            {},
            request.client.host if request.client else None,
        )

    # Try to queue analysis task via Celery, fall back to sync
    celery_available = False
    try:
        from ..workers.tasks.er_analysis import run_timeline_analysis
        from ..workers.celery_app import celery_app
        ping_responses = celery_app.control.ping(timeout=1)
        if not ping_responses:
            raise RuntimeError("No Celery workers responded to ping")
        task = run_timeline_analysis.delay(str(case_id))
        celery_available = True
        logger.info(f"Queued timeline analysis for case {case_id}, task_id={task.id}")
        return TaskStatusResponse(
            task_id=task.id,
            status="queued",
            message="Timeline analysis queued",
        )
    except Exception as e:
        logger.warning(f"Celery unavailable ({e}), running timeline analysis synchronously")

    # Fallback: run synchronously
    if not celery_available:
        try:
            from ..workers.tasks.er_analysis import _run_timeline_analysis
            logger.info(f"Starting synchronous timeline analysis for case {case_id}")
            result = await _run_timeline_analysis(str(case_id))
            logger.info(f"Timeline analysis completed for case {case_id}: {result}")
            return TaskStatusResponse(
                task_id=None,
                status="completed",
                message=f"Timeline analysis completed: {result.get('events_found', 0)} events found",
            )
        except Exception as sync_error:
            logger.error(f"Timeline analysis failed for case {case_id}: {sync_error}", exc_info=True)
            raise HTTPException(status_code=500, detail=f"Timeline analysis failed: {str(sync_error)}")


@router.get("/{case_id}/analysis/timeline")
async def get_timeline(
    case_id: UUID,
    current_user=Depends(require_admin_or_client),
):
    """Get cached timeline analysis."""
    async with get_connection() as conn:
        row = await conn.fetchrow(
            """
            SELECT analysis_data, source_documents, generated_at
            FROM er_case_analysis
            WHERE case_id = $1 AND analysis_type = 'timeline'
            """,
            case_id,
        )

        if not row:
            raise HTTPException(status_code=404, detail="Timeline analysis not found. Generate it first.")

        # Handle case where JSONB might be returned as string
        analysis = row["analysis_data"]
        if isinstance(analysis, str):
            analysis = json.loads(analysis)

        source_docs = row["source_documents"]
        if isinstance(source_docs, str):
            source_docs = json.loads(source_docs)

        return {
            "analysis": analysis,
            "source_documents": source_docs,
            "generated_at": row["generated_at"],
        }


@router.post("/{case_id}/analysis/discrepancies", response_model=TaskStatusResponse)
async def generate_discrepancies(
    case_id: UUID,
    request: Request,
    current_user=Depends(require_admin_or_client),
):
    """Generate discrepancy analysis. Queues async task or runs synchronously."""
    async with get_connection() as conn:
        doc_count = await conn.fetchval(
            "SELECT COUNT(*) FROM er_case_documents WHERE case_id = $1 AND processing_status = 'completed'",
            case_id,
        )

        if not doc_count:
            raise HTTPException(
                status_code=400,
                detail="No processed documents found.",
            )

        await log_audit(
            conn,
            str(case_id),
            str(current_user.id),
            "analysis_requested",
            "discrepancies",
            None,
            {},
            request.client.host if request.client else None,
        )

    # Try to queue analysis task via Celery, fall back to sync
    celery_available = False
    try:
        from ..workers.tasks.er_analysis import run_discrepancy_analysis
        from ..workers.celery_app import celery_app
        ping_responses = celery_app.control.ping(timeout=1)
        if not ping_responses:
            raise RuntimeError("No Celery workers responded to ping")
        task = run_discrepancy_analysis.delay(str(case_id))
        celery_available = True
        logger.info(f"Queued discrepancy analysis for case {case_id}, task_id={task.id}")
        return TaskStatusResponse(
            task_id=task.id,
            status="queued",
            message="Discrepancy analysis queued",
        )
    except Exception as e:
        logger.warning(f"Celery unavailable ({e}), running discrepancy analysis synchronously")

    # Fallback: run synchronously
    if not celery_available:
        try:
            from ..workers.tasks.er_analysis import _run_discrepancy_analysis
            logger.info(f"Starting synchronous discrepancy analysis for case {case_id}")
            result = await _run_discrepancy_analysis(str(case_id))
            logger.info(f"Discrepancy analysis completed for case {case_id}: {result}")
            return TaskStatusResponse(
                task_id=None,
                status="completed",
                message=f"Discrepancy analysis completed: {result.get('discrepancies_found', 0)} discrepancies found",
            )
        except Exception as sync_error:
            logger.error(f"Discrepancy analysis failed for case {case_id}: {sync_error}", exc_info=True)
            raise HTTPException(status_code=500, detail=f"Discrepancy analysis failed: {str(sync_error)}")


@router.get("/{case_id}/analysis/discrepancies")
async def get_discrepancies(
    case_id: UUID,
    current_user=Depends(require_admin_or_client),
):
    """Get cached discrepancy analysis."""
    async with get_connection() as conn:
        row = await conn.fetchrow(
            """
            SELECT analysis_data, source_documents, generated_at
            FROM er_case_analysis
            WHERE case_id = $1 AND analysis_type = 'discrepancies'
            """,
            case_id,
        )

        if not row:
            raise HTTPException(status_code=404, detail="Discrepancy analysis not found.")

        analysis = row["analysis_data"]
        if isinstance(analysis, str):
            analysis = json.loads(analysis)

        source_docs = row["source_documents"]
        if isinstance(source_docs, str):
            source_docs = json.loads(source_docs)

        return {
            "analysis": analysis,
            "source_documents": source_docs,
            "generated_at": row["generated_at"],
        }


@router.post("/{case_id}/analysis/policy-check", response_model=TaskStatusResponse)
async def run_policy_check(
    case_id: UUID,
    request: Request,
    current_user=Depends(require_admin_or_client),
):
    """Run policy violation check against all company policies. Queues async task or runs synchronously."""
    async with get_connection() as conn:
        # Verify we have evidence documents
        evidence_count = await conn.fetchval(
            """
            SELECT COUNT(*) FROM er_case_documents
            WHERE case_id = $1 AND document_type != 'policy' AND processing_status = 'completed'
            """,
            case_id,
        )

        if not evidence_count:
            raise HTTPException(
                status_code=400,
                detail="No evidence documents found.",
            )

        await log_audit(
            conn,
            str(case_id),
            str(current_user.id),
            "analysis_requested",
            "policy_check",
            None,
            {},
            request.client.host if request.client else None,
        )

    # Try to queue analysis task via Celery, fall back to sync
    celery_available = False
    try:
        from ..workers.tasks.er_analysis import run_policy_check as run_policy_check_task
        from ..workers.celery_app import celery_app
        ping_responses = celery_app.control.ping(timeout=1)
        if not ping_responses:
            raise RuntimeError("No Celery workers responded to ping")
        task = run_policy_check_task.delay(str(case_id))
        celery_available = True
        logger.info(f"Queued policy check for case {case_id}, task_id={task.id}")
        return TaskStatusResponse(
            task_id=task.id,
            status="queued",
            message="Policy check queued",
        )
    except Exception as e:
        logger.warning(f"Celery unavailable ({e}), running policy check synchronously")

    # Fallback: run synchronously
    if not celery_available:
        try:
            from ..workers.tasks.er_analysis import _run_policy_check
            logger.info(f"Starting synchronous policy check for case {case_id}")
            result = await _run_policy_check(str(case_id))
            logger.info(f"Policy check completed for case {case_id}: {result}")
            return TaskStatusResponse(
                task_id=None,
                status="completed",
                message=f"Policy check completed: {result.get('violations_found', 0)} violations found",
            )
        except Exception as sync_error:
            logger.error(f"Policy check failed for case {case_id}: {sync_error}", exc_info=True)
            raise HTTPException(status_code=500, detail=f"Policy check failed: {str(sync_error)}")


@router.get("/{case_id}/analysis/policy-check")
async def get_policy_check(
    case_id: UUID,
    current_user=Depends(require_admin_or_client),
):
    """Get cached policy check analysis."""
    async with get_connection() as conn:
        row = await conn.fetchrow(
            """
            SELECT analysis_data, source_documents, generated_at
            FROM er_case_analysis
            WHERE case_id = $1 AND analysis_type = 'policy_check'
            """,
            case_id,
        )

        if not row:
            raise HTTPException(status_code=404, detail="Policy check not found.")

        analysis = row["analysis_data"]
        if isinstance(analysis, str):
            analysis = json.loads(analysis)

        source_docs = row["source_documents"]
        if isinstance(source_docs, str):
            source_docs = json.loads(source_docs)

        return {
            "analysis": analysis,
            "source_documents": source_docs,
            "generated_at": row["generated_at"],
        }


# ===========================================
# Evidence Search (RAG)
# ===========================================

@router.post("/{case_id}/search", response_model=EvidenceSearchResponse)
async def search_evidence(
    case_id: UUID,
    search: EvidenceSearchRequest,
    current_user=Depends(require_admin_or_client),
):
    """Search case evidence using semantic similarity."""
    settings = get_settings()

    from ..services.embedding_service import EmbeddingService
    from ..services.rag_service import RAGService

    embedding_service = EmbeddingService(
        api_key=settings.gemini_api_key,
        vertex_project=settings.vertex_project,
        vertex_location=settings.vertex_location,
    )
    rag_service = RAGService(embedding_service)

    async with get_connection() as conn:
        results = await rag_service.search_evidence(
            case_id=str(case_id),
            query=search.query,
            conn=conn,
            top_k=search.top_k,
        )

        total_chunks = await rag_service.get_total_chunks(str(case_id), conn)

        return EvidenceSearchResponse(
            results=[
                EvidenceSearchResult(
                    chunk_id=r["chunk_id"],
                    content=r["content"],
                    speaker=r["speaker"],
                    source_file=r["source_file"],
                    document_type=r["document_type"],
                    page_number=r["page_number"],
                    line_range=r["line_range"],
                    similarity=r["similarity"],
                    metadata=r["metadata"],
                )
                for r in results
            ],
            query=search.query,
            total_chunks=total_chunks,
        )


# ===========================================
# Reports
# ===========================================

@router.post("/{case_id}/reports/summary", response_model=TaskStatusResponse)
async def generate_summary_report(
    case_id: UUID,
    request: Request,
    current_user=Depends(require_admin_or_client),
):
    """Generate investigation summary report. Queues async task or runs synchronously."""
    async with get_connection() as conn:
        await log_audit(
            conn,
            str(case_id),
            str(current_user.id),
            "report_requested",
            "summary",
            None,
            {},
            request.client.host if request.client else None,
        )

    # Try to queue task via Celery, fall back to sync
    celery_available = False
    try:
        from ..workers.tasks.er_analysis import generate_summary_report as generate_summary_task
        from ..workers.celery_app import celery_app
        ping_responses = celery_app.control.ping(timeout=1)
        if not ping_responses:
            raise RuntimeError("No Celery workers responded to ping")
        task = generate_summary_task.delay(str(case_id), str(current_user.id))
        celery_available = True
        logger.info(f"Queued summary report for case {case_id}, task_id={task.id}")
        return TaskStatusResponse(
            task_id=task.id,
            status="queued",
            message="Summary report generation queued",
        )
    except Exception as e:
        logger.warning(f"Celery unavailable ({e}), generating summary report synchronously")

    # Fallback: run synchronously
    if not celery_available:
        try:
            from ..workers.tasks.er_analysis import _generate_summary_report
            logger.info(f"Starting synchronous summary report generation for case {case_id}")
            result = await _generate_summary_report(str(case_id), str(current_user.id))
            logger.info(f"Summary report generated for case {case_id}: {result}")
            return TaskStatusResponse(
                task_id=None,
                status="completed",
                message="Summary report generated successfully",
            )
        except Exception as sync_error:
            logger.error(f"Summary report generation failed for case {case_id}: {sync_error}", exc_info=True)
            raise HTTPException(status_code=500, detail=f"Summary report generation failed: {str(sync_error)}")


@router.post("/{case_id}/reports/determination", response_model=TaskStatusResponse)
async def generate_determination_letter(
    case_id: UUID,
    report_request: ReportGenerateRequest,
    request: Request,
    current_user=Depends(require_admin_or_client),
):
    """Generate determination letter. Queues async task or runs synchronously."""
    if not report_request.determination:
        raise HTTPException(
            status_code=400,
            detail="Determination is required (substantiated, unsubstantiated, inconclusive)",
        )

    valid_determinations = ["substantiated", "unsubstantiated", "inconclusive"]
    if report_request.determination not in valid_determinations:
        raise HTTPException(
            status_code=400,
            detail=f"Invalid determination. Must be one of: {valid_determinations}",
        )

    async with get_connection() as conn:
        await log_audit(
            conn,
            str(case_id),
            str(current_user.id),
            "report_requested",
            "determination",
            None,
            {"determination": report_request.determination},
            request.client.host if request.client else None,
        )

    # Try to queue task via Celery, fall back to sync
    celery_available = False
    try:
        from ..workers.tasks.er_analysis import generate_determination_letter as generate_determination_task
        from ..workers.celery_app import celery_app
        ping_responses = celery_app.control.ping(timeout=1)
        if not ping_responses:
            raise RuntimeError("No Celery workers responded to ping")
        task = generate_determination_task.delay(
            str(case_id),
            report_request.determination,
            str(current_user.id),
        )
        celery_available = True
        logger.info(f"Queued determination letter for case {case_id}, task_id={task.id}")
        return TaskStatusResponse(
            task_id=task.id,
            status="queued",
            message="Determination letter generation queued",
        )
    except Exception as e:
        logger.warning(f"Celery unavailable ({e}), generating determination letter synchronously")

    # Fallback: run synchronously
    if not celery_available:
        try:
            from ..workers.tasks.er_analysis import _generate_determination_letter
            logger.info(f"Starting synchronous determination letter generation for case {case_id}")
            result = await _generate_determination_letter(
                str(case_id),
                report_request.determination,
                str(current_user.id),
            )
            logger.info(f"Determination letter generated for case {case_id}: {result}")
            return TaskStatusResponse(
                task_id=None,
                status="completed",
                message="Determination letter generated successfully",
            )
        except Exception as sync_error:
            logger.error(f"Determination letter generation failed for case {case_id}: {sync_error}", exc_info=True)
            raise HTTPException(status_code=500, detail=f"Determination letter generation failed: {str(sync_error)}")


@router.get("/{case_id}/reports/{report_type}")
async def get_report(
    case_id: UUID,
    report_type: str,
    current_user=Depends(require_admin_or_client),
):
    """Get generated report."""
    valid_types = ["summary", "determination"]
    if report_type not in valid_types:
        raise HTTPException(
            status_code=400,
            detail=f"Invalid report type. Must be one of: {valid_types}",
        )

    async with get_connection() as conn:
        row = await conn.fetchrow(
            """
            SELECT analysis_data, source_documents, generated_at
            FROM er_case_analysis
            WHERE case_id = $1 AND analysis_type = $2
            """,
            case_id,
            report_type,
        )

        if not row:
            raise HTTPException(status_code=404, detail=f"{report_type.title()} report not found.")

        return {
            "report_type": report_type,
            "content": row["analysis_data"].get("content", ""),
            "generated_at": row["generated_at"],
            "source_documents": row["source_documents"],
        }


# ===========================================
# Audit Log
# ===========================================

@router.get("/{case_id}/audit-log", response_model=AuditLogResponse)
async def get_audit_log(
    case_id: UUID,
    limit: int = 100,
    offset: int = 0,
    current_user=Depends(require_admin_or_client),
):
    """Get audit log for a case."""
    async with get_connection() as conn:
        rows = await conn.fetch(
            """
            SELECT id, case_id, user_id, action, entity_type, entity_id, details, ip_address, created_at
            FROM er_audit_log
            WHERE case_id = $1
            ORDER BY created_at DESC
            LIMIT $2 OFFSET $3
            """,
            case_id,
            limit,
            offset,
        )

        total = await conn.fetchval(
            "SELECT COUNT(*) FROM er_audit_log WHERE case_id = $1",
            case_id,
        )

        entries = [
            AuditLogEntry(
                id=row["id"],
                case_id=row["case_id"],
                user_id=row["user_id"],
                action=row["action"],
                entity_type=row["entity_type"],
                entity_id=row["entity_id"],
                details=row["details"],
                ip_address=row["ip_address"],
                created_at=row["created_at"],
            )
            for row in rows
        ]

        return AuditLogResponse(entries=entries, total=total or 0)
