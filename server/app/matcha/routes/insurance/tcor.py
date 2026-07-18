"""Total Cost of Risk routes (`/tcor`, feature `tcor`).

TCOR (premiums + retained losses + fees + mitigation) + an aggregate
retention/SIR optimizer priced off the risk assessment's Monte-Carlo loss
distribution. Business-facing, tenant-isolated.
"""

from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException

from ....database import get_connection
from ...dependencies import require_admin_or_client, get_client_company_id
from ...services import tcor_service
from ...models.tcor import TcorInput

router = APIRouter()


async def _require_company_id(current_user) -> UUID:
    company_id = await get_client_company_id(current_user)
    if company_id is None:
        raise HTTPException(status_code=403, detail="No company associated with this account")
    return company_id


@router.get("")
async def get_tcor(current_user=Depends(require_admin_or_client)):
    """Assembled TCOR + retention optimization for the caller's company."""
    company_id = await _require_company_id(current_user)
    async with get_connection() as conn:
        return await tcor_service.build_tcor(conn, company_id)


@router.put("/inputs")
async def upsert_input(body: TcorInput, current_user=Depends(require_admin_or_client)):
    """Create/update the premium/fee/retention inputs for one line + policy year."""
    company_id = await _require_company_id(current_user)
    async with get_connection() as conn:
        await conn.execute(
            """
            INSERT INTO company_tcor_inputs
                (company_id, line, annual_premium, fees, risk_mitigation_spend,
                 current_retention, policy_year, updated_by, updated_at)
            VALUES ($1, $2, $3, $4, $5, $6, $7, $8, NOW())
            ON CONFLICT (company_id, line, policy_year) DO UPDATE SET
                annual_premium        = EXCLUDED.annual_premium,
                fees                  = EXCLUDED.fees,
                risk_mitigation_spend = EXCLUDED.risk_mitigation_spend,
                current_retention     = EXCLUDED.current_retention,
                updated_by            = EXCLUDED.updated_by,
                updated_at            = NOW()
            """,
            company_id, body.line, body.annual_premium, body.fees,
            body.risk_mitigation_spend, body.current_retention,
            body.policy_year, current_user.id,
        )
        return await tcor_service.build_tcor(conn, company_id)


@router.delete("/inputs")
async def delete_input(line: str, policy_year: int | None = None,
                       current_user=Depends(require_admin_or_client)):
    """Remove a line's inputs (policy_year optional — NULL matches the null-year row)."""
    company_id = await _require_company_id(current_user)
    async with get_connection() as conn:
        result = await conn.execute(
            "DELETE FROM company_tcor_inputs WHERE company_id = $1 AND line = $2 "
            "AND policy_year IS NOT DISTINCT FROM $3",
            company_id, line, policy_year,
        )
        if result == "DELETE 0":
            raise HTTPException(status_code=404, detail="TCOR input not found")
        return await tcor_service.build_tcor(conn, company_id)
