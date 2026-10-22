"""Caption options for the composer, from the photos and the product.

One Messages call with the images attached by URL (Claude fetches them; ours
are public CloudFront objects). The model writes three options in different
registers plus alt text; hashtags come back as a list so the composer can
toggle them, and the owner's default set is merged in. Nothing here posts.
"""
from __future__ import annotations

import logging
from typing import Any, Optional

from app.core.services import anthropic_messages

from ..email import fmt_money as fmt_money_cents
from .ai import AiUnavailable, model_for

logger = logging.getLogger(__name__)

MAX_IMAGES = 4
_SYSTEM = (
    "You write social media captions for a small business's own Instagram and Facebook accounts. "
    "Write in the business's voice, in the first person plural, with no corporate filler and no "
    "emoji walls (one or two emoji at most, and only when the tone asks for it). Never invent "
    "facts: prices, ingredients, materials, availability and claims come only from the details "
    "given. Never mention that you are an AI. Reply with JSON only."
)


def _tone_line(tone: Optional[str]) -> str:
    return {
        "professional": "Tone: polished and professional.",
        "playful": "Tone: playful and warm, light humour is welcome.",
        "minimal": "Tone: minimal — short lines, few words, no hashtags in the text itself.",
    }.get(tone or "friendly", "Tone: friendly and direct.")


def build_prompt(
    *, site_name: str, product: Optional[dict[str, Any]], brief: Optional[str], tone: Optional[str],
    default_hashtags: list[str], store_url: Optional[str], image_count: int,
) -> str:
    lines = [f"Business: {site_name}.", _tone_line(tone)]
    if product:
        price = fmt_money_cents(product.get("price_cents"), product.get("currency") or "USD")
        lines.append(f"Product in the photos: {product.get('name')} — {price}.")
        if product.get("description"):
            lines.append(f"Product details: {str(product['description'])[:600]}")
    if store_url:
        lines.append(f"Store link (the caption may say where to buy; the link is added separately): {store_url}")
    if brief:
        lines.append(f"What the owner wants to say: {brief[:500]}")
    if default_hashtags:
        lines.append("The owner's usual hashtags (use the ones that fit): " + " ".join(default_hashtags))
    lines.append(f"{image_count} photo(s) attached." if image_count else "No photo attached — write from the details alone.")
    lines.append(
        "Return JSON: {\"options\": [{\"text\": \"caption\", \"hashtags\": [\"#tag\", ...]}, ...3 options], "
        "\"alt_text\": \"one sentence describing the first photo for screen readers\"}. "
        "Captions under 300 characters; hashtags 3-8 per option, lowercase, no spaces."
    )
    return "\n".join(lines)


def parse_reply(raw: str) -> dict[str, Any]:
    """The model's JSON into `{options, alt_text}`, tolerant of a missing
    piece but never of a wrong shape."""
    data = anthropic_messages.parse_json_object(raw)
    options: list[dict[str, Any]] = []
    # Filter before taking three: a malformed option must not cost a good one.
    for opt in data.get("options") or []:
        if len(options) == 3:
            break
        if not isinstance(opt, dict):
            continue
        text = str(opt.get("text") or "").strip()
        if not text:
            continue
        tags = [str(t) for t in (opt.get("hashtags") or []) if str(t).strip()]
        options.append({"text": text[:2200], "hashtags": tags[:30]})
    alt = data.get("alt_text")
    return {"options": options, "alt_text": str(alt).strip()[:500] if isinstance(alt, str) and alt.strip() else None}


async def draft_captions(
    *, site_name: str, media_urls: list[str], product: Optional[dict[str, Any]], brief: Optional[str],
    tone: Optional[str], default_hashtags: list[str], store_url: Optional[str],
) -> dict[str, Any]:
    """Raises AiUnavailable when no model may be called, RuntimeError on a
    failed call."""
    model = await model_for("captions")
    if not model:
        raise AiUnavailable("Caption drafting needs Claude; ask your admin to set ANTHROPIC_API_KEY")
    attachments = [
        {"type": "image", "source": {"type": "url", "url": url}} for url in media_urls[:MAX_IMAGES]
    ]
    prompt = build_prompt(
        site_name=site_name, product=product, brief=brief, tone=tone,
        default_hashtags=default_hashtags, store_url=store_url, image_count=len(attachments),
    )
    raw = await anthropic_messages.generate_text(
        prompt, model=model, system=_SYSTEM, attachments=attachments, json_output=True,
        max_tokens=2_000, effort="low", timeout_seconds=45.0,
    )
    parsed = parse_reply(raw)
    parsed["model"] = model
    return parsed


__all__ = ["MAX_IMAGES", "build_prompt", "parse_reply", "draft_captions"]
