"""Brave Search API: the agents' `web_search` when `BRAVE_SEARCH_API_KEY` is set.

Claude's own web search runs on Brave's index too. Calling it directly costs
less (about 1.4k tokens for ten results with snippets, against about 13.8k for
Anthropic's search, and $5 per 1,000 searches against $10) and lets code choose
the count, the freshness and the snippets. See
`agent_runtime/abilities/web.py` for the tool and what happens without Brave.

`search` makes one request:
- 401 or 403: the key was refused. 402: the subscription can't pay for more.
  A 429, or a 200, whose rate-limit headers show a window of a day or longer
  with nothing left: no searches left until that window resets. Each of these
  takes Brave out of play for this process (`available` is False) and raises
  `Unavailable`; a refusal is logged as an error once, so it shows in
  Admin → Server Errors.
- Any other 429 (more than the per-second rate), a 5xx or a dropped
  connection: asked once more after a second. Failing again raises
  `Unavailable` for this search only.
- Any other 4xx: also `Unavailable` for this search only.

Being out is remembered per process, not shared: a worker that starts after
Brave ran out spends one refused request finding out.
"""
from __future__ import annotations

import asyncio
import html
import logging
import re
import time
from collections.abc import Awaitable, Callable
from typing import Any

import httpx

logger = logging.getLogger(__name__)

URL = "https://api.search.brave.com/res/v1/web/search"
COUNT = 10
TIMEOUT_SECONDS = 10.0
# How long Brave stays out after a refused key or a 402: long enough not to
# ask on every search, short enough that a fixed key or a paid bill is used
# again within the hour.
REFUSED_SECONDS = 3600.0
# A window this long or longer is a quota (a month, a day), not a rate.
_QUOTA_WINDOW = 86_400
_MAX_OUT_SECONDS = 32 * 86_400

FRESHNESS = {"day": "pd", "week": "pw", "month": "pm", "year": "py"}

SleepFn = Callable[[float], Awaitable[None]]
Clock = Callable[[], float]

_TAGS = re.compile(r"<[^>]+>")


class Unavailable(Exception):
    """Brave could not answer this search. `out` when it is out of play for a while."""

    def __init__(self, message: str, *, out: bool = False):
        super().__init__(message)
        self.out = out


_out_until = 0.0
_out_reason = ""


def _key() -> str | None:
    from app.config import get_settings

    try:
        settings = get_settings()
    except RuntimeError:  # settings not loaded (a bare script, some tests): no Brave
        return None
    return getattr(settings, "brave_search_api_key", None) or None


def configured() -> bool:
    return _key() is not None


def available(*, clock: Clock = time.monotonic) -> bool:
    """Whether a search should go to Brave now: a key, and not out."""
    return configured() and clock() >= _out_until


def out_reason() -> str:
    return _out_reason


def mark_out(reason: str, seconds: float, *, clock: Clock = time.monotonic) -> None:
    global _out_until, _out_reason
    seconds = max(1.0, min(seconds, _MAX_OUT_SECONDS))
    if clock() >= _out_until:
        logger.error("Brave search is out for %d s: %s; using the model's own web search", int(seconds), reason)
    _out_until = clock() + seconds
    _out_reason = reason


def reset() -> None:
    """Back in play (tests, and nothing else)."""
    global _out_until, _out_reason
    _out_until, _out_reason = 0.0, ""


def _numbers(value: str | None) -> list[int]:
    out = []
    for part in (value or "").split(","):
        part = part.strip().split(";", 1)[0].strip()
        if part.isdigit():
            out.append(int(part))
    return out


def _windows(policy: str | None) -> list[int]:
    """Each window's length in seconds, from `X-RateLimit-Policy: 1;w=1, 2000;w=2678400`."""
    found = []
    for part in (policy or "").split(","):
        match = re.search(r"w=(\d+)", part)
        found.append(int(match.group(1)) if match else 0)
    return found


def spent_quota(headers: httpx.Headers) -> float | None:
    """Seconds until a spent quota resets, when a day-or-longer window has
    nothing left; None otherwise (a per-second limit is a rate, not a quota)."""
    windows = _windows(headers.get("x-ratelimit-policy"))
    remaining = _numbers(headers.get("x-ratelimit-remaining"))
    resets = _numbers(headers.get("x-ratelimit-reset"))
    longest = None
    for n, window in enumerate(windows):
        if window < _QUOTA_WINDOW or n >= len(remaining) or remaining[n] > 0:
            continue
        reset_in = float(resets[n]) if n < len(resets) else float(window)
        longest = reset_in if longest is None else max(longest, reset_in)
    return longest


def _said(response: httpx.Response) -> str:
    try:
        body = response.json()
    except ValueError:
        return ""
    error = body.get("error") if isinstance(body, dict) else None
    if isinstance(error, dict):
        error = error.get("detail") or error.get("code")
    return " ".join(str(error or "").split())[:200]


def _clean(text: Any, limit: int) -> str:
    return " ".join(html.unescape(_TAGS.sub("", str(text or ""))).split())[:limit]


def results(body: dict) -> list[dict]:
    """The web results, as the model sees them: title, URL, how old, what it says."""
    out = []
    for item in ((body.get("web") or {}).get("results") or [])[:COUNT]:
        if not isinstance(item, dict):
            continue
        url = item.get("url")
        if not isinstance(url, str) or not url.startswith(("https://", "http://")):
            continue
        row = {"title": _clean(item.get("title"), 200), "url": url,
               "description": _clean(item.get("description"), 500)}
        if item.get("age"):
            row["age"] = _clean(item.get("age"), 40)
        extra = [_clean(s, 300) for s in item.get("extra_snippets") or [] if s]
        if extra:
            row["more"] = extra[:3]
        out.append(row)
    return out


async def search(query: str, *, freshness: str | None = None,
                 transport: httpx.AsyncBaseTransport | None = None,
                 sleep: SleepFn = asyncio.sleep, clock: Clock = time.monotonic) -> list[dict]:
    """Up to `COUNT` web results for `query`, under the rules in the docstring."""
    key = _key()
    if key is None:
        raise Unavailable("Brave search has no key", out=True)
    if clock() < _out_until:
        raise Unavailable(f"Brave search is out ({_out_reason})", out=True)
    params: dict[str, Any] = {"q": query[:400], "count": COUNT, "extra_snippets": "true",
                              "result_filter": "web", "text_decorations": "false"}
    if freshness in FRESHNESS:
        params["freshness"] = FRESHNESS[freshness]
    headers = {"X-Subscription-Token": key, "Accept": "application/json"}
    last = ""
    for attempt in range(2):
        try:
            async with httpx.AsyncClient(timeout=TIMEOUT_SECONDS, transport=transport) as client:
                response = await client.get(URL, params=params, headers=headers)
        except httpx.HTTPError as exc:
            last = type(exc).__name__
        else:
            status, why = response.status_code, _said(response)
            spent = spent_quota(response.headers)
            if status in (401, 403):
                mark_out(f"Brave refused the API key ({status}{': ' + why if why else ''})",
                         REFUSED_SECONDS, clock=clock)
                raise Unavailable(_out_reason, out=True)
            if status == 402:
                mark_out(f"Brave would not bill the search (402{': ' + why if why else ''})",
                         REFUSED_SECONDS, clock=clock)
                raise Unavailable(_out_reason, out=True)
            if status == 429 and spent is not None:
                mark_out("Brave has no searches left this period", spent, clock=clock)
                raise Unavailable(_out_reason, out=True)
            if status == 429 or status >= 500:
                last = f"Brave answered {status}{': ' + why if why else ''}"
            elif status >= 400:
                raise Unavailable(f"Brave answered {status}{': ' + why if why else ''}")
            else:
                try:
                    body = response.json()
                except ValueError:
                    body = None
                if not isinstance(body, dict):
                    raise Unavailable("Brave returned something other than a JSON object")
                if spent is not None:
                    # That was the last one: the next search would be refused.
                    mark_out("Brave has no searches left this period", spent, clock=clock)
                return results(body)
        if attempt == 0:
            await sleep(1.0)
    raise Unavailable(f"Brave did not answer: {last}")
