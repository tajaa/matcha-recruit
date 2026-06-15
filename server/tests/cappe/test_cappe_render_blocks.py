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


def test_centered_hero_with_photo_becomes_image_hero():
    # The intuitive "add a hero image" path: a default (centered) hero that gets
    # a photo auto-promotes to the full-bleed image hero.
    html = _render({"type": "hero", "style": "centered", "heading": "Studio", "image": "https://cdn.example.com/p.jpg"})
    assert "cz-hero--image" in html
    assert "background-image:url('https://cdn.example.com/p.jpg')" in html


def test_centered_hero_without_photo_stays_centered():
    html = _render({"type": "hero", "style": "centered", "heading": "Studio"})
    assert '<section class="cz-hero cz-hero--centered"' in html


def test_split_hero_with_photo_stays_split():
    html = _render({"type": "hero", "style": "split", "heading": "Studio", "image": "https://cdn.example.com/p.jpg"})
    assert "cz-hero--split" in html


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

def test_reviews_block_renders_widget_with_form():
    html = _render({"type": "reviews", "heading": "What clients say", "allowSubmissions": True})
    assert "cz-reviews" in html
    assert 'data-form="1"' in html
    assert "RT.get('/reviews')" in html       # widget hydrates approved reviews
    assert "What clients say" in html


def test_reviews_block_can_disable_submissions():
    html = _render({"type": "reviews", "allowSubmissions": False})
    assert 'data-form="0"' in html


def test_booking_picker_is_two_step_day_then_time():
    html = _render({"type": "booking", "heading": "Book a session"})
    # Day strip + times container classes ship in the base CSS.
    assert ".cz-daystrip" in html
    assert ".cz-times" in html
    # Runtime copy: pick a day first, not a flat "Pick a time (UTC)" dump.
    assert "Pick a day" in html
    assert "Pick a time (" not in html


# --- bespoke designer layer (_design) ----------------------------------------

def _main(html: str) -> str:
    # The rendered block markup, excluding the static <style> + runtime script
    # (which always reference the designer class/var NAMES).
    return html.split("<main>", 1)[1].split("</main>", 1)[0]


def test_block_without_design_is_unchanged():
    # No _design → no designer classes in the markup, no runtime, empty body class.
    html = _render({"type": "features", "heading": "F", "items": [{"title": "a"}]})
    main = _main(html)
    assert "cz-design" not in main and "cz-rv" not in main and "cz-bg" not in main
    assert 'class=""' in html  # body has no premium/motion class
    assert "IntersectionObserver" not in html


def test_design_motion_classes_and_runtime():
    html = _render({"type": "features", "heading": "F", "items": [{"title": "a"}],
                    "_design": {"motion": {"effect": "slide-up", "delay": 150, "duration": 900, "stagger": True}}})
    assert "cz-design" in html and "cz-rv cz-rv--slide-up" in html and "cz-rv--stagger" in html
    assert 'data-cz-delay="150"' in html and 'data-cz-dur="900"' in html
    assert 'class="cz-motion"' in html  # body class
    assert "IntersectionObserver" in html  # runtime emitted


def test_design_background_video_injects_media_and_overlay():
    html = _render({"type": "cta", "heading": "C",
                    "_design": {"bg": {"type": "video", "video": "https://cdn.example.com/v.mp4",
                                       "overlay": "dark", "blur": 8}}})
    assert "cz-bg cz-bg--video" in html
    assert '<video autoplay muted loop playsinline preload="metadata"><source src="https://cdn.example.com/v.mp4">' in html
    assert "cz-bg-ov cz-ov-dark" in html and "--cz-blur:8px" in html


def test_design_gradient_and_color_and_layout_and_colors():
    html = _render({"type": "features", "heading": "F", "items": [],
                    "_design": {"bg": {"type": "gradient", "gradient": {"angle": 90, "stops": ["#ffffff", "#000000"]}},
                                "layout": {"maxWidth": "wide", "padTop": "xl", "align": "center", "minHeight": "tall"},
                                "colors": {"text": "#222222", "accent": "#ff0000"}}})
    assert "cz-bg--gradient" in html and "--cz-grad:linear-gradient(90deg,#ffffff,#000000)" in html
    assert "cz-has-maxw" in html and "--cz-maxw:84rem" in html and "--cz-pad-t:9rem" in html
    assert "cz-al-center" in html and "--cz-minh:70vh" in html
    assert "--cz-text:#222222" in html and "cz-acc" in html and "--cz-brand:#ff0000" in html


def test_design_rejects_malicious_values():
    html = _render({"type": "cta", "heading": "C",
                    "_design": {"bg": {"type": "color", "color": "red;background:url(evil)"},
                                "colors": {"text": "javascript:alert(1)", "accent": "</style><script>x"},
                                "motion": {"effect": "<script>"}}})
    # invalid hex/url/effect all dropped; nothing injected into the section markup
    main = _main(html)
    open_tag = main.split(">", 1)[0] + ">"
    assert "javascript" not in open_tag and "url(evil" not in open_tag and "<script" not in open_tag
    assert "--cz-bg-color" not in main and "--cz-text:" not in main
    assert "cz-rv--" not in main  # bogus effect not applied


def test_design_preserves_trailing_widget_script():
    # reviews emits <section>...</section><script>...; wrapper must not swallow it.
    html = _render({"type": "reviews", "heading": "R",
                    "_design": {"motion": {"effect": "fade"}, "bg": {"type": "color", "color": "#0a0a0a"}}})
    assert "cz-rv--fade" in html and "--cz-bg-color:#0a0a0a" in html
    assert "RT.get('/reviews')" in html  # widget script intact
