"""What the caller may manage on the schedule.

The Matcha Schedule app reads this once after sign-in to decide whether to
show manager tools, which stores to offer, and the pending-approvals badge.
Crew get `can_manage: false` rather than a 403, so the app can ask everyone.
No wage or labor-cost field ever rides on it.
"""

from fastapi import APIRouter, Depends, HTTPException

from app.core.feature_flags import get_company_features
from app.database import get_connection
from ...dependencies import require_company_member
from ._shared import (
    REQUEST_SELECT, request_queue_filter, require_company_id, resolve_schedule_manager_scope,
)

router = APIRouter()


@router.get("/manager/scope")
async def get_manager_scope(current_user=Depends(require_company_member)):
    company_id = await require_company_id(current_user)
    async with get_connection() as conn:
        features = await get_company_features(company_id, conn=conn)
        feature_flags = {
            name: bool(features.get(name)) for name in ("huume", "matcha_work", "time_off")
        }
        try:
            scope = await resolve_schedule_manager_scope(conn, company_id=company_id, user=current_user)
        except HTTPException as exc:
            if exc.status_code != 403:
                raise
            return {
                "can_manage": False, "role": current_user.role, "company_wide": False,
                "locations": [], "features": feature_flags, "pending_requests": 0,
            }
        locations = await conn.fetch(
            """
            SELECT l.id, l.name, l.timezone,
                   COALESCE(p.week_start_weekday, 0) AS week_start_weekday
              FROM business_locations l
              LEFT JOIN schedule_location_profiles p
                ON p.location_id = l.id AND p.company_id = l.company_id
             WHERE l.company_id = $1 AND COALESCE(l.is_active, true)
               AND ($2::boolean OR l.id = ANY($3::uuid[]))
             ORDER BY l.name NULLS LAST, l.city, l.state
            """,
            company_id, scope.company_wide, sorted(scope.location_ids),
        )
        params: list = [company_id]
        where = request_queue_filter(scope, None, params)
        pending = await conn.fetchval(
            f"SELECT COUNT(*) FROM ({REQUEST_SELECT} "
            f"WHERE r.company_id = $1 AND r.status = 'awaiting_manager'{where}) AS queue",
            *params,
        )
    return {
        "can_manage": True,
        "role": current_user.role,
        "company_wide": scope.company_wide,
        "locations": [
            {
                "id": str(row["id"]),
                "name": row["name"],
                "timezone": row["timezone"],
                "week_start_weekday": int(row["week_start_weekday"] or 0),
            }
            for row in locations
        ],
        "features": feature_flags,
        "pending_requests": int(pending or 0),
    }
