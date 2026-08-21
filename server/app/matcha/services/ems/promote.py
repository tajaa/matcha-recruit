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
from typing import Any, Collection, Literal, Optional
from uuid import UUID

from app.matcha.services.ir.ir_incident_create import create_incident_core
from app.matcha.services.ops.permissions import OpsCapability

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


def evaluate_promote(
    *,
    role: Optional[str] = None,
    capabilities: Collection[OpsCapability] | None = None,
    features: dict,
    event_status: str,
    source_kind: Optional[str] = None,
) -> PromoteVerdict:
    if capabilities is not None:
        allowed = OpsCapability.EVENT_PROMOTE in capabilities
    else:
        # Compatibility for callers that have not yet resolved Work access.
        allowed = role in _ALLOWED_ROLES
    if not allowed:
        return PromoteVerdict("refuse", "Only a business admin can promote an event.", 403)
    if not features.get("ems"):
        return PromoteVerdict("refuse", "EMS is not enabled for this company.", 403)
    if not features.get("incidents"):
        return PromoteVerdict("refuse", "Incident reporting is not enabled for this company.", 403)
    if event_status != "logged":
        return PromoteVerdict("refuse", f"Event is already {event_status}, not logged.", 409)
    if source_kind == "schedule_compliance_warning":
        return PromoteVerdict(
            "refuse",
            "Schedule competency warnings are operational follow-ups, not incident reports.",
            409,
        )
    return PromoteVerdict("proceed")


def naive_occurred_at(value):
    """Strip the tzinfo off a datetime bound for `ir_incidents.occurred_at`,
    which is TIMESTAMP *WITHOUT* TIME ZONE.

    The UI sends a local wall-clock string (already naive — see
    PromoteModal.tsx), so this is a no-op on that path. It bites on the
    fallback, where `ems_events.created_at` IS tz-aware (timestamptz):
    handing that to asyncpg let it silently convert to UTC and drop the
    offset, so an evening event west of UTC filed an incident dated a day
    ahead. Converting explicitly keeps the wall-clock the reporter would
    recognize instead of a UTC one, matching every other IR intake path."""
    if value is None or getattr(value, "tzinfo", None) is None:
        return value
    return value.astimezone().replace(tzinfo=None)


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
    occurred_at = naive_occurred_at(overrides.get("occurred_at") or event["created_at"])
    location = overrides.get("location")
    # The store captured at intake (channels.location_id, stamped onto the
    # event — see oploc01) carries forward as the incident's real FK, same
    # as the location magic-link intake. `location` above stays the
    # free-text override/display string; the two are independent fields on
    # create_incident_core.
    location_id = event.get("location_id")
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
        location_id=location_id,
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
