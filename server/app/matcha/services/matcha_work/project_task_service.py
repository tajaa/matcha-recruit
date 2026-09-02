"""Project task service — project-scoped kanban tasks for collab projects.

Project tasks live in `mw_tasks` with `project_id` set (null project_id is reserved for
company-wide dashboard tasks surfaced via /tasks). Board state is tracked in
`board_column` (todo|in_progress|changes_requested|review|done). The existing
`status` column (pending|completed|cancelled) stays in sync with `board_column`:
- moving to 'done'   → status='completed', completed_at=now
- moving out of 'done' → status='pending',  completed_at=null
- toggling status complete ↔ moves column to 'done' / 'todo' accordingly

Review send-back (`reject_project_task`) drops a card from review back to `todo`
and auto-opens the next round: unfixed checklist items roll forward into the new
round (the live, foreground checklist) while items the reviewer accepted stay
archived on the prior round (background). review_note + the round_started title
carry the feedback; the churn count tracks how many times it bounced. The
`changes_requested` column remains valid for manual drag but is no longer
auto-populated by send-back.
"""

import json
import logging
import re
from datetime import date as _date, datetime, timedelta, timezone
from typing import Optional
from uuid import UUID
from zoneinfo import ZoneInfo

from ....database import get_connection
from .task_events import broadcast_task_event
from .project_task_notifications import (
    _TRANSITION_TEMPLATES,
    _lookup_actor_identity,
    _notify_task_assigned,
    _notify_task_column_transition,
    _notify_task_comment,
    _notify_task_rejected,
    _post_kanban_move_to_chat,
)

logger = logging.getLogger(__name__)

# A board's Done column accumulates forever, so it is never fetched whole.
# `week` (the default) sends only what was finished this Pacific week; `all`
# sends the most recently finished, capped. Both are bounded by DONE_MAX_ROWS —
# a two-year-old board would otherwise ship thousands of closed cards, each
# carrying attachments + history subquery results, on every project open.
DONE_SCOPE_WEEK = "week"
DONE_SCOPE_ALL = "all"
DONE_MAX_ROWS = 200

_PACIFIC = ZoneInfo("America/Los_Angeles")


def pacific_week_start(now: Optional[datetime] = None) -> datetime:
    """Monday 00:00 Pacific of the week containing `now`, as an aware UTC-comparable
    datetime. Matches the client's `PacificDateFormatter.startOfWeek` so the board
    and the weekly replay agree on where a week begins."""
    now = (now or datetime.now(timezone.utc)).astimezone(_PACIFIC)
    midnight = now.replace(hour=0, minute=0, second=0, microsecond=0)
    return midnight - timedelta(days=midnight.weekday())


async def _log_task_history(
    conn,
    *,
    task_id: UUID,
    project_id: UUID,
    actor_user_id: Optional[UUID],
    event_type: str,
    from_value: Optional[str] = None,
    to_value: Optional[str] = None,
    metadata: Optional[dict] = None,
) -> None:
    """Insert a row into mw_task_history. Best-effort — if the table
    doesn't exist yet (migration not run), warn and continue so the
    underlying task write still succeeds.
    """
    try:
        await conn.execute(
            """
            INSERT INTO mw_task_history
                (task_id, task_id_text, project_id, actor_user_id, event_type, from_value, to_value, metadata)
            VALUES ($1, $2, $3, $4, $5, $6, $7, $8::jsonb)
            """,
            task_id, str(task_id) if task_id is not None else None, project_id, actor_user_id, event_type,
            from_value, to_value, json.dumps(metadata or {}),
        )
    except Exception as e:
        logger.warning(
            "Failed to log task history task=%s event=%s: %s",
            task_id, event_type, e,
        )


_ALLOWED_COLUMNS = {
    "todo", "in_progress", "changes_requested", "review", "done",
    # Sales-pipeline stages kept here for backward compat (pre-migration rows).
    # New tasks place the stage in pipeline_column, not board_column.
    "lead", "qualified", "proposal", "negotiation", "closed",
}
_ALLOWED_PIPELINE_COLUMNS = {"lead", "qualified", "proposal", "negotiation", "closed"}
_ALLOWED_PRIORITIES = {"critical", "high", "medium", "low"}
# Ticket-template kinds stored in mw_tasks.category. "manual" = no template
# (blank task / legacy rows) and renders without a badge on the client.
_ALLOWED_CATEGORIES = {"manual", "engineering", "sales", "product", "bug", "general", "feat", "fix"}
# Sales-pipeline deal outcome. "open" = still in the funnel; won/lost are
# terminal and independent of board_column (a deal can be lost from any stage).
_ALLOWED_OUTCOMES = {"open", "won", "lost"}
# Sales follow-up activity kinds, logged onto the task history timeline.
_ALLOWED_ACTIVITY_KINDS = {"call", "email", "note", "meeting"}

_AUTOPR_NO_SPEC_RE = re.compile(
    r"\[autopr:no-spec [^\]]+\]\s+"
    r"(already_fixed|migration_required|policy_blocked|external_dependency)(?:\s|$)"
)
_AUTOPR_TEST_ROUTE_RE = re.compile(
    r"(?:test[-_ ]route|reproduce(?:[-_ ]route)?)\s*(?:=|:)\s*(/[^\s]+)",
    re.IGNORECASE,
)
_AUTOPR_DIRECTIVE_MARKER_RE = re.compile(r"\[autopr:directives ([a-z_,]+)\]")
# Operator directive grammar. Deliberately generous: this parser only ever
# sees text an authorized owner bound to one exact AutoPR decision, so a plain
# affirmative ("you can work on this", "do it anyway", "draft the migration")
# is authority. Keep in lock-step with the harness-side copy in
# scripts/kanban-autopr/resolve-directive-policy.py.
_AUTOPR_LEAD_IN = (
    r"^(?:(?:please|pls|hey|ok|okay|yes|yep|yeah|sure|thanks)\b[\s,]*)*"
    r"(?:(?:anyway|anyways|either\s+way|regardless|still|nonetheless)\b[\s,]*)*"
    r"(?:i\s+(?:need|want|expect)\s+(?:you\s+)?to\s+)?"
    r"(?:(?:you|u|it|autopr|the\s+bot|the\s+agent)\s+)?"
    r"(?:(?:can|may|must|should|could|shall|will|need\s+to|have\s+to|ought\s+to"
    r"|are\s+(?:ok|okay|clear|free|allowed)\s+to)\s+)?"
    r"(?:go\s+ahead\s+(?:and\s+)?)?"
    r"(?:(?:just|still|absolutely|definitely|certainly|totally|really|simply"
    r"|please|now|then|instead|anyway|anyways)\s+)*"
)
_AUTOPR_DRAFT_COMMAND_RE = re.compile(
    _AUTOPR_LEAD_IN
    + r"(?:draft|create|open|make|write|author|submit|raise|put\s+up)\s+"
    r"(?:(?:this|that|a|an|the)\s+)?(?:draft\s+)?"
    r"(?:pr|pull\s+request|migration(?:\s+(?:script|file|version))?s?)\b"
)
_AUTOPR_WORK_COMMAND_RE = re.compile(
    _AUTOPR_LEAD_IN
    + r"(?:work\s+on|start\s+(?:work\s+)?on|implement|build|do|handle|fix"
    r"|finish|complete|tackle|take\s+on|pick\s+up|proceed\s+with)\s+"
    r"(?:this|that|it|the\s+(?:ticket|card|pr|pull\s+request|work|change|migration))\b"
)
_AUTOPR_GO_AHEAD_COMMAND_RE = re.compile(
    _AUTOPR_LEAD_IN + r"(?:go\s+ahead|proceed|carry\s+on|keep\s+going)\b"
)
_AUTOPR_FORCE_NEGATION_RE = re.compile(
    r"(?:\b(?:do\s+not|don't|dont|never|not|no)\b.{0,40}"
    r"\b(?:work|implement|draft|create|open|build|handle|fix|finish|proceed"
    r"|go\s+ahead)\b)"
    r"|(?:\b(?:work|implement|draft|create|open|build|handle|fix|finish|proceed)\b"
    r".{0,20}\b(?:not|never)\b)"
)
_AUTOPR_EXPLICIT_DRAFT_COMMANDS = {
    "draft-pr", "draft pr", "force-pr", "force pr", "force", "override",
    "draft it", "do it", "work on it", "ship it",
}


def _is_autopr_waiting_for_answers_note(note: str) -> bool:
    normalized = (note or "").strip()
    lowered = normalized.lower()
    return normalized.startswith("🤖 AUTO SETUP · BLOCKED: AWAITING ANSWERS") or (
        lowered.startswith("from auto setup") and "answers needed" in lowered
    )


def _is_autopr_waiting_for_runtime_approval_note(note: str) -> bool:
    normalized = (note or "").strip()
    return (
        normalized.startswith("🤖 AUTO SETUP · PAUSED: APPROVE 10 MORE MINUTES")
        or normalized.startswith("🤖 AUTO SETUP · PAUSED: RUNTIME APPROVAL REQUIRED")
    )


def _parse_autopr_directives(text: str) -> tuple[list[str], Optional[str]]:
    """Parse operator-owned directives from decision-bound context.

    This function is called only for an authorized reply bound to the exact
    live AutoPR decision, so a clear affirmative work command is authority
    even without a ``--`` prefix. Ordinary ticket prose never reaches this
    parser. Other directives retain their explicit ``--`` marker.
    """
    directives: list[str] = []
    test_route: Optional[str] = None
    for raw_line in (text or "").splitlines():
        line = raw_line.strip()
        marked = line.startswith("--")
        directive_text = line[2:] if marked else line
        instruction = " ".join(
            directive_text.strip().lower().replace("’", "'").split()
        )
        explicit_draft = instruction in _AUTOPR_EXPLICIT_DRAFT_COMMANDS
        natural_draft = bool(_AUTOPR_DRAFT_COMMAND_RE.search(instruction))
        natural_work = bool(_AUTOPR_WORK_COMMAND_RE.search(instruction))
        natural_go_ahead = bool(_AUTOPR_GO_AHEAD_COMMAND_RE.search(instruction))
        force_is_negated = bool(_AUTOPR_FORCE_NEGATION_RE.search(instruction))
        if (
            (explicit_draft or natural_draft or natural_work or natural_go_ahead)
            and not force_is_negated
            and "draft_pr" not in directives
        ):
            directives.append("draft_pr")
        if marked and (
            instruction in {"trust-still-broken", "trust still broken"}
            or ("trust" in instruction and any(
                phrase in instruction
                for phrase in ("still not working", "isn't working", "is not working", "still broken")
            ))
        ) and "trust_still_broken" not in directives:
            directives.append("trust_still_broken")
        if marked and instruction in {
            "extend-runtime",
            "extend runtime",
            "allow-more-time",
            "allow more time",
        } and "extend_runtime" not in directives:
            directives.append("extend_runtime")
        route_match = _AUTOPR_TEST_ROUTE_RE.search(directive_text) if marked else None
        if route_match:
            candidate = route_match.group(1).rstrip(".,;)")
            if (
                candidate.startswith("/")
                and not candidate.startswith("//")
                and "://" not in candidate
                and ".." not in candidate
                and "?" not in candidate
                and "#" not in candidate
                and len(candidate) <= 500
            ):
                test_route = candidate
    return directives, test_route


class AutoPRReconsiderationConflict(ValueError):
    """The AutoPR decision being answered is stale or no longer reconsiderable."""

# History event types that count as a "viewable update" on a ticket — drives
# the kanban card's unviewed-updates badge + the viewer's UPDATES checkoff list.
# Keep in lock-step with the client's COUNTED_UPDATE_EVENTS (TicketUpdatesStore):
# comments, round changes, subtasks added, column moves + review send-backs.
# (Images count only when attached to a comment — they have no standalone
# history row.) Intentionally excludes assignee/description/progress-note edits,
# subtask completion/reopen/delete, created, and deleted.
COUNTED_UPDATE_EVENTS = (
    'activity', 'round_started', 'subtask_added', 'column_change', 'review_rejected',
    'subtask_rejected',
)


async def _broadcast_task_event_safe(project_id: UUID, event: str, payload: dict) -> None:
    """Wrapped broadcast — never fails the caller; logs at warning level."""
    try:
        logger.info("dispatching %s for project=%s", event, project_id)
        await broadcast_task_event(project_id, event, payload)
    except Exception as e:
        logger.warning("Failed to broadcast %s for project %s: %s", event, project_id, e)


def _row_to_task(row: dict) -> dict:
    d = dict(row)
    for key in (
        "id", "project_id", "created_by", "assigned_to",
        "autopr_reconsideration_event_id",
    ):
        if d.get(key) is not None:
            d[key] = str(d[key])
    if d.get("due_date") is not None:
        d["due_date"] = d["due_date"].isoformat()
    for key in (
        "completed_at", "created_at", "updated_at", "last_moved_at",
        "autopr_reconsideration_at", "autopr_run_requested_at",
    ):
        if d.get(key) is not None:
            d[key] = d[key].isoformat()
    # Sales-pipeline fields (present only once the salespipe0001 migration is
    # applied; NULL on non-sales boards). Dates → ISO; NUMERIC → float so the
    # JSON response carries a plain number rather than a Decimal.
    for key in ("next_action_at", "expected_close"):
        if d.get(key) is not None:
            d[key] = d[key].isoformat()
    if d.get("deal_value") is not None:
        d["deal_value"] = float(d["deal_value"])
    return d


async def request_autopr_reconsideration(
    *,
    project_id: UUID,
    task_id: UUID,
    actor_user_id: UUID,
    expected_progress_note: str,
    body: Optional[str] = None,
    attachment_ids: Optional[list[UUID]] = None,
) -> Optional[dict]:
    """Attach human evidence to one exact AutoPR context-blocked decision.

    The history event is the durable retry signal. It stores the full current
    progress note in autopr_reconsideration_of; the task-list query only
    exposes the event as pending while that value still equals the task's live
    progress note. Any subsequent AutoPR outcome changes the note and consumes
    this signal without deleting audit history or faking a board move.
    """
    text = (body or "").strip()
    if not text and not attachment_ids:
        raise ValueError("Additional context requires text or an attachment")
    if len(text) > 10_000:
        raise ValueError("Additional context must be 10,000 characters or fewer")
    directives, test_route = _parse_autopr_directives(text)

    expected = (expected_progress_note or "").strip()
    async with get_connection() as conn:
        async with conn.transaction():
            task = await conn.fetchrow(
                """
                SELECT id, progress_note, board_column, status
                FROM mw_tasks
                WHERE id = $1 AND project_id = $2
                FOR UPDATE
                """,
                task_id, project_id,
            )
            if not task:
                return None

            if (
                task["status"] == "cancelled"
                or task["board_column"] not in ("todo", "changes_requested")
            ):
                raise AutoPRReconsiderationConflict(
                    "AutoPR reconsideration is only available while the ticket "
                    "is in Todo or Changes Requested"
                )

            current_note_raw = task["progress_note"] or ""
            current_note = current_note_raw.strip()
            marker_match = _AUTOPR_DIRECTIVE_MARKER_RE.search(current_note)
            if marker_match:
                for inherited in marker_match.group(1).split(","):
                    if inherited in {"draft_pr", "trust_still_broken"} and inherited not in directives:
                        directives.append(inherited)
            if not expected or current_note != expected:
                raise AutoPRReconsiderationConflict(
                    "The AutoPR decision changed; refresh the ticket and try again"
                )
            waiting_for_answers = _is_autopr_waiting_for_answers_note(current_note)
            waiting_for_runtime_approval = _is_autopr_waiting_for_runtime_approval_note(
                current_note
            )
            if (
                not _AUTOPR_NO_SPEC_RE.search(current_note)
                and not waiting_for_answers
                and not waiting_for_runtime_approval
            ):
                raise AutoPRReconsiderationConflict(
                    "This ticket no longer has an AutoPR decision awaiting context"
                )

            metadata: dict = {
                "kind": "autopr_additional_context",
                "body": text,
                # Preserve the exact database value because the pending-event
                # query intentionally binds this retry to that exact decision.
                "autopr_reconsideration_of": current_note_raw,
                "reply_to_name": "AUTO SETUP",
                "reply_to_excerpt": current_note.replace("\n", " ")[:140],
            }
            if directives:
                # Keep these strings for the desktop history decoder. The
                # trusted harness expands them back into structured policy.
                metadata["autopr_directives"] = ",".join(directives)
            if test_route:
                metadata["autopr_test_route"] = test_route
            if attachment_ids:
                metadata["attachment_ids"] = [str(a) for a in attachment_ids]

            row = await conn.fetchrow(
                """
                INSERT INTO mw_task_history
                    (task_id, task_id_text, project_id, actor_user_id,
                     event_type, metadata)
                VALUES ($1, $2, $3, $4, 'activity', $5::jsonb)
                RETURNING id, created_at
                """,
                task_id, str(task_id), project_id, actor_user_id,
                json.dumps(metadata),
            )

    await _notify_task_comment(
        project_id=project_id,
        task_id=task_id,
        actor_user_id=actor_user_id,
        body=text or "Added evidence for AutoPR reconsideration",
    )
    return {
        "ok": True,
        "activity_id": str(row["id"]),
        "created_at": row["created_at"].isoformat(),
        "autopr_reconsideration_pending": True,
        "autopr_directives": directives,
        "autopr_test_route": test_route,
    }


# The four Espresso boards the kanban-autopr harness actually watches (kept in
# sync with scripts/seed/autopr_bot.py's PROJECTS list and scripts/kanban-autopr
# /lib.sh's KANBAN_AUTOPR_PROJECT_IDS). Anything outside this set has no
# harness polling it, so a run request there could never be claimed — reject it
# at the door instead of queueing work nothing will pick up.
KANBAN_AUTOPR_PROJECT_IDS = {
    "7f728636-3219-4d83-9df3-a4682e3242de",  # WerkWerk
    "fade10b4-36ff-4c60-af59-5cc6058285ab",  # Beetlejuse
    "84823d21-c752-4abd-9696-4c93c8b3c21e",  # Gummfit
    "8b924347-d6e4-4000-8e7d-ca8f46f76fba",  # MATCHA
}

_AUTOPR_RUN_LANES = ("todo", "changes_requested")

# How long a "run now" request can still be waiting for the harness. The local
# watcher dispatches within a minute and the selector consumes the request in
# the pass that dispatch triggers, so anything older than this was dropped on
# the floor — a run killed before select.sh ran, or a board the AutoPR bot does
# not watch. Bounding it is what stops a stranded request from forcing a Kanban
# dispatch every five minutes forever, keeps the once-a-minute poll off a
# full-history scan, and lets the card's "Queued for AutoPR" chip clear itself.
# A code constant interpolated into SQL below; never user input.
_AUTOPR_RUN_REQUEST_TTL = "30 minutes"

# The bookkeeping rows this feature writes carry no body and render nothing, so
# they must not reach the unviewed-updates badge or the ticket activity graph.
# They share event_type='activity' with real discussion notes and are told
# apart by metadata kind.
_AUTOPR_BOOKKEEPING_KINDS = ("autopr_run_request", "autopr_run_claim")


async def request_autopr_run(
    *,
    project_id: UUID,
    task_id: UUID,
    actor_user_id: UUID,
) -> Optional[dict]:
    """Queue one immediate AutoPR pass for this card.

    The scheduled lane is deliberately slow. This is the human's way past it:
    a request sits pending until the harness posts a matching claim, and the
    local watcher dispatches a run as soon as it sees one. Repeating the
    request while one is already pending is idempotent — it returns the
    existing timestamp rather than stacking events.
    """
    if str(project_id) not in KANBAN_AUTOPR_PROJECT_IDS:
        raise AutoPRReconsiderationConflict(
            "AutoPR does not watch this board, so it cannot pick up this ticket"
        )
    async with get_connection() as conn:
        async with conn.transaction():
            task = await conn.fetchrow(
                """
                SELECT id, board_column, status
                FROM mw_tasks
                WHERE id = $1 AND project_id = $2
                FOR UPDATE
                """,
                task_id, project_id,
            )
            if not task:
                return None
            if task["status"] == "cancelled" or task["board_column"] not in _AUTOPR_RUN_LANES:
                raise AutoPRReconsiderationConflict(
                    "AutoPR only picks up tickets in Todo or Changes Requested"
                )
            pending_at = await conn.fetchval(
                f"""
                SELECT MAX(h.created_at) FROM mw_task_history h
                WHERE h.task_id = $1
                  AND h.event_type = 'activity'
                  AND h.metadata->>'kind' = 'autopr_run_request'
                  AND h.created_at > now() - interval '{_AUTOPR_RUN_REQUEST_TTL}'
                  AND h.created_at > COALESCE((
                        SELECT MAX(c.created_at) FROM mw_task_history c
                        WHERE c.task_id = $1
                          AND c.event_type = 'activity'
                          AND c.metadata->>'kind' = 'autopr_run_claim'
                      ), '-infinity'::timestamptz)
                """,
                task_id,
            )
            if pending_at is not None:
                return {
                    "ok": True,
                    "already_pending": True,
                    "autopr_run_requested_at": pending_at.isoformat(),
                }
            row = await conn.fetchrow(
                """
                INSERT INTO mw_task_history
                    (task_id, task_id_text, project_id, actor_user_id,
                     event_type, metadata)
                VALUES ($1, $2, $3, $4, 'activity', $5::jsonb)
                RETURNING id, created_at
                """,
                task_id, str(task_id), project_id, actor_user_id,
                # No body: the discussion feed renders bodyless notes as
                # nothing, so a queue request stays out of the conversation.
                json.dumps({"kind": "autopr_run_request"}),
            )
    return {
        "ok": True,
        "already_pending": False,
        "activity_id": str(row["id"]),
        "autopr_run_requested_at": row["created_at"].isoformat(),
    }


async def claim_autopr_run(
    *,
    project_id: UUID,
    task_id: UUID,
    actor_user_id: Optional[UUID] = None,
) -> Optional[dict]:
    """Consume any pending run request for this card.

    Called by the trusted harness when it actually starts investigating, so a
    crashed or unselectable card cannot make the watcher dispatch forever.
    """
    async with get_connection() as conn:
        exists = await conn.fetchval(
            "SELECT 1 FROM mw_tasks WHERE id = $1 AND project_id = $2",
            task_id, project_id,
        )
        if not exists:
            return None
        row = await conn.fetchrow(
            """
            INSERT INTO mw_task_history
                (task_id, task_id_text, project_id, actor_user_id,
                 event_type, metadata)
            VALUES ($1, $2, $3, $4, 'activity', $5::jsonb)
            RETURNING id, created_at
            """,
            task_id, str(task_id), project_id, actor_user_id,
            json.dumps({"kind": "autopr_run_claim"}),
        )
    return {"ok": True, "claimed_at": row["created_at"].isoformat()}


async def list_autopr_run_requests(project_ids: list[UUID]) -> list[dict]:
    """Pending run requests across the caller's projects.

    Deliberately tiny: the local watcher polls this once a minute and must not
    pay for a whole board bundle to learn that nothing is queued.
    """
    if not project_ids:
        return []
    async with get_connection() as conn:
        # The TTL predicate is what keeps this a bounded query: it rides
        # idx_mw_task_history_project_created (project_id, created_at) instead
        # of walking every history row on four boards, 1440 times a day, to
        # answer "is anything queued?". The claim lookup is bounded by the same
        # window — a claim older than the oldest live request cannot matter.
        # LIMIT is a backstop only; the watcher acts on the queue's existence.
        rows = await conn.fetch(
            f"""
            SELECT t.id AS task_id, t.project_id, t.board_column,
                   MAX(h.created_at) AS requested_at
            FROM mw_task_history h
            JOIN mw_tasks t ON t.id = h.task_id
            WHERE h.project_id = ANY($1::uuid[])
              AND h.created_at > now() - interval '{_AUTOPR_RUN_REQUEST_TTL}'
              AND h.event_type = 'activity'
              AND h.metadata->>'kind' = 'autopr_run_request'
              AND t.status != 'cancelled'
              AND t.board_column = ANY($2::text[])
              AND h.created_at > COALESCE((
                    SELECT MAX(c.created_at) FROM mw_task_history c
                    WHERE c.task_id = h.task_id
                      AND c.created_at > now() - interval '{_AUTOPR_RUN_REQUEST_TTL}'
                      AND c.event_type = 'activity'
                      AND c.metadata->>'kind' = 'autopr_run_claim'
                  ), '-infinity'::timestamptz)
            GROUP BY t.id, t.project_id, t.board_column
            ORDER BY MAX(h.created_at)
            LIMIT 200
            """,
            project_ids, list(_AUTOPR_RUN_LANES),
        )
    return [
        {
            "task_id": str(r["task_id"]),
            "project_id": str(r["project_id"]),
            "board_column": r["board_column"],
            "requested_at": r["requested_at"].isoformat(),
        }
        for r in rows
    ]


async def log_task_activity(
    *,
    project_id: UUID,
    task_id: UUID,
    actor_user_id: Optional[UUID],
    kind: str,
    body: Optional[str] = None,
    attachment_ids: Optional[list[UUID]] = None,
    reply_to: Optional[UUID] = None,
) -> Optional[dict]:
    """Log a sales follow-up activity (call/email/note/meeting) onto a task's
    history timeline. Reuses mw_task_history (event_type='activity') so it
    renders in the existing task viewer timeline — no separate table.
    Returns None if the task doesn't belong to the project.

    `attachment_ids` (optional) links this note to N existing mw_project_files
    rows for the task. Caller is responsible for validating ownership before
    invoking. Stored inside metadata JSONB so no schema change is needed.

    `reply_to` (optional) is the mw_task_history id of an existing comment this
    note replies to. We resolve the parent's author + a short body excerpt
    server-side and stash them in metadata (reply_to / reply_to_name /
    reply_to_excerpt) so the client can render the quoted parent without a
    second round-trip. A reply to a non-note row is ignored.
    """
    kind = (kind or "note").strip().lower()
    if kind not in _ALLOWED_ACTIVITY_KINDS:
        raise ValueError(f"Invalid activity kind: {kind}")
    async with get_connection() as conn:
        exists = await conn.fetchrow(
            "SELECT id FROM mw_tasks WHERE id = $1 AND project_id = $2",
            task_id, project_id,
        )
        if not exists:
            return None
        metadata: dict = {"kind": kind, "body": (body or "").strip()}
        if attachment_ids:
            metadata["attachment_ids"] = [str(a) for a in attachment_ids]
        if reply_to:
            parent = await conn.fetchrow(
                """
                SELECT h.metadata,
                       COALESCE(c.name, CONCAT(e.first_name, ' ', e.last_name),
                                a.name, u.email) AS actor_name
                FROM mw_task_history h
                LEFT JOIN users u     ON u.id      = h.actor_user_id
                LEFT JOIN clients c   ON c.user_id = h.actor_user_id
                LEFT JOIN employees e ON e.user_id = h.actor_user_id
                LEFT JOIN admins a    ON a.user_id = h.actor_user_id
                WHERE h.id = $1 AND h.task_id = $2 AND h.event_type = 'activity'
                """,
                reply_to, task_id,
            )
            if parent:
                metadata["reply_to"] = str(reply_to)
                if parent["actor_name"]:
                    metadata["reply_to_name"] = parent["actor_name"]
                pmeta = parent["metadata"]
                if isinstance(pmeta, str):
                    import json as _json
                    try:
                        pmeta = _json.loads(pmeta)
                    except Exception:
                        pmeta = {}
                parent_body = (pmeta or {}).get("body") if isinstance(pmeta, dict) else None
                if parent_body:
                    excerpt = parent_body.strip().replace("\n", " ")
                    metadata["reply_to_excerpt"] = excerpt[:140]
        await _log_task_history(
            conn,
            task_id=task_id,
            project_id=project_id,
            actor_user_id=actor_user_id,
            event_type="activity",
            metadata=metadata,
        )
    # Notify the other participants of a new in-ticket comment (the discussion
    # channel). Only plain notes — sales touchpoints (call/email/meeting) don't
    # ping collaborators. Best-effort; never blocks the log.
    if kind == "note":
        await _notify_task_comment(
            project_id=project_id,
            task_id=task_id,
            actor_user_id=actor_user_id,
            body=body or "",
        )
    return {"ok": True, "kind": kind}


async def count_done_tasks(project_id: UUID) -> dict:
    """How many cards sit in Done, and how many landed there this Pacific week.
    The board needs the total to label its "show earlier finished" expander —
    `list_project_tasks` deliberately never returns the whole column."""
    async with get_connection() as conn:
        row = await conn.fetchrow(
            """
            SELECT COUNT(*) AS total,
                   COUNT(*) FILTER (
                       WHERE COALESCE(t.completed_at, t.updated_at, t.created_at) >= $2
                   ) AS this_week
            FROM mw_tasks t
            WHERE t.project_id = $1 AND t.status != 'cancelled' AND t.board_column = 'done'
            """,
            project_id, pacific_week_start(),
        )
    return {"total": row["total"], "this_week": row["this_week"]}


async def _visible_done_task_ids(conn, project_id: UUID, scope: str, limit: int) -> list[UUID]:
    """The subset of the Done column a board is allowed to load. Ordered
    newest-finished first and hard-capped, so the payload can't grow with the
    project's age. Cards with no `completed_at` (pre-dating the column, or moved
    by a path that didn't stamp it) fall back to updated/created time rather than
    dropping out of Done entirely."""
    limit = max(1, min(limit, DONE_MAX_ROWS))
    recency = "COALESCE(t.completed_at, t.updated_at, t.created_at)"
    params: list = [project_id]
    week_clause = ""
    if scope == DONE_SCOPE_WEEK:
        params.append(pacific_week_start())
        week_clause = f"AND {recency} >= $2"
    params.append(limit)
    rows = await conn.fetch(
        f"""
        SELECT t.id FROM mw_tasks t
        WHERE t.project_id = $1 AND t.status != 'cancelled' AND t.board_column = 'done'
          {week_clause}
        ORDER BY {recency} DESC
        LIMIT ${len(params)}
        """,
        *params,
    )
    return [r["id"] for r in rows]


async def list_project_tasks(
    project_id: UUID,
    viewer_id: Optional[UUID] = None,
    *,
    done_scope: str = DONE_SCOPE_WEEK,
    done_limit: int = DONE_MAX_ROWS,
) -> list[dict]:
    # Inline the counted-event literals (code constants, not user input) so the
    # badge subqueries stay in lock-step with COUNTED_UPDATE_EVENTS.
    _counted = ", ".join(f"'{e}'" for e in COUNTED_UPDATE_EVENTS)
    # AutoPR's run-request / run-claim rows ride event_type='activity' but have
    # no body, so NoteRow renders nothing for them. Counting them would put an
    # unviewed-updates chip on the card that opening the ticket cannot clear.
    _bookkeeping = ", ".join(f"'{k}'" for k in _AUTOPR_BOOKKEEPING_KINDS)
    _skip_bookkeeping3 = (
        f"AND COALESCE(h3.metadata->>'kind', '') NOT IN ({_bookkeeping})"
    )
    _skip_bookkeeping4 = (
        f"AND COALESCE(h4.metadata->>'kind', '') NOT IN ({_bookkeeping})"
    )
    # Exclude the viewer's OWN history events from the unviewed-updates badge +
    # count: your own move/comment isn't "an update you haven't seen", so a
    # reviewer who drags a ticket to Done shouldn't then see it ringed yellow.
    # NULL viewer_id (no user context) counts every actor. Applied to both the
    # count and the id list so they stay consistent.
    params: list = [project_id]
    if viewer_id is not None:
        params.append(viewer_id)
        _self3 = "AND h3.actor_user_id IS DISTINCT FROM $2"
        _self4 = "AND h4.actor_user_id IS DISTINCT FROM $2"
    else:
        _self3 = _self4 = ""
    async with get_connection() as conn:
        # Resolve which Done cards are in scope first, then admit exactly those.
        # Filtering inside the main query instead would still evaluate the
        # per-card history subqueries for every closed card on the board.
        done_ids = await _visible_done_task_ids(conn, project_id, done_scope, done_limit)
        params.append(done_ids)
        _done_clause = f"AND (t.board_column <> 'done' OR t.id = ANY(${len(params)}::uuid[]))"
        rows = await conn.fetch(
            f"""
            SELECT t.id, t.project_id, t.company_id, t.created_by, t.title, t.description,
                   t.due_date, t.priority, t.status, t.board_column, t.assigned_to,
                   t.completed_at, t.created_at, t.updated_at, t.progress_note, t.category,
                    t.element_id, t.review_note,
                    to_jsonb(t) ->> 'pr_url' AS pr_url,
                    (to_jsonb(t) ->> 'pr_number')::integer AS pr_number,
                   t.deal_value, t.probability, t.contact_name, t.contact_company,
                   t.contact_email, t.contact_phone, t.outcome, t.loss_reason,
                   t.next_action_at, t.expected_close,
                   COALESCE(t.pipeline_column, 'lead') AS pipeline_column,
                   (autopr_ctx.id IS NOT NULL) AS autopr_reconsideration_pending,
                   autopr_ctx.id AS autopr_reconsideration_event_id,
                   autopr_ctx.created_at AS autopr_reconsideration_at,
                   -- "Run AutoPR now" on the card. Pending until the harness
                   -- claims the card for a run, so the scheduled lane can stay
                   -- slow without a human having to wait for its next tick.
                   autopr_run.created_at AS autopr_run_requested_at,
                   -- Last time this card crossed columns, for the "Moved …" stamp
                   -- on the kanban card. Null until the first move. Counts a
                   -- review_rejected as a move too (review → changes_requested)
                   -- so a freshly bounced card resets its aging clock instead
                   -- of inheriting the time it entered review.
                   (SELECT MAX(h.created_at) FROM mw_task_history h
                      WHERE h.task_id = t.id
                        AND h.event_type IN ('column_change', 'review_rejected')) AS last_moved_at,
                   -- How many times this card has been sent back from review.
                   -- Drives the "↻ ×N" churn chip so thrashing tickets are
                   -- visible at board glance, not just in the card history.
                   (SELECT COUNT(*) FROM mw_task_history h2
                      WHERE h2.task_id = t.id AND h2.event_type = 'review_rejected') AS review_cycle_count,
                   -- Checklist progress for the card face ("done/total"),
                   -- scoped to the ticket's CURRENT round (max round_index) so
                   -- the card matches the live (current-round) checklist —
                   -- archived past-round items don't inflate the count.
                   (SELECT COUNT(*) FROM mw_subtasks s
                      WHERE s.task_id = t.id
                        AND s.round_index = (SELECT COALESCE(MAX(round_index), 1)
                                             FROM mw_subtasks s3 WHERE s3.task_id = t.id)) AS subtask_total,
                   (SELECT COUNT(*) FROM mw_subtasks s
                      WHERE s.task_id = t.id AND s.is_done
                        AND s.round_index = (SELECT COALESCE(MAX(round_index), 1)
                                             FROM mw_subtasks s3 WHERE s3.task_id = t.id)) AS subtask_done,
                   -- Unviewed-updates badge on the card. update_count = total
                   -- "viewable" history events (comments / rounds / subtasks
                   -- added / moves+send-backs); recent_event_ids = the newest
                   -- such event ids so the client can diff against its per-user
                   -- viewed set (TicketUpdatesStore) without fetching full
                   -- history per card. Capped at 100 (overflow is cosmetic).
                   (SELECT COUNT(*) FROM mw_task_history h3
                      WHERE h3.task_id = t.id
                        AND h3.event_type IN ({_counted})
                        {_skip_bookkeeping3}
                        {_self3}) AS update_count,
                   ARRAY(SELECT h4.id::text FROM mw_task_history h4
                      WHERE h4.task_id = t.id
                        AND h4.event_type IN ({_counted})
                        {_skip_bookkeeping4}
                        {_self4}
                      ORDER BY h4.created_at DESC
                      LIMIT 100) AS recent_event_ids,
                   -- Split assignee fields so the client can pick a
                   -- human-readable name and never fall back to showing
                   -- a raw email in cards / tooltips. Older callsites
                   -- expected `assigned_name` to fall back to email; that
                   -- behavior moves to the client via AssigneeDisplay.
                   COALESCE(c.name, CONCAT(e.first_name, ' ', e.last_name), a.name) AS assigned_name,
                   u.email AS assigned_email,
                   u.avatar_url AS assigned_avatar_url,
                   -- Creator identity for the card-face "created by" avatar
                   -- badge. Mirrors the assignee join above, aliased to avoid
                   -- collision.
                   COALESCE(c2.name, CONCAT(e2.first_name, ' ', e2.last_name), a2.name, u2.email) AS created_by_name,
                   u2.avatar_url AS created_by_avatar_url,
                   el.name AS element_name
            FROM mw_tasks t
            LEFT JOIN users u ON u.id = t.assigned_to
            LEFT JOIN clients c ON c.user_id = t.assigned_to
            LEFT JOIN employees e ON e.user_id = t.assigned_to
            LEFT JOIN admins a ON a.user_id = t.assigned_to
            LEFT JOIN users u2 ON u2.id = t.created_by
            LEFT JOIN clients c2 ON c2.user_id = t.created_by
            LEFT JOIN employees e2 ON e2.user_id = t.created_by
            LEFT JOIN admins a2 ON a2.user_id = t.created_by
            LEFT JOIN mw_project_elements el ON el.id = t.element_id
            LEFT JOIN LATERAL (
                SELECT h5.id, h5.created_at
                FROM mw_task_history h5
                WHERE h5.task_id = t.id
                  AND h5.event_type = 'activity'
                  AND h5.metadata->>'kind' = 'autopr_additional_context'
                  AND h5.metadata->>'autopr_reconsideration_of' = t.progress_note
                ORDER BY h5.created_at DESC
                LIMIT 1
            ) autopr_ctx ON TRUE
            LEFT JOIN LATERAL (
                -- A run request outlives nothing but its own claim: the
                -- harness posts autopr_run_claim when it actually picks the
                -- card up, which is what stops the request re-firing every
                -- tick. No column, same shape as the reconsideration join.
                SELECT h6.created_at
                FROM mw_task_history h6
                WHERE h6.task_id = t.id
                  AND h6.event_type = 'activity'
                  AND h6.metadata->>'kind' = 'autopr_run_request'
                  -- Same shelf life the dispatcher honours, so the card's
                  -- "Queued for AutoPR" chip can never outlive the request.
                  AND h6.created_at > now() - interval '{_AUTOPR_RUN_REQUEST_TTL}'
                  AND h6.created_at > COALESCE((
                        SELECT MAX(h7.created_at) FROM mw_task_history h7
                        WHERE h7.task_id = t.id
                          AND h7.event_type = 'activity'
                          AND h7.metadata->>'kind' = 'autopr_run_claim'
                      ), '-infinity'::timestamptz)
                ORDER BY h6.created_at DESC
                LIMIT 1
            ) autopr_run ON TRUE
            WHERE t.project_id = $1 AND t.status != 'cancelled'
              {_done_clause}
            ORDER BY
                CASE t.priority
                    WHEN 'critical' THEN 0 WHEN 'high' THEN 1
                    WHEN 'medium' THEN 2 WHEN 'low' THEN 3 ELSE 4
                END,
                t.created_at DESC
            """,
            *params,
        )
    return [_row_to_task(dict(r)) for r in rows]


async def create_project_task(
    *,
    project_id: UUID,
    company_id: UUID,
    created_by: UUID,
    title: str,
    description: Optional[str] = None,
    board_column: str = "todo",
    pipeline_column: str = "lead",
    priority: str = "medium",
    due_date: Optional[_date] = None,
    assigned_to: Optional[UUID] = None,
    progress_note: Optional[str] = None,
    project_title: Optional[str] = None,
    category: str = "manual",
    element_id: Optional[str] = None,
    deal_value: Optional[float] = None,
    probability: Optional[int] = None,
    contact_name: Optional[str] = None,
    contact_company: Optional[str] = None,
    contact_email: Optional[str] = None,
    contact_phone: Optional[str] = None,
    outcome: Optional[str] = None,
    loss_reason: Optional[str] = None,
    next_action_at: Optional[_date] = None,
    expected_close: Optional[_date] = None,
) -> dict:
    if board_column not in _ALLOWED_COLUMNS:
        raise ValueError(f"Invalid board_column: {board_column}")
    if pipeline_column not in _ALLOWED_PIPELINE_COLUMNS:
        raise ValueError(f"Invalid pipeline_column: {pipeline_column}")
    if priority not in _ALLOWED_PRIORITIES:
        raise ValueError(f"Invalid priority: {priority}")
    if category not in _ALLOWED_CATEGORIES:
        raise ValueError(f"Invalid category: {category}")
    if outcome is not None and outcome not in _ALLOWED_OUTCOMES:
        raise ValueError(f"Invalid outcome: {outcome}")
    if not title or not title.strip():
        raise ValueError("Title required")

    status = "completed" if board_column == "done" else "pending"
    completed_at = datetime.now(timezone.utc) if status == "completed" else None

    async with get_connection() as conn:
        row = await conn.fetchrow(
            """
            INSERT INTO mw_tasks (
                company_id, created_by, project_id, title, description,
                due_date, priority, status, board_column, pipeline_column, assigned_to,
                completed_at, category, progress_note, element_id,
                deal_value, probability, contact_name, contact_company,
                contact_email, contact_phone, outcome, loss_reason,
                next_action_at, expected_close
            )
            VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9, $10,
                    $11, $12, $13, $14, $15, $16, $17, $18,
                    $19, $20, $21, $22, $23, $24, $25)
            RETURNING id, project_id, company_id, created_by, title, description,
                      due_date, priority, status, board_column,
                      COALESCE(pipeline_column, 'lead') AS pipeline_column,
                      assigned_to, completed_at, created_at, updated_at,
                      progress_note, category, element_id,
                      deal_value, probability, contact_name, contact_company,
                      contact_email, contact_phone, outcome, loss_reason,
                      next_action_at, expected_close
            """,
            company_id, created_by, project_id, title.strip(), description,
            due_date, priority, status, board_column, pipeline_column, assigned_to,
            completed_at, category, progress_note, element_id,
            deal_value, probability, contact_name, contact_company,
            contact_email, contact_phone, outcome, loss_reason,
            next_action_at, expected_close,
        )

        await _log_task_history(
            conn,
            task_id=row["id"],
            project_id=project_id,
            actor_user_id=created_by,
            event_type="created",
            to_value=board_column,
            metadata={"title": title.strip()},
        )
        if assigned_to is not None:
            await _log_task_history(
                conn,
                task_id=row["id"],
                project_id=project_id,
                actor_user_id=created_by,
                event_type="assignee_change",
                to_value=str(assigned_to),
            )

    if assigned_to is not None and assigned_to != created_by:
        await _notify_task_assigned(
            assigned_to=assigned_to,
            company_id=company_id,
            actor_user_id=created_by,
            project_id=project_id,
            project_title=project_title,
            task_id=row["id"],
            task_title=title.strip(),
        )

    task_payload = _row_to_task(dict(row))
    task_payload["actor_id"] = str(created_by)
    await _broadcast_task_event_safe(project_id, "task.created", task_payload)
    return _row_to_task(dict(row))


async def reject_project_task(
    project_id: UUID,
    task_id: UUID,
    note: str,
    *,
    actor_user_id: Optional[UUID] = None,
    project_title: Optional[str] = None,
) -> Optional[dict]:
    """Reviewer sends a task back: bounce review → changes_requested, store the
    reason in review_note, auto-open the next round (roll unfixed checklist
    items forward, archive accepted ones), log a `review_rejected` history
    event, and email the assignee. Only valid from the `review` column.
    Returns the updated task row (same shape as `update_project_task`) or None
    if not found.
    """
    note = (note or "").strip()
    async with get_connection() as conn:
        current = await conn.fetchrow(
            """
            SELECT board_column, company_id, assigned_to, title
            FROM mw_tasks WHERE id = $1 AND project_id = $2
            """,
            task_id, project_id,
        )
        if not current:
            return None
        if current["board_column"] != "review":
            raise ValueError("Task must be in review to send it back")

        row = await conn.fetchrow(
            """
            UPDATE mw_tasks SET
                board_column = 'changes_requested',
                status = 'pending',
                completed_at = NULL,
                review_note = $3::text,
                updated_at = NOW()
            WHERE id = $1 AND project_id = $2
            RETURNING id, project_id, company_id, created_by, title, description,
                      due_date, priority, status, board_column,
                      COALESCE(pipeline_column, 'lead') AS pipeline_column,
                      assigned_to, completed_at, created_at, updated_at,
                      progress_note, category, element_id, review_note,
                      deal_value, probability, contact_name, contact_company,
                      contact_email, contact_phone, outcome, loss_reason,
                      next_action_at, expected_close
            """,
            task_id, project_id, note,
        )
        cycle_count = 0
        if row:
            # Auto-open the next round so the rework cycle reads as
            # foreground/background: log the round boundary FIRST, roll every
            # UNFIXED (uncompleted) checklist item into the new round (the live
            # foreground checklist), and leave items the reviewer accepted
            # stamped on the prior round so they archive into the background.
            # The reviewer's "re-open these items" taps already flipped the
            # rejected pieces to not-done, so they roll forward here as the new
            # round's work.
            from . import project_subtask_service as st_svc
            round_title = note[:80] if note else "Reviewer requested changes"
            # Shared with the explicit POST .../rounds endpoint. Runs inside
            # this transaction — start_new_round opens none of its own.
            await st_svc.start_new_round(
                conn,
                task_id=task_id,
                project_id=project_id,
                actor_user_id=actor_user_id,
                title=round_title,
            )
            # The bounce event lands AFTER round_started so it falls inside the
            # new round on the history feed ("Round N · sent back · <note>").
            await _log_task_history(
                conn,
                task_id=task_id,
                project_id=project_id,
                actor_user_id=actor_user_id,
                event_type="review_rejected",
                from_value="review",
                to_value="changes_requested",
                metadata={"note": note[:500]},
            )
            # Count includes the bounce we just logged, so the card's churn chip
            # reflects the new total immediately (optimistic update + broadcast)
            # without waiting for the next full board reload.
            cycle_count = await conn.fetchval(
                """SELECT COUNT(*) FROM mw_task_history
                   WHERE task_id = $1 AND event_type = 'review_rejected'""",
                task_id,
            )

    if not row:
        return None

    # Email + bell the assignee only (skip if unassigned — banner + history
    # still record the bounce-back).
    if current["assigned_to"] is not None:
        await _notify_task_rejected(
            assigned_to=current["assigned_to"],
            company_id=current["company_id"],
            actor_user_id=actor_user_id,
            project_id=project_id,
            project_title=project_title,
            task_id=task_id,
            task_title=row["title"],
            note=note,
        )

    result = _row_to_task(dict(row))
    result["last_moved_at"] = datetime.now(timezone.utc).isoformat()
    result["review_cycle_count"] = cycle_count
    task_payload = dict(result)
    if actor_user_id is not None:
        task_payload["actor_id"] = str(actor_user_id)
    await _broadcast_task_event_safe(project_id, "task.updated", task_payload)
    return result


async def approve_project_task(
    project_id: UUID,
    task_id: UUID,
    *,
    note: Optional[str] = None,
    actor_user_id: Optional[UUID] = None,
) -> Optional[dict]:
    """Reviewer approves a task out of review → done, with a sign-off audit row
    (`review_approved`, carrying the approver via actor + an optional note). The
    symmetric counterpart to `reject_project_task`. Only valid from `review`.
    Returns the updated task row, or None if not found.
    """
    note = (note or "").strip()
    async with get_connection() as conn:
        current = await conn.fetchrow(
            "SELECT board_column FROM mw_tasks WHERE id = $1 AND project_id = $2",
            task_id, project_id,
        )
        if not current:
            return None
        if current["board_column"] != "review":
            raise ValueError("Task must be in review to approve it")

        row = await conn.fetchrow(
            """
            UPDATE mw_tasks SET
                board_column = 'done',
                status = 'completed',
                completed_at = NOW(),
                review_note = NULL,
                updated_at = NOW()
            WHERE id = $1 AND project_id = $2
            RETURNING id, project_id, company_id, created_by, title, description,
                      due_date, priority, status, board_column,
                      COALESCE(pipeline_column, 'lead') AS pipeline_column,
                      assigned_to, completed_at, created_at, updated_at,
                      progress_note, category, element_id, review_note,
                      deal_value, probability, contact_name, contact_company,
                      contact_email, contact_phone, outcome, loss_reason,
                      next_action_at, expected_close
            """,
            task_id, project_id,
        )
        if not row:
            return None
        # Sign-off: who approved (actor) + when (now) + optional note. Metadata is
        # string-only (desktop decodes as [String: String]).
        await _log_task_history(
            conn,
            task_id=task_id,
            project_id=project_id,
            actor_user_id=actor_user_id,
            event_type="review_approved",
            from_value="review",
            to_value="done",
            metadata={"note": note[:500]} if note else {},
        )

    result = _row_to_task(dict(row))
    result["last_moved_at"] = datetime.now(timezone.utc).isoformat()
    task_payload = dict(result)
    if actor_user_id is not None:
        task_payload["actor_id"] = str(actor_user_id)
    await _broadcast_task_event_safe(project_id, "task.updated", task_payload)
    return result


async def update_project_task(
    project_id: UUID,
    task_id: UUID,
    patch: dict,
    *,
    actor_user_id: Optional[UUID] = None,
    project_title: Optional[str] = None,
) -> Optional[dict]:
    """Partial update. Enforces status↔board_column sync rules."""
    async with get_connection() as conn:
        current = await conn.fetchrow(
            """
            SELECT board_column, status, assigned_to, company_id,
                   description, progress_note
            FROM mw_tasks WHERE id = $1 AND project_id = $2
            """,
            task_id, project_id,
        )
        if not current:
            return None

        # Resolve target column + status with sync rules
        new_column = patch.get("board_column", current["board_column"])
        new_status = patch.get("status", current["status"])

        if "board_column" in patch:
            if new_column not in _ALLOWED_COLUMNS:
                raise ValueError(f"Invalid board_column: {new_column}")
            if new_column == "done":
                new_status = "completed"
            elif current["board_column"] == "done":
                new_status = "pending"

        if "status" in patch:
            if new_status not in ("pending", "completed", "cancelled"):
                raise ValueError(f"Invalid status: {new_status}")
            if new_status == "completed" and new_column != "done":
                new_column = "done"
            elif new_status == "pending" and new_column == "done":
                new_column = "todo"

        # Collect simple field updates
        title = patch.get("title")
        description = patch.get("description")
        priority = patch.get("priority")
        due_date = patch.get("due_date")
        assigned_to = patch.get("assigned_to")
        progress_note = patch.get("progress_note")
        element_id = patch.get("element_id")
        deal_value = patch.get("deal_value")
        probability = patch.get("probability")
        contact_name = patch.get("contact_name")
        contact_company = patch.get("contact_company")
        contact_email = patch.get("contact_email")
        contact_phone = patch.get("contact_phone")
        outcome = patch.get("outcome")
        loss_reason = patch.get("loss_reason")
        next_action_at = patch.get("next_action_at")
        expected_close = patch.get("expected_close")
        pipeline_column = patch.get("pipeline_column")
        pr_url = patch.get("pr_url")
        pr_number = patch.get("pr_number")

        if priority is not None and priority not in _ALLOWED_PRIORITIES:
            raise ValueError(f"Invalid priority: {priority}")
        if outcome is not None and outcome not in _ALLOWED_OUTCOMES:
            raise ValueError(f"Invalid outcome: {outcome}")
        if pipeline_column is not None and pipeline_column not in _ALLOWED_PIPELINE_COLUMNS:
            raise ValueError(f"Invalid pipeline_column: {pipeline_column}")

        has_pr_update = "pr_url" in patch or "pr_number" in patch
        if has_pr_update:
            pr_columns_exist = await conn.fetchval(
                """
                SELECT COUNT(*) = 2
                FROM information_schema.columns
                WHERE table_schema = 'public'
                  AND table_name = 'mw_tasks'
                  AND column_name = ANY($1::text[])
                """,
                ["pr_url", "pr_number"],
            )
            if not pr_columns_exist:
                raise ValueError("Pull request links are unavailable until the database is updated")

        # Compute completed_at in Python rather than via a SQL CASE on $3.
        # asyncpg infers each $N's type from how it's used. $3 is assigned to
        # `status` (varchar column) AND compared to text inside the CASE; the
        # previous attempt cast only the CASE site (`$3::text = 'completed'`)
        # but PG saw two contexts demanding different types for the same
        # parameter and raised
        #   AmbiguousParameterError: inconsistent types deduced for $3
        #   DETAIL: text versus character varying
        # Fix: cast at every use of $3 (and $1) so all references are
        # unambiguously text. PG assignment-casts text -> varchar implicitly.
        completed_at_value = (
            datetime.now(timezone.utc) if new_status == "completed" else None
        )

        pr_update = ""
        params = [
            new_column,                   # $1
            task_id,                      # $2
            new_status,                   # $3
            title,                        # $4
            "description" in patch,       # $5
            description,                  # $6
            priority,                     # $7
            "due_date" in patch,          # $8
            due_date,                     # $9
            "assigned_to" in patch,       # $10
            assigned_to,                  # $11
            project_id,                   # $12
            completed_at_value,           # $13
            "progress_note" in patch,     # $14
            progress_note,                # $15
            "element_id" in patch,        # $16
            element_id,                   # $17
            "deal_value" in patch,        # $18
            deal_value,                   # $19
            "probability" in patch,       # $20
            probability,                  # $21
            "contact_name" in patch,      # $22
            contact_name,                 # $23
            "contact_company" in patch,   # $24
            contact_company,              # $25
            "contact_email" in patch,     # $26
            contact_email,                # $27
            "contact_phone" in patch,     # $28
            contact_phone,                # $29
            "outcome" in patch,           # $30
            outcome,                      # $31
            "loss_reason" in patch,       # $32
            loss_reason,                  # $33
            "next_action_at" in patch,    # $34
            next_action_at,               # $35
            "expected_close" in patch,    # $36
            expected_close,               # $37
            "pipeline_column" in patch,   # $38
            pipeline_column,              # $39
        ]
        if has_pr_update:
            pr_update = """
                pr_url = CASE WHEN $40::boolean THEN $41::text ELSE pr_url END,
                pr_number = CASE WHEN $42::boolean THEN $43::integer ELSE pr_number END,
            """
            params.extend([
                "pr_url" in patch,        # $40
                pr_url,                    # $41
                "pr_number" in patch,     # $42
                pr_number,                 # $43
            ])

        row = await conn.fetchrow(
            f"""
            UPDATE mw_tasks SET
                board_column = $1::text,
                status = $3::text,
                completed_at = CASE
                    WHEN $3::text = 'completed' THEN COALESCE(completed_at, $13::timestamptz)
                    ELSE NULL
                END,
                title = COALESCE($4::text, title),
                description = CASE WHEN $5::boolean THEN $6::text ELSE description END,
                priority = COALESCE($7::text, priority),
                due_date = CASE WHEN $8::boolean THEN $9::date ELSE due_date END,
                assigned_to = CASE WHEN $10::boolean THEN $11::uuid ELSE assigned_to END,
                progress_note = CASE WHEN $14::boolean THEN $15::text ELSE progress_note END,
                element_id = CASE WHEN $16::boolean THEN $17::text ELSE element_id END,
                deal_value = CASE WHEN $18::boolean THEN $19::numeric ELSE deal_value END,
                probability = CASE WHEN $20::boolean THEN $21::smallint ELSE probability END,
                contact_name = CASE WHEN $22::boolean THEN $23::text ELSE contact_name END,
                contact_company = CASE WHEN $24::boolean THEN $25::text ELSE contact_company END,
                contact_email = CASE WHEN $26::boolean THEN $27::text ELSE contact_email END,
                contact_phone = CASE WHEN $28::boolean THEN $29::text ELSE contact_phone END,
                outcome = CASE WHEN $30::boolean THEN $31::text ELSE outcome END,
                loss_reason = CASE WHEN $32::boolean THEN $33::text ELSE loss_reason END,
                next_action_at = CASE WHEN $34::boolean THEN $35::date ELSE next_action_at END,
                expected_close = CASE WHEN $36::boolean THEN $37::date ELSE expected_close END,
                pipeline_column = CASE WHEN $38::boolean THEN $39::text ELSE COALESCE(pipeline_column, 'lead') END,
                {pr_update}
                -- Clear the reviewer's "needs work" note once the task is
                -- re-submitted to review or marked done — the bounce-back
                -- banner only applies while it sits back in todo/in_progress.
                review_note = CASE WHEN $1::text IN ('review', 'done') THEN NULL ELSE review_note END,
                updated_at = NOW()
            WHERE id = $2 AND project_id = $12
            RETURNING id, project_id, company_id, created_by, title, description,
                      due_date, priority, status, board_column,
                      COALESCE(pipeline_column, 'lead') AS pipeline_column,
                      assigned_to, completed_at, created_at, updated_at,
                       progress_note, category, element_id, review_note,
                       deal_value, probability, contact_name, contact_company,
                       contact_email, contact_phone, outcome, loss_reason,
                       next_action_at, expected_close,
                       to_jsonb(mw_tasks) ->> 'pr_url' AS pr_url,
                       (to_jsonb(mw_tasks) ->> 'pr_number')::integer AS pr_number
            """,
            *params,
        )

        if row and new_column != current["board_column"]:
            await _log_task_history(
                conn,
                task_id=task_id,
                project_id=project_id,
                actor_user_id=actor_user_id,
                event_type="column_change",
                from_value=current["board_column"],
                to_value=new_column,
            )
        if row and "assigned_to" in patch and patch.get("assigned_to") != current["assigned_to"]:
            await _log_task_history(
                conn,
                task_id=task_id,
                project_id=project_id,
                actor_user_id=actor_user_id,
                event_type="assignee_change",
                from_value=str(current["assigned_to"]) if current["assigned_to"] else None,
                to_value=str(patch["assigned_to"]) if patch.get("assigned_to") else None,
            )
        # Surface description / "where we're at" edits in the task viewer
        # timeline so collaborators see when someone added new info.
        # Short previews land in metadata; the full text is already on
        # the task row itself so a follow-up read can pull it.
        if row and "description" in patch and (description or "") != (current["description"] or ""):
            await _log_task_history(
                conn,
                task_id=task_id,
                project_id=project_id,
                actor_user_id=actor_user_id,
                event_type="description_change",
                metadata={
                    "from_preview": (current["description"] or "")[:120],
                    "to_preview": (description or "")[:120],
                },
            )
        if row and "progress_note" in patch and (progress_note or "") != (current["progress_note"] or ""):
            await _log_task_history(
                conn,
                task_id=task_id,
                project_id=project_id,
                actor_user_id=actor_user_id,
                event_type="progress_note_change",
                metadata={
                    "from_preview": (current["progress_note"] or "")[:120],
                    "to_preview": (progress_note or "")[:120],
                },
            )

    if row and "assigned_to" in patch:
        new_assignee = row["assigned_to"]
        old_assignee = current["assigned_to"]
        if (
            new_assignee is not None
            and new_assignee != old_assignee
            and new_assignee != actor_user_id
        ):
            await _notify_task_assigned(
                assigned_to=new_assignee,
                company_id=current["company_id"],
                actor_user_id=actor_user_id or new_assignee,
                project_id=project_id,
                project_title=project_title,
                task_id=task_id,
                task_title=row["title"],
            )

    # Resuming rework (changes_requested → in_progress) is a continuation, not a
    # fresh start — skip the "Task started" blast. Re-submitting to review/done
    # still notifies.
    _is_rework_resume = (
        current["board_column"] == "changes_requested" and new_column == "in_progress"
    )
    if row and new_column != current["board_column"] and not _is_rework_resume:
        await _notify_task_column_transition(
            project_id=project_id,
            company_id=current["company_id"],
            actor_user_id=actor_user_id,
            task_id=task_id,
            task_title=row["title"],
            new_column=new_column,
            project_title=project_title,
        )
        # Echo the move into the project's discussion channel as a plain chat
        # bubble ("<verb> \"<title>\"" from the mover). Same guard as the
        # notification so chat + banner always agree on which moves are worth
        # announcing.
        _move_actor_name, _move_actor_avatar = await _lookup_actor_identity(actor_user_id)
        await _post_kanban_move_to_chat(
            project_id=project_id,
            task_id=task_id,
            task_title=row["title"],
            new_column=new_column,
            actor_user_id=actor_user_id,
            actor_name=_move_actor_name,
            actor_avatar_url=_move_actor_avatar,
        )

    result = _row_to_task(dict(row)) if row else None
    # Stamp the fresh move time so the card's "Moved …" line updates without
    # waiting for the next list reload (the list query derives last_moved_at
    # from mw_task_history; here we approximate it with now()).
    if result is not None and new_column != current["board_column"]:
        result["last_moved_at"] = datetime.now(timezone.utc).isoformat()

    if result is not None:
        task_payload = dict(result)
        if actor_user_id is not None:
            task_payload["actor_id"] = str(actor_user_id)
        await _broadcast_task_event_safe(project_id, "task.updated", task_payload)

    return result


async def delete_project_task(
    project_id: UUID, task_id: UUID, *, actor_user_id: Optional[UUID] = None
) -> bool:
    async with get_connection() as conn:
        existing = await conn.fetchrow(
            "SELECT title FROM mw_tasks WHERE id = $1 AND project_id = $2",
            task_id, project_id,
        )
        if existing:
            # Log BEFORE the delete so the FK still resolves. ON DELETE
            # SET NULL on task_id then nulls the reference when the task
            # row is gone — leaving the history row in place with the
            # title cached in metadata so the activity feed can still
            # render "X deleted Task Y".
            await _log_task_history(
                conn,
                task_id=task_id,
                project_id=project_id,
                actor_user_id=actor_user_id,
                event_type="deleted",
                metadata={"title": existing["title"]},
            )
        result = await conn.execute(
            "DELETE FROM mw_tasks WHERE id = $1 AND project_id = $2",
            task_id, project_id,
        )
        deleted = result.endswith(" 1")
    if deleted:
        payload: dict = {"id": str(task_id)}
        if actor_user_id is not None:
            payload["actor_id"] = str(actor_user_id)
        await _broadcast_task_event_safe(project_id, "task.deleted", payload)
    return deleted


async def mark_project_complete(project_id: UUID) -> dict:
    async with get_connection() as conn:
        row = await conn.fetchrow(
            """
            UPDATE mw_projects SET status = 'completed', updated_at = NOW()
            WHERE id = $1
            RETURNING id, status, updated_at
            """,
            project_id,
        )
    if not row:
        raise ValueError("Project not found")
    d = dict(row)
    d["id"] = str(d["id"])
    if d.get("updated_at") is not None:
        d["updated_at"] = d["updated_at"].isoformat()
    return d
