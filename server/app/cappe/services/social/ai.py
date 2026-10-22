"""The one place the social feature asks "which Claude, and may I call it".

Admin → Settings → AI models picks the model for the `gummfit.social`
surface; its default is Claude Haiku 5.5 whenever this server has an
Anthropic key, and None without one (there is no Gemini fallback here — a
reply the owner's name goes out under needs a model we chose on purpose).
Every call also counts in the `anthropic` rate-limit bucket, and a full
bucket means "not now", never a different provider.
"""
from __future__ import annotations

import logging
from typing import Optional

from app.core.services import agent_surfaces, anthropic_messages

logger = logging.getLogger(__name__)

SERVICE = "cappe_social"


class AiUnavailable(RuntimeError):
    """No model is configured, or the bucket is full right now."""


async def model_for(endpoint: str) -> Optional[str]:
    """The model to call for `endpoint` ("reply" / "captions"), or None when
    there is none or the bucket says not now. Counts the call."""
    model = await anthropic_messages.claude_default(agent_surfaces.GUMMFIT_SOCIAL)
    if not model:
        return None
    from app.core.services.rate_limiter import RateLimitExceeded, get_rate_limiter

    limiter = get_rate_limiter("anthropic")
    try:
        await limiter.check_limit(SERVICE, endpoint)
    except RateLimitExceeded as exc:
        logger.warning("cappe social %s: anthropic bucket full (%s)", endpoint, exc)
        return None
    except Exception:
        logger.warning("cappe social %s: rate-limit check failed; allowing", endpoint, exc_info=True)
    try:
        await limiter.record_call(SERVICE, endpoint)
    except Exception:
        logger.warning("cappe social %s: could not record the call", endpoint, exc_info=True)
    return model


async def available() -> bool:
    """Whether a model is configured at all (for the settings page), without
    spending a bucket slot."""
    return bool(await anthropic_messages.claude_default(agent_surfaces.GUMMFIT_SOCIAL))


__all__ = ["AiUnavailable", "SERVICE", "model_for", "available"]
