"""Scheduled labor cost — the dollars behind the hours (feature `labor_cost`).

One endpoint, deliberately its own router rather than a block bolted onto
`planning-inputs`: that route is mounted on `require_company_member`, which
admits the `employee` role, and wage data must not ride a response an employee
can reach even when a manager scope happens to gate it today. Everything here
goes through `is_labor_cost_visible` (flag + business-admin role) and the same
`assert_manager_location` check the rest of the Schedule Pilot uses.

Figures are AS-SCHEDULED, never as-worked — there is no time-clock data in this
codebase. The response says so in `basis.as_scheduled`, and the UI copy must
say "scheduled labor cost".
"""

from datetime import date
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query

from app.database import get_connection

from ...dependencies import require_admin_or_client
from ...services.scheduling.labor_cost_service import (
    is_labor_cost_visible, load_week_cost,
)
from ...services.scheduling.schedule_assistant_session import assert_manager_location
from ...services.scheduling.schedule_review import jurisdiction_message
from ...services.scheduling.shift_compliance import jurisdiction_rule_status
from ._shared import require_company_id

router = APIRouter()


@router.get("/locations/{location_id}/labor-cost")
async def get_labor_cost(
    location_id: UUID,
    week_start: date = Query(..., description="First day of the editor week"),
    current_user=Depends(require_admin_or_client),
):
    """The week's scheduled labor cost for one location.

    403 rather than an empty payload when the flag is off or the caller is not
    a business admin: a zeroed cost block reads as "this week is free", which
    is the one thing it never means.
    """
    company_id = await require_company_id(current_user)
    async with get_connection() as conn:
        if not await is_labor_cost_visible(company_id, current_user.role, conn=conn):
            raise HTTPException(status_code=403, detail="Labor cost is not enabled for this account")
        await assert_manager_location(
            conn, company_id=company_id, user_id=current_user.id,
            actor_role=current_user.role, location_id=location_id,
        )
        cost = await load_week_cost(
            conn, company_id=company_id, location_id=location_id, week_start=week_start,
        )
        jurisdiction = jurisdiction_message(
            await jurisdiction_rule_status(conn, company_id, location_id),
        )
    return {**cost.payload(), "jurisdiction": jurisdiction}
