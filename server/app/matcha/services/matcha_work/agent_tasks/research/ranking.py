"""Ordering what a research task found. Pure: the same facts give the same order.

Bands first, then a weighted score inside each band, then fit:

  0  meets every hard constraint, each on a verified fact
  1  nothing rules it out, but at least one constraint can't be confirmed
     (the fact is missing, or only claimed on some other page): "Unconfirmed"
  9  hidden: breaks a constraint on a verified fact, judged irrelevant,
     no longer available, or dismissed by the person

An apartment building with its homes listed one by one (`units.py`) is
judged on its homes: a limit on rent, beds, baths, size or move-in date is met
only when one home meets every such limit at once (`unit_verdict`), never
when one home has the rent and another the bedrooms.

The score is the plan's preferences (`{field, weight, higher_is_better}`),
each scaled 0..1 across the task's findings, plus fit (0-5) at the plan's
`fit_weight`. A fact that is not verified or claimed scores as the worst; a
text fact (move-in specials) scores for being there at all.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from typing import Any

from . import fields as F

OPS = ("lte", "gte", "eq", "between", "includes", "excludes", "any_of", "is_true", "is_false", "before", "after")
HIDDEN = 9
UNCONFIRMED = 1
OK = 0
_FIT_UNKNOWN = 0.4
# Limits a building with listed homes is judged on home by home.
UNIT_FIELDS = frozenset({"price", "beds", "baths", "sqft", "available_date"})


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
    if op == "between" and isinstance(value, list) and len(value) == 2 and spec.type in ("money", "number"):
        low, high = sorted(float(v) for v in value)
        if spec.type == "money":
            currency = constraint.get("currency")
            return (f"{spec.label} between {F.display(spec, low, currency=currency)} and "
                    f"{F.display(spec, high, currency=currency, unit=constraint.get('unit'))}")
        return f"{spec.label} between {F.display(spec, low)} and {F.display(spec, high)}"
    if spec.type == "money" and isinstance(value, (int, float)):
        shown = F.display(spec, float(value), currency=constraint.get("currency"), unit=constraint.get("unit"))
    elif spec.type in ("number", "rating") and isinstance(value, (int, float)):
        shown = F.display(spec, float(value)) + (" mi" if spec.key == "distance" else "")
    elif spec.type == "tags":
        joiner = " or " if op == "any_of" else ", "
        shown = joiner.join(spec.tags.get(t, t) for t in (value if isinstance(value, list) else [value]))
    elif spec.type == "date" and isinstance(value, str):
        try:
            shown = F.display(spec, value)
        except ValueError:
            pass
    words = {
        "lte": "at most", "gte": "at least", "eq": "is", "includes": "includes", "excludes": "excludes",
        "any_of": "is", "between": "between",
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
        if op in ("lte", "gte", "eq", "between") and spec.type in ("money", "number", "rating"):
            if spec.type == "money":
                want_unit = constraint.get("unit")
                if want_unit and entry.get("unit") and entry["unit"] != want_unit:
                    return "unknown"  # a nightly price says nothing about a monthly budget
                if constraint.get("currency") and entry.get("currency") != constraint["currency"]:
                    return "unknown"
            return _in_range(op, want, entry.get("spans") or [[have, have]])
        if op in ("includes", "excludes", "any_of") and spec.type == "tags":
            wanted = set(want if isinstance(want, list) else [want])
            present = set(have or [])
            if op == "any_of":  # north or south: one of them will do
                return "ok" if wanted & present else "violates" if present else "unknown"
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


def _in_range(op: str, want: Any, spans: list) -> str:
    """`ok` when any of a finding's figures meets the limit. `spans` are
    [low, high]: one figure is [x, x]; a building's floor plans are many; a
    "starting at x" is [x, None], some homes at x and the rest dearer."""
    if op == "between":
        low, high = sorted(float(v) for v in want)
    elif op == "eq":
        if len(spans) != 1 or spans[0][1] is None or float(spans[0][0]) != float(spans[0][1]):
            return "unknown"  # many figures, or only a floor: no one value to compare
        return "ok" if abs(float(spans[0][0]) - float(want)) < 1e-9 else "violates"
    else:
        low, high = (float("-inf"), float(want)) if op == "lte" else (float(want), float("inf"))
    maybe = False
    for start, end in spans:
        start = float(start)
        if end is None:
            if low <= start <= high:
                return "ok"
            maybe = maybe or start < low  # dearer homes may reach it
        elif start <= high and float(end) >= low:
            return "ok"
    return "unknown" if maybe else "violates"


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
    if spec_type == "text":
        return 1.0 if value else None  # having it at all (move-in specials)
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


def unit_entry(unit: dict, key: str) -> dict | None:
    """One home's figure as a stored field, so `check` reads it like any
    other. Its rent spans its net rent (after a stated special) to its rent:
    a budget the special brings it under is met."""
    if key == "price":
        rent = unit.get("rent")
        if not isinstance(rent, (int, float)):
            return None
        low = min(unit.get("net_rent") or rent, rent)
        return {"value": low, "status": "verified", "unit": "month", "currency": unit.get("currency") or "USD",
                "spans": [[low, rent]]}
    value = unit.get("available") if key == "available_date" else unit.get(key)
    return None if value is None else {"value": value, "status": "verified"}


def _home_value(units: list[dict], constraint: dict) -> str:
    if constraint.get("field") == "price":
        low = min(min(u.get("net_rent") or u["rent"], u["rent"]) for u in units)
        return f"From ${low:,.0f}/mo ({len(units)} homes)"
    return f"None of {len(units)} homes"


def unit_verdict(units: list[dict], constraints: list[dict]) -> tuple[list[str], list[dict], list[str]]:
    """(ids of the homes that meet every one of `constraints`, violations,
    unconfirmed field keys). A building breaks a limit only when every home
    breaks one; a limit every home breaks is named, otherwise the violation
    is that no home meets them all together."""
    verdicts = [[check(c, unit_entry(u, c.get("field"))) for c in constraints] for u in units]
    fits = [str(u.get("id")) for u, v in zip(units, verdicts) if all(x == "ok" for x in v)]
    if fits:
        return fits, [], []
    if verdicts and all("violates" in v for v in verdicts):
        named = [c for i, c in enumerate(constraints) if all(v[i] == "violates" for v in verdicts)]
        if named:
            return [], [{"field": c.get("field"), "rule": describe(c), "value": _home_value(units, c)}
                        for c in named], []
        return [], [{"field": "units", "rule": "No home here meets every limit at once: "
                     + "; ".join(describe(c) for c in constraints), "value": f"{len(units)} homes"}], []
    # Homes not ruled out, each with something that can't be confirmed.
    unsure = [c.get("field") for i, c in enumerate(constraints)
              if any(v[i] == "unknown" for v in verdicts if "violates" not in v)]
    return [], [], list(dict.fromkeys(unsure))


def _assess(item: dict, constraints: list[dict]) -> tuple[int, list[dict], list[str], list[str] | None]:
    units = [u for u in item.get("units") or [] if isinstance(u, dict)]
    per_home = [c for c in constraints if units and c.get("field") in UNIT_FIELDS]
    violations, unconfirmed = [], []
    for constraint in constraints:
        if constraint in per_home:
            continue
        verdict = check(constraint, (item.get("fields") or {}).get(constraint.get("field")))
        if verdict == "violates":
            violations.append({"field": constraint.get("field"), "rule": describe(constraint),
                               "value": ((item.get("fields") or {}).get(constraint.get("field")) or {}).get("display")})
        elif verdict == "unknown" and constraint.get("field") not in unconfirmed:
            unconfirmed.append(constraint.get("field"))
    fits = None
    if units:
        fits, home_violations, home_unsure = unit_verdict(units, per_home)
        violations += home_violations
        unconfirmed += [f for f in home_unsure if f not in unconfirmed]
    if violations:
        return HIDDEN, violations, unconfirmed, fits
    return (UNCONFIRMED if unconfirmed else OK), violations, unconfirmed, fits


def assess(item: dict, constraints: list[dict]) -> tuple[int, list[dict], list[str]]:
    """(band, violations, unconfirmed field keys) before the person's own say."""
    return _assess(item, constraints)[:3]


def rank(items: list[dict], plan: dict) -> list[Ranked]:
    """Every item ranked. `items`: `{id, fields, status, fit_score, user_state}`
    (and a building's `units`) in the order found (ties keep it)."""
    constraints = [c for c in plan.get("constraints") or [] if isinstance(c, dict)]
    prefs = [p for p in plan.get("preferences") or [] if isinstance(p, dict) and (p.get("weight") or 0) > 0]
    fit_weight = float(plan.get("fit_weight") if plan.get("fit_weight") is not None else 0.3)
    scaled = [(_scaled(items, p), float(p["weight"])) for p in prefs]
    total = sum(w for _, w in scaled) + fit_weight
    rows = []
    for order, item in enumerate(items):
        key = str(item["id"])
        band, violations, unconfirmed, fits = _assess(item, constraints)
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
        explain = {"band": band, "flags": flags, "violations": violations, "score": score,
                   "parts": parts, "fit": fit}
        if fits is not None:
            explain["units_fit"] = fits  # the homes that meet every per-home limit
        rows.append((band, -score, -(fit if isinstance(fit, (int, float)) else -1), order, key, score, explain))
    rows.sort(key=lambda r: r[:4])
    return [Ranked(item_id=r[4], rank=i + 1, band=r[0], score=r[5], explain=r[6]) for i, r in enumerate(rows)]
