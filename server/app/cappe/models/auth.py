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
    # ("business of one") who gets hired/booked; creator = influencer/content
    # creator on the creator marketplace (media kit + collab offers). Same
    # engine, different framing.
    account_type: Literal["business", "personal", "creator"] = "business"
    # The paid plan picked on the pricing page, if any. Remembered across the
    # email-confirmation hop so the person lands in checkout for it. Grants
    # nothing by itself.
    intended_plan: Optional[str] = Field(default=None, max_length=40, pattern=r"^[a-z0-9_]+$")
    intended_interval: Optional[Literal["month", "year"]] = None


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
    # NOTE: subscription status is deliberately NOT carried here. It would mean
    # joining cappe_subscriptions in the auth dependency that every request
    # passes through, which turns a missing migration into a total outage.
    # GET /billing/subscription serves it instead.


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
    intended_plan: Optional[str] = None
    intended_interval: Optional[str] = None


class CappeVerifyResponse(CappeTokenResponse):
    """A fresh session plus the plan picked at signup, when there was one, so
    the client can continue to checkout. Returned once: confirming clears it."""
    intended_plan: Optional[str] = None
    intended_interval: Optional[str] = None


class CappeVerifyRequest(BaseModel):
    token: str


class CappeResendRequest(BaseModel):
    email: EmailStr


class CappeForgotPasswordRequest(BaseModel):
    email: EmailStr


class CappeResetPasswordRequest(BaseModel):
    token: str = Field(min_length=1, max_length=200)
    # Same bounds as signup.
    password: str = Field(min_length=8, max_length=200)


__all__ = [
    "CappeSignup",
    "CappeLogin",
    "CappeRefreshRequest",
    "CappeAccount",
    "CappeTokenResponse",
    "CappeSignupResponse",
    "CappeVerifyResponse",
    "CappeVerifyRequest",
    "CappeResendRequest",
    "CappeForgotPasswordRequest",
    "CappeResetPasswordRequest",
]
