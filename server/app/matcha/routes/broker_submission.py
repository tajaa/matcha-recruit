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
from ..services import (
    wc_depth, epl_readiness, external_clients as ext, submission_packet as sp,
    controls_evidence as ce, claims_readiness as cr, submission_readiness as sr,
    venue_severity as vs, exclusion_gap as eg, limit_adequacy as la,
    loss_development as ld, property_sov, property_cat,
)
from .ir_incidents import compute_wc_metrics
from .broker_portfolio import _assert_broker_owns_company
from .broker_external import _broker_id

logger = logging.getLogger(__name__)
router = APIRouter()


async def _safe(coro, default, label: str):
    """Best-effort optional context builder. A single feature failing (e.g. a
    missing column from a lagging migration, or a transient AI/DB error) must not
    sink the whole submission packet — it degrades to ``default``, which the PDF
    section renderers already treat as "omit this section"."""
    try:
        return await coro
    except Exception as exc:  # noqa: BLE001 - intentionally broad; isolates one section
        logger.warning("submission: %s builder failed: %s", label, exc)
        return default


class CoverageGapBody(BaseModel):
    current_coverage: Optional[dict] = None


async def _tenant_context(conn, user_id, company_id: UUID) -> dict:
    """Common submission context for an on-platform (tenant) client."""
    meta = await _assert_broker_owns_company(conn, user_id, company_id)
    broker_id = await _broker_id(conn, user_id)
    m = await compute_wc_metrics(conn, company_id)
    states = await wc_depth.resolve_company_states(conn, company_id)
    rates = await wc_depth.get_state_rates(conn, states)
    mods = await wc_depth.latest_mods(conn, [company_id])
    epl = await epl_readiness.compute_epl_readiness(conn, company_id)
    # Optional sections — each isolated so one feature can't 500 the whole packet.
    controls = await _safe(ce.build_register(conn, company_id, epl=epl), {}, "controls")
    readiness = await _safe(
        sr.compute_readiness(conn, company_id, wc=m, epl=epl, controls=controls), None, "readiness")
    venue = await _safe(vs.company_venue_exposure(conn, company_id), {}, "venue")
    exclusions = await _safe(eg.company_exclusions(conn, company_id), {}, "exclusions")
    limits = await _safe(la.build_review(conn, company_id, venue=venue), {}, "limits")
    loss_dev = await _safe(
        ld.build_development(conn, broker_id, "company", company_id, subject_name=meta["name"]),
        {}, "loss_development")
    sov = await _safe(property_sov.build_sov(conn, company_id), {}, "property_sov")
    cat = await _safe(property_cat.company_cat_exposure(conn, company_id), {}, "property_cat")
    property_ctx = {**sov, "cat": cat} if sov else None
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
        "controls": controls,
        "readiness": readiness,
        "venue": venue,
        "exclusions": exclusions,
        "limits": limits,
        "property": property_ctx,
        "loss_development": loss_dev,
    }


async def _external_context(conn, user_id, client_id: UUID) -> dict:
    """Common submission context for an off-platform (Broker Pro) client."""
    broker_id = await _broker_id(conn, user_id)
    detail = await ext.client_detail(conn, broker_id, client_id)
    if not detail:
        raise HTTPException(status_code=404, detail="External client not found")
    c, wc, epl = detail["client"], detail["wc"], detail["epl"]
    venue = await _safe(vs.state_venue(conn, c["primary_state"]), {}, "venue")
    try:
        exclusions = eg.external_exclusions(c["industry"], c["primary_state"])
    except Exception as exc:  # noqa: BLE001 - isolates one section
        logger.warning("submission: external exclusions builder failed: %s", exc)
        exclusions = {}
    loss_dev = await _safe(
        ld.build_development(conn, broker_id, "external", client_id, subject_name=c["name"]),
        {}, "loss_development")
    return {
        "name": c["name"], "industry": c["industry"], "headcount": c["headcount"],
        "state": c["primary_state"],
        "wc": wc,
        "epl": {"score": epl["score"], "band": epl["band"], "factors": epl["factors"]},
        "venue": venue,
        "exclusions": exclusions,
        "property": detail.get("property"),
        "loss_development": loss_dev,
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


# --- controls-evidence (proof-of-controls) for an on-platform client --------

def _named_pdf(name: str, prefix: str, pdf: bytes) -> Response:
    safe = (name or "client").replace("/", "-").replace('"', "")
    return Response(
        content=pdf, media_type="application/pdf",
        headers={"Content-Disposition": f'attachment; filename="{prefix}-{safe}.pdf"'},
    )


@router.get("/clients/{company_id}/controls-evidence")
async def tenant_controls_register(company_id: UUID, current_user=Depends(require_broker)):
    async with get_connection() as conn:
        await _assert_broker_owns_company(conn, current_user.id, company_id)
        return await ce.build_register(conn, company_id)


@router.get("/clients/{company_id}/controls.pdf")
async def tenant_controls_pdf(company_id: UUID, current_user=Depends(require_broker)):
    async with get_connection() as conn:
        meta = await _assert_broker_owns_company(conn, current_user.id, company_id)
        register = await ce.build_register(conn, company_id)
    pdf = await ce.render_controls_packet(meta["name"], register)
    return _named_pdf(meta["name"], "proof-of-controls", pdf)


# --- claims-readiness / defense packets for an on-platform client -----------

@router.get("/clients/{company_id}/defense/incidents")
async def tenant_defense_incidents(company_id: UUID, current_user=Depends(require_broker)):
    async with get_connection() as conn:
        await _assert_broker_owns_company(conn, current_user.id, company_id)
        rows = await conn.fetch(
            """
            SELECT id, incident_number, title, incident_type, severity, status, occurred_at
            FROM ir_incidents WHERE company_id = $1
            ORDER BY occurred_at DESC NULLS LAST LIMIT 200
            """,
            company_id,
        )
    return {"incidents": [dict(r) for r in rows]}


@router.get("/clients/{company_id}/defense/incidents/{incident_id}.pdf")
async def tenant_defense_incident_pdf(company_id: UUID, incident_id: UUID,
                                      current_user=Depends(require_broker)):
    async with get_connection() as conn:
        meta = await _assert_broker_owns_company(conn, current_user.id, company_id)
        data = await cr.build_incident_packet(conn, incident_id, company_id)
    if data is None:
        raise HTTPException(status_code=404, detail="Incident not found")
    pdf = await cr.render_incident_packet_pdf(data)
    num = str(data["incident"].get("incident_number") or incident_id)
    return _named_pdf(num, "claims-readiness", pdf)


@router.get("/clients/{company_id}/defense/er-cases")
async def tenant_defense_er_cases(company_id: UUID, current_user=Depends(require_broker)):
    async with get_connection() as conn:
        await _assert_broker_owns_company(conn, current_user.id, company_id)
        rows = await conn.fetch(
            """
            SELECT id, case_number, title, status, category, outcome, created_at
            FROM er_cases WHERE company_id = $1
            ORDER BY created_at DESC NULLS LAST LIMIT 200
            """,
            company_id,
        )
    return {"cases": [dict(r) for r in rows]}


@router.get("/clients/{company_id}/defense/er-cases/{case_id}.pdf")
async def tenant_defense_er_case_pdf(company_id: UUID, case_id: UUID,
                                     current_user=Depends(require_broker)):
    async with get_connection() as conn:
        meta = await _assert_broker_owns_company(conn, current_user.id, company_id)
        data = await cr.build_er_packet(conn, case_id, company_id)
    if data is None:
        raise HTTPException(status_code=404, detail="ER case not found")
    pdf = await cr.render_er_packet_pdf(data)
    num = str(data["case"].get("case_number") or case_id)
    return _named_pdf(num, "claims-readiness", pdf)


# --- limit-adequacy / contract review for an on-platform client -------------

@router.get("/clients/{company_id}/limit-adequacy")
async def tenant_limit_adequacy(company_id: UUID, current_user=Depends(require_broker)):
    async with get_connection() as conn:
        await _assert_broker_owns_company(conn, current_user.id, company_id)
        return await la.build_review(conn, company_id)


@router.get("/clients/{company_id}/limits.pdf")
async def tenant_limits_pdf(company_id: UUID, current_user=Depends(require_broker)):
    async with get_connection() as conn:
        meta = await _assert_broker_owns_company(conn, current_user.id, company_id)
        review = await la.build_review(conn, company_id)
    pdf = await la.render_review_pdf(meta["name"], review)
    return _named_pdf(meta["name"], "limit-adequacy", pdf)
