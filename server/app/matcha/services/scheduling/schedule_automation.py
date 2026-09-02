"""Tenant-scoped timing and generation for review-only schedule suggestions."""

from datetime import date, datetime, time, timedelta, timezone
from uuid import UUID
from zoneinfo import ZoneInfo

from app.database import connection_or_direct


def location_zone(timezone_name: str | None):
    try:
        return ZoneInfo(timezone_name or "UTC")
    except (KeyError, ValueError):
        return timezone.utc


def next_run_at(
    *, cadence: str, timezone_name: str | None, run_time: time,
    run_weekday: int | None = None, run_date: date | None = None,
    after: datetime | None = None,
) -> datetime:
    """Return the next configured wall-clock occurrence as UTC."""
    zone = location_zone(timezone_name)
    now = (after or datetime.now(timezone.utc)).astimezone(zone)
    if cadence == "once":
        if run_date is None:
            raise ValueError("A one-time schedule needs a run date.")
        candidate = datetime.combine(run_date, run_time, tzinfo=zone)
        if candidate <= now:
            raise ValueError("Choose a one-time run date and time in the future.")
        return candidate.astimezone(timezone.utc)
    if run_weekday is None:
        raise ValueError("A weekly schedule needs a run day.")
    days_ahead = (run_weekday - ((now.weekday() + 1) % 7)) % 7
    candidate = datetime.combine(now.date() + timedelta(days=days_ahead), run_time, tzinfo=zone)
    if candidate <= now:
        candidate += timedelta(days=7)
    return candidate.astimezone(timezone.utc)


def target_week_start(
    *, cadence: str, scheduled_for: datetime, timezone_name: str | None,
    target_weeks_ahead: int | None, one_time_week_start: date | None,
) -> date:
    if cadence == "once":
        if one_time_week_start is None:
            raise ValueError("A one-time schedule needs a target week.")
        return one_time_week_start
    local_day = scheduled_for.astimezone(location_zone(timezone_name)).date()
    current_sunday = local_day - timedelta(days=(local_day.weekday() + 1) % 7)
    return current_sunday + timedelta(days=7 * int(target_weeks_ahead or 1))


async def generate_review_suggestion(
    *, company_id: UUID, location_id: UUID, week_start: date,
    week_template_id: UUID,
) -> dict:
    """Build one proposal without applying or publishing any schedule data."""
    week_end = week_start + timedelta(days=7)
    week_start_at = datetime.combine(week_start, time.min, tzinfo=timezone.utc)
    week_end_at = datetime.combine(week_end, time.min, tzinfo=timezone.utc)
    async with connection_or_direct() as conn:
        # Applying a proposal does not permanently reserve its week: managers
        # can delete or cancel every resulting draft before publishing. Keep
        # the run state aligned with the editor's visible schedule so that
        # orphaned applied runs do not block a replacement suggestion.
        await conn.execute(
            """
            UPDATE schedule_generation_runs r
            SET status='stale', updated_at=NOW()
            WHERE r.company_id=$1 AND r.location_id=$2 AND r.week_start=$3
              AND r.status='applied'
              AND NOT EXISTS (
                  SELECT 1 FROM schedule_shifts s
                  WHERE s.company_id=$1 AND s.location_id=$2
                    AND s.status IN ('draft', 'published')
                    AND s.starts_at >= $4 AND s.starts_at < $5
              )
            """,
            company_id, location_id, week_start, week_start_at, week_end_at,
        )
        existing = await conn.fetchrow(
            """SELECT id, status FROM schedule_generation_runs
               WHERE company_id=$1 AND location_id=$2 AND week_start=$3
                 AND status IN ('proposed', 'applied')
               ORDER BY created_at DESC LIMIT 1""",
            company_id, location_id, week_start,
        )
    if existing:
        return {
            "status": "already_present",
            "message": "A schedule suggestion or approved schedule already exists for that week.",
            "generation_run_id": str(existing["id"]),
        }

    from .week_builder import get_week_build_readiness, propose_week_draft

    readiness = await get_week_build_readiness(
        company_id=company_id, location_id=location_id, week_start=week_start,
        week_template_id=week_template_id,
    )
    if readiness.get("status") != "ok" or not readiness.get("ready"):
        blockers = readiness.get("blockers") or [readiness.get("message") or "The week is not ready."]
        return {"status": "not_ready", "message": " ".join(blockers)}
    result = await propose_week_draft(
        company_id=company_id,
        actor_user_id=None,
        thread_id=None,
        location_id=location_id,
        week_start=week_start,
        source_mode="template",
        week_template_id=str(week_template_id),
        origin="automatic",
    )
    if result.get("status") == "ready":
        return {
            "status": "generated",
            "message": "Huume prepared a schedule suggestion for manager review.",
            "generation_run_id": result.get("generation_run_id"),
        }
    if result.get("status") == "skipped":
        return {"status": "already_present", "message": result.get("message")}
    return {"status": "not_ready", "message": result.get("message") or "The week is not ready."}
