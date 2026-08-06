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
round trip the way channels do — so it's surfaced as a refusal asking the
admin to be more specific, not staged. That's a deliberate v1 scope cut,
not an oversight."""

from datetime import date as _date
from typing import Any, Optional
from uuid import UUID

_ALLOWED_ROLES = frozenset({"client", "admin"})


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
) -> dict[str, Any]:
    """STAGE-turn resolution. Returns `{"error": str}` (refuse staging
    outright — same contract `parse_attachment_for_staging` uses) or
    `{"proposal_id", "pill_text"}` to merge into the staged dict."""
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
                return {"error": "I don't have enough to make that change — who, and which shift?"}
            parsed = {"ack": "Got it.", "action": "edit", "shift_requests": [], "edit_requests": [edit_req]}
            build = await schedule_chat.build_edit_proposal(
                conn, company_id=company_id, channel_id=None, source_message_id=None,
                created_by=actor_user_id, parsed=parsed, today=today,
                original_content=f"[huume thread] {kind} request",
            )
    except Exception:
        return {"error": "That failed just now — try the Schedule page instead."}

    if build.kind == "clarify":
        # No threaded clarify round-trip (v1 scope cut) — ask the admin to
        # restate with the missing detail instead of staging a proposal
        # that can never be confirmed. Keep the full pill_text (question +
        # numbered candidates), not just its first line — the model needs
        # the options to relay them, not just the fact that some exist.
        text = build.pill_text.removeprefix("\U0001F4C5 ").strip()
        return {"error": (
            f"{text}\nAsk the admin which one they mean, then call "
            f"propose_schedule_change again adding target_time_hint (e.g. "
            f"'12:30pm'), target_employee_name, or — if the candidates differ "
            f"only by who's on them — target_staffing_hint ('staffed' or "
            f"'unstaffed') to pin down the shift."
        )}
    return {"proposal_id": str(build.proposal_id), "pill_text": build.pill_text}


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
        text = await executor(
            conn, proposal_row={**dict(row), "proposal": proposal},
            confirmed_by=actor_user_id, features=features,
        )
    return {"status": "created", "message": text, "record_id": proposal_id, "bg_tasks": []}
