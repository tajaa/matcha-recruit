"""find_jobs and the job_postings block: live postings, read at the employer. No network."""
import pytest

from app.matcha.services.matcha_work.agent_runtime import catalog, result
from app.matcha.services.matcha_work.agent_runtime.abilities import job_listings as J
from app.matcha.services.matcha_work.agent_runtime.context import RunState
from app.matcha.services.matcha_work.job_search.providers import Posting
from app.matcha.services.matcha_work.search_apis import ProviderError

from .helpers import context


def posting(title, company, location, *, salary=None, links=None):
    return Posting(title=title, company=company, location=location, via="via LinkedIn", salary_text=salary,
                   posted_text="3 days ago", apply_links=links or [], share_url="https://www.google.com/jobs/x")


class Provider:
    def __init__(self, *pages):
        self.pages, self.asked = list(pages), []

    async def search(self, q, location=None, *, page_token=None):
        self.asked.append((q, location, page_token))
        page = self.pages.pop(0)
        if isinstance(page, Exception):
            raise page
        return page


def state():
    return RunState(started=0.0, sessions={J.KEY: J.JobListingsSession()})


@pytest.fixture
def wired(monkeypatch):
    read = {}

    async def verify(lead):
        return read.get(lead["company"])

    monkeypatch.setattr(J, "_verify", verify)
    return read


async def find(st, provider, monkeypatch, **args):
    monkeypatch.setattr(J, "_provider", lambda: provider)
    return await J.FIND_JOBS.handler(context(), st, args, 120)


def test_job_listings_needs_a_listings_key_and_nothing_switched_on(monkeypatch):
    ability = J.build()
    assert ability.consent_version is None and not ability.private_only
    monkeypatch.setattr(J, "_provider", lambda: object())
    assert catalog.availability(ability, catalog.Situation(private=False)).available
    monkeypatch.setattr(J, "_provider", lambda: None)
    assert not catalog.availability(ability, catalog.Situation(private=True)).available


@pytest.mark.asyncio
async def test_find_jobs_keeps_jobs_near_the_place_and_reads_them_at_the_employer(monkeypatch, wired):
    wired["Figma"] = {
        "source": "greenhouse", "source_url": "https://job-boards.greenhouse.io/figma/jobs/123",
        "comp": {"base": {"status": "posted", "annual_min": 180000, "annual_max": 220000, "currency": "USD",
                          "evidence": {"quote": "$180,000 - $220,000 USD", "origin": "ats_api"}}},
    }
    provider = Provider(([
        posting("Senior Product Designer", "Figma", "Los Angeles, CA",
                links=[{"url": "https://www.linkedin.com/jobs/1", "source": "LinkedIn"}]),
        posting("Senior Product Designer", "Acme", "Santa Monica, CA",
                links=[{"url": "https://www.linkedin.com/jobs/2", "source": "LinkedIn"},
                       {"url": "https://acme.test/careers/9", "source": "Acme"}]),
        posting("Senior Product Designer", "Faraway", "New York, NY"),
    ], None))
    st = state()
    out = await find(st, provider, monkeypatch, title="senior product designer", location="Los Angeles, CA")
    assert provider.asked == [("senior product designer Los Angeles, CA", None, None)]
    assert out.payload["new_jobs"] == 2 and out.payload["left_out_elsewhere"] == 1
    assert out.payload["live_at_employer"] == 1 and out.payload["live_on_a_board"] == 0
    figma, acme = out.payload["jobs"]
    assert figma.startswith("J1 | Senior Product Designer | Figma | Los Angeles, CA")
    assert "$180K–$220K" in figma and '"$180,000 - $220,000 USD"' in figma and "live at the employer (Greenhouse)" in figma
    assert figma.endswith("https://job-boards.greenhouse.io/figma/jobs/123")
    # Not read at the employer: said so, and its link is the employer's own, not LinkedIn.
    assert "listed on Google Jobs only" in acme and "Pay not posted" in acme and acme.endswith("https://acme.test/careers/9")
    assert "https://job-boards.greenhouse.io/figma/jobs/123" in out.provenance
    assert "https://acme.test/careers/9" in out.provenance


@pytest.mark.asyncio
async def test_a_job_found_twice_is_kept_once_and_remote_means_remote(monkeypatch, wired):
    st = state()
    remote = posting("Staff Engineer", "Remoteco", "Anywhere")
    remote.remote = True
    office = posting("Staff Engineer", "Officeco", "Chicago, IL")
    office.remote = False
    out = await find(st, Provider(([remote, office], None)), monkeypatch, title="staff engineer", location="Remote")
    assert out.payload["new_jobs"] == 1 and out.payload["jobs"][0].startswith("J1 | Staff Engineer | Remoteco")
    again = await find(st, Provider(([remote], None)), monkeypatch, title="staff engineer", location="Remote")
    assert again.payload["new_jobs"] == 0 and again.payload["already_found"] == 1


@pytest.mark.asyncio
async def test_listings_down_is_a_tool_error_the_model_can_route_around(monkeypatch, wired):
    out = await find(state(), Provider(ProviderError("SerpApi answered 500")), monkeypatch, title="nurse")
    assert "web_search" in out.payload["error"]


@pytest.mark.asyncio
async def test_the_block_puts_jobs_read_at_the_employer_first(monkeypatch, wired):
    wired["Beta"] = {"source": "lever", "source_url": "https://jobs.lever.co/beta/abc", "comp": {}}
    st = state()
    await find(st, Provider(([posting("Designer", "Alpha", "Austin, TX"), posting("Designer", "Beta", "Austin, TX"),
                              posting("Designer", "Gamma", "Austin, TX")], None)),
               monkeypatch, title="designer", location="Austin, TX")
    block, _ = J.gate_block("job_postings", {"job_ids": []}, st)
    assert [j["company"] for j in block["jobs"]] == ["Beta", "Alpha", "Gamma"]
    assert block["jobs"][0]["verified"] is True and block["jobs"][0]["apply_url"] == "https://jobs.lever.co/beta/abc"
    picked, warnings = J.gate_block("job_postings", {"job_ids": ["j3", "J9"]}, st)
    assert [j["id"] for j in picked["jobs"]] == ["J3"] and warnings
    out, _ = result.normalize({"headline": "3 designer jobs", "summary": "Three."}, st, [J.build()])
    assert [b["type"] for b in out["blocks"]] == ["job_postings"]


@pytest.mark.asyncio
async def test_a_posting_read_on_a_job_board_is_said_to_be_on_that_board(monkeypatch, wired):
    # builtin.com carries the posting's JobPosting data, but it isn't Plug's site.
    wired["Plug Technologies"] = {"source": "web", "source_url": "https://builtin.com/job/staff-product-designer/1",
                                  "comp": {}}
    wired["Disney"] = {"source": "web", "source_url": "https://jobs.disneycareers.com/job/glendale/designer/1",
                       "comp": {}}
    st = state()
    out = await find(st, Provider(([
        posting("Product Designer", "Plug Technologies", "Los Angeles, CA",
                links=[{"url": "https://builtin.com/job/staff-product-designer/1", "source": "Built In"},
                       {"url": "https://jobs.ashbyhq.com/plug/0b1c2d3e-0000-4000-8000-000000000001", "source": "Ashby"}]),
        posting("Product Designer", "Disney", "Glendale, CA"),
        posting("Product Designer", "Nominal", "Los Angeles, CA",
                links=[{"url": "https://www.jobleads.com/us/job/1", "source": "JobLeads"},
                       {"url": "https://nominal.io/careers/designer", "source": "Nominal"}]),
    ], None)), monkeypatch, title="product designer", location="Los Angeles, CA")
    plug, disney, nominal = out.payload["jobs"]
    assert "live on builtin.com, a job board" in plug
    # Where to apply: the employer's own ATS over the board it was read on.
    assert plug.endswith("https://jobs.ashbyhq.com/plug/0b1c2d3e-0000-4000-8000-000000000001")
    assert "live at the employer (jobs.disneycareers.com)" in disney
    # Not read anywhere: the employer's own careers page over another board.
    assert "listed on Google Jobs only" in nominal and nominal.endswith("https://nominal.io/careers/designer")
    block, _ = J.gate_block("job_postings", {"job_ids": []}, st)
    assert [j["company"] for j in block["jobs"]] == ["Disney", "Plug Technologies", "Nominal"]
    assert block["jobs"][1]["verified"] and not block["jobs"][1]["at_employer"]
    assert block["jobs"][1]["read_on"] == "builtin.com"


@pytest.mark.asyncio
async def test_a_posting_read_on_a_board_is_looked_up_on_the_employers_own_board(monkeypatch):
    from types import SimpleNamespace

    from app.matcha.services.matcha_work.job_search import ats, phases

    async def enrich(lead, deps, budget):
        return {"source": "web", "source_url": "https://builtin.com/job/1", "description": "board text", "comp": {}}

    found = {}

    async def find(company, title, *, take):
        assert take()
        return found.get(company)

    monkeypatch.setattr(phases, "enrich_one", enrich)
    monkeypatch.setattr(phases, "Deps", lambda: SimpleNamespace(ats_find=find))
    lead = {"title": "Product Designer", "company": "Otter", "apply_links": []}
    # Not on any of its boards: the board read stands.
    assert (await J._verify(lead))["source_url"] == "https://builtin.com/job/1"
    found["Otter"] = ats.AtsPosting(ref=ats.AtsRef("greenhouse", "otter", "123"),
                                    url="https://job-boards.greenhouse.io/otter/jobs/123",
                                    title="Product Designer", company="Otter")
    upgraded = await J._verify(lead)
    assert upgraded["source"] == "greenhouse" and upgraded["source_url"] == "https://job-boards.greenhouse.io/otter/jobs/123"
    # Another job on the employer's board is not this one.
    found["Otter"] = ats.AtsPosting(ref=ats.AtsRef("greenhouse", "otter", "9"), url="https://job-boards.greenhouse.io/otter/jobs/9",
                                    title="Staff Accountant", company="Otter")
    assert (await J._verify(lead))["source"] == "web"


@pytest.mark.parametrize("url, company, theirs", [
    ("https://careers.bostonscientific.com/job/1", "Boston Scientific", True),
    ("https://bostonscientific.wd5.myworkdayjobs.com/x", "Boston Scientific Corporation", True),
    ("https://jobs.disneycareers.com/job/glendale/1", "The Walt Disney Company", True),
    ("https://www.metacareers.com/jobs/1", "Meta", True),
    ("https://jobs.netflix.com/jobs/1", "Netflix", True),
    ("https://otter.ai/careers", "Otter.ai", True),
    ("https://www.bmw.com/careers", "BMW", True),
    ("https://amazon.jobs/en/jobs/1", "Amazon", True),
    ("https://careers.tesco.co.uk/1", "Tesco PLC", True),
    # A word of the name inside a board's host is not the employer's site.
    ("https://www.builtinboston.com/job/1", "Boston Scientific", False),
    ("https://builtin.com/job/1", "Plug Technologies", False),
    ("https://www.jobilize.com/job/1", "Disney", False),
    ("https://boston.craigslist.org/jobs/1", "Boston Scientific", False),
    ("", "Boston Scientific", False),
    ("https://careers.example.com/1", "Confidential", False),
])
def test_a_host_is_the_employers_when_a_label_is_its_name(url, company, theirs):
    assert J.employer_host(url, company) is theirs


@pytest.mark.asyncio
async def test_a_slow_read_costs_its_check_not_the_list(monkeypatch):
    import asyncio

    stopped = []

    async def verify(lead):
        try:
            await asyncio.sleep(30)
        except asyncio.CancelledError:
            stopped.append(lead["company"])
            raise

    monkeypatch.setattr(J, "_verify", verify)
    monkeypatch.setattr(J, "VERIFY_MARGIN", 0.0)
    monkeypatch.setattr(J, "_provider", lambda: Provider(([
        posting("Product Designer", "Acme", "Los Angeles, CA"),
        posting("Product Designer", "Brightline", "Los Angeles, CA"),
    ], None)))
    st = state()
    # 0.2 s left in the run: the reads get that, then are stopped.
    out = await J.FIND_JOBS.handler(context(), st, {"title": "product designer", "location": "Los Angeles, CA"}, 0.2)
    assert out.payload["new_jobs"] == 2 and out.payload["live_at_employer"] == 0
    assert all("listed on Google Jobs only" in line for line in out.payload["jobs"])
    await asyncio.sleep(0)  # the reads called off get their cancellation
    assert sorted(stopped) == ["Acme", "Brightline"]


@pytest.mark.asyncio
async def test_a_job_is_in_the_run_before_it_is_read(monkeypatch):
    # Called off mid-read (the runner's timeout), the jobs listed are kept, and
    # a second search can't count them as new.
    import asyncio

    reading = asyncio.Event()

    async def verify(lead):
        reading.set()
        await asyncio.sleep(30)

    monkeypatch.setattr(J, "_verify", verify)
    monkeypatch.setattr(J, "_provider", lambda: Provider(
        ([posting("Product Designer", "Acme", "Los Angeles, CA")], None),
        ([posting("Product Designer", "Acme", "Los Angeles, CA")], None),
    ))
    st = state()
    first = asyncio.ensure_future(J.FIND_JOBS.handler(context(), st, {"title": "product designer",
                                                                      "location": "Los Angeles, CA"}, 120))
    await reading.wait()
    first.cancel()
    with pytest.raises(asyncio.CancelledError):
        await first
    assert list(st.sessions[J.KEY].jobs) == ["J1"] and not st.sessions[J.KEY].jobs["J1"]["verified"]
    again = await J.FIND_JOBS.handler(context(), st, {"title": "product designer", "location": "Los Angeles, CA",
                                                      "pages": 1}, 0.0)
    assert again.payload["new_jobs"] == 0 and again.payload["already_found"] == 1


@pytest.mark.asyncio
async def test_listing_pages_stop_at_the_runs_budget(monkeypatch, wired):
    provider = Provider(([posting("Product Designer", "Acme", "Los Angeles, CA")], "next"),
                        ([posting("Product Designer", "Brightline", "Los Angeles, CA")], "next"))
    st = state()
    st.sessions[J.KEY].paid = J.MAX_PAID - 1
    await find(st, provider, monkeypatch, title="product designer", location="Los Angeles, CA", pages=2)
    assert len(provider.asked) == 1 and st.sessions[J.KEY].paid == J.MAX_PAID
