"""build_image_prompt — deterministic prompt reshaping for AI image generation.

Pure string logic, no SDK, no network — see services/image_prompting.py.

Run from server/:  ./venv/bin/python -m pytest tests/cappe/test_image_prompting.py -q
"""
import os

os.environ.setdefault("LIVE_API", "test-key")
os.environ.setdefault("DATABASE_URL", "postgresql://test:test@localhost/test")
os.environ.setdefault("JWT_SECRET_KEY", "test-secret-key-cappe")

from app.cappe.services.image_prompting import build_image_prompt  # noqa: E402
from app.cappe.services.merlin_catalog import AI_IMAGE_PROMPT_MAX  # noqa: E402


def test_bare_prompt_gains_default_style_and_mood_clauses():
    out = build_image_prompt("a bakery interior")
    assert out.startswith("a bakery interior")
    assert "professional business website" in out
    assert "no text, no watermarks" in out


def test_known_style_chip_expands_to_its_clause():
    out = build_image_prompt("a bakery interior", style="Cinematic")
    assert "cinematic photography" in out.lower()


def test_known_mood_chip_expands_to_its_clause():
    out = build_image_prompt("a bakery interior", mood="Golden Hour")
    assert "golden hour lighting" in out.lower()


def test_free_text_style_rides_through_verbatim():
    out = build_image_prompt("a bakery interior", style="mid-century modern")
    assert "mid-century modern" in out


def test_you_decide_and_empty_string_both_fall_back_to_default():
    a = build_image_prompt("x", style="You decide")
    b = build_image_prompt("x", style="")
    c = build_image_prompt("x", style=None)
    assert "professional business website" in a
    assert "professional business website" in b
    assert "professional business website" in c


def test_style_matching_is_case_insensitive():
    out = build_image_prompt("x", style="PHOTOREALISTIC")
    assert "full-frame camera" in out


def test_output_is_capped_to_the_request_models_prompt_max():
    out = build_image_prompt("x" * AI_IMAGE_PROMPT_MAX, style="a very long free-text style " * 10)
    assert len(out) <= AI_IMAGE_PROMPT_MAX


def test_quality_direction_survives_a_maxed_out_user_prompt():
    """A description already at the length cap must not swallow the whole
    budget — the style/mood/baseline clauses (the point of this function) are
    reserved first and the DESCRIPTION is trimmed, not the direction."""
    out = build_image_prompt("x" * AI_IMAGE_PROMPT_MAX, style="Cinematic", mood="Golden hour")
    assert len(out) <= AI_IMAGE_PROMPT_MAX
    assert "cinematic photography" in out.lower()
    assert "golden hour lighting" in out.lower()
    assert "no text, no watermarks" in out


def test_never_returns_the_raw_prompt_unmodified():
    """The whole point: even a bare call gains quality direction, so a
    generation is never sent to Gemini as the user's literal words alone."""
    raw = "a bakery interior"
    assert build_image_prompt(raw) != raw
