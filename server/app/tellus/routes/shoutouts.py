"""Brand shoutout-radar setup and human review queue."""
from typing import Literal
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query

from ...database import get_connection
from ..dependencies import require_brand_capability
from ..models.shoutouts import (
    ShoutoutApproveIn, ShoutoutConfigOut, ShoutoutConfigPut, ShoutoutEnableIn,
    ShoutoutMentionOut, ShoutoutRejectIn, ShoutoutRunOut,
)
from ..services.access_service import BrandAccessContext
from ..services.shoutout import config_service, review_service

router = APIRouter()
SHOUTOUT_MANAGER = require_brand_capability("promos.manage")


def _review_error(error: review_service.ShoutoutReviewError) -> None:
    raise HTTPException(error.status, detail={"code": error.code, "message": error.message})


@router.get("/businesses/{brand_id}/shoutouts/config", response_model=ShoutoutConfigOut)
async def get_config(brand_id: UUID, context: BrandAccessContext = Depends(SHOUTOUT_MANAGER)):
    async with get_connection() as conn:
        return await config_service.get_config(conn, brand_id)


@router.put("/businesses/{brand_id}/shoutouts/config", response_model=ShoutoutConfigOut)
async def put_config(brand_id: UUID, body: ShoutoutConfigPut, context: BrandAccessContext = Depends(SHOUTOUT_MANAGER)):
    async with get_connection() as conn:
        try:
            return await config_service.put_config(conn, brand_id, body)
        except ValueError as error:
            raise HTTPException(422, str(error))


@router.post("/businesses/{brand_id}/shoutouts/config/enable", response_model=ShoutoutConfigOut)
async def enable_config(brand_id: UUID, body: ShoutoutEnableIn, context: BrandAccessContext = Depends(SHOUTOUT_MANAGER)):
    async with get_connection() as conn:
        try:
            return await config_service.set_enabled(conn, brand_id, body.enabled)
        except ValueError as error:
            raise HTTPException(409, str(error))


@router.get("/businesses/{brand_id}/shoutouts/mentions", response_model=list[ShoutoutMentionOut])
async def mentions(
    brand_id: UUID,
    status: Literal["pending", "approved", "rejected", "expired"] | None = Query(default=None),
    context: BrandAccessContext = Depends(SHOUTOUT_MANAGER),
):
    async with get_connection() as conn:
        return await config_service.list_mentions(conn, brand_id, status)


@router.post("/businesses/{brand_id}/shoutouts/mentions/{mention_id}/reject", status_code=204)
async def reject_mention(
    brand_id: UUID, mention_id: UUID, body: ShoutoutRejectIn,
    context: BrandAccessContext = Depends(SHOUTOUT_MANAGER),
):
    async with get_connection() as conn:
        try:
            await review_service.reject_mention(conn, brand_id=brand_id, mention_id=mention_id, actor_id=context.account.id)
        except review_service.ShoutoutReviewError as error:
            _review_error(error)


@router.post("/businesses/{brand_id}/shoutouts/mentions/{mention_id}/approve")
async def approve_mention(
    brand_id: UUID, mention_id: UUID, body: ShoutoutApproveIn,
    context: BrandAccessContext = Depends(SHOUTOUT_MANAGER),
):
    async with get_connection() as conn:
        try:
            return await review_service.approve_mention(
                conn, brand_id=brand_id, mention_id=mention_id, actor_id=context.account.id,
                client_request_id=body.client_request_id,
            )
        except review_service.ShoutoutReviewError as error:
            _review_error(error)


@router.get("/businesses/{brand_id}/shoutouts/runs", response_model=list[ShoutoutRunOut])
async def runs(brand_id: UUID, context: BrandAccessContext = Depends(SHOUTOUT_MANAGER)):
    async with get_connection() as conn:
        return await config_service.list_runs(conn, brand_id)
