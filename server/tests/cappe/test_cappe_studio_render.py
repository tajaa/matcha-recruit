"""A paged story's pages and Text view (services/magazine/studio/render.py,
text_view.py) and its paywall.

What each block pins:

  * each composed line is printed as Stage 0 proved it must be: a box of
    its aligned width placed by its bottom edge on the baseline, aligned by
    the browser (justified: `lyt-l--j`), the break spaces after it in a
    sizeless `.lyt-sp`, a span per run in the face the Studio measured
    (`f-<sha>`), and paragraphs as `<p>`s;
  * everything typed is escaped; pictures print their library credit; shapes,
    lines, strokes, rotation and opacity; hidden items aren't printed;
  * a thread with no composition is flowed into one frame;
  * the Text view reads pages in order, top down: the cover picture, headings,
    quotes, photos, a thread continued where it continues, never overset text;
  * a paid story leaks nothing past its wall: not in its pages' HTML (locked
    pages are empty), not in the Text view's free part, not through flowed
    text, not in the feed's blocks; a subscriber's `/paid` gets the pages.

Run from server/:  ./venv/bin/python -m pytest tests/cappe/test_cappe_studio_render.py -q
"""
import re

import pytest

from app.cappe.services.magazine import pages as mag_pages
from app.cappe.services.magazine.story_render import split_at_paywall
from app.cappe.services.magazine.studio import fonts as faces
from app.cappe.services.magazine.studio import render as R
from app.cappe.services.magazine.studio import schema as S
from app.cappe.services.magazine.studio import text_view as T

ASSET = "8d7d2b1e-4d5e-4d0a-9d73-1b2c3d4e5f60"
ASSET_ROW = {"id": ASSET, "url": "https://cdn.example.test/a.jpg", "alt": "Boats", "credit_line": "Photo: Ana Ruiz",
             "license": "own", "ai_generated": False, "source_url": None, "width": 1600, "height": 1000,
             "variants": {"webp": [{"w": 480, "url": "https://cdn.example.test/a-480.webp"}]}}
SHA = "a" * 64
SENTINEL = "ZXQsubscribersZXQ"


@pytest.fixture(autouse=True)
def one_face(monkeypatch):
    """The Studio's own face for Source Serif 4 regular; others by name."""
    monkeypatch.setattr(faces, "face", lambda fam, wt, it: {"sha": SHA} if (fam, wt, it) == (
        "Source Serif 4", 400, False) else None)


def _doc(paras, comp=None, **over):
    thread = {"id": "s1", "frames": ["t1", "t2"], "paras": paras}
    if comp is not None:
        thread["comp"] = {"lines": comp}
    raw = {
        "pages": [{"id": "p1"}, {"id": "p2"}, {"id": "p3"}],
        "items": [
            {"id": "t1", "kind": "text", "page": "p1", "x": 54, "y": 54, "w": 240, "h": 600},
            {"id": "t2", "kind": "text", "page": "p2", "x": 54, "y": 54, "w": 240, "h": 600},
        ],
        "threads": [thread],
        **over,
    }
    return S.normalize_doc(raw)


def test_numbers_print_as_javascript_prints_them():
    assert [R.n(v) for v in (12, 12.0, 0.5, 1.005, 2.675, -0.0, 1234.5678)] == \
        ["12", "12", "0.5", "1", "2.68", "0", "1234.57"]
    assert R.u(3) == "calc(3 * var(--u))"


def test_a_composed_line_is_placed_by_its_baseline_and_aligned_in_its_box():
    doc = _doc([{"runs": [{"t": "Low tide at "}, {"t": "dawn", "font": "Inter", "wt": 700}, {"t": " and boats"}]}],
               comp=[[0, 0, 0, 16, 0, 20, 240, 3], [0, 0, 17, 26, 0, 34, 240, 0]])
    html, used = R.pages_html(doc, {})
    assert ('<p class="lyt-p"><span class="lyt-l lyt-l--j" style="left:calc(0 * var(--u));'
            'bottom:calc(580 * var(--u));width:calc(240 * var(--u))">') in html
    assert f"<span style=\"font-family:'f-{SHA[:16]}';font-size:calc(10.5 * var(--u))\">Low tide at </span>" in html
    assert "font-family:'Inter', system-ui" in html and ";font-weight:700" in html  # not built: by name
    assert used == {"Inter": {(700, False)}}
    assert '</span><span class="lyt-sp"> </span><span class="lyt-l"' in html  # the space it broke at
    assert html.count('<p class="lyt-p">') == 1


def test_a_paragraph_is_split_where_it_crosses_frames():
    doc = _doc([{"runs": [{"t": "One two"}]}], comp=[[0, 0, 0, 3, 0, 20, 240, 2], [1, 0, 4, 7, 0, 20, 240, 1]])
    html, _ = R.pages_html(doc, {})
    assert html.count('<p class="lyt-p">') == 2
    assert "lyt-l lyt-l--r" in html and "lyt-l lyt-l--c" in html
    assert 'One</span></span><span class="lyt-sp"> </span></p>' in html  # its space ends the frame's part


def test_typed_text_is_escaped():
    doc = _doc([{"runs": [{"t": "<script>alert(1)</script> & \"q\""}]}],
               comp=[[0, 0, 0, 35, 0, 20, 240, 0]])
    html, _ = R.pages_html(doc, {})
    assert "<script>" not in html and "&lt;script&gt;alert(1)&lt;/script&gt; &amp; \"q\"" in html


def test_run_styles():
    used: dict = {}
    style = R.run_style({"track": 50, "size": 20, "color": "#ff0000", "u": True}, used)
    assert "letter-spacing:calc(1 * var(--u))" in style and "color:#ff0000" in style
    assert "text-decoration:underline" in style
    italic = R.run_style({"font": "Lora", "it": True}, used)
    assert "font-style:italic" in italic and used == {"Lora": {(400, True)}}


def test_without_a_composition_text_flows_into_its_first_frame():
    doc = _doc([{"runs": [{"t": "Flowing words"}], "align": "c", "li": 6, "sb": 4, "lead": 14}])
    doc["items"][0]["cols"] = 2
    html, _ = R.pages_html(doc, {})
    assert html.count("Flowing words") == 1
    assert '<div class="lyt-flow" style="padding:calc(0 * var(--u));column-count:2;column-gap:calc(12 * var(--u))">' in html
    assert ('<p style="text-align:center;padding-left:calc(6 * var(--u));margin-top:calc(4 * var(--u));'
            'line-height:calc(14 * var(--u))">') in html


def test_pictures_shapes_and_lines():
    doc = S.normalize_doc({
        "pages": [{"id": "p1"}],
        "items": [
            {"id": "i1", "kind": "image", "page": "p1", "x": 0, "y": 0, "w": 306, "h": 200, "asset_id": ASSET,
             "fit": "fit", "fx": 30, "zoom": 150, "radius": 8, "stroke": {"c": "#000000", "w": 2}, "rot": 5},
            {"id": "i2", "kind": "image", "page": "p1", "w": 10, "h": 10},
            {"id": "r1", "kind": "rect", "page": "p1", "w": 10, "h": 10, "fill": "#ff0000", "opacity": 50},
            {"id": "e1", "kind": "ellipse", "page": "p1", "w": 10, "h": 10},
            {"id": "l1", "kind": "line", "page": "p1", "x": 10, "y": 10, "w": 100, "h": 0,
             "stroke": {"c": "#00ff00", "w": 4}, "flip": True},
            {"id": "h1", "kind": "rect", "page": "p1", "w": 10, "h": 10, "hidden": True, "fill": "#123456"},
        ],
        "threads": [],
    })
    html, _ = R.pages_html(doc, {ASSET: ASSET_ROW})
    assert 'src="https://cdn.example.test/a.jpg"' in html and 'alt="Boats"' in html
    assert 'sizes="(min-width: 700px) 25vw, 50vw"' in html and 'fetchpriority="high"' in html
    assert "object-fit:contain;object-position:30% 50%;transform:scale(1.5);transform-origin:30% 50%" in html
    assert '<figcaption class="lyt-credit"><span class="mz-credit">Photo: Ana Ruiz</span></figcaption>' in html
    assert "transform:rotate(5deg)" in html and "border-radius:calc(8 * var(--u))" in html
    assert 'box-shadow:inset 0 0 0 calc(2 * var(--u)) #000000' in html
    assert '<figure class="lyt-item lyt-img" style="left:calc(0 * var(--u));top:calc(0 * var(--u));width:calc(10 * var(--u));height:calc(10 * var(--u))"></figure>' in html
    assert "background:#ff0000;opacity" not in html and "opacity:0.5" in html
    assert "border-radius:50%" in html
    assert ('viewBox="-2 -2 104 4"' in html and '<line x1="0" y1="0" x2="100" y2="0" stroke="#00ff00" '
            'stroke-width="4"/>' in html)
    assert "#123456" not in html


def test_spreads_and_paper():
    doc = _doc([{"runs": [{"t": "x"}]}])
    html, _ = R.pages_html(doc, {})
    assert html.startswith('<div class="lyt" data-lyt style="--pw:612;--ph:792;--sw:1224;--paper:#ffffff">')
    assert html.count('class="lyt-slot"') == 2  # page 1 alone, then 2–3
    assert '<div class="lyt-paper" data-lyt-n="3" style="left:calc(612 * var(--u));width:calc(612 * var(--u))">' in html
    single = S.normalize_doc({**doc, "facing": False})
    assert "--sw:612" in R.pages_html(single, {})[0]


def test_faces_css_names_only_the_studios_faces():
    doc = _doc([{"runs": [{"t": "a"}, {"t": "b", "font": "Inter"}]}])
    css = R.faces_css(doc)
    assert css == (f"@font-face{{font-family:'f-{SHA[:16]}';src:url(/api/cappe/public/fonts/{SHA}.ttf) "
                   "format('truetype');font-display:block}")


def test_the_layout_css_is_the_studios():
    assert ".lyt-l{position:absolute" in R.CSS and ".lyt-l--j{text-align:justify;text-align-last:justify" in R.CSS


# ── the Text view ────────────────────────────────────────────────────────────

def test_the_text_view_reads_the_pages_in_order():
    doc = S.normalize_doc({
        "pages": [{"id": "p1"}, {"id": "p2"}],
        "items": [
            {"id": "big", "kind": "image", "page": "p1", "x": 0, "y": 0, "w": 600, "h": 400, "asset_id": ASSET},
            {"id": "t1", "kind": "text", "page": "p1", "x": 54, "y": 420, "w": 240, "h": 300},
            {"id": "pic", "kind": "image", "page": "p2", "x": 0, "y": 0, "w": 100, "h": 80,
             "asset_id": "11111111-1111-4111-8111-111111111111", "caption": "The pier"},
            {"id": "t2", "kind": "text", "page": "p2", "x": 54, "y": 200, "w": 240, "h": 300},
        ],
        "threads": [{"id": "s1", "frames": ["t1", "t2"], "paras": [
            {"runs": [{"t": "Gem of the Bay", "wt": 700, "size": 30}], "role": "h1"},
            {"runs": [{"t": "Low tide."}, {"t": " Bold", "wt": 700}, {"t": " slant", "it": True}]},
            {"runs": [{"t": "Every bell rings."}], "role": "quote"},
            {"runs": [{"t": "Second page words.\nNew line"}]},
        ], "comp": {"lines": [[0, 0, 0, 14, 0, 30, 240, 0], [0, 1, 0, 20, 0, 50, 240, 0],
                              [0, 2, 0, 17, 0, 70, 240, 0], [1, 3, 0, 18, 0, 20, 240, 0],
                              [1, 3, 19, 27, 0, 34, 240, 0]]}}],
    })
    blocks = T.text_blocks(doc)
    assert [b["type"] for b in blocks] == ["cover", "text", "quote", "photo", "text"]
    assert blocks[0]["asset_id"] == ASSET
    assert blocks[1]["md"] == "## Gem of the Bay\n\nLow tide. **Bold** *slant*"
    assert blocks[1]["rt"]["content"][0]["type"] == "heading"
    assert blocks[2]["text"] == "Every bell rings."
    assert blocks[3]["caption"] == "The pier" and blocks[3]["size"] == "column"
    assert blocks[4]["rt"]["content"][0]["content"][1] == {"type": "hardBreak"}


def test_a_long_pull_quote_is_read_whole():
    long = "A quotation that goes on. " * 23 + "Fin."
    short = "Every bell rings."
    doc = _doc([{"runs": [{"t": long}], "role": "quote"}, {"runs": [{"t": short}], "role": "quote"}],
               comp=[[0, 0, 0, len(long), 0, 20, 240, 0], [0, 1, 0, len(short), 0, 40, 240, 0]])
    blocks = T.text_blocks(doc)
    assert [b["type"] for b in blocks] == ["text", "quote"]
    assert blocks[0]["rt"]["content"][0]["type"] == "blockquote"
    assert blocks[0]["md"].endswith("Fin.") and len(long) > 400
    assert blocks[1]["text"] == short


def test_overset_text_isnt_read():
    doc = _doc([{"runs": [{"t": "Shown words"}]}, {"runs": [{"t": "Never set"}]}],
               comp=[[0, 0, 0, 5, 0, 20, 240, 0]])
    words = " ".join(b.get("md", "") for b in T.text_blocks(doc))
    assert "Shown" in words and "words" not in words and "Never" not in words


def test_an_empty_story_has_no_blocks():
    assert T.text_blocks(_doc([{"runs": [{"t": ""}]}])) == []
    assert T.text_blocks({}) == []


def test_the_text_view_keeps_a_drop_cap_and_reads_the_subject_in_front_once():
    doc = _doc([{"runs": [{"t": "Once upon a time"}], "dc": 3}, {"runs": [{"t": "Then"}]}],
               comp=[[0, 0, 0, 16, 0, 20, 240, 0], [0, 1, 0, 4, 0, 40, 240, 0]])
    photo = {**doc["items"][0], "id": "i8", "kind": "image", "asset_id": ASSET, "fit": "fill", "fx": 50, "fy": 50,
             "zoom": 100, "radius": 0, "caption": "", "link": "lk1", "page": "p2", "y": 700}
    doc["items"] += [photo, {**photo, "id": "i9", "cutout": True}]
    blocks = T.text_blocks(doc)
    assert [b["type"] for b in blocks] == ["text", "photo"]
    assert blocks[0]["dropcap"] is True
    plain = T.text_blocks(_doc([{"runs": [{"t": "Plain"}]}], comp=[[0, 0, 0, 5, 0, 20, 240, 0]]))
    assert plain[0]["dropcap"] is False


# ── paid stories leak nothing ───────────────────────────────────────────────

def _paid():
    """Free words on page 1; the sentinel starts mid-paragraph on page 2 (the
    first locked page), and a picture sits on page 3."""
    paras = [{"runs": [{"t": "Free words then " + SENTINEL}]}, {"runs": [{"t": "More " + SENTINEL}]}]
    doc = _doc(paras, comp=[[0, 0, 0, 16, 0, 20, 240, 0], [1, 0, 16, 33, 0, 20, 240, 0],
                            [1, 1, 0, 22, 0, 34, 240, 0]])
    doc["items"].append({**doc["items"][0], "id": "i9", "kind": "image", "page": "p3", "asset_id": ASSET,
                         "fit": "fill", "fx": 50, "fy": 50, "zoom": 100, "radius": 0, "caption": SENTINEL})
    return {"access": "paid", "format": "pages", "content": {"doc": doc}}


def test_locked_pages_are_empty_in_the_pages_html():
    post = _paid()
    html, _ = R.pages_html(post["content"]["doc"], {ASSET: ASSET_ROW}, locked_from=S.paywall_from(post))
    assert SENTINEL not in html and "Free words" in html
    assert '<div class="lyt-page lyt-page--locked" data-lyt-lock="2"' in html and 'data-lyt-lock="3"' in html
    assert "a.jpg" not in html


def test_the_text_views_free_part_stops_at_the_wall():
    post = _paid()
    blocks = mag_pages.story_blocks(post)
    free, rest = split_at_paywall(blocks, preview_blocks=3)
    assert SENTINEL not in str(free) and "Free words" in str(free)
    assert SENTINEL in str(rest)
    assert [b["type"] for b in free] == ["text"]


def test_uncomposed_text_never_shows_on_a_free_page_of_a_paid_story():
    post = _paid()
    del post["content"]["doc"]["threads"][0]["comp"]
    html, _ = R.pages_html(post["content"]["doc"], {}, locked_from=2)
    assert SENTINEL not in html and "Free words" not in html
    free, _rest = split_at_paywall(mag_pages.story_blocks(post), preview_blocks=3)
    assert SENTINEL not in str(free)


def test_a_subscriber_gets_the_locked_pages():
    post = _paid()
    pages = R.locked_pages(post["content"]["doc"], {ASSET: ASSET_ROW}, 2)
    assert [p["n"] for p in pages] == [2, 3]
    assert SENTINEL in pages[0]["html"] and "a.jpg" in pages[1]["html"]


def test_the_reader_page_of_a_paid_story(monkeypatch):
    post = {**_paid(), "id": "x", "slug": "tide", "title": "Tide <b>", "kicker": "Coast", "excerpt": "Dek",
            "byline": "Ana", "topic": None, "published_at": None, "updated_at": None, "layout": "standard",
            "reading_minutes": 3}
    site = {"slug": "bloom", "name": "Bloom", "theme_config": {}, "meta_config": {}}
    mag = {"name": "Salt", "masthead_style": "classic", "paid_enabled": True, "price_cents": 500}
    monkeypatch.setattr(mag_pages, "_page", lambda site, nav, mag, body, **kw: kw["extra_head"] + body)
    html = mag_pages.render_story(site, [], mag, post, {ASSET: ASSET_ROW}, more=[], more_covers={}, origin="https://x.test",
                                  currency="USD")
    assert SENTINEL not in html
    assert '<h1 class="lyt-title">Tide &lt;b&gt;</h1>' in html and 'href="/stories/tide/text"' in html
    assert "data-mz-pages" in html and '"cssSelector":".lyt-page--locked"' in html.replace(" ", "")
    assert "@font-face" in html and ".lyt-l{" in html and "data-lyt-prev" in html
    text = mag_pages.render_story(site, [], mag, post, {ASSET: ASSET_ROW}, more=[], more_covers={},
                                  origin="https://x.test", currency="USD", text_view=True)
    assert SENTINEL not in text and "See it as designed" in text and "Free words" in text


def test_the_page_turner_script_is_inlined():
    assert "data-lyt-strip" in mag_pages._PAGES_JS and re.search(r"ArrowRight", mag_pages._PAGES_JS)
