"""D&O / Management-liability readiness routes (`/management-liability`, feature `do_readiness`).

EPL-style readiness score for Directors & Officers / management liability, from
business-attested governance + financial factors. Tenant-isolated.
"""

from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException

from ....database import get_connection
from ...dependencies import require_admin_or_client, get_client_company_id
from ...services import do_readiness
from ...models.do_readiness import DoAttestation

router = APIRouter()

_VALID_KEYS = {f["key"] for f in do_readiness.FACTORS}


async def _require_company_id(current_user) -> UUID:
    company_id = await get_client_company_id(current_user)
    if company_id is None:
        raise HTTPException(status_code=403, detail="No company associated with this account")
    return company_id


@router.get("")
async def get_readiness(current_user=Depends(require_admin_or_client)):
    """D&O readiness composite + per-factor breakdown + top gap."""
    company_id = await _require_company_id(current_user)
    async with get_connection() as conn:
        result = await do_readiness.compute_do_readiness(conn, company_id)
    result["top_gap"] = do_readiness.do_top_gap(result)
    result["factor_catalog"] = do_readiness.FACTORS
    return result


@router.put("/attestations")
async def upsert_attestation(body: DoAttestation, current_user=Depends(require_admin_or_client)):
    """Record/update one factor attestation, then return the refreshed readiness."""
    if body.item_key not in _VALID_KEYS:
        raise HTTPException(status_code=400, detail="Unknown D&O factor key")
    company_id = await _require_company_id(current_user)
    async with get_connection() as conn:
        await conn.execute(
            """
            INSERT INTO company_do_attestations (company_id, item_key, status, note, updated_by, updated_at)
            VALUES ($1, $2, $3, $4, $5, NOW())
            ON CONFLICT (company_id, item_key) DO UPDATE SET
                status = EXCLUDED.status, note = EXCLUDED.note,
                updated_by = EXCLUDED.updated_by, updated_at = NOW()
            """,
            company_id, body.item_key, body.status, body.note, current_user.id,
        )
        result = await do_readiness.compute_do_readiness(conn, company_id)
    result["top_gap"] = do_readiness.do_top_gap(result)
    result["factor_catalog"] = do_readiness.FACTORS
    return result
