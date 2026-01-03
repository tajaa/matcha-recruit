from fastapi import APIRouter, Depends, HTTPException, Query
from typing import List, Optional

from ..dependencies import require_client
from ..dependencies import get_client_company_id
from ..models.policy import (
    Policy,
    PolicyCreate,
    PolicyUpdate,
    PolicyResponse,
    PolicyStatus,
    SignatureRequest,
    SignatureCreate,
    PolicySignatureResponse,
    SignatureStatus,
    SignerType,
)
from ..services.policy_service import PolicyService, SignatureService
from ..services.email import get_email_service
from ..models.auth import CurrentUser
from uuid import UUID

router = APIRouter(prefix="/api/policies", tags=["policies"])


@router.get("", response_model=List[PolicyResponse])
async def list_policies(
    status: Optional[PolicyStatus] = None,
    current_user: CurrentUser = Depends(require_client),
):
    company_id = await get_client_company_id(current_user)
    if company_id is None:
        return []
    
    policies = await PolicyService.get_policies(str(company_id), status)
    return policies


@router.post("", response_model=PolicyResponse)
async def create_policy(
    data: PolicyCreate,
    current_user: CurrentUser = Depends(require_client),
):
    company_id = await get_client_company_id(current_user)
    if company_id is None:
        raise HTTPException(status_code=400, detail="No company found")
    
    policy = await PolicyService.create_policy(str(company_id), data, str(current_user.id))
    return policy


@router.get("/{policy_id}", response_model=PolicyResponse)
async def get_policy(
    policy_id: str,
    current_user: CurrentUser = Depends(require_client),
):
    company_id = await get_client_company_id(current_user)
    if company_id is None:
        raise HTTPException(status_code=403, detail="Access denied")

    policy = await PolicyService.get_policy_by_id(policy_id)
    if not policy:
        raise HTTPException(status_code=404, detail="Policy not found")

    can_access = await PolicyService.can_user_access_policy(str(current_user.id), policy_id)
    if not can_access:
        raise HTTPException(status_code=403, detail="Access denied")

    return policy


@router.put("/{policy_id}", response_model=PolicyResponse)
async def update_policy(
    policy_id: str,
    data: PolicyUpdate,
    current_user: CurrentUser = Depends(require_client),
):
    can_access = await PolicyService.can_user_access_policy(str(current_user.id), policy_id)
    if not can_access:
        raise HTTPException(status_code=403, detail="Access denied")

    policy = await PolicyService.update_policy(policy_id, data)
    if not policy:
        raise HTTPException(status_code=404, detail="Policy not found")

    return policy


@router.delete("/{policy_id}")
async def delete_policy(
    policy_id: str,
    current_user: CurrentUser = Depends(require_client),
):
    can_access = await PolicyService.can_user_access_policy(str(current_user.id), policy_id)
    if not can_access:
        raise HTTPException(status_code=403, detail="Access denied")

    success = await PolicyService.delete_policy(policy_id)
    if not success:
        raise HTTPException(status_code=404, detail="Policy not found")

    return {"message": "Policy deleted successfully"}


@router.post("/{policy_id}/signatures")
async def send_signature_requests(
    policy_id: str,
    requests: List[SignatureRequest],
    current_user: CurrentUser = Depends(require_client),
):
    company_id = await get_client_company_id(current_user)
    if company_id is None:
        raise HTTPException(status_code=403, detail="Access denied")

    can_access = await PolicyService.can_user_access_policy(str(current_user.id), policy_id)
    if not can_access:
        raise HTTPException(status_code=403, detail="Access denied")

    policy = await PolicyService.get_policy_by_id(policy_id)
    if not policy:
        raise HTTPException(status_code=404, detail="Policy not found")

    if not requests:
        raise HTTPException(status_code=400, detail="At least one signer is required")

    signatures = await SignatureService.create_batch_signature_requests(policy_id, requests)

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

    return {"message": f"Sent {len(signatures)} signature requests", "signatures": len(signatures)}


@router.get("/{policy_id}/signatures", response_model=List[PolicySignatureResponse])
async def list_policy_signatures(
    policy_id: str,
    current_user: CurrentUser = Depends(require_client),
):
    company_id = await get_client_company_id(current_user)
    if company_id is None:
        raise HTTPException(status_code=403, detail="Access denied")

    can_access = await PolicyService.can_user_access_policy(str(current_user.id), policy_id)
    if not can_access:
        raise HTTPException(status_code=403, detail="Access denied")

    signatures = await SignatureService.get_policy_signatures(policy_id)
    return signatures


@router.delete("/signatures/{signature_id}")
async def cancel_signature_request(
    signature_id: str,
    current_user: CurrentUser = Depends(require_client),
):
    company_id = await get_client_company_id(current_user)
    if company_id is None:
        raise HTTPException(status_code=403, detail="Access denied")

    signature = await SignatureService.get_signature_by_id(signature_id)
    if not signature:
        raise HTTPException(status_code=404, detail="Signature request not found")

    can_access = await PolicyService.can_user_access_policy(str(current_user.id), signature.policy_id)
    if not can_access:
        raise HTTPException(status_code=403, detail="Access denied")

    success = await SignatureService.delete_signature(signature_id)
    if not success:
        raise HTTPException(status_code=404, detail="Signature request not found")

    return {"message": "Signature request cancelled"}


@router.post("/signatures/{signature_id}/resend")
async def resend_signature_request(
    signature_id: str,
    current_user: CurrentUser = Depends(require_client),
):
    company_id = await get_client_company_id(current_user)
    if company_id is None:
        raise HTTPException(status_code=403, detail="Access denied")

    signature = await SignatureService.get_signature_by_id(signature_id)
    if not signature:
        raise HTTPException(status_code=404, detail="Signature request not found")

    can_access = await PolicyService.can_user_access_policy(str(current_user.id), signature.policy_id)
    if not can_access:
        raise HTTPException(status_code=403, detail="Access denied")

    signature = await SignatureService.resend_signature(signature_id)
    if not signature:
        raise HTTPException(status_code=400, detail="Cannot resend this signature request")

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

    return {"message": "Signature request resent"}
