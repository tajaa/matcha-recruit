"""What a channel "@huume <question>" can be grounded on, beyond
`ems_events` (see `ask.py`).

Registry-driven so adding a topic later is a new `ChannelTopic` row plus a
render function — no changes anywhere else. Reuses
`services/huume/onboarding_skill._lookup_context_impl`, the same read layer
Huume-thread `lookup_context` calls hit: same per-topic feature gate
(`_TOPIC_REQUIRED_FEATURE`, three-state `{"module": "off"}` idiom), same
legal-record redaction (the `incidents` topic never returns names/narrative).

## Why this list is short

A channel answer is broadcast to EVERYONE in the room, employees included —
there is no per-recipient redaction the way a Huume thread has (that's a
single admin/client's own conversation). Two topic classes are excluded on
purpose:

- **Legal/HR-confidential even at title level** — `er_cases`, `discipline`,
  `documents`, `offers`. Naming an ER case or a discipline record in a public
  channel is the exact leak `services/huume/hr_ops_skill.py` and
  `record_view.py`'s redaction rules exist to prevent. Thread-only.
- Everything left in (`schedule`, `inventory`, `incidents`, `training_status`,
  `credentials`, `pto_leave`) is either already name-free at the source
  (`incidents` strips narrative/witnesses the same way it does for threads)
  or, per product decision, an accepted disclosure: an admin asking a named
  question in a public channel is choosing to say it there, the same posture
  `ask.py` already takes with `behavioral` events (`is_admin=True` unlocks
  them). `schedule` assignee names go to EVERYONE, admin or not — a
  published shift's staffing is already portal-visible to the whole team,
  so naming it in chat isn't a new disclosure.
"""

import logging
from dataclasses import dataclass
from typing import Any, Callable, Optional
from uuid import UUID

logger = logging.getLogger(__name__)


def _render_schedule(result: dict[str, Any]) -> str:
    shifts = result.get("upcoming_shifts") or []
    if not shifts:
        return ""
    lines = []
    for s in shifts:
        when = s["starts_at"].strftime("%a %b %d, %I:%M%p") if s.get("starts_at") else "unknown time"
        ends = s["ends_at"].strftime("%I:%M%p") if s.get("ends_at") else "?"
        who = ", ".join(s.get("assignees") or []) or "unassigned"
        role = s.get("role") or "Shift"
        lines.append(f"- [{when}–{ends}] {role}: {who} ({s.get('assigned_count', 0)}/{s.get('required_staff', 1)} staffed)")
    return "\n".join(lines)


def _render_inventory(result: dict[str, Any]) -> str:
    items = result.get("items") or []
    if not items:
        return ""
    lines = []
    for it in items:
        qty = it.get("current_quantity")
        unit = it.get("unit") or ""
        status = f" (order {it['order_status']})" if it.get("order_status") else ""
        lines.append(f"- {it.get('name', 'item')}: {qty} {unit}{status}".rstrip())
    return "\n".join(lines)


def _render_incidents(result: dict[str, Any]) -> str:
    incidents = result.get("incidents") or []
    if not incidents:
        return ""
    window = result.get("window_days", 90)
    lines = [f"(last {window} days)"]
    for inc in incidents:
        when = inc["occurred_at"].strftime("%b %d, %Y") if inc.get("occurred_at") else "unknown date"
        lines.append(
            f"- [{when}] {inc.get('incident_number', '?')} {inc.get('title', 'Untitled')} "
            f"({inc.get('incident_type', 'unspecified')}, {inc.get('severity', 'unspecified')} severity, {inc.get('status', 'unspecified')})"
        )
    return "\n".join(lines)


def _render_training(result: dict[str, Any]) -> str:
    overdue = result.get("overdue") or []
    if not overdue:
        return ""
    lines = []
    for r in overdue:
        due = r["due_date"].strftime("%b %d, %Y") if r.get("due_date") else "unknown date"
        lines.append(f"- {r.get('first_name', '')} {r.get('last_name', '')}: {r.get('title', 'training')} overdue since {due}")
    return "\n".join(lines)


def _render_credentials(result: dict[str, Any]) -> str:
    rows = result.get("expiring_or_overdue") or []
    if not rows:
        return ""
    lines = []
    for r in rows:
        due = r["due_date"].strftime("%b %d, %Y") if r.get("due_date") else "unknown date"
        lines.append(f"- {r.get('first_name', '')} {r.get('last_name', '')}: {r.get('credential_label', 'credential')} ({r.get('status', 'unspecified')}, due {due})")
    return "\n".join(lines)


def _render_pto(result: dict[str, Any]) -> str:
    lines = []
    for r in result.get("active_leave") or []:
        back = r["expected_return_date"].strftime("%b %d, %Y") if r.get("expected_return_date") else "unknown date"
        lines.append(f"- {r.get('first_name', '')} {r.get('last_name', '')}: out on {r.get('leave_type', 'leave')}, back {back}")
    for r in result.get("upcoming_pto") or []:
        start = r["start_date"].strftime("%b %d, %Y") if r.get("start_date") else "?"
        end = r["end_date"].strftime("%b %d, %Y") if r.get("end_date") else "?"
        lines.append(f"- {r.get('first_name', '')} {r.get('last_name', '')}: {r.get('request_type', 'PTO')} {start}–{end}")
    return "\n".join(lines)


@dataclass(frozen=True)
class ChannelTopic:
    topic: str
    title: str
    admin_only: bool
    location_scoped: bool
    help_line: str
    render: Callable[[dict[str, Any]], str]


CHANNEL_TOPICS: tuple[ChannelTopic, ...] = (
    ChannelTopic(
        topic="schedule", title="UPCOMING SCHEDULE (next 7 days)",
        admin_only=False, location_scoped=True,
        help_line='Answer schedule questions ("@huume who\'s working tomorrow?")',
        render=_render_schedule,
    ),
    ChannelTopic(
        topic="inventory", title="INVENTORY ON HAND",
        admin_only=False, location_scoped=True,
        help_line='Answer stock questions ("@huume how much flour is left?")',
        render=_render_inventory,
    ),
    ChannelTopic(
        topic="incidents", title="RECENT INCIDENTS (no names or narrative)",
        admin_only=True, location_scoped=True,
        help_line='Summarize recent incidents (admins only)',
        render=_render_incidents,
    ),
    ChannelTopic(
        topic="training_status", title="OVERDUE TRAINING",
        admin_only=True, location_scoped=False,
        help_line='Flag overdue training (admins only)',
        render=_render_training,
    ),
    ChannelTopic(
        topic="credentials", title="EXPIRING/OVERDUE CREDENTIALS",
        admin_only=True, location_scoped=False,
        help_line='Flag expiring credentials (admins only)',
        render=_render_credentials,
    ),
    ChannelTopic(
        topic="pto_leave", title="WHO'S OUT / UPCOMING PTO",
        admin_only=True, location_scoped=False,
        help_line="Say who's out or has upcoming PTO (admins only)",
        render=_render_pto,
    ),
)


async def fetch_topic_blocks(
    conn, *, company_id: UUID, features: Optional[dict[str, Any]], is_admin: bool,
    location_id: Optional[UUID],
) -> list[tuple[str, str]]:
    """Best-effort grounding blocks for a channel ASK. One broken topic
    logs and is skipped — never kills the whole answer (same never-raises
    contract as `_lookup_context_impl` itself, defense in depth against a
    render function choking on an unexpected shape)."""
    from app.matcha.services.huume.onboarding_skill import _lookup_context_impl

    blocks: list[tuple[str, str]] = []
    for t in CHANNEL_TOPICS:
        if t.admin_only and not is_admin:
            continue
        try:
            result = await _lookup_context_impl(
                conn, company_id=company_id, topic=t.topic, features=features,
                location_id=location_id if t.location_scoped else None,
            )
            if result.get("module") == "off":
                continue
            text = t.render(result)
            if text:
                blocks.append((t.title, text))
        except Exception:
            logger.exception("channel_grounding: topic '%s' failed for company %s", t.topic, company_id)
    return blocks


def help_lines(*, features: Optional[dict[str, Any]], is_admin: bool) -> list[str]:
    """Capability-pill bullets for the topics this asker can actually reach
    right now — same admin/feature gate `fetch_topic_blocks` applies, so
    "@huume help" never advertises something the next question can't do."""
    from app.matcha.services.huume.onboarding_skill import _TOPIC_REQUIRED_FEATURE

    lines = []
    for t in CHANNEL_TOPICS:
        if t.admin_only and not is_admin:
            continue
        required = _TOPIC_REQUIRED_FEATURE.get(t.topic)
        if required and not (features or {}).get(required):
            continue
        lines.append(f"• {t.help_line}")
    return lines
