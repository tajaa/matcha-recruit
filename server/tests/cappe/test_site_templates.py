"""Site-template catalog drift gate.

Pure (registry + renderer are stdlib):
  ./venv/bin/python -m pytest tests/cappe/test_site_templates.py -q

Templates are data that only ever meets a user AFTER it has been cloned and
rendered, so a template referencing a renamed block field, a dead design key,
a retired directory category, or a third-party image host would fail in front
of a customer. This file fails it here instead. Modelled on
`test_section_presets.py`: every block through the REAL add_block validation
with nothing filtered, every page through `render_site_html` — gated as the
free plan AND ungated as a paid one, because every template must look finished
both ways.
"""
import json
import os
import re
from types import SimpleNamespace

import pytest

os.environ.setdefault("LIVE_API", "test-key")
os.environ.setdefault("DATABASE_URL", "postgresql://test:test@localhost/test")
os.environ.setdefault("JWT_SECRET_KEY", "test-secret-key-cappe")

from app.cappe.services.design_gate import gate_content, gate_theme  # noqa: E402
from app.cappe.services.directory import CATEGORY_SLUGS  # noqa: E402
from app.cappe.services.merlin.ops import validate_ops  # noqa: E402
from app.cappe.services.render import render_site_html  # noqa: E402
from app.cappe.services.site_templates import (  # noqa: E402
    BUSINESS_NAME,
    SITE_TEMPLATES,
    TEMPLATES_BY_SLUG,
    clone_structure,
    get_template,
    list_templates,
    template_summary,
    template_theme,
)
from app.cappe.services.site_templates._shared import (  # noqa: E402
    find_tokens,
    substitute_tokens,
)
from app.cappe.services.site_templates.imagery import (  # noqa: E402
    IMAGE_MANIFEST,
    PLACEHOLDER_PATH,
    image_url,
)
from app.cappe.services.site_templates.preview import (
    render_template_preview,  # noqa: E402
)
from app.cappe.services.theme_presets import FONT_PAIRINGS  # noqa: E402

FREE = "free"
PAID = "business"

_THEME_COLOR_KEYS = {"bg", "surface", "text", "muted", "border", "brand", "brandText", "accent"}
_HEX = re.compile(r"^#[0-9a-fA-F]{6}$")


def _blocks(t):
    for p in t.pages:
        for i, b in enumerate(p["content"]["blocks"]):
            yield p, i, b


def _strings(value):
    if isinstance(value, str):
        yield value
    elif isinstance(value, list):
        for v in value:
            yield from _strings(v)
    elif isinstance(value, dict):
        for v in value.values():
            yield from _strings(v)


def _ids(items):
    return [getattr(t, "slug", t) for t in items]


# --- catalog shape -------------------------------------------------------------

def test_catalog_is_non_empty_with_unique_slugs():
    slugs = [t.slug for t in SITE_TEMPLATES]
    assert slugs and len(slugs) == len(set(slugs))
    assert all(re.fullmatch(r"[a-z0-9-]+", s) for s in slugs)
    assert TEMPLATES_BY_SLUG == {t.slug: t for t in SITE_TEMPLATES}


def test_every_template_sits_in_a_discover_category():
    """`category` must be a directory slug — the gallery filter chips and the
    seeded `directory_category` both come from the same fixed taxonomy."""
    for t in SITE_TEMPLATES:
        assert t.category in CATEGORY_SLUGS, (t.slug, t.category)


def test_every_discover_category_has_at_least_one_template():
    covered = {t.category for t in SITE_TEMPLATES}
    missing = sorted(CATEGORY_SLUGS - covered)
    assert not missing, f"directory categories with no template: {missing}"


def test_catalog_is_not_mostly_dark():
    light = sum(t.mode == "light" for t in SITE_TEMPLATES)
    assert light / len(SITE_TEMPLATES) >= 0.4, f"only {light}/{len(SITE_TEMPLATES)} light templates"


def test_every_template_has_a_home_page_first_and_unique_page_slugs():
    for t in SITE_TEMPLATES:
        slugs = [p["slug"] for p in t.pages]
        assert slugs and slugs[0] == "home", t.slug
        assert len(slugs) == len(set(slugs)), (t.slug, slugs)
        for p in t.pages:
            assert p["content"]["blocks"], (t.slug, p["slug"], "empty page")


def test_theme_base_layer_is_complete_and_hex():
    """The free plan gets `gate_theme(theme)`; it must not fall back to the
    renderer's defaults for any token — a template's look is deliberate."""
    heading_fonts = {h for h, _ in FONT_PAIRINGS} | {b for _, b in FONT_PAIRINGS}
    for t in SITE_TEMPLATES:
        base = gate_theme(t.theme, FREE)
        colors = base.get("colors") or {}
        assert set(colors) >= _THEME_COLOR_KEYS, (t.slug, sorted(_THEME_COLOR_KEYS - set(colors)))
        assert all(_HEX.match(v) for v in colors.values()), (t.slug, colors)
        assert base.get("mode") in ("light", "dark"), t.slug
        for key in ("radius", "heroStyle", "navStyle"):
            assert base.get(key), (t.slug, key)
        fonts = base.get("fonts") or {}
        # Fonts the editor's pairing picker knows, so the Design drawer can
        # show the template's own pair rather than "custom".
        assert fonts.get("heading") in heading_fonts, (t.slug, fonts)
        assert fonts.get("body") in heading_fonts, (t.slug, fonts)
        # Nothing premium survives the gate; a template never sets `preset`
        # (it is not one) — `template_theme` adds the `template` marker.
        assert not ({"style", "type", "premium"} & set(base)), t.slug
        assert "preset" not in t.theme, t.slug


# --- block vocabulary drift gate -----------------------------------------------

def test_every_block_expands_through_add_block_with_nothing_filtered():
    """content == what the real add_block validation keeps, and design == what
    `_clean_design_bag` keeps. A dropped key means the template drifted from
    BLOCK_FIELDS / SELECT_OPTIONS / DESIGN_GROUPS."""
    for t in SITE_TEMPLATES:
        for p, i, b in _blocks(t):
            content = {k: v for k, v in b.items() if k not in ("type", "_design")}
            op = {"op": "add_block", "type": b["type"], "at": 0, "content": content}
            design = b.get("_design")
            if design is not None:
                op["design"] = design
            valid, rejected = validate_ops([op], [], premium=True)
            where = (t.slug, p["slug"], i, b["type"])
            assert len(valid) == 1 and not rejected, (where, rejected)
            assert valid[0]["content"] == content, (where, "content filtered — field drift")
            if design is not None:
                assert valid[0].get("design") == design, (where, "design filtered — design drift")


def test_internal_links_point_at_pages_that_exist():
    """A CTA at `/p/menu` on a template with no menu page is a 404 on day one."""
    for t in SITE_TEMPLATES:
        slugs = {p["slug"] for p in t.pages}
        for p, i, b in _blocks(t):
            for key in ("ctaHref", "cta2Href"):
                href = b.get(key)
                if not href:
                    continue
                if href.startswith("/p/"):
                    assert href[3:] in slugs, (t.slug, p["slug"], i, href)
                else:
                    assert href.startswith("#"), (t.slug, p["slug"], i, href)
            for plan in b.get("plans") or []:
                href = plan.get("ctaHref")
                if href and href.startswith("/p/"):
                    assert href[3:] in slugs, (t.slug, p["slug"], i, href)


# --- copy hygiene ----------------------------------------------------------------

def test_copy_invents_no_facts_and_uses_no_outside_hosts():
    """No third-party image hosts (the picsum era), no plain-http URLs, no
    email addresses (root CLAUDE.md test-data rule: a realistic fake domain
    bounces for real), and no invented history ("Est. 2014") that a real
    business would ship by accident."""
    year = re.compile(r"\b(19|20)\d{2}\b")
    for t in SITE_TEMPLATES:
        for s in _strings({"theme": t.theme, "pages": list(t.pages), "desc": t.description}):
            assert "picsum" not in s, (t.slug, s)
            assert "http://" not in s, (t.slug, s)
            assert "@" not in s or BUSINESS_NAME in s, (t.slug, s)
            assert not year.search(s), (t.slug, s)
            assert not s.lstrip().lower().startswith("est."), (t.slug, s)


def test_images_resolve_through_the_manifest_only():
    """Every image slot must be a manifest URL (generated) or the self-hosted
    placeholder — never anything else — and every manifest key with a prompt
    must be used by some template (an orphan prompt is a wasted generation)."""
    used: set[str] = set()
    for t in SITE_TEMPLATES:
        for p, i, b in _blocks(t):
            urls = [b.get("image")]
            urls += [x.get("url") for x in b.get("images") or [] if isinstance(x, dict)]
            urls += [x.get("image") for x in b.get("items") or [] if isinstance(x, dict)]
            for u in urls:
                if u is None:
                    continue
                assert isinstance(u, str) and u, (t.slug, p["slug"], i)
                m = re.fullmatch(PLACEHOLDER_PATH.replace("{key}", r"([a-z0-9-]+)"), u)
                if m:
                    assert m.group(1) in IMAGE_MANIFEST, (t.slug, u)
                    used.add(m.group(1))
                else:
                    assert u.startswith("https://"), (t.slug, p["slug"], i, u)
                    used.update(k for k in IMAGE_MANIFEST if image_url(k) == u)
    orphans = sorted(set(IMAGE_MANIFEST) - used)
    assert not orphans, f"manifest keys no template uses: {orphans}"


def test_image_url_rejects_unknown_keys():
    with pytest.raises(KeyError):
        image_url("not-a-real-slot")


def test_every_home_hero_names_the_business():
    """The one personalisation we do deterministically: the business name.
    Each home page must use the token somewhere a visitor reads first, and
    nothing else may use a token we don't substitute."""
    for t in SITE_TEMPLATES:
        home = t.page("home")
        assert BUSINESS_NAME in json.dumps(home["content"]), (t.slug, "home page never names the business")
        tokens = find_tokens({"pages": list(t.pages), "theme": t.theme})
        assert tokens <= {"business_name"}, (t.slug, tokens)


def test_substitute_tokens_replaces_everywhere_and_copies():
    src = {"a": "Hi {{business_name}}", "b": ["{{business_name}}!", {"c": "{{ business_name }}"}], "d": 3}
    out = substitute_tokens(src, {"business_name": "Po Coffee Co"})
    assert out == {"a": "Hi Po Coffee Co", "b": ["Po Coffee Co!", {"c": "Po Coffee Co"}], "d": 3}
    assert src["a"] == "Hi {{business_name}}"  # input untouched
    assert substitute_tokens("{{unknown}}", {}) == "{{unknown}}"


# --- render smoke: gated and ungated -------------------------------------------

@pytest.mark.parametrize("plan", [FREE, PAID])
def test_every_page_smoke_renders_for_plan(plan):
    for t in SITE_TEMPLATES:
        theme, pages = clone_structure(t, business_name="Po Coffee Co", plan=plan)
        site = {"slug": "po", "name": "Po Coffee Co", "theme_config": theme, "meta_config": {}}
        for p in pages:
            html = render_site_html(site, p, t.nav, preview=True)
            assert "<section" in html, (t.slug, p["slug"], plan)
            assert "{{" not in html, (t.slug, p["slug"], "unsubstituted token")
            assert "Po Coffee Co" in html, (t.slug, p["slug"])
        # The gate is the plan boundary: free loses every premium key and every
        # `_design` bag; paid keeps them (when the template has any).
        has_design = any("_design" in b for _, _, b in _blocks(t))
        flat = json.dumps(pages)
        if plan == FREE:
            assert "_design" not in flat, t.slug
            assert not ({"style", "type", "premium"} & set(theme)), t.slug
        else:
            assert ("_design" in flat) == has_design, t.slug
            assert theme.get("premium") is True, (t.slug, "premium polish missing")
        assert theme["template"] == t.slug


def test_clone_is_gated_like_the_editor_save_path():
    t = SITE_TEMPLATES[0]
    free_theme, free_pages = clone_structure(t, business_name="X", plan=FREE)
    assert free_theme == {**gate_theme(t.theme, FREE), "template": t.slug}
    for p, src in zip(free_pages, t.pages):
        assert p["content"] == gate_content(substitute_tokens(src["content"], {"business_name": "X"}), FREE)


def test_clone_falls_back_to_the_sample_name_for_a_blank_business_name():
    t = SITE_TEMPLATES[0]
    _, pages = clone_structure(t, business_name="   ", plan=FREE)
    assert t.sample_name in json.dumps(pages)


def test_template_theme_does_not_mutate_the_registry():
    t = SITE_TEMPLATES[0]
    theme = template_theme(t, plan=PAID)
    theme["colors"]["bg"] = "#000000"
    theme["template"] = "mutated"
    assert t.theme["colors"]["bg"] != "#000000"
    assert "template" not in t.theme


# --- registry API ----------------------------------------------------------------

def test_list_templates_filters_by_category_and_get_template_is_safe():
    cat = SITE_TEMPLATES[0].category
    assert all(t.category == cat for t in list_templates(cat))
    assert _ids(list_templates()) == _ids(SITE_TEMPLATES)
    assert get_template("nope") is None
    assert get_template(None) is None
    assert get_template(SITE_TEMPLATES[0].slug) is SITE_TEMPLATES[0]


def test_template_summary_is_the_gallery_card_shape():
    for t in SITE_TEMPLATES:
        card = template_summary(t)
        assert set(card) == {
            "slug", "name", "category", "category_label", "tags", "description",
            "mode", "heading_font", "swatch", "pages",
        }
        assert card["category_label"] and card["category_label"] != card["category"]
        assert set(card["swatch"]) == {"bg", "surface", "brand", "text"}
        assert card["pages"][0] == {"slug": "home", "title": "Home"}
        assert not ({"is_premium", "price_cents", "preview_image_url", "id"} & set(card))


# --- preview ---------------------------------------------------------------------

def test_preview_renders_any_page_with_browsable_links():
    render_template_preview.cache_clear()
    t = next(t for t in SITE_TEMPLATES if len(t.pages) > 1)
    other = t.pages[1]["slug"]
    html = render_template_preview(t.slug, other, False)
    assert html and "<section" in html
    # Nav + CTA links stay inside the preview instead of 404ing on the API host.
    assert 'href="/p/' not in html and 'href="/"' not in html
    assert f'href="?page={other}"' in html or 'href="?page=home"' in html
    assert t.sample_name in html
    assert '"preview": true' in html  # widgets draw placeholders, not API calls


def test_preview_premium_flag_selects_the_layer_and_threads_through_links():
    render_template_preview.cache_clear()
    t = next(t for t in SITE_TEMPLATES if t.theme.get("premium"))
    free_html = render_template_preview(t.slug, "home", False)
    paid_html = render_template_preview(t.slug, "home", True)
    # The stylesheet always carries the premium rules; the BODY class is what
    # turns the layer on, so that is what the plan boundary is asserted on.
    assert '<body class="cz-premium' not in free_html
    assert '<body class="cz-premium' in paid_html
    assert "&premium=1" in paid_html and "&premium=1" not in free_html


def test_preview_404s_unknown_template_or_page_and_is_memoised():
    render_template_preview.cache_clear()
    assert render_template_preview("nope", "home", False) is None
    assert render_template_preview(SITE_TEMPLATES[0].slug, "no-such-page", False) is None
    a = render_template_preview(SITE_TEMPLATES[0].slug, "home", False)
    b = render_template_preview(SITE_TEMPLATES[0].slug, "home", False)
    assert a is b  # same object → served from the cache


# --- route: gallery + placeholder -----------------------------------------------

@pytest.mark.asyncio
async def test_templates_route_lists_cards_and_filters_by_known_category():
    from app.cappe.routes import templates as routes

    cards = await routes.list_templates(category=None)
    assert [c["slug"] for c in cards] == [t.slug for t in SITE_TEMPLATES]
    cat = SITE_TEMPLATES[0].category
    assert all(c["category"] == cat for c in await routes.list_templates(category=cat))
    assert await routes.list_templates(category="not-a-category") == []


def test_placeholder_svg_is_deterministic_text_free_art():
    from app.cappe.routes.templates import _placeholder_svg

    a = _placeholder_svg("saveur-hero")
    assert a == _placeholder_svg("saveur-hero")
    assert a != _placeholder_svg("onyx-hero")
    assert a.startswith("<svg") and "<text" not in a and "<script" not in a


@pytest.mark.asyncio
async def test_placeholder_route_only_serves_manifest_keys(monkeypatch):
    from app.cappe.routes import templates as routes
    from fastapi import HTTPException

    async def _no_limit(*_a, **_k):
        return None

    monkeypatch.setattr(routes, "check_rate_limit", _no_limit)
    request = SimpleNamespace(client=SimpleNamespace(host="203.0.113.9"), headers={})
    res = await routes.template_placeholder(next(iter(IMAGE_MANIFEST)), request)
    assert res.media_type == "image/svg+xml"
    assert "immutable" in res.headers["cache-control"]
    with pytest.raises(HTTPException) as exc:
        await routes.template_placeholder("../etc/passwd", request)
    assert exc.value.status_code == 404
