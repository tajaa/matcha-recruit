"""Authenticated Tell-Us loyalty routes."""
from typing import Optional
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, status
from fastapi.encoders import jsonable_encoder

from ...database import get_connection
from ..dependencies import (
    require_brand_capability,
    require_verified_consumer,
)
from ..models.loyalty import (
    LoyaltyProgramPut,
    LoyaltyRedemptionCreate,
    LoyaltyRedeemIn,
    LoyaltyRewardCreate,
    LoyaltyRewardPatch,
    LoyaltySocialDecisionIn,
    LoyaltySocialSubmissionCreate,
    LoyaltyPurchaseIn,
)
from ..models.tellus import TellusAccount
from ..services import loyalty_service
from ..services.access_service import BrandAccessContext, resolve_store_access


router = APIRouter()

LOYALTY_MANAGER = require_brand_capability("rewards.manage")
LOYALTY_OPERATOR = require_brand_capability("redemptions.redeem")
LOYALTY_REDEEMER = require_brand_capability("redemptions.redeem", paid=False)


def _raise(error: loyalty_service.LoyaltyError) -> None:
    raise HTTPException(
        status_code=error.http_status,
        detail=jsonable_encoder({"code": error.code, "message": error.message, **error.extra}),
    )


@router.get("/me/loyalty/programs")
async def list_my_programs(account: TellusAccount = Depends(require_verified_consumer)):
    async with get_connection() as conn:
        return await loyalty_service.list_consumer_programs(conn, account.id)


@router.get("/me/loyalty/programs/{brand_id}")
async def get_my_program(brand_id: UUID, account: TellusAccount = Depends(require_verified_consumer)):
    async with get_connection() as conn:
        try:
            return await loyalty_service.get_consumer_program(
                conn, account_id=account.id, brand_id=brand_id
            )
        except loyalty_service.LoyaltyError as error:
            _raise(error)


@router.post("/me/loyalty/programs/{brand_id}/member-qr")
async def member_qr(brand_id: UUID, account: TellusAccount = Depends(require_verified_consumer)):
    async with get_connection() as conn:
        try:
            return await loyalty_service.mint_member_qr(
                conn, brand_id=brand_id, account_id=account.id
            )
        except loyalty_service.LoyaltyError as error:
            _raise(error)


@router.get("/me/loyalty/programs/{brand_id}/ledger")
async def my_ledger(
    brand_id: UUID,
    account: TellusAccount = Depends(require_verified_consumer),
    limit: int = Query(default=50, ge=1, le=200),
    offset: int = Query(default=0, ge=0),
):
    async with get_connection() as conn:
        return await loyalty_service.list_ledger(
            conn, brand_id=brand_id, account_id=account.id, limit=limit, offset=offset
        )


@router.post("/me/loyalty/programs/{brand_id}/redemptions", status_code=status.HTTP_201_CREATED)
async def issue_redemption(
    brand_id: UUID,
    body: LoyaltyRedemptionCreate,
    account: TellusAccount = Depends(require_verified_consumer),
):
    async with get_connection() as conn:
        try:
            return await loyalty_service.issue_redemption(
                conn,
                brand_id=brand_id,
                account_id=account.id,
                reward_id=body.reward_id,
                client_request_id=body.client_request_id,
            )
        except loyalty_service.LoyaltyError as error:
            _raise(error)


@router.get("/me/loyalty/redemptions")
async def my_redemptions(account: TellusAccount = Depends(require_verified_consumer)):
    async with get_connection() as conn:
        return await loyalty_service.list_redemptions(conn, account_id=account.id)


@router.post("/me/loyalty/programs/{brand_id}/social-submissions", status_code=status.HTTP_201_CREATED)
async def submit_social(
    brand_id: UUID,
    body: LoyaltySocialSubmissionCreate,
    account: TellusAccount = Depends(require_verified_consumer),
):
    async with get_connection() as conn:
        try:
            return await loyalty_service.submit_social_post(
                conn, brand_id=brand_id, account_id=account.id, data=body
            )
        except loyalty_service.LoyaltyError as error:
            _raise(error)


@router.get("/me/loyalty/programs/{brand_id}/social-submissions")
async def my_social(brand_id: UUID, account: TellusAccount = Depends(require_verified_consumer)):
    async with get_connection() as conn:
        return await loyalty_service.list_social_submissions(
            conn, brand_id=brand_id, account_id=account.id
        )


@router.delete("/me/loyalty/social-submissions/{submission_id}", status_code=status.HTTP_204_NO_CONTENT)
async def withdraw_social(
    submission_id: UUID,
    account: TellusAccount = Depends(require_verified_consumer),
):
    async with get_connection() as conn:
        try:
            await loyalty_service.withdraw_social_submission(
                conn, submission_id=submission_id, account_id=account.id
            )
        except loyalty_service.LoyaltyError as error:
            _raise(error)


@router.get("/businesses/{brand_id}/loyalty/program")
async def get_builder(
    brand_id: UUID,
    context: BrandAccessContext = Depends(LOYALTY_MANAGER),
):
    async with get_connection() as conn:
        try:
            return await loyalty_service.get_program_config(conn, brand_id)
        except loyalty_service.LoyaltyError as error:
            _raise(error)


@router.put("/businesses/{brand_id}/loyalty/program")
async def save_builder(
    brand_id: UUID,
    body: LoyaltyProgramPut,
    context: BrandAccessContext = Depends(LOYALTY_MANAGER),
):
    async with get_connection() as conn:
        try:
            return await loyalty_service.put_program_config(
                conn, brand_id=brand_id, actor_account_id=context.account.id, data=body
            )
        except loyalty_service.LoyaltyError as error:
            _raise(error)


@router.get("/businesses/{brand_id}/loyalty/rewards")
async def builder_rewards(
    brand_id: UUID,
    context: BrandAccessContext = Depends(LOYALTY_MANAGER),
):
    async with get_connection() as conn:
        return await loyalty_service.list_rewards(conn, brand_id, include_inactive=True)


@router.post("/businesses/{brand_id}/loyalty/rewards", status_code=status.HTTP_201_CREATED)
async def create_builder_reward(
    brand_id: UUID,
    body: LoyaltyRewardCreate,
    context: BrandAccessContext = Depends(LOYALTY_MANAGER),
):
    async with get_connection() as conn:
        return await loyalty_service.create_reward(
            conn, brand_id=brand_id, actor_account_id=context.account.id, data=body
        )


@router.patch("/businesses/{brand_id}/loyalty/rewards/{reward_id}")
async def patch_builder_reward(
    brand_id: UUID,
    reward_id: UUID,
    body: LoyaltyRewardPatch,
    context: BrandAccessContext = Depends(LOYALTY_MANAGER),
):
    async with get_connection() as conn:
        try:
            return await loyalty_service.patch_reward(
                conn,
                brand_id=brand_id,
                reward_id=reward_id,
                actor_account_id=context.account.id,
                data=body,
            )
        except loyalty_service.LoyaltyError as error:
            _raise(error)


@router.get("/businesses/{brand_id}/loyalty/social-submissions")
async def brand_social_queue(
    brand_id: UUID,
    status_filter: Optional[str] = Query(default=None, alias="status"),
    context: BrandAccessContext = Depends(LOYALTY_MANAGER),
):
    async with get_connection() as conn:
        rows = await loyalty_service.list_social_submissions(conn, brand_id=brand_id)
    return [row for row in rows if status_filter is None or row["status"] == status_filter]


@router.post("/businesses/{brand_id}/loyalty/social-submissions/{submission_id}/approve")
async def approve_social(
    brand_id: UUID,
    submission_id: UUID,
    body: LoyaltySocialDecisionIn,
    context: BrandAccessContext = Depends(LOYALTY_MANAGER),
):
    async with get_connection() as conn:
        try:
            return await loyalty_service.decide_social_submission(
                conn,
                brand_id=brand_id,
                submission_id=submission_id,
                actor_account_id=context.account.id,
                decision="approved",
                note=body.note,
            )
        except loyalty_service.LoyaltyError as error:
            _raise(error)


@router.post("/businesses/{brand_id}/loyalty/social-submissions/{submission_id}/reject")
async def reject_social(
    brand_id: UUID,
    submission_id: UUID,
    body: LoyaltySocialDecisionIn,
    context: BrandAccessContext = Depends(LOYALTY_MANAGER),
):
    async with get_connection() as conn:
        try:
            return await loyalty_service.decide_social_submission(
                conn,
                brand_id=brand_id,
                submission_id=submission_id,
                actor_account_id=context.account.id,
                decision="rejected",
                note=body.note,
            )
        except loyalty_service.LoyaltyError as error:
            _raise(error)


@router.get("/businesses/{brand_id}/loyalty/summary")
async def builder_summary(
    brand_id: UUID,
    context: BrandAccessContext = Depends(LOYALTY_MANAGER),
):
    async with get_connection() as conn:
        return await loyalty_service.loyalty_summary(conn, brand_id)


@router.post("/businesses/{brand_id}/stores/{store_id}/loyalty/purchase")
async def counter_purchase(
    brand_id: UUID,
    store_id: UUID,
    body: LoyaltyPurchaseIn,
    context: BrandAccessContext = Depends(LOYALTY_OPERATOR),
):
    async with get_connection() as conn:
        try:
            store = await resolve_store_access(conn, context, store_id)
            return await loyalty_service.record_purchase(
                conn,
                brand=context,
                store=store,
                raw_member_token=body.member_token,
                amount_cents=body.amount_cents,
            )
        except loyalty_service.LoyaltyError as error:
            _raise(error)


@router.post("/businesses/{brand_id}/stores/{store_id}/loyalty/redemptions/redeem")
async def counter_redeem(
    brand_id: UUID,
    store_id: UUID,
    body: LoyaltyRedeemIn,
    context: BrandAccessContext = Depends(LOYALTY_REDEEMER),
):
    async with get_connection() as conn:
        try:
            store = await resolve_store_access(conn, context, store_id)
            return await loyalty_service.redeem_reward(
                conn, brand=context, store=store, raw_redemption_token=body.redemption_token
            )
        except loyalty_service.LoyaltyError as error:
            _raise(error)
