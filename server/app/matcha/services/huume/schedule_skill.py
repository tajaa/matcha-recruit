"""Thread Huume's schedule capability — a read tool (`find_shift_coverage`)
plus one staged write (`propose_schedule_change`, action_type
`schedule_change`). One staged action can hold a whole correction: the
`changes` array takes cancellations, edits AND `kind='create'` replacement
shifts together (bounded by `schedule_batch.MAX_BATCH_OPERATIONS`), which
`schedule_chat.build_batch_proposal` resolves into ONE `kind='batch'` row
that ONE confirmation applies in ONE transaction — the "four edits per
confirmation, one staged action at a time" serial-confirm loop a seven-day
correction used to fall into is gone. Over the cap, `_coerce_tool_batch`
answers with a server-computed day-contiguous split plan, never a silently
truncated prefix. Reuses `services/scheduling/schedule_chat.py`'s
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

import logging
from datetime import date as _date
from typing import Any, Literal, NotRequired, Optional, TypedDict
from uuid import UUID

from app.matcha.services.scheduling.schedule_batch import (
    MAX_BATCH_OPERATIONS, BatchItem, item_day, plan_batches, split_plan_message,
    summarize_operations,
)

logger = logging.getLogger(__name__)

_ALLOWED_ROLES = frozenset({"client", "admin"})
_MAX_BULK_VACANT_SHIFTS = 500


class ScheduleProposalResult(TypedDict):
    status: Literal["ready", "clarify", "refused"]
    message: NotRequired[str]
    proposal_id: NotRequired[str]
    pill_text: NotRequired[str]
    operation_count: NotRequired[int]
    operation_summary: NotRequired[dict[str, int]]
    # The `ScheduleReview` (services/scheduling/schedule_review.py) for what
    # was staged — the model relays `rejected`/warnings/compliance from it on
    # the SAME turn; the state block re-renders a summary on later turns.
    review: NotRequired[dict[str, Any]]
    rejected_count: NotRequired[int]
    compliance_status: NotRequired[str]


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


def _is_named_people_swap(change: dict[str, Any]) -> bool:
    return (
        str(change.get("kind") or "").strip().lower() == "swap"
        and bool(change.get("target_employee_name"))
        and bool(change.get("second_employee_name"))
    )


def _coerce_tool_batch(
    schedule_chat, args: dict[str, Any],
) -> tuple[list[dict[str, Any]], list[dict[str, Any]], Optional[str]]:
    """Normalize one legacy flat edit or a bounded `changes` batch into
    ``(edit_requests, shift_requests, error)``.

    The schedule engine executes ``edit_requests`` as one transactional
    proposal and, since the batch row exists, ``shift_requests`` right after
    them in the same transaction — so a correction's cancellations and its
    replacement `kind='create'` items ride one confirmation. A named-person
    swap expands to two reassignments and weighs two operations. The cap is
    checked BEFORE anything resolves: an over-cap request gets the smallest
    day-contiguous split plan back, never a silently staged prefix (the pill
    would then differ from the ask). The whole batch is rejected if any item
    is unusable, for the same reason.
    """
    raw_changes = args.get("changes")
    # Structured-output providers materialize optional array fields as [] even
    # when the model used the legacy flat fields. Treat only a non-empty array
    # as a batch so a valid flat edit is not discarded by that schema default.
    # An empty array with no usable flat edit still fails through the normal
    # single-edit validation below.
    is_batch = isinstance(raw_changes, list) and bool(raw_changes)
    if raw_changes is not None and not isinstance(raw_changes, list):
        return [], [], "Give me schedule changes as a list."
    if is_batch:
        if str(args.get("kind") or "").strip().lower() == "create":
            return [], [], (
                "Put the new shift inside `changes` as a `kind: create` item so it "
                "rides the same confirmation as the other changes."
            )
        changes = raw_changes
    else:
        changes = [args]

    items: list[BatchItem] = []
    for index, change in enumerate(changes, start=1):
        if not isinstance(change, dict):
            return [], [], f"Schedule change {index} is not a usable edit."
        items.append(BatchItem(day=item_day(change), operations=2 if _is_named_people_swap(change) else 1))
    total = sum(item.operations for item in items)
    if total > MAX_BATCH_OPERATIONS:
        return [], [], split_plan_message(total, plan_batches(items, MAX_BATCH_OPERATIONS), MAX_BATCH_OPERATIONS)

    edit_requests: list[dict[str, Any]] = []
    shift_requests: list[dict[str, Any]] = []
    for index, change in enumerate(changes, start=1):
        kind = str(change.get("kind") or "").strip().lower()
        if kind == "create":
            if not is_batch:
                return [], [], "New shifts and edits need separate schedule proposals."
            request = _coerce_tool_shift_request(change)
            if not (request["date"] and request["start_time"] and request["end_time"]):
                return [], [], (
                    f"Schedule change {index} needs a date, start time, and end time "
                    "before I can create that shift."
                )
            shift_requests.append(request)
            continue

        # `schedule_chat` reserves kind='swap' for a roster-level swap: every
        # assignee on one shift moves to the other. On this surface, a request
        # naming two people means exchange only those assignment rows.
        if _is_named_people_swap(change):
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
            return [], [], prefix + "needs an employee and a specific shift before I can stage it."
        edit_requests.extend(normalized)

    return edit_requests, shift_requests, None


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
        SELECT s.id, s.starts_at
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
    if len(rows) > MAX_BATCH_OPERATIONS:
        # Same reviewability cap as an enumerated batch — the bulk path used
        # to bypass it (500 ops behind a one-line banner).
        items = [BatchItem(day=row["starts_at"].date()) for row in rows]
        return [], split_plan_message(len(rows), plan_batches(items, MAX_BATCH_OPERATIONS), MAX_BATCH_OPERATIONS)
    return [
        {
            "kind": "assign", "target_shift_id": str(row["id"]),
            "to_employee_name": employee_full_name,
        }
        for row in rows
    ], None


async def _fill_vacant_requests(
    conn, *, company_id: UUID, location_id: Optional[UUID],
    week_start: Optional[_date], week_end: Optional[_date],
    args: dict[str, Any], schedule_chat,
) -> tuple[list[dict[str, Any]], list[dict[str, Any]], Optional[str]]:
    """Server-side fill: `week_builder.plan_vacant_fill` picks the people;
    the result becomes plain `assign` edit requests so the SAME
    `build_edit_proposal` (guard, pill, confirm) stages them. Returns
    ``(edit_requests, unfilled, error)``."""
    from app.matcha.services.scheduling.week_builder import plan_vacant_fill, vacant_fill_edit_requests

    if location_id is None or week_start is None:
        return [], [], "Filling open shifts requires a scoped schedule workspace."

    async def _resolve(name_hint: str) -> tuple[Optional[dict[str, Any]], Optional[str]]:
        matched = await schedule_chat._match_single_employee(conn, company_id, name_hint, location_id)
        if "none" in matched:
            return None, matched["none"]
        if "ambiguous" in matched:
            return None, f"Which {name_hint} did you mean? " + ", ".join(matched["ambiguous"])
        return matched["employee"], None

    only_ids: list[UUID] = []
    if str(args.get("to_employee_name") or "").strip():
        employee, error = await _resolve(str(args["to_employee_name"]).strip())
        if error:
            return [], [], error
        only_ids.append(employee["id"])
    exclude_ids: list[UUID] = []
    for name in args.get("exclude_employee_names") or []:
        if not str(name or "").strip():
            continue
        employee, error = await _resolve(str(name).strip())
        if error:
            return [], [], error
        exclude_ids.append(employee["id"])
    shift_ids: list[UUID] = []
    for raw in args.get("fill_shift_ids") or []:
        try:
            shift_ids.append(UUID(str(raw)))
        except (TypeError, ValueError):
            return [], [], "One of those shift ids isn't one I recognise — use ids from get_schedule_overview."

    plan = await plan_vacant_fill(
        conn, company_id=company_id, location_id=location_id, week_start=week_start,
        week_end=week_end, role_hint=(args.get("fill_job_name") or "").strip() or None,
        shift_ids=shift_ids or None, only_employee_ids=only_ids or None,
        exclude_employee_ids=exclude_ids or None,
        allow_split_shift=args.get("allow_split_shift") is True,
    )
    unfilled = [
        {**item, "starts_at": _iso(item.get("starts_at")), "ends_at": _iso(item.get("ends_at"))}
        for item in plan.get("unfilled") or []
    ]
    if plan.get("status") != "ready":
        return [], unfilled, str(plan.get("message") or "I couldn't plan those shifts.")
    if not plan["assignments"]:
        reasons = _unfilled_summary(unfilled)
        return [], unfilled, (
            "I couldn't fill any of those shifts: " + reasons
            + " Loosen the request (another job, allow a split shift, or exclude nobody) or assign by hand."
        )
    edit_requests, error = vacant_fill_edit_requests(plan["assignments"])
    return edit_requests, unfilled, error


def _iso(value: Any) -> Any:
    return value.isoformat() if hasattr(value, "isoformat") else value


def _unfilled_summary(unfilled: list[dict[str, Any]], limit: int = 5) -> str:
    parts = []
    for item in unfilled[:limit]:
        when = str(item.get("starts_at") or "")[:16].replace("T", " ")
        parts.append(f"{(item.get('role') or 'shift')} {when} — {item.get('reason') or 'no eligible employees'}")
    more = f"; …and {len(unfilled) - limit} more" if len(unfilled) > limit else ""
    return "; ".join(parts) + more + "."


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
            statuses=("draft", "published") if schedule_surface else ("published",),
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
            operation_summary = {"create": 1}
        else:
            shift_requests: list[dict[str, Any]] = []
            unfilled: list[dict[str, Any]] = []
            if args.get("fill_vacant_shifts") is True:
                edit_requests, unfilled, error = await _fill_vacant_requests(
                    conn, company_id=company_id, location_id=location_id,
                    week_start=week_start, week_end=week_end, args=args,
                    schedule_chat=schedule_chat,
                )
            elif args.get("all_vacant_shifts") is True:
                edit_requests, error = await _all_vacant_shift_requests(
                    conn, company_id=company_id, location_id=location_id,
                    week_start=week_start, week_end=week_end,
                    employee_name=args.get("to_employee_name"),
                    schedule_chat=schedule_chat,
                )
            else:
                edit_requests, shift_requests, error = _coerce_tool_batch(schedule_chat, args)
            if error:
                return {"status": "clarify", "message": error}
            if not edit_requests and not shift_requests:
                return {
                    "status": "clarify",
                    "message": "I need the employee and the specific shift before I can make that change. "
                               "Reply with the shift date and time, or the employee currently assigned.",
                }
            shift_statuses = ("draft", "published") if is_editor_surface else ("published",)
            if shift_requests:
                # A correction: cancellations/edits plus the replacement
                # shifts they make room for — ONE row, ONE confirmation, ONE
                # transaction (edits first, then creates).
                build = await schedule_chat.build_batch_proposal(
                    conn, company_id=company_id, channel_id=None, source_message_id=None,
                    created_by=actor_user_id, edit_requests=edit_requests,
                    shift_requests=shift_requests, location_hint=args.get("location_name"),
                    ack="Got it.", today=today,
                    original_content="[huume thread] batched schedule correction",
                    surface=surface, shift_statuses=shift_statuses,
                    editor_location_id=location_id, week_start=week_start, week_end=week_end,
                )
            else:
                parsed = {"ack": "Got it.", "action": "edit", "shift_requests": [], "edit_requests": edit_requests}
                build = await schedule_chat.build_edit_proposal(
                    conn, company_id=company_id, channel_id=None, source_message_id=None,
                    created_by=actor_user_id, parsed=parsed, today=today,
                    original_content=f"[huume thread] {kind} request",
                    surface=surface,
                    shift_statuses=shift_statuses,
                    editor_location_id=location_id,
                    editor_week_start=week_start, editor_week_end=week_end,
                )
            operation_count = len(edit_requests) + len(shift_requests)
            operation_summary = summarize_operations(edit_requests, shift_requests)
    except Exception:
        logger.exception("schedule_skill.propose failed for company %s", company_id)
        return {"status": "refused", "message": "That failed just now — try the Schedule page instead."}
    if kind == "create" and args.get("changes") in (None, []):
        unfilled = []

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
        if build.clarify_kind == "refused":
            # Every op was rejected (overlaps, unavailable, full) or the state's
            # rules could not be loaded — the message already says what to do.
            return {"status": "clarify", "message": text}
        return {"status": "clarify", "message": (
            f"{text}\nReply with the shift time, employee, or whether you mean the "
            "staffed or unstaffed shift."
        )}
    review = build.review or {}
    if unfilled:
        # Seats the planner could not fill are part of what the manager
        # reviews — on the pill via the review, on the state block, and in the
        # model's same-turn echo.
        review = {**review, "unfilled": unfilled}
    if review:
        # Count what was actually STAGED: the guard may have rejected some of
        # the requested ops, and the model must not describe those as done.
        staged_ops = [a for a in review.get("assignments") or [] if a.get("op") != "create"]
        create_count = len({a.get("shift_id") for a in review.get("assignments") or [] if a.get("op") == "create"})
        operation_count = len(staged_ops) + (create_count or (1 if kind == "create" else 0))
        operation_summary = summarize_operations(
            [{"kind": a.get("op")} for a in staged_ops], [None] * create_count,
        ) if staged_ops or create_count else operation_summary
    return {
        "status": "ready",
        "proposal_id": str(build.proposal_id),
        "pill_text": build.pill_text,
        "operation_count": operation_count,
        "operation_summary": operation_summary,
        "review": review,
        "rejected_count": len(review.get("rejected") or []),
        "unfilled_count": len(review.get("unfilled") or []),
        "compliance_status": review.get("compliance_status") or "unmapped",
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
        proposal_kind = proposal.get("kind")
        if proposal_kind == "batch":
            executor = schedule_chat.execute_batch_proposal
        elif proposal_kind == "edit":
            executor = schedule_chat.execute_edit_proposal
        else:
            executor = schedule_chat.execute_proposal
        try:
            text = await executor(
                conn, proposal_row={**dict(row), "proposal": proposal},
                confirmed_by=actor_user_id, features=features,
                week_start=week_start, week_end=week_end,
            )
        except schedule_chat.ProposalExecutionClaimError as exc:
            return {"status": "error", "message": str(exc)}
        except schedule_chat.ProposalScopeError as exc:
            # Raised inside the batch transaction → everything rolled back.
            return {"status": "error", "message": f"Nothing was applied — {exc}"}
        except Exception:
            if proposal_kind != "batch":
                raise
            # The batch executor runs both halves in one transaction, so an
            # unexpected failure here means the DB rolled ALL of it back —
            # say so plainly rather than letting the agent's generic failure
            # path imply a partial write.
            logger.exception("schedule batch %s failed and was rolled back", proposal_id)
            return {
                "status": "error",
                "message": "Nothing was applied — that batch failed partway and was rolled back. "
                           "Try confirming again, or make the change on the Schedule page.",
            }
    return {"status": "created", "message": text, "record_id": proposal_id, "bg_tasks": []}
