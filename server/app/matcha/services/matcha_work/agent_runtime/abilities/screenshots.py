"""Looking at a page in a real browser: its text as drawn, and a screenshot.

`fetch_page` reads the HTML a site serves. Many sites draw what people want
(a unit list, a menu, a schedule) with JavaScript after load, so that HTML
has none of it. `view_page` opens the page in the guarded Chromium
(`../../browser`: an egress proxy that allows public addresses only, and a
main frame kept on the page's own site), lets it settle, and returns the
visible text. It also takes a screenshot, which is re-encoded (WebP, at most
1200px, metadata stripped) and stored on our CDN.

The model only ever gets a screenshot's id. A `screenshots` block is rebuilt
from the run's session by id, so it can never show the person an image this
run did not take.

Chromium never runs on the main worker. The ability is offered only when
`AGENT_BROWSER_QUEUE` is set. A run is not moved to that queue for it: the
browser worker has one slot and also runs agent cards and bookings, so every
run would wait behind them. Instead each view is its own short task there
(`workers/tasks/assistant.view_page`), unless the run is already on a worker
that serves the browser queue, where waiting on that queue would wait on
itself; there the view runs in-process.
"""
from __future__ import annotations

import asyncio
import logging
import os
import time
from typing import Any, Awaitable, Callable
from urllib.parse import urlsplit

from app.matcha.services.matcha_work.gmail_service import addresses_in

from ..context import RunContext, RunState
from ..registry import Ability, AgentTool, ToolOutput
from .reservations import BROWSER_QUEUE_ENV, browser_ready

logger = logging.getLogger(__name__)

KEY = "screenshots"
MAX_VIEWS = 4
# Chromium's launch, the page load, the settle, the text and the screenshot.
VIEW_SECONDS = 45.0
# Re-encoding and uploading the screenshot (`images.store_image` bounds the upload at 20s).
STORE_SECONDS = 25.0
# How long a view may sit queued for the browser worker before it is called off.
QUEUE_SECONDS = 20.0
_POLL_SECONDS = 0.5
_GOTO_MS = 20_000
_SETTLE_MS = 8_000
MAX_TEXT = 6000
MAX_IN_RESULT = 4
_CAPTION = 160
BUSY = "the browser is busy with another task; try fetch_page"

# (url, storage prefix) -> the page as `view_and_store` returns it
Viewer = Callable[[str, str], Awaitable[dict]]


class ViewRefused(Exception):
    """A definite no, worded for the model: an error status, or a page that
    redirected off its own site."""


def _site(host: str) -> str:
    """The navigation allowlist entry for a host: `www.` dropped, so the page
    may bounce between example.com and www.example.com."""
    return host[4:] if host.startswith("www.") else host


def _checked(url: str) -> tuple[str, str]:
    parts = urlsplit(url)
    host = (parts.hostname or "").lower().rstrip(".")
    if parts.scheme not in ("http", "https") or not host:
        raise ValueError("view_page needs an http(s) URL")
    return url, host


def _page_text(text: str) -> str:
    """The page's text with its line breaks kept: a unit list or a menu is
    one row per line, and a price belongs to the row it is on."""
    lines = (" ".join(line.split()) for line in text.splitlines())
    return "\n".join(line for line in lines if line)[:MAX_TEXT]


def _off_site(url: str) -> ViewRefused:
    away = urlsplit(url).hostname or "another site"
    return ViewRefused(f"it redirected to {away[:80]}, off its own site, which is not allowed")


async def _view_in_browser(url: str) -> tuple[dict, bytes | None]:
    from app.matcha.services.matcha_work.browser.session import BrowsePolicy, host_allowed, open_page

    _, host = _checked(url)
    allowed = frozenset({_site(host)})
    async with open_page(BrowsePolicy(allowed_hosts=allowed)) as session:
        page = session.page
        from ...recaps.capture import window
        async with window(page) as capture:
            try:
                response = await page.goto(url, wait_until="domcontentloaded", timeout=_GOTO_MS)
            except Exception:
                if session.blocked_navigations:
                    # The guard aborted the navigation, so goto only says "blocked by client".
                    raise _off_site(session.blocked_navigations[0])
                raise
            # The navigation guard never sees an HTTP redirect (Playwright routes
            # only a redirect's first request), so where the page ended up is
            # checked here: after the load, and again once it has settled.
            if not host_allowed(page.url, allowed):
                raise _off_site(page.url)
            if response is not None and response.status >= 400:
                raise ViewRefused(f"HTTP {response.status}")
            try:
                await page.wait_for_load_state("networkidle", timeout=_SETTLE_MS)
            except Exception:  # noqa: BLE001
                pass  # a page that never goes quiet (polling, ads) still shows something
            if not host_allowed(page.url, allowed):
                raise _off_site(page.url)
            title = await page.title()
            text = await page.inner_text("body")
            shot = await page.screenshot(type="png", full_page=False)
            out = {"url": page.url, "title": (title or "")[:200], "text": _page_text(text)}
            if session.blocked_navigations:
                out["note"] = "The page tried to leave its own site; that was blocked."
            capture.accepted = True
            return out, shot


async def _store_screenshot(png: bytes, prefix: str) -> str | None:
    from app.matcha.services.matcha_work.agent_card import images

    try:
        return await images.store_image(png, prefix, "screenshot.webp")
    except images.StorageHasNoPublicUrl:
        logger.warning("screenshot dropped: storage returns no public URL (CLOUDFRONT_DOMAIN unset?)")
        return None


async def view_and_store(url: str, prefix: str) -> dict:
    """Open, read and screenshot one page, and store the screenshot. Runs only
    where Chromium does. Always a JSON-safe dict, since it is also the
    browser task's result: the page with `screenshot_url` (or None), or
    `{"url", "error"}`."""
    try:
        out, png = await asyncio.wait_for(_view_in_browser(url), timeout=VIEW_SECONDS)
    except ViewRefused as exc:
        return {"url": url, "error": str(exc)}
    except TimeoutError:
        return {"url": url, "error": "it took too long to load"}
    except Exception as exc:  # noqa: BLE001
        # The site refused, timed out or is not public: a definite no, said plainly.
        logger.info("view_page could not open url=%s", url[:200], exc_info=True)
        return {"url": url, "error": type(exc).__name__}
    out["screenshot_url"] = (await _store_screenshot(png, prefix)) if png else None
    return out


def browser_here() -> bool:
    """Whether this worker process serves the browser queue itself."""
    from app.workers.celery_app import consumes_queue

    return consumes_queue(os.getenv(BROWSER_QUEUE_ENV))


def _recap_worker_scope() -> dict:
    from ...recaps import scope, settings
    run_id = scope.current_run.get()
    return {"recap_run_id": str(run_id)} if settings.enabled() and run_id else {}


async def _view_on_browser_worker(url: str, prefix: str) -> dict:
    from app.workers.tasks.assistant import view_page as view_task

    pending = view_task.apply_async(
        args=[url, prefix], queue=os.getenv(BROWSER_QUEUE_ENV),
        **({"kwargs": _recap_worker_scope()} if _recap_worker_scope() else {}),
        # Still queued by then, it is dropped rather than run for nobody.
        expires=QUEUE_SECONDS,
    )
    started = time.monotonic()
    while True:
        state = await asyncio.to_thread(lambda: pending.state)
        if state == "SUCCESS":
            result = await asyncio.to_thread(lambda: pending.result)
            return result if isinstance(result, dict) else {"url": url, "error": "no result"}
        if state in ("FAILURE", "REVOKED"):
            return {"url": url, "error": "the browser task failed"}
        waited = time.monotonic() - started
        if state == "PENDING" and waited >= QUEUE_SECONDS:
            return {"url": url, "error": BUSY}
        if waited >= QUEUE_SECONDS + VIEW_SECONDS + STORE_SECONDS:
            return {"url": url, "error": "it took too long to load"}
        await asyncio.sleep(_POLL_SECONDS)


async def view(url: str, prefix: str) -> dict:
    """A view from wherever the run is: in-process on the browser worker,
    else as a task on it."""
    if browser_here():
        return await view_and_store(url, prefix)
    return await _view_on_browser_worker(url, prefix)


def _session(state: RunState) -> dict:
    return state.sessions.setdefault(KEY, {"shots": []})


def _tool(viewer: Viewer) -> AgentTool:
    async def handler(ctx: RunContext, state: RunState, args: dict, _left: float) -> ToolOutput:
        try:
            url, host = _checked(str(args.get("url") or "").strip())
        except ValueError as exc:
            return ToolOutput(payload={"error": str(exc)}, status="error")
        await ctx.progress.note(f"Looking at {host[:60]}…")
        out = dict(await viewer(url, f"{ctx.storage_prefix}/screenshots"))
        if out.get("error"):
            # Nothing was read, so nothing here may be cited.
            return ToolOutput(payload={"url": url, "error": f"Could not open the page: {out['error']}"},
                              status="error")
        cdn = out.pop("screenshot_url", None)
        shots = _session(state)["shots"]
        shot_id = None
        if isinstance(cdn, str) and cdn.startswith("https://"):
            shot_id = f"s{len(shots) + 1}"
            shots.append({"id": shot_id, "url": cdn, "page_url": out.get("url") or url,
                          "title": out.get("title") or host})
        state.observed_emails.update(addresses_in(str(out.get("text") or "")))
        payload = {**out, "screenshot_id": shot_id}
        if shot_id is None:
            payload["screenshot_note"] = "No screenshot could be kept for this page."
        return ToolOutput(payload=payload, provenance=frozenset(u for u in (url, out.get("url")) if u))

    return AgentTool(
        name="view_page",
        effect="read",
        description=(
            "Open one public web page in a real browser. Returns the text as the page draws "
            "it (including lists and tables that only appear with JavaScript) and a "
            "screenshot_id. Use it when fetch_page did not show what they want, or when they "
            "ask to see the page; put screenshot ids in a `screenshots` block to show them."
        ),
        parameters={
            "type": "object",
            "properties": {"url": {"type": "string", "description": "An http(s) URL"}},
            "required": ["url"],
        },
        step_kind="browse",
        handler=handler,
        max_calls=MAX_VIEWS,
        # Queued, opened and stored; the view bounds each part, this is the backstop.
        timeout_seconds=QUEUE_SECONDS + VIEW_SECONDS + STORE_SECONDS + 5,
        min_seconds_left=VIEW_SECONDS,
        describe=lambda args: f"Looked at {(urlsplit(str(args.get('url') or '')).hostname or 'a page')[:60]}",
        audit=lambda out: {k: out.get(k) for k in ("url", "title", "error", "screenshot_id")},
        exhausted_label="Screenshot budget exhausted",
        exhausted_message="No more page views in this run; finish with what you have.",
        timeout_message="The page took too long to open.",
        untrusted_output=True,
    )


_PROMPT = """Looking at pages:
- view_page opens a page in a real browser. Use it when fetch_page came back without what they \
asked for (the page draws it with JavaScript), or when they ask to see a page or for a screenshot.
- To show screenshots, add a `screenshots` block with the screenshot_id values view_page gave you, \
each with a short caption. Never describe a screenshot you did not take."""

SCREENSHOTS_BLOCK: dict[str, Any] = {
    "type": "object",
    "description": "Screenshots view_page took in this run, by id, to show the person.",
    "properties": {
        "screenshots": {
            "type": "array",
            "items": {"type": "object", "properties": {
                "id": {"type": "string", "description": "A screenshot_id view_page returned"},
                "caption": {"type": "string"},
            }},
        },
    },
}


def gate_block(block_type: str, raw: Any, state: RunState) -> tuple[dict | None, list[str]]:
    """Rebuilt from the run's own screenshots; the model only picks and captions them."""
    taken = {shot["id"]: shot for shot in _session(state)["shots"]}
    wanted = raw.get("screenshots") if isinstance(raw, dict) else None
    shown, warnings, seen = [], [], set()
    for item in wanted if isinstance(wanted, list) else []:
        shot_id = item.get("id") if isinstance(item, dict) else None
        shot = taken.get(shot_id) if isinstance(shot_id, str) else None
        if shot is None:
            warnings.append("Dropped a screenshot this run did not take")
            continue
        if shot["id"] in seen:
            continue
        seen.add(shot["id"])
        caption = " ".join(str(item.get("caption") or "").split())[:_CAPTION] or shot["title"]
        shown.append({"url": shot["url"], "page_url": shot["page_url"], "caption": caption})
    if len(shown) > MAX_IN_RESULT:
        warnings.append(f"Kept the first {MAX_IN_RESULT} screenshots")
    shown = shown[:MAX_IN_RESULT]
    return ({"type": "screenshots", "screenshots": shown} if shown else None), warnings


def build(*, viewer: Viewer | None = None,
          env_ready: Callable[[], bool] = browser_ready) -> Ability:
    return Ability(
        key=KEY,
        label="Page screenshots",
        tools=(_tool(viewer or view),),
        prompt_block=lambda _ctx: _PROMPT,
        env_ready=env_ready,
        session_factory=lambda _ctx: {"shots": []},
        block_schemas={"screenshots": SCREENSHOTS_BLOCK},
        gate=gate_block,
    )
