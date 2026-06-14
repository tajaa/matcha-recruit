"""Cappe render: business identity + SEO from meta_config (head tags + footer).
Pure render — no DB, no app boot.

Run from server/:  ./venv/bin/python -m pytest tests/cappe/test_cappe_render_meta.py -q
"""
import os

os.environ.setdefault("LIVE_API", "test-key")
os.environ.setdefault("DATABASE_URL", "postgresql://test:test@localhost/test")
os.environ.setdefault("JWT_SECRET_KEY", "test-secret-key-cappe")

from app.cappe.services.render import render_site_html  # noqa: E402


def _render(meta: dict) -> str:
    site = {"slug": "d", "name": "Studio", "theme_config": None, "meta_config": meta, "timezone": "UTC"}
    page = {"title": "Home", "content": {"blocks": [{"type": "text", "body": "hi"}]}}
    return render_site_html(site, page, [{"slug": "home", "title": "Home"}])


def test_seo_head_tags():
    h = _render({"seo": {"title": "Best Pilates NYC", "description": "Private sessions.", "og_image": "https://cdn.example.com/og.jpg"},
                 "favicon_url": "https://cdn.example.com/fav.png"})
    assert "<title>Best Pilates NYC</title>" in h
    assert 'name="description" content="Private sessions."' in h
    assert 'property="og:image" content="https://cdn.example.com/og.jpg"' in h
    assert 'rel="icon" href="https://cdn.example.com/fav.png"' in h


def test_title_falls_back_to_site_and_page():
    h = _render({})
    assert "<title>Studio — Home</title>" in h


def test_footer_contact_and_social():
    h = _render({"contact_email": "hi@studio.test", "contact_phone": "+1 555 0100",
                 "business_hours": "Mon–Fri 9–5",
                 "social": {"instagram": "https://instagram.com/x", "website": "https://s.test"}})
    assert "mailto:hi@studio.test" in h
    assert "tel:+15550100" in h          # spaces stripped in the tel: href
    assert "Mon–Fri 9–5" in h
    assert "instagram.com/x" in h and ">Instagram<" in h


def test_footer_blocks_dangerous_social_url():
    h = _render({"social": {"x": "javascript:alert(1)", "instagram": "https://instagram.com/ok"}})
    assert "javascript:alert" not in h
    assert "instagram.com/ok" in h


def test_footer_escapes_contact_html():
    h = _render({"contact_address": "<script>evil()</script>"})
    assert "<script>evil()</script>" not in h
    assert "&lt;script&gt;" in h


def _render_theme(theme: dict) -> str:
    site = {"slug": "d", "name": "Studio", "theme_config": theme, "meta_config": {}, "timezone": "UTC"}
    page = {"title": "Home", "content": {"blocks": [{"type": "hero", "heading": "Hi", "eyebrow": "Studio"}]}}
    return render_site_html(site, page, [{"slug": "home", "title": "Home"}])


def test_localbusiness_jsonld_from_hours_and_address():
    site = {"slug": "c", "name": "Bean There", "theme_config": None, "timezone": "America/Los_Angeles",
            "meta_config": {"contact_address": "1 Main St", "contact_phone": "+1 555 0100",
                            "geo": {"lat": 37.77, "lng": -122.41},
                            "hours": [{"day": 0, "open": "09:00", "close": "17:00", "closed": False}]}}
    h = render_site_html(site, {"title": "Home", "content": {"blocks": []}}, [{"slug": "home", "title": "Home"}])
    assert 'application/ld+json' in h and '"LocalBusiness"' in h
    assert '"openingHoursSpecification"' in h and 'schema.org/Monday' in h
    assert '"GeoCoordinates"' in h


def test_map_and_hours_blocks_render():
    site = {"slug": "c", "name": "Cafe", "theme_config": None, "timezone": "UTC",
            "meta_config": {"contact_address": "1 Main St, SF", "geo": {"lat": 1.0, "lng": 2.0},
                            "hours": [{"day": 0, "open": "08:00", "close": "16:00", "closed": False}]}}
    page = {"title": "Home", "content": {"blocks": [{"type": "map", "heading": "Find us"}, {"type": "hours"}]}}
    h = render_site_html(site, page, [{"slug": "home", "title": "Home"}])
    assert "cz-map" in h and "maps/search/?api=1" in h and "openstreetmap.org/export/embed.html" in h
    # "Open now" is computed client-side (cache-safe), so the badge ships as JS, not a baked value.
    assert "data-opennow" in h and "Intl.DateTimeFormat" in h
    assert "cz-hours__row" in h and "Monday" in h


def test_premium_theme_adds_layer():
    h = _render_theme({"mode": "dark", "premium": True, "colors": {"brand": "#C6F16B"}})
    assert '<body class="cz-premium">' in h
    assert "czGlow" in h                         # glow keyframes present
    assert "classList.add('cz-js')" in h         # scroll-reveal script injected


def test_non_premium_theme_has_no_layer():
    h = _render_theme({"mode": "dark"})
    assert '<body class="">' in h
    assert "classList.add('cz-js')" not in h     # reveal script only for premium


def test_fancy_alias_enables_premium():
    h = _render_theme({"fancy": True})
    assert '<body class="cz-premium">' in h


def test_empty_meta_renders_minimal_footer():
    h = _render({})
    assert "© Studio" in h
    # No footer social/contact markup when none set (the classes still exist in CSS).
    assert '<div class="cz-foot-social">' not in h
    assert '<div class="cz-foot-contact">' not in h
