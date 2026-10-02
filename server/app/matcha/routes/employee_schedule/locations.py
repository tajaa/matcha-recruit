"""Stores, from the schedule screens (`/employee-schedule/locations*`).

A scheduling customer adds, repairs and staffs a store without leaving the
schedule. Nothing here is a second location model: creating and editing
delegate to the compliance location service, which is the one path that gives
a store its timezone and jurisdiction — the two things
`schedule_location_readiness` needs before a week can publish.

`GET /locations/{id}/readiness` lives in shifts.py; the per-store scheduling
rules (hours, week start, leads) live in location_profile.py.
"""

import logging
from uuid import UUID

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException

from app.core.feature_flags import get_company_features
from app.core.models.compliance import LocationCreate, LocationUpdate
from app.core.services.compliance_service import (
    _get_or_create_jurisdiction,
    create_location,
    run_compliance_check_background,
    update_location,
)
from app.core.services.redis_cache import check_rate_limit
from app.database import get_connection
from ...dependencies import require_admin_or_client
from ...models.scheduling.employee_schedule import (
    ScheduleStoreAssignEmployees,
    ScheduleStoreCreate,
    ScheduleStoreUpdate,
)
from ...services.scheduling.schedule_assistant_session import assert_manager_location
from ...services.scheduling.schedule_location_readiness import (
    get_schedule_location_readiness,
    readiness_message,
)
from ._shared import require_company_id

logger = logging.getLogger(__name__)

router = APIRouter()


async def _project_store_compliance(location_id: UUID, company_id: UUID) -> None:
    """Copy what the shared catalog already holds onto a repaired store.

    Projection only (no research, no catalog refresh): the store is already
    publishable by the time this runs, so it must never spend a model call.
    """
    try:
        await run_compliance_check_background(
            location_id,
            company_id,
            check_type="proactive",
            allow_live_research=False,
            allow_repository_refresh=False,
        )
    except Exception:
        logger.exception("Could not project compliance for store %s", location_id)


async def _store_payload(conn, company_id: UUID, location_id: UUID) -> dict:
    row = await conn.fetchrow(
        """SELECT id, name, address, city, state, zipcode, is_active, timezone
             FROM business_locations WHERE id = $1 AND company_id = $2""",
        location_id,
        company_id,
    )
    if not row:
        raise HTTPException(status_code=404, detail="Location not found")
    readiness = await get_schedule_location_readiness(conn, company_id, location_id)
    return {
        "id": str(row["id"]),
        "name": row["name"],
        "address": row["address"],
        "city": row["city"],
        "state": row["state"],
        "zipcode": row["zipcode"],
        "is_active": row["is_active"],
        "timezone": row["timezone"],
        "ready_to_publish": readiness.ready_to_publish,
        "missing_fields": list(readiness.missing_fields),
        "message": readiness_message(readiness),
    }


@router.post("/locations", status_code=201)
async def create_schedule_store(
    body: ScheduleStoreCreate,
    background_tasks: BackgroundTasks,
    current_user=Depends(require_admin_or_client),
):
    company_id = await require_company_id(current_user)
    await check_rate_limit(str(company_id), "compliance_create_location", 30, 3600)

    # The same call Company settings makes, so a store is the same row whichever
    # screen created it: timezone inferred or chosen, jurisdiction linked,
    # catalog requirements cloned.
    location, has_complete_repository_coverage = await create_location(
        company_id,
        LocationCreate(
            name=body.name,
            address=body.address,
            city=body.city,
            state=body.state.upper(),
            zipcode=body.zipcode,
            timezone=body.timezone,
            timezone_source="manual" if body.timezone else "auto",
        ),
    )
    if not has_complete_repository_coverage:
        features = await get_company_features(company_id)
        background_tasks.add_task(
            run_compliance_check_background,
            location.id,
            company_id,
            allow_live_research=features.get("compliance", False),
        )

    async with get_connection() as conn:
        return await _store_payload(conn, company_id, location.id)


@router.patch("/locations/{location_id}")
async def update_schedule_store(
    location_id: UUID,
    body: ScheduleStoreUpdate,
    background_tasks: BackgroundTasks,
    current_user=Depends(require_admin_or_client),
):
    company_id = await require_company_id(current_user)
    patch = body.model_dump(exclude_unset=True, exclude_none=True)
    if "state" in patch:
        patch["state"] = patch["state"].upper()
    async with get_connection() as conn:
        await assert_manager_location(
            conn, company_id=company_id, user_id=current_user.id,
            actor_role=current_user.role, location_id=location_id,
        )

    if patch:
        updated = await update_location(location_id, company_id, LocationUpdate(**patch))
        if updated is None:
            raise HTTPException(status_code=404, detail="Location not found")

    async with get_connection() as conn:
        # `update_location` never links a jurisdiction, and a store created
        # before setup wrote one has none — which blocks publishing with
        # nothing in the product able to fix it. Link it here, once. A store
        # that already has one keeps it (re-linking on a city change is a
        # compliance decision, not a scheduling one).
        row = await conn.fetchrow(
            """SELECT city, state, county, zipcode, jurisdiction_id
                 FROM business_locations WHERE id = $1 AND company_id = $2""",
            location_id,
            company_id,
        )
        if row and row["jurisdiction_id"] is None and row["state"]:
            jurisdiction_id = await _get_or_create_jurisdiction(
                conn, row["city"] or "", row["state"], row["county"], row["zipcode"]
            )
            await conn.execute(
                """UPDATE business_locations SET jurisdiction_id = $1, updated_at = NOW()
                    WHERE id = $2 AND company_id = $3 AND jurisdiction_id IS NULL""",
                jurisdiction_id,
                location_id,
                company_id,
            )
            background_tasks.add_task(_project_store_compliance, location_id, company_id)
        return await _store_payload(conn, company_id, location_id)


@router.get("/locations/unassigned-employees")
async def list_unassigned_employees(current_user=Depends(require_admin_or_client)):
    """Active employees with no store — invisible to every schedule roster."""
    company_id = await require_company_id(current_user)
    async with get_connection() as conn:
        rows = await conn.fetch(
            """SELECT id, first_name, last_name, email, job_title, work_state
                 FROM employees
                WHERE org_id = $1
                  AND work_location_id IS NULL
                  AND termination_date IS NULL
                  AND COALESCE(employment_status, 'active') = 'active'
                ORDER BY last_name, first_name, email""",
            company_id,
        )
    return {"employees": [
        {
            "id": str(row["id"]),
            "first_name": row["first_name"],
            "last_name": row["last_name"],
            "email": row["email"],
            "job_title": row["job_title"],
            "work_state": row["work_state"],
        }
        for row in rows
    ]}


@router.post("/locations/{location_id}/employees")
async def assign_employees_to_store(
    location_id: UUID,
    body: ScheduleStoreAssignEmployees,
    current_user=Depends(require_admin_or_client),
):
    """Put employees who have no store at this one.

    Add-only. Someone already at another store is left alone and reported
    back: moving them can strand their upcoming shifts at the old store, so
    that stays a deliberate, one-person edit on the employee page.
    """
    company_id = await require_company_id(current_user)
    async with get_connection() as conn:
        await assert_manager_location(
            conn, company_id=company_id, user_id=current_user.id,
            actor_role=current_user.role, location_id=location_id,
        )
        assigned = await conn.fetch(
            """UPDATE employees
                  SET work_location_id = $1, updated_at = NOW()
                WHERE org_id = $2
                  AND id = ANY($3::uuid[])
                  AND work_location_id IS NULL
                  AND termination_date IS NULL
               RETURNING id""",
            location_id,
            company_id,
            body.employee_ids,
        )
    assigned_ids = {row["id"] for row in assigned}
    return {
        "assigned": [str(employee_id) for employee_id in body.employee_ids if employee_id in assigned_ids],
        "skipped": [str(employee_id) for employee_id in body.employee_ids if employee_id not in assigned_ids],
    }
