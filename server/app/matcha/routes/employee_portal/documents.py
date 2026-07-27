"""Employee document view/sign, incl. handbook acknowledgment content."""
from typing import Optional
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Request, status

from app.database import get_connection
from app.core.models.handbook import HandbookVersionContent
from app.core.services.policy_service import SignatureService
from app.matcha.models.employees.employee import (
    EmployeeDocumentResponse, EmployeeDocumentListResponse, SignDocumentRequest,
)
from app.matcha.dependencies import require_employee_record

router = APIRouter()


@router.get("/me/documents", response_model=EmployeeDocumentListResponse)
async def get_my_documents(
    status_filter: Optional[str] = None,
    employee: dict = Depends(require_employee_record)
):
    """Get documents assigned to the employee."""
    async with get_connection() as conn:
        if status_filter:
            docs = await conn.fetch(
                """SELECT id, org_id, employee_id, doc_type, title, description,
                          storage_path, status, expires_at, signed_at, assigned_by,
                          created_at, updated_at
                   FROM employee_documents
                   WHERE employee_id = $1 AND status = $2
                   ORDER BY created_at DESC""",
                employee["id"], status_filter
            )
        else:
            docs = await conn.fetch(
                """SELECT id, org_id, employee_id, doc_type, title, description,
                          storage_path, status, expires_at, signed_at, assigned_by,
                          created_at, updated_at
                   FROM employee_documents
                   WHERE employee_id = $1
                   ORDER BY
                       CASE WHEN status = 'pending_signature' THEN 0 ELSE 1 END,
                       created_at DESC""",
                employee["id"]
            )

        return EmployeeDocumentListResponse(
            documents=[
                EmployeeDocumentResponse(
                    id=d["id"],
                    org_id=d["org_id"],
                    employee_id=d["employee_id"],
                    doc_type=d["doc_type"],
                    title=d["title"],
                    description=d["description"],
                    storage_path=d["storage_path"],
                    status=d["status"],
                    expires_at=d["expires_at"],
                    signed_at=d["signed_at"],
                    assigned_by=d["assigned_by"],
                    created_at=d["created_at"],
                    updated_at=d["updated_at"]
                ) for d in docs
            ],
            total=len(docs)
        )


@router.get("/me/documents/{document_id}", response_model=EmployeeDocumentResponse)
async def get_document(
    document_id: UUID,
    employee: dict = Depends(require_employee_record)
):
    """Get a specific document."""
    async with get_connection() as conn:
        doc = await conn.fetchrow(
            """SELECT id, org_id, employee_id, doc_type, title, description,
                      storage_path, status, expires_at, signed_at, assigned_by,
                      created_at, updated_at
               FROM employee_documents
               WHERE id = $1 AND employee_id = $2""",
            document_id, employee["id"]
        )

        if not doc:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Document not found"
            )

        return EmployeeDocumentResponse(
            id=doc["id"],
            org_id=doc["org_id"],
            employee_id=doc["employee_id"],
            doc_type=doc["doc_type"],
            title=doc["title"],
            description=doc["description"],
            storage_path=doc["storage_path"],
            status=doc["status"],
            expires_at=doc["expires_at"],
            signed_at=doc["signed_at"],
            assigned_by=doc["assigned_by"],
            created_at=doc["created_at"],
            updated_at=doc["updated_at"]
        )


@router.get("/me/documents/{document_id}/handbook", response_model=HandbookVersionContent)
async def get_document_handbook_content(
    document_id: UUID,
    employee: dict = Depends(require_employee_record)
):
    """Readable handbook text behind a `handbook:<id>:<version>` document.

    Employees have to read a handbook before they can meaningfully acknowledge
    it, and the stored `storage_path` PDF isn't served to the portal. Returns
    the sections of the exact version that was distributed.
    """
    from app.core.services.handbook_service import HandbookService

    async with get_connection() as conn:
        doc = await conn.fetchrow(
            "SELECT org_id, doc_type FROM employee_documents WHERE id = $1 AND employee_id = $2",
            document_id, employee["id"]
        )

    if not doc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Document not found")

    parsed = HandbookService.parse_doc_type(doc["doc_type"])
    if parsed is None:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="This document is not a handbook"
        )
    handbook_id, version_number = parsed

    content = await HandbookService.get_sections_for_version(
        handbook_id, str(doc["org_id"]), version_number
    )
    if content is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Handbook content not found")
    return content


@router.post("/me/documents/{document_id}/sign", response_model=EmployeeDocumentResponse)
async def sign_document(
    document_id: UUID,
    request: SignDocumentRequest,
    http_request: Request,
    employee: dict = Depends(require_employee_record)
):
    """Sign a document."""
    async with get_connection() as conn:
        # Verify the document belongs to this employee and is pending signature
        doc = await conn.fetchrow(
            """SELECT id, status FROM employee_documents
               WHERE id = $1 AND employee_id = $2""",
            document_id, employee["id"]
        )

        if not doc:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Document not found"
            )

        if doc["status"] != "pending_signature":
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Document is not pending signature"
            )

        # Get client IP
        client_ip = http_request.client.host if http_request.client else None

        # Update the document as signed
        updated = await conn.fetchrow(
            """UPDATE employee_documents
               SET status = 'signed',
                   signed_at = NOW(),
                   signature_data = $1,
                   signature_ip = $2,
                   updated_at = NOW()
               WHERE id = $3
               RETURNING id, org_id, employee_id, doc_type, title, description,
                         storage_path, status, expires_at, signed_at, assigned_by,
                         created_at, updated_at""",
            request.signature_data, client_ip, document_id
        )

        # Keep admin policy-signature tracking in sync for employee policy docs.
        try:
            await SignatureService.sync_employee_document_signature(
                company_id=str(updated["org_id"]),
                employee_id=str(employee["id"]),
                employee_name=f"{employee['first_name']} {employee['last_name']}".strip(),
                employee_email=employee["email"],
                document_title=updated["title"],
                document_type=updated["doc_type"],
                signature_data=request.signature_data,
                ip_address=client_ip,
            )
        except Exception as exc:
            print(f"[Policy] Failed to sync employee policy signature for admin tracking: {exc}")

        return EmployeeDocumentResponse(
            id=updated["id"],
            org_id=updated["org_id"],
            employee_id=updated["employee_id"],
            doc_type=updated["doc_type"],
            title=updated["title"],
            description=updated["description"],
            storage_path=updated["storage_path"],
            status=updated["status"],
            expires_at=updated["expires_at"],
            signed_at=updated["signed_at"],
            assigned_by=updated["assigned_by"],
            created_at=updated["created_at"],
            updated_at=updated["updated_at"]
        )
