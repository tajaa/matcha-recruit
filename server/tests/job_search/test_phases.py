"""Plan, discover and enrich, against a scripted provider, ATS and web."""
import json
from unittest.mock import AsyncMock
from uuid import uuid4

import pytest

from app.core.services.safe_fetch import FetchedResponse, UnsafeURL
from app.matcha.services.matcha_work.job_search import ats, phases, providers
from tests.agent_runtime.helpers import FakeConn, connection

from ._fixtures import SEARCH, TOKEN, search_row

GH_URL = "https://boards.greenhouse.io/acme/jobs/123"


def test_plan_from_criteria():
    plan = phases.plan_from_criteria("COO roles", {"titles": ["COO", "Chief Operating Officer"],
                                                   "locations": ["across the country", "Austin, TX", "Remote"]})
    assert plan["queries"][:3] == [
        {"q": "COO", "location": "United States"},
        {"q": "COO Austin, TX", "location": None},
        {"q": "COO remote", "location": "United States"},
    ]
    assert len(plan["queries"]) == 6
    fallback = phases.plan_from_criteria("  COO   jobs paying equity ", {"remote": "remote_only"})
    assert fallback["queries"] == [{"q": "COO jobs paying equity remote", "location": "United States"}]
    many = phases.plan_from_criteria("x", {"titles": [f"T{i}" for i in range(5)], "locations": ["A", "B"]})
    assert len(many["queries"]) == phases.MAX_QUERIES
    dup = phases.plan_from_criteria("x", {"titles": ["COO", "coo"]})
    assert len(dup["queries"]) == 1


@pytest.fixture
def conn(monkeypatch):
    conn = FakeConn()
    monkeypatch.setattr(phases, "connection_or_direct", connection(conn))
    return conn


def guard():
    return phases.Guard(SEARCH, TOKEN)


@pytest.mark.asyncio
async def test_plan_phase_writes_under_the_token(conn):
    out = await phases.plan(search_row(criteria=json.dumps({"titles": ["COO"]})), phases.Deps(), guard())
    assert out.status == "discovering"
    [write] = conn.ran("SET plan = $3::jsonb")
    assert write[2][:2] == (SEARCH, TOKEN) and json.loads(write[2][2])["queries"][0]["q"] == "COO"


def posting(title, company, **over):
    return providers.Posting(title=title, company=company, location=over.pop("location", "Austin, TX"), **over)


class FakeProvider:
    def __init__(self, pages):
        self.pages = pages  # q -> list of (postings, next_token)
        self.calls = []

    async def search(self, q, location=None, *, page_token=None):
        self.calls.append((q, location, page_token))
        pages = self.pages.get(q) or [([], None)]
        index = 0 if page_token is None else int(page_token)
        result = pages[index]
        if isinstance(result, Exception):
            raise result
        return result


def discover_search(queries, **over):
    fields = {"status": "discovering", "provider_calls": 0,
              "plan": json.dumps({"queries": [{"q": q, "location": None} for q in queries]}), **over}
    return search_row(**fields)


def count_script(*values):
    queue = list(values)
    return lambda *_args: queue.pop(0) if len(queue) > 1 else queue[0]


@pytest.mark.asyncio
async def test_discover_dedupes_filters_and_counts_calls(conn):
    provider = FakeProvider({
        "COO": [([posting("COO", "Acme Inc.", salary_text="250K–300K a year",
                          apply_links=[{"url": GH_URL, "source": "Greenhouse"}]),
                  posting("COO", "Excluded Co")], "1"),
                ([posting("COO", "ACME", location="Austin, Texas")], None)],
        "Chief Operating Officer": [([posting("Chief Operating Officer", "Beta", remote=True)], None)],
    })
    conn.on("SELECT COUNT(*) FROM mw_job_leads", count_script(0, 2))
    conn.on("INSERT INTO mw_job_leads", 2)
    search = discover_search(["COO", "Chief Operating Officer"],
                             criteria=json.dumps({"exclude_companies": ["excluded co"]}))
    out = await phases.discover(search, phases.Deps(provider=lambda: provider), guard())
    assert out.status == "enriching" and out.progress["found"] == 2
    assert len(provider.calls) == 3
    [counter] = conn.ran("provider_calls = provider_calls + $2")
    assert counter[2] == (SEARCH, 3)
    [insert] = conn.ran("INSERT INTO mw_job_leads")
    records = json.loads(insert[2][2])
    assert sorted(r["company"] for r in records) == ["Acme Inc.", "Beta"]
    acme = next(r for r in records if r["company"] == "Acme Inc.")
    assert acme["comp_status"] == "posted" and acme["comp"]["base"]["evidence"]["origin"] == "google_jobs"
    assert acme["state_code"] == "TX" and insert[2][3] == TOKEN


@pytest.mark.asyncio
async def test_discover_respects_remote_preference_and_budget(conn):
    provider = FakeProvider({"COO": [([posting("COO", "Acme"), posting("COO", "Remote Co", remote=True)], "1"),
                                     ([posting("COO", "Later")], None)]})
    conn.on("SELECT COUNT(*) FROM mw_job_leads", 1)
    search = discover_search(["COO"], criteria=json.dumps({"remote": "remote_only"}),
                             provider_calls=phases.MAX_PROVIDER_CALLS - 1)
    await phases.discover(search, phases.Deps(provider=lambda: provider), guard())
    assert len(provider.calls) == 1  # one call left in the search's budget
    records = json.loads(conn.ran("INSERT INTO mw_job_leads")[0][2][2])
    assert [r["company"] for r in records] == ["Remote Co"]
    assert not phases.keep_posting(posting("COO", "Remote Co", remote=True), {"remote": "onsite_only"})


@pytest.mark.asyncio
async def test_discover_failures(conn):
    with pytest.raises(phases.PhaseFailed, match="isn't set up"):
        await phases.discover(discover_search(["COO"]), phases.Deps(provider=lambda: None), guard())

    fatal = FakeProvider({"COO": [providers.ProviderError("bad key", fatal=True)]})
    with pytest.raises(phases.PhaseFailed, match="refused"):
        await phases.discover(discover_search(["COO"]), phases.Deps(provider=lambda: fatal), guard())

    conn.on("SELECT COUNT(*) FROM mw_job_leads", 0)
    flaky = FakeProvider({"COO": [providers.ProviderError("503")]})
    with pytest.raises(RuntimeError, match="every job listing query failed"):
        await phases.discover(discover_search(["COO"]), phases.Deps(provider=lambda: flaky), guard())

    empty = FakeProvider({})
    with pytest.raises(phases.PhaseFailed, match="No postings matched"):
        await phases.discover(discover_search(["COO"]), phases.Deps(provider=lambda: empty), guard())


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
    budget = phases._Budget(left=5)
    update = await phases.enrich_one(lead(["https://www.linkedin.com/jobs/1", GH_URL]), deps, budget)
    assert update["source"] == "greenhouse" and update["ats"]["questions"][0]["key"] == "q1"
    assert update["comp"]["base"]["annual_max"] == 310000 and update["description"].startswith("Full")
    deps.page_fetch.assert_not_awaited()
    assert budget.used == 1


@pytest.mark.asyncio
async def test_enrich_one_reads_the_company_page():
    deps = phases.Deps(ats_fetch=AsyncMock(return_value=None), page_fetch=AsyncMock(return_value=page(JSONLD_PAGE)))
    update = await phases.enrich_one(
        lead(["https://www.indeed.com/viewjob?jk=1", "https://careers.delta.test/coo"]), deps, phases._Budget(left=5))
    assert update["source"] == "web" and update["remote"] is True
    assert update["comp"]["base"]["evidence"]["origin"] == "jsonld"
    assert update["comp"]["bonus"]["pct_min"] == 25
    assert deps.page_fetch.await_args.args[0] == "https://careers.delta.test/coo"


@pytest.mark.asyncio
async def test_enrich_one_follows_a_careers_redirect_into_the_ats():
    deps = phases.Deps(ats_fetch=AsyncMock(return_value=ats_posting()),
                       page_fetch=AsyncMock(return_value=page("<html></html>", final_url=GH_URL)))
    update = await phases.enrich_one(lead(["https://delta.test/careers/coo"]), deps, phases._Budget(left=5))
    assert update["source"] == "greenhouse"


@pytest.mark.asyncio
async def test_enrich_one_gives_up_quietly():
    aggregator_only = phases.Deps(ats_fetch=AsyncMock(), page_fetch=AsyncMock())
    assert await phases.enrich_one(lead(["https://www.linkedin.com/jobs/1"]), aggregator_only,
                                   phases._Budget(left=5)) is None
    aggregator_only.page_fetch.assert_not_awaited()
    assert await phases.enrich_one(lead([GH_URL]), aggregator_only, phases._Budget(left=0)) is None
    for result in (page("", status=404), page("{}", ctype="application/json"), page("<html>no ld</html>")):
        deps = phases.Deps(ats_fetch=AsyncMock(), page_fetch=AsyncMock(return_value=result))
        assert await phases.enrich_one(lead(["https://delta.test/coo"]), deps, phases._Budget(left=5)) is None
    for exc in (UnsafeURL("private"), TimeoutError(), RuntimeError("weird")):
        deps = phases.Deps(ats_fetch=AsyncMock(), page_fetch=AsyncMock(side_effect=exc))
        assert await phases.enrich_one(lead(["https://delta.test/coo"]), deps, phases._Budget(left=5)) is None


@pytest.mark.asyncio
async def test_enrich_phase_batches_then_ranks(conn, monkeypatch):
    rerank = AsyncMock(return_value=2)
    monkeypatch.setattr(phases, "rerank", rerank)
    leads = [lead([GH_URL]), lead(["https://www.linkedin.com/x"])]
    conn.on("WHERE search_id = $1 AND enriched_at IS NULL AND screen_status <> 'irrelevant'\n                ORDER BY",
            leads)
    conn.on("SELECT COUNT(*) FROM mw_job_leads WHERE search_id = $1\n               AND enriched_at IS NULL", 5)
    conn.on("COUNT(*) FILTER", {"total": 7, "posted": 3})
    deps = phases.Deps(ats_fetch=AsyncMock(return_value=ats_posting()), page_fetch=AsyncMock())
    search = search_row(status="enriching", fetch_calls=0)
    out = await phases.enrich(search, deps, guard())
    assert out.status == "enriching"  # more to read
    saves = conn.ran("enriched_at = NOW()")
    assert len(saves) == 2 and all(s[2][2] == TOKEN for s in saves)
    assert conn.ran("fetch_calls = fetch_calls + $2")[0][2] == (SEARCH, 1)
    rerank.assert_not_awaited()

    conn.on("SELECT COUNT(*) FROM mw_job_leads WHERE search_id = $1\n               AND enriched_at IS NULL", 0)
    conn.on("SELECT 1 FROM mw_job_searches WHERE id = $1 AND dispatch_token = $2", 1)
    conn.on("SELECT * FROM mw_job_searches WHERE id = $1", search)
    out = await phases.enrich(search, deps, guard())
    assert out.status == "done" and out.progress["posted_pay"] == 3 and out.progress["ranked"] is True
    rerank.assert_awaited_once()

    # Out of page loads: rank what there is.
    rerank.reset_mock()
    conn.on("SELECT COUNT(*) FROM mw_job_leads WHERE search_id = $1\n               AND enriched_at IS NULL", 5)
    out = await phases.enrich(search_row(status="enriching", fetch_calls=phases.MAX_FETCHES), deps, guard())
    assert out.status == "done"
    rerank.assert_awaited_once()

    # A cancelled search is not ranked by a chain that lost its token.
    conn.on("SELECT 1 FROM mw_job_searches WHERE id = $1 AND dispatch_token = $2", None)
    rerank.reset_mock()
    out = await phases.enrich(search_row(status="enriching", fetch_calls=phases.MAX_FETCHES), deps, guard())
    assert out.status == "enriching"
    rerank.assert_not_awaited()


@pytest.mark.asyncio
async def test_guard_note(conn):
    await guard().note("Reading", found=3)
    [call] = conn.ran("progress = progress || $3::jsonb")
    assert call[2][:2] == (SEARCH, TOKEN) and json.loads(call[2][2]) == {"note": "Reading", "found": 3}
