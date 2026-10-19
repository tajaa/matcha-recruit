"""The paid search API's request rules, with no network."""
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

