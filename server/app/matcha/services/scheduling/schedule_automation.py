"""Tenant-scoped timing and generation for review-only schedule suggestions."""

from datetime import date, datetime, time, timedelta, timezone
from uuid import UUID
from zoneinfo import ZoneInfo

from app.database import connection_or_direct
from app.matcha.services.scheduling.schedule_rules import align_week_start


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
    week_start_weekday: int = 0,
) -> date:
    if cadence == "once":
        if one_time_week_start is None:
            raise ValueError("A one-time schedule needs a target week.")
        return one_time_week_start
    local_day = scheduled_for.astimezone(location_zone(timezone_name)).date()
    current_week = align_week_start(local_day, week_start_weekday)
    return current_week + timedelta(days=7 * int(target_weeks_ahead or 1))


def past_week_refusal(
    *, week_start: date, timezone_name: str | None, week_start_weekday: int = 0,
    now: datetime | None = None,
) -> dict | None:
    """Refuse a rule-derived target week that has already ended.

    A one-time rule keeps its ``target_week_start`` forever, so "Run now" on a
    rule saved weeks ago silently rebuilt a PAST week and was refused by that
    week's old approved run — which a manager looking at the current week read
    as their week being blocked (Po Coffee, 2026-09-27). "Past" is judged on
    the location's own clock and week start, never UTC's Sunday.
    """
    local_today = (now or datetime.now(timezone.utc)).astimezone(location_zone(timezone_name)).date()
    if week_start >= align_week_start(local_today, week_start_weekday):
        return None
    iso = week_start.isoformat()
    return {
        "status": "not_ready",
        "week_start": iso,
        "message": (
            f"This rule targets the week of {iso}, which has already passed. "
            "Change 'Week starting' and save, or build the week from the shift editor."
        ),
    }


def already_present_result(
    *, week_start: date, blocking_status: str | None, generation_run_id: str | None = None,
) -> dict:
    """The duplicate-generation refusal, naming the week and what holds it.

    The message used to say only "…already exists for that week", so a manager
    could not tell WHICH week the rule had targeted or whether it was an
    unapproved suggestion (review it) or an applied schedule (clear its shifts).
    """
    iso = week_start.isoformat()
    if blocking_status == "proposed":
        message = f"A schedule suggestion for the week of {iso} is already waiting for review."
    elif blocking_status == "applied":
        message = (
            f"An approved schedule for the week of {iso} already exists. "
            "Clear its shifts before generating a replacement."
        )
    else:
        message = f"A schedule suggestion already exists for the week of {iso}."
    result = {
        "status": "already_present",
        "message": message,
        "week_start": iso,
        "blocking_status": blocking_status,
    }
    if generation_run_id:
        result["generation_run_id"] = generation_run_id
    return result


async def generate_review_suggestion(
    *, company_id: UUID, location_id: UUID, week_start: date,
    week_template_id: UUID | None, mode: str = "template",
    actor_user_id: UUID | None = None, actor_role: str | None = None,
    supersede_proposed: bool = False,
) -> dict:
    """Build one proposal without applying or publishing any schedule data.

    The scheduled worker passes no actor. A manager's own click passes
    ``actor_user_id``/``actor_role`` (audit attribution, and the role
    `cost_delta_for_rows` needs before it prices the week) and
    ``supersede_proposed=True``: rebuilding after tuning the inputs replaces
    the still-unapproved suggestion for that week instead of being refused by
    it. An applied run is never superseded.
    """
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
        blocking = "status='applied'" if supersede_proposed else "status IN ('proposed', 'applied')"
        existing = await conn.fetchrow(
            f"""SELECT id, status FROM schedule_generation_runs
               WHERE company_id=$1 AND location_id=$2 AND week_start=$3
                 AND {blocking}
               ORDER BY created_at DESC LIMIT 1""",
            company_id, location_id, week_start,
        )
    if existing:
        return already_present_result(
            week_start=week_start, blocking_status=existing["status"],
            generation_run_id=str(existing["id"]),
        )

    from .week_builder import get_week_build_readiness, propose_week_draft

    readiness = await get_week_build_readiness(
        company_id=company_id, location_id=location_id, week_start=week_start,
        week_template_id=week_template_id, source_mode=mode,
    )
    if readiness.get("status") != "ok" or not readiness.get("ready"):
        blockers = readiness.get("blockers") or [readiness.get("message") or "The week is not ready."]
        return {"status": "not_ready", "message": " ".join(blockers)}
    # The older unapproved suggestion is retired inside propose_week_draft's
    # insert transaction, only once its replacement exists — retiring it here
    # first left the week with nothing when the rebuild was refused.
    result = await propose_week_draft(
        company_id=company_id,
        actor_user_id=actor_user_id,
        actor_role=actor_role,
        thread_id=None,
        location_id=location_id,
        week_start=week_start,
        source_mode=mode,
        week_template_id=str(week_template_id) if week_template_id else None,
        origin="automatic",
        supersede_proposed=supersede_proposed,
    )
    if result.get("status") == "ready":
        return {
            "status": "generated",
            "message": "Huume prepared a schedule suggestion for manager review.",
            "generation_run_id": result.get("generation_run_id"),
        }
    if result.get("status") == "skipped":
        # Lost the insert race to another build of the same week; which state
        # won is not known here.
        return already_present_result(week_start=week_start, blocking_status=None)
    return {"status": "not_ready", "message": result.get("message") or "The week is not ready."}
