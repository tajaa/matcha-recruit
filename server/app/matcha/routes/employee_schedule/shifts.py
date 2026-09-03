"""Shift CRUD, publish, weekly view + roster (`/employee-schedule`).

Owns the package `router`; templates/assignments/requests attach their own
routers in __init__.py. Business-facing (admin/client), tenant-isolated.
"""

import logging
from datetime import date, datetime, timezone
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query

from app.database import get_connection
from app.core.feature_flags import get_company_features
from ...dependencies import require_admin_or_client
from app.matcha.models.scheduling.employee_schedule import (
    ShiftCreate, ShiftUpdate, PublishRange, DuplicateShift,
)
from ...services.scheduling.schedule_rules import (
    build_patch, summarize_shifts as _summarize, week_bounds as _week_bounds,
)
from ...services.scheduling import schedule_compliance, schedule_eligibility, schedule_intelligence
from ...services.scheduling.shift_writes import create_shift_core
from ...services.scheduling.schedule_location_readiness import (
    assert_schedule_location_ready_to_publish,
    get_schedule_location_readiness,
)
from ...services.scheduling.schedule_guidance import refresh_assignment_break_guidance
from ...services.scheduling.schedule_breaks import minimum_meal_break_minutes
from ...services.scheduling.schedule_guidance import (
    resolve_shift_break_plan, resolve_shift_break_plans,
)
from ._shared import (
    require_company_id, log_audit, fetch_shifts, fetch_roster, fetch_shift_by_id,
    assert_employee_in_company, assert_employee_schedulable_at, assert_location_in_company,
    assert_job_in_company,
    find_conflicts, raise_conflict, shift_snapshot,
    fetch_availability, availability_violations, log_availability_override, raise_outside_availability,
    shift_window_on_date, check_job_qualification, raise_not_qualified,
    reconcile_warning_events,
    lock_scheduling_employees,
)
from ._compliance import (
    check_shift_compliance, raise_for_violations, _approved_db_rules,
    _fair_workweek_advisories,
)

logger = logging.getLogger(__name__)

router = APIRouter()


def _locked_break_write(
    *, requested: int, locked: int, existing: int, minimum: int,
    manual: bool, legacy_value: bool,
) -> int:
    """Resolve a break write after locking without losing a newer increase."""
    if manual:
        if locked != existing:
            raise HTTPException(
                status_code=409,
                detail={
                    "code": "shift_changed",
                    "message": "The shift changed while you were editing it. Reload and try again.",
                },
            )
        return requested
    if legacy_value and locked == existing:
        # A legacy API caller may still intentionally lower a compliant value.
        # It is only automatic when stale or racing a newer write.
        return max(requested, minimum)
    return max(requested, locked, minimum)


async def _resolve_break_plans_for_ids(
    conn, company_id: UUID, *, location_id: UUID | None,
    starts_at: datetime, ends_at: datetime,
    employee_ids: list[UUID | None],
):
    concrete_ids = [employee_id for employee_id in employee_ids if employee_id is not None]
    if concrete_ids:
        plans = await resolve_shift_break_plans(
            conn, company_id, location_id=location_id, starts_at=starts_at,
            ends_at=ends_at, employee_ids=concrete_ids,
        )
        return [plans[employee_id] for employee_id in concrete_ids]
    return [await resolve_shift_break_plan(
        conn, company_id, location_id=location_id,
        starts_at=starts_at, ends_at=ends_at,
    )]


async def _lock_and_assert_publish_assignments_eligible(
    conn,
    company_id: UUID,
    candidate_shifts: list[dict],
) -> dict[UUID, int]:
    """Lock assignees and reject publication if eligibility changed in draft."""
    if not candidate_shifts:
        return {}
    shifts_by_id = {shift["id"]: shift for shift in candidate_shifts}
    assignments = await conn.fetch(
        """
        SELECT shift_id, employee_id
        FROM schedule_shift_assignments
        WHERE shift_id = ANY($1::uuid[])
        ORDER BY shift_id, employee_id
        FOR UPDATE
        """,
        list(shifts_by_id),
    )
    assignments_by_shift: dict[UUID, list[UUID]] = {}
    for assignment in assignments:
        assignments_by_shift.setdefault(assignment["shift_id"], []).append(
            assignment["employee_id"]
        )
    effective_breaks: dict[UUID, int] = {}
    for shift in candidate_shifts:
        employee_ids = assignments_by_shift.get(shift["id"], [])
        plans = await _resolve_break_plans_for_ids(
            conn, company_id, location_id=shift["location_id"],
            starts_at=shift["starts_at"], ends_at=shift["ends_at"],
            employee_ids=employee_ids or [None],
        )
        generated_minimum = max(minimum_meal_break_minutes(plan) for plan in plans)
        effective_break = max(int(shift["break_minutes"] or 0), generated_minimum)
        effective_breaks[shift["id"]] = effective_break
        if effective_break > int(shift["break_minutes"] or 0):
            await conn.execute(
                "UPDATE schedule_shifts SET break_minutes=$1, updated_at=NOW() "
                "WHERE id=$2 AND company_id=$3",
                effective_break, shift["id"], company_id,
            )
    for assignment in assignments:
        shift = shifts_by_id[assignment["shift_id"]]
        violations = await check_shift_compliance(
            conn, company_id, location_id=shift["location_id"],
            job_id=shift.get("job_id"), starts_at=shift["starts_at"],
            ends_at=shift["ends_at"], break_minutes=effective_breaks[shift["id"]],
            employee_id=assignment["employee_id"], exclude_shift_id=shift["id"],
            shift_kind=shift["kind"],
            training_requirement_id=shift["training_requirement_id"],
        )
        eligibility_blocks = [
            violation for violation in violations
            if violation.get("check") == "schedule_eligibility"
            and violation.get("severity") == "block"
        ]
        raise_for_violations(eligibility_blocks, force=False)
    return effective_breaks


async def _duplicate_assignment_block(
    conn,
    company_id: UUID,
    *,
    employee_id: UUID,
    location_id: UUID | None,
    job_id: UUID | None,
    starts_at: datetime,
    ends_at: datetime,
    break_minutes: int,
    shift_kind: str,
    training_requirement_id: UUID | None,
) -> dict | None:
    """Return the live hard block for one duplicated assignment, if any."""
    violations = await check_shift_compliance(
        conn, company_id, location_id=location_id, job_id=job_id,
        starts_at=starts_at, ends_at=ends_at, break_minutes=break_minutes,
        employee_id=employee_id, shift_kind=shift_kind,
        training_requirement_id=training_requirement_id,
    )
    return next((violation for violation in violations if violation.get("severity") == "block"), None)


@router.get("/roster")
async def get_roster(
    location: UUID = Query(..., description="Business location to scope the roster to"),
    current_user=Depends(require_admin_or_client),
):
    company_id = await require_company_id(current_user)
    async with get_connection() as conn:
        await assert_location_in_company(conn, company_id, location)
        return {"employees": await fetch_roster(conn, company_id, location_id=location)}


@router.get("/shifts")
async def list_shifts(
    start: datetime = Query(...),
    end: datetime = Query(...),
    status: str | None = Query(None),
    location: UUID | None = Query(None),
    current_user=Depends(require_admin_or_client),
):
    if end <= start:
        raise HTTPException(status_code=422, detail="end must be after start")
    company_id = await require_company_id(current_user)
    async with get_connection() as conn:
        await assert_location_in_company(conn, company_id, location)
        shifts = await fetch_shifts(conn, company_id, start, end, status=status, location_id=location)
    return {"shifts": shifts, "summary": _summarize(shifts)}


@router.get("/shifts/{shift_id}")
async def get_shift(shift_id: UUID, current_user=Depends(require_admin_or_client)):
    """One shift by id, tenant-scoped. Exists so a `?shift=` deep link that
    carries no location (the Huume `[[shift:…]]` pill token predates location
    scoping) can resolve which location to scope the page to."""
    company_id = await require_company_id(current_user)
    async with get_connection() as conn:
        shift = await fetch_shift_by_id(conn, company_id, shift_id)
    if shift is None:
        raise HTTPException(status_code=404, detail="Shift not found")
    return shift


@router.get("/week")
async def get_week(
    start: date = Query(..., description="Week start date (YYYY-MM-DD)"),
    location: UUID = Query(..., description="Business location to scope this week's shifts to"),
    current_user=Depends(require_admin_or_client),
):
    """Weekly grid: the 7 days from `start` for ONE location, plus the roster
    for the picker. `location` is mandatory — callers fetch the location list
    via GET /locations first and never see cross-location shift data in one
    response."""
    company_id = await require_company_id(current_user)
    lo, hi = _week_bounds(start)
    async with get_connection() as conn:
        await assert_location_in_company(conn, company_id, location)
        # starts_within: the grid buckets by start date and publish_range only
        # publishes shifts starting in the window — matching on overlap here
        # would count a shift in the summary that no day column renders and no
        # publish touches.
        shifts = await fetch_shifts(conn, company_id, lo, hi, location_id=location, starts_within=True)
        roster = await fetch_roster(conn, company_id, location_id=location)

        features = await get_company_features(company_id, conn=conn)
        training_enabled = bool(features.get("training"))
        credential_templates_enabled = bool(features.get("credential_templates"))
        roster_flags = None
        if (training_enabled or credential_templates_enabled) and roster:
            emp_uuids = [UUID(e["id"]) for e in roster]
            lapses = await schedule_intelligence.fetch_lapse_items(
                conn, company_id, emp_uuids,
                credential_templates_enabled=credential_templates_enabled,
                training_enabled=training_enabled,
            )
            today = datetime.now(timezone.utc).date()
            roster_flags = {
                emp_id: {
                    "overdue_training": sum(
                        1 for it in items if it["source"] == "training" and it["date"] and it["date"] < today
                    ),
                    "lapsed_credentials": sum(
                        1 for it in items if it["source"] != "training" and it["date"] and it["date"] < today
                    ),
                    "warnings": [
                        (
                            f"Overdue training: {it['item'] or 'Training'} "
                            f"(due {it['date'].isoformat()})"
                            if it["source"] == "training"
                            else f"Lapsed credential: {it['item'] or 'Credential'} "
                            f"(due {it['date'].isoformat()})"
                        )
                        for it in items if it["date"] and it["date"] < today
                    ],
                }
                for emp_id, items in lapses.items()
            }
            if credential_templates_enabled:
                eligibility_flags = await schedule_eligibility.schedule_eligibility_roster_flags(
                    conn, company_id, emp_uuids, as_of=today,
                )
                for emp_id, flags in eligibility_flags.items():
                    entry = roster_flags.setdefault(emp_id, {
                        "overdue_training": 0,
                        "lapsed_credentials": 0,
                        "warnings": [],
                        "credential_expirations": [],
                    })
                    blocks = flags["blocking_credentials"]
                    warnings = flags["credential_warnings"]
                    entry["blocking_credentials"] = blocks
                    entry["credential_warnings"] = warnings
                    entry["credential_expirations"] = flags["credential_expirations"]
                    entry["warnings"].extend(warnings)
    return {
        "week_start": start.isoformat(),
        "location_id": str(location),
        "shifts": shifts,
        "roster": roster,
        "roster_flags": roster_flags,
        "summary": _summarize(shifts),
    }


@router.get("/compliance/location/{location_id}")
async def location_scheduling_compliance(
    location_id: UUID, current_user=Depends(require_admin_or_client),
):
    """Passive "scheduling law for this location" panel: the curated thresholds
    we deterministically check + the codified catalog statutes behind them."""
    company_id = await require_company_id(current_user)
    async with get_connection() as conn:
        await assert_location_in_company(conn, company_id, location_id)
        loc = await conn.fetchrow(
            "SELECT state FROM business_locations WHERE id = $1 AND company_id = $2",
            location_id, company_id,
        )
        state = loc["state"] if loc else None
        statutes = await schedule_compliance.get_schedule_statutes(
            location_id, company_id, conn=conn,
        )
        db_rules = None
        if state and not schedule_compliance.is_curated_state(state):
            db_rules, _fetch_failed = await _approved_db_rules(conn, state.strip().upper())
    return {
        "state": state,
        "rules": schedule_compliance.rules_summary(state, db_rules),
        "statutes": statutes,
    }


@router.get("/locations/{location_id}/readiness")
async def schedule_location_readiness(
    location_id: UUID, current_user=Depends(require_admin_or_client),
):
    """Expose the exact prerequisites that block schedule publication."""
    company_id = await require_company_id(current_user)
    async with get_connection() as conn:
        await assert_location_in_company(conn, company_id, location_id)
        readiness = await get_schedule_location_readiness(conn, company_id, location_id)
    return {
        "location_id": str(location_id),
        "ready_to_publish": readiness.ready_to_publish,
        "missing_fields": list(readiness.missing_fields),
        "jurisdiction_id": str(readiness.jurisdiction_id) if readiness.jurisdiction_id else None,
        "timezone": readiness.timezone,
        "industry_code": readiness.industry_code,
    }


@router.post("/shifts")
async def create_shift(body: ShiftCreate,
                       force: bool = Query(False, description="Assign despite overlapping shifts"),
                       current_user=Depends(require_admin_or_client)):
    company_id = await require_company_id(current_user)
    async with get_connection() as conn:
        await assert_location_in_company(conn, company_id, body.location_id)
        await assert_job_in_company(
            conn, company_id, body.job_id, location_id=body.location_id,
        )
        plan_employee_ids = list(dict.fromkeys(body.employee_ids)) or [None]
        break_plans = await _resolve_break_plans_for_ids(
            conn, company_id, location_id=body.location_id,
            starts_at=body.starts_at, ends_at=body.ends_at,
            employee_ids=plan_employee_ids,
        )
        generated_minimum = max(
            minimum_meal_break_minutes(plan) for plan in break_plans
        )
        if body.break_mode == "manual" and body.break_minutes < generated_minimum:
            raise HTTPException(
                status_code=422,
                detail={
                    "code": "break_minimum_required",
                    "minimum_break_minutes": generated_minimum,
                    "message": (
                        f"Planned break cannot be below the generated "
                        f"{generated_minimum}-minute legal minimum."
                    ),
                },
            )
        effective_break = max(body.break_minutes, generated_minimum)
        training_requirement = None
        if body.kind == "training":
            features = await get_company_features(company_id, conn=conn)
            if not features.get("training"):
                raise HTTPException(
                    status_code=403, detail="Training feature required for training shifts"
                )
            training_requirement = await conn.fetchrow(
                "SELECT id, title, training_type, frequency_months "
                "FROM training_requirements WHERE id = $1 AND company_id = $2",
                body.training_requirement_id, company_id,
            )
            if not training_requirement:
                raise HTTPException(status_code=404, detail="Training requirement not found")

        # Hoist the feature lookup + batch the lapse-item fetch over the whole
        # employee list — otherwise check_shift_compliance re-resolves company
        # features and re-queries training/credential lapses once per employee.
        lapse_map: dict = {}
        if body.employee_ids:
            company_features = await get_company_features(company_id, conn=conn)
            lapse_map = await schedule_intelligence.fetch_lapse_items(
                conn, company_id, list(dict.fromkeys(body.employee_ids)),
                credential_templates_enabled=bool(company_features.get("credential_templates")),
                training_enabled=bool(company_features.get("training")),
            )

        avail_map: dict = {}
        if body.employee_ids:
            avail_map = await fetch_availability(
                conn, company_id, list(dict.fromkeys(body.employee_ids)))

        forced: dict[str, list[dict]] = {}
        availability_overrides: dict[str, list[dict]] = {}
        qualification_overrides: dict[str, dict] = {}
        for emp_id in body.employee_ids:
            await assert_employee_in_company(conn, company_id, emp_id)
            await assert_employee_schedulable_at(conn, company_id, emp_id, body.location_id)
            avail = availability_violations(
                avail_map.get(emp_id, {}), body.starts_at, body.ends_at,
            )
            unqualified = await check_job_qualification(
                conn, company_id, emp_id, body.job_id, starts_at=body.starts_at,
            )
            if not force:
                conflicts = await find_conflicts(
                    conn, company_id, emp_id, body.starts_at, body.ends_at,
                )
                if conflicts:
                    raise_conflict(emp_id, conflicts)
                if avail:
                    raise_outside_availability(emp_id, avail)
                if unqualified:
                    raise_not_qualified(unqualified)
            if avail:
                availability_overrides[str(emp_id)] = avail
            if unqualified:
                qualification_overrides[str(emp_id)] = unqualified
            violations = await check_shift_compliance(
                conn, company_id, location_id=body.location_id, job_id=body.job_id,
                starts_at=body.starts_at, ends_at=body.ends_at,
                break_minutes=effective_break, employee_id=emp_id,
                shift_kind=body.kind, training_requirement_id=body.training_requirement_id,
                lapse_items=lapse_map.get(str(emp_id), []),
            )
            raise_for_violations(violations, force=force)
            if violations:
                forced[str(emp_id)] = violations
        if not body.employee_ids:
            # Open shift (no assignee yet): only shift-intrinsic checks run.
            raise_for_violations(
                await check_shift_compliance(
                    conn, company_id, location_id=body.location_id, job_id=body.job_id,
                    starts_at=body.starts_at, ends_at=body.ends_at,
                    break_minutes=effective_break,
                ),
                force=force,
            )
        async with conn.transaction():
            # Re-resolve under the write transaction so a concurrent job edit
            # cannot persist a stale/cross-location role label.
            job = await assert_job_in_company(
                conn, company_id, body.job_id, location_id=body.location_id,
            )
            # Re-check conflicts under transaction-scoped employee locks in a
            # stable order.  The earlier pass provides detailed validation;
            # this pass closes the gap between that snapshot and insertion.
            if not force:
                for employee_id in sorted(set(body.employee_ids)):
                    conflicts = await find_conflicts(
                        conn, company_id, employee_id,
                        body.starts_at, body.ends_at,
                    )
                    if conflicts:
                        raise_conflict(employee_id, conflicts)
            shift_id = await create_shift_core(
                conn, company_id,
                location_id=body.location_id, role=job["name"], department=body.department,
                starts_at=body.starts_at, ends_at=body.ends_at,
                break_minutes=effective_break, required_staff=body.required_staff,
                color=body.color, notes=body.notes, kind=body.kind, job_id=body.job_id,
                training_requirement=dict(training_requirement) if training_requirement else None,
                training_requirement_id=body.training_requirement_id,
                employee_ids=body.employee_ids, created_by=current_user.id,
                status="draft",
            )
            if forced:
                await log_audit(conn, company_id, "shift", shift_id, current_user.id,
                                "shift.compliance_override", {"forced": forced})
            for emp_id, avail in availability_overrides.items():
                await log_availability_override(
                    conn, company_id, shift_id, current_user.id, UUID(emp_id), avail,
                )
            for emp_id, detail in qualification_overrides.items():
                await log_audit(conn, company_id, "assignment", shift_id, current_user.id,
                                "assignment.qualification_override",
                                {"employee_id": emp_id, **detail})
        await reconcile_warning_events(conn, company_id, [shift_id])
        return await fetch_shift_by_id(conn, company_id, shift_id)


@router.post("/shifts/{shift_id}/duplicate")
async def duplicate_shift(shift_id: UUID, body: DuplicateShift,
                          current_user=Depends(require_admin_or_client)):
    """Copy a shift onto other dates as drafts. Assignments are copied when
    include_assignments; an assignee with a conflict or outside availability
    on a target date is dropped for that copy and reported in `dropped` —
    the bulk-create convention (same as template generation and the @huume
    chat flow): never a per-date 409, warnings/drops surface in the body.
    `compliance_warnings` is computed for the first target date only, as a
    representative sample — weekday-dependent rules may differ per date."""
    company_id = await require_company_id(current_user)
    async with get_connection() as conn:
        src = await conn.fetchrow(
            "SELECT * FROM schedule_shifts WHERE id = $1 AND company_id = $2",
            shift_id, company_id,
        )
        if not src:
            raise HTTPException(status_code=404, detail="Shift not found")
        if src["status"] == "cancelled":
            raise HTTPException(status_code=409, detail="Cannot duplicate a cancelled shift")
        for d in body.target_dates:
            if d == src["starts_at"].date():
                raise HTTPException(
                    status_code=422, detail="Target date equals the source shift's date")

        employee_ids: list[UUID] = []
        names: dict[str, str] = {}
        if body.include_assignments:
            rows = await conn.fetch(
                "SELECT a.employee_id, e.first_name, e.last_name "
                "FROM schedule_shift_assignments a JOIN employees e ON e.id = a.employee_id "
                "WHERE a.shift_id = $1",
                shift_id,
            )
            employee_ids = [r["employee_id"] for r in rows]
            names = {str(r["employee_id"]): f"{r['first_name']} {r['last_name']}".strip() for r in rows}
        avail_map = await fetch_availability(conn, company_id, employee_ids)

        # kind='training' needs the requirement row for create_shift_core's hooks
        training_requirement = None
        if src["training_requirement_id"]:
            tr = await conn.fetchrow(
                "SELECT id, title, training_type, frequency_months "
                "FROM training_requirements WHERE id = $1 AND company_id = $2",
                src["training_requirement_id"], company_id,
            )
            training_requirement = dict(tr) if tr else None

        first_start, first_end = shift_window_on_date(
            src["starts_at"], src["ends_at"], body.target_dates[0])
        compliance_warnings = await check_shift_compliance(
            conn, company_id, location_id=src["location_id"], job_id=src["job_id"],
            starts_at=first_start, ends_at=first_end,
            break_minutes=src["break_minutes"] or 0, shift_kind=src["kind"],
        )

        dropped: list[dict] = []
        created_ids: list[UUID] = []
        async with conn.transaction():
            await lock_scheduling_employees(conn, company_id, employee_ids)
            for d in body.target_dates:
                new_start, new_end = shift_window_on_date(src["starts_at"], src["ends_at"], d)
                surviving: list[UUID] = []
                for eid in employee_ids:
                    conflicts = await find_conflicts(conn, company_id, eid, new_start, new_end)
                    avail = availability_violations(avail_map.get(eid, {}), new_start, new_end)
                    unqualified = await check_job_qualification(
                        conn, company_id, eid, src["job_id"], starts_at=new_start,
                    )
                    blocked = await _duplicate_assignment_block(
                        conn, company_id, employee_id=eid, location_id=src["location_id"], job_id=src["job_id"],
                        starts_at=new_start, ends_at=new_end,
                        break_minutes=src["break_minutes"] or 0, shift_kind=src["kind"],
                        training_requirement_id=src["training_requirement_id"],
                    )
                    if conflicts or avail or unqualified or blocked:
                        dropped.append({
                            "date": d.isoformat(), "employee_id": str(eid),
                            "name": names.get(str(eid), ""),
                            "reason": "outside their logged availability" if avail
                                      else "already scheduled during this time" if conflicts
                                      else unqualified["message"] if unqualified
                                      else blocked["message"],
                        })
                        continue
                    surviving.append(eid)
                new_id = await create_shift_core(
                    conn, company_id,
                    location_id=src["location_id"], role=src["role"], department=src["department"],
                    starts_at=new_start, ends_at=new_end,
                    break_minutes=src["break_minutes"], required_staff=src["required_staff"],
                    color=src["color"], notes=src["notes"], kind=src["kind"], job_id=src["job_id"],
                    training_requirement=training_requirement,
                    training_requirement_id=src["training_requirement_id"],
                    employee_ids=surviving, created_by=current_user.id, status="draft",
                    audit_details={"source": "duplicate", "source_shift_id": str(shift_id)},
                )
                created_ids.append(new_id)
        await reconcile_warning_events(conn, company_id, created_ids)
        shifts = [await fetch_shift_by_id(conn, company_id, i) for i in created_ids]
    return {"created": len(created_ids), "shifts": shifts,
            "dropped": dropped, "compliance_warnings": compliance_warnings}


@router.put("/shifts/{shift_id}")
async def update_shift(shift_id: UUID, body: ShiftUpdate,
                       force: bool = Query(False, description="Retime despite overlapping shifts"),
                       current_user=Depends(require_admin_or_client)):
    """True PATCH: only the fields the caller sent are written, so an explicit
    null clears a nullable column (role, department, location, colour, notes).
    """
    company_id = await require_company_id(current_user)
    patch = body.model_dump(exclude_unset=True)
    break_mode = patch.pop("break_mode", None)
    legacy_break_value = break_mode is None and "break_minutes" in patch
    auto_break_requested = break_mode == "auto"
    if auto_break_requested:
        # Auto is an instruction, not a database column.  Ignore any value a
        # caller happened to serialize with it and preserve longer stored
        # breaks while enforcing the generated minimum below.
        patch.pop("break_minutes", None)
    break_was_explicit = break_mode == "manual"
    async with get_connection() as conn:
        existing = await conn.fetchrow(
            """
            SELECT starts_at, ends_at, status, published_at, break_minutes, location_id,
                   role, department, required_staff, color, notes,
                   kind, training_requirement_id, job_id, updated_at
            FROM schedule_shifts WHERE id = $1 AND company_id = $2
            """,
            shift_id, company_id,
        )
        if not existing:
            raise HTTPException(status_code=404, detail="Shift not found")
        if not patch and (not auto_break_requested or existing["location_id"] is None):
            return await fetch_shift_by_id(conn, company_id, shift_id)
        if "location_id" in patch:
            await assert_location_in_company(conn, company_id, patch["location_id"])
        if "job_id" in patch:
            await assert_job_in_company(conn, company_id, patch["job_id"])

        new_status = patch.get("status", existing["status"])
        publishing = new_status == "published" and existing["status"] != "published"
        # Cancelled is terminal for publication — POST /publish already refuses it
        # (`AND status <> 'cancelled'`), and a resurrected shift would reappear on
        # every assignee's portal. Reopening as a draft is the supported path.
        if existing["status"] == "cancelled" and new_status == "published":
            raise HTTPException(
                status_code=409,
                detail="Cannot publish a cancelled shift — reopen it as a draft first",
            )

        if new_status == "published":
            await assert_schedule_location_ready_to_publish(
                conn, company_id, patch.get("location_id", existing["location_id"]),
            )

        new_start = patch.get("starts_at") or existing["starts_at"]
        new_end = patch.get("ends_at") or existing["ends_at"]
        if new_end <= new_start:
            raise HTTPException(status_code=422, detail="ends_at must be after starts_at")

        # Retiming a staffed shift is an assignment path like any other: it can
        # double-book everyone already on it, so it takes the same guard + force.
        # A break/location edit is compliance-relevant too (meal-break, jurisdiction).
        retimed = new_start != existing["starts_at"] or new_end != existing["ends_at"]
        compliance_relevant = auto_break_requested or (
            retimed or "break_minutes" in patch or "location_id" in patch or "job_id" in patch
        )
        # Fair Workweek notice/clopening obligations attach to a POSTED shift's
        # timing changing, not to break/location edits alone — only pass the
        # event when the shift's start/end actually moved.
        fw_event = "retime" if retimed else None
        fw_shift_published = existing["published_at"] is not None
        forced: dict[str, list[dict]] = {}
        availability_overrides: dict[str, list[dict]] = {}
        qualification_overrides: dict[str, dict] = {}
        if compliance_relevant and new_status != "cancelled":
            new_location = patch.get("location_id", existing["location_id"])
            new_job_id = patch.get("job_id", existing["job_id"])
            assignees = await conn.fetch(
                "SELECT employee_id FROM schedule_shift_assignments WHERE shift_id = $1",
                shift_id,
            )
            plan_employee_ids = [row["employee_id"] for row in assignees] or [None]
            plans = await _resolve_break_plans_for_ids(
                conn, company_id, location_id=new_location,
                starts_at=new_start, ends_at=new_end,
                employee_ids=plan_employee_ids,
            )
            generated_minimum = max(minimum_meal_break_minutes(plan) for plan in plans)
            requested_break = patch.get("break_minutes", existing["break_minutes"])
            if break_was_explicit and requested_break < generated_minimum:
                raise HTTPException(
                    status_code=422,
                    detail={
                        "code": "break_minimum_required",
                        "minimum_break_minutes": generated_minimum,
                        "message": (
                            f"Planned break cannot be below the generated "
                            f"{generated_minimum}-minute legal minimum."
                        ),
                    },
                )
            if requested_break < generated_minimum:
                patch["break_minutes"] = generated_minimum
            new_break = patch.get("break_minutes", existing["break_minutes"])
            # Same hoist-and-batch as create_shift: one feature lookup + one
            # batched lapse fetch for every assignee, not one each.
            lapse_map: dict = {}
            if assignees:
                company_features = await get_company_features(company_id, conn=conn)
                lapse_map = await schedule_intelligence.fetch_lapse_items(
                    conn, company_id, [row["employee_id"] for row in assignees],
                    credential_templates_enabled=bool(company_features.get("credential_templates")),
                    training_enabled=bool(company_features.get("training")),
                )
            avail_map: dict = {}
            if assignees and retimed:
                avail_map = await fetch_availability(
                    conn, company_id, [row["employee_id"] for row in assignees])
            for row in assignees:
                emp = row["employee_id"]
                avail = availability_violations(
                    avail_map.get(emp, {}), new_start, new_end,
                ) if retimed else []
                if retimed and not force:
                    conflicts = await find_conflicts(
                        conn, company_id, emp, new_start, new_end,
                        exclude_shift_id=shift_id,
                    )
                    if conflicts:
                        raise_conflict(emp, conflicts)
                    if avail:
                        raise_outside_availability(emp, avail)
                if avail:
                    availability_overrides[str(emp)] = avail
                unqualified = await check_job_qualification(
                    conn, company_id, emp, new_job_id, starts_at=new_start,
                )
                if unqualified and not force:
                    raise_not_qualified(unqualified)
                if unqualified:
                    qualification_overrides[str(emp)] = unqualified
                violations = await check_shift_compliance(
                    conn, company_id, location_id=new_location, job_id=new_job_id,
                    starts_at=new_start, ends_at=new_end,
                    break_minutes=new_break or 0, employee_id=emp,
                    exclude_shift_id=shift_id,
                    fw_event=fw_event, fw_shift_published=fw_shift_published,
                    shift_kind=existing["kind"], training_requirement_id=existing["training_requirement_id"],
                    lapse_items=lapse_map.get(str(emp), []),
                )
                raise_for_violations(violations, force=force)
                if violations:
                    forced[str(emp)] = violations
            if not assignees:
                # Open (unassigned) shift: run the shift-intrinsic checks the
                # create path runs — otherwise retiming a 6h open shift to 14h
                # escapes the meal-break/daily-OT advisories entirely.
                raise_for_violations(
                    await check_shift_compliance(
                        conn, company_id, location_id=new_location, job_id=new_job_id,
                        starts_at=new_start, ends_at=new_end,
                        break_minutes=new_break or 0,
                        exclude_shift_id=shift_id,
                        fw_event=fw_event, fw_shift_published=fw_shift_published,
                        shift_kind=existing["kind"], training_requirement_id=existing["training_requirement_id"],
                    ),
                    force=force,
                )
        elif new_status == "cancelled" and fw_shift_published:
            # Cancelling a previously-published shift is skipped by the block
            # above (`new_status != "cancelled"`), but it's exactly the event
            # a Fair Workweek ordinance cares about — check it on its own.
            violations = await check_shift_compliance(
                conn, company_id, location_id=existing["location_id"], job_id=existing["job_id"],
                starts_at=existing["starts_at"], ends_at=existing["ends_at"],
                break_minutes=existing["break_minutes"] or 0,
                exclude_shift_id=shift_id,
                fw_event="cancel", fw_shift_published=True,
            )
            raise_for_violations(violations, force=force)
            if violations:
                forced["cancel"] = violations

        # published_at rides along as a patched column — no spliced CASE clause
        # whose hardcoded $10 silently rebinds when a column is added above it.
        if "status" in patch:
            if new_status == "published":
                if existing["published_at"] is None:
                    patch["published_at"] = datetime.now(timezone.utc)
            else:
                patch["published_at"] = None

        new_location = patch.get("location_id", existing["location_id"])
        was_published = existing["published_at"] is not None
        locked_plans_by_employee = {}
        locked_guidance_timezone = None
        async with conn.transaction():
            locked_shift = await conn.fetchrow(
                "SELECT break_minutes, updated_at FROM schedule_shifts "
                "WHERE id = $1 AND company_id = $2 FOR UPDATE",
                shift_id, company_id,
            )
            if locked_shift is None:
                raise HTTPException(status_code=404, detail="Shift not found")
            if locked_shift["updated_at"] != existing["updated_at"]:
                raise HTTPException(
                    status_code=409,
                    detail={
                        "code": "shift_changed",
                        "message": "The shift changed while you were editing it. Reload and try again.",
                    },
                )
            if compliance_relevant and new_status != "cancelled":
                locked_break = int(locked_shift["break_minutes"] or 0)
                locked_assignees = await conn.fetch(
                    "SELECT employee_id FROM schedule_shift_assignments WHERE shift_id = $1",
                    shift_id,
                )
                if {row["employee_id"] for row in locked_assignees} != {
                    row["employee_id"] for row in assignees
                }:
                    raise HTTPException(
                        status_code=409,
                        detail={
                            "code": "shift_changed",
                            "message": "The shift roster changed while you were editing it. Reload and try again.",
                        },
                    )
                if retimed and not force:
                    # Employee advisory locks serialize this retime with
                    # assignments to other shifts; repeat overlap checks only
                    # after those locks are held.
                    for employee_id in sorted(
                        row["employee_id"] for row in locked_assignees
                    ):
                        conflicts = await find_conflicts(
                            conn, company_id, employee_id, new_start, new_end,
                            exclude_shift_id=shift_id,
                        )
                        if conflicts:
                            raise_conflict(employee_id, conflicts)
                locked_employee_ids = [row["employee_id"] for row in locked_assignees] or [None]
                locked_plans = await _resolve_break_plans_for_ids(
                    conn, company_id, location_id=new_location,
                    starts_at=new_start, ends_at=new_end,
                    employee_ids=locked_employee_ids,
                )
                locked_minimum = max(
                    minimum_meal_break_minutes(plan) for plan in locked_plans
                )
                locked_plans_by_employee = dict(zip(locked_employee_ids, locked_plans))
                if locked_assignees and new_location is not None:
                    locked_guidance_timezone = await conn.fetchval(
                        "SELECT timezone FROM business_locations WHERE id=$1 AND company_id=$2",
                        new_location, company_id,
                    ) or "UTC"
                write_break = int(patch.get("break_minutes", existing["break_minutes"]) or 0)
                if write_break < locked_minimum:
                    if break_was_explicit:
                        raise HTTPException(
                            status_code=422,
                            detail={
                                "code": "break_minimum_required",
                                "minimum_break_minutes": locked_minimum,
                                "message": (
                                    f"Planned break cannot be below the generated "
                                    f"{locked_minimum}-minute legal minimum."
                                ),
                            },
                        )
                    write_break = locked_minimum
                write_break = _locked_break_write(
                    requested=write_break,
                    locked=locked_break,
                    existing=int(existing["break_minutes"] or 0),
                    minimum=locked_minimum,
                    manual=break_was_explicit,
                    legacy_value=legacy_break_value,
                )
                if write_break != locked_break or auto_break_requested:
                    patch["break_minutes"] = write_break

            if publishing:
                # ShiftUpdate historically accepts status changes, so keep that
                # contract while routing draft -> published through the same
                # locked minimum/eligibility gate as the dedicated endpoints.
                publish_breaks = await _lock_and_assert_publish_assignments_eligible(
                    conn,
                    company_id,
                    [{
                        "id": shift_id,
                        "location_id": new_location,
                        "job_id": patch.get("job_id", existing["job_id"]),
                        "starts_at": new_start,
                        "ends_at": new_end,
                        "break_minutes": patch.get(
                            "break_minutes", locked_shift["break_minutes"],
                        ),
                        "kind": existing["kind"],
                        "training_requirement_id": existing["training_requirement_id"],
                    }],
                )
                effective_break = publish_breaks[shift_id]
                if effective_break != int(locked_shift["break_minutes"] or 0):
                    patch["break_minutes"] = effective_break

            # Auto is intentionally a no-op for cancelled shifts.  Avoid
            # asking build_patch() to synthesize an UPDATE from no columns.
            if not patch:
                return await fetch_shift_by_id(conn, company_id, shift_id)

            before = shift_snapshot(existing)
            after = {**before}
            for field, value in patch.items():
                after[field] = (
                    value.isoformat() if isinstance(value, datetime)
                    else str(value) if isinstance(value, UUID)
                    else value
                )
            audit_assignees = await conn.fetch(
                "SELECT employee_id FROM schedule_shift_assignments WHERE shift_id = $1",
                shift_id,
            ) if was_published else []
            set_sql, params = build_patch(patch, first_param=3)
            await conn.execute(
                f"""
                UPDATE schedule_shifts SET {set_sql}, updated_at = NOW()
                WHERE id = $1 AND company_id = $2
                """,
                shift_id, company_id, *params,
            )
            await log_audit(conn, company_id, "shift", shift_id, current_user.id,
                            "shift.update", {
                                "fields": sorted(patch),
                                "before": before,
                                "after": after,
                                "was_published": was_published,
                                "assigned_employee_ids": [str(row["employee_id"]) for row in audit_assignees],
                            })
            if retimed or "location_id" in patch:
                assignees = await conn.fetch(
                    "SELECT employee_id FROM schedule_shift_assignments WHERE shift_id = $1",
                    shift_id,
                )
                for assignee in assignees:
                    await refresh_assignment_break_guidance(
                        conn, company_id, shift_id=shift_id,
                        employee_id=assignee["employee_id"], location_id=new_location,
                        starts_at=new_start, ends_at=new_end,
                        plan=locked_plans_by_employee.get(assignee["employee_id"]),
                        timezone_name=locked_guidance_timezone,
                    )
            if forced:
                await log_audit(conn, company_id, "shift", shift_id, current_user.id,
                                "shift.compliance_override", {"forced": forced})
            for employee_id, avail in availability_overrides.items():
                await log_availability_override(
                    conn, company_id, shift_id, current_user.id,
                    UUID(employee_id), avail,
                )
            for employee_id, detail in qualification_overrides.items():
                await log_audit(
                    conn, company_id, "assignment", shift_id, current_user.id,
                    "assignment.qualification_override",
                    {"employee_id": employee_id, **detail},
                )
        await reconcile_warning_events(conn, company_id, [shift_id])
        return await fetch_shift_by_id(conn, company_id, shift_id)


@router.delete("/shifts/{shift_id}")
async def delete_shift(shift_id: UUID,
                       force: bool = Query(False, description="Delete despite a Fair Workweek notice/clopening advisory"),
                       current_user=Depends(require_admin_or_client)):
    company_id = await require_company_id(current_user)
    async with get_connection() as conn:
        async with conn.transaction():
            existing = await conn.fetchrow(
                """
                SELECT starts_at, ends_at, status, published_at, location_id, break_minutes,
                       role, department, required_staff, color, notes, job_id
                FROM schedule_shifts WHERE id = $1 AND company_id = $2
                """,
                shift_id, company_id,
            )
            if not existing:
                raise HTTPException(status_code=404, detail="Shift not found")
            if existing["published_at"] is not None:
                # Deleting a published shift is a cancellation for Fair
                # Workweek purposes — advisory only (never blocks the delete
                # outright), same force-through convention as every other
                # scheduling advisory. Only the FW half runs: meal-break/OT
                # checks gate scheduling someone, and re-raising them on a
                # shift being REMOVED is noise (same reasoning as unassign).
                violations = await _fair_workweek_advisories(
                    conn, company_id, location_id=existing["location_id"],
                    starts_at=existing["starts_at"], ends_at=existing["ends_at"],
                    event="cancel", shift_published=True, min_rest_gap_hours=None,
                )
                raise_for_violations(violations, force=force)
            audit_assignees = await conn.fetch(
                "SELECT employee_id FROM schedule_shift_assignments WHERE shift_id = $1",
                shift_id,
            ) if existing["published_at"] is not None else []
            result = await conn.execute(
                "DELETE FROM schedule_shifts WHERE id = $1 AND company_id = $2",
                shift_id, company_id,
            )
            if result == "DELETE 0":
                raise HTTPException(status_code=404, detail="Shift not found")
            await log_audit(conn, company_id, "shift", shift_id, current_user.id,
                            "shift.delete", {
                                "before": shift_snapshot(existing),
                                "was_published": existing["published_at"] is not None,
                                "assigned_employee_ids": [str(row["employee_id"]) for row in audit_assignees],
                            })
        await reconcile_warning_events(conn, company_id, [shift_id])
    return {"ok": True, "id": str(shift_id)}


@router.post("/shifts/{shift_id}/publish")
async def publish_shift(shift_id: UUID, current_user=Depends(require_admin_or_client)):
    company_id = await require_company_id(current_user)
    async with get_connection() as conn:
        async with conn.transaction():
            shift = await conn.fetchrow(
                """
                SELECT id, location_id, job_id, starts_at, ends_at, break_minutes,
                       kind, training_requirement_id
                FROM schedule_shifts
                WHERE id = $1 AND company_id = $2 AND status <> 'cancelled'
                FOR UPDATE
                """,
                shift_id, company_id,
            )
            if not shift:
                raise HTTPException(status_code=404, detail="Shift not found")
            await assert_schedule_location_ready_to_publish(
                conn, company_id, shift["location_id"],
            )
            await _lock_and_assert_publish_assignments_eligible(
                conn, company_id, [shift],
            )
            row = await conn.fetchrow(
                """
                UPDATE schedule_shifts
                SET status = 'published',
                    published_at = COALESCE(published_at, NOW()),
                    updated_at = NOW()
                WHERE id = $1 AND company_id = $2 AND status <> 'cancelled'
                RETURNING id
                """,
                shift_id, company_id,
            )
            if not row:
                raise HTTPException(status_code=404, detail="Shift not found")
            await log_audit(conn, company_id, "shift", shift_id, current_user.id,
                            "shift.publish", {})
        await reconcile_warning_events(conn, company_id, [shift_id])
        return await fetch_shift_by_id(conn, company_id, shift_id)


@router.post("/shifts/publish")
async def publish_range(body: PublishRange, current_user=Depends(require_admin_or_client)):
    """Publish every draft shift starting within [start, end).

    `location_id`, when given, scopes this to one location (plus shifts with
    no location set) — matching the location-scoped week the caller is
    looking at, so "Publish week (N)" doesn't silently publish other
    locations' drafts too.
    """
    company_id = await require_company_id(current_user)
    async with get_connection() as conn:
        await assert_location_in_company(conn, company_id, body.location_id)
        async with conn.transaction():
            candidate_shifts = await conn.fetch(
                """
                SELECT id, location_id, job_id, starts_at, ends_at, break_minutes,
                       kind, training_requirement_id
                FROM schedule_shifts
                WHERE company_id = $1 AND status = 'draft'
                  AND starts_at >= $2 AND starts_at < $3
                  AND ($4::uuid IS NULL OR location_id = $4 OR location_id IS NULL)
                ORDER BY id
                FOR UPDATE
                """,
                company_id, body.start, body.end, body.location_id,
            )
            seen_locations = set()
            for shift in candidate_shifts:
                if shift["location_id"] in seen_locations:
                    continue
                seen_locations.add(shift["location_id"])
                await assert_schedule_location_ready_to_publish(
                    conn, company_id, shift["location_id"],
                )
            await _lock_and_assert_publish_assignments_eligible(
                conn, company_id, candidate_shifts,
            )
            candidate_ids = [shift["id"] for shift in candidate_shifts]
            count = 0
            if candidate_ids:
                count = await conn.fetchval(
                """
                WITH updated AS (
                    UPDATE schedule_shifts
                    SET status = 'published',
                        published_at = COALESCE(published_at, NOW()),
                        updated_at = NOW()
                    WHERE company_id = $1 AND status = 'draft'
                      AND id = ANY($2::uuid[])
                    RETURNING id
                )
                SELECT COUNT(*) FROM updated
                """,
                    company_id, candidate_ids,
                )
            await log_audit(conn, company_id, "shift", None, current_user.id,
                            "shift.publish_range", {"count": count, "location_id": str(body.location_id) if body.location_id else None})
        await reconcile_warning_events(conn, company_id)
        # Same window semantics as the UPDATE above, so the returned summary
        # counts exactly the shifts this call could have published.
        shifts = await fetch_shifts(conn, company_id, body.start, body.end,
                                    location_id=body.location_id, starts_within=True)
    return {"published": count, "shifts": shifts, "summary": _summarize(shifts)}
