"""Per-location scheduling setup (`/employee-schedule/locations/{id}/profile`).

The hand-editable twin of what Huume interviews for on the schedule-assistant
surface — same table, same service, so a manager can correct in the editor
whatever the chat saved (and vice versa).

Authorization is `assert_manager_location`, the same location check the
schedule assistant session uses: role alone is not enough, because a
location-scoped manager must not read or rewrite another store's setup.
"""

from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException

from app.database import get_connection
from ...dependencies import require_admin_or_client
from ...models.scheduling.employee_schedule import LocationScheduleProfileUpdate
from ...services.scheduling.location_profile import (
    UNSET, bundle_leader_jobs, load_profile_bundle, missing_fields, upsert_location_profile,
)
from ...services.scheduling.schedule_assistant_session import assert_manager_location
from ...services.scheduling.week_template_writes import JobUnavailable, assert_job_available
from ._shared import require_company_id

router = APIRouter()


def _serialize(bundle: dict, *, location_id: UUID) -> dict:
    profile = bundle.get("profile") or {}
    template = bundle.get("template")
    missing = missing_fields(bundle)
    leader_jobs = bundle_leader_jobs(bundle)
    return {
        "location_id": str(location_id),
        # A never-configured location and one saved as Sunday-start with no
        # buffers used to be byte-identical on the wire, so the editor could
        # not tell "not set up" from "set up plainly" without guessing.
        "profile_exists": bundle.get("profile") is not None,
        "week_rules": {"established": not missing, "missing": missing},
        "operating_hours": profile.get("operating_hours") or {},
        "default_week_template_id": (
            str(profile["default_week_template_id"]) if profile.get("default_week_template_id") else None
        ),
        # The rule is the set: any ONE of these jobs on shift is lead coverage.
        # The scalar pair is its first entry, kept for readers that predate it.
        "leader_job_ids": [job["id"] for job in leader_jobs],
        "leader_job_names": [job["name"] for job in leader_jobs],
        "leader_job_id": leader_jobs[0]["id"] if leader_jobs else None,
        "leader_job_name": leader_jobs[0]["name"] if leader_jobs else None,
        "leader_required": profile.get("leader_required"),
        "notes": profile.get("notes"),
        # Sunday unless this location says otherwise — the default every
        # week-start computation in the codebase already assumes.
        "week_start_weekday": int(profile.get("week_start_weekday") or 0),
        "open_buffer_minutes": int(profile.get("open_buffer_minutes") or 0),
        "close_buffer_minutes": int(profile.get("close_buffer_minutes") or 0),
        "template": template,
    }


@router.get("/locations/{location_id}/profile")
async def get_location_schedule_profile(
    location_id: UUID, current_user=Depends(require_admin_or_client),
):
    company_id = await require_company_id(current_user)
    async with get_connection() as conn:
        await assert_manager_location(
            conn, company_id=company_id, user_id=current_user.id,
            actor_role=current_user.role, location_id=location_id,
        )
        bundle = await load_profile_bundle(conn, company_id=company_id, location_id=location_id)
    return _serialize(bundle, location_id=location_id)


@router.put("/locations/{location_id}/profile")
async def update_location_schedule_profile(
    location_id: UUID, body: LocationScheduleProfileUpdate,
    current_user=Depends(require_admin_or_client),
):
    company_id = await require_company_id(current_user)
    patch = body.model_dump(exclude_unset=True)
    async with get_connection() as conn:
        await assert_manager_location(
            conn, company_id=company_id, user_id=current_user.id,
            actor_role=current_user.role, location_id=location_id,
        )
        # Every leader job has to be usable at this store — the set, or the
        # one-element legacy spelling when that is all the caller sent.
        leader_jobs = patch.get("leader_job_ids")
        if leader_jobs is None and patch.get("leader_job_id") is not None:
            leader_jobs = [patch["leader_job_id"]]
        for job_id in leader_jobs or []:
            try:
                await assert_job_available(conn, company_id, job_id, location_id=location_id)
            except JobUnavailable as exc:
                raise HTTPException(status_code=422, detail=str(exc)) from exc
        if patch.get("default_week_template_id") is not None:
            # Must be this location's own template. A company-wide one
            # (location_id IS NULL) shows in every store's picker and would
            # make one store's default silently follow another's edits.
            owned = await conn.fetchval(
                "SELECT 1 FROM schedule_week_templates "
                "WHERE id = $1 AND company_id = $2 AND location_id = $3",
                patch["default_week_template_id"], company_id, location_id,
            )
            if not owned:
                raise HTTPException(
                    status_code=422,
                    detail="That week template does not belong to this location",
                )
        async with conn.transaction():
            try:
                await upsert_location_profile(
                    conn, company_id=company_id, location_id=location_id,
                    actor_user_id=current_user.id,
                    operating_hours=(
                        {
                            day: ({"open": window["open"], "close": window["close"]} if window else None)
                            for day, window in (patch["operating_hours"] or {}).items()
                        }
                        if "operating_hours" in patch else UNSET
                    ),
                    default_week_template_id=patch.get("default_week_template_id", UNSET),
                    leader_job_id=patch.get("leader_job_id", UNSET),
                    leader_job_ids=patch.get("leader_job_ids", UNSET),
                    leader_required=patch.get("leader_required", UNSET),
                    notes=patch.get("notes", UNSET),
                    week_start_weekday=patch.get("week_start_weekday", UNSET),
                    open_buffer_minutes=patch.get("open_buffer_minutes", UNSET),
                    close_buffer_minutes=patch.get("close_buffer_minutes", UNSET),
                )
            except ValueError as exc:
                raise HTTPException(status_code=422, detail=str(exc)) from exc
        bundle = await load_profile_bundle(conn, company_id=company_id, location_id=location_id)
    return _serialize(bundle, location_id=location_id)
