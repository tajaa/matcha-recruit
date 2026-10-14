"""What each research model phase must hand back, and how it is checked. Pure: no I/O.

The model never writes to the database. Each phase ends with one `finish`
call; its arguments go through a `normalize_*` here, and the phase stores
only what survives. A ValueError gets the model one repair.

  plan      what kind of thing, where to look, which facts matter, the hard
            constraints and the preferences
  discover  candidates, each with a link the run actually saw, and facts that
            each quote the page they came from
  screen    relevant or not, and a 0-5 fit, per finding, by short id
  summary   a headline, a short summary and the top picks with a reason; every
            number in it must be one the findings themselves state
  refine    the person's follow-up as a change to the constraints and
            preferences

Checks that matter:
  * a candidate's link must be one this run's searches or page loads returned
  * a fact's quote must be printed on the page it names (`fields.verify_quote`)
    and must state the value (`fields.supports`); on the candidate's own page
    it is verified, on any other it is only claimed; anything else is dropped
  * a photo must be one a loaded page showed
  * ids must be ones the batch showed
"""
from __future__ import annotations

import re
from datetime import date
from typing import Any

from app.matcha.services.matcha_work.agent_card import schema
from app.matcha.services.matcha_work.agent_runtime import registry

from . import fields as F
from .ranking import OPS

MAX_QUERIES = 8
MAX_FIELDS = 8
MAX_CONSTRAINTS = 8
MAX_PREFERENCES = 6
MAX_CANDIDATES = 20
MAX_FACTS = 10
SOURCES = ("shopping", "places", "web")
ITEM_KINDS = ("product", "place", "listing", "offer", "other")
DEFAULT_FIELDS = {
    "product": ("price", "rating", "review_count", "seller"),
    "place": ("rating", "review_count", "price_level", "address", "hours"),
    "listing": ("price", "beds", "baths", "sqft", "pets", "available_date", "neighborhood"),
    "offer": ("price",),
    "other": ("price",),
}
_OPS_FOR = {
    "money": ("lte", "gte", "eq"), "number": ("lte", "gte", "eq"), "rating": ("lte", "gte", "eq"),
    "tags": ("includes", "excludes"), "text": ("includes", "excludes"),
    "bool": ("is_true", "is_false"), "date": ("before", "after"),
}
_CONTROL = re.compile(r"[\x00-\x08\x0b\x0c\x0e-\x1f\x7f]")
# Numbers up to this are everywhere ("top 5", "2 baths") and not worth checking.
SMALL_NUMBER = 10


def _text(value: Any, limit: int) -> str:
    return " ".join(_CONTROL.sub(" ", str(value or "")).split())[:limit]


def _finish(label: str, description: str, schema_: dict) -> registry.AgentTool:
    return registry.AgentTool(
        name="finish", effect="finish", description=description,
        parameters={"type": "object", "properties": {"result": schema_}, "required": ["result"]},
        step_kind="finish", describe=lambda _args: label,
    )


def _result(args: dict) -> dict:
    result = args.get("result") if isinstance(args, dict) else None
    if not isinstance(result, dict):
        raise ValueError("`result` must be an object")
    return result


# ── constraints and preferences ──────────────────────────────────────────────

_FIELD_ENUM = sorted(F.LIBRARY)
CONSTRAINT_SCHEMA = {
    "type": "object",
    "properties": {
        "field": {"type": "string", "enum": _FIELD_ENUM},
        "op": {"type": "string", "enum": list(OPS)},
        "value": {"description": "A number, a date (YYYY-MM-DD), a word, or a list of tag values",
                  "type": ["number", "string", "boolean", "array", "null"], "items": {"type": "string"}},
        "unit": {"type": ["string", "null"], "description": "For a price: month, night, week, year or null"},
    },
    "required": ["field", "op", "value", "unit"],
}
PREFERENCE_SCHEMA = {
    "type": "object",
    "properties": {
        "field": {"type": "string", "enum": _FIELD_ENUM},
        "weight": {"type": "number", "description": "0-1: how much it matters"},
        "higher_is_better": {"type": ["boolean", "null"]},
    },
    "required": ["field", "weight", "higher_is_better"],
}


def clean_constraint(raw: Any, *, today: date) -> dict | None:
    if not isinstance(raw, dict):
        return None
    spec = F.LIBRARY.get(str(raw.get("field") or ""))
    op = raw.get("op")
    if spec is None or op not in _OPS_FOR[spec.type]:
        return None
    value = raw.get("value")
    if spec.type in ("money", "number", "rating"):
        value = F.coerce(spec, value, today=today)
    elif spec.type == "tags":
        value = F.tags_in(spec.key, value) or None
    elif spec.type == "date":
        value = F.coerce(spec, value, today=today)
    elif spec.type == "text":
        value = _text(value, 60) or None
    else:
        value = True
    if value is None:
        return None
    out = {"field": spec.key, "op": op, "value": value}
    if spec.type == "money":
        unit = F.unit_of(raw.get("unit"))
        if unit:
            out["unit"] = unit
        if raw.get("currency"):
            out["currency"] = str(raw["currency"]).upper()[:3]
    return out


def clean_preference(raw: Any) -> dict | None:
    if not isinstance(raw, dict):
        return None
    spec = F.LIBRARY.get(str(raw.get("field") or ""))
    weight = raw.get("weight")
    if spec is None or spec.type == "text" or isinstance(weight, bool) or not isinstance(weight, (int, float)):
        return None
    out = {"field": spec.key, "weight": round(max(0.0, min(1.0, float(weight))), 3)}
    if isinstance(raw.get("higher_is_better"), bool):
        out["higher_is_better"] = raw["higher_is_better"]
    return out if out["weight"] > 0 else None


def _unique(items: list[dict], key) -> list[dict]:
    seen, out = set(), []
    for item in items:
        k = key(item)
        if k not in seen:
            seen.add(k)
            out.append(item)
    return out


def brief_constraints(brief: dict, *, item_kind: str, today: date) -> list[dict]:
    """The hard limits the person typed, as constraints. They always win."""
    out = []
    if brief.get("budget_max"):
        constraint = {"field": "price", "op": "lte", "value": float(brief["budget_max"]),
                      "currency": brief.get("currency") or "USD", "source": "brief"}
        if item_kind == "listing":
            constraint["unit"] = "month"
        out.append(constraint)
    if brief.get("needed_by") and item_kind == "listing":
        made = clean_constraint({"field": "available_date", "op": "before", "value": brief["needed_by"]}, today=today)
        if made:
            out.append({**made, "source": "brief"})
    return out


def finalize_plan(plan: dict, brief: dict, *, today: date) -> dict:
    """The person's own limits merged in (replacing the model's on the same
    field and op), every constrained or preferred field shown, caps applied."""
    kind = plan.get("item_kind") if plan.get("item_kind") in ITEM_KINDS else "other"
    typed = brief_constraints(brief, item_kind=kind, today=today)
    taken = {(c["field"], c["op"]) for c in typed}
    constraints = typed + [c for c in plan.get("constraints") or [] if (c["field"], c["op"]) not in taken]
    constraints = _unique(constraints, lambda c: (c["field"], c["op"], str(c["value"])))[:MAX_CONSTRAINTS]
    preferences = _unique(plan.get("preferences") or [], lambda p: p["field"])[:MAX_PREFERENCES]
    shown = list(plan.get("fields") or [])
    for key in [c["field"] for c in constraints] + [p["field"] for p in preferences]:
        if key not in shown:
            shown.append(key)
    if not shown:
        shown = list(DEFAULT_FIELDS[kind])
    location = brief.get("location")
    queries = list(plan.get("queries") or [])
    if location:
        queries = [q if location.casefold() in q.casefold() else f"{q} {location}"[:160] for q in queries]
    return {
        **plan,
        "item_kind": kind,
        "queries": queries[:MAX_QUERIES],
        "fields": shown[:MAX_FIELDS + 2],
        "constraints": constraints,
        "preferences": preferences,
        "must_haves": list(brief.get("must_haves") or []),
        "nice_to_haves": list(brief.get("nice_to_haves") or []),
        "avoid": list(brief.get("avoid") or []),
        "location": location,
    }


# ── plan ─────────────────────────────────────────────────────────────────────

PLAN_SCHEMA = {
    "type": "object",
    "properties": {
        "title": {"type": "string", "description": "A short name for the task, under 60 characters"},
        "item_kind": {"type": "string", "enum": list(ITEM_KINDS)},
        "source": {"type": "string", "enum": list(SOURCES),
                   "description": "shopping for things to buy, places for restaurants/shops/venues, web otherwise"},
        "queries": {"type": "array", "items": {"type": "string"}, "maxItems": MAX_QUERIES},
        "fields": {"type": "array", "items": {"type": "string", "enum": _FIELD_ENUM}, "maxItems": MAX_FIELDS},
        "constraints": {"type": "array", "items": CONSTRAINT_SCHEMA, "maxItems": MAX_CONSTRAINTS},
        "preferences": {"type": "array", "items": PREFERENCE_SCHEMA, "maxItems": MAX_PREFERENCES},
        "fit_weight": {"type": "number", "description": "0-1: how much overall fit counts next to the preferences"},
        "prefer_sources": {"type": "array", "items": {"type": "string"}, "maxItems": 6,
                           "description": "Kinds of sites to read first, e.g. 'the building's own site'"},
        "summary": {"type": "string", "description": "One or two sentences: what a good result is"},
    },
    "required": ["title", "item_kind", "source", "queries", "fields", "constraints", "preferences",
                 "fit_weight", "prefer_sources", "summary"],
}
PLAN_FINISH = _finish("Planned the task", "Finish with the plan.", PLAN_SCHEMA)


def normalize_plan(args: dict, *, brief: dict, today: date) -> tuple[dict, list[str]]:
    result = _result(args)
    warnings = []
    queries = []
    for q in result.get("queries") or []:
        text = _text(q, 160)
        if len(text) >= 2 and text.casefold() not in {x.casefold() for x in queries}:
            queries.append(text)
    if not queries:
        raise ValueError("give at least one query")
    constraints = []
    for raw in result.get("constraints") or []:
        made = clean_constraint(raw, today=today)
        if made:
            constraints.append(made)
        else:
            warnings.append(f"Dropped a constraint it couldn't read: {str(raw)[:80]}")
    fit = result.get("fit_weight")
    plan = {
        "title": _text(result.get("title"), 80),
        "item_kind": result.get("item_kind") if result.get("item_kind") in ITEM_KINDS else "other",
        "source": result.get("source") if result.get("source") in SOURCES else "web",
        "queries": queries,
        "fields": [k for k in dict.fromkeys(result.get("fields") or []) if k in F.LIBRARY][:MAX_FIELDS],
        "constraints": constraints,
        "preferences": [p for p in (clean_preference(r) for r in result.get("preferences") or []) if p],
        "fit_weight": round(max(0.0, min(1.0, float(fit))), 3)
        if isinstance(fit, (int, float)) and not isinstance(fit, bool) else 0.3,
        "prefer_sources": [t for t in (_text(s, 80) for s in result.get("prefer_sources") or []) if t][:6],
        "summary": _text(result.get("summary"), 400),
        "origin": "model",
    }
    return finalize_plan(plan, brief, today=today), warnings


def plan_from_brief(directive: str, brief: dict, *, today: date) -> dict:
    """The plan when the model's plan fails: search the directive as written."""
    query = " ".join(directive.split())[:160]
    plan = {
        "title": query[:60], "item_kind": "other", "source": "web", "queries": [query],
        "fields": [], "constraints": [], "preferences": [], "fit_weight": 0.5,
        "prefer_sources": [], "summary": "", "origin": "fallback",
    }
    return finalize_plan(plan, brief, today=today)


# ── discover ─────────────────────────────────────────────────────────────────

FACT_SCHEMA = {
    "type": "object",
    "properties": {
        "field": {"type": "string", "enum": _FIELD_ENUM},
        "value": {"type": ["number", "string", "boolean", "array"], "items": {"type": "string"}},
        "quote": {"type": "string", "description": "The exact words on the page that state it, copied verbatim"},
        "source_url": {"type": "string", "description": "The page the quote is on: one you loaded"},
    },
    "required": ["field", "value", "quote", "source_url"],
}
DISCOVER_SCHEMA = {
    "type": "object",
    "properties": {
        "candidates": {
            "type": "array", "maxItems": MAX_CANDIDATES,
            "items": {"type": "object", "properties": {
                "title": {"type": "string"},
                "subtitle": {"type": "string", "description": "Where it is, who sells it, in a few words"},
                "url": {"type": "string", "description": "Its own page: a URL search returned or you loaded"},
                "image_url": {"type": ["string", "null"],
                              "description": "An image fetch_page returned for it (og_image or a product image), or null"},
                "facts": {"type": "array", "items": FACT_SCHEMA, "maxItems": MAX_FACTS},
            }, "required": ["title", "subtitle", "url", "image_url", "facts"]},
        },
        "notes": {"type": "string", "description": "What was hard to find, in a sentence"},
    },
    "required": ["candidates", "notes"],
}
DISCOVER_FINISH = _finish("Listed what it found", "Finish with the candidates you found.", DISCOVER_SCHEMA)


def _host(url: str | None) -> str:
    normalized = schema.normalize_url(url) or ""
    return normalized.split("/")[2] if normalized.count("/") >= 2 else ""


def normalize_candidates(
    args: dict, *, plan: dict, citable: set[str], pages: dict[str, str], images: dict[str, str],
    today: date,
) -> tuple[list[dict], list[str]]:
    """Candidates as finding records. `pages`: url -> the text this run loaded
    from it; `images`: image url -> the page it was on."""
    result = _result(args)
    allowed = {schema.normalize_url(u): u for u in citable if schema.normalize_url(u)}
    page_text = {schema.normalize_url(u): text for u, text in pages.items() if schema.normalize_url(u)}
    kind = plan.get("item_kind") if plan.get("item_kind") in ITEM_KINDS else "other"
    out, warnings, seen = [], [], set()
    for raw in result.get("candidates") or []:
        if not isinstance(raw, dict):
            continue
        title = _text(raw.get("title"), 200)
        url = str(raw.get("url") or "").strip()
        key = schema.normalize_url(url)
        if not title or key is None or key not in allowed:
            warnings.append(f"Dropped {title[:60] or 'a candidate'!r}: its link was never seen in this run")
            continue
        if key in seen:
            continue
        seen.add(key)
        facts: dict[str, dict] = {}
        for fact in raw.get("facts") or []:
            made, why = _fact(fact, item_key=key, page_text=page_text, allowed=allowed, today=today)
            if made is None:
                warnings.append(f"{title[:40]}: {why}")
            elif F.better(made[1], facts.get(made[0])):
                facts[made[0]] = made[1]
        image = raw.get("image_url")
        image_candidates = []
        if isinstance(image, str) and image in images:
            image_candidates.append({"source_url": image, "page_url": images[image], "alt": title})
        out.append({
            "kind": kind, "title": title, "subtitle": _text(raw.get("subtitle"), 200), "url": url,
            "origin": "web", "provider": None, "fields": facts, "image_candidates": image_candidates,
        })
    return out, warnings


def _fact(raw: Any, *, item_key: str, page_text: dict[str, str], allowed: dict, today: date):
    if not isinstance(raw, dict):
        return None, "dropped a fact that wasn't an object"
    spec = F.LIBRARY.get(str(raw.get("field") or ""))
    if spec is None:
        return None, "dropped a fact about an unknown field"
    source = schema.normalize_url(str(raw.get("source_url") or ""))
    quote = _text(raw.get("quote"), 300)
    text = page_text.get(source) if source else None
    if source not in allowed or text is None:
        return None, f"dropped {spec.label.lower()}: its page wasn't loaded in this run"
    value = F.coerce(spec, raw.get("value"), today=today)
    if value is None:
        return None, f"dropped {spec.label.lower()}: not a value it can hold"
    if not F.verify_quote(quote, text) or not F.supports(spec, value, quote):
        return None, f"dropped {spec.label.lower()}: the quote isn't on the page or doesn't say that"
    own = source == item_key or _host(source) == _host(item_key)
    made = F.entry(spec, raw.get("value"), status="verified" if own else "claimed", origin="model",
                   today=today, url=allowed[source], quote=quote)
    return (spec.key, made), ""


# ── screen ───────────────────────────────────────────────────────────────────

SCREEN_SCHEMA = {
    "type": "object",
    "properties": {
        "verdicts": {
            "type": "array",
            "items": {"type": "object", "properties": {
                "id": {"type": "string", "description": "The finding's short id, e.g. F3"},
                "relevant": {"type": "boolean"},
                "fit": {"type": "integer", "minimum": 0, "maximum": 5},
                "reasons": {"type": "array", "items": {"type": "string"}, "maxItems": 3},
            }, "required": ["id", "relevant", "fit", "reasons"]},
        },
    },
    "required": ["verdicts"],
}
SCREEN_FINISH = _finish("Screened the findings", "Finish with one verdict per finding shown.", SCREEN_SCHEMA)
SCREEN_MISSING_TOLERANCE = 0.2


def normalize_screen(args: dict, batch: dict[str, str]) -> tuple[dict[str, dict], list[str]]:
    """`batch`: short id -> item id. Returns item id -> verdict."""
    result = _result(args)
    verdicts: dict[str, dict] = {}
    warnings = []
    for item in result.get("verdicts") or []:
        if not isinstance(item, dict):
            continue
        short = str(item.get("id") or "").strip().upper()
        item_id = batch.get(short)
        if item_id is None:
            warnings.append(f"Ignored a verdict for an unknown finding {short[:12]!r}")
            continue
        fit = item.get("fit")
        fit = max(0, min(5, int(fit))) if isinstance(fit, (int, float)) and not isinstance(fit, bool) else None
        verdicts[item_id] = {
            "relevant": bool(item.get("relevant")),
            "fit": fit,
            "reasons": [t for t in (_text(r, 200) for r in item.get("reasons") or []) if t][:3],
        }
    missing = len(batch) - len(verdicts)
    if batch and missing > len(batch) * SCREEN_MISSING_TOLERANCE:
        raise ValueError(f"give a verdict for every finding: {missing} of {len(batch)} are missing")
    return verdicts, warnings


# ── summary ──────────────────────────────────────────────────────────────────

SUMMARY_SCHEMA = {
    "type": "object",
    "properties": {
        "headline": {"type": "string", "description": "One line: what was found"},
        "summary": {"type": "string", "description": "Two to four sentences"},
        "sections": {"type": "array", "maxItems": 4, "items": {"type": "object", "properties": {
            "heading": {"type": "string"}, "body_md": {"type": "string"},
        }, "required": ["heading", "body_md"]}},
        "top": {"type": "array", "maxItems": 5, "items": {"type": "object", "properties": {
            "id": {"type": "string", "description": "A finding's short id, e.g. F1"},
            "why": {"type": "string", "description": "One sentence, using only facts shown for it"},
        }, "required": ["id", "why"]}},
    },
    "required": ["headline", "summary", "sections", "top"],
}
SUMMARY_FINISH = _finish("Summarized", "Finish with the summary.", SUMMARY_SCHEMA)


def unsupported_numbers(text: str, allowed: str) -> list[float]:
    """Numbers in `text` (above SMALL_NUMBER) that `allowed` never states."""
    stated = F.amounts(allowed)
    return [n for n in F.amounts(text) if n > SMALL_NUMBER
            and not any(abs(s - n) <= max(0.5, n * 0.005) for s in stated)]


def normalize_summary(args: dict, *, batch: dict[str, str], item_texts: dict[str, str],
                      citable: set[str]) -> tuple[dict, list[str]]:
    """`batch`: short id -> item id; `item_texts`: item id -> what its fields
    and title say. Every number must come from there."""
    result = _result(args)
    everything = " ".join(item_texts.values())
    warnings: list[str] = []
    headline = _text(result.get("headline"), 160)
    summary = _text(result.get("summary"), 900)
    if not headline:
        raise ValueError("give a headline")
    for name, text in (("headline", headline), ("summary", summary)):
        if unsupported_numbers(text, everything):
            raise ValueError(f"the {name} states a number no finding shows; use only the facts given")
    gate = schema.Gate(citable)
    sections = []
    for section in schema.gate_sections(result.get("sections"), gate):
        if unsupported_numbers(section["body_md"], everything):
            warnings.append(f"Dropped section {section['heading'][:40]!r}: a number no finding shows")
            continue
        sections.append(section)
    warnings.extend(gate.warnings)
    top, seen = [], set()
    for pick in result.get("top") or []:
        if not isinstance(pick, dict):
            continue
        item_id = batch.get(str(pick.get("id") or "").strip().upper())
        if item_id is None or item_id in seen:
            continue
        seen.add(item_id)
        why = _text(pick.get("why"), 300)
        if why and unsupported_numbers(why, item_texts.get(item_id, "")):
            warnings.append("Dropped a reason that stated a number its finding doesn't show")
            why = ""
        top.append({"item_id": item_id, "why": why})
    return {"headline": headline, "summary": summary, "sections": sections, "top": top[:5]}, warnings


# ── refine ───────────────────────────────────────────────────────────────────

REFINE_SCHEMA = {
    "type": "object",
    "properties": {
        "constraints": {"type": "array", "items": CONSTRAINT_SCHEMA, "maxItems": MAX_CONSTRAINTS,
                        "description": "The whole new list of hard limits"},
        "preferences": {"type": "array", "items": PREFERENCE_SCHEMA, "maxItems": MAX_PREFERENCES,
                        "description": "The whole new list of preferences"},
        "fields_add": {"type": "array", "items": {"type": "string", "enum": _FIELD_ENUM}, "maxItems": 4},
        "queries": {"type": "array", "items": {"type": "string"}, "maxItems": MAX_QUERIES,
                    "description": "New queries if a new search is needed, else []"},
        "search_again": {"type": "boolean", "description": "True when what was found can't satisfy the change"},
        "note": {"type": "string", "description": "What changed, in one sentence for the person"},
    },
    "required": ["constraints", "preferences", "fields_add", "queries", "search_again", "note"],
}
REFINE_FINISH = _finish("Read the change", "Finish with the changed plan.", REFINE_SCHEMA)


def normalize_refine(args: dict, *, plan: dict, brief: dict, today: date) -> tuple[dict, list[str]]:
    """The plan after the person's follow-up, plus `search_again` and `note`."""
    result = _result(args)
    constraints = [c for c in (clean_constraint(r, today=today) for r in result.get("constraints") or []) if c]
    # The person may change their own limit ("up to $4,000 now"), but one the
    # model simply left out of its new list stays.
    for kept in [c for c in plan.get("constraints") or [] if c.get("source") == "brief"]:
        if not any(c["field"] == kept["field"] and c["op"] == kept["op"] for c in constraints):
            constraints.insert(0, kept)
    preferences = [p for p in (clean_preference(r) for r in result.get("preferences") or []) if p]
    fields = list(plan.get("fields") or [])
    for key in result.get("fields_add") or []:
        if key in F.LIBRARY and key not in fields:
            fields.append(key)
    queries = [q for q in (_text(q, 160) for q in result.get("queries") or []) if len(q) >= 2]
    changed = {**plan, "constraints": constraints, "preferences": preferences, "fields": fields,
               "queries": queries or plan.get("queries") or []}
    # The brief's limits are already in `constraints` (kept or changed above).
    rest = {k: v for k, v in (brief or {}).items() if k not in ("budget_max", "needed_by")}
    final = finalize_plan(changed, rest, today=today)
    return {"plan": final, "search_again": bool(result.get("search_again")),
            "note": _text(result.get("note"), 240)}, []
