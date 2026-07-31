"""Merlin's unified highlight selection contract (highlight-driven precision
design, Phase 1) — `_resolve_field_text`/`_resolve_element_text`,
`build_selection_prompt_line`'s exact-match/re-anchor/stale ladder, and the
render-side `data-cz-field` coverage every block type needs for the contract
to be able to name anything other than a hero heading.

Run from server/:  ./venv/bin/python -m pytest tests/cappe/test_merlin_selection.py -q
"""
import os

os.environ.setdefault("LIVE_API", "test-key")
os.environ.setdefault("DATABASE_URL", "postgresql://test:test@localhost/test")
os.environ.setdefault("JWT_SECRET_KEY", "test-secret-key-cappe")

from app.cappe.services import render as R  # noqa: E402
from app.cappe.services.merlin.turn import (  # noqa: E402
    _resolve_element_text,
    _resolve_field_text,
    build_selection_prompt_line,
)

# --- _resolve_field_text -----------------------------------------------------

_BLOCKS = [
    {"id": "b1", "type": "hero", "heading": "Fresh coffee daily"},
    {"id": "b2", "type": "faq", "items": [{"q": "Q1", "a": "A1"}, {"q": "Q2", "a": "A2"}]},
]


def test_resolve_field_text_scalar():
    assert _resolve_field_text(_BLOCKS, "b1", "heading") == "Fresh coffee daily"


def test_resolve_field_text_list_item_dot_path():
    assert _resolve_field_text(_BLOCKS, "b2", "items.1.a") == "A2"


def test_resolve_field_text_out_of_range_index():
    assert _resolve_field_text(_BLOCKS, "b2", "items.9.a") is None


def test_resolve_field_text_missing_block():
    assert _resolve_field_text(_BLOCKS, "nope", "heading") is None


def test_resolve_field_text_non_dict_block_in_list_is_skipped_not_raised():
    blocks = ["not-a-dict", {"id": "b1", "type": "hero", "heading": "x"}]
    assert _resolve_field_text(blocks, "b1", "heading") == "x"


def test_resolve_field_text_non_string_leaf():
    blocks = [{"id": "b1", "type": "gallery", "images": [1, 2]}]
    assert _resolve_field_text(blocks, "b1", "images.0") is None


# --- _resolve_element_text ----------------------------------------------------

_CANVAS_BLOCKS = [
    {"id": "cv1", "type": "canvas", "elements": [{"id": "el1", "kind": "heading", "text": "Hi"}]},
]


def test_resolve_element_text_found():
    assert _resolve_element_text(_CANVAS_BLOCKS, "cv1", "el1") == "Hi"


def test_resolve_element_text_missing_element():
    assert _resolve_element_text(_CANVAS_BLOCKS, "cv1", "nope") is None


def test_resolve_element_text_missing_block():
    assert _resolve_element_text(_CANVAS_BLOCKS, "nope", "el1") is None


# --- build_selection_prompt_line ---------------------------------------------

def test_exact_range_match():
    sel = {"block": "b1", "field": "heading", "start": 0, "end": 5, "text": "Fresh", "kind": "text"}
    line = build_selection_prompt_line(sel, _BLOCKS, None)
    assert 'characters 0-5 ("Fresh")' in line
    assert 'field "heading"' in line
    assert "not the whole field" in line


def test_drifted_offsets_reanchor_by_text():
    # Offsets claim 10-15 but "Fresh" actually sits at 0-5 now (the field
    # changed since the click) — the text substring still exists, so this
    # re-anchors instead of degrading to whole-field.
    sel = {"block": "b1", "field": "heading", "start": 10, "end": 15, "text": "Fresh", "kind": "text"}
    line = build_selection_prompt_line(sel, _BLOCKS, None)
    assert 're-anchored by text match' in line
    assert 'characters 0-5 ("Fresh")' in line


def test_text_gone_degrades_to_whole_field():
    sel = {"block": "b1", "field": "heading", "start": 0, "end": 6, "text": "Nomore", "kind": "text"}
    line = build_selection_prompt_line(sel, _BLOCKS, None)
    assert "may be stale" in line
    assert "WHOLE field" in line


def test_field_with_no_range_is_whole_field_selection():
    sel = {"block": "b1", "field": "heading", "start": None, "end": None, "text": None, "kind": "text"}
    line = build_selection_prompt_line(sel, _BLOCKS, None)
    assert 'field "heading"' in line
    assert "whole field is" in line


def test_no_field_is_block_level_selection():
    sel = {"block": "b1", "field": None, "start": None, "end": None, "text": None, "kind": "element"}
    line = build_selection_prompt_line(sel, _BLOCKS, None)
    assert "block b1" in line
    assert "no specific field" in line


def test_canvas_element_addressed_with_canvas_update():
    sel = {"block": "cv1", "field": None, "element": "el1", "start": 0, "end": 2,
           "text": "Hi", "kind": "text"}
    line = build_selection_prompt_line(sel, _CANVAS_BLOCKS, None)
    assert 'canvas element "el1"' in line
    assert "canvas_update" in line
    assert "not set_field" in line


def test_canvas_element_re_anchors_like_a_field():
    sel = {"block": "cv1", "field": None, "element": "el1", "start": 5, "end": 7,
           "text": "Hi", "kind": "text"}
    line = build_selection_prompt_line(sel, _CANVAS_BLOCKS, None)
    assert "re-anchored by text match" in line
    assert "canvas_update" in line


def test_missing_block_falls_back_to_selected_block():
    sel = {"block": "ghost", "field": "heading", "start": 0, "end": 3, "text": "abc", "kind": "text"}
    line = build_selection_prompt_line(sel, _BLOCKS, "b1")
    assert "SELECTED SECTION: id=b1" in line
    assert "ghost" not in line


def test_missing_block_and_no_selected_block_falls_back_to_nothing():
    sel = {"block": "ghost", "field": "heading", "start": 0, "end": 3, "text": "abc", "kind": "text"}
    line = build_selection_prompt_line(sel, _BLOCKS, None)
    assert "SELECTED: nothing" in line


def test_no_selection_falls_back_to_legacy_selected_block():
    line = build_selection_prompt_line(None, _BLOCKS, "b1")
    assert "SELECTED SECTION: id=b1" in line


def test_no_selection_and_no_selected_block_is_nothing():
    line = build_selection_prompt_line(None, _BLOCKS, None)
    assert "SELECTED: nothing" in line


# --- render coverage: every block type tags its text fields -----------------
# One fixture per type, populated so every text/textarea field this type
# supports actually renders. Values are the field's own dotted path, so the
# assertion just has to find `data-cz-field="<path>"` immediately followed by
# that same string as the escaped text content — catching both "never tagged"
# and "tagged wrapper contains extra sibling text" (the pricing price/period,
# testimonial curly-quote bugs this suite exists to pin).
_COVERAGE_FIXTURES: dict[str, dict] = {
    "hero": {"type": "hero", "style": "centered", "eyebrow": "eyebrow", "heading": "heading",
             "subheading": "subheading", "cta": "cta", "cta2": "cta2"},
    "features": {"type": "features", "heading": "heading", "subheading": "subheading",
                 "items": [{"title": "items.0.title", "body": "items.0.body"}]},
    "gallery": {"type": "gallery", "heading": "heading", "subheading": "subheading",
                "images": [{"url": "https://x.test/a.png", "caption": "images.0.caption"}]},
    "pricing": {"type": "pricing", "heading": "heading", "subheading": "subheading",
                "plans": [{"name": "plans.0.name", "price": "plans.0.price", "period": "mo",
                           "cta": "plans.0.cta", "ctaHref": "https://x.test"}]},
    "testimonial": {"type": "testimonial", "heading": "heading", "subheading": "subheading",
                    "items": [{"quote": "items.0.quote", "author": "items.0.author", "role": "items.0.role"}]},
    "cta": {"type": "cta", "heading": "heading", "subheading": "subheading", "cta": "cta",
            "ctaHref": "https://x.test"},
    "menu": {"type": "menu", "heading": "heading", "subheading": "subheading",
             "sections": [{"name": "sections.0.name",
                           "items": [{"name": "sections.0.items.0.name", "price": "sections.0.items.0.price",
                                      "description": "sections.0.items.0.description"}]}]},
    "posts": {"type": "posts", "heading": "heading", "subheading": "subheading",
              "items": [{"date": "items.0.date", "title": "items.0.title", "excerpt": "items.0.excerpt",
                         "slug": "s"}]},
    "stats": {"type": "stats", "heading": "heading", "subheading": "subheading",
              "items": [{"value": "items.0.value", "label": "items.0.label"}]},
    "logos": {"type": "logos", "heading": "heading", "items": [{"name": "items.0.name"}]},
    "faq": {"type": "faq", "heading": "heading", "subheading": "subheading",
            "items": [{"q": "items.0.q", "a": "items.0.a"}]},
    "bento": {"type": "bento", "heading": "heading", "subheading": "subheading",
              "items": [{"title": "items.0.title", "body": "items.0.body"}]},
    "split": {"type": "split", "eyebrow": "eyebrow", "heading": "heading", "body": "body",
              "bullets": ["bullets.0"], "cta": "cta", "ctaHref": "https://x.test"},
    "credentials": {"type": "credentials", "heading": "heading", "subheading": "subheading",
                    "items": [{"title": "items.0.title", "detail": "items.0.detail"}]},
    "reviews": {"type": "reviews", "heading": "heading", "subheading": "subheading"},
    "map": {"type": "map", "heading": "heading", "address": "address"},
    "hours": {"type": "hours", "heading": "heading", "subheading": "subheading"},
    "text": {"type": "text", "heading": "heading", "body": "body"},
    "contact": {"type": "contact", "heading": "heading", "subheading": "subheading",
                "fields": ["name", "email", "message"]},
    "store": {"type": "store", "heading": "heading", "subheading": "subheading"},
    "booking": {"type": "booking", "heading": "heading", "subheading": "subheading"},
    "newsletter": {"type": "newsletter", "heading": "heading", "subheading": "subheading"},
}

# The text/textarea fields each fixture above should tag — same keys the
# fixture's placeholder VALUES are named after, so `data-cz-field="X">X<`
# proves both presence and exact-match (no leaking sibling text into the
# tagged element).
_EXPECTED_FIELDS: dict[str, list[str]] = {
    "hero": ["eyebrow", "heading", "subheading", "cta", "cta2"],
    "features": ["heading", "subheading", "items.0.title", "items.0.body"],
    "gallery": ["heading", "subheading", "images.0.caption"],
    "pricing": ["heading", "subheading", "plans.0.name", "plans.0.price", "plans.0.cta"],
    "testimonial": ["heading", "subheading", "items.0.quote", "items.0.author", "items.0.role"],
    "cta": ["heading", "subheading", "cta"],
    "menu": ["heading", "subheading", "sections.0.name", "sections.0.items.0.name",
             "sections.0.items.0.price", "sections.0.items.0.description"],
    "posts": ["heading", "subheading", "items.0.date", "items.0.title", "items.0.excerpt"],
    "stats": ["heading", "subheading", "items.0.value", "items.0.label"],
    "logos": ["heading", "items.0.name"],
    "faq": ["heading", "subheading", "items.0.q", "items.0.a"],
    "bento": ["heading", "subheading", "items.0.title", "items.0.body"],
    "split": ["eyebrow", "heading", "body", "cta", "bullets.0"],
    "credentials": ["heading", "subheading", "items.0.title", "items.0.detail"],
    "reviews": ["heading", "subheading"],
    "map": ["heading", "address"],
    "hours": ["heading", "subheading"],
    "text": ["heading", "body"],
    "contact": ["heading", "subheading"],
    "store": ["heading", "subheading"],
    "booking": ["heading", "subheading"],
    "newsletter": ["heading", "subheading"],
}


def _tokens_for(btype: str):
    # `t["meta"]`/`t["locations"]` aren't part of `_tokens()`'s theme-config
    # input — `render/page.py` mutates them onto the tokens dict separately
    # after building it (see `render_site_html`). `_hours` needs a non-empty
    # hours list somewhere in that chain or it renders "" entirely.
    t = R._tokens({})
    if btype == "hours":
        t["meta"] = {"hours": [{"day": 0, "open": "9:00", "close": "17:00"}]}
    return t


def test_every_block_type_tags_its_text_fields_in_editor_mode():
    assert set(_COVERAGE_FIXTURES) == set(_EXPECTED_FIELDS)
    for btype, block in _COVERAGE_FIXTURES.items():
        t = _tokens_for(btype)
        html = R._render_block(block, t, index=0, editable=True)
        for field in _EXPECTED_FIELDS[btype]:
            marker = f'data-cz-field="{field}"'
            assert marker in html, f"{btype}: missing {marker} in editor render"
            # Exact-match sanity: the tagged element's escaped placeholder text
            # (identical to its own field name) must appear right after the
            # opening tag closes — proves no sibling text (a period suffix, a
            # currency span) leaked into the tagged element's textContent,
            # which would break the server's exact-match anchor check.
            tag_start = html.index(marker)
            tag_close = html.index(">", tag_start)
            assert html[tag_close + 1:].startswith(field), (
                f"{btype}.{field}: tagged element's content isn't an exact match "
                "(sibling text leaked into the tagged range)"
            )


def test_every_block_type_publishes_no_field_tags():
    for btype, block in _COVERAGE_FIXTURES.items():
        t = _tokens_for(btype)
        html = R._render_block(block, t, index=0, editable=False)
        assert "data-cz-field" not in html, f"{btype}: leaked data-cz-field into published output"


# --- image-kind fields (separate from the text-only coverage loop above) ----

def test_hero_split_image_is_tagged_image_kind():
    block = {"type": "hero", "style": "split", "heading": "h", "image": "https://x.test/a.png"}
    html = R._render_block(block, R._tokens({}), index=0, editable=True)
    assert 'data-cz-field="image"' in html
    assert 'data-cz-kind="image"' in html


def test_split_block_image_is_tagged_image_kind():
    block = {"type": "split", "heading": "h", "image": "https://x.test/a.png"}
    html = R._render_block(block, R._tokens({}), index=0, editable=True)
    assert 'data-cz-field="image"' in html
    assert 'data-cz-kind="image"' in html


def test_gallery_image_url_is_tagged_image_kind():
    block = {"type": "gallery", "images": [{"url": "https://x.test/a.png", "caption": "c"}]}
    html = R._render_block(block, R._tokens({}), index=0, editable=True)
    assert 'data-cz-field="images.0.url"' in html
    assert 'data-cz-kind="image"' in html


def test_logos_item_image_is_tagged_image_kind():
    block = {"type": "logos", "items": [{"image": "https://x.test/a.png", "name": "n"}]}
    html = R._render_block(block, R._tokens({}), index=0, editable=True)
    assert 'data-cz-field="items.0.image"' in html
    assert 'data-cz-kind="image"' in html


def test_bento_item_image_is_tagged_image_kind():
    block = {"type": "bento", "items": [{"title": "t", "image": "https://x.test/a.png"}]}
    html = R._render_block(block, R._tokens({}), index=0, editable=True)
    assert 'data-cz-field="items.0.image"' in html
    assert 'data-cz-kind="image"' in html
