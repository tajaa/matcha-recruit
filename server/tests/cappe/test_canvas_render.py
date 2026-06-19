"""Freeform grid-snap canvas block render — safety + correctness (pure, no DB).

Run from server/:  ./venv/bin/python -m pytest tests/cappe/test_canvas_render.py -q
"""
import os

os.environ.setdefault("LIVE_API", "test-key")
os.environ.setdefault("DATABASE_URL", "postgresql://test:test@localhost/test")
os.environ.setdefault("JWT_SECRET_KEY", "test-secret-key-cappe")

from app.cappe.services import render as R  # noqa: E402


def _block():
    return {
        "type": "canvas",
        "grid": {"cols": 24, "rowH": 24},
        "mobile": {"cols": 8, "rowH": 24},
        "elements": [
            {"id": "h1", "kind": "heading", "text": "<script>x</script>",
             "d": {"x": 2, "y": 1, "w": 12, "h": 3},
             "style": {"font": "Playfair Display", "size": 48, "weight": "700",
                       "color": "#10b981", "align": "center", "spacing": "-0.02em", "lineHeight": 1.1}},
            {"id": "bad id!", "kind": "text", "text": "skip me", "d": {"x": 0, "y": 0, "w": 4, "h": 2}},
            {"id": "img1", "kind": "image", "src": "https://x.test/a.png", "alt": '"oops',
             "d": {"x": 0, "y": 5, "w": 8, "h": 6}, "style": {"fit": "contain", "radius": 12}},
            {"id": "evil", "kind": "image", "src": "javascript:alert(1)", "d": {"x": 0, "y": 12, "w": 4, "h": 2}},
        ],
    }


def test_hostile_content_is_escaped():
    html = R._render_block(_block(), R._tokens({}), 3, True)
    assert "<script>x" not in html and "&lt;script&gt;x" in html  # text escaped
    assert '"oops' not in html and "&quot;oops" in html           # alt escaped
    assert "javascript:alert" not in html                          # bad scheme dropped


def test_bad_id_is_skipped():
    html = R._render_block(_block(), R._tokens({}), 3, True)
    assert "bad id!" not in html
    assert 'data-cz-id="bad' not in html


def test_mobile_style_is_block_scoped():
    html = R._render_block(_block(), R._tokens({}), 3, True)
    assert "@media(max-width:767px)" in html
    assert ".cz-cv-3 [data-cz-id=" in html        # scoped to this block index
    assert '.cz-cv-3 [data-cz-id="bad' not in html  # skipped id has no mobile rule


def test_field_tags_are_text_only_and_editor_only():
    edit = R._render_block(_block(), R._tokens({}), 3, True)
    assert edit.count("data-cz-field") == 1        # only the heading text element
    pub = R._render_block(_block(), R._tokens({}), 3, False)
    assert "data-cz-field" not in pub              # no inline-edit hooks published
    assert "data-cz-block" not in pub              # no selection hooks published
    assert "cz-cv-3" in pub                        # but the scope class is present (mobile CSS works)


def test_coords_become_one_based_grid_lines():
    html = R._render_block(_block(), R._tokens({}), 3, True)
    # heading d.x=2,w=12 -> grid-column:3/span 12 ; d.y=1,h=3 -> grid-row:2/span 3
    assert "grid-column:3/span 12;grid-row:2/span 3" in html


def _btn_block():
    return {
        "type": "canvas", "grid": {"cols": 24, "rowH": 24}, "mobile": {"cols": 8, "rowH": 24},
        "elements": [
            {"id": "ok", "kind": "button", "text": "Book <now>", "href": "/book",
             "d": {"x": 2, "y": 1, "w": 6, "h": 2},
             "style": {"variant": "solid", "bg": "#10b981", "color": "#ffffff", "radius": 8}},
            {"id": "evil", "kind": "button", "text": "x", "href": "javascript:alert(1)",
             "d": {"x": 9, "y": 1, "w": 6, "h": 2}, "style": {"variant": "outline"}},
        ],
    }


def test_button_element_render_and_safety():
    html = R._render_block(_btn_block(), R._tokens({}), 0, True)
    assert "Book &lt;now&gt;" in html and "Book <now>" not in html   # label escaped
    assert 'href="/book"' in html                                    # safe link kept
    assert "javascript:" not in html                                 # bad scheme dropped
    assert "cz-btn--solid" in html and "cz-btn--ghost" in html       # variant → class
    assert html.count("data-cz-field") == 2                          # both labels inline-editable
    assert "background:#10b981" in html and "border-radius:8px" in html
