"""Designs: words, shapes and pictures laid over a story's pictures and pages.

What this pins:

  * the normalizer keeps only what a design may hold (ids unique, numbers
    clamped and rounded as the client rounds, colours hex or the accent, faces
    and weights the face has, links web or mail, pictures library ids) and
    refuses one too big;
  * the server draws exactly the shared fixture the client draws too, and
    escapes every word;
  * a story keeps designs on its cover, photos, photo groups and designed
    pages, counts their pictures as its own (credits printed, deletes refused),
    reads their words, and asks Google for exactly the faces it sets;
  * the editor's page marks each layer and opens its words exactly.

Run from server/:  ./venv/bin/python -m pytest tests/cappe/test_cappe_design_schema.py -q
"""
import json
import re
from pathlib import Path
from uuid import uuid4

import pytest

from app.cappe.services.magazine import design_render, design_schema, fonts, pages, story_render, story_schema
from app.cappe.services.magazine.stories import story_text

ROOT = Path(__file__).resolve().parents[3]
FIXTURE = Path(__file__).parent / "fixtures" / "magazine_design_cases.json"
FONTS_TS = ROOT / "client/src/cappe/magazine/design/fonts.ts"
A, B = str(uuid4()), str(uuid4())
ASSETS = {
    A: {"id": A, "url": "https://cdn.example.test/a.jpg", "alt": "Tower", "width": 1600, "height": 1200,
        "credit_line": "Photo: Ana", "variants": {}},
    B: {"id": B, "url": "https://cdn.example.test/b.png", "alt": "Gull", "width": 400, "height": 400,
        "credit_line": "Photo: Bo", "variants": {}},
}


def doc(text):
    return {"type": "doc", "content": [{"type": "paragraph", "content": [{"type": "text", "text": text}]}]}


def norm(*layers, **design):
    return design_schema.normalize_design({"layers": list(layers), **design})


# ── what a design may hold ───────────────────────────────────────────────────

def test_a_layer_keeps_known_choices_and_clamped_numbers():
    (lay,) = norm({"kind": "shape", "id": "Bad Id!", "x": -500, "y": "12.34", "w": 0, "h": 999, "rot": 400,
                   "opacity": 140.6, "blend": "dodgy", "shape": "star", "flip_x": 1, "radius": 70,
                   "stroke": {"width": 99, "style": "wavy", "color": "red"}, "extra": "dropped"})["layers"]
    assert lay["id"] == "l1" and lay["x"] == -100 and lay["y"] == 12.3 and (lay["w"], lay["h"]) == (0.5, 400)
    assert lay["rot"] == 180 and lay["opacity"] == 100 and lay["blend"] == "normal" and lay["shape"] == "rect"
    assert lay["flip_x"] is True and lay["radius"] == [50, 50, 50, 50] and "extra" not in lay
    assert lay["stroke"] == {"color": "#000000", "width": 10, "style": "solid"}


def test_numbers_round_half_up_as_the_client_does():
    assert design_schema.num(12.25, 0, 100, 0) == 12.3 and design_schema.num(-12.25, -100, 100, 0) == -12.2
    assert design_schema.num(-0.04, -1, 1, 0) == 0 and str(design_schema.num(-0.04, -1, 1, 0)) == "0.0"
    assert design_schema.num(float("nan"), 0, 1, 0.5) == 0.5 and design_schema.num("x", 0, 1, 0.5) == 0.5


def test_ids_are_kept_once_and_made_when_missing():
    layers = norm({"kind": "shape", "id": "a"}, {"kind": "shape", "id": "a"}, {"kind": "shape"})["layers"]
    assert [lay["id"] for lay in layers] == ["a", "l2", "l3"]


def test_paint_is_none_a_colour_or_a_gradient_of_two_to_eight_stops():
    p = design_schema.paint
    assert p({"kind": "solid", "color": "#ABCDEF"})["color"] == "#abcdef"
    assert p({"kind": "solid", "color": "url(x)"})["color"] == "#000000"
    g = p({"kind": "linear", "angle": 450, "stops": [{"color": "#fff", "at": 80}, {"color": "#000000", "at": -5}]})
    assert g["angle"] == 360 and g["stops"] == [{"color": "#000000", "at": 0}, {"color": "#000000", "at": 80}]
    assert p({"kind": "radial", "stops": [{"color": "#000000", "at": 0}]})["kind"] == "solid"  # one stop is a colour
    assert len(p({"kind": "linear", "stops": [{"color": "#000000", "at": i} for i in range(20)]})["stops"]) == 8
    assert p({"kind": "fancy"})["kind"] == "none" and p(None)["kind"] == "none"


def test_text_keeps_a_face_it_knows_and_the_weights_that_face_has():
    (t,) = norm({"kind": "text", "font": "Anton", "weight": 900, "italic": True, "size": 99, "leading": 0.123,
                 "tracking": 5, "case": "shout", "color": "accent", "rt": doc("Hi")})["layers"]
    assert (t["font"], t["weight"], t["italic"]) == ("Anton", 400, False)  # Anton has one weight, no italic
    assert (t["size"], t["leading"], t["tracking"], t["case"], t["color"]) == (60, 0.6, 1, "none", "accent")
    (u,) = norm({"kind": "text", "font": "Comic Sans", "weight": 650, "italic": True})["layers"]
    assert (u["font"], u["weight"], u["italic"]) == ("heading", 700, True) and u["rt"] == {"type": "doc", "content": [{"type": "paragraph"}]}
    (v,) = norm({"kind": "text", "rt": {"type": "doc", "content": [{"type": "paragraph", "content": [{"type": "text", "text": "x" * 3000}]}]}})["layers"]
    assert len(v["rt"]["content"][0]["content"][0]["text"]) == design_schema.MAX_TEXT


def test_a_link_is_web_or_mail_only():
    links = [lay["link"] for lay in norm(*({"kind": "shape", "link": href} for href in (
        "https://example.test/x", "mailto:a@example.com", "javascript:alert(1)", "data:text/html,x", "x" * 600)))["layers"]]
    assert links == ["https://example.test/x", "mailto:a@example.com", "", "", ""]


def test_a_picture_is_a_library_id_and_a_picture_layer_needs_one():
    assert norm({"kind": "image"}) is None  # nothing left: no design
    with pytest.raises(design_schema.DesignError, match="library"):
        norm({"kind": "image", "asset_id": "https://evil.test/x.jpg"})
    (img,) = norm({"kind": "image", "asset_id": A, "fit": "stretch", "zoom": 900, "focal": {"x": -4}})["layers"]
    assert (img["fit"], img["zoom"], img["focal"]) == ("cover", 400, {"x": 0, "y": 50})


def test_groups_nest_four_deep_and_an_empty_one_is_dropped():
    deep = {"kind": "shape", "id": "leaf"}
    for i in range(6):
        deep = {"kind": "group", "id": f"g{i}", "children": [deep]}
    (top,) = norm(deep)["layers"]
    depth, node = 1, top
    while node["kind"] == "group":
        node, depth = node["children"][0], depth + 1
    assert depth == 5 and node["id"] == "leaf"  # four groups, then the leaf
    assert norm({"kind": "group", "children": [{"kind": "image"}]}) is None


def test_the_limits_an_owner_is_told_about():
    with pytest.raises(design_schema.DesignError, match="at most 200"):
        norm(*[{"kind": "shape"}] * 201)
    with pytest.raises(design_schema.DesignError, match="too much"):
        norm(*[{"kind": "text", "rt": doc("x" * 1900)}] * 60)


def test_a_designed_page_always_has_its_background():
    page = design_schema.normalize_design(None, page=True)
    assert page == {"layers": [], "background": {"kind": "solid", "color": "#ffffff", "angle": 180, "stops": []}}


# ── the same bytes on both sides ─────────────────────────────────────────────

def test_the_shared_fixture_is_what_the_server_draws():
    for case in json.loads(FIXTURE.read_text(encoding="utf-8")):
        pic = case["picture"]
        html = design_render.design_html(case["design"], case["assets"], edit=case["edit"], path=case["path"],
                                         picture=tuple(pic) if pic else None)
        assert html == case["html"], case["name"]


def test_every_word_is_escaped_and_hidden_layers_never_drawn():
    design = norm({"kind": "text", "rt": doc('<img src=x onerror="alert(1)">'), "name": "<b>"},
                  {"kind": "shape", "hidden": True, "fill": {"kind": "solid", "color": "#ff0000"}})
    html = design_render.design_html(design, {})
    assert "<img" not in html and "&lt;img src=x onerror=&quot;alert(1)&quot;&gt;" not in html  # quotes stay in text
    assert "&lt;img src=x onerror=\"alert(1)\"&gt;" in html and "#ff0000" not in html


def test_the_page_lists_the_same_faces_as_the_client():
    ts = FONTS_TS.read_text(encoding="utf-8")
    rows = re.findall(r"\{ name: '([^']+)', cat: '(\w+)', body: (true|false), w: \[([\d, ]*)\], i: \[([\d, ]*)\] \}", ts)
    client = {name: (cat, body == "true", tuple(int(x) for x in w.split(", ") if x), tuple(int(x) for x in i.split(", ") if x))
              for name, cat, body, w, i in rows}
    assert client == fonts.FONTS
    assert all(400 in weights for _cat, _body, weights, _i in fonts.FONTS.values())  # the style every link asks for


def test_a_page_asks_google_for_each_face_it_sets_and_no_style_it_lacks():
    links = fonts.fonts_links({"Lora": {(700, True), (900, False)}, "Anton": {(400, True)}, "Nope": {(400, False)}})
    assert links.count("<link") == 2 and "Nope" not in links
    assert "family=Anton:ital,wght@0,400&amp;display=swap" in links  # no italic Anton is asked for
    assert "family=Lora:ital,wght@0,400;0,700;1,700&amp;display=swap" in links
    assert "family=Playfair%20Display" in fonts.fonts_links({"Playfair Display": {(400, False)}})


# ── a story with designs ─────────────────────────────────────────────────────

def _story(*blocks):
    return story_schema.normalize_story({"blocks": list(blocks)})


TEXT = {"kind": "text", "id": "head", "rt": doc("Over the bay"), "font": "Lora", "weight": 700}
PIC = {"kind": "image", "id": "gull", "asset_id": B}


def test_a_story_keeps_designs_on_every_picture_and_its_pages():
    content = _story({"type": "cover", "asset_id": A, "design": {"layers": [TEXT]}},
                     {"type": "photo", "asset_id": A, "design": {"layers": [PIC]}},
                     {"type": "photos", "items": [{"asset_id": A, "design": {"layers": [TEXT]}}]},
                     {"type": "page", "aspect": "9:16", "design": {"layers": [TEXT, PIC]}})
    cover, photo, group, page = content["blocks"]
    assert cover["design"]["layers"][0]["id"] == "head" and photo["design"]["layers"][0]["asset_id"] == B
    assert group["items"][0]["design"]["layers"][0]["font"] == "Lora"
    assert page["aspect"] == "3:4" and page["design"]["background"]["color"] == "#ffffff"
    assert story_schema.referenced_asset_ids(content) == {A, B}
    with pytest.raises(story_schema.StoryError, match="library"):
        _story({"type": "photo", "design": {"layers": [{"kind": "image", "asset_id": "nope"}]}})


def test_the_words_on_pictures_and_pages_are_the_story_s_text():
    content = _story({"type": "cover", "asset_id": A, "design": {"layers": [TEXT]}},
                     {"type": "photo", "asset_id": A, "caption": "The bay.", "design": {"layers": [{**TEXT, "rt": doc("Dawn")}]}},
                     {"type": "photos", "items": [{"asset_id": A, "design": {"layers": [{**TEXT, "rt": doc("Gulls")}]}}]},
                     {"type": "page", "design": {"layers": [{**TEXT, "rt": doc("Fin"), "hidden": True}, {**TEXT, "id": "x", "rt": doc("End")}]}})
    assert story_text(content) == "Over the bay\n\nDawn\n\nThe bay.\n\nGulls\n\nEnd"


def test_the_page_draws_designs_with_their_credits_and_asks_for_their_faces():
    post = {"id": "p1", "slug": "s", "title": "S", "format": "blocks", "layout": "standard", "access": "free",
            "content": _story({"type": "cover", "asset_id": A, "style": "overlay", "focal": {"x": 30, "y": 60},
                               "design": {"layers": [TEXT]}},
                              {"type": "photo", "asset_id": A, "design": {"layers": [PIC]}},
                              {"type": "text", "md": "Body.", "font": "Inter", "size": 1.25, "color": "#111111", "leading": 1.8},
                              {"type": "page", "aspect": "4:5", "design": {"layers": [PIC], "background": {"kind": "solid", "color": "#0e0e0e"}}})}
    html = pages.render_story({"name": "Bloom", "slug": "bloom", "theme_config": {}, "meta_config": {}}, [],
                              {"name": "Salt", "masthead_style": "classic"}, post, ASSETS, more=[], more_covers={},
                              origin="https://x.test")
    assert '<div class="mz-cover__scrim"></div><div class="mzd" style="--ar:1.3333;--fx:0.3;--fy:0.6">' in html
    assert "Over the bay" in html and html.count("Photo: Bo") == 2  # the gull's credit, under the photo and the page
    assert 'style="font-family:&#x27;Inter&#x27;, system-ui, -apple-system, &#x27;Segoe UI&#x27;, sans-serif;font-size:1.25em;color:#111111;line-height:1.8"' in html
    assert '<section class="mz-page"><div class="mz-page__art" style="--ar:0.8;background:#0e0e0e">' in html
    assert "family=Lora:ital,wght@0,400;0,700&amp;display=swap" in html and "family=Inter:" in html
    assert 'data-mzd' not in html and 'data-mz-f="' not in html  # nothing of the editor's for readers


def test_the_editor_marks_each_layer_and_opens_its_words_exactly():
    blocks = _story({"type": "photo", "asset_id": A, "design": {"layers": [TEXT, PIC]}},
                    {"type": "photos", "items": [{"asset_id": A}, {"asset_id": A, "design": {"layers": [{**TEXT, "id": "cap"}]}}]})["blocks"]
    html = story_render.render_blocks(blocks, ASSETS, edit=True)
    assert 'data-mzd="design"' in html and 'data-mzd="items.0.design"' in html  # every picture can take layers
    assert 'data-mzd-l="head"' in html and 'data-mzd-l="gull"' in html
    assert 'data-mz-f="design.head" data-mz-k="rich" data-mz-lazy' in html
    assert 'data-mz-f="items.1.design.cap"' in html
    registry = json.loads(re.search(r"data-mz-rt>(.*?)</script>", pages.rich_registry(blocks)).group(1))
    assert registry["0|design.head"] == doc("Over the bay") and registry["1|items.1.design.cap"] == doc("Over the bay")


def test_a_photo_saved_before_designs_reads_with_its_words_as_layers():
    old = {"type": "photo", "asset_id": A, "overlays": [{"x": 50, "y": 50, "text": "Dawn", "size": "l", "tone": "light"}]}
    (b,) = story_schema.with_designs([old])
    assert "overlays" not in b and b["design"]["layers"][0]["rt"] == doc("Dawn")
    assert story_schema.with_designs([{"type": "photo", "overlays": "junk"}])[0]["design"] is None
    post = {"format": "blocks", "content": {"blocks": [old]}}
    assert pages.story_blocks(post)[0]["design"]["layers"][0]["kind"] == "text"
