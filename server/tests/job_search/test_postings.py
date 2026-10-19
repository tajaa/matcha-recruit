"""The postings Espresso has read, kept: what a search reuses, skips and sends again. No database."""
import json
import logging
from contextlib import asynccontextmanager
from unittest.mock import AsyncMock

import pytest

from app.matcha.services.matcha_work.job_search import ats, discovery, normalize, phases, postings
from tests.agent_runtime.helpers import FakeConn

GH = "https://job-boards.greenhouse.io/Acme/jobs/4001"
LEVER = "https://jobs.lever.co/brightpath/0f6b2a4e-1111-2222-3333-444455556666"
KEY = ("greenhouse", "acme", "4001")


def record(url=GH, title="Chief People Officer", company="Acme", location="San Diego, CA", remote=False):
    """A posting as `discovery._record` reads it from its board."""
    ref = ats.detect(url)
    return {"dedupe_key": normalize.dedupe_key(company, title, location), "title": title, "company": company,
            "location": location, "state_code": normalize.state_of(location), "remote": remote,
            "source": ref.provider, "source_url": url, "comp": {}, "comp_status": "not_posted",
            "comp_annual_min": None, "comp_annual_max": None, "comp_currency": None,
            "ats": {**ref.view(), "questions": []}, "description": "Lead people.", "enriched": True}


def row(rec, *, live=True, fresh=True, key=KEY):
    return {"provider": key[0], "board_key": key[1], "job_key": key[2], "url": rec["source_url"] if rec else None,
            "live": live, "fresh": fresh, "record": json.dumps(rec) if rec else None}


def test_keys():
    assert postings.key_of_url(GH) == KEY and postings.key_of_url("https://acme.test/jobs/1") is None
    assert postings.key_of_record(record()) == KEY
    assert postings.key_of_record({"ats": {"provider": "web"}}) is None
    assert postings.key_of_record({"ats": {"provider": "lever", "board": "", "job_id": "x"}}) is None
    assert postings.query_key('  "COO"   site:jobs.lever.co ') == '"coo" site:jobs.lever.co'


def test_a_search_sent_today_asks_for_its_next_page():
    queries = ['"COO" site:jobs.lever.co', '"COO" site:jobs.ashbyhq.com', '"COO" site:boards.greenhouse.io',
               '"COO" site:job-boards.greenhouse.io']
    sent = {postings.query_key(queries[1]): (2, False), postings.query_key(queries[2]): (1, True),
            postings.query_key(queries[3]): (postings.MAX_PAGE + 1, False)}
    assert postings.plan(queries, sent) == [postings.Page(queries[0], 0), postings.Page(queries[1], 2)]
    page = postings.Page(queries[0], 0)
    assert postings.last_page(page, 7, 20) and not postings.last_page(page, 20, 20)
    assert postings.last_page(postings.Page("q", postings.MAX_PAGE), 20, 20)


def test_a_stored_posting_is_kept_by_the_read_steps_own_rules():
    criteria = {"locations": ["San Diego, CA"]}
    near = postings.Stored(KEY, GH, True, True, record())
    far = postings.Stored(KEY, GH, True, True, record(location="Boston, MA"))
    other = postings.Stored(KEY, GH, True, True, record(title="Software Engineer"))
    empty = postings.Stored(KEY, GH, True, True, None)
    assert postings.keep([near, far, other, empty], ["Head of People"], criteria) == [near]


@pytest.mark.asyncio
async def test_known_says_what_is_stored_about_each_posting():
    conn = FakeConn().on("FROM mw_job_postings", [row(record()), row(None, live=False, key=("lever", "b", "j"))])
    found = await postings.Store(conn).known([KEY, KEY, ("lever", "b", "j")])
    assert found[KEY].live and found[KEY].fresh and found[KEY].record["title"] == "Chief People Officer"
    assert found[KEY].url == GH and found[("lever", "b", "j")].live is False
    (_, query, args), = conn.calls
    assert "unnest($1::text[], $2::text[], $3::text[])" in query
    assert args == (["greenhouse", "lever"], ["acme", "b"], ["4001", "j"], postings.LIVE_HOURS, postings.CLOSED_DAYS)
    assert await postings.Store(conn).known([]) == {} and len(conn.calls) == 1


@pytest.mark.asyncio
async def test_matching_finds_stored_postings_with_a_related_title_in_the_place():
    rows = [row(record()), row(record(title="Staff Accountant"), key=("greenhouse", "acme", "2")),
            row(record(location="Boston, MA"), key=("greenhouse", "acme", "3"))]
    conn = FakeConn().on("to_tsquery", rows)
    found = await postings.Store(conn).matching(["Head of People", "CHRO"], {"locations": ["San Diego, CA"]})
    assert [r.key for r in found] == [KEY]
    (_, query, args), = conn.calls
    assert "WHERE live AND live_at" in query and "@@ to_tsquery('english', $1)" in query
    # Work words, not level words: "human resources" for Head of People and CHRO alike.
    assert args[0] == "human | resources" and args[3] == ["CA"] and args[4] is True
    # A title of level words alone (CEO) is searched by all of them.
    await postings.Store(conn).matching(["CEO"], {})
    assert conn.calls[-1][2][0] == "chief | executive | officer"
    assert await postings.Store(conn).matching(["", "  "], {}) == [] and len(conn.calls) == 2


@pytest.mark.asyncio
async def test_save_keeps_what_was_read_live_and_what_the_board_closed():
    conn = FakeConn()
    store = postings.Store(conn)
    lever = record(LEVER, title="VP of People", company="Brightpath", location="Remote", remote=True)
    page = {**record(), "ats": None}  # a careers page, not an ATS posting
    await store.save([record(), record(), lever, page], [KEY, ("lever", "gone", "x")])
    live, closed = conn.calls
    rows = json.loads(live[2][0])
    assert [r["board_key"] for r in rows] == ["acme", "brightpath"], "once each, pages left out"
    assert rows[0]["title_terms"] == "chief human officer resources" and rows[0]["ref"]["board"] == "Acme"
    assert rows[0]["record"]["description"] == "Lead people." and rows[0]["url"] == GH
    assert "ON CONFLICT (provider, board_key, job_key) DO UPDATE" in live[1] and "closed_at = NULL" in live[1]
    # Read live in this batch wins over closed.
    assert closed[2] == (["lever"], ["gone"], ["x"]) and "COALESCE(p.closed_at, NOW())" in closed[1]
    await store.save([], [])
    assert len(conn.calls) == 2


@pytest.mark.asyncio
async def test_searches_sent_and_recorded():
    conn = FakeConn().on("FROM mw_job_board_searches", [{"query": '"coo" site:jobs.lever.co', "next_offset": 2,
                                                          "exhausted": False}])
    store = postings.Store(conn)
    assert await store.sent(['"COO" site:jobs.lever.co']) == {'"coo" site:jobs.lever.co': (2, False)}
    assert conn.calls[0][2] == (['"coo" site:jobs.lever.co'], postings.SEARCH_HOURS)
    await store.searched([(postings.Page('"COO" site:jobs.lever.co', 0), False),
                          (postings.Page('"CHRO" site:jobs.lever.co', 3), True)])
    _, query, args = conn.calls[1]
    assert args == (['"coo" site:jobs.lever.co', '"chro" site:jobs.lever.co'], [1, 4], [False, True])
    assert "WHEN EXCLUDED.next_offset = 1 THEN NOW() ELSE s.started_at" in query
    assert await store.sent([]) == {}
    await store.searched([])
    assert len(conn.calls) == 2


@pytest.mark.asyncio
async def test_a_store_that_fails_stores_nothing_and_costs_nothing(caplog):
    broken = FakeConn().on("mw_job", RuntimeError('relation "mw_job_postings" does not exist'))
    store = postings.Store(broken)
    with caplog.at_level(logging.WARNING):
        assert await store.known([KEY]) == {}
        assert await store.matching(["COO"], {}) == []
        await store.save([record()], [("lever", "gone", "x")])
        assert await store.sent(["q"]) == {}
        await store.searched([(postings.Page("q", 0), True)])
    assert caplog.text.count("job postings:") == 6
    nothing = postings.Store(None)
    assert await nothing.known([KEY]) == {} and await nothing.sent(["q"]) == {}
    await nothing.save([record()])

    def no_database():
        raise OSError("connection refused")

    async with postings.store(no_database) as store:
        assert store.conn is None and await store.matching(["COO"], {}) == []

    conn = FakeConn()

    @asynccontextmanager
    async def connect():
        yield conn

    async with postings.store(connect) as store:
        assert store.conn is conn


@pytest.mark.asyncio
async def test_reads_note_what_the_board_said_is_closed(monkeypatch):
    ref = ats.detect(GH)
    answers = {"4001": ats.AtsRead(None, closed=True), "5": ats.AtsRead(None)}
    monkeypatch.setattr(ats, "read", AsyncMock(side_effect=lambda r, more=None: answers[r.job_id]))
    reads = postings.Reads()
    assert await reads.fetch(ref) is None
    assert await reads.fetch(ats.AtsRef("greenhouse", "acme", "5")) is None
    assert reads.closed == {KEY}, "no answer is not closed"
    # A stand-in reader (tests) is asked as is.
    stand_in = AsyncMock(return_value="posting")
    reads = postings.Reads(stand_in)
    assert await reads.fetch(ref, more=None) == "posting" and not reads.closed
    stand_in.assert_awaited_once_with(ref, more=None)


@pytest.mark.asyncio
async def test_a_closed_board_posting_read_through_discovery_is_noted(monkeypatch):
    monkeypatch.setattr(ats, "read", AsyncMock(return_value=ats.AtsRead(None, closed=True)))
    reads = postings.Reads()
    budget = iter([True, True])
    out = await discovery.read_posting({"url": GH}, phases.Deps(ats_fetch=reads.fetch),
                                       lambda: next(budget, False), today=None)
    assert out is None and reads.closed == {KEY}


def test_a_stored_posting_is_read_again_on_its_board():
    careers = {**record(), "source_url": "https://www.acme.test/careers?gh_jid=4001"}
    assert postings.Stored(KEY, careers["source_url"], True, False, careers).read_url == (
        "https://job-boards.greenhouse.io/Acme/jobs/4001")
    assert postings.Stored(KEY, GH, True, False, None).read_url == GH
