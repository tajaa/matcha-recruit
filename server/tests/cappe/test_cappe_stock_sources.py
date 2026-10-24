"""Open-image sources for the magazine Library (services/magazine/sources).

The fixtures in tests/cappe/fixtures/stock/ are real responses, trimmed,
captured 2026-10-21. What each block pins:

  * each archive's results become the same shape, with the credit we print;
  * only CC0 / public domain / CC BY / CC BY-SA, nothing mature — whatever
    the archive's own filter claims (the Met's `isPublicDomain` search filter
    let copyrighted works through when this was written);
  * NASA leaves out third-party pictures and takes a size its manifest lists;
  * Smithsonian keeps each image's own CC0 mark and resizes at the source;
  * the registry caches searches for everyone, re-checks on a fresh resolve,
    and filters on the way out;
  * Openverse uses a client-credentials token when one is configured and
    falls back to anonymous when the exchange fails;
  * signed thumbnail links: only ours verify, and they expire.

Run from server/:  ./venv/bin/python -m pytest tests/cappe/test_cappe_stock_sources.py -q
"""
import asyncio
import io
import json
import os
import pathlib
from types import SimpleNamespace

os.environ.setdefault("LIVE_API", "test-key")
os.environ.setdefault("DATABASE_URL", "postgresql://test:test@localhost/test")
os.environ.setdefault("JWT_SECRET_KEY", "test-secret-key-cappe")

import pytest  # noqa: E402
from PIL import Image  # noqa: E402

from app.config import load_settings  # noqa: E402

load_settings()

from app.cappe.services.magazine import sources  # noqa: E402
from app.cappe.services.magazine.sources import base, credit, met, nasa, openverse, smithsonian, stock, thumbs  # noqa: E402

FIX = pathlib.Path(__file__).parent / "fixtures" / "stock"


def fixture(name):
    return json.loads((FIX / name).read_text())


def run(coro):
    return asyncio.run(coro)


# ── each archive ─────────────────────────────────────────────────────────────

def test_openverse_results_carry_their_license_and_credit():
    results = [openverse.normalize(i) for i in fixture("openverse_search.json")["results"]]
    first = results[0]
    assert (first.source, first.license, first.license_version) == ("openverse", "by", "2.0")
    assert first.credit_line == "“Street fashion” by Giuseppe Milo (www.pixael.com) / CC BY 2.0 via Flickr"
    assert first.landing_url.startswith("https://www.flickr.com/photos/")
    assert first.image_url.startswith("https://live.staticflickr.com/")
    assert first.thumb_url.startswith("https://api.openverse.org/v1/images/")
    assert all(r is not None for r in results)
    http = openverse.normalize({**fixture("openverse_search.json")["results"][0], "url": "http://x.test/a.jpg"})
    assert http.image_url == "https://x.test/a.jpg"  # upgraded, never fetched over http


@pytest.mark.parametrize("change", [{"license": "by-nc"}, {"license": "by-nd"}, {"mature": True}, {"url": ""},
                                    {"url": "ftp://x.test/x.jpg"}, {"id": None}])
def test_openverse_drops_what_we_cant_publish(change):
    item = {**fixture("openverse_search.json")["results"][0], **change}
    assert openverse.normalize(item) is None


def test_smithsonian_keeps_each_cc0_image_and_resizes_at_the_source():
    rows = fixture("smithsonian_search.json")["response"]["rows"]
    results = smithsonian.normalize(rows[0])
    assert len(results) == 1
    r = results[0]
    assert r.license == "cc0" and r.source_id == f"{rows[0]['id']}|SAAM-1929.6.159_1"
    assert r.image_url == "https://ids.si.edu/ids/deliveryService?id=SAAM-1929.6.159_1&max=2048"
    assert r.thumb_url.endswith("&max=400")
    assert (r.width, r.height) == (1363, 2048)  # 1996x3000 scaled to fit 2048
    assert r.creator == "James McNeill Whistler"  # "born …-died …" trimmed
    assert r.credit_line == "James McNeill Whistler / Smithsonian American Art Museum (CC0)"
    assert r.landing_url == "https://americanart.si.edu/collections/search/artwork/?id=27615"


def test_smithsonian_skips_an_image_that_isnt_cc0_itself():
    row = json.loads(json.dumps(fixture("smithsonian_search.json")["response"]["rows"][0]))
    row["content"]["descriptiveNonRepeating"]["online_media"]["media"][0]["usage"]["access"] = "Usage conditions apply"
    assert smithsonian.normalize(row) == []
    row["content"]["descriptiveNonRepeating"]["online_media"]["media"][0]["usage"]["access"] = "CC0"
    row["content"]["descriptiveNonRepeating"]["online_media"]["media"][0]["type"] = "3d_package"
    assert smithsonian.normalize(row) == []


def test_the_met_decides_by_each_objects_own_rights():
    pd = met.normalize(fixture("met_object_public_domain.json"))
    assert pd.license == "cc0" and pd.creator == "Thomas Rowlandson"
    assert pd.image_url.startswith("https://images.metmuseum.org/") and "web-large" in pd.thumb_url
    assert pd.credit_line == "Thomas Rowlandson / The Metropolitan Museum of Art (CC0)"
    assert met.normalize(fixture("met_object_copyrighted.json")) is None


def test_nasa_credits_the_center_and_skips_third_party_pictures():
    items = fixture("nasa_search.json")["collection"]["items"]
    r = nasa.normalize(items[0])
    assert r.license == "pdm" and r.credit_line == "NASA/GSFC"
    assert r.image_url.endswith("/collection.json") and r.thumb_url.endswith("~small.jpg")
    assert r.landing_url == "https://images.nasa.gov/details/GSFC_20171208_Archive_e000746"
    courtesy = json.loads(json.dumps(items[0]))
    courtesy["data"][0]["description"] = "Image courtesy of Some Agency. All rights reserved."
    assert nasa.normalize(courtesy) is None
    photographer = json.loads(json.dumps(items[0]))
    photographer["data"][0]["photographer"] = "Bill Ingalls"
    assert nasa.normalize(photographer).credit_line == "NASA/GSFC/Bill Ingalls"


def test_nasa_takes_the_largest_size_its_manifest_lists():
    manifest = fixture("nasa_manifest.json")
    assert nasa.best_file(manifest) == (
        "https://images-assets.nasa.gov/image/GSFC_20171208_Archive_e000746/GSFC_20171208_Archive_e000746~orig.jpg")
    assert nasa.best_file(manifest + ["http://x.test/a~large.jpg"]) == "https://x.test/a~large.jpg"
    assert nasa.best_file({"not": "a list"}) == ""


def test_credit_lines():
    r = base.StockResult(source="openverse", source_id="1", title="", creator="Ana", license="pdm", license_version="",
                         license_url="", provider_label="Wikimedia Commons", landing_url="", image_url="x", thumb_url="")
    assert credit.credit_line(r) == "Photo: Ana / public domain via Wikimedia Commons"
    r.license, r.creator, r.title = "cc0", "", "Harbour"
    assert credit.credit_line(r) == "“Harbour” / CC0 via Wikimedia Commons"
    r.license, r.creator, r.license_version = "by-sa", "Jo", "4.0"
    assert credit.credit_line(r) == "“Harbour” by Jo / CC BY-SA 4.0 via Wikimedia Commons"
    r.title = ""
    assert credit.credit_line(r) == "Photo: Jo / CC BY-SA 4.0 via Wikimedia Commons"
    r.source, r.creator, r.license = "met", "", "cc0"
    r.provider_label = "The Metropolitan Museum of Art"
    assert credit.credit_line(r) == "The Metropolitan Museum of Art (CC0)"


# ── the registry ─────────────────────────────────────────────────────────────

def _result(**over):
    base_ = dict(source="openverse", source_id="abc", title="t", creator="c", license="by", license_version="2.0",
                 license_url="", provider_label="Flickr", landing_url="", image_url="https://x.test/a.jpg",
                 thumb_url="https://x.test/t.jpg")
    return base.StockResult(**{**base_, **over})


def test_search_is_cached_for_everyone_and_filtered(monkeypatch):
    calls = []

    async def fake_search(q, page):
        calls.append((q, page))
        return [_result(), _result(source_id="nc", license="by-nc"), _result(source_id="m", mature=True)]

    store = {}

    async def cache_get(_r, key):
        return store.get(key)

    async def cache_set(_r, key, value, ttl):
        store[key] = value

    monkeypatch.setattr(openverse, "search", fake_search)
    monkeypatch.setattr(base, "get_redis_cache", lambda: object())
    monkeypatch.setattr(base, "cache_get", cache_get)
    monkeypatch.setattr(base, "cache_set", cache_set)
    first = run(sources.search("openverse", "  Street   fashion ", 0))
    again = run(sources.search("openverse", "street fashion", 0))
    assert [r.source_id for r in first] == ["abc"] == [r.source_id for r in again]
    assert calls == [("Street fashion", 0)]  # the second came from the cache
    assert run(sources.search("openverse", "   ", 0)) == []
    with pytest.raises(KeyError):
        run(sources.search("unsplash", "x", 0))


def test_resolve_fresh_skips_the_cache_and_still_filters(monkeypatch):
    async def resolve_nc(source_id):
        return _result(license="by-nc")

    async def resolve_ok(source_id):
        return _result()

    monkeypatch.setattr(base, "get_redis_cache", lambda: None)
    monkeypatch.setattr(openverse, "resolve", resolve_nc)
    assert run(sources.resolve("openverse", "abc", fresh=True)) is None
    monkeypatch.setattr(openverse, "resolve", resolve_ok)
    assert run(sources.resolve("openverse", "abc", fresh=True)).source_id == "abc"
    assert run(sources.resolve("openverse", "abc")).source_id == "abc"


def test_page_numbers_and_queries_are_bounded(monkeypatch):
    seen = []

    async def fake_search(q, page):
        seen.append((q, page))
        return []

    monkeypatch.setattr(base, "get_redis_cache", lambda: None)
    monkeypatch.setattr(nasa, "search", fake_search)
    run(sources.search("nasa", "x" * 500, 999))
    assert seen == [("x" * sources.MAX_QUERY, sources.MAX_PAGE)]


# ── calling the archives ─────────────────────────────────────────────────────

class Fetched(SimpleNamespace):
    pass


def _fetch(responses):
    calls = []

    async def fake(url, **kw):
        calls.append(url)
        for needle, (status_, body) in responses.items():
            if needle in url:
                data = body if isinstance(body, bytes) else json.dumps(body).encode()
                return Fetched(status=status_, truncated=False, body=data, content_type="application/json")
        raise AssertionError(f"unexpected fetch {url}")

    return fake, calls


def test_smithsonian_met_and_nasa_search_and_resolve_through_the_guarded_fetcher(monkeypatch):
    si = fixture("smithsonian_search.json")
    fake, calls = _fetch({
        "api.si.edu/openaccess/api/v1.0/search": (200, si),
        "api.si.edu/openaccess/api/v1.0/content/": (200, {"response": si["response"]["rows"][0]}),
        "v1.1/search": (200, {"total": 2, "objectIDs": [363984, 490097]}),
        "objects/363984": (200, fixture("met_object_public_domain.json")),
        "objects/490097": (200, fixture("met_object_copyrighted.json")),
        "images-api.nasa.gov/search": (200, fixture("nasa_search.json")),
        "collection.json": (200, fixture("nasa_manifest.json")),
    })
    monkeypatch.setattr(base, "fetch_public", fake)
    monkeypatch.setattr(base, "get_redis_cache", lambda: None)

    found = run(smithsonian.search("harbor", 0))
    assert found and "online_visual_material%3Atrue" in calls[0] and "api_key=DEMO_KEY" in calls[0]
    assert run(smithsonian.resolve(found[0].source_id)).source_id == found[0].source_id
    assert run(smithsonian.resolve("no-separator")) is None

    met_found = run(met.search("harbor boats", 0))
    assert [r.source_id for r in met_found] == ["363984"]  # the copyrighted one is dropped
    assert run(met.resolve("363984")).source_id == "363984"
    assert run(met.resolve("../etc")) is None

    nasa_found = run(nasa.search("earth from orbit", 0))
    assert len(nasa_found) == 3
    resolved = run(nasa.resolve(nasa_found[0].source_id))
    assert resolved.image_url.endswith("~orig.jpg")


def test_an_archive_that_fails_raises_source_error(monkeypatch):
    async def down(url, **kw):
        raise TimeoutError

    monkeypatch.setattr(base, "fetch_public", down)
    with pytest.raises(base.SourceError):
        run(met.search("x", 0))
    fake, _ = _fetch({"images-api": (503, {}), "metmuseum": (200, b"<html>")})
    monkeypatch.setattr(base, "fetch_public", fake)
    with pytest.raises(base.SourceError, match="HTTP 503"):
        run(nasa.search("x", 0))
    with pytest.raises(base.SourceError, match="not JSON"):
        run(met.resolve("1"))
    fake404, _ = _fetch({"metmuseum": (404, {})})
    monkeypatch.setattr(base, "fetch_public", fake404)
    assert run(met.resolve("1")) is None


def test_one_bad_met_object_never_sinks_the_page(monkeypatch):
    fake, _ = _fetch({"v1.1/search": (200, {"objectIDs": [363984, 1]}),
                      "objects/363984": (200, fixture("met_object_public_domain.json")),
                      "objects/1": (500, {})})
    monkeypatch.setattr(base, "fetch_public", fake)
    monkeypatch.setattr(base, "get_redis_cache", lambda: None)
    assert [r.source_id for r in run(met.search("x", 0))] == ["363984"]


class FakeResponse:
    def __init__(self, status, data):
        self.status_code, self._data = status, data

    def json(self):
        if isinstance(self._data, bytes):
            raise ValueError("not json")
        return self._data

    def raise_for_status(self):
        if self.status_code >= 400:
            raise RuntimeError(self.status_code)


class FakeClient:
    def __init__(self, routes, log):
        self.routes, self.log = routes, log

    async def __aenter__(self):
        return self

    async def __aexit__(self, *exc):
        return False

    async def post(self, url, data=None, headers=None):
        self.log.append(("POST", url, data))
        return self.routes["token"]

    async def get(self, url, params=None, headers=None):
        self.log.append(("GET", url, headers))
        return self.routes["get"]


def test_openverse_uses_a_token_when_configured_and_falls_back_when_it_fails(monkeypatch):
    log = []
    routes = {"token": FakeResponse(200, {"access_token": "tok", "expires_in": 3600}),
              "get": FakeResponse(200, fixture("openverse_search.json"))}
    monkeypatch.setattr(openverse.httpx, "AsyncClient", lambda **kw: FakeClient(routes, log))
    monkeypatch.setattr(openverse, "get_redis_cache", lambda: None)
    monkeypatch.setattr(openverse, "get_settings",
                        lambda: SimpleNamespace(openverse_client_id="id", openverse_client_secret="secret"))
    results = run(openverse.search("street fashion", 0))
    assert len(results) == 3
    assert log[0][0] == "POST" and log[0][2]["grant_type"] == "client_credentials"
    assert log[1][2]["Authorization"] == "Bearer tok"

    log.clear()
    routes["token"] = FakeResponse(401, {})
    run(openverse.search("street fashion", 0))
    assert "Authorization" not in log[-1][2]

    log.clear()
    monkeypatch.setattr(openverse, "get_settings",
                        lambda: SimpleNamespace(openverse_client_id=None, openverse_client_secret=None))
    routes["get"] = FakeResponse(200, fixture("openverse_search.json")["results"][0])
    assert run(openverse.resolve("2df75d75-7772-46c2-918a-2f2af893690d")).source == "openverse"
    assert log[0][0] == "GET" and "Authorization" not in log[0][2]
    assert run(openverse.resolve("../../auth_tokens")) is None
    log.clear()
    assert run(openverse.search("x", openverse.ANON_PAGES)) == []  # anonymous paging stops at 240
    assert log == []


class ParamsClient(FakeClient):
    async def get(self, url, params=None, headers=None):
        self.log.append(("GET", url, params))
        return self.routes["get"]


def test_free_photos_are_openverses_cc0_stock_collections_browsable_with_no_words(monkeypatch):
    snap = {**fixture("openverse_search.json")["results"][0], "source": "stocksnap", "provider": "stocksnap",
            "license": "cc0", "license_version": "1.0", "creator": "Ana Ruiz"}
    log = []
    routes = {"get": FakeResponse(200, {"results": [snap]})}
    monkeypatch.setattr(openverse.httpx, "AsyncClient", lambda **kw: ParamsClient(routes, log))
    monkeypatch.setattr(openverse, "get_settings",
                        lambda: SimpleNamespace(openverse_client_id=None, openverse_client_secret=None))
    monkeypatch.setattr(base, "get_redis_cache", lambda: None)
    results, more = run(sources.search_page("stock", "", 0))
    params = log[-1][2]
    assert "q" not in params and params["source"] == "stocksnap,wordpress,nappy" and params["license"] == "cc0,pdm"
    assert more and results[0].source == "openverse"  # imported, credited and re-checked as Openverse's
    assert results[0].credit_line == "Photo: Ana Ruiz / CC0 via StockSnap.io"
    run(sources.search_page("stock", "  coffee  ", 1))
    assert log[-1][2]["q"] == "coffee" and log[-1][2]["page"] == 2
    run(openverse.search("coffee", 0))
    assert "source" not in log[-1][2] and log[-1][2]["license"] == ",".join(sorted(base.ALLOWED_LICENSES))
    assert sources.browsable("stock") and not sources.browsable("met")
    assert openverse.normalize(fixture("openverse_search.json")["results"][0]).tags[:2] == ["blackandwhite", "bw"]
    assert run(sources.search_page("met", "   ", 0)) == ([], False)  # an archive needs words
    assert stock.resolve is not None and stock.NAME in sources.SOURCES


def test_free_photo_searches_are_kept_a_day_archives_an_hour(monkeypatch):
    kept = {}

    async def cached(kind, parts, ttl, load):
        kept[parts[0]] = ttl
        return []

    monkeypatch.setattr(sources, "cached", cached)
    run(sources.search_page("stock", "coffee", 0))
    run(sources.search_page("met", "coffee", 0))
    assert kept == {"stock": 86400, "met": base.SEARCH_TTL}


def test_openverse_errors(monkeypatch):
    log = []
    routes = {"get": FakeResponse(429, {})}
    monkeypatch.setattr(openverse.httpx, "AsyncClient", lambda **kw: FakeClient(routes, log))
    monkeypatch.setattr(openverse, "get_settings",
                        lambda: SimpleNamespace(openverse_client_id=None, openverse_client_secret=None))
    with pytest.raises(base.SourceError, match="429"):
        run(openverse.search("x", 0))
    routes["get"] = FakeResponse(404, {})
    assert run(openverse.resolve("00000000-0000-0000-0000-000000000000")) is None
    routes["get"] = FakeResponse(200, b"<html>")
    with pytest.raises(base.SourceError, match="not JSON"):
        run(openverse.search("x", 0))


# ── signed thumbnails ────────────────────────────────────────────────────────

def test_only_our_thumbnail_links_verify_and_they_expire():
    token = thumbs.sign("https://api.openverse.org/v1/images/x/thumb/", now=1_000)
    assert thumbs.verify(token, now=1_001) == "https://api.openverse.org/v1/images/x/thumb/"
    assert thumbs.verify(token, now=1_000 + thumbs.TTL_SECONDS + 1) is None
    payload, mac = token.split(".")
    forged = thumbs._b64(json.dumps({"u": "https://evil.test/x", "e": 9_999_999_999}).encode())
    assert thumbs.verify(f"{forged}.{mac}", now=1_001) is None
    assert thumbs.verify("nonsense", now=1_001) is None
    assert thumbs.verify(thumbs.sign("http://x.test/a.jpg", now=1_000), now=1_001) is None  # https only
    assert thumbs.thumb_path("") == ""
    assert thumbs.thumb_path("https://x.test/a.jpg").startswith("/public/stock-thumbs/")  # under the Cappe API


def test_a_thumbnail_is_re_encoded_small():
    buf = io.BytesIO()
    Image.new("RGB", (1600, 900), "teal").save(buf, "JPEG")
    out = thumbs.to_webp(buf.getvalue())
    with Image.open(io.BytesIO(out)) as img:
        assert img.format == "WEBP" and max(img.size) == thumbs.THUMB_SIDE
    with pytest.raises(Exception):
        thumbs.to_webp(b"not an image")


def test_archive_pictures_are_asked_for_like_a_browser_asks():
    """Openverse's thumbnail endpoint answers a bare `image/*` with 406, which
    left every search result blank (2026-10-21)."""
    import inspect

    from app.cappe.routes.public import stock as stock_route
    from app.cappe.services.magazine import imports
    from app.cappe.services.magazine.sources.base import IMAGE_ACCEPT

    assert IMAGE_ACCEPT != "image/*" and "*/*" in IMAGE_ACCEPT
    for module in (stock_route, imports):
        assert 'accept="image/*"' not in inspect.getsource(module) and "accept=IMAGE_ACCEPT" in inspect.getsource(module)
