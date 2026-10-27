"""The one place the social feature asks "which Claude, and may I call it".

Admin → Settings → AI models picks the model for the `gummfit.social`
surface; its default is Claude Haiku 5.5 whenever this server has an
Anthropic key, and None without one (there is no Gemini fallback here — a
reply the owner's name goes out under needs a model we chose on purpose).
Every call also counts in the `anthropic` rate-limit bucket, and a full
bucket means "not now", never a different provider.

That bucket is the whole server's (Espresso, Huume, Merlin…), and replies to
comments and DMs are driven by strangers: a "comment to win" giveaway is
hundreds of them. So the automatic calls (`automatic=True`) may use only
`AUTOMATIC_SHARE` of its hourly limit, counted under `AUTOMATIC_ENDPOINT`.
"""
from __future__ import annotations

import logging
from typing import Optional

from app.core.services import agent_surfaces, anthropic_messages

logger = logging.getLogger(__name__)

SERVICE = "cappe_social"
AUTOMATIC_ENDPOINT = "reply_auto"
AUTOMATIC_SHARE = 0.5


class AiUnavailable(RuntimeError):
    """No model is configured, or the bucket is full right now."""


async def automatic_calls_last_hour() -> int:
    from app.database import connection_or_direct

    async with connection_or_direct() as conn:
        return int(await conn.fetchval(
            "SELECT count(*) FROM api_rate_limits WHERE provider = 'anthropic' AND service_name = $1 "
            "AND endpoint = $2 AND called_at > NOW() - INTERVAL '1 hour'",
            SERVICE, AUTOMATIC_ENDPOINT,
        ) or 0)


async def model_for(endpoint: str, *, automatic: bool = False) -> Optional[str]:
    """The model to call for `endpoint` ("reply" / "captions"), or None when
    there is none or the bucket says not now. Counts the call. `automatic`
    is a call nobody on our side asked for (an inbound comment's draft): it
    also stops at its share of the bucket."""
    model = await anthropic_messages.claude_default(agent_surfaces.GUMMFIT_SOCIAL)
    if not model:
        return None
    from app.core.services.rate_limiter import RateLimitExceeded, get_rate_limiter

    limiter = get_rate_limiter("anthropic")
    label = AUTOMATIC_ENDPOINT if automatic else endpoint
    try:
        await limiter.check_limit(SERVICE, label)
        if automatic:
            share = max(1, int(limiter.hourly_limit * AUTOMATIC_SHARE))
            used = await automatic_calls_last_hour()
            if used >= share:
                logger.warning("cappe social: automatic replies at their share of the anthropic bucket (%d/%d)",
                               used, share)
                return None
    except RateLimitExceeded as exc:
        logger.warning("cappe social %s: anthropic bucket full (%s)", endpoint, exc)
        return None
    except Exception:
        logger.warning("cappe social %s: rate-limit check failed; allowing", endpoint, exc_info=True)
    try:
        await limiter.record_call(SERVICE, label)
    except Exception:
        logger.warning("cappe social %s: could not record the call", endpoint, exc_info=True)
    return model


async def available() -> bool:
    """Whether a model is configured at all (for the settings page), without
    spending a bucket slot."""
    return bool(await anthropic_messages.claude_default(agent_surfaces.GUMMFIT_SOCIAL))


__all__ = ["AiUnavailable", "SERVICE", "AUTOMATIC_ENDPOINT", "AUTOMATIC_SHARE", "automatic_calls_last_hour",
           "model_for", "available"]
