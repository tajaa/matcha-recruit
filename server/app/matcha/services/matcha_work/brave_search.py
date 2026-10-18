"""Brave Search API: the agents' `web_search` when `BRAVE_SEARCH_API_KEY` is set.

Claude's own web search runs on Brave's index too. Calling it directly costs
less (about 1.4k tokens for ten results with snippets, against about 13.8k for
Anthropic's search, and $5 per 1,000 searches against $10) and lets code choose
the count, the freshness and the snippets. See
`agent_runtime/abilities/web.py` for the tool and what happens without Brave.

`search` makes one request through `search_apis.answer` (the rules job search
and research follow), plus Brave's own quota headers:
- 401 or 403 (a refused key) or 402 (the subscription can't pay for more):
  Brave is out for `REFUSED_SECONDS`.
- A 429, or a 200, whose rate-limit headers show a window of a day or longer
  with nothing left: out until that window resets. A 429 like that is not
  asked again; the 200 is used, and it was the last one.
- Any other 429 (faster than the per-second rate), a 5xx or a dropped
  connection: asked once more. Failing again, or any other 4xx, fails this
  search only.

The monthly quota each response reports (`quota`: the day-or-longer window in
its rate-limit headers) is saved as the latest snapshot, which Admin → AI Usage
shows as searches left; every request is a row in the usage ledger.

Requests from one process are spaced to Brave's per-second rate (`_pace`,
`BRAVE_SEARCH_QPS`, 1 on the free plan), since a run's searches can go out
together.

Out means `available` is False and `search` raises `Unavailable(out=True)`
without a request. Going out is logged as an error once, so it shows in
Admin → Server Errors. It is remembered per process, not shared: a worker that
starts after Brave ran out spends one refused request finding out.
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

from app.matcha.services.matcha_work import search_apis

logger = logging.getLogger(__name__)

URL = "https://api.search.brave.com/res/v1/web/search"
COUNT = 10
# Brave answers at most 20 results a request (code's board searches ask for that).
MAX_COUNT = 20
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
# When this process may send its next request (`_pace`).
_next_at = 0.0


def _pace_seconds() -> float:
    """The gap between two requests: Brave's per-second rate (`BRAVE_SEARCH_QPS`,
    1 on the free plan) with a little room."""
    from app.config import get_settings

    try:
        qps = float(getattr(get_settings(), "brave_search_qps", 1.0) or 1.0)
    except (RuntimeError, TypeError, ValueError):
        qps = 1.0
    return 1.05 / max(qps, 0.1)


async def _pace(*, sleep: SleepFn, clock: Clock) -> None:
    """Space this process's requests out to Brave's rate. A run's searches go
    out together when a turn asks for several (`runner`: reads run at once),
    and on the free plan the second of two in the same second is a 429. Each
    caller takes the next free slot before it awaits anything, so the slots
    are handed out in order without a lock (one event loop per process)."""
    global _next_at
    now = clock()
    at = max(now, _next_at)
    gap = _pace_seconds()
    _next_at = at + gap
    if at > now:
        try:
            await sleep(at - now)
        except asyncio.CancelledError:
            # Called off while waiting (the tool's timeout): give the slot back
            # when nobody has queued behind it, so the next search isn't held
            # for a request that never went out.
            if _next_at == at + gap:
                _next_at = at
            raise


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
    global _out_until, _out_reason, _next_at
    _out_until, _out_reason, _next_at = 0.0, "", 0.0


def _parts(value: str | None) -> list[int | None]:
    """`X-RateLimit-*` numbers by position (`1, 2000`); a part that isn't a
    number stays as None, so the windows still line up."""
    if not value:
        return []
    out: list[int | None] = []
    for part in value.split(","):
        part = part.split(";", 1)[0].strip()
        out.append(int(part) if part.isdigit() else None)
    return out


def _windows(policy: str | None) -> list[int | None]:
    """Each window's length in seconds, from `X-RateLimit-Policy: 1;w=1, 2000;w=2678400`."""
    if not policy:
        return []
    found: list[int | None] = []
    for part in policy.split(","):
        match = re.search(r"w=(\d+)", part)
        found.append(int(match.group(1)) if match else None)
    return found


def quota(headers: httpx.Headers) -> dict | None:
    """The longest day-or-longer window Brave reports (the plan's monthly
    quota): its `limit`, what is `remaining`, its length and the seconds until
    it resets. None when the response names no such window (a per-second rate
    alone, or no headers)."""
    windows = _windows(headers.get("x-ratelimit-policy"))
    limits = _parts(headers.get("x-ratelimit-limit"))
    remaining = _parts(headers.get("x-ratelimit-remaining"))
    resets = _parts(headers.get("x-ratelimit-reset"))
    best = None
    for n, window in enumerate(windows):
        if window is None or window < _QUOTA_WINDOW or (best is not None and window <= best[1]):
            continue
        best = (n, window)
    if best is None:
        return None
    n, window = best

    def at(values: list[int | None]) -> int | None:
        return values[n] if n < len(values) else None

    return {"limit": at(limits), "remaining": at(remaining), "window_seconds": window,
            "reset_seconds": at(resets)}


async def _keep_quota(response: httpx.Response) -> None:
    """Save the quota this response reported, for Admin → AI Usage."""
    found = quota(response.headers)
    if found is None:
        return
    from app.core.services.ai_usage import save_api_quota

    await save_api_quota("brave", limit=found["limit"], remaining=found["remaining"],
                         reset_seconds=found["reset_seconds"], window_seconds=found["window_seconds"])


def spent_quota(headers: httpx.Headers) -> float | None:
    """Seconds until a spent quota resets, when a day-or-longer window has
    nothing left; None otherwise (a per-second limit is a rate, not a quota)."""
    windows = _windows(headers.get("x-ratelimit-policy"))
    remaining = _parts(headers.get("x-ratelimit-remaining"))
    resets = _parts(headers.get("x-ratelimit-reset"))
    longest = None
    for n, window in enumerate(windows):
        if window is None or window < _QUOTA_WINDOW or n >= len(remaining) or remaining[n] != 0:
            continue
        reset = resets[n] if n < len(resets) else None
        reset_in = float(reset if reset is not None else window)
        longest = reset_in if longest is None else max(longest, reset_in)
    return longest


class _Spent(Exception):
    """A 429 whose headers show a spent quota: stop, don't ask again."""

    def __init__(self, seconds: float):
        super().__init__("no searches left")
        self.seconds = seconds


def _clean(text: Any, limit: int) -> str:
    return " ".join(html.unescape(_TAGS.sub("", str(text or ""))).split())[:limit]


def results(body: dict, count: int = COUNT) -> list[dict]:
    """The web results, as the model sees them: title, URL, how old, what it says."""
    out = []
    for item in ((body.get("web") or {}).get("results") or [])[:count]:
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


async def search(query: str, *, freshness: Any = None, count: int = COUNT,
                 transport: httpx.AsyncBaseTransport | None = None,
                 sleep: SleepFn = asyncio.sleep, clock: Clock = time.monotonic) -> list[dict]:
    """Up to `count` (`COUNT` unless asked, at most `MAX_COUNT`) web results
    for `query`, under the rules in the docstring."""
    count = max(1, min(int(count), MAX_COUNT))
    key = _key()
    if key is None:
        raise Unavailable("Brave search has no key", out=True)
    if clock() < _out_until:
        raise Unavailable(f"Brave search is out ({_out_reason})", out=True)
    params: dict[str, Any] = {"q": query[:400], "count": count, "extra_snippets": "true",
                              "result_filter": "web", "text_decorations": "false"}
    if isinstance(freshness, str) and freshness in FRESHNESS:
        params["freshness"] = FRESHNESS[freshness]
    headers = {"X-Subscription-Token": key, "Accept": "application/json"}
    answered: list[httpx.Response] = []
    await _pace(sleep=sleep, clock=clock)
    if clock() < _out_until:  # went out while this one waited its turn
        raise Unavailable(f"Brave search is out ({_out_reason})", out=True)

    async def send(client: httpx.AsyncClient) -> httpx.Response:
        response = await client.get(URL, params=params, headers=headers)
        answered.append(response)
        if response.status_code == 429:
            spent = spent_quota(response.headers)
            if spent is not None:
                raise _Spent(spent)
        return response

    try:
        body = await search_apis.answer("Brave", send, transport=transport, sleep=sleep,
                                        timeout=TIMEOUT_SECONDS, sku="web_search")
    except _Spent as exc:
        mark_out("Brave has no searches left this period", exc.seconds, clock=clock)
        raise Unavailable(_out_reason, out=True) from None
    except search_apis.ProviderError as exc:
        if exc.fatal:
            mark_out(str(exc), REFUSED_SECONDS, clock=clock)
            raise Unavailable(_out_reason, out=True) from None
        raise Unavailable(str(exc)) from None
    finally:
        if answered:
            await _keep_quota(answered[-1])
    spent = spent_quota(answered[-1].headers)
    if spent is not None:
        # That was the last one: the next search would be refused.
        mark_out("Brave has no searches left this period", spent, clock=clock)
    return results(body, count)
