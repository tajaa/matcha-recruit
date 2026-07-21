"""Phase 4 section presets — apply_section_preset + add_block's design bag.

Pure (registries + render.py are stdlib):
  ./venv/bin/python -m pytest tests/cappe/test_section_presets.py -q

The library drift-gate is the important part: every preset must expand through
the REAL add_block validation with nothing filtered (a preset referencing a
renamed block field or dead design key fails here, not in front of a user) and
must smoke-render through render_site_html.
"""
import os

os.environ.setdefault("LIVE_API", "test-key")
os.environ.setdefault("DATABASE_URL", "postgresql://test:test@localhost/test")
os.environ.setdefault("JWT_SECRET_KEY", "test-secret-key-cappe")

from app.cappe.services.merlin_ops import validate_ops  # noqa: E402
from app.cappe.services.render import render_site_html  # noqa: E402
from app.cappe.services.section_presets import PRESETS_BY_KEY, SECTION_PRESETS  # noqa: E402

_BLOCKS: list = []  # apply_section_preset needs no existing blocks


def _apply(key, at=0, **kw):
    return validate_ops([{"op": "apply_section_preset", "preset": key, "at": at}], _BLOCKS, **kw)


# --- library drift-gate -------------------------------------------------------

def test_every_preset_expands_cleanly_with_nothing_filtered():
    """content == the library's content and design == the library's design after
    the real add_block validation ran — i.e. zero fields were dropped. A drop
    means the library drifted from BLOCK_FIELDS/DESIGN_GROUPS."""
    for p in SECTION_PRESETS:
        valid, rejected = _apply(p.key)
        assert len(valid) == 1 and not rejected, (p.key, rejected)
        op = valid[0]
        assert op["op"] == "add_block" and op["type"] == p.block_type, p.key
        assert op["content"] == p.content, f"{p.key}: content filtered — library drifted"
        if p.design:
            assert op["design"] == p.design, f"{p.key}: design filtered — library drifted"
        assert op["preset"] == p.key  # provenance survives for the client summary


def test_every_preset_smoke_renders():
    site = {"slug": "d", "name": "D", "theme_config": {"mode": "light", "premium": True}}
    for p in SECTION_PRESETS:
        valid, _ = _apply(p.key)
        op = valid[0]
        block = {"id": "b", "type": op["type"], **op["content"], "_design": op.get("design", {})}
        html = render_site_html(site, {"slug": "home", "title": "H", "content": {"blocks": [block]}},
                                [{"slug": "home", "title": "Home"}])
        assert "<section" in html, p.key
        if p.design:
            assert "cz-design" in html, p.key  # the design bag actually took effect


def test_library_data_is_not_mutated_by_expansion():
    """Expansion deepcopies — mutating an expanded op must not corrupt the
    shared library for the next request."""
    first, _ = _apply("features-grid")
    first[0]["content"]["heading"] = "MUTATED"
    first[0]["design"]["motion"]["effect"] = "zoom"
    second, _ = _apply("features-grid")
    assert second[0]["content"]["heading"] != "MUTATED"
    assert second[0]["design"]["motion"]["effect"] == "fade-up"


# --- op validation ------------------------------------------------------------

def test_unknown_preset_rejected_with_the_known_names():
    valid, rejected = _apply("not-a-preset")
    assert not valid and "unknown preset" in rejected[0]["reason"]
    assert "hero-impact" in rejected[0]["reason"]


def test_missing_at_rejected():
    valid, rejected = validate_ops([{"op": "apply_section_preset", "preset": "faq-clean"}], _BLOCKS)
    assert not valid and "'at'" in rejected[0]["reason"]


def test_non_premium_gets_content_without_design():
    valid, rejected = _apply("stats-band-dark", premium=False)
    assert len(valid) == 1 and not rejected
    op = valid[0]
    assert op["content"] == PRESETS_BY_KEY["stats-band-dark"].content
    assert "design" not in op  # stripped: gate_content would drop it on save anyway


# --- add_block design bag (the enabling primitive) ----------------------------

def test_add_block_keeps_valid_design_and_drops_invalid_entries():
    valid, rejected = validate_ops([{
        "op": "add_block", "type": "text", "at": 0, "content": {"heading": "T"},
        "design": {
            "motion": {"effect": "fade-up", "easing": "boing", "bogus": 1},   # easing invalid, bogus unknown
            "nope": {"x": 1},                                                  # unknown group
            "colors": {"accent": "#112233", "heading": None},                  # null dropped
        },
    }], _BLOCKS)
    assert len(valid) == 1 and not rejected
    assert valid[0]["design"] == {"motion": {"effect": "fade-up"}, "colors": {"accent": "#112233"}}


def test_add_block_design_stripped_for_non_premium():
    valid, _ = validate_ops([{
        "op": "add_block", "type": "text", "at": 0,
        "design": {"motion": {"effect": "fade"}},
    }], _BLOCKS, premium=False)
    assert len(valid) == 1 and "design" not in valid[0]


def test_add_block_all_invalid_design_removes_the_key():
    valid, _ = validate_ops([{
        "op": "add_block", "type": "text", "at": 0,
        "design": {"motion": {"effect": "teleport"}},
    }], _BLOCKS)
    assert len(valid) == 1 and "design" not in valid[0]
