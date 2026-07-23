"""Open-enrollment periods, election review, life-event review (admin/client)."""
import json
import logging
from datetime import date
from uuid import UUID

import asyncpg
from fastapi import APIRouter, Depends, HTTPException

from app.core.models.auth import CurrentUser
from app.database import get_connection
from app.matcha.dependencies import require_admin_or_client, get_client_company_id
from app.matcha.models.benefits import DecisionInput, OePeriodCreate, OePeriodUpdate
from app.matcha.services.benefits_enrollment import life_event_window_ends_on, log_benefit_audit

logger = logging.getLogger(__name__)

router = APIRouter()


async def _require_company(current_user: CurrentUser) -> UUID:
    company_id = await get_client_company_id(current_user)
    if company_id is None:
        raise HTTPException(status_code=400, detail="No company found")
    return company_id


def _serialize_period(r) -> dict:
    return {
        "id": str(r["id"]),
        "company_id": str(r["company_id"]),
        "name": r["name"],
        "starts_on": r["starts_on"],
        "ends_on": r["ends_on"],
        "plan_year_start": r["plan_year_start"],
        "status": r["status"],
        "opened_at": r["opened_at"],
        "closed_at": r["closed_at"],
    }


def _serialize_election(r) -> dict:
    return {
        "id": str(r["id"]),
        "employee_id": str(r["employee_id"]),
        "employee_name": r.get("employee_name"),
        "plan_type": r["plan_type"],
        "plan_id": str(r["plan_id"]) if r["plan_id"] else None,
        "plan_name": r.get("plan_name"),
        "tier_id": str(r["tier_id"]) if r["tier_id"] else None,
        "coverage_tier": r.get("coverage_tier"),
        "waived": r["waived"],
        "dependents": json.loads(r["dependents"]) if isinstance(r["dependents"], str) else r["dependents"],
        "status": r["status"],
        "submitted_at": r["submitted_at"],
        "decided_at": r["decided_at"],
        "decision_note": r["decision_note"],
        "effective_date": r["effective_date"],
    }


def _serialize_life_event(r) -> dict:
    return {
        "id": str(r["id"]),
        "employee_id": str(r["employee_id"]),
        "employee_name": r.get("employee_name"),
        "event_type": r["event_type"],
        "event_date": r["event_date"],
        "description": r["description"],
        "status": r["status"],
        "window_days": r["window_days"],
        "window_ends_on": r["window_ends_on"],
        "review_note": r["review_note"],
    }


# ---------------------------------------------------------------------------
# Open enrollment periods
# ---------------------------------------------------------------------------

@router.get("/enrollment/periods")
async def list_periods(current_user: CurrentUser = Depends(require_admin_or_client)):
    company_id = await _require_company(current_user)
    async with get_connection() as conn:
        rows = await conn.fetch(
            "SELECT * FROM open_enrollment_periods WHERE company_id = $1 ORDER BY starts_on DESC",
            company_id,
        )
    return {"periods": [_serialize_period(r) for r in rows]}


@router.post("/enrollment/periods")
async def create_period(
    payload: OePeriodCreate,
    current_user: CurrentUser = Depends(require_admin_or_client),
):
    company_id = await _require_company(current_user)
    async with get_connection() as conn:
        period = await conn.fetchrow(
            """
            INSERT INTO open_enrollment_periods (company_id, name, starts_on, ends_on, plan_year_start)
            VALUES ($1, $2, $3, $4, $5)
            RETURNING *
            """,
            company_id, payload.name, payload.starts_on, payload.ends_on, payload.plan_year_start,
        )
        await log_benefit_audit(
            conn, company_id, current_user.id, current_user.role,
            "oe_period", period["id"], "created", {"name": payload.name},
        )
    return _serialize_period(period)


@router.patch("/enrollment/periods/{period_id}")
async def update_period(
    period_id: UUID,
    payload: OePeriodUpdate,
    current_user: CurrentUser = Depends(require_admin_or_client),
):
    company_id = await _require_company(current_user)
    fields = payload.model_dump(exclude_unset=True)
    if not fields:
        raise HTTPException(status_code=400, detail="No fields to update")
    async with get_connection() as conn:
        existing = await conn.fetchrow(
            "SELECT * FROM open_enrollment_periods WHERE id = $1 AND company_id = $2",
            period_id, company_id,
        )
        if not existing:
            raise HTTPException(status_code=404, detail="Period not found")
        if existing["status"] == "open":
            disallowed = set(fields) - {"ends_on"}
            if disallowed:
                raise HTTPException(status_code=409, detail="only ends_on can be edited while open")
        elif existing["status"] == "closed":
            raise HTTPException(status_code=409, detail="cannot edit a closed period")

        set_clauses = []
        values: list = []
        for i, (k, v) in enumerate(fields.items(), start=1):
            set_clauses.append(f"{k} = ${i}")
            values.append(v)
        values.append(period_id)
        period = await conn.fetchrow(
            f"UPDATE open_enrollment_periods SET {', '.join(set_clauses)}, updated_at = NOW() "
            f"WHERE id = ${len(values)} RETURNING *",
            *values,
        )
        await log_benefit_audit(
            conn, company_id, current_user.id, current_user.role,
            "oe_period", period_id, "updated", fields,
        )
    return _serialize_period(period)


@router.post("/enrollment/periods/{period_id}/open")
async def open_period(
    period_id: UUID,
    current_user: CurrentUser = Depends(require_admin_or_client),
):
    company_id = await _require_company(current_user)
    async with get_connection() as conn:
        existing = await conn.fetchrow(
            "SELECT * FROM open_enrollment_periods WHERE id = $1 AND company_id = $2",
            period_id, company_id,
        )
        if not existing:
            raise HTTPException(status_code=404, detail="Period not found")
        if existing["status"] != "draft":
            raise HTTPException(status_code=409, detail=f"period is {existing['status']}, not draft")
        try:
            period = await conn.fetchrow(
                "UPDATE open_enrollment_periods SET status = 'open', opened_at = NOW(), updated_at = NOW() "
                "WHERE id = $1 RETURNING *",
                period_id,
            )
        except asyncpg.UniqueViolationError:
            raise HTTPException(status_code=409, detail="another period is already open for this company")
        await log_benefit_audit(
            conn, company_id, current_user.id, current_user.role, "oe_period", period_id, "opened",
        )
    return _serialize_period(period)


@router.post("/enrollment/periods/{period_id}/close")
async def close_period(
    period_id: UUID,
    current_user: CurrentUser = Depends(require_admin_or_client),
):
    company_id = await _require_company(current_user)
    async with get_connection() as conn:
        existing = await conn.fetchrow(
            "SELECT * FROM open_enrollment_periods WHERE id = $1 AND company_id = $2",
            period_id, company_id,
        )
        if not existing:
            raise HTTPException(status_code=404, detail="Period not found")
        if existing["status"] != "open":
            raise HTTPException(status_code=409, detail=f"period is {existing['status']}, not open")
        period = await conn.fetchrow(
            "UPDATE open_enrollment_periods SET status = 'closed', closed_at = NOW(), updated_at = NOW() "
            "WHERE id = $1 RETURNING *",
            period_id,
        )
        await log_benefit_audit(
            conn, company_id, current_user.id, current_user.role, "oe_period", period_id, "closed",
        )
    return _serialize_period(period)


@router.get("/enrollment/periods/{period_id}/elections")
async def review_period_elections(
    period_id: UUID,
    current_user: CurrentUser = Depends(require_admin_or_client),
):
    company_id = await _require_company(current_user)
    async with get_connection() as conn:
        period = await conn.fetchrow(
            "SELECT id FROM open_enrollment_periods WHERE id = $1 AND company_id = $2",
            period_id, company_id,
        )
        if not period:
            raise HTTPException(status_code=404, detail="Period not found")

        elections = await conn.fetch(
            """
            SELECT el.*, (e.first_name || ' ' || e.last_name) AS employee_name,
                   p.name AS plan_name, t.coverage_tier
            FROM benefit_elections el
            JOIN employees e ON e.id = el.employee_id
            LEFT JOIN benefit_plans p ON p.id = el.plan_id
            LEFT JOIN benefit_plan_tiers t ON t.id = el.tier_id
            WHERE el.open_enrollment_period_id = $1
            ORDER BY employee_name, el.plan_type
            """,
            period_id,
        )
        counts = await conn.fetch(
            "SELECT status, COUNT(*) AS n FROM benefit_elections WHERE open_enrollment_period_id = $1 GROUP BY status",
            period_id,
        )
        not_submitted = await conn.fetch(
            """
            SELECT e.id, (e.first_name || ' ' || e.last_name) AS employee_name
            FROM employees e
            WHERE e.org_id = $1
              AND e.employment_status NOT IN ('terminated', 'offboarded')
              AND e.id NOT IN (
                  SELECT employee_id FROM benefit_elections
                  WHERE open_enrollment_period_id = $2 AND status IN ('submitted', 'approved')
              )
            ORDER BY employee_name
            """,
            company_id, period_id,
        )
    return {
        "elections": [_serialize_election(r) for r in elections],
        "status_counts": {r["status"]: r["n"] for r in counts},
        "not_submitted": [{"employee_id": str(r["id"]), "employee_name": r["employee_name"]} for r in not_submitted],
    }


# ---------------------------------------------------------------------------
# Election decisions
# ---------------------------------------------------------------------------

async def _load_election_for_decision(conn, election_id: UUID, company_id: UUID):
    election = await conn.fetchrow(
        "SELECT * FROM benefit_elections WHERE id = $1 AND company_id = $2", election_id, company_id,
    )
    if not election:
        raise HTTPException(status_code=404, detail="Election not found")
    if election["status"] != "submitted":
        raise HTTPException(status_code=409, detail=f"election is {election['status']}, not submitted")
    return election


@router.post("/enrollment/elections/{election_id}/approve")
async def approve_election(
    election_id: UUID,
    payload: DecisionInput,
    current_user: CurrentUser = Depends(require_admin_or_client),
):
    company_id = await _require_company(current_user)
    async with get_connection() as conn:
        election = await _load_election_for_decision(conn, election_id, company_id)

        effective_date = None
        if election["open_enrollment_period_id"]:
            period = await conn.fetchrow(
                "SELECT plan_year_start, ends_on FROM open_enrollment_periods WHERE id = $1",
                election["open_enrollment_period_id"],
            )
            effective_date = period["plan_year_start"] or period["ends_on"]
        elif election["life_event_id"]:
            life_event = await conn.fetchrow(
                "SELECT event_date FROM life_event_changes WHERE id = $1", election["life_event_id"],
            )
            effective_date = life_event["event_date"]

        updated = await conn.fetchrow(
            """
            UPDATE benefit_elections
            SET status = 'approved', decided_at = NOW(), decided_by = $1,
                decision_note = $2, effective_date = $3, updated_at = NOW()
            WHERE id = $4
            RETURNING *
            """,
            current_user.id, payload.note, effective_date, election_id,
        )
        await log_benefit_audit(
            conn, company_id, current_user.id, current_user.role,
            "election", election_id, "approved", {"note": payload.note},
        )
    return _serialize_election(updated)


@router.post("/enrollment/elections/{election_id}/reject")
async def reject_election(
    election_id: UUID,
    payload: DecisionInput,
    current_user: CurrentUser = Depends(require_admin_or_client),
):
    company_id = await _require_company(current_user)
    async with get_connection() as conn:
        await _load_election_for_decision(conn, election_id, company_id)
        updated = await conn.fetchrow(
            """
            UPDATE benefit_elections
            SET status = 'rejected', decided_at = NOW(), decided_by = $1,
                decision_note = $2, updated_at = NOW()
            WHERE id = $3
            RETURNING *
            """,
            current_user.id, payload.note, election_id,
        )
        await log_benefit_audit(
            conn, company_id, current_user.id, current_user.role,
            "election", election_id, "rejected", {"note": payload.note},
        )
    return _serialize_election(updated)


# ---------------------------------------------------------------------------
# Life events
# ---------------------------------------------------------------------------

@router.get("/enrollment/life-events")
async def list_life_events(
    status: str = "pending",
    current_user: CurrentUser = Depends(require_admin_or_client),
):
    company_id = await _require_company(current_user)
    async with get_connection() as conn:
        rows = await conn.fetch(
            """
            SELECT le.*, (e.first_name || ' ' || e.last_name) AS employee_name
            FROM life_event_changes le
            JOIN employees e ON e.id = le.employee_id
            WHERE le.company_id = $1 AND le.status = $2
            ORDER BY le.created_at DESC
            """,
            company_id, status,
        )
    return {"life_events": [_serialize_life_event(r) for r in rows]}


@router.post("/enrollment/life-events/{event_id}/approve")
async def approve_life_event(
    event_id: UUID,
    payload: DecisionInput,
    current_user: CurrentUser = Depends(require_admin_or_client),
):
    company_id = await _require_company(current_user)
    async with get_connection() as conn:
        event = await conn.fetchrow(
            "SELECT * FROM life_event_changes WHERE id = $1 AND company_id = $2", event_id, company_id,
        )
        if not event:
            raise HTTPException(status_code=404, detail="Life event not found")
        if event["status"] != "pending":
            raise HTTPException(status_code=409, detail=f"life event is {event['status']}, not pending")

        window_ends_on = life_event_window_ends_on(event["event_date"], date.today(), event["window_days"])
        updated = await conn.fetchrow(
            """
            UPDATE life_event_changes
            SET status = 'approved', window_ends_on = $1, reviewed_by = $2,
                reviewed_at = NOW(), review_note = $3, updated_at = NOW()
            WHERE id = $4
            RETURNING *
            """,
            window_ends_on, current_user.id, payload.note, event_id,
        )
        await log_benefit_audit(
            conn, company_id, current_user.id, current_user.role,
            "life_event", event_id, "approved", {"note": payload.note},
        )
    return _serialize_life_event(updated)


@router.post("/enrollment/life-events/{event_id}/deny")
async def deny_life_event(
    event_id: UUID,
    payload: DecisionInput,
    current_user: CurrentUser = Depends(require_admin_or_client),
):
    company_id = await _require_company(current_user)
    async with get_connection() as conn:
        event = await conn.fetchrow(
            "SELECT * FROM life_event_changes WHERE id = $1 AND company_id = $2", event_id, company_id,
        )
        if not event:
            raise HTTPException(status_code=404, detail="Life event not found")
        if event["status"] != "pending":
            raise HTTPException(status_code=409, detail=f"life event is {event['status']}, not pending")
        updated = await conn.fetchrow(
            """
            UPDATE life_event_changes
            SET status = 'denied', reviewed_by = $1, reviewed_at = NOW(), review_note = $2, updated_at = NOW()
            WHERE id = $3
            RETURNING *
            """,
            current_user.id, payload.note, event_id,
        )
        await log_benefit_audit(
            conn, company_id, current_user.id, current_user.role,
            "life_event", event_id, "denied", {"note": payload.note},
        )
    return _serialize_life_event(updated)
