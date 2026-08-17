"""Company business locations — the one canonical read used by every
location-scoped surface. Ungated on purpose: a location list is not a paid
feature, and gating it behind any one flag (as /compliance/locations does)
is what made that endpoint unusable as the shared source.
"""

from fastapi import APIRouter, Depends

from app.database import get_connection
from ..dependencies import require_admin_or_client, get_client_company_id

router = APIRouter()


@router.get("")
async def list_company_locations(current_user=Depends(require_admin_or_client)):
    company_id = await get_client_company_id(current_user)
    if company_id is None:
        return {"locations": []}
    async with get_connection() as conn:
        rows = await conn.fetch(
            """
            SELECT id, name, city, state, is_active
            FROM business_locations
            WHERE company_id = $1
            ORDER BY is_active DESC, name NULLS LAST, city, state
            """,
            company_id,
        )
    return {"locations": [
        {"id": str(r["id"]), "name": r["name"], "city": r["city"],
         "state": r["state"], "is_active": r["is_active"]}
        for r in rows
    ]}
