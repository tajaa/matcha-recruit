"""Matcha Work billing routes."""

from __future__ import annotations

from datetime import datetime
from typing import Optional
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import BaseModel, Field

from ...core.models.auth import CurrentUser
from ...core.dependencies import require_admin as require_platform_admin
from ...core.services.stripe_service import StripeService, StripeServiceError
from ...database import get_connection
from ..dependencies import get_client_company_id, require_admin_or_client, require_feature
from ..services import billing_service

router = APIRouter(dependencies=[Depends(require_feature("matcha_work"))])
admin_router = APIRouter()


class CreditTransactionResponse(BaseModel):
    id: UUID
    company_id: UUID
    transaction_type: str
    credits_delta: int
    credits_after: int
    description: Optional[str] = None
    reference_id: Optional[UUID] = None
    created_by: Optional[UUID] = None
    created_by_email: Optional[str] = None
    created_at: datetime


class BillingBalanceResponse(BaseModel):
    company_id: UUID
    credits_remaining: int
    total_credits_purchased: int
    total_credits_granted: int
    updated_at: Optional[datetime] = None
    recent_transactions: list[CreditTransactionResponse]


class CreditPackResponse(BaseModel):
    pack_id: str
    credits: int
    base_cents: int
    amount_cents: int
    fee_cents: int
    label: str
    description: str
    currency: str = "usd"


class SubscriptionResponse(BaseModel):
    active: bool
    pack_id: Optional[str] = None
    credits_per_cycle: Optional[int] = None
    amount_cents: Optional[int] = None
    status: Optional[str] = None
    current_period_end: Optional[datetime] = None
    canceled_at: Optional[datetime] = None


class CheckoutRequest(BaseModel):
    pack_id: str = Field(..., min_length=1, max_length=50)
    auto_renew: bool = False
    success_url: Optional[str] = Field(default=None, max_length=2000)
    cancel_url: Optional[str] = Field(default=None, max_length=2000)


class CheckoutResponse(BaseModel):
    checkout_url: str
    stripe_session_id: str


class TransactionHistoryResponse(BaseModel):
    items: list[CreditTransactionResponse]
    total: int
    limit: int
    offset: int


@router.get("/balance", response_model=BillingBalanceResponse)
async def get_billing_balance(
    current_user: CurrentUser = Depends(require_admin_or_client),
):
    company_id = await get_client_company_id(current_user)
    if company_id is None:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="No company associated with this account")

    balance = await billing_service.get_credit_balance(company_id)
    history = await billing_service.get_transaction_history(company_id, limit=20, offset=0)

    return BillingBalanceResponse(
        company_id=balance["company_id"],
        credits_remaining=balance["credits_remaining"],
        total_credits_purchased=balance["total_credits_purchased"],
        total_credits_granted=balance["total_credits_granted"],
        updated_at=balance["updated_at"],
        recent_transactions=[CreditTransactionResponse(**item) for item in history["items"]],
    )


@router.get("/packs", response_model=list[CreditPackResponse])
async def list_credit_packs(
    _: CurrentUser = Depends(require_admin_or_client),
):
    stripe_service = StripeService()
    packs = stripe_service.list_credit_packs()
    return [CreditPackResponse(**pack) for pack in packs]


@router.post("/checkout", response_model=CheckoutResponse)
async def create_checkout_session(
    body: CheckoutRequest,
    current_user: CurrentUser = Depends(require_admin_or_client),
):
    company_id = await get_client_company_id(current_user)
    if company_id is None:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="No company associated with this account")

    stripe_service = StripeService()
    pack = stripe_service.get_credit_pack(body.pack_id)
    if pack is None:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Invalid credit pack")

    try:
        if body.auto_renew:
            session = await stripe_service.create_subscription_checkout_session(
                company_id=company_id,
                pack_id=body.pack_id,
                success_url=body.success_url,
                cancel_url=body.cancel_url,
            )
        else:
            session = await stripe_service.create_checkout_session(
                company_id=company_id,
                pack_id=body.pack_id,
                success_url=body.success_url,
                cancel_url=body.cancel_url,
            )
    except StripeServiceError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc

    stripe_session_id = str(getattr(session, "id", "") or "")
    checkout_url = str(getattr(session, "url", "") or "")
    if not stripe_session_id or not checkout_url:
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail="Stripe checkout session did not return expected fields",
        )

    await billing_service.create_pending_stripe_session(
        company_id=company_id,
        stripe_session_id=stripe_session_id,
        credit_pack_id=body.pack_id,
        credits_to_add=int(pack["credits"]),
        amount_cents=int(pack["amount_cents"]),
    )

    return CheckoutResponse(checkout_url=checkout_url, stripe_session_id=stripe_session_id)


@router.get("/subscription", response_model=SubscriptionResponse)
async def get_subscription(
    current_user: CurrentUser = Depends(require_admin_or_client),
):
    company_id = await get_client_company_id(current_user)
    if company_id is None:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="No company associated with this account")

    sub = await billing_service.get_active_subscription(company_id)
    if sub is None:
        return SubscriptionResponse(active=False)

    return SubscriptionResponse(
        active=True,
        pack_id=sub["pack_id"],
        credits_per_cycle=int(sub["credits_per_cycle"]),
        amount_cents=int(sub["amount_cents"]),
        status=sub["status"],
        current_period_end=sub["current_period_end"],
        canceled_at=sub["canceled_at"],
    )


@router.delete("/subscription", status_code=status.HTTP_200_OK)
async def cancel_subscription(
    current_user: CurrentUser = Depends(require_admin_or_client),
):
    company_id = await get_client_company_id(current_user)
    if company_id is None:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="No company associated with this account")

    sub = await billing_service.get_active_subscription(company_id)
    if sub is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="No active subscription found")

    stripe_service = StripeService()
    try:
        await stripe_service.cancel_subscription(sub["stripe_subscription_id"])
    except StripeServiceError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc

    await billing_service.cancel_subscription_record(sub["stripe_subscription_id"])
    return {"canceled": True, "message": "Subscription will not renew at the end of the current period."}


@router.get("/transactions", response_model=TransactionHistoryResponse)
async def list_billing_transactions(
    limit: int = Query(50, ge=1, le=200),
    offset: int = Query(0, ge=0),
    current_user: CurrentUser = Depends(require_admin_or_client),
):
    company_id = await get_client_company_id(current_user)
    if company_id is None:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="No company associated with this account")

    history = await billing_service.get_transaction_history(
        company_id,
        limit=limit,
        offset=offset,
    )

    return TransactionHistoryResponse(
        items=[CreditTransactionResponse(**item) for item in history["items"]],
        total=history["total"],
        limit=history["limit"],
        offset=history["offset"],
    )


# ── Admin-only endpoints (no feature gate, platform admin only) ──────────────


class CompanyCreditSummary(BaseModel):
    company_id: UUID
    company_name: str
    company_status: str
    credits_remaining: int
    total_credits_purchased: int
    total_credits_granted: int
    updated_at: Optional[datetime] = None


class AdminGrantRequest(BaseModel):
    credits: int = Field(..., description="Positive = grant, negative = deduct")
    description: Optional[str] = Field(None, max_length=500)


@admin_router.get("/admin/companies", response_model=list[CompanyCreditSummary])
async def admin_list_company_credits(
    current_user: CurrentUser = Depends(require_platform_admin),
):
    """List all companies with their Matcha Work credit balances."""
    async with get_connection() as conn:
        rows = await conn.fetch(
            """
            SELECT
                c.id, c.name, COALESCE(c.status, 'approved') AS status,
                COALESCE(b.credits_remaining, 0)        AS credits_remaining,
                COALESCE(b.total_credits_purchased, 0)  AS total_credits_purchased,
                COALESCE(b.total_credits_granted, 0)    AS total_credits_granted,
                b.updated_at
            FROM companies c
            LEFT JOIN mw_credit_balances b ON b.company_id = c.id
            ORDER BY c.name
            """
        )
    return [
        CompanyCreditSummary(
            company_id=row["id"],
            company_name=row["name"],
            company_status=row["status"],
            credits_remaining=int(row["credits_remaining"]),
            total_credits_purchased=int(row["total_credits_purchased"]),
            total_credits_granted=int(row["total_credits_granted"]),
            updated_at=row["updated_at"],
        )
        for row in rows
    ]


@admin_router.post("/admin/companies/{company_id}/grant", response_model=CreditTransactionResponse)
async def admin_grant_credits_endpoint(
    company_id: UUID,
    body: AdminGrantRequest,
    current_user: CurrentUser = Depends(require_platform_admin),
):
    """Grant or adjust credits for a company."""
    async with get_connection() as conn:
        company_exists = await conn.fetchval(
            "SELECT EXISTS(SELECT 1 FROM companies WHERE id = $1)", company_id
        )
    if not company_exists:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Company not found")

    result = await billing_service.grant_credits(
        company_id=company_id,
        credits=body.credits,
        description=body.description or ("Admin grant" if body.credits > 0 else "Admin adjustment"),
        granted_by=current_user.id,
    )
    return CreditTransactionResponse(**result["transaction"])
