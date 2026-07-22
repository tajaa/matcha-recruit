"""Phase 6 AI image generation — generate_image op validation + config mirrors.

The op validation is pure (merlin_ops stays google-SDK-free — the whole pure
suite depends on that). The actual Gemini call lives in
app/core/services/image_gen.py, which imports google.genai; the aspect-ratio
mirror check imports it lazily and skips if the SDK isn't installed.

  ./venv/bin/python -m pytest tests/cappe/test_image_gen.py -q
"""
import os

os.environ.setdefault("LIVE_API", "test-key")
os.environ.setdefault("DATABASE_URL", "postgresql://test:test@localhost/test")
os.environ.setdefault("JWT_SECRET_KEY", "test-secret-key-cappe")

from app.cappe.services.merlin_catalog import AI_ASPECT_RATIOS, AI_IMAGE_PROMPT_MAX  # noqa: E402
from app.cappe.services.merlin_ops import validate_ops  # noqa: E402

_BLOCKS = [
    {"id": "hero1", "type": "hero", "heading": "H"},
    {"id": "split1", "type": "split", "heading": "S"},
    {"id": "txt1", "type": "text", "heading": "T"},
]


def _op(**kw):
    return validate_ops([{"op": "generate_image", **kw}], _BLOCKS)


def test_generate_image_valid_on_an_image_field():
    v, r = _op(block="hero1", prompt="a sunlit bakery interior")
    assert len(v) == 1 and not r
    assert v[0]["field"] == "image"  # default normalized onto the op


def test_generate_image_valid_with_explicit_field_and_aspect():
    v, r = _op(block="split1", field="image", prompt="a product on a table", aspect="1:1")
    assert len(v) == 1 and not r and v[0]["aspect"] == "1:1"


def test_generate_image_rejects_block_without_an_image_field():
    v, r = _op(block="txt1", prompt="x")   # text block has no image field
    assert not v and "not an image field" in r[0]["reason"]


def test_generate_image_rejects_non_image_field():
    v, r = _op(block="hero1", field="heading", prompt="x")
    assert not v and "not an image field" in r[0]["reason"]


def test_generate_image_rejects_unknown_block():
    v, r = _op(block="ghost", prompt="x")
    assert not v and "not found" in r[0]["reason"]


def test_generate_image_rejects_blank_and_overlong_prompt():
    assert _op(block="hero1", prompt="   ")[1][0]["reason"] == "missing image prompt"
    long = _op(block="hero1", prompt="x" * (AI_IMAGE_PROMPT_MAX + 1))
    assert not long[0] and "too long" in long[1][0]["reason"]


def test_generate_image_drops_unknown_aspect_for_service_default():
    v, r = _op(block="hero1", prompt="x", aspect="banana")
    assert len(v) == 1 and not r and "aspect" not in v[0]  # dropped → service defaults


def test_generate_image_drops_non_string_aspect():
    """A non-string aspect hallucination (16, {}, True) must be dropped, not left
    to 422 the client's str-typed request. Regression for the _sid-only check."""
    for bad in (16, 1.5, True, {"x": 1}, ["16:9"]):
        v, r = _op(block="hero1", prompt="x", aspect=bad)
        assert len(v) == 1 and not r and "aspect" not in v[0], bad


def test_generate_image_keeps_valid_aspects():
    for a in AI_ASPECT_RATIOS:
        v, r = _op(block="hero1", prompt="x", aspect=a)
        assert len(v) == 1 and v[0]["aspect"] == a


def test_generate_image_reference_images_ride_ahead_of_the_prompt():
    """Phase 4 (chat image conditioning): reference_images become Part.from_bytes
    entries BEFORE the text part, so the model sees "here is the input image,
    here is the instruction" — the order Gemini's image-editing mode expects.
    Skips if google.genai isn't installed (mirrors the test above)."""
    try:
        from google.genai import types as genai_types

        from app.core.services import image_gen
    except Exception:
        import pytest
        pytest.skip("google.genai not installed in this environment")

    captured = {}

    class _FakeModels:
        def generate_content(self, *, model, contents, config):
            captured["contents"] = contents
            candidate = type("C", (), {
                "content": type("Content", (), {
                    "parts": [type("Part", (), {
                        "inline_data": type("Inline", (), {"data": b"PNG", "mime_type": "image/png"})(),
                    })()],
                })(),
            })()
            return type("Resp", (), {"candidates": [candidate]})()

    class _FakeClient:
        def __init__(self):
            self.models = _FakeModels()

    # image_gen imports the NAME `get_genai_client` into its own namespace
    # (`from .genai_client import get_genai_client`), so patching the source
    # module's attribute wouldn't reach this call — patch image_gen's own.
    orig = image_gen.get_genai_client
    image_gen.get_genai_client = lambda *a, **k: _FakeClient()
    try:
        bytes_out, mime = image_gen._generate_sync(
            "a lake", "16:9", reference_images=[(b"REF", "image/jpeg")]
        )
    finally:
        image_gen.get_genai_client = orig

    assert bytes_out == b"PNG"
    contents = captured["contents"]
    assert len(contents) == 2
    assert isinstance(contents[-1], genai_types.Part) and contents[-1].text == "a lake"


def test_aspect_ratio_whitelist_mirrors_the_service():
    """merlin_catalog.AI_ASPECT_RATIOS must match image_gen.ASPECT_RATIOS — they
    are duplicated because merlin_catalog stays SDK-free. Skips if google.genai
    isn't installed (this env); runs in CI where it is."""
    try:
        from app.core.services.image_gen import ASPECT_RATIOS, DEFAULT_ASPECT, IMAGE_MODEL
    except Exception:
        import pytest
        pytest.skip("google.genai not installed in this environment")
    assert AI_ASPECT_RATIOS == ASPECT_RATIOS
    assert DEFAULT_ASPECT in ASPECT_RATIOS
    # GA name — the "-preview" model Google shipped this under was shut down
    # 2026-06-25; a regression back to it means every image-gen call 404s.
    assert IMAGE_MODEL == "gemini-3.1-flash-image"
