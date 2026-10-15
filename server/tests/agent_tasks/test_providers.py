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


def test_google_pages_are_never_a_stores_own():
    assert P.is_google("https://shopping.google.co.uk/p") and P.is_google(GOOGLE_PRODUCT)
    assert not P.is_google("https://www.drbronner.com/x") and not P.is_google(None)
    assert P.store_link("https://www.google.com/url?url=https://shop.test/a") == "https://shop.test/a"
    assert P.store_link("https://www.google.com/url?q=https://www.google.com/x") is None
    assert P.store_link("https://www.google.com/aclk?x=1") is None and P.store_link("ftp://x.test") is None
