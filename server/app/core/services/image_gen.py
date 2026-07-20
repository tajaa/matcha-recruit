"""Shared AI image generation — Gemini image model → bytes → stored public URL.

Extracted into core so Cappe (which may import only from ``app/core/*``) can
generate images the same proven way matcha-work does
(``matcha/services/matcha_work_ai.py`` ``_call_imagen``) without duplicating the
SDK plumbing.

Two deliberate improvements over the matcha-work inline version:
  * uses the central ``get_genai_client()`` factory (Vertex-aware) instead of a
    hand-rolled ``genai.Client``;
  * wraps the blocking call in ``asyncio.wait_for`` — matcha-work's has NO
    timeout, so a hung image call pins a request worker indefinitely.

Never raises a bare SDK error to the caller: any failure (no image, safety
block, timeout, API error) surfaces as ``ImageGenError``, which callers turn
into a clean 502 / chat message — never a 500.
"""
import asyncio
import logging
import secrets

from google.genai import types as genai_types

from .genai_client import get_genai_client
from .storage import get_storage

logger = logging.getLogger(__name__)

IMAGE_MODEL = "gemini-3.1-flash-image-preview"  # matches matcha_work_ai._IMAGE_MODEL
IMAGE_GEN_TIMEOUT = 60  # seconds — image gen is slower than text; cap so a hang can't pin a worker
# Aspect ratios the model accepts. The AI-op validator keeps a mirror of these
# keys in `cappe/services/merlin_catalog.py:AI_ASPECT_RATIOS` (that module must
# stay import-light — no google SDK — so it can't import this one).
ASPECT_RATIOS = frozenset({"1:1", "16:9", "9:16", "4:3", "3:4", "3:2", "2:3"})
DEFAULT_ASPECT = "16:9"


class ImageGenError(Exception):
    """Generation produced no usable image (model returned only text, safety
    block, timeout, or API error)."""


def _generate_sync(prompt: str, aspect_ratio: str) -> tuple[bytes, str]:
    """Blocking Gemini image call → (image_bytes, mime). Raises ImageGenError
    if the response carries no inline image data."""
    client = get_genai_client()
    response = client.models.generate_content(
        model=IMAGE_MODEL,
        contents=prompt,
        config=genai_types.GenerateContentConfig(
            response_modalities=["IMAGE", "TEXT"],
            image_config=genai_types.ImageConfig(aspect_ratio=aspect_ratio),
        ),
    )
    if response.candidates and response.candidates[0].content and response.candidates[0].content.parts:
        for part in response.candidates[0].content.parts:
            if part.inline_data and part.inline_data.data:
                return part.inline_data.data, (part.inline_data.mime_type or "image/png")
    raise ImageGenError("model returned no image")


async def generate_image(prompt: str, *, prefix: str, aspect_ratio: str = DEFAULT_ASPECT) -> str:
    """Generate an image from ``prompt`` and return a public URL (stored under
    ``prefix`` via the platform storage service → CloudFront).

    Raises ``ImageGenError`` on no-image / timeout / any SDK failure."""
    ar = aspect_ratio if aspect_ratio in ASPECT_RATIOS else DEFAULT_ASPECT
    try:
        image_bytes, mime = await asyncio.wait_for(
            asyncio.to_thread(_generate_sync, prompt, ar), timeout=IMAGE_GEN_TIMEOUT
        )
    except ImageGenError:
        raise
    except asyncio.TimeoutError as exc:
        raise ImageGenError(f"image generation timed out after {IMAGE_GEN_TIMEOUT}s") from exc
    except Exception as exc:  # noqa: BLE001 — degrade any SDK error to a clean failure
        logger.warning("image generation failed: %s", exc)
        raise ImageGenError("image generation failed") from exc

    ext = "png" if "png" in mime else "jpg"
    filename = f"gen_{secrets.token_hex(8)}.{ext}"
    return await get_storage().upload_file(image_bytes, filename, prefix=prefix, content_type=mime)
