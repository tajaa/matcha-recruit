from datetime import datetime
from typing import Optional, Literal
from uuid import UUID

from pydantic import BaseModel, EmailStr


PolicyStatus = Literal["draft", "active", "archived"]
SignatureStatus = Literal["pending", "signed", "declined", "expired"]
SignerType = Literal["candidate", "employee", "external"]


class Policy(BaseModel):
    id: UUID
    company_id: UUID
    title: str
    description: Optional[str] = None
    content: str
    file_url: Optional[str] = None
    version: str
    status: PolicyStatus
    created_at: datetime
    updated_at: datetime
    created_by: Optional[UUID] = None


class PolicyCreate(BaseModel):
    title: str
    description: Optional[str] = None
    content: str = ""
    file_url: Optional[str] = None
    version: Optional[str] = "1.0"
    status: Optional[PolicyStatus] = "draft"


class PolicyUpdate(BaseModel):
    title: Optional[str] = None
    description: Optional[str] = None
    content: Optional[str] = None
    file_url: Optional[str] = None
    version: Optional[str] = None
    status: Optional[PolicyStatus] = None


class PolicyResponse(BaseModel):
    id: UUID
    company_id: UUID
    company_name: Optional[str] = None
    title: str
    description: Optional[str] = None
    content: str
    file_url: Optional[str] = None
    version: str
    status: PolicyStatus
    signature_count: Optional[int] = None
    pending_signatures: Optional[int] = None
    signed_count: Optional[int] = None
    created_at: datetime
    updated_at: datetime
    created_by: Optional[UUID] = None


class PolicySignature(BaseModel):
    id: UUID
    policy_id: UUID
    signer_type: SignerType
    signer_id: Optional[UUID] = None
    signer_name: str
    signer_email: str
    status: SignatureStatus
    signed_at: Optional[datetime] = None
    signature_data: Optional[str] = None
    ip_address: Optional[str] = None
    token: str
    expires_at: datetime
    created_at: datetime


class SignatureRequest(BaseModel):
    name: str
    email: EmailStr
    type: SignerType
    id: Optional[UUID] = None


class SignatureCreate(BaseModel):
    signature_data: Optional[str] = None
    accepted: bool = True


class PolicySignatureResponse(BaseModel):
    id: UUID
    policy_id: UUID
    policy_title: Optional[str] = None
    policy_content: Optional[str] = None
    policy_file_url: Optional[str] = None
    signer_type: SignerType
    signer_id: Optional[UUID] = None
    signer_name: str
    signer_email: str
    status: SignatureStatus
    signed_at: Optional[datetime] = None
    signature_data: Optional[str] = None
    expires_at: datetime
    created_at: datetime


class PolicySignatureWithToken(PolicySignatureResponse):
    token: str
