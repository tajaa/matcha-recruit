"""ER Copilot API Routes.

Employee Relations Investigation management:
- Cases CRUD
- Document upload and processing
- AI analysis (timeline, discrepancies, policy check)
- Report generation
- Evidence search (RAG)
"""

import json
import secrets
from datetime import datetime, timezone
from typing import Optional
from uuid import UUID

from fastapi import APIRouter, HTTPException, Depends, UploadFile, File, Form, Request

from ..database import get_connection
from ..dependencies import require_admin
from ..config import get_settings
from ..services.storage import get_storage
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
    current_user=Depends(require_admin),
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
    current_user=Depends(require_admin),
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
    current_user=Depends(require_admin),
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
    current_user=Depends(require_admin),
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
    current_user=Depends(require_admin),
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
    current_user=Depends(require_admin),
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

        # Queue Celery task for processing
        task_id = None
        try:
            from ..workers.tasks.er_document_processing import process_er_document
            task = process_er_document.delay(str(row["id"]), str(case_id))
            task_id = task.id
        except Exception:
            # Celery not available, processing will need to be triggered manually
            pass

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
    current_user=Depends(require_admin),
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
    current_user=Depends(require_admin),
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


@router.delete("/{case_id}/documents/{doc_id}")
async def delete_document(
    case_id: UUID,
    doc_id: UUID,
    request: Request,
    current_user=Depends(require_admin),
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
    current_user=Depends(require_admin),
):
    """Generate timeline analysis. Queues async task."""
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

    # Queue analysis task
    try:
        from ..workers.tasks.er_analysis import run_timeline_analysis
        task = run_timeline_analysis.delay(str(case_id))
        return TaskStatusResponse(
            task_id=task.id,
            status="queued",
            message="Timeline analysis queued",
        )
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to queue task: {str(e)}")


@router.get("/{case_id}/analysis/timeline")
async def get_timeline(
    case_id: UUID,
    current_user=Depends(require_admin),
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

        return {
            "analysis": row["analysis_data"],
            "source_documents": row["source_documents"],
            "generated_at": row["generated_at"],
        }


@router.post("/{case_id}/analysis/discrepancies", response_model=TaskStatusResponse)
async def generate_discrepancies(
    case_id: UUID,
    request: Request,
    current_user=Depends(require_admin),
):
    """Generate discrepancy analysis. Queues async task."""
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

    try:
        from ..workers.tasks.er_analysis import run_discrepancy_analysis
        task = run_discrepancy_analysis.delay(str(case_id))
        return TaskStatusResponse(
            task_id=task.id,
            status="queued",
            message="Discrepancy analysis queued",
        )
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to queue task: {str(e)}")


@router.get("/{case_id}/analysis/discrepancies")
async def get_discrepancies(
    case_id: UUID,
    current_user=Depends(require_admin),
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

        return {
            "analysis": row["analysis_data"],
            "source_documents": row["source_documents"],
            "generated_at": row["generated_at"],
        }


@router.post("/{case_id}/analysis/policy-check", response_model=TaskStatusResponse)
async def run_policy_check(
    case_id: UUID,
    policy_document_id: UUID,
    request: Request,
    current_user=Depends(require_admin),
):
    """Run policy violation check. Queues async task."""
    async with get_connection() as conn:
        # Verify policy document exists and is type 'policy'
        policy_doc = await conn.fetchrow(
            """
            SELECT id FROM er_case_documents
            WHERE id = $1 AND case_id = $2 AND document_type = 'policy' AND processing_status = 'completed'
            """,
            policy_document_id,
            case_id,
        )

        if not policy_doc:
            raise HTTPException(
                status_code=400,
                detail="Policy document not found or not processed.",
            )

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
            str(policy_document_id),
            {},
            request.client.host if request.client else None,
        )

    try:
        from ..workers.tasks.er_analysis import run_policy_check as run_policy_check_task
        task = run_policy_check_task.delay(str(case_id), str(policy_document_id))
        return TaskStatusResponse(
            task_id=task.id,
            status="queued",
            message="Policy check queued",
        )
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to queue task: {str(e)}")


@router.get("/{case_id}/analysis/policy-check")
async def get_policy_check(
    case_id: UUID,
    current_user=Depends(require_admin),
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

        return {
            "analysis": row["analysis_data"],
            "source_documents": row["source_documents"],
            "generated_at": row["generated_at"],
        }


# ===========================================
# Evidence Search (RAG)
# ===========================================

@router.post("/{case_id}/search", response_model=EvidenceSearchResponse)
async def search_evidence(
    case_id: UUID,
    search: EvidenceSearchRequest,
    current_user=Depends(require_admin),
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
    current_user=Depends(require_admin),
):
    """Generate investigation summary report."""
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

    try:
        from ..workers.tasks.er_analysis import generate_summary_report as generate_summary_task
        task = generate_summary_task.delay(str(case_id), str(current_user.id))
        return TaskStatusResponse(
            task_id=task.id,
            status="queued",
            message="Summary report generation queued",
        )
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to queue task: {str(e)}")


@router.post("/{case_id}/reports/determination", response_model=TaskStatusResponse)
async def generate_determination_letter(
    case_id: UUID,
    report_request: ReportGenerateRequest,
    request: Request,
    current_user=Depends(require_admin),
):
    """Generate determination letter."""
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

    try:
        from ..workers.tasks.er_analysis import generate_determination_letter as generate_determination_task
        task = generate_determination_task.delay(
            str(case_id),
            report_request.determination,
            str(current_user.id),
        )
        return TaskStatusResponse(
            task_id=task.id,
            status="queued",
            message="Determination letter generation queued",
        )
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to queue task: {str(e)}")


@router.get("/{case_id}/reports/{report_type}")
async def get_report(
    case_id: UUID,
    report_type: str,
    current_user=Depends(require_admin),
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
    current_user=Depends(require_admin),
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
