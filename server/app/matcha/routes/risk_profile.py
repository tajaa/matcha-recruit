"""Client-facing risk portal (`/risk-profile`, feature `risk_profile`).

The report's "Risk Intelligence Central" (WTW p.10) for Matcha tenants: the
business's own composite risk index + WC/EPL/compliance component breakdown +
top fixes — "your insurability at a glance, and how to improve your terms."
The same `risk_index` engine the broker sees, scoped to the caller's own company.
"""

from fastapi import APIRouter, Depends

from ...database import get_connection
from ..dependencies import require_admin_or_client, get_client_company_id
from ..services import risk_index

router = APIRouter()


@router.get("")
async def get_risk_profile(current_user=Depends(require_admin_or_client)):
    company_id = await get_client_company_id(current_user)
    async with get_connection() as conn:
        return await risk_index.compute_risk_index(conn, company_id)
