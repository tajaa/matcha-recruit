"""The request rules for the paid API Espresso's agents call: Brave's web
search (`brave_search.py`). No search API (SearchAPI, SerpApi) is called since
2026-10-18, and no Google API either: job search, research tasks and the chat
assistant run on Brave and Claude.

`answer` makes one request under these rules:
- 401 or 403: the key was refused. `fatal`: asking again can't help.
- 402, or a 429 whose own words say the account has no searches left
  (`out_of_searches`): `fatal` too.
- Any other 429 (too many at once, a per-minute quota), a 5xx or a dropped
  connection: asked once more after 2 s. Failing again, the API is `down`.
- Any other 4xx: this request's own error.

Each call is logged to the AI usage ledger (`ai_usage.record_api_call`), so
Admin → AI Usage shows every paid search by API, what asked for it and what
it cost.
"""
from __future__ import annotations

import asyncio
import re
import time
from typing import Any, Awaitable, Callable

import httpx

TIMEOUT_SECONDS = 20.0

SleepFn = Callable[[float], Awaitable[None]]
SendFn = Callable[[httpx.AsyncClient], Awaitable[httpx.Response]]


class ProviderError(Exception):
    """A search that could not be done. `fatal` when asking again can't help
    (a refused key, no searches left); `down` when the API didn't answer even
    after a retry, so another API may."""

    def __init__(self, message: str, *, fatal: bool = False, down: bool = False):
        super().__init__(message)
        self.fatal = fatal
        self.down = down


# An account with no searches left, in the APIs' own words: SearchAPI's 429
# "You have used all of the searches for the month. Please upgrade your plan
# on SearchApi.io.", SerpApi's 429 "Your account has run out of searches."
# Never "quota" or "upgrade your plan" alone: Google's per-minute 429 says
# "Quota exceeded", and an hourly limit can ask for an upgrade. Both pass.
_NO_SEARCHES_LEFT = re.compile(r"used all (?:of )?(?:the|your) searches|out of (?:searches|credits)", re.I)


def _said(body: Any) -> str:
    """What an API's error body says: SearchAPI's and SerpApi's `error` text,
    Google's error status and message, or Brave's status and detail."""
    error = body.get("error") if isinstance(body, dict) else None
    if isinstance(error, dict):
        error = ": ".join(str(error[k]) for k in ("status", "message", "detail") if error.get(k))
    return " ".join(str(error or "").split())[:200]


def out_of_searches(status: int, body: Any) -> str | None:
    """The API's own words when the account has no searches left (a 402, or a
    429 that says so); None otherwise, so a plain 429 is asked again."""
    if status not in (402, 429):
        return None
    said = _said(body)
    if status == 402 or _NO_SEARCHES_LEFT.search(said):
        return said or "no searches left"
    return None


def provider_id(name: str) -> str:
    """The ledger's provider for an API's display name: "Google Places" -> "google_places"."""
    return "_".join(name.lower().split())


async def answer(name: str, send: SendFn, *, transport: httpx.AsyncBaseTransport | None = None,
                 sleep: SleepFn = asyncio.sleep, timeout: float = TIMEOUT_SECONDS,
                 sku: str | None = None) -> dict:
    """One JSON object from an API, under the rules above. `send` may raise
    an error of its own (not an `httpx.HTTPError`) to stop at once.

    Every call is one row in the AI usage ledger (`ai_usage.record_api_call`):
    provider `name`, model `sku` (the engine or SKU, which sets the price),
    whether it answered and how long it took, the retry included."""
    from app.core.services.ai_usage import record_api_call

    started = time.monotonic()
    status, error = "error", None
    try:
        body = await _ask(name, send, transport=transport, sleep=sleep, timeout=timeout)
        status = "ok"
        return body
    except ProviderError as exc:
        error = str(exc)
        raise
    except asyncio.CancelledError:
        status, error = "timeout", "cancelled"
        raise
    except Exception as exc:
        error = str(exc) or type(exc).__name__
        raise
    finally:
        await record_api_call(
            provider=provider_id(name), model=sku or "request", method="search",
            latency_ms=int((time.monotonic() - started) * 1000), status=status, error=error,
        )


async def _ask(name: str, send: SendFn, *, transport: httpx.AsyncBaseTransport | None,
               sleep: SleepFn, timeout: float) -> dict:
    last = ""
    for attempt in range(2):
        try:
            async with httpx.AsyncClient(timeout=timeout, transport=transport) as client:
                response = await send(client)
        except httpx.HTTPError as exc:
            last = type(exc).__name__
        else:
            try:
                body = response.json()
            except ValueError:
                body = None
            status = response.status_code
            why = f" ({_said(body)})" if _said(body) else ""
            if status in (401, 403):
                raise ProviderError(f"{name} refused the API key{why}", fatal=True)
            spent = out_of_searches(status, body)
            if spent is not None:
                raise ProviderError(f"{name} has no searches left ({spent})", fatal=True)
            if status == 429 or status >= 500:
                last = f"{name} answered {status}{why}"
            elif status >= 400:
                raise ProviderError(f"{name} answered {status}{why}")
            elif not isinstance(body, dict):
                raise ProviderError(f"{name} returned "
                                    f"{'something other than JSON' if body is None else 'an unexpected shape'}")
            else:
                return body
        if attempt == 0:
            await sleep(2.0)
    raise ProviderError(f"{name} did not answer: {last}", down=True)

