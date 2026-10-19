"""Google Maps from Google's own Places API: parsing, paging, errors. (Google
Shopping and the SERP APIs, SearchAPI and SerpApi, were taken out on 2026-10-18.)"""
import json
from types import SimpleNamespace

import httpx
import pytest

from app.matcha.services.matcha_work.agent_tasks.research import geo
from app.matcha.services.matcha_work.agent_tasks.research import providers as P

from ._fixtures import TODAY


async def _no_sleep(_s):
    return None


GOOGLE_PRODUCT = "https://www.google.com/search?ibp=oshop&q=organic lip balm&prds=catalogid:1,productid:2"


def test_google_pages_are_never_a_stores_own():
    assert P.is_google("https://shopping.google.co.uk/p") and P.is_google(GOOGLE_PRODUCT)
    # Ad clicks: following one would register a paid click.
    assert P.is_google("https://www.googleadservices.com/pagead/aclk?sa=L") and P.is_google("https://ad.doubleclick.net/x")
    assert P.store_link("https://www.googleadservices.com/pagead/aclk?sa=L") is None
    assert not P.is_google("https://www.drbronner.com/x") and not P.is_google(None)
    assert P.store_link("https://www.google.com/url?url=https://shop.test/a") == "https://shop.test/a"
    assert P.store_link("https://www.google.com/url?q=https://www.google.com/x") is None
    assert P.store_link("https://www.google.com/aclk?x=1") is None and P.store_link("ftp://x.test") is None


# Google Maps straight from Google's Places API (New). Shapes trimmed from a
# real Text Search answer (2026-10-15: "apartments" north of Lady Bird Lake).
PLACES = {"places": [
    {"id": "ChIJBablpjPNRIYRW_spWlRLRCY", "nationalPhoneNumber": "(512) 331-0013",
     "formattedAddress": "13359 Pond Springs Rd, Austin, TX 78729, USA",
     "location": {"latitude": 30.4490711, "longitude": -97.7824956}, "rating": 4.1,
     "websiteUri": "http://hiddentimberapts.com/",
     "regularOpeningHours": {"weekdayDescriptions": ["Monday: 9:00 AM – 5:30 PM", "Saturday: Closed"]},
     "businessStatus": "OPERATIONAL", "userRatingCount": 63, "priceLevel": "PRICE_LEVEL_MODERATE",
     "displayName": {"text": "Hidden Timber Apartments", "languageCode": "en"},
     "primaryTypeDisplayName": {"text": "Apartment complex", "languageCode": "en"}},
    {"id": "noSite", "displayName": {"text": "Oak Flats"}, "location": {"latitude": 30.5, "longitude": -97.7}},
    {"id": "gone", "displayName": {"text": "Closed Lofts"}, "websiteUri": "https://gone.test",
     "businessStatus": "CLOSED_PERMANENTLY"},
    {"id": "nameless"}, "junk",
], "nextPageToken": "page-2"}


def _places(handler):
    return P.GooglePlaces("gkey", transport=httpx.MockTransport(handler), sleep=_no_sleep, today=lambda: TODAY)


def test_a_places_search_costs_a_call_per_page():
    places = _places(lambda request: httpx.Response(200, json={}))
    assert [P.calls_per_search(places, n) for n in (1, 2, P.MAX_PAGES, P.MAX_PAGES + 1)] == [1, 2, P.MAX_PAGES, 0]


@pytest.mark.asyncio
async def test_google_places_become_verified_findings_inside_the_map_box():
    seen = []

    def handler(request):
        seen.append((str(request.url), request.headers, json.loads(request.content)))
        return httpx.Response(200, json=PLACES)

    timber, oak = await _places(handler).search("places", "apartments", ll="@30.46478,-97.71810,13z")
    url, headers, body = seen[0]
    assert url == P.PLACES_URL and headers["X-Goog-Api-Key"] == "gkey"
    assert "places.websiteUri" in headers["X-Goog-FieldMask"] and "nextPageToken" in headers["X-Goog-FieldMask"]
    assert body["textQuery"] == "apartments" and body["pageSize"] == P.MAX_RESULTS and "pageToken" not in body
    box = body["locationRestriction"]["rectangle"]
    assert box["low"]["latitude"] < 30.46478 < box["high"]["latitude"]
    assert box["low"]["longitude"] < -97.7181 < box["high"]["longitude"]
    assert timber.url == "http://hiddentimberapts.com/" and timber.provider == "google_maps"
    assert timber.provider_id == "ChIJBablpjPNRIYRW_spWlRLRCY" and timber.point == (30.4490711, -97.7824956)
    assert timber.subtitle.startswith("13359 Pond Springs Rd") and timber.fields["phone"]["evidence"]["origin"] == "provider"
    assert timber.fields["rating"]["value"] == 4.1 and timber.fields["review_count"]["value"] == 63
    assert timber.fields["price_level"]["value"] == "$$" and timber.fields["cuisine"]["value"] == "Apartment complex"
    assert timber.fields["hours"]["value"].startswith("Monday: 9:00 AM")
    # No site of its own: its Google Maps page. Closed for good: skipped.
    assert oak.url.startswith("https://www.google.com/maps/search/") and "noSite" in oak.url
    await _places(handler).search("places", "apartments Round Rock TX")
    assert "locationRestriction" not in seen[-1][2]
    with pytest.raises(ValueError):
        await _places(handler).search("shopping", "lip balm")


@pytest.mark.asyncio
async def test_google_places_pages_by_token():
    bodies = []

    def handler(request):
        body = json.loads(request.content)
        bodies.append(body)
        return httpx.Response(200, json={"places": PLACES["places"][:1]} if body.get("pageToken") else PLACES)

    assert len(await _places(handler).search("places", "apartments", page=2)) == 1
    assert [b.get("pageToken") for b in bodies] == [None, "page-2"]
    # The second page has no token, so there is no third.
    bodies.clear()
    assert await _places(handler).search("places", "apartments", page=3) == [] and len(bodies) == 2
    assert await _places(handler).search("places", "apartments", page=P.MAX_PAGES + 1) == [] and len(bodies) == 2


@pytest.mark.asyncio
async def test_google_places_locates_one_place():
    seen = []

    def handler(request):
        seen.append((request.headers["X-Goog-FieldMask"], json.loads(request.content)))
        return httpx.Response(200, json={"places": [
            {"location": {"latitude": 30.2476846, "longitude": -97.7181049}, "displayName": {"text": "Lady Bird Lake"}}]})

    assert await _places(handler).locate("Lady Bird Lake, Austin, TX") == ("Lady Bird Lake", (30.2476846, -97.7181049))
    assert seen[0] == (P.LOCATE_MASK, {"textQuery": "Lady Bird Lake, Austin, TX", "pageSize": 1, "languageCode": "en"})
    assert await _places(lambda _r: httpx.Response(200, json={})).locate("Atlantis") is None


@pytest.mark.asyncio
async def test_google_places_errors_say_what_google_said():
    denied = httpx.Response(403, json={"error": {"code": 403, "message": "Places API (New) has not been used",
                                                 "status": "PERMISSION_DENIED"}})
    with pytest.raises(P.ProviderError, match="PERMISSION_DENIED") as exc:
        await _places(lambda _r: denied).search("places", "x")
    assert exc.value.fatal
    calls = {"n": 0}

    def busy(_request):
        calls["n"] += 1
        return httpx.Response(429, json={"error": {"status": "RESOURCE_EXHAUSTED"}}) if calls["n"] == 1 \
            else httpx.Response(200, json={})

    assert await _places(busy).search("places", "x") == [] and calls["n"] == 2


def test_a_map_box_is_the_area_the_map_shows():
    centre = (30.46478, -97.7181)
    box = P.map_box("@30.46478,-97.71810,13z")
    assert round(geo.miles(centre, (box["high"]["latitude"], centre[1]))) == 5
    assert round(geo.miles(centre, (centre[0], box["high"]["longitude"]))) == 5
    wide = P.map_box("@30.46478,-97.71810,12z")
    assert round(geo.miles(centre, (wide["low"]["latitude"], centre[1]))) == 10
    assert P.map_box(None) is None and P.map_box("30.4,-97.7") is None


def test_places_come_from_google_and_nothing_else(monkeypatch):
    """No search API: places are Google's own API or nothing, and every other
    source (products among them) has no provider."""
    monkeypatch.setattr(P, "_google_key", lambda: "g")
    listings = P.choose_provider("places")
    assert [type(api) for api in listings.apis] == [P.GooglePlaces]
    assert P.choose_provider("shopping") is None and P.choose_provider() is None
    monkeypatch.setattr(P, "_google_key", lambda: None)
    assert P.choose_provider("places") is None
    assert not hasattr(P, "SearchApi") and not hasattr(P, "SerpApi") and not hasattr(P, "configured")


def test_the_google_key_is_the_maps_platform_key(monkeypatch):
    import app.config as config

    monkeypatch.setattr(config, "get_settings", lambda: SimpleNamespace(google_maps_api_key="maps-key"))
    assert P._google_key() == "maps-key"
    monkeypatch.setattr(config, "get_settings", lambda: SimpleNamespace(google_maps_api_key=""))
    assert P._google_key() is None


@pytest.mark.asyncio
async def test_listings_ask_google_and_say_when_it_is_down(caplog):
    asked = []

    def handler(request):
        asked.append(json.loads(request.content)["textQuery"])
        if asked[-1] == "down":
            return httpx.Response(503)
        if asked[-1] == "Lady Bird Lake":
            return httpx.Response(200, json={"places": [
                {"location": {"latitude": 30.25, "longitude": -97.72}, "displayName": {"text": "Lady Bird Lake"}}]})
        return httpx.Response(200, json=PLACES)

    listings = P.Listings([_places(handler)])
    assert len(await listings.search("places", "apartments")) == 2
    assert len(await listings.search_pages("places", "apartments", pages=1)) == 2
    assert await listings.locate("Lady Bird Lake") == ("Lady Bird Lake", (30.25, -97.72))
    with pytest.raises(P.ProviderError):
        await listings.search("places", "down")
    assert asked.count("down") == 2, "asked once more, then down"


@pytest.mark.asyncio
async def test_google_places_search_pages_walks_the_tokens_once():
    bodies = []

    def handler(request):
        body = json.loads(request.content)
        bodies.append(body)
        token = body.get("pageToken")
        nxt = {None: "page-2", "page-2": "page-3", "page-3": None}[token]
        return httpx.Response(200, json={"places": PLACES["places"][:1], **({"nextPageToken": nxt} if nxt else {})})

    items = await _places(handler).search_pages("places", "coffee shops in Silver Lake", pages=3)
    # Three pages for three calls, where search(page=1..3) would have made six.
    assert len(items) == 3 and [b.get("pageToken") for b in bodies] == [None, "page-2", "page-3"]
    bodies.clear()
    assert len(await _places(handler).search_pages("places", "x", pages=P.MAX_PAGES + 2)) == 3 and len(bodies) == 3
