"""Before a batch is released: what its findings still lack, and whether to look further.

Runs after `rank`, and is where "10 more" starts (`batches`):

1. **Look up.** The best findings still waiting that lack a price, a photo or
   a phone number get one web search each (Brave), for the finding by name
   and place: at most `ROUND_LOOK_UPS` a round. A result about the finding (its own site, or a page whose title
   names it) may give its picture (Brave's thumbnail) and, for a building, the
   rents its snippet states. Those are `claimed` facts (origin `search`): a
   search engine's copy of someone else's page, so they are shown with their
   source and never meet a hard limit. Each finding is looked up once a task.
2. **Photos.** The findings about to be released get up to
   `batches.PHOTOS_PER_ITEM` photos each, copied to our CDN from what their
   pages and the look-up showed. Photos follow what is shown, not the order
   findings were read in.
3. **Search, or release.** A `more` round with fewer than `batches.BATCH`
   ready runs its own search first (providers, then the web as a more round
   always has). Otherwise the summary releases what there is and, when that
   is under ten, says what was missing and suggests where to look next
   (`suggest.py`). A model is never sent back to search from here: on
   2026-10-18 a Haiku then Sonnet search on a short batch found 2 of 42
   apartments shown, for nearly all of the round's model cost.
"""
from __future__ import annotations

import asyncio
import json
import logging
import re
import time
from typing import Any
from uuid import UUID

from app.database import connection_or_direct, decode_jsonb
from app.matcha.services.matcha_work.agent_runtime.chain import Guard, PhaseOutcome

from . import batches
from . import fields as F
from .phases import (
    PROVIDERS,
    SUMMARIZE,
    Deps,
    brief_of,
    cursor_of,
    item_room,
    normalize_url,
    plan_of,
)

logger = logging.getLogger(__name__)

# The ranked findings looked at for a batch, and how many may be looked up a
# round (one Brave search each; Brave's free plan is 2,000 a month).
LOOK_AT = 120
ROUND_LOOK_UPS = 12
PHOTO_SECONDS = 60.0
PHOTO_CONCURRENCY = 4
# A result names a finding when this share of the finding's own words are in its title.
NAME_SHARE = 0.75
_PHONE = re.compile(r"(?<!\d)(?:\+?1[\s.-]?)?\(?([2-9]\d{2})\)?[\s.-]?(\d{3})[\s.-]?(\d{4})(?!\d)")
_FILLER = frozenset({"the", "at", "on", "of", "and", "apartments", "apartment", "apts", "homes", "residences",
                     "a", "an", "by", "in", "cafe", "coffee", "co", "inc", "llc"})


def _words(text: str) -> list[str]:
    return [w for w in re.findall(r"[a-z0-9]+", (text or "").lower()) if w not in _FILLER and len(w) > 1]


def names(title: str, text: str) -> bool:
    """Whether `text` (a result's title) names the finding called `title`."""
    own = _words(title)
    if not own:
        return False
    there = set(_words(text))
    return sum(1 for w in own if w in there) / len(own) >= NAME_SHARE


def _host(url: Any) -> str:
    normalized = normalize_url(url if isinstance(url, str) else None) or ""
    host = normalized.split("/")[2] if normalized.count("/") >= 2 else ""
    return host.removeprefix("www.")


def where_of(task: dict) -> str:
    plan, brief = plan_of(task), brief_of(task)
    for value in (plan.get("location"), brief.get("location"), brief.get("near")):
        if isinstance(value, str) and value.strip():
            return value.strip()[:80]
    return ""


def query_for(row: Any, item_kind: str | None, where: str) -> str:
    title = " ".join(str(row["title"] or "").split())[:120]
    place = "" if where and where.split(",")[0].lower() in title.lower() else where
    return " ".join(p for p in (title, place, "rent" if item_kind == "listing" else "") if p)


def _decoded(row: Any, key: str, default: Any) -> Any:
    try:
        return decode_jsonb(row[key], default) or default
    except (KeyError, IndexError):
        return default


def _claimed(made: dict | None) -> dict | None:
    if made is None:
        return None
    return {**made, "status": "claimed", "evidence": {**(made.get("evidence") or {}), "origin": "search"}}


def read_results(row: Any, results: list[dict], *, item_kind: str | None, today) -> dict:
    """What `results` say about the finding `row`: `{fields, image_candidates}`
    to merge in. Its own site's results first."""
    title, own = str(row["title"] or ""), _host(row["url"])
    about = [r for r in results if isinstance(r, dict) and isinstance(r.get("url"), str)
             and ((own and _host(r["url"]) == own) or names(title, str(r.get("title") or "")))]
    about.sort(key=lambda r: _host(r["url"]) != own)
    fields: dict[str, dict] = {}
    images: list[dict] = []
    for result in about:
        text = " ".join([str(result.get("description") or ""), *[str(s) for s in result.get("more") or []]])
        if isinstance(result.get("image"), str):
            images.append({"source_url": result["image"], "page_url": result["url"], "alt": title})
        if item_kind == "listing" and "price" not in fields:
            made = _claimed(F.building_rent(text, url=result["url"], today=today))
            if made is not None:
                fields["price"] = made
        if "phone" not in fields:
            phone = _PHONE.search(text)
            if phone is not None:
                made = _claimed(F.entry(F.LIBRARY["phone"], f"({phone.group(1)}) {phone.group(2)}-{phone.group(3)}",
                                        status="verified", origin="search", today=today, url=result["url"],
                                        quote=phone.group(0)))
                if made is not None:
                    fields["phone"] = made
    return {"fields": fields, "image_candidates": images}


async def _look_up(row: Any, *, item_kind: str | None, where: str, deps: Deps) -> dict | None:
    try:
        results = await deps.search(query_for(row, item_kind, where))
    except Exception:  # Brave out or down: the finding just isn't looked up
        logger.info("research look-up failed item=%s", row["id"], exc_info=True)
        return None
    return read_results(row, results, item_kind=item_kind, today=deps.today())


def _needs_looking_up(row: Any, item_kind: str | None) -> bool:
    return bool(set(batches.missing(row, item_kind)) & {"price", "photo", "contact"})


async def _photos(rows: list[Any], deps: Deps, prefix: str) -> dict[str, list[dict]]:
    """Up to PHOTOS_PER_ITEM photos for each of `rows` that has fewer, within PHOTO_SECONDS."""
    gate = asyncio.Semaphore(PHOTO_CONCURRENCY)
    stop = time.monotonic() + PHOTO_SECONDS
    out: dict[str, list[dict]] = {}

    async def one(row: Any) -> None:
        have = _decoded(row, "images", [])
        want = batches.PHOTOS_PER_ITEM - len(have)
        known = {i.get("source_url") for i in have if isinstance(i, dict)}
        candidates = [c for c in _decoded(row, "image_candidates", []) if isinstance(c, dict)
                      and c.get("source_url") and c.get("source_url") not in known]
        if want <= 0 or not candidates:
            return
        async with gate:
            left = stop - time.monotonic()
            if left <= 1:
                return
            try:
                kept, _warnings = await deps.rehost(candidates, prefix=f"{prefix}/photos", limit=want,
                                                    total_seconds=left)
            except Exception:
                logger.warning("research photos failed item=%s", row["id"], exc_info=True)
                return
        if kept:
            out[str(row["id"])] = have + kept

    await asyncio.gather(*(one(r) for r in rows))
    return out


async def round_kind(conn, task: dict) -> str:
    return str(await conn.fetchval(
        "SELECT kind FROM mw_agent_task_rounds WHERE task_id = $1 AND n = $2", task["id"], task["current_round"],
    ) or "initial")


async def released_and_looked_up(conn, task_id: UUID) -> tuple[list[str], set[str]]:
    summaries = [r["summary"] for r in await conn.fetch(
        "SELECT summary FROM mw_agent_task_rounds WHERE task_id = $1 ORDER BY n", task_id,
    )]
    looked: set[str] = set()
    for summary in summaries:
        looked.update(str(i) for i in (decode_jsonb(summary, {}) or {}).get("looked_up") or [])
    return batches.released(summaries), looked


async def ranked_rows(conn, task_id: UUID, limit: int = LOOK_AT) -> list[Any]:
    return list(await conn.fetch(
        f"""SELECT id, kind, title, subtitle, url, fields, units, images, image_candidates, user_state,
                   fit_score, fit_reasons, rank_explain, rank
            FROM mw_agent_task_items WHERE task_id = $1 AND rank_band < 9
            ORDER BY rank LIMIT {int(limit)}""",
        task_id,
    ))


async def fill(task: dict, deps: Deps, guard: Guard) -> PhaseOutcome:
    cursor = cursor_of(task)
    plan = plan_of(task)
    if not batches.uses_batches(plan):  # planned before batches: summarized as it was
        return PhaseOutcome(status="running", phase=SUMMARIZE, progress={"note": "Writing up what it found…"})
    item_kind = plan.get("item_kind")
    async with connection_or_direct() as conn:
        kind_of_round = await round_kind(conn, task)
        released, looked = await released_and_looked_up(conn, task["id"])
        rows = await ranked_rows(conn, task["id"])
        room = await item_room(conn, task["id"])
    looked |= set(cursor.get("looked_up") or [])
    # A refine re-picks the best ten under the changed plan, shown before or not.
    exclude = set() if kind_of_round == "refine" else set(released)
    waiting = [r for r in rows if str(r["id"]) not in exclude]

    spent = int(cursor.get("look_ups") or 0)
    targets = [r for r in waiting if str(r["id"]) not in looked and _needs_looking_up(r, item_kind)]
    targets = targets[:max(0, ROUND_LOOK_UPS - spent)]
    if targets:
        await guard.note(f"Looking up {len(targets)} of them…")
        where = where_of(task)
        found = await asyncio.gather(*(_look_up(r, item_kind=item_kind, where=where, deps=deps) for r in targets))
        looked |= {str(r["id"]) for r in targets}
        async with connection_or_direct() as conn:
            for row, update in zip(targets, found):
                if not update or not (update["fields"] or update["image_candidates"]):
                    continue
                known = _decoded(row, "image_candidates", [])
                seen = {c.get("source_url") for c in known if isinstance(c, dict)}
                await conn.execute(
                    """UPDATE mw_agent_task_items SET fields = $4::jsonb, image_candidates = $5::jsonb,
                           updated_at = NOW()
                       WHERE id = $1 AND task_id = $2
                         AND EXISTS (SELECT 1 FROM mw_agent_tasks WHERE id = $2 AND dispatch_token = $3)""",
                    row["id"], task["id"], guard.token,
                    json.dumps(F.merge(_decoded(row, "fields", {}), update["fields"]), default=str),
                    json.dumps(known + [c for c in update["image_candidates"] if c["source_url"] not in seen]),
                )
            rows = await ranked_rows(conn, task["id"])
        waiting = [r for r in rows if str(r["id"]) not in exclude]

    # Photos for what is about to be shown: the next batch, judged without them.
    next_up = [r for r in waiting if not set(batches.missing(r, item_kind, plan)) - {"photo"}][:batches.BATCH]
    if next_up:
        prefix = f"matcha-work/{task['company_id']}/agent-tasks/{task['id']}"
        copied = await _photos(next_up, deps, prefix)
        if copied:
            async with connection_or_direct() as conn:
                for item_id, images in copied.items():
                    await conn.execute(
                        """UPDATE mw_agent_task_items SET images = $4::jsonb, updated_at = NOW()
                           WHERE id = $1 AND task_id = $2
                             AND EXISTS (SELECT 1 FROM mw_agent_tasks WHERE id = $2 AND dispatch_token = $3)""",
                        UUID(item_id), task["id"], guard.token, json.dumps(images),
                    )
                rows = await ranked_rows(conn, task["id"])
            waiting = [r for r in rows if str(r["id"]) not in exclude]

    ready = len(batches.pick(waiting, item_kind=item_kind, plan=plan))
    cursor = {**cursor, "looked_up": sorted(looked), "look_ups": spent + len(targets)}
    if next_step(round_kind=kind_of_round, cursor=cursor, ready=ready, room=room) == PROVIDERS:
        return PhaseOutcome(status="running", phase=PROVIDERS, cursor={**cursor, "searched": True},
                            progress={"note": "Looking for more…"})
    return PhaseOutcome(status="running", phase=SUMMARIZE, cursor=cursor,
                        progress={"note": "Writing up what it found…"})


def next_step(*, round_kind: str, cursor: dict, ready: int, room: int) -> str:
    """Where a round goes from `fill`: a more round's own search when fewer
    than a batch is ready and it hasn't searched yet (or was asked for more
    like some), else the summary, which releases what there is."""
    if round_kind != "more" or cursor.get("searched") or room <= 0:
        return SUMMARIZE
    if cursor.get("like") or ready < batches.BATCH:
        return PROVIDERS
    return SUMMARIZE
