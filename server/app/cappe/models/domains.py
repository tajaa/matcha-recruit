"""Pydantic shapes — Cappe domain reselling (Porkbun)."""
from datetime import datetime
from typing import Literal, Optional
from uuid import UUID

from pydantic import BaseModel, Field, field_validator

from .sites import _DOMAIN_RE, normalize_custom_domain

class CappeDomainSearchResult(BaseModel):
    """One candidate from a domain search."""
    domain: str
    available: bool
    # Tenant-facing yearly price (wholesale + markup). None if pricing unknown.
    price_cents: Optional[int] = None


class CappeDomainPurchaseRequest(BaseModel):
    site_id: UUID
    domain: str
    success_url: Optional[str] = None
    cancel_url: Optional[str] = None

    @field_validator("domain")
    @classmethod
    def _check_domain(cls, v: str) -> str:
        v = (v or "").strip().lower().rstrip(".")
        if not _DOMAIN_RE.match(v) or len(v) > 255:
            raise ValueError("Enter a valid domain (e.g. yourbrand.com)")
        return v


class CappeDomainConnectRequest(BaseModel):
    """Attach a domain the tenant already owns (BYO — no registration)."""
    site_id: UUID
    domain: str
    _norm = field_validator("domain")(normalize_custom_domain)


class CappeDomainCheckoutResponse(BaseModel):
    domain_id: UUID
    checkout_url: str


class CappeDomain(BaseModel):
    id: UUID
    site_id: UUID
    domain: str
    kind: Literal["register", "connect"] = "register"
    status: Literal["pending", "registering", "active", "failed", "expired"]
    price_cents: Optional[int] = None
    auto_renew: bool = True
    expires_at: Optional[datetime] = None
    failure_reason: Optional[str] = None
    # Set on a pending 'connect' domain: add a TXT record at
    # `_cappe-verify.<domain>` with this value, then call /verify.
    verification_token: Optional[str] = None
    transfer_requested_at: Optional[datetime] = None
    created_at: datetime


class CappeDnsRecord(BaseModel):
    id: str
    type: str
    name: str  # full host as Porkbun returns it (FQDN)
    content: str
    ttl: Optional[str] = None
    prio: Optional[str] = None


class CappeDnsRecordInput(BaseModel):
    type: Literal["A", "AAAA", "CNAME", "MX", "TXT", "NS", "ALIAS", "CAA", "SRV"]
    # Subdomain only ('' = apex, 'www', 'mail'); Porkbun appends the domain.
    name: str = Field(default="", max_length=255)
    content: str = Field(min_length=1, max_length=2048)
    ttl: int = Field(default=600, ge=600)
    prio: Optional[int] = Field(default=None, ge=0)


class CappeDomainAutoRenewUpdate(BaseModel):
    auto_renew: bool


__all__ = [
    "CappeDomainSearchResult",
    "CappeDomainPurchaseRequest",
    "CappeDomainConnectRequest",
    "CappeDomainCheckoutResponse",
    "CappeDomain",
    "CappeDnsRecord",
    "CappeDnsRecordInput",
    "CappeDomainAutoRenewUpdate",
]
