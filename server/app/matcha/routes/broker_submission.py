"""Broker submission packet + coverage-gap — `/broker/.../submission.pdf` + `.../coverage-gap`.

The outward, terms-winning layer: a carrier-ready underwriting submission PDF
from a client's WC + EPL posture, plus an AI coverage-gap read. Works for both
on-platform (tenant) clients and off-platform Broker Pro clients.
"""

import logging
from typing import Optional
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Response
from pydantic import BaseModel

from ...database import get_connection
from ..dependencies import require_broker, require_broker_pro
from ..services import wc_depth, epl_readiness, external_clients as ext, submission_packet as sp
from .ir_incidents import compute_wc_metrics
from .broker_portfolio import _assert_broker_owns_company
from .broker_external import _broker_id

logger = logging.getLogger(__name__)
router = APIRouter()


class CoverageGapBody(BaseModel):
    current_coverage: Optional[dict] = None


async def _tenant_context(conn, user_id, company_id: UUID) -> dict:
    """Common submission context for an on-platform (tenant) client."""
    meta = await _assert_broker_owns_company(conn, user_id, company_id)
    m = await compute_wc_metrics(conn, company_id)
    states = await wc_depth.resolve_company_states(conn, company_id)
    rates = await wc_depth.get_state_rates(conn, states)
    mods = await wc_depth.latest_mods(conn, [company_id])
    epl = await epl_readiness.compute_epl_readiness(conn, company_id)
    primary = states[0] if states else None
    latest = mods.get(str(company_id)) or {}
    return {
        "name": meta["name"],
        "industry": m.get("industry"),
        "headcount": m.get("headcount"),
        "state": primary,
        "wc": {
            "trir": m.get("trir"), "dart_rate": m.get("dart_rate"),
            "severity_band": m.get("severity_band"), "benchmark": m.get("benchmark"),
            "recordable_cases": m.get("recordable_cases"), "dart_cases": m.get("dart_cases"),
            "lost_days": m.get("lost_days"), "claim_breakdown": m.get("claim_breakdown"),
            "post_termination_cases": m.get("post_termination_cases"), "rtw": m.get("rtw"),
            "current_emr": latest.get("experience_mod"),
            "state_rate": rates.get(primary) if primary else None,
        },
        "epl": {"score": epl["score"], "band": epl["band"], "factors": epl["factors"]},
    }


async def _external_context(conn, user_id, client_id: UUID) -> dict:
    """Common submission context for an off-platform (Broker Pro) client."""
    broker_id = await _broker_id(conn, user_id)
    detail = await ext.client_detail(conn, broker_id, client_id)
    if not detail:
        raise HTTPException(status_code=404, detail="External client not found")
    c, wc, epl = detail["client"], detail["wc"], detail["epl"]
    return {
        "name": c["name"], "industry": c["industry"], "headcount": c["headcount"],
        "state": c["primary_state"],
        "wc": wc,
        "epl": {"score": epl["score"], "band": epl["band"], "factors": epl["factors"]},
    }


def _pdf_response(context: dict, pdf: bytes) -> Response:
    safe = (context.get("name") or "client").replace("/", "-").replace('"', "")
    return Response(
        content=pdf, media_type="application/pdf",
        headers={"Content-Disposition": f'attachment; filename="submission-{safe}.pdf"'},
    )


# --- tenant (on-platform) ---------------------------------------------------

@router.get("/clients/{company_id}/submission.pdf")
async def tenant_submission_pdf(company_id: UUID, current_user=Depends(require_broker)):
    async with get_connection() as conn:
        ctx = await _tenant_context(conn, current_user.id, company_id)
    pdf = await sp.render_submission_pdf(ctx)
    return _pdf_response(ctx, pdf)


@router.post("/clients/{company_id}/coverage-gap")
async def tenant_coverage_gap(company_id: UUID, body: Optional[CoverageGapBody] = None,
                              current_user=Depends(require_broker)):
    async with get_connection() as conn:
        ctx = await _tenant_context(conn, current_user.id, company_id)
    return await sp.generate_coverage_gap(context=ctx, current_coverage=body.current_coverage if body else None)


# --- external (off-platform, Broker Pro) ------------------------------------

@router.get("/external-clients/{client_id}/submission.pdf")
async def external_submission_pdf(client_id: UUID, current_user=Depends(require_broker_pro)):
    async with get_connection() as conn:
        ctx = await _external_context(conn, current_user.id, client_id)
    pdf = await sp.render_submission_pdf(ctx)
    return _pdf_response(ctx, pdf)


@router.post("/external-clients/{client_id}/coverage-gap")
async def external_coverage_gap(client_id: UUID, body: Optional[CoverageGapBody] = None,
                                current_user=Depends(require_broker_pro)):
    async with get_connection() as conn:
        ctx = await _external_context(conn, current_user.id, client_id)
    return await sp.generate_coverage_gap(context=ctx, current_coverage=body.current_coverage if body else None)
