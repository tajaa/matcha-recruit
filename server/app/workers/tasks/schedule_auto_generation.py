"""Execute one tenant-configured, review-only schedule automation rule."""

import asyncio
import logging
from datetime import datetime, timedelta, timezone
from uuid import UUID

from app.core.feature_flags import merge_company_features
from app.matcha.services.scheduling.schedule_automation import (
    generate_review_suggestion,
    next_run_at,
    target_week_start,
)

from ..celery_app import celery_app
from ..utils import get_db_connection


logger = logging.getLogger(__name__)


def enqueue_schedule_automation(rule_id: UUID, schedule_version: int, scheduled_for: datetime) -> None:
    """Publish the exact rule/version occurrence; edited rules make it stale."""
    run_schedule_auto_generation.apply_async(
        args=[str(rule_id), schedule_version, scheduled_for.isoformat()],
        eta=scheduled_for,
    )


def supports_automatic_generation(enabled_features, signup_source: str | None) -> bool:
    features = merge_company_features(enabled_features, signup_source)
    return all(features.get(key) for key in ("employee_schedule", "huume", "matcha_work"))


async def _run(rule_id: str, schedule_version: int, scheduled_for: str) -> dict:
    rule_uuid = UUID(rule_id)
    expected_at = datetime.fromisoformat(scheduled_for)
    if expected_at.tzinfo is None:
        expected_at = expected_at.replace(tzinfo=timezone.utc)
    expected_at = expected_at.astimezone(timezone.utc)

    conn = await get_db_connection()
    try:
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
        if rule["company_status"] not in (None, "approved") or not supports_automatic_generation(
            rule["enabled_features"], rule["signup_source"],
        ):
            await conn.execute(
                """UPDATE schedule_automation_rules
                   SET enabled=false, next_run_at=NULL, last_attempt_at=NOW(),
                       last_completed_at=NOW(), last_status='feature_disabled',
                       last_message='Required scheduling or Huume features are not enabled.', updated_at=NOW()
                   WHERE id=$1""",
                rule_uuid,
            )
            return {"skipped": True, "reason": "feature_disabled"}

        following_at = None
        following_enabled = False
        if rule["cadence"] == "weekly":
            following_at = next_run_at(
                cadence="weekly",
                timezone_name=rule["timezone"],
                run_time=rule["run_time"],
                run_weekday=rule["run_weekday"],
                after=expected_at + timedelta(seconds=1),
            )
            following_enabled = True
        claim = await conn.execute(
            """UPDATE schedule_automation_rules
               SET next_run_at=$1, enabled=$2, last_attempt_at=NOW(),
                   last_status='running', last_message=NULL, updated_at=NOW()
               WHERE id=$3 AND schedule_version=$4 AND enabled=true AND next_run_at=$5""",
            following_at, following_enabled, rule_uuid, schedule_version, expected_at,
        )
        if claim == "UPDATE 0":
            return {"skipped": True, "reason": "already_claimed"}
        # Queue the following occurrence immediately after the DB claim. A
        # planner failure (or worker death during planning) must not silently
        # erase the recurring rule's future cadence.
        if following_at:
            enqueue_schedule_automation(rule_uuid, schedule_version, following_at)

        week_start = target_week_start(
            cadence=rule["cadence"],
            scheduled_for=expected_at,
            timezone_name=rule["timezone"],
            target_weeks_ahead=rule["target_weeks_ahead"],
            one_time_week_start=rule["target_week_start"],
        )
        try:
            if rule["week_template_id"] is None:
                result = {"status": "not_ready", "message": "Choose a saved week template."}
            else:
                result = await generate_review_suggestion(
                    company_id=rule["company_id"],
                    location_id=rule["location_id"],
                    week_start=week_start,
                    week_template_id=rule["week_template_id"],
                )
        except Exception as exc:
            logger.exception("Schedule planner failed rule=%s", rule_uuid)
            result = {"status": "failed", "message": str(exc)[:1000]}
        generation_id = result.get("generation_run_id")
        await conn.execute(
            """UPDATE schedule_automation_rules
               SET last_completed_at=NOW(), last_status=$1, last_message=$2,
                   last_generation_run_id=$3, updated_at=NOW()
               WHERE id=$4 AND schedule_version=$5""",
            result["status"], result.get("message"), UUID(generation_id) if generation_id else None,
            rule_uuid, schedule_version,
        )
        return {**result, "week_start": week_start.isoformat(), "next_run_at": following_at}
    finally:
        await conn.close()


@celery_app.task(name="schedule_auto_generation.run", bind=True, max_retries=1)
def run_schedule_auto_generation(self, rule_id: str, schedule_version: int, scheduled_for: str):
    try:
        return asyncio.run(_run(rule_id, schedule_version, scheduled_for))
    except Exception as exc:
        logger.exception("Schedule automation failed rule=%s", rule_id)
        raise self.retry(exc=exc, countdown=120)
