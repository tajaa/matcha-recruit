"""Reading "@huume what's been logged in here lately?" in a channel — the
pure, DB-adjacent pieces shared by every answer path. The model-facing loop
that actually answers a question lives in `channel_agent.py`; this module
owns the parts that don't change no matter how the answer is produced: the
channel's own `ems_events` corpus (fetch + render), the deterministic
no-model-call replies, and the admin/employee role split.

## Why this needs its own authorization rule

Every REST read of `ems_events` (`routes/ems.py`) is
`require_admin_or_client` — the Events tab is an HR surface. A channel is
not: `werk_lite`/`matcha_work` channels carry `employee`-role members too,
and a channel answer is broadcast to everyone in the room, not to the
asker. So this module re-derives visibility itself rather than reusing a
route gate that assumes an HR reader:

- **This channel's `ems_events` are channel-scoped, never company-wide for
  employees.** An answer covers events logged *in this channel* — things
  this room already witnessed and reported out loud. Pulling the company's
  whole event history into a store's chat would make any channel a read
  replica of the Events tab. The *grounding topics* `channel_agent.py`
  reaches beyond `ems_events` (schedule/inventory/etc, via
  `channel_grounding.py`) are a different rule — see that module's
  docstring: they're company-wide unless the channel is store-bound,
  because a published shift's staffing and stock levels are already
  team-visible in the portal, so naming them here isn't a new disclosure.
- **`behavioral` is admin-only.** Those are conduct accounts naming
  coworkers; they are the category HR review exists for. Same instinct as
  `hr_pilot_corpus.redact_for_employee`, which strips the coworker-naming
  groups from the employee-facing corpus.
- **HR's own assessment never leaks.** `severity_hint`,
  `incident_recommendation`, `incident_reasoning` and the extracted `doc`
  are Matcha's read on the event, not the reporter's words — admin only.
  The narrative/title are, by construction, derived from a message this
  channel already saw.

`is_admin` here means role ∈ {client, admin} — business admins and platform
admins, the same pair `evaluate_huume_action` and `promote` accept.
"""

import logging
from typing import Optional
from uuid import UUID

from . import categories

logger = logging.getLogger(__name__)

_LOOKBACK_DAYS = 120
_MAX_EVENTS = 25

ADMIN_ROLES = ("client", "admin")


def is_admin_role(role: Optional[str]) -> bool:
    return role in ADMIN_ROLES


async def fetch_channel_events(
    conn, *, company_id: UUID, channel_id: UUID, include_behavioral: bool,
) -> list[dict]:
    """Recent non-dismissed events for THIS channel, newest first.

    Dismissed events are excluded on purpose: an admin dismissing an event
    is a judgment that it isn't a thing, and re-narrating it in the channel
    would relitigate that decision in front of everyone.

    `include_behavioral=False` filters in SQL rather than in the prompt —
    a redaction the model could ignore is not a redaction.
    """
    where = [
        "ev.company_id = $1", "ev.channel_id = $2", "ev.status <> 'dismissed'",
        f"ev.created_at > NOW() - INTERVAL '{_LOOKBACK_DAYS} days'",
    ]
    if not include_behavioral:
        where.append("ev.category <> 'behavioral'")
    rows = await conn.fetch(
        f"""
        SELECT ev.id, ev.title, ev.category, ev.severity_hint, ev.doc,
               ev.narrative, ev.incident_recommendation, ev.status,
               ev.incident_id, ev.created_at
        FROM ems_events ev
        WHERE {' AND '.join(where)}
        ORDER BY ev.created_at DESC
        LIMIT {_MAX_EVENTS}
        """,
        company_id, channel_id,
    )
    return [dict(r) for r in rows]


def render_events_block(events: list[dict], *, is_admin: bool, filtered: bool = False) -> str:
    """The corpus handed to the model. Admin rows carry Matcha's assessment
    (severity/incident flag/extracted doc); employee rows carry only what
    the channel itself produced — title, category, date, and whether it
    became a formal incident.

    `filtered=True` (only meaningful when `events` is empty) means this
    channel actually has logged events the asker just can't see — a
    non-admin's `behavioral` filter excluded all of them. The rendered text
    must not say the room is clean, the same distinction `no_events_text`
    draws for the fully-empty case."""
    if not events:
        if filtered:
            return "(nothing in this channel that you can see — an admin may see more)"
        return "(nothing logged in this channel)"
    lines = []
    for ev in events:
        label = categories.category_label(ev["category"])
        when = ev["created_at"].strftime("%b %d, %Y") if ev.get("created_at") else "unknown date"
        parts = [f"- [{when}] {label}: {ev.get('title') or 'Untitled'}"]
        if ev.get("status") == "promoted":
            parts.append("(promoted to a formal incident)")
        if is_admin:
            if ev.get("severity_hint"):
                parts.append(f"(severity {ev['severity_hint']})")
            if ev.get("incident_recommendation") and ev.get("status") != "promoted":
                parts.append("(flagged for possible incident review)")
            doc = ev.get("doc") if isinstance(ev.get("doc"), dict) else None
            if doc:
                detail = "; ".join(f"{k}: {v}" for k, v in list(doc.items())[:4])
                parts.append(f"— {detail[:400]}")
        lines.append(" ".join(parts))
    return "\n".join(lines)


def no_events_text(*, filtered: bool) -> str:
    """Deterministic reply when there's nothing to narrate — no model call
    for an empty corpus. `filtered` distinguishes "this channel has logged
    nothing" from "nothing this asker can see", which must not read as the
    same thing: telling a team member the room is clean when a behavioral
    event exists is a false statement about the record."""
    if filtered:
        return (
            "\U0001F4CB Nothing I can pull up here. If something was reported, "
            "an admin can see the full picture in Ops."
        )
    return (
        "\U0001F4CB Nothing's been logged in this channel yet. Tell me what "
        "happened and I'll write it down."
    )


def help_text(*, is_admin: bool, extra_lines: tuple[str, ...] = ()) -> str:
    """Deterministic capability pill — no model call. This is the answer to
    "what can you do", so it must be correct rather than fluent, and it
    doubles as the fallback whenever intent is HELP.

    `extra_lines` is `channel_grounding.help_lines(...)` — only topics this
    asker can actually reach right now, so this pill never advertises
    something the next question would refuse."""
    lines = [
        "\U0001F4CB Here's what I can do in this channel:",
        "• Log anything that happened — just tell me "
        "(\"@huume walk-in freezer is at 48°\")",
        "• Answer what's been logged in here lately "
        "(\"@huume what happened last week?\")",
        "• Fill in details — reply to any of my messages and I'll add it",
        "• Share the anonymous reporting link (\"@huume send the reporting link\")",
        *extra_lines,
    ]
    if is_admin:
        lines.append(
            "• Everything logged is reviewable in Ops, where you can "
            "promote something into a formal incident",
        )
    return "\n".join(lines)


FIRST_TIME_HINT = (
    "\n\U0001F4A1 You can also ask me what's been logged in here, or reply to "
    "add detail. Say \"@huume help\" anytime."
)
