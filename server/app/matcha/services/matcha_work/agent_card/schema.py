"""The agent-card result shape and its deterministic provenance gate.

The model hands back `agent_result.v1` through the `finish` tool. Nothing it
wrote reaches the user until `normalize_result` has:
  * coerced every field to its type and bound (strings trimmed, lists capped);
  * dropped every link, review, rating and price whose URL is not in the
    run's provenance set — the URLs the provider's web search cited or
    returned, plus the pages `fetch_page` actually loaded.

So the model can summarise and rank, but it cannot mint a buy link, a review
quote's source or a rating the run never saw.

Flight results work the same way with offers instead of URLs: the model names
offers by id and `_flights` rebuilds each one (price, times, flights, bags,
warnings) from the run's `FlightSession`, dropping any id it never returned.
"""
from __future__ import annotations

import re
from typing import Any
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit

from .flights import privacy_disclosure

SCHEMA_VERSION = "agent_result.v1"

MAX_ALTERNATIVES = 4
MAX_WHY = 5
MAX_REVIEWS = 4
MAX_IMAGES_PER_PICK = 3
MAX_BUY_LINKS = 3
MAX_SECTIONS = 6
MAX_SOURCES = 12
MAX_CRITERIA = 6
MAX_CAVEATS = 5
_CONFIDENCE = {"high", "medium", "low"}
_SENTIMENT = {"pos", "neg", "mixed"}
_ANSWER_TYPES = {"recommendation", "answer", "flights"}
MAX_FLIGHT_OPTIONS = 5
FLIGHT_LABELS = {"Cheapest", "Best value", "Fastest", "Fewest stops", "Most flexible"}
_TRACKING_PARAMS = {"gclid", "fbclid", "mc_cid", "mc_eid", "ref_", "srsltid"}


def _s(desc: str = "") -> dict:
    return {"type": "string", **({"description": desc} if desc else {})}


def _n(desc: str = "") -> dict:
    return {"type": ["number", "null"], **({"description": desc} if desc else {})}


_URL = _s("An exact URL returned by web search or loaded with fetch_page")

_PICK = {
    "type": "object",
    "properties": {
        "name": _s("Product / option name"),
        "brand": _s(),
        "why": {"type": "array", "items": _s(), "description": "Up to 5 short reasons"},
        "price": {
            "type": ["object", "null"],
            "properties": {"amount": _n(), "currency": _s("ISO code, e.g. USD"), "source_url": _URL},
        },
        "rating": {
            "type": ["object", "null"],
            "properties": {
                "value": _n(), "scale": _n("Usually 5"),
                "count": {"type": ["integer", "null"]}, "source_url": _URL,
            },
        },
        "reviews": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "quote": _s("Verbatim excerpt, at most 280 characters"),
                    "source_name": _s(), "url": _URL,
                    "sentiment": {"type": "string", "enum": sorted(_SENTIMENT)},
                },
            },
        },
        "images": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "source_url": _s("Direct image URL seen on a fetched page (og:image / JSON-LD image)"),
                    "page_url": _URL, "alt": _s(),
                },
            },
        },
        "buy_links": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {"retailer": _s(), "url": _URL, "price": _n()},
            },
        },
    },
    "required": ["name"],
}

RESULT_SCHEMA: dict[str, Any] = {
    "type": "object",
    "properties": {
        "headline": _s("One line answer"),
        "summary": _s("2-4 sentences"),
        "answer_type": {"type": "string", "enum": sorted(_ANSWER_TYPES)},
        "criteria": {
            "type": "array",
            "items": {"type": "object", "properties": {"name": _s(), "why": _s()}},
        },
        "top_pick": {**_PICK, "type": ["object", "null"]},
        "alternatives": {"type": "array", "items": _PICK},
        "sections": {
            "type": "array",
            "items": {"type": "object", "properties": {"heading": _s(), "body_md": _s()}},
        },
        "caveats": {"type": "array", "items": _s()},
        "sources": {
            "type": "array",
            "items": {"type": "object", "properties": {"title": _s(), "url": _URL}},
        },
        "confidence": {"type": "string", "enum": sorted(_CONFIDENCE)},
        "changes_from_previous": {"type": ["string", "null"]},
        "flights": {
            "type": ["object", "null"],
            "description": "Only with answer_type flights: the offers you chose from search_flights",
            "properties": {
                "query_summary": _s("The trip searched, in a few words"),
                "options": {
                    "type": "array",
                    "items": {
                        "type": "object",
                        "properties": {
                            "offer_id": _s("An offer_id search_flights returned"),
                            "label": {"type": "string", "enum": sorted(FLIGHT_LABELS)},
                            "why": {"type": "array", "items": _s(), "description": "1-3 short reasons"},
                        },
                        "required": ["offer_id"],
                    },
                },
            },
        },
    },
    "required": ["headline", "summary", "answer_type", "confidence"],
}


def normalize_url(url: Any) -> str | None:
    """Canonical comparison form: http(s) only, lowercase host, no fragment,
    no `www.`, no tracking params, no trailing slash. None when not a URL."""
    if not isinstance(url, str):
        return None
    try:
        parts = urlsplit(url.strip())
    except ValueError:
        return None
    if parts.scheme.lower() not in ("http", "https") or not parts.hostname:
        return None
    host = parts.hostname.lower()
    host = host.removeprefix("www.")
    query = urlencode([
        (k, v) for k, v in parse_qsl(parts.query, keep_blank_values=True)
        if not k.lower().startswith("utm_") and k.lower() not in _TRACKING_PARAMS
    ])
    path = parts.path.rstrip("/") or ""
    return urlunsplit(("https", host, path, query, ""))


def _is_http_url(url: Any) -> bool:
    return normalize_url(url) is not None


def _text(value: Any, limit: int) -> str:
    return str(value or "").strip()[:limit] if value is not None else ""


def _num(value: Any) -> float | None:
    if isinstance(value, bool):
        return None
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None
    return number if number == number and abs(number) < 1e9 else None


def _list(value: Any) -> list:
    return value if isinstance(value, list) else []


class _Gate:
    def __init__(self, provenance: set[str]) -> None:
        self.allowed = {n for n in (normalize_url(u) for u in provenance) if n}
        self.warnings: list[str] = []

    def ok(self, url: Any, what: str) -> bool:
        normalized = normalize_url(url)
        if normalized is None:
            self.warnings.append(f"Dropped {what}: not an http(s) URL")
            return False
        if normalized not in self.allowed:
            self.warnings.append(f"Dropped {what}: {str(url)[:120]} was never seen by this run")
            return False
        return True


# ── section Markdown ────────────────────────────────────────────────────────
# `sections[].body_md` is the one free-form field both clients render as live
# Markdown, so it is the one place a model (or a page it was steered by) could
# mint a link or an image the provenance gate never saw. Everything that can
# navigate or load a resource is removed unless its URL is verified.
_MD_IMAGE = re.compile(r"!\[[^\]]*\](?:\((?:[^()]|\([^()]*\))*\)|\[[^\]]*\])")
_MD_INLINE_LINK = re.compile(
    # The URL may hold one level of balanced parens (`javascript:alert(1)`), so
    # a hostile link can't leave a stray `)` behind that reads as a fragment.
    r"\[([^\]]*)\]\(\s*<?((?:[^()\s>]|\([^()\s]*\))*)>?(?:\s+(?:\"[^\"]*\"|'[^']*'))?\s*\)"
)
_MD_REF_LINK = re.compile(r"\[([^\]]+)\]\[[^\]]*\]")
_MD_REF_DEF = re.compile(r"^[ \t]{0,3}\[[^\]]+\]:[ \t]*\S.*$", re.MULTILINE)
_MD_AUTOLINK = re.compile(r"<([a-zA-Z][a-zA-Z0-9+.\-]*:[^>\s]*)>")
_HTML_TAG = re.compile(r"</?[a-zA-Z!][^>]*>")
_BARE_URL = re.compile(
    r"(?<![(\[<])\b(?:(?:https?|ftp|file)://|(?:javascript|data|vbscript):)[^\s<>()\[\]]+",
    re.IGNORECASE,
)
_URL_TRAILING = ".,;:!?'\"”’"


def sanitize_markdown(text: str, gate: _Gate) -> str:
    """`text` with images, raw HTML, reference links and every link or bare URL
    the run never saw removed. Link text is kept; verified links survive."""
    removed = 0

    def inline_link(match: re.Match) -> str:
        nonlocal removed
        label, url = match.group(1), match.group(2)
        normalized = normalize_url(url)
        if normalized is not None and normalized in gate.allowed:
            return f"[{label}]({url})"
        removed += 1
        return label

    def bare_url(match: re.Match) -> str:
        nonlocal removed
        raw = match.group(0)
        core = raw.rstrip(_URL_TRAILING)
        normalized = normalize_url(core)
        if normalized is not None and normalized in gate.allowed:
            return raw
        removed += 1
        return ""

    def autolink(match: re.Match) -> str:
        nonlocal removed
        normalized = normalize_url(match.group(1))
        if normalized is not None and normalized in gate.allowed:
            return match.group(1)
        removed += 1
        return ""

    out = _MD_IMAGE.sub(lambda _m: "", text)
    out = _MD_INLINE_LINK.sub(inline_link, out)
    out = _MD_REF_DEF.sub("", out)
    out = _MD_REF_LINK.sub(lambda m: m.group(1), out)
    out = _MD_AUTOLINK.sub(autolink, out)
    out = _HTML_TAG.sub("", out)
    out = _BARE_URL.sub(bare_url, out)
    if out != text:
        gate.warnings.append(
            f"Removed {removed} unverified link(s) or embedded content from a section"
            if removed else "Removed images or markup from a section"
        )
    return out.strip()


def _sections(raw: Any, gate: _Gate) -> list[dict]:
    sections = []
    for section in _list(raw):
        if not isinstance(section, dict):
            continue
        body = sanitize_markdown(_text(section.get("body_md"), 4000), gate)
        if body:
            sections.append({"heading": _text(section.get("heading"), 120), "body_md": body})
    return sections[:MAX_SECTIONS]


def _pick(raw: Any, gate: _Gate) -> dict | None:
    if not isinstance(raw, dict):
        return None
    name = _text(raw.get("name"), 160)
    if not name:
        gate.warnings.append("Dropped a pick with no name")
        return None
    price = None
    if isinstance(raw.get("price"), dict):
        p = raw["price"]
        amount = _num(p.get("amount"))
        if amount is not None and gate.ok(p.get("source_url"), f"price for {name}"):
            price = {
                "amount": round(amount, 2),
                "currency": _text(p.get("currency"), 8).upper() or "USD",
                "source_url": str(p["source_url"]).strip(),
            }
    rating = None
    if isinstance(raw.get("rating"), dict):
        r = raw["rating"]
        value, scale = _num(r.get("value")), _num(r.get("scale")) or 5.0
        count = r.get("count")
        if (
            value is not None and 0 <= value <= scale
            and gate.ok(r.get("source_url"), f"rating for {name}")
        ):
            rating = {
                "value": round(value, 2),
                "scale": scale,
                "count": int(count) if isinstance(count, int) and count >= 0 else None,
                "source_url": str(r["source_url"]).strip(),
            }
    reviews = []
    for review in _list(raw.get("reviews")):
        if not isinstance(review, dict):
            continue
        quote = _text(review.get("quote"), 280)
        if quote and gate.ok(review.get("url"), f"review of {name}"):
            sentiment = review.get("sentiment")
            reviews.append({
                "quote": quote,
                "source_name": _text(review.get("source_name"), 80),
                "url": str(review["url"]).strip(),
                "sentiment": sentiment if sentiment in _SENTIMENT else "mixed",
            })
    images = []
    for image in _list(raw.get("images")):
        # Image URLs are not provenance-gated (og:image lives on a CDN host the
        # page never linked as a source); the PAGE they came from is, and the
        # bytes are refetched through the SSRF guard and re-encoded before use.
        if (
            isinstance(image, dict)
            and _is_http_url(image.get("source_url"))
            and gate.ok(image.get("page_url"), f"image page for {name}")
        ):
            images.append({
                "source_url": str(image["source_url"]).strip(),
                "page_url": str(image["page_url"]).strip(),
                "alt": _text(image.get("alt"), 160) or name,
            })
    buy_links = []
    for link in _list(raw.get("buy_links")):
        if isinstance(link, dict) and gate.ok(link.get("url"), f"buy link for {name}"):
            buy_links.append({
                "retailer": _text(link.get("retailer"), 60) or (urlsplit(str(link["url"])).hostname or ""),
                "url": str(link["url"]).strip(),
                "price": _num(link.get("price")),
            })
    return {
        "name": name,
        "brand": _text(raw.get("brand"), 80),
        "why": [w for w in (_text(x, 240) for x in _list(raw.get("why"))) if w][:MAX_WHY],
        "price": price,
        "rating": rating,
        "reviews": reviews[:MAX_REVIEWS],
        "images": images[:MAX_IMAGES_PER_PICK],
        "buy_links": buy_links[:MAX_BUY_LINKS],
    }


def _sources(raw: Any, gate: _Gate) -> list[dict]:
    sources = []
    seen: set[str] = set()
    for source in _list(raw):
        if not isinstance(source, dict) or not gate.ok(source.get("url"), "source"):
            continue
        key = normalize_url(source["url"])
        if key in seen:
            continue
        seen.add(key)
        sources.append({
            "title": _text(source.get("title"), 160) or (urlsplit(str(source["url"])).hostname or ""),
            "url": str(source["url"]).strip(),
        })
    return sources[:MAX_SOURCES]


def _criteria(raw: Any) -> list[dict]:
    return [
        {"name": _text(c.get("name"), 80), "why": _text(c.get("why"), 240)}
        for c in _list(raw)
        if isinstance(c, dict) and _text(c.get("name"), 80)
    ][:MAX_CRITERIA]


# The gates, by their public names, for the agent runtime's result blocks.
Gate = _Gate
gate_pick = _pick
gate_sections = _sections
gate_sources = _sources
gate_criteria = _criteria


def _flights(raw: Any, session: Any, gate: _Gate) -> dict | None:
    """The chosen flight offers, each rebuilt from the run's own search data.
    None when no chosen offer survives."""
    if not isinstance(raw, dict):
        return None
    options: list[dict] = []
    seen: set[str] = set()
    for item in _list(raw.get("options")):
        if not isinstance(item, dict):
            continue
        offer_id = _text(item.get("offer_id"), 200)
        option = session.option(offer_id) if offer_id else None
        if option is None:
            gate.warnings.append(f"Dropped flight option {offer_id[:60] or '(no id)'}: not an offer this run's search returned")
            continue
        if offer_id in seen:
            continue
        seen.add(offer_id)
        label = item.get("label")
        options.append({
            **option,
            "label": label if label in FLIGHT_LABELS else None,
            "why": [w for w in (_text(x, 240) for x in _list(item.get("why"))) if w][:3],
        })
    if not options:
        return None
    if len(options) > MAX_FLIGHT_OPTIONS:
        gate.warnings.append(f"Trimmed flight options to {MAX_FLIGHT_OPTIONS}")
    return {
        "query_summary": _text(raw.get("query_summary"), 200) or session.query_summary or "",
        "options": options[:MAX_FLIGHT_OPTIONS],
        "searched_at": session.searched_at,
        "test_data": bool(session.test_data),
        "privacy": privacy_disclosure(),
    }


gate_flights = _flights


def normalize_result(raw: Any, provenance: set[str], *, flights: Any = None) -> tuple[dict, list[str]]:
    """Coerce and provenance-gate a `finish` payload.

    Raises ValueError when the payload is unusable (not an object, or missing
    the headline/summary every result must carry, or a flights answer with no
    offer this run found) so the loop can ask once for a repair. Everything
    else degrades by dropping, recorded in warnings.

    `flights` is the run's `FlightSession` when `search_flights` was offered.
    """
    if not isinstance(raw, dict):
        raise ValueError("finish.result must be an object")
    headline = _text(raw.get("headline"), 200)
    summary = _text(raw.get("summary"), 1200)
    if not headline or not summary:
        raise ValueError("headline and summary are required")
    gate = _Gate(provenance)

    top_pick = _pick(raw.get("top_pick"), gate) if raw.get("top_pick") else None
    alternatives = [p for p in (_pick(a, gate) for a in _list(raw.get("alternatives"))) if p]
    if len(alternatives) > MAX_ALTERNATIVES:
        gate.warnings.append(f"Trimmed alternatives to {MAX_ALTERNATIVES}")
    sources = _sources(raw.get("sources"), gate)
    answer_type = raw.get("answer_type")
    flight_block = _flights(raw.get("flights"), flights, gate) if flights is not None else None
    if flight_block is not None:
        # A flight answer is never a product pick, so it never reaches the
        # "want me to buy it?" flow (`chat_flow.purchase_offer`).
        answer_type = "flights"
        if top_pick or alternatives:
            gate.warnings.append("Dropped product picks from a flight result")
        top_pick, alternatives = None, []
    elif answer_type == "flights":
        if flights is not None:
            raise ValueError("answer_type flights needs flights.options with offer_ids from search_flights")
        answer_type = "answer"
    if answer_type not in _ANSWER_TYPES:
        answer_type = "recommendation" if top_pick else "answer"
    confidence = raw.get("confidence")
    result = {
        "schema": SCHEMA_VERSION,
        "headline": headline,
        "summary": summary,
        "answer_type": answer_type,
        "criteria": _criteria(raw.get("criteria")),
        "top_pick": top_pick,
        "alternatives": alternatives[:MAX_ALTERNATIVES],
        "sections": _sections(raw.get("sections"), gate),
        "caveats": [c for c in (_text(x, 300) for x in _list(raw.get("caveats"))) if c][:MAX_CAVEATS],
        "sources": sources,
        "confidence": confidence if confidence in _CONFIDENCE else "low",
        "changes_from_previous": _text(raw.get("changes_from_previous"), 800) or None,
    }
    if flight_block is not None:
        result["flights"] = flight_block
    return result, gate.warnings
