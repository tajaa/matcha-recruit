"""`ScheduleReview` — the one shape for "what this schedule write will do".

Produced from a resolved `schedule_chat_proposals` doc (`kind` edit / create /
batch) after `assignment_guard` has annotated its ops, and consumed by three
renderers that must never disagree: the thread/channel pill
(`schedule_chat.edit_proposal_text` & co.), Huume's stage-turn tool response
and state block (`huume/schedule_skill.propose`, `huume/prompt`), and — later
— the Schedule Pilot review pane and the REST preview route. Pure: no DB.

Contract (JSON-safe):
    proposal_id, kind, compliance_status ∈ {verified, advisory, unmapped, unavailable},
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

from typing import Any, Optional

_STATUS_SOURCE_LABEL = {"curated": "hand-curated", "catalog": "approved catalog research"}


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
        create_assignments, create_advisories = _create_assignments(create_doc.get("shifts") or [])
        rejected = list(edit_doc.get("rejected") or []) + list(proposal.get("rejected") or [])
        jurisdiction = proposal.get("jurisdiction") or edit_doc.get("jurisdiction") or create_doc.get("jurisdiction")
        findings = list(create_doc.get("findings") or [])
    elif kind == "edit":
        ops = list(proposal.get("ops") or [])
        create_assignments, create_advisories = [], []
        rejected = list(proposal.get("rejected") or [])
        jurisdiction = proposal.get("jurisdiction")
        findings = []
    else:
        ops = []
        create_assignments, create_advisories = _create_assignments(proposal.get("shifts") or [])
        rejected = []
        jurisdiction = proposal.get("jurisdiction")
        findings = list(proposal.get("findings") or [])

    jurisdiction = jurisdiction_message(jurisdiction)
    advisories = _advisories_from_ops(ops) + create_advisories
    return {
        "proposal_id": proposal_id,
        "kind": kind,
        "compliance_status": compliance_status_for(jurisdiction, advisories),
        "assignments": [_assignment_from_op(op) for op in ops] + create_assignments,
        "rejected": rejected,
        "unfilled": list(proposal.get("unfilled") or []),
        "employees": _employees_from_ops(ops),
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
    return {
        "staged": len([a for a in review.get("assignments") or [] if a.get("verdict") != "blocked"]),
        "rejected": len(review.get("rejected") or []),
        "unfilled": len(review.get("unfilled") or []),
        "warnings": warnings,
        "compliance_status": review.get("compliance_status"),
        "jurisdiction_message": (review.get("jurisdiction") or {}).get("message"),
    }
