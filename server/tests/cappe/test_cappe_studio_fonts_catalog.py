"""The Studio's built-in faces: the catalog (`magazine/fonts.FONTS`, also the
classic editor's) and the Gummfit cuts (`studio/cuts.py`, the Studio's own),
both built into `fonts_manifest.json` by `scripts/build_magazine_fonts.py`.

Run from server/:  ./venv/bin/python -m pytest tests/cappe/test_cappe_studio_fonts_catalog.py -q
"""
import asyncio
import json
import re
from io import BytesIO
from pathlib import Path

from fontTools.fontBuilder import FontBuilder
from fontTools.pens.ttGlyphPen import TTGlyphPen
from fontTools.ttLib import TTFont

from app.cappe.services.magazine.fonts import FONTS
from app.cappe.services.magazine.studio import fonts as faces
from app.cappe.services.magazine.studio import render as R
from app.cappe.services.magazine.studio import schema as S
from app.cappe.services.magazine.studio.cuts import CUTS
from app.cappe.services.magazine.studio.font_build import rename
from scripts.build_magazine_fonts import merge, upload

ROOT = Path(__file__).resolve().parents[3]
CUTS_TS = ROOT / "client/src/cappe/studio/fonts/cuts.ts"
ADDED = ("Big Shoulders Stencil Display", "Anybody", "Jost", "Poiret One", "Great Vibes", "Italianno", "Pinyon Script")


def _weights(expr: str) -> tuple[int, ...]:
    m = re.fullmatch(r"w\((\d+), (\d+)\)", expr.strip())
    if m:
        return tuple(range(int(m.group(1)), int(m.group(2)) + 1, 100))
    return tuple(int(x) for x in re.findall(r"\d+", expr))


def test_the_client_lists_the_same_cuts():
    rows = re.findall(r"\{ name: '([^']+)', cat: '(\w+)', body: (true|false), w: (w\(\d+, \d+\)|\[[\d, ]*\]), "
                      r"i: (w\(\d+, \d+\)|\[[\d, ]*\]), source: '([^']+)', axes: \{ ([^}]*) \}(?:, fallback: '([^']+)')? \}",
                      CUTS_TS.read_text())
    client = {name: (cat, body == "true", _weights(w), _weights(i), source,
                     {k: float(v) for k, v in re.findall(r"(\w+): ([\d.]+)", axes)}, fallback)
              for name, cat, body, w, i, source, axes, fallback in rows}
    assert client == {name: (c.category, c.body, c.weights, c.italics, c.source, {k: float(v) for k, v in c.axes.items()},
                             c.fallback) for name, c in CUTS.items()}


def test_a_cut_is_named_apart_from_every_catalog_font_and_cut_from_one():
    assert not set(CUTS) & set(FONTS)
    for name, c in CUTS.items():
        assert c.stand_in in FONTS, name  # what a page is set in while its faces aren't built
        assert c.axes and set(c.weights) >= set(c.italics) and 400 in c.weights, name
        assert c.category in ("serif", "sans", "display", "handwriting", "mono")


def test_every_style_of_the_new_families_and_cuts_is_built():
    built = {(f["family"], f["weight"], f["italic"]) for f in faces.manifest()["faces"]}
    for name in ADDED:
        _cat, _body, weights, italics = FONTS[name]
        assert {(name, w, False) for w in weights} | {(name, w, True) for w in italics} <= built, name
    for name, c in CUTS.items():
        assert {(name, w, False) for w in c.weights} | {(name, w, True) for w in c.italics} <= built, name


def test_a_cut_is_set_at_its_nearest_style_and_falls_back_to_its_source_unbuilt():
    a = S.char_attrs({"font": "Bodoni Moda Display", "wt": 300, "it": True})
    assert (a["font"], a["wt"], a["it"]) == ("Bodoni Moda Display", 400, True)
    b = S.char_attrs({"font": "Bricolage Grotesque Condensed", "wt": 900, "it": True})
    assert (b["wt"], b["it"]) == (800, False)  # no italics
    used: dict = {}
    style = R.run_style({"font": "Bodoni Moda Display", "wt": 400, "it": False, "size": 40}, used)
    if faces.face("Bodoni Moda Display", 400, False) is None:  # an environment with an older manifest
        assert "'Bodoni Moda'" in style and "Bodoni Moda" in used
    else:
        assert "font-family:'f-" in style


def test_the_render_fallback_names_the_source(monkeypatch):
    monkeypatch.setattr(faces, "face", lambda *a: None)
    used: dict = {}
    style = R.run_style({"font": "Playfair Poster", "wt": 700, "it": True, "size": 60}, used)
    assert style.startswith("font-family:'Playfair Display', Georgia") and ";font-weight:700;font-style:italic" in style
    assert set(used) == {"Playfair Display"}
    R.run_style({"font": "Archivo Condensed", "wt": 500}, used)
    assert "Archivo" in used


def _font(family="Source Family", style="Black") -> TTFont:
    fb = FontBuilder(1000, isTTF=True)
    fb.setupGlyphOrder([".notdef", "A"])
    fb.setupCharacterMap({0x41: "A"})
    pen = TTGlyphPen(None)
    pen.moveTo((0, 0)); pen.lineTo((500, 700)); pen.lineTo((600, 0)); pen.closePath()
    fb.setupGlyf({".notdef": TTGlyphPen(None).glyph(), "A": pen.glyph()})
    fb.setupHorizontalMetrics({".notdef": (500, 0), "A": (600, 0)})
    fb.setupHorizontalHeader(ascent=900, descent=-250)
    fb.setupNameTable({"familyName": family, "styleName": style, "copyright": "Copyright the designers",
                       "licenseDescription": "SIL Open Font License 1.1", "typographicSubfamily": style})
    fb.setupOS2()
    fb.setupPost()
    buf = BytesIO()
    fb.save(buf)
    return TTFont(BytesIO(buf.getvalue()))


def test_a_cut_is_renamed_inside_its_file_and_keeps_its_licence():
    names = lambda f: {n: f["name"].getDebugName(n) for n in (0, 1, 2, 4, 6, 13, 16, 17)}  # noqa: E731
    assert names(rename(_font(), "Fraunces Display", 400, False)) == {
        0: "Copyright the designers", 1: "Fraunces Display", 2: "Regular", 4: "Fraunces Display Regular",
        6: "FrauncesDisplay-Regular", 13: "SIL Open Font License 1.1", 16: "Fraunces Display", 17: "Regular"}
    semi = names(rename(_font(), "Fraunces Display", 600, True))
    assert (semi[1], semi[2], semi[6], semi[17]) == ("Fraunces Display SemiBold", "Italic", "FrauncesDisplay-SemiBoldItalic", "SemiBold Italic")
    bold = names(rename(_font(), "Playfair Poster", 700, True))
    assert (bold[1], bold[2]) == ("Playfair Poster", "Bold Italic")
    assert "Source Family" not in json.dumps(names(rename(_font(), "Playfair Poster", 300, False)))


def test_adding_families_leaves_the_rest_of_the_manifest_as_it_was():
    kept = faces.manifest()["faces"]
    assert merge(kept, [], []) == kept
    first = kept[0]
    rebuilt = {**first, "sha": "f" * 64}
    out = merge(kept, [rebuilt] + [f for f in kept if f["family"] == first["family"] and f is not first], [first["family"]])
    assert len(out) == len(kept) and out[0] == rebuilt and out[1:] == kept[1:]
    cut = {"family": "Fraunces Display", "weight": 100, "italic": False, "sha": "e" * 64}
    assert merge([f for f in kept if f["family"] != "Fraunces Display"], [cut], ["Fraunces Display"])[-1]["family"] in CUTS


def test_upload_loads_settings_before_opening_storage(monkeypatch, tmp_path):
    """A standalone script has to load settings itself: --upload used to call
    get_storage() first and die with 'Settings not initialized'."""
    import app.config
    import app.core.services.storage

    calls, stored = [], {}

    class FakeStorage:
        async def get_key(self, key):
            return stored.get(key)

        async def put_key(self, key, data, content_type):
            stored[key] = (data, content_type)

    def fake_get_storage():
        assert calls == ["settings"], "storage opened before settings were loaded"
        return FakeStorage()

    monkeypatch.setattr(app.config, "load_settings", lambda: calls.append("settings"))
    monkeypatch.setattr(app.core.services.storage, "get_storage", fake_get_storage)
    sha = "a" * 64
    (tmp_path / f"{sha}.ttf").write_bytes(b"face")
    stored[f"cappe/fonts/{'b' * 64}.ttf"] = (b"old", "font/ttf")
    faces_ = [{"sha": sha}, {"sha": "b" * 64}]

    asyncio.run(upload(faces_, tmp_path, dry_run=True))
    assert f"cappe/fonts/{sha}.ttf" not in stored
    calls.clear()
    asyncio.run(upload(faces_, tmp_path, dry_run=False))
    assert stored[f"cappe/fonts/{sha}.ttf"] == (b"face", "font/ttf")
    assert stored[f"cappe/fonts/{'b' * 64}.ttf"] == (b"old", "font/ttf")
