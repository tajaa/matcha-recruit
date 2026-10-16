"""Google Shopping and Google Maps through SearchAPI, and Google Maps from
Google's own Places API: parsing, retries, errors."""
import json
from types import SimpleNamespace

import httpx
import pytest

from app.matcha.services.matcha_work.agent_tasks.research import geo
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


# Shopping results link to Google's product page; the store's own page comes
# from a second call. Shapes trimmed from a real SerpApi response (2026-10-14)
# and SearchAPI's documented `google_product_offers` response.
GOOGLE_PRODUCT = "https://www.google.com/search?ibp=oshop&q=organic lip balm&prds=catalogid:1,productid:2"
SERP_SHOP = {"shopping_results": [
    {"title": "Dr Bronner's Organic Lip Balm", "source": "Dr. Bronner's", "price": "$3.99", "extracted_price": 3.99,
     "product_link": GOOGLE_PRODUCT, "product_id": "8587175971051732824", "immersive_product_page_token": "serp-token"},
]}
SEARCHAPI_SHOP = {"shopping_results": [
    {"title": "Lip Balm", "seller": "Walmart", "price": "$4.97", "extracted_price": 4.97,
     "product_link": "https://www.google.com/shopping/product/545?gl=us", "offers_link": "https://www.google.com/x",
     "product_token": "searchapi-token"},
]}
SERP_STORES = {"product_results": {"stores": [
    {"name": "Dr. Bronner's", "price": "$3.99", "extracted_price": 3.99,
     "link": "https://www.drbronner.com/products/peppermint-organic-lip-balms?variant=3602&utm_source=goog"},
    {"name": "Target", "price": "$3.89", "extracted_price": 3.89, "link": "https://www.target.com/p/balm/-/A-948"},
    {"name": "Google", "link": "https://www.google.com/shopping/x"},
    {"name": "", "link": "https://nameless.test/x"},
    "junk",
]}}
SEARCHAPI_OFFERS = {"offers": [
    {"merchant": {"name": "Walmart"}, "price": "$4.97", "extracted_price": 4.97,
     "link": "https://www.google.com/url?q=https://www.walmart.com/ip/balm/154&sa=U"},
    {"seller": "Dell", "price": "$5.10", "extracted_price": 5.1, "link": "https://www.dell.test/balm"},
    {"merchant": "not a dict", "link": "https://x.test"},
]}


@pytest.mark.asyncio
async def test_shopping_results_keep_the_token_for_their_stores():
    def handler(request):
        engine = request.url.params["engine"]
        return httpx.Response(200, json={"google_shopping": SERP_SHOP, "google_immersive_product": SERP_STORES}[engine])

    api = _api(handler, cls=P.SerpApi)
    [balm] = await api.search("shopping", "organic lip balm")
    assert balm.url == GOOGLE_PRODUCT and balm.offers_token == "serp-token" and P.is_google(balm.url)
    stores = await api.stores("serp-token")
    assert [s.name for s in stores] == ["Dr. Bronner's", "Target"]
    assert stores[0].link.startswith("https://www.drbronner.com/") and stores[0].price == 3.99

    seen = []

    def searchapi(request):
        seen.append(dict(request.url.params))
        return httpx.Response(200, json=SEARCHAPI_SHOP if request.url.params["engine"] == "google_shopping" else SEARCHAPI_OFFERS)

    api = _api(searchapi)
    [balm] = await api.search("shopping", "lip balm")
    assert balm.offers_token == "searchapi-token" and balm.subtitle == "Walmart"
    walmart, dell = await api.stores("searchapi-token")
    assert seen[-1]["engine"] == "google_product_offers" and seen[-1]["product_token"] == "searchapi-token"
    # Google's redirect is unwrapped to the store's own page.
    assert walmart.name == "Walmart" and walmart.link == "https://www.walmart.com/ip/balm/154"
    assert dell.name == "Dell" and dell.price == 5.1
    assert P.shopping_item({"title": "x", "product_link": GOOGLE_PRODUCT, "product_token": "t" * 5000}, today=TODAY).offers_token is None
    assert P.SearchApi("k")._stores({"offers": "nope"}) == [] and P.SerpApi("k")._stores({"product_results": []}) == []


def test_a_finding_moves_to_its_sellers_own_page():
    balm = P.shopping_item({**SERP_SHOP["shopping_results"][0], "delivery": "Free delivery", "rating": 4.7},
                           today=TODAY)
    stores = P.SerpApi("k")._stores(SERP_STORES)
    # The listing's seller sells it: same facts, its own page.
    moved = P.with_store(balm, stores, today=TODAY)
    assert moved.url.startswith("https://www.drbronner.com/products/") and moved.subtitle == "Dr. Bronner's"
    assert moved.fields == balm.fields and moved.offers_token == "serp-token"
    # The seller isn't among the stores: the first store, its price and name;
    # the listing's delivery note was the other seller's.
    other = P.with_store(balm, stores[1:], today=TODAY)
    assert other.url == "https://www.target.com/p/balm/-/A-948" and other.subtitle == "Target"
    assert other.fields["price"]["value"] == 3.89 and other.fields["seller"]["value"] == "Target"
    assert "shipping" not in other.fields and other.fields["rating"]["value"] == 4.7
    assert other.fields["price"]["evidence"]["origin"] == "provider"
    no_price = P.with_store(balm, [P.Store(name="Shop", link="https://shop.test/b")], today=TODAY)
    assert "price" not in no_price.fields and no_price.fields["seller"]["value"] == "Shop"
    assert P.with_store(balm, [], today=TODAY) is balm


def test_a_fallback_store_keeps_the_listings_currency():
    listing = P.shopping_item({"title": "Balm", "source": "Boots", "price": "£4.50", "extracted_price": 4.5,
                               "currency": "GBP", "product_link": GOOGLE_PRODUCT}, today=TODAY)
    other = P.with_store(listing, [P.Store(name="Superdrug", link="https://superdrug.test/balm", price=4.25)],
                         today=TODAY)
    assert other.fields["price"]["value"] == 4.25 and other.fields["price"]["currency"] == "GBP"


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
    assert P.calls_per_search(P.SearchApi("key"), 3) == 1  # the SERP APIs take the page number


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


@pytest.mark.asyncio
async def test_a_spent_search_api_says_so_and_is_not_asked_again():
    asked = []
    spent = httpx.Response(429, json={"error": "You have used all of the searches for the month."})
    with pytest.raises(P.ProviderError, match="used all of the searches") as exc:
        await _api(lambda r: asked.append(r) or spent).search("shopping", "x")
    assert exc.value.fatal and len(asked) == 1


def test_a_map_box_is_the_area_the_map_shows():
    centre = (30.46478, -97.7181)
    box = P.map_box("@30.46478,-97.71810,13z")
    assert round(geo.miles(centre, (box["high"]["latitude"], centre[1]))) == 5
    assert round(geo.miles(centre, (centre[0], box["high"]["longitude"]))) == 5
    wide = P.map_box("@30.46478,-97.71810,12z")
    assert round(geo.miles(centre, (wide["low"]["latitude"], centre[1]))) == 10
    assert P.map_box(None) is None and P.map_box("30.4,-97.7") is None


def test_places_come_from_google_when_its_key_is_set(monkeypatch):
    monkeypatch.setattr(P, "_keys", lambda: ("k", None))
    monkeypatch.setattr(P, "_google_key", lambda: "g")
    assert isinstance(P.choose_provider("places"), P.GooglePlaces)
    assert isinstance(P.choose_provider("shopping"), P.SearchApi) and isinstance(P.choose_provider(), P.SearchApi)
    monkeypatch.setattr(P, "_google_key", lambda: None)
    assert isinstance(P.choose_provider("places"), P.SearchApi)
    monkeypatch.setattr(P, "_keys", lambda: (None, None))
    assert P.choose_provider("places") is None


def test_the_google_key_is_the_maps_platform_key(monkeypatch):
    import app.config as config

    monkeypatch.setattr(config, "get_settings", lambda: SimpleNamespace(google_maps_api_key="maps-key"))
    assert P._google_key() == "maps-key"
    monkeypatch.setattr(config, "get_settings", lambda: SimpleNamespace(google_maps_api_key=""))
    assert P._google_key() is None
