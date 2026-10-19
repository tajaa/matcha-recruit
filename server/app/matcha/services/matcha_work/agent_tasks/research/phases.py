"""The research phases that use no model. Each runs inside one worker task.

  providers  Google Maps (Google's own Places API) for places and homes:
             findings with rating, address and link as provider data.
             Products are found by the model's web search (no Google
             Shopping since 2026-10-18: no search API)
  enrich     each finding's own page: its schema.org data, then (for a home) a
             conservative scan of its text; an apartment building's homes to
             let one by one from the leasing system its site names
             (`units.py`), else its floor plans page for its rents; a page
             that is gone marks the finding unavailable; where it is, from
             the place the person named; photos and floor plans rehosted on
             our CDN, and the page as the browser drew it kept (apart from
             the photos) when viewed
  rank       every finding ordered from stored facts (`ranking.py`)

The model phases (plan, discover, screen, summarize, refine) are in
`model_phases.py`; the order is `PHASES` in `research/__init__.py`.

Paid calls are reserved on the task row before they are made (`chain.grant`)
and only what went unused is given back, so a retried phase never spends a
second budget. Every write checks the task's dispatch token.
"""
from __future__ import annotations

import asyncio
import json
import logging
import re
import time
from dataclasses import dataclass, field, replace
from datetime import date
from typing import Any, Awaitable, Callable
from urllib.parse import urlsplit
from uuid import UUID

from app.core.services.safe_fetch import UnsafeURL, fetch_public
from app.database import connection_or_direct, decode_jsonb
from app.matcha.services.matcha_work.agent_card.page_extract import anchors, extract_page, site_of
from app.matcha.services.matcha_work.agent_card.schema import normalize_url
from app.matcha.services.matcha_work.agent_runtime import chain
from app.matcha.services.matcha_work.agent_runtime.chain import Budget, PhaseOutcome

from .. import items as items_mod
from ..playbook import Budgets
from . import fields as F
from . import batches, geo, kinds, providers, ranking
from . import units as leasing

logger = logging.getLogger(__name__)

BUDGETS = Budgets()
QUERY_CONCURRENCY = 3
# Queries sent to Google Maps a round (it has an area per query, north and south both).
PROVIDER_QUERIES = 6
# Apartment buildings kept from Google Maps a round: each may take
# BUILDING_LOADS page loads, within the round's page loads.
PROVIDER_BUILDINGS = 30
# A building's page loads: its site, its floor plans page, and LEASING_LOADS
# for its leasing system (a unit map is two: its embed page, then its API).
LEASING_LOADS = 2
BUILDING_LOADS = 2 + LEASING_LOADS
LEASING_BYTES = 3_000_000
# Floor plans newly rehosted per building a pass (the plans of homes that meet
# the limits first, then the cheapest homes'), and how long a pass may take:
# an enrich batch's, alongside its photos; a refine's, for homes that fit now.
PLAN_IMAGES = 8
PLAN_IMAGE_SECONDS = 45.0
PLAN_FILL_SECONDS = 30.0
PLAN_IMAGE_CONCURRENCY = 4
ENRICH_BATCH = 12
# Looking up the place distances are measured from, when lookups fail.
ANCHOR_TRIES = 3
ENRICH_CONCURRENCY = 4
# A batch's views run one at a time and none starts after this long, so the
# last one (queued, loaded, screenshot stored: 90 s at most) and the photos
# still end inside the step's 420 s.
ENRICH_VIEW_SECONDS = 150.0
PAGE_BYTES = 2_000_000
PAGE_SECONDS = 20.0
# Below this much text with no schema.org data, a page is drawn by JavaScript.
THIN_PAGE_CHARS = 400
ENRICH_IMAGES_PER_BATCH = 12
IMAGE_SECONDS = 60.0
# Pages that are a search engine's, never the finding's own: any google.<tld>,
# and these.
NOT_OWN_PAGE = ("gstatic.com", "bing.com", "duckduckgo.com")
_GONE = re.compile(
    r"\b(?:no longer available|listing (?:has been |was )?(?:removed|deleted|expired)|"
    r"this (?:listing|posting|ad) (?:has been |was )?(?:removed|deleted|expired)|"
    r"posting has been deleted|no longer accepting|property is off the market)\b",
    re.I,
)
# Phase names, as the chain stores them (`<playbook>.<phase>`).
PROVIDERS, DISCOVER, ENRICH, SCREEN, RANK, FILL, SUMMARIZE = (
    f"research.{name}" for name in ("providers", "discover", "enrich", "screen", "rank", "fill", "summarize")
)


def _default_client(model: str) -> Any:
    from app.matcha.services.matcha_work.agent_runtime.phase_run import default_client

    return default_client(model)


async def _default_fetch_page(url: str) -> tuple[dict, set[str]]:
    from .fetch import fetch_page

    return await fetch_page(url)


async def _default_view(url: str, prefix: str) -> dict:
    from app.matcha.services.matcha_work.agent_runtime.abilities.screenshots import view

    return await view(url, prefix)


def _default_browser_ready() -> bool:
    from app.matcha.services.matcha_work.agent_runtime.abilities.reservations import browser_ready

    return browser_ready()


async def _default_rehost(images: list[dict], **kwargs) -> tuple[list[dict], list[str]]:
    from app.matcha.services.matcha_work.agent_card.images import rehost_urls

    return await rehost_urls(images, **kwargs)


async def _default_search(query: str) -> list[dict]:
    """A look-up for one finding (`fill.py`): a few Brave results with their pictures."""
    from app.matcha.services.matcha_work import brave_search

    if not brave_search.configured() or not brave_search.available():
        return []
    return await brave_search.search(query, count=5, images=True)


@dataclass
class Deps:
    # Google Maps for `places` (Google's own Places API), or None.
    provider: Callable[[str], Any] = providers.choose_provider
    page_fetch: Callable[..., Awaitable[Any]] = fetch_public
    # Model phases: the model client for a model id, and the model's page tools.
    client: Callable[[str], Any] = _default_client
    fetch_page: Callable[[str], Awaitable[tuple[dict, set[str]]]] = _default_fetch_page
    view: Callable[[str, str], Awaitable[dict]] = _default_view
    browser_ready: Callable[[], bool] = _default_browser_ready
    rehost: Callable[..., Awaitable[tuple[list[dict], list[str]]]] = _default_rehost
    # A web search for one finding by name (Brave), for what it still lacks.
    search: Callable[[str], Awaitable[list[dict]]] = _default_search
    geocode: geo.Geocode = geo.census_point
    today: Callable[[], date] = field(default=date.today)


def _chain() -> chain.ChainSpec:
    from ..orchestrator import TASK_CHAIN  # the orchestrator imports this module

    return TASK_CHAIN


def plan_of(task: dict) -> dict:
    return decode_jsonb(task.get("plan"), {}) or {}


def cursor_of(task: dict) -> dict:
    cursor = decode_jsonb(task.get("phase_cursor"), {}) or {}
    return cursor if isinstance(cursor, dict) else {}


async def count_items(conn, task_id: UUID, where: str = "") -> int:
    return int(await conn.fetchval(
        f"SELECT COUNT(*) FROM mw_agent_task_items WHERE task_id = $1 {where}", task_id,
    ) or 0)


def brief_of(task: dict) -> dict:
    brief = decode_jsonb(task.get("brief"), {}) or {}
    return brief if isinstance(brief, dict) else {}


async def ensure_anchor(task: dict, deps: Deps, guard: chain.Guard) -> dict | None:
    """The place distances are measured from (the brief's `near`) on the map,
    found once per task and kept in the plan; None when there is none or it
    can't be found. Finding it may spend one provider call. A lookup that
    failed (an outage, a rate limit, no calls left) rather than found nothing
    is tried again by the next step, ANCHOR_TRIES times in all."""
    near = brief_of(task).get("near")
    if not near:
        return None
    plan = plan_of(task)
    anchor = plan.get("anchor")
    same = isinstance(anchor, dict) and anchor.get("name") == near
    tries = int(anchor.get("tries") or 1) if same and anchor.get("transient") else 0
    if not same or (anchor.get("transient") and tries < ANCHOR_TRIES):
        provider = deps.provider("places")
        budget = Budget(left=await chain.grant(_chain(), task["id"], "provider_calls", 1, BUDGETS.provider_calls)
                        if provider is not None else 0)
        asked = budget.take()
        anchor = await geo.resolve_anchor(near, brief_of(task).get("location"),
                                          provider=provider if asked else None, geocode=deps.geocode)
        await chain.refund(_chain(), task["id"], "provider_calls", budget.left)
        if "lat" not in anchor and (anchor.get("transient") or (provider is not None and not asked)):
            anchor = {**anchor, "transient": True, "tries": tries + 1}
        async with connection_or_direct() as conn:
            await conn.execute(
                """UPDATE mw_agent_tasks SET plan = COALESCE(plan, '{}'::jsonb) || jsonb_build_object('anchor', $3::jsonb),
                       updated_at = NOW()
                   WHERE id = $1 AND dispatch_token = $2""",
                task["id"], guard.token, json.dumps(anchor),
            )
        task["plan"] = {**plan, "anchor": anchor}
    return anchor if "lat" in anchor else None


async def item_room(conn, task_id: UUID) -> int:
    """How many more findings this task may keep: more once it was asked to search more."""
    searched_more = await conn.fetchval(
        "SELECT EXISTS (SELECT 1 FROM mw_agent_task_rounds WHERE task_id = $1 AND kind = 'more')", task_id,
    )
    cap = BUDGETS.items_after_more if searched_more else BUDGETS.items
    return max(0, cap - await count_items(conn, task_id))


# ── providers ────────────────────────────────────────────────────────────────

# A Google Maps result's facts that say nothing about a home (its "cuisine" is
# "Apartment complex").
NOT_A_HOME = ("cuisine", "price_level")


def provider_record(item: providers.ProviderItem) -> dict:
    return {
        "kind": item.kind, "title": item.title, "subtitle": item.subtitle, "url": item.url,
        "origin": "provider", "provider": item.provider, "fields": item.fields,
        "image_candidates": ([{"source_url": item.image_url, "page_url": item.url, "alt": item.title}]
                             if item.image_url else []),
    }


def as_kind(item: providers.ProviderItem, plan: dict, anchor: dict | None) -> providers.ProviderItem:
    """A provider result as the task's own kind of finding (an apartment
    building on Google Maps is a listing), with its distance from the anchor."""
    fields = dict(item.fields)
    kind = item.kind
    if plan.get("item_kind") == "listing" and kind == "place":
        kind = "listing"
        fields = {k: v for k, v in fields.items() if k not in NOT_A_HOME}
    if anchor is not None and item.point is not None:
        fields.update(geo.distance_fields(item.point, anchor, status="verified", origin="provider", url=item.url,
                                          how="where Google Maps puts it"))
    return replace(item, kind=kind, fields=fields)


def prerank(found: list[providers.ProviderItem], plan: dict) -> list[providers.ProviderItem]:
    """Provider results in the order the task will likely rank them (their own
    price, rating and reviews against the plan's limits and preferences), so
    the store lookups and the room go to the ones the person sees first, not
    to whatever the search happened to list first. Ties keep their order."""
    if len(found) < 2:
        return found
    ranked = sorted(ranking.rank([{"id": str(n), "fields": item.fields, "status": "candidate", "fit_score": None,
                                   "user_state": "new"} for n, item in enumerate(found)], plan),
                    key=lambda r: r.rank)
    ways = asked_directions(plan)
    if len(ways) < 2:
        return [found[int(r.item_id)] for r in ranked]
    kept = [found[int(r.item_id)] for r in ranked if r.band != ranking.HIDDEN]
    return by_direction(kept, ways) + [found[int(r.item_id)] for r in ranked if r.band == ranking.HIDDEN]


def asked_directions(plan: dict) -> list[str]:
    for c in plan.get("constraints") or []:
        if isinstance(c, dict) and c.get("field") == "direction" and c.get("op") == "any_of":
            return [w for w in c.get("value") or [] if isinstance(w, str)]
    return []


def by_direction(found: list[providers.ProviderItem], ways: list[str]) -> list[providers.ProviderItem]:
    """North's best, south's best, north's second, …: room for every direction
    asked, however many of the searches leaned one way. One with no direction
    yet comes after."""
    groups: dict[str, list] = {way: [] for way in ways}
    rest = []
    for item in found:
        way = ((item.fields.get("direction") or {}).get("value") or [None])[0]
        (groups[way] if way in groups else rest).append(item)
    return interleave(list(groups.values())) + rest


def interleave(lists: list[list]) -> list:
    """Every query's first result, then every second one, …: the best of each first."""
    out = []
    for n in range(max((len(x) for x in lists), default=0)):
        out.extend(x[n] for x in lists if n < len(x))
    return out


async def run_providers(task: dict, deps: Deps, guard: chain.Guard) -> PhaseOutcome:
    """Places from Google Maps, then on to the model's search. Any other
    source (products too: a task planned for Google Shopping before
    2026-10-18 among them) is the web search alone."""
    plan = plan_of(task)
    cursor = cursor_of(task)
    source = plan.get("source")
    anchor = await ensure_anchor(task, deps, guard)
    provider = deps.provider(source) if source == "places" else None
    if source == "places" and provider is None:
        logger.info("research task=%s wanted places but GOOGLE_MAPS_API_KEY isn't set", task["id"])
    added = 0
    if provider is not None:
        kind = kinds.of(task)
        # Each area a distance limit covers first (north and south both), then the plan's own.
        around = (geo.areas(anchor, brief_of(task)) if source == "places" and anchor is not None
                  and kind is not None and kind.area_query else [])
        searches = [(kind.area_query, ll) for ll in around] + [
            (q, None) for q in [q for q in plan.get("queries") or [] if q][:PROVIDER_QUERIES]]
        page = int(cursor.get("provider_page") or 1)
        cost = providers.calls_per_search(provider, page)
        budget = Budget(left=await chain.grant(_chain(), task["id"], "provider_calls", len(searches) * cost,
                                               BUDGETS.provider_calls))
        gate = asyncio.Semaphore(QUERY_CONCURRENCY)
        per_query: list[list[providers.ProviderItem]] = [[] for _ in searches]
        refused: list[providers.ProviderError] = []

        async def one(n: int, query: str, ll: str | None) -> None:
            async with gate:
                # Nothing more once every API refused for good (it may have while this one waited).
                if refused or not budget.take(cost):
                    return
                try:
                    per_query[n] = await provider.search(source, query, page=page, **({"ll": ll} if ll else {}))
                except providers.ProviderError as exc:
                    if exc.fatal:
                        # Google refused for good (the provider logged it as an error):
                        # nothing more is asked, and the web search still runs.
                        refused.append(exc)
                    logger.info("research provider query failed task=%s: %s", task["id"], exc)

        await guard.note("Searching Google Maps…")
        await asyncio.gather(*(one(n, q, ll) for n, (q, ll) in enumerate(searches)))
        await chain.refund(_chain(), task["id"], "provider_calls", budget.left)
        found = prerank([as_kind(i, plan, anchor) for i in interleave(per_query)], plan)
        async with connection_or_direct() as conn:
            room = await item_room(conn, task["id"])
            if plan.get("item_kind") == "listing":
                room = min(room, PROVIDER_BUILDINGS)
            added = await items_mod.insert_items(conn, task, guard.token, int(task["current_round"]),
                                                 [provider_record(i) for i in found], room=room)
    return PhaseOutcome(
        status="running", phase=DISCOVER, cursor={**cursor, "provider_added": added},
        progress={"note": f"Found {added} on Google Maps. Searching the web…" if provider is not None
                  else "Searching the web…"},
    )


# ── enrich ───────────────────────────────────────────────────────────────────

def own_page(url: str | None) -> bool:
    normalized = normalize_url(url)
    if not normalized:
        return False
    host = normalized.split("/")[2]
    if "google" in host.split("."):
        return False
    return not any(host == h or host.endswith("." + h) for h in NOT_OWN_PAGE)


def page_images(page: dict, title: str, url: str) -> list[dict]:
    found = []
    for key in ("products", "listings", "places"):
        for node in page.get(key) or []:
            found.extend(node.get("images") or [])
    if page.get("og_image"):
        found.append(page["og_image"])
    out, seen = [], set()
    for image in found:
        if isinstance(image, str) and image.startswith(("https://", "http://")) and image not in seen:
            seen.add(image)
            out.append({"source_url": image, "page_url": url, "alt": title})
    return out[:4]


_PLANS = re.compile(r"floor\s*-?\s*plans?|floorplans|pricing|availability|plans?-and-pricing", re.I)


def plans_link(html: bytes, base: str) -> str | None:
    """A building's floor plans page on its own site (where its rents are),
    from any link on the page, its menu included."""
    site = site_of(urlsplit(base).hostname)
    for anchor, href, parts, its_site in anchors(html, base, limit=400):
        if parts.scheme not in ("http", "https") or its_site != site:
            continue
        if href.rstrip("/") != base.split("#")[0].rstrip("/") and (
                _PLANS.search(anchor.get_text(" ", strip=True)) or _PLANS.search(parts.path)):
            return href
    return None


def _no_rent(fields: dict) -> bool:
    """No rent yet, or only "starting at" ones: a range that ends somewhere is a rent."""
    price = fields.get("price") or {}
    spans = price.get("spans") or []
    return not price or (bool(spans) and all(end is None for _, end in spans))


def _take_rent(found: dict, new: dict) -> dict:
    """`found` with `new`'s facts. `new`'s rent replaces the one there only
    when it is a real rent (a range that ends somewhere), so another "starting
    at" never throws away a better one."""
    if "price" in new and not _no_rent({"price": new["price"]}):
        found = {**found, "price": new["price"]}
    return F.merge(found, {k: v for k, v in new.items() if k != "price"} if "price" in found else new)


async def view_scan(url: str, deps: Deps, views: Budget, *, prefix: str, today: date,
                    building: bool, shots: list[dict] | None = None) -> dict | None:
    """A home's facts from a page as the browser draws it: {} when the view
    failed, None when none was made (no browser worker, or no views left).
    The screenshot (already on our CDN) goes on `shots`."""
    if not deps.browser_ready() or not views.take():
        return None
    viewed = await deps.view(url, f"{prefix}/views")
    if not isinstance(viewed, dict) or viewed.get("error"):
        return {}
    shot = viewed.get("screenshot_url")
    if shots is not None and isinstance(shot, str) and shot.startswith("https://"):
        shots.append({"url": shot, "page_url": viewed.get("url") or url, "alt": "Its page as it looked"})
    return {k: {**v, "evidence": {**v["evidence"], "origin": "browser"}}
            for k, v in F.scan_listing_text(str(viewed.get("text") or ""), url=url, today=today,
                                             building=building).items()}


@dataclass(frozen=True)
class Loaded:
    """A page as loaded: its HTML, where it ended up, and what it says."""

    body: bytes
    url: str
    page: dict


async def plans_page(html: bytes, base: str, deps: Deps, fetches: Budget) -> Loaded | None:
    """A building's floor plans page on its own site, loaded: where its rents
    are, and often its unit map."""
    url = await asyncio.to_thread(plans_link, html, base)
    if url is None or not fetches.take():
        return None
    try:
        fetched = await deps.page_fetch(url, max_bytes=PAGE_BYTES, accept="text/html,application/xhtml+xml",
                                        total_timeout=PAGE_SECONDS)
        if fetched.status != 200 or "html" not in (fetched.content_type or ""):
            return None
        page = await asyncio.to_thread(extract_page, fetched.body, fetched.final_url)
    except Exception:
        logger.info("research floor plans fetch failed", exc_info=True)
        return None
    return Loaded(fetched.body, fetched.final_url, page)


async def floor_plans(plans: Loaded | None, deps: Deps, views: Budget, *, prefix: str, today: date,
                      shots: list[dict] | None = None) -> dict:
    """A building's rents and specials from its floor plans page: read, or
    viewed in the browser when its prices are drawn by JavaScript."""
    if plans is None:
        return {}
    found = F.scan_listing_text(str(plans.page.get("text") or ""), url=plans.url, today=today, building=True)
    if "price" not in found:
        seen = await view_scan(plans.url, deps, views, prefix=prefix, today=today, building=True, shots=shots)
        found = F.merge(found, seen or {})
    return found


def leasing_loader(deps: Deps, fetches: Budget, mine: Budget) -> leasing.Load:
    """How `units.find_units` loads a leasing system's pages: each one of
    this round's page loads, and of `mine`, the building's own LEASING_LOADS,
    so one building never spends another's."""
    async def load(url: str, is_json: bool) -> bytes | None:
        if not mine.take() or not fetches.take():
            return None
        try:
            # SightMap's API sends gzip whatever is asked for.
            fetched = await deps.page_fetch(
                url, max_bytes=LEASING_BYTES, total_timeout=PAGE_SECONDS, gzip=True,
                accept="application/json" if is_json else "text/html,application/xhtml+xml",
            )
        except Exception:
            logger.info("research leasing system load failed", exc_info=True)
            return None
        return fetched.body if fetched.status == 200 and not fetched.truncated else None

    return load


class _NotTried:
    """`enrich_one` ran out of granted page loads before reading this finding."""


NOT_TRIED = _NotTried()


async def enrich_one(row: dict, deps: Deps, fetches: Budget, views: Budget, *, prefix: str) -> dict | _NotTried:
    """The changes for one finding: `{fields, status, image_candidates}`."""
    fields = decode_jsonb(row.get("fields"), {}) or {}
    candidates = decode_jsonb(row.get("image_candidates"), []) or []
    update: dict[str, Any] = {"fields": fields, "status": row.get("status") or "candidate",
                              "image_candidates": candidates}
    url = row.get("url")
    if not own_page(url):
        return update
    if not fetches.take():
        return NOT_TRIED
    today = deps.today()
    try:
        fetched = await deps.page_fetch(url, max_bytes=PAGE_BYTES, accept="text/html,application/xhtml+xml",
                                        total_timeout=PAGE_SECONDS)
    except (UnsafeURL, TimeoutError, OSError):
        return update
    except Exception:
        logger.info("research page fetch failed", exc_info=True)
        return update
    if fetched.status in (404, 410):
        update["status"] = "unavailable"
        return update
    if fetched.status != 200 or "html" not in (fetched.content_type or ""):
        return update
    try:
        page = await asyncio.to_thread(extract_page, fetched.body, fetched.final_url)
    except Exception:
        return update
    text = str(page.get("text") or "")
    if _GONE.search(text):
        update["status"] = "unavailable"
        return update
    found = F.from_page(page, url=fetched.final_url, title=row.get("title") or "", today=today)
    structured = any(page.get(k) for k in ("products", "listings", "places", "events", "offers"))
    # An apartment building from Google Maps: many homes, rents on its floor plans.
    building = row.get("kind") == "listing" and row.get("origin") == "provider"
    viewed_own = False
    shots: list[dict] = []
    if row.get("kind") == "listing":
        found = F.merge(F.scan_listing_text(text, url=fetched.final_url, today=today, building=building), found)
        if not structured and len(text) < THIN_PAGE_CHARS:
            seen = await view_scan(fetched.final_url, deps, views, prefix=prefix, today=today, building=building,
                                   shots=shots)
            viewed_own = seen is not None
            found = F.merge(found, seen or {})
    if building and "price" in found and not found["price"].get("spans"):
        found["price"] = F.starting_at(found["price"])  # a building's one price is its cheapest home
    homes, plans = None, None
    if building:
        # Its homes one by one, from the leasing system its site or its floor plans page names.
        load, tried = leasing_loader(deps, fetches, Budget(left=LEASING_LOADS)), set()
        homes = await leasing.find_units(fetched.body, fetched.final_url, load, today=today, tried=tried)
        if homes is None:
            plans = await plans_page(fetched.body, fetched.final_url, deps, fetches)
            if plans is not None:
                homes = await leasing.find_units(plans.body, plans.url, load, today=today, tried=tried)
    if homes is not None:
        update["units"] = homes.units
        found = F.merge(found, leasing.building_fields(homes, today=today))
    elif building and _no_rent(found):
        # Its floor plans' rents beat a "starting at".
        found = _take_rent(found, await floor_plans(plans, deps, views, prefix=prefix, today=today, shots=shots))
        if _no_rent(found) and not viewed_own:
            # Some buildings draw their rents on their own page but not on their floor plans page.
            found = _take_rent(found, await view_scan(fetched.final_url, deps, views, prefix=prefix, today=today,
                                                      building=True, shots=shots) or {})
    if shots:
        update["screenshots"] = shots[:1]
    update["fields"] = F.merge(fields, found)
    update["status"] = "verified"
    point = geo.page_point(page, row.get("title") or "")
    if point is not None:
        update["point"] = (point, fetched.final_url)
    known = {c.get("source_url") for c in candidates}
    update["image_candidates"] = candidates + [
        c for c in page_images(page, row.get("title") or "", fetched.final_url) if c["source_url"] not in known
    ]
    return update


async def locate(update: dict, anchor: dict, deps: Deps) -> None:
    """Distance and direction for a finding that has none verified yet: from
    its page's schema.org `geo`, else its address."""
    found = update.pop("point", None)
    have = (update["fields"] or {}).get("distance") or {}
    if have.get("status") == "verified" and found is None:
        return
    if found is not None:
        point, url = found
        made = geo.distance_fields(point, anchor, status="verified", origin="jsonld", url=url,
                                   how="where its page's map data puts it")
    else:
        made = await geo.from_address(update["fields"], anchor, geocode=deps.geocode)
    update["fields"] = F.merge(update["fields"], made)


async def enrich(task: dict, deps: Deps, guard: chain.Guard) -> PhaseOutcome:
    async with connection_or_direct() as conn:
        rows = await conn.fetch(
            f"""SELECT id, kind, title, url, origin, status, fields, image_candidates, images, units
                FROM mw_agent_task_items
                WHERE task_id = $1 AND enriched_at IS NULL AND status IN ('candidate', 'verified')
                ORDER BY created_at, id LIMIT {ENRICH_BATCH}""",
            task["id"],
        )
        images_kept = int(await conn.fetchval(
            "SELECT COALESCE(SUM(jsonb_array_length(images)), 0) FROM mw_agent_task_items WHERE task_id = $1",
            task["id"],
        ) or 0)
    own = [r for r in rows if own_page(r["url"])]
    # A building may also load its floor plans page and its leasing system.
    buildings = sum(1 for r in own if r["kind"] == "listing" and r["origin"] == "provider")
    fetches = Budget(left=await chain.grant(_chain(), task["id"], "fetch_calls",
                                            len(own) + (BUILDING_LOADS - 1) * buildings, BUDGETS.fetch_calls))
    if own and fetches.left <= 0:
        fetches.exhausted = True
    # A building may take two views: its floor plans page, then its own.
    views = Budget(left=await chain.grant(_chain(), task["id"], "browser_views", max(1, 2 * buildings),
                                          BUDGETS.browser_views)
                   if any(r["kind"] == "listing" for r in own) and deps.browser_ready() else 0)
    gate = asyncio.Semaphore(ENRICH_CONCURRENCY)
    updates: dict = {}
    prefix = f"matcha-work/{task['company_id']}/agent-tasks/{task['id']}"
    anchor = await ensure_anchor(task, deps, guard)
    in_turn = asyncio.Lock()
    stop_viewing = time.monotonic() + ENRICH_VIEW_SECONDS

    async def view(url: str, where: str) -> dict:
        # One at a time: the browser worker has one slot, and a view queued
        # behind this batch's others would give up as busy. The row gives up
        # its slot meanwhile, so rows that only load a page don't wait on views.
        gate.release()
        try:
            async with in_turn:
                if time.monotonic() >= stop_viewing:
                    views.left += 1  # never made, so it goes back with the rest
                    return {"url": url, "error": "out of time"}
                return await deps.view(url, where)
        finally:
            await gate.acquire()

    batch = replace(deps, view=view)

    async def one(row) -> None:
        async with gate:
            try:
                update = await enrich_one(dict(row), batch, fetches, views, prefix=prefix)
                if anchor is not None and isinstance(update, dict) and update["status"] != "unavailable":
                    await locate(update, anchor, deps)
                updates[row["id"]] = update
            except Exception:
                logger.warning("research enrichment failed item=%s", row["id"], exc_info=True)
                updates[row["id"]] = None

    if rows:
        await guard.note(f"Reading {len(rows)} pages for the details…")
        await asyncio.gather(*(one(row) for row in rows))
    await chain.refund(_chain(), task["id"], "fetch_calls", fetches.left)
    await chain.refund(_chain(), task["id"], "browser_views", views.left)

    async def photos() -> None:
        # Up to images_per_item each, within the task's cap and IMAGE_SECONDS.
        photo_room = max(0, min(ENRICH_IMAGES_PER_BATCH, BUDGETS.images - images_kept))
        stop = time.monotonic() + IMAGE_SECONDS
        for row in rows:
            update = updates.get(row["id"])
            left = stop - time.monotonic()
            if not isinstance(update, dict) or update["status"] == "unavailable" or photo_room <= 0 or left <= 1:
                continue
            have = decode_jsonb(row["images"], []) or []
            want = min(BUDGETS.images_per_item - len(have), photo_room)
            if want <= 0 or not update["image_candidates"]:
                continue
            kept, _warnings = await deps.rehost(update["image_candidates"], prefix=f"{prefix}/photos",
                                                limit=want, total_seconds=min(IMAGE_SECONDS / 2, left))
            update["images"] = have + kept
            photo_room -= len(kept)

    async def plans() -> None:
        found = [(row, updates.get(row["id"])) for row in rows]
        found = [(row, u) for row, u in found if isinstance(u, dict) and u.get("units") and u["status"] != "unavailable"]
        if not found:
            return
        # Floor plans this finding already has on our CDN are kept, not copied again.
        copies = {u["plan_source"]: u["plan_image"] for row, _ in found
                  for u in decode_jsonb(row.get("units"), []) or []
                  if isinstance(u, dict) and u.get("plan_source") and u.get("plan_image")}
        copied = await rehost_plans([u["units"] for _, u in found], plan_of(task), deps, prefix=prefix,
                                    seconds=PLAN_IMAGE_SECONDS, copies=copies)
        for (_, update), units in zip(found, copied):
            update["units"] = units

    # Both at once, so a batch's media take about a minute, not one after the
    # other. A task shown in batches gets its photos when a batch is released
    # (`fill.py`), so they go to what is shown, not to whatever was read first.
    await asyncio.gather(*([] if batches.uses_batches(plan_of(task)) else [photos()]), plans())

    async with connection_or_direct() as conn:
        for item_id, update in updates.items():
            if update is NOT_TRIED:
                continue
            update = update or {}
            await conn.execute(
                """UPDATE mw_agent_task_items SET
                       fields = COALESCE($4::jsonb, fields), status = COALESCE($5, status),
                       image_candidates = COALESCE($6::jsonb, image_candidates),
                       images = COALESCE($7::jsonb, images), units = COALESCE($8::jsonb, units),
                       screenshots = COALESCE($9::jsonb, screenshots),
                       enriched_at = NOW(), updated_at = NOW()
                   WHERE id = $1 AND task_id = $2
                     AND EXISTS (SELECT 1 FROM mw_agent_tasks WHERE id = $2 AND dispatch_token = $3)""",
                item_id, task["id"], guard.token,
                json.dumps(update["fields"], default=str) if "fields" in update else None,
                update.get("status"),
                json.dumps(update["image_candidates"]) if "image_candidates" in update else None,
                json.dumps(update["images"]) if "images" in update else None,
                json.dumps(update["units"], default=str) if "units" in update else None,
                json.dumps(update["screenshots"]) if "screenshots" in update else None,
            )
        remaining = await count_items(
            conn, task["id"], "AND enriched_at IS NULL AND status IN ('candidate', 'verified')",
        )
    if remaining and rows and not fetches.exhausted:
        return PhaseOutcome(status="running", phase=ENRICH,
                            progress={"note": f"Read the pages; {remaining} to go…"})
    return PhaseOutcome(status="running", phase=SCREEN, progress={"note": "Checking what fits…"})


def plan_order(units: list[dict], plan: dict) -> list[str]:
    """A building's floor plans, those of homes that meet the person's
    limits first, then the cheapest homes'; each once."""
    per_home = [c for c in plan.get("constraints") or []
                if isinstance(c, dict) and c.get("field") in ranking.UNIT_FIELDS]
    fits = set(ranking.unit_verdict(units, per_home)[0]) if per_home else set()
    ordered = sorted(units, key=lambda u: str(u.get("id")) not in fits)  # stable: cheapest first within each
    return list(dict.fromkeys(u["plan_source"] for u in ordered if u.get("plan_source")))


async def rehost_plans(buildings: list[list[dict]], plan: dict, deps: Deps, *, prefix: str, seconds: float,
                       copies: dict[str, str] | None = None) -> list[list[dict]]:
    """Each building's homes with their floor plans on our CDN (`plan_image`):
    PLAN_IMAGES not yet copied per building, within `seconds`, `copies`
    (source -> our copy) reused. A plan not copied stays None, never the
    leasing system's URL; its `plan_source` is kept for a later pass."""
    copies = dict(copies or {})
    wanted = [source for units in buildings
              for source in [s for s in plan_order(units, plan) if s not in copies][:PLAN_IMAGES]]
    gate = asyncio.Semaphore(PLAN_IMAGE_CONCURRENCY)
    stop = time.monotonic() + seconds

    async def one(source: str) -> None:
        async with gate:
            left = stop - time.monotonic()
            if left <= 1:
                return
            try:
                kept, _warnings = await deps.rehost([{"source_url": source, "alt": "Floor plan"}],
                                                    prefix=f"{prefix}/plans", limit=1, total_seconds=left)
            except Exception:
                logger.info("research floor plan rehost failed", exc_info=True)
                return
            if kept:
                copies[source] = kept[0]["url"]

    await asyncio.gather(*(one(source) for source in dict.fromkeys(wanted)))
    return [[{**unit, "plan_image": copies.get(unit.get("plan_source"))} for unit in units] for units in buildings]


async def fill_plans(task: dict, plan: dict, deps: Deps, guard: chain.Guard) -> None:
    """After a refine: the floor plans of homes that fit now, where they were
    never copied (enrich copies the plans that fit then, and the cheapest)."""
    async with connection_or_direct() as conn:
        rows = await conn.fetch(
            """SELECT id, units FROM mw_agent_task_items
               WHERE task_id = $1 AND rank_band < 9 AND units <> '[]'::jsonb""",
            task["id"],
        )
    found = [(row["id"], [u for u in decode_jsonb(row["units"], []) or [] if isinstance(u, dict)]) for row in rows]
    found = [(item_id, units) for item_id, units in found
             if any(u.get("plan_source") and not u.get("plan_image") for u in units)]
    if not found:
        return
    copies = {u["plan_source"]: u["plan_image"] for _, units in found for u in units
              if u.get("plan_source") and u.get("plan_image")}
    prefix = f"matcha-work/{task['company_id']}/agent-tasks/{task['id']}"
    copied = await rehost_plans([units for _, units in found], plan, deps, prefix=prefix,
                                seconds=PLAN_FILL_SECONDS, copies=copies)
    async with connection_or_direct() as conn:
        for (item_id, before), after in zip(found, copied):
            if after != before:
                await conn.execute(
                    """UPDATE mw_agent_task_items SET units = $3::jsonb, updated_at = NOW()
                       WHERE id = $1 AND task_id = $2
                         AND EXISTS (SELECT 1 FROM mw_agent_tasks WHERE id = $2 AND dispatch_token = $4)""",
                    item_id, task["id"], json.dumps(after, default=str), guard.token,
                )


# ── rank ─────────────────────────────────────────────────────────────────────

async def rerank(conn, task: dict) -> int:
    """Recompute every finding's rank from stored facts. Returns how many."""
    task = dict(task)
    rows = await conn.fetch(
        """SELECT id, fields, units, status, fit_score, user_state FROM mw_agent_task_items
           WHERE task_id = $1 ORDER BY created_at, id""",
        task["id"],
    )
    if not rows:
        return 0
    ranked = ranking.rank([items_mod.as_rank_input(row) for row in rows], plan_of(task))
    await conn.execute(
        """UPDATE mw_agent_task_items AS i
           SET rank = v.rank, rank_band = v.band, rank_score = v.score,
               rank_explain = v.explain::jsonb, violations = (v.explain::jsonb)->'violations',
               updated_at = NOW()
           FROM unnest($2::uuid[], $3::int[], $4::int[], $5::float8[], $6::text[])
                AS v(id, rank, band, score, explain)
           WHERE i.id = v.id AND i.task_id = $1""",
        task["id"],
        [UUID(str(r.item_id)) for r in ranked],
        [r.rank for r in ranked],
        [r.band for r in ranked],
        [r.score for r in ranked],
        [json.dumps(r.explain) for r in ranked],
    )
    return len(ranked)


async def rank_phase(task: dict, deps: Deps, guard: chain.Guard) -> PhaseOutcome:
    if not await guard.current():
        return PhaseOutcome(status="running")  # advance will find the chain retired
    async with connection_or_direct() as conn:
        fresh = await conn.fetchrow("SELECT * FROM mw_agent_tasks WHERE id = $1", task["id"])
        await rerank(conn, dict(fresh))
    return PhaseOutcome(status="running", phase=FILL, progress={"note": "Getting the best ready to show…"})
