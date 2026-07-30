"""EMS event -> IR incident promotion.

AI never auto-creates the incident (same invariant as `ir_voice_intake`) —
promotion is always an explicit HR-admin action through this module.
`evaluate_promote` is a pure, DB-free verdict function mirroring
`services/huume/actions.py:evaluate_huume_action`: every guard a normal
incident write would get (role, feature flags, record status) is
re-asserted here rather than trusted to the caller.
"""

import json
import logging
from dataclasses import dataclass
from typing import Any, Literal, Optional
from uuid import UUID

from app.matcha.services.ir.ir_incident_create import create_incident_core

logger = logging.getLogger(__name__)

_ALLOWED_ROLES = frozenset({"client", "admin"})


class PromoteRaceError(Exception):
    """The status='logged' guard on the promote UPDATE missed — someone
    promoted/dismissed the event between the route's read and this write.
    Deliberately not a ValueError: create_incident_core can raise ValueError
    for unrelated reasons (date parse, JSON encode) and those must surface
    as real 500s, not a fake "promoted by someone else" 409."""


@dataclass(frozen=True)
class PromoteVerdict:
    kind: Literal["proceed", "refuse"]
    reason: Optional[str] = None
    http_status: int = 403

    @property
    def ok(self) -> bool:
        return self.kind == "proceed"


def evaluate_promote(*, role: Optional[str], features: dict, event_status: str) -> PromoteVerdict:
    if role not in _ALLOWED_ROLES:
        return PromoteVerdict("refuse", "Only a business admin can promote an event.", 403)
    if not features.get("ems"):
        return PromoteVerdict("refuse", "EMS is not enabled for this company.", 403)
    if not features.get("incidents"):
        return PromoteVerdict("refuse", "Incident reporting is not enabled for this company.", 403)
    if event_status != "logged":
        return PromoteVerdict("refuse", f"Event is already {event_status}, not logged.", 409)
    return PromoteVerdict("proceed")


def shape_witnesses(raw: Optional[list]) -> list[dict]:
    """Convert PromoteRequest.witnesses (bare display-name strings) into the
    Witness-shaped dicts create_incident_core stores and every reader
    round-trips through parse_witnesses() -> Witness(**w). A bare string
    there TypeErrors and silently drops the WHOLE witness list."""
    return [
        {"name": w.strip()}
        for w in (raw or [])
        if isinstance(w, str) and w.strip()
    ]


def _render_description(event: dict, channel_name: Optional[str], reporter_name: Optional[str]) -> str:
    lines = [event["narrative"]]
    doc = event.get("doc") or {}
    if isinstance(doc, str):
        try:
            doc = json.loads(doc)
        except (ValueError, TypeError):
            doc = {}
    if doc:
        lines.append("")
        lines.append("Details:")
        for key, value in doc.items():
            lines.append(f"- {key.replace('_', ' ').title()}: {value}")
    lines.append("")
    lines.append(
        f"(Logged via @huume in #{channel_name or 'unknown channel'}"
        f"{f' by {reporter_name}' if reporter_name else ''} on "
        f"{event['created_at'].strftime('%Y-%m-%d')})"
    )
    return "\n".join(lines)


async def promote_event(
    conn,
    *,
    company_id: UUID,
    event: dict,
    channel_name: Optional[str],
    reporter_name: Optional[str],
    overrides: dict[str, Any],
    actor_user_id: UUID,
    actor_email: Optional[str],
) -> tuple[dict, list]:
    """One transaction: create_incident_core(...) -> stamp the event
    promoted -> audit both sides. Returns (incident_row, bg_tasks) — the
    caller runs bg_tasks post-commit via FastAPI BackgroundTasks, exactly
    like the authenticated IR create route does."""
    title = overrides.get("title") or event.get("title") or "Event"
    incident_type = overrides.get("incident_type") or event.get("suggested_incident_type")
    severity = overrides.get("severity") or event.get("suggested_severity")
    occurred_at = overrides.get("occurred_at") or event["created_at"]
    location = overrides.get("location")
    witnesses = shape_witnesses(overrides.get("witnesses"))

    incident_row, bg_tasks = await create_incident_core(
        conn,
        company_id=str(company_id),
        description=_render_description(event, channel_name, reporter_name),
        occurred_at=occurred_at,
        reported_by_name=reporter_name or "Unknown",
        title=title,
        incident_type=incident_type,
        severity=severity,
        location=location,
        witnesses=witnesses,
        created_by=str(actor_user_id),
        actor_user_id=str(actor_user_id),
        actor_email=actor_email,
        index_people=True,  # attributed intake (reporter known, admin-reviewed) —
                            # mirrors the attributed /intake/:token path, not
                            # the anonymous /report:token one.
    )

    updated = await conn.fetchrow(
        """
        UPDATE ems_events
        SET status = 'promoted', incident_id = $2, promoted_by = $3, promoted_at = NOW(), updated_at = NOW()
        WHERE id = $1 AND status = 'logged'
        RETURNING id
        """,
        event["id"], UUID(str(incident_row["id"])), actor_user_id,
    )
    if updated is None:
        raise PromoteRaceError("Event was promoted or dismissed by someone else — refresh and retry.")

    await conn.execute(
        """
        INSERT INTO ems_event_audit_log (event_id, user_id, action, details)
        VALUES ($1, $2, 'promoted', $3::jsonb)
        """,
        event["id"], actor_user_id,
        json.dumps({"incident_id": str(incident_row["id"])}),
    )

    return incident_row, bg_tasks
