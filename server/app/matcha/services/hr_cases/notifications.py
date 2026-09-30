"""Who hears about an HR case, and what they're told.

- GM: whoever reported the incident — its `created_by` user, else the
  company member whose email matches `reported_by_email`. Anonymous intake
  has no GM; HR alone is told.
- HR: `clients.is_hr_approver` users (the column's documented purpose is
  exactly this: notification targeting), falling back to the company owner,
  then every active business user so a flag never notifies nobody.

Bodies are fixed templates: incident number, case number, policy titles and
names of the people copied. Never the incident narrative, never the
employee's name, never model text.
"""

from __future__ import annotations

import logging
from typing import Any, Optional
from uuid import UUID

logger = logging.getLogger(__name__)


async def resolve_gm_user_id(conn, *, company_id: UUID, incident: dict[str, Any]) -> Optional[UUID]:
    candidates = []
    if incident.get("created_by"):
        candidates.append(("id", incident["created_by"]))
    if incident.get("reported_by_email"):
        candidates.append(("email", incident["reported_by_email"]))
    for kind, value in candidates:
        column = "u.id = $2::uuid" if kind == "id" else "lower(u.email) = lower($2)"
        uid = await conn.fetchval(
            f"""
            SELECT u.id FROM users u
            WHERE {column} AND u.is_active IS NOT FALSE
              AND (EXISTS (SELECT 1 FROM clients c WHERE c.user_id = u.id AND c.company_id = $1)
                   OR EXISTS (SELECT 1 FROM employees e WHERE e.user_id = u.id AND e.org_id = $1
                              AND e.termination_date IS NULL))
            LIMIT 1
            """,
            company_id, str(value),
        )
        if uid:
            return uid
    return None


async def hr_recipients(conn, company_id: UUID) -> list[dict[str, Any]]:
    """[{user_id, name}] — designated HR approvers, else owner, else all
    active business users."""
    queries = (
        """
        SELECT u.id AS user_id, COALESCE(NULLIF(c.name, ''), u.email) AS name
        FROM clients c JOIN users u ON u.id = c.user_id
        WHERE c.company_id = $1 AND c.is_hr_approver AND u.is_active IS NOT FALSE
        ORDER BY name
        """,
        """
        SELECT u.id AS user_id, COALESCE(NULLIF(c.name, ''), u.email) AS name
        FROM companies co JOIN users u ON u.id = co.owner_id
        LEFT JOIN clients c ON c.user_id = u.id
        WHERE co.id = $1 AND u.is_active IS NOT FALSE
        """,
        """
        SELECT u.id AS user_id, COALESCE(NULLIF(c.name, ''), u.email) AS name
        FROM clients c JOIN users u ON u.id = c.user_id
        WHERE c.company_id = $1 AND u.is_active IS NOT FALSE
        ORDER BY name
        """,
    )
    for sql in queries:
        rows = await conn.fetch(sql, company_id)
        if rows:
            return [dict(r) for r in rows]
    return []


def _join_names(names: list[str]) -> str:
    names = [n for n in names if n]
    if len(names) <= 1:
        return names[0] if names else "HR"
    return ", ".join(names[:-1]) + f" and {names[-1]}"


def flagged_messages(
    *, case_number: str, incident_number: Optional[str], policy_titles: list[str],
    hr_names: list[str], gm_name: Optional[str],
) -> dict[str, dict[str, str]]:
    """Pure: the two notification bodies for a newly flagged case."""
    incident = incident_number or "A recent incident"
    policies = "; ".join(policy_titles[:4]) or "a company policy"
    hr = _join_names(hr_names)
    return {
        "gm": {
            "title": "Incident flagged for HR review",
            "body": (
                f"{incident} looks like it may involve {policies}. "
                f"{hr} in HR {'is' if len(hr_names) <= 1 else 'are'} copied and will follow up on next steps."
            ),
        },
        "hr": {
            "title": f"{case_number}: incident flagged",
            "body": (
                f"{incident} looks like it may involve {policies}."
                + (f" {gm_name}, who reported it, was notified." if gm_name else " It was reported anonymously.")
            ),
        },
    }


async def notify_flagged(
    conn, *, case: dict[str, Any], incident: dict[str, Any], policy_titles: list[str],
) -> None:
    """Never raises: a failed notification must not undo a flagged case."""
    from app.matcha.services import notification_service

    try:
        hr = await hr_recipients(conn, case["company_id"])
        gm_id = case.get("gm_user_id")
        gm_name = None
        if gm_id:
            gm_name = await conn.fetchval(
                "SELECT COALESCE(NULLIF(c.name, ''), u.email) FROM users u "
                "LEFT JOIN clients c ON c.user_id = u.id WHERE u.id = $1",
                gm_id,
            )
        msgs = flagged_messages(
            case_number=case["case_number"], incident_number=incident.get("incident_number"),
            policy_titles=policy_titles, hr_names=[r["name"] for r in hr], gm_name=gm_name,
        )
    except Exception:
        logger.exception("[hr_cases] could not build notifications for case %s", case.get("id"))
        return

    meta = {"hr_case_id": str(case["id"]), "incident_id": str(incident["id"])}
    sends = [
        (r["user_id"], msgs["hr"], f"/work/hr-cases/{case['id']}")
        for r in hr if r["user_id"] != gm_id
    ]
    if gm_id:
        sends.append((gm_id, msgs["gm"], f"/app/ir/{incident['id']}"))
    for user_id, msg, link in sends:
        try:
            await notification_service.create_notification(
                user_id=user_id, company_id=case["company_id"], type="hr_case_flagged",
                title=msg["title"], body=msg["body"], link=link, metadata=meta, send_email=True,
            )
        except Exception:
            logger.exception("[hr_cases] notification to %s failed for case %s", user_id, case.get("id"))
