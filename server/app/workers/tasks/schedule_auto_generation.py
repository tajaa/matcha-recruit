"""Prepare next-week schedule proposals for manager review.

The worker is intentionally deterministic and review-only: it creates a
``schedule_generation_runs`` proposal but never creates or publishes shifts.
The schedule assistant adopts the proposal when an authorized manager opens
that location/week.
"""

import asyncio
import logging
from datetime import date, datetime, timedelta, timezone
from zoneinfo import ZoneInfo

from app.core.feature_flags import merge_company_features

from ..celery_app import celery_app
from ..utils import get_db_connection, scheduler_settings_row


logger = logging.getLogger(__name__)
TASK_KEY = "schedule_auto_generation"


def upcoming_week_start(today: date) -> date:
    """Return the Sunday beginning the next editor week."""
    current_sunday = today - timedelta(days=(today.weekday() + 1) % 7)
    return current_sunday + timedelta(days=7)


def location_today(timezone_name: str | None) -> date:
    try:
        zone = ZoneInfo(timezone_name or "UTC")
    except (KeyError, ValueError):
        zone = timezone.utc
    return datetime.now(zone).date()


def supports_automatic_generation(enabled_features, signup_source: str | None) -> bool:
    features = merge_company_features(enabled_features, signup_source)
    return all(features.get(key) for key in ("employee_schedule", "huume", "matcha_work"))


async def _run() -> dict:
    conn = await get_db_connection()
    try:
        settings = await scheduler_settings_row(conn, TASK_KEY)
        if not settings:
            return {"skipped": True, "reason": "scheduler_not_registered"}
        if not settings["enabled"]:
            return {"skipped": True, "reason": "scheduler_disabled"}
        max_per_cycle = max(1, min(int(settings["max_per_cycle"] or 100), 1_000))
        locations = await conn.fetch(
            """
            SELECT l.id AS location_id, l.company_id, l.timezone,
                   c.enabled_features, c.signup_source
            FROM business_locations l
            JOIN companies c ON c.id=l.company_id
            WHERE l.is_active IS NOT FALSE
              AND (c.status IS NULL OR c.status='approved')
            ORDER BY l.company_id, l.id
            """
        )
        generated = 0
        already_present = 0
        not_ready = 0
        failures = 0
        eligible_locations = 0
        from app.matcha.services.scheduling.week_builder import (
            get_week_build_readiness,
            propose_week_draft,
        )

        for location in locations:
            if generated >= max_per_cycle:
                break
            if not supports_automatic_generation(
                location["enabled_features"], location["signup_source"],
            ):
                continue
            eligible_locations += 1
            week_start = upcoming_week_start(location_today(location["timezone"]))
            has_active_run = await conn.fetchval(
                """
                SELECT EXISTS (
                    SELECT 1 FROM schedule_generation_runs
                    WHERE company_id=$1 AND location_id=$2 AND week_start=$3
                      AND (
                          status IN ('proposed', 'applied')
                          OR (origin='automatic' AND status='cancelled')
                      )
                )
                """,
                location["company_id"], location["location_id"], week_start,
            )
            if has_active_run:
                already_present += 1
                continue
            try:
                readiness = await get_week_build_readiness(
                    company_id=location["company_id"],
                    location_id=location["location_id"],
                    week_start=week_start,
                )
                if readiness.get("status") != "ok" or not readiness.get("ready"):
                    not_ready += 1
                    continue
                result = await propose_week_draft(
                    company_id=location["company_id"],
                    actor_user_id=None,
                    thread_id=None,
                    location_id=location["location_id"],
                    week_start=week_start,
                    source_mode="auto",
                    origin="automatic",
                )
            except Exception:
                failures += 1
                logger.exception(
                    "Automatic schedule generation failed company=%s location=%s week=%s",
                    location["company_id"], location["location_id"], week_start,
                )
                continue
            if result.get("status") == "ready":
                generated += 1
            elif result.get("status") == "skipped":
                already_present += 1
            else:
                # Missing availability, demand, or an unambiguous template is
                # expected setup state, not a failed worker run.
                not_ready += 1
        return {
            "locations_checked": len(locations),
            "eligible_locations": eligible_locations,
            "generated": generated,
            "already_present": already_present,
            "not_ready": not_ready,
            "failures": failures,
        }
    finally:
        await conn.close()


@celery_app.task(name="schedule_auto_generation.run", bind=True, max_retries=1)
def run_schedule_auto_generation(self):
    try:
        return asyncio.run(_run())
    except Exception as exc:
        logger.exception("Automatic schedule generation sweep failed")
        raise self.retry(exc=exc, countdown=120)
