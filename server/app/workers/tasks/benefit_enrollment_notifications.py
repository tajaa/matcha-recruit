"""Celery task: benefit open-enrollment auto-transitions + reminder emails.

Periodic (re-dispatched on every ~15-min worker startup, gated by the
`benefit_enrollment_notifications` row in scheduler_settings — seeded
DISABLED). Separate from `benefit_eligibility_sync` on purpose: that task
also runs for broker-linked companies WITHOUT `benefits_admin` — enrollment
emails must never fire there, and the two switches need to move
independently.

Per cycle:
  1. Auto-transition OE periods (draft->open, open->closed) and expire life
     events whose window has lapsed — set-based, all companies (rows only
     exist where the workflow was used).
  2. For each company with `benefits_admin` on: send window_opened /
     unsubmitted_nudge / closing_soon emails, deduped via
     benefit_enrollment_notices (claim-before-send).

Email builders + policy constants live in `services/benefits_enrollment.py`
so they're unit-testable without a worker.
"""
import asyncio
import logging
from datetime import date

from ..celery_app import celery_app
from ..utils import get_db_connection, scheduler_settings_row
from app.config import get_settings
from app.core.services.email import get_email_service
from app.matcha.services.benefits_enrollment import (
    CLOSING_SOON_DAYS,
    NUDGE_AFTER_DAYS,
    build_closing_soon_email,
    build_unsubmitted_nudge_email,
    build_window_opened_email,
)

logger = logging.getLogger(__name__)

DEFAULT_MAX_PER_CYCLE = 500


async def _auto_transition(conn) -> dict:
    opened = await conn.fetch(
        """
        UPDATE open_enrollment_periods
        SET status = 'open', opened_at = NOW(), updated_at = NOW()
        WHERE status = 'draft' AND starts_on <= CURRENT_DATE
        RETURNING id
        """
    )
    closed = await conn.fetch(
        """
        UPDATE open_enrollment_periods
        SET status = 'closed', closed_at = NOW(), updated_at = NOW()
        WHERE status = 'open' AND ends_on < CURRENT_DATE
        RETURNING id
        """
    )
    expired = await conn.fetch(
        """
        UPDATE life_event_changes
        SET status = 'expired', updated_at = NOW()
        WHERE status = 'approved' AND window_ends_on < CURRENT_DATE
        RETURNING id
        """
    )
    return {"opened": len(opened), "closed": len(closed), "expired_life_events": len(expired)}


async def _claim_notice(conn, period_id, employee_id, notice_type: str) -> bool:
    row = await conn.fetchval(
        """
        INSERT INTO benefit_enrollment_notices (company_id, open_enrollment_period_id, employee_id, notice_type)
        SELECT company_id, $1, $2, $3 FROM open_enrollment_periods WHERE id = $1
        ON CONFLICT (open_enrollment_period_id, employee_id, notice_type) DO NOTHING
        RETURNING id
        """,
        period_id, employee_id, notice_type,
    )
    return row is not None


async def _release_notice(conn, period_id, employee_id, notice_type: str) -> None:
    await conn.execute(
        "DELETE FROM benefit_enrollment_notices "
        "WHERE open_enrollment_period_id = $1 AND employee_id = $2 AND notice_type = $3",
        period_id, employee_id, notice_type,
    )


async def _send_and_claim(conn, period_id, employee, notice_type: str, subject: str, html: str, budget: dict) -> bool:
    if budget["sent"] >= budget["max"]:
        return False
    claimed = await _claim_notice(conn, period_id, employee["id"], notice_type)
    if not claimed:
        return False
    ok = await get_email_service().send_email(
        employee["email"], f"{employee['first_name']} {employee['last_name']}", subject, html,
    )
    if not ok:
        await _release_notice(conn, period_id, employee["id"], notice_type)
        return False
    budget["sent"] += 1
    return True


async def _run() -> dict:
    conn = await get_db_connection()
    try:
        transitions = await _auto_transition(conn)

        row = await scheduler_settings_row(conn, "benefit_enrollment_notifications")
        max_per_cycle = row["max_per_cycle"] if row and row["max_per_cycle"] else DEFAULT_MAX_PER_CYCLE
        budget = {"sent": 0, "max": max_per_cycle}

        settings = get_settings()
        today = date.today()

        companies = await conn.fetch(
            "SELECT id FROM companies WHERE COALESCE(enabled_features->>'benefits_admin', 'false') = 'true'"
        )
        window_opened = 0
        nudged = 0
        closing_soon = 0
        failed = 0

        for c in companies:
            if budget["sent"] >= budget["max"]:
                break
            try:
                periods = await conn.fetch(
                    "SELECT * FROM open_enrollment_periods WHERE company_id = $1 AND status = 'open'",
                    c["id"],
                )
                for period in periods:
                    employees = await conn.fetch(
                        """
                        SELECT id, email, first_name, last_name
                        FROM employees
                        WHERE org_id = $1
                          AND email IS NOT NULL AND email != ''
                          AND employment_status NOT IN ('terminated', 'offboarded')
                        """,
                        c["id"],
                    )
                    not_submitted_ids = {
                        r["employee_id"] for r in await conn.fetch(
                            """
                            SELECT employee_id FROM benefit_elections
                            WHERE open_enrollment_period_id = $1 AND status IN ('submitted', 'approved')
                            """,
                            period["id"],
                        )
                    }

                    for employee in employees:
                        if budget["sent"] >= budget["max"]:
                            break

                        subject, html = build_window_opened_email(period["name"], period["ends_on"], settings.app_base_url)
                        if await _send_and_claim(conn, period["id"], employee, "window_opened", subject, html, budget):
                            window_opened += 1

                        if employee["id"] in not_submitted_ids:
                            continue

                        opened_at = period["opened_at"].date() if period["opened_at"] else period["starts_on"]
                        if (today - opened_at).days >= NUDGE_AFTER_DAYS:
                            subject, html = build_unsubmitted_nudge_email(period["name"], period["ends_on"], settings.app_base_url)
                            if await _send_and_claim(conn, period["id"], employee, "unsubmitted_nudge", subject, html, budget):
                                nudged += 1

                        if 0 <= (period["ends_on"] - today).days <= CLOSING_SOON_DAYS:
                            subject, html = build_closing_soon_email(period["name"], period["ends_on"], settings.app_base_url)
                            if await _send_and_claim(conn, period["id"], employee, "closing_soon", subject, html, budget):
                                closing_soon += 1
            except Exception as exc:  # noqa: BLE001 — one bad company shouldn't stop the run
                failed += 1
                logger.warning("benefit_enrollment_notifications: company %s failed: %s", c["id"], exc)
    finally:
        await conn.close()

    summary = {
        **transitions,
        "window_opened_sent": window_opened,
        "nudged_sent": nudged,
        "closing_soon_sent": closing_soon,
        "failed_companies": failed,
    }
    logger.info("benefit_enrollment_notifications complete: %s", summary)
    return summary


@celery_app.task(bind=True, max_retries=3)
def run_benefit_enrollment_notifications(self):
    """Entry point dispatched by ``@worker_ready`` when the scheduler row is enabled."""
    return asyncio.run(_run())
