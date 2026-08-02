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
from ...services.scheduling import schedule_compliance, schedule_intelligence
from ...services.scheduling.shift_writes import create_shift_core
from ._shared import (
    require_company_id, log_audit, fetch_shifts, fetch_roster, fetch_shift_by_id,
    assert_employee_in_company, assert_location_in_company,
    find_conflicts, raise_conflict, shift_snapshot,
    fetch_availability, availability_violations, raise_outside_availability,
    shift_window_on_date,
)
from ._compliance import (
    check_shift_compliance, raise_for_violations, _approved_db_rules,
    _fair_workweek_advisories,
)

logger = logging.getLogger(__name__)

router = APIRouter()


@router.get("/roster")
async def get_roster(current_user=Depends(require_admin_or_client)):
    company_id = await require_company_id(current_user)
    async with get_connection() as conn:
        return {"employees": await fetch_roster(conn, company_id)}


@router.get("/shifts")
async def list_shifts(
    start: datetime = Query(...),
    end: datetime = Query(...),
    status: str | None = Query(None),
    current_user=Depends(require_admin_or_client),
):
    if end <= start:
        raise HTTPException(status_code=422, detail="end must be after start")
    company_id = await require_company_id(current_user)
    async with get_connection() as conn:
        shifts = await fetch_shifts(conn, company_id, start, end, status=status)
    return {"shifts": shifts, "summary": _summarize(shifts)}


@router.get("/week")
async def get_week(
    start: date = Query(..., description="Week start date (YYYY-MM-DD)"),
    current_user=Depends(require_admin_or_client),
):
    """Weekly grid: the 7 days from `start`, plus the roster for the picker."""
    company_id = await require_company_id(current_user)
    lo, hi = _week_bounds(start)
    async with get_connection() as conn:
        # starts_within: the grid buckets by start date and publish_range only
        # publishes shifts starting in the window — matching on overlap here
        # would count a shift in the summary that no day column renders and no
        # publish touches.
        shifts = await fetch_shifts(conn, company_id, lo, hi, starts_within=True)
        roster = await fetch_roster(conn, company_id)

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
                }
                for emp_id, items in lapses.items()
            }
    return {
        "week_start": start.isoformat(),
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


@router.post("/shifts")
async def create_shift(body: ShiftCreate,
                       force: bool = Query(False, description="Assign despite overlapping shifts"),
                       current_user=Depends(require_admin_or_client)):
    company_id = await require_company_id(current_user)
    async with get_connection() as conn:
        await assert_location_in_company(conn, company_id, body.location_id)
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
        if body.employee_ids and not force:
            avail_map = await fetch_availability(
                conn, company_id, list(dict.fromkeys(body.employee_ids)))

        forced: dict[str, list[dict]] = {}
        for emp_id in body.employee_ids:
            await assert_employee_in_company(conn, company_id, emp_id)
            if not force:
                conflicts = await find_conflicts(
                    conn, company_id, emp_id, body.starts_at, body.ends_at,
                )
                if conflicts:
                    raise_conflict(emp_id, conflicts)
                avail = availability_violations(
                    avail_map.get(emp_id, {}), body.starts_at, body.ends_at)
                if avail:
                    raise_outside_availability(emp_id, avail)
            violations = await check_shift_compliance(
                conn, company_id, location_id=body.location_id,
                starts_at=body.starts_at, ends_at=body.ends_at,
                break_minutes=body.break_minutes or 0, employee_id=emp_id,
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
                    conn, company_id, location_id=body.location_id,
                    starts_at=body.starts_at, ends_at=body.ends_at,
                    break_minutes=body.break_minutes or 0,
                ),
                force=force,
            )
        async with conn.transaction():
            shift_id = await create_shift_core(
                conn, company_id,
                location_id=body.location_id, role=body.role, department=body.department,
                starts_at=body.starts_at, ends_at=body.ends_at,
                break_minutes=body.break_minutes, required_staff=body.required_staff,
                color=body.color, notes=body.notes, kind=body.kind,
                training_requirement=dict(training_requirement) if training_requirement else None,
                training_requirement_id=body.training_requirement_id,
                employee_ids=body.employee_ids, created_by=current_user.id,
                status="draft",
            )
            if forced:
                await log_audit(conn, company_id, "shift", shift_id, current_user.id,
                                "shift.compliance_override", {"forced": forced})
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
            conn, company_id, location_id=src["location_id"],
            starts_at=first_start, ends_at=first_end,
            break_minutes=src["break_minutes"] or 0, shift_kind=src["kind"],
        )

        dropped: list[dict] = []
        created_ids: list[UUID] = []
        async with conn.transaction():
            for d in body.target_dates:
                new_start, new_end = shift_window_on_date(src["starts_at"], src["ends_at"], d)
                surviving: list[UUID] = []
                for eid in employee_ids:
                    conflicts = await find_conflicts(conn, company_id, eid, new_start, new_end)
                    avail = availability_violations(avail_map.get(eid, {}), new_start, new_end)
                    if conflicts or avail:
                        dropped.append({
                            "date": d.isoformat(), "employee_id": str(eid),
                            "name": names.get(str(eid), ""),
                            "reason": "outside their logged availability" if avail
                                      else "already scheduled during this time",
                        })
                        continue
                    surviving.append(eid)
                new_id = await create_shift_core(
                    conn, company_id,
                    location_id=src["location_id"], role=src["role"], department=src["department"],
                    starts_at=new_start, ends_at=new_end,
                    break_minutes=src["break_minutes"], required_staff=src["required_staff"],
                    color=src["color"], notes=src["notes"], kind=src["kind"],
                    training_requirement=training_requirement,
                    training_requirement_id=src["training_requirement_id"],
                    employee_ids=surviving, created_by=current_user.id, status="draft",
                    audit_details={"source": "duplicate", "source_shift_id": str(shift_id)},
                )
                created_ids.append(new_id)
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
    async with get_connection() as conn:
        existing = await conn.fetchrow(
            """
            SELECT starts_at, ends_at, status, published_at, break_minutes, location_id,
                   kind, training_requirement_id
            FROM schedule_shifts WHERE id = $1 AND company_id = $2
            """,
            shift_id, company_id,
        )
        if not existing:
            raise HTTPException(status_code=404, detail="Shift not found")
        if not patch:
            return await fetch_shift_by_id(conn, company_id, shift_id)
        if "location_id" in patch:
            await assert_location_in_company(conn, company_id, patch["location_id"])

        new_status = patch.get("status", existing["status"])
        # Cancelled is terminal for publication — POST /publish already refuses it
        # (`AND status <> 'cancelled'`), and a resurrected shift would reappear on
        # every assignee's portal. Reopening as a draft is the supported path.
        if existing["status"] == "cancelled" and new_status == "published":
            raise HTTPException(
                status_code=409,
                detail="Cannot publish a cancelled shift — reopen it as a draft first",
            )

        new_start = patch.get("starts_at") or existing["starts_at"]
        new_end = patch.get("ends_at") or existing["ends_at"]
        if new_end <= new_start:
            raise HTTPException(status_code=422, detail="ends_at must be after starts_at")

        # Retiming a staffed shift is an assignment path like any other: it can
        # double-book everyone already on it, so it takes the same guard + force.
        # A break/location edit is compliance-relevant too (meal-break, jurisdiction).
        retimed = new_start != existing["starts_at"] or new_end != existing["ends_at"]
        compliance_relevant = retimed or "break_minutes" in patch or "location_id" in patch
        # Fair Workweek notice/clopening obligations attach to a POSTED shift's
        # timing changing, not to break/location edits alone — only pass the
        # event when the shift's start/end actually moved.
        fw_event = "retime" if retimed else None
        fw_shift_published = existing["published_at"] is not None
        forced: dict[str, list[dict]] = {}
        if compliance_relevant and new_status != "cancelled":
            new_break = patch.get("break_minutes", existing["break_minutes"])
            new_location = patch.get("location_id", existing["location_id"])
            assignees = await conn.fetch(
                "SELECT employee_id FROM schedule_shift_assignments WHERE shift_id = $1",
                shift_id,
            )
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
            if assignees and retimed and not force:
                avail_map = await fetch_availability(
                    conn, company_id, [row["employee_id"] for row in assignees])
            for row in assignees:
                emp = row["employee_id"]
                if retimed and not force:
                    conflicts = await find_conflicts(
                        conn, company_id, emp, new_start, new_end,
                        exclude_shift_id=shift_id,
                    )
                    if conflicts:
                        raise_conflict(emp, conflicts)
                    avail = availability_violations(avail_map.get(emp, {}), new_start, new_end)
                    if avail:
                        raise_outside_availability(emp, avail)
                violations = await check_shift_compliance(
                    conn, company_id, location_id=new_location,
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
                        conn, company_id, location_id=new_location,
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
                conn, company_id, location_id=existing["location_id"],
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

        before = shift_snapshot(existing)
        new_location = patch.get("location_id", existing["location_id"])
        after = {
            "starts_at": new_start.isoformat(),
            "ends_at": new_end.isoformat(),
            "status": new_status,
            "location_id": str(new_location) if new_location else None,
        }
        was_published = existing["published_at"] is not None

        set_sql, params = build_patch(patch, first_param=3)
        async with conn.transaction():
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
                            })
            if forced:
                await log_audit(conn, company_id, "shift", shift_id, current_user.id,
                                "shift.compliance_override", {"forced": forced})
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
                SELECT starts_at, ends_at, status, published_at, location_id, break_minutes
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
                            })
    return {"ok": True, "id": str(shift_id)}


@router.post("/shifts/{shift_id}/publish")
async def publish_shift(shift_id: UUID, current_user=Depends(require_admin_or_client)):
    company_id = await require_company_id(current_user)
    async with get_connection() as conn:
        async with conn.transaction():
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
        return await fetch_shift_by_id(conn, company_id, shift_id)


@router.post("/shifts/publish")
async def publish_range(body: PublishRange, current_user=Depends(require_admin_or_client)):
    """Publish every draft shift starting within [start, end)."""
    company_id = await require_company_id(current_user)
    async with get_connection() as conn:
        async with conn.transaction():
            count = await conn.fetchval(
                """
                WITH updated AS (
                    UPDATE schedule_shifts
                    SET status = 'published',
                        published_at = COALESCE(published_at, NOW()),
                        updated_at = NOW()
                    WHERE company_id = $1 AND status = 'draft'
                      AND starts_at >= $2 AND starts_at < $3
                    RETURNING id
                )
                SELECT COUNT(*) FROM updated
                """,
                company_id, body.start, body.end,
            )
            await log_audit(conn, company_id, "shift", None, current_user.id,
                            "shift.publish_range", {"count": count})
        # Same window semantics as the UPDATE above, so the returned summary
        # counts exactly the shifts this call could have published.
        shifts = await fetch_shifts(conn, company_id, body.start, body.end,
                                    starts_within=True)
    return {"published": count, "shifts": shifts, "summary": _summarize(shifts)}
