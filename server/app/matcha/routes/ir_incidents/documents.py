"""Document upload / list / download / delete for IR Incidents."""
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
from ._shared import (
    MAX_DOCUMENT_BYTES,
    log_audit,
    read_upload_capped,
    validate_upload_name,
)

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

    safe_name, file_ext, stored_mime = validate_upload_name(file.filename)
    content = await read_upload_capped(file, MAX_DOCUMENT_BYTES)
    file_size = len(content)

    # Store the object under a generated key (no client input in the S3 path) so a
    # crafted filename can't traverse the prefix and two files with the same name
    # on one incident can't collide/overwrite each other. The human-readable name
    # is kept only in the DB row. The content type is derived from the validated
    # extension, never the client-supplied value.
    #
    # Private bucket: incident documents are injury photos, witness statements and
    # medical forms — they must never be reachable on the public CloudFront
    # distribution. Reads go through the presigned /download route below.
    storage = get_storage()
    try:
        file_path = await storage.upload_private_file(
            content,
            safe_name,
            prefix=f"ir-incidents/{incident_id}",
            content_type=stored_mime,
        )
    except Exception as e:
        logger.error(f"Failed to upload IR document for incident {incident_id}: {e}")
        raise HTTPException(status_code=500, detail="Failed to upload file. Please try again.")

    async with get_connection() as conn:
        row = await conn.fetchrow(
            """
            INSERT INTO ir_incident_documents (
                incident_id, document_type, filename, file_path, mime_type, file_size,
                uploaded_by, uploaded_via
            )
            VALUES ($1, $2, $3, $4, $5, $6, $7, 'authed')
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
                uploaded_via=row["uploaded_via"],
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
                uploaded_via=row["uploaded_via"],
                created_at=row["created_at"],
            )
            for row in rows
        ]


@router.get("/{incident_id}/documents/{document_id}/download")
async def download_document(
    incident_id: UUID,
    document_id: UUID,
    current_user=Depends(require_admin_or_client),
):
    """Return a short-lived presigned URL for a document.

    Documents live in the private bucket, so this is the only read path — the
    stored s3:// URI is never handed to the client.
    """
    company_id = await get_client_company_id(current_user)
    if company_id is None:
        raise HTTPException(status_code=404, detail="Document not found")

    async with get_connection() as conn:
        row = await conn.fetchrow(
            """SELECT d.file_path, d.filename
               FROM ir_incident_documents d
               JOIN ir_incidents i ON d.incident_id = i.id
               WHERE d.id = $1 AND d.incident_id = $2 AND i.company_id = $3""",
            str(document_id),
            str(incident_id),
            company_id,
        )
    if not row:
        raise HTTPException(status_code=404, detail="Document not found")

    url = get_storage().get_presigned_download_url(row["file_path"], expires_in=900)
    if not url:
        # Pre-fix rows hold a fabricated path that was never uploaded (the
        # upload call was never awaited), so there is no object to sign.
        raise HTTPException(status_code=404, detail="This file is no longer available.")
    return {"url": url, "filename": row["filename"]}


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
            await get_storage().delete_private_file(row["file_path"])
        except Exception:
            logger.warning(
                "[IR] storage delete failed for document %s (row removed anyway)", document_id
            )

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
