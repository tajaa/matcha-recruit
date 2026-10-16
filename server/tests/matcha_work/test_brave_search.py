"""Brave's search client: the request, the results, and when Brave is out. No network."""
import httpx
import pytest

from app.matcha.services.matcha_work import brave_search as B

MONTHLY = {"x-ratelimit-policy": "1;w=1, 2000;w=2678400"}


@pytest.fixture(autouse=True)
def _keyed(monkeypatch):
    monkeypatch.setattr(B, "_key", lambda: "brave-key")
    B.reset()
    yield
    B.reset()


class Clock:
    def __init__(self):
        self.now = 1000.0

    def __call__(self):
        return self.now


async def _no_sleep(_s):
    return None


async def _search(*responses, clock=None, **kw):
    queue, seen = list(responses), []

    def handler(request):
        seen.append(request)
        response = queue.pop(0)
        if isinstance(response, Exception):
            raise response
        return response

    try:
        found = await B.search("lip balm", transport=httpx.MockTransport(handler), sleep=_no_sleep,
                               clock=clock or Clock(), **kw)
    except B.Unavailable as exc:
        return exc, seen
    return found, seen


def _ok(results, headers=None):
    return httpx.Response(200, json={"web": {"results": results}}, headers=headers or {})


@pytest.mark.asyncio
async def test_the_request_and_what_the_model_sees():
    found, seen = await _search(_ok([
        {"title": "Best <strong>lip balm</strong> &amp; more", "url": "https://reviews.example/a",
         "description": "Our <strong>top</strong> pick", "age": "2 days ago",
         "extra_snippets": ["one", "two", "three", "four"]},
        {"title": "Not a page", "url": "javascript:alert(1)"},
        {"title": "Plain", "url": "http://shop.example/b"},
        "not a result",
    ]), freshness="week")
    request = seen[0]
    assert request.headers["X-Subscription-Token"] == "brave-key"
    params = dict(request.url.params)
    assert params == {"q": "lip balm", "count": "10", "extra_snippets": "true", "result_filter": "web",
                      "text_decorations": "false", "freshness": "pw"}
    assert found == [
        {"title": "Best lip balm & more", "url": "https://reviews.example/a", "description": "Our top pick",
         "age": "2 days ago", "more": ["one", "two", "three"]},
        {"title": "Plain", "url": "http://shop.example/b", "description": ""},
    ]


@pytest.mark.asyncio
@pytest.mark.parametrize("freshness", ["decade", ["week"], {"week": 1}, 7])
async def test_an_unknown_freshness_is_left_out(freshness):
    _, seen = await _search(_ok([]), freshness=freshness)
    assert "freshness" not in dict(seen[0].url.params)


@pytest.mark.asyncio
@pytest.mark.parametrize("status", [401, 403, 402])
async def test_a_refused_key_or_bill_takes_brave_out_for_an_hour(status, caplog):
    clock = Clock()
    exc, seen = await _search(httpx.Response(status, json={"error": {"detail": "nope"}}), clock=clock)
    assert isinstance(exc, B.Unavailable) and exc.out and len(seen) == 1
    assert "nope" in str(exc) and "nope" in B.out_reason()
    assert "Brave search is out" in caplog.text
    assert not B.available(clock=clock)
    # Out means no request at all.
    again, seen = await _search(_ok([]), clock=clock)
    assert isinstance(again, B.Unavailable) and again.out and seen == []
    clock.now += B.REFUSED_SECONDS
    assert B.available(clock=clock)


@pytest.mark.asyncio
async def test_no_searches_left_is_out_until_the_month_resets():
    clock = Clock()
    exc, seen = await _search(httpx.Response(429, headers={**MONTHLY, "x-ratelimit-remaining": "0, 0",
                                                           "x-ratelimit-reset": "1, 86400"}), clock=clock)
    assert exc.out and "no searches left" in str(exc) and len(seen) == 1  # not asked again
    clock.now += 86_399
    assert not B.available(clock=clock)
    clock.now += 1
    assert B.available(clock=clock)


@pytest.mark.asyncio
async def test_the_last_search_of_the_month_is_used_and_then_brave_is_out():
    clock = Clock()
    found, _ = await _search(_ok([{"title": "A", "url": "https://a.example"}],
                                 {**MONTHLY, "x-ratelimit-remaining": "0, 0", "x-ratelimit-reset": "1, 600"}),
                             clock=clock)
    assert [r["url"] for r in found] == ["https://a.example"]
    assert not B.available(clock=clock)


@pytest.mark.asyncio
async def test_too_fast_is_asked_again_not_out():
    rate = httpx.Response(429, headers={**MONTHLY, "x-ratelimit-remaining": "0, 1500", "x-ratelimit-reset": "1, 9"})
    found, seen = await _search(rate, _ok([]))
    assert found == [] and len(seen) == 2 and B.available()


@pytest.mark.asyncio
async def test_down_twice_is_this_search_only():
    for first, second in ((httpx.Response(503), httpx.Response(500)),
                          (httpx.ConnectError("x"), httpx.ConnectError("x")),
                          (httpx.Response(429), httpx.Response(429))):
        exc, seen = await _search(first, second)
        assert isinstance(exc, B.Unavailable) and not exc.out and len(seen) == 2
        assert B.available()


@pytest.mark.asyncio
async def test_a_bad_request_or_answer_is_this_search_only():
    exc, seen = await _search(httpx.Response(422, json={"error": {"status": 422, "detail": "bad count"}}))
    assert not exc.out and "422: bad count" in str(exc) and len(seen) == 1
    exc, _ = await _search(httpx.Response(200, text="<html>"))
    assert not exc.out and "JSON" in str(exc)
    assert B.available()


@pytest.mark.asyncio
async def test_without_a_key_brave_is_not_asked(monkeypatch):
    monkeypatch.setattr(B, "_key", lambda: None)
    assert not B.configured() and not B.available()
    exc, seen = await _search(_ok([]))
    assert exc.out and seen == []


def test_the_key_comes_from_settings(monkeypatch):
    monkeypatch.undo()
    from app import config

    monkeypatch.setattr(config, "get_settings", lambda: type("S", (), {"brave_search_api_key": "k"})())
    assert B._key() == "k"
    monkeypatch.setattr(config, "get_settings", lambda: type("S", (), {"brave_search_api_key": ""})())
    assert B._key() is None

    def unloaded():
        raise RuntimeError("Settings not initialized")

    monkeypatch.setattr(config, "get_settings", unloaded)
    assert B._key() is None


def test_spent_quota_reads_only_day_or_longer_windows():
    assert B.spent_quota(httpx.Headers({})) is None
    assert B.spent_quota(httpx.Headers({"x-ratelimit-policy": "50;w=1", "x-ratelimit-remaining": "0"})) is None
    assert B.spent_quota(httpx.Headers({**MONTHLY, "x-ratelimit-remaining": "1, 0",
                                        "x-ratelimit-reset": "1, 77"})) == 77.0
    # No reset given: the whole window.
    assert B.spent_quota(httpx.Headers({"x-ratelimit-policy": "100;w=86400",
                                        "x-ratelimit-remaining": "0"})) == 86400.0
    # A blank or odd part keeps its place, so each number stays with its window.
    assert B.spent_quota(httpx.Headers({**MONTHLY, "x-ratelimit-remaining": " , 0",
                                        "x-ratelimit-reset": "x, 50"})) == 50.0
    assert B.spent_quota(httpx.Headers({**MONTHLY, "x-ratelimit-remaining": "0, ",
                                        "x-ratelimit-reset": "1, 50"})) is None
    assert B.spent_quota(httpx.Headers({"x-ratelimit-policy": "1;w=1, 2000",
                                        "x-ratelimit-remaining": "1, 0"})) is None


def test_out_is_capped_and_logged_once(caplog):
    clock = Clock()
    B.mark_out("first", 10**9, clock=clock)
    B.mark_out("second", 60, clock=clock)
    assert caplog.text.count("Brave search is out") == 1
    assert B.out_reason() == "second"
    clock.now += 61
    assert B.available(clock=clock)
