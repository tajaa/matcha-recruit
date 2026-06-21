"""Off-platform broker clients — Broker Pro (`/broker/external-clients/*`).

Clients a broker manages who aren't Matcha tenants. Broker keys in a WC loss-run
summary + an EPL questionnaire; the shared WC + EPL scoring engines run on it.
Mounted under ``require_broker_pro`` so the whole surface is Pro-gated.
"""

import logging
from typing import Optional
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, File, UploadFile
from pydantic import BaseModel, Field

from ...database import get_connection
from ..dependencies import require_broker_pro
from ..services import external_clients as ext
from ..services import epl_readiness
from ..services import loss_run_parser

logger = logging.getLogger(__name__)
router = APIRouter()

_EPL_KEYS = {f["key"] for f in epl_readiness.FACTORS}


class ExternalClientBody(BaseModel):
    name: str = Field(..., min_length=1, max_length=255)
    industry: Optional[str] = None
    headcount: Optional[int] = Field(default=None, ge=0)
    primary_state: Optional[str] = None
    note: Optional[str] = None


class ExternalWcBody(BaseModel):
    period_label: Optional[str] = None
    recordable_cases: int = Field(default=0, ge=0)
    dart_cases: int = Field(default=0, ge=0)
    lost_days: int = Field(default=0, ge=0)
    restricted_days: int = Field(default=0, ge=0)
    ct_cases: int = Field(default=0, ge=0)
    acute_cases: int = Field(default=0, ge=0)
    post_termination_cases: int = Field(default=0, ge=0)
    lost_time_open: int = Field(default=0, ge=0)
    lost_time_resolved: int = Field(default=0, ge=0)
    avg_days_to_rtw: Optional[float] = Field(default=None, ge=0)
    current_emr: Optional[float] = Field(default=None, gt=0, le=10)
    carrier: Optional[str] = None
    annual_premium: Optional[float] = Field(default=None, ge=0)


class ExternalEplBody(BaseModel):
    status: str = Field(..., pattern="^(in_place|partial|gap|unknown)$")
    note: Optional[str] = None


async def _broker_id(conn, user_id) -> UUID:
    bid = await conn.fetchval(
        "SELECT broker_id FROM broker_members WHERE user_id = $1 AND is_active = true "
        "ORDER BY created_at ASC LIMIT 1",
        user_id,
    )
    if not bid:
        raise HTTPException(status_code=403, detail="No active broker membership")
    return bid


@router.get("/external-clients")
async def list_external_clients(current_user=Depends(require_broker_pro)):
    async with get_connection() as conn:
        broker_id = await _broker_id(conn, current_user.id)
        clients = await ext.list_with_scores(conn, broker_id)
    return {"clients": clients}


@router.post("/external-clients")
async def create_external_client(body: ExternalClientBody, current_user=Depends(require_broker_pro)):
    async with get_connection() as conn:
        broker_id = await _broker_id(conn, current_user.id)
        client = await ext.create_client(
            conn, broker_id, current_user.id,
            name=body.name.strip(), industry=body.industry, headcount=body.headcount,
            primary_state=body.primary_state, note=body.note,
        )
    return client


async def _detail_or_404(conn, broker_id, client_id) -> dict:
    detail = await ext.client_detail(conn, broker_id, client_id)
    if not detail:
        raise HTTPException(status_code=404, detail="External client not found")
    return detail


@router.get("/external-clients/{client_id}")
async def get_external_client(client_id: UUID, current_user=Depends(require_broker_pro)):
    async with get_connection() as conn:
        broker_id = await _broker_id(conn, current_user.id)
        return await _detail_or_404(conn, broker_id, client_id)


@router.put("/external-clients/{client_id}")
async def update_external_client(client_id: UUID, body: ExternalClientBody,
                                 current_user=Depends(require_broker_pro)):
    async with get_connection() as conn:
        broker_id = await _broker_id(conn, current_user.id)
        client = await ext.update_client(
            conn, broker_id, client_id,
            name=body.name.strip(), industry=body.industry, headcount=body.headcount,
            primary_state=body.primary_state, note=body.note,
        )
        if not client:
            raise HTTPException(status_code=404, detail="External client not found")
    return client


@router.delete("/external-clients/{client_id}")
async def delete_external_client(client_id: UUID, current_user=Depends(require_broker_pro)):
    async with get_connection() as conn:
        broker_id = await _broker_id(conn, current_user.id)
        ok = await ext.archive_client(conn, broker_id, client_id)
        if not ok:
            raise HTTPException(status_code=404, detail="External client not found")
    return {"status": "archived"}


@router.put("/external-clients/{client_id}/wc")
async def upsert_external_wc(client_id: UUID, body: ExternalWcBody,
                            current_user=Depends(require_broker_pro)):
    async with get_connection() as conn:
        broker_id = await _broker_id(conn, current_user.id)
        # ownership check
        if not await ext.get_client(conn, broker_id, client_id):
            raise HTTPException(status_code=404, detail="External client not found")
        await ext.upsert_wc_snapshot(conn, client_id, current_user.id, body.model_dump())
        return await _detail_or_404(conn, broker_id, client_id)


@router.post("/external-clients/{client_id}/loss-run")
async def parse_external_loss_run(client_id: UUID, file: UploadFile = File(...),
                                  current_user=Depends(require_broker_pro)):
    """Parse an uploaded carrier loss-run PDF → draft WC fields for the broker to
    review and save. Does NOT auto-commit — returns the extracted draft only."""
    async with get_connection() as conn:
        broker_id = await _broker_id(conn, current_user.id)
        if not await ext.get_client(conn, broker_id, client_id):
            raise HTTPException(status_code=404, detail="External client not found")
    is_pdf = (file.content_type == "application/pdf") or (file.filename or "").lower().endswith(".pdf")
    if not is_pdf:
        raise HTTPException(status_code=400, detail="Upload a PDF loss run")
    data = await file.read()
    if not data:
        raise HTTPException(status_code=400, detail="Empty file")
    if len(data) > 15_000_000:
        raise HTTPException(status_code=413, detail="PDF too large (max 15 MB)")
    return await loss_run_parser.parse_loss_run(data)


@router.put("/external-clients/{client_id}/epl/{item_key}")
async def upsert_external_epl(client_id: UUID, item_key: str, body: ExternalEplBody,
                             current_user=Depends(require_broker_pro)):
    if item_key not in _EPL_KEYS:
        raise HTTPException(status_code=400, detail="Unknown EPL factor")
    async with get_connection() as conn:
        broker_id = await _broker_id(conn, current_user.id)
        if not await ext.get_client(conn, broker_id, client_id):
            raise HTTPException(status_code=404, detail="External client not found")
        await ext.upsert_epl_attestation(conn, client_id, item_key, body.status, body.note, current_user.id)
        return await _detail_or_404(conn, broker_id, client_id)
