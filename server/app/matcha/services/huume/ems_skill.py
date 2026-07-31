"""Huume EMS skill — promote a logged event into a real IR incident from chat.

Executor contract matches hr_ops_skill.py: assumes actions.evaluate_huume_action
already returned kind=="proceed"; returns {status, message, record_id?,
record_label?, bg_tasks?}; status MUST be exactly "created" on success
(agent.py's staged dispatch treats anything else as failure); bg_tasks are
(fn, args, kwargs) tuples the CALLER awaits post-commit — never awaited here.

The single-flag actions._HUUME_ACTION_REQUIRED_FEATURE registry carries only
"ems" for this action type; the incidents+role+status half of the gate is
re-asserted HERE per call via ems.promote.evaluate_promote — the same
envelope the REST promote route runs (routes/ems.py:promote), so chat can
never promote what the Events-tab button couldn't.
"""

import logging
from typing import Any, Optional
from uuid import UUID

from app.database import get_connection

logger = logging.getLogger(__name__)


async def execute_promote(
    *, company_id: UUID, actor_user_id: Optional[UUID], action: dict[str, Any],
) -> dict[str, Any]:
    from app.core.feature_flags import get_company_features
    from app.matcha.services.ems.promote import PromoteRaceError, evaluate_promote, promote_event
    from app.matcha.services.ems.queries import EVENT_SELECT

    event_id = action.get("event_id")
    try:
        event_uuid = UUID(str(event_id))
    except (ValueError, TypeError):
        return {"status": "error", "message": "That event id isn't valid."}

    async with get_connection() as conn:
        actor = await conn.fetchrow("SELECT role, email FROM users WHERE id = $1", actor_user_id)
        role = actor["role"] if actor else None
        actor_email = actor["email"] if actor else None

        features = await get_company_features(company_id, conn=conn)

        row = await conn.fetchrow(
            f"{EVENT_SELECT} WHERE ev.id = $1 AND ev.company_id = $2", event_uuid, company_id,
        )
        if not row:
            return {"status": "error", "message": "No logged event with that id exists for this company."}
        event = dict(row)

        verdict = evaluate_promote(role=role, features=features, event_status=event["status"])
        if not verdict.ok:
            return {"status": "error", "message": verdict.reason}

        overrides = {
            k: action[k]
            for k in ("title", "incident_type", "severity", "occurred_at", "location")
            if action.get(k)
        }

        try:
            async with conn.transaction():
                incident_row, bg_tasks = await promote_event(
                    conn,
                    company_id=company_id,
                    event=event,
                    channel_name=event.get("channel_name"),
                    reporter_name=event.get("reporter_name"),
                    overrides=overrides,
                    actor_user_id=actor_user_id,
                    actor_email=actor_email,
                )
        except PromoteRaceError:
            return {
                "status": "error",
                "message": "Someone promoted or dismissed this event first — refresh Events.",
            }

    label = incident_row.get("incident_number") or incident_row.get("title") or "the incident"
    return {
        "status": "created",
        "message": (
            f"Promoted the event into incident {label}. The IR classifier and policy "
            # Not actually background: agent.py awaits bg_tasks inline before
            # this message reaches the admin, same as every other HR-ops
            # tool's bg_tasks (see hr_ops_skill.py's report_incident message,
            # which makes no "background" claim for the same reason).
            "mapper have run; the record is editable in Incidents."
        ),
        "record_id": str(incident_row["id"]),
        "record_label": str(label),
        "bg_tasks": list(bg_tasks or []),
    }
