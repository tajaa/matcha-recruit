"""The Census geocoder for a caller that must tell "no such address" from
"it didn't answer" (`geo.geocode_or_raise`); `geocode` itself is unchanged."""
import httpx
import pytest

from app.core.services import geo

MATCH = {"result": {"addressMatches": [{"coordinates": {"x": -97.74, "y": 30.27},
                                         "geographies": {"Counties": [{"BASENAME": "Travis"}]}}]}}
NONE = {"result": {"addressMatches": []}}


def _client(handler):
    return httpx.AsyncClient(transport=httpx.MockTransport(handler))


@pytest.mark.asyncio
@pytest.mark.parametrize("response, want", [
    (httpx.Response(200, json=MATCH), {"lat": 30.27, "lng": -97.74, "county": "Travis", "source": "census"}),
    (httpx.Response(200, json=NONE), None),
    (httpx.Response(400, json={"errors": ["Address cannot be empty"]}), None),  # the query's own problem
])
async def test_an_answer_is_a_match_or_none(response, want):
    async with _client(lambda request: response) as client:
        assert await geo.geocode_or_raise(client, "100 Congress Ave, Austin, TX") == want
    async with _client(lambda request: response) as client:
        assert await geo.geocode(client, "100 Congress Ave", "Austin", "TX", None) == want


@pytest.mark.asyncio
@pytest.mark.parametrize("response", [
    httpx.Response(503, text="Service Unavailable"),
    httpx.Response(200, text="<html>maintenance</html>"),
    httpx.Response(200, json={"unexpected": True}),
    httpx.ConnectError("refused"),
])
async def test_no_answer_raises(response):
    def handler(request):
        if isinstance(response, Exception):
            raise response
        return response

    async with _client(handler) as client:
        with pytest.raises(geo.GeocoderUnavailable):
            await geo.geocode_or_raise(client, "100 Congress Ave, Austin, TX")
    async with _client(handler) as client:  # the shared one still reads it as no match
        assert await geo.geocode(client, "100 Congress Ave", "Austin", "TX", None) is None


@pytest.mark.asyncio
async def test_an_empty_line_asks_nothing():
    asked = []
    async with _client(lambda request: asked.append(request) or httpx.Response(200, json=MATCH)) as client:
        assert await geo.geocode_or_raise(client, "") is None
    assert asked == []
