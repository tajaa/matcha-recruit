"""The Gummfit-curated bank in Gummfit Studio (services/magazine/studio/bank.py,
routes/studio_bank_admin.py, the bank routes in routes/library.py and
routes/public/graphics.py, cappemag11).

What each block pins:

  * what an admin types: names, tags and collections cleaned; a photo's
    credit is the admin's words, else its creator and Gummfit; a graphic
    drawn in one paint is a silhouette, a second paint or a gradient keeps
    its colours;
  * pages: a graphic the manifest lacks is looked up in the bank (hidden ones
    too) and only then accepted, coloured only when it is one colour;
  * placing a photo makes (or finds) the site's library row on the bank's
    own files, credited and licensed as the bank says; a hidden or deleted
    photo can't be placed;
  * the admin's routes: a graphic is cleaned and stored by its sha (refused
    when it is built in), a photo stored with its sizes; a graphic can't be
    deleted or given a credit; every change is audited;
  * the public routes: the live picks, and a bank graphic's file served like
    a built-in one.

Run from server/:  ./venv/bin/python -m pytest tests/cappe/test_cappe_studio_bank.py -q
"""
import hashlib
import json
import re
from types import SimpleNamespace
from unittest.mock import AsyncMock
from uuid import uuid4

import pytest

from app.cappe.routes import blog as blog_mod
from app.cappe.routes import library as library_mod
from app.cappe.routes import studio_bank_admin as admin_mod
from app.cappe.routes.public import graphics as public_mod
from app.cappe.services import media
from app.cappe.services.magazine.studio import bank
from app.cappe.services.magazine.studio import graphics as G
from app.cappe.services.magazine.studio import schema as S
from tests._helpers.routes import route_client
from tests.cappe.test_cappe_magazine_routes import ACCOUNT, NOW, SITE, SITE_ROW, Conn, Ctx

SVG = 'xmlns="http://www.w3.org/2000/svg"'
CURATED = "c" * 64
PHOTO_ID = uuid4()
ADMIN = SimpleNamespace(email="admin@example.com", role="admin")
PHOTO = {"id": PHOTO_ID, "kind": "photo", "name": "Harbour at dawn", "tags": ["harbour", "boats"],
         "collection": "Coast", "status": "live", "sort_order": 0, "url": "https://cdn.example.test/b.jpg",
         "variants": json.dumps({"webp": [{"width": 400, "url": "https://cdn.example.test/b-400.webp"}]}),
         "width": 1600, "height": 1000, "bytes": 1000, "mime": "image/jpeg", "creator": "Ana Ruiz",
         "credit_line": "Ana Ruiz / Gummfit", "license": "gummfit", "source_url": None, "sha": None, "mono": None,
         "fit": None, "graphic_group": None, "w": None, "h": None, "created_by_email": "admin@example.com",
         "created_at": NOW, "updated_at": NOW}
GRAPHIC = {**PHOTO, "id": uuid4(), "kind": "graphic", "name": "Wave", "url": None, "variants": None, "width": None,
           "height": None, "credit_line": None, "license": None, "creator": None, "sha": CURATED, "mono": True,
           "fit": "stretch", "graphic_group": "lines", "w": 200.0, "h": 20.0}


# ── what an admin types ──────────────────────────────────────────────────────

def test_names_tags_and_collections_are_cleaned():
    assert bank.clean_name("  Harbour\n at   dawn ") == "Harbour at dawn"
    assert bank.clean_tags(" Boats, harbour ,BOATS,, a very long tag " + "x" * 60) == \
        ["boats", "harbour", ("a very long tag " + "x" * 60)[:bank.MAX_TAG]]
    assert bank.clean_tags([f"t{i}" for i in range(20)]) == [f"t{i}" for i in range(bank.MAX_TAGS)]
    assert bank.clean_collection("   ") is None and bank.clean_collection(" Coast ") == "Coast"


def test_a_photo_is_credited_as_the_admin_says_else_its_creator_and_gummfit():
    assert bank.credit("Ana Ruiz", "  Photo:  Ana Ruiz ") == "Photo: Ana Ruiz"
    assert bank.credit(" Ana  Ruiz ", None) == "Ana Ruiz / Gummfit"
    assert bank.credit(None, "") == "Gummfit"


@pytest.mark.parametrize("body, one", [
    ('<path d="M0 0h10v10z"/>', True),  # no paint: black
    ('<path fill="#123456" d="M0 0h10v10z"/><path fill="#123456" d="M5 5h1v1z"/>', True),
    ('<path fill="none" stroke="currentColor" d="M0 0h10"/>', True),
    ('<path fill="#123456" d="M0 0h10v10z"/><path fill="red" d="M5 5h1v1z"/>', False),
    ('<path style="fill:#fff;stroke:#000" d="M0 0h10v10z"/>', False),
    ('<defs><linearGradient id="g"><stop offset="0"/></linearGradient></defs><path fill="url(#g)" d="M0 0h1z"/>',
     False),
    # SVG's own defaults and inheritance: a fill nobody set is black, groups pass theirs down.
    ('<path d="M0 0h10v10z"/><path fill="red" d="M5 5h1v1z"/>', False),
    ('<g fill="red"><path d="M0 0h10v10z"/></g><path d="M5 5h1v1z"/>', False),
    ('<g fill="#f00"><path d="M0 0h10v10z"/></g><path fill="red" d="M5 5h1v1z"/>', False),  # names aren't guessed
    ('<g fill="#f00"><path d="M0 0h10v10z"/></g><path fill="#FF0000" d="M5 5h1v1z"/>', True),
    ('<path fill="#000" d="M0 0h10v10z"/><path fill="black" d="M5 5h1v1z"/>', True),
    ('<g color="#ff0000"><path fill="currentColor" d="M0 0h10v10z"/></g><path fill="#ff0000" d="M5 5h1v1z"/>', True),
    ('<g color="#ff0000"><path fill="currentColor" d="M0 0h10v10z"/></g><path d="M5 5h1v1z"/>', False),
    ('<line x1="0" y1="0" x2="10" y2="10" stroke="#ff0000"/><path fill="#ff0000" d="M0 0h1z"/>', True),
    ('<clipPath id="c"><path fill="blue" d="M0 0h10v10z"/></clipPath><path d="M0 0h1z"/>', True),
    ('<path fill="red" style="fill:#0000ff" d="M0 0h1z"/><path fill="#0000ff" d="M0 0h1z"/>', True),
    ('<g fill="#00f"><path fill="inherit" d="M0 0h1z"/></g><path fill="#0000ff" d="M0 0h1z"/>', True),
])
def test_one_paint_is_a_silhouette_more_keeps_its_colours(body, one):
    assert bank.one_colour(f'<svg {SVG} viewBox="0 0 10 10">{body}</svg>'.encode()) is one


def test_unreadable_svg_keeps_its_own_colours():
    assert bank.one_colour(b"<svg") is False


@pytest.mark.parametrize("attrs", ['viewBox="0 0 NaN 10"', 'viewBox="0 0 10 Infinity"', 'viewBox="nan 0 10 10"',
                                   'viewBox="0 0 10 -inf"', 'width="Infinity" height="10"', 'width="nan" height="nan"'])
def test_a_graphic_with_no_finite_size_is_refused(attrs):
    with pytest.raises(G.SvgError):
        G.clean_svg(f'<svg {SVG} {attrs}><path d="M0 0h1z"/></svg>'.encode())


def test_how_a_graphic_fills_its_box_by_its_group():
    assert [bank.default_fit(g) for g in ("lines", "shapes", "patterns", "icons", "stickers", "badges")] == \
        ["stretch", "stretch", "tile", "contain", "contain", "contain"]


# ── pages ────────────────────────────────────────────────────────────────────

def _doc(**item):
    return {"pages": [{"id": "p1"}], "items": [{"id": "g1", "kind": "graphic", "page": "p1", "w": 50, "h": 50, **item}],
            "threads": []}


@pytest.mark.asyncio
async def test_a_page_names_bank_graphics_the_manifest_lacks():
    star = next(g for g in G.manifest()["graphics"] if g["id"] == "gummfit/star")["sha"]
    doc = _doc(src=CURATED)
    doc["items"] += [{"id": "g2", "kind": "graphic", "page": "p1", "src": star},
                     {"id": "g3", "kind": "graphic", "page": "p1", "src": ["not", "a", "sha"]}]
    conn = Conn(fetch={"FROM cappe_studio_bank": [{"sha": CURATED, "mono": False, "fit": "contain"}]})
    assert await bank.doc_graphics(conn, doc) == {CURATED: {"sha": CURATED, "mono": False, "fit": "contain"}}
    assert conn.calls[0][2] == ([CURATED],)  # only what the manifest doesn't have
    quiet = Conn()
    assert await bank.doc_graphics(quiet, _doc(src=star)) == {} and quiet.calls == []


@pytest.mark.asyncio
async def test_every_bank_graphic_a_document_names_is_looked_up():
    shas = [f"{n:064x}" for n in range(501)]
    doc = {"pages": [{"id": "p1"}, {"id": "p2"}], "threads": [],
           "items": [{"id": f"g{n}", "kind": "graphic", "page": f"p{n % 2 + 1}", "src": sha} for n, sha in enumerate(shas)]}
    conn = Conn(fetch={"FROM cappe_studio_bank": [{"sha": sha, "mono": True, "fit": "contain"} for sha in shas]})
    found = await bank.doc_graphics(conn, doc)
    assert conn.calls[0][2] == (shas,) and len(found) == 501
    assert len(S.normalize_doc(doc, found)["items"]) == 501


def test_a_bank_graphic_on_a_page_is_held_to_the_bank():
    with pytest.raises(S.DocError):
        S.normalize_doc(_doc(src=CURATED))  # not looked up: not one the Studio has
    item = S.normalize_doc(_doc(src=CURATED, color="#AA0000", fit="nope"),
                           {CURATED: {"sha": CURATED, "mono": True, "fit": "stretch"}})["items"][0]
    assert (item["src"], item["color"], item["fit"]) == (CURATED, "#aa0000", "stretch")
    item = S.normalize_doc(_doc(src=CURATED, color="#AA0000"),
                           {CURATED: {"sha": CURATED, "mono": False, "fit": "contain"}})["items"][0]
    assert item["color"] is None  # a colourful graphic keeps its colours
    with pytest.raises(S.DocError):
        S.normalize_doc(_doc(src={"sha": CURATED}), {CURATED: {"sha": CURATED, "mono": True, "fit": "stretch"}})


@pytest.mark.asyncio
async def test_a_save_looks_the_pages_bank_graphics_up(monkeypatch):
    lookup = AsyncMock(return_value={CURATED: {"sha": CURATED, "mono": True, "fit": "stretch"}})
    monkeypatch.setattr(blog_mod.studio_bank, "doc_graphics", lookup)
    out = await blog_mod.pages_fields(Conn(), SITE, _doc(src=CURATED))
    assert out["content"]["doc"]["items"][0]["src"] == CURATED
    lookup.assert_awaited_once()


# ── placing a photo ──────────────────────────────────────────────────────────

ASSET_OUT = {"id": uuid4(), "kind": "stock", "url": PHOTO["url"], "prompt": None, "aspect": None, "image_size": None,
             "created_at": NOW, "source": "gummfit", "source_url": None, "title": "Harbour at dawn",
             "creator": "Ana Ruiz", "creator_url": None, "license": "gummfit", "license_version": None,
             "license_url": None, "provider_label": "Gummfit", "credit_line": "Ana Ruiz / Gummfit",
             "alt": "Harbour at dawn", "caption": None, "width": 1600, "height": 1000, "bytes": 1000,
             "mime": "image/jpeg", "variants": PHOTO["variants"], "ai_generated": False, "rights_attested_at": None,
             "moderation": "unchecked", "updated_at": NOW, "parent_asset_id": None, "recipe": None, "adapted": False}


@pytest.mark.asyncio
async def test_placing_a_photo_makes_the_sites_row_on_the_banks_files():
    conn = Conn(fetchrow={"FROM cappe_studio_bank": PHOTO, "INSERT INTO cappe_assets": ASSET_OUT})
    asset = await bank.place_photo(conn, account_id=ACCOUNT.id, site_id=SITE, item_id=PHOTO_ID)
    assert asset["source"] == "gummfit" and asset["variants"]["webp"][0]["width"] == 400
    select, insert = conn.calls
    assert "status = 'live'" in select[1]
    assert "ON CONFLICT (site_id, source, source_id)" in insert[1]  # placed again: the same row
    args = insert[2]
    assert args[:6] == (ACCOUNT.id, SITE, PHOTO["url"], "gummfit", str(PHOTO_ID), None)
    assert (args[8], args[9], args[10]) == ("gummfit", "Gummfit", "Ana Ruiz / Gummfit")  # licence, provider, credit
    assert json.loads(args[16]) == json.loads(PHOTO["variants"])
    assert await bank.place_photo(Conn(fetchrow={"FROM cappe_studio_bank": None}), account_id=ACCOUNT.id,
                                  site_id=SITE, item_id=PHOTO_ID) is None


@pytest.mark.asyncio
async def test_photos_match_every_word_in_name_tags_or_collection():
    conn = Conn(fetchval={"count(*)": 1}, fetch={"SELECT id, name": [PHOTO], "SELECT DISTINCT collection":
                                                 [{"collection": "Coast"}]})
    out = await bank.photos(conn, "Harbour 50%_off", "Coast", 0, 999)
    assert out["total"] == 1 and out["collections"] == ["Coast"]
    assert out["items"][0]["variants"]["webp"][0]["width"] == 400
    count_sql, args = conn.calls[0][1], conn.calls[0][2]
    assert args == ("Coast", "%harbour%", "%50\\%\\_off%") and "status = 'live'" in count_sql
    assert f"LIMIT {bank.PAGE_MAX}" in conn.calls[1][1]


# ── the site's routes ────────────────────────────────────────────────────────

def _site_client(monkeypatch, conn):
    monkeypatch.setattr(library_mod, "get_connection", lambda: Ctx(conn))
    monkeypatch.setattr(library_mod, "check_rate_limit", AsyncMock())
    return route_client(library_mod.router, overrides={library_mod.require_cappe_account: ACCOUNT})


def test_a_site_browses_and_places_bank_photos(monkeypatch):
    conn = Conn(fetchrow={"FROM cappe_sites": SITE_ROW, "FROM cappe_studio_bank": PHOTO,
                          "INSERT INTO cappe_assets": ASSET_OUT},
                fetchval={"count(*)": 1}, fetch={"SELECT id, name": [PHOTO], "SELECT DISTINCT collection": []})
    with _site_client(monkeypatch, conn) as client:
        res = client.get(f"/sites/{SITE}/library/bank?q=harbour")
        assert res.status_code == 200 and res.json()["items"][0]["name"] == "Harbour at dawn"
        res = client.post(f"/sites/{SITE}/library/bank/{PHOTO_ID}")
        assert res.status_code == 200 and res.json()["source"] == "gummfit"
    gone = Conn(fetchrow={"FROM cappe_sites": SITE_ROW, "FROM cappe_studio_bank": None})
    with _site_client(monkeypatch, gone) as client:
        assert client.post(f"/sites/{SITE}/library/bank/{PHOTO_ID}").status_code == 404


# ── the admin's routes ───────────────────────────────────────────────────────

def _admin_client(monkeypatch, conn, storage=None):
    monkeypatch.setattr(admin_mod, "get_connection", lambda: Ctx(conn))
    monkeypatch.setattr(admin_mod, "get_storage", lambda: storage or AsyncMock(get_key=AsyncMock(return_value=None)))
    audit = AsyncMock()
    monkeypatch.setattr(admin_mod, "record_matcha_admin_action", audit)
    return route_client(admin_mod.router, overrides={admin_mod.require_admin: ADMIN}), audit


WAVE = f'<svg {SVG} viewBox="0 0 200 20" width="200"><path fill="#0a0a0a" d="M0 10h200"/><script>x</script></svg>'


def test_an_admin_adds_a_graphic_cleaned_and_stored_by_its_sha(monkeypatch):
    clean, *_ = G.clean_svg(WAVE.encode())
    sha = hashlib.sha256(clean).hexdigest()
    conn = Conn(fetchrow={"INSERT INTO cappe_studio_bank": {**GRAPHIC, "sha": sha}})
    storage = AsyncMock(get_key=AsyncMock(return_value=None))
    cm, audit = _admin_client(monkeypatch, conn, storage)
    with cm as client:
        res = client.post("/studio-bank/graphics", files={"file": ("wave.svg", WAVE, "image/svg+xml")},
                          data={"name": "  Wave ", "tags": "sea, Water", "group": "lines"})
    assert res.status_code == 201
    storage.put_key.assert_awaited_once_with(f"cappe/graphics/{sha}.svg", clean, "image/svg+xml")
    assert b"script" not in clean
    args = conn.calls[0][2]
    assert args[:8] == ("Wave", ["sea", "water"], None, sha, True, "stretch", "lines", 200.0)  # one paint, a line
    assert audit.await_args.args[2] == "studio_bank.add_graphic"


def test_a_graphic_that_isnt_one_or_is_built_in_is_refused(monkeypatch):
    star = next(g for g in G.manifest()["graphics"] if g["id"] == "gummfit/star")
    from app.cappe.services.magazine.studio import graphics_own
    own = next(s for slug, *_, s, _ in graphics_own.all_graphics() if slug == "star").encode()
    cm, _ = _admin_client(monkeypatch, Conn())
    with cm as client:
        res = client.post("/studio-bank/graphics", files={"file": ("x.svg", b"<html/>", "image/svg+xml")},
                          data={"name": "X"})
        assert res.status_code == 422
        res = client.post("/studio-bank/graphics", files={"file": ("star.svg", own, "image/svg+xml")},
                          data={"name": "Star"})
        assert res.status_code == 409 and star["sha"]
        res = client.post("/studio-bank/graphics", files={"file": ("w.svg", WAVE, "image/svg+xml")},
                          data={"name": "   "})
        assert res.status_code == 422


def test_an_svg_with_no_finite_size_stores_nothing(monkeypatch):
    conn = Conn()
    storage = AsyncMock(get_key=AsyncMock(return_value=None))
    cm, audit = _admin_client(monkeypatch, conn, storage)
    with cm as client:
        res = client.post("/studio-bank/graphics", data={"name": "Bad"},
                          files={"file": ("x.svg", f'<svg {SVG} viewBox="0 0 NaN 10"><path d="M0 0h1z"/></svg>',
                                          "image/svg+xml")})
    assert res.status_code == 422
    assert conn.calls == [] and storage.put_key.await_count == 0 and audit.await_count == 0


def test_an_admin_adds_a_photo_with_its_sizes(monkeypatch):
    stored = media.StoredImage(url="https://cdn.example.test/bank.jpg", mime="image/jpeg", width=1600, height=1000,
                               bytes=1000, variants={"webp": []})
    monkeypatch.setattr(admin_mod.media, "process_image", lambda *a, **k: object())
    store = AsyncMock(return_value=stored)
    monkeypatch.setattr(admin_mod.media, "store_processed", store)
    monkeypatch.setattr(admin_mod.upload_guard, "verify_upload", lambda data, declared, allowed: "image/jpeg")
    conn = Conn(fetchrow={"INSERT INTO cappe_studio_bank": PHOTO})
    cm, _ = _admin_client(monkeypatch, conn)
    with cm as client:
        res = client.post("/studio-bank/photos", files={"file": ("b.jpg", b"JPEG", "image/jpeg")},
                          data={"name": "Harbour at dawn", "creator": "Ana Ruiz", "collection": "Coast"})
        assert res.status_code == 201
        assert store.await_args.kwargs["prefix"] == "cappe/bank"
        args = conn.calls[0][2]
        assert (args[0], args[2], args[9], args[10], args[11]) == \
            ("Harbour at dawn", "Coast", "Ana Ruiz", "Ana Ruiz / Gummfit", "gummfit")
        res = client.post("/studio-bank/photos", files={"file": ("b.jpg", b"JPEG", "image/jpeg")},
                          data={"name": "Harbour", "license": "by"})
        assert res.status_code == 422  # CC BY: say who to credit
        res = client.post("/studio-bank/photos", files={"file": ("b.jpg", b"JPEG", "image/jpeg")},
                          data={"name": "Harbour", "source_url": "javascript:alert(1)"})
        assert res.status_code == 422


def test_editing_hiding_and_deleting(monkeypatch):
    conn = Conn(fetchrow={"FROM cappe_studio_bank WHERE id = $1": PHOTO, "UPDATE cappe_studio_bank": PHOTO})
    cm, audit = _admin_client(monkeypatch, conn)
    with cm as client:
        res = client.patch(f"/studio-bank/{PHOTO_ID}", json={"creator": "Bo Li", "status": "hidden", "tags": ["A", "a"]})
        assert res.status_code == 200
        update = next(c for c in conn.calls if "UPDATE" in c[1])
        written = {name: update[2][int(n) - 1] for name, n in re.findall(r"(\w+) = \$(\d+)", update[1])}
        assert written == {"id": PHOTO_ID, "tags": ["a"], "status": "hidden", "creator": "Bo Li",
                           "credit_line": "Bo Li / Gummfit"}  # the credit follows the creator
        written_by_hand = Conn(fetchrow={"FROM cappe_studio_bank WHERE id = $1": {**PHOTO, "credit_line": "Photo: AR"},
                                         "UPDATE cappe_studio_bank": PHOTO})
        monkeypatch.setattr(admin_mod, "get_connection", lambda: Ctx(written_by_hand))
        client.patch(f"/studio-bank/{PHOTO_ID}", json={"creator": "Bo Li"})
        assert written_by_hand.calls[-1][2][-1] == "Photo: AR"  # the admin's own words stay
        monkeypatch.setattr(admin_mod, "get_connection", lambda: Ctx(conn))
        assert client.delete(f"/studio-bank/{PHOTO_ID}").status_code == 204
    assert [c.args[2] for c in audit.await_args_list] == ["studio_bank.update"] * 2 + ["studio_bank.delete"]

    conn = Conn(fetchrow={"FROM cappe_studio_bank WHERE id = $1": GRAPHIC})
    cm, _ = _admin_client(monkeypatch, conn)
    with cm as client:
        assert client.delete(f"/studio-bank/{GRAPHIC['id']}").status_code == 409  # pages may use it
        assert client.patch(f"/studio-bank/{GRAPHIC['id']}", json={"credit_line": "Me"}).status_code == 422
    cm, _ = _admin_client(monkeypatch, Conn(fetchrow={"FROM cappe_studio_bank WHERE id = $1": None}))
    with cm as client:
        assert client.delete(f"/studio-bank/{uuid4()}").status_code == 404


@pytest.mark.parametrize("stored, patch, ok", [
    ({"creator": None, "license": "gummfit"}, {"license": "by"}, False),         # BY with no one to credit
    ({"creator": None, "license": "gummfit"}, {"license": "by-sa", "creator": " "}, False),
    ({"creator": "Ana Ruiz", "license": "by"}, {"creator": ""}, False),          # clearing a BY photo's creator
    ({"creator": "Ana Ruiz", "license": "by"}, {"creator": None, "credit_line": ""}, False),
    ({"creator": None, "license": "gummfit"}, {"license": "by", "creator": "Bo Li"}, True),
    ({"creator": "Ana Ruiz", "license": "by"}, {"creator": "", "license": "cc0"}, True),
    ({"creator": "Ana Ruiz", "license": "by"}, {"name": "Harbour"}, True),
])
def test_a_cc_by_photo_always_has_a_creator_after_an_edit(monkeypatch, stored, patch, ok):
    conn = Conn(fetchrow={"FROM cappe_studio_bank WHERE id = $1": {**PHOTO, **stored}, "UPDATE cappe_studio_bank": PHOTO})
    cm, _ = _admin_client(monkeypatch, conn)
    with cm as client:
        res = client.patch(f"/studio-bank/{PHOTO_ID}", json=patch)
    assert res.status_code == (200 if ok else 422)
    assert any("UPDATE" in c[1] for c in conn.calls) is ok


def test_the_downgrade_refuses_while_the_bank_holds_graphics():
    import pathlib
    text = (pathlib.Path(__file__).resolve().parents[2] / "alembic" / "versions" / "cappemag11_studio_bank.py").read_text()
    down = text[text.index("_DOWNGRADE = ["):]
    guard = down.index("FROM cappe_studio_bank WHERE kind = 'graphic'")
    assert down.index("RAISE EXCEPTION", guard) < down.index("DROP TABLE IF EXISTS cappe_studio_bank")


# ── the public routes ────────────────────────────────────────────────────────

def test_the_live_picks_and_a_bank_graphics_file(monkeypatch, tmp_path):
    clean, *_ = G.clean_svg(WAVE.encode())
    sha = hashlib.sha256(clean).hexdigest()
    (tmp_path / f"{sha}.svg").write_bytes(clean)
    public_mod._cache.clear()
    monkeypatch.setenv("CAPPE_GRAPHICS_DIR", str(tmp_path))
    conn = Conn(fetch={"FROM cappe_studio_bank": [{**GRAPHIC, "sha": sha, "tags": ["sea"]}]},
                fetchval={"FROM cappe_studio_bank": lambda sql, args: 1 if args[0] == sha else None})
    monkeypatch.setattr(public_mod, "get_connection", lambda: Ctx(conn))
    with route_client(public_mod.router) as client:
        res = client.get("/public/graphics/picks")
        assert res.status_code == 200 and "max-age=300" in res.headers["cache-control"]
        assert res.json()["items"] == [{"sha": sha, "name": "Wave", "group": "lines", "mono": True, "fit": "stretch",
                                        "w": 200.0, "h": 20.0, "tags": ["sea"], "collection": "Coast"}]
        res = client.get(f"/public/graphics/{sha}.svg")
        assert res.status_code == 200 and res.content == clean and "sandbox" in res.headers["content-security-policy"]
        assert client.get(f"/public/graphics/stretch/{sha}.svg").content.startswith(b'<svg preserveAspectRatio="none"')
        assert client.get(f"/public/graphics/{'d' * 64}.svg").status_code == 404
        assert client.get("/public/graphics/not-a-sha.svg").status_code == 404
