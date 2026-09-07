"""Bounded batch shape for one confirmable schedule correction.

Pure helpers shared by `schedule_chat` (the resolver/executor that owns the
`kind='batch'` proposal) and Huume's `schedule_skill`/`tools`/`prompt`
(which read the cap so the tool schema, the system prompt, and the refusal
copy can never disagree about the number). No DB, no model, stdlib only —
`huume/tools.py` imports this at module load and must stay light.

A "batch" is every operation one clarified scheduling request needs —
cancellations, reassignments, retimes, AND the replacement shifts they make
room for — staged as ONE `schedule_chat_proposals` row and applied by ONE
confirmation in ONE transaction (edits first, then creates, so a replacement
never double-books against the draft it replaces). `MAX_BATCH_OPERATIONS`
bounds the review: past it the pill stops being something a manager can
actually read before typing "confirm", so the server refuses with a concrete
split plan (`plan_batches` + `split_plan_message`) rather than silently
staging a prefix or asking the model to chunk by hand.

Why 40: a seven-day correction at a store running up to four shifts a day is
28 cancellations + up to 12 replacement rows — comfortably one batch — while
the pill stays under the schedule strip's readable range. It is a module
constant, not a per-company setting, on purpose: the limit protects the
reviewer, not the tenant, and the split plan makes hitting it a one-message
detour instead of a dead end.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date, datetime
from typing import Optional

MAX_BATCH_OPERATIONS = 40


@dataclass(frozen=True)
class BatchItem:
    """One requested change, already weighed: a named-person swap is two
    reassignments and therefore `operations=2`."""
    day: Optional[date]
    operations: int = 1


@dataclass
class BatchGroup:
    days: list[date] = field(default_factory=list)
    operations: int = 0
    undated: bool = False
    oversized: bool = False


def item_day(change: dict) -> Optional[date]:
    """The calendar day a change touches — `target_date` for edits, `date`
    for creates. Unparseable/missing dates bucket together as undated."""
    raw = change.get("target_date") or change.get("date")
    if not raw:
        return None
    try:
        return date.fromisoformat(str(raw).strip()[:10])
    except ValueError:
        return None


def plan_batches(items: list[BatchItem], cap: int = MAX_BATCH_OPERATIONS) -> list[BatchGroup]:
    """Greedy day-contiguous packing: the fewest confirmations that keep
    each batch under `cap` without splitting a day across two batches (a
    day's cancellations and its replacement shifts belong in one review).
    A single day above the cap becomes its own `oversized` group — the
    message then tells the manager to split THAT day by kind."""
    by_day: dict[date, int] = {}
    undated = 0
    for item in items:
        if item.day is None:
            undated += item.operations
        else:
            by_day[item.day] = by_day.get(item.day, 0) + item.operations

    groups: list[BatchGroup] = []
    current = BatchGroup()
    for day in sorted(by_day):
        ops = by_day[day]
        if ops > cap:
            if current.days:
                groups.append(current)
                current = BatchGroup()
            groups.append(BatchGroup(days=[day], operations=ops, oversized=True))
            continue
        if current.days and current.operations + ops > cap:
            groups.append(current)
            current = BatchGroup()
        current.days.append(day)
        current.operations += ops
    if current.days:
        groups.append(current)
    if undated:
        if groups and not groups[-1].oversized and groups[-1].operations + undated <= cap:
            groups[-1].operations += undated
            groups[-1].undated = True
        else:
            groups.append(BatchGroup(operations=undated, undated=True, oversized=undated > cap))
    return groups


def _fmt_day(value: date) -> str:
    return f"{value.strftime('%a %b')} {value.day}"


def _group_label(group: BatchGroup) -> str:
    if not group.days:
        return "the undated changes"
    first, last = group.days[0], group.days[-1]
    label = _fmt_day(first) if first == last else f"{_fmt_day(first)}–{_fmt_day(last)}"
    if group.undated:
        label += " plus the undated changes"
    return label


def split_plan_message(total: int, groups: list[BatchGroup], cap: int = MAX_BATCH_OPERATIONS) -> str:
    """Server-composed refusal for an over-cap request: names the cap, the
    real total, and the smallest day-contiguous split — so the manager's
    next message is "do batch 1", not a negotiation about chunk sizes."""
    lines = [
        f"That's {total} schedule operations in one go — I can stage up to {cap} per "
        f"confirmation so you can actually review what you're approving."
    ]
    if len(groups) <= 1:
        lines.append(
            "Split it by kind: send the cancellations first, then the replacement shifts."
        )
        return " ".join(lines)
    parts = []
    for index, group in enumerate(groups, start=1):
        note = " (still over the cap — split that day by kind)" if group.oversized else ""
        parts.append(f"({index}) {_group_label(group)}, {group.operations} operations{note}")
    lines.append(f"Smallest split is {len(groups)} batches: " + "; ".join(parts) + ".")
    lines.append("Send the first batch and I'll stage it for your confirmation.")
    return " ".join(lines)


def summarize_operations(edit_requests: list[dict], shift_requests: list[dict]) -> dict[str, int]:
    """kind → count, for the staged dict / state block ("28 cancel, 7 create")."""
    summary: dict[str, int] = {}
    for request in edit_requests:
        kind = str(request.get("kind") or "edit")
        summary[kind] = summary.get(kind, 0) + 1
    if shift_requests:
        summary["create"] = summary.get("create", 0) + len(shift_requests)
    return summary


def describe_operations(count: int, summary: Optional[dict[str, int]]) -> str:
    if not summary:
        return f"{count} operation{'s' if count != 1 else ''}"
    order = ("cancel", "unassign", "reassign", "assign", "retime", "swap", "create")
    parts = [f"{summary[k]} {k}" for k in order if summary.get(k)]
    parts += [f"{v} {k}" for k, v in summary.items() if k not in order]
    return f"{count} operation{'s' if count != 1 else ''}: " + ", ".join(parts)


def net_per_day(edit_ops: list[dict], created_shifts: list[dict]) -> list[tuple[date, int, int, int]]:
    """(day, cancelled, other_edits, created) per calendar day, sorted — the
    "resulting schedule state" line of the review pill."""
    rows: dict[date, list[int]] = {}
    for op in edit_ops:
        day = datetime.fromisoformat(op["starts_at"]).date()
        slot = rows.setdefault(day, [0, 0, 0])
        if op.get("kind") == "cancel":
            slot[0] += 1
        else:
            slot[1] += 1
    for shift in created_shifts:
        day = datetime.fromisoformat(shift["starts_at"]).date()
        rows.setdefault(day, [0, 0, 0])[2] += 1
    return [(day, *rows[day]) for day in sorted(rows)]
