"""Google Shopping and Google Maps through SearchAPI: parsing, retries, errors."""
import httpx
import pytest

from app.matcha.services.matcha_work.agent_tasks.research import providers as P

from ._fixtures import TODAY


async def _no_sleep(_s):
    return None


def _api(handler, cls=P.SearchApi):
    return cls("key", transport=httpx.MockTransport(handler), sleep=_no_sleep, today=lambda: TODAY)


SHOP = {"shopping_results": [
    {"title": "Organic Lip Balm", "link": "https://shop.test/balm", "source": "Acme", "price": "$12.99",
     "extracted_price": 12.99, "rating": 4.7, "reviews": 812, "thumbnail": "https://img.test/b.jpg",
     "delivery": "Free delivery", "product_id": "p1"},
    {"title": "No link"}, {"link": "https://shop.test/x"}, "junk",
]}
MAPS = {"local_results": [
    {"title": "Ramen Place", "place_id": "abc", "address": "1 Mission St", "rating": 4.6, "reviews": 900,
     "price": "$$", "type": "Ramen restaurant", "phone": "555", "website": "https://ramen.test",
     "open_hours": {"friday": "5 PM–2 AM"}, "thumbnail": "https://img.test/r.jpg"},
    {"title": "No site", "place_id": "def", "open_state": "Open now"},
    {"title": "Nothing"},
]}


@pytest.mark.asyncio
async def test_shopping_and_places_become_verified_findings():
    seen = []

    def handler(request):
        seen.append(dict(request.url.params))
        return httpx.Response(200, json=SHOP if request.url.params["engine"] == "google_shopping" else MAPS)

    api = _api(handler)
    [balm] = await api.search("shopping", "organic lip balm", page=2)
    assert balm.kind == "product" and balm.subtitle == "Acme" and balm.image_url == "https://img.test/b.jpg"
    assert balm.fields["price"]["value"] == 12.99 and balm.fields["price"]["evidence"]["origin"] == "provider"
    assert balm.fields["review_count"]["value"] == 812 and balm.fields["shipping"]["value"] == "Free delivery"
    assert seen[0]["page"] == "2" and seen[0]["api_key"] == "key"
    ramen, other = await api.search("places", "ramen mission")
    assert ramen.url == "https://ramen.test" and ramen.fields["hours"]["value"].startswith("friday")
    assert ramen.fields["price_level"]["value"] == "$$" and ramen.fields["cuisine"]["value"] == "Ramen restaurant"
    assert other.url.startswith("https://www.google.com/maps/search/") and other.fields["hours"]["value"] == "Open now"
    with pytest.raises(ValueError):
        await api.search("flights", "x")


@pytest.mark.asyncio
async def test_errors_and_one_retry():
    calls = {"n": 0}

    def flaky(_request):
        calls["n"] += 1
        return httpx.Response(503) if calls["n"] == 1 else httpx.Response(200, json={"error": "Google hasn't returned any results"})

    assert await _api(flaky).search("shopping", "x") == []
    assert calls["n"] == 2
    for response, fatal in ((httpx.Response(401), True), (httpx.Response(400), False),
                            (httpx.Response(200, text="nope"), False), (httpx.Response(200, json=[1]), False),
                            (httpx.Response(200, json={"error": "Invalid key"}), False),
                            (httpx.Response(500), False)):
        with pytest.raises(P.ProviderError) as exc:
            await _api(lambda _r, resp=response: resp).search("shopping", "x")
        assert exc.value.fatal is fatal

    def broken(_request):
        raise httpx.ConnectError("down")

    with pytest.raises(P.ProviderError):
        await _api(broken).search("places", "x")


@pytest.mark.asyncio
async def test_serpapi_pages_by_offset_and_asks_maps_for_a_search():
    seen = []

    def handler(request):
        seen.append((str(request.url).split("?")[0], dict(request.url.params)))
        return httpx.Response(200, json=SHOP if request.url.params["engine"] == "google_shopping" else MAPS)

    api = _api(handler, P.SerpApi)
    assert len(await api.search("shopping", "balm")) == 1
    places = await api.search("places", "ramen", page=3)
    assert seen[0][0] == "https://serpapi.com/search.json" and "start" not in seen[0][1]
    assert seen[1][1]["type"] == "search" and seen[1][1]["start"] == "40" and len(places) == 2
    hours = P.place_item({"title": "x", "website": "https://x.test", "operating_hours": {"monday": "9–5"}},
                         today=TODAY)
    assert hours.fields["hours"]["value"] == "monday: 9–5"


def test_configured_and_choose(monkeypatch):
    monkeypatch.setattr(P, "_keys", lambda: ("k", "s"))
    assert P.configured() and isinstance(P.choose_provider(), P.SearchApi)
    monkeypatch.setattr(P, "_keys", lambda: (None, "s"))
    assert P.configured() and isinstance(P.choose_provider(), P.SerpApi)
    monkeypatch.setattr(P, "_keys", lambda: (None, None))
    assert not P.configured() and P.choose_provider() is None

    def boom():
        raise RuntimeError("settings")

    monkeypatch.setattr(P, "_keys", boom)
    assert P.configured() is False
