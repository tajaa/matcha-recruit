"""
Celery tasks for leave compliance deadline tracking.

check_leave_deadlines — runs on worker startup to escalate overdue deadlines.
create_leave_deadlines — called when a leave request is approved to seed deadlines.
"""

import asyncio
from datetime import date, timedelta

from ..celery_app import celery_app
from ..notifications import publish_task_complete, publish_task_error
from ..utils import get_db_connection


# FMLA-related leave types that get the full notice/certification deadline set.
# Includes both the current canonical value and legacy granular variants.
FMLA_LEAVE_TYPES = {
    "fmla",
    "fmla_serious_health",
    "fmla_family_care",
    "fmla_baby_bonding",
    "fmla_military",
}


def _add_business_days(start: date, days: int) -> date:
    """Add *days* business days (Mon–Fri) to *start*."""
    current = start
    added = 0
    while added < days:
        current += timedelta(days=1)
        if current.weekday() < 5:  # Mon=0 … Fri=4
            added += 1
    return current


# ------------------------------------------------------------------
# Async helpers
# ------------------------------------------------------------------

async def _check_deadlines() -> dict:
    """Scan pending leave_deadlines and escalate as needed."""
    conn = await get_db_connection()
    try:
        rows = await conn.fetch(
            "SELECT id, leave_request_id, org_id, deadline_type, due_date, escalation_level, status "
            "FROM leave_deadlines WHERE status IN ('pending', 'overdue')"
        )

        today = date.today()
        warnings = 0
        overdue = 0
        escalated = 0

        for row in rows:
            due = row["due_date"]
            level = row["escalation_level"]
            status = row["status"]
            new_level = level
            new_status = status

            # Level 1: warning — due within 2 days
            if status == "pending" and 0 <= (due - today).days <= 2 and level == 0:
                new_level = 1
                warnings += 1

            # Level 2: overdue — past due date
            if today > due and level < 2:
                new_level = 2
                new_status = "overdue"
                overdue += 1

            # Level 3: admin escalation — overdue by 3+ days
            if today > due and (today - due).days >= 3 and level < 3:
                new_level = 3
                new_status = "overdue"
                escalated += 1

            if new_level != level or new_status != status:
                await conn.execute(
                    "UPDATE leave_deadlines "
                    "SET escalation_level = $1, status = $2, updated_at = NOW() "
                    "WHERE id = $3",
                    new_level, new_status, row["id"],
                )

                publish_task_complete(
                    channel=f"company:{row['org_id']}",
                    task_type="leave_deadline_escalation",
                    entity_id=str(row["leave_request_id"]),
                    result={
                        "deadline_id": str(row["id"]),
                        "deadline_type": row["deadline_type"],
                        "escalation_level": new_level,
                        "status": new_status,
                    },
                )

        return {
            "checked": len(rows),
            "warnings": warnings,
            "overdue": overdue,
            "escalated": escalated,
        }
    finally:
        await conn.close()


async def _create_deadlines(leave_request_id: str) -> dict:
    """Create applicable deadlines for an approved leave request."""
    from uuid import UUID

    conn = await get_db_connection()
    try:
        lr = await conn.fetchrow(
            "SELECT id, org_id, employee_id, leave_type, start_date, "
            "end_date, expected_return_date "
            "FROM leave_requests WHERE id = $1",
            UUID(leave_request_id),
        )
        if not lr:
            return {"created": 0, "deadlines": []}

        today = date.today()
        deadlines: list[dict] = []

        leave_type = (lr["leave_type"] or "").strip().lower()
        return_date = lr["expected_return_date"] or lr["end_date"]
        is_fmla = leave_type in FMLA_LEAVE_TYPES or leave_type.startswith("fmla_")

        # --- FMLA-specific deadlines ---
        if is_fmla:
            # Eligibility notice: 5 business days from today (request date)
            deadlines.append({
                "type": "eligibility_notice_due",
                "due": _add_business_days(today, 5),
            })
            # Designation notice: 5 business days from today
            deadlines.append({
                "type": "designation_notice_due",
                "due": _add_business_days(today, 5),
            })
            # Certification due: 15 calendar days from today
            deadlines.append({
                "type": "certification_due",
                "due": today + timedelta(days=15),
            })

        # --- Medical / FMLA: fitness-for-duty tied to return date ---
        if is_fmla or leave_type == "medical":
            if return_date:
                deadlines.append({
                    "type": "fitness_for_duty_due",
                    "due": return_date,
                })

        # --- All types: return date deadline ---
        if return_date:
            deadlines.append({
                "type": "return_date",
                "due": return_date,
            })

        created_records = []
        for d in deadlines:
            row = await conn.fetchrow(
                "INSERT INTO leave_deadlines "
                "(leave_request_id, org_id, deadline_type, due_date) "
                "SELECT $1, $2, $3, $4 "
                "WHERE NOT EXISTS ("
                "  SELECT 1 FROM leave_deadlines "
                "  WHERE leave_request_id = $1 AND deadline_type = $3"
                ") "
                "RETURNING id, deadline_type, due_date",
                lr["id"], lr["org_id"], d["type"], d["due"],
            )
            if row:
                created_records.append({
                    "id": str(row["id"]),
                    "deadline_type": row["deadline_type"],
                    "due_date": str(row["due_date"]),
                })

        return {"created": len(created_records), "deadlines": created_records}
    finally:
        await conn.close()


# ------------------------------------------------------------------
# Celery tasks
# ------------------------------------------------------------------

@celery_app.task(bind=True, max_retries=1)
def check_leave_deadlines(self) -> dict:
    """Scan pending leave deadlines and escalate overdue items.

    Triggered on worker startup via the worker_ready signal.
    """
    print("[Leave Deadlines] Checking for overdue leave deadlines...")

    try:
        result = asyncio.run(_check_deadlines())
        print(
            f"[Leave Deadlines] Checked {result['checked']} deadlines: "
            f"{result['warnings']} warnings, {result['overdue']} overdue, "
            f"{result['escalated']} escalated"
        )
        return {"status": "success", **result}

    except Exception as e:
        print(f"[Leave Deadlines] Failed: {e}")
        raise self.retry(exc=e, countdown=60)


@celery_app.task(bind=True, max_retries=2)
def create_leave_deadlines(self, leave_request_id: str) -> dict:
    """Create compliance deadlines for a newly approved leave request."""
    print(f"[Leave Deadlines] Creating deadlines for leave request {leave_request_id}")

    try:
        result = asyncio.run(_create_deadlines(leave_request_id))
        print(f"[Leave Deadlines] Created {result['created']} deadlines for {leave_request_id}")
        return {"status": "success", **result}

    except Exception as e:
        print(f"[Leave Deadlines] Failed to create deadlines for {leave_request_id}: {e}")

        publish_task_error(
            channel="system",
            task_type="create_leave_deadlines",
            entity_id=leave_request_id,
            error=str(e),
        )

        raise self.retry(exc=e, countdown=60)
