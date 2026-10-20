"""Product pages — physical sellers round, PR 2 (zzzzcappe51).

What each block pins:

  * a product's address is made from its name once, folds accents, never
    collides, and an owner's own choice that is taken is refused;
  * a barcode must carry a valid check digit, and a picture is an https link
    or one of our own paths;
  * the pictures are an ordered list whose first is the cover the one-column
    readers (both apps, receipts) still see;
  * /shop/<slug> is a server-rendered page with its own title, canonical,
    Open Graph and Product data, and only for what the store's plan sells;
  * a store's /robots.txt and /sitemap.xml are its own, not Matcha's;
  * every product write drops the store's cached pages.

Run from server/:  ./venv/bin/python -m pytest tests/cappe/test_cappe_product_pages.py -q
"""
import asyncio
import json
import os
import re
from datetime import datetime, timezone
from types import SimpleNamespace
from unittest.mock import AsyncMock
from uuid import uuid4

os.environ.setdefault("LIVE_API", "test-key")
os.environ.setdefault("DATABASE_URL", "postgresql://test:test@localhost/test")
os.environ.setdefault("JWT_SECRET_KEY", "test-secret-key-cappe")

import pytest  # noqa: E402
from fastapi import HTTPException  # noqa: E402
from pydantic import ValidationError  # noqa: E402
from starlette.requests import Request  # noqa: E402

from app.cappe.models.shop import CappeProductCreate, CappeProductImageInput, CappeProductUpdate  # noqa: E402
from app.cappe.routes import render as render_mod  # noqa: E402
from app.cappe.routes import shop as shop_mod  # noqa: E402
from app.cappe.services import product_pages as pp  # noqa: E402
from app.cappe.services.render.page import render_site_html  # noqa: E402
from app.cappe.services.render.product_page import render_catalog_page, render_product_page  # noqa: E402
from app.core.routes.content import sitemap as core_sitemap  # noqa: E402

SITE, PRODUCT = uuid4(), uuid4()
NOW = datetime(2026, 10, 20, 12, tzinfo=timezone.utc)
ALL = frozenset({"physical", "digital", "service", "booking"})


class Ctx:
    def __init__(self, conn):
        self.conn = conn

    async def __aenter__(self):
        return self.conn

    async def __aexit__(self, *exc):
        return False


class SqlConn:
    """Answers by the first matching SQL fragment; records every call."""

    def __init__(self, answers=()):
        self.answers, self.calls = list(answers), []

    def _answer(self, sql, args):
        self.calls.append((sql, args))
        for needle, value in self.answers:
            if needle in sql:
                return value(sql, args) if callable(value) else value
        return None

    async def fetchrow(self, sql, *args):
        return self._answer(sql, args)

    async def fetchval(self, sql, *args):
        return self._answer(sql, args)

    async def fetch(self, sql, *args):
        return self._answer(sql, args) or []

    async def execute(self, sql, *args):
        self._answer(sql, args)

    async def executemany(self, sql, rows):
        for args in rows:
            self._answer(sql, tuple(args))

    def transaction(self):
        return Ctx(self)

    def sql(self, needle):
        return [c for c in self.calls if needle in c[0]]


# ── the address ──────────────────────────────────────────────────────────────

@pytest.mark.parametrize("name,slug", [
    ("Café Crème — 250 g", "cafe-creme-250-g"), ("  Mug!!  ", "mug"), ("💥", "product"), ("a" * 100, "a" * 72),
])
def test_a_name_becomes_an_address(name, slug):
    assert pp.product_slug(name) == slug and pp.SLUG_RE.match(slug)


def test_a_new_product_takes_the_first_free_address():
    conn = SqlConn([("SELECT slug FROM cappe_products", [{"slug": "mug"}, {"slug": "mug-2"}, {"slug": "mug-4"}])])
    assert asyncio.run(pp.assign_slug(conn, SITE, PRODUCT, "Mug")) == "mug-3"
    (sql, args), = conn.sql("UPDATE cappe_products SET slug")
    assert args == ("mug-3", PRODUCT, SITE)
    # Its own row never counts as taken.
    assert "id <> $2" in conn.sql("SELECT slug FROM cappe_products")[0][0]


def test_an_address_the_owner_chose_is_theirs_or_refused():
    conn = SqlConn([("SELECT slug FROM cappe_products", [{"slug": "summer-tee"}])])
    with pytest.raises(HTTPException) as exc:
        asyncio.run(pp.assign_slug(conn, SITE, PRODUCT, "Tee", "summer-tee"))
    assert exc.value.status_code == 409 and conn.sql("UPDATE") == []
    conn = SqlConn([("SELECT slug FROM cappe_products", [])])
    assert asyncio.run(pp.assign_slug(conn, SITE, PRODUCT, "Tee", "summer-tee")) == "summer-tee"


def test_an_address_taken_in_a_race_is_a_409_or_a_fresh_suffix():
    from asyncpg.exceptions import UniqueViolationError

    class Racing(SqlConn):
        async def execute(self, sql, *args):
            await super().execute(sql, *args)
            if "SET slug" in sql and len(self.sql("SET slug")) == 1:
                raise UniqueViolationError("uq_cappe_products_site_slug")

    with pytest.raises(HTTPException) as exc:
        asyncio.run(pp.assign_slug(Racing(), SITE, PRODUCT, "Tee", "summer-tee"))
    assert exc.value.status_code == 409
    conn = Racing()
    slug = asyncio.run(pp.assign_slug(conn, SITE, PRODUCT, "Mug"))
    assert re.fullmatch(r"mug-[0-9a-f]{6}", slug) and conn.sql("SET slug")[-1][1][0] == slug


# ── what an owner may type ───────────────────────────────────────────────────

@pytest.mark.parametrize("gtin,ok", [
    ("4006381333931", True), ("036000291452", True), ("96385074", True), ("00012345600012", True),
    ("4006381333932", False), ("12345", False), ("40063813339311", False),
])
def test_a_barcode_needs_its_check_digit(gtin, ok):
    assert pp.gtin_valid(gtin) is ok


def test_the_editor_input_is_cleaned_or_refused():
    body = CappeProductCreate(name="Tee", slug=" Summer-Tee ", gtin="4006 3813 3393 1", brand="Acme")
    assert (body.slug, body.gtin) == ("summer-tee", "4006381333931")
    assert CappeProductUpdate(gtin="  ").gtin is None
    for bad in ({"slug": "summer--tee"}, {"slug": "Summer Tee!"}, {"gtin": "4006381333932"}):
        with pytest.raises(ValidationError):
            CappeProductCreate(name="Tee", **bad)


@pytest.mark.parametrize("url,ok", [
    ("https://cdn.example.com/a.jpg", True), ("/uploads/a.png", True),
    ("http://cdn.example.com/a.jpg", False), ("//evil.example.com/a.jpg", False),
    ("javascript:alert(1)", False), ('https://cdn.example.com/a.jpg"onerror="x', False),
])
def test_a_picture_is_https_or_our_own_path(url, ok):
    if ok:
        assert CappeProductImageInput(url=url).url == url
    else:
        with pytest.raises(ValidationError):
            CappeProductImageInput(url=url)


# ── pictures ─────────────────────────────────────────────────────────────────

def _img(url, alt=None):
    return CappeProductImageInput(url=url, alt=alt)


def test_the_pictures_are_replaced_in_order_and_the_first_is_the_cover():
    conn = SqlConn()
    asyncio.run(pp.replace_images(conn, SITE, PRODUCT, [_img("https://c.example.com/1.jpg"), _img("/uploads/2.png", "Back")]))
    inserts = conn.sql("INSERT INTO cappe_product_images")
    assert [(a[2], a[3], a[4]) for _s, a in inserts] == [("https://c.example.com/1.jpg", None, 0), ("/uploads/2.png", "Back", 1)]
    (_s, cover), = conn.sql("UPDATE cappe_products SET image_url")
    assert cover[0] == "https://c.example.com/1.jpg"
    conn = SqlConn()
    asyncio.run(pp.replace_images(conn, SITE, PRODUCT, []))
    assert conn.sql("UPDATE cappe_products SET image_url")[0][1][0] is None
    asyncio.run(pp.replace_images(conn, SITE, PRODUCT, None))         # None: nothing touched
    assert len(conn.calls) == 2


def test_more_than_twenty_pictures_is_refused():
    with pytest.raises(HTTPException) as exc:
        asyncio.run(pp.replace_images(SqlConn(), SITE, PRODUCT, [_img(f"/u/{i}.png") for i in range(21)]))
    assert exc.value.status_code == 422


def test_an_app_that_only_knows_the_cover_still_keeps_the_list_true():
    first = {"id": uuid4()}
    conn = SqlConn([("FROM cappe_product_images", first)])
    asyncio.run(pp.set_cover(conn, SITE, PRODUCT, "https://c.example.com/new.jpg"))
    assert conn.sql("UPDATE cappe_product_images SET url")[0][1] == ("https://c.example.com/new.jpg", first["id"])
    asyncio.run(pp.set_cover(conn, SITE, PRODUCT, None))
    assert conn.sql("DELETE FROM cappe_product_images")[0][1] == (first["id"],)
    # The next picture becomes the cover, and the column says so.
    assert "SELECT url FROM cappe_product_images" in conn.sql("UPDATE cappe_products SET image_url")[0][0]
    conn = SqlConn()
    asyncio.run(pp.set_cover(conn, SITE, PRODUCT, "/uploads/a.png"))
    assert conn.sql("INSERT INTO cappe_product_images")[0][1][2] == "/uploads/a.png"


# ── the page ─────────────────────────────────────────────────────────────────

SITE_DICT = {"name": "Bloom", "slug": "bloom", "theme_config": {}, "meta_config": {"seo": {"title": "Bloom flowers"}}}


def _product(**kw):
    return {"id": PRODUCT, "name": "Peony bunch", "description": "Ten stems.", "price_cents": 4500, "currency": "USD",
            "image_url": "https://c.example.com/1.jpg", "sku": "PEO-10", "inventory": 3, "status": "active",
            "fulfillment": "physical", "category": "Flowers", "slug": "peony-bunch", "brand": "Bloom",
            "gtin": "4006381333931", **kw}


def _page(**kw):
    images = kw.pop("images", [{"url": "https://c.example.com/1.jpg", "alt": "Front"}, {"url": "/uploads/2.png", "alt": None}])
    variants = kw.pop("variants", [])
    return render_product_page(
        SITE_DICT, [{"slug": "home", "title": "Home"}], _product(**kw), images=images, variants=variants,
        price_cents=kw.get("price_cents", 4500), discount_percent=0, origin="https://bloom.gummfit.com",
        rating={"count": 2, "avg": 4.5}, back_href="/p/shop", back_label="Shop",
    )


def _ld(html):
    return json.loads(re.search(r'<script type="application/ld\+json">(\{"@context": "https://schema.org", "@type": "Product".*?)</script>', html).group(1))


def _media(html):
    """The server-rendered gallery (the inlined store script mentions the same classes)."""
    return re.search(r'data-media>(.*?)</div><div class="cz-pd__info"', html, re.S).group(1)


def test_the_page_is_the_products_own_for_search_and_link_previews():
    html = _page()
    assert "<title>Peony bunch — Bloom</title>" in html         # not the store's SEO title
    assert '<link rel="canonical" href="https://bloom.gummfit.com/shop/peony-bunch" />' in html
    assert '<meta property="og:type" content="product" />' in html
    assert '<meta property="og:image" content="https://c.example.com/1.jpg" />' in html
    assert '<meta property="product:price:amount" content="45.00" />' in html
    ld = _ld(html)
    assert ld["offers"] == {"@type": "Offer", "price": "45.00", "priceCurrency": "USD",
                            "availability": "https://schema.org/InStock", "url": "https://bloom.gummfit.com/shop/peony-bunch",
                            "itemCondition": "https://schema.org/NewCondition"}
    # Every picture, absolute; the identifiers feeds match on.
    assert ld["image"] == ["https://c.example.com/1.jpg", "https://bloom.gummfit.com/uploads/2.png"]
    assert (ld["sku"], ld["gtin"], ld["brand"]["name"]) == ("PEO-10", "4006381333931", "Bloom")
    assert ld["aggregateRating"] == {"@type": "AggregateRating", "ratingValue": 4.5, "reviewCount": 2}
    # The store widget fills the same panel in place; thumbnails only with two or more.
    assert 'data-product="peony-bunch"' in html and 'class="cz-pd__thumbs"' in _media(html)
    assert 'href="/p/shop">← Shop' in html


def test_variants_priced_differently_make_a_price_range_and_all_out_is_out_of_stock():
    variants = [{"status": "active", "price_cents": 5500, "inventory": 0},
                {"status": "active", "price_cents": None, "inventory": 0},
                {"status": "disabled", "price_cents": 9900, "inventory": 5}]
    html = _page(inventory=None, variants=variants, images=[])
    ld = _ld(html)
    assert ld["offers"]["@type"] == "AggregateOffer"
    assert (ld["offers"]["lowPrice"], ld["offers"]["highPrice"]) == ("45.00", "55.00")   # disabled ignored
    assert ld["offers"]["availability"] == "https://schema.org/OutOfStock"
    assert "Sold out" in html and "image" not in ld and "cz-pd__thumbs" not in _media(html)


def test_a_discount_prices_the_variants_too_and_a_price_nobody_pays_is_left_out():
    variants = [{"status": "active", "price_cents": 6000, "inventory": 3},
                {"status": "active", "price_cents": 8000, "inventory": 3}]
    product = _product()
    low, high = pp.price_range(product, variants, 2250, discount_percent=50)
    assert (low, high) == (3000, 4000)       # not the discounted base, which no combination sells at
    assert pp.price_range(product, [], 2250, discount_percent=50) == (2250, 2250)


def test_a_picture_link_the_validator_never_saw_is_not_rendered():
    html = _page(images=[{"url": "javascript:alert(1)", "alt": None}, {"url": "https://c.example.com/1.jpg", "alt": None}])
    assert "javascript:" not in _media(html) and _ld(html)["image"] == ["https://c.example.com/1.jpg"]


def test_home_is_the_page_slugged_home_wherever_it_sits():
    from app.cappe.services.render.page import home_slug
    assert home_slug([{"slug": "about"}, {"slug": "home"}]) == "home"
    assert home_slug([{"slug": "about"}, {"slug": "menu"}]) == "about"
    assert home_slug([]) == "home"


def test_everything_the_owner_typed_is_escaped():
    html = _page(name="</script><script>alert(1)</script>", description="<!--<script><img src=x onerror=alert(1)>")
    assert "<script>alert(1)" not in html and "<img src=x" not in html and "<!--<script>" not in html
    # Inside the structured data it is still the same text, as JSON escapes.
    assert _ld(html)["description"] == "<!--<script><img src=x onerror=alert(1)>"


def test_a_plain_page_has_no_canonical_of_its_own():
    html = render_site_html(SITE_DICT, {"title": "About", "slug": "about", "content": {}}, [])
    assert "<title>Bloom flowers</title>" in html and 'rel="canonical"' not in html
    assert '<meta property="og:type" content="website" />' in html


def test_the_catalog_links_every_product():
    html = render_catalog_page(SITE_DICT, [], [{"name": "Peony", "slug": "peony"}, {"name": "No slug", "slug": None}],
                               origin="https://bloom.gummfit.com")
    assert '<a href="/shop/peony">Peony</a>' in html and "No slug" not in html
    assert '<link rel="canonical" href="https://bloom.gummfit.com/shop" />' in html


# ── the routes ───────────────────────────────────────────────────────────────

def _request(path, host="bloom.gummfit.com"):
    return Request({"type": "http", "method": "GET", "path": path, "client": ("127.0.0.1", 1),
                    "headers": [(b"host", host.encode())]})


SITE_ROW = {"id": SITE, "name": "Bloom", "slug": "bloom", "subdomain": "bloom", "custom_domain": None,
            "theme_config": "{}", "meta_config": "{}", "timezone": "UTC", "account_id": uuid4()}


def _wire(monkeypatch, *, site=SITE_ROW, product=None, sells=ALL, pages=None):
    conn = SqlConn([
        ("FROM cappe_sites WHERE subdomain", site),
        ("SELECT plan FROM cappe_accounts", "business"),
        ("jsonb_path_exists", {"slug": "shop", "title": "Shop"}),
        ("FROM cappe_pages", pages if pages is not None else [{"slug": "home", "title": "Home", "updated_at": NOW}]),
        ("AND slug = $2 AND status = 'active'", product),
        ("FROM cappe_products WHERE site_id = $1 AND status = 'active' AND slug IS NOT NULL", [
            {"id": uuid4(), "name": "Peony", "slug": "peony", "fulfillment": "physical", "updated_at": NOW},
            {"id": uuid4(), "name": "Class", "slug": "class", "fulfillment": "booking", "updated_at": NOW},
        ]),
        ("FROM cappe_reviews", {"count": 0, "avg": None}),
        ("SELECT NOW()", NOW),
    ])
    monkeypatch.setattr(render_mod, "get_connection", lambda: Ctx(conn))
    monkeypatch.setattr(render_mod, "get_redis_cache", lambda: None)
    monkeypatch.setattr(render_mod, "subdomain_from_host", lambda host: "bloom" if host and "gummfit" in host else None)
    monkeypatch.setattr(render_mod, "_custom_domain_candidates", lambda host: [])
    monkeypatch.setattr(render_mod, "resolve_entitlements", AsyncMock(return_value=SimpleNamespace(allowed_fulfillment=sells)))
    monkeypatch.setattr(render_mod, "fetch_images", AsyncMock(return_value={}))
    monkeypatch.setattr(render_mod, "fetch_variants", AsyncMock(return_value={}))
    monkeypatch.setattr(render_mod, "fetch_active_discounts", AsyncMock(return_value=[]))
    monkeypatch.setattr(render_mod, "site_public_origin", lambda site: "https://bloom.gummfit.com")
    return conn


def test_a_product_page_renders_from_its_address(monkeypatch):
    conn = _wire(monkeypatch, product=_product())
    response = asyncio.run(render_mod.product_page("peony-bunch", _request("/shop/peony-bunch")))
    assert response.status_code == 200 and b"Peony bunch" in response.body
    assert response.headers["content-security-policy"] == render_mod.TENANT_CSP
    (sql, args), = conn.sql("AND slug = $2 AND status = 'active'")
    assert args == (SITE, "peony-bunch")


@pytest.mark.parametrize("slug,product,sells", [
    ("peony-bunch", None, ALL),                                          # no such (active) product
    ("Peony Bunch", _product(), ALL),                                    # not an address we make
    ("peony-bunch", _product(), frozenset({"digital", "service", "booking"})),   # the plan doesn't sell it
])
def test_what_isnt_for_sale_has_no_page(monkeypatch, slug, product, sells):
    _wire(monkeypatch, product=product, sells=sells)
    response = asyncio.run(render_mod.product_page(slug, _request(f"/shop/{slug}")))
    assert response.status_code == 404


def test_a_product_page_only_exists_on_a_store_host(monkeypatch):
    _wire(monkeypatch, product=_product())
    with pytest.raises(HTTPException) as exc:
        asyncio.run(render_mod.product_page("peony-bunch", _request("/shop/peony-bunch", host="hey-matcha.com")))
    assert exc.value.status_code == 404


def test_the_catalog_lists_only_what_the_plan_sells(monkeypatch):
    _wire(monkeypatch, sells=frozenset({"physical"}))
    body = asyncio.run(render_mod.catalog_page(_request("/shop"))).body.decode()
    assert 'href="/shop/peony"' in body and "/shop/class" not in body


def test_a_store_has_its_own_robots_and_sitemap(monkeypatch):
    _wire(monkeypatch, sells=frozenset({"physical"}),
          pages=[{"slug": "home", "title": "Home", "updated_at": NOW}, {"slug": "about", "title": "About", "updated_at": NOW}])
    robots = asyncio.run(render_mod.tenant_seo(_request("/robots.txt"), "robots")).body.decode()
    assert "Sitemap: https://bloom.gummfit.com/sitemap.xml" in robots and "Disallow: /order/" in robots
    xml = asyncio.run(render_mod.tenant_seo(_request("/sitemap.xml"), "sitemap")).body.decode()
    locs = re.findall(r"<loc>(.*?)</loc>", xml)
    assert locs == ["https://bloom.gummfit.com/", "https://bloom.gummfit.com/p/about",
                    "https://bloom.gummfit.com/shop", "https://bloom.gummfit.com/shop/peony"]
    assert "<lastmod>2026-10-20</lastmod>" in xml


def test_the_sitemap_lists_a_page_that_sits_before_home(monkeypatch):
    _wire(monkeypatch, sells=frozenset({"physical"}),
          pages=[{"slug": "about", "title": "About", "updated_at": NOW}, {"slug": "home", "title": "Home", "updated_at": NOW}])
    xml = asyncio.run(render_mod.tenant_seo(_request("/sitemap.xml"), "sitemap")).body.decode()
    locs = re.findall(r"<loc>(.*?)</loc>", xml)
    assert locs[:2] == ["https://bloom.gummfit.com/p/about", "https://bloom.gummfit.com/"]


def test_a_store_that_isnt_live_asks_not_to_be_indexed(monkeypatch):
    _wire(monkeypatch, site=None)
    robots = asyncio.run(render_mod.tenant_seo(_request("/robots.txt"), "robots")).body.decode()
    assert robots == "User-agent: *\nDisallow: /\n"
    assert asyncio.run(render_mod.tenant_seo(_request("/sitemap.xml"), "sitemap")).status_code == 404


def test_matchas_own_host_is_left_to_matcha(monkeypatch):
    _wire(monkeypatch)
    assert asyncio.run(render_mod.tenant_seo(_request("/robots.txt", host="hey-matcha.com"), "robots")) is None


def test_matchas_seo_routes_ask_the_store_first(monkeypatch):
    seen = []

    async def hook(request, kind):
        seen.append(kind)
        return "STORE" if request.headers["host"] == "bloom.gummfit.com" else None

    monkeypatch.setattr(core_sitemap, "_HOST_HOOKS", [hook])
    assert asyncio.run(core_sitemap.robots(_request("/robots.txt"))) == "STORE"
    assert asyncio.run(core_sitemap.sitemap(_request("/sitemap.xml"))) == "STORE"
    own = asyncio.run(core_sitemap.robots(_request("/robots.txt", host="hey-matcha.com")))
    assert "Disallow: /app/" in own and seen == ["robots", "sitemap", "robots"]


def test_main_registers_the_store_hook():
    import inspect
    import app.main as main
    src = inspect.getsource(main)
    assert "register_host_seo(cappe_tenant_seo)" in src


# ── owner writes ─────────────────────────────────────────────────────────────

ACCOUNT = SimpleNamespace(id=uuid4(), plan="business")


def _wire_owner(monkeypatch):
    row = {"id": PRODUCT, "name": "Tee", "slug": None}
    conn = SqlConn([("RETURNING", row), ("SELECT * FROM cappe_products", {**row, "fulfillment": "physical"}),
                    ("SELECT inventory FROM cappe_products", {"inventory": None}), ("SELECT subscription_intervals", row)])
    calls = SimpleNamespace(slug=[], images=[], cover=[], dropped=[])
    monkeypatch.setattr(shop_mod, "get_connection", lambda: Ctx(conn))
    monkeypatch.setattr(shop_mod, "get_owned_site", AsyncMock())
    monkeypatch.setattr(shop_mod, "resolve_entitlements", AsyncMock())
    monkeypatch.setattr(shop_mod, "require_fulfillment", lambda *_a: None)
    monkeypatch.setattr("app.cappe.services.recurring.validate_product_subscription", AsyncMock())
    monkeypatch.setattr(shop_mod, "_replace_option_groups", AsyncMock())
    monkeypatch.setattr(shop_mod, "replace_variants", AsyncMock())
    monkeypatch.setattr(shop_mod, "refresh_site_search", AsyncMock())
    monkeypatch.setattr(shop_mod, "_product_out", AsyncMock(side_effect=lambda _c, r: dict(r)))
    monkeypatch.setattr(shop_mod, "assign_slug", AsyncMock(side_effect=lambda _c, _s, _p, name, wanted=None: calls.slug.append((name, wanted))))
    monkeypatch.setattr(shop_mod, "replace_images", AsyncMock(side_effect=lambda _c, _s, _p, imgs: calls.images.append(imgs)))
    monkeypatch.setattr(shop_mod, "set_cover", AsyncMock(side_effect=lambda _c, _s, _p, url: calls.cover.append(url)))
    monkeypatch.setattr(shop_mod, "invalidate_site_render_cache", AsyncMock(side_effect=lambda site: calls.dropped.append(site)))
    return conn, calls


def test_a_new_product_gets_its_address_and_pictures(monkeypatch):
    _conn, calls = _wire_owner(monkeypatch)
    asyncio.run(shop_mod.create_product(SITE, CappeProductCreate(name="Tee", images=[{"url": "/u/1.png"}]), account=ACCOUNT))
    asyncio.run(shop_mod.create_product(SITE, CappeProductCreate(name="Mug", image_url="/u/m.png", slug="the-mug"), account=ACCOUNT))
    assert calls.slug == [("Tee", None), ("Mug", "the-mug")]
    assert [i[0].url for i in calls.images] == ["/u/1.png"] and calls.cover == ["/u/m.png"]
    assert calls.dropped == [SITE, SITE]


def test_an_edit_keeps_the_address_and_the_pictures_decide_the_cover(monkeypatch):
    conn, calls = _wire_owner(monkeypatch)
    asyncio.run(shop_mod.update_product(SITE, PRODUCT, CappeProductUpdate(
        name="Renamed", images=[{"url": "/u/2.png"}], image_url="/u/ignored.png"), account=ACCOUNT))
    # The pictures win: the cover column is not patched from `image_url` beside them.
    (sql, _args), = conn.sql("UPDATE cappe_products SET")
    assert "image_url" not in sql.split("RETURNING")[0] and calls.cover == [] and [i[0].url for i in calls.images] == ["/u/2.png"]
    # A product that never had an address gets one; renaming alone never changes it.
    assert calls.slug == [("Tee", None)]
    asyncio.run(shop_mod.update_product(SITE, PRODUCT, CappeProductUpdate(image_url="/u/app.png", slug="new-tee"),
                                        account=ACCOUNT))
    assert calls.cover == ["/u/app.png"] and calls.slug[-1] == ("Tee", "new-tee")
    assert calls.dropped == [SITE, SITE]


def test_a_product_with_an_address_keeps_it_through_a_rename(monkeypatch):
    conn, calls = _wire_owner(monkeypatch)
    conn.answers[0] = ("RETURNING", {"id": PRODUCT, "name": "Renamed", "slug": "tee"})
    asyncio.run(shop_mod.update_product(SITE, PRODUCT, CappeProductUpdate(name="Renamed"), account=ACCOUNT))
    assert calls.slug == []


def test_every_product_write_drops_the_cached_pages():
    import inspect
    for fn in (shop_mod.create_product, shop_mod.update_product, shop_mod.delete_product, shop_mod.adjust_stock):
        assert "invalidate_site_render_cache(site_id)" in inspect.getsource(fn), fn.__name__


# ── the storefront script ────────────────────────────────────────────────────

def test_cards_are_links_and_the_overlay_shows_the_products_address():
    js = open(os.path.join(os.path.dirname(render_mod.__file__), "..", "services", "render", "assets", "store.js")).read()
    assert "document.createElement(p.url?'a':'button');if(p.url)c.href=p.url" in js
    assert "e.metaKey||e.ctrlKey" in js and "e.preventDefault();openDetail(p)" in js
    assert "history.pushState({czpd:1},'',p.url||location.href)" in js
    # On a product's own page the panel is filled in place.
    assert "var single=box.getAttribute('data-product')" in js
    assert "openDetail(mine,box.querySelector('.cz-pd__panel'))" in js
