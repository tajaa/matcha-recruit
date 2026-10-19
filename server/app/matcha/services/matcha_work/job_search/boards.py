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

What earlier searches read is kept (`postings.py`): the live postings they
read with a related title in the person's places come first, and a board
search Brave was sent in the last day asks for its next page of results
instead of the same one (one read to its end isn't sent). The pages answered
go back with the links; the read step records them once the links are read,
so a step killed before then searches the same pages again.

No model chooses here. Brave's index is months behind: in a prod run on
2026-10-17, 10 of the 45 board links it returned were still posted, and a
model given those results (with no location in their snippets) kept one of
the six that fit. So the posting's own API says whether a job is open, and the
posting's own location says where it is.
"""
from __future__ import annotations

import asyncio
import logging

from app.database import connection_or_direct
from app.matcha.services.matcha_work import brave_search
from app.matcha.services.matcha_work.agent_runtime import chain

from . import normalize, phases, places, postings
from .phases import Deps

logger = logging.getLogger(__name__)

HOSTS = ("job-boards.greenhouse.io", "boards.greenhouse.io", "jobs.lever.co", "jobs.ashbyhq.com")
# Titles searched: at least TITLES, and every one the person typed and every
# kept direction (`phases.must_search`). Places: all they can name (6).
TITLES = 4
LOCAL_TITLES = 2
PLACES = 6
MAX_SEARCHES = 24
RESULTS = 20
# Brave's free plan answers one request a second.
PACE_SECONDS = 1.05
MAX_LINKS = 160
# Postings earlier searches read, ahead of Brave's links.
STORED_LINKS = 60


# A whole state's job hubs, searched by name beside the state: most postings
# write "Los Angeles, CA" and never "California", so a state searched by its
# name alone found little, and before 2026-10-19 a state got no searches in
# it at all ("California" was searched nationwide). The state still keeps a
# job anywhere in it (`places.fits`); these only decide what Brave is asked.
STATE_HUBS = {
    "AL": ("Birmingham", "Huntsville"), "AK": ("Anchorage",), "AZ": ("Phoenix", "Tucson"),
    "AR": ("Little Rock", "Bentonville"), "CA": ("Los Angeles", "San Francisco", "San Diego"),
    "CO": ("Denver", "Boulder"), "CT": ("Stamford", "Hartford"), "DE": ("Wilmington",),
    "DC": ("Washington",), "FL": ("Miami", "Tampa", "Orlando"), "GA": ("Atlanta",), "HI": ("Honolulu",),
    "ID": ("Boise",), "IL": ("Chicago",), "IN": ("Indianapolis",), "IA": ("Des Moines",),
    "KS": ("Overland Park", "Wichita"), "KY": ("Louisville", "Lexington"), "LA": ("New Orleans", "Baton Rouge"),
    "ME": ("Portland",), "MD": ("Baltimore", "Bethesda"), "MA": ("Boston", "Cambridge"),
    "MI": ("Detroit", "Grand Rapids", "Ann Arbor"), "MN": ("Minneapolis",), "MS": ("Jackson",),
    "MO": ("St. Louis", "Kansas City"), "MT": ("Billings", "Bozeman"), "NE": ("Omaha", "Lincoln"),
    "NV": ("Las Vegas", "Reno"), "NH": ("Manchester", "Nashua"), "NJ": ("Newark", "Jersey City", "Princeton"),
    "NM": ("Albuquerque", "Santa Fe"), "NY": ("New York", "Buffalo", "Rochester"),
    "NC": ("Charlotte", "Raleigh", "Durham"), "ND": ("Fargo",), "OH": ("Columbus", "Cleveland", "Cincinnati"),
    "OK": ("Oklahoma City", "Tulsa"), "OR": ("Portland",), "PA": ("Philadelphia", "Pittsburgh"),
    "RI": ("Providence",), "SC": ("Charleston", "Greenville"), "SD": ("Sioux Falls",),
    "TN": ("Nashville", "Memphis"), "TX": ("Austin", "Dallas", "Houston"), "UT": ("Salt Lake City", "Lehi"),
    "VT": ("Burlington",), "VA": ("Arlington", "Richmond", "Reston"), "WA": ("Seattle", "Bellevue"),
    "WV": ("Charleston",), "WI": ("Milwaukee", "Madison"), "WY": ("Cheyenne",),
}
_STATE_NAMES = {code: name.title().replace(" Of ", " of ") for name, code in normalize.STATES.items()}


def _city(text: str) -> str:
    """A place as a search phrase: "San Diego, CA" -> San Diego."""
    return str(text or "").split(",")[0].strip()


def search_places(criteria: dict) -> list[str]:
    """The places to search in, as phrases: each place named, and a whole
    state by its name and its job hubs (`STATE_HUBS`). Each place named comes
    before any hub, so a second state isn't pushed past `PLACES`."""
    groups = []
    for target in places.targets(criteria):
        if target.points or target.name:
            groups.append([_city(target.label)])
        elif target.state:
            groups.append([_STATE_NAMES.get(target.state, target.label), *STATE_HUBS.get(target.state, ())])
    ranked = [group[i] for i in range(max(map(len, groups), default=0)) for group in groups if i < len(group)]
    return list(dict.fromkeys(ranked))[:PLACES]


def board_searches(titles: list[str], criteria: dict, must: int = 0) -> list[str]:
    """The searches for one search's boards: each title on each host, and
    the first titles in each place on each host, taken in turn so a search
    with places gets both before the cap. Titles and hosts, and places and
    hosts, are paired with `phases.cover`, so even a capped list searches
    every title (the first `must` at least), every place and every host:
    listed host by host, two places were enough to leave Ashby unsearched."""
    titles = [t for t in titles if t][:max(TITLES, must)]
    remote = " remote" if criteria.get("remote") == "remote_only" else ""
    spots = search_places(criteria)
    wide = [f'"{title}"{remote} site:{host}' for title, host in phases.cover(titles, list(HOSTS))]
    local = [f'"{title}" "{spot}" site:{host}'
             for (title, spot), host in phases.cover(phases.cover(titles[:LOCAL_TITLES], spots), list(HOSTS))]
    turns = []
    for i in range(max(len(wide), len(local))):
        turns += [s for s in (local[i] if i < len(local) else None, wide[i] if i < len(wide) else None) if s]
    return list(dict.fromkeys(turns))[:MAX_SEARCHES]


def _link(url: str) -> dict:
    return {"url": url, "title": "", "company": "", "location": ""}


async def find(search: dict, titles: list[str], criteria: dict, deps: Deps,
               guard: chain.Guard, *, must: int = 0) -> tuple[list[dict], bool, list[dict]]:
    """The board postings for the read step, once each: the live ones
    earlier searches read that this one would keep, then what Brave's
    answers link to. `([{url, title, company, location}], whether the boards
    were searched, the pages Brave answered as {query, offset, last})`. Each
    search is reserved on the search's `provider_calls` first."""
    searches = board_searches(titles, criteria, must)
    if not searches:
        return [], False, []
    async with postings.store(connection_or_direct) as store:
        sent = await store.sent(searches)
        stored = await store.matching(titles, criteria)
    links: dict[tuple, dict] = {row.key: _link(row.read_url) for row in stored[:STORED_LINKS] if row.read_url}
    pages = postings.plan(searches, sent)
    if not pages:
        # Every one of them was read to its end in the last day, and what
        # they found is stored: searched, not a source that couldn't be reached.
        return list(links.values()), True, []
    granted = await phases.grant(search["id"], "provider_calls", len(pages), phases.MAX_PROVIDER_CALLS)
    if granted <= 0:
        # The budget went on earlier passes, which did search: not a source
        # that couldn't be reached (that would end the search as unavailable).
        return list(links.values()), True, []
    answered: list[dict] = []
    used = 0
    linked = 0  # Brave's links, past the stored ones
    for i, page in enumerate(pages[:granted]):
        if i:
            await asyncio.sleep(PACE_SECONDS)
        used += 1
        try:
            results = await deps.web_search(page.query, RESULTS, offset=page.offset)
        except brave_search.Unavailable as exc:
            if exc.out:
                logger.info("job search board searches stopped search=%s: %s", search["id"], exc)
                used -= 1
                break
            continue
        answered.append({"query": page.query, "offset": page.offset,
                         "last": postings.last_page(page, len(results), RESULTS)})
        for result in results:
            key = postings.key_of_url(result.get("url"))
            if key is not None and key not in links and linked < MAX_LINKS:
                links[key] = _link(result["url"])
                linked += 1
        if i % 4 == 3:
            if not await guard.current():
                break  # cancelled or replaced: its searches stop here
            await guard.note(f"Searched employers' job boards ({i + 1} of {len(pages)})…")
    await phases.refund(search["id"], "provider_calls", granted - used)
    return list(links.values()), bool(answered), answered


async def record_searched(pages: list[dict]) -> None:
    """The board searches `find` sent, once their postings are read (and
    so stored): the same search within a day asks for the next page."""
    done = [(postings.Page(str(p["query"]), int(p["offset"])), bool(p.get("last")))
            for p in pages if isinstance(p, dict) and p.get("query")]
    if done:
        async with postings.store(connection_or_direct) as store:
            await store.searched(done)
