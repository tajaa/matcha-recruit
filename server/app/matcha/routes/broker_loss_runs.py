"""Loss-run triangulation routes (`/broker/.../loss-runs|loss-development`).

Gap-analysis #5/#23. A broker uploads a client's historical carrier loss runs
(each valued as of a different date); the chain-ladder engine lines up the same
policy years across valuations → development factors → projected ultimate losses
+ adverse development. Works for on-platform (tenant) clients and off-platform
Broker Pro clients. The PDF/section ride the submission packet.
"""

import logging
from uuid import UUID

from fastapi import APIRouter, Depends, File, HTTPException, Response, UploadFile

from ...database import get_connection
from ..dependencies import require_broker, require_broker_pro
from ..services import loss_development as ld, loss_run_parser, external_clients as ext
from ..models.loss_development import LossRunValuationCommit, LossPremiumUpsert
from .broker_portfolio import _assert_broker_owns_company
from .broker_external import _broker_id

logger = logging.getLogger(__name__)
router = APIRouter()


async def _read_pdf(file: UploadFile) -> bytes:
    is_pdf = (file.content_type == "application/pdf") or (file.filename or "").lower().endswith(".pdf")
    if not is_pdf:
        raise HTTPException(status_code=400, detail="Upload a PDF loss run")
    data = await file.read()
    if not data:
        raise HTTPException(status_code=400, detail="Empty file")
    if len(data) > 15_000_000:
        raise HTTPException(status_code=413, detail="PDF too large (max 15 MB)")
    return data


async def _commit_valuation(conn, broker_id, kind: str, sid: UUID, body: LossRunValuationCommit, user_id):
    for p in body.periods:
        await conn.execute(
            """
            INSERT INTO wc_loss_runs
                (broker_id, subject_kind, subject_id, line, policy_period_label, policy_period_start,
                 valuation_date, claim_count, open_count, paid, reserved, source, created_by)
            VALUES ($1,$2,$3,$4,$5,$6,$7,$8,$9,$10,$11,$12,$13)
            ON CONFLICT ON CONSTRAINT uq_wc_loss_runs DO UPDATE SET
                policy_period_start = EXCLUDED.policy_period_start,
                claim_count = EXCLUDED.claim_count, open_count = EXCLUDED.open_count,
                paid = EXCLUDED.paid, reserved = EXCLUDED.reserved,
                source = EXCLUDED.source, created_by = EXCLUDED.created_by
            """,
            broker_id, kind, sid, body.line, p.policy_period_label, p.policy_period_start,
            body.valuation_date, p.claim_count, p.open_count, p.paid, p.reserved, body.source, user_id,
        )


async def _upsert_premium(conn, broker_id, kind: str, sid: UUID, body: LossPremiumUpsert, user_id):
    await conn.execute(
        """
        INSERT INTO broker_loss_premiums
            (broker_id, subject_kind, subject_id, line, policy_period_label, paid_premium, created_by, updated_at)
        VALUES ($1,$2,$3,$4,$5,$6,$7,NOW())
        ON CONFLICT ON CONSTRAINT uq_broker_loss_premiums DO UPDATE SET
            paid_premium = EXCLUDED.paid_premium, created_by = EXCLUDED.created_by, updated_at = NOW()
        """,
        broker_id, kind, sid, body.line, body.policy_period_label, body.paid_premium, user_id,
    )


def _pdf(name: str, pdf: bytes) -> Response:
    safe = (name or "client").replace("/", "-").replace('"', "")
    return Response(content=pdf, media_type="application/pdf",
                    headers={"Content-Disposition": f'attachment; filename="loss-development-{safe}.pdf"'})


# --- tenant (on-platform) ---------------------------------------------------

@router.get("/clients/{company_id}/loss-development")
async def tenant_loss_development(company_id: UUID, current_user=Depends(require_broker)):
    async with get_connection() as conn:
        meta = await _assert_broker_owns_company(conn, current_user.id, company_id)
        broker_id = await _broker_id(conn, current_user.id)
        return await ld.build_development(conn, broker_id, "company", company_id, subject_name=meta["name"])


@router.post("/clients/{company_id}/loss-runs/parse")
async def tenant_parse_loss_run(company_id: UUID, file: UploadFile = File(...),
                                current_user=Depends(require_broker)):
    async with get_connection() as conn:
        await _assert_broker_owns_company(conn, current_user.id, company_id)
    return await loss_run_parser.parse_loss_run_development(await _read_pdf(file))


@router.post("/clients/{company_id}/loss-runs")
async def tenant_commit_loss_run(company_id: UUID, body: LossRunValuationCommit,
                                 current_user=Depends(require_broker)):
    async with get_connection() as conn:
        meta = await _assert_broker_owns_company(conn, current_user.id, company_id)
        broker_id = await _broker_id(conn, current_user.id)
        await _commit_valuation(conn, broker_id, "company", company_id, body, current_user.id)
        return await ld.build_development(conn, broker_id, "company", company_id, subject_name=meta["name"])


@router.delete("/clients/{company_id}/loss-runs/{snapshot_id}")
async def tenant_delete_loss_run(company_id: UUID, snapshot_id: UUID,
                                 current_user=Depends(require_broker)):
    async with get_connection() as conn:
        meta = await _assert_broker_owns_company(conn, current_user.id, company_id)
        broker_id = await _broker_id(conn, current_user.id)
        await conn.execute(
            "DELETE FROM wc_loss_runs WHERE id = $1 AND broker_id = $2 AND subject_kind = 'company' AND subject_id = $3",
            snapshot_id, broker_id, company_id,
        )
        return await ld.build_development(conn, broker_id, "company", company_id, subject_name=meta["name"])


@router.get("/clients/{company_id}/loss-development.pdf")
async def tenant_loss_development_pdf(company_id: UUID, current_user=Depends(require_broker)):
    async with get_connection() as conn:
        meta = await _assert_broker_owns_company(conn, current_user.id, company_id)
        broker_id = await _broker_id(conn, current_user.id)
        tri = await ld.build_development(conn, broker_id, "company", company_id, subject_name=meta["name"])
    pdf = await ld.render_triangle_pdf(meta["name"], tri)
    return _pdf(meta["name"], pdf)


@router.get("/clients/{company_id}/loss-ratio")
async def tenant_loss_ratio(company_id: UUID, current_user=Depends(require_broker)):
    async with get_connection() as conn:
        meta = await _assert_broker_owns_company(conn, current_user.id, company_id)
        broker_id = await _broker_id(conn, current_user.id)
        return await ld.compute_loss_ratio(conn, broker_id, "company", company_id, subject_name=meta["name"])


@router.put("/clients/{company_id}/loss-ratio/premium")
async def tenant_set_loss_premium(company_id: UUID, body: LossPremiumUpsert,
                                  current_user=Depends(require_broker)):
    async with get_connection() as conn:
        meta = await _assert_broker_owns_company(conn, current_user.id, company_id)
        broker_id = await _broker_id(conn, current_user.id)
        await _upsert_premium(conn, broker_id, "company", company_id, body, current_user.id)
        return await ld.compute_loss_ratio(conn, broker_id, "company", company_id, subject_name=meta["name"])


# --- external (off-platform, Broker Pro) ------------------------------------

async def _external_ctx(conn, user_id, client_id: UUID):
    broker_id = await _broker_id(conn, user_id)
    client = await ext.get_client(conn, broker_id, client_id)
    if not client:
        raise HTTPException(status_code=404, detail="External client not found")
    return broker_id, client["name"]


@router.get("/external-clients/{client_id}/loss-development")
async def external_loss_development(client_id: UUID, current_user=Depends(require_broker_pro)):
    async with get_connection() as conn:
        broker_id, name = await _external_ctx(conn, current_user.id, client_id)
        return await ld.build_development(conn, broker_id, "external", client_id, subject_name=name)


@router.post("/external-clients/{client_id}/loss-runs/parse")
async def external_parse_loss_run(client_id: UUID, file: UploadFile = File(...),
                                  current_user=Depends(require_broker_pro)):
    async with get_connection() as conn:
        await _external_ctx(conn, current_user.id, client_id)
    return await loss_run_parser.parse_loss_run_development(await _read_pdf(file))


@router.post("/external-clients/{client_id}/loss-runs")
async def external_commit_loss_run(client_id: UUID, body: LossRunValuationCommit,
                                   current_user=Depends(require_broker_pro)):
    async with get_connection() as conn:
        broker_id, name = await _external_ctx(conn, current_user.id, client_id)
        await _commit_valuation(conn, broker_id, "external", client_id, body, current_user.id)
        return await ld.build_development(conn, broker_id, "external", client_id, subject_name=name)


@router.delete("/external-clients/{client_id}/loss-runs/{snapshot_id}")
async def external_delete_loss_run(client_id: UUID, snapshot_id: UUID,
                                   current_user=Depends(require_broker_pro)):
    async with get_connection() as conn:
        broker_id, name = await _external_ctx(conn, current_user.id, client_id)
        await conn.execute(
            "DELETE FROM wc_loss_runs WHERE id = $1 AND broker_id = $2 AND subject_kind = 'external' AND subject_id = $3",
            snapshot_id, broker_id, client_id,
        )
        return await ld.build_development(conn, broker_id, "external", client_id, subject_name=name)


@router.get("/external-clients/{client_id}/loss-development.pdf")
async def external_loss_development_pdf(client_id: UUID, current_user=Depends(require_broker_pro)):
    async with get_connection() as conn:
        broker_id, name = await _external_ctx(conn, current_user.id, client_id)
        tri = await ld.build_development(conn, broker_id, "external", client_id, subject_name=name)
    pdf = await ld.render_triangle_pdf(name, tri)
    return _pdf(name, pdf)


@router.get("/external-clients/{client_id}/loss-ratio")
async def external_loss_ratio(client_id: UUID, current_user=Depends(require_broker_pro)):
    async with get_connection() as conn:
        broker_id, name = await _external_ctx(conn, current_user.id, client_id)
        return await ld.compute_loss_ratio(conn, broker_id, "external", client_id, subject_name=name)


@router.put("/external-clients/{client_id}/loss-ratio/premium")
async def external_set_loss_premium(client_id: UUID, body: LossPremiumUpsert,
                                    current_user=Depends(require_broker_pro)):
    async with get_connection() as conn:
        broker_id, name = await _external_ctx(conn, current_user.id, client_id)
        await _upsert_premium(conn, broker_id, "external", client_id, body, current_user.id)
        return await ld.compute_loss_ratio(conn, broker_id, "external", client_id, subject_name=name)
