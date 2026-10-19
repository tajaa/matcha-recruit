"""Code's own board searches: Brave for each title on Greenhouse, Lever and Ashby. No network."""
from unittest.mock import AsyncMock

import pytest

from app.matcha.services.matcha_work import brave_search
from app.matcha.services.matcha_work.job_search import boards, phases

from ._fixtures import SEARCH, search_row

GRANT = "RETURNING GREATEST(LEAST($2, $3 - cur.before), 0)"
REFUND = "SET provider_calls = GREATEST(provider_calls - $2, 0)"
GH = "https://job-boards.greenhouse.io/acme/jobs/4001"
LEVER = "https://jobs.lever.co/brightpath/0f6b2a4e-1111-2222-3333-444455556666"


@pytest.fixture
def conn(monkeypatch):
    from app.matcha.services.matcha_work.agent_runtime import chain
    from tests.agent_runtime.helpers import FakeConn, connection

    conn = FakeConn()
    for module in (phases, chain, boards):
        monkeypatch.setattr(module, "connection_or_direct", connection(conn))
    monkeypatch.setattr(boards, "PACE_SECONDS", 0)
    return conn


class Guard:
    def __init__(self, current=True):
        self.notes = []
        self._current = current

    async def note(self, text, **_counts):
        self.notes.append(text)

    async def current(self):
        return self._current


def test_board_searches():
    titles = ["Chief People Officer", "CHRO", "VP People", "Head of People", "Fifth Title"]
    wide = boards.board_searches(titles, {})
    # Titles and hosts in turn (`phases.cover`): the first four reach every
    # title and every host, so a capped list has each of both in it.
    assert wide[:4] == [f'"{title}" site:{host}' for title, host in zip(titles, boards.HOSTS)]
    assert len(wide) == 16 and not any("Fifth Title" in q for q in wide)
    # A fifth typed title (or kept direction) is searched too.
    assert len(boards.board_searches(titles, {}, must=5)) == 20
    # With places: a local search, then a wide one, in turn, up to the cap;
    # each place is reached before a title repeats (`phases.cover`).
    local = boards.board_searches(titles, {"locations": ["San Diego, CA", "Remote", "Orange County, CA"]})
    assert local[:4] == ['"Chief People Officer" "San Diego" site:job-boards.greenhouse.io',
                         '"Chief People Officer" site:job-boards.greenhouse.io',
                         '"CHRO" "Orange County" site:boards.greenhouse.io',
                         '"CHRO" site:boards.greenhouse.io']
    assert len(local) == boards.MAX_SEARCHES and len(set(local)) == len(local)
    assert any('"Orange County"' in q for q in local) and not any('"Remote"' in q for q in local)
    assert boards.board_searches(["COO"], {"remote": "remote_only"})[0] == '"COO" remote site:job-boards.greenhouse.io'
    assert boards.board_searches([], {"locations": ["Austin, TX"]}) == []


def test_a_whole_state_is_searched_by_name_and_its_job_hubs():
    """Before 2026-10-19 a state got no searches in it ("California" was
    searched nationwide only, and kept California jobs after): it is now its
    name and its job hubs, each named place before any hub."""
    assert boards.search_places({"locations": ["California"]}) == [
        "California", "Los Angeles", "San Francisco", "San Diego"]
    assert boards.search_places({"locations": ["CA"]})[0] == "California"
    assert boards.search_places({"locations": ["California", "Texas"]}) == [
        "California", "Texas", "Los Angeles", "Austin", "San Francisco", "Dallas"]
    assert boards.search_places({"locations": ["Texas", "Denver, CO"]})[:2] == ["Texas", "Denver"]
    assert boards.search_places({"locations": ["San Diego, CA", "Remote"]}) == ["San Diego"]
    assert boards.search_places({}) == []
    assert set(boards.STATE_HUBS) == set(boards.normalize.STATES.values())
    # find_jobs' eight: each of the four, each on its own board, beside the four nationwide.
    quick = boards.board_searches(["Chief People Officer"], {"locations": ["California"]})[:8]
    assert [q for q in quick if q.count('"') == 4] == [
        '"Chief People Officer" "California" site:job-boards.greenhouse.io',
        '"Chief People Officer" "Los Angeles" site:boards.greenhouse.io',
        '"Chief People Officer" "San Francisco" site:jobs.lever.co',
        '"Chief People Officer" "San Diego" site:jobs.ashbyhq.com']
    # A job search's capped list still reaches every host and every hub.
    full = boards.board_searches(["Chief People Officer", "Head of HR", "CHRO", "VP of People"],
                                 {"locations": ["California"]})
    assert len(full) == boards.MAX_SEARCHES
    assert all(any(f"site:{host}" in q for q in full) for host in boards.HOSTS)
    assert all(any(f'"{spot}"' in q for q in full) for spot in ("California", "Los Angeles", "San Diego"))


def test_a_capped_list_still_searches_every_typed_title_and_place():
    """When the Google Jobs step went (2026-10-18), so did its query per typed
    title and place: eight typed titles and six places are each searched."""
    typed = [f"Title {n}" for n in range(1, 9)]
    towns = ["Austin, TX", "Dallas, TX", "Houston, TX", "Denver, CO", "Phoenix, AZ", "Seattle, WA"]
    searches = boards.board_searches([*typed, "Model One", "Model Two"], {"titles": typed, "locations": towns},
                                     must=len(typed))
    assert len(searches) == boards.MAX_SEARCHES
    assert all(any(f'"{t}"' in q for q in searches) for t in typed)
    assert all(any(f'"{town.split(",")[0]}"' in q for q in searches) for town in towns)


@pytest.mark.parametrize("towns", [
    ["Austin, TX"], ["Austin, TX", "Dallas, TX"],
    ["Austin, TX", "Dallas, TX", "Houston, TX", "Denver, CO", "Phoenix, AZ", "Seattle, WA"],
])
def test_every_host_is_searched_under_the_cap(towns):
    """Listed host by host, two places were enough to push Ashby past the
    cap; with eight typed titles and six places, Ashby and Lever both went."""
    typed = [f"Title {n}" for n in range(1, 9)]
    for titles, must in ((["COO", "Chief Operating Officer", "VP Ops", "Head of Operations"], 0), (typed, len(typed))):
        searches = boards.board_searches(titles, {"locations": towns}, must=must)
        assert len(searches) <= boards.MAX_SEARCHES
        for host in boards.HOSTS:
            assert any(f"site:{host}" in q for q in searches), (host, towns, must)
            # Each host gets a wide search (any place) too.
            assert any(q.endswith(f"site:{host}") and q.count('"') == 2 for q in searches), (host, towns)


@pytest.mark.asyncio
async def test_find_collects_each_board_link_once(conn):
    conn.on(GRANT, lambda _id, want, _limit: want)
    answers = {
        0: [{"url": GH}, {"url": "https://acme.test/careers"}, {"url": LEVER}],
        1: [{"url": GH.replace("/acme/", "/ACME/")}],
    }
    calls = []

    async def web_search(query, count, offset=0):
        calls.append((query, count, offset))
        return answers.get(len(calls) - 1, [])

    guard = Guard()
    links, worked, pages = await boards.find(search_row(), ["COO"], {}, phases.Deps(web_search=web_search), guard)
    assert worked and [link["url"] for link in links] == [GH, LEVER]
    assert links[0] == {"url": GH, "title": "", "company": "", "location": ""}
    assert len(calls) == 4 and all(count == boards.RESULTS and offset == 0 for _q, count, offset in calls)
    # Each page Brave answered, for the read step to record once its postings are read.
    assert pages == [{"query": q, "offset": 0, "last": True} for q, _c, _o in calls]
    assert conn.ran(GRANT)[0][2] == (SEARCH, 4, phases.MAX_PROVIDER_CALLS)
    assert guard.notes == ["Searched employers' job boards (4 of 4)…"]
    assert not conn.ran(REFUND)  # all four used


@pytest.mark.asyncio
async def test_find_stops_when_brave_is_out_and_gives_back_the_rest(conn):
    conn.on(GRANT, lambda _id, want, _limit: want)
    seen = []

    async def web_search(query, _count, offset=0):
        seen.append(query)
        if len(seen) == 1:
            raise brave_search.Unavailable("too slow")  # this search only
        if len(seen) == 2:
            return [{"url": LEVER}]
        raise brave_search.Unavailable("no searches left", out=True)

    links, worked, pages = await boards.find(search_row(), ["COO"], {}, phases.Deps(web_search=web_search), Guard())
    assert worked and [link["url"] for link in links] == [LEVER] and [p["query"] for p in pages] == [seen[1]]
    assert len(seen) == 3
    # Four reserved, two used: the one Brave refused for good and the one never asked go back.
    assert conn.ran(REFUND)[0][2] == (SEARCH, 2)


@pytest.mark.asyncio
async def test_find_with_no_budget_or_no_answers(conn):
    conn.on(GRANT, 0)
    web_search = AsyncMock(return_value=[{"url": GH}])
    found = await boards.find(search_row(), ["COO"], {}, phases.Deps(web_search=web_search), Guard())
    # A spent budget (earlier passes searched) is not a source that was down.
    assert found == ([], True, [])
    web_search.assert_not_awaited()

    conn.on(GRANT, lambda _id, want, _limit: want)
    web_search = AsyncMock(side_effect=brave_search.Unavailable("Brave search has no key", out=True))
    assert await boards.find(search_row(), ["COO"], {}, phases.Deps(web_search=web_search), Guard()) == ([], False, [])
    assert web_search.await_count == 1
    assert await boards.find(search_row(), [], {}, phases.Deps(web_search=web_search), Guard()) == ([], False, [])


@pytest.mark.asyncio
async def test_a_cancelled_search_stops_spending_its_searches(conn):
    """The guard is checked every few searches: a cancelled or replaced
    search stops, and what it did not use goes back."""
    conn.on(GRANT, lambda _id, want, _limit: want)
    web_search = AsyncMock(return_value=[{"url": LEVER}])
    links, worked, _ = await boards.find(search_row(), ["COO", "Chief Operating Officer", "Head of Operations"], {},
                                         phases.Deps(web_search=web_search), Guard(current=False))
    assert worked and [link["url"] for link in links] == [LEVER]
    assert web_search.await_count == 4  # the check comes after the fourth
    assert conn.ran(REFUND)[0][2] == (SEARCH, 12 - 4)


@pytest.mark.asyncio
async def test_find_caps_the_links(conn, monkeypatch):
    conn.on(GRANT, lambda _id, want, _limit: want)
    monkeypatch.setattr(boards, "MAX_LINKS", 3)
    many = [{"url": f"https://job-boards.greenhouse.io/acme/jobs/{i}"} for i in range(10)]
    links, _, _ = await boards.find(search_row(), ["COO"], {}, phases.Deps(web_search=AsyncMock(return_value=many)),
                                    Guard())
    assert len(links) == 3


def stored_row(url, title="Chief Operating Officer", location="Austin, TX"):
    import json as _json

    from app.matcha.services.matcha_work.job_search import ats, normalize

    ref = ats.detect(url)
    record = {"title": title, "company": ref.board, "location": location, "remote": False, "source_url": url,
              "dedupe_key": normalize.dedupe_key(ref.board, title, location), "ats": ref.view()}
    return {"provider": ref.provider, "board_key": ref.board, "job_key": ref.job_id, "url": url, "live": True,
            "fresh": True, "record": _json.dumps(record)}


@pytest.mark.asyncio
async def test_find_starts_from_stored_postings_and_asks_for_the_next_page(conn):
    """What earlier searches read comes first; a search sent today asks for
    its next page; one read to its end isn't sent, or reserved."""
    from app.matcha.services.matcha_work.job_search import postings

    stored = "https://jobs.ashbyhq.com/stored/0f6b2a4e-1111-2222-3333-444455556666"
    searches = boards.board_searches(["COO"], {})
    conn.on(GRANT, lambda _id, want, _limit: want)
    conn.on("FROM mw_job_board_searches", [
        {"query": postings.query_key(searches[0]), "next_offset": 2, "exhausted": False},
        {"query": postings.query_key(searches[1]), "next_offset": 1, "exhausted": True},
    ])
    conn.on("to_tsquery", [stored_row(stored), stored_row(GH.replace("4001", "9"), title="Forklift Operator")])
    calls = []

    async def web_search(query, count, offset=0):
        calls.append((query, offset))
        return [{"url": GH}, {"url": stored}]

    links, worked, pages = await boards.find(search_row(), ["COO"], {}, phases.Deps(web_search=web_search), Guard())
    assert worked and [link["url"] for link in links] == [stored, GH], "a stored Forklift Operator isn't a COO"
    assert calls == [(searches[0], 2), (searches[2], 0), (searches[3], 0)]
    assert conn.ran(GRANT)[0][2] == (SEARCH, 3, phases.MAX_PROVIDER_CALLS)
    assert pages[0] == {"query": searches[0], "offset": 2, "last": True}

    # Every one read to its end today: the stored postings, nothing sent.
    conn.on("FROM mw_job_board_searches", [{"query": postings.query_key(q), "next_offset": 1, "exhausted": True}
                                           for q in searches])
    web_search = AsyncMock()
    found = await boards.find(search_row(), ["COO"], {}, phases.Deps(web_search=web_search), Guard())
    assert found == ([{"url": stored, "title": "", "company": "", "location": ""}], True, [])
    web_search.assert_not_awaited()


@pytest.mark.asyncio
async def test_pages_are_recorded_for_the_next_search(conn):
    await boards.record_searched([{"query": '"COO" site:jobs.lever.co', "offset": 1, "last": False}, "junk", {}])
    assert conn.ran("INSERT INTO mw_job_board_searches")[0][2] == (['"coo" site:jobs.lever.co'], [2], [False])
    await boards.record_searched([])
    assert len(conn.ran("INSERT INTO mw_job_board_searches")) == 1
