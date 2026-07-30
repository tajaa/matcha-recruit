"""Pydantic shapes — Cappe auth (signup/login/tokens/account)."""
from typing import Literal, Optional
from uuid import UUID

from pydantic import BaseModel, EmailStr, Field

# --- Auth -------------------------------------------------------------------

class CappeSignup(BaseModel):
    email: EmailStr
    password: str = Field(min_length=8, max_length=200)
    name: Optional[str] = Field(default=None, max_length=255)
    # business = an organization's storefront; personal = a solo professional
    # ("business of one") who gets hired/booked. Same engine, different framing.
    account_type: Literal["business", "personal"] = "business"


class CappeLogin(BaseModel):
    email: EmailStr
    password: str = Field(max_length=200)


class CappeRefreshRequest(BaseModel):
    refresh_token: str


class CappeAccount(BaseModel):
    """The authenticated Cappe identity (returned by require_cappe_account)."""
    id: UUID
    email: str
    name: Optional[str] = None
    plan: str = "free"
    status: str = "active"
    account_type: str = "business"
    # Platform staff flag for the in-Cappe admin surface (plans, prices, take
    # rates). Not a tenant-facing capability — defaults false for everyone.
    is_platform_admin: bool = False
    # Live subscription status, when there is one ('trialing'/'active'/
    # 'past_due'/…). None on free accounts. Carried here so the billing UI can
    # render without a second round-trip.
    subscription_status: Optional[str] = None


class CappeTokenResponse(BaseModel):
    access_token: str
    refresh_token: str
    expires_in: int
    account: CappeAccount


class CappeSignupResponse(BaseModel):
    """Signup result. Real signups must confirm their email first
    (`verification_required=True`, no tokens). Reserved test-domain signups
    (which the email guard won't deliver to) auto-verify and get tokens inline
    so dev/seed flows still work."""
    verification_required: bool
    email: str
    access_token: Optional[str] = None
    refresh_token: Optional[str] = None
    expires_in: Optional[int] = None
    account: Optional[CappeAccount] = None


class CappeVerifyRequest(BaseModel):
    token: str


class CappeResendRequest(BaseModel):
    email: EmailStr


__all__ = [
    "CappeSignup",
    "CappeLogin",
    "CappeRefreshRequest",
    "CappeAccount",
    "CappeTokenResponse",
    "CappeSignupResponse",
    "CappeVerifyRequest",
    "CappeResendRequest",
]
