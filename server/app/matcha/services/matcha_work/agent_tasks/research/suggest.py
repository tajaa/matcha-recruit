"""What to suggest when a batch is thin, or a search is too broad to be useful.

Worked out by code from what the round found. A thin batch (fewer than
`batches.BATCH` could be shown) suggests looking wider: the nearest sizeable
places from the offline gazetteer (`job_search.places`), loosening the limit
that hid the most findings (to the lowest figure among those it hid), or
searching more. A broad one (a full batch, many more like it waiting, few
limits) suggests narrowing it. Each option is a follow-up the app can start
as it is: a refine (free) or a more round (a unit). The model only phrases
the question, and its numbers are checked like the summary's.
"""
from __future__ import annotations

import math
from typing import Any

from app.matcha.services.matcha_work.job_search import places as gazetteer

from . import batches
from . import fields as F

BROAD_WAITING = 30
# What a waiting finding lacks, as the question says it: (one, several).
_LACKING = {
    "price": ("has no price", "have no price"),
    "photo": ("has no photo", "have no photo"),
    "contact": ("has no phone number", "have no phone number"),
    batches.OVER_LIMIT: ("is listed over your limit", "are listed over your limit"),
}
NEARBY_MILES = 25.0
# Places smaller than this (square miles) aren't worth naming as somewhere to widen to.
NEARBY_MIN_SQMI = 5.0
MAX_OPTIONS = 3
_SMALL = {"of", "the", "and", "on", "by", "upon"}


def _title(key: str) -> str:
    return " ".join(w if w in _SMALL and n else w.capitalize() for n, w in enumerate(key.split()))


def nearby(location: str | None, n: int = 2) -> list[str]:
    """The `n` places near `location` most worth searching too: large and
    close (area over distance), in the same state, not `location` itself."""
    if not location:
        return []
    where = gazetteer.target(location)
    if where is None or not where.points or where.state is None and not where.name:
        return []
    here = where.points[0]
    own = gazetteer.place_key(location.split(",")[0])
    found: list[tuple[float, str, tuple[float, float]]] = []
    taken: list[tuple[tuple[float, float], str]] = []
    for key, entries in gazetteer._index().items():
        if key == own:
            continue
        for entry in entries:
            if entry.county or entry.sqmi < NEARBY_MIN_SQMI:
                continue
            if where.state and entry.state != where.state:
                continue
            away = gazetteer.miles(here, entry.point)
            if 2.0 <= away <= NEARBY_MILES:
                found.append((entry.sqmi / max(away, 1.0), key, (round(entry.lat, 2), round(entry.lon, 2))))
    found.sort(reverse=True)
    out: list[str] = []
    for _, key, point in found:
        # One name each: the gazetteer can carry a city under two keys ("jersey", "jersey city").
        if len(out) >= n:
            break
        if any(point == p for p, _ in taken):
            continue
        taken.append((point, key))
        out.append(_title(key))
    return out


def _round_up(value: float, step: float) -> float:
    return math.ceil(value / step) * step


def _and(parts: list[str]) -> str:
    return parts[0] if len(parts) == 1 else ", ".join(parts[:-1]) + " and " + parts[-1]


def loosen(plan: dict, hidden_by: dict[str, int], hidden_prices: list[float],
           over_prices: list[float] = ()) -> dict | None:
    """The limit that kept the most findings out, as an option to loosen it:
    those it hid, plus those other sites say cost more than it (`over_prices`)."""
    counts = dict(hidden_by)
    if over_prices:
        counts["price"] = counts.get("price", 0) + len(over_prices)
    if not counts:
        return None
    hidden_prices = [*hidden_prices, *over_prices]
    field, count = max(counts.items(), key=lambda kv: kv[1])
    constraint = next((c for c in plan.get("constraints") or [] if c.get("field") == field), None)
    spec = F.LIBRARY.get(field)
    if constraint is None or spec is None:
        return None
    if field == "price" and constraint.get("op") in ("lte", "between") and hidden_prices:
        cap = constraint["value"][1] if isinstance(constraint.get("value"), list) else constraint.get("value")
        above = sorted(p for p in hidden_prices if isinstance(cap, (int, float)) and p > cap)
        if not above:
            return None
        raised = _round_up(above[0], 100)
        money = F.display(spec, raised, currency=constraint.get("currency"))
        unit = " a month" if constraint.get("unit") == "month" else ""
        return {"label": f"Raise the limit to {money}{unit}", "round": "refine",
                "directive": f"Raise the price limit to {money}{unit}", "hides": count}
    if spec.type == "tags":
        return {"label": f"Drop \"{F.clean_text(_rule(constraint), 60)}\"", "round": "refine",
                "directive": f"{spec.label}: drop that requirement", "hides": count}
    return {"label": f"Loosen \"{F.clean_text(_rule(constraint), 60)}\"", "round": "refine",
            "directive": f"Loosen the {spec.label.lower()} limit", "hides": count}


def _rule(constraint: dict) -> str:
    from .ranking import describe

    return describe(constraint)


def diagnose(*, plan: dict, shown: int, ready_waiting: int, short: dict[str, int], hidden_by: dict[str, int],
             hidden_prices: list[float], waiting_prices: list[float], room: int,
             over_prices: list[float] = (), near: list[str] | None = None) -> dict | None:
    """`shown`: released this round; `ready_waiting`: could be released next;
    `short`: how many waiting lack each requirement (`batches.shortfall`);
    `hidden_by`: findings hidden per limit field; `over_prices`: what other
    sites say the waiting ones over the price limit cost. None when nothing
    needs saying."""
    item_kind = plan.get("item_kind")
    if shown < batches.BATCH:
        facts = []
        lacking = [f"{n} {_LACKING[k][n != 1]}" for k, n in sorted(short.items(), key=lambda kv: -kv[1])
                   if n and k in _LACKING]
        if lacking:
            facts.append("Of the others, " + _and(lacking) + ".")
        if hidden_by:
            field, count = max(hidden_by.items(), key=lambda kv: kv[1])
            facts.append(f"{count} were left out for {F.LIBRARY[field].label.lower() if field in F.LIBRARY else field}.")
        options = []
        places = near if near is not None else nearby(plan.get("location"))
        if places and item_kind in ("listing", "place"):
            both = " and ".join(places)
            options.append({"label": f"Also search {both}", "round": "refine",
                            "directive": f"Also look in {both}"})
        relaxed = loosen(plan, hidden_by, hidden_prices, over_prices)
        if relaxed:
            options.append({k: v for k, v in relaxed.items() if k != "hides"})
        if room > 0:
            options.append({"label": "Keep looking", "round": "more", "directive": ""})
        if not options:
            return None
        text = (f"I could only find {shown} that I can show you with everything you need. "
                if shown else "I couldn't find any I can show you with everything you need yet. ")
        text += " ".join(facts)
        text += " Want me to " + _offer(options[0]) + "?"
        return {"kind": "thin", "text": " ".join(text.split()), "facts": " ".join(facts),
                "options": options[:MAX_OPTIONS]}
    limits = [c for c in plan.get("constraints") or [] if c.get("field") not in F.COMPUTED]
    if ready_waiting >= BROAD_WAITING and len(limits) <= 1:
        options = []
        fields = {c.get("field") for c in limits}
        if "price" not in fields and len(waiting_prices) >= 5:
            middle = sorted(waiting_prices)[len(waiting_prices) // 2]
            money = F.display(F.LIBRARY["price"], _round_up(middle, 100))
            options.append({"label": f"Only under {money}", "round": "refine",
                            "directive": f"Only ones under {money}"})
        if item_kind == "listing" and "beds" not in fields:
            options.append({"label": "Only 1 bedroom or more", "round": "refine",
                            "directive": "Only 1 bedroom or more"})
        if item_kind == "place" and "rating" not in fields:
            options.append({"label": "Only 4.5 stars and up", "round": "refine",
                            "directive": "Only places rated 4.5 or higher"})
        if not options:
            return None
        return {"kind": "broad",
                "text": f"There are {ready_waiting} more like these. Want to narrow it down, say "
                        f"{options[0]['label'][0].lower() + options[0]['label'][1:]}?",
                "facts": f"{ready_waiting} more that fit are waiting.", "options": options[:MAX_OPTIONS]}
    return None


def _offer(option: dict) -> str:
    if option["round"] == "more":
        return "keep looking"
    label = option["label"]
    return label[0].lower() + label[1:]


def numbers_allowed(diagnosis: dict | None) -> str:
    """What the question may state besides the summary's own numbers."""
    if not diagnosis:
        return ""
    return " ".join([diagnosis.get("text") or "", *(o.get("label") or "" for o in diagnosis.get("options") or [])])


def view(diagnosis: dict | None, phrased: Any) -> dict | None:
    """The stored question: the model's phrasing when it gave one, else code's."""
    if not diagnosis:
        return None
    text = phrased if isinstance(phrased, str) and phrased.strip() else diagnosis["text"]
    return {"kind": diagnosis["kind"], "text": " ".join(text.split())[:400], "options": diagnosis["options"]}
