"""What a channel `@huume` question can be grounded on, beyond `ems_events`
(see `ask.py` for that channel-scoped corpus). This module is the POLICY
registry only — which topics exist, who can reach them, whether they're
location-scoped, and how a raw `lookup_context_impl` result renders into
text. It executes nothing itself; `channel_agent.py`'s tool-calling loop is
the one caller, dispatching a model-requested `lookup_context(topic, ...)`
tool call against `CHANNEL_TOPICS_BY_NAME` and formatting the result through
`format_topic_result` below. Reuses
`services/huume/onboarding_skill.lookup_context_impl`, the same read layer
Huume-thread `lookup_context` calls hit: same per-topic feature gate
(`onboarding_skill.topic_allowed`, three-state `{"module": "off"}` idiom),
same legal-record redaction (the `incidents` topic never returns
names/narrative).

## Why the model never sees a topic it can't reach

Earlier versions of this module pre-fetched every allowed topic on every
question — cheap to reason about, but it meant an admin asking about a
walk-in freezer pulled PTO/training/credential names into the prompt
regardless of what was actually asked, purely because the topic was
*permitted*. `channel_agent.py` instead lets the model choose which topics
to call, one at a time, but the choice is advisory only: every call is
re-checked here (`admin_only`, `topic_allowed`, `location_scoped`) before
any SQL runs, so a topic this asker can't reach is refused at the tool
boundary regardless of what the model asks for — the model picking a topic
is not the same as the model being trusted to pick correctly.

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
  so naming it in chat isn't a new disclosure. `pto_leave` never names the
  reason (see `_render_pto`) — who's out is team-relevant, why is not.
"""

import logging
import re
from dataclasses import dataclass
from typing import Any, Callable, Optional
from uuid import UUID

logger = logging.getLogger(__name__)

# Defense in depth against a forged "## SECTION" header riding in on DB free
# text (an item name, an incident title) that a tool result's rendered text
# includes verbatim — same reasoning `event_intake.classify_event` already
# applies to a channel's store name. Function-calling hands this back to the
# model as a structured tool result, not a spliced prompt string, so the
# injection surface is narrower than the old single-prompt design, but a
# model that reasons over the text at face value is still worth guarding.
_HEADER_RE = re.compile(r"(?m)^[ \t]*#+")
_BLANK_RUN_RE = re.compile(r"\n{3,}")
_MAX_BLOCK_CHARS = 2000


def _sanitize_block(text: str) -> str:
    text = _HEADER_RE.sub("", text)
    text = _BLANK_RUN_RE.sub("\n\n", text)
    return text[:_MAX_BLOCK_CHARS]


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
    """Who's out and when they're back — never WHY. `leave_type` (medical/
    FMLA/etc) next to a name is the exact disclosure `hr_ops_skill.py`'s
    coworker-naming redaction exists to prevent, and unlike the `incidents`
    topic nothing else redacts this path before it reaches the room."""
    lines = []
    for r in result.get("active_leave") or []:
        back = r["expected_return_date"].strftime("back %b %d, %Y") if r.get("expected_return_date") else "back date TBD"
        lines.append(f"- {r.get('first_name', '')} {r.get('last_name', '')}: out, {back}")
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
        # NOTE: the incident `title` field is free text and, per
        # onboarding_skill.lookup_context_impl's own comment, routinely
        # names people ("Maria slipped near bay 3") — this header must not
        # claim the block is name-free, only that the DEDICATED
        # narrative/witness fields are withheld (see _render_incidents).
        topic="incidents", title="RECENT INCIDENTS (type/severity/status — title is free text, may name people; no narrative/witnesses)",
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


CHANNEL_TOPICS_BY_NAME: dict[str, ChannelTopic] = {t.topic: t for t in CHANNEL_TOPICS}


def reachable_topics(*, features: Optional[dict[str, Any]], is_admin: bool) -> list[ChannelTopic]:
    """The subset of `CHANNEL_TOPICS` this asker could reach right now —
    same admin + feature gate `run_topic_lookup`/`help_lines` apply, shared
    here so callers deciding whether to run the agent loop at all (an empty
    list means there's nothing for it to ground beyond ems_events) and the
    loop's own tool-declaration enum stay in agreement."""
    from app.matcha.services.huume.onboarding_skill import topic_allowed

    return [
        t for t in CHANNEL_TOPICS
        if (is_admin or not t.admin_only) and topic_allowed(t.topic, features)
    ]


async def run_topic_lookup(
    conn, *, topic: str, company_id: UUID, features: Optional[dict[str, Any]], is_admin: bool,
    location_id: Optional[UUID], location_unavailable: bool = False,
    query: Optional[str] = None, days: Optional[int] = None,
) -> dict[str, Any]:
    """Execute one model-requested `lookup_context(topic=...)` call for a
    channel — the single enforcement point `channel_agent.py`'s tool loop
    calls for every topic the model asks for. The model's choice of topic
    is advisory only: `admin_only`, the feature gate, and location
    availability are all re-checked here before any SQL runs, so a
    hallucinated or out-of-policy topic argument never reaches the
    database — same posture as re-checking a staged action's flags at
    confirm time rather than trusting what was true when it was proposed.

    Returns `{"text": str, "degraded": bool}`. `text` is always safe to hand
    back to the model as the function result — either the sanitized render,
    or a plain-language refusal/failure sentence, never raw exception
    detail. `degraded=True` marks a genuine read failure (vs "no data" or
    "not allowed"), so the caller can tell the asker something broke rather
    than rendering an outage as an all-clear."""
    from app.matcha.services.huume.onboarding_skill import lookup_context_impl, topic_allowed

    t = CHANNEL_TOPICS_BY_NAME.get(topic)
    if t is None:
        return {"text": f"'{topic}' isn't something I can look up in this channel.", "degraded": False}
    if t.admin_only and not is_admin:
        return {"text": "That's only available to admins in this channel.", "degraded": False}
    if not topic_allowed(t.topic, features):
        return {"text": "That isn't enabled for this company.", "degraded": False}
    if t.location_scoped and location_unavailable:
        return {
            "text": "This channel's store is deactivated, so that data is paused here — "
                    "an admin can reactivate the store or rebind this channel.",
            "degraded": False,
        }
    try:
        result = await lookup_context_impl(
            conn, company_id=company_id, topic=t.topic, query=query, days=days,
            features=features, location_id=location_id if t.location_scoped else None,
        )
    except Exception:
        logger.exception("channel_grounding: topic '%s' failed for company %s", t.topic, company_id)
        return {"text": "That lookup failed just now — try again in a bit.", "degraded": True}
    if result.get("module") == "off":
        return {"text": "That isn't enabled for this company.", "degraded": False}
    if result.get("error"):
        logger.warning("channel_grounding: topic '%s' returned an error for company %s", t.topic, company_id)
        return {"text": "That lookup failed just now — try again in a bit.", "degraded": True}
    try:
        text = t.render(result)
    except Exception:
        logger.exception("channel_grounding: rendering topic '%s' failed for company %s", t.topic, company_id)
        return {"text": "That lookup failed just now — try again in a bit.", "degraded": True}
    if not text:
        return {"text": "Nothing on file for that right now.", "degraded": False}
    return {"text": _sanitize_block(text), "degraded": False}


def help_lines(*, features: Optional[dict[str, Any]], is_admin: bool) -> list[str]:
    """Capability-pill bullets for the topics this asker can actually reach
    right now — same admin/feature gate `run_topic_lookup` applies (via the
    shared `topic_allowed`), so "@huume help" never advertises something
    the next question can't do."""
    from app.matcha.services.huume.onboarding_skill import topic_allowed

    lines = []
    for t in CHANNEL_TOPICS:
        if t.admin_only and not is_admin:
            continue
        if not topic_allowed(t.topic, features):
            continue
        lines.append(f"• {t.help_line}")
    return lines
