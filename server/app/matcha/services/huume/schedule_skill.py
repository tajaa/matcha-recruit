"""Thread Huume's schedule capability — a read tool (`find_shift_coverage`)
plus one staged write (`propose_schedule_change`, action_type
`schedule_change`). Reuses `services/scheduling/schedule_chat.py`'s
resolution/dry-run/execute machinery wholesale rather than reimplementing
shift lookup a third time (channel regex fork, channel ASK-loop tool, and
now here) — `schedule_chat_proposals` becomes shared scratch storage
between two different "who confirms it" mechanisms: a channel's
reply-to-pill claim (`confirm_message_id`), and here Huume's own
stage/confirm two-turn loop (`evaluate_huume_action`). This module never
touches `confirm_message_id` — the thread's own turn-boundary IS the
confirmation.

`propose` runs on the STAGE turn, called from `agent.py` BEFORE
`evaluate_huume_action` (mirrors `inventory_skill.parse_attachment_for_
staging`'s special-case shape exactly): it resolves the model's args into
a real `schedule_chat_proposals` row via `build_proposal`/
`build_edit_proposal` and merges the resulting `proposal_id`/`pill_text`
into the staged dict. `execute` runs on the CONFIRM turn, dispatched from
`actions.execute_huume_action`: it re-fetches that row and calls the
matching `schedule_chat` executor.

A `build_*` call that comes back `kind='clarify'` (ambiguous shift, unknown
employee, ...) has no home here — threads have no per-pill clarify-answer
round trip the way channels do — so it's surfaced as a terminal clarification
asking the admin to be more specific, not staged. That's a deliberate v1
scope cut, not an oversight."""

from datetime import date as _date
from typing import Any, Literal, NotRequired, Optional, TypedDict
from uuid import UUID

_ALLOWED_ROLES = frozenset({"client", "admin"})
_MAX_SCHEDULE_EDIT_OPS = 4
_MAX_BULK_VACANT_SHIFTS = 500


class ScheduleProposalResult(TypedDict):
    status: Literal["ready", "clarify", "refused"]
    message: NotRequired[str]
    proposal_id: NotRequired[str]
    pill_text: NotRequired[str]
    operation_count: NotRequired[int]


def _coerce_tool_shift_request(args: dict[str, Any]) -> dict[str, Any]:
    return {
        "label": args.get("label") or args.get("role") or "shift",
        # target_date fallback: the tool schema's edit-kind field is the one
        # name the model reaches for reflexively even on kind='create' — accept
        # either rather than making "which days?" the answer to a date it did
        # provide, just under the wrong key.
        "template_hint": None, "date": args.get("date") or args.get("target_date"),
        "weekdays": [], "start_time": args.get("start_time"), "end_time": args.get("end_time"),
        "role": args.get("role"), "count": args.get("count") or 1,
        "employee_name_hints": [n for n in (args.get("employee_names") or []) if n],
    }


def _tool_args_to_edit_request(kind: str, args: dict[str, Any]) -> dict[str, Any]:
    return {
        "kind": kind,
        "target_shift_id": args.get("target_shift_id"),
        "target_employee_name": args.get("target_employee_name"),
        "target_date": args.get("target_date"),
        "target_time_hint": args.get("target_time_hint"),
        "target_staffing_hint": args.get("target_staffing_hint"),
        "target_role_hint": args.get("target_role_hint"),
        "to_employee_name": args.get("to_employee_name"),
        "second_employee_name": args.get("second_employee_name"),
        "second_date": args.get("second_date"),
        "second_time_hint": args.get("second_time_hint"),
        "second_role_hint": args.get("second_role_hint"),
        "new_date": args.get("new_date"),
        "new_start_time": args.get("new_start_time"),
        "new_end_time": args.get("new_end_time"),
        "shift_by_minutes": args.get("shift_by_minutes"),
    }


def _coerce_tool_edit_requests(schedule_chat, args: dict[str, Any]) -> tuple[list[dict[str, Any]], Optional[str]]:
    """Normalize either one legacy flat edit or a bounded `changes` batch.

    The schedule engine already executes ``parsed['edit_requests']`` as one
    transactional proposal. This is the Huume-only adapter that used to
    collapse the tool call to one request. A named-person swap expands to two
    reassignments and therefore consumes two of the four concrete-op slots.
    The whole batch is rejected if any item is unusable; silently staging a
    partial write would make the confirmation pill differ from the ask.
    """
    raw_changes = args.get("changes")
    # Structured-output providers materialize optional array fields as [] even
    # when the model used the legacy flat fields. Treat only a non-empty array
    # as a batch so a valid flat edit is not discarded by that schema default.
    # An empty array with no usable flat edit still fails through the normal
    # single-edit validation below.
    is_batch = isinstance(raw_changes, list) and bool(raw_changes)
    if raw_changes is not None and not isinstance(raw_changes, list):
        return [], "Give me schedule changes as a list."
    if is_batch:
        if len(raw_changes) > _MAX_SCHEDULE_EDIT_OPS:
            return [], (
                f"I can stage up to {_MAX_SCHEDULE_EDIT_OPS} schedule edits in one confirmation. "
                "Split the remaining edits into a later request."
            )
        if str(args.get("kind") or "").strip().lower() == "create":
            return [], "New shifts and edits need separate schedule proposals."
        changes = raw_changes
    else:
        changes = [args]

    edit_requests: list[dict[str, Any]] = []
    for index, change in enumerate(changes, start=1):
        if not isinstance(change, dict):
            return [], f"Schedule change {index} is not a usable edit."
        kind = str(change.get("kind") or "").strip().lower()
        if kind == "create":
            return [], "New shifts and edits need separate schedule proposals."

        # `schedule_chat` reserves kind='swap' for a roster-level swap: every
        # assignee on one shift moves to the other. On this surface, a request
        # naming two people means exchange only those assignment rows.
        if kind == "swap" and change.get("target_employee_name") and change.get("second_employee_name"):
            first = schedule_chat.coerce_edit_request({
                "kind": "reassign",
                "target_employee_name": change.get("target_employee_name"),
                "to_employee_name": change.get("second_employee_name"),
                "target_date": change.get("target_date"),
                "target_time_hint": change.get("target_time_hint"),
                "target_staffing_hint": change.get("target_staffing_hint"),
                "target_role_hint": change.get("target_role_hint"),
            })
            second = schedule_chat.coerce_edit_request({
                "kind": "reassign",
                "target_employee_name": change.get("second_employee_name"),
                "to_employee_name": change.get("target_employee_name"),
                "target_date": change.get("second_date") or change.get("target_date"),
                "target_time_hint": change.get("second_time_hint"),
                "target_role_hint": change.get("second_role_hint"),
            })
            normalized = [request for request in (first, second) if request is not None]
        else:
            request = schedule_chat.coerce_edit_request(_tool_args_to_edit_request(kind, change))
            normalized = [request] if request is not None else []

        if not normalized:
            prefix = f"Schedule change {index} " if is_batch else "That schedule change "
            return [], prefix + "needs an employee and a specific shift before I can stage it."
        if len(edit_requests) + len(normalized) > _MAX_SCHEDULE_EDIT_OPS:
            return [], (
                f"I can stage up to {_MAX_SCHEDULE_EDIT_OPS} concrete schedule edits in one confirmation. "
                "A named-person swap counts as two edits."
            )
        edit_requests.extend(normalized)

    return edit_requests, None


async def _all_vacant_shift_requests(
    conn, *, company_id: UUID, location_id: Optional[UUID],
    week_start: Optional[_date], week_end: Optional[_date],
    employee_name: Optional[str], schedule_chat,
) -> tuple[list[dict[str, Any]], Optional[str]]:
    """Resolve an explicit all-vacant request inside the editor scope."""
    if location_id is None or week_start is None:
        return [], "Bulk vacant-shift assignment requires a scoped schedule workspace."
    employee_hint = str(employee_name or "").strip()
    if not employee_hint:
        return [], "Who should I assign to every vacant shift?"

    matched = await schedule_chat._match_single_employee(
        conn, company_id, employee_hint, location_id,
    )
    if "none" in matched:
        return [], matched["none"]
    if "ambiguous" in matched:
        return [], f"Which {employee_hint} did you mean? " + ", ".join(matched["ambiguous"])
    employee = matched["employee"]
    employee_id = employee["id"]
    employee_full_name = f"{employee['first_name']} {employee['last_name']}".strip()
    inclusive_end = week_end or (week_start + _date.resolution * 6)
    rows = await conn.fetch(
        """
        SELECT s.id
        FROM schedule_shifts s
        WHERE s.company_id=$1 AND s.location_id=$2
          AND s.status = ANY($3::text[])
          AND s.starts_at::date >= $4 AND s.starts_at::date <= $5
          AND (SELECT COUNT(*) FROM schedule_shift_assignments a WHERE a.shift_id=s.id)
              < COALESCE(s.required_staff, 1)
          AND NOT EXISTS (
              SELECT 1 FROM schedule_shift_assignments a
              WHERE a.shift_id=s.id AND a.employee_id=$6
          )
        ORDER BY s.starts_at, s.id
        LIMIT $7
        """,
        company_id, location_id, ["draft", "published"], week_start,
        inclusive_end, employee_id, _MAX_BULK_VACANT_SHIFTS + 1,
    )
    if len(rows) > _MAX_BULK_VACANT_SHIFTS:
        return [], (
            f"This week has more than {_MAX_BULK_VACANT_SHIFTS} vacant shifts. "
            "Narrow the request by day or role."
        )
    if not rows:
        return [], f"There are no vacant shifts in this editor week for {employee_full_name} to pick up."
    return [
        {
            "kind": "assign", "target_shift_id": str(row["id"]),
            "to_employee_name": employee_full_name,
        }
        for row in rows
    ], None


async def find_coverage(
    *, company_id: UUID, role: Optional[str], features: dict[str, Any],
    date_str: str, role_hint: Optional[str], location_id: Optional[UUID] = None,
    schedule_surface: bool = False,
) -> dict[str, Any]:
    """Read-only — same envelope shape as every other read tool: role +
    `employee_schedule` re-checked per call, never trusted from an earlier
    turn."""
    from app.database import get_connection
    from app.matcha.services.scheduling.coverage import find_coverage_candidates

    if role not in _ALLOWED_ROLES and not schedule_surface:
        return {"error": "Only a business admin can ask for coverage suggestions."}
    if not features.get("employee_schedule"):
        return {"error": "Scheduling isn't enabled for this company."}
    if schedule_surface and not location_id:
        return {"error": "This tool requires a scoped schedule workspace."}
    try:
        target = _date.fromisoformat((date_str or "").strip())
    except ValueError:
        return {"error": "I need a date like 2026-08-05 for that."}
    async with get_connection() as conn:
        result = await find_coverage_candidates(
            conn, company_id=company_id, target_date=target, location_id=location_id,
            role_hint=(role_hint or "").strip() or None, features=features,
        )
    return result


async def propose(
    conn, *, company_id: UUID, actor_user_id: UUID, args: dict[str, Any],
    location_id: Optional[UUID] = None, week_start: Optional[_date] = None,
    week_end: Optional[_date] = None,
) -> ScheduleProposalResult:
    """Resolve a STAGE-turn request without executing it.

    ``clarify`` and ``refused`` are terminal for the current Huume turn. A
    thread has no channel pill-reply round trip, so the caller must relay the
    message and wait for the admin's next turn rather than asking Gemini to
    retry the same deterministic resolution.
    """
    from app.matcha.services.scheduling import schedule_chat

    if location_id and not (args.get("location_name") or "").strip():
        location_name = await conn.fetchval(
            "SELECT name FROM business_locations WHERE id=$1 AND company_id=$2 AND is_active IS NOT FALSE",
            location_id, company_id,
        )
        if location_name:
            args = {**args, "location_name": location_name}

    kind = str(args.get("kind") or "").strip().lower()
    today = _date.today()
    # The schedule assistant is embedded in the draft-capable editor. Its
    # overview intentionally includes both draft and published shifts, so
    # proposal resolution must use that same visibility or an open draft shift
    # the manager can see cannot be assigned through Huume. Channel Huume
    # keeps the conservative published-only lookup.
    is_editor_surface = location_id is not None
    surface = "editor" if is_editor_surface else "channel"
    try:
        if kind == "create" and args.get("changes") in (None, []):
            parsed = {
                "ack": "Got it.", "action": "create",
                "location_hint": args.get("location_name"),
                "shift_requests": [_coerce_tool_shift_request(args)],
                "edit_requests": [],
            }
            build = await schedule_chat.build_proposal(
                conn, company_id=company_id, channel_id=None, source_message_id=None,
                created_by=actor_user_id, parsed=parsed, today=today,
                original_content="[huume thread] shift create", week_start=week_start,
                week_end=week_end, surface=surface,
            )
            operation_count = 1
        else:
            if args.get("all_vacant_shifts") is True:
                edit_requests, error = await _all_vacant_shift_requests(
                    conn, company_id=company_id, location_id=location_id,
                    week_start=week_start, week_end=week_end,
                    employee_name=args.get("to_employee_name"),
                    schedule_chat=schedule_chat,
                )
            else:
                edit_requests, error = _coerce_tool_edit_requests(schedule_chat, args)
            if error:
                return {"status": "clarify", "message": error}
            if not edit_requests:
                return {
                    "status": "clarify",
                    "message": "I need the employee and the specific shift before I can make that change. "
                               "Reply with the shift date and time, or the employee currently assigned.",
                }
            parsed = {"ack": "Got it.", "action": "edit", "shift_requests": [], "edit_requests": edit_requests}
            build = await schedule_chat.build_edit_proposal(
                conn, company_id=company_id, channel_id=None, source_message_id=None,
                created_by=actor_user_id, parsed=parsed, today=today,
                original_content=f"[huume thread] {kind} request",
                surface=surface,
                shift_statuses=("draft", "published") if is_editor_surface else ("published",),
                editor_location_id=location_id,
                editor_week_start=week_start, editor_week_end=week_end,
            )
            operation_count = len(edit_requests)
    except Exception:
        return {"status": "refused", "message": "That failed just now — try the Schedule page instead."}

    if build.kind == "clarify":
        # No threaded clarify round-trip (v1 scope cut) — ask the admin to
        # restate with the missing detail instead of staging a proposal
        # that can never be confirmed. Keep the full pill_text (question +
        # numbered candidates), not just its first line — the model needs
        # the options to relay them, not just the fact that some exist.
        # clarify_text() ends with "Just reply to this message." — that's
        # channel UX (reply to the pill). A thread has no pill to reply to,
        # and the very next sentence tells the model to call the tool again
        # instead — leaving both in was a direct contradiction.
        text = build.pill_text.removeprefix("\U0001F4C5 ").strip()
        text = text.removesuffix("Just reply to this message.").strip()
        return {"status": "clarify", "message": (
            f"{text}\nReply with the shift time, employee, or whether you mean the "
            "staffed or unstaffed shift."
        )}
    return {
        "status": "ready",
        "proposal_id": str(build.proposal_id),
        "pill_text": build.pill_text,
        "operation_count": operation_count,
    }


async def execute(
    *, company_id: UUID, actor_user_id: UUID, action: dict[str, Any],
    week_start: Optional[_date] = None, week_end: Optional[_date] = None,
) -> dict[str, Any]:
    """CONFIRM-turn executor, dispatched from `actions.execute_huume_action`.
    `action['proposal_id']` was minted by `propose` above on the stage turn
    and rides the staged dict verbatim across the turn boundary."""
    import json as _json

    from app.core.feature_flags import get_company_features
    from app.database import get_connection
    from app.matcha.services.scheduling import schedule_chat

    proposal_id = action.get("proposal_id")
    if not proposal_id:
        return {"status": "error", "message": "Nothing was actually staged — try again."}

    async with get_connection() as conn:
        row = await conn.fetchrow(
            "SELECT id, company_id, channel_id, proposal, status FROM schedule_chat_proposals "
            "WHERE id = $1 AND company_id = $2",
            UUID(proposal_id), company_id,
        )
        if row is None or row["status"] != "proposed":
            return {"status": "error", "message": "That proposal isn't available anymore — try again."}
        proposal = row["proposal"]
        if isinstance(proposal, str):
            proposal = _json.loads(proposal)
        features = await get_company_features(company_id, conn=conn)
        executor = (
            schedule_chat.execute_edit_proposal if proposal.get("kind") == "edit"
            else schedule_chat.execute_proposal
        )
        try:
            text = await executor(
                conn, proposal_row={**dict(row), "proposal": proposal},
                confirmed_by=actor_user_id, features=features,
                week_start=week_start, week_end=week_end,
            )
        except schedule_chat.ProposalExecutionClaimError as exc:
            return {"status": "error", "message": str(exc)}
    return {"status": "created", "message": text, "record_id": proposal_id, "bg_tasks": []}
