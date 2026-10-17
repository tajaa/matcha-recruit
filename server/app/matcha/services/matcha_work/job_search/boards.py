"""Postings on employers' own job boards, found by code.

Brave web search (`Deps.web_search`) for each planned title on each board
host (Greenhouse, both of its hosts, Lever and Ashby), interleaved with each
title in each of the person's places on each host (`board_searches`). Every
Greenhouse, Lever or Ashby job link in the answers is a posting to read
(`ats.detect`). The links go to the discovery `read` step
(`discovery.read_postings`), which reads each from its board's public API, so
a job no longer posted is dropped, keeps it only where the person wants it
(`places.fits`) and with a title related to theirs (`normalize.related_title`),
and saves it as a lead.

No model chooses here. Brave's index is months behind: in a prod run on
2026-10-17, 10 of the 45 board links it returned were still posted, and a
model given those results (with no location in their snippets) kept one of
the six that fit. So the posting's own API says whether a job is open, and the
posting's own location says where it is.
"""
from __future__ import annotations

import asyncio
import logging

from app.matcha.services.matcha_work import brave_search
from app.matcha.services.matcha_work.agent_runtime import chain

from . import ats, phases, places
from .phases import Deps

logger = logging.getLogger(__name__)

HOSTS = ("job-boards.greenhouse.io", "boards.greenhouse.io", "jobs.lever.co", "jobs.ashbyhq.com")
TITLES = 4
LOCAL_TITLES = 2
PLACES = 5
MAX_SEARCHES = 24
RESULTS = 20
# Brave's free plan answers one request a second.
PACE_SECONDS = 1.05
MAX_LINKS = 160


def _city(text: str) -> str:
    """A place as a search phrase: "San Diego, CA" -> San Diego."""
    return str(text or "").split(",")[0].strip()


def board_searches(titles: list[str], criteria: dict) -> list[str]:
    """The searches for one search's boards: each title on each host, and
    each of the first titles in each place on each host, taken in turn so a
    search with places gets both before the cap."""
    titles = [t for t in titles if t][:TITLES]
    remote = " remote" if criteria.get("remote") == "remote_only" else ""
    spots = [_city(t.label) for t in places.targets(criteria) if t.points or t.name][:PLACES]
    wide = [f'"{title}"{remote} site:{host}' for title in titles for host in HOSTS]
    local = [f'"{title}" "{spot}" site:{host}' for spot in spots for title in titles[:LOCAL_TITLES]
             for host in HOSTS]
    turns = []
    for i in range(max(len(wide), len(local))):
        turns += [s for s in (local[i] if i < len(local) else None, wide[i] if i < len(wide) else None) if s]
    return list(dict.fromkeys(turns))[:MAX_SEARCHES]


async def find(search: dict, titles: list[str], criteria: dict, deps: Deps,
               guard: chain.Guard) -> tuple[list[dict], bool]:
    """The board postings Brave's answers link to, once each, for the read
    step: `([{url, title, company, location}], whether any search answered)`.
    Each search is reserved on the search's `provider_calls` first."""
    searches = board_searches(titles, criteria)
    if not searches:
        return [], False
    granted = await phases.grant(search["id"], "provider_calls", len(searches), phases.MAX_PROVIDER_CALLS)
    links: dict[tuple, dict] = {}
    answered = 0
    used = 0
    for i, query in enumerate(searches[:granted]):
        if i:
            await asyncio.sleep(PACE_SECONDS)
        used += 1
        try:
            results = await deps.web_search(query, RESULTS)
        except brave_search.Unavailable as exc:
            if exc.out:
                logger.info("job search board searches stopped search=%s: %s", search["id"], exc)
                used -= 1
                break
            continue
        answered += 1
        for result in results:
            ref = ats.detect(result.get("url"))
            if ref is not None and len(links) < MAX_LINKS:
                links.setdefault((ref.provider, ref.board.lower(), ref.job_id.lower()),
                                 {"url": result["url"], "title": "", "company": "", "location": ""})
        if i % 4 == 3:
            await guard.note(f"Searched employers' job boards ({i + 1} of {len(searches)})…")
    await phases.refund(search["id"], "provider_calls", granted - used)
    return list(links.values()), answered > 0
