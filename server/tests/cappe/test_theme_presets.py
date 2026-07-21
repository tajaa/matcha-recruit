"""theme_presets.py is a hand-maintained server mirror of the client's
CAPPE_THEMES (cappeThemes.ts) — the AI-facing subset (id/name/blurb/premium/
mode), so Merlin can be theme-aware without moving client-rendering concerns
(swatch, the full theme_config `config` object) server-side. Drift is silent in
both directions: an id only the client knows can never be suggested by the
model to a preset it's unaware of, and an id only the server knows is offered
in the prompt but `applyThemeOp` will silently skip it client-side.

Pure — no DB, no app boot, no Gemini:
  ./venv/bin/python -m pytest tests/cappe/test_theme_presets.py -q
"""
import os
import pathlib
import re

os.environ.setdefault("LIVE_API", "test-key")
os.environ.setdefault("DATABASE_URL", "postgresql://test:test@localhost/test")
os.environ.setdefault("JWT_SECRET_KEY", "test-secret-key-cappe")

from app.cappe.services.merlin_ops import _v_set_theme, ValidationCtx  # noqa: E402
from app.cappe.services.theme_presets import (  # noqa: E402
    FONT_PAIRINGS,
    PRESET_IDS,
    THEME_PRESETS,
)

_CAPPE_THEMES_TS = pathlib.Path(__file__).resolve().parents[2] / (
    "../client/src/cappe/data/cappeThemes.ts"
)


def _client_source() -> str:
    return _CAPPE_THEMES_TS.resolve().read_text()


def _client_preset_blocks() -> list[str]:
    """Each top-level entry in CAPPE_THEMES, as raw text — bounded by an
    `id: '...'` opener and the following 2-space-indented `},` closer (nested
    `swatch`/`config` objects close at 4-space indent, so they don't match)."""
    source = _client_source()
    return re.findall(r"\{\n\s*id: '[a-z]+',.*?\n  \},", source, re.S)


def test_theme_preset_ids_match_client():
    blocks = _client_preset_blocks()
    client_ids = {re.search(r"id: '([a-z]+)'", b).group(1) for b in blocks}
    assert client_ids == PRESET_IDS, (
        f"theme preset drift — client-only: {sorted(client_ids - PRESET_IDS)}, "
        f"server-only: {sorted(PRESET_IDS - client_ids)}"
    )


def test_theme_preset_premium_and_mode_match_client():
    blocks = {re.search(r"id: '([a-z]+)'", b).group(1): b for b in _client_preset_blocks()}
    for preset in THEME_PRESETS:
        block = blocks[preset.id]
        premium = re.search(r"premium: (true|false)", block).group(1) == "true"
        mode = re.search(r"mode: '(\w+)'", block).group(1)
        assert premium == preset.premium, f"{preset.id}: premium drift"
        assert mode == preset.mode, f"{preset.id}: mode drift"


def test_theme_preset_blurbs_match_client():
    """The blurb is exactly what the model reads (preset_catalog_text) — an
    id-only parity check would pass while the model still recommends a
    theme's OLD description. Regex, not a byte-diff of the whole file, so an
    unrelated edit elsewhere in cappeThemes.ts can't spuriously fail this."""
    blocks = {re.search(r"id: '([a-z]+)'", b).group(1): b for b in _client_preset_blocks()}
    for preset in THEME_PRESETS:
        client_blurb = re.search(r"blurb: '([^']*)'", blocks[preset.id]).group(1)
        assert client_blurb == preset.blurb, f"{preset.id}: blurb drift"


def test_font_pairings_match_client():
    """Content, not just count — a swapped heading/body or an edited pairing
    with the list length unchanged is exactly the drift a count-only check
    misses, and it's the pairing text (not the count) that reaches the
    prompt via font_pairings_text()."""
    source = _client_source()
    match = re.search(r"export const FONT_PAIRINGS.*?= \[(.*?)\n\]", source, re.S)
    assert match, "couldn't find FONT_PAIRINGS in cappeThemes.ts"
    client_pairs = re.findall(r"heading: '([^']*)', body: '([^']*)'", match.group(1))
    assert client_pairs == list(FONT_PAIRINGS), (
        f"font pairing drift — client: {client_pairs}, server: {list(FONT_PAIRINGS)}"
    )


# --- set_theme preset validation ----------------------------------------------

_BLOCKS = [{"id": "b1", "type": "hero", "heading": "H"}]


def _ctx(theme_intent=True):
    return ValidationCtx(by_id={b["id"]: b for b in _BLOCKS}, pending_canvas_count={}, theme_intent=theme_intent)


def test_set_theme_known_preset_accepted():
    reason = _v_set_theme({"key": "preset", "value": "noir"}, _ctx())
    assert reason is None


def test_set_theme_unknown_preset_rejected():
    reason = _v_set_theme({"key": "preset", "value": "cyberpunk"}, _ctx())
    assert reason and "unknown theme preset" in reason


def test_set_theme_preset_still_gated_without_theme_intent():
    reason = _v_set_theme({"key": "preset", "value": "noir"}, _ctx(theme_intent=False))
    assert reason and "won't switch the site theme" in reason
