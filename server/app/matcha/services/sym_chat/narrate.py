"""Shape delta → one shared feed line, or None when nothing material changed.

Material means: the responded count moved, the best slot / leading option
changed (or its headcount did), or consensus flipped. Deterministic template
strings only — the shared feed never carries model text, so nothing one
participant typed in their private tunnel can leak to the group.
"""
from __future__ import annotations

from datetime import date as date_cls

from .kinds import parse_hhmm


def fmt_time(hhmm: str | None) -> str:
    """'14:00' → '2:00 PM'."""
    minutes = parse_hhmm(hhmm)
    if minutes is None:
        return hhmm or ""
    hours, mins = divmod(minutes % (24 * 60), 60)
    suffix = "AM" if hours < 12 else "PM"
    return f"{hours % 12 or 12}:{mins:02d} {suffix}"


def fmt_date(iso: str | None) -> str:
    """'2026-09-29' → 'Tue, Sep 29'."""
    try:
        day = date_cls.fromisoformat(iso or "")
    except ValueError:
        return iso or ""
    return f"{day.strftime('%a, %b')} {day.day}"


def _people(n: int) -> str:
    return "1 person" if n == 1 else f"{n} people"


def _schedule_key(shape: dict) -> tuple:
    best = shape.get("best") or {}
    return (shape.get("responded"), best.get("start"), best.get("count"), bool(shape.get("consensus")))


def _decide_key(shape: dict) -> tuple:
    leading = shape.get("leading") or {}
    return (shape.get("responded"), leading.get("name"), leading.get("ok"), bool(shape.get("consensus")))


def _describe_schedule(shape: dict) -> str:
    total, responded = shape.get("total", 0), shape.get("responded", 0)
    best = shape.get("best")
    if shape.get("consensus") and best:
        return (
            f"All {total} agree on {fmt_time(best['start'])} on {fmt_date(shape.get('date'))}. "
            "Sending invites to everyone."
        )
    if best:
        return (
            f"So far {fmt_time(best['start'])} looks best — {best['count']} of {total} can make it "
            f"({responded}/{total} responded)."
        )
    if responded:
        return f"No time works for everyone who's answered yet ({responded}/{total} responded)."
    return f"Waiting on {_people(total)}."


def _describe_decide(shape: dict) -> str:
    total, responded = shape.get("total", 0), shape.get("responded", 0)
    leading = shape.get("leading")
    if shape.get("consensus") and leading:
        return f"All {total} agree on {leading['name']}. Sending invites to everyone."
    if leading:
        return (
            f"So far {leading['name']} is leading — {leading['ok']} of {total} are in "
            f"({responded}/{total} responded)."
        )
    if responded:
        return f"Nothing without a veto yet ({responded}/{total} responded)."
    return f"Waiting on {_people(total)}."


def describe_shape(kind: str, shape: dict) -> str:
    return _describe_schedule(shape) if kind == "schedule" else _describe_decide(shape)


def describe_change(kind: str, old_shape: dict | None, new_shape: dict) -> str | None:
    key = _schedule_key if kind == "schedule" else _decide_key
    if old_shape and key(old_shape) == key(new_shape):
        return None
    return describe_shape(kind, new_shape)
