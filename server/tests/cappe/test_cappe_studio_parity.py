"""The Studio draws exactly what readers get (services/magazine/studio/
render.py ↔ client/src/cappe/studio/render/layoutRender.ts).

`fixtures/studio_render_cases.json` is this renderer's output for a set of
documents covering every way a page is drawn; the client's test renders the
same documents and must produce the same bytes. This test checks the fixture
is this renderer's current output, so a change on one side fails until the
other matches and the fixture is written again:

    STUDIO_FIXTURES=write ./venv/bin/python -m pytest tests/cappe/test_cappe_studio_parity.py -q

It also holds the two copies of layout.css and the limits mirror equal.

Run from server/:  ./venv/bin/python -m pytest tests/cappe/test_cappe_studio_parity.py -q
"""
import json
import os
import re
from pathlib import Path

from app.cappe.services.magazine.studio import fonts as faces
from app.cappe.services.magazine.studio import graphics as G
from app.cappe.services.magazine.studio import limits as L
from app.cappe.services.magazine.studio import render as R
from app.cappe.services.magazine.studio import schema as S

ROOT = Path(__file__).resolve().parents[3]
FIXTURE = Path(__file__).parent / "fixtures" / "studio_render_cases.json"
CLIENT_CSS = ROOT / "client/src/cappe/studio/render/layout.css"
CLIENT_LIMITS = ROOT / "client/src/cappe/studio/model/limits.ts"

FACES = [{"family": "Source Serif 4", "weight": 400, "italic": False, "sha": "1" * 64},
         {"family": "Source Serif 4", "weight": 700, "italic": False, "sha": "2" * 64},
         {"family": "Inter", "weight": 400, "italic": True, "sha": "3" * 64}]
A, B, C = ("8d7d2b1e-4d5e-4d0a-9d73-1b2c3d4e5f60", "11111111-1111-4111-8111-111111111111",
           "22222222-2222-4222-8222-222222222222")
ASSETS = {
    A: {"id": A, "url": "https://cdn.example.test/a.jpg", "alt": "Boats \"at\" dawn", "credit_line": "Photo: Ana & Bo",
        "license": "by", "ai_generated": False, "source_url": "https://flickr.example.test/p/1", "width": 1600,
        "height": 1000, "variants": {"webp": [{"w": 960, "url": "https://cdn.example.test/a-960.webp"},
                                              {"w": 480, "url": "https://cdn.example.test/a-480.webp"}]}},
    B: {"id": B, "url": "https://cdn.example.test/b.png", "alt": None, "credit_line": "ignored", "ai_generated": True,
        "source_url": None, "width": 512, "height": 512, "variants": {}},
    C: {"id": C, "url": "javascript:alert(1)", "alt": "x", "credit_line": "", "ai_generated": False, "variants": {}},
}

PAGES3 = [{"id": "p1"}, {"id": "p2"}, {"id": "p3"}]


def _frame(fid, page, **over):
    return {"id": fid, "kind": "text", "page": page, "x": 54, "y": 54, "w": 240, "h": 300, **over}


def _cases() -> list[dict]:
    paras = [
        {"runs": [{"t": "Low tide at "}, {"t": "dawn", "wt": 700}, {"t": " and the boats come in", "font": "Inter",
                                                                  "it": True, "track": 40, "color": "#aa3300"}],
         "align": "j"},
        {"runs": [{"t": "Second 😀 paragraph, underlined", "u": True, "size": 14}], "align": "c"},
        {"runs": [{"t": "Right & <b>escaped</b> \"text\"", "font": "Lora", "wt": 700}], "align": "r"},
    ]
    t1 = len("Low tide at dawn and")
    p1_len = S.len16(S.para_text(paras[0]))
    p2_len = S.len16(S.para_text(paras[1]))
    comp = [[0, 0, 0, t1, 0, 14, 240, 3], [0, 0, t1 + 1, p1_len, 0, 28, 240, 0],
            [0, 1, 0, 9, 10.5, 50, 229.5, 1], [1, 1, 10, p2_len, 0, 18.25, 240, 1],
            [1, 2, 0, S.len16(S.para_text(paras[2])), 0, 40, 240, 2]]
    composed = {"pages": PAGES3, "items": [_frame("t1", "p1"), _frame("t2", "p2", rot=-3.5, opacity=80,
                                                                       fill="#f4efe8", stroke={"c": "#000000", "w": 1.5})],
                "threads": [{"id": "s1", "frames": ["t1", "t2"], "paras": paras, "comp": {"lines": comp}}]}
    flowed = {"pages": PAGES3, "items": [_frame("t1", "p1", cols=2, gutter=9, inset=6), _frame("t2", "p3")],
              "threads": [{"id": "s1", "frames": ["t1", "t2"], "paras": [
                  {"runs": [{"t": "Flowing <words>"}], "align": "ja", "li": 6, "ri": 3, "fi": 12, "sb": 4, "sa": 2,
                   "lead": 13.5},
                  {"runs": [{"t": "", "size": 20}]}]}]}
    pictures = {"pages": [{"id": "p1"}, {"id": "p2"}], "facing": False, "paper": "#fffaf0", "items": [
        {"id": "i1", "kind": "image", "page": "p1", "x": -9, "y": -9, "w": 630, "h": 400, "asset_id": A, "fit": "fit",
         "fx": 33.33, "fy": 70, "zoom": 125, "radius": 6, "stroke": {"c": "#ffffff", "w": 4}, "rot": 12.25},
        {"id": "i2", "kind": "image", "page": "p1", "x": 0, "y": 420, "w": 200, "h": 200, "asset_id": B},
        {"id": "i3", "kind": "image", "page": "p1", "x": 220, "y": 420, "w": 200, "h": 200, "asset_id": C},
        {"id": "i4", "kind": "image", "page": "p2", "x": 10, "y": 10, "w": 50, "h": 50, "fill": "#cccccc"},
        {"id": "r1", "kind": "rect", "page": "p2", "x": 100, "y": 100, "w": 120, "h": 60, "fill": "#123456",
         "radius": 8, "opacity": 45},
        {"id": "e1", "kind": "ellipse", "page": "p2", "x": 300, "y": 100, "w": 90, "h": 90,
         "stroke": {"c": "#ff0000", "w": 2}},
        {"id": "l1", "kind": "line", "page": "p2", "x": 54, "y": 700, "w": 504, "h": 0},
        {"id": "l2", "kind": "line", "page": "p2", "x": 54, "y": 600, "w": 100, "h": 80,
         "stroke": {"c": "#00aa00", "w": 3}, "flip": True},
        {"id": "h1", "kind": "rect", "page": "p2", "w": 10, "h": 10, "hidden": True, "fill": "#999999"},
    ], "threads": []}
    by_id = {g["id"]: g["sha"] for g in G.manifest()["graphics"]}
    graphic_page = {"pages": [{"id": "p1"}], "items": [
        {"id": "g1", "kind": "graphic", "page": "p1", "x": 20, "y": 30, "w": 144, "h": 120, "src": by_id["gummfit/star"],
         "color": "#B4532A", "fit": "stretch", "rot": 15, "opacity": 70},
        {"id": "g2", "kind": "graphic", "page": "p1", "x": 200, "y": 30, "w": 96, "h": 96, "src": by_id["fluent/red-heart"],
         "color": "#00ff00"},
        {"id": "g3", "kind": "graphic", "page": "p1", "x": -9, "y": -9, "w": 630, "h": 810, "src": by_id["gummfit/dots"],
         "color": "#d9d4cc", "fit": "tile", "tile": 18.5},
        {"id": "g4", "kind": "graphic", "page": "p1", "x": 300, "y": 300, "w": 72, "h": 72, "src": by_id["lucide/heart"]},
    ], "threads": []}
    locked = {**composed, "paywall_page": 2}
    a4 = {**composed, "size": {"w": 595.28, "h": 841.89}}
    identity = json.loads((Path(__file__).parent / 'fixtures/studio_identity.json').read_text())
    branded = {"identity": identity, "pages": [{"id": "p1"}, {"id": "p2", "parent": "pl1", "header": "Feature & profile"}],
               "items": [_frame("t1", "p1")], "threads": [{"id": "s1", "frames": ["t1"], "paras": [
                   {"style": "ps1", "runs": [{"t": "Named caption"}, {"t": " emphasis", "style": "cs1"}, {"t": " local", "it": False, "color": "#1a1a1a"}]}]}]}
    out = []
    for name, raw, locked_from in [("composed text", composed, None), ("flowed text", flowed, None),
                                   ("pictures and shapes", pictures, None), ("locked pages", locked, 2),
                                   ("a4 pages", a4, None), ("uncomposed past the wall", flowed, 2),
                                   ("graphics", graphic_page, None), ("magazine identity", branded, None),
                                   ("identity locked pages", branded, 2)]:
        doc = S.normalize_doc(raw)
        html, used = R.pages_html(doc, ASSETS, locked_from=locked_from, label="Pages of 'Tide'")
        out.append({"name": name, "doc": doc, "locked_from": locked_from, "html": html,
                    "used": {k: sorted(f"{w}|{int(i)}" for w, i in v) for k, v in sorted(used.items())},
                    "faces_css": R.faces_css(doc)})
    return out


def _with_faces(monkeypatch):
    table = {(f["family"], f["weight"], f["italic"]): f for f in FACES}
    monkeypatch.setattr(faces, "face", lambda fam, wt, it: table.get((fam, wt, it)))


def test_the_fixture_is_this_renderers_output(monkeypatch):
    _with_faces(monkeypatch)
    cases = _cases()
    payload = {"faces": FACES, "assets": ASSETS, "label": "Pages of 'Tide'", "cases": cases}
    text = json.dumps(payload, indent=1, ensure_ascii=False) + "\n"
    if os.environ.get("STUDIO_FIXTURES") == "write":
        FIXTURE.write_text(text, encoding="utf-8")
    assert json.loads(FIXTURE.read_text(encoding="utf-8")) == json.loads(text), \
        "the renderer changed: write the fixture again (see this module) and make the client match"


def test_the_fixture_covers_what_it_says():
    cases = {c["name"]: c for c in json.loads(FIXTURE.read_text(encoding="utf-8"))["cases"]}
    assert "lyt-l--j" in cases["composed text"]["html"] and 'class="lyt-sp"' in cases["composed text"]["html"]
    assert "&lt;b&gt;escaped&lt;/b&gt;" in cases["composed text"]["html"]
    assert "lyt-flow" in cases["flowed text"]["html"]
    assert "AI illustration" in cases["pictures and shapes"]["html"]
    assert "javascript:" not in cases["pictures and shapes"]["html"]
    assert "lyt-page--locked" in cases["locked pages"]["html"]
    assert "Flowing" not in cases["uncomposed past the wall"]["html"].split('data-lyt-lock="3"')[0]
    g = cases["graphics"]["html"]
    assert "background:#b4532a;-webkit-mask:url(/api/cappe/public/graphics/" in g  # a one-colour graphic, recoloured
    assert "center/100% 100% no-repeat" in g and "center/contain no-repeat" in g
    assert "0 0/calc(18.5 * var(--u)) auto repeat" in g  # a pattern
    assert g.count("-webkit-mask:") == 3  # the colourful heart is drawn as it is, its colour dropped


def test_both_copies_of_layout_css_are_the_same():
    assert CLIENT_CSS.read_text(encoding="utf-8") == R.CSS


def test_the_client_limits_are_the_servers():
    ts = CLIENT_LIMITS.read_text(encoding="utf-8")
    body = ts[ts.index("export const LIMITS = {"):ts.index("} as const")]
    for key, value in L.limits().items():
        m = re.search(rf"\n  {key}: (.+),\n", body)
        assert m, f"{key} is missing from limits.ts"
        expected = value
        got = m.group(1).replace("_", "")
        if isinstance(value, (list, dict)):
            js = got.replace("'", '"')
            js = re.sub(r"([{,]\s*)(\w+):", r'\1"\2":', js)
            assert json.loads(js) == expected, key
        else:
            assert float(got) == float(expected), key
