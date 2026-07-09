"""Document upload / list / delete for IR Incidents."""
import logging
import os
from uuid import UUID, uuid4

from fastapi import APIRouter, Depends, File, Form, HTTPException, Request, UploadFile

from app.database import get_connection
from app.core.services.storage import get_storage
from app.matcha.dependencies import require_admin_or_client, get_client_company_id
from app.matcha.models.ir_incident import (
    IRDocumentResponse,
    IRDocumentUploadResponse,
)

# log_audit currently lives in _legacy.py; will move to _shared.py in step 10.
from ._shared import log_audit

logger = logging.getLogger(__name__)

router = APIRouter()

# Max IR document size. Matches the voice-intake guard; keeps a single large
# upload from being buffered whole into memory unbounded.
MAX_DOCUMENT_BYTES = 25 * 1024 * 1024

# Server-derived MIME per allowed extension. We do NOT trust the client-supplied
# content_type for storage: a .png uploaded as text/html would be a stored-XSS
# vector if the object is ever served inline. The stored/served type is derived
# from the validated extension here.
_EXT_MIME = {
    ".pdf": "application/pdf",
    ".doc": "application/msword",
    ".docx": "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
    ".txt": "text/plain",
    ".png": "image/png",
    ".jpg": "image/jpeg",
    ".jpeg": "image/jpeg",
    ".gif": "image/gif",
    ".csv": "text/csv",
    ".json": "application/json",
}


@router.post("/{incident_id}/documents", response_model=IRDocumentUploadResponse)
async def upload_document(
    incident_id: UUID,
    request: Request,
    file: UploadFile = File(...),
    document_type: str = Form("other"),
    current_user=Depends(require_admin_or_client),
):
    """Upload a document to an incident."""
    company_id = await get_client_company_id(current_user)
    if company_id is None:
        raise HTTPException(status_code=404, detail="Incident not found")
    company_clause = "company_id = $2"

    async with get_connection() as conn:
        incident = await conn.fetchrow(
            f"SELECT id FROM ir_incidents WHERE id = $1 AND {company_clause}",
            str(incident_id),
            company_id,
        )
        if not incident:
            raise HTTPException(status_code=404, detail="Incident not found")

    valid_types = ["photo", "form", "statement", "other"]
    if document_type not in valid_types:
        raise HTTPException(status_code=400, detail=f"Invalid document type. Must be one of: {valid_types}")

    # Reduce the client filename to a bare basename before doing anything with it
    # (an attacker-controlled name can contain path separators / be absent).
    raw_name = file.filename or ""
    safe_name = os.path.basename(raw_name.replace("\\", "/")).strip() or "upload"
    _, ext = os.path.splitext(safe_name)
    file_ext = ext.lower()
    if file_ext not in _EXT_MIME:
        raise HTTPException(
            status_code=400,
            detail=f"File type not allowed. Allowed: {sorted(_EXT_MIME)}",
        )

    content = await file.read()
    file_size = len(content)
    if file_size == 0:
        raise HTTPException(status_code=400, detail="Uploaded file is empty.")
    if file_size > MAX_DOCUMENT_BYTES:
        raise HTTPException(
            status_code=413,
            detail=f"File too large. Max {MAX_DOCUMENT_BYTES // (1024 * 1024)} MB.",
        )

    # Store the object under a generated key (no client input in the S3 path) so a
    # crafted filename can't traverse the prefix and two files with the same name
    # on one incident can't collide/overwrite each other. The human-readable name
    # is kept only in the DB row. The content type is derived from the validated
    # extension, never the client-supplied value.
    stored_mime = _EXT_MIME[file_ext]
    file_path = f"ir-incidents/{incident_id}/{uuid4().hex}{file_ext}"

    storage = get_storage()
    try:
        storage.upload_file(content, file_path, stored_mime)
    except Exception as e:
        logger.error(f"Failed to upload IR document for incident {incident_id}: {e}")
        raise HTTPException(status_code=500, detail="Failed to upload file. Please try again.")

    async with get_connection() as conn:
        row = await conn.fetchrow(
            """
            INSERT INTO ir_incident_documents (
                incident_id, document_type, filename, file_path, mime_type, file_size, uploaded_by
            )
            VALUES ($1, $2, $3, $4, $5, $6, $7)
            RETURNING *
            """,
            str(incident_id),
            document_type,
            safe_name,
            file_path,
            stored_mime,
            file_size,
            str(current_user.id),
        )

        await log_audit(
            conn,
            str(incident_id),
            str(current_user.id),
            "document_uploaded",
            "document",
            str(row["id"]),
            {"filename": safe_name, "document_type": document_type},
            request.client.host if request.client else None,
        )

        return IRDocumentUploadResponse(
            document=IRDocumentResponse(
                id=row["id"],
                incident_id=row["incident_id"],
                document_type=row["document_type"],
                filename=row["filename"],
                mime_type=row["mime_type"],
                file_size=row["file_size"],
                uploaded_by=row["uploaded_by"],
                created_at=row["created_at"],
            ),
            message="Document uploaded successfully",
        )


@router.get("/{incident_id}/documents", response_model=list[IRDocumentResponse])
async def list_documents(
    incident_id: UUID,
    current_user=Depends(require_admin_or_client),
):
    """List all documents for an incident."""
    company_id = await get_client_company_id(current_user)
    if company_id is None:
        raise HTTPException(status_code=404, detail="Incident not found")
    company_clause = "company_id = $2"

    async with get_connection() as conn:
        incident = await conn.fetchrow(
            f"SELECT id FROM ir_incidents WHERE id = $1 AND {company_clause}",
            str(incident_id),
            company_id,
        )
        if not incident:
            raise HTTPException(status_code=404, detail="Incident not found")

        rows = await conn.fetch(
            """
            SELECT * FROM ir_incident_documents
            WHERE incident_id = $1
            ORDER BY created_at DESC
            """,
            str(incident_id),
        )

        return [
            IRDocumentResponse(
                id=row["id"],
                incident_id=row["incident_id"],
                document_type=row["document_type"],
                filename=row["filename"],
                mime_type=row["mime_type"],
                file_size=row["file_size"],
                uploaded_by=row["uploaded_by"],
                created_at=row["created_at"],
            )
            for row in rows
        ]


@router.delete("/{incident_id}/documents/{document_id}")
async def delete_document(
    incident_id: UUID,
    document_id: UUID,
    request: Request,
    current_user=Depends(require_admin_or_client),
):
    """Delete a document from an incident."""
    company_id = await get_client_company_id(current_user)
    if company_id is None:
        raise HTTPException(status_code=404, detail="Document not found")
    company_clause = "i.company_id = $3"

    async with get_connection() as conn:
        row = await conn.fetchrow(
            f"""SELECT d.id, d.filename, d.file_path
                FROM ir_incident_documents d
                JOIN ir_incidents i ON d.incident_id = i.id
                WHERE d.id = $1 AND d.incident_id = $2 AND {company_clause}""",
            str(document_id),
            str(incident_id),
            company_id,
        )
        if not row:
            raise HTTPException(status_code=404, detail="Document not found")

        try:
            storage = get_storage()
            storage.delete_file(row["file_path"])
        except Exception:
            pass  # Continue even if storage delete fails

        await conn.execute(
            "DELETE FROM ir_incident_documents WHERE id = $1",
            str(document_id),
        )

        await log_audit(
            conn,
            str(incident_id),
            str(current_user.id),
            "document_deleted",
            "document",
            str(document_id),
            {"filename": row["filename"]},
            request.client.host if request.client else None,
        )

        return {"message": "Document deleted successfully"}
