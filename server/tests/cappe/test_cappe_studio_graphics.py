"""The Studio's graphics bank (services/magazine/studio/graphics.py,
graphics_own.py, routes/public/graphics.py, the `graphic` item in schema.py).

What each block pins:

  * cleaning: an SVG keeps only drawing (no scripts, events, styles, foreign
    content, other files, `javascript:` or `data:` values, declarations or
    entities), loses its width and height, and keeps references inside
    itself; anything that isn't an SVG is refused;
  * the committed manifest: unique shas, known groups and fits, every one of
    our own graphics in it (one colour), and the licences kept;
  * a page's graphic must be one of the bank's; only a one-colour graphic
    takes a colour; its fit and a pattern's tile are held to their limits;
  * search: every word must match, an exact name first, by group and sticker
    set; browsing gives each group's first graphics and counts;
  * over HTTP: a file only by a manifest sha, checked against it, immutable
    and sent with a CSP that runs nothing.

Run from server/:  ./venv/bin/python -m pytest tests/cappe/test_cappe_studio_graphics.py -q
"""
import hashlib

import pytest

from app.cappe.routes.public import graphics as route
from app.cappe.services.magazine.studio import graphics as G
from app.cappe.services.magazine.studio import graphics_own
from app.cappe.services.magazine.studio import limits as L
from app.cappe.services.magazine.studio import schema as S
from tests._helpers.routes import route_client

SVG = 'xmlns="http://www.w3.org/2000/svg"'
BY_ID = {g["id"]: g for g in G.manifest()["graphics"]}


# ── cleaning ─────────────────────────────────────────────────────────────────

def test_cleaning_keeps_drawing_and_nothing_else():
    dirty = (f'<svg {SVG} xmlns:xlink="http://www.w3.org/1999/xlink" width="24" height="24" viewBox="0 0 24 24" '
             'onload="alert(1)" class="x" style="background:url(https://evil.example.test/x.png)">'
             '<script>alert(1)</script><style>*{fill:red}</style>'
             '<foreignObject><div xmlns="http://www.w3.org/1999/xhtml">hi</div></foreignObject>'
             '<defs><linearGradient id="g"><stop offset="0" stop-color="#fff"/></linearGradient></defs>'
             '<path d="M0 0H24V24Z" fill="url(#g)" onclick="x()"/>'
             '<use href="#g"/><use xlink:href="https://evil.example.test/s.svg#a"/>'
             '<rect width="4" height="4" fill="url(https://evil.example.test/p.svg#a)"/>'
             '<a href="javascript:alert(1)"><circle r="2"/></a>'
             '<image href="data:image/png;base64,AAAA"/></svg>').encode()
    clean, w, h = G.clean_svg(dirty)
    text = clean.decode()
    assert (w, h) == (24, 24)
    for gone in ("onload", "onclick", "script", "style", "foreignObject", "evil.example.test", "javascript:",
                 "data:", "class=", "<a", "<image", 'width="24"'):
        assert gone not in text, gone
    assert 'fill="url(#g)"' in text and 'href="#g"' in text and '<rect width="4" height="4" />' in text
    assert text.startswith("<svg") and "<?xml" not in text
    assert G.clean_svg(clean)[0] == clean  # cleaning twice changes nothing


def test_a_viewbox_comes_from_the_size_when_missing():
    clean, w, h = G.clean_svg(f'<svg {SVG} width="40px" height="20"><path d="M0 0H1"/></svg>'.encode())
    assert (w, h) == (40, 20) and 'viewBox="0 0 40.0 20.0"' in clean.decode()


@pytest.mark.parametrize("data", [
    b'<?xml version="1.0"?><!DOCTYPE svg [<!ENTITY a "aaaa">]><svg xmlns="http://www.w3.org/2000/svg">&a;</svg>',
    b"<html><body/></html>",
    b"not xml",
    f'<svg {SVG}><path d="M0 0"/></svg>'.encode(),  # no size at all
    f'<svg {SVG} viewBox="0 0 0 10"/>'.encode(),
    f'<svg {SVG} viewBox="0 0 10 10">{"<g/>" * 50_000}</svg>'.encode(),  # too big
])
def test_what_isnt_an_svg_is_refused(data):
    with pytest.raises(G.SvgError):
        G.clean_svg(data)


# ── the bank ─────────────────────────────────────────────────────────────────

def test_the_manifest_holds_together():
    graphics = G.manifest()["graphics"]
    shas = [g["sha"] for g in graphics]
    assert len(shas) == len(set(shas)) and len(graphics) > 3000
    assert {g["group"] for g in graphics} == set(G.GROUPS)
    assert all(g["fit"] in L.GRAPHIC_FITS and g["w"] > 0 and g["h"] > 0 for g in graphics)
    assert all(g["mono"] for g in graphics if g["source"] in ("lucide", "gummfit"))
    assert not any(g["mono"] for g in graphics if g["source"] == "fluent")
    assert all(g.get("set") for g in graphics if g["group"] == "stickers")
    assert {s["id"] for s in G.manifest()["sources"]} == {"gummfit", "lucide", "fluent"}
    licences = G.MANIFEST.with_name("graphics_licenses.txt").read_text(encoding="utf-8")
    assert "ISC License" in licences and "Cole Bemis" in licences and "Microsoft Corporation" in licences
    assert "CC0" in licences


def test_our_own_graphics_are_in_the_bank_as_built():
    own = graphics_own.all_graphics()
    assert len({slug for slug, *_ in own}) == len(own)
    for slug, name, group, tags, svg, fit in own:
        clean, *_ = G.clean_svg(svg.encode())
        entry = BY_ID[f"gummfit/{slug}"]
        assert entry["sha"] == hashlib.sha256(clean).hexdigest(), f"{slug}: build the bank again"
        assert (entry["name"], entry["group"], entry["fit"]) == (name, group, fit)


# ── on a page ────────────────────────────────────────────────────────────────

def _doc(**item):
    return {"pages": [{"id": "p1"}], "items": [{"id": "g1", "kind": "graphic", "page": "p1", "w": 50, "h": 50, **item}],
            "threads": []}


def test_a_graphic_on_a_page():
    star, heart = BY_ID["gummfit/star"], BY_ID["fluent/red-heart"]
    item = S.normalize_doc(_doc(src=star["sha"], color="#AA0000", fit="tile", tile=99_999))["items"][0]
    assert item == {**item, "src": star["sha"], "color": "#aa0000", "fit": "tile", "tile": L.TILE_MAX}
    item = S.normalize_doc(_doc(src=star["sha"], color="nope", fit="sideways"))["items"][0]
    assert (item["color"], item["fit"], item["tile"]) == ("#1a1a1a", "stretch", L.TILE_DEFAULT)  # its own fit
    item = S.normalize_doc(_doc(src=heart["sha"], color="#00ff00"))["items"][0]
    assert (item["color"], item["fit"]) == (None, "contain")  # a colourful graphic keeps its colours


@pytest.mark.parametrize("src", ["0" * 64, None, "../../etc/passwd"])
def test_only_the_banks_graphics(src):
    with pytest.raises(S.DocError):
        S.normalize_doc(_doc(src=src))


# ── search ───────────────────────────────────────────────────────────────────

def test_search_puts_an_exact_name_first_and_needs_every_word():
    found = G.search("heart")
    assert found["items"][0]["name"] == "Heart" and found["total"] > 20
    assert all("heart" in (g["name"].lower() + " ".join(BY_ID_TAGS[g["sha"]])) for g in found["items"])
    two = G.search("red heart")
    assert two["items"][0]["name"] == "Red heart" and two["total"] < found["total"]
    assert G.search("zzzzqqq")["total"] == 0


BY_ID_TAGS = {g["sha"]: g["tags"] for g in G.manifest()["graphics"]}


def test_search_by_group_and_set():
    icons = G.search("arrow", group="icons", limit=500)
    assert icons["total"] > 30 and {g["group"] for g in icons["items"]} == {"icons"}
    food = G.search("", group="stickers", set_="Food and drink", limit=500)
    assert food["total"] > 50 and {g["set"] for g in food["items"]} == {"Food and drink"}
    assert len(G.search("", limit=10_000)["items"]) == G.SEARCH_MAX
    page2 = G.search("", group="icons", offset=60, limit=60)["items"]
    assert page2[0] == G.search("", group="icons", limit=61)["items"][60]


def test_browsing_gives_each_groups_first():
    b = G.browse()
    assert [g["group"] for g in b["groups"]] == list(G.GROUPS)
    assert all(len(g["items"]) == min(g["count"], G.BROWSE_PER_GROUP) for g in b["groups"])
    assert sum(s["count"] for s in b["sets"]) == next(g["count"] for g in b["groups"] if g["group"] == "stickers")
    assert set(b["groups"][0]["items"][0]) == {"sha", "name", "group", "mono", "fit", "w", "h"}


# ── over HTTP ────────────────────────────────────────────────────────────────

class NoStorage:
    async def get_key(self, key):
        return None


@pytest.fixture
def files(monkeypatch, tmp_path):
    route._cache.clear()
    monkeypatch.setattr(route, "get_storage", lambda: NoStorage())
    monkeypatch.setenv("CAPPE_GRAPHICS_DIR", str(tmp_path))
    star = BY_ID["gummfit/star"]
    clean, *_ = G.clean_svg(next(s for slug, *_, s, _ in graphics_own.all_graphics() if slug == "star").encode())
    (tmp_path / f"{star['sha']}.svg").write_bytes(clean)
    return star


def _get(path):
    with route_client(route.router) as client:
        return client.get(path)


def test_a_file_is_served_by_its_sha_with_nothing_to_run(files):
    res = _get(f"/public/graphics/{files['sha']}.svg")
    assert res.status_code == 200 and res.headers["content-type"] == "image/svg+xml"
    assert "immutable" in res.headers["cache-control"] and "sandbox" in res.headers["content-security-policy"]
    assert res.headers["x-content-type-options"] == "nosniff"
    assert hashlib.sha256(res.content).hexdigest() == files["sha"]


def test_unknown_unbuilt_or_changed_files_are_404(files, tmp_path):
    assert _get(f"/public/graphics/{'0' * 64}.svg").status_code == 404
    other = BY_ID["gummfit/heart"]["sha"]
    assert _get(f"/public/graphics/{other}.svg").status_code == 404  # not built here, not in storage
    (tmp_path / f"{other}.svg").write_bytes(b"<svg/>")  # not the bytes its sha names
    assert _get(f"/public/graphics/{other}.svg").status_code == 404


def test_browse_search_and_licences_over_http():
    assert _get("/public/graphics/browse").json()["groups"][0]["group"] == "shapes"
    res = _get("/public/graphics/search?q=coffee&group=stickers")
    assert res.status_code == 200 and res.json()["items"][0]["name"] == "Hot beverage"
    assert _get("/public/graphics/search?group=fonts").status_code == 422
    assert "MIT License" in _get("/public/graphics/licenses.txt").text
