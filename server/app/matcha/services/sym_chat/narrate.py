"""Every string the group or a tunnel sees that the model did not write.

- `describe_stance` — the shared per-person line ("Priya can't do 3:00 PM. They
  can do 4:00 PM–5:00 PM."), rendered from the structured stance.
- `describe_change` — the shared group line, or None when nothing material
  changed (responded count, best slot / leading option or its headcount,
  consensus).
- `kickoff_text` / `nudge_text` / `confirmed_text` — the coordinator's
  messages into each private tunnel, steering everyone toward the candidate.

Deterministic templates only: the shared feed never carries model text or a
participant's raw words, so what someone typed stays in their own tunnel; only
the structured reading of it is shared.
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
            f"So far {leading['name']} is leading — {leading['ok']} of {total} in "
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


# ── per-person lines + coordinator messages ────────────────────────────────


def _join(items: list[str]) -> str:
    if len(items) <= 1:
        return "".join(items)
    return f"{', '.join(items[:-1])} and {items[-1]}"


def _span(window: dict) -> str:
    return f"{fmt_time(window.get('start'))}–{fmt_time(window.get('end'))}"


def _names_in(stance: dict) -> list[str]:
    seen: list[str] = []
    for name in (stance.get("top_pick"), *(stance.get("proposals") or []), *(stance.get("ok_with") or [])):
        if isinstance(name, str) and name and name.casefold() not in {s.casefold() for s in seen}:
            seen.append(name)
    return seen


def describe_stance(kind: str, name: str, stance: dict | None) -> str | None:
    """One person's structured answer as a shared line; None if they've said nothing usable."""
    stance = stance or {}
    parts: list[str] = []
    if kind == "schedule":
        unavailable = [_span(w) for w in stance.get("unavailable") or []]
        available = [_span(w) for w in stance.get("available") or []]
        preferred = [fmt_time(p) for p in stance.get("preferred") or []]
        if unavailable:
            parts.append(f"{name} can't do {_join(unavailable)}.")
        if available:
            parts.append(f"{'They' if unavailable else name} can do {_join(available)}.")
        if preferred and parts:
            parts.append(f"Prefers {_join(preferred)}.")
    else:
        in_for = _names_in(stance)
        vetoes = [v for v in stance.get("vetoes") or [] if isinstance(v, str)]
        if in_for:
            parts.append(f"{name} is in for {_join(in_for)}.")
        if stance.get("top_pick"):
            parts.append(f"Top pick: {stance['top_pick']}.")
        if vetoes:
            parts.append(f"{'They' if in_for else name} won't do {_join(vetoes)}.")
    return " ".join(parts) or None


def outcome_text(resolution: dict) -> str:
    if resolution.get("kind") == "schedule":
        return (
            f"{fmt_time(resolution.get('start'))}–{fmt_time(resolution.get('end'))} "
            f"on {fmt_date(resolution.get('date'))} ({resolution.get('timezone')})"
        )
    return str(resolution.get("choice"))


def candidate_text(kind: str, shape: dict) -> str | None:
    """The group's current candidate, as a phrase ("4:00 PM on Tue, Sep 29")."""
    if kind == "schedule":
        best = shape.get("best")
        return f"{fmt_time(best['start'])} on {fmt_date(shape.get('date'))}" if best else None
    leading = shape.get("leading")
    return leading["name"] if leading else None


def kickoff_text(kind: str, config: dict, organizer: str, objective: str = "") -> str:
    why = f" ({objective.strip()})" if objective and objective.strip() else ""
    if kind == "schedule":
        return (
            f"Hi! {organizer} is finding a {config.get('duration_min')}-minute slot on "
            f"{fmt_date(config.get('date'))} between {fmt_time(config.get('window_start'))} and "
            f"{fmt_time(config.get('window_end'))} ({config.get('timezone')}){why}. "
            "When are you free? Just tell me in your own words — I'll handle the back-and-forth."
        )
    options = config.get("options") or []
    table = f" Options so far: {_join(options)}." if options else ""
    return (
        f"Hi! {organizer} wants the group to settle on one choice{why}.{table} "
        "What works for you, and is there anything you'd rule out? I'll handle the back-and-forth."
    )


def nudge_text(kind: str, shape: dict, *, responded: bool) -> str | None:
    """Ask one participant whether the current candidate works for them."""
    candidate = candidate_text(kind, shape)
    if not candidate:
        return None
    total = shape.get("total", 0)
    if kind == "schedule":
        count = shape["best"]["count"]
        short = fmt_time(shape["best"]["start"])
    else:
        count = shape["leading"]["ok"]
        short = shape["leading"]["name"]
    if not responded:
        return f"The group is looking at {candidate} ({count} of {total} so far). Does that work for you? If not, tell me what does."
    return f"The best option so far is {candidate} — {count} of {total} can make it. Could you make {short} work?"


def is_nudge_about(message: str | None, candidate: str | None) -> bool:
    """Was `message` a coordinator nudge about this exact candidate? Matches the
    two nudge templates, not a bare substring — the kickoff message lists every
    option, and a substring test there silently suppressed every first nudge."""
    if not message or not candidate:
        return False
    return f"looking at {candidate} (" in message or f"so far is {candidate} —" in message


def confirmed_text(resolution: dict) -> str:
    return f"It's confirmed: {outcome_text(resolution)}. Everyone's in — invites are on the way, nothing else to do."
