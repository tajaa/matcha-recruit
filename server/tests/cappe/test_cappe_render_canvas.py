"""Cappe canvas-mode render tests: the selection/edit runtime + element tagging
must appear ONLY in editable previews, never on published output. Pure render —
no DB, no app boot.

Run from server/:  ./venv/bin/python -m pytest tests/cappe/test_cappe_render_canvas.py -q
"""
import os

os.environ.setdefault("LIVE_API", "test-key")
os.environ.setdefault("DATABASE_URL", "postgresql://test:test@localhost/test")
os.environ.setdefault("JWT_SECRET_KEY", "test-secret-key-cappe")

from app.cappe.services.render import render_site_html  # noqa: E402

_SITE = {"slug": "demo", "name": "Demo", "theme_config": None, "meta_config": {}}
_NAV = [{"slug": "home", "title": "Home"}]
_BLOCKS = [
    {"type": "hero", "style": "centered", "heading": "Welcome", "subheading": "Sub", "eyebrow": "Hi"},
    {"type": "cta", "heading": "Act now", "subheading": "Do it", "cta": "Go", "ctaHref": "/x"},
]


def _render(*, editable: bool, preview: bool = True) -> str:
    return render_site_html(
        _SITE, {"title": "Home", "content": {"blocks": _BLOCKS}}, _NAV, preview=preview, editable=editable
    )


# --- published output must be clean -----------------------------------------

def test_published_has_no_canvas_artifacts():
    html = _render(editable=False, preview=False)
    for needle in ("data-cz-block", "data-cz-field", "cz-editable", "cz-ready", "cz-select"):
        assert needle not in html, f"leaked into published render: {needle}"


def test_form_preview_has_no_canvas_artifacts():
    # A normal (non-editable) live preview is also clean.
    html = _render(editable=False, preview=True)
    assert "data-cz-block" not in html
    assert "cz-ready" not in html


# --- editable preview carries the canvas surface ----------------------------

def test_editable_tags_blocks_and_fields():
    html = _render(editable=True)
    assert 'data-cz-block="0"' in html and 'data-cz-block="1"' in html
    # hero text fields tagged for inline editing
    assert 'class="cz-hero__title" data-cz-field="heading"' in html
    assert 'data-cz-field="subheading"' in html
    assert 'data-cz-field="eyebrow"' in html
    # body carries the editable class + the runtime
    assert "cz-editable" in html.split("<body", 1)[1].split(">", 1)[0]
    assert "cz-ready" in html  # runtime sentinel
    assert "window.parent.postMessage" in html


def test_block_without_design_still_tagged_when_editable():
    # data-cz-block must be injected even though the block has no _design.
    html = render_site_html(
        _SITE, {"title": "Home", "content": {"blocks": [{"type": "text", "heading": "Plain", "body": "Just text"}]}},
        _NAV, preview=True, editable=True,
    )
    assert 'data-cz-block="0"' in html
    assert 'data-cz-field="heading"' in html and 'data-cz-field="body"' in html
