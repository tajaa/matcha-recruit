"""Broker carrier hub — quote/present/bind + claims bridge + risk-to-rate (`/broker`).

Puts the broker in the middle between their clients and the carrier (Coterie). A
broker can quote and place policies for any client in their book — on-platform
tenant `companies` (rich data) and off-platform `broker_external_clients` — then
either bind directly (when the client-link permits) or present the quote for the
client to accept on their own Insurance page.

Two adjacent capabilities ride the same carrier link, gated by
`coterie_service.has_capability` so they stay inert until a partner sandbox
confirms the data exists:
- **Claims Bridge** — pull loss runs; file a First Notice of Loss from a logged
  IR incident (`insurance_claims`).
- **Risk-to-Rate** — surface the client's verified controls as premium-credit
  levers and push the verified evidence to the carrier.

Role-gated per-endpoint (`require_broker` / `require_broker_pro`), never a company
feature flag — brokers aren't tenants. Ownership via the shared broker helpers.
"""

import json
import logging
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query

from ...database import get_connection
from ..dependencies import require_broker, require_broker_pro
from ..models.insurance import BrokerQuoteRequest, FnolRequest, PresentRequest
from ..services import coterie_service, risk_to_rate
from ..services.coterie_service import CoterieError
from .broker_external import _broker_id
from .broker_portfolio import _assert_broker_owns_company

logger = logging.getLogger(__name__)
router = APIRouter()


# --- shared helpers ------------------------------------------------------------

async def _assert_external_owned(conn, broker_id: UUID, client_id: UUID) -> None:
    owns = await conn.fetchval(
        "SELECT 1 FROM broker_external_clients WHERE id = $1 AND broker_id = $2",
        client_id, broker_id,
    )
    if not owns:
        raise HTTPException(status_code=404, detail="External client not found")


async def _can_broker_bind(conn, broker_id: UUID, company_id: UUID) -> bool:
    """The 'configurable' bind-authority knob: a broker may bind directly for a
    client only when that client-link grants ``allow_broker_bind``. Default off →
    the broker must present the quote for the client to accept."""
    perms = await conn.fetchval(
        "SELECT permissions FROM broker_company_links "
        "WHERE broker_id = $1 AND company_id = $2 AND status IN ('active', 'grace') "
        "ORDER BY linked_at ASC LIMIT 1",
        broker_id, company_id,
    )
    if isinstance(perms, str):
        perms = json.loads(perms)
    return bool((perms or {}).get("allow_broker_bind"))


def _raise_coterie(e: CoterieError):
    code = str(e)
    mapping = {
        "quote_not_found": (404, "Quote not found"),
        "already_bound": (409, "Quote already bound"),
        "not_quotable": (409, "Quote is not in a bindable state"),
        "external_client_not_found": (404, "External client not found"),
    }
    status_code, detail = mapping.get(code, (502, f"Carrier error: {code}"))
    raise HTTPException(status_code=status_code, detail=detail)


def _require_capability(name: str):
    if not coterie_service.has_capability(name):
        raise HTTPException(
            status_code=501,
            detail=f"Carrier capability '{name}' is not enabled — needs a live carrier appointment.",
        )


def _quote_line(line: str) -> BrokerQuoteRequest:
    try:
        return BrokerQuoteRequest(line=line)
    except Exception:
        raise HTTPException(status_code=400, detail="Unsupported line")


# --- on-platform clients (require_broker) --------------------------------------

@router.get("/clients/{company_id}/insurance/prefill")
async def tenant_prefill(company_id: UUID, line: str = "bop", current_user=Depends(require_broker)):
    async with get_connection() as conn:
        await _assert_broker_owns_company(conn, current_user.id, company_id)
        broker_id = await _broker_id(conn, current_user.id)
        payload = await coterie_service.build_quote_request(conn, company_id, _quote_line(line))
        can_bind = await _can_broker_bind(conn, broker_id, company_id)
    return {"line": line, "payload": payload, "mock_mode": coterie_service.is_mock_mode(),
            "can_bind": can_bind}


@router.get("/clients/{company_id}/insurance/quotes")
async def tenant_list_quotes(company_id: UUID, current_user=Depends(require_broker)):
    async with get_connection() as conn:
        await _assert_broker_owns_company(conn, current_user.id, company_id)
        return {"quotes": await coterie_service.list_broker_quotes(conn, company_id=company_id)}


@router.post("/clients/{company_id}/insurance/quote")
async def tenant_create_quote(company_id: UUID, req: BrokerQuoteRequest,
                              current_user=Depends(require_broker)):
    async with get_connection() as conn:
        await _assert_broker_owns_company(conn, current_user.id, company_id)
        broker_id = await _broker_id(conn, current_user.id)
        return await coterie_service.create_broker_quote(
            conn, broker_id=broker_id, req=req, created_by=current_user.id, company_id=company_id)


@router.post("/clients/{company_id}/insurance/quotes/{quote_id}/present")
async def tenant_present_quote(company_id: UUID, quote_id: UUID,
                              body: PresentRequest | None = None,
                              current_user=Depends(require_broker)):
    """Present a quoted policy to the client for acceptance (they bind it on their
    own Insurance page). The non-direct half of the configurable bind authority."""
    async with get_connection() as conn:
        await _assert_broker_owns_company(conn, current_user.id, company_id)
        try:
            return await coterie_service.present_quote(
                conn, company_id=company_id, quote_id=quote_id,
                commission_bps=body.commission_bps if body else None,
                broker_note=body.broker_note if body else None)
        except CoterieError as e:
            _raise_coterie(e)


@router.post("/clients/{company_id}/insurance/quotes/{quote_id}/bind")
async def tenant_bind_quote(company_id: UUID, quote_id: UUID, current_user=Depends(require_broker)):
    """Broker binds directly (agent-of-record). Gated by the client-link's
    ``allow_broker_bind`` — otherwise the broker must present for client acceptance."""
    async with get_connection() as conn:
        await _assert_broker_owns_company(conn, current_user.id, company_id)
        broker_id = await _broker_id(conn, current_user.id)
        if not await _can_broker_bind(conn, broker_id, company_id):
            raise HTTPException(
                status_code=403,
                detail="Direct bind is not enabled for this client — present the quote for client acceptance.")
        try:
            return await coterie_service.bind_quote(conn, company_id, quote_id, current_user.id)
        except CoterieError as e:
            _raise_coterie(e)


# --- Risk-to-Rate (capability: credits) ----------------------------------------

@router.get("/clients/{company_id}/insurance/risk-to-rate")
async def tenant_risk_to_rate(company_id: UUID, current_user=Depends(require_broker)):
    _require_capability("credits")
    async with get_connection() as conn:
        await _assert_broker_owns_company(conn, current_user.id, company_id)
        return await risk_to_rate.build(conn, company_id)


@router.post("/clients/{company_id}/insurance/risk-to-rate/sync")
async def tenant_risk_to_rate_sync(company_id: UUID, current_user=Depends(require_broker)):
    """Push the client's verified evidence bundle to the carrier (mock no-op until
    the credits capability is live)."""
    _require_capability("credits")
    async with get_connection() as conn:
        await _assert_broker_owns_company(conn, current_user.id, company_id)
        levers = await risk_to_rate.build(conn, company_id)
    return {"synced": True, "mock_mode": coterie_service.is_mock_mode(),
            "levers_pushed": len(levers["levers"]),
            "available_credit_bps": levers["available_credit_bps"],
            "realized_credit_bps": levers["realized_credit_bps"]}


# --- Claims Bridge (capabilities: loss_runs, fnol) -----------------------------

def _serialize_claim(row) -> dict:
    return {
        "id": str(row["id"]),
        "kind": row["kind"],
        "carrier": row["carrier"],
        "claim_ref": row["claim_ref"],
        "status": row["status"],
        "incident_id": str(row["incident_id"]) if row["incident_id"] else None,
        "amount_cents": row["amount_cents"],
        "created_at": row["created_at"].isoformat() if row["created_at"] else None,
    }


@router.get("/clients/{company_id}/insurance/loss-runs")
async def tenant_loss_runs(company_id: UUID, current_user=Depends(require_broker)):
    """Pull loss runs from the carrier. Mock returns representative rows and records
    the pull as provenance; live-wiring into loss-development is a follow-up."""
    _require_capability("loss_runs")
    async with get_connection() as conn:
        await _assert_broker_owns_company(conn, current_user.id, company_id)
        broker_id = await _broker_id(conn, current_user.id)
        loss_runs = coterie_service.mock_loss_runs() if coterie_service.is_mock_mode() else []
        await conn.execute(
            """
            INSERT INTO insurance_claims
                (company_id, broker_id, carrier, kind, status, payload, created_by)
            VALUES ($1, $2, 'coterie', 'loss_run_import', 'imported', $3::jsonb, $4)
            """,
            company_id, broker_id, json.dumps({"loss_runs": loss_runs}), current_user.id,
        )
    return {"loss_runs": loss_runs, "mock_mode": coterie_service.is_mock_mode()}


@router.post("/clients/{company_id}/insurance/fnol")
async def tenant_fnol(company_id: UUID, body: FnolRequest, current_user=Depends(require_broker)):
    """File a First Notice of Loss from a logged IR incident."""
    _require_capability("fnol")
    async with get_connection() as conn:
        await _assert_broker_owns_company(conn, current_user.id, company_id)
        broker_id = await _broker_id(conn, current_user.id)
        inc = await conn.fetchrow(
            "SELECT id, incident_number FROM ir_incidents WHERE id = $1 AND company_id = $2",
            body.incident_id, company_id,
        )
        if not inc:
            raise HTTPException(status_code=404, detail="Incident not found")
        claim_ref = coterie_service.file_fnol(str(body.incident_id), inc["incident_number"])
        row = await conn.fetchrow(
            """
            INSERT INTO insurance_claims
                (company_id, broker_id, incident_id, carrier, kind, claim_ref, status, payload, created_by)
            VALUES ($1, $2, $3, 'coterie', 'fnol', $4, 'open', $5::jsonb, $6)
            RETURNING *
            """,
            company_id, broker_id, body.incident_id, claim_ref,
            json.dumps({"description": body.description, "incident_number": inc["incident_number"]}),
            current_user.id,
        )
    return _serialize_claim(row)


# --- off-platform clients (require_broker_pro) ---------------------------------

@router.get("/external-clients/{client_id}/insurance/prefill")
async def external_prefill(client_id: UUID, line: str = "bop", current_user=Depends(require_broker_pro)):
    async with get_connection() as conn:
        broker_id = await _broker_id(conn, current_user.id)
        await _assert_external_owned(conn, broker_id, client_id)
        try:
            payload = await coterie_service.build_quote_request_external(
                conn, client_id, _quote_line(line), broker_id=broker_id)
        except CoterieError as e:
            _raise_coterie(e)
    return {"line": line, "payload": payload, "mock_mode": coterie_service.is_mock_mode(),
            "can_bind": True}


@router.get("/external-clients/{client_id}/insurance/quotes")
async def external_list_quotes(client_id: UUID, current_user=Depends(require_broker_pro)):
    async with get_connection() as conn:
        broker_id = await _broker_id(conn, current_user.id)
        await _assert_external_owned(conn, broker_id, client_id)
        return {"quotes": await coterie_service.list_broker_quotes(conn, external_client_id=client_id)}


@router.post("/external-clients/{client_id}/insurance/quote")
async def external_create_quote(client_id: UUID, req: BrokerQuoteRequest,
                                current_user=Depends(require_broker_pro)):
    async with get_connection() as conn:
        broker_id = await _broker_id(conn, current_user.id)
        await _assert_external_owned(conn, broker_id, client_id)
        return await coterie_service.create_broker_quote(
            conn, broker_id=broker_id, req=req, created_by=current_user.id, external_client_id=client_id)


@router.post("/external-clients/{client_id}/insurance/quotes/{quote_id}/bind")
async def external_bind_quote(client_id: UUID, quote_id: UUID, current_user=Depends(require_broker_pro)):
    async with get_connection() as conn:
        broker_id = await _broker_id(conn, current_user.id)
        await _assert_external_owned(conn, broker_id, client_id)
        try:
            return await coterie_service.bind_external_quote(
                conn, broker_id=broker_id, external_client_id=client_id,
                quote_id=quote_id, bound_by=current_user.id)
        except CoterieError as e:
            _raise_coterie(e)


# --- broker book-level rollups (require_broker) --------------------------------

@router.get("/insurance/book")
async def insurance_book(current_user=Depends(require_broker)):
    """Placed policies across the broker's whole book — premium + estimated
    commission rollup. Reads bound, broker-placed quotes."""
    async with get_connection() as conn:
        broker_id = await _broker_id(conn, current_user.id)
        rows = await conn.fetch(
            """
            SELECT q.id, q.line, q.premium_cents, q.commission_bps, q.company_id,
                   q.external_client_id, q.quote_payload,
                   COALESCE(c.name, ec.name) AS client_name
            FROM insurance_quotes q
            LEFT JOIN companies c ON c.id = q.company_id
            LEFT JOIN broker_external_clients ec ON ec.id = q.external_client_id
            WHERE q.broker_id = $1 AND q.status = 'bound'
            ORDER BY q.updated_at DESC
            """,
            broker_id,
        )
    policies, total_premium, total_commission = [], 0, 0
    for r in rows:
        premium = r["premium_cents"] or 0
        bps = r["commission_bps"] or 0
        commission = int(round(premium * bps / 10_000))
        total_premium += premium
        total_commission += commission
        payload = r["quote_payload"]
        if isinstance(payload, str):
            payload = json.loads(payload) if payload else {}
        policies.append({
            "id": str(r["id"]), "line": r["line"], "client_name": r["client_name"],
            "on_platform": r["company_id"] is not None,
            "premium_cents": premium, "commission_bps": bps,
            "est_commission_cents": commission,
            "policy_expiry": (payload or {}).get("policy_expiry"),
        })
    return {"policies": policies, "count": len(policies),
            "total_premium_cents": total_premium, "est_commission_cents": total_commission}


@router.get("/insurance/renewals")
async def insurance_renewals(days: int = Query(90, ge=1, le=365),
                             current_user=Depends(require_broker)):
    """Bound policies whose term expires within ``days`` — the re-quote queue."""
    async with get_connection() as conn:
        broker_id = await _broker_id(conn, current_user.id)
        rows = await conn.fetch(
            """
            SELECT q.id, q.line, q.premium_cents, q.company_id, q.external_client_id,
                   (q.quote_payload->>'policy_expiry') AS policy_expiry,
                   COALESCE(c.name, ec.name) AS client_name
            FROM insurance_quotes q
            LEFT JOIN companies c ON c.id = q.company_id
            LEFT JOIN broker_external_clients ec ON ec.id = q.external_client_id
            WHERE q.broker_id = $1 AND q.status = 'bound'
              AND (q.quote_payload->>'policy_expiry') IS NOT NULL
              AND (q.quote_payload->>'policy_expiry')::date <= (CURRENT_DATE + ($2 || ' days')::interval)
            ORDER BY (q.quote_payload->>'policy_expiry')::date ASC
            """,
            broker_id, str(days),
        )
    return {"renewals": [
        {"id": str(r["id"]), "line": r["line"], "client_name": r["client_name"],
         "on_platform": r["company_id"] is not None,
         "premium_cents": r["premium_cents"], "policy_expiry": r["policy_expiry"]}
        for r in rows
    ], "window_days": days}
