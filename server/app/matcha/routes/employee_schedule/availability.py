"""Admin view/edit of an employee's recurring weekly availability
(`/employee-schedule/availability/{employee_id}`). Portal counterpart —
the employee editing their own — lives at
routes/employee_portal/schedule.py's /me/schedule/availability."""

from uuid import UUID

import asyncpg
from fastapi import APIRouter, Depends, HTTPException

from app.database import get_connection
from ...dependencies import require_admin_or_client
from app.matcha.models.scheduling.employee_schedule import (
    AvailabilityReplace, EmployeeScheduleProfileUpdate,
    EmployeeSchedulingDetailsUpdate,
)
from ...services.scheduling.schedule_profiles import (
    fetch_availability_windows, fetch_schedule_profile, replace_availability_core,
    replace_employee_jobs_core, serialize_schedule_profile,
    upsert_schedule_profile,
)
from ...services.scheduling.shift_writes import log_audit
from ._shared import require_company_id, assert_employee_in_company

router = APIRouter()


@router.get("/availability/{employee_id}")
async def get_employee_availability(employee_id: UUID,
                                    current_user=Depends(require_admin_or_client)):
    company_id = await require_company_id(current_user)
    async with get_connection() as conn:
        await assert_employee_in_company(conn, company_id, employee_id)
        windows = await fetch_availability_windows(
            conn, company_id=company_id, employee_id=employee_id,
        )
        profile = await fetch_schedule_profile(
            conn, company_id=company_id, employee_id=employee_id,
        )
    return {"availability_state": profile.availability_state, "windows": windows}


@router.put("/availability/{employee_id}")
async def replace_employee_availability(employee_id: UUID, body: AvailabilityReplace,
                                        current_user=Depends(require_admin_or_client)):
    """Full replacement; omitted state preserves legacy empty=always behavior."""
    company_id = await require_company_id(current_user)
    async with get_connection() as conn:
        await assert_employee_in_company(conn, company_id, employee_id)
        async with conn.transaction():
            result = await replace_availability_core(
                conn, company_id=company_id, employee_id=employee_id,
                availability_state=body.availability_state, windows=body.windows,
                actor_user_id=current_user.id, actor_kind="admin",
            )
    return {"saved": result["saved"], "availability_state": result["state"]}


@router.get("/profiles/{employee_id}")
async def get_employee_schedule_profile(
    employee_id: UUID, current_user=Depends(require_admin_or_client),
):
    company_id = await require_company_id(current_user)
    async with get_connection() as conn:
        await assert_employee_in_company(conn, company_id, employee_id)
        profile = await fetch_schedule_profile(
            conn, company_id=company_id, employee_id=employee_id,
        )
    return serialize_schedule_profile(profile)


@router.put("/profiles/{employee_id}")
async def update_employee_schedule_profile(
    employee_id: UUID, body: EmployeeScheduleProfileUpdate,
    current_user=Depends(require_admin_or_client),
):
    company_id = await require_company_id(current_user)
    patch = body.model_dump(exclude_unset=True)
    async with get_connection() as conn:
        await assert_employee_in_company(conn, company_id, employee_id)
        try:
            async with conn.transaction():
                profile = await upsert_schedule_profile(
                    conn, company_id=company_id, employee_id=employee_id,
                    values=patch, actor_user_id=current_user.id,
                )
                await log_audit(
                    conn, company_id, "employee_schedule_profile", employee_id,
                    current_user.id, "employee_schedule_profile.update",
                    {"fields": sorted(patch)},
                )
        except ValueError as exc:
            raise HTTPException(status_code=422, detail=str(exc)) from exc
    return serialize_schedule_profile(profile)


@router.put("/profiles/{employee_id}/details")
async def update_employee_scheduling_details(
    employee_id: UUID, body: EmployeeSchedulingDetailsUpdate,
    current_user=Depends(require_admin_or_client),
):
    """Atomically save the employee profile panel's three scheduling sections."""
    company_id = await require_company_id(current_user)
    profile_patch = body.profile.model_dump(exclude_unset=True)
    async with get_connection() as conn:
        await assert_employee_in_company(conn, company_id, employee_id)
        try:
            async with conn.transaction():
                assignments = None
                if body.jobs is not None:
                    assignments = await replace_employee_jobs_core(
                        conn, company_id=company_id, employee_id=employee_id,
                        assignments=body.jobs.assignments,
                        actor_user_id=current_user.id,
                    )
                availability = await replace_availability_core(
                    conn, company_id=company_id, employee_id=employee_id,
                    availability_state=body.availability.availability_state,
                    windows=body.availability.windows,
                    actor_user_id=current_user.id, actor_kind="admin",
                )
                profile = await upsert_schedule_profile(
                    conn, company_id=company_id, employee_id=employee_id,
                    values=profile_patch, actor_user_id=current_user.id,
                )
                await log_audit(
                    conn, company_id, "employee_schedule_profile", employee_id,
                    current_user.id, "employee_schedule_profile.update",
                    {"fields": sorted(profile_patch), "source": "details"},
                )
        except ValueError as exc:
            raise HTTPException(status_code=422, detail=str(exc)) from exc
        except asyncpg.UniqueViolationError as exc:
            raise HTTPException(
                status_code=409,
                detail="Employee already has another active primary job",
            ) from exc
    return {
        "employee_id": str(employee_id),
        "assignments": assignments,
        "availability_state": availability["state"],
        "saved_windows": availability["saved"],
        "profile": serialize_schedule_profile(profile),
    }
