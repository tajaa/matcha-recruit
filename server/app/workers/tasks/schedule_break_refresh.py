"""Refresh future shift break guidance after an employee fact changes."""

import asyncio
import logging
from datetime import date, datetime
from uuid import UUID

from ..celery_app import celery_app
from ..utils import get_db_connection

logger = logging.getLogger(__name__)

_PAGE_SIZE = 100


async def _refresh_employee_breaks(
    *,
    company_id: UUID,
    employee_id: UUID,
    actor_user_id: UUID | None,
    source: str,
    effective_from: date | None,
    cursor_start: datetime | None = None,
    cursor_id: UUID | None = None,
) -> dict:
    """Refresh one deterministic page so retries resume instead of looping."""
    from app.matcha.services.scheduling.schedule_guidance import (
        refresh_assignment_break_guidance_and_minimum,
    )

    conn = await get_db_connection()
    refreshed = 0
    try:
        rows = await conn.fetch(
            """
            SELECT s.id AS shift_id, s.starts_at
            FROM schedule_shift_assignments a
            JOIN schedule_shifts s ON s.id = a.shift_id
            LEFT JOIN business_locations l ON l.id = s.location_id
            LEFT JOIN pg_timezone_names tz ON tz.name = l.timezone
            WHERE a.company_id = $1 AND a.employee_id = $2
              AND s.status <> 'cancelled'
              AND s.location_id IS NOT NULL
              AND s.starts_at::date >= CASE
                    WHEN $3::date IS NULL
                        THEN (NOW() AT TIME ZONE COALESCE(tz.name, 'UTC'))::date
                    ELSE GREATEST(
                        $3::date,
                            (NOW() AT TIME ZONE COALESCE(tz.name, 'UTC'))::date
                    )
                  END
              AND (
                    $4::timestamptz IS NULL
                    OR (s.starts_at, s.id) > ($4::timestamptz, $5::uuid)
                  )
            ORDER BY s.starts_at, s.id
            LIMIT $6
            """,
            company_id, employee_id, effective_from,
            cursor_start, cursor_id, _PAGE_SIZE,
        )
        if rows:
            async with conn.transaction():
                for row in rows:
                    await refresh_assignment_break_guidance_and_minimum(
                        conn, company_id, shift_id=row["shift_id"],
                        employee_id=employee_id, actor_user_id=actor_user_id,
                        source=source,
                    )
                    refreshed += 1
        return {
            "refreshed": refreshed,
            "has_more": len(rows) == _PAGE_SIZE,
            "cursor_start": rows[-1]["starts_at"].isoformat() if rows else None,
            "cursor_id": str(rows[-1]["shift_id"]) if rows else None,
        }
    finally:
        await conn.close()


async def _stale_employee_facts() -> list[dict]:
    """Find committed employee/rule facts whose future guidance is stale."""
    conn = await get_db_connection()
    try:
        return await conn.fetch(
            """
            WITH RECURSIVE jurisdiction_descendants AS (
                SELECT id AS ancestor_id, id AS descendant_id
                FROM jurisdictions
                UNION ALL
                SELECT d.ancestor_id, j.id
                FROM jurisdiction_descendants d
                JOIN jurisdictions j ON j.parent_id = d.descendant_id
            ), latest_facts AS (
                SELECT company_id, employee_id, MAX(changed_at) AS changed_at
                FROM (
                    SELECT company_id, employee_id, confirmed_at AS changed_at
                    FROM employee_compliance_attestations
                    WHERE attestation_type = 'meal_break_waiver_on_file'
                    UNION ALL
                    SELECT org_id AS company_id, employee_id, updated_at AS changed_at
                    FROM employee_demographics
                ) facts
                GROUP BY company_id, employee_id
            )
            SELECT DISTINCT a.company_id, a.employee_id
            FROM schedule_shift_assignments a
            JOIN schedule_shifts s ON s.id = a.shift_id
            JOIN business_locations l ON l.id = s.location_id
            LEFT JOIN pg_timezone_names tz ON tz.name = l.timezone
            LEFT JOIN latest_facts f
              ON f.company_id = a.company_id AND f.employee_id = a.employee_id
            WHERE s.status <> 'cancelled'
              AND s.starts_at::date >=
                  (NOW() AT TIME ZONE COALESCE(tz.name, 'UTC'))::date
              AND (
                  a.guidance_evaluated_at IS NULL
                  OR (f.changed_at IS NOT NULL AND a.guidance_evaluated_at < f.changed_at)
                  OR EXISTS (
                      SELECT 1
                      FROM schedule_break_rule_sets r
                      JOIN jurisdiction_descendants d
                        ON d.ancestor_id = r.jurisdiction_id
                       AND d.descendant_id = l.jurisdiction_id
                      WHERE r.is_active = true
                        AND r.updated_at > a.guidance_evaluated_at
                        AND r.effective_from <= s.starts_at::date
                        AND (r.effective_to IS NULL OR r.effective_to >= s.starts_at::date)
                  )
              )
            ORDER BY a.company_id, a.employee_id
            LIMIT 500
            """
        )
    finally:
        await conn.close()


def enqueue_employee_schedule_break_refresh(
    *,
    company_id: UUID,
    employee_id: UUID,
    actor_user_id: UUID | None,
    source: str,
    effective_from: date | None = None,
) -> bool:
    """Best-effort fast dispatch; committed facts remain recovery records."""
    try:
        refresh_employee_schedule_breaks.delay(
            str(company_id), str(employee_id),
            str(actor_user_id) if actor_user_id else None,
            source, effective_from.isoformat() if effective_from else None,
        )
        return True
    except Exception:
        # The worker-ready recovery scan compares fact timestamps with stored
        # guidance and will rediscover this employee after the broker returns.
        logger.exception("Could not enqueue employee schedule break refresh")
        return False


def enqueue_schedule_break_recovery() -> bool:
    """Prompt the durable stale-fact scan after a rule status transition."""
    try:
        recover_stale_employee_schedule_breaks.delay()
        return True
    except Exception:
        logger.exception("Could not enqueue schedule break recovery")
        return False


@celery_app.task(name="schedule_breaks.refresh_employee", bind=True, max_retries=3)
def refresh_employee_schedule_breaks(
    self,
    company_id: str,
    employee_id: str,
    actor_user_id: str | None,
    source: str,
    effective_from: str | None = None,
    cursor_start: str | None = None,
    cursor_id: str | None = None,
):
    try:
        result = asyncio.run(_refresh_employee_breaks(
            company_id=UUID(company_id),
            employee_id=UUID(employee_id),
            actor_user_id=UUID(actor_user_id) if actor_user_id else None,
            source=source,
            effective_from=date.fromisoformat(effective_from) if effective_from else None,
            cursor_start=datetime.fromisoformat(cursor_start) if cursor_start else None,
            cursor_id=UUID(cursor_id) if cursor_id else None,
        ))
        if result["has_more"]:
            refresh_employee_schedule_breaks.delay(
                company_id, employee_id, actor_user_id, source, effective_from,
                result["cursor_start"], result["cursor_id"],
            )
        return result
    except Exception as exc:
        logger.exception("Employee schedule break refresh failed")
        raise self.retry(exc=exc, countdown=60)


@celery_app.task(name="schedule_breaks.recover_stale", bind=True, max_retries=1)
def recover_stale_employee_schedule_breaks(self):
    try:
        rows = asyncio.run(_stale_employee_facts())
        for row in rows:
            refresh_employee_schedule_breaks.delay(
                str(row["company_id"]), str(row["employee_id"]), None,
                "employee_fact_recovery", None,
            )
        return {"employees": len(rows)}
    except Exception as exc:
        logger.exception("Stale employee schedule break recovery failed")
        raise self.retry(exc=exc, countdown=120)
