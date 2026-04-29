"""Discipline notification fanout.

Resolves the recipient set for each state transition (direct manager,
grandparent manager, issuing HR, plus other HR users on the company)
and sends in-app + email notifications via notification_service.

Missing manager rows degrade to a warning log — never a 500.
"""

from __future__ import annotations

import logging
from typing import Any, Optional
from uuid import UUID

from ...database import get_connection
from . import notification_service

logger = logging.getLogger(__name__)


_TITLES = {
    "discipline_issued": "Discipline Record Issued",
    "discipline_signature_requested": "Signature Requested",
    "discipline_signed": "Discipline Signed",
    "discipline_refused": "Refused to Sign",
    "discipline_physical_uploaded": "Signed PDF Uploaded",
}


async def _resolve_recipients(
    conn,
    record: dict[str, Any],
    *,
    notify_grandparent: bool,
) -> list[dict[str, Any]]:
    """Build the recipient set for a discipline notification.

    Returns a list of {user_id, kind} dicts. Each user_id is a Matcha
    `users.id` (not employees.id) — so we can deliver via existing
    mw_notifications tooling.
    """
    employee_id = record["employee_id"]
    company_id = record["company_id"]
    issuer_id = record["issued_by"]

    # Direct manager (employees.manager_id → employees.id) → user_id via employee email match
    manager_user_ids: list[UUID] = []
    grandparent_user_ids: list[UUID] = []
    try:
        rows = await conn.fetch(
            """
            WITH e AS (SELECT manager_id FROM employees WHERE id = $1),
                 m AS (
                   SELECT em.id AS manager_employee_id, em.manager_id AS grandparent_id, em.email AS manager_email
                   FROM employees em
                   WHERE em.id = (SELECT manager_id FROM e)
                 ),
                 g AS (
                   SELECT eg.id AS grandparent_employee_id, eg.email AS grandparent_email
                   FROM employees eg
                   WHERE eg.id = (SELECT grandparent_id FROM m)
                 )
            SELECT
              (SELECT manager_email FROM m) AS manager_email,
              (SELECT grandparent_email FROM g) AS grandparent_email
            """,
            employee_id,
        )
        if rows:
            manager_email = rows[0]["manager_email"]
            grandparent_email = rows[0]["grandparent_email"]
            if manager_email:
                u = await conn.fetchrow("SELECT id FROM users WHERE email = $1", manager_email)
                if u:
                    manager_user_ids.append(u["id"])
                else:
                    logger.warning(
                        "[discipline_notifications] direct manager email %s has no users row",
                        manager_email,
                    )
            if notify_grandparent and grandparent_email:
                u = await conn.fetchrow("SELECT id FROM users WHERE email = $1", grandparent_email)
                if u:
                    grandparent_user_ids.append(u["id"])
                else:
                    logger.warning(
                        "[discipline_notifications] grandparent manager email %s has no users row",
                        grandparent_email,
                    )
    except Exception:
        logger.exception(
            "[discipline_notifications] manager-chain lookup failed for employee %s — skipping",
            employee_id,
        )

    # HR users — issuer + any other 'client' role linked to the company via the clients table
    hr_user_ids: set[UUID] = {issuer_id} if issuer_id else set()
    try:
        hr_rows = await conn.fetch(
            """
            SELECT u.id
            FROM users u
            JOIN clients c ON c.user_id = u.id
            WHERE c.company_id = $1 AND u.role = 'client' AND u.is_active = TRUE
            """,
            company_id,
        )
        for r in hr_rows:
            hr_user_ids.add(r["id"])
    except Exception:
        logger.exception("[discipline_notifications] HR user lookup failed")

    recipients: list[dict[str, Any]] = []
    seen: set[UUID] = set()
    for uid in manager_user_ids:
        if uid not in seen:
            recipients.append({"user_id": uid, "kind": "direct_manager"})
            seen.add(uid)
    for uid in grandparent_user_ids:
        if uid not in seen:
            recipients.append({"user_id": uid, "kind": "grandparent_manager"})
            seen.add(uid)
    for uid in hr_user_ids:
        if uid not in seen:
            recipients.append({"user_id": uid, "kind": "hr"})
            seen.add(uid)
    return recipients


def _build_body(record: dict[str, Any], action: str, employee_name: Optional[str]) -> str:
    name = employee_name or "an employee"
    level = (record.get("discipline_type") or "").replace("_", " ").title()
    if action == "discipline_issued":
        return f"A {level} has been issued for {name}."
    if action == "discipline_signature_requested":
        return f"A signature has been requested from {name} for the {level}."
    if action == "discipline_signed":
        return f"{name} signed the {level} record."
    if action == "discipline_refused":
        return f"{name} refused to sign the {level} record. The warning remains active."
    if action == "discipline_physical_uploaded":
        return f"A physically-signed copy of the {level} for {name} has been uploaded."
    return ""


async def dispatch(
    *,
    record: dict[str, Any],
    action: str,
    notify_grandparent: bool = True,
    skip_user_id: Optional[UUID] = None,
) -> None:
    """Send notifications for a discipline state transition.

    `action` must be one of the keys in `_TITLES`.
    `skip_user_id` skips a single recipient (useful for the actor who
    just performed the action — they don't need to notify themselves).
    """
    title = _TITLES.get(action)
    if not title:
        logger.warning("[discipline_notifications] unknown action: %s", action)
        return

    async with get_connection() as conn:
        emp_row = await conn.fetchrow(
            """
            SELECT TRIM(BOTH ' ' FROM COALESCE(first_name, '') || ' ' || COALESCE(last_name, '')) AS name,
                   email
            FROM employees WHERE id = $1
            """,
            record["employee_id"],
        )
        employee_name = emp_row["name"] if emp_row else None

        recipients = await _resolve_recipients(
            conn, record, notify_grandparent=notify_grandparent
        )

    body = _build_body(record, action, employee_name)
    link = f"/app/discipline/{record['id']}"
    metadata = {
        "discipline_id": str(record["id"]),
        "employee_id": str(record["employee_id"]),
        "discipline_type": record.get("discipline_type"),
        "severity": record.get("severity"),
    }

    for rcpt in recipients:
        if skip_user_id and rcpt["user_id"] == skip_user_id:
            continue
        try:
            await notification_service.create_notification(
                user_id=rcpt["user_id"],
                company_id=record["company_id"],
                type=action,
                title=title,
                body=body,
                link=link,
                metadata={**metadata, "recipient_kind": rcpt["kind"]},
                send_email=True,
                email_subject=f"Matcha — {title}",
            )
        except Exception:
            logger.exception(
                "[discipline_notifications] failed to deliver %s to %s",
                action, rcpt["user_id"],
            )
