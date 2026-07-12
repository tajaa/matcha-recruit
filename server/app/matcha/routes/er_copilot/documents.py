"""ER case documents: upload, list, get, reprocess, delete."""
import asyncio
from uuid import UUID

from fastapi import APIRouter, HTTPException, Depends, UploadFile, File, Form, Request

from ....database import get_connection
from ...dependencies import require_admin_or_client, get_client_company_id
from ....core.models.auth import CurrentUser
from ....core.services.storage import get_storage
from ...models.er_case import (
    ERDocumentResponse,
    ERDocumentUploadResponse,
    TaskStatusResponse,
)

from ._shared import (
    logger,
    MAX_UPLOAD_SIZE,
    log_audit,
    _verify_case_company,
)

router = APIRouter()


@router.post("/{case_id}/documents", response_model=ERDocumentUploadResponse)
async def upload_document(
    case_id: UUID,
    request: Request,
    file: UploadFile = File(...),
    document_type: str = Form("transcript"),
    current_user: CurrentUser = Depends(require_admin_or_client),
):
    """Upload a document to a case. Triggers async processing."""
    company_id = await get_client_company_id(current_user)
    if company_id is None:
        raise HTTPException(status_code=404, detail="Case not found")

    # Validate case exists and belongs to company
    is_admin = current_user.role == "admin"
    async with get_connection() as conn:
        if is_admin:
            case = await conn.fetchval(
                "SELECT id FROM er_cases WHERE id = $1 AND (company_id = $2 OR company_id IS NULL)",
                case_id,
                company_id,
            )
        else:
            case = await conn.fetchval(
                "SELECT id FROM er_cases WHERE id = $1 AND company_id = $2",
                case_id,
                company_id,
            )
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

    if file_size > MAX_UPLOAD_SIZE:
        raise HTTPException(
            status_code=413,
            detail=f"File too large. Maximum size is {MAX_UPLOAD_SIZE // (1024 * 1024)}MB",
        )

    # Upload to storage
    storage = get_storage()
    # Private upload (s3:// URI, no CDN URL) — ER evidence must never be
    # world-fetchable by URL; all readers go through storage.download_file.
    file_path = await storage.upload_private_file(
        file_bytes,
        filename,
        prefix=f"er-documents/{case_id}",
        content_type=file.content_type,
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
            from app.workers.tasks.er_document_processing import process_er_document
            # Check if Celery broker AND workers are available
            from app.workers.celery_app import celery_app
            ping_responses = celery_app.control.ping(timeout=1)
            if not ping_responses:
                raise RuntimeError("No Celery workers responded to ping")
            task = process_er_document.delay(str(row["id"]), str(case_id))
            task_id = task.id
            celery_available = True
            logger.info(f"Queued document {row['id']} for Celery processing, task_id={task_id}")
        except Exception as e:
            logger.warning(f"Celery unavailable ({e}), will process document synchronously")

        # Fallback: process in background if Celery not available
        if not celery_available:
            async def _background_process(doc_id: str, c_id: str):
                """Process document in background, updating status on completion/failure."""
                try:
                    from app.workers.tasks.er_document_processing import _process_document
                    logger.info(f"Starting background processing for document {doc_id}")
                    result = await asyncio.wait_for(
                        _process_document(doc_id, c_id),
                        timeout=120.0,
                    )
                    logger.info(f"Document {doc_id} processed successfully: {result}")
                except asyncio.TimeoutError:
                    logger.error(f"Document {doc_id} processing timed out after 120s")
                    async with get_connection() as bg_conn:
                        await bg_conn.execute(
                            """UPDATE er_case_documents
                               SET processing_status = 'failed',
                                   processing_error = 'Processing timed out. Try a smaller document.'
                               WHERE id = $1::uuid AND processing_status = 'processing'""",
                            doc_id,
                        )
                except Exception as sync_error:
                    logger.error(f"Document {doc_id} processing failed: {sync_error}", exc_info=True)
                    error_detail = str(sync_error).strip() or "Document processing failed"
                    if len(error_detail) > 1000:
                        error_detail = error_detail[:997] + "..."
                    async with get_connection() as bg_conn:
                        await bg_conn.execute(
                            """UPDATE er_case_documents
                               SET processing_status = 'failed', processing_error = $1
                               WHERE id = $2::uuid""",
                            error_detail,
                            doc_id,
                        )

            asyncio.create_task(_background_process(str(row["id"]), str(case_id)))

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
    current_user: CurrentUser = Depends(require_admin_or_client),
):
    """List all documents in a case."""
    company_id = await get_client_company_id(current_user)
    if company_id is None:
        raise HTTPException(status_code=404, detail="Case not found")

    async with get_connection() as conn:
        await _verify_case_company(conn, case_id, company_id, current_user.role == "admin")
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
    current_user: CurrentUser = Depends(require_admin_or_client),
):
    """Get document details."""
    company_id = await get_client_company_id(current_user)
    if company_id is None:
        raise HTTPException(status_code=404, detail="Case not found")

    async with get_connection() as conn:
        await _verify_case_company(conn, case_id, company_id, current_user.role == "admin")
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
    current_user: CurrentUser = Depends(require_admin_or_client),
):
    """Manually reprocess a document that is stuck or failed."""
    company_id = await get_client_company_id(current_user)
    if company_id is None:
        raise HTTPException(status_code=404, detail="Case not found")

    async with get_connection() as conn:
        await _verify_case_company(conn, case_id, company_id, current_user.role == "admin")
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
        from app.workers.tasks.er_document_processing import process_er_document
        from app.workers.celery_app import celery_app
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
            from app.workers.tasks.er_document_processing import _process_document
            await _process_document(str(doc_id), str(case_id))
            return TaskStatusResponse(
                task_id=None,
                status="completed",
                message="Document reprocessed successfully",
            )
        except Exception as sync_error:
            logger.error(f"Reprocess failed: {sync_error}", exc_info=True)
            error_detail = str(sync_error).strip() or "Document reprocessing failed"
            if len(error_detail) > 1000:
                error_detail = error_detail[:997] + "..."
            async with get_connection() as err_conn:
                await err_conn.execute(
                    """UPDATE er_case_documents
                       SET processing_status = 'failed', processing_error = $1
                       WHERE id = $2""",
                    error_detail,
                    doc_id,
                )
            return TaskStatusResponse(
                task_id=None,
                status="failed",
                message="Reprocessing failed",
            )


@router.post("/{case_id}/documents/reprocess-all")
async def reprocess_all_documents(
    case_id: UUID,
    request: Request,
    current_user: CurrentUser = Depends(require_admin_or_client),
):
    """Reprocess all pending or failed documents in a case."""
    company_id = await get_client_company_id(current_user)
    if company_id is None:
        raise HTTPException(status_code=404, detail="Case not found")

    async with get_connection() as conn:
        await _verify_case_company(conn, case_id, company_id, current_user.role == "admin")
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
                from app.workers.tasks.er_document_processing import _process_document
                await _process_document(str(doc_id), str(case_id))
                results.append({"id": str(doc_id), "filename": doc["filename"], "status": "completed"})
            except Exception as e:
                logger.error(f"Failed to reprocess document {doc_id}: {e}", exc_info=True)
                error_detail = str(e).strip() or "Document processing failed"
                if len(error_detail) > 1000:
                    error_detail = error_detail[:997] + "..."
                await conn.execute(
                    "UPDATE er_case_documents SET processing_status = 'failed', processing_error = $1 WHERE id = $2",
                    error_detail,
                    doc_id,
                )
                results.append({"id": str(doc_id), "filename": doc["filename"], "status": "failed"})

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
    current_user: CurrentUser = Depends(require_admin_or_client),
):
    """Delete a document and its chunks."""
    company_id = await get_client_company_id(current_user)
    if company_id is None:
        raise HTTPException(status_code=404, detail="Case not found")

    async with get_connection() as conn:
        await _verify_case_company(conn, case_id, company_id, current_user.role == "admin")
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

