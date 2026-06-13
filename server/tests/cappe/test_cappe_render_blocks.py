"""Cappe render tests for the hero image overlay, the certifications block, and
the two-step booking slot picker. Pure render — no DB, no app boot.

Run from server/:  ./venv/bin/python -m pytest tests/cappe/test_cappe_render_blocks.py -q
"""
import os

os.environ.setdefault("LIVE_API", "test-key")
os.environ.setdefault("DATABASE_URL", "postgresql://test:test@localhost/test")
os.environ.setdefault("JWT_SECRET_KEY", "test-secret-key-cappe")

from app.cappe.services.render import render_site_html  # noqa: E402

_SITE = {"slug": "demo", "name": "Demo", "theme_config": None, "meta_config": {}}
_NAV = [{"slug": "home", "title": "Home"}]


def _render(*blocks: dict) -> str:
    return render_site_html(_SITE, {"title": "Home", "content": {"blocks": list(blocks)}}, _NAV)


# --- hero image layout -------------------------------------------------------

def test_hero_image_overlay_align_height_classes():
    html = _render({
        "type": "hero", "style": "image", "heading": "Strong & Steady",
        "image": "https://cdn.example.com/a.jpg", "overlay": "dark", "align": "left", "height": "full",
    })
    assert "cz-hero--image cz-ov-dark cz-hero--left cz-hero--full" in html
    assert "background-image:url('https://cdn.example.com/a.jpg')" in html


def test_hero_image_defaults_to_medium_centered_tall():
    html = _render({"type": "hero", "style": "image", "heading": "h", "image": "https://cdn.example.com/a.jpg"})
    # Assert on the rendered section's class list (the classes also exist in CSS).
    assert '<section class="cz-hero cz-hero--image cz-ov-medium"' in html


def test_hero_image_rejects_url_breakout():
    bad = "https://x/a.jpg'); } body{display:none} .x{background:url('"
    html = _render({"type": "hero", "style": "image", "heading": "h", "image": bad})
    # _safe_image rejects quotes/parens — no background-image emitted at all.
    assert "body{display:none}" not in html
    assert "background-image:url" not in html


# --- credentials / qualifications -------------------------------------------

def test_credentials_block_renders_items():
    html = _render({
        "type": "credentials", "heading": "Certifications", "items": [
            {"title": "Certified Personal Trainer", "issuer": "NASM", "year": "2021", "detail": "Corrective exercise."},
            {"title": "CPR & First Aid", "issuer": "Red Cross", "year": "2024"},
        ],
    })
    assert "cz-creds-grid" in html
    assert "Certified Personal Trainer" in html
    assert "NASM · 2021" in html          # issuer · year meta line
    assert "Corrective exercise." in html  # optional detail
    assert "Red Cross · 2024" in html


def test_credentials_block_escapes_html():
    html = _render({"type": "credentials", "items": [{"title": "<script>x</script>", "issuer": "y"}]})
    assert "<script>x</script>" not in html
    assert "&lt;script&gt;" in html


# --- booking two-step picker -------------------------------------------------

def test_booking_picker_is_two_step_day_then_time():
    html = _render({"type": "booking", "heading": "Book a session"})
    # Day strip + times container classes ship in the base CSS.
    assert ".cz-daystrip" in html
    assert ".cz-times" in html
    # Runtime copy: pick a day first, not a flat "Pick a time (UTC)" dump.
    assert "Pick a day" in html
    assert "Pick a time (" not in html
