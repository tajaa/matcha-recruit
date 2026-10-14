"""Google Jobs through SearchAPI and SerpApi, with no network."""
from types import SimpleNamespace

import httpx
import pytest

from app.matcha.services.matcha_work.job_search import providers

SEARCHAPI_PAGE = {
    "jobs": [
        {
            "title": "Chief Operating Officer", "company_name": "Acme Robotics", "location": "Austin, TX",
            "via": "Greenhouse", "description": "Lead operations. Salary $250K-$300K a year.",
            "detected_extensions": {"salary": "250K–300K a year", "posted_at": "3 days ago",
                                    "schedule_type": "Full-time", "work_from_home": True},
            "job_highlights": [{"title": "Qualifications", "items": ["10+ years"]}, "junk"],
            "apply_links": [{"link": "https://boards.greenhouse.io/acme/jobs/123", "source": "Greenhouse"},
                            {"link": "javascript:alert(1)", "source": "x"},
                            {"link": "https://boards.greenhouse.io/acme/jobs/123", "source": "dup"}],
            "job_id": "abc", "sharing_link": "https://www.google.com/search?q=x",
        },
        {"title": "", "company_name": "No title"},
        "junk",
    ],
    "pagination": {"next_page_token": "tok2"},
}
SERPAPI_PAGE = {
    "jobs_results": [{
        "title": "COO", "company_name": "Beta Health", "location": "Denver, CO",
        "description": "Bonus eligible.", "detected_extensions": {"posted_at": "1 day ago"},
        "apply_options": [{"title": "Lever", "link": "https://jobs.lever.co/beta/0b9c3b6e-1111-4222-8333-944445555666"}],
        "share_link": "https://www.google.com/search?ibp=x", "job_id": "def",
    }],
    "serpapi_pagination": {"next_page_token": None},
}


def transport(*responses, seen=None):
    queue = list(responses)

    def handler(request):
        if seen is not None:
            seen.append(request)
        status, body = queue.pop(0)
        return httpx.Response(status, json=body) if not isinstance(body, str) else httpx.Response(status, text=body)

    return httpx.MockTransport(handler)


async def no_sleep(_s):
    return None


@pytest.mark.asyncio
async def test_searchapi_page_is_parsed_and_paginated():
    seen = []
    api = providers.SearchApiJobs("k", transport=transport((200, SEARCHAPI_PAGE), seen=seen), sleep=no_sleep)
    postings, token = await api.search("Chief Operating Officer", "United States", page_token="t1")
    assert token == "tok2"
    [posting] = postings
    assert (posting.title, posting.company, posting.remote) == ("Chief Operating Officer", "Acme Robotics", True)
    assert posting.salary_text == "250K–300K a year" and posting.posted_text == "3 days ago"
    assert posting.apply_links == [{"url": "https://boards.greenhouse.io/acme/jobs/123", "source": "Greenhouse"}]
    assert posting.highlights == [{"title": "Qualifications", "items": ["10+ years"]}]
    params = dict(seen[0].url.params)
    assert params == {"engine": "google_jobs", "q": "Chief Operating Officer", "api_key": "k",
                      "location": "United States", "next_page_token": "t1"}


@pytest.mark.asyncio
async def test_serpapi_shape_and_no_results():
    api = providers.SerpApiJobs("k", transport=transport(
        (200, SERPAPI_PAGE), (200, {"error": "Google hasn't returned any results for this query."})),
        sleep=no_sleep)
    postings, token = await api.search("COO")
    assert token is None and postings[0].apply_links[0]["source"] == "Lever"
    assert postings[0].share_url.startswith("https://www.google.com/")
    assert await api.search("nothing") == ([], None)


@pytest.mark.asyncio
async def test_errors_retry_once_and_a_refused_key_is_fatal():
    api = providers.SearchApiJobs("k", transport=transport((503, {}), (200, SEARCHAPI_PAGE)), sleep=no_sleep)
    postings, _ = await api.search("COO")
    assert len(postings) == 1

    api = providers.SearchApiJobs("k", transport=transport((429, {}), (500, {})), sleep=no_sleep)
    with pytest.raises(providers.ProviderError) as exc:
        await api.search("COO")
    assert not exc.value.fatal

    api = providers.SerpApiJobs("bad", transport=transport((401, {"error": "Invalid API key"})), sleep=no_sleep)
    with pytest.raises(providers.ProviderError) as exc:
        await api.search("COO")
    assert exc.value.fatal

    for body in ((400, {}), (200, "not json"), (200, ["list"]), (200, {"error": "Unsupported location"})):
        api = providers.SearchApiJobs("k", transport=transport(body), sleep=no_sleep)
        with pytest.raises(providers.ProviderError):
            await api.search("COO")

    def boom(_request):
        raise httpx.ConnectError("down")

    api = providers.SerpApiJobs("k", transport=httpx.MockTransport(boom), sleep=no_sleep)
    with pytest.raises(providers.ProviderError, match="did not answer"):
        await api.search("COO")


def test_provider_choice(monkeypatch):
    import app.config as config

    def settings(search=None, serp=None):
        monkeypatch.setattr(config, "get_settings", lambda: SimpleNamespace(search_api_key=search, serp_api_key=serp))

    settings("a", "b")
    assert isinstance(providers.choose_provider(), providers.SearchApiJobs) and providers.configured()
    settings(None, "b")
    assert isinstance(providers.choose_provider(), providers.SerpApiJobs)
    settings(None, None)
    assert providers.choose_provider() is None and not providers.configured()

    def broken():
        raise RuntimeError("no settings")

    monkeypatch.setattr(config, "get_settings", broken)
    assert providers.configured() is False
