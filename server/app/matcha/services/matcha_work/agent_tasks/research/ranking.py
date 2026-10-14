"""Ordering what a research task found. Pure: the same facts give the same order.

Bands first, then a weighted score inside each band, then fit:

  0  meets every hard constraint, each on a verified fact
  1  nothing rules it out, but at least one constraint can't be confirmed
     (the fact is missing, or only claimed on some other page): "Unconfirmed"
  9  hidden: breaks a constraint on a verified fact, judged irrelevant,
     no longer available, or dismissed by the person

The score is the plan's preferences (`{field, weight, higher_is_better}`),
each scaled 0..1 across the task's findings, plus fit (0-5) at the plan's
`fit_weight`. A fact that is not verified or claimed scores as the worst.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from typing import Any

from . import fields as F

OPS = ("lte", "gte", "eq", "includes", "excludes", "is_true", "is_false", "before", "after")
HIDDEN = 9
UNCONFIRMED = 1
OK = 0
_FIT_UNKNOWN = 0.4


@dataclass(frozen=True)
class Ranked:
    item_id: str
    rank: int
    band: int
    score: float
    explain: dict


def describe(constraint: dict) -> str:
    """A constraint as a person reads it: "Price at most $3,500"."""
    spec = F.LIBRARY.get(constraint.get("field"))
    if spec is None:
        return ""
    op, value = constraint.get("op"), constraint.get("value")
    shown = value
    if spec.type == "money" and isinstance(value, (int, float)):
        shown = F.display(spec, float(value), currency=constraint.get("currency"), unit=constraint.get("unit"))
    elif spec.type == "tags":
        shown = ", ".join(spec.tags.get(t, t) for t in (value if isinstance(value, list) else [value]))
    elif spec.type == "date" and isinstance(value, str):
        try:
            shown = F.display(spec, value)
        except ValueError:
            pass
    words = {
        "lte": "at most", "gte": "at least", "eq": "is", "includes": "includes", "excludes": "excludes",
        "before": "by", "after": "after",
    }
    if op == "is_true":
        return f"{spec.label}: yes"
    if op == "is_false":
        return f"{spec.label}: no"
    return f"{spec.label} {words.get(op, op)} {shown}"


def check(constraint: dict, entry: dict | None) -> str:
    """`ok`, `violates` or `unknown` for one constraint against one stored field."""
    if not entry or entry.get("status") != "verified":
        return "unknown"
    spec = F.LIBRARY.get(constraint.get("field"))
    if spec is None:
        return "unknown"
    op, want, have = constraint.get("op"), constraint.get("value"), entry.get("value")
    try:
        if op in ("lte", "gte", "eq") and spec.type in ("money", "number", "rating"):
            if spec.type == "money":
                want_unit = constraint.get("unit")
                if want_unit and entry.get("unit") and entry["unit"] != want_unit:
                    return "unknown"  # a nightly price says nothing about a monthly budget
                if constraint.get("currency") and entry.get("currency") != constraint["currency"]:
                    return "unknown"
            a, b = float(have), float(want)
            ok = a <= b if op == "lte" else a >= b if op == "gte" else abs(a - b) < 1e-9
            return "ok" if ok else "violates"
        if op in ("includes", "excludes") and spec.type == "tags":
            wanted = set(want if isinstance(want, list) else [want])
            present = set(have or [])
            if op == "excludes":
                return "violates" if wanted & present else "ok"
            if wanted <= present:
                return "ok"
            if spec.key == "pets" and "none" in present:
                return "violates"
            return "unknown"  # "cats OK" doesn't say dogs aren't
        if op in ("includes", "excludes") and spec.type == "text":
            found = str(want).casefold() in str(have).casefold()
            return "ok" if found == (op == "includes") else "violates"
        if op in ("is_true", "is_false") and spec.type == "bool":
            return "ok" if bool(have) == (op == "is_true") else "violates"
        if op in ("before", "after") and spec.type == "date":
            a, b = date.fromisoformat(str(have)), date.fromisoformat(str(want))
            return "ok" if (a <= b if op == "before" else a >= b) else "violates"
    except (TypeError, ValueError):
        return "unknown"
    return "unknown"


def _sortable(spec_type: str, value: Any) -> float | None:
    if value is None:
        return None
    if spec_type in ("money", "number", "rating"):
        return float(value)
    if spec_type == "bool":
        return 1.0 if value else 0.0
    if spec_type == "date":
        try:
            return float(date.fromisoformat(str(value)).toordinal())
        except ValueError:
            return None
    if spec_type == "tags":
        return float(len(value or []))
    return None


def _scaled(items: list[dict], pref: dict) -> dict[str, float]:
    """item id -> 0..1 on this preference, best = 1. Missing facts score 0."""
    spec = F.LIBRARY.get(pref.get("field"))
    if spec is None:
        return {}
    values = {}
    for item in items:
        entry = (item.get("fields") or {}).get(spec.key)
        if entry and entry.get("status") in F.STATUS_RANK:
            number = _sortable(spec.type, entry.get("value"))
            if number is not None:
                values[str(item["id"])] = number
    if not values:
        return {}
    lo, hi = min(values.values()), max(values.values())
    higher = pref.get("higher_is_better")
    if higher is None:
        higher = spec.higher_is_better if spec.higher_is_better is not None else True
    out = {}
    for item_id, number in values.items():
        if hi == lo:
            out[item_id] = 1.0  # all the same: none is worse
            continue
        share = (number - lo) / (hi - lo)
        out[item_id] = share if higher else 1.0 - share
    return out


def assess(item: dict, constraints: list[dict]) -> tuple[int, list[dict], list[str]]:
    """(band, violations, unconfirmed field keys) before the person's own say."""
    violations, unconfirmed = [], []
    for constraint in constraints:
        verdict = check(constraint, (item.get("fields") or {}).get(constraint.get("field")))
        if verdict == "violates":
            violations.append({"field": constraint.get("field"), "rule": describe(constraint),
                               "value": ((item.get("fields") or {}).get(constraint.get("field")) or {}).get("display")})
        elif verdict == "unknown" and constraint.get("field") not in unconfirmed:
            unconfirmed.append(constraint.get("field"))
    if violations:
        return HIDDEN, violations, unconfirmed
    return (UNCONFIRMED if unconfirmed else OK), violations, unconfirmed


def rank(items: list[dict], plan: dict) -> list[Ranked]:
    """Every item ranked. `items`: `{id, fields, status, fit_score, user_state}`
    in the order found (ties keep it)."""
    constraints = [c for c in plan.get("constraints") or [] if isinstance(c, dict)]
    prefs = [p for p in plan.get("preferences") or [] if isinstance(p, dict) and (p.get("weight") or 0) > 0]
    fit_weight = float(plan.get("fit_weight") if plan.get("fit_weight") is not None else 0.3)
    scaled = [(_scaled(items, p), float(p["weight"])) for p in prefs]
    total = sum(w for _, w in scaled) + fit_weight
    rows = []
    for order, item in enumerate(items):
        key = str(item["id"])
        band, violations, unconfirmed = assess(item, constraints)
        flags = [f"unconfirmed:{field}" for field in unconfirmed]
        if item.get("status") == "unavailable":
            band, flags = HIDDEN, [*flags, "unavailable"]
        elif item.get("status") == "irrelevant":
            band, flags = HIDDEN, [*flags, "irrelevant"]
        if item.get("user_state") == "dismissed":
            band, flags = HIDDEN, [*flags, "dismissed"]
        if violations:
            flags.append("violates")
        fit = item.get("fit_score")
        fit_share = (float(fit) / 5.0) if isinstance(fit, (int, float)) else _FIT_UNKNOWN
        parts = {p["field"]: round(s.get(key, 0.0), 3) for (s, _), p in zip(scaled, prefs)}
        raw = sum(s.get(key, 0.0) * w for s, w in scaled) + fit_share * fit_weight
        score = round(raw / total, 4) if total > 0 else 0.0
        rows.append((band, -score, -(fit if isinstance(fit, (int, float)) else -1), order, key, score,
                     {"band": band, "flags": flags, "violations": violations, "score": score,
                      "parts": parts, "fit": fit}))
    rows.sort(key=lambda r: r[:4])
    return [Ranked(item_id=r[4], rank=i + 1, band=r[0], score=r[5], explain=r[6]) for i, r in enumerate(rows)]
