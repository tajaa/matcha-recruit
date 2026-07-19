from typing import Optional

from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel

from ..services.handbook_service import HandbookService
from ..services.policy_service import SignatureService
from ...database import get_connection

router = APIRouter(prefix="/employee-documents", tags=["public-employee-documents"])


class EmployeeDocumentSignData(BaseModel):
    id: str
    doc_type: str
    title: str
    description: Optional[str] = None
    content: Optional[str] = None
    file_url: Optional[str] = None
    company_name: Optional[str] = None
    signer_name: str
    signer_email: str
    status: str
    expires_at: Optional[str] = None


class SignAction(BaseModel):
    action: str  # "sign" or "decline"
    signature_data: Optional[str] = None


async def _fetch_document(token: str) -> Optional[dict]:
    async with get_connection() as conn:
        row = await conn.fetchrow(
            """
                SELECT
                    ed.id, ed.org_id, ed.employee_id, ed.doc_type, ed.title,
                    ed.description, ed.storage_path, ed.status, ed.expires_at,
                    e.first_name, e.last_name, e.email AS employee_email,
                    c.name AS company_name
                FROM employee_documents ed
                JOIN employees e ON e.id = ed.employee_id
                LEFT JOIN companies c ON c.id = ed.org_id
                WHERE ed.sign_token = $1
            """,
            token,
        )
        return dict(row) if row else None


async def _document_content(doc: dict) -> Optional[str]:
    """Readable body for a `handbook:<id>:<version>` document; None otherwise."""
    parsed = HandbookService.parse_doc_type(doc["doc_type"])
    if not parsed:
        return None
    handbook_id, version_number = parsed
    content = await HandbookService.get_sections_for_version(
        handbook_id, str(doc["org_id"]), version_number
    )
    if not content:
        return None
    parts = []
    for section in content["sections"]:
        if section.get("title"):
            parts.append(f"## {section['title']}")
        if section.get("content"):
            parts.append(section["content"])
    return "\n\n".join(parts).strip() or None


# Public, no-login signature page for employee documents (handbook
# acknowledgement) reached via an emailed link (/sign-document/:token). The
# token is an opaque lookup key on employee_documents.sign_token — identity is
# already bound to the row (employee_id/name/email), so no account is needed.
# See migration signdoc01.
@router.get("/verify/{token}", response_model=EmployeeDocumentSignData)
async def get_employee_document_data(token: str):
    doc = await _fetch_document(token)
    if not doc:
        raise HTTPException(status_code=404, detail="Invalid or expired signature link")

    content = await _document_content(doc)
    signer_name = " ".join(
        part for part in [doc.get("first_name"), doc.get("last_name")] if part
    ).strip()

    return EmployeeDocumentSignData(
        id=str(doc["id"]),
        doc_type=doc["doc_type"],
        title=doc["title"],
        description=doc.get("description"),
        content=content,
        file_url=doc.get("storage_path"),
        company_name=doc.get("company_name"),
        signer_name=signer_name or doc["employee_email"],
        signer_email=doc["employee_email"],
        status=doc["status"],
        expires_at=doc["expires_at"].isoformat() if doc.get("expires_at") else None,
    )


@router.post("/verify/{token}")
async def submit_employee_document_signature(token: str, data: SignAction, request: Request):
    doc = await _fetch_document(token)
    if not doc:
        raise HTTPException(status_code=404, detail="Invalid or expired signature link")

    if doc["status"] != "pending_signature":
        raise HTTPException(status_code=410, detail="This signature request is no longer pending")

    # employee_documents.status has no "declined" state (unlike policy_signatures) —
    # acknowledgement is the only outcome the portal's own sign endpoint supports.
    if data.action != "sign" or not data.signature_data:
        raise HTTPException(status_code=400, detail="A typed signature is required")

    ip_address = request.client.host if request.client else None

    async with get_connection() as conn:
        updated = await conn.fetchrow(
            """
                UPDATE employee_documents
                SET status = 'signed',
                    signed_at = NOW(),
                    signature_data = $1,
                    signature_ip = $2,
                    updated_at = NOW()
                WHERE id = $3
                RETURNING status
            """,
            data.signature_data,
            ip_address,
            doc["id"],
        )

    if not updated:
        raise HTTPException(status_code=400, detail="Failed to process signature")

    signer_name = " ".join(
        part for part in [doc.get("first_name"), doc.get("last_name")] if part
    ).strip()
    try:
        # Keep admin policy-signature tracking in sync, same as the portal path.
        await SignatureService.sync_employee_document_signature(
            company_id=str(doc["org_id"]),
            employee_id=str(doc["employee_id"]),
            employee_name=signer_name,
            employee_email=doc["employee_email"],
            document_title=doc["title"],
            document_type=doc["doc_type"],
            signature_data=data.signature_data,
            ip_address=ip_address,
        )
    except Exception:
        pass

    return {"status": updated["status"], "message": "Signature recorded successfully"}
