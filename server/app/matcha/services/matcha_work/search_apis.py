"""The paid search APIs job search and research tasks share: SearchAPI.io,
SerpApi and Google's Places API.

`answer` makes one request under the rules both follow:
- 401 or 403: the key was refused. `fatal`: asking again can't help.
- 402, or a 429 whose own words say the account has no searches left
  (`out_of_searches`): `fatal` too.
- Any other 429 (too many at once, a per-minute quota), a 5xx or a dropped
  connection: asked once more after 2 s. Failing again, the API is `down`.
- Any other 4xx: this request's own error.

`Fallback` holds the APIs that have keys, in order, for one phase. A call goes
to the first one still in play. One that refuses for good is dropped (logged
once as an error, so it shows in Admin → Server Errors), and so is one that is
down while another follows it (a warning); the last one is always asked. A
token an API gave (a next page, a product's stores) means nothing to another,
so `tag` marks it with its API, and a call with a dropped API's token returns
None. Once every API is dropped nothing more can be asked this phase: each
call raises a fresh fatal error.
"""
from __future__ import annotations

import asyncio
import logging
import re
from typing import Any, Awaitable, Callable

import httpx

logger = logging.getLogger(__name__)

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
    or Google's error status and message."""
    error = body.get("error") if isinstance(body, dict) else None
    if isinstance(error, dict):
        error = ": ".join(str(error[k]) for k in ("status", "message") if error.get(k))
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


def result_error(data: dict) -> str:
    """The error an answer carries, or "" when it only says there were no results."""
    error = str(data.get("error") or "")
    return "" if "hasn't returned any results" in error or "no results" in error.lower() else error


async def answer(name: str, send: SendFn, *, transport: httpx.AsyncBaseTransport | None = None,
                 sleep: SleepFn = asyncio.sleep) -> dict:
    """One JSON object from an API, under the rules above."""
    last = ""
    for attempt in range(2):
        try:
            async with httpx.AsyncClient(timeout=TIMEOUT_SECONDS, transport=transport) as client:
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


Ask = Callable[[Any, "str | None"], Awaitable[Any]]


class Fallback:
    """The APIs that have keys, in order, for one phase (see the module's
    docstring). Each API has a `name`."""

    label = "search"

    def __init__(self, apis: list[Any]):
        self.apis = list(apis)
        self._dropped: dict[int, ProviderError] = {}

    def _first(self) -> int | None:
        return next((n for n in range(len(self.apis)) if n not in self._dropped), None)

    def first(self) -> Any | None:
        """The API a call goes to now; None with none left."""
        n = self._first()
        return None if n is None else self.apis[n]

    @staticmethod
    def tag(at: int, token: str | None) -> str | None:
        """`token`, marked as API `at`'s."""
        return f"{at}:{token}" if token else None

    def _owner(self, token: str) -> int | None:
        given = token.partition(":")[0]
        return int(given) if given.isdigit() and int(given) < len(self.apis) else None

    def holds(self, token: str | None) -> bool:
        """Whether the API that gave `token` is still in play."""
        at = self._owner(token or "")
        return at is not None and at not in self._dropped

    def _drop(self, at: int, exc: ProviderError) -> bool:
        """Whether `exc` takes API `at` out of play (now, or already)."""
        if at in self._dropped:
            return True
        if not (exc.fatal or (exc.down and any(n > at and n not in self._dropped for n in range(len(self.apis))))):
            return False
        self._dropped[at] = exc
        following = self.first()
        instead = f"using {following.name} instead" if following is not None else "none left"
        (logger.error if exc.fatal else logger.warning)("%s: %s; %s", self.label, exc, instead)
        return True

    def _spent(self) -> ProviderError:
        # A fresh error each time: re-raising one from several calls at once
        # grows its traceback.
        last = list(self._dropped.values())[-1] if self._dropped else None
        return ProviderError(f"no {self.label} API left" + (f" ({last})" if last else ""), fatal=True)

    async def call(self, ask: Ask, token: str | None = None) -> tuple[int, Any] | None:
        """`(n, its answer)`: `ask(api, the token as that API gave it)` answered
        by API n, the first still in play, or the one that gave `token`. None
        when that API has been dropped since."""
        while True:
            if len(self._dropped) == len(self.apis):
                raise self._spent()
            at = self._first() if token is None else self._owner(token)
            if at is None or at in self._dropped:
                return None
            try:
                return at, await ask(self.apis[at], token.partition(":")[2] if token else None)
            except ProviderError as exc:
                if not self._drop(at, exc):
                    raise
