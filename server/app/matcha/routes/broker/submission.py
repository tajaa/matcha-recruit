"""Broker submission packet + coverage-gap — `/broker/.../submission.pdf` + `.../coverage-gap`.

The outward, terms-winning layer: a carrier-ready underwriting submission PDF
from a client's WC + EPL posture, plus an AI coverage-gap read. Works for both
on-platform (tenant) clients and off-platform Broker Pro clients.
"""

import json
import logging
from typing import Optional
from uuid import UUID

from fastapi import APIRouter, Depends, File, HTTPException, Response, UploadFile
from pydantic import BaseModel

from ....database import get_connection
from ....core.feature_flags import merge_company_features
from ...dependencies import require_broker, require_broker_pro
from ...models.limit_adequacy import ContractUpdate
from ...services import (
    wc_depth, epl_readiness, external_clients as ext, submission_packet as sp,
    controls_evidence as ce, claims_readiness as cr, submission_readiness as sr,
    venue_severity as vs, exclusion_gap as eg, limit_adequacy as la,
    risk_transfer as rt,
    loss_development as ld, property_sov, property_cat,
    property_exposure as property_exp, property_recommendations as property_recs,
    property_risk as property_risk_svc, risk_index,
)
from ..ir_incidents import compute_wc_metrics
from .portfolio import _assert_broker_owns_company
from .external import _broker_id

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


class SubmissionAnnotation(BaseModel):
    label: str = ""
    note: str = ""


class SubmissionNotesBody(BaseModel):
    cover_note: str = ""
    annotations: list[SubmissionAnnotation] = []


_MAX_ANNOTATIONS = 24
_MAX_COVER = 8000
_MAX_FIELD = 2000


def _clean_notes(body: SubmissionNotesBody) -> tuple[str, list[dict]]:
    """Trim/cap broker-authored text before persisting. Drops fully-empty
    annotation rows (the editor leaves trailing blanks)."""
    cover = (body.cover_note or "").strip()[:_MAX_COVER]
    annotations: list[dict] = []
    for a in (body.annotations or [])[:_MAX_ANNOTATIONS]:
        label = (a.label or "").strip()[:_MAX_FIELD]
        note = (a.note or "").strip()[:_MAX_FIELD]
        if label or note:
            annotations.append({"label": label, "note": note})
    return cover, annotations


def _notes_row(row) -> dict:
    ann = row["annotations"] if row else None
    if isinstance(ann, str):
        ann = json.loads(ann)
    return {
        "cover_note": (row["cover_note"] if row else "") or "",
        "annotations": ann or [],
        "updated_at": row["updated_at"].isoformat() if row and row["updated_at"] else None,
    }


async def _load_notes(conn, broker_id: UUID, subject_type: str, subject_id: UUID) -> dict:
    row = await conn.fetchrow(
        "SELECT cover_note, annotations, updated_at FROM broker_submission_notes "
        "WHERE broker_id = $1 AND subject_type = $2 AND subject_id = $3",
        broker_id, subject_type, subject_id,
    )
    return _notes_row(row)


async def _save_notes(conn, broker_id: UUID, subject_type: str, subject_id: UUID,
                      cover: str, annotations: list[dict], updated_by) -> dict:
    row = await conn.fetchrow(
        """
        INSERT INTO broker_submission_notes
            (broker_id, subject_type, subject_id, cover_note, annotations, updated_by, updated_at)
        VALUES ($1, $2, $3, $4, $5::jsonb, $6, now())
        ON CONFLICT (broker_id, subject_type, subject_id) DO UPDATE
        SET cover_note = EXCLUDED.cover_note,
            annotations = EXCLUDED.annotations,
            updated_by = EXCLUDED.updated_by,
            updated_at = now()
        RETURNING cover_note, annotations, updated_at
        """,
        broker_id, subject_type, subject_id, cover, json.dumps(annotations), updated_by,
    )
    return _notes_row(row)


async def _assert_external_owned(conn, broker_id: UUID, client_id: UUID) -> None:
    owns = await conn.fetchval(
        "SELECT 1 FROM broker_external_clients WHERE id = $1 AND broker_id = $2",
        client_id, broker_id,
    )
    if not owns:
        raise HTTPException(status_code=404, detail="External client not found")


def _submission_preview(ctx: dict) -> dict:
    """Compact, read-only summary of what the submission PDF will contain — lets the
    broker eyeball the packet (headline scores + which sections carry data) before
    downloading. Mirrors the section gating in ``submission_packet._packet_html``."""
    wc = ctx.get("wc") or {}
    epl = ctx.get("epl") or {}
    readiness = ctx.get("readiness") or {}
    sections: list[str] = []
    if readiness:
        sections.append("Submission readiness")
    sections.append("Workers' Compensation")
    sections.append("EPL Readiness")
    if (ctx.get("controls") or {}).get("controls"):
        sections.append("Proof of Controls")
    if (ctx.get("venue") or {}).get("locations"):
        sections.append("Venue Exposure")
    if (ctx.get("exclusions") or {}).get("exclusions"):
        sections.append("Coverage Exclusions")
    if any((l.get("carried") or l.get("contract_required"))
           for l in ((ctx.get("limits") or {}).get("lines") or [])):
        sections.append("Limit Adequacy")
    prop = ctx.get("property") or {}
    if prop and ((prop.get("rollup") or {}).get("building_count") or prop.get("building_count")):
        sections.append("Commercial Property")
    if any(ln.get("periods") for ln in ((ctx.get("loss_development") or {}).get("lines") or [])):
        sections.append("Loss Development")
    return {
        "name": ctx.get("name"),
        "industry": ctx.get("industry"),
        "headcount": ctx.get("headcount"),
        "state": ctx.get("state"),
        "wc": {"trir": wc.get("trir"), "dart_rate": wc.get("dart_rate"), "current_emr": wc.get("current_emr")},
        "epl": {"score": epl.get("score"), "band": epl.get("band")},
        "readiness": {"score": readiness.get("score"), "band": readiness.get("band")} if readiness else None,
        "sections": sections,
    }


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
    property_ctx = None
    if sov and (sov.get("buildings")):
        exp = property_exp.portfolio_exposure(sov["buildings"])
        plan = property_recs.build_plan(sov["buildings"], sov.get("rollup"), cat=cat, exposure=exp)
        risk = property_risk_svc.portfolio_risk(sov["buildings"])
        property_ctx = {**sov, "cat": cat, "exposure": exp, "plan": plan, "risk": risk}
    # Composite index (WC + EPL + compliance [+ property]) — the same engine the
    # client's own risk portal renders. Carried in the context so Broker Pilot can
    # cite it; the packet renderers ignore keys they don't know.
    risk_idx = await _safe(risk_index.compute_risk_index(conn, company_id), None, "risk_index")
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
        "risk_index": risk_idx,
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
        broker_id = await _broker_id(conn, current_user.id)
        ctx["broker_notes"] = await _load_notes(conn, broker_id, "company", company_id)
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
        broker_id = await _broker_id(conn, current_user.id)
        ctx["broker_notes"] = await _load_notes(conn, broker_id, "external", client_id)
    pdf = await sp.render_submission_pdf(ctx)
    return _pdf_response(ctx, pdf)


@router.post("/external-clients/{client_id}/coverage-gap")
async def external_coverage_gap(client_id: UUID, body: Optional[CoverageGapBody] = None,
                                current_user=Depends(require_broker_pro)):
    async with get_connection() as conn:
        ctx = await _external_context(conn, current_user.id, client_id)
    return await sp.generate_coverage_gap(context=ctx, current_coverage=body.current_coverage if body else None)


# --- broker commentary notes + preview (see & edit before download) ---------
# A compact preview (headline scores + sections) and a persisted "Broker
# Commentary" (cover memo + labeled annotations) that leads the submission PDF.

@router.get("/clients/{company_id}/submission")
async def tenant_submission_preview(company_id: UUID, current_user=Depends(require_broker)):
    async with get_connection() as conn:
        ctx = await _tenant_context(conn, current_user.id, company_id)
    return _submission_preview(ctx)


@router.get("/clients/{company_id}/submission-notes")
async def tenant_submission_notes(company_id: UUID, current_user=Depends(require_broker)):
    async with get_connection() as conn:
        await _assert_broker_owns_company(conn, current_user.id, company_id)
        broker_id = await _broker_id(conn, current_user.id)
        return await _load_notes(conn, broker_id, "company", company_id)


@router.put("/clients/{company_id}/submission-notes")
async def save_tenant_submission_notes(company_id: UUID, body: SubmissionNotesBody,
                                       current_user=Depends(require_broker)):
    cover, annotations = _clean_notes(body)
    async with get_connection() as conn:
        await _assert_broker_owns_company(conn, current_user.id, company_id)
        broker_id = await _broker_id(conn, current_user.id)
        return await _save_notes(conn, broker_id, "company", company_id, cover, annotations, current_user.id)


@router.get("/external-clients/{client_id}/submission")
async def external_submission_preview(client_id: UUID, current_user=Depends(require_broker_pro)):
    async with get_connection() as conn:
        ctx = await _external_context(conn, current_user.id, client_id)
    return _submission_preview(ctx)


@router.get("/external-clients/{client_id}/submission-notes")
async def external_submission_notes(client_id: UUID, current_user=Depends(require_broker_pro)):
    async with get_connection() as conn:
        broker_id = await _broker_id(conn, current_user.id)
        await _assert_external_owned(conn, broker_id, client_id)
        return await _load_notes(conn, broker_id, "external", client_id)


@router.put("/external-clients/{client_id}/submission-notes")
async def save_external_submission_notes(client_id: UUID, body: SubmissionNotesBody,
                                         current_user=Depends(require_broker_pro)):
    cover, annotations = _clean_notes(body)
    async with get_connection() as conn:
        broker_id = await _broker_id(conn, current_user.id)
        await _assert_external_owned(conn, broker_id, client_id)
        return await _save_notes(conn, broker_id, "external", client_id, cover, annotations, current_user.id)


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


# --- broker-driven contract review ------------------------------------------
#
# The real-world flow is "send the contract to your broker before you sign it",
# so the broker — not only the tenant — can upload, correct, confirm, and package
# a client's contracts. Writes land in the client's own `company_contracts`, so
# the tenant sees the same records on its Limit Adequacy page. Handler bodies live
# in `risk_transfer`, shared verbatim with the tenant routes.

async def _assert_client_has_limit_adequacy(conn, company_id: UUID) -> None:
    """Broker WRITES need the client's own feature flag.

    A broker owning the client is enough to *read* its posture (the convention
    across every `/broker/clients/{id}/…` surface), but writing a contract into a
    company whose Limit Adequacy page doesn't exist would strand the row where the
    client can never see, correct, or confirm it. Reads stay ungated.
    """
    row = await conn.fetchrow(
        "SELECT enabled_features, signup_source FROM companies WHERE id = $1", company_id
    )
    features = merge_company_features(row["enabled_features"] if row else None,
                                      row["signup_source"] if row else None)
    if not features.get("limit_adequacy"):
        raise HTTPException(status_code=403, detail="Client does not have Limit Adequacy enabled")


@router.get("/clients/{company_id}/contracts")
async def tenant_contracts(company_id: UUID, current_user=Depends(require_broker)):
    async with get_connection() as conn:
        await _assert_broker_owns_company(conn, current_user.id, company_id)
        rows = await conn.fetch(
            f"SELECT {rt._CONTRACT_COLS} FROM company_contracts "
            "WHERE company_id = $1 ORDER BY created_at DESC",
            company_id,
        )
    return {"contracts": [la._contract_row(r) for r in rows]}


@router.post("/clients/{company_id}/contracts/upload")
async def tenant_contract_upload(company_id: UUID, file: UploadFile = File(...),
                                 current_user=Depends(require_broker)):
    rt.validate_pdf_upload(file)
    data = await file.read()
    rt.validate_pdf_bytes(data)
    async with get_connection() as conn:
        await _assert_broker_owns_company(conn, current_user.id, company_id)
        await _assert_client_has_limit_adequacy(conn, company_id)
        return await rt.store_uploaded_contract(conn, company_id, current_user.id, data, file.filename)


@router.put("/clients/{company_id}/contracts/{contract_id}")
async def tenant_contract_update(company_id: UUID, contract_id: UUID, body: ContractUpdate,
                                 current_user=Depends(require_broker)):
    async with get_connection() as conn:
        await _assert_broker_owns_company(conn, current_user.id, company_id)
        await _assert_client_has_limit_adequacy(conn, company_id)
        row = await rt.update_contract(conn, company_id, contract_id, body)
    if row is None:
        raise HTTPException(status_code=404, detail="Contract not found")
    return row


@router.post("/clients/{company_id}/contracts/{contract_id}/confirm")
async def tenant_contract_confirm(company_id: UUID, contract_id: UUID,
                                  current_user=Depends(require_broker)):
    async with get_connection() as conn:
        await _assert_broker_owns_company(conn, current_user.id, company_id)
        await _assert_client_has_limit_adequacy(conn, company_id)
        row = await rt.confirm_contract(conn, company_id, contract_id, current_user.id)
    if row is None:
        raise HTTPException(status_code=404, detail="Contract not found")
    return row


@router.get("/clients/{company_id}/contracts/{contract_id}/review")
async def tenant_contract_review(company_id: UUID, contract_id: UUID,
                                 current_user=Depends(require_broker)):
    async with get_connection() as conn:
        await _assert_broker_owns_company(conn, current_user.id, company_id)
        review = await rt.build_contract_review(conn, company_id, contract_id)
    if review is None:
        raise HTTPException(status_code=404, detail="Contract not found")
    return review


@router.get("/clients/{company_id}/contracts/{contract_id}/review.pdf")
async def tenant_contract_review_pdf(company_id: UUID, contract_id: UUID,
                                     current_user=Depends(require_broker)):
    async with get_connection() as conn:
        await _assert_broker_owns_company(conn, current_user.id, company_id)
        review = await rt.build_contract_review(conn, company_id, contract_id)
    if review is None:
        raise HTTPException(status_code=404, detail="Contract not found")
    pdf = await rt.render_contract_review_pdf(review)
    return _named_pdf(str((review.get("contract") or {}).get("name") or "contract"), "contract-review", pdf)


@router.get("/clients/{company_id}/contracts/{contract_id}/file")
async def tenant_contract_file(company_id: UUID, contract_id: UUID,
                               current_user=Depends(require_broker)):
    async with get_connection() as conn:
        await _assert_broker_owns_company(conn, current_user.id, company_id)
        url = await rt.contract_source_url(conn, company_id, contract_id)
    if not url:
        raise HTTPException(status_code=404, detail="No source document on file")
    return {"url": url}
