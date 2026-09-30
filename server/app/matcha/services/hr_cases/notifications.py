"""Who hears about an HR case, and what they're told.

- GM: whoever reported the incident — its `created_by` user, else the
  company member whose email matches `reported_by_email`. Anonymous intake
  has no GM; HR alone is told.
- HR: `clients.is_hr_approver` users (the column's documented purpose is
  exactly this: notification targeting), falling back to the company owner,
  then everyone else in the company. Every tier is filtered through
  `access.has_hr_access`, the same rule as the HR Cases page: nobody is told
  about an HR matter they couldn't open, and nobody gets a link that 404s.

Bodies are fixed templates: incident number, case number, policy titles and
names of the people copied. Never the incident narrative, never the
employee's name, never model text.
"""

from __future__ import annotations

import logging
from types import SimpleNamespace
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
    """[{user_id, name}] with HR access — designated HR approvers, else the
    owner, else anyone in the company who has HR access. Empty when nobody
    does (then nobody is told, rather than the wrong people)."""
    from .access import has_hr_access

    queries = (
        """
        SELECT u.id AS user_id, u.role, COALESCE(NULLIF(c.name, ''), u.email) AS name
        FROM clients c JOIN users u ON u.id = c.user_id
        WHERE c.company_id = $1 AND c.is_hr_approver AND u.is_active IS NOT FALSE
        ORDER BY name
        """,
        """
        SELECT u.id AS user_id, u.role, COALESCE(NULLIF(c.name, ''), u.email) AS name
        FROM companies co JOIN users u ON u.id = co.owner_id
        LEFT JOIN clients c ON c.user_id = u.id
        WHERE co.id = $1 AND u.is_active IS NOT FALSE
        """,
        """
        SELECT u.id AS user_id, u.role, COALESCE(NULLIF(c.name, ''), u.email) AS name
        FROM clients c JOIN users u ON u.id = c.user_id
        WHERE c.company_id = $1 AND u.is_active IS NOT FALSE
        ORDER BY name
        """,
    )
    for sql in queries:
        allowed = []
        for r in await conn.fetch(sql, company_id):
            user = SimpleNamespace(id=r["user_id"], role=r["role"])
            if await has_hr_access(conn, user=user, company_id=company_id):
                allowed.append({"user_id": r["user_id"], "name": r["name"]})
        if allowed:
            return allowed
    return []


def _join_names(names: list[str]) -> str:
    names = [n for n in names if n]
    if len(names) <= 1:
        return names[0] if names else "HR"
    return ", ".join(names[:-1]) + f" and {names[-1]}"


def flagged_messages(
    *, case_number: str, incident_number: Optional[str], policy_titles: list[str],
    hr_names: list[str], gm_name: Optional[str], has_reporter: bool = False,
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
                + (
                    f" {gm_name}, who reported it, was notified." if gm_name
                    else " Whoever reported it isn't an active member here, so only HR was notified." if has_reporter
                    else " It was reported anonymously."
                )
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
            has_reporter=bool(incident.get("created_by") or incident.get("reported_by_email")),
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


async def send(
    *, user_ids: list, company_id: UUID, type: str, title: str, body: str, link: str,
    metadata: Optional[dict[str, Any]] = None, skip_user_id: Optional[UUID] = None,
) -> None:
    """Bell + email to each user once. Never raises."""
    from app.matcha.services import notification_service

    seen = set()
    for uid in user_ids:
        if not uid or uid in seen or uid == skip_user_id:
            continue
        seen.add(uid)
        try:
            await notification_service.create_notification(
                user_id=uid, company_id=company_id, type=type, title=title, body=body,
                link=link, metadata=metadata or {}, send_email=True,
            )
        except Exception:
            logger.exception("[hr_cases] %s notification to %s failed", type, uid)


def hr_link(case: dict[str, Any]) -> str:
    return f"/work/hr-cases/{case['id']}"


def manager_link(case: dict[str, Any]) -> str:
    return f"/work/write-ups/{case['id']}"


async def step_recipients(conn, *, case: dict[str, Any], step: str) -> list:
    """HR user ids for a step's notice (empty for steps that only tell the
    manager). The only part of a notice that needs the database."""
    if step not in ("draft_submitted", "draft_held", "delivered"):
        return []
    try:
        return [r["user_id"] for r in await hr_recipients(conn, case["company_id"])]
    except Exception:
        logger.exception("[hr_cases] could not resolve HR for case %s", case.get("id"))
        return []


async def notify_step(conn, *, case: dict[str, Any], step: str, actor_user_id: Optional[UUID], reason: Optional[str] = None) -> None:
    """Fixed-template notice for a workflow step. HR gets the HR link; the
    manager gets the write-ups link. The acting person is never notified of
    their own action. Never raises."""
    hr_ids = await step_recipients(conn, case=case, step=step)
    await send_step(case=case, step=step, hr_ids=hr_ids, actor_user_id=actor_user_id, reason=reason)


async def send_step(
    *, case: dict[str, Any], step: str, hr_ids: list, actor_user_id: Optional[UUID], reason: Optional[str] = None,
) -> None:
    """The sending half of `notify_step`; holds no connection of the caller's
    (bell + email go through notification_service's own). Never raises."""
    number = case["case_number"]
    meta = {"hr_case_id": str(case["id"])}
    gm = case.get("gm_user_id")
    if step == "draft_submitted":
        await send(user_ids=hr_ids, company_id=case["company_id"], type="hr_case_draft_submitted",
                   title=f"{number}: write-up ready for review",
                   body="A manager sent a write-up. It passed the protected-leave check and is waiting for HR approval.",
                   link=hr_link(case), metadata=meta, skip_user_id=actor_user_id)
    elif step == "draft_held":
        await send(user_ids=hr_ids, company_id=case["company_id"], type="hr_case_draft_held",
                   title=f"{number}: write-up held",
                   body="A write-up conflicts with a protected-leave rule and can't go forward as written. Open the case for details.",
                   link=hr_link(case), metadata=meta, skip_user_id=actor_user_id)
    elif step == "approved":
        await send(user_ids=[gm], company_id=case["company_id"], type="hr_case_approved",
                   title=f"{number}: approved to deliver",
                   body="HR approved the write-up. Deliver it to the employee, then mark it delivered and upload the signed copy.",
                   link=manager_link(case), metadata=meta, skip_user_id=actor_user_id)
    elif step == "changes_requested":
        await send(user_ids=[gm], company_id=case["company_id"], type="hr_case_changes_requested",
                   title=f"{number}: HR asked for changes",
                   body=(f"HR's note: {reason}" if reason else "HR asked for changes to the write-up."),
                   link=manager_link(case), metadata=meta, skip_user_id=actor_user_id)
    elif step == "delivered":
        await send(user_ids=hr_ids, company_id=case["company_id"], type="hr_case_delivered",
                   title=f"{number}: delivered",
                   body="The write-up was delivered to the employee. The signed copy is next.",
                   link=hr_link(case), metadata=meta, skip_user_id=actor_user_id)


async def notify_signed(conn, *, case: dict[str, Any], actor_user_id: Optional[UUID]) -> None:
    """After the signed-copy check. HR hears every outcome; the manager hears
    only problems a new upload can fix. The employee's comment text is never
    put in a notification — HR reads it on the case. Never raises."""
    from .workflow import MANAGER_FIXABLE_REASONS
    from .verification import REASON_TEXT

    try:
        hr_ids = [r["user_id"] for r in await hr_recipients(conn, case["company_id"])]
    except Exception:
        logger.exception("[hr_cases] could not resolve HR for case %s", case.get("id"))
        hr_ids = []
    number = case["case_number"]
    meta = {"hr_case_id": str(case["id"])}
    reasons = case.get("attention_reasons") or []
    if case["stage"] == "closed":
        await send(user_ids=hr_ids, company_id=case["company_id"], type="hr_case_signed_filed",
                   title=f"{number}: signed copy filed",
                   body="The signed copy was checked and filed in Drive. The case is closed.",
                   link=hr_link(case), metadata=meta)
        return
    if case["stage"] != "needs_attention":
        return
    await send(user_ids=hr_ids, company_id=case["company_id"], type="hr_case_signed_attention",
               title=f"{number}: signed copy needs attention",
               body=" ".join(REASON_TEXT.get(r, r) for r in reasons),
               link=hr_link(case), metadata=meta)
    fixable = [REASON_TEXT[r] for r in reasons if r in MANAGER_FIXABLE_REASONS]
    gm = case.get("gm_user_id")
    if fixable and gm and gm not in hr_ids:
        await send(user_ids=[gm], company_id=case["company_id"], type="hr_case_signed_attention",
                   title=f"{number}: please upload the signed copy again",
                   body=" ".join(fixable) + " Upload a new copy on the Write-ups page.",
                   link=manager_link(case), metadata=meta)
