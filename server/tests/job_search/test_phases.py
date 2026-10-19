"""Plan fallback, where a job is kept, and enrich, against a scripted ATS and web."""
import json
from unittest.mock import AsyncMock
from uuid import uuid4

import pytest

from app.core.services.safe_fetch import FetchedResponse, UnsafeURL
from app.matcha.services.matcha_work.agent_runtime import chain
from app.matcha.services.matcha_work.job_search import ats, contracts, phases
from tests.agent_runtime.helpers import FakeConn, connection

from ._fixtures import SEARCH, TOKEN, search_row

GH_URL = "https://boards.greenhouse.io/acme/jobs/123"


def test_plan_from_criteria():
    """Titles to search, as they typed them (or the role their ask names): no
    Google Jobs queries since 2026-10-18."""
    plan = phases.plan_from_criteria("COO roles", {"titles": [" COO ", "Chief  Operating Officer", "coo", ""],
                                                   "locations": ["Austin, TX", "Remote"]})
    assert plan == {"titles": ["COO", "Chief Operating Officer"], "source": "criteria"}
    # Every search quotes its titles, so an ask is never searched as a sentence.
    assert phases.plan_from_criteria("  COO   jobs paying equity ", {})["titles"] == ["COO"]
    many = phases.plan_from_criteria("x", {"titles": [f"T{i}" for i in range(20)]})
    assert len(many["titles"]) == contracts.MAX_TITLES
    assert phases.titles_in("not a list") == []


@pytest.mark.parametrize("ask, title", [
    ("Find me a senior product designer job in Austin that pays 150k", "senior product designer"),
    ("I'm looking for remote COO roles at startups", "COO"),
    ("I want a job as a dental hygienist in San Diego", "dental hygienist"),
    ("Please find me a full-time Staff Software Engineer, backend", "Staff Software Engineer"),
    ("Head of Growth for fintech", "Head of Growth"),
    ("VP of Operations", "VP of Operations"),
    ("nurse jobs near me", "nurse"),
    ("Chief Executive Officer of a large global technology holding company", "Chief Executive Officer of a large"),
    ("something in operations, maybe chief of staff", ""),
    ("", ""),
])
def test_the_role_an_ask_names(ask, title):
    assert phases.title_from_ask(ask) == title


def test_every_typed_title_and_direction_is_searched():
    criteria = {"titles": ["COO", "VP Operations", "Head of Ops"]}
    plan = {"directions": [{"title": "Chief of Staff"}, {"title": "coo"}, "junk"]}
    assert phases.must_search(criteria, plan) == 4  # "coo" is one they typed
    assert phases.must_search({}, {}) == 0
    assert phases.cover(["a", "b", "c"], ["x", "y"]) == [
        ("a", "x"), ("b", "y"), ("c", "x"), ("a", "y"), ("b", "x"), ("c", "y")]
    assert phases.cover([], ["x"]) == [] and phases.cover(["a"], []) == []


@pytest.fixture
def conn(monkeypatch):
    conn = FakeConn()
    monkeypatch.setattr(phases, "connection_or_direct", connection(conn))
    # Guard, grant and refund run in agent_runtime.chain.
    monkeypatch.setattr(chain, "connection_or_direct", connection(conn))
    return conn


def guard():
    return phases.Guard(SEARCH, TOKEN)


def test_a_job_is_kept_only_in_the_places_named_and_the_way_they_asked():
    criteria = {"locations": ["Austin, TX"], "remote": "any"}
    assert phases.keep_job("Acme", None, criteria, "Round Rock, TX")  # 17 miles
    assert not phases.keep_job("Acme", None, criteria, "Dallas, TX")
    assert phases.keep_job("Acme", True, criteria, "Remote")
    assert not phases.keep_job("Acme", True, {**criteria, "remote": "onsite_only"}, "Remote")
    assert not phases.keep_job("Acme", False, {"remote": "remote_only"}, "Austin, TX")
    assert not phases.keep_job("Excluded Co", True, {"exclude_companies": ["excluded co"]}, "Remote")
    # No places, or only nationwide ones: anywhere.
    assert phases.keep_job("Acme", False, {"locations": []}, "Dallas, TX")
    assert phases.keep_job("Acme", False, {"locations": ["United States"]}, "Dallas, TX")


@pytest.mark.asyncio
async def test_new_leads_are_written_under_the_token(conn):
    conn.on("INSERT INTO mw_job_leads", 2)
    search = search_row(status="discovering")
    assert await phases.insert_leads(search, TOKEN, []) == 0
    assert await phases.insert_leads(search, TOKEN, [{"dedupe_key": "a"}, {"dedupe_key": "b"}]) == 2
    [write] = conn.ran("INSERT INTO mw_job_leads")
    assert write[2][3] == TOKEN and "dispatch_token = $4" in write[1]


def ats_posting(**over):
    base = dict(
        ref=ats.AtsRef("greenhouse", "acme", "123"), url=GH_URL, title="COO", location="Austin, TX",
        remote=False, description="Full description. The base salary is $260,000 - $310,000 per year.",
        findings=[{"component": "base", "status": "posted", "min": 260000, "max": 310000, "currency": "USD",
                   "period": "year", "annual_min": 260000, "annual_max": 310000,
                   "evidence": {"quote": "x", "origin": "ats_api", "url": GH_URL}}],
        questions=[{"key": "q1", "label": "Why us?", "kind": "open"}],
    )
    base.update(over)
    return ats.AtsPosting(**base)


def page(body, status=200, ctype="text/html", final_url="https://careers.delta.test/coo"):
    return FetchedResponse(url=final_url, final_url=final_url, status=status, content_type=ctype,
                           body=body.encode() if isinstance(body, str) else body, truncated=False)


JSONLD_PAGE = """<html><head><script type="application/ld+json">{"@type": "JobPosting",
"title": "Chief Operating Officer", "url": "https://careers.delta.test/coo",
"baseSalary": {"currency": "USD", "value": {"minValue": 230000, "maxValue": 270000, "unitText": "YEAR"}},
"jobLocationType": "TELECOMMUTE", "description": "<p>Run operations. Annual bonus target of 25%.</p>"}
</script></head><body></body></html>"""


def lead(links, **over):
    return {"id": uuid4(), "title": "Chief Operating Officer", "comp": "{}", "description": "short",
            "apply_links": json.dumps([{"url": u, "source": "s"} for u in links]), **over}


@pytest.mark.asyncio
async def test_enrich_one_prefers_the_ats():
    deps = phases.Deps(ats_fetch=AsyncMock(return_value=ats_posting()), page_fetch=AsyncMock())
    budget = phases.Budget(left=5)
    update = await phases.enrich_one(lead(["https://www.linkedin.com/jobs/1", GH_URL]), deps, budget)
    assert update["source"] == "greenhouse" and update["ats"]["questions"][0]["key"] == "q1"
    assert update["comp"]["base"]["annual_max"] == 310000 and update["description"].startswith("Full")
    deps.page_fetch.assert_not_awaited()
    assert budget.used == 1


def workable_fetch(posting):
    """`ats.fetch` for a Workable posting: pays for its form with `more()`."""
    async def fetch(ref, *, more=None):
        fetch.formless = more is not None and not more()
        return posting

    fetch.formless = False
    return fetch


@pytest.mark.asyncio
async def test_enrich_one_pays_for_both_workable_calls():
    url = "https://apply.workable.com/delta/j/9A1F916774/"
    posting = ats_posting(ref=ats.AtsRef("workable", "delta", "9A1F916774"), url=url)
    deps = phases.Deps(ats_fetch=workable_fetch(posting), page_fetch=AsyncMock())
    budget = phases.Budget(left=5)
    update = await phases.enrich_one(lead([url]), deps, budget)
    assert update["source"] == "workable" and budget.used == 2
    # One fetch left: read, without its form (nothing paid for and lost).
    short = phases.Deps(ats_fetch=workable_fetch(posting), page_fetch=AsyncMock())
    budget = phases.Budget(left=1)
    assert (await phases.enrich_one(lead([url]), short, budget))["source"] == "workable"
    assert budget.used == 1 and short.ats_fetch.formless
    # None left: not tried, so the lead is read in a later batch.
    assert await phases.enrich_one(lead([url]), short, phases.Budget(left=0)) is phases.NOT_TRIED


@pytest.mark.asyncio
async def test_enrich_one_reads_the_company_page():
    deps = phases.Deps(ats_fetch=AsyncMock(return_value=None), page_fetch=AsyncMock(return_value=page(JSONLD_PAGE)))
    update = await phases.enrich_one(
        lead(["https://www.indeed.com/viewjob?jk=1", "https://careers.delta.test/coo"]), deps, phases.Budget(left=5))
    assert update["source"] == "web" and update["remote"] is True
    assert update["comp"]["base"]["evidence"]["origin"] == "jsonld"
    assert update["comp"]["bonus"]["pct_min"] == 25
    assert deps.page_fetch.await_args.args[0] == "https://careers.delta.test/coo"


@pytest.mark.asyncio
async def test_enrich_one_follows_a_careers_redirect_into_the_ats():
    deps = phases.Deps(ats_fetch=AsyncMock(return_value=ats_posting()),
                       page_fetch=AsyncMock(return_value=page("<html></html>", final_url=GH_URL)))
    update = await phases.enrich_one(lead(["https://delta.test/careers/coo"]), deps, phases.Budget(left=5))
    assert update["source"] == "greenhouse"


@pytest.mark.asyncio
async def test_a_careers_redirect_into_workable_pays_for_both_calls():
    url = "https://apply.workable.com/delta/j/9A1F916774/"
    posting = ats_posting(ref=ats.AtsRef("workable", "delta", "9A1F916774"), url=url)
    deps = phases.Deps(ats_fetch=workable_fetch(posting),
                       page_fetch=AsyncMock(return_value=page("<html></html>", final_url=url)))
    budget = phases.Budget(left=3)
    update = await phases.enrich_one(lead(["https://delta.test/careers/coo"]), deps, budget)
    assert update["source"] == "workable" and budget.used == 3
    # The page paid for, one call left: Workable read without its form.
    short = phases.Deps(ats_fetch=workable_fetch(posting),
                        page_fetch=AsyncMock(return_value=page("<html></html>", final_url=url)))
    read = await phases.read_job_page("https://delta.test/careers/coo", short, iter([True, False]).__next__)
    assert read.posting is posting and short.ats_fetch.formless
    # None left: not read through it.
    none = phases.Deps(ats_fetch=AsyncMock(return_value=posting),
                       page_fetch=AsyncMock(return_value=page("<html></html>", final_url=url)))
    assert (await phases.read_job_page("https://delta.test/careers/coo", none, iter([False]).__next__)).posting is None
    none.ats_fetch.assert_not_awaited()


@pytest.mark.asyncio
async def test_enrich_one_gives_up_quietly():
    aggregator_only = phases.Deps(ats_fetch=AsyncMock(), page_fetch=AsyncMock())
    assert await phases.enrich_one(lead(["https://www.linkedin.com/jobs/1"]), aggregator_only,
                                   phases.Budget(left=5)) is None
    aggregator_only.page_fetch.assert_not_awaited()
    # Out of granted fetches: not tried, so the lead stays unread for later.
    budget = phases.Budget(left=0)
    assert await phases.enrich_one(lead([GH_URL]), aggregator_only, budget) is phases.NOT_TRIED
    assert budget.exhausted
    for result in (page("", status=404), page("{}", ctype="application/json"), page("<html>no ld</html>")):
        deps = phases.Deps(ats_fetch=AsyncMock(), page_fetch=AsyncMock(return_value=result))
        assert await phases.enrich_one(lead(["https://delta.test/coo"]), deps, phases.Budget(left=5)) is None
    for exc in (UnsafeURL("private"), TimeoutError(), RuntimeError("weird")):
        deps = phases.Deps(ats_fetch=AsyncMock(), page_fetch=AsyncMock(side_effect=exc))
        assert await phases.enrich_one(lead(["https://delta.test/coo"]), deps, phases.Budget(left=5)) is None


def no_board():
    return AsyncMock(return_value=None)


@pytest.mark.asyncio
async def test_enrich_one_passes_over_another_employers_posting():
    # Google listed Headway's job among Flex's apply links (2026-10-15 audit).
    headway = ats_posting(ref=ats.AtsRef("ashby", "headway", "1"), title="Director, Chief of Staff – R&D")
    flex = ats_posting(ref=ats.AtsRef("greenhouse", "flex", "7"), title="Chief of Staff and VP of Strategy",
                       company="Flex")
    deps = phases.Deps(ats_fetch=AsyncMock(side_effect=[headway, flex]), page_fetch=AsyncMock(), ats_find=no_board())
    links = [f"https://jobs.ashbyhq.com/headway/{'1' * 8}-1111-4111-8111-{'1' * 12}", GH_URL]
    update = await phases.enrich_one(lead(links, title="Chief of Staff and VP of Strategy", company="Flex"),
                                     deps, phases.Budget(left=9))
    assert update["ats"]["board"] == "flex"

    # The same title at another employer is not the job either.
    other = ats_posting(company="VVater")
    deps = phases.Deps(ats_fetch=AsyncMock(return_value=other), page_fetch=AsyncMock(), ats_find=no_board())
    assert await phases.enrich_one(lead([GH_URL], company="American Alchemy"), deps,
                                   phases.Budget(left=9)) is None
    deps.ats_find.assert_awaited_once()


SPECIAL_PROJECTS = JSONLD_PAGE.replace('"title": "Chief Operating Officer"', '"title": "Special Projects Lead"')


@pytest.mark.asyncio
async def test_enrich_one_skips_a_page_about_another_job():
    deps = phases.Deps(ats_fetch=AsyncMock(), ats_find=no_board(),
                       page_fetch=AsyncMock(side_effect=[page(SPECIAL_PROJECTS), page(JSONLD_PAGE)]))
    update = await phases.enrich_one(lead(["https://talents.example.test/x", "https://careers.delta.test/coo"]),
                                     deps, phases.Budget(left=9))
    assert update["source_url"] == "https://careers.delta.test/coo"
    # A careers page redirecting into another employer's ATS is passed over too.
    deps = phases.Deps(ats_fetch=AsyncMock(return_value=ats_posting(company="Headway")), ats_find=no_board(),
                       page_fetch=AsyncMock(return_value=page("<html></html>", final_url=GH_URL)))
    assert await phases.enrich_one(lead(["https://delta.test/careers/coo"], company="Delta"), deps,
                                   phases.Budget(left=9)) is None


@pytest.mark.asyncio
async def test_enrich_one_looks_on_the_employers_own_board():
    found = ats_posting(company="Nametag")
    deps = phases.Deps(ats_fetch=AsyncMock(), page_fetch=AsyncMock(), ats_find=AsyncMock(return_value=found))
    update = await phases.enrich_one(lead(["https://www.linkedin.com/jobs/1"], company="Nametag"), deps,
                                     phases.Budget(left=9))
    assert update["source"] == "greenhouse"
    company, title = deps.ats_find.await_args.args
    assert (company, title) == ("Nametag", "Chief Operating Officer")

    # One lead spends at most LEAD_FETCHES, however many guesses it could make.
    budget = phases.Budget(left=50)

    async def greedy(_company, _title, *, take):
        while take():
            pass
    deps = phases.Deps(ats_fetch=AsyncMock(), page_fetch=AsyncMock(), ats_find=AsyncMock(side_effect=greedy))
    assert await phases.enrich_one(lead([], company="Acme"), deps, budget) is None
    assert budget.used == phases.LEAD_FETCHES and not budget.exhausted

    # No budget at all: not tried, so it stays unread for a later batch.
    budget = phases.Budget(left=0)
    deps = phases.Deps(ats_fetch=AsyncMock(), page_fetch=AsyncMock(), ats_find=AsyncMock(side_effect=greedy))
    assert await phases.enrich_one(lead([], company="Acme"), deps, budget) is phases.NOT_TRIED
    budget = phases.Budget(left=0)
    assert await phases.enrich_one(lead(["https://delta.test/coo"]), deps, budget) is phases.NOT_TRIED


@pytest.mark.asyncio
async def test_enrich_phase_batches_then_ranks(conn, monkeypatch):
    rerank = AsyncMock(return_value=2)
    monkeypatch.setattr(phases, "rerank", rerank)
    leads = [lead([GH_URL]), lead(["https://www.linkedin.com/x"])]
    conn.on("AND enriched_at IS NULL AND screen_status <> 'irrelevant' AND (fit_score IS NULL OR fit_score >= $2)\n                ORDER BY",
            leads)
    conn.on("SELECT COUNT(*) FROM mw_job_leads WHERE search_id = $1\n               AND enriched_at IS NULL", 5)
    conn.on("COUNT(*) FILTER", {"total": 7, "posted": 3})
    conn.on("RETURNING GREATEST(LEAST($2, $3 - cur.before), 0)", 4)
    deps = phases.Deps(ats_fetch=AsyncMock(return_value=ats_posting()), page_fetch=AsyncMock())
    search = search_row(status="enriching", fetch_calls=0)
    out = await phases.enrich(search, deps, guard())
    assert out.status == "enriching"  # more to read
    saves = conn.ran("enriched_at = NOW()")
    assert len(saves) == 2 and all(s[2][2] == TOKEN for s in saves)
    assert conn.ran("SET fetch_calls = cur.before")[0][2] == (SEARCH, 2 * phases.LEAD_FETCHES,
                                                           phases.MAX_FETCHES)
    assert conn.ran("SET fetch_calls = GREATEST(fetch_calls - $2, 0)")[0][2] == (SEARCH, 3)
    rerank.assert_not_awaited()

    conn.on("SELECT COUNT(*) FROM mw_job_leads WHERE search_id = $1\n               AND enriched_at IS NULL", 0)
    conn.on("SELECT 1 FROM mw_job_searches WHERE id = $1 AND dispatch_token = $2", 1)
    conn.on("SET progress = progress || $2::jsonb", search)
    out = await phases.enrich(search, deps, guard())
    assert out.status == "done" and out.progress["posted_pay"] == 3 and out.progress["ranked"] is True
    rerank.assert_awaited_once()

    # Out of page loads: rank what there is, and mark nothing read.
    rerank.reset_mock()
    conn.calls.clear()
    conn.on("SELECT COUNT(*) FROM mw_job_leads WHERE search_id = $1\n               AND enriched_at IS NULL", 5)
    conn.on("RETURNING GREATEST(LEAST($2, $3 - cur.before), 0)", 0)
    out = await phases.enrich(search_row(status="enriching"), deps, guard())
    assert out.status == "done"
    rerank.assert_awaited_once()
    assert not conn.ran("enriched_at = NOW()")

    # A cancelled search is not ranked by a chain that lost its token.
    conn.on("SELECT 1 FROM mw_job_searches WHERE id = $1 AND dispatch_token = $2", None)
    rerank.reset_mock()
    out = await phases.enrich(search_row(status="enriching"), deps, guard())
    assert out.status == "enriching"
    rerank.assert_not_awaited()


@pytest.mark.asyncio
async def test_a_budget_that_runs_out_mid_batch_leaves_the_rest_unread(conn, monkeypatch):
    monkeypatch.setattr(phases, "rerank", AsyncMock(return_value=2))
    leads = [lead([GH_URL]), lead([GH_URL])]
    conn.on("AND enriched_at IS NULL AND screen_status <> 'irrelevant' AND (fit_score IS NULL OR fit_score >= $2)\n                ORDER BY",
            leads)
    conn.on("COUNT(*) FILTER", {"total": 2, "posted": 1})
    conn.on("SELECT COUNT(*) FROM mw_job_leads WHERE search_id = $1\n               AND enriched_at IS NULL", 1)
    conn.on("SELECT 1 FROM mw_job_searches WHERE id = $1 AND dispatch_token = $2", 1)
    conn.on("RETURNING GREATEST(LEAST($2, $3 - cur.before), 0)", 1)
    conn.on("SET progress = progress || $2::jsonb", search_row(status="enriching"))
    deps = phases.Deps(ats_fetch=AsyncMock(return_value=ats_posting()), page_fetch=AsyncMock())
    out = await phases.enrich(search_row(status="enriching"), deps, guard())
    # One lead read; the other was never tried, so it is not marked read, and
    # the budget is spent, so the search moves on to ranking.
    assert len(conn.ran("enriched_at = NOW()")) == 1
    assert out.status == "done"


@pytest.mark.asyncio
async def test_grant_and_refund(conn):
    conn.on("RETURNING GREATEST(LEAST($2, $3 - cur.before), 0)", 5)
    assert await phases.grant(SEARCH, "fetch_calls", 8, 60) == 5
    assert await phases.grant(SEARCH, "fetch_calls", 0, 60) == 0
    await phases.refund(SEARCH, "provider_calls", 0)
    assert not conn.ran("GREATEST(provider_calls - $2, 0)")
    with pytest.raises(AssertionError):
        await phases.grant(SEARCH, "tokens; DROP TABLE x", 1, 1)


@pytest.mark.asyncio
async def test_guard_note(conn):
    await guard().note("Reading", found=3)
    [call] = conn.ran("progress = progress || $3::jsonb")
    assert call[2][:2] == (SEARCH, TOKEN) and json.loads(call[2][2]) == {"note": "Reading", "found": 3}
