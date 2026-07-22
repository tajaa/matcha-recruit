"""The AI image-generation daily quota, shared by the editor's Generate button
(`routes/uploads.py`) and Merlin's agent-loop `generate_image` tool
(`services/merlin_agent.py`).

One counter, one place the numbers live — a request through either path spends
against the same allowance, so an agent turn can't grant free image generation
by routing around the button's cap.
"""
from ...core.services.redis_cache import check_rate_limit

# Free/hosting plans get a taste (upgrade funnel, like Merlin's lite tier);
# paid plans get headroom. Tunable; the Redis counter keys on account id.
DAILY_FREE = 3
DAILY_PAID = 30

_KEY = "cappe_image_gen"
_WINDOW_SECONDS = 86_400


async def check_and_record(account_id: str, *, premium: bool) -> None:
    """Raises `fastapi.HTTPException(429)` (via `check_rate_limit`) once the
    account's daily allowance is spent — NOT `RateLimitExceeded` (that type
    belongs to `GeminiRateLimiter`, a different budget); callers must catch
    HTTPException. Call BEFORE generating — a failed generation still counts,
    same as Merlin's Gemini call accounting."""
    daily = DAILY_PAID if premium else DAILY_FREE
    await check_rate_limit(account_id, _KEY, daily, _WINDOW_SECONDS)
