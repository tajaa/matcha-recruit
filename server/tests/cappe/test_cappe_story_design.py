"""How a story's text and photos are designed: type, alignment and columns for
text; border, shape, colour and crop for a photo, and the words set on it.

What each block pins:

  * the normalizer keeps only known choices, bounds a crop inside the picture
    (a crop of the whole picture is none), and turns words set on a photo
    before designs (`overlays`) into its design's text layers;
  * the page draws the crop by scaling the picture inside a frame of the crop's
    shape, escapes every word set on a picture, and says "(cropped)" in a
    CC BY credit when the picture was cut;
  * words on a picture are part of the story's text, and go under the picture
    in an issue email, which can't lay them over it.

Run from server/:  ./venv/bin/python -m pytest tests/cappe/test_cappe_story_design.py -q
"""
from uuid import uuid4

import pytest

from app.cappe.services.magazine import issue_email, story_render, story_schema
from app.cappe.services.magazine.stories import story_text

A = str(uuid4())
ASSET = {"id": A, "url": "https://cdn.example.test/a.jpg", "alt": "Tower", "width": 2000, "height": 1000,
         "credit_line": "“Tower” by Ana / CC BY 2.0", "license": "by", "variants": {}}


def _photo(**over):
    return story_schema.normalize_story({"blocks": [{"type": "photo", "asset_id": A, **over}]})["blocks"][0]


def test_text_keeps_known_choices_only():
    t = story_schema.normalize_story({"blocks": [
        {"type": "text", "md": "x", "columns": 3, "variant": "lede", "align": "justify"},
        {"type": "text", "md": "x", "columns": 5, "variant": "huge", "align": "diagonal"},
    ]})["blocks"]
    assert (t[0]["columns"], t[0]["variant"], t[0]["align"]) == (3, "lede", "justify")
    assert (t[1]["columns"], t[1]["variant"], t[1]["align"]) == (1, "body", "left")


def test_a_photo_keeps_known_choices_and_a_crop_inside_the_picture():
    p = _photo(border="mat", shape="arch", filter="bw", crop={"x": 90, "y": "10", "w": 30, "h": 2})
    assert (p["border"], p["shape"], p["filter"]) == ("mat", "arch", "bw")
    assert p["crop"] == {"x": 70, "y": 10, "w": 30, "h": 5}  # pulled inside, at least 5%
    odd = _photo(border="neon", shape="star", filter="vhs", crop={"x": 0, "y": 0, "w": 100, "h": 100})
    assert (odd["border"], odd["shape"], odd["filter"], odd["crop"]) == ("none", "rect", "none", None)
    assert _photo(crop="half")["crop"] is None and _photo()["design"] is None and "overlays" not in _photo()


def test_words_set_on_a_photo_before_designs_become_its_text_layers():
    p = _photo(overlays=[{"x": 120, "y": -3, "text": "  Dawn  ", "size": "xl", "tone": "dark", "box": 1, "align": "left"},
                         {"text": "x" * 400, "size": "giant"}, "nope", {"text": "   "}])
    dawn, long = p["design"]["layers"]
    assert (dawn["kind"], dawn["name"], dawn["color"], dawn["align"], dawn["size"]) == ("text", "Dawn", "#111111", "left", 9)
    assert dawn["fill"] == {"kind": "solid", "color": "#ffffffd9", "angle": 180, "stops": []} and dawn["shadows"] == []
    assert dawn["x"] + dawn["w"] <= 100 and dawn["y"] == 0  # kept on the picture
    assert dawn["rt"]["content"][0]["content"][0]["text"] == "Dawn"
    assert len(long["rt"]["content"][0]["content"][0]["text"]) == 300 and long["size"] == 3.8
    assert long["color"] == "#ffffff" and long["shadows"][0]["color"] == "#0000008c"  # light words, shadowed
    assert "overlays" not in p
    # A design sent with them wins: the overlays are what it replaced.
    kept = _photo(design={"layers": []}, overlays=[{"text": "old"}])
    assert kept["design"] is None
    with pytest.raises(story_schema.StoryError, match="at most 8"):
        _photo(overlays=[{"text": "x"}] * 9)


def test_the_page_draws_the_crop_and_the_words():
    p = _photo(crop={"x": 25, "y": 0, "w": 50, "h": 100}, border="thick", filter="sepia",
               overlays=[{"x": 30, "y": 70, "text": "<b>Dawn</b>\nover the bay", "size": "l", "box": True},
                         {"text": "   "}])
    html = story_render.photo_html(p, ASSET)
    assert 'class="mz-fig mz-fig--column mz-border--thick mz-shape--rect mz-filter--sepia"' in html
    assert 'style="aspect-ratio:100000/100000"' in html  # 2000×50% by 1000×100%
    assert "width:200.000%;height:100.000%;left:-50.000%;top:0.000%" in html
    assert html.count('class="mzd__l mzd__l--text') == 1  # an empty one draws nothing
    assert "<p>&lt;b&gt;Dawn&lt;/b&gt;</p><p>over the bay</p>" in html and "<b>Dawn" not in html
    assert "CC BY 2.0 (cropped)" in html


def test_a_circle_ignores_the_crop_and_still_says_cropped():
    html = story_render.photo_html(_photo(shape="circle", crop={"x": 10, "y": 10, "w": 50, "h": 50}), ASSET)
    assert "aspect-ratio" not in html and "position:absolute" not in html and "(cropped)" in html
    plain = story_render.photo_html(_photo(), ASSET)
    assert "(cropped)" not in plain and "mz-border--none mz-shape--rect mz-filter--none" in plain
    assert story_render.photo_html(_photo(), None) == ""
    assert story_render.photo_html(_photo(), {**ASSET, "url": "javascript:alert(1)"}) == ""


def test_text_classes():
    blocks = story_schema.normalize_story({"blocks": [
        {"type": "text", "md": "One", "dropcap": True, "columns": 3, "variant": "statement", "align": "center"},
        {"type": "text", "md": "Two", "columns": 2},
    ]})["blocks"]
    html = story_render.render_blocks(blocks, {})
    assert 'class="mz-text mz-measure mz-text--statement mz-align--center mz-dropcap mz-text--cols mz-text--cols3"' in html
    assert 'class="mz-text mz-measure mz-text--body mz-align--left mz-text--cols"' in html


def test_words_on_a_photo_are_story_text_and_go_under_it_in_email():
    p = _photo(caption="The bay.", overlays=[{"text": "Dawn"}, {"text": " "}, {"text": "6 a.m."}])
    assert story_text({"blocks": [p]}) == "Dawn\n\n6 a.m.\n\nThe bay."
    row = issue_email._block(p, {A: {**ASSET, "variants": {}}})
    assert "Dawn · 6 a.m. — The bay." in row
