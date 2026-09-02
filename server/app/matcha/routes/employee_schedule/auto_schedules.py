"""Manager-configured Huume schedule suggestion timing, scoped per location."""

from datetime import datetime, timezone
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query

from app.core.feature_flags import get_company_features
from app.database import get_connection
from app.matcha.models.scheduling.employee_schedule import ScheduleAutomationRuleUpsert
from app.matcha.services.scheduling.schedule_automation import (
    generate_review_suggestion,
    next_run_at,
    target_week_start as automation_target_week_start,
)

from ...dependencies import require_admin_or_client
from ._shared import assert_location_in_company, log_audit, require_company_id


router = APIRouter()


async def _require_schedule_huume(company_id: UUID) -> None:
    features = await get_company_features(company_id)
    if not features.get("huume") or not features.get("matcha_work"):
        raise HTTPException(status_code=403, detail="Huume scheduling is not enabled for this company.")


def _serialize(row) -> dict:
    return {
        "id": str(row["id"]),
        "location_id": str(row["location_id"]),
        "location_name": row["location_name"],
        "timezone": row["timezone"] or "UTC",
        "enabled": row["enabled"],
        "cadence": row["cadence"],
        "week_template_id": str(row["week_template_id"]) if row["week_template_id"] else None,
        "week_template_name": row["week_template_name"],
        "run_weekday": row["run_weekday"],
        "run_date": row["run_date"].isoformat() if row["run_date"] else None,
        "run_time": row["run_time"].isoformat(timespec="minutes"),
        "target_weeks_ahead": row["target_weeks_ahead"],
        "target_week_start": row["target_week_start"].isoformat() if row["target_week_start"] else None,
        "next_run_at": row["next_run_at"].isoformat() if row["next_run_at"] else None,
        "last_attempt_at": row["last_attempt_at"].isoformat() if row["last_attempt_at"] else None,
        "last_completed_at": row["last_completed_at"].isoformat() if row["last_completed_at"] else None,
        "last_status": row["last_status"],
        "last_message": row["last_message"],
        "last_generation_run_id": (
            str(row["last_generation_run_id"]) if row["last_generation_run_id"] else None
        ),
    }


async def _fetch_rule(conn, company_id: UUID, location_id: UUID):
    return await conn.fetchrow(
        """
        SELECT r.*, l.name AS location_name, l.timezone,
               wt.name AS week_template_name
        FROM schedule_automation_rules r
        JOIN business_locations l ON l.id=r.location_id AND l.company_id=r.company_id
        LEFT JOIN schedule_week_templates wt ON wt.id=r.week_template_id
        WHERE r.company_id=$1 AND r.location_id=$2
        """,
        company_id, location_id,
    )


@router.get("/auto-schedules")
async def get_auto_schedule(
    location_id: UUID = Query(...),
    current_user=Depends(require_admin_or_client),
):
    company_id = await require_company_id(current_user)
    await _require_schedule_huume(company_id)
    async with get_connection() as conn:
        await assert_location_in_company(conn, company_id, location_id)
        row = await _fetch_rule(conn, company_id, location_id)
    return {"rule": _serialize(row) if row else None}


@router.put("/auto-schedules/{location_id}")
async def save_auto_schedule(
    location_id: UUID,
    body: ScheduleAutomationRuleUpsert,
    current_user=Depends(require_admin_or_client),
):
    company_id = await require_company_id(current_user)
    await _require_schedule_huume(company_id)
    async with get_connection() as conn:
        location = await conn.fetchrow(
            """SELECT id, timezone FROM business_locations
               WHERE id=$1 AND company_id=$2 AND is_active IS NOT FALSE""",
            location_id, company_id,
        )
        if not location:
            raise HTTPException(status_code=404, detail="Location not found")
        template_exists = await conn.fetchval(
            """SELECT EXISTS(
                   SELECT 1 FROM schedule_week_templates
                   WHERE id=$1 AND company_id=$2 AND (location_id=$3 OR location_id IS NULL)
               )""",
            body.week_template_id, company_id, location_id,
        )
        if not template_exists:
            raise HTTPException(status_code=422, detail="Choose a week template available to this location.")
        try:
            scheduled_at = next_run_at(
                cadence=body.cadence,
                timezone_name=location["timezone"],
                run_time=body.run_time,
                run_weekday=body.run_weekday,
                run_date=body.run_date,
            ) if body.enabled else None
        except ValueError as exc:
            raise HTTPException(status_code=422, detail=str(exc)) from exc

        async with conn.transaction():
            row = await conn.fetchrow(
                """
                INSERT INTO schedule_automation_rules(
                    company_id, location_id, week_template_id, enabled, cadence,
                    run_weekday, run_date, run_time, target_weeks_ahead,
                    target_week_start, next_run_at, created_by, updated_by
                ) VALUES($1,$2,$3,$4,$5,$6,$7,$8,$9,$10,$11,$12,$12)
                ON CONFLICT (company_id, location_id) DO UPDATE SET
                    week_template_id=EXCLUDED.week_template_id,
                    enabled=EXCLUDED.enabled,
                    cadence=EXCLUDED.cadence,
                    run_weekday=EXCLUDED.run_weekday,
                    run_date=EXCLUDED.run_date,
                    run_time=EXCLUDED.run_time,
                    target_weeks_ahead=EXCLUDED.target_weeks_ahead,
                    target_week_start=EXCLUDED.target_week_start,
                    next_run_at=EXCLUDED.next_run_at,
                    schedule_version=schedule_automation_rules.schedule_version + 1,
                    updated_by=EXCLUDED.updated_by,
                    updated_at=NOW()
                RETURNING id, schedule_version
                """,
                company_id, location_id, body.week_template_id, body.enabled, body.cadence,
                body.run_weekday, body.run_date, body.run_time, body.target_weeks_ahead,
                body.target_week_start, scheduled_at, current_user.id,
            )
            await log_audit(
                conn, company_id, "schedule_automation", row["id"], current_user.id,
                "schedule_automation.save",
                {"location_id": str(location_id), "cadence": body.cadence, "enabled": body.enabled},
            )
        saved = await _fetch_rule(conn, company_id, location_id)

    if scheduled_at:
        from app.workers.tasks.schedule_auto_generation import enqueue_schedule_automation
        enqueue_schedule_automation(row["id"], row["schedule_version"], scheduled_at)
    return _serialize(saved)


@router.post("/auto-schedules/{location_id}/run-now")
async def run_auto_schedule_now(
    location_id: UUID,
    current_user=Depends(require_admin_or_client),
):
    company_id = await require_company_id(current_user)
    await _require_schedule_huume(company_id)
    async with get_connection() as conn:
        row = await _fetch_rule(conn, company_id, location_id)
    if not row:
        raise HTTPException(status_code=404, detail="Configure this location's auto schedule first.")
    if not row["week_template_id"]:
        raise HTTPException(status_code=422, detail="Choose a saved week template first.")
    target = automation_target_week_start(
        cadence=row["cadence"],
        scheduled_for=datetime.now(timezone.utc),
        timezone_name=row["timezone"],
        target_weeks_ahead=row["target_weeks_ahead"],
        one_time_week_start=row["target_week_start"],
    )
    result = await generate_review_suggestion(
        company_id=company_id,
        location_id=location_id,
        week_start=target,
        week_template_id=row["week_template_id"],
    )
    generation_id = result.get("generation_run_id")
    async with get_connection() as conn:
        await conn.execute(
            """UPDATE schedule_automation_rules
               SET last_attempt_at=NOW(), last_completed_at=NOW(), last_status=$1,
                   last_message=$2, last_generation_run_id=$3, updated_at=NOW()
               WHERE id=$4 AND company_id=$5""",
            result["status"], result.get("message"), UUID(generation_id) if generation_id else None,
            row["id"], company_id,
        )
    return {**result, "week_start": target.isoformat()}
