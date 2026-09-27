"""Deterministic consensus roll-up: participants' stances → the shared shape.

No model call and no I/O. `participants` is a list of `{"stance": dict|None}`
in a stable order (the service passes join order), which is what makes
"first-seen" tie-breaks reproducible.

schedule — enumerate candidate slots from window_start to window_end-duration
in step_min steps. A participant covers a slot iff one of their `available`
windows contains it and none of their `unavailable` windows overlaps it. The
best slot is the one fewest people have explicitly ruled out (an
`unavailable` overlap) → max coverage → most `preferred` hits → earliest.
Ruled-out-first matters: a slot someone said they can't do can never reach
consensus, so the coordinator should chase the slot that still can. Consensus: every
participant responded and the best slot covers all of them.

decide — options are the organizer's seeds plus every name any participant
proposed, is ok with, or top-picked (first-seen order; vetoes alone never
create an option). Per option: `ok` (people in), `top` (top picks), `vetoes`.
The leader is the vetoless option with the most `ok` → most `top` → first
seen. Consensus: every participant responded and the leader has all of them.
"""
from __future__ import annotations

from .extract import stance_has_content
from .kinds import fmt_hhmm, parse_hhmm

MAX_SLOTS_SHOWN = 5


def _spans(windows) -> list[tuple[int, int]]:
    out = []
    for w in windows or []:
        if not isinstance(w, dict):
            continue
        start, end = parse_hhmm(w.get("start")), parse_hhmm(w.get("end"))
        if start is not None and end is not None and start < end:
            out.append((start, end))
    return out


def _covers(stance: dict, start: int, end: int) -> bool:
    if not any(a <= start and end <= b for a, b in _spans(stance.get("available"))):
        return False
    return not any(u_start < end and start < u_end for u_start, u_end in _spans(stance.get("unavailable")))


def _schedule_shape(config: dict, stances: list[dict | None]) -> dict:
    lo = parse_hhmm(config.get("window_start")) or 0
    hi = parse_hhmm(config.get("window_end")) or 24 * 60
    duration = int(config.get("duration_min") or 30)
    step = int(config.get("step_min") or 15)
    total = len(stances)
    responded = [s for s in stances if stance_has_content("schedule", s)]

    slots = []
    start = lo
    while start + duration <= hi:
        end = start + duration
        count = sum(1 for s in responded if _covers(s, start, end))
        blocked = sum(
            1 for s in responded
            if any(u_start < end and start < u_end for u_start, u_end in _spans(s.get("unavailable")))
        )
        preferred = 0
        for s in responded:
            for p in s.get("preferred") or []:
                minutes = parse_hhmm(p)
                # A preference lands on the slot whose start it rounds down to.
                if minutes is not None and start <= minutes < start + step:
                    preferred += 1
        slots.append({"start": fmt_hhmm(start), "end": fmt_hhmm(end), "count": count, "preferred": preferred,
                      "blocked": blocked, "_m": start})
        start += step

    ranked = sorted(
        (s for s in slots if s["count"] > 0),
        key=lambda s: (s["blocked"], -s["count"], -s["preferred"], s["_m"]),
    )
    for s in slots:
        s.pop("_m")
    best = dict(ranked[0]) if ranked else None
    return {
        "kind": "schedule",
        "date": config.get("date"),
        "timezone": config.get("timezone"),
        "duration_min": duration,
        "total": total,
        "responded": len(responded),
        "best": best,
        "top_slots": [dict(s) for s in ranked[:MAX_SLOTS_SHOWN]],
        "consensus": bool(total and len(responded) == total and best and best["count"] == total),
    }


def _decide_shape(config: dict, stances: list[dict | None]) -> dict:
    total = len(stances)
    responded = [s for s in stances if stance_has_content("decide", s)]

    order: list[str] = []
    display: dict[str, str] = {}

    def _see(name) -> str | None:
        if not isinstance(name, str) or not name.strip():
            return None
        key = name.casefold()
        if key not in display:
            display[key] = name
            order.append(key)
        return key

    for name in config.get("options") or []:
        _see(name)
    for s in responded:
        for name in (s.get("proposals") or []) + (s.get("ok_with") or []) + [s.get("top_pick")]:
            _see(name)

    tallies = {key: {"ok": 0, "top": 0, "vetoes": 0} for key in order}
    for s in responded:
        vetoed = {v.casefold() for v in s.get("vetoes") or [] if isinstance(v, str)}
        in_keys = {
            n.casefold()
            for n in (s.get("proposals") or []) + (s.get("ok_with") or []) + [s.get("top_pick")]
            if isinstance(n, str) and n.strip()
        } - vetoed
        for key in in_keys:
            tallies[key]["ok"] += 1
        top = s.get("top_pick")
        if isinstance(top, str) and top.casefold() in tallies and top.casefold() not in vetoed:
            tallies[top.casefold()]["top"] += 1
        for key in vetoed:
            if key in tallies:
                tallies[key]["vetoes"] += 1

    options = [{"name": display[key], **tallies[key]} for key in order]
    candidates = sorted(
        (
            (i, o) for i, o in enumerate(options)
            if o["vetoes"] == 0 and o["ok"] > 0
        ),
        key=lambda pair: (-pair[1]["ok"], -pair[1]["top"], pair[0]),
    )
    leading = dict(candidates[0][1]) if candidates else None
    return {
        "kind": "decide",
        "total": total,
        "responded": len(responded),
        "options": options,
        "leading": leading,
        "consensus": bool(total and len(responded) == total and leading and leading["ok"] == total),
    }


def compute_shape(kind: str, config: dict, participants: list[dict]) -> dict:
    stances = [p.get("stance") if isinstance(p, dict) else None for p in participants]
    stances = [s if isinstance(s, dict) else None for s in stances]
    if kind == "schedule":
        return _schedule_shape(config or {}, stances)
    if kind == "decide":
        return _decide_shape(config or {}, stances)
    raise ValueError(f"Unknown sym-chat kind: {kind}")


def resolution_for(kind: str, config: dict, shape: dict) -> dict | None:
    """The settled outcome, only when the shape is at consensus."""
    if not shape.get("consensus"):
        return None
    if kind == "schedule":
        best = shape["best"]
        return {
            "kind": "schedule",
            "date": config.get("date"),
            "start": best["start"],
            "end": best["end"],
            "timezone": config.get("timezone"),
        }
    return {"kind": "decide", "choice": shape["leading"]["name"]}


def fits_candidate(kind: str, stance: dict | None, shape: dict) -> bool:
    """Does this participant's stance already include the group's candidate?"""
    if not stance:
        return False
    if kind == "schedule":
        best = shape.get("best")
        if not best:
            return False
        return _covers(stance, parse_hhmm(best["start"]), parse_hhmm(best["end"]))
    leading = shape.get("leading")
    if not leading:
        return False
    key = leading["name"].casefold()
    vetoed = {v.casefold() for v in stance.get("vetoes") or [] if isinstance(v, str)}
    named = {
        n.casefold()
        for n in (stance.get("proposals") or []) + (stance.get("ok_with") or []) + [stance.get("top_pick")]
        if isinstance(n, str) and n
    }
    return key in named and key not in vetoed
