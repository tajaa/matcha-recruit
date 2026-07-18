"""Carrier quote/bind routes (`/insurance`, feature `carrier_quotes`).

A matcha-lite business gets a real small-commercial insurance quote (BOP/GL/WC/PL)
from Coterie built from data it already has on file, reviews it, and binds a policy
inline. A bound policy lands in the existing certificate store + carried-coverage
lines. Carrier calls run through coterie_service (mock mode until live partner
credentials exist). Tenant-isolated.
"""

from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException

from ....database import get_connection
from ...dependencies import require_admin_or_client, get_client_company_id
from ...models.insurance import QuoteRequest
from ...services import coterie_service
from ...services.coterie_service import CoterieError

router = APIRouter()


async def _require_company_id(current_user) -> UUID:
    company_id = await get_client_company_id(current_user)
    if company_id is None:
        raise HTTPException(status_code=403, detail="No company associated with this account")
    return company_id


@router.get("/prefill")
async def prefill(line: str = "bop", current_user=Depends(require_admin_or_client)):
    """The quote inputs derived from the company's own data, for the caller to
    review/edit before submitting. Never auto-submits — quoting is a financial action."""
    company_id = await _require_company_id(current_user)
    try:
        req = QuoteRequest(line=line)  # validates the line; overrides empty
    except Exception:
        raise HTTPException(status_code=400, detail="Unsupported line")
    async with get_connection() as conn:
        payload = await coterie_service.build_quote_request(conn, company_id, req)
    return {"line": line, "payload": payload, "mock_mode": coterie_service.is_mock_mode()}


@router.get("/quotes")
async def list_quotes(current_user=Depends(require_admin_or_client)):
    company_id = await _require_company_id(current_user)
    async with get_connection() as conn:
        return {"quotes": await coterie_service.list_quotes(conn, company_id)}


@router.post("/quote")
async def create_quote(req: QuoteRequest, current_user=Depends(require_admin_or_client)):
    """Request a quote from Coterie and persist it. Returns the quote row (an
    error status if the carrier call failed — never a 500 for a carrier decline)."""
    company_id = await _require_company_id(current_user)
    async with get_connection() as conn:
        return await coterie_service.create_quote(conn, company_id, req, current_user.id)


@router.post("/quotes/{quote_id}/bind")
async def bind_quote(quote_id: UUID, current_user=Depends(require_admin_or_client)):
    """Bind a quoted policy. Writes a certificate + carried-coverage line."""
    company_id = await _require_company_id(current_user)
    async with get_connection() as conn:
        try:
            return await coterie_service.bind_quote(conn, company_id, quote_id, current_user.id)
        except CoterieError as e:
            code = str(e)
            if code == "quote_not_found":
                raise HTTPException(status_code=404, detail="Quote not found")
            if code == "already_bound":
                raise HTTPException(status_code=409, detail="Quote already bound")
            if code == "not_quotable":
                raise HTTPException(status_code=409, detail="Quote is not in a bindable state")
            raise HTTPException(status_code=502, detail=f"Carrier bind failed: {code}")
