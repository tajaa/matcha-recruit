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


class ScheduleProposalResult(TypedDict):
    status: Literal["ready", "clarify", "refused"]
    message: NotRequired[str]
    proposal_id: NotRequired[str]
    pill_text: NotRequired[str]


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
        "target_employee_name": args.get("target_employee_name"),
        "target_date": args.get("target_date"),
        "target_time_hint": args.get("target_time_hint"),
        "target_staffing_hint": args.get("target_staffing_hint"),
        "target_role_hint": args.get("target_role_hint"),
        "to_employee_name": args.get("to_employee_name"),
        "second_employee_name": args.get("second_employee_name"),
        "second_date": args.get("second_date"),
        "second_role_hint": args.get("second_role_hint"),
        "new_date": args.get("new_date"),
        "new_start_time": args.get("new_start_time"),
        "new_end_time": args.get("new_end_time"),
        "shift_by_minutes": args.get("shift_by_minutes"),
    }


async def find_coverage(
    *, company_id: UUID, role: Optional[str], features: dict[str, Any],
    date_str: str, role_hint: Optional[str], location_id: Optional[UUID] = None,
) -> dict[str, Any]:
    """Read-only — same envelope shape as every other read tool: role +
    `employee_schedule` re-checked per call, never trusted from an earlier
    turn."""
    from app.database import get_connection
    from app.matcha.services.scheduling.coverage import find_coverage_candidates

    if role not in _ALLOWED_ROLES:
        return {"error": "Only a business admin can ask for coverage suggestions."}
    if not features.get("employee_schedule"):
        return {"error": "Scheduling isn't enabled for this company."}
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
) -> ScheduleProposalResult:
    """Resolve a STAGE-turn request without executing it.

    ``clarify`` and ``refused`` are terminal for the current Huume turn. A
    thread has no channel pill-reply round trip, so the caller must relay the
    message and wait for the admin's next turn rather than asking Gemini to
    retry the same deterministic resolution.
    """
    from app.matcha.services.scheduling import schedule_chat

    kind = str(args.get("kind") or "").strip().lower()
    today = _date.today()
    try:
        if kind == "create":
            parsed = {
                "ack": "Got it.", "action": "create",
                "location_hint": args.get("location_name"),
                "shift_requests": [_coerce_tool_shift_request(args)],
                "edit_requests": [],
            }
            build = await schedule_chat.build_proposal(
                conn, company_id=company_id, channel_id=None, source_message_id=None,
                created_by=actor_user_id, parsed=parsed, today=today,
                original_content="[huume thread] shift create",
            )
        else:
            edit_req = schedule_chat.coerce_edit_request(_tool_args_to_edit_request(kind, args))
            if edit_req is None:
                return {
                    "status": "clarify",
                    "message": "I need the employee and the specific shift before I can make that change. "
                               "Reply with the shift date and time, or the employee currently assigned.",
                }
            parsed = {"ack": "Got it.", "action": "edit", "shift_requests": [], "edit_requests": [edit_req]}
            build = await schedule_chat.build_edit_proposal(
                conn, company_id=company_id, channel_id=None, source_message_id=None,
                created_by=actor_user_id, parsed=parsed, today=today,
                original_content=f"[huume thread] {kind} request",
            )
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
    }


async def execute(*, company_id: UUID, actor_user_id: UUID, action: dict[str, Any]) -> dict[str, Any]:
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
            )
        except schedule_chat.ProposalExecutionClaimError as exc:
            return {"status": "error", "message": str(exc)}
    return {"status": "created", "message": text, "record_id": proposal_id, "bg_tasks": []}
