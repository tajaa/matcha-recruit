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
`AGENT_BROWSER_QUEUE` is set, and `enqueue.queue_for` sends every run that
has it to that queue.
"""
from __future__ import annotations

import logging
from typing import Any, Awaitable, Callable
from urllib.parse import urlsplit

from ..context import RunContext, RunState
from ..registry import Ability, AgentTool, ToolOutput
from .reservations import browser_ready

logger = logging.getLogger(__name__)

KEY = "screenshots"
MAX_VIEWS = 4
VIEW_SECONDS = 45.0
_GOTO_MS = 20_000
_SETTLE_MS = 8_000
MAX_TEXT = 6000
MAX_IN_RESULT = 4
_CAPTION = 160

# (url) -> (what the page showed, the screenshot's PNG bytes or None)
Viewer = Callable[[str], Awaitable[tuple[dict, bytes | None]]]
# (PNG bytes, storage prefix) -> a CDN URL, or None
Store = Callable[[bytes, str], Awaitable[str | None]]


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


async def _view_in_browser(url: str) -> tuple[dict, bytes | None]:
    from app.matcha.services.matcha_work.browser.session import BrowsePolicy, open_page

    _, host = _checked(url)
    policy = BrowsePolicy(allowed_hosts=frozenset({_site(host)}), wall_seconds=VIEW_SECONDS)
    async with open_page(policy) as session:
        page = session.page
        await page.goto(url, wait_until="domcontentloaded", timeout=_GOTO_MS)
        try:
            await page.wait_for_load_state("networkidle", timeout=_SETTLE_MS)
        except Exception:  # noqa: BLE001
            pass  # a page that never goes quiet (polling, ads) still shows something
        title = await page.title()
        text = await page.inner_text("body")
        shot = await page.screenshot(type="png", full_page=False)
        out = {"url": page.url, "title": (title or "")[:200], "text": " ".join(text.split())[:MAX_TEXT]}
        if session.blocked_navigations:
            out["note"] = "The page tried to leave its own site; that was blocked."
        return out, shot


async def _store_screenshot(png: bytes, prefix: str) -> str | None:
    from app.matcha.services.matcha_work.agent_card import images

    try:
        return await images.store_image(png, prefix, "screenshot.webp")
    except images.StorageHasNoPublicUrl:
        logger.warning("screenshot dropped: storage returns no public URL (CLOUDFRONT_DOMAIN unset?)")
        return None


def _session(state: RunState) -> dict:
    return state.sessions.setdefault(KEY, {"shots": []})


def _tool(viewer: Viewer, store: Store) -> AgentTool:
    async def handler(ctx: RunContext, state: RunState, args: dict, _left: float) -> ToolOutput:
        try:
            url, host = _checked(str(args.get("url") or "").strip())
        except ValueError as exc:
            return ToolOutput(payload={"error": str(exc)}, status="error")
        await ctx.progress.note(f"Looking at {host[:60]}…")
        try:
            out, png = await viewer(url)
        except Exception as exc:  # noqa: BLE001
            # The site refused, timed out or is not public: a definite no, said plainly.
            return ToolOutput(payload={"url": url, "error": f"Could not open the page: {type(exc).__name__}"},
                              status="error")
        shots = _session(state)["shots"]
        shot_id = None
        if png:
            cdn = await store(png, f"{ctx.storage_prefix}/screenshots")
            if cdn:
                shot_id = f"s{len(shots) + 1}"
                shots.append({"id": shot_id, "url": cdn, "page_url": out.get("url") or url,
                              "title": out.get("title") or host})
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
        timeout_seconds=VIEW_SECONDS + 15,
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
        shot = taken.get(item.get("id")) if isinstance(item, dict) else None
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


def build(*, viewer: Viewer | None = None, store: Store | None = None,
          env_ready: Callable[[], bool] = browser_ready) -> Ability:
    return Ability(
        key=KEY,
        label="Page screenshots",
        tools=(_tool(viewer or _view_in_browser, store or _store_screenshot),),
        prompt_block=lambda _ctx: _PROMPT,
        env_ready=env_ready,
        session_factory=lambda _ctx: {"shots": []},
        block_schemas={"screenshots": SCREENSHOTS_BLOCK},
        gate=gate_block,
    )
