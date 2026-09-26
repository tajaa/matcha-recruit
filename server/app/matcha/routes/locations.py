"""Company business locations — the one canonical read used by every
location-scoped surface. It is not feature-gated: company operators receive
the complete list while employees receive their own work site.
"""

from fastapi import APIRouter, Depends

from app.database import get_connection
from ..dependencies import get_client_company_id, require_company_member

router = APIRouter()


@router.get("")
async def list_company_locations(current_user=Depends(require_company_member)):
    company_id = await get_client_company_id(current_user)
    if company_id is None:
        return {"locations": []}
    async with get_connection() as conn:
        if current_user.role in {"admin", "client", "individual"}:
            rows = await conn.fetch(
                """
                SELECT l.id, l.name, l.address, l.city, l.state, l.zipcode, l.is_active,
                       COALESCE(p.week_start_weekday, 0) AS week_start_weekday
                FROM business_locations l
                LEFT JOIN schedule_location_profiles p
                  ON p.location_id = l.id AND p.company_id = l.company_id
                WHERE l.company_id = $1
                ORDER BY l.is_active DESC, l.name NULLS LAST, l.city, l.state
                """,
                company_id,
            )
        else:
            # Employee accounts receive their own active work site. This
            # supplies a name for published shifts without disclosing any
            # other company location in shared location pickers.
            rows = await conn.fetch(
                """
                SELECT l.id, l.name, l.address, l.city, l.state, l.zipcode, l.is_active,
                       COALESCE(p.week_start_weekday, 0) AS week_start_weekday
                FROM business_locations l
                JOIN employees e ON e.work_location_id = l.id
                LEFT JOIN schedule_location_profiles p
                  ON p.location_id = l.id AND p.company_id = l.company_id
                WHERE l.company_id = $1 AND e.org_id = $1 AND e.user_id = $2
                  AND COALESCE(e.employment_status, 'active') = 'active'
                ORDER BY l.is_active DESC, l.name NULLS LAST, l.city, l.state
                """,
                company_id, current_user.id,
            )
    return {"locations": [
        {"id": str(r["id"]), "name": r["name"], "address": r["address"],
         "city": r["city"], "state": r["state"], "zipcode": r["zipcode"],
         "is_active": r["is_active"],
         # Every location-scoped page computes its own week boundaries; without
         # this they would all render Sunday weeks for a Monday-start store.
         "week_start_weekday": int(r["week_start_weekday"] or 0)}
        for r in rows
    ]}
