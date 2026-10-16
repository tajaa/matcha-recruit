"""The search APIs' shared request rules and the fallback between them, with no network."""
import asyncio

import httpx
import pytest

from app.matcha.services.matcha_work import search_apis as A


async def _no_sleep(_s):
    return None


async def _answer(*responses):
    queue, seen = list(responses), []

    def handler(request):
        seen.append(request)
        response = queue.pop(0)
        if isinstance(response, Exception):
            raise response
        return response

    try:
        return await A.answer("SearchAPI", lambda client: client.get("https://api.test/search"),
                              transport=httpx.MockTransport(handler), sleep=_no_sleep), seen
    except A.ProviderError as exc:
        return exc, seen


@pytest.mark.asyncio
async def test_what_each_answer_means():
    data, seen = await _answer(httpx.Response(200, json={"jobs": []}))
    assert data == {"jobs": []} and len(seen) == 1
    # Refused for good, asked once.
    for response in (httpx.Response(401), httpx.Response(402),
                     httpx.Response(429, json={"error": "You have used all of the searches for the month."}),
                     httpx.Response(429, json={"error": "Your account has run out of searches."})):
        exc, seen = await _answer(response)
        assert exc.fatal and not exc.down and len(seen) == 1, response
    exc, _ = await _answer(httpx.Response(403, json={"error": {"status": "PERMISSION_DENIED",
                                                               "message": "Places API (New) has not been used"}}))
    assert str(exc) == "SearchAPI refused the API key (PERMISSION_DENIED: Places API (New) has not been used)"
    # A per-minute quota or an hourly limit passes: asked again, and down when it fails again.
    for body in ({"error": {"status": "RESOURCE_EXHAUSTED", "message": "Quota exceeded … per minute"}},
                 {"error": "Hourly limit reached. Please upgrade your plan."}):
        exc, seen = await _answer(httpx.Response(429, json=body), httpx.Response(429, json=body))
        assert exc.down and not exc.fatal and len(seen) == 2 and "answered 429" in str(exc)
    exc, seen = await _answer(httpx.ConnectError("x"), httpx.Response(503))
    assert exc.down and "SearchAPI answered 503" in str(exc) and len(seen) == 2
    exc, _ = await _answer(httpx.ConnectError("x"), httpx.ConnectError("x"))
    assert str(exc) == "SearchAPI did not answer: ConnectError"
    # This request's own error.
    for response, said in ((httpx.Response(400, json={"error": "Bad q"}), "answered 400 (Bad q)"),
                           (httpx.Response(200, text="<html>"), "something other than JSON"),
                           (httpx.Response(200, json=[1]), "an unexpected shape")):
        exc, seen = await _answer(response)
        assert said in str(exc) and not exc.fatal and not exc.down and len(seen) == 1


def test_errors_that_only_say_there_were_no_results():
    assert A.result_error({"error": "Google hasn't returned any results for this query."}) == ""
    assert A.result_error({"error": "No results found"}) == "" and A.result_error({}) == ""
    assert A.result_error({"error": "Unsupported location"}) == "Unsupported location"


class Api:
    def __init__(self, name, *answers):
        self.name, self.answers, self.asked = name, list(answers), []

    async def get(self, token=None):
        self.asked.append(token)
        await asyncio.sleep(0)  # calls running alongside interleave here
        answer = self.answers.pop(0)
        if isinstance(answer, Exception):
            raise answer
        return answer


def _get(api, token):
    return api.get(token)


SPENT = A.ProviderError("SearchAPI has no searches left", fatal=True)
DOWN = A.ProviderError("SearchAPI did not answer: ConnectError", down=True)


@pytest.mark.asyncio
async def test_a_refusing_api_is_dropped_once_for_the_next(caplog):
    first, second = Api("SearchAPI", SPENT, SPENT), Api("SerpApi", "a", "b", "c")
    apis = A.Fallback([first, second])
    with caplog.at_level("ERROR"):
        assert await asyncio.gather(apis.call(_get), apis.call(_get)) == [(1, "a"), (1, "b")]
    assert [r.levelname for r in caplog.records] == ["ERROR"] and "using SerpApi instead" in caplog.text
    assert apis.first() is second and await apis.call(_get) == (1, "c") and len(first.asked) == 2


@pytest.mark.asyncio
async def test_an_api_that_is_down_is_passed_over_only_for_another(caplog):
    first, second = Api("SearchAPI", DOWN), Api("SerpApi", "a", DOWN, DOWN)
    apis = A.Fallback([first, second])
    with caplog.at_level("WARNING"):
        assert await apis.call(_get) == (1, "a")
    assert [r.levelname for r in caplog.records] == ["WARNING"]
    # The last one is always asked: down, it's this call's error.
    for _ in range(2):
        with pytest.raises(A.ProviderError) as exc:
            await apis.call(_get)
        assert exc.value is DOWN
    assert len(second.asked) == 3
    # Any other error is the call's own: nothing is dropped.
    own = A.ProviderError("SearchAPI: Unsupported location")
    apis = A.Fallback([Api("SearchAPI", own, "a"), Api("SerpApi")])
    with pytest.raises(A.ProviderError) as exc:
        await apis.call(_get)
    assert exc.value is own and await apis.call(_get) == (0, "a")


@pytest.mark.asyncio
async def test_with_every_api_dropped_each_call_gets_a_fresh_error():
    first, second = Api("SearchAPI", DOWN), Api("SerpApi", SPENT)
    apis = A.Fallback([first, second])
    errors = []
    for _ in range(3):
        with pytest.raises(A.ProviderError) as exc:
            await apis.call(_get)
        errors.append(exc.value)
    assert all(e.fatal for e in errors) and len({id(e) for e in errors}) == 3
    assert str(errors[0]) == "no search API left (SearchAPI has no searches left)"
    assert all(e is not SPENT for e in errors)
    assert len(first.asked) == 1 and len(second.asked) == 1 and apis.first() is None
    with pytest.raises(A.ProviderError, match="no search API left") as exc:
        await A.Fallback([]).call(_get)
    assert exc.value.fatal


@pytest.mark.asyncio
async def test_a_token_goes_back_to_the_api_that_gave_it():
    first, second = Api("SearchAPI", "a", SPENT), Api("SerpApi", "b")
    apis = A.Fallback([first, second])
    at, _ = await apis.call(_get)
    token = A.Fallback.tag(at, "page-2")
    assert token == "0:page-2" and A.Fallback.tag(0, None) is None and apis.holds(token)
    # Its API refuses for good: nothing else is asked with its token.
    assert await apis.call(_get, token) is None and first.asked == [None, "page-2"] and not second.asked
    assert not apis.holds(token) and await apis.call(_get, token) is None
    assert await apis.call(_get, "1:next") == (1, "b") and second.asked == ["next"]
    # Not one of ours.
    for stray in ("nonsense", "7:x", ""):
        assert not apis.holds(stray) and await apis.call(_get, stray) is None
    assert not apis.holds(None)
