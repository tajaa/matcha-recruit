"""Document upload / list / delete for IR Incidents."""
import logging
from uuid import UUID

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

    allowed_extensions = {".pdf", ".doc", ".docx", ".txt", ".png", ".jpg", ".jpeg", ".gif", ".csv", ".json"}
    file_ext = "." + file.filename.split(".")[-1].lower() if "." in file.filename else ""
    if file_ext not in allowed_extensions:
        raise HTTPException(status_code=400, detail=f"File type not allowed. Allowed: {allowed_extensions}")

    content = await file.read()
    file_size = len(content)

    storage = get_storage()
    file_path = f"ir-incidents/{incident_id}/{file.filename}"

    try:
        storage.upload_file(content, file_path, file.content_type)
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
            file.filename,
            file_path,
            file.content_type,
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
            {"filename": file.filename, "document_type": document_type},
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
