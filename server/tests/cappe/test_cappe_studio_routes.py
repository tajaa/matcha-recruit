"""Paged stories over HTTP (routes/studio.py, the paged branches of
routes/blog.py, routes/render.py, routes/public/blog.py, routes/public/
magazine.py, routes/public/fonts.py; migration cappemag09).

What each block pins:

  * a paged story is made with its first pages and its derived text; the
    story API changes only what isn't on its pages (its document is the
    Studio's; an app edit of its words is a 409; it can't change format);
  * the Studio: opening a story that isn't paged is a 409; a save from a
    stale revision is a 409 naming the current one; an unpublished story's
    save is the story; a published one's goes to its working copy (readers
    keep the live pages, nothing is invalidated) until it updates the live
    story (kept as a revision, cache dropped); the working copy can be thrown
    away, and an earlier version restored;
  * a paged story's page and Text view render on the tenant host, and other
    stories' `/text` redirects to them; the public JSON never returns the
    document; a subscriber's `/paid` carries its locked pages;
  * faces are served only from the manifest, checked against their sha, and
    cached for a year.

Run from server/:  ./venv/bin/python -m pytest tests/cappe/test_cappe_studio_routes.py -q
"""
import asyncio
import hashlib
import json
from datetime import datetime, timezone
from unittest.mock import AsyncMock
from uuid import uuid4

import pytest

from app.cappe.routes import render as render_mod
from app.cappe.routes import studio as studio_mod
from app.cappe.routes.public import blog as public_blog
from app.cappe.routes.public import fonts as fonts_mod
from app.cappe.services.magazine.studio import fonts as faces
from app.cappe.services.magazine.studio import schema as S
from tests._helpers.routes import route_client
from tests.cappe.test_cappe_magazine_paid import PAID_POST, SENTINEL as PAID_SENTINEL, _paid_client  # noqa: F401
from tests.cappe.test_cappe_magazine_routes import (
    ACCOUNT, ASSET, POST, SITE, SITE_ROW, Conn, Ctx, _blog_client, _owner_conn, _render_conn, _request, _returning,
    _wire, invalidated, story_row,  # noqa: F401
)

NOW = datetime(2026, 10, 22, 9, tzinfo=timezone.utc)
WORDS = "Low tide at the pier"


def _doc(text=WORDS, *, image=False):
    doc = S.starter_doc()
    doc["threads"][0]["paras"] = [{"runs": [{"t": text}]}]
    if image:
        doc["items"].insert(0, {"id": "i1", "kind": "image", "page": "p1", "x": 0, "y": 0, "w": 612, "h": 300,
                                "asset_id": str(ASSET)})
    return S.normalize_doc(doc)


def paged_row(**over):
    return story_row(**{"format": "pages", "content": json.dumps({"doc": _doc()}), "rev": 3, "draft": None,
                        "body": WORDS, **over})


# ── the story API ────────────────────────────────────────────────────────────

def test_a_paged_story_is_made_with_its_first_pages(monkeypatch, invalidated):
    conn = _owner_conn(fetchrow={"INSERT INTO cappe_posts": _returning(None)})
    with _blog_client(monkeypatch, conn) as client:
        res = client.post(f"/sites/{SITE}/posts", json={"title": "Dawn", "format": "pages"})
    assert res.status_code == 201, res.text
    args = conn.args_for("INSERT INTO cappe_posts")
    assert args[7] == "pages"
    doc = json.loads(args[8])["doc"]
    assert [p["id"] for p in doc["pages"]] == ["p1", "p2"] and doc["threads"][0]["frames"] == ["t1", "t2"]


def test_a_paged_story_can_be_made_from_a_document(monkeypatch, invalidated):
    conn = _owner_conn(fetchrow={"INSERT INTO cappe_posts": _returning(None)})
    with _blog_client(monkeypatch, conn) as client:
        res = client.post(f"/sites/{SITE}/posts", json={"title": "Dawn", "format": "pages",
                                                        "content": {"doc": _doc(image=True)}})
        bad = client.post(f"/sites/{SITE}/posts", json={"title": "Dawn", "format": "pages",
                                                        "content": {"doc": {"pages": []}}})
    assert res.status_code == 201, res.text
    args = conn.args_for("INSERT INTO cappe_posts")
    assert args[4] == WORDS  # its body is its Text view's words
    assert args[5] == "https://cdn.example.test/a.jpg" and args[12] == str(ASSET)  # the cover: page 1's picture
    assert conn.args_for("INSERT INTO cappe_post_assets")[1] == [str(ASSET)]
    assert bad.status_code == 422 and "at least one page" in bad.text


@pytest.mark.parametrize("change, code", [
    ({"content": {"doc": {}}}, 422),
    ({"format": "blocks"}, 422),
    ({"cover_asset_id": str(uuid4())}, 422),
    ({"cover_image_url": "https://cdn.example.test/other.jpg"}, 422),
    ({"body": "Rewritten"}, 409),
])
def test_the_story_api_leaves_a_paged_storys_pages_alone(monkeypatch, invalidated, change, code):
    conn = _owner_conn(fetchrow={"FOR UPDATE": paged_row()})
    with _blog_client(monkeypatch, conn) as client:
        res = client.put(f"/sites/{SITE}/posts/{POST}", json=change)
    assert res.status_code == code, res.text


def test_the_story_api_still_titles_and_publishes_a_paged_story(monkeypatch, invalidated):
    row = paged_row()
    conn = _owner_conn(fetchrow={"FOR UPDATE": row, "UPDATE cappe_posts SET": paged_row(title="New")})
    # The iOS app sends the cover it was given back with every save: no change.
    with _blog_client(monkeypatch, conn) as client:
        res = client.put(f"/sites/{SITE}/posts/{POST}", json={"title": "New", "status": "published", "body": WORDS,
                                                             "cover_image_url": row["cover_image_url"],
                                                             "cover_asset_id": str(row["cover_asset_id"])})
    assert res.status_code == 200, res.text
    sql = conn.sql_for("fetchrow")[-1]
    assert "title = $1" in sql and "content" not in sql.split("RETURNING")[0]


@pytest.mark.parametrize("over, change, taken, slug", [
    # A draft still at its placeholder takes its headline's address when it first goes out ...
    ({}, {"status": "published", "title": "Gem of the Bay"}, (), "gem-of-the-bay"),
    ({"title": "Gem of the Bay"}, {"status": "published"}, ("gem-of-the-bay",), "gem-of-the-bay-2"),
    # ... but never once it has been out, nor over an address someone chose, nor from no words.
    ({"published_at": NOW}, {"status": "published", "title": "Gem of the Bay"}, (), None),
    ({"slug": "my-pier"}, {"status": "published", "title": "Gem of the Bay"}, (), None),
    ({}, {"status": "published", "title": "!!!"}, (), None),
    ({}, {"status": "published"}, (), None),
    ({}, {"status": "draft", "title": "Gem of the Bay"}, (), None),
    ({}, {"status": "published", "title": "Gem", "slug": "chosen"}, (), "chosen"),
])
def test_a_story_takes_its_headline_address_when_it_first_goes_out(monkeypatch, invalidated, over, change, taken, slug):
    row = paged_row(**{"slug": "untitled-story-3", "title": "Untitled story", "status": "draft", "published_at": None,
                       **over})
    conn = _owner_conn(fetchrow={"FOR UPDATE": row, "UPDATE cappe_posts SET": row},
                       fetchval={"SELECT 1 FROM cappe_posts WHERE site_id": lambda sql, args: args[1] in taken or None})
    with _blog_client(monkeypatch, conn) as client:
        res = client.put(f"/sites/{SITE}/posts/{POST}", json=change)
    assert res.status_code == 200, res.text
    sql = conn.sql_for("fetchrow")[-1]
    if slug is None:
        assert "slug =" not in sql.split("RETURNING")[0]
    else:
        assert "slug =" in sql and slug in conn.args_for("UPDATE cappe_posts SET")


def test_a_story_cant_become_pages_through_the_story_api(monkeypatch, invalidated):
    conn = _owner_conn(fetchrow={"FOR UPDATE": story_row()})
    with _blog_client(monkeypatch, conn) as client:
        res = client.put(f"/sites/{SITE}/posts/{POST}", json={"format": "pages"})
    assert res.status_code == 422 and "Make a new story in the Studio" in res.text


def test_the_list_doesnt_carry_documents(monkeypatch):
    conn = _owner_conn(fetch={"FROM cappe_posts WHERE site_id = $1 ORDER BY": [paged_row()]},
                       fetchrow={"FROM cappe_posts WHERE id = $1 AND site_id = $2": paged_row()})
    with _blog_client(monkeypatch, conn) as client:
        posts = client.get(f"/sites/{SITE}/posts").json()
        one = client.get(f"/sites/{SITE}/posts/{POST}").json()
    assert posts[0]["format"] == "pages" and posts[0]["content"] is None and posts[0]["rev"] == 3
    assert one["content"]["doc"]["pages"]


def test_a_paged_preview(monkeypatch):
    conn = _owner_conn()
    with _blog_client(monkeypatch, conn) as client:
        res = client.post(f"/sites/{SITE}/stories/preview", json={"title": "Dawn", "format": "pages",
                                                                   "content": {"doc": _doc(image=True)}})
        bad = client.post(f"/sites/{SITE}/stories/preview", json={"format": "pages", "content": {"doc": []}})
    assert res.status_code == 200 and 'class="lyt"' in res.text and res.headers["cache-control"] == "no-store"
    assert bad.status_code == 422


# ── the Studio ───────────────────────────────────────────────────────────────

@pytest.fixture
def dropped(monkeypatch):
    calls = []

    async def fake(site_id):
        calls.append(site_id)

    monkeypatch.setattr(studio_mod, "invalidate_render_cache", fake)
    return calls


def _studio(monkeypatch, conn):
    monkeypatch.setattr(studio_mod, "get_connection", lambda: Ctx(conn))
    return route_client(studio_mod.router, overrides={studio_mod.require_cappe_account: ACCOUNT})


def _studio_conn(row, **tables):
    fetchrow = {"draft FROM cappe_posts": row}
    fetchrow.update(tables.pop("fetchrow", {}))
    return _owner_conn(fetchrow=fetchrow, **tables)


def test_opening_a_story(monkeypatch):
    with _studio(monkeypatch, _studio_conn(paged_row(status="draft"))) as client:
        res = client.get(f"/sites/{SITE}/studio/stories/{POST}").json()
    assert res["doc"]["threads"][0]["paras"][0]["runs"][0]["t"] == WORDS
    assert res["post"]["rev"] == 3 and res["draft"] is False and res["live"] is False


def test_opening_a_published_story_opens_its_working_copy(monkeypatch):
    draft = json.dumps({"doc": _doc("Working copy")})
    with _studio(monkeypatch, _studio_conn(paged_row(draft=draft))) as client:
        res = client.get(f"/sites/{SITE}/studio/stories/{POST}").json()
    assert res["draft"] is True and res["live"] is True
    assert res["doc"]["threads"][0]["paras"][0]["runs"][0]["t"] == "Working copy"


@pytest.mark.parametrize("method, path", [("get", ""), ("put", ""), ("post", "/discard")])
def test_a_story_that_isnt_paged_isnt_the_studios(monkeypatch, method, path):
    with _studio(monkeypatch, _studio_conn(story_row(rev=0, draft=None))) as client:
        body = {"base_rev": 0, "doc": _doc()} if method != "get" else None
        res = getattr(client, method)(f"/sites/{SITE}/studio/stories/{POST}{path}", **({"json": body} if body else {}))
    assert res.status_code == 409 and "isn't made of pages" in res.text


def test_a_missing_story(monkeypatch):
    with _studio(monkeypatch, _studio_conn(None)) as client:
        assert client.get(f"/sites/{SITE}/studio/stories/{POST}").status_code == 404
        assert client.put(f"/sites/{SITE}/studio/stories/{POST}", json={"base_rev": 0, "doc": _doc()}).status_code == 404


def test_a_stale_save_is_refused(monkeypatch, dropped):
    conn = _studio_conn(paged_row())
    with _studio(monkeypatch, conn) as client:
        res = client.put(f"/sites/{SITE}/studio/stories/{POST}", json={"base_rev": 2, "doc": _doc()})
    assert res.status_code == 409 and res.json()["detail"]["code"] == "stale_rev" and res.json()["detail"]["rev"] == 3
    assert not [s for s in conn.sql_for("execute") if "UPDATE cappe_posts" in s]


def test_saving_an_unpublished_story_saves_the_story(monkeypatch, dropped):
    conn = _studio_conn(paged_row(status="draft"))
    with _studio(monkeypatch, conn) as client:
        res = client.put(f"/sites/{SITE}/studio/stories/{POST}", json={"base_rev": 3, "doc": _doc("New words here")})
    assert res.status_code == 200, res.text
    assert res.json()["rev"] == 4 and res.json()["draft"] is False
    args = conn.args_for("UPDATE cappe_posts SET content")
    assert json.loads(args[0])["doc"]["threads"][0]["paras"][0]["runs"][0]["t"] == "New words here"
    assert args[1] == "New words here" and args[2] == 3 and args[6] == 4
    assert not [s for s in conn.sql_for("execute") if "cappe_post_revisions" in s]
    assert dropped == []  # nothing a reader sees changed


def test_saving_a_published_story_saves_its_working_copy(monkeypatch, dropped):
    conn = _studio_conn(paged_row())
    with _studio(monkeypatch, conn) as client:
        res = client.put(f"/sites/{SITE}/studio/stories/{POST}", json={"base_rev": 3, "doc": _doc("Draft", image=True),
                                                                       "keep": True})
    assert res.status_code == 200 and res.json()["draft"] is True
    assert json.loads(conn.args_for("UPDATE cappe_posts SET draft")[0])["doc"]
    assert conn.args_for("INSERT INTO cappe_post_revisions")[3] == "save"
    assert conn.args_for("INSERT INTO cappe_post_assets")[1] == [str(ASSET)]  # the working copy's picture is protected
    assert dropped == []


def test_updating_the_live_story(monkeypatch, dropped):
    conn = _studio_conn(paged_row())
    with _studio(monkeypatch, conn) as client:
        res = client.put(f"/sites/{SITE}/studio/stories/{POST}",
                         json={"base_rev": 3, "doc": _doc("Live"), "publish": True})
    assert res.status_code == 200 and res.json()["draft"] is False
    assert "draft = NULL" in [s for s in conn.sql_for("execute") if "UPDATE cappe_posts" in s][0]
    assert conn.args_for("INSERT INTO cappe_post_revisions")[3] == "publish"
    assert "LIMIT $2" in [s for s in conn.sql_for("execute") if "DELETE FROM cappe_post_revisions" in s][0]
    assert dropped == [SITE]


def test_a_bad_document_is_a_422(monkeypatch, dropped):
    with _studio(monkeypatch, _studio_conn(paged_row())) as client:
        res = client.put(f"/sites/{SITE}/studio/stories/{POST}", json={"base_rev": 3, "doc": {"pages": []}})
    assert res.status_code == 422 and "at least one page" in res.text


def test_throwing_the_working_copy_away(monkeypatch):
    conn = _studio_conn(paged_row(draft=json.dumps({"doc": _doc("x")})))
    with _studio(monkeypatch, conn) as client:
        res = client.post(f"/sites/{SITE}/studio/stories/{POST}/discard", json={"base_rev": 3})
        stale = client.post(f"/sites/{SITE}/studio/stories/{POST}/discard", json={"base_rev": 1})
    assert res.status_code == 200 and res.json() == {"rev": 4, "draft": False, "doc": _doc()}
    assert stale.status_code == 409


def test_revisions_listed_and_restored(monkeypatch, dropped):
    kept = json.dumps({"doc": _doc("An older version")})
    conn = _studio_conn(paged_row(status="draft"), fetch={"FROM cappe_post_revisions": [
        {"id": uuid4(), "rev": 2, "kind": "save", "title": "Dawn", "created_at": NOW}]},
        fetchval={"SELECT content FROM cappe_post_revisions": kept})
    rid = uuid4()
    with _studio(monkeypatch, conn) as client:
        listed = client.get(f"/sites/{SITE}/studio/stories/{POST}/revisions").json()
        res = client.post(f"/sites/{SITE}/studio/stories/{POST}/revisions/{rid}/restore", json={"base_rev": 3})
    assert listed[0]["kind"] == "save"
    assert res.status_code == 200 and res.json()["doc"]["threads"][0]["paras"][0]["runs"][0]["t"] == "An older version"
    assert conn.args_for("INSERT INTO cappe_post_revisions")[3] == "restore"
    conn.set("fetchval", "SELECT content FROM cappe_post_revisions", None)
    with _studio(monkeypatch, conn) as client:
        gone = client.post(f"/sites/{SITE}/studio/stories/{POST}/revisions/{rid}/restore", json={"base_rev": 3})
    assert gone.status_code == 404


def test_the_studios_limits_and_faces(monkeypatch):
    with _studio(monkeypatch, _owner_conn()) as client:
        res = client.get(f"/sites/{SITE}/studio/limits").json()
    assert res["limits"]["MAX_PAGES"] == 256 and "faces" in res["fonts"]


# ── readers ──────────────────────────────────────────────────────────────────

def test_a_paged_story_reads_as_pages_and_as_text(monkeypatch):
    row = paged_row(cover_asset_id=None)
    _wire(monkeypatch, _render_conn(story=row))
    page = asyncio.run(render_mod.story_page("harbour-at-dawn", _request("/stories/harbour-at-dawn")))
    assert page.status_code == 200 and 'class="lyt"' in page.body.decode() and WORDS in page.body.decode()
    text = asyncio.run(render_mod.story_text_page("harbour-at-dawn", _request("/stories/harbour-at-dawn/text")))
    assert text.status_code == 200 and "See it as designed" in text.body.decode() and WORDS in text.body.decode()


def test_other_stories_have_no_text_view(monkeypatch):
    _wire(monkeypatch, _render_conn(story=story_row()))
    res = asyncio.run(render_mod.story_text_page("harbour-at-dawn", _request("/stories/harbour-at-dawn/text")))
    assert res.status_code == 308 and res.headers["location"] == "/stories/harbour-at-dawn"
    _wire(monkeypatch, _render_conn(story=None))
    assert asyncio.run(render_mod.story_text_page("gone", _request("/stories/gone/text"))).status_code == 404
    assert asyncio.run(render_mod.story_text_page("../x", _request("/stories/x/text"))).status_code == 404


def test_the_public_json_never_returns_a_document(monkeypatch):
    conn = Conn(fetch={"FROM cappe_posts": [paged_row()]})
    monkeypatch.setattr(public_blog, "get_connection", lambda: Ctx(conn))
    monkeypatch.setattr(public_blog, "_published_site", AsyncMock(return_value=SITE_ROW))
    monkeypatch.setattr(public_blog, "_read_rate_limit", AsyncMock())
    with route_client(public_blog.router) as client:
        posts = client.get("/public/sites/bloom/posts").json()
    assert posts[0]["content"] is None and posts[0]["body"] == WORDS


def test_a_subscriber_gets_the_locked_pages(monkeypatch):
    doc = _doc("Free words")
    doc["threads"][0]["paras"].append({"runs": [{"t": PAID_SENTINEL}]})
    doc["threads"][0]["comp"] = {"lines": [[0, 0, 0, 10, 0, 20, 240, 0], [1, 1, 0, len(PAID_SENTINEL), 0, 20, 240, 0]]}
    post = {**PAID_POST, "format": "pages", "content": {"doc": S.normalize_doc(doc)}}
    with _paid_client(monkeypatch, post=post) as client:
        res = client.get("/public/sites/salt/stories/low-tide/paid")
    assert res.status_code == 200
    body = res.json()
    assert [p["n"] for p in body["pages"]] == [2] and PAID_SENTINEL in body["pages"][0]["html"]
    assert PAID_SENTINEL in body["html"] and "Free words" not in body["html"]


# ── faces ────────────────────────────────────────────────────────────────────

FACE = b"\x00\x01\x00\x00 not really a font"
FACE_SHA = hashlib.sha256(FACE).hexdigest()


@pytest.fixture
def one_face(monkeypatch, tmp_path):
    (tmp_path / f"{FACE_SHA}.ttf").write_bytes(FACE)
    (tmp_path / f"{'b' * 64}.ttf").write_bytes(b"other bytes")
    monkeypatch.setenv("CAPPE_FONTS_DIR", str(tmp_path))
    monkeypatch.setattr(faces, "_index", lambda: ({}, {FACE_SHA: {"sha": FACE_SHA}, "b" * 64: {"sha": "b" * 64}}))
    monkeypatch.setattr(fonts_mod, "_cache", fonts_mod.OrderedDict())
    storage = AsyncMock()
    storage.get_key.return_value = None
    monkeypatch.setattr(fonts_mod, "get_storage", lambda: storage)
    return storage


def test_a_face_is_served_for_a_year(one_face):
    with route_client(fonts_mod.router) as client:
        res = client.get(f"/public/fonts/{FACE_SHA}.ttf")
        again = client.get(f"/public/fonts/{FACE_SHA}.ttf")
    assert res.status_code == 200 and res.content == FACE and res.headers["content-type"] == "font/ttf"
    assert res.headers["cache-control"] == "public, max-age=31536000, immutable"
    assert again.content == FACE and FACE_SHA in fonts_mod._cache


def test_only_the_manifests_faces_with_their_own_bytes(one_face, monkeypatch):
    with route_client(fonts_mod.router) as client:
        assert client.get(f"/public/fonts/{'c' * 64}.ttf").status_code == 404  # not in the manifest
        assert client.get(f"/public/fonts/{'b' * 64}.ttf").status_code == 404  # bytes aren't its sha's
        monkeypatch.delenv("CAPPE_FONTS_DIR")
        assert client.get(f"/public/fonts/{FACE_SHA}.ttf").status_code == 404  # not uploaded
        one_face.get_key.return_value = FACE
        assert client.get(f"/public/fonts/{FACE_SHA}.ttf").status_code == 200  # from storage
    assert one_face.get_key.call_args.args[0] == f"cappe/fonts/{FACE_SHA}.ttf"


def test_the_manifest_is_served(monkeypatch):
    monkeypatch.setattr(fonts_mod, "manifest", lambda: {"version": "v", "faces": []})
    with route_client(fonts_mod.router) as client:
        res = client.get("/public/fonts/manifest.json")
    assert res.json() == {"version": "v", "faces": []} and "max-age=3600" in res.headers["cache-control"]


# ── storage at a fixed key ───────────────────────────────────────────────────

def _local_storage(tmp_path):
    from app.core.services.storage import StorageService

    s = StorageService.__new__(StorageService)
    s.s3_client, s.bucket = None, None
    s.app_root = str(tmp_path)
    s.uploads_root = str(tmp_path / "uploads")
    return s


def test_fixed_keys_on_local_storage(tmp_path):
    s = _local_storage(tmp_path)
    asyncio.run(s.put_key("cappe/fonts/x.ttf", b"face", "font/ttf"))
    assert asyncio.run(s.get_key("cappe/fonts/x.ttf")) == b"face"
    assert asyncio.run(s.get_key("cappe/fonts/missing.ttf")) is None
    for bad in ("../escape", "/abs", ""):
        with pytest.raises(RuntimeError):
            asyncio.run(s.get_key(bad))
    # A link inside uploads that leads out of it is refused too.
    (tmp_path / "outside").mkdir()
    (tmp_path / "outside" / "secret").write_bytes(b"no")
    (tmp_path / "uploads" / "link").symlink_to(tmp_path / "outside")
    with pytest.raises(RuntimeError):
        asyncio.run(s.get_key("link/secret"))


def test_fixed_keys_on_s3(tmp_path):
    from botocore.exceptions import ClientError

    s = _local_storage(tmp_path)
    s.bucket = "bucket"
    s.s3_client = AsyncMock()
    s.s3_client.put_object = lambda **kw: kw
    body = AsyncMock()
    body.read = lambda: b"face"
    s.s3_client.get_object = lambda **kw: {"Body": body}
    asyncio.run(s.put_key("cappe/fonts/x.ttf", b"face", "font/ttf"))
    assert asyncio.run(s.get_key("cappe/fonts/x.ttf")) == b"face"

    def missing(**kw):
        raise ClientError({"Error": {"Code": "NoSuchKey"}}, "GetObject")

    s.s3_client.get_object = missing
    assert asyncio.run(s.get_key("cappe/fonts/x.ttf")) is None
