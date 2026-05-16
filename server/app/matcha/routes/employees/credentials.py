"""Healthcare employee credentials + credential-document upload/review.

Routes:
  GET  /{employee_id}/credentials                                — read credentials
  PUT  /{employee_id}/credentials                                — upsert credentials
  POST /{employee_id}/credential-documents                       — upload doc + queue AI extraction
  GET  /{employee_id}/credential-documents                       — list docs
  DEL  /{employee_id}/credential-documents/{document_id}         — delete doc
  POST /{employee_id}/credential-documents/{id}/approve          — approve (optionally apply to creds)
  POST /{employee_id}/credential-documents/{id}/reject           — reject
  GET  /{employee_id}/credential-documents/{id}/download         — presigned download URL
"""
import json
import logging
from datetime import date
from typing import Optional
from uuid import UUID

from fastapi import (
    APIRouter,
    BackgroundTasks,
    Depends,
    File,
    HTTPException,
    Query,
    UploadFile,
)
from pydantic import BaseModel

from app.core.models.auth import CurrentUser
from app.core.services.credential_crypto import (
    decrypt_credential_fields,
    encrypt_credential_fields,
)
from app.core.services.storage import get_storage
from app.database import get_connection
from app.matcha.dependencies import get_client_company_id, require_admin_or_client

logger = logging.getLogger(__name__)

router = APIRouter()


class EmployeeCredentialsRequest(BaseModel):
    license_type: Optional[str] = None
    license_number: Optional[str] = None
    license_state: Optional[str] = None
    license_expiration: Optional[str] = None  # YYYY-MM-DD
    npi_number: Optional[str] = None
    dea_number: Optional[str] = None
    dea_expiration: Optional[str] = None
    board_certification: Optional[str] = None
    board_certification_expiration: Optional[str] = None
    clinical_specialty: Optional[str] = None
    oig_last_checked: Optional[str] = None
    oig_status: Optional[str] = None
    malpractice_carrier: Optional[str] = None
    malpractice_policy_number: Optional[str] = None
    malpractice_expiration: Optional[str] = None
    health_clearances: Optional[dict] = None


class EmployeeCredentialsResponse(BaseModel):
    id: Optional[UUID] = None
    employee_id: UUID
    license_type: Optional[str] = None
    license_number: Optional[str] = None
    license_state: Optional[str] = None
    license_expiration: Optional[str] = None
    npi_number: Optional[str] = None
    dea_number: Optional[str] = None
    dea_expiration: Optional[str] = None
    board_certification: Optional[str] = None
    board_certification_expiration: Optional[str] = None
    clinical_specialty: Optional[str] = None
    oig_last_checked: Optional[str] = None
    oig_status: Optional[str] = None
    malpractice_carrier: Optional[str] = None
    malpractice_policy_number: Optional[str] = None
    malpractice_expiration: Optional[str] = None
    health_clearances: Optional[dict] = None


@router.get("/{employee_id}/credentials", response_model=EmployeeCredentialsResponse)
async def get_employee_credentials(
    employee_id: UUID,
    current_user: CurrentUser = Depends(require_admin_or_client),
):
    """Get healthcare credentials for an employee."""
    company_id = await get_client_company_id(current_user)

    async with get_connection() as conn:
        # Verify employee belongs to company
        emp = await conn.fetchval(
            "SELECT id FROM employees WHERE id = $1 AND org_id = $2",
            employee_id, company_id,
        )
        if not emp:
            raise HTTPException(status_code=404, detail="Employee not found")

        row = await conn.fetchrow(
            "SELECT * FROM employee_credentials WHERE employee_id = $1",
            employee_id,
        )
        if not row:
            return EmployeeCredentialsResponse(employee_id=employee_id)

        decrypted = decrypt_credential_fields(dict(row))

        def _date_str(val):
            return val.isoformat() if val else None

        return EmployeeCredentialsResponse(
            id=row["id"],
            employee_id=row["employee_id"],
            license_type=row["license_type"],
            license_number=decrypted["license_number"],
            license_state=row["license_state"],
            license_expiration=_date_str(row["license_expiration"]),
            npi_number=decrypted["npi_number"],
            dea_number=decrypted["dea_number"],
            dea_expiration=_date_str(row["dea_expiration"]),
            board_certification=row["board_certification"],
            board_certification_expiration=_date_str(row["board_certification_expiration"]),
            clinical_specialty=row["clinical_specialty"],
            oig_last_checked=_date_str(row["oig_last_checked"]),
            oig_status=row["oig_status"],
            malpractice_carrier=row["malpractice_carrier"],
            malpractice_policy_number=decrypted["malpractice_policy_number"],
            malpractice_expiration=_date_str(row["malpractice_expiration"]),
            health_clearances=row["health_clearances"] if isinstance(row["health_clearances"], dict) else None,
        )


@router.put("/{employee_id}/credentials", response_model=EmployeeCredentialsResponse)
async def upsert_employee_credentials(
    employee_id: UUID,
    body: EmployeeCredentialsRequest,
    current_user: CurrentUser = Depends(require_admin_or_client),
):
    """Create or update healthcare credentials for an employee."""
    company_id = await get_client_company_id(current_user)

    async with get_connection() as conn:
        emp = await conn.fetchval(
            "SELECT id FROM employees WHERE id = $1 AND org_id = $2",
            employee_id, company_id,
        )
        if not emp:
            raise HTTPException(status_code=404, detail="Employee not found")

        def _parse_date(val):
            if not val:
                return None
            return date.fromisoformat(val)

        encrypted = encrypt_credential_fields({
            "license_number": body.license_number,
            "npi_number": body.npi_number,
            "dea_number": body.dea_number,
            "malpractice_policy_number": body.malpractice_policy_number,
        })

        await conn.execute("""
            INSERT INTO employee_credentials (
                employee_id, org_id,
                license_type, license_number, license_state, license_expiration,
                npi_number, dea_number, dea_expiration,
                board_certification, board_certification_expiration,
                clinical_specialty,
                oig_last_checked, oig_status,
                malpractice_carrier, malpractice_policy_number, malpractice_expiration,
                health_clearances,
                updated_at
            ) VALUES (
                $1, $2,
                $3, $4, $5, $6,
                $7, $8, $9,
                $10, $11,
                $12,
                $13, $14,
                $15, $16, $17,
                $18::jsonb,
                NOW()
            )
            ON CONFLICT (employee_id) DO UPDATE SET
                license_type = EXCLUDED.license_type,
                license_number = EXCLUDED.license_number,
                license_state = EXCLUDED.license_state,
                license_expiration = EXCLUDED.license_expiration,
                npi_number = EXCLUDED.npi_number,
                dea_number = EXCLUDED.dea_number,
                dea_expiration = EXCLUDED.dea_expiration,
                board_certification = EXCLUDED.board_certification,
                board_certification_expiration = EXCLUDED.board_certification_expiration,
                clinical_specialty = EXCLUDED.clinical_specialty,
                oig_last_checked = EXCLUDED.oig_last_checked,
                oig_status = EXCLUDED.oig_status,
                malpractice_carrier = EXCLUDED.malpractice_carrier,
                malpractice_policy_number = EXCLUDED.malpractice_policy_number,
                malpractice_expiration = EXCLUDED.malpractice_expiration,
                health_clearances = EXCLUDED.health_clearances,
                updated_at = NOW()
        """,
            employee_id, company_id,
            body.license_type, encrypted["license_number"], body.license_state, _parse_date(body.license_expiration),
            encrypted["npi_number"], encrypted["dea_number"], _parse_date(body.dea_expiration),
            body.board_certification, _parse_date(body.board_certification_expiration),
            body.clinical_specialty,
            _parse_date(body.oig_last_checked), body.oig_status or "not_checked",
            body.malpractice_carrier, encrypted["malpractice_policy_number"], _parse_date(body.malpractice_expiration),
            json.dumps(body.health_clearances) if body.health_clearances else "{}",
        )

    # Return updated data
    return await get_employee_credentials(employee_id, current_user)


# ===========================================
# Credential Documents (upload + AI extraction)
# ===========================================

MAX_CREDENTIAL_UPLOAD_SIZE = 10 * 1024 * 1024  # 10 MB
ALLOWED_CREDENTIAL_EXTENSIONS = {".pdf", ".png", ".jpg", ".jpeg", ".gif", ".tiff"}
VALID_DOCUMENT_TYPES = {"medical_license", "dea", "npi", "board_cert", "malpractice", "health_clearance", "other"}


class CredentialDocumentResponse(BaseModel):
    id: str
    company_id: str
    employee_id: str
    document_type: str
    filename: str
    file_path: Optional[str] = None
    mime_type: Optional[str] = None
    file_size: Optional[int] = None
    extracted_data: Optional[dict] = None
    extraction_status: str = "pending"
    review_status: str = "pending"
    reviewed_by: Optional[str] = None
    reviewed_at: Optional[str] = None
    review_notes: Optional[str] = None
    uploaded_by: Optional[str] = None
    uploaded_via: str = "admin"
    created_at: Optional[str] = None
    updated_at: Optional[str] = None


def _cred_doc_from_row(row) -> dict:
    return {
        "id": str(row["id"]),
        "company_id": str(row["company_id"]),
        "employee_id": str(row["employee_id"]),
        "document_type": row["document_type"],
        "filename": row["filename"],
        "file_path": row.get("file_path"),
        "mime_type": row.get("mime_type"),
        "file_size": row.get("file_size"),
        "extracted_data": json.loads(row["extracted_data"]) if isinstance(row.get("extracted_data"), str) else row.get("extracted_data"),
        "extraction_status": row.get("extraction_status", "pending"),
        "review_status": row.get("review_status", "pending"),
        "reviewed_by": str(row["reviewed_by"]) if row.get("reviewed_by") else None,
        "reviewed_at": row["reviewed_at"].isoformat() if row.get("reviewed_at") else None,
        "review_notes": row.get("review_notes"),
        "uploaded_by": str(row["uploaded_by"]) if row.get("uploaded_by") else None,
        "uploaded_via": row.get("uploaded_via", "admin"),
        "created_at": row["created_at"].isoformat() if row.get("created_at") else None,
        "updated_at": row["updated_at"].isoformat() if row.get("updated_at") else None,
    }


async def _run_credential_extraction(document_id: UUID, file_bytes: bytes, mime_type: str, document_type: str):
    """Background task: run Gemini extraction and update the DB row."""
    try:
        from app.core.services.credential_extraction import extract_credential_info
        result = await extract_credential_info(file_bytes, mime_type, document_type)
        extraction_status = "extracted" if result.get("fields") else "failed"
        async with get_connection() as conn:
            await conn.execute(
                """UPDATE credential_documents
                   SET extracted_data = $1::jsonb, extraction_status = $2, updated_at = NOW()
                   WHERE id = $3""",
                json.dumps(result), extraction_status, document_id,
            )
    except Exception as e:
        logger.error(f"Credential extraction failed for document {document_id}: {e}")
        async with get_connection() as conn:
            await conn.execute(
                """UPDATE credential_documents
                   SET extraction_status = 'failed', extracted_data = $1::jsonb, updated_at = NOW()
                   WHERE id = $2""",
                json.dumps({"error": str(e)}), document_id,
            )


@router.post("/{employee_id}/credential-documents", response_model=CredentialDocumentResponse)
async def upload_credential_document(
    employee_id: UUID,
    background_tasks: BackgroundTasks,
    file: UploadFile = File(...),
    document_type: str = Query(..., description="Document type"),
    current_user: CurrentUser = Depends(require_admin_or_client),
):
    """Upload a credential document for an employee. Triggers AI extraction."""
    company_id = await get_client_company_id(current_user)

    if document_type not in VALID_DOCUMENT_TYPES:
        raise HTTPException(status_code=400, detail=f"Invalid document_type. Must be one of: {sorted(VALID_DOCUMENT_TYPES)}")

    filename = file.filename or "document"
    ext = ("." + filename.rsplit(".", 1)[-1].lower()) if "." in filename else ""
    if ext not in ALLOWED_CREDENTIAL_EXTENSIONS:
        raise HTTPException(status_code=400, detail=f"Unsupported file type. Allowed: {sorted(ALLOWED_CREDENTIAL_EXTENSIONS)}")

    file_bytes = await file.read()
    if len(file_bytes) > MAX_CREDENTIAL_UPLOAD_SIZE:
        raise HTTPException(status_code=413, detail=f"File too large. Maximum size is {MAX_CREDENTIAL_UPLOAD_SIZE // (1024 * 1024)}MB")

    async with get_connection() as conn:
        emp = await conn.fetchval(
            "SELECT id FROM employees WHERE id = $1 AND org_id = $2",
            employee_id, company_id,
        )
        if not emp:
            raise HTTPException(status_code=404, detail="Employee not found")

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
               VALUES ($1, $2, $3, $4, $5, $6, $7, $8, 'admin')
               RETURNING *""",
            company_id, employee_id, document_type, filename, file_path,
            file.content_type, len(file_bytes), current_user.id,
        )

    background_tasks.add_task(_run_credential_extraction, row["id"], file_bytes, file.content_type or "application/octet-stream", document_type)

    return _cred_doc_from_row(row)


@router.get("/{employee_id}/credential-documents")
async def list_credential_documents(
    employee_id: UUID,
    current_user: CurrentUser = Depends(require_admin_or_client),
):
    """List all credential documents for an employee."""
    company_id = await get_client_company_id(current_user)

    async with get_connection() as conn:
        emp = await conn.fetchval(
            "SELECT id FROM employees WHERE id = $1 AND org_id = $2",
            employee_id, company_id,
        )
        if not emp:
            raise HTTPException(status_code=404, detail="Employee not found")

        rows = await conn.fetch(
            """SELECT * FROM credential_documents
               WHERE employee_id = $1 AND company_id = $2
               ORDER BY created_at DESC""",
            employee_id, company_id,
        )

    return [_cred_doc_from_row(r) for r in rows]


@router.delete("/{employee_id}/credential-documents/{document_id}")
async def delete_credential_document(
    employee_id: UUID,
    document_id: UUID,
    current_user: CurrentUser = Depends(require_admin_or_client),
):
    """Delete a credential document."""
    company_id = await get_client_company_id(current_user)

    async with get_connection() as conn:
        row = await conn.fetchrow(
            """SELECT file_path FROM credential_documents
               WHERE id = $1 AND employee_id = $2 AND company_id = $3""",
            document_id, employee_id, company_id,
        )
        if not row:
            raise HTTPException(status_code=404, detail="Document not found")

        storage = get_storage()
        await storage.delete_private_file(row["file_path"])

        await conn.execute("DELETE FROM credential_documents WHERE id = $1", document_id)

    return {"message": "Document deleted"}


class ApproveRequest(BaseModel):
    apply_to_credentials: bool = False
    notes: Optional[str] = None


@router.post("/{employee_id}/credential-documents/{document_id}/approve")
async def approve_credential_document(
    employee_id: UUID,
    document_id: UUID,
    body: ApproveRequest,
    current_user: CurrentUser = Depends(require_admin_or_client),
):
    """Approve a credential document. Optionally apply extracted data to employee credentials."""
    company_id = await get_client_company_id(current_user)

    async with get_connection() as conn:
        row = await conn.fetchrow(
            """SELECT * FROM credential_documents
               WHERE id = $1 AND employee_id = $2 AND company_id = $3""",
            document_id, employee_id, company_id,
        )
        if not row:
            raise HTTPException(status_code=404, detail="Document not found")

        await conn.execute(
            """UPDATE credential_documents
               SET review_status = 'approved', reviewed_by = $1, reviewed_at = NOW(),
                   review_notes = $2, updated_at = NOW()
               WHERE id = $3""",
            current_user.id, body.notes, document_id,
        )

        if body.apply_to_credentials and row.get("extracted_data"):
            extracted = row["extracted_data"] if isinstance(row["extracted_data"], dict) else json.loads(row["extracted_data"])
            fields = extracted.get("fields", {})

            # Map extracted fields to employee_credentials columns
            updates = {}
            doc_type = row["document_type"]

            for field_name, field_data in fields.items():
                if not isinstance(field_data, dict):
                    continue
                val = field_data.get("value")
                if val is None:
                    continue

                # Only map known credential fields
                if field_name in (
                    "license_type", "license_number", "license_state", "license_expiration",
                    "npi_number", "dea_number", "dea_expiration",
                    "board_certification", "board_certification_expiration",
                    "clinical_specialty",
                    "malpractice_carrier", "malpractice_policy_number", "malpractice_expiration",
                ):
                    updates[field_name] = val

            if updates:
                encrypted = encrypt_credential_fields(updates)
                # Use upsert to write extracted data into employee_credentials
                set_clauses = []
                values = [employee_id, company_id]
                insert_cols = ["employee_id", "org_id"]
                insert_placeholders = ["$1", "$2"]
                idx = 3

                for col, val in encrypted.items():
                    insert_cols.append(col)
                    insert_placeholders.append(f"${idx}")
                    set_clauses.append(f"{col} = ${idx}")
                    values.append(val)
                    idx += 1

                set_clauses.append("updated_at = NOW()")
                sql = f"""
                    INSERT INTO employee_credentials ({', '.join(insert_cols)})
                    VALUES ({', '.join(insert_placeholders)})
                    ON CONFLICT (employee_id) DO UPDATE SET {', '.join(set_clauses)}
                """
                await conn.execute(sql, *values)

        # Auto-complete matching credential onboarding task
        try:
            await conn.execute(
                """UPDATE employee_onboarding_tasks
                   SET status = 'completed', completed_at = NOW(), completed_by = $1, updated_at = NOW()
                   WHERE employee_id = $2 AND document_type = $3 AND status = 'pending'""",
                current_user.id, employee_id, row["document_type"],
            )
        except Exception:
            logger.exception("Failed to auto-complete onboarding task for credential doc %s", document_id)

    return {"message": "Document approved", "applied_to_credentials": body.apply_to_credentials}


class RejectRequest(BaseModel):
    notes: str


@router.post("/{employee_id}/credential-documents/{document_id}/reject")
async def reject_credential_document(
    employee_id: UUID,
    document_id: UUID,
    body: RejectRequest,
    current_user: CurrentUser = Depends(require_admin_or_client),
):
    """Reject a credential document."""
    company_id = await get_client_company_id(current_user)

    async with get_connection() as conn:
        exists = await conn.fetchval(
            """SELECT id FROM credential_documents
               WHERE id = $1 AND employee_id = $2 AND company_id = $3""",
            document_id, employee_id, company_id,
        )
        if not exists:
            raise HTTPException(status_code=404, detail="Document not found")

        await conn.execute(
            """UPDATE credential_documents
               SET review_status = 'rejected', reviewed_by = $1, reviewed_at = NOW(),
                   review_notes = $2, updated_at = NOW()
               WHERE id = $3""",
            current_user.id, body.notes, document_id,
        )

    return {"message": "Document rejected"}


@router.get("/{employee_id}/credential-documents/{document_id}/download")
async def download_credential_document(
    employee_id: UUID,
    document_id: UUID,
    current_user: CurrentUser = Depends(require_admin_or_client),
):
    """Get a presigned download URL for a credential document."""
    company_id = await get_client_company_id(current_user)

    async with get_connection() as conn:
        row = await conn.fetchrow(
            """SELECT file_path, filename, mime_type FROM credential_documents
               WHERE id = $1 AND employee_id = $2 AND company_id = $3""",
            document_id, employee_id, company_id,
        )
        if not row:
            raise HTTPException(status_code=404, detail="Document not found")

    storage = get_storage()
    presigned = storage.get_presigned_download_url(row["file_path"])
    if not presigned:
        raise HTTPException(status_code=500, detail="Unable to generate download URL")
    return {"url": presigned, "filename": row["filename"]}
