"""Matcha Work billing routes — token-based billing."""

from __future__ import annotations

import json
from datetime import datetime
from typing import Optional
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, Response, status
from pydantic import BaseModel, Field

from ...core.models.auth import CurrentUser
from ...core.dependencies import require_admin as require_platform_admin
from ...core.services.stripe_service import StripeService, StripeServiceError
from ...database import get_connection
from ..dependencies import get_client_company_id, require_admin_or_client, require_feature
from ..services import billing_service
from ..services import token_budget_service
from ..services.token_budget_service import (
    SUBSCRIPTION_AMOUNT_CENTS,
    SUBSCRIPTION_PACK_ID,
    SUBSCRIPTION_TOKENS,
)

router = APIRouter(dependencies=[Depends(require_feature("matcha_work"))])
admin_router = APIRouter()


# ── Response models ───────────────────────────────────────────────────────────


class TokenBudgetResponse(BaseModel):
    company_id: UUID
    free_tokens_used: int
    free_token_limit: int
    free_tokens_remaining: int
    subscription_tokens_used: int
    subscription_token_limit: int
    subscription_tokens_remaining: int
    subscription_period_start: Optional[datetime] = None
    total_tokens_remaining: int
    has_active_subscription: bool


class TokenPackResponse(BaseModel):
    pack_id: str
    label: str
    description: str
    amount_cents: int
    currency: str = "usd"
    tokens_per_month: int


class SubscriptionResponse(BaseModel):
    active: bool
    pack_id: Optional[str] = None
    tokens_per_cycle: Optional[int] = None
    amount_cents: Optional[int] = None
    status: Optional[str] = None
    current_period_end: Optional[datetime] = None
    canceled_at: Optional[datetime] = None


class CheckoutRequest(BaseModel):
    success_url: Optional[str] = Field(default=None, max_length=2000)
    cancel_url: Optional[str] = Field(default=None, max_length=2000)


class CheckoutResponse(BaseModel):
    checkout_url: str
    stripe_session_id: str


# ── Client endpoints ──────────────────────────────────────────────────────────


@router.get("/balance")
async def get_billing_balance(
    response: Response,
    current_user: CurrentUser = Depends(require_admin_or_client),
):
    response.headers["Cache-Control"] = "private, max-age=60"
    company_id = await get_client_company_id(current_user)
    if company_id is None:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="No company associated with this account")

    # Admins bypass billing
    if current_user.role == "admin":
        return TokenBudgetResponse(
            company_id=company_id,
            free_tokens_used=0,
            free_token_limit=999_999_999,
            free_tokens_remaining=999_999_999,
            subscription_tokens_used=0,
            subscription_token_limit=0,
            subscription_tokens_remaining=0,
            total_tokens_remaining=999_999_999,
            has_active_subscription=False,
        )

    budget = await token_budget_service.get_token_budget(company_id)
    return TokenBudgetResponse(**budget)


@router.get("/packs", response_model=list[TokenPackResponse])
async def list_packs(
    _: CurrentUser = Depends(require_admin_or_client),
):
    return [
        TokenPackResponse(
            pack_id=SUBSCRIPTION_PACK_ID,
            label="Matcha Work Pro",
            description="5M tokens/month",
            amount_cents=SUBSCRIPTION_AMOUNT_CENTS,
            tokens_per_month=SUBSCRIPTION_TOKENS,
        )
    ]


@router.post("/checkout", response_model=CheckoutResponse)
async def create_checkout_session(
    body: CheckoutRequest,
    current_user: CurrentUser = Depends(require_admin_or_client),
):
    company_id = await get_client_company_id(current_user)
    if company_id is None:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="No company associated with this account")

    stripe_service = StripeService()
    try:
        session = await stripe_service.create_token_subscription_checkout(
            company_id=company_id,
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
        credit_pack_id=SUBSCRIPTION_PACK_ID,
        credits_to_add=0,
        amount_cents=SUBSCRIPTION_AMOUNT_CENTS,
    )

    return CheckoutResponse(checkout_url=checkout_url, stripe_session_id=stripe_session_id)


@router.post("/checkout/personal", response_model=CheckoutResponse)
async def create_personal_checkout_session(
    body: CheckoutRequest,
    current_user: CurrentUser = Depends(require_admin_or_client),
):
    """Start Matcha Work Plus ($20/mo) checkout for an individual user.

    Plus unlocks the pro AI model; token quota is unchanged from free.
    Only individual accounts (or admins for testing) can subscribe —
    business users stay on Pro.
    """
    if current_user.role not in ("individual", "admin"):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Plus is available for personal accounts only",
        )

    company_id = await get_client_company_id(current_user)
    if company_id is None:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="No workspace associated with this account")

    stripe_service = StripeService()
    try:
        session = await stripe_service.create_personal_subscription_checkout(
            company_id=company_id,
            user_id=current_user.id,
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
        credit_pack_id="matcha_work_personal",
        credits_to_add=0,
        amount_cents=2000,
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
        tokens_per_cycle=SUBSCRIPTION_TOKENS,
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
    await token_budget_service.cancel_subscription_budget(company_id)
    return {"canceled": True, "message": "Subscription will not renew at the end of the current period."}


# ── Admin endpoints ───────────────────────────────────────────────────────────


class CompanyTokenSummary(BaseModel):
    company_id: UUID
    company_name: str
    company_status: str
    free_tokens_used: int
    free_token_limit: int
    free_tokens_remaining: int
    subscription_token_limit: int
    subscription_tokens_remaining: int
    has_active_subscription: bool


class AdminGrantTokensRequest(BaseModel):
    tokens: int = Field(..., gt=0, description="Number of tokens to grant")
    description: Optional[str] = Field(None, max_length=500)


class TokenUsageEvent(BaseModel):
    id: UUID
    user_id: Optional[UUID] = None
    thread_id: Optional[UUID] = None
    model: Optional[str] = None
    prompt_tokens: Optional[int] = None
    completion_tokens: Optional[int] = None
    total_tokens: Optional[int] = None
    operation: Optional[str] = None
    cost_dollars: Optional[float] = None
    created_at: datetime


class CompanyTokenDetailResponse(BaseModel):
    budget: TokenBudgetResponse
    recent_usage: list[TokenUsageEvent]


class IndividualUserSummary(BaseModel):
    user_id: UUID
    email: str
    name: Optional[str] = None
    company_id: UUID
    created_at: Optional[datetime] = None
    free_tokens_used: int = 0
    free_token_limit: int = 0
    free_tokens_remaining: int = 0
    subscription_token_limit: int = 0
    subscription_tokens_remaining: int = 0
    has_active_subscription: bool = False
    beta_features: dict = {}
    is_suspended: bool = False
    subscription: Optional[dict] = None


@admin_router.get("/admin/individuals")
async def admin_list_individual_users(
    current_user: CurrentUser = Depends(require_platform_admin),
):
    """List all individual/personal account users with token budgets + Stripe sub state."""
    async with get_connection() as conn:
        rows = await conn.fetch(
            """
            SELECT u.id AS user_id, u.email, u.created_at, u.is_suspended,
                   c.id AS company_id, c.name,
                   COALESCE(u.beta_features, '{}'::jsonb) AS beta_features,
                   COALESCE(t.free_tokens_used, 0) AS free_tokens_used,
                   COALESCE(t.free_token_limit, 0) AS free_token_limit,
                   COALESCE(t.subscription_tokens_used, 0) AS subscription_tokens_used,
                   COALESCE(t.subscription_token_limit, 0) AS subscription_token_limit,
                   sub.pack_id          AS sub_pack_id,
                   sub.status           AS sub_status,
                   sub.amount_cents     AS sub_amount_cents,
                   sub.stripe_subscription_id AS sub_stripe_sub_id,
                   sub.stripe_customer_id     AS sub_stripe_customer_id,
                   sub.current_period_end     AS sub_current_period_end,
                   sub.canceled_at            AS sub_canceled_at
            FROM users u
            JOIN clients cl ON cl.user_id = u.id
            JOIN companies c ON c.id = cl.company_id
            LEFT JOIN mw_token_budgets t ON t.company_id = c.id
            LEFT JOIN LATERAL (
                SELECT pack_id, status, amount_cents, stripe_subscription_id,
                       stripe_customer_id, current_period_end, canceled_at
                FROM mw_subscriptions
                WHERE company_id = c.id
                ORDER BY (status = 'active') DESC, created_at DESC
                LIMIT 1
            ) sub ON TRUE
            WHERE u.role = 'individual' AND c.is_personal = true
            ORDER BY u.created_at DESC
            """
        )
    out: list[IndividualUserSummary] = []
    for r in rows:
        sub_payload = None
        if r["sub_pack_id"]:
            sub_payload = {
                "pack_id": r["sub_pack_id"],
                "status": r["sub_status"],
                "amount_cents": r["sub_amount_cents"],
                "stripe_subscription_id": r["sub_stripe_sub_id"],
                "stripe_customer_id": r["sub_stripe_customer_id"],
                "current_period_end": r["sub_current_period_end"].isoformat() if r["sub_current_period_end"] else None,
                "canceled_at": r["sub_canceled_at"].isoformat() if r["sub_canceled_at"] else None,
            }
        out.append(
            IndividualUserSummary(
                user_id=r["user_id"],
                email=r["email"],
                name=r["name"],
                company_id=r["company_id"],
                created_at=r["created_at"],
                beta_features=json.loads(r["beta_features"]) if isinstance(r["beta_features"], str) else dict(r["beta_features"]),
                free_tokens_used=r["free_tokens_used"],
                free_token_limit=r["free_token_limit"],
                free_tokens_remaining=max(0, r["free_token_limit"] - r["free_tokens_used"]),
                subscription_token_limit=r["subscription_token_limit"],
                subscription_tokens_remaining=max(0, r["subscription_token_limit"] - r["subscription_tokens_used"]),
                has_active_subscription=r["subscription_token_limit"] > 0,
                is_suspended=bool(r["is_suspended"]),
                subscription=sub_payload,
            )
        )
    return out


@admin_router.get("/admin/companies")
async def admin_list_company_tokens(
    current_user: CurrentUser = Depends(require_platform_admin),
):
    """List all companies with their token budgets."""
    async with get_connection() as conn:
        rows = await conn.fetch(
            """
            SELECT
                c.id, c.name, COALESCE(c.status, 'approved') AS status,
                COALESCE(t.free_tokens_used, 0) AS free_tokens_used,
                COALESCE(t.free_token_limit, 0) AS free_token_limit,
                COALESCE(t.subscription_tokens_used, 0) AS subscription_tokens_used,
                COALESCE(t.subscription_token_limit, 0) AS subscription_token_limit
            FROM companies c
            LEFT JOIN mw_token_budgets t ON t.company_id = c.id
            ORDER BY c.name
            """
        )
    return [
        CompanyTokenSummary(
            company_id=row["id"],
            company_name=row["name"],
            company_status=row["status"],
            free_tokens_used=row["free_tokens_used"],
            free_token_limit=row["free_token_limit"],
            free_tokens_remaining=max(0, row["free_token_limit"] - row["free_tokens_used"]),
            subscription_token_limit=row["subscription_token_limit"],
            subscription_tokens_remaining=max(0, row["subscription_token_limit"] - row["subscription_tokens_used"]),
            has_active_subscription=row["subscription_token_limit"] > 0,
        )
        for row in rows
    ]


@admin_router.post("/admin/companies/{company_id}/tokens")
async def admin_grant_tokens(
    company_id: UUID,
    body: AdminGrantTokensRequest,
    current_user: CurrentUser = Depends(require_platform_admin),
):
    """Grant tokens to a company (adds to free_token_limit)."""
    async with get_connection() as conn:
        company_exists = await conn.fetchval(
            "SELECT EXISTS(SELECT 1 FROM companies WHERE id = $1)", company_id
        )
    if not company_exists:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Company not found")

    budget = await token_budget_service.grant_tokens(
        company_id=company_id,
        amount=body.tokens,
        description=body.description or f"Admin granted {body.tokens:,} tokens",
        granted_by=current_user.id,
    )
    return budget


@admin_router.get("/admin/companies/{company_id}/token-usage")
async def admin_company_token_usage(
    company_id: UUID,
    limit: int = Query(50, ge=1, le=200),
    current_user: CurrentUser = Depends(require_platform_admin),
):
    """Get token budget and recent usage events for a company."""
    budget = await token_budget_service.get_token_budget(company_id)

    async with get_connection() as conn:
        rows = await conn.fetch(
            """SELECT id, user_id, thread_id, model, prompt_tokens,
                      completion_tokens, total_tokens, operation,
                      cost_dollars, created_at
               FROM mw_token_usage_events
               WHERE company_id = $1
               ORDER BY created_at DESC
               LIMIT $2""",
            company_id, limit,
        )

    return CompanyTokenDetailResponse(
        budget=TokenBudgetResponse(**budget),
        recent_usage=[
            TokenUsageEvent(
                id=r["id"],
                user_id=r["user_id"],
                thread_id=r["thread_id"],
                model=r["model"],
                prompt_tokens=r["prompt_tokens"],
                completion_tokens=r["completion_tokens"],
                total_tokens=r["total_tokens"],
                operation=r["operation"],
                cost_dollars=float(r["cost_dollars"]) if r["cost_dollars"] else None,
                created_at=r["created_at"],
            )
            for r in rows
        ],
    )
