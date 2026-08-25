"""Portal credential document upload (license/DEA/NPI/etc.)."""
import json

from fastapi import APIRouter, BackgroundTasks, Depends, File, HTTPException, Query, UploadFile

from app.database import get_connection
from app.matcha.dependencies import require_employee_record

router = APIRouter()

_MAX_CRED_UPLOAD = 10 * 1024 * 1024  # 10 MB
_ALLOWED_CRED_EXTS = {".pdf", ".png", ".jpg", ".jpeg", ".gif", ".tiff"}
_VALID_DOC_TYPES = {
    "medical_license", "dea", "npi", "board_cert", "malpractice",
    "health_clearance", "food_handler_card", "other",
}


def _cred_doc_response(row) -> dict:
    return {
        "id": str(row["id"]),
        "company_id": str(row["company_id"]),
        "employee_id": str(row["employee_id"]),
        "document_type": row["document_type"],
        "filename": row["filename"],
        "mime_type": row.get("mime_type"),
        "file_size": row.get("file_size"),
        "extraction_status": row.get("extraction_status", "pending"),
        "review_status": row.get("review_status", "pending"),
        "uploaded_via": row.get("uploaded_via", "portal"),
        "created_at": row["created_at"].isoformat() if row.get("created_at") else None,
    }


@router.post("/me/credential-documents")
async def portal_upload_credential_document(
    background_tasks: BackgroundTasks,
    file: UploadFile = File(...),
    document_type: str = Query(..., description="Document type"),
    employee: dict = Depends(require_employee_record),
):
    """Upload a credential document via the employee portal."""
    if document_type not in _VALID_DOC_TYPES:
        raise HTTPException(status_code=400, detail=f"Invalid document_type. Must be one of: {sorted(_VALID_DOC_TYPES)}")

    filename = file.filename or "document"
    ext = ("." + filename.rsplit(".", 1)[-1].lower()) if "." in filename else ""
    if ext not in _ALLOWED_CRED_EXTS:
        raise HTTPException(status_code=400, detail=f"Unsupported file type. Allowed: {sorted(_ALLOWED_CRED_EXTS)}")

    file_bytes = await file.read()
    if len(file_bytes) > _MAX_CRED_UPLOAD:
        raise HTTPException(status_code=413, detail="File too large. Maximum size is 10MB")

    company_id = employee["org_id"]
    employee_id = employee["id"]

    from app.core.services.storage import get_storage
    storage = get_storage()
    file_path = await storage.upload_private_file(
        file_bytes, filename,
        prefix=f"employee-credentials/{company_id}/{employee_id}",
        content_type=file.content_type,
    )

    async with get_connection() as conn:
        row = await conn.fetchrow(
            """INSERT INTO credential_documents
               (company_id, employee_id, document_type, filename, file_path, mime_type, file_size, uploaded_by, uploaded_via)
               VALUES ($1, $2, $3, $4, $5, $6, $7, $8, 'portal')
               RETURNING *""",
            company_id, employee_id, document_type, filename, file_path,
            file.content_type, len(file_bytes), employee.get("user_id"),
        )

    # Trigger extraction in background
    async def _extract():
        try:
            from app.core.services.credential_extraction import extract_credential_info
            result = await extract_credential_info(file_bytes, file.content_type or "application/octet-stream", document_type)
            extraction_status = "extracted" if result.get("fields") else "failed"
            async with get_connection() as conn:
                await conn.execute(
                    """UPDATE credential_documents
                       SET extracted_data = $1::jsonb, extraction_status = $2, updated_at = NOW()
                       WHERE id = $3""",
                    json.dumps(result), extraction_status, row["id"],
                )
        except Exception as e:
            import logging
            logging.getLogger(__name__).error(f"Portal credential extraction failed: {e}")
            async with get_connection() as conn:
                await conn.execute(
                    """UPDATE credential_documents
                       SET extraction_status = 'failed', updated_at = NOW()
                       WHERE id = $1""",
                    row["id"],
                )

    background_tasks.add_task(_extract)

    return _cred_doc_response(row)


@router.get("/me/credential-documents")
async def portal_list_credential_documents(
    employee: dict = Depends(require_employee_record),
):
    """List credential documents uploaded by/for the current employee."""
    async with get_connection() as conn:
        rows = await conn.fetch(
            """SELECT * FROM credential_documents
               WHERE employee_id = $1 AND company_id = $2
               ORDER BY created_at DESC""",
            employee["id"], employee["org_id"],
        )

    return [_cred_doc_response(r) for r in rows]
