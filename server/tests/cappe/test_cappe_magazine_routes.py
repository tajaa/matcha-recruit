"""The magazine over HTTP (routes/render.py, routes/blog.py, routes/magazine.py,
routes/public/blog.py; migration cappemag02).

What each block pins:

  * magazine pages render only on a tenant host with a live magazine (turned
    on AND a plan that includes one); hidden stories are 404s;
  * a writer's magazine-only site serves its front at `/`, `/magazine`
    redirects there, and the sitemap lists the front, stories and topics;
  * the story API: a story is saved with its derived body, reading time and
    cover URL; pictures from another site are refused; the iOS app's plain
    posts keep working and an app edit of a story's body is a 409; every
    write drops the render cache; a story can't be paid while the magazine
    takes no subscribers;
  * the magazine settings: topics from the list, the cover story must be
    the site's, the view says whether the plan includes a magazine;
  * the public JSON never returns a hidden story or a paid story's words;
  * a picture a story uses can't be deleted from the library.

Run from server/:  ./venv/bin/python -m pytest tests/cappe/test_cappe_magazine_routes.py -q
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
from starlette.requests import Request  # noqa: E402

from app.cappe.routes import blog as blog_mod  # noqa: E402
from app.cappe.routes import magazine as magazine_mod  # noqa: E402
from app.cappe.routes import render as render_mod  # noqa: E402
from app.cappe.routes import uploads as uploads_mod  # noqa: E402
from app.cappe.routes.public import blog as public_blog  # noqa: E402
from app.cappe.services.magazine import magazines as mags  # noqa: E402
from tests._helpers.routes import QueryConn, route_client  # noqa: E402

SITE, ACCOUNT_ID = uuid4(), uuid4()
ASSET, OTHER_ASSET, POST = uuid4(), uuid4(), uuid4()
NOW = datetime(2026, 10, 20, 9, tzinfo=timezone.utc)
ACCOUNT = SimpleNamespace(id=ACCOUNT_ID, plan="business", account_type="business")
SITE_ROW = {"id": SITE, "name": "Bloom", "slug": "bloom", "subdomain": "bloom", "custom_domain": None,
            "theme_config": "{}", "meta_config": "{}", "timezone": "UTC", "account_id": ACCOUNT_ID, "status": "published"}
MAG_ROW = {"site_id": SITE, "enabled": True, "name": "Salt & Light", "tagline": "Harbour stories", "about": None,
           "masthead_style": "classic", "accent": None, "topics": ["city"], "front_at_root": False,
           "nav_label": "Magazine", "cover_post_id": None, "follow_enabled": True, "created_at": NOW, "updated_at": NOW}
ASSET_ROW = {"id": ASSET, "kind": "upload", "url": "https://cdn.example.test/a.jpg", "alt": "Boats", "caption": None,
             "credit_line": "Photo: Ana Ruiz", "license": "own", "ai_generated": False, "source_url": None,
             "width": 1600, "height": 1000, "variants": "{}", "created_at": NOW}
SENTINEL = "ZXQ-subscribers-only-ZXQ"


def story_row(**over):
    base = {"id": POST, "site_id": SITE, "title": "The harbour at dawn", "slug": "harbour-at-dawn", "excerpt": "Forty boats.",
            "body": "The boats.", "cover_image_url": "https://cdn.example.test/a.jpg", "status": "published",
            "published_at": NOW, "created_at": NOW, "updated_at": NOW, "format": "blocks",
            "content": json.dumps({"blocks": [{"type": "cover", "asset_id": str(ASSET), "style": "stacked", "tone": "light",
                                              "focal": {"x": 50, "y": 50}},
                                             {"type": "text", "md": "The **boats**.", "dropcap": True, "columns": 1}]}),
            "kicker": "Dispatch", "topic": "city", "layout": "standard", "access": "free", "cover_asset_id": ASSET,
            "byline": "Ana Ruiz", "word_count": 2, "reading_minutes": 1, "hidden_at": None}
    return {**base, **over}


class Ctx:
    def __init__(self, conn):
        self.conn = conn

    async def __aenter__(self):
        return self.conn

    async def __aexit__(self, *exc):
        return False


class Conn(QueryConn):
    """QueryConn that also hands out transactions and answers with callables."""

    def transaction(self):
        return Ctx(self)

    def _dispatch(self, kind, sql, args):
        value = super()._dispatch(kind, sql, args)
        return value(sql, args) if callable(value) else value


def _request(path, host="bloom.gummfit.com", query=b""):
    return Request({"type": "http", "method": "GET", "path": path, "client": ("127.0.0.1", 1),
                    "query_string": query, "headers": [(b"host", host.encode())]})


# ── rendered pages ───────────────────────────────────────────────────────────

def _render_conn(*, magazine=MAG_ROW, plan="business", stories=None, story=None, pages=None, topics=None):
    stories = stories if stories is not None else [story_row()]
    return Conn(
        fetchrow={
            "FROM cappe_sites WHERE subdomain": SITE_ROW,
            "FROM cappe_magazines": magazine,
            "AND slug = $2 AND status = 'published' AND hidden_at IS NULL": story,
            "AND id = $2 AND status = 'published' AND hidden_at IS NULL": None,
            "SELECT title, slug, content FROM cappe_pages": {"title": "Home", "slug": "home", "content": "{}"},
        },
        fetchval={"SELECT plan FROM cappe_accounts": plan},
        fetch={
            "FROM cappe_posts WHERE site_id = $1 AND status = 'published' AND hidden_at IS NULL": stories,
            "SELECT DISTINCT topic": topics if topics is not None else [{"topic": "city"}],
            "FROM cappe_assets WHERE site_id = $1 AND id = ANY": [ASSET_ROW],
            "FROM cappe_pages": pages if pages is not None else [{"title": "Home", "slug": "home", "updated_at": NOW}],
            "FROM cappe_locations": [],
            "FROM cappe_site_policies": [],
            "SELECT slug, topic, updated_at FROM cappe_posts": [{"slug": "harbour-at-dawn", "topic": "city", "updated_at": NOW}],
            "FROM cappe_products": [],
        },
    )


def _wire(monkeypatch, conn):
    monkeypatch.setattr(render_mod, "get_connection", lambda: Ctx(conn))
    monkeypatch.setattr(render_mod, "get_redis_cache", lambda: None)
    monkeypatch.setattr(render_mod, "subdomain_from_host", lambda host: "bloom" if host and "gummfit" in host else None)
    monkeypatch.setattr(render_mod, "_custom_domain_candidates", lambda host: [])
    monkeypatch.setattr(render_mod, "site_public_origin", lambda site: "https://bloom.gummfit.com")
    monkeypatch.setattr(mags, "resolve_entitlements",
                        AsyncMock(side_effect=lambda plan, conn=None: SimpleNamespace(
                            has=lambda f: f == "magazine" and plan in ("business", "pro", "creator", "writer"))))
    return conn


def test_the_front_lists_the_stories_and_the_header_links_to_it(monkeypatch):
    _wire(monkeypatch, _render_conn())
    body = asyncio.run(render_mod.magazine_front(_request("/magazine"))).body.decode()
    assert "Salt &amp; Light" in body and 'href="/stories/harbour-at-dawn"' in body
    assert 'href="/magazine">Magazine</a>' in body  # the site's nav
    assert "Photo: Ana Ruiz" not in body  # cards carry no credit line; the story page does
    home = asyncio.run(render_mod.render_home(_request("/"))).body.decode()
    assert 'href="/magazine">Magazine</a>' in home and "mz-masthead" not in home


def test_a_story_page_renders_with_its_credit(monkeypatch):
    conn = _wire(monkeypatch, _render_conn(story=story_row()))
    response = asyncio.run(render_mod.story_page("harbour-at-dawn", _request("/stories/harbour-at-dawn")))
    assert response.status_code == 200
    body = response.body.decode()
    assert "The harbour at dawn" in body and "Photo: Ana Ruiz" in body and "<strong>boats</strong>" in body
    assert response.headers["content-security-policy"] == render_mod.TENANT_CSP
    assert conn.args_for("AND slug = $2 AND status = 'published' AND hidden_at IS NULL") == (SITE, "harbour-at-dawn")


@pytest.mark.parametrize("slug", ["Harbour", "a" * 161, "../x"])
def test_a_story_slug_that_isnt_an_address_is_a_404(monkeypatch, slug):
    _wire(monkeypatch, _render_conn())
    assert asyncio.run(render_mod.story_page(slug, _request(f"/stories/{slug}"))).status_code == 404


def test_a_hidden_or_missing_story_is_a_404(monkeypatch):
    _wire(monkeypatch, _render_conn(story=None))
    assert asyncio.run(render_mod.story_page("gone", _request("/stories/gone"))).status_code == 404


def test_no_magazine_or_no_plan_means_no_pages(monkeypatch):
    _wire(monkeypatch, _render_conn(magazine={**MAG_ROW, "enabled": False}))
    assert asyncio.run(render_mod.magazine_front(_request("/magazine"))).status_code == 404
    _wire(monkeypatch, _render_conn(plan="free"))
    assert asyncio.run(render_mod.story_page("harbour-at-dawn", _request("/stories/harbour-at-dawn"))).status_code == 404
    assert asyncio.run(render_mod.magazine_feed(_request("/feed.xml"))).status_code == 404
    _wire(monkeypatch, _render_conn(magazine=None))
    assert asyncio.run(render_mod.topic_page("city", _request("/topics/city"))).status_code == 404


def test_magazine_pages_exist_only_on_a_tenant_host(monkeypatch):
    _wire(monkeypatch, _render_conn())
    with pytest.raises(HTTPException) as exc:
        asyncio.run(render_mod.magazine_front(_request("/magazine", host="hey-matcha.com")))
    assert exc.value.status_code == 404


def test_a_topic_page_and_an_unknown_or_empty_topic(monkeypatch):
    _wire(monkeypatch, _render_conn())
    body = asyncio.run(render_mod.topic_page("city", _request("/topics/city"))).body.decode()
    assert '<a href="/topics/city" aria-current="page">City life</a>' in body
    assert asyncio.run(render_mod.topic_page("crypto", _request("/topics/crypto"))).status_code == 404
    _wire(monkeypatch, _render_conn(stories=[]))
    assert asyncio.run(render_mod.topic_page("city", _request("/topics/city"))).status_code == 404


def test_the_feed(monkeypatch):
    _wire(monkeypatch, _render_conn())
    response = asyncio.run(render_mod.magazine_feed(_request("/feed.xml")))
    assert response.media_type == "application/rss+xml"
    assert "<item>" in response.body.decode() and "Photo: Ana Ruiz" in response.body.decode()


def test_a_writers_site_serves_its_front_at_root_and_redirects_magazine(monkeypatch):
    _wire(monkeypatch, _render_conn(magazine={**MAG_ROW, "front_at_root": True}))
    home = asyncio.run(render_mod.render_home(_request("/")))
    assert home.status_code == 200 and "mz-masthead" in home.body.decode()
    assert 'href="/magazine"' not in home.body.decode()
    redirect = asyncio.run(render_mod.magazine_front(_request("/magazine")))
    assert redirect.status_code == 308 and redirect.headers["location"] == "/"
    page2 = asyncio.run(render_mod.render_home(_request("/", query=b"page=2")))
    assert page2.status_code == 200 and "Newer stories" in page2.body.decode()


def test_page_numbers_are_bounded(monkeypatch):
    assert render_mod._page_number(_request("/", query=b"page=abc")) == 1
    assert render_mod._page_number(_request("/", query=b"page=0")) == 1
    assert render_mod._page_number(_request("/", query=b"page=999")) == 1
    assert render_mod._page_number(_request("/", query=b"page=3")) == 3


def test_the_sitemap_lists_the_magazine(monkeypatch):
    _wire(monkeypatch, _render_conn())
    xml = asyncio.run(render_mod.tenant_seo(_request("/sitemap.xml"), "sitemap")).body.decode()
    locs = re.findall(r"<loc>(.*?)</loc>", xml)
    assert locs == ["https://bloom.gummfit.com/magazine", "https://bloom.gummfit.com/",
                    "https://bloom.gummfit.com/stories/harbour-at-dawn", "https://bloom.gummfit.com/topics/city"]
    _wire(monkeypatch, _render_conn(magazine={**MAG_ROW, "front_at_root": True}))
    xml = asyncio.run(render_mod.tenant_seo(_request("/sitemap.xml"), "sitemap")).body.decode()
    locs = re.findall(r"<loc>(.*?)</loc>", xml)
    assert locs[:2] == ["https://bloom.gummfit.com/", "https://bloom.gummfit.com/p/home"]


def test_the_cache_is_written_and_read(monkeypatch):
    store: dict = {}

    async def cache_get(_redis, key):
        return store.get(key)

    async def cache_set(_redis, key, value, ttl):
        store[key] = value

    conn = _wire(monkeypatch, _render_conn())
    monkeypatch.setattr(render_mod, "get_redis_cache", lambda: object())
    monkeypatch.setattr(render_mod, "cache_get", cache_get)
    monkeypatch.setattr(render_mod, "cache_set", cache_set)
    asyncio.run(render_mod.magazine_front(_request("/magazine")))
    assert f"cappe:render:{SITE}:__mag__:front:0:1" in store
    reads = len(conn.calls)
    asyncio.run(render_mod.magazine_front(_request("/magazine")))
    assert len(conn.calls) == reads + 1  # the site lookup only


# ── the story API ────────────────────────────────────────────────────────────

def _owner_conn(**tables):
    fetchrow = {"FROM cappe_sites": SITE_ROW, "FROM cappe_magazines": MAG_ROW,
                "stripe_charges_enabled FROM cappe_accounts": {"stripe_account_id": None, "stripe_charges_enabled": False}}
    fetchrow.update(tables.pop("fetchrow", {}))
    fetch = {"FROM cappe_assets WHERE site_id = $1 AND id = ANY": [ASSET_ROW], "FROM cappe_pages": []}
    fetch.update(tables.pop("fetch", {}))
    fetchval = {"SELECT 1 FROM cappe_posts WHERE id": None, "SELECT 1 FROM cappe_posts WHERE site_id": None,
                "SELECT plan FROM cappe_accounts": "business", "SELECT paid_enabled FROM cappe_magazines": False,
                "FROM cappe_marketplace_settings": None}
    fetchval.update(tables.pop("fetchval", {}))
    return Conn(fetchrow=fetchrow, fetch=fetch, fetchval=fetchval, **tables)


@pytest.fixture
def invalidated(monkeypatch):
    calls = []

    async def fake(site_id):
        calls.append(site_id)

    monkeypatch.setattr(blog_mod, "invalidate_render_cache", fake)
    monkeypatch.setattr(magazine_mod, "invalidate_render_cache", fake)
    return calls


def _blog_client(monkeypatch, conn):
    monkeypatch.setattr(blog_mod, "get_connection", lambda: Ctx(conn))
    return route_client(blog_mod.router, overrides={blog_mod.require_cappe_account: ACCOUNT})


def _returning(conn):
    """The INSERT/UPDATE RETURNING row: the real values that were bound."""
    def answer(sql, args):
        row = story_row()
        if sql.lstrip().startswith("INSERT"):
            keys = ("site_id", "title", "slug", "excerpt", "body", "cover_image_url", "status", "format", "content",
                    "kicker", "topic", "layout", "cover_asset_id", "byline", "word_count", "reading_minutes")
            row.update(dict(zip(keys, args)))
        return row
    return answer


def test_a_story_is_saved_with_what_its_blocks_decide(monkeypatch, invalidated):
    conn = _owner_conn(fetchrow={"INSERT INTO cappe_posts": _returning(None)})
    content = {"blocks": [
        {"type": "cover", "asset_id": str(ASSET), "style": "overlay", "junk": 1},
        {"type": "text", "md": "Word " * 460, "dropcap": True},
    ]}
    with _blog_client(monkeypatch, conn) as client:
        res = client.post(f"/sites/{SITE}/posts", json={"title": "Dawn", "content": content, "topic": "City",
                                                        "layout": "photo_essay", "status": "published"})
    assert res.status_code == 201, res.text
    body = res.json()
    assert body["format"] == "blocks" and body["word_count"] == 460 and body["reading_minutes"] == 2
    assert body["cover_image_url"] == "https://cdn.example.test/a.jpg" and body["topic"] == "city"
    assert body["content"]["blocks"][0] == {"type": "cover", "asset_id": str(ASSET), "style": "overlay", "tone": "light",
                                            "focal": {"x": 50, "y": 50}}
    assert body["body"].startswith("Word Word")
    assert conn.args_for("INSERT INTO cappe_post_assets")[1] == [str(ASSET)]
    assert invalidated == [SITE]


def test_a_picture_from_another_site_is_refused(monkeypatch, invalidated):
    conn = _owner_conn(fetch={"FROM cappe_assets WHERE site_id = $1 AND id = ANY": []})
    with _blog_client(monkeypatch, conn) as client:
        res = client.post(f"/sites/{SITE}/posts", json={"title": "Dawn", "content": {"blocks": [
            {"type": "photo", "asset_id": str(OTHER_ASSET)}]}})
    assert res.status_code == 422 and "library" in res.json()["detail"]
    assert not conn.sql_for("execute") and invalidated == []


def test_bad_blocks_a_bad_topic_and_paid_access_are_refused(monkeypatch, invalidated):
    with _blog_client(monkeypatch, _owner_conn()) as client:
        assert client.post(f"/sites/{SITE}/posts", json={"title": "x", "content": {"blocks": [{"type": "video"}]}}).status_code == 422
        assert client.post(f"/sites/{SITE}/posts", json={"title": "x", "topic": "crypto"}).status_code == 422
        assert client.post(f"/sites/{SITE}/posts", json={"title": "x", "access": "paid"}).status_code == 422
        assert client.post(f"/sites/{SITE}/posts", json={"title": "x", "cover_asset_id": str(ASSET)}).status_code == 422


def test_the_ios_app_still_creates_a_plain_post(monkeypatch, invalidated):
    conn = _owner_conn(fetchrow={"INSERT INTO cappe_posts": _returning(None)})
    with _blog_client(monkeypatch, conn) as client:
        res = client.post(f"/sites/{SITE}/posts", json={"title": "Hello", "slug": "hello", "excerpt": None,
                                                        "body": "Plain *words* here.", "cover_image_url": None,
                                                        "status": "draft"})
    assert res.status_code == 201, res.text
    body = res.json()
    assert body["format"] == "markdown" and body["body"] == "Plain *words* here." and body["word_count"] == 3
    for key in ("id", "site_id", "title", "slug", "status"):
        assert body[key] is not None
    assert not any("cappe_post_assets" in sql for sql in conn.sql_for("execute"))


def test_an_app_edit_of_a_storys_body_is_a_409_but_an_echo_is_fine(monkeypatch, invalidated):
    conn = _owner_conn(fetchrow={"FOR UPDATE": story_row(), "UPDATE cappe_posts": story_row(title="New")})
    with _blog_client(monkeypatch, conn) as client:
        res = client.put(f"/sites/{SITE}/posts/{POST}", json={"title": "New", "body": "Rewritten in the app"})
        assert res.status_code == 409 and res.json()["detail"] == blog_mod.EDIT_ON_WEB
        res = client.put(f"/sites/{SITE}/posts/{POST}", json={"title": "New", "body": "The boats.", "status": "published"})
    assert res.status_code == 200, res.text
    sql = conn.sql_for("fetchrow")[-1]
    assert "title = $1" in sql and "published_at = COALESCE(published_at, NOW())" in sql and "body =" not in sql
    assert invalidated == [SITE]


def test_editing_a_storys_blocks_rederives_everything(monkeypatch, invalidated):
    conn = _owner_conn(fetchrow={"FOR UPDATE": story_row(), "UPDATE cappe_posts": story_row()})
    with _blog_client(monkeypatch, conn) as client:
        res = client.put(f"/sites/{SITE}/posts/{POST}", json={"content": {"blocks": [{"type": "text", "md": "New words."}]},
                                                               "cover_asset_id": None})
    assert res.status_code == 200, res.text
    args = conn.args_for("UPDATE cappe_posts")
    sql = conn.sql_for("fetchrow")[-1]
    assert "content = $" in sql and "::jsonb" in sql and "body = $" in sql and "cover_image_url = $" in sql
    assert "New words." in args and None in args  # the derived body; no cover any more
    # No pictures left: the old links are removed and nothing is inserted.
    assert any("DELETE FROM cappe_post_assets" in sql for sql in conn.sql_for("execute"))
    assert not any("INSERT INTO cappe_post_assets" in sql for sql in conn.sql_for("execute"))


def test_a_plain_post_becomes_a_story_keeping_its_words(monkeypatch, invalidated):
    plain = story_row(format="markdown", content="{}", body="Old *words*.", cover_asset_id=None)
    conn = _owner_conn(fetchrow={"FOR UPDATE": plain, "UPDATE cappe_posts": story_row()})
    with _blog_client(monkeypatch, conn) as client:
        res = client.put(f"/sites/{SITE}/posts/{POST}", json={"format": "blocks"})
    assert res.status_code == 200, res.text
    content = json.loads(conn.args_for("UPDATE cappe_posts")[conn.sql_for("fetchrow")[-1].index("content") and 1])
    assert content["blocks"][0] == {"type": "text", "md": "Old *words*.", "dropcap": True, "columns": 1}
    with _blog_client(monkeypatch, _owner_conn(fetchrow={"FOR UPDATE": story_row()})) as client:
        assert client.put(f"/sites/{SITE}/posts/{POST}", json={"format": "markdown"}).status_code == 422


def test_the_ios_app_edits_a_plain_posts_body_and_a_taken_slug_is_a_409(monkeypatch, invalidated):
    plain = story_row(format="markdown", content="{}", body="Old.", cover_asset_id=None)
    conn = _owner_conn(fetchrow={"FOR UPDATE": plain, "UPDATE cappe_posts": plain})
    with _blog_client(monkeypatch, conn) as client:
        res = client.put(f"/sites/{SITE}/posts/{POST}", json={"title": "Hello", "slug": "hello", "excerpt": None,
                                                               "body": "New words here.", "cover_image_url": None,
                                                               "status": "published"})
    assert res.status_code == 200, res.text
    sql = conn.sql_for("fetchrow")[-1]
    assert "body = $" in sql and "word_count = $" in sql and "cover_image_url = $" in sql and "slug = $" in sql
    assert "New words here." in conn.args_for("UPDATE cappe_posts") and 3 in conn.args_for("UPDATE cappe_posts")

    def taken(sql, args):
        raise Exception('duplicate key value violates unique constraint "cappe_posts_site_id_slug_key"')

    conn = _owner_conn(fetchrow={"FOR UPDATE": plain, "UPDATE cappe_posts": taken})
    with _blog_client(monkeypatch, conn) as client:
        res = client.put(f"/sites/{SITE}/posts/{POST}", json={"slug": "taken"})
    assert res.status_code == 409 and "slug" in res.json()["detail"]
    conn = _owner_conn(fetchrow={"FOR UPDATE": plain})
    with _blog_client(monkeypatch, conn) as client:
        assert client.put(f"/sites/{SITE}/posts/{POST}", json={"cover_asset_id": str(ASSET)}).status_code == 422


def test_an_update_with_nothing_to_change_reads_the_post(monkeypatch, invalidated):
    conn = _owner_conn(fetchrow={"FOR UPDATE": story_row()})
    with _blog_client(monkeypatch, conn) as client:
        res = client.put(f"/sites/{SITE}/posts/{POST}", json={})
    assert res.status_code == 200 and res.json()["title"] == "The harbour at dawn"
    assert not any("UPDATE cappe_posts" in s for s in conn.sql_for("fetchrow"))


def test_a_missing_post_and_a_null_title(monkeypatch, invalidated):
    conn = _owner_conn(fetchrow={"FOR UPDATE": None, "WHERE id = $1 AND site_id = $2": None})
    with _blog_client(monkeypatch, conn) as client:
        assert client.put(f"/sites/{SITE}/posts/{POST}", json={"title": "x"}).status_code == 404
        assert client.put(f"/sites/{SITE}/posts/{POST}", json={"title": None}).status_code == 422
        assert client.get(f"/sites/{SITE}/posts/{POST}").status_code == 404


def test_deleting_drops_the_cache(monkeypatch, invalidated):
    conn = _owner_conn(execute={"DELETE FROM cappe_posts": "DELETE 1"})
    with _blog_client(monkeypatch, conn) as client:
        assert client.delete(f"/sites/{SITE}/posts/{POST}").status_code == 204
    assert invalidated == [SITE]
    with _blog_client(monkeypatch, _owner_conn(execute={"DELETE FROM cappe_posts": "DELETE 0"})) as client:
        assert client.delete(f"/sites/{SITE}/posts/{POST}").status_code == 404


def test_the_list_marks_hidden_stories(monkeypatch):
    conn = _owner_conn(fetch={"FROM cappe_posts WHERE site_id = $1 ORDER BY": [story_row(hidden_at=NOW), story_row(id=uuid4())]})
    with _blog_client(monkeypatch, conn) as client:
        res = client.get(f"/sites/{SITE}/posts")
    assert [p["hidden"] for p in res.json()] == [True, False]
    assert "hidden_at" not in res.json()[0]


def test_the_editors_options_and_preview(monkeypatch):
    conn = _owner_conn()
    with _blog_client(monkeypatch, conn) as client:
        options = client.get(f"/sites/{SITE}/stories/options").json()
        assert [l["key"] for l in options["layouts"]][:2] == ["standard", "cover_story"]
        assert options["layouts"][0]["content"]["blocks"][0]["type"] == "cover"
        assert {"key": "city", "label": "City life"} in options["topics"]
        res = client.post(f"/sites/{SITE}/stories/preview", json={
            "title": "Dawn", "kicker": "Dispatch", "content": {"blocks": [
                {"type": "cover", "asset_id": str(ASSET)}, {"type": "text", "md": "Hello **there**."}]}})
        assert res.status_code == 200 and res.headers["cache-control"] == "no-store"
        body = res.text
        assert "Hello <strong>there</strong>." in body and "Photo: Ana Ruiz" in body and "Salt &amp; Light" in body
        assert client.post(f"/sites/{SITE}/stories/preview", json={"content": {"blocks": [{"type": "nope"}]}}).status_code == 422


def test_a_preview_without_a_magazine_uses_the_sites_name(monkeypatch):
    conn = _owner_conn(fetchrow={"FROM cappe_magazines": None})
    with _blog_client(monkeypatch, conn) as client:
        res = client.post(f"/sites/{SITE}/stories/preview", json={"title": "Dawn", "content": {"blocks": []}})
    assert res.status_code == 200 and "Bloom" in res.text


# ── magazine settings ────────────────────────────────────────────────────────

def _mag_client(monkeypatch, conn):
    monkeypatch.setattr(magazine_mod, "get_connection", lambda: Ctx(conn))
    monkeypatch.setattr(magazine_mod, "resolve_entitlements",
                        AsyncMock(side_effect=lambda plan, conn=None: SimpleNamespace(has=lambda f: plan == "business")))
    return route_client(magazine_mod.router, overrides={magazine_mod.require_cappe_account: ACCOUNT})


def test_a_site_without_a_magazine_gets_defaults(monkeypatch):
    with _mag_client(monkeypatch, _owner_conn(fetchrow={"FROM cappe_magazines": None})) as client:
        res = client.get(f"/sites/{SITE}/magazine")
    assert res.status_code == 200
    assert res.json()["name"] == "Bloom" and res.json()["enabled"] is False and res.json()["live"] is False
    assert res.json()["plan_includes_magazine"] is True


def test_saving_the_magazine(monkeypatch, invalidated):
    conn = _owner_conn(fetchrow={"INSERT INTO cappe_magazines": {**MAG_ROW, "topics": ["food", "city"], "enabled": True}})
    with _mag_client(monkeypatch, conn) as client:
        res = client.put(f"/sites/{SITE}/magazine", json={"enabled": True, "topics": ["Food", "city", "food"],
                                                           "tagline": "  ", "masthead_style": "display"})
    assert res.status_code == 200, res.text
    assert res.json()["live"] is True
    sql = next(q for q in conn.sql_for("fetchrow") if "INSERT INTO cappe_magazines" in q)
    assert "ON CONFLICT (site_id) DO UPDATE SET enabled = EXCLUDED.enabled" in sql and "name" in sql
    args = conn.args_for("INSERT INTO cappe_magazines")
    assert ["food", "city"] in args and None in args and "Bloom" in args  # tagline cleared; default name on first save
    assert invalidated == [SITE]


def test_bad_topics_an_empty_name_and_a_foreign_cover_story(monkeypatch, invalidated):
    with _mag_client(monkeypatch, _owner_conn()) as client:
        assert client.put(f"/sites/{SITE}/magazine", json={"topics": ["crypto"]}).status_code == 422
        assert client.put(f"/sites/{SITE}/magazine", json={"name": None}).status_code == 422
        assert client.put(f"/sites/{SITE}/magazine", json={"accent": "red"}).status_code == 422
        assert client.put(f"/sites/{SITE}/magazine", json={"cover_post_id": str(POST)}).status_code == 422
    assert invalidated == []


def test_the_plan_decides_live(monkeypatch):
    conn = _owner_conn()
    monkeypatch.setattr(magazine_mod, "get_connection", lambda: Ctx(conn))
    monkeypatch.setattr(magazine_mod, "resolve_entitlements",
                        AsyncMock(return_value=SimpleNamespace(has=lambda f: False)))
    with route_client(magazine_mod.router, overrides={magazine_mod.require_cappe_account: ACCOUNT}) as client:
        res = client.get(f"/sites/{SITE}/magazine")
    assert res.json()["enabled"] is True and res.json()["live"] is False and res.json()["plan_includes_magazine"] is False


# ── the public JSON ──────────────────────────────────────────────────────────

def test_the_public_json_hides_paid_words_and_hidden_stories(monkeypatch):
    paid = story_row(id=uuid4(), slug="paid", access="paid", body=SENTINEL,
                     content=json.dumps({"blocks": [{"type": "text", "md": SENTINEL}]}))
    conn = Conn(fetchrow={"FROM cappe_sites": SITE_ROW, "AND slug = $2 AND status = 'published' AND hidden_at IS NULL": paid},
                fetch={"FROM cappe_posts": [story_row(), paid]})
    monkeypatch.setattr(public_blog, "get_connection", lambda: Ctx(conn))
    monkeypatch.setattr(public_blog, "_published_site", AsyncMock(return_value=SITE_ROW))
    monkeypatch.setattr(public_blog, "_read_rate_limit", AsyncMock())
    with route_client(public_blog.router) as client:
        posts = client.get("/public/sites/bloom/posts").json()
        one = client.get("/public/sites/bloom/posts/paid")
    assert SENTINEL not in json.dumps(posts) and SENTINEL not in one.text
    assert posts[0]["body"] == "The boats." and posts[0]["content"]["blocks"][1]["md"] == "The **boats**."
    assert posts[1]["body"] is None and posts[1]["content"] is None
    assert "hidden_at IS NULL" in conn.sql_for("fetch")[0] and "hidden_at IS NULL" in conn.sql_for("fetchrow")[-1]


# ── the library ──────────────────────────────────────────────────────────────

def test_a_picture_a_story_uses_cant_be_deleted(monkeypatch):
    conn = Conn(fetchrow={"FROM cappe_sites": SITE_ROW},
                fetch={"JOIN cappe_posts p ON p.id = pa.post_id": [{"title": "The harbour at dawn"}]},
                execute={"DELETE FROM cappe_assets": "DELETE 1"})
    monkeypatch.setattr(uploads_mod, "get_connection", lambda: Ctx(conn))
    with route_client(uploads_mod.router, overrides={uploads_mod.require_cappe_account: ACCOUNT}) as client:
        res = client.delete(f"/sites/{SITE}/assets/{ASSET}")
    assert res.status_code == 409 and "The harbour at dawn" in res.json()["detail"]
    assert conn.sql_for("execute") == []
