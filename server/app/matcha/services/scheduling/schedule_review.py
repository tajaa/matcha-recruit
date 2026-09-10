"""`ScheduleReview` — the one shape for "what this schedule write will do".

Produced from a resolved `schedule_chat_proposals` doc (`kind` edit / create /
batch) after `assignment_guard` has annotated its ops — or, via
`build_week_draft_review`, from a week-builder plan — and consumed by three
renderers that must never disagree: the thread/channel pill
(`schedule_chat.edit_proposal_text` & co.), Huume's stage-turn tool response
and state block (`huume/schedule_skill.propose`, `huume/prompt`), and — later
— the Schedule Pilot review pane and the REST preview route. Pure: no DB.

Contract (JSON-safe):
    proposal_id, kind, compliance_status ∈ {verified, advisory, unmapped, unavailable},
    operation_count, operation_summary,  # resolved edits + new shifts, not flattened assignees
    assignments: [{shift_id, role, starts_at, ends_at, employee_id, employee_name, op, verdict, reasons}],
    rejected:    [{shift_id, role, starts_at, ends_at, employee_name, op, reasons}],   # not staged
    unfilled:    [...],                                                                # planner only
    employees:   [{employee_id, name, before, after, warnings}],
    advisories:  [{message, statute, employee_name, shift_id}],                         # statutory, verbatim
    findings:    [...],
    jurisdiction:{state, status, message}

`compliance_status` is the honesty flag every surface reads before saying a
word about legality: `unmapped`/`unavailable` mean the statutory check did
NOT evaluate this state's law and the output must never be called compliant.
"""

from __future__ import annotations

from collections import Counter
from datetime import datetime
from typing import Any, Optional

from .schedule_batch import summarize_operations

_STATUS_SOURCE_LABEL = {"curated": "hand-curated", "catalog": "approved catalog research"}
_REVIEW_ECHO_ITEMS = 20


def jurisdiction_message(info: Optional[dict[str, Any]]) -> dict[str, Any]:
    """Normalize a `shift_compliance.jurisdiction_rule_status` result into the
    `{state, status, message}` the review carries. The message is the exact
    sentence every surface renders — one place to get the wording right."""
    info = info or {}
    state = (info.get("state") or "").strip().upper() or None
    status = info.get("status") or "unmapped"
    if status == "unavailable":
        message = (
            f"Could not load {state or 'this state'}'s scheduling-law thresholds just now — "
            "this is temporary, not an all-clear."
        )
    elif status in _STATUS_SOURCE_LABEL:
        message = f"Scheduling law for {state} is on file ({_STATUS_SOURCE_LABEL[status]})."
    elif state is None:
        message = "This location has no state on file, so no scheduling law was checked."
    else:
        message = (
            f"Legality was NOT verified for {state} — Matcha has no researched scheduling "
            "thresholds for it. Confirming means you've checked meal-break, overtime and rest "
            "rules yourself."
        )
    return {"state": state, "status": status, "message": message}


def compliance_status_for(jurisdiction: dict[str, Any], advisories: list[dict[str, Any]]) -> str:
    status = jurisdiction.get("status")
    if status == "unavailable":
        return "unavailable"
    if status not in _STATUS_SOURCE_LABEL:
        return "unmapped"
    return "advisory" if advisories else "verified"


def _op_label(op: dict[str, Any]) -> str:
    return (op.get("shift_role") or "shift").title()


def _assignment_from_op(op: dict[str, Any]) -> dict[str, Any]:
    review = op.get("review") or {}
    return {
        "shift_id": op.get("shift_id"),
        "role": _op_label(op),
        "starts_at": op.get("starts_at"),
        "ends_at": op.get("ends_at"),
        "employee_id": op.get("to_employee_id") or op.get("from_employee_id"),
        "employee_name": op.get("to_employee_name") or op.get("from_employee_name"),
        "op": op.get("kind"),
        "verdict": review.get("verdict") or "ok",
        "reasons": list(review.get("reasons") or []),
    }


def _advisories_from_ops(ops: list[dict[str, Any]]) -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []
    for op in ops:
        who = op.get("to_employee_name") or op.get("from_employee_name")
        for item in op.get("advisories") or []:
            out.append({
                "message": item.get("message"), "statute": item.get("statute"),
                "employee_name": who, "shift_id": op.get("shift_id"),
            })
    return out


def _employees_from_ops(ops: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """First accepted op's `before` and last accepted op's `after` per person,
    plus every policy warning raised on their ops."""
    seen: dict[str, dict[str, Any]] = {}
    for op in ops:
        review = op.get("review")
        if not review or review.get("verdict") == "blocked":
            continue  # no guard data (legacy/channel op) or refused — nothing to summarize
        employee_id = op.get("to_employee_id")
        if not employee_id:
            continue
        entry = seen.setdefault(employee_id, {
            "employee_id": employee_id,
            "name": op.get("to_employee_name") or "",
            "before": review.get("before") or {},
            "after": review.get("after") or {},
            "warnings": [],
        })
        entry["after"] = review.get("after") or entry["after"]
        for reason in review.get("reasons") or []:
            message = reason.get("message")
            if message and message not in entry["warnings"]:
                entry["warnings"].append(message)
    return list(seen.values())


def _create_assignments(shifts: list[dict[str, Any]]) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    assignments: list[dict[str, Any]] = []
    advisories: list[dict[str, Any]] = []
    for shift in shifts:
        label = (shift.get("label") or shift.get("role") or "shift").title()
        for assignee in shift.get("assignees") or []:
            assignments.append({
                "shift_id": shift.get("id"), "role": label,
                "starts_at": shift.get("starts_at"), "ends_at": shift.get("ends_at"),
                "employee_id": assignee.get("employee_id"), "employee_name": assignee.get("name"),
                "op": "create", "verdict": "warn" if assignee.get("violations") else "ok",
                "reasons": [],
            })
            for item in assignee.get("violations") or []:
                advisories.append({
                    "message": item.get("message"), "statute": item.get("statute"),
                    "employee_name": assignee.get("name"), "shift_id": shift.get("id"),
                })
        if not shift.get("assignees"):
            assignments.append({
                "shift_id": shift.get("id"), "role": label,
                "starts_at": shift.get("starts_at"), "ends_at": shift.get("ends_at"),
                "employee_id": None, "employee_name": None,
                "op": "create", "verdict": "ok", "reasons": [],
            })
        for item in shift.get("intrinsic_violations") or []:
            advisories.append({
                "message": item.get("message"), "statute": item.get("statute"),
                "employee_name": None, "shift_id": shift.get("id"),
            })
    return assignments, advisories


def build_review(proposal: dict[str, Any], *, proposal_id: Optional[str] = None) -> dict[str, Any]:
    """Build the review for an edit, create or batch doc. Idempotent — safe to
    call on a doc that already carries a `review` (it is recomputed)."""
    kind = proposal.get("kind") or "create"
    if kind == "batch":
        edit_doc = proposal.get("edit") or {}
        create_doc = proposal.get("create") or {}
        ops = list(edit_doc.get("ops") or [])
        shifts = list(create_doc.get("shifts") or [])
        create_assignments, create_advisories = _create_assignments(shifts)
        rejected = list(edit_doc.get("rejected") or []) + list(proposal.get("rejected") or [])
        jurisdiction = proposal.get("jurisdiction") or edit_doc.get("jurisdiction") or create_doc.get("jurisdiction")
        findings = list(create_doc.get("findings") or [])
    elif kind == "edit":
        ops = list(proposal.get("ops") or [])
        shifts = []
        create_assignments, create_advisories = [], []
        rejected = list(proposal.get("rejected") or [])
        jurisdiction = proposal.get("jurisdiction")
        findings = []
    else:
        ops = []
        shifts = list(proposal.get("shifts") or [])
        create_assignments, create_advisories = _create_assignments(shifts)
        rejected = []
        jurisdiction = proposal.get("jurisdiction")
        findings = list(proposal.get("findings") or [])

    jurisdiction = jurisdiction_message(jurisdiction)
    advisories = _advisories_from_ops(ops) + create_advisories
    return {
        "proposal_id": proposal_id,
        "kind": kind,
        "operation_count": len(ops) + len(shifts),
        "operation_summary": summarize_operations(ops, shifts),
        "compliance_status": compliance_status_for(jurisdiction, advisories),
        "assignments": [_assignment_from_op(op) for op in ops] + create_assignments,
        "rejected": rejected,
        "unfilled": list(proposal.get("unfilled") or []),
        "employees": _employees_from_ops(ops),
        "advisories": advisories,
        "findings": findings,
        "jurisdiction": jurisdiction,
    }


def _week_bucket(assignments: list[dict[str, Any]], *, week_start, week_end) -> dict[str, dict[str, Any]]:
    """Per-employee minutes / shifts / days from a list of `{employee_id,
    starts_at, worked_minutes}` rows, counting only the given week."""
    out: dict[str, dict[str, Any]] = {}
    for item in assignments:
        starts = item.get("starts_at")
        if isinstance(starts, str):
            starts = datetime.fromisoformat(starts)
        day = starts.date() if hasattr(starts, "date") else None
        if day is None or not (week_start <= day <= week_end):
            continue
        entry = out.setdefault(str(item["employee_id"]), {"minutes": 0, "shifts": 0, "days": set()})
        entry["minutes"] += int(item.get("worked_minutes") or 0)
        entry["shifts"] += 1
        entry["days"].add(day)
    return out


def _load_shape(entry: Optional[dict[str, Any]]) -> dict[str, int]:
    entry = entry or {}
    return {"minutes": int(entry.get("minutes", 0)), "shifts": int(entry.get("shifts", 0)),
            "days": len(entry.get("days") or ())}


def build_week_draft_review(
    plan: dict[str, Any], *, employee_names: dict[str, str],
    existing_assignments: list[dict[str, Any]], week_start, week_end,
    proposal_id: Optional[str] = None,
    concentration_findings: Optional[list[dict[str, Any]]] = None,
) -> dict[str, Any]:
    """The `ScheduleReview` for a week-builder plan (`kind="week_draft"`).

    Same contract as an edit review so one pane renders both: `assignments`
    are the planner's proposed pairs (verdict `warn` when the preflight
    attached a statutory advisory), `unfilled` the open seats with the
    planner's reason, `employees` each person's load before/after with the
    concentration finding as their warning, `advisories` verbatim, and
    `jurisdiction`/`compliance_status` from the findings pass. `rejected` is
    empty by construction — the planner refuses before proposing."""
    shifts = list(plan.get("shifts") or [])
    by_key = {shift.get("key"): shift for shift in shifts}
    assignments: list[dict[str, Any]] = []
    advisories: list[dict[str, Any]] = []
    proposed_rows: list[dict[str, Any]] = []
    for shift in shifts:
        role = (shift.get("role") or "shift").title()
        for item in shift.get("proposed_assignments") or []:
            employee_id = str(item["employee_id"])
            name = item.get("employee_name") or employee_names.get(employee_id) or "Employee"
            items = list(item.get("advisories") or [])
            assignments.append({
                "shift_id": shift.get("key"), "role": role,
                "starts_at": shift.get("starts_at"), "ends_at": shift.get("ends_at"),
                "employee_id": employee_id, "employee_name": name, "op": "assign",
                "verdict": "warn" if items else "ok", "reasons": [],
            })
            advisories.extend({
                "message": adv.get("message"), "statute": adv.get("statute"),
                "employee_name": name, "shift_id": shift.get("key"),
            } for adv in items)
            proposed_rows.append({
                "employee_id": employee_id, "starts_at": shift.get("starts_at"),
                "worked_minutes": shift.get("worked_minutes") or 0,
            })
    before = _week_bucket(existing_assignments, week_start=week_start, week_end=week_end)
    after = {
        employee_id: {
            "minutes": entry["minutes"], "shifts": entry["shifts"],
            "days": set(entry["days"]),
        }
        for employee_id, entry in before.items()
    }
    for employee_id, delta in _week_bucket(
        proposed_rows, week_start=week_start, week_end=week_end,
    ).items():
        entry = after.setdefault(employee_id, {"minutes": 0, "shifts": 0, "days": set()})
        entry["minutes"] += delta["minutes"]
        entry["shifts"] += delta["shifts"]
        entry["days"].update(delta["days"])
    findings = list(plan.get("findings") or [])
    concentration = {
        str(finding["employee_id"]): finding.get("detail")
        for finding in (
            concentration_findings if concentration_findings is not None else findings
        )
        if finding.get("kind") == "staffing_concentration" and finding.get("employee_id")
    }
    employees: list[dict[str, Any]] = []
    review_employee_ids = {row["employee_id"] for row in proposed_rows} | set(concentration)
    for employee_id in sorted(review_employee_ids,
                              key=lambda eid: (-after.get(eid, {}).get("minutes", 0), eid)):
        name = employee_names.get(employee_id) or next(
            (a["employee_name"] for a in assignments if a["employee_id"] == employee_id), "Employee",
        )
        warning = concentration.get(employee_id)
        employees.append({
            "employee_id": employee_id, "name": name,
            "before": _load_shape(before.get(employee_id)), "after": _load_shape(after.get(employee_id)),
            "warnings": [warning] if warning else [],
        })
    unfilled = [{
        "shift_id": item.get("shift_key"), "role": item.get("role"),
        "starts_at": item.get("starts_at"),
        "ends_at": (by_key.get(item.get("shift_key")) or {}).get("ends_at"),
        "reason": item.get("reason"), "exclusions": dict(item.get("exclusions") or {}),
    } for item in plan.get("unfilled") or []]
    jurisdiction = jurisdiction_message(plan.get("jurisdiction"))
    return {
        "proposal_id": proposal_id,
        "kind": "week_draft",
        "compliance_status": compliance_status_for(jurisdiction, advisories),
        "assignments": assignments,
        "rejected": [],
        "unfilled": unfilled,
        "employees": employees,
        "advisories": advisories,
        "findings": findings,
        "jurisdiction": jurisdiction,
    }


def rejected_entry(op: dict[str, Any]) -> dict[str, Any]:
    """Compact form of a blocked op for `proposal["rejected"]`."""
    review = op.get("review") or {}
    return {
        "shift_id": op.get("shift_id"),
        "role": _op_label(op),
        "starts_at": op.get("starts_at"),
        "ends_at": op.get("ends_at"),
        "employee_id": op.get("to_employee_id"),
        "employee_name": op.get("to_employee_name"),
        "op": op.get("kind"),
        "reasons": list(review.get("reasons") or []),
    }


def summarize_review(review: dict[str, Any]) -> dict[str, Any]:
    """The few numbers the Huume state block / banner render."""
    warnings = [w for person in review.get("employees") or [] for w in person.get("warnings") or []]
    staged = review.get("assignment_count")
    if staged is None:
        staged = len([
            item for item in review.get("assignments") or []
            if item.get("verdict") != "blocked"
        ])
    rejected = review.get("rejected_count")
    if rejected is None:
        rejected = len(review.get("rejected") or [])
    unfilled = review.get("unfilled_count")
    if unfilled is None:
        unfilled = len(review.get("unfilled") or [])
    advisories = review.get("advisory_count")
    if advisories is None:
        advisories = len(review.get("advisories") or [])
    return {
        "staged": int(staged),
        "rejected": int(rejected),
        "unfilled": int(unfilled),
        # Already summarized when the review came back through `compact_review`
        # (the state-block path); recomputed for a full review.
        "unfilled_reasons": (
            list(review.get("unfilled_reasons") or []) or unfilled_reason_summary(review)
        ),
        "advisories": int(advisories),
        "warnings": warnings,
        "compliance_status": review.get("compliance_status"),
        "jurisdiction_message": (review.get("jurisdiction") or {}).get("message"),
    }


def unfilled_reason_summary(
    review: dict[str, Any], *, limit: int = 3,
) -> list[dict[str, Any]]:
    """The distinct blockers behind the open seats, heaviest first.

    A COUNT is not an explanation: on the turn after a fill, the state block
    is all the model has, and "12 open seats" is a number it cannot turn into
    anything actionable — which is how a fabricated reason ("only two people
    are qualified") reaches the manager. Bounded, because the state block
    must not carry the week twice.
    """
    counted: Counter = Counter()
    for item in review.get("unfilled") or []:
        exclusions = item.get("exclusions") or {}
        if exclusions:
            for message, count in exclusions.items():
                counted[str(message)] += int(count or 0)
        elif item.get("reason"):
            counted[str(item["reason"])] += 1
    return [
        {"reason": message, "seats": count}
        for message, count in sorted(counted.items(), key=lambda pair: (-pair[1], pair[0]))[:limit]
    ]


def compact_review(review: dict[str, Any]) -> dict[str, Any]:
    """Bounded schedule-review state for a staged Huume action.

    The generation proposal remains the source of truth. Thread state only
    needs counts, warning text, and the jurisdiction verdict for the next-turn
    confirmation prompt and card; duplicating every assignment/open seat/
    finding/advisory there makes each later model call carry the week twice.
    """
    warnings = []
    for person in review.get("employees") or []:
        messages = list(person.get("warnings") or [])
        if messages:
            warnings.append({
                "employee_id": person.get("employee_id"),
                "name": person.get("name"),
                "warnings": messages,
            })
    return {
        "proposal_id": review.get("proposal_id"),
        "kind": review.get("kind"),
        "compliance_status": review.get("compliance_status"),
        "assignment_count": len([
            item for item in review.get("assignments") or []
            if item.get("verdict") != "blocked"
        ]),
        "rejected_count": len(review.get("rejected") or []),
        "unfilled_count": len(review.get("unfilled") or []),
        "unfilled_reasons": unfilled_reason_summary(review),
        "advisory_count": len(review.get("advisories") or []),
        "finding_count": len(review.get("findings") or []),
        "employees": warnings,
        "jurisdiction": dict(review.get("jurisdiction") or {}),
    }


def bounded_review_echo(
    review: dict[str, Any], *, limit: int = _REVIEW_ECHO_ITEMS,
) -> dict[str, Any]:
    """Same-turn model payload: compact state plus bounded actionable detail."""
    return {
        **compact_review(review),
        "rejected": list(review.get("rejected") or [])[:limit],
        "unfilled": list(review.get("unfilled") or [])[:limit],
        "advisories": list(review.get("advisories") or [])[:limit],
    }
