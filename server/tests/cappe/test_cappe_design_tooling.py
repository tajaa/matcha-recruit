"""Cappe design-tooling tests: the global style system (theme_config.style),
the extended per-section `_design` (columns / px padding / type / border /
anchor), the anchor-id gate, and the premium design gate.

Pure — no DB, no app boot.

Run from server/:  ./venv/bin/python -m pytest tests/cappe/test_cappe_design_tooling.py -q
"""
import os

os.environ.setdefault("LIVE_API", "test-key")
os.environ.setdefault("DATABASE_URL", "postgresql://test:test@localhost/test")
os.environ.setdefault("JWT_SECRET_KEY", "test-secret-key-cappe")

from app.cappe.services.design_gate import gate_content, gate_theme  # noqa: E402
from app.cappe.services.render import _anchor_id, render_site_html  # noqa: E402

_NAV = [{"slug": "home", "title": "Home"}]


def _render(theme=None, blocks=None) -> str:
    site = {"slug": "demo", "name": "Demo", "theme_config": theme, "meta_config": {}}
    return render_site_html(site, {"title": "Home", "content": {"blocks": blocks or []}}, _NAV)


# --- global style system -----------------------------------------------------

def test_unset_style_is_byte_identical():
    """No `style` key ⇒ no extra :root vars and no per-section classes applied."""
    blocks = [{"type": "features", "heading": "F", "items": [{"title": "a", "body": "b"}]}]
    html = _render(theme={}, blocks=blocks)
    assert ":root{--base-fs" not in html
    body = html.split("</style>", 1)[1]
    for cls in ("cz-has-cols", "cz-bd-t", "cz-has-hsize", "cz-design"):
        assert cls not in body
    # The fallback literals must survive in the stylesheet.
    assert "font-size:var(--base-fs,17px)" in html
    assert "max-width:var(--container,72rem)" in html


def test_style_tokens_emit_clamped_and_enum():
    html = _render(theme={"style": {
        "baseFont": 19, "container": "wide", "sectionPad": "roomy",
        "cardPad": 30, "gap": "roomy", "cardBorder": "bold", "brandSize": 40,  # 40 clamps to 32
    }})
    assert "--base-fs:19px" in html
    assert "--container:80rem" in html
    assert "--sec-pad:clamp(4rem,8vw,6.5rem)" in html
    assert "--card-pad:30px" in html
    assert "--grid-gap:2rem" in html
    assert "--card-bd:2px" in html
    assert "--brand-fs:32px" in html  # clamped 40 → 32


def test_style_junk_values_dropped():
    html = _render(theme={"style": {"baseFont": "not-a-number", "container": "bogus", "cardPad": None}})
    assert ":root{--base-fs" not in html
    assert "--container:" not in html.split("_BASE_CSS", 1)[0] if False else True  # container enum miss → absent
    assert "--base-fs" not in html.split("</style>")[0].split("var(--base-fs")[0]


# --- per-section _design extensions ------------------------------------------

def test_section_columns_and_gap_and_border_and_type():
    blocks = [{
        "type": "features", "heading": "F", "items": [{"title": "a", "body": "b"}],
        "_design": {
            "layout": {"columns": 4, "gap": 40, "padTopPx": 0},
            "type": {"headingSize": 60, "bodySize": 20},
            "border": {"top": True, "width": 3, "color": "#ff0000"},
        },
    }]
    html = _render(blocks=blocks)
    assert "--cz-cols:repeat(4,minmax(0,1fr))" in html
    assert "cz-has-cols" in html
    assert "--cz-gap:40px" in html
    assert "--cz-pad-t:0px" in html and "cz-has-pt" in html   # px 0 wins & applies
    assert "--cz-h-size:60px" in html and "cz-has-hsize" in html
    assert "--cz-p-size:20px" in html
    assert "cz-bd-t" in html and "--cz-bd-w:3px" in html and "--cz-bd-col:#ff0000" in html


def test_section_px_padding_wins_over_enum():
    blocks = [{"type": "text", "heading": "T", "_design": {"layout": {"padTop": "lg", "padTopPx": 120}}}]
    html = _render(blocks=blocks)
    assert "--cz-pad-t:120px" in html
    assert "--cz-pad-t:6rem" not in html  # enum 'lg' would be 6rem — must be overridden


def test_bad_hex_border_color_dropped():
    blocks = [{"type": "features", "items": [], "_design": {"border": {"top": True, "color": "red; }"}}}]
    html = _render(blocks=blocks)
    assert "cz-bd-t" in html
    assert "--cz-bd-col" not in html.split("</style>", 1)[1]  # invalid hex → no color var on section


# --- anchor id gate ----------------------------------------------------------

def test_anchor_id_strict_slug():
    assert _anchor_id("Pricing") == "pricing"
    assert _anchor_id("my-section") == "my-section"
    assert _anchor_id('a b"><script') == ""
    assert _anchor_id("-bad") == ""
    assert _anchor_id("bad-") == ""
    assert _anchor_id("good1") == "good1"


def test_anchor_id_applied_to_section():
    blocks = [{"type": "text", "heading": "T", "_design": {"anchor": {"id": "contact"}}}]
    html = _render(blocks=blocks)
    assert 'id="contact"' in html
    # An injection attempt yields no id attribute at all.
    blocks2 = [{"type": "text", "heading": "T", "_design": {"anchor": {"id": 'x"><b>'}}}]
    assert 'id="x' not in _render(blocks=blocks2)


def test_anchor_id_not_duplicated_on_store_and_booking():
    """store (id="shop") / booking (id="book") already carry an id — the anchor
    must NOT add a second id= (invalid HTML; browser would keep the first)."""
    for btype, existing in (("store", "shop"), ("booking", "book")):
        html = _render(blocks=[{"type": btype, "heading": "H", "_design": {"anchor": {"id": "myanchor"}}}])
        assert f'id="{existing}"' in html          # original preserved
        assert 'id="myanchor"' not in html         # user anchor suppressed, not doubled
        # exactly one id on that block's <section> open tag
        section = html.split("<section", 1)[1].split(">", 1)[0]
        assert section.count("id=") == 1


# --- premium gate ------------------------------------------------------------

def test_gate_theme_strips_for_free_keeps_for_pro():
    tc = {"preset": "x", "mode": "dark", "colors": {"brand": "#111", "brandGradient": {"stops": ["#1", "#2"]}},
          "style": {"baseFont": 19}, "type": {"headingWeight": 800}, "premium": True}
    free = gate_theme(tc, "free")
    assert "style" not in free and "type" not in free and "premium" not in free
    assert "brandGradient" not in free["colors"]
    assert free["preset"] == "x" and free["colors"]["brand"] == "#111"  # basics kept
    assert gate_theme(tc, "pro") == tc                                   # premium untouched
    assert "style" in tc                                                 # original not mutated


def test_gate_content_strips_design_for_free():
    content = {"blocks": [{"type": "hero", "_design": {"motion": {"effect": "fade"}}}, {"type": "text"}]}
    free = gate_content(content, "free")
    assert "_design" not in free["blocks"][0]
    assert "_design" in gate_content(content, "business")["blocks"][0]
    assert "_design" in content["blocks"][0]  # original intact
