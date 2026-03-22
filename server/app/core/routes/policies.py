from fastapi import APIRouter, Depends, HTTPException, Query, UploadFile, File, Form, BackgroundTasks
from pydantic import BaseModel, Field
from typing import List, Optional

from ...matcha.dependencies import require_admin_or_client, get_client_company_id
from ..models.policy import (
    Policy,
    PolicyCreate,
    PolicyUpdate,
    PolicyResponse,
    PolicyStatus,
    SignatureRequest,
    SignatureCreate,
    PolicySignatureResponse,
    PolicySignatureWithToken,
    SignatureStatus,
    SignerType,
)
from ..services.policy_service import PolicyService, SignatureService
from ..services.email import get_email_service
from ..services.storage import get_storage
from ..models.auth import CurrentUser
from ...matcha.services.er_document_parser import ERDocumentParser
from uuid import UUID
import logging

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/policies", tags=["policies"])


# ---------------------------------------------------------------------------
# Topic-based policy drafting
# ---------------------------------------------------------------------------

class PolicyDraftFromTopicRequest(BaseModel):
    topic: str = Field(..., min_length=2, max_length=500, description="Policy topic (e.g., 'Bloodborne Pathogen Exposure Control')")
    jurisdiction: str = Field(..., min_length=2, max_length=100, description="Target jurisdiction (e.g., 'California', 'CA')")
    location_id: Optional[UUID] = Field(None, description="Optional business location ID to narrow jurisdiction scope")
    industry_context: Optional[str] = Field(None, max_length=200, description="Optional industry context (e.g., 'oncology clinic')")


class PolicyDraftCitation(BaseModel):
    requirement_key: str
    title: str
    source_url: str


class PolicyDraftFromTopicResponse(BaseModel):
    title: str
    content: str
    citations: List[PolicyDraftCitation]
    applicable_jurisdictions: List[str]
    category: str


@router.post("/draft", response_model=PolicyDraftFromTopicResponse)
async def draft_policy_from_topic(
    body: PolicyDraftFromTopicRequest,
    current_user: CurrentUser = Depends(require_admin_or_client),
):
    """Generate a policy draft for a freeform topic and jurisdiction.

    Fetches relevant regulatory requirements from the database and uses
    Gemini to produce a complete policy document with citations.
    """
    from ..services.policy_draft_service import (
        draft_policy_from_topic as _draft_policy_from_topic,
        _fetch_requirements_for_topic,
    )

    try:
        # Fetch requirements matching the topic + jurisdiction
        requirements = await _fetch_requirements_for_topic(
            jurisdiction=body.jurisdiction,
            topic=body.topic,
            location_id=str(body.location_id) if body.location_id else None,
        )

        logger.info(
            "Policy draft: topic=%r jurisdiction=%r matched %d requirements",
            body.topic,
            body.jurisdiction,
            len(requirements),
        )

        # Generate the policy draft
        result = await _draft_policy_from_topic(
            topic=body.topic,
            jurisdiction=body.jurisdiction,
            requirements=requirements,
            industry=body.industry_context,
        )

        return PolicyDraftFromTopicResponse(**result)

    except RuntimeError as exc:
        raise HTTPException(status_code=502, detail=str(exc))
    except Exception as exc:
        logger.error("Policy draft from topic failed: %s", exc, exc_info=True)
        raise HTTPException(
            status_code=500,
            detail=f"Policy generation failed: {str(exc)}",
        )


async def send_signature_emails_task(signatures: List[PolicySignatureWithToken], policy: PolicyResponse):
    email_service = get_email_service()
    for sig in signatures:
        await email_service.send_policy_signature_email(
            to_email=sig.signer_email,
            to_name=sig.signer_name,
            policy_title=policy.title,
            policy_version=policy.version,
            token=sig.token,
            expires_at=sig.expires_at,
            company_name=policy.company_name,
        )


@router.get("", response_model=List[PolicyResponse])
async def list_policies(
    status: Optional[PolicyStatus] = None,
    category: Optional[str] = Query(None),
    current_user: CurrentUser = Depends(require_admin_or_client),
):
    company_id = await get_client_company_id(current_user)
    if company_id is None:
        return []

    policies = await PolicyService.get_policies(str(company_id), status, category)
    return policies


@router.post("", response_model=PolicyResponse)
async def create_policy(
    title: str = Form(...),
    description: Optional[str] = Form(None),
    content: str = Form(""),
    version: str = Form("1.0"),
    status: PolicyStatus = Form("draft"),
    category: Optional[str] = Form(None),
    effective_date: Optional[str] = Form(None),
    review_date: Optional[str] = Form(None),
    file: Optional[UploadFile] = File(None),
    current_user: CurrentUser = Depends(require_admin_or_client),
):
    from datetime import date as date_type

    data = PolicyCreate(
        title=title,
        description=description,
        content=content,
        version=version,
        status=status,
        category=category,
        effective_date=date_type.fromisoformat(effective_date) if effective_date else None,
        review_date=date_type.fromisoformat(review_date) if review_date else None,
    )

    company_id = await get_client_company_id(current_user)
    if company_id is None:
        raise HTTPException(status_code=400, detail="No company found")

    # Upload file if provided — extract text content from PDF/DOCX
    if file:
        storage = get_storage()
        file_content = await file.read()
        file_url = await storage.upload_file(
            file_bytes=file_content,
            filename=file.filename or "policy.pdf",
            prefix="policies",
            content_type=file.content_type,
        )
        data.file_url = file_url
        data.source_type = "uploaded"
        data.original_filename = file.filename
        data.mime_type = file.content_type

        # Extract text if no explicit content was provided
        if not content.strip():
            try:
                parser = ERDocumentParser()
                text, page_count = parser.extract_text_from_bytes(file_content, file.filename or "policy.pdf")
                data.content = text or ""
                data.page_count = page_count
            except Exception as exc:
                logger.warning("Policy text extraction failed: %s", exc)

    policy = await PolicyService.create_policy(str(company_id), data, str(current_user.id))
    return policy


@router.get("/{policy_id}", response_model=PolicyResponse)
async def get_policy(
    policy_id: str,
    current_user: CurrentUser = Depends(require_admin_or_client),
):
    company_id = await get_client_company_id(current_user)
    if company_id is None:
        raise HTTPException(status_code=403, detail="Access denied")

    policy = await PolicyService.get_policy_by_id(policy_id, str(company_id))
    if not policy:
        raise HTTPException(status_code=404, detail="Policy not found")

    return policy


@router.put("/{policy_id}", response_model=PolicyResponse)
async def update_policy(
    policy_id: str,
    data: PolicyUpdate,
    current_user: CurrentUser = Depends(require_admin_or_client),
):
    company_id = await get_client_company_id(current_user)
    if company_id is None:
        raise HTTPException(status_code=403, detail="Access denied")

    policy = await PolicyService.update_policy(policy_id, data, str(company_id))
    if not policy:
        raise HTTPException(status_code=404, detail="Policy not found")

    return policy


@router.delete("/{policy_id}")
async def delete_policy(
    policy_id: str,
    current_user: CurrentUser = Depends(require_admin_or_client),
):
    company_id = await get_client_company_id(current_user)
    if company_id is None:
        raise HTTPException(status_code=403, detail="Access denied")

    success = await PolicyService.delete_policy(policy_id, str(company_id))
    if not success:
        raise HTTPException(status_code=404, detail="Policy not found")

    return {"message": "Policy deleted successfully"}


@router.post("/{policy_id}/signatures")
async def send_signature_requests(
    policy_id: str,
    requests: List[SignatureRequest],
    background_tasks: BackgroundTasks,
    current_user: CurrentUser = Depends(require_admin_or_client),
):
    company_id = await get_client_company_id(current_user)
    if company_id is None:
        raise HTTPException(status_code=403, detail="Access denied")

    policy = await PolicyService.get_policy_by_id(policy_id, str(company_id))
    if not policy:
        raise HTTPException(status_code=404, detail="Policy not found")

    if not requests:
        raise HTTPException(status_code=400, detail="At least one signer is required")

    signatures = await SignatureService.create_batch_signature_requests(policy_id, requests)

    # Send emails in background to prevent request timeout
    background_tasks.add_task(send_signature_emails_task, signatures, policy)

    return {"message": f"Sent {len(signatures)} signature requests", "signatures": len(signatures)}


@router.get("/{policy_id}/signatures", response_model=List[PolicySignatureResponse])
async def list_policy_signatures(
    policy_id: str,
    current_user: CurrentUser = Depends(require_admin_or_client),
):
    company_id = await get_client_company_id(current_user)
    if company_id is None:
        raise HTTPException(status_code=403, detail="Access denied")

    policy = await PolicyService.get_policy_by_id(policy_id, str(company_id))
    if not policy:
        raise HTTPException(status_code=404, detail="Policy not found")

    signatures = await SignatureService.get_policy_signatures(policy_id)
    return signatures


@router.delete("/signatures/{signature_id}")
async def cancel_signature_request(
    signature_id: str,
    current_user: CurrentUser = Depends(require_admin_or_client),
):
    company_id = await get_client_company_id(current_user)
    if company_id is None:
        raise HTTPException(status_code=403, detail="Access denied")

    signature = await SignatureService.get_signature_by_id(signature_id)
    if not signature:
        raise HTTPException(status_code=404, detail="Signature request not found")

    # Verify the policy belongs to this company
    policy = await PolicyService.get_policy_by_id(signature.policy_id, str(company_id))
    if not policy:
        raise HTTPException(status_code=404, detail="Signature request not found")

    success = await SignatureService.delete_signature(signature_id)
    if not success:
        raise HTTPException(status_code=404, detail="Signature request not found")

    return {"message": "Signature request cancelled"}


async def resend_signature_email_task(signature: PolicySignatureWithToken):
    email_service = get_email_service()
    await email_service.send_policy_signature_email(
        to_email=signature.signer_email,
        to_name=signature.signer_name,
        policy_title=signature.policy_title,
        policy_version="",
        token=signature.token,
        expires_at=signature.expires_at,
        company_name=None,
    )


@router.post("/signatures/{signature_id}/resend")
async def resend_signature_request(
    signature_id: str,
    background_tasks: BackgroundTasks,
    current_user: CurrentUser = Depends(require_admin_or_client),
):
    company_id = await get_client_company_id(current_user)
    if company_id is None:
        raise HTTPException(status_code=403, detail="Access denied")

    signature = await SignatureService.get_signature_by_id(signature_id)
    if not signature:
        raise HTTPException(status_code=404, detail="Signature request not found")

    # Verify the policy belongs to this company
    policy = await PolicyService.get_policy_by_id(signature.policy_id, str(company_id))
    if not policy:
        raise HTTPException(status_code=404, detail="Signature request not found")

    signature = await SignatureService.resend_signature(signature_id)
    if not signature:
        raise HTTPException(status_code=400, detail="Cannot resend this signature request")

    background_tasks.add_task(resend_signature_email_task, signature)

    return {"message": "Signature request resent"}
