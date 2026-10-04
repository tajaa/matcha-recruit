"""Durable, bounded dispatch of tenant-configured schedule suggestions."""

import asyncio
import logging
from datetime import datetime, timedelta, timezone
from uuid import UUID

from app.core.feature_flags import merge_company_features
from app.matcha.services.scheduling.location_profile import resolve_week_start_weekday
from app.matcha.services.scheduling.schedule_automation import (
    generate_review_suggestion,
    next_run_at,
    past_week_refusal,
    target_week_start,
)

from ..celery_app import celery_app
from ..utils import get_db_connection


logger = logging.getLogger(__name__)
DISPATCH_TASK_KEY = "schedule_auto_generation_dispatch"
DISPATCH_SECONDS = 60
DISPATCH_HORIZON_SECONDS = 120
# Longer than the worker's ten-minute hard time limit. A killed worker's
# current occurrence stays durable and becomes eligible for recovery here.
DISPATCH_LEASE_SECONDS = 660
# One occurrence is retried for this long after its first attempt, then it is
# recorded as failed and the rule moves on. Without the bound a planner that
# always raises (or always dies) replays the same occurrence on every lease
# expiry until its target week has passed.
RETRY_WINDOW_SECONDS = 1800
# Attempts start at or after their occurrence; the slack only absorbs clock
# skew between the worker and Postgres.
_ATTEMPT_CLOCK_SLACK = timedelta(minutes=5)
_RETRYING_MESSAGE = "Huume hit a problem preparing this week and will retry automatically."
_FAILED_MESSAGE = (
    "Huume could not prepare this week after several attempts. "
    "Use Run now to try again."
)


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


def enqueue_schedule_automation(rule_id: UUID, schedule_version: int, scheduled_for: datetime) -> bool:
    """Only publish near-term occurrences; distant timers remain in Postgres."""
    now = _utcnow()
    if scheduled_for > now + timedelta(seconds=DISPATCH_HORIZON_SECONDS):
        return False
    run_schedule_auto_generation.apply_async(
        args=[str(rule_id), schedule_version, scheduled_for.isoformat()],
        eta=max(now, scheduled_for),
    )
    return True


def supports_automatic_generation(
    enabled_features, signup_source: str | None, mode: str = "template",
) -> bool:
    features = merge_company_features(enabled_features, signup_source)
    required = ["employee_schedule", "huume", "matcha_work"]
    if mode == "autopilot":
        required.append("schedule_autopilot")
    return all(features.get(key) for key in required)


async def _run(rule_id: str, schedule_version: int, scheduled_for: str) -> dict:
    rule_uuid = UUID(rule_id)
    expected_at = datetime.fromisoformat(scheduled_for)
    if expected_at.tzinfo is None:
        expected_at = expected_at.replace(tzinfo=timezone.utc)
    expected_at = expected_at.astimezone(timezone.utc)

    conn = await get_db_connection()
    try:
        # Session-scoped: a crash releases it, without advancing the durable
        # occurrence. Saves can still invalidate the version during planning.
        locked = await conn.fetchval(
            "SELECT pg_try_advisory_lock(hashtextextended($1, 0))",
            f"schedule-auto:{rule_uuid}",
        )
        if not locked:
            return {"skipped": True, "reason": "already_running"}
        rule = await conn.fetchrow(
            """
            SELECT r.*, l.timezone, c.enabled_features, c.signup_source, c.status AS company_status
            FROM schedule_automation_rules r
            JOIN business_locations l ON l.id=r.location_id AND l.company_id=r.company_id
            JOIN companies c ON c.id=r.company_id
            WHERE r.id=$1 AND l.is_active IS NOT FALSE
            """,
            rule_uuid,
        )
        if not rule or not rule["enabled"] or rule["schedule_version"] != schedule_version:
            return {"skipped": True, "reason": "stale_or_disabled_rule"}
        if rule["next_run_at"] != expected_at:
            return {"skipped": True, "reason": "superseded_occurrence"}
        mode = rule.get("mode") or "template"
        if rule["company_status"] not in (None, "approved") or not supports_automatic_generation(
            rule["enabled_features"], rule["signup_source"], mode,
        ):
            disabled = await conn.execute(
                """UPDATE schedule_automation_rules
                   SET enabled=false, next_run_at=NULL, last_attempt_at=NOW(),
                       last_completed_at=NOW(), last_status='feature_disabled',
                       last_message='Required scheduling or Huume features are not enabled.', updated_at=NOW()
                   WHERE id=$1 AND schedule_version=$2 AND enabled=true AND next_run_at=$3""",
                rule_uuid, schedule_version, expected_at,
            )
            return {"skipped": True, "reason": "feature_disabled" if disabled != "UPDATE 0" else "stale_or_disabled_rule"}

        # A retry keeps the occurrence's first attempt time, so the retry
        # window is measured across Celery retries and lease recoveries.
        now = _utcnow()
        previous_attempt = rule.get("last_attempt_at")
        first_attempt_at = (
            previous_attempt
            if previous_attempt is not None and previous_attempt >= expected_at - _ATTEMPT_CLOCK_SLACK
            else now
        )
        claim = await conn.execute(
            """UPDATE schedule_automation_rules
               SET last_attempt_at=$4, last_status='running', last_message=NULL, updated_at=NOW()
               WHERE id=$1 AND schedule_version=$2 AND enabled=true AND next_run_at=$3""",
            rule_uuid, schedule_version, expected_at, first_attempt_at,
        )
        if claim == "UPDATE 0":
            return {"skipped": True, "reason": "already_claimed"}

        async def finish(result: dict) -> dict:
            """Record a terminal result and advance to the following occurrence."""
            following_at = None
            if rule["cadence"] == "weekly":
                following_at = next_run_at(
                    cadence="weekly", timezone_name=rule["timezone"],
                    run_time=rule["run_time"], run_weekday=rule["run_weekday"],
                    # A long outage must not replay every missed week before
                    # reaching a future occurrence.
                    after=max(expected_at + timedelta(seconds=1), _utcnow()),
                )
            generation_id = result.get("generation_run_id")
            completed = await conn.execute(
                """UPDATE schedule_automation_rules
                   SET last_completed_at=NOW(), last_status=$1, last_message=$2,
                       last_generation_run_id=$3, next_run_at=$6, enabled=$7, updated_at=NOW()
                   WHERE id=$4 AND schedule_version=$5 AND enabled=true AND next_run_at=$8""",
                result["status"], result.get("message"), UUID(generation_id) if generation_id else None,
                rule_uuid, schedule_version, following_at, following_at is not None, expected_at,
            )
            if completed == "UPDATE 0":
                return {"skipped": True, "reason": "stale_or_disabled_rule"}
            return {**result, "next_run_at": following_at}

        failed = {"status": "failed", "message": _FAILED_MESSAGE}
        retry_age = (now - first_attempt_at).total_seconds()
        if retry_age >= RETRY_WINDOW_SECONDS + DISPATCH_LEASE_SECONDS:
            # Every attempt inside the window died without reaching the
            # handler below (hard time limit, killed worker). Stop here
            # rather than run the same occurrence into the same death.
            logger.error("Schedule automation abandoned after repeated worker deaths rule=%s", rule_uuid)
            return await finish(failed)
        try:
            week_start_weekday = await resolve_week_start_weekday(
                conn, company_id=rule["company_id"], location_id=rule["location_id"],
            )
            week_start = target_week_start(
                cadence=rule["cadence"], scheduled_for=expected_at,
                timezone_name=rule["timezone"], target_weeks_ahead=rule["target_weeks_ahead"],
                one_time_week_start=rule["target_week_start"], week_start_weekday=week_start_weekday,
            )
            stale_target = past_week_refusal(
                week_start=week_start, timezone_name=rule["timezone"],
                week_start_weekday=week_start_weekday, now=max(expected_at, _utcnow()),
            )
            if stale_target:
                result = stale_target
            elif mode == "template" and rule["week_template_id"] is None:
                result = {"status": "not_ready", "message": "Choose a saved week template."}
            else:
                kwargs = {
                    "company_id": rule["company_id"], "location_id": rule["location_id"],
                    "week_start": week_start, "week_template_id": rule["week_template_id"],
                }
                if mode == "autopilot":
                    kwargs["mode"] = mode
                result = await generate_review_suggestion(**kwargs)
            finished = await finish(result)
            return finished if finished.get("skipped") else {**finished, "week_start": week_start.isoformat()}
        except Exception:
            if retry_age >= RETRY_WINDOW_SECONDS:
                # The retry window is spent: record the failure and move on,
                # as a deterministic planner error would otherwise replay
                # until the target week had passed.
                logger.exception("Schedule automation failed permanently rule=%s", rule_uuid)
                return await finish(failed)
            # Keep the current occurrence pending for Celery retry and the
            # dispatcher. A proposal already inserted is found idempotently
            # on replay if the completion write was interrupted. The cause
            # is logged by the task wrapper, not shown to the manager.
            try:
                await conn.execute(
                    """UPDATE schedule_automation_rules
                       SET last_status='retrying', last_message=$1, updated_at=NOW()
                       WHERE id=$2 AND schedule_version=$3 AND enabled=true AND next_run_at=$4""",
                    _RETRYING_MESSAGE, rule_uuid, schedule_version, expected_at,
                )
            except Exception:
                logger.exception("Could not record schedule automation retry rule=%s", rule_uuid)
            raise
    finally:
        # Closing the raw connection also releases its advisory lock.
        await conn.close()


async def _dispatch() -> dict:
    """Recover durable occurrences and publish at most a bounded near-term batch."""
    conn = await get_db_connection()
    try:
        # Existing scheduler infrastructure, no schema change. Never overwrite
        # an operator's explicit disable or configured cycle limit.
        await conn.execute(
            """INSERT INTO scheduler_settings(task_key, display_name, description, enabled, max_per_cycle)
               VALUES($1, 'Auto schedule dispatch',
                      'Recovers pending location rules and queues only near-term review suggestions.', true, 100)
               ON CONFLICT (task_key) DO NOTHING""",
            DISPATCH_TASK_KEY,
        )
        settings = await conn.fetchrow(
            "SELECT enabled, max_per_cycle FROM scheduler_settings WHERE task_key=$1", DISPATCH_TASK_KEY,
        )
        if not settings or not settings["enabled"]:
            return {"skipped": True, "reason": "disabled", "reschedule": False}
        claimed = await conn.fetchval(
            """UPDATE scheduler_settings SET last_run_at=NOW()
               WHERE task_key=$1 AND enabled=true
                 AND (last_run_at IS NULL OR last_run_at < NOW() - make_interval(secs => $2))
               RETURNING true""",
            DISPATCH_TASK_KEY, int(DISPATCH_SECONDS * 0.75),
        )
        if not claimed:
            return {"skipped": True, "reason": "another_chain", "reschedule": False}
        limit = max(1, min(int(settings["max_per_cycle"] or 100), 1000))
        horizon = _utcnow() + timedelta(seconds=DISPATCH_HORIZON_SECONDS)
        rules = await conn.fetch(
            """SELECT r.id, r.schedule_version, r.next_run_at
               FROM schedule_automation_rules r
               JOIN business_locations l ON l.id=r.location_id AND l.company_id=r.company_id
               WHERE r.enabled=true AND r.next_run_at <= $1 AND l.is_active IS NOT FALSE
                 AND (r.last_status IS NULL OR r.last_status NOT IN ('queued', 'running', 'retrying')
                      OR r.updated_at < NOW() - make_interval(secs => $2))
               ORDER BY r.next_run_at, r.id LIMIT $3""",
            horizon, DISPATCH_LEASE_SECONDS, limit,
        )
        queued, failed = 0, 0
        for rule in rules:
            queued_claim = await conn.execute(
                """UPDATE schedule_automation_rules SET last_status='queued', updated_at=NOW()
                   WHERE id=$1 AND schedule_version=$2 AND enabled=true AND next_run_at=$3
                     AND (last_status IS NULL OR last_status NOT IN ('queued', 'running', 'retrying')
                          OR updated_at < NOW() - make_interval(secs => $4))""",
                rule["id"], rule["schedule_version"], rule["next_run_at"], DISPATCH_LEASE_SECONDS,
            )
            if queued_claim == "UPDATE 0":
                continue
            try:
                published = enqueue_schedule_automation(rule["id"], rule["schedule_version"], rule["next_run_at"])
                if published is False:
                    raise RuntimeError("Occurrence moved beyond the short dispatch horizon; waiting for recovery.")
                queued += 1
            except Exception as exc:
                failed += 1
                logger.exception("Could not dispatch schedule automation rule=%s", rule["id"])
                # Publication can fail after the queue lease was persisted.
                # Release it for the next sweep; a death before this write is
                # repaired by lease expiry. A started task wins the predicate.
                await conn.execute(
                    """UPDATE schedule_automation_rules
                       SET last_status='dispatch_failed', last_message=$1, updated_at=NOW()
                       WHERE id=$2 AND schedule_version=$3 AND enabled=true AND next_run_at=$4
                         AND last_status='queued'""",
                    str(exc)[:1000], rule["id"], rule["schedule_version"], rule["next_run_at"],
                )
        return {"queued": queued, "failed": failed, "reschedule": True}
    finally:
        await conn.close()


def _reschedule_dispatch() -> None:
    try:
        dispatch_schedule_automation.apply_async(countdown=DISPATCH_SECONDS)
    except Exception:
        logger.exception("Auto schedule dispatch could not re-enqueue; worker startup resumes recovery")


@celery_app.task(name="schedule_auto_generation.dispatch")
def dispatch_schedule_automation(resume: bool = False):
    try:
        result = asyncio.run(_dispatch())
    except Exception:
        _reschedule_dispatch()
        raise
    # Worker startup passes resume=True. When it loses the claim to a sweep
    # that ran moments before the previous worker died, that sweep's countdown
    # message may have died with it; one plain follow-up either finds the
    # chain alive and stops, or takes it over.
    if result.pop("reschedule", False) or (resume and result.get("reason") == "another_chain"):
        _reschedule_dispatch()
    return result


@celery_app.task(name="schedule_auto_generation.run", bind=True, max_retries=1)
def run_schedule_auto_generation(self, rule_id: str, schedule_version: int, scheduled_for: str):
    try:
        return asyncio.run(_run(rule_id, schedule_version, scheduled_for))
    except Exception as exc:
        logger.exception("Schedule automation failed rule=%s", rule_id)
        raise self.retry(exc=exc, countdown=120)
