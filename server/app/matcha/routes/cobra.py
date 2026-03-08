"""COBRA Qualifying Event Tracking API Routes.

Track COBRA qualifying events, deadlines, notices, and election status
for terminated or otherwise eligible employees.
"""

import logging
from datetime import date, datetime, timedelta
from typing import Optional, List
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field

from ...database import get_connection
from ...core.dependencies import get_current_user
from ..dependencies import require_admin_or_client, get_client_company_id
from ...core.models.auth import CurrentUser

logger = logging.getLogger(__name__)

router = APIRouter()

VALID_EVENT_TYPES = {
    "termination",
    "reduction_in_hours",
    "divorce",
    "dependent_aging_out",
    "medicare_enrollment",
    "employee_death",
}

VALID_STATUSES = {
    "pending_notice",
    "notice_sent",
    "election_pending",
    "elected",
    "waived",
    "expired",
    "terminated",
}

# Event types that get 36-month continuation (vs 18 for the rest)
EXTENDED_CONTINUATION_EVENT_TYPES = {
    "divorce",
    "dependent_aging_out",
    "medicare_enrollment",
    "employee_death",
}


# ---------------------------------------------------------------------------
# Pydantic Models
# ---------------------------------------------------------------------------

class CobraEventCreate(BaseModel):
    employee_id: UUID
    event_type: str
    event_date: date
    beneficiary_count: int = 1
    notes: Optional[str] = None
    offboarding_case_id: Optional[UUID] = None


class CobraEventUpdate(BaseModel):
    employer_notice_sent: Optional[bool] = None
    employer_notice_sent_date: Optional[date] = None
    administrator_notified: Optional[bool] = None
    administrator_notified_date: Optional[date] = None
    election_received: Optional[bool] = None
    election_received_date: Optional[date] = None
    status: Optional[str] = None
    beneficiary_count: Optional[int] = None
    notes: Optional[str] = None


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _row_to_dict(row) -> dict:
    """Convert an asyncpg Record to a JSON-friendly dict with string UUIDs."""
    d = dict(row)
    for key in ("id", "company_id", "employee_id", "offboarding_case_id"):
        if key in d and d[key] is not None:
            d[key] = str(d[key])
    for key in (
        "event_date",
        "employer_notice_deadline",
        "administrator_notice_deadline",
        "election_deadline",
        "continuation_end_date",
        "employer_notice_sent_date",
        "administrator_notified_date",
        "election_received_date",
    ):
        if key in d and d[key] is not None:
            d[key] = d[key].isoformat()
    for key in ("created_at", "updated_at"):
        if key in d and d[key] is not None:
            d[key] = d[key].isoformat()
    return d


def _compute_deadlines(event_type: str, event_date: date) -> dict:
    """Compute COBRA deadlines from event type and date."""
    employer_notice_deadline = event_date + timedelta(days=30)
    administrator_notice_deadline = event_date + timedelta(days=44)
    election_deadline = administrator_notice_deadline + timedelta(days=60)

    if event_type in EXTENDED_CONTINUATION_EVENT_TYPES:
        continuation_months = 36
    else:
        continuation_months = 18

    continuation_end_date = event_date + timedelta(days=continuation_months * 30)

    return {
        "employer_notice_deadline": employer_notice_deadline,
        "administrator_notice_deadline": administrator_notice_deadline,
        "election_deadline": election_deadline,
        "continuation_months": continuation_months,
        "continuation_end_date": continuation_end_date,
    }


# ---------------------------------------------------------------------------
# Endpoints
# ---------------------------------------------------------------------------

@router.post("/events")
async def create_cobra_event(
    body: CobraEventCreate,
    current_user: CurrentUser = Depends(require_admin_or_client),
):
    """Create a COBRA qualifying event."""
    company_id = await get_client_company_id(current_user)
    if company_id is None:
        raise HTTPException(status_code=400, detail="No company found")

    if body.event_type not in VALID_EVENT_TYPES:
        raise HTTPException(
            status_code=400,
            detail=f"Invalid event_type. Must be one of: {sorted(VALID_EVENT_TYPES)}",
        )

    async with get_connection() as conn:
        # Verify employee belongs to company
        emp = await conn.fetchval(
            "SELECT id FROM employees WHERE id = $1 AND org_id = $2",
            body.employee_id,
            company_id,
        )
        if not emp:
            raise HTTPException(status_code=404, detail="Employee not found in your organization")

        deadlines = _compute_deadlines(body.event_type, body.event_date)

        row = await conn.fetchrow(
            """
            INSERT INTO cobra_qualifying_events (
                company_id, employee_id, event_type, event_date,
                employer_notice_deadline, administrator_notice_deadline,
                election_deadline, continuation_months, continuation_end_date,
                beneficiary_count, notes, offboarding_case_id
            )
            VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9, $10, $11, $12)
            RETURNING *
            """,
            company_id,
            body.employee_id,
            body.event_type,
            body.event_date,
            deadlines["employer_notice_deadline"],
            deadlines["administrator_notice_deadline"],
            deadlines["election_deadline"],
            deadlines["continuation_months"],
            deadlines["continuation_end_date"],
            body.beneficiary_count,
            body.notes,
            body.offboarding_case_id,
        )

        return _row_to_dict(row)


@router.get("/events")
async def list_cobra_events(
    status: Optional[str] = Query(None),
    overdue: Optional[bool] = Query(None),
    current_user: CurrentUser = Depends(require_admin_or_client),
):
    """List COBRA qualifying events for the company."""
    company_id = await get_client_company_id(current_user)
    if company_id is None:
        return []

    async with get_connection() as conn:
        query = "SELECT * FROM cobra_qualifying_events WHERE company_id = $1"
        params: list = [company_id]
        idx = 2

        if status is not None:
            if status not in VALID_STATUSES:
                raise HTTPException(
                    status_code=400,
                    detail=f"Invalid status. Must be one of: {sorted(VALID_STATUSES)}",
                )
            query += f" AND status = ${idx}"
            params.append(status)
            idx += 1

        if overdue is True:
            query += " AND employer_notice_deadline < CURRENT_DATE AND employer_notice_sent = false"

        query += " ORDER BY created_at DESC"

        rows = await conn.fetch(query, *params)
        return [_row_to_dict(r) for r in rows]


@router.get("/overdue")
async def list_overdue_events(
    current_user: CurrentUser = Depends(require_admin_or_client),
):
    """List COBRA events past their employer notice deadline that haven't been actioned."""
    company_id = await get_client_company_id(current_user)
    if company_id is None:
        return []

    async with get_connection() as conn:
        rows = await conn.fetch(
            """
            SELECT
                ce.*,
                e.first_name AS employee_first_name,
                e.last_name AS employee_last_name,
                e.email AS employee_email,
                (CURRENT_DATE - ce.employer_notice_deadline) AS days_overdue
            FROM cobra_qualifying_events ce
            JOIN employees e ON e.id = ce.employee_id
            WHERE ce.company_id = $1
              AND ce.employer_notice_deadline < CURRENT_DATE
              AND ce.employer_notice_sent = false
            ORDER BY ce.employer_notice_deadline ASC
            """,
            company_id,
        )

        results = []
        for r in rows:
            d = _row_to_dict(r)
            d["employee_first_name"] = r["employee_first_name"]
            d["employee_last_name"] = r["employee_last_name"]
            d["employee_email"] = r["employee_email"]
            d["days_overdue"] = r["days_overdue"]
            results.append(d)
        return results


@router.get("/dashboard")
async def cobra_dashboard(
    current_user: CurrentUser = Depends(require_admin_or_client),
):
    """Summary stats for COBRA management dashboard."""
    company_id = await get_client_company_id(current_user)
    if company_id is None:
        return {
            "pending_notices": 0,
            "overdue_count": 0,
            "upcoming_deadlines": [],
            "total_active": 0,
        }

    async with get_connection() as conn:
        pending_notices = await conn.fetchval(
            "SELECT COUNT(*) FROM cobra_qualifying_events WHERE company_id = $1 AND status = 'pending_notice'",
            company_id,
        )

        overdue_count = await conn.fetchval(
            """
            SELECT COUNT(*) FROM cobra_qualifying_events
            WHERE company_id = $1
              AND employer_notice_deadline < CURRENT_DATE
              AND employer_notice_sent = false
            """,
            company_id,
        )

        upcoming_rows = await conn.fetch(
            """
            SELECT ce.*, e.first_name AS employee_first_name, e.last_name AS employee_last_name
            FROM cobra_qualifying_events ce
            JOIN employees e ON e.id = ce.employee_id
            WHERE ce.company_id = $1
              AND ce.employer_notice_deadline >= CURRENT_DATE
              AND ce.employer_notice_deadline <= CURRENT_DATE + INTERVAL '30 days'
            ORDER BY ce.employer_notice_deadline ASC
            """,
            company_id,
        )
        upcoming_deadlines = []
        for r in upcoming_rows:
            d = _row_to_dict(r)
            d["employee_first_name"] = r["employee_first_name"]
            d["employee_last_name"] = r["employee_last_name"]
            upcoming_deadlines.append(d)

        total_active = await conn.fetchval(
            """
            SELECT COUNT(*) FROM cobra_qualifying_events
            WHERE company_id = $1
              AND status NOT IN ('expired', 'terminated')
            """,
            company_id,
        )

        return {
            "pending_notices": pending_notices or 0,
            "overdue_count": overdue_count or 0,
            "upcoming_deadlines": upcoming_deadlines,
            "total_active": total_active or 0,
        }


@router.get("/events/{event_id}")
async def get_cobra_event(
    event_id: UUID,
    current_user: CurrentUser = Depends(require_admin_or_client),
):
    """Get a single COBRA event with employee info."""
    company_id = await get_client_company_id(current_user)
    if company_id is None:
        raise HTTPException(status_code=404, detail="Event not found")

    async with get_connection() as conn:
        row = await conn.fetchrow(
            """
            SELECT
                ce.*,
                e.first_name AS employee_first_name,
                e.last_name AS employee_last_name,
                e.email AS employee_email
            FROM cobra_qualifying_events ce
            JOIN employees e ON e.id = ce.employee_id
            WHERE ce.id = $1 AND ce.company_id = $2
            """,
            event_id,
            company_id,
        )

        if not row:
            raise HTTPException(status_code=404, detail="Event not found")

        d = _row_to_dict(row)
        d["employee_first_name"] = row["employee_first_name"]
        d["employee_last_name"] = row["employee_last_name"]
        d["employee_email"] = row["employee_email"]
        return d


@router.put("/events/{event_id}")
async def update_cobra_event(
    event_id: UUID,
    body: CobraEventUpdate,
    current_user: CurrentUser = Depends(require_admin_or_client),
):
    """Update a COBRA qualifying event."""
    company_id = await get_client_company_id(current_user)
    if company_id is None:
        raise HTTPException(status_code=404, detail="Event not found")

    async with get_connection() as conn:
        # Verify event belongs to company
        existing = await conn.fetchrow(
            "SELECT * FROM cobra_qualifying_events WHERE id = $1 AND company_id = $2",
            event_id,
            company_id,
        )
        if not existing:
            raise HTTPException(status_code=404, detail="Event not found")

        updates = []
        params: list = []
        idx = 1

        # Handle employer_notice_sent with auto-date
        if body.employer_notice_sent is not None:
            updates.append(f"employer_notice_sent = ${idx}")
            params.append(body.employer_notice_sent)
            idx += 1

            if body.employer_notice_sent and body.employer_notice_sent_date is None:
                updates.append(f"employer_notice_sent_date = ${idx}")
                params.append(date.today())
                idx += 1
            elif body.employer_notice_sent_date is not None:
                updates.append(f"employer_notice_sent_date = ${idx}")
                params.append(body.employer_notice_sent_date)
                idx += 1
        elif body.employer_notice_sent_date is not None:
            updates.append(f"employer_notice_sent_date = ${idx}")
            params.append(body.employer_notice_sent_date)
            idx += 1

        # Handle administrator_notified with auto-date
        if body.administrator_notified is not None:
            updates.append(f"administrator_notified = ${idx}")
            params.append(body.administrator_notified)
            idx += 1

            if body.administrator_notified and body.administrator_notified_date is None:
                updates.append(f"administrator_notified_date = ${idx}")
                params.append(date.today())
                idx += 1
            elif body.administrator_notified_date is not None:
                updates.append(f"administrator_notified_date = ${idx}")
                params.append(body.administrator_notified_date)
                idx += 1
        elif body.administrator_notified_date is not None:
            updates.append(f"administrator_notified_date = ${idx}")
            params.append(body.administrator_notified_date)
            idx += 1

        # Handle election_received with auto-status advancement
        status_override = None
        if body.election_received is not None:
            updates.append(f"election_received = ${idx}")
            params.append(body.election_received)
            idx += 1

            if body.election_received_date is not None:
                updates.append(f"election_received_date = ${idx}")
                params.append(body.election_received_date)
                idx += 1
            elif body.election_received:
                updates.append(f"election_received_date = ${idx}")
                params.append(date.today())
                idx += 1

            # Auto-advance status based on election decision
            if body.election_received is True:
                status_override = "elected"
            elif body.election_received is False:
                status_override = "waived"
        elif body.election_received_date is not None:
            updates.append(f"election_received_date = ${idx}")
            params.append(body.election_received_date)
            idx += 1

        # Handle explicit status (takes precedence over auto-advance)
        if body.status is not None:
            if body.status not in VALID_STATUSES:
                raise HTTPException(
                    status_code=400,
                    detail=f"Invalid status. Must be one of: {sorted(VALID_STATUSES)}",
                )
            updates.append(f"status = ${idx}")
            params.append(body.status)
            idx += 1
        elif status_override is not None:
            updates.append(f"status = ${idx}")
            params.append(status_override)
            idx += 1

        # Simple fields
        if body.beneficiary_count is not None:
            updates.append(f"beneficiary_count = ${idx}")
            params.append(body.beneficiary_count)
            idx += 1

        if body.notes is not None:
            updates.append(f"notes = ${idx}")
            params.append(body.notes)
            idx += 1

        if not updates:
            raise HTTPException(status_code=400, detail="No updates provided")

        updates.append("updated_at = NOW()")
        params.append(event_id)
        params.append(company_id)

        query = f"""
            UPDATE cobra_qualifying_events
            SET {', '.join(updates)}
            WHERE id = ${idx} AND company_id = ${idx + 1}
            RETURNING *
        """

        row = await conn.fetchrow(query, *params)
        if not row:
            raise HTTPException(status_code=404, detail="Event not found")

        return _row_to_dict(row)
