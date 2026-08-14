"""Admin Matcha Ops entitlement and health management."""

from __future__ import annotations

from typing import Optional
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, status

from app.core.dependencies import require_admin
from app.core.models.admin_ops import MatchaOpsFeaturePatch
from app.core.services.matcha_ops_admin import (
    get_ops_company_detail,
    get_ops_overview,
    list_ops_companies,
    update_ops_company_features,
)
from app.database import get_connection

router = APIRouter(prefix="/matcha-ops", dependencies=[Depends(require_admin)])


@router.get("/overview")
async def ops_overview():
    async with get_connection() as conn:
        return (await get_ops_overview(conn)).model_dump(mode="json")


@router.get("/companies")
async def ops_companies(
    query: Optional[str] = Query(default=None, max_length=120),
    enabled: Optional[bool] = None,
    needs_attention: Optional[bool] = None,
    limit: int = Query(default=100, ge=1, le=500),
    offset: int = Query(default=0, ge=0),
):
    async with get_connection() as conn:
        rows, total = await list_ops_companies(
            conn,
            query=query,
            enabled=enabled,
            needs_attention=needs_attention,
            limit=limit,
            offset=offset,
        )
    return {"companies": [row.model_dump(mode="json") for row in rows], "total": total}


@router.get("/companies/{company_id}")
async def ops_company_detail(company_id: UUID):
    async with get_connection() as conn:
        detail = await get_ops_company_detail(conn, company_id=company_id)
    if detail is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Company not found")
    return detail.model_dump(mode="json")


@router.patch("/companies/{company_id}/features")
async def patch_ops_company_features(
    company_id: UUID,
    body: MatchaOpsFeaturePatch,
    current_user=Depends(require_admin),
):
    async with get_connection() as conn:
        try:
            detail = await update_ops_company_features(
                conn,
                company_id=company_id,
                updates=body,
                actor_user_id=current_user.id,
            )
        except LookupError:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Company not found")
        except ValueError as exc:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc))
    return detail.model_dump(mode="json")
