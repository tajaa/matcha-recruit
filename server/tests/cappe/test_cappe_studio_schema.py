"""A paged story's document (services/magazine/studio/schema.py).

What each block pins:

  * the document is reshaped, not trusted: numbers clamped and rounded as the
    client rounds, colours hex, faces from the catalog (an italic only where
    the face has one), ids named, pictures by library id, unknown keys gone,
    and attributes stored only when they aren't their defaults;
  * structure the owner has to fix is refused with a message: an unknown
    kind of frame, a frame on no page, text flowing into a shape or two texts
    in one frame, too many pages, too much text;
  * a composition is kept only while it is one of this text: lines in order,
    leaving out only the spaces and line breaks they break at, never half a
    character, each frame after the last; overset is allowed;
  * spreads, the first locked page of a paid story, and where uncomposed
    text flows (never onto a free page when it reaches a locked one).

Run from server/:  ./venv/bin/python -m pytest tests/cappe/test_cappe_studio_schema.py -q
"""
import json

import pytest

from app.cappe.services.magazine.studio import limits as L
from app.cappe.services.magazine.studio import schema as S


def _doc(**over):
    base = {
        "pages": [{"id": "p1"}, {"id": "p2"}, {"id": "p3"}],
        "items": [
            {"id": "t1", "kind": "text", "page": "p1", "x": 54, "y": 54, "w": 240, "h": 600},
            {"id": "t2", "kind": "text", "page": "p2", "x": 54, "y": 54, "w": 240, "h": 600},
        ],
        "threads": [{"id": "s1", "frames": ["t1", "t2"], "paras": [{"runs": [{"t": "Hello world"}]}]}],
    }
    return {**base, **over}


def test_a_new_story_starts_with_two_threaded_pages():
    doc = S.starter_doc()
    assert [p["id"] for p in doc["pages"]] == ["p1", "p2"]
    assert doc["threads"][0]["frames"] == ["t1", "t2"]
    assert doc["items"][0]["cols"] == 3 and doc["facing"] is True
    assert S.normalize_doc(json.loads(json.dumps(doc))) == doc  # stable


def test_numbers_are_clamped_and_rounded_like_the_client():
    doc = S.normalize_doc(_doc(size={"w": 5, "h": 99999}, bleed=-3))
    assert doc["size"] == {"w": L.PAGE_MIN, "h": L.PAGE_MAX}
    assert doc["bleed"] == 0
    assert S.num(1.006, 0, 10, 0) == 1.01 and S.num(1.005, 0, 10, 0) == 1  # as JavaScript rounds it; and S.num(2.5, 0, 10, 0) == 2.5
    assert S.num(-0.001, -1, 1, 0) == 0 and str(S.num(-0.001, -1, 1, 0)) == "0"
    assert S.num(float("nan"), 0, 1, 7) == 7 and S.num(True, 0, 9, 3) == 3 and S.num("x", 0, 9, 3) == 3
    assert isinstance(S.num(12.0, 0, 99, 0), int)


def test_items_are_reshaped():
    raw = _doc(items=[
        {"id": "t1", "kind": "text", "page": "p1", "x": 1.234, "y": 2, "w": 3, "h": 4, "rot": 400, "cols": 40,
         "fill": "#ABCDEF", "stroke": {"c": "red", "w": 2}, "evil": "<script>"},
        {"id": "i1", "kind": "image", "page": "p2", "asset_id": "8d7d2b1e-4d5e-4d0a-9d73-1b2c3d4e5f60", "fit": "zoom",
         "zoom": 5000, "caption": "Low tide\x00"},
        {"id": "l1", "kind": "line", "page": "p3", "w": 100, "h": 0},
        {"id": "e1", "kind": "ellipse", "page": "p3", "stroke": {"c": "#000000", "w": 0}},
    ], threads=[])
    text, image, line, ellipse = S.normalize_doc(raw)["items"]
    assert text["x"] == 1.23 and text["rot"] == 180 and text["cols"] == 12 and "evil" not in text
    assert text["fill"] == "#abcdef" and text["stroke"] == {"c": "#1a1a1a", "w": 2}
    assert image["fit"] == "fill" and image["zoom"] == L.ZOOM_MAX and image["caption"] == "Low tide"
    assert line["stroke"] == {"c": "#1a1a1a", "w": 1}  # a line always has one
    assert ellipse["stroke"] is None  # no width, no stroke


@pytest.mark.parametrize("bad, message", [
    ({"kind": "video"}, "isn't a kind of frame"),
    ({"page": "nope"}, "isn't in the story"),
    ({"id": "Bad Id"}, "bad name"),
    ({"asset_id": "https://example.com/x.jpg", "kind": "image"}, "isn't from your library"),
])
def test_bad_items_are_refused(bad, message):
    item = {"id": "x1", "kind": "rect", "page": "p1", **bad}
    with pytest.raises(S.DocError, match=message):
        S.normalize_doc(_doc(items=[item], threads=[]))


@pytest.mark.parametrize("raw, message", [
    ({"pages": []}, "at least one page"),
    ({"pages": [{"id": f"p{i}"} for i in range(L.MAX_PAGES + 1)], "items": [], "threads": []}, "at most"),
    ({"pages": [{"id": "p1"}, {"id": "p1"}], "items": [], "threads": []}, "share a name"),
    ({"threads": [{"id": "s1", "frames": ["nope"], "paras": []}]}, "isn't a text frame"),
    ({"threads": [{"id": "s1", "frames": ["t1"], "paras": []}, {"id": "s2", "frames": ["t1"], "paras": []}]},
     "two stories"),
    ({"threads": [{"id": "s1", "frames": [], "paras": []}]}, "no frame"),
])
def test_bad_structure_is_refused(raw, message):
    with pytest.raises(S.DocError, match=message):
        S.normalize_doc(_doc(**raw))


def test_a_document_that_isnt_one_is_refused():
    with pytest.raises(S.DocError):
        S.normalize_doc(["pages"])


def test_text_runs_are_cleaned_merged_and_sparse():
    doc = S.normalize_doc(_doc(threads=[{"id": "s1", "frames": ["t1"], "paras": [
        {"runs": [{"t": "Tab\there\x07 ", "font": "Inter"}, {"t": "and on", "font": "Inter", "wt": 400},
                  {"t": "", "size": 99}, {"t": "!", "font": "Nope", "size": 0}],
         "align": "j", "role": "h2", "li": 9, "fi": -50, "junk": 1},
        {"runs": [{"t": "", "size": 30, "wt": 700}]},
        {"runs": [{"t": "x", "font": "Anton", "wt": 900, "it": True}]},
    ]}]))
    first, empty, anton = doc["threads"][0]["paras"]
    assert first["runs"][0] == {"t": "Tab here and on", "font": "Inter"}
    assert first["runs"][1] == {"t": "!", "size": 1}  # an unknown face is the default; size clamped
    assert first["align"] == "j" and first["role"] == "h2" and first["li"] == 9 and first["fi"] == -9
    assert "junk" not in first
    assert empty == {"runs": [{"t": "", "wt": 700, "size": 30}]}  # keeps its type for its line's height
    assert anton["runs"][0] == {"t": "x", "font": "Anton"}  # Anton has 400 only, and no italic


def test_line_breaks_stay_and_other_controls_go():
    doc = S.normalize_doc(_doc(threads=[{"id": "s1", "frames": ["t1"], "paras": [
        {"runs": [{"t": "one\r\ntwo\rthree\x0bfour\ud800"}]}]}]))
    assert S.para_text(doc["threads"][0]["paras"][0]) == "one\ntwo\nthreefour"


def test_too_much_text_is_refused(monkeypatch):
    monkeypatch.setattr(L, "MAX_THREAD_CHARS", 10)
    with pytest.raises(S.DocError, match="too long"):
        S.normalize_doc(_doc(threads=[{"id": "s1", "frames": ["t1"], "paras": [{"runs": [{"t": "x" * 11}]}]}]))
    monkeypatch.setattr(L, "MAX_THREAD_CHARS", 100)
    monkeypatch.setattr(L, "MAX_DOC_CHARS", 15)
    with pytest.raises(S.DocError, match="too much text"):
        S.normalize_doc(_doc(threads=[{"id": "s1", "frames": ["t1"], "paras": [{"runs": [{"t": "x" * 10}]}]},
                                      {"id": "s2", "frames": ["t2"], "paras": [{"runs": [{"t": "y" * 10}]}]}]))


def test_too_big_a_document_is_refused(monkeypatch):
    monkeypatch.setattr(L, "MAX_DOC_BYTES", 500)
    with pytest.raises(S.DocError, match="too big"):
        S.normalize_doc(_doc())


def test_too_many_items_on_a_page(monkeypatch):
    monkeypatch.setattr(L, "MAX_ITEMS_PER_PAGE", 1)
    with pytest.raises(S.DocError, match="A page holds"):
        S.normalize_doc(_doc(items=[{"id": "a", "kind": "rect", "page": "p1"}, {"id": "b", "kind": "rect", "page": "p1"}],
                             threads=[]))


def test_guides_keep_to_their_pages():
    doc = S.normalize_doc(_doc(guides=[{"id": "g1", "page": "p1", "axis": "h", "at": 100.567},
                                       {"id": "g2", "page": "gone", "axis": "v", "at": 3}, "x"]))
    assert doc["guides"] == [{"id": "g1", "page": "p1", "axis": "h", "at": 100.57}]


def test_the_paywall_page_is_never_the_first():
    assert S.normalize_doc(_doc(paywall_page=1))["paywall_page"] == 2
    assert S.normalize_doc(_doc(paywall_page=99))["paywall_page"] == 3
    assert S.normalize_doc(_doc(paywall_page=None))["paywall_page"] is None
    one = _doc(pages=[{"id": "p1"}], items=[], threads=[], paywall_page=2)
    assert S.normalize_doc(one)["paywall_page"] is None


# ── compositions ─────────────────────────────────────────────────────────────

PARAS = [{"runs": [{"t": "One two three"}]}, {"runs": [{"t": "Four 😀 five"}]}]


def _comp(*lines):
    return {"lines": [list(ln) for ln in lines]}


def test_a_good_composition_is_kept_and_rounded():
    comp = _comp((0, 0, 0, 7, 0, 12.345, 100, 0), (0, 0, 8, 13, 0, 24, 100, 3), (1, 1, 0, 12, 0, 12, 100, 2))
    assert S.valid_comp(comp, PARAS, 2) == {"lines": [[0, 0, 0, 7, 0, 12.35, 100, 0], [0, 0, 8, 13, 0, 24, 100, 3],
                                                       [1, 1, 0, 12, 0, 12, 100, 2]]}


def test_an_overset_composition_is_kept():
    comp = _comp((0, 0, 0, 7, 0, 12, 100, 0))
    assert S.valid_comp(comp, PARAS, 1) is not None


@pytest.mark.parametrize("lines", [
    [(0, 0, 0, 5, 0, 12, 100, 0), (0, 0, 8, 13, 0, 24, 100, 0)],  # skips "wo " — words left out
    [(0, 0, 2, 13, 0, 12, 100, 0)],  # a paragraph's first line starts at 0
    [(0, 0, 0, 13, 0, 12, 100, 0), (0, 0, 0, 13, 0, 12, 100, 0)],  # back over the same text
    [(0, 0, 0, 13, 0, 12, 100, 0), (0, 1, 0, 6, 0, 24, 100, 0)],  # half of the emoji
    [(1, 0, 0, 13, 0, 12, 100, 0), (0, 1, 0, 13, 0, 24, 100, 0)],  # back to an earlier frame
    [(2, 0, 0, 13, 0, 12, 100, 0)],  # no such frame
    [(0, 1, 0, 13, 0, 12, 100, 0)],  # starts in the second paragraph
    [(0, 0, 0, 7, 0, 12, 100, 0), (0, 2, 0, 1, 0, 12, 100, 0)],  # skips a paragraph
    [(0, 0, 0, 99, 0, 12, 100, 0)],  # past the end
    [(0, 0, 0, 13, 0, 12, 100, 9)],  # no such alignment
    [(0, 0, 0, 13, 0, float("inf"), 100, 0)],
    [(0, 0, 0, 13, 0, True, 100, 0)],
    [(0, 0, 0, 13, 0, 12, 100)],
    ["line"],
])
def test_a_composition_that_isnt_of_this_text_is_dropped(lines):
    assert S.valid_comp({"lines": [list(ln) if isinstance(ln, tuple) else ln for ln in lines]}, PARAS, 2) is None


def test_a_composition_needs_lines_and_text():
    assert S.valid_comp(None, PARAS, 1) is None
    assert S.valid_comp({"lines": [[0, 0, 0, 0, 0, 0, 0, 0]]}, [], 1) is None
    assert S.valid_comp({"lines": []}, [], 1) == {"lines": []}


def test_a_dropped_composition_isnt_stored():
    raw = _doc()
    raw["threads"][0]["comp"] = _comp((0, 0, 0, 3, 0, 12, 100, 0), (0, 0, 9, 11, 0, 24, 100, 0))
    assert "comp" not in S.normalize_doc(raw)["threads"][0]
    raw["threads"][0]["comp"] = _comp((0, 0, 0, 5, 0, 12, 100, 0), (1, 0, 6, 11, 0, 12, 100, 0))
    assert S.normalize_doc(raw)["threads"][0]["comp"]["lines"][1][0] == 1


def test_overset():
    thread = {"paras": PARAS, "comp": _comp((0, 0, 0, 13, 0, 12, 100, 0))}
    assert S.overset(thread)
    thread["comp"] = _comp((0, 0, 0, 13, 0, 12, 100, 0), (0, 1, 0, 12, 0, 24, 100, 0))
    assert not S.overset(thread)
    thread["comp"] = _comp((0, 0, 0, 13, 0, 12, 100, 0), (0, 1, 0, 6, 0, 24, 100, 0))
    assert S.overset(thread)
    assert S.overset({"paras": PARAS}) and not S.overset({"paras": []})
    assert not S.overset({"paras": [{"runs": [{"t": ""}]}]})


def test_utf16_offsets_are_the_browsers():
    assert S.len16("a😀b") == 4
    assert S.slice16("a😀b", 1, 3) == "😀"
    assert S.slice16("a😀b", 1, 2) is None


# ── spreads and paywalls ─────────────────────────────────────────────────────

def test_spreads():
    assert S.spreads({"pages": [1, 2, 3, 4], "facing": True}) == [[0], [1, 2], [3]]
    assert S.spreads({"pages": [1, 2, 3], "facing": True}) == [[0], [1, 2]]
    assert S.spreads({"pages": [1, 2], "facing": False}) == [[0], [1]]
    assert S.spreads({"pages": [], "facing": True}) == []
    assert S.page_side({"facing": True}, 1) == "left" and S.page_side({"facing": True}, 2) == "right"
    assert S.page_side({"facing": False}, 1) == "right"


def test_the_first_locked_page():
    doc = S.normalize_doc(_doc())
    assert S.paywall_from({"access": "free", "content": {"doc": doc}}) is None
    assert S.paywall_from({"access": "paid", "content": {"doc": doc}}) == 2
    assert S.paywall_from({"access": "paid", "content": {"doc": {**doc, "paywall_page": 3}}}) == 3
    single = {**doc, "pages": doc["pages"][:1]}
    assert S.paywall_from({"access": "paid", "content": {"doc": single}}) is None


def test_uncomposed_text_never_flows_onto_a_free_page_past_the_wall():
    doc = S.normalize_doc(_doc())
    thread = doc["threads"][0]
    assert S.flow_frame(doc, thread) == 0
    assert S.flow_frame(doc, thread, 2) == 1  # its second frame is on page 2, the first locked
    assert S.flow_frame(doc, thread, 3) == 0  # no frame on a locked page


def test_asset_ids():
    raw = _doc(items=[{"id": "i1", "kind": "image", "page": "p1", "asset_id": "8d7d2b1e-4d5e-4d0a-9d73-1b2c3d4e5f60"},
                      {"id": "i2", "kind": "image", "page": "p1"}], threads=[])
    assert S.doc_asset_ids(S.normalize_doc(raw)) == {"8d7d2b1e-4d5e-4d0a-9d73-1b2c3d4e5f60"}
    assert S.doc_asset_ids(None) == set()
