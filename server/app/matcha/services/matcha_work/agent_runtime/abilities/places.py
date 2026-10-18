"""Businesses in an area, from Google Maps: `find_places`, and the `places` list.

"Cafes in LA", "dentists in Austin", "gyms near Union Square". A web search
answers those with listicles and review sites the page loader can't read, so
a run used to spend its searches and page loads to come back with a dozen
names and no phone numbers. Google Maps answers with the businesses
themselves: name, kind, rating, address, phone and website, as data.

The provider is research tasks' (`agent_tasks/research/providers.py`,
`choose_provider("places")`): Google's Places API (New) Text Search with
`GOOGLE_MAPS_API_KEY`, else SearchAPI, else SerpApi, by `search_apis`' rules.
Only the query text leaves the server, as with `web_search`, so nothing needs
switching on. Every page is a paid call (Google's Enterprise Text Search SKU,
recorded in the usage ledger), held to `MAX_PAID` a run.

A run keeps every place it found, deduped by Google's place id (else name and
address), under a short id (P1, P2…). The model sees compact rows to choose
from; the `places` block is rebuilt from what the run found, by id, so a
name, phone or address in the list is always Google's, never the model's
restatement. A run that found a list and left the block out gets it anyway
(`auto_blocks`), when the run built a list: more than one page across its
searches. A one-page lookup ("the phone number for Woodcat Coffee") answered
without the block is left that way. Each place's website and Maps link are
run provenance, so a place can be saved as a sales prospect with its source.
"""
from __future__ import annotations

import logging
import re
from dataclasses import dataclass, field
from typing import Any
from urllib.parse import quote_plus

from app.matcha.services.matcha_work.search_apis import ProviderError

from ..context import RunContext, RunState
from ..registry import Ability, AgentTool, ToolOutput

logger = logging.getLogger(__name__)

KEY = "places"
# Google answers at most three pages of 20 for one query.
MAX_PAGES = 3
# find_places calls a run, and paid pages across them (a page is one call).
MAX_CALLS = 8
MAX_PAID = 18
# Rows in the `places` block (and the CSV the app makes from it): all a run
# can find, so a list is never cut short of what the answer says it holds.
MAX_BLOCK = MAX_PAID * 20
# Rows from one call that always reach the model, whatever the output budget.
MIN_ROWS = 10
TOOL_SECONDS = 60.0
# A run that built a list (more than one page) of at least this many and
# left it out still shows it.
AUTO_BLOCK_AT = 3


@dataclass
class PlacesSession:
    places: dict[str, dict] = field(default_factory=dict)  # short id -> place row, in found order
    keys: dict[str, str] = field(default_factory=dict)  # dedupe key -> short id
    paid: int = 0


def session_of(state: RunState) -> PlacesSession:
    return state.sessions[KEY]


def _provider() -> Any:
    """The places APIs with keys, in order; None with none. Tests patch this seam."""
    from app.matcha.services.matcha_work.agent_tasks.research.providers import choose_provider

    return choose_provider("places")


def _ready() -> bool:
    try:
        return _provider() is not None
    except Exception:  # settings not loaded (a bare script): not offered
        return False


def _value(item: Any, key: str) -> Any:
    entry = (getattr(item, "fields", None) or {}).get(key)
    return entry.get("value") if isinstance(entry, dict) else None


def _norm(text: Any) -> str:
    return re.sub(r"[^a-z0-9]+", " ", str(text or "").lower()).strip()


def maps_url(name: str, place_id: str | None) -> str | None:
    if not place_id:
        return None
    return (f"https://www.google.com/maps/search/?api=1&query={quote_plus(name)}"
            f"&query_place_id={quote_plus(place_id)}")


def place_row(item: Any, query: str) -> dict | None:
    """One provider place as the run keeps it; None without a name or a link."""
    from app.matcha.services.matcha_work.agent_tasks.research.providers import is_google

    name = " ".join(str(getattr(item, "title", "") or "").split())[:200]
    if not name:
        return None
    place_id = getattr(item, "provider_id", None) or None
    website = item.url if isinstance(item.url, str) and item.url and not is_google(item.url) else None
    maps = maps_url(name, place_id)
    if not website and not maps:
        return None
    rating = _value(item, "rating")
    reviews = _value(item, "review_count")
    point = getattr(item, "point", None)
    return {
        "name": name,
        "category": _value(item, "cuisine"),
        "rating": float(rating) if isinstance(rating, (int, float)) else None,
        "reviews": int(reviews) if isinstance(reviews, (int, float)) else None,
        "price": _value(item, "price_level"),
        "address": _value(item, "address") or getattr(item, "subtitle", None) or None,
        "phone": _value(item, "phone"),
        "website": website,
        "maps_url": maps,
        "hours": _value(item, "hours"),
        "lat": point[0] if point else None,
        "lng": point[1] if point else None,
        "place_id": place_id,
        "query": query,
    }


def dedupe_key(row: dict) -> str:
    if row.get("place_id"):
        return f"id:{row['place_id']}"
    return f"na:{_norm(row['name'])}|{_norm(row.get('address'))[:60]}"


def model_line(short_id: str, row: dict) -> str:
    """A place as one compact line for the model: what it needs to choose and cite."""
    parts = [short_id, row["name"]]
    if row.get("category"):
        parts.append(row["category"])
    if row.get("rating") is not None:
        rated = f"{row['rating']:.1f}★"
        if row.get("reviews") is not None:
            rated += f" {row['reviews']:,} reviews"
        parts.append(rated)
    if row.get("price"):
        parts.append(str(row["price"]))
    if row.get("address"):
        parts.append(str(row["address"]))
    if row.get("phone"):
        parts.append(str(row["phone"]))
    parts.append(row.get("website") or "no website")
    return " | ".join(parts)


def fit_lines(lines: list[str], budget: int, min_rows: int = MIN_ROWS) -> tuple[list[str], int]:
    """As many lines as fit `budget` characters (never fewer than `min_rows`),
    and how many were left out. `find_jobs` fits its list the same way."""
    kept, used = [], 0
    for line in lines:
        if len(kept) >= min_rows and used + len(line) + 4 > budget:
            break
        kept.append(line)
        used += len(line) + 4
    return kept, len(lines) - len(kept)


async def _find(ctx: RunContext, state: RunState, args: dict, _left: float) -> ToolOutput:
    session = session_of(state)
    query = " ".join(str(args.get("query") or "").split())[:200]
    if not query:
        return ToolOutput(payload={"error": "Say what to look for and where, e.g. coffee shops in Silver Lake, Los Angeles."},
                          status="error")
    if session.paid >= MAX_PAID:
        return ToolOutput(payload={"error": "Place search budget used up; finish with what you have."},
                          label="Place search budget exhausted")
    try:
        pages = int(args.get("pages") or 1)
    except (TypeError, ValueError):
        pages = 1
    pages = max(1, min(MAX_PAGES, pages, MAX_PAID - session.paid))
    provider = _provider()
    if provider is None:
        return ToolOutput(payload={"error": "Place search isn't set up on this server. Use web_search instead."},
                          status="error")
    # Counted before the call: a page that left may be billed even if no answer came back.
    session.paid += pages
    await ctx.progress.note(f"Searching Google Maps: {query[:60]}…")
    try:
        items = await provider.search_pages("places", query, pages=pages)
    except ProviderError as exc:
        logger.info("find_places failed: %s", exc)
        return ToolOutput(payload={"error": "Place search is unavailable right now. Try web_search instead."},
                          status="error", audit={"query": query, "pages": pages, "error": str(exc)[:200]})
    new: list[tuple[str, dict]] = []
    repeats = 0
    provenance: set[str] = set()
    for item in items:
        row = place_row(item, query)
        if row is None:
            continue
        provenance.update(u for u in (row["website"], row["maps_url"]) if u)
        key = dedupe_key(row)
        if key in session.keys:
            repeats += 1
            continue
        short_id = f"P{len(session.places) + 1}"
        session.keys[key] = short_id
        session.places[short_id] = row
        new.append((short_id, row))
    lines, hidden = fit_lines([model_line(i, r) for i, r in new], max(2000, ctx.limits.max_tool_output_chars - 1200))
    payload: dict[str, Any] = {
        "query": query,
        "new_places": len(new),
        "already_found": repeats,
        "found_in_this_run": len(session.places),
        "places": lines,
    }
    if hidden:
        payload["not_shown_here"] = (f"{hidden} more were found and kept; the places block shows them "
                                     "(leave place_ids empty to show everything).")
    if not new and not repeats:
        payload["note"] = "Nothing found. Try a broader area or other words for the kind of business."
    return ToolOutput(
        payload=payload,
        provenance=frozenset(provenance),
        label=f"Searched Google Maps: {query[:100]} ({len(new)} new)",
        audit={"query": query, "pages": pages, "found": len(items), "new": len(new), "repeats": repeats},
    )


FIND_PLACES = AgentTool(
    name="find_places",
    effect="read",
    description=(
        "Search Google Maps for businesses or places in an area. Returns each one's name, kind, rating and "
        "review count, price level, address, phone and website as listed on Google Maps, under an id (P1, P2…). "
        "Up to 20 a page, 3 pages a query. Places already found in this run are not repeated."
    ),
    parameters={
        "type": "object",
        "properties": {
            "query": {
                "type": "string",
                "description": "What and where, as you'd type it into Google Maps: "
                               "'coffee shops in Silver Lake, Los Angeles'",
            },
            "pages": {
                "type": "integer", "minimum": 1, "maximum": MAX_PAGES,
                "description": "Pages of 20: 3 when building a list, 1 to look up a few places",
            },
        },
        "required": ["query"],
        "additionalProperties": False,
    },
    step_kind="search",
    handler=_find,
    max_calls=MAX_CALLS,
    timeout_seconds=TOOL_SECONDS,
    # Pages are paid for and places deduped before or without an await.
    concurrent=True,
    describe=lambda args: f"Searched Google Maps: {' '.join(str(args.get('query') or '').split())[:100]}",
    exhausted_label="Place search budget exhausted",
    exhausted_message="Place search budget used up; finish with what you have.",
    timeout_message="Google Maps took too long to answer.",
    untrusted_output=True,
)

_PROMPT = f"""Finding businesses (find_places):
- For businesses or places in an area (cafes in LA, dentists in Austin, gyms near Union Square), use \
find_places, not web_search. It returns Google Maps listings: name, kind, rating, address, phone and website.
- Write the query the way you'd type it into Google Maps: what + where. One query returns at most 60 \
(pages=3). For a big city, split it into neighborhoods or nearby cities and search them in the same turn \
(they run at the same time): "coffee shops in Silver Lake, Los Angeles", "coffee shops in Santa Monica, CA". \
A place found twice is kept once.
- A run pays for at most {MAX_PAID} pages: {MAX_PAID // MAX_PAGES} searches of 3 pages, or more with fewer pages \
each. Pick the areas that matter most, and name the ones you left out.
- Show the list with a `places` block. Leave place_ids empty to show every place found. To drop some \
(chains, closed, off-topic), list them in leave_out_ids rather than listing every place you keep; list \
place_ids only for a short pick (the top 10, those with a website). The person can download it as CSV.
- Load a business's own site with fetch_page only for what Maps doesn't list (an email, the owner, the menu), \
and only for the few that need it.
- Ratings, phones and addresses are Google Maps' as of now. Don't add facts about a place that no tool returned."""

PLACES_BLOCK: dict[str, Any] = {
    "type": "object",
    "description": "A list of businesses find_places found, shown as a table the person can download as CSV.",
    "properties": {
        "title": {"type": "string", "description": "What the list is, e.g. 'Independent coffee shops in LA'"},
        "place_ids": {
            "type": "array", "items": {"type": "string"},
            "description": "Ids find_places returned, in the order to show. Empty: every place found.",
        },
        "leave_out_ids": {
            "type": "array", "items": {"type": "string"},
            "description": "Ids to leave out of the list (chains, closed, off-topic).",
        },
    },
}


def _view(short_id: str, row: dict) -> dict:
    view = {k: row.get(k) for k in ("name", "category", "rating", "reviews", "price", "address", "phone",
                                    "website", "maps_url")}
    return {"id": short_id, **{k: v for k, v in view.items() if v not in (None, "")}}


def _ids(raw: Any) -> list[str]:
    return [str(i or "").strip().upper() for i in raw] if isinstance(raw, list) else []


def chosen_ids(found: dict[str, dict], place_ids: Any, leave_out_ids: Any = None) -> tuple[list[str], int]:
    """The places a list (or a save to a campaign) means: the ids given, in
    order, else every place found; less the ids left out. Also how many of
    the given ids this run never found."""
    given = _ids(place_ids)
    chosen = list(dict.fromkeys(i for i in given if i in found)) if given else list(found)
    left_out = set(_ids(leave_out_ids))
    return [i for i in chosen if i not in left_out], sum(1 for i in given if i not in found)


def _block(session: PlacesSession, ids: Any, title: str, leave_out: Any = None) -> tuple[dict | None, list[str]]:
    chosen, unknown = chosen_ids(session.places, ids, leave_out)
    warnings = [f"Dropped {unknown} place id(s) this run did not find"] if unknown else []
    if len(chosen) > MAX_BLOCK:
        warnings.append(f"Kept the first {MAX_BLOCK} places")
        chosen = chosen[:MAX_BLOCK]
    if not chosen:
        return None, warnings or ["Dropped an empty places block"]
    return {
        "type": "places",
        "title": " ".join(title.split())[:120],
        "places": [_view(i, session.places[i]) for i in chosen],
        "found": len(session.places),
    }, warnings


def gate_block(block_type: str, raw: Any, state: RunState) -> tuple[dict | None, list[str]]:
    session = state.sessions.get(KEY)
    if session is None or not session.places:
        return None, ["Dropped a places block: find_places found nothing in this run"]
    if not isinstance(raw, dict):
        return None, ["Dropped a places block: not an object"]
    return _block(session, raw.get("place_ids"), str(raw.get("title") or ""), raw.get("leave_out_ids"))


def auto_blocks(state: RunState) -> list[dict]:
    """The list a run built, when its answer left it out. A run that looked a
    place or two up (one page) meant to leave it out."""
    session = state.sessions.get(KEY)
    if session is None or session.paid < 2 or len(session.places) < AUTO_BLOCK_AT:
        return []
    block, _ = _block(session, None, "")
    return [block] if block else []


def build() -> Ability:
    return Ability(
        key=KEY,
        label="Places on Google Maps",
        tools=(FIND_PLACES,),
        prompt_block=lambda _ctx: _PROMPT,
        env_ready=_ready,
        session_factory=lambda _ctx: PlacesSession(),
        block_schemas={"places": PLACES_BLOCK},
        gate=gate_block,
        auto_blocks=auto_blocks,
    )
