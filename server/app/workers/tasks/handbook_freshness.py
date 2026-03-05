"""
Celery tasks for scheduled handbook freshness checks.

These tasks check published handbooks for stale content on a schedule
via the systemd timer that restarts the Celery worker every 15 minutes.
"""

import asyncio
from typing import Optional

from ..celery_app import celery_app
from ..notifications import publish_task_complete, publish_task_error
from ..utils import get_db_connection


async def _run_single_freshness_check(handbook_id: str, company_id: str) -> dict:
    """Run a freshness check for a single handbook."""
    from app.core.services.handbook_service import HandbookService

    result = await HandbookService.run_freshness_check(
        handbook_id=handbook_id,
        company_id=company_id,
        check_type="scheduled",
    )
    if result is None:
        return {"handbook_id": handbook_id, "status": "not_found"}
    return {
        "handbook_id": handbook_id,
        "status": "completed",
        "is_outdated": result.is_outdated,
        "impacted_sections": result.impacted_sections,
        "new_change_requests_count": result.new_change_requests_count,
    }


async def _dispatch_freshness_checks() -> dict:
    """Find published handbooks due for freshness check and run them."""
    conn = await get_db_connection()
    try:
        try:
            sched_row = await conn.fetchrow(
                "SELECT enabled, max_per_cycle FROM scheduler_settings WHERE task_key = 'handbook_freshness'"
            )
        except Exception:
            sched_row = None

        if sched_row and not sched_row["enabled"]:
            print("[Handbook Freshness] Scheduler disabled, skipping.")
            return {"checked": 0}

        limit = (
            sched_row["max_per_cycle"]
            if sched_row and sched_row["max_per_cycle"] and sched_row["max_per_cycle"] > 0
            else 5
        )

        rows = await conn.fetch(
            """
            SELECT h.id AS handbook_id, h.company_id
            FROM handbooks h
            WHERE h.status = 'active'
            ORDER BY h.updated_at ASC
            LIMIT $1
            """,
            limit,
        )
    finally:
        await conn.close()

    checked = 0
    outdated_handbooks = []

    for row in rows:
        hb_id = str(row["handbook_id"])
        comp_id = str(row["company_id"])
        try:
            result = await _run_single_freshness_check(hb_id, comp_id)
            checked += 1
            if result.get("is_outdated"):
                outdated_handbooks.append({
                    "handbook_id": hb_id,
                    "company_id": comp_id,
                    "impacted_sections": result.get("impacted_sections", 0),
                })
        except Exception as e:
            print(f"[Handbook Freshness] Error checking handbook {hb_id}: {e}")

    # Send email notifications for outdated handbooks
    for item in outdated_handbooks:
        try:
            await _send_freshness_notification(
                item["company_id"],
                item["handbook_id"],
                item["impacted_sections"],
            )
        except Exception as e:
            print(f"[Handbook Freshness] Error sending notification for {item['handbook_id']}: {e}")

    return {"checked": checked, "outdated": len(outdated_handbooks)}


async def _send_freshness_notification(company_id: str, handbook_id: str, impacted_sections: int):
    """Send email notification about outdated handbook."""
    from app.core.services.email import EmailService

    conn = await get_db_connection()
    try:
        company_row = await conn.fetchrow(
            "SELECT name FROM companies WHERE id = $1",
            company_id,
        )
        if not company_row:
            return

        admin_row = await conn.fetchrow(
            """
            SELECT u.email, u.name
            FROM users u
            JOIN companies c ON c.id = $1
            WHERE u.role = 'client'
              AND u.company_id = $1
            ORDER BY u.created_at ASC
            LIMIT 1
            """,
            company_id,
        )
        if not admin_row or not admin_row["email"]:
            return

        company_name = company_row["name"] or "Your Company"
        email_service = EmailService()
        await email_service.send_handbook_freshness_alert(
            to_email=admin_row["email"],
            to_name=admin_row["name"],
            company_name=company_name,
            handbook_id=handbook_id,
            impacted_sections=impacted_sections,
        )
    finally:
        await conn.close()


@celery_app.task(name="handbook_freshness.run_handbook_freshness_checks", bind=True, max_retries=1)
def run_handbook_freshness_checks(self):
    """Dispatch handbook freshness checks for all active handbooks."""
    try:
        result = asyncio.run(_dispatch_freshness_checks())
        print(f"[Handbook Freshness] Completed: {result}")
        return result
    except Exception as e:
        print(f"[Handbook Freshness] Task failed: {e}")
        raise self.retry(exc=e, countdown=120)
