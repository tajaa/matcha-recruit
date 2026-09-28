"""Tenant-scoped history of break-reminder deliveries (email digest + push).

Read-only: the record is written by the producers themselves
(``services/scheduling/daily_digest.py``, ``services/scheduling/break_reminders.py``)
and the table refuses updates. Same audience as the published-shift audit log
(``audit_logs.py``): company admins and platform admins acting for a company.
"""

from datetime import date
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query

from app.database import get_connection
from app.matcha.dependencies import require_admin_or_client
from app.matcha.services.scheduling.break_reminder_events import (
    filter_options,
    list_events,
)

from ._shared import require_company_id

router = APIRouter()

_PAGE_LIMIT = 200


def validate_range(start: date | None, end: date | None) -> None:
    # Both ends are inclusive calendar days, so start == end is one full day.
    if start is not None and end is not None and end < start:
        raise HTTPException(status_code=422, detail="End date must be on or after the start date")


@router.get("/break-reminder-events")
async def list_break_reminder_events(
    start: date | None = Query(None, description="First location-local day, inclusive"),
    end: date | None = Query(None, description="Last location-local day, inclusive"),
    location_id: UUID | None = Query(None),
    employee_id: UUID | None = Query(None),
    limit: int = Query(50, ge=1, le=_PAGE_LIMIT),
    offset: int = Query(0, ge=0),
    current_user=Depends(require_admin_or_client),
):
    """Delivery attempts for break reminders, newest first."""
    company_id = await require_company_id(current_user)
    validate_range(start, end)
    async with get_connection() as conn:
        events, total = await list_events(
            conn, company_id,
            start=start, end=end, location_id=location_id, employee_id=employee_id,
            limit=limit, offset=offset,
        )
    return {"events": events, "total": total}


@router.get("/break-reminder-events/filter-options")
async def break_reminder_filter_options(current_user=Depends(require_admin_or_client)):
    """Locations and employees present in this company's delivery history."""
    company_id = await require_company_id(current_user)
    async with get_connection() as conn:
        return await filter_options(conn, company_id)
