"""Discovery: Google Jobs when it's there, then the web, read posting by posting."""
import json
from collections import Counter
from datetime import date
from unittest.mock import AsyncMock
from uuid import uuid4

import pytest

from app.core.services.safe_fetch import FetchedResponse
from app.matcha.services.matcha_work.agent_runtime import chain, phase_run, runner
from app.matcha.services.matcha_work.agent_runtime.chain import PhaseFailed
from app.matcha.services.matcha_work.job_search import agent_phase, ats, discovery, phases
from tests.agent_runtime.helpers import FakeClient, FakeConn, call, connection, response, wire_store

from ._fixtures import SEARCH, TOKEN, search_row

GH = "https://job-boards.greenhouse.io/acme/jobs/4001"
LEVER = "https://jobs.lever.co/brightpath/0f6b2a4e-1111-2222-3333-444455556666"
NORTHWIND = "https://jobs.lever.co/northwind/0f6b2a4e-7777-2222-3333-444455556666"
GONE = "https://jobs.ashbyhq.com/gone/0f6b2a4e-8888-2222-3333-444455556666"
EXCLUDED = "https://boards.greenhouse.io/excluded/jobs/77"
TWIN = "https://boards.greenhouse.io/betainc/jobs/78"
PAGE = "https://careers.delta.test/jobs/cpo"
EXPIRED = "https://careers.delta.test/jobs/old"
KNOWN = "https://careers.beta.test/coo"
LINKEDIN = "https://www.linkedin.com/jobs/view/1"
INVENTED = "https://jobs.lever.co/made-up/0f6b2a4e-aaaa-bbbb-cccc-ddddeeeeffff"
GRANT = "RETURNING GREATEST(LEAST($2, $3 - cur.before), 0)"
NO_BOARD = AsyncMock(return_value=None)
REFUND = "SET fetch_calls = GREATEST(fetch_calls - $2, 0)"


@pytest.fixture
def conn(monkeypatch):
    conn = FakeConn()
    for module in (discovery, phases, agent_phase, phase_run, chain):
        monkeypatch.setattr(module, "connection_or_direct", connection(conn))
    wire_store(monkeypatch)
    monkeypatch.setattr(phase_run.store, "mark_run", AsyncMock())
    from app.matcha.services.billing import token_budget_service

    monkeypatch.setattr(token_budget_service, "deduct_tokens", AsyncMock())
    conn.on("INSERT INTO mw_project_agent_runs", uuid4())
    return conn


def guard():
    return phases.Guard(SEARCH, TOKEN)


def at_step(step, **cursor):
    return search_row(status="discovering", phase_cursor=json.dumps({"step": step, **cursor}),
                      plan=json.dumps({"titles": ["Chief People Officer"]}))


def searched(query, sources):
    return {"type": "web_search_call", "status": "completed",
            "action": {"type": "search", "query": query, "sources": [{"type": "url", "url": u} for u in sources]}}


def claim(url, title="Chief People Officer", company="Acme", location="San Diego, CA"):
    return {"url": url, "title": title, "company": company, "location": location}


# ── the steps ────────────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_a_search_starts_on_the_boards_with_no_google_jobs(conn, monkeypatch):
    """Brave and Claude only since 2026-10-18: a new search, or one whose cursor
    still says `listings` (in flight at the deploy), starts on the boards."""
    find = AsyncMock(return_value=([], True))
    monkeypatch.setattr(discovery.boards, "find", find)
    assert not hasattr(phases, "listings") and not hasattr(phases.Deps(), "provider")
    for cursor in ("{}", json.dumps({"step": "listings"})):
        out = await discovery.discover(search_row(status="discovering", phase_cursor=cursor), phases.Deps(), guard())
        assert out.status == "discovering" and out.cursor["step"] == "web" and out.cursor["boards_ok"] is True
    assert find.await_count == 2


@pytest.mark.asyncio
async def test_the_boards_are_searched_by_code_then_read(conn, monkeypatch):
    find = AsyncMock(return_value=([claim(GH, title="", company="", location="")], True))
    monkeypatch.setattr(discovery.boards, "find", find)
    out = await discovery.discover(places_search("boards"), phases.Deps(), guard())
    assert out.status == "discovering" and out.cursor["step"] == "read" and out.cursor["boards_ok"] is True
    assert [p["url"] for p in out.cursor["postings"]] == [GH]
    assert out.progress["note"] == "Reading 1 postings on employers' job boards…"
    titles, criteria = find.await_args.args[1:3]
    assert titles[0] == "Chief People Officer" and criteria["locations"][0] == "Orange County, CA"

    # Nothing on the boards: on to the web.
    find.return_value = ([], False)
    out = await discovery.discover(places_search("boards"), phases.Deps(), guard())
    assert out.cursor["step"] == "web" and out.cursor["boards_ok"] is False

    # Read: fewer than the target found, so the web next; enough, and it is skipped.
    conn.on("SELECT dedupe_key, title, company, source_url, apply_links FROM mw_job_leads", [])
    out = await discovery.discover(at_step("read", boards_ok=True, postings=[]), phases.Deps(), guard())
    assert out.cursor["step"] == "web"
    conn.on("SELECT COUNT(*) FROM mw_job_leads", 30)
    out = await discovery.discover(at_step("read", boards_ok=True, web_added=30, postings=[]),
                                   phases.Deps(), guard())
    assert out.status == "screening"


@pytest.mark.asyncio
async def test_boards_that_answered_count_as_searched(conn, monkeypatch):
    monkeypatch.setattr(discovery, "run_model_phase", AsyncMock(side_effect=runner.AgentRunError("down")))
    conn.on("SELECT COUNT(*) FROM mw_job_leads", 0)
    with pytest.raises(PhaseFailed, match="No postings matched"):
        await discovery.discover(at_step("web", boards_ok=True), phases.Deps(), guard())
    with pytest.raises(PhaseFailed, match="aren't available right now"):
        await discovery.discover(at_step("web", boards_ok=False), phases.Deps(), guard())


@pytest.mark.asyncio
async def test_a_web_run_hands_back_only_links_it_saw(conn):
    conn.on("SELECT title, company FROM mw_job_leads", [{"title": "COO", "company": "Beta"}])
    client = FakeClient([
        response(call("finish", {"result": {"postings": [
            claim(GH), claim(LEVER, company="Brightpath Health"), claim(PAGE, company="Delta"),
            claim(INVENTED), claim(GH),
        ]}}), output=[searched('"Chief People Officer" site:jobs.lever.co', [GH, LEVER, PAGE])]),
    ])
    deps = phases.Deps(client=lambda _model: client)
    search = at_step("web")
    search["use_resume"] = True
    out = await discovery.discover(search, deps, guard())

    assert out.status == "discovering" and out.cursor["step"] == "read"
    assert [p["url"] for p in out.cursor["postings"]] == [GH, LEVER, PAGE]  # not the invented one, once each
    assert out.cursor["web_runs"] == 1 and out.cursor["web_ok"] is True
    assert out.progress["note"] == "Reading 3 postings…"
    # The ask, settings, titles and searches go out, and what was already found; never the résumé.
    sent = json.dumps(client.calls[0]["input"], ensure_ascii=False)
    assert "Titles to look for: Chief People Officer" in sent and "COO — Beta" in sent
    assert "Run these searches first" in sent and '\\"Chief People Officer\\" site:apply.workable.com' in sent
    assert "<resume>" not in sent
    # Search only: code reads every posting, so the run loads no pages.
    tools = client.calls[0]["tools"]
    assert tools[0]["type"] == "web_search" and not any(t.get("name") == "fetch_page" for t in tools)
    [run] = conn.ran("INSERT INTO mw_project_agent_runs")
    assert run[2][2] == f"discover:{SEARCH}"
    assert not conn.ran("fetch_calls")


def test_a_read_posting_carries_only_its_own_location():
    """A web run's claim about where a job is never decides `places.fits`."""
    found = ats.AtsPosting(ref=ats.AtsRef("lever", "acme", "0f6b2a4e-1111-2222-3333-444455556666"), url=LEVER,
                           title="COO", location="")
    record = discovery._ats_record(found, claim(LEVER, location="San Diego, CA"))
    assert record["location"] == "" and record["state_code"] is None
    page = discovery._page_record({"title": "COO", "company": "Acme"}, PAGE, claim(PAGE, location="San Diego, CA"))
    assert page["location"] == ""


def test_the_search_ability_is_built_for_each_run(monkeypatch):
    """`web.search_tool` picks Brave or the hosted search for a run starting
    now; a module-level ability froze that choice for the process."""
    from app.matcha.services.matcha_work.agent_runtime.abilities import web

    picks = []
    monkeypatch.setattr(web, "search_tool", lambda **kw: picks.append(kw) or web.hosted_search_tool())
    assert discovery.search_only().key == "web" and discovery.search_only().key == "web"
    assert len(picks) == 2 and not hasattr(discovery, "SEARCH_ONLY")


@pytest.mark.asyncio
async def test_when_the_web_run_fails_or_finds_nothing(conn, monkeypatch):
    model = AsyncMock(side_effect=runner.AgentRunError("nothing usable"))
    monkeypatch.setattr(discovery, "run_model_phase", model)
    conn.on("SELECT COUNT(*) FROM mw_job_leads", 0)
    # No source could be searched: unavailable, and free.
    with pytest.raises(PhaseFailed, match="aren't available right now") as failed:
        await discovery.discover(at_step("web"), phases.Deps(), guard())
    assert "allowance" in str(failed.value)
    # A cursor from before 2026-10-18 saying Google Jobs ran no longer counts as searched.
    with pytest.raises(PhaseFailed, match="aren't available right now"):
        await discovery.discover(at_step("web", listings="ok"), phases.Deps(), guard())
    # The web run worked and found nothing.
    model.side_effect = None
    model.return_value = runner.RunOutcome(kind="result", result={"postings": []})
    with pytest.raises(PhaseFailed, match="No postings matched"):
        await discovery.discover(at_step("web"), phases.Deps(), guard())
    # Some jobs from the boards and nothing new on the web: on to screening.
    conn.on("SELECT COUNT(*) FROM mw_job_leads", 9)
    out = await discovery.discover(at_step("web", boards_ok=True), phases.Deps(), guard())
    assert out.status == "screening" and out.cursor == {} and out.progress["found"] == 9


@pytest.mark.asyncio
async def test_the_web_is_searched_at_most_twice_and_never_past_the_cap(conn, monkeypatch):
    model = AsyncMock()
    monkeypatch.setattr(discovery, "run_model_phase", model)
    conn.on("SELECT COUNT(*) FROM mw_job_leads", 31)
    out = await discovery.discover(at_step("web", web_runs=2, web_ok=True), phases.Deps(), guard())
    assert out.status == "screening"
    conn.on("SELECT title, company FROM mw_job_leads",
            [{"title": f"T{i}", "company": "C"} for i in range(phases.MAX_LEADS)])
    out = await discovery.discover(at_step("web"), phases.Deps(), guard())
    assert out.status == "screening"
    model.assert_not_awaited()


def places_search(step, **cursor):
    search = at_step(step, **cursor)
    search["plan"] = json.dumps({"titles": ["Chief People Officer", "Chief Human Resources Officer", "VP People"]})
    search["criteria"] = json.dumps({"locations": ["Orange County, CA", "San Diego, CA", "Los Angeles, CA"]})
    return search


@pytest.mark.asyncio
async def test_each_web_run_gets_its_share_of_the_searches(conn, monkeypatch):
    model = AsyncMock(return_value=runner.RunOutcome(kind="result", result={"postings": []}))
    monkeypatch.setattr(discovery, "run_model_phase", model)
    conn.on("SELECT COUNT(*) FROM mw_job_leads", 0)
    # The first run found nothing, and searches are left: search again.
    out = await discovery.discover(places_search("web"), phases.Deps(), guard())
    assert out.status == "discovering" and out.cursor["step"] == "web" and out.cursor["web_runs"] == 1
    assert out.progress["note"] == "Searching the web for more…"
    first = model.await_args.kwargs["user_text"]
    assert '"Chief People Officer" "Orange County, CA" job' in first
    assert '"VP People" "Los Angeles, CA" job' in first  # every title and place, first
    assert '"VP People" site:jobs.smartrecruiters.com' not in first
    with pytest.raises(PhaseFailed, match="No postings matched"):
        await discovery.discover(places_search("web", web_runs=1, web_ok=True),
                                 phases.Deps(), guard())
    second = model.await_args.kwargs["user_text"]
    assert '"VP People" site:jobs.smartrecruiters.com' in second
    assert '"Chief People Officer" "San Diego, CA" job' in second
    assert '"Chief People Officer" "Orange County, CA" job' not in second

    # After reading: a second run while searches are left, even when this one added nothing.
    conn.on("SELECT dedupe_key, title, company, source_url, apply_links FROM mw_job_leads", [])
    out = await discovery.discover(places_search("read", web_runs=1, web_ok=True, postings=[]),
                                   phases.Deps(), guard())
    assert out.status == "discovering" and out.cursor["step"] == "web"


def test_web_searches():
    """Greenhouse, Lever and Ashby are code's (`boards.py`): a web run looks
    in each place, then on the other boards."""
    titles = ["Chief People Officer", "CHRO", "VP People", "Head of People"]
    places = {"locations": ["Orange County, CA", "San Diego, CA", "Los Angeles, CA"]}
    three = discovery.web_searches(titles, places)
    # Each title and each place first (`phases.cover`), then the other boards, then the other pairs.
    assert three[:3] == ['"Chief People Officer" "Orange County, CA" job', '"CHRO" "San Diego, CA" job',
                         '"VP People" "Los Angeles, CA" job']
    assert three[3] == '"Chief People Officer" site:apply.workable.com'
    assert three[9] == '"Chief People Officer" "San Diego, CA" job'
    assert len(three) == discovery.MAX_SEARCHES and not any("Head of People" in q for q in three)
    # A fourth typed title (or kept direction) is searched too.
    assert any("Head of People" in q for q in discovery.web_searches(titles, places, must=4)[:4])
    assert not any(board in q for q in three for board in ("lever.co", "greenhouse.io", "ashbyhq.com"))
    assert discovery.web_searches(["COO"], {"locations": ["Austin, TX"]}) == [
        '"COO" "Austin, TX" job', '"COO" "Austin, TX" site:apply.workable.com',
        '"COO" "Austin, TX" site:jobs.smartrecruiters.com']
    assert discovery.web_searches(["COO"], {"locations": ["Remote", "United States"], "remote": "remote_only"}) == [
        '"COO" remote job opening', '"COO" "remote" site:apply.workable.com',
        '"COO" "remote" site:jobs.smartrecruiters.com']
    assert discovery.web_searches([], {"locations": ["Austin, TX"]}) == []


# ── reading the postings ─────────────────────────────────────────────────────

def ats_found(ref, url, title="Chief People Officer", company="", **over):
    return ats.AtsPosting(ref=ref, url=url, title=title, company=company,
                          location=over.pop("location", "San Diego, CA"), **over)


def fetched(body, final_url):
    return FetchedResponse(url=final_url, final_url=final_url, status=200, content_type="text/html",
                           body=body.encode(), truncated=False)


def jsonld(*jobs):
    blobs = "".join(f'<script type="application/ld+json">{json.dumps(job)}</script>' for job in jobs)
    return f"<html><head>{blobs}</head><body></body></html>"


DELTA_JOB = {"@type": "JobPosting", "title": "Chief People Officer", "hiringOrganization": {"name": "Delta"},
             "jobLocationType": "TELECOMMUTE",
             "baseSalary": {"currency": "USD", "value": {"minValue": 240000, "maxValue": 280000, "unitText": "YEAR"}},
             "description": "<p>Lead people.</p>", "validThrough": "2999-01-01"}


async def ats_fetch(ref, more=None):
    return {
        "4001": ats_found(ref, GH, company="Acme", description="The base salary is $250,000 - $300,000 per year.",
                          findings=[{"component": "base", "status": "posted", "min": 250000, "max": 300000,
                                     "currency": "USD", "period": "year", "annual_min": 250000,
                                     "annual_max": 300000, "evidence": {"quote": "x", "origin": "ats_api", "url": GH}}],
                          questions=[{"key": "q1", "label": "Why us?", "kind": "open"}]),
        "0f6b2a4e-1111-2222-3333-444455556666": ats_found(ref, LEVER, remote=False),
        "0f6b2a4e-7777-2222-3333-444455556666": ats_found(ref, NORTHWIND),
        "77": ats_found(ref, EXCLUDED, company="Excluded Co"),
        "78": ats_found(ref, TWIN, title="Chief Operating Officer", company="Beta Inc", location="Austin, TX"),
    }.get(ref.job_id)


async def page_fetch(url, **_kwargs):
    if url == PAGE:
        return fetched(jsonld(DELTA_JOB), PAGE)
    return fetched(jsonld({**DELTA_JOB, "validThrough": "2020-01-01"}), url)


@pytest.mark.asyncio
async def test_reading_keeps_live_new_postings_as_read_leads(conn):
    conn.on("SELECT dedupe_key, title, company, source_url, apply_links FROM mw_job_leads", [
        {"dedupe_key": "beta|chief operating officer|austin", "title": "Chief Operating Officer",
         "company": "Beta", "source_url": None, "apply_links": json.dumps([{"url": KNOWN, "source": "Beta"}])},
    ])
    conn.on(GRANT, lambda _id, want, _limit: want)
    conn.on("INSERT INTO mw_job_leads", 4)
    conn.on("SELECT COUNT(*) FROM mw_job_leads", 5)
    postings = [claim(GH), claim(LEVER, company="Brightpath Health"), claim(NORTHWIND, company="Someone Else"),
                claim(GONE), claim(EXCLUDED), claim(TWIN, title="COO", company="Beta Inc"),
                claim(PAGE, company="Delta"), claim(EXPIRED, company="Delta"), claim(KNOWN), claim(LINKEDIN)]
    search = at_step("read", web_runs=1, web_ok=True, postings=postings)
    search["criteria"] = json.dumps({"exclude_companies": ["excluded co"]})
    deps = phases.Deps(ats_find=NO_BOARD, ats_fetch=AsyncMock(side_effect=ats_fetch), page_fetch=AsyncMock(side_effect=page_fetch))
    out = await discovery.discover(search, deps, guard())

    # Added jobs, one run so far: look once more.
    assert out.status == "discovering" and out.cursor["step"] == "web"
    assert out.cursor["web_added"] == 4 and out.cursor["postings"] == []
    # What became of each of the ten, for the next search to be tuned by.
    assert out.progress == {"note": "Found 5 jobs so far; looking for more…", "found": 5, "reads": {"web": {
        "links": 10, "known": 1, "aggregator": 1, "unread": 2, "title": 1, "elsewhere": 1, "kept": 4,
    }}}
    # A known link and an aggregator are never read; one API read reserved
    # for each of the six board links, four for each of the two pages.
    assert conn.ran("SET fetch_calls = cur.before")[0][2] == (SEARCH, 6 + 2 * discovery.READS_PER_POSTING,
                                                              phases.MAX_FETCHES)
    assert all(c.args[0] not in (KNOWN, LINKEDIN) for c in deps.page_fetch.await_args_list)

    records = {r["company"]: r for r in json.loads(conn.ran("INSERT INTO mw_job_leads")[0][2][2])}
    assert sorted(records) == ["Acme", "Brightpath Health", "Delta", "Northwind"]
    acme = records["Acme"]
    assert acme["source"] == "greenhouse" and acme["enriched"] is True and acme["source_url"] == GH
    assert acme["apply_links"] == [{"url": GH, "source": "Greenhouse"}]
    assert acme["ats"]["questions"][0]["key"] == "q1" and acme["ats"]["board"] == "acme"
    assert acme["comp_status"] == "posted" and acme["comp_annual_max"] == 300000
    # Lever names no employer: the web run's name when it is the board's, else the board's own.
    assert records["Brightpath Health"]["source"] == "lever" and records["Northwind"]["state_code"] == "CA"
    delta = records["Delta"]
    assert delta["source"] == "web" and delta["remote"] is True and delta["ats"] is None
    assert delta["comp"]["base"]["evidence"]["origin"] == "jsonld"
    assert delta["apply_links"] == [{"url": PAGE, "source": "careers.delta.test"}]

    # A second run done: on to screening.
    search["phase_cursor"] = json.dumps({**json.loads(search["phase_cursor"]), "web_runs": 2})
    out = await discovery.discover(search, deps, guard())
    assert out.status == "screening" and out.cursor == {}


@pytest.mark.asyncio
async def test_reading_keeps_only_related_titles_in_the_places_named(conn):
    """A board search turns up any job that names a wanted title, anywhere:
    each is kept only for a related title, in or near a place named."""
    conn.on(GRANT, lambda _id, want, _limit: want)
    conn.on("INSERT INTO mw_job_leads", lambda *args: len(json.loads(args[2])))
    jobs = {
        "1": ("Chief People Officer", "Irvine, CA", None),        # 9 miles from Orange County
        "2": ("VP, People Operations", "Remote - US", True),      # remote, which they'd take
        "3": ("Chief People Officer", "Austin, TX", False),        # nowhere they named
        "4": ("Senior Software Engineer", "San Diego, CA", False),  # other work
        "5": ("Chief People Officer", "Remote - Canada", True),    # remote abroad
        "6": ("Head of HR", "", False),                            # no location
    }

    async def fetch(ref, more=None):
        title, location, remote = jobs[ref.job_id]
        return ats_found(ref, f"https://job-boards.greenhouse.io/co{ref.job_id}/jobs/{ref.job_id}", title=title,
                         company=f"Co {ref.job_id}", location=location, remote=remote)

    deps = phases.Deps(ats_find=NO_BOARD, ats_fetch=AsyncMock(side_effect=fetch), page_fetch=AsyncMock())
    postings = [{"url": f"https://job-boards.greenhouse.io/co{i}/jobs/{i}", "title": "", "company": "", "location": ""}
                for i in jobs]
    assert await discovery.read_postings(places_search("read"), deps, guard(), postings) == 2
    records = json.loads(conn.ran("INSERT INTO mw_job_leads")[0][2][2])
    assert [r["company"] for r in records] == ["Co 1", "Co 2"]
    # One API read reserved for each board link.
    assert conn.ran("SET fetch_calls = cur.before")[0][2] == (SEARCH, 6, phases.MAX_FETCHES)


@pytest.mark.asyncio
async def test_reading_with_no_room_or_nothing_new(conn):
    conn.on("SELECT dedupe_key, title, company, source_url, apply_links FROM mw_job_leads",
            [{"dedupe_key": f"k{i}", "title": "T", "company": "C", "source_url": f"https://x.test/{i}",
              "apply_links": "[]"} for i in range(phases.MAX_LEADS)])
    deps = phases.Deps(ats_find=NO_BOARD, ats_fetch=AsyncMock(), page_fetch=AsyncMock())
    assert await discovery.read_postings(search_row(), deps, guard(), [claim(GH)]) == 0
    conn.on("SELECT dedupe_key, title, company, source_url, apply_links FROM mw_job_leads", [])
    assert await discovery.read_postings(search_row(), deps, guard(), [claim(LINKEDIN), {"url": None}]) == 0
    deps.ats_fetch.assert_not_awaited()
    assert not conn.ran("SET fetch_calls = cur.before")


@pytest.mark.asyncio
async def test_a_read_that_breaks_skips_that_posting(conn):
    conn.on(GRANT, lambda _id, want, _limit: want)
    conn.on("INSERT INTO mw_job_leads", 1)

    async def flaky(ref, more=None):
        if ref.board == "brightpath":
            raise KeyError("a bug")
        return await ats_fetch(ref)

    deps = phases.Deps(ats_find=NO_BOARD, ats_fetch=AsyncMock(side_effect=flaky), page_fetch=AsyncMock())
    assert await discovery.read_postings(at_step("read"), deps, guard(), [claim(GH), claim(LEVER)]) == 1
    records = json.loads(conn.ran("INSERT INTO mw_job_leads")[0][2][2])
    assert [r["source_url"] for r in records] == [GH]


@pytest.mark.asyncio
async def test_read_posting_edges():
    today = date(2026, 10, 16)
    nothing_left = lambda: False  # noqa: E731
    deps = phases.Deps(ats_find=NO_BOARD, ats_fetch=AsyncMock(side_effect=ats_fetch), page_fetch=AsyncMock(side_effect=page_fetch))
    assert await discovery.read_posting(claim(GH), deps, nothing_left, today=today) is None
    assert await discovery.read_posting(claim(PAGE), deps, nothing_left, today=today) is None

    # A careers page that redirected into an ATS is read as that ATS.
    redirected = phases.Deps(ats_find=NO_BOARD, ats_fetch=AsyncMock(side_effect=ats_fetch),
                             page_fetch=AsyncMock(return_value=fetched("<html></html>", GH)))
    record = await discovery.read_posting(claim("https://acme.test/careers/cpo"), redirected, lambda: True, today=today)
    assert record["source"] == "greenhouse" and record["company"] == "Acme"

    # A page listing several jobs: the one with the title the run gave, or none.
    other = {**DELTA_JOB, "title": "Director of Facilities"}
    several = phases.Deps(ats_find=NO_BOARD, ats_fetch=AsyncMock(), page_fetch=AsyncMock(return_value=fetched(jsonld(other, DELTA_JOB), PAGE)))
    record = await discovery.read_posting(claim(PAGE), several, lambda: True, today=today)
    assert record["title"] == "Chief People Officer"
    record = await discovery.read_posting(claim(PAGE, title="Chief Financial Officer"), several, lambda: True, today=today)
    assert record is None

    # Unreadable: a page that won't load, or one with no posting on it.
    broken = phases.Deps(ats_find=NO_BOARD, ats_fetch=AsyncMock(), page_fetch=AsyncMock(side_effect=TimeoutError()))
    assert await discovery.read_posting(claim(PAGE), broken, lambda: True, today=today) is None
    bare = phases.Deps(ats_find=NO_BOARD, ats_fetch=AsyncMock(), page_fetch=AsyncMock(return_value=fetched("<html>hi</html>", PAGE)))
    assert await discovery.read_posting(claim(PAGE), bare, lambda: True, today=today) is None


@pytest.mark.asyncio
async def test_a_workable_posting_is_read_from_workable():
    """The web run's Workable links were dropped before Workable could be read
    (prod, 2026-10-17): now it is an ATS like the others, its form a second
    fetch paid as it is asked (`ats.fetch(more=...)`)."""
    today = date(2026, 10, 18)
    url = "https://apply.workable.com/delta-health/j/B688C603EB/"
    found = ats_found(ats.detect(url), url, location="San Diego, California, United States",
                      questions=[{"key": "QA_1", "label": "Why us?", "kind": "open"}])
    deps = phases.Deps(ats_find=NO_BOARD, ats_fetch=AsyncMock(return_value=found), page_fetch=AsyncMock())
    record = await discovery.read_posting(claim(url, company="Delta Health"), deps, lambda: True, today=today)
    assert record["source"] == "workable" and record["company"] == "Delta Health"
    assert record["apply_links"] == [{"url": url, "source": "Workable"}]
    assert record["ats"]["provider"] == "workable" and record["ats"]["questions"][0]["key"] == "QA_1"
    deps.page_fetch.assert_not_awaited()
    # The form is paid with `more`, from the same budget.
    assert deps.ats_fetch.await_args.kwargs["more"]() is True
    # One fetch left: the posting, read without its form; none: not read.
    asked = []

    async def formless(ref, more=None):
        asked.append(more())
        return found

    one_left = phases.Deps(ats_find=NO_BOARD, ats_fetch=formless, page_fetch=AsyncMock())
    left = iter([True, False])
    assert (await discovery.read_posting(claim(url), one_left, lambda: next(left), today=today))["source"] == "workable"
    assert asked == [False]
    none_left = phases.Deps(ats_find=NO_BOARD, ats_fetch=AsyncMock(return_value=found), page_fetch=AsyncMock())
    assert await discovery.read_posting(claim(url), none_left, lambda: False, today=today) is None
    none_left.ats_fetch.assert_not_awaited()


@pytest.mark.asyncio
async def test_an_unreadable_careers_page_is_looked_up_on_the_employers_board():
    today = date(2026, 10, 16)
    challenge = FetchedResponse(url=PAGE, final_url=PAGE, status=202, content_type="text/html",
                                body=b"<html>checking your browser</html>", truncated=False)
    on_board = ats_found(ats.AtsRef("greenhouse", "delta", "9"), "https://job-boards.greenhouse.io/delta/jobs/9",
                         company="Delta")

    def deps(found):
        return phases.Deps(ats_find=AsyncMock(return_value=found), ats_fetch=AsyncMock(),
                           page_fetch=AsyncMock(return_value=challenge))

    found = deps(on_board)
    record = await discovery.read_posting(claim(PAGE, company="Delta"), found, lambda: True, today=today)
    assert record["source"] == "greenhouse" and record["source_url"].endswith("/delta/jobs/9")
    assert found.ats_find.await_args.args == ("Delta", "Chief People Officer")
    # Another title, or another employer, is not this job.
    other = ats_found(on_board.ref, on_board.url, title="Payroll Specialist", company="Delta")
    assert await discovery.read_posting(claim(PAGE, company="Delta"), deps(other), lambda: True, today=today) is None
    elsewhere = ats_found(on_board.ref, on_board.url, company="Northwind Traders")
    assert await discovery.read_posting(claim(PAGE, company="Delta"), deps(elsewhere), lambda: True, today=today) is None
    # One posting's share: the page, then three looks at the board at most.
    asked = []

    async def look(_company, _title, *, take):
        while take():
            asked.append(1)
        return None

    capped = phases.Deps(ats_find=look, ats_fetch=AsyncMock(), page_fetch=AsyncMock(return_value=challenge))
    assert await discovery.read_posting(claim(PAGE), capped, lambda: True, today=today) is None
    assert len(asked) == discovery.READS_PER_POSTING - 1


@pytest.mark.asyncio
async def test_reads_still_loading_at_the_deadline_are_dropped(conn, monkeypatch):
    import asyncio

    conn.on(GRANT, lambda _id, want, _limit: want)
    conn.on("INSERT INTO mw_job_leads", 1)
    monkeypatch.setattr(discovery, "READ_SECONDS", 0.05)

    async def slow(ref, more=None):
        if ref.board == "brightpath":
            await asyncio.sleep(5)
        return await ats_fetch(ref)

    async def slow_page(_url, **_kwargs):
        await asyncio.sleep(5)

    deps = phases.Deps(ats_find=NO_BOARD, ats_fetch=AsyncMock(side_effect=slow),
                       page_fetch=AsyncMock(side_effect=slow_page))
    assert await discovery.read_postings(at_step("read"), deps, guard(), [claim(GH), claim(LEVER), claim(PAGE)]) == 1
    assert [r["source_url"] for r in json.loads(conn.ran("INSERT INTO mw_job_leads")[0][2][2])] == [GH]
    # The slow page's unused reservation goes back with the rest.
    assert conn.ran(REFUND)[0][2] == (SEARCH, discovery.READS_PER_POSTING - 1)


@pytest.mark.asyncio
async def test_hostile_markup_is_a_page_with_no_posting(monkeypatch):
    def explode(_body, _url):
        raise RecursionError("absurd nesting")

    monkeypatch.setattr(phases, "job_postings", explode)
    deps = phases.Deps(ats_find=NO_BOARD, ats_fetch=AsyncMock(), page_fetch=AsyncMock(return_value=fetched(jsonld(DELTA_JOB), PAGE)))
    assert await discovery.read_posting(claim(PAGE), deps, lambda: True, today=date(2026, 10, 16)) is None


def test_small_helpers():
    assert discovery._text("Chief People Officer &#8211; San Diego") == "Chief People Officer – San Diego"
    assert discovery._board_name("acme-health_inc") == "Acme Health Inc"
    assert discovery._expired({"valid_through": "soon"}, date(2026, 10, 16)) is False
    assert discovery._expired({"valid_through": "2026-10-15T23:59:00Z"}, date(2026, 10, 16)) is True
    assert discovery._expired({}, date(2026, 10, 16)) is False


@pytest.mark.asyncio
async def test_each_read_says_what_became_of_its_postings(conn):
    """A dev search read 160 board links, kept 21 and said nothing about the
    other 139 (2026-10-19). Each read counts what became of each posting, and
    adds it to the search's earlier reads under where they came from."""
    conn.on("SELECT dedupe_key, title, company, source_url, apply_links FROM mw_job_leads", [
        {"dedupe_key": "beta|chief operating officer|austin", "title": "Chief Operating Officer",
         "company": "Beta", "source_url": None, "apply_links": "[]"},
    ])
    conn.on(GRANT, lambda _id, want, _limit: want)
    deps = phases.Deps(ats_find=NO_BOARD, ats_fetch=AsyncMock(side_effect=ats_fetch),
                       page_fetch=AsyncMock(side_effect=page_fetch))
    tally = Counter()
    twin = claim(TWIN, title="COO", company="Beta Inc")  # reads back as Beta's Chief Operating Officer
    assert await discovery.read_postings(search_row(), deps, guard(), [twin], tally) == 0
    assert +tally == Counter(links=1, duplicate=1)

    search = search_row(progress=json.dumps({"note": "x", "reads": {"boards": {"links": 5, "kept": 2}}}))
    assert discovery.add_reads(search, "boards", Counter(links=3, unread=1, kept=1)) == {
        "boards": {"links": 8, "unread": 1, "kept": 3}}
    assert discovery.add_reads(search, "web", Counter(links=2, kept=0)) == {
        "boards": {"links": 5, "kept": 2}, "web": {"links": 2}}
