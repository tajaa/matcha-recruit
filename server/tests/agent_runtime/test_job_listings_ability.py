"""find_jobs and the job_postings block: Brave's board searches, every posting
read on its board. No network."""
import asyncio

import pytest

from app.matcha.services.matcha_work import brave_search
from app.matcha.services.matcha_work.agent_runtime import catalog, result
from app.matcha.services.matcha_work.agent_runtime.abilities import job_listings as J
from app.matcha.services.matcha_work.agent_runtime.context import RunLimits, RunState
from app.matcha.services.matcha_work.job_search import ats, boards, normalize
from tests.job_search._fixtures import MemoryStore

from .helpers import context

FIGMA = "https://job-boards.greenhouse.io/figma/jobs/123"
ACME = "https://jobs.lever.co/acme/0b9c3b6e-1111-4222-8333-944445555666"
FARAWAY = "https://jobs.ashbyhq.com/faraway/1f2e3d4c-aaaa-4bbb-8ccc-0123456789ab"
GONE = "https://job-boards.greenhouse.io/oldco/jobs/9"
ACCOUNTANT = "https://job-boards.greenhouse.io/figma/jobs/777"
LINKEDIN = "https://www.linkedin.com/jobs/view/1"
LA = {"title": "senior product designer", "location": "Los Angeles, CA"}


def record(url, title, company, location, *, remote=None, source="greenhouse", comp=None):
    """A posting as `discovery.read_posting` reads it from its board."""
    ref = ats.detect(url)
    return {"dedupe_key": normalize.dedupe_key(company, title, location), "title": title, "company": company,
            "location": location, "remote": remote, "source": source, "source_url": url, "comp": comp or {},
            "ats": ref.view() if ref is not None else None}


PAY = {"base": {"status": "posted", "annual_min": 180000, "annual_max": 220000, "currency": "USD",
                "evidence": {"quote": "$180,000 - $220,000 USD", "origin": "ats_api"}}}


def state():
    return RunState(started=0.0, sessions={J.KEY: J.JobListingsSession()})


@pytest.fixture
def web(monkeypatch):
    """Brave: every search answers with `web.results` (or raises `web.error`)."""
    class Web:
        results: list[dict] = []
        asked: list[str] = []
        pages: list[int] = []
        error: Exception | None = None

    async def search(query, count, offset=0):
        Web.asked.append(query)
        Web.pages.append(offset)
        assert count == boards.RESULTS
        if Web.error is not None:
            raise Web.error
        return Web.results

    Web.asked, Web.pages = [], []
    monkeypatch.setattr(J, "_web_search", search)
    return Web


@pytest.fixture(autouse=True)
def stored(monkeypatch):
    """The postings earlier searches read, in memory; no answer here showed a job yet."""
    memory = MemoryStore()
    monkeypatch.setattr(J, "_store", memory.opener())
    shown: set[str] = set()

    async def shown_before(_ctx):
        return set(shown)

    monkeypatch.setattr(J, "_shown_before", shown_before)
    memory.shown = shown
    return memory


@pytest.fixture
def boards_read(monkeypatch):
    """The board APIs: url -> record (absent: no longer posted)."""
    posted: dict[str, dict] = {}
    reads: list[str] = []

    async def read(url):
        reads.append(url)
        return posted.get(url)

    monkeypatch.setattr(J, "_read", read)
    posted["reads"] = reads  # type: ignore[assignment]
    return posted


def links(*urls):
    return [{"url": u, "title": "t"} for u in urls]


async def find(st, **args):
    return await J.FIND_JOBS.handler(context(), st, args, 120)


def test_find_jobs_needs_brave_and_nothing_switched_on(monkeypatch):
    ability = J.build()
    assert ability.consent_version is None and not ability.private_only
    monkeypatch.setattr(brave_search, "available", lambda: True)
    assert catalog.availability(ability, catalog.Situation(private=False)).available
    monkeypatch.setattr(brave_search, "available", lambda: False)
    assert not catalog.availability(ability, catalog.Situation(private=True)).available


def test_ready_is_brave_answering(monkeypatch):
    monkeypatch.setattr(brave_search, "available", lambda: True)
    assert J._ready() is True

    def broken():
        raise RuntimeError("settings not loaded")

    monkeypatch.setattr(brave_search, "available", broken)
    assert J._ready() is False


@pytest.mark.asyncio
async def test_find_jobs_searches_the_boards_and_keeps_live_jobs_near_the_place(web, boards_read):
    """No Google Jobs (taken out 2026-10-18): Brave's board searches, each
    posting read on its board, kept for a related title in the place named."""
    web.results = links(FIGMA, ACME, FARAWAY, GONE, ACCOUNTANT, LINKEDIN)
    boards_read[FIGMA] = record(FIGMA, "Senior Product Designer", "Figma", "Los Angeles, CA", comp=PAY)
    boards_read[ACME] = record(ACME, "Senior Product Designer", "Acme", "Santa Monica, CA", source="lever")
    boards_read[FARAWAY] = record(FARAWAY, "Senior Product Designer", "Faraway", "New York, NY", source="ashby")
    boards_read[ACCOUNTANT] = record(ACCOUNTANT, "Staff Accountant", "Figma", "Los Angeles, CA")
    st = state()
    out = await find(st, **LA)
    criteria = {"titles": ["senior product designer"], "locations": ["Los Angeles, CA"], "remote": None}
    assert web.asked == boards.board_searches(["senior product designer"], criteria) and len(web.asked) == 8
    assert st.sessions[J.KEY].searches == 8
    # Each board posting read once, however many searches returned it; LinkedIn isn't a board.
    assert sorted(boards_read["reads"]) == sorted([FIGMA, ACME, FARAWAY, GONE, ACCOUNTANT])
    assert {k: out.payload[k] for k in ("new_jobs", "board_postings_found", "still_posted", "no_longer_posted",
                                        "other_roles", "left_out_elsewhere", "already_found")} == {
        "new_jobs": 2, "board_postings_found": 5, "still_posted": 4, "no_longer_posted": 1,
        "other_roles": 1, "left_out_elsewhere": 1, "already_found": 0}
    figma, acme = out.payload["jobs"]
    assert figma == ('J1 | Senior Product Designer | Figma | Los Angeles, CA | $180K–$220K ("$180,000 - $220,000 USD")'
                     f" | live at the employer (Greenhouse) | {FIGMA}")
    assert "Pay not posted" in acme and "live at the employer (Lever)" in acme and acme.endswith(ACME)
    assert out.provenance == frozenset({FIGMA, ACME})
    assert out.audit == {"title": "senior product designer", "location": "Los Angeles, CA", "searches": 8,
                         "links": 5, "read": 5, "reused": 0, "stored": 0, "posted": 4, "kept": 2}
    assert "note" not in out.payload and "not_read" not in out.payload


@pytest.mark.asyncio
async def test_a_job_found_twice_is_kept_once_and_remote_means_remote(web, boards_read, stored):
    remote_url, office_url = (f"https://jobs.lever.co/{c}/0b9c3b6e-1111-4222-8333-94444555566{n}"
                              for c, n in (("remoteco", 1), ("officeco", 2)))
    boards_read[remote_url] = record(remote_url, "Staff Engineer", "Remoteco", "Anywhere", remote=True, source="lever")
    boards_read[office_url] = record(office_url, "Staff Engineer", "Officeco", "Chicago, IL", remote=False,
                                     source="lever")
    web.results = links(remote_url, office_url)
    st = state()
    out = await find(st, title="staff engineer", location="Remote")
    assert out.payload["new_jobs"] == 1 and out.payload["jobs"][0].startswith("J1 | Staff Engineer | Remoteco")
    # Asked again: what this run read isn't read again, and Brave's answers
    # were all there was (under a page), so it isn't asked the same searches.
    asked = len(web.asked)
    again = await find(st, title="staff engineer", location="Remote")
    assert again.payload["new_jobs"] == 0 and again.payload["already_found"] == 1
    assert again.payload["note"].startswith("Every board search for that title and place was already read")
    assert len(boards_read["reads"]) == 2 and len(web.asked) == asked
    # The same job on another board (Greenhouse here, Lever before) is the same job.
    stored.sent_pages.clear()
    copy = "https://job-boards.greenhouse.io/remoteco/jobs/55"
    boards_read[copy] = record(copy, "Staff Engineer", "Remoteco", "Remote", remote=True)
    web.results = links(copy)
    third = await find(st, title="staff engineer", location="Remote")
    assert third.payload["new_jobs"] == 0 and third.payload["already_found"] == 2
    assert third.payload["note"] == "Every posting still up was already found in this run."


@pytest.mark.asyncio
async def test_brave_down_is_a_tool_error_and_one_failed_search_is_skipped(web, boards_read, monkeypatch):
    web.error = brave_search.Unavailable("no searches left", out=True)
    out = await find(state(), **LA)
    assert out.status == "error" and "Brave search isn't answering" in out.payload["error"]
    assert len(web.asked) == 1, "out: no more searches"
    # One search failing (not out) is skipped; the others still count.
    calls = []

    async def flaky(query, count, offset=0):
        calls.append(query)
        if len(calls) == 1:
            raise brave_search.Unavailable("503")
        return links(FIGMA)

    monkeypatch.setattr(J, "_web_search", flaky)
    boards_read[FIGMA] = record(FIGMA, "Senior Product Designer", "Figma", "Los Angeles, CA")
    out = await find(state(), **LA)
    assert len(calls) == 8 and out.payload["new_jobs"] == 1 and out.audit["searches"] == 7


@pytest.mark.asyncio
async def test_searches_stop_at_the_runs_budget(web, boards_read):
    st = state()
    st.sessions[J.KEY].searches = J.MAX_SEARCHES - 2
    await find(st, **LA)
    assert len(web.asked) == 2 and st.sessions[J.KEY].searches == J.MAX_SEARCHES
    spent = await find(st, **LA)
    assert spent.label == "Job search budget exhausted" and len(web.asked) == 2
    missing = await find(state(), title="  ")
    assert missing.status == "error" and "Say which role" in missing.payload["error"]


@pytest.mark.asyncio
async def test_searching_stops_when_it_runs_long(web, boards_read, monkeypatch):
    monkeypatch.setattr(J, "SEARCH_SECONDS", -1.0)
    await find(state(), **LA)
    assert len(web.asked) == 1, "the first search always runs"


@pytest.mark.asyncio
async def test_a_slow_read_is_stopped_and_tried_again_later(web, monkeypatch):
    stopped = []

    async def slow(url):
        try:
            await asyncio.sleep(30)
        except asyncio.CancelledError:
            stopped.append(url)
            raise

    monkeypatch.setattr(J, "_read", slow)
    monkeypatch.setattr(J, "READ_MARGIN", 0.0)
    web.results = links(FIGMA, ACME)
    st = state()
    # 0.2 s left in the run: the reads get that, then are stopped.
    out = await J.FIND_JOBS.handler(context(), st, LA, 0.2)
    assert out.payload["new_jobs"] == 0 and out.payload["not_read_in_time"] == 2
    assert out.payload["note"] == "The postings found couldn't be read in time. Try again."
    await asyncio.sleep(0)  # the reads called off get their cancellation
    assert sorted(stopped) == sorted([FIGMA, ACME])
    assert not st.sessions[J.KEY].read, "not read: a later call tries them again"
    # No time at all: nothing is started.
    none_left = await J.FIND_JOBS.handler(context(), state(), LA, 0.0)
    assert none_left.payload["not_read_in_time"] == 2


@pytest.mark.asyncio
async def test_a_read_that_breaks_counts_as_not_posted(web, monkeypatch):
    async def broken(url):
        raise RuntimeError("bad json")

    monkeypatch.setattr(J, "_read", broken)
    web.results = links(FIGMA)
    out = await find(state(), **LA)
    assert out.payload["no_longer_posted"] == 1
    assert out.payload["note"].startswith("None of the job-board postings found is still posted")


@pytest.mark.asyncio
async def test_more_links_than_a_call_reads(web, boards_read, monkeypatch):
    monkeypatch.setattr(J, "READS", 2)
    web.results = links(FIGMA, ACME, FARAWAY)
    out = await find(state(), **LA)
    assert len(boards_read["reads"]) == 2 and out.payload["not_read"].startswith("1 more board postings")


def studios(first, last):
    urls = [f"https://job-boards.greenhouse.io/studio{n:02d}/jobs/{n}" for n in range(first, last + 1)]
    return urls, {u: record(u, "Product Designer", f"Studio{n:02d}", "Los Angeles, CA")
                  for n, u in zip(range(first, last + 1), urls)}


@pytest.mark.asyncio
async def test_a_long_list_reaches_the_model_inside_the_output_budget(web, boards_read):
    urls, posted = studios(1, 30)
    boards_read.update(posted)
    web.results = links(*urls)
    st = state()
    ctx = context(limits=RunLimits(max_tool_output_chars=4000))
    out = await J.FIND_JOBS.handler(ctx, st, {"title": "product designer", "location": "Los Angeles, CA"}, 120)
    shown = out.payload["jobs"]
    assert 10 <= len(shown) < 30 and "not_shown_here" in out.payload and out.payload["new_jobs"] == 30
    block, warnings = J.gate_block("job_postings", {"job_ids": []}, st)
    assert len(block["jobs"]) == 30 and block["found"] == 30 and not warnings, "the block has every one"


@pytest.mark.asyncio
async def test_the_block_is_rebuilt_from_the_run(web, boards_read):
    urls, posted = studios(1, 3)
    boards_read.update(posted)
    web.results = links(*urls)
    st = state()
    await find(st, title="product designer", location="Los Angeles, CA")
    block, _ = J.gate_block("job_postings", {"job_ids": []}, st)
    assert [j["company"] for j in block["jobs"]] == ["Studio01", "Studio02", "Studio03"]
    first = block["jobs"][0]
    assert first["verified"] is True and first["at_employer"] is True and first["read_on"] == "Greenhouse"
    assert first["apply_url"] == urls[0] and "via" not in first and "posted" not in first
    picked, warnings = J.gate_block("job_postings", {"job_ids": ["j3", "J9"]}, st)
    assert [j["id"] for j in picked["jobs"]] == ["J3"] and warnings
    out, _ = result.normalize({"headline": "3 designer jobs", "summary": "Three."}, st, [J.build()])
    assert [b["type"] for b in out["blocks"]] == ["job_postings"]


def test_a_row_read_off_an_ats_names_where(monkeypatch):
    row = J.job_row(record("https://www.careers.example.com/1", "Designer", "Ex", "LA", source="web"))
    assert row["at_employer"] is False and row["read_on"] == "careers.example.com"
    assert J.model_line("J1", row).endswith("live on careers.example.com | https://www.careers.example.com/1")
    assert J.model_line("J2", {**row, "location": "", "remote": True, "apply_url": None}).split(" | ")[3] == "Remote"


@pytest.mark.parametrize("args, note", [
    ((0, 0, 0, 0, 0, 0, 0), "No Greenhouse, Lever or Ashby postings turned up"),
    ((3, 0, 3, 0, 2, 1, 0), "Every posting still up was another kind of role or outside the place asked for."),
    ((1, 0, 1, 0, 0, 0, 0), "Nothing new turned up."),
])
def test_empty_notes(args, note):
    assert J._empty_note(*args).startswith(note)


@pytest.mark.asyncio
async def test_a_board_link_is_read_through_the_job_searchs_reader(monkeypatch):
    from app.matcha.services.matcha_work.job_search import discovery

    seen = {}

    async def read_posting(posting, deps, take, *, today):
        seen.update(posting=posting, fetches=sum(1 for _ in iter(take, False)), today=today)
        return {"title": "x"}

    monkeypatch.setattr(discovery, "read_posting", read_posting)
    assert await J._read(FIGMA) == {"title": "x"}
    assert seen["posting"] == {"url": FIGMA, "title": "", "company": "", "location": ""}
    assert seen["fetches"] == J.READ_FETCHES


NEWJOB = "https://jobs.lever.co/newco/0b9c3b6e-1111-4222-8333-944445555777"


@pytest.mark.asyncio
async def test_asked_for_more_it_reads_the_next_page_and_only_new_postings(web, boards_read, stored, monkeypatch):
    """The 2026-10-19 follow-up ("any others?") sent the first answer's board
    searches again word for word and read the same postings again. Now a new
    run asks for each search's next page, uses what was read in the last
    hours, and counts the jobs already shown instead of listing them."""
    monkeypatch.setattr(boards, "RESULTS", 3)  # a full page here
    web.results = links(FIGMA, ACME, GONE)
    boards_read[FIGMA] = record(FIGMA, "Senior Product Designer", "Figma", "Los Angeles, CA", comp=PAY)
    boards_read[ACME] = record(ACME, "Senior Product Designer", "Acme", "Santa Monica, CA", source="lever")
    boards_read[GONE] = J._CLOSED
    first = await find(state(), **LA)
    assert first.payload["new_jobs"] == 2 and set(web.pages) == {0}
    assert len(stored.searched_pages) == 8 and not any(last for _q, _o, last in stored.searched_pages)
    # The first answer showed both (Figma's link written another way).
    stored.shown.update({FIGMA.replace("job-boards.", "boards.") + "?gh_jid=123", ACME})

    web.asked, web.pages = [], []
    boards_read["reads"].clear()
    web.results = links(FIGMA, ACME, NEWJOB)
    boards_read[NEWJOB] = record(NEWJOB, "Product Designer", "Newco", "Burbank, CA", source="lever")
    again = await find(state(), **LA)
    assert set(web.pages) == {1} and len(web.asked) == 8, "each search's next page"
    assert boards_read["reads"] == [NEWJOB], "the two live ones are as read; the closed one isn't asked for"
    assert again.payload["new_jobs"] == 1 and again.payload["jobs"][0].startswith("J1 | Product Designer | Newco")
    assert again.payload["shown_in_earlier_answers"] == 2 and "searched_further" in again.payload
    assert again.audit["reused"] == 2 and again.audit["stored"] == 2 and again.audit["read"] == 1


@pytest.mark.asyncio
async def test_a_posting_its_board_closed_is_skipped_next_time(web, boards_read, stored):
    web.results = links(GONE)
    boards_read[GONE] = J._CLOSED
    first = await find(state(), **LA)
    assert first.payload["no_longer_posted"] == 1 and boards_read["reads"] == [GONE]
    stored.sent_pages.clear()  # another search that turns it up again
    again = await find(state(), **LA)
    assert again.payload["no_longer_posted"] == 1 and boards_read["reads"] == [GONE], "not read again"
    # Couldn't be read (no answer either way): not stored, read next time.
    web.results = links(ACME)
    stored.sent_pages.clear()
    await find(state(), **LA)
    stored.sent_pages.clear()
    await find(state(), **LA)
    assert boards_read["reads"].count(ACME) == 2


@pytest.mark.asyncio
async def test_searches_read_to_their_end_still_bring_back_what_they_found(web, boards_read, stored):
    criteria = {"titles": ["senior product designer"], "locations": ["Los Angeles, CA"], "remote": None}
    for query in boards.board_searches(["senior product designer"], criteria):
        stored.sent_pages[query.lower()] = (1, True)
    stored.put(record(FIGMA, "Senior Product Designer", "Figma", "Los Angeles, CA"))
    stored.put(record(ACME, "Senior Product Designer", "Acme", "Santa Monica, CA", source="lever"), fresh=False)
    boards_read[ACME] = record(ACME, "Senior Product Designer", "Acme", "Santa Monica, CA", source="lever")
    out = await find(state(), **LA)
    assert web.asked == [] and boards_read["reads"] == [ACME], "only the one read long ago is read again"
    assert out.payload["new_jobs"] == 2 and out.audit["searches"] == 0 and out.audit["stored"] == 2
    # Nothing stored either: say so, and what to try.
    stored.rows.clear()
    empty = await find(state(), **LA)
    assert empty.payload["note"].startswith("Every board search for that title and place was already read")


@pytest.mark.asyncio
async def test_brave_down_still_answers_from_what_was_stored(web, boards_read, stored):
    web.error = brave_search.Unavailable("no searches left", out=True)
    stored.put(record(FIGMA, "Senior Product Designer", "Figma", "Los Angeles, CA"))
    out = await find(state(), **LA)
    assert out.status != "error" and out.payload["new_jobs"] == 1
    assert out.payload["searching"].startswith("Brave search isn't answering")


@pytest.mark.asyncio
async def test_a_page_is_remembered_only_once_its_postings_are_read(web, boards_read, stored, monkeypatch):
    monkeypatch.setattr(J, "READS", 1)
    web.results = links(FIGMA, ACME)
    boards_read[FIGMA] = record(FIGMA, "Senior Product Designer", "Figma", "Los Angeles, CA")
    out = await find(state(), **LA)
    assert out.payload["not_read"].startswith("1 more") and stored.searched_pages == []


def test_shown_links_reads_job_postings_blocks():
    results = [{"blocks": [{"type": "job_postings", "jobs": [{"apply_url": FIGMA}, {"apply_url": None}, "x"]},
                           {"type": "sources", "sources": [{"url": ACME}]}]},
               {"blocks": "not a list"}, "not a result", {}]
    assert J.shown_links(results) == {FIGMA}


@pytest.mark.asyncio
async def test_shown_before_reads_this_conversations_answers(monkeypatch):
    from uuid import uuid4

    from app import database

    from .helpers import FakeConn, connection

    monkeypatch.undo()  # the real seam, not the autouse stand-in
    assert await J._shown_before(context()) == set(), "no conversation, nothing shown"
    answer = {"schema": result.SCHEMA_VERSION, "headline": "3 jobs", "summary": "",
              "blocks": [{"type": "job_postings", "jobs": [{"id": "J1", "apply_url": FIGMA}]}]}
    conn = FakeConn().on("FROM mw_project_agent_runs", [{"result": answer}])
    monkeypatch.setattr(database, "connection_or_direct", connection(conn))
    ctx = context(channel_id=uuid4())
    assert await J._shown_before(ctx) == {FIGMA}
    assert conn.calls[0][2] == (ctx.channel_id, ctx.run_id, J.SHOWN_HOURS, J.SHOWN_RUNS)
    monkeypatch.setattr(database, "connection_or_direct", connection(FakeConn().on("FROM", RuntimeError("down"))))
    assert await J._shown_before(ctx) == set()


@pytest.mark.asyncio
async def test_a_read_its_board_said_is_closed_says_so(monkeypatch):
    from app.matcha.services.matcha_work.job_search import ats as ats_mod

    monkeypatch.setattr(ats_mod, "read", lambda ref, more=None: _done(ats_mod.AtsRead(None, closed=True)))
    assert await J._read(FIGMA) is J._CLOSED
    monkeypatch.setattr(ats_mod, "read", lambda ref, more=None: _done(ats_mod.AtsRead(None)))
    assert await J._read(FIGMA) is None


async def _done(value):
    return value


@pytest.mark.asyncio
async def test_the_store_seam_opens_its_own_connection(monkeypatch):
    from app import database

    from .helpers import FakeConn, connection

    monkeypatch.undo()
    conn = FakeConn()
    monkeypatch.setattr(database, "connection_or_direct", connection(conn))
    async with J._store() as store:
        assert store.conn is conn
