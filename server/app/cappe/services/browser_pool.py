"""A process-wide headless Chromium, for screenshotting rendered Cappe pages.

The Merlin agent loop (`services/merlin_agent.py`) renders its working copy of
the page to standalone HTML and screenshots it, so the model can SEE what its
own edit did instead of reasoning about a JSON tree. That happens inside an
interactive SSE turn, so:

- **The browser is a singleton, not per-request.** Launching Chromium costs
  ~500ms; the turn may take several shots. `research_browse.py` launches per
  task because it runs in a Celery worker where that cost is amortized over a
  long job — here it would be paid on every screenshot.
- **A worker round-trip would be worse, not better.** The turn is streaming to
  a user; handing each shot to Celery adds queue latency plus plumbing the PNG
  back through redis, for no isolation gain (the HTML is local `set_content`,
  never a network fetch).
- **Concurrency is capped** (`_MAX_CONCURRENT`): Chromium is the memory-heaviest
  thing in the API container, and this shares it with WeasyPrint.

Everything degrades. If Chromium isn't installed in the image (`playwright
install chromium` — see server/Dockerfile), `screenshot_html` raises
`ScreenshotUnavailable` and the loop simply proceeds without vision rather than
failing the turn.
"""
import asyncio
import logging
from typing import Any, Optional

from ...config import get_settings

logger = logging.getLogger(__name__)

# Desktop matches the editor's own preview width; mobile is a common phone
# viewport. Height is the visible fold — a full-page shot of a long landing page
# scales down to an unreadable strip, and the fold is what design feedback is
# about anyway.
VIEWPORTS: dict[str, dict[str, int]] = {
    "desktop": {"width": 1280, "height": 900},
    "mobile": {"width": 390, "height": 844},
}
DEFAULT_VIEWPORT = "desktop"

# Shots go to the model as image input tokens and to storage as transcript
# thumbnails. JPEG at q80 is a fraction of PNG's bytes for a judgment the model
# makes at tile resolution anyway — the difference a designer would notice
# (colour relationships, contrast, whether a section reads) survives it intact.
# Exported so callers declare ONE mime: a Part labelled image/png over JPEG
# bytes is a lie the model has no way to catch.
SHOT_MIME = "image/jpeg"
SHOT_EXT = "jpg"
_SHOT_QUALITY = 80

_MAX_CONCURRENT = 2
# Chromium leaks over a long-lived process; recycle on a shot count rather than
# waiting for the container's memory ceiling to do it for us.
_RECYCLE_AFTER = 50
# Per-shot ceiling. The HTML is set in-process (no network), so anything slower
# than this is a hung renderer, not a slow page.
_SHOT_TIMEOUT = 20.0


class ScreenshotUnavailable(RuntimeError):
    """Chromium is missing or unusable. Callers degrade; they never 500."""


_playwright: Any = None
_browser: Any = None
_shots_taken = 0
# Checked-out-but-not-yet-released callers. `_MAX_CONCURRENT` lets two shots
# run at once, so the age-based recycle in `_get_browser` must not close the
# browser a SIBLING call is mid-`set_content`/`screenshot` on — gating recycle
# on this reaching 0 is what prevents that race (see screenshot_html/`finally`
# for the release side).
_in_flight = 0
_lock = asyncio.Lock()
_semaphore: Optional[asyncio.Semaphore] = None


def _get_semaphore() -> asyncio.Semaphore:
    # Built lazily: a module-level Semaphore binds to whatever loop imported the
    # module, which is not necessarily the one serving the request.
    global _semaphore
    if _semaphore is None:
        _semaphore = asyncio.Semaphore(_MAX_CONCURRENT)
    return _semaphore


async def _close_browser() -> None:
    """Tear the singleton down. Never raises — this runs on the error path."""
    global _playwright, _browser, _shots_taken
    for obj, name in ((_browser, "browser"), (_playwright, "playwright")):
        if obj is None:
            continue
        try:
            await (obj.close() if name == "browser" else obj.stop())
        except Exception as exc:  # noqa: BLE001 — teardown must not mask the real error
            logger.warning("Merlin browser %s teardown failed: %s", name, exc)
    _browser = None
    _playwright = None
    _shots_taken = 0


async def _get_browser() -> Any:
    """The shared Chromium, launched on first use and recycled periodically.

    Marks the browser checked-out (`_in_flight += 1`) before returning it —
    the caller MUST release it via `_release_browser()` when done, or the age
    recycle below stops firing (fresh launches after a crash still work
    either way, since that branch doesn't consult `_in_flight`)."""
    global _playwright, _browser, _shots_taken, _in_flight

    async with _lock:
        if _browser is not None and _shots_taken >= _RECYCLE_AFTER and _in_flight == 0:
            logger.info("Recycling Merlin browser after %d screenshots", _shots_taken)
            await _close_browser()

        if _browser is None:
            try:
                from playwright.async_api import async_playwright

                _playwright = await async_playwright().start()
                _browser = await _playwright.chromium.launch(headless=True)
            except Exception as exc:  # noqa: BLE001 — includes "executable doesn't exist"
                await _close_browser()
                raise ScreenshotUnavailable(str(exc)) from exc
        _in_flight += 1
        return _browser


async def _release_browser() -> None:
    """Pair with `_get_browser()` — always call from a `finally`."""
    global _in_flight
    async with _lock:
        _in_flight = max(0, _in_flight - 1)


# `set_content` means the TOP-LEVEL document is never fetched over the
# network — but the HTML it sets is a rendered Cappe page, and a page's own
# content (a business's logo URL, a generated image) is user-controlled. Left
# ungated, Chromium would issue THOSE fetches for real, from inside the VPC,
# on every screenshot — a live SSRF surface, not a hypothetical one, on a tool
# an agent loop drives. Block-listed by default: this deployment's own
# storage domain, plus the two font hosts the renderer itself hardcodes
# (never user-controlled — see render.py's `<link>` tags) get through;
# browser-internal schemes (data:/about:/blob:) are never real fetches and
# are always allowed. Everything else is aborted.
_UNGATED_SCHEMES = ("data:", "about:", "blob:")
_ALLOWED_EXTERNAL_HOSTS = ("fonts.googleapis.com", "fonts.gstatic.com")


async def _route_guard(route: Any, blocked_hosts: set[str]) -> None:
    request = route.request
    url = request.url
    if url.startswith(_UNGATED_SCHEMES):
        await route.continue_()
        return
    if any(url.startswith(f"https://{host}/") for host in _ALLOWED_EXTERNAL_HOSTS):
        await route.continue_()
        return
    domain = getattr(get_settings(), "cloudfront_domain", None)
    if domain and url.startswith(f"https://{domain}/"):
        await route.continue_()
        return
    # Record what got dropped so the caller can tell the model its shot may be
    # missing real content (an external image/logo the page legitimately
    # references) rather than let it mistake a blocked fetch for a rendering
    # bug and "fix" a section that looks fine to the actual site visitor.
    host = url.split("://", 1)[-1].split("/", 1)[0] if "://" in url else url
    blocked_hosts.add(host)
    await route.abort()


async def screenshot_html(
    html: str, viewport: str = DEFAULT_VIEWPORT, *, focus_block: Optional[int] = None,
) -> tuple[bytes, list[str]]:
    """Render an HTML document and return (a JPEG of the fold, blocked external hosts).

    The document is set with `set_content` rather than navigated to, so
    nothing here can point the TOP-LEVEL request at an arbitrary URL. The
    rendered HTML's own subresource fetches (image `src`, font `url()`) are a
    separate concern — `_route_guard` gates every one of those to this
    deployment's own storage domain; anything else is aborted rather than
    fetched, which also skips the network round trip for third-party assets
    the shot never needed to wait on. The hosts it aborted are returned
    alongside the image — a blocked logo/hero image renders as blank in the
    shot, and the caller needs to be able to say so rather than pass a
    silently-incomplete render off as ground truth.

    `focus_block` scrolls to the section carrying `data-cz-block="<index>"`
    (rendered when the caller passes `render_site_html(..., block_anchors=True)`)
    before shooting, so a shot of section 6 of 8 shows section 6 rather than
    always the top fold — best-effort: a miss (section removed mid-turn, no
    match) falls back to shooting wherever the page already is, never fails
    the shot over it.
    """
    size = VIEWPORTS.get(viewport, VIEWPORTS[DEFAULT_VIEWPORT])
    global _shots_taken
    blocked_hosts: set[str] = set()

    async with _get_semaphore():
        browser = await _get_browser()
        context = None
        try:
            context = await browser.new_context(viewport=size, device_scale_factor=1)
            page = await context.new_page()
            await page.route("**/*", lambda route: _route_guard(route, blocked_hosts))
            # `domcontentloaded`, not `load`: the rendered HTML can reference
            # real image/font URLs (CloudFront, a user's own upload), and
            # `load` waits on every one of them — a slow or dead asset then
            # burns the whole `_SHOT_TIMEOUT` and looks like a crashed
            # browser. The 0.4s settle below still covers fonts/entrance
            # animations; it just doesn't also block on network fetches this
            # tool was never meant to make (see the docstring above).
            await asyncio.wait_for(
                page.set_content(html, wait_until="domcontentloaded"), timeout=_SHOT_TIMEOUT
            )
            if focus_block is not None:
                try:
                    # scrollIntoView({block:"center"}), not Playwright's own
                    # scroll_into_view_if_needed — that does the MINIMAL scroll,
                    # which can leave a short section hugging the bottom edge of
                    # the viewport, partially clipped. Centering is what the
                    # tool description promises the model ("scroll to and
                    # center this block's section").
                    await asyncio.wait_for(
                        page.evaluate(
                            """(idx) => {
                                const el = document.querySelector(`[data-cz-block="${idx}"]`)
                                if (el) el.scrollIntoView({ block: 'center', behavior: 'instant' })
                            }""",
                            int(focus_block),
                        ),
                        timeout=2,
                    )
                except Exception as exc:  # noqa: BLE001 — degrade to the fold, never fail the shot
                    logger.info("Merlin screenshot focus_block=%s scroll skipped: %s", focus_block, exc)
            # Fonts and entrance animations settle after load; without this
            # the shot can catch a mid-reveal section at opacity 0 and the
            # model "sees" an empty page it then tries to fix.
            await asyncio.sleep(0.4)
            png = await asyncio.wait_for(
                page.screenshot(type="jpeg", quality=_SHOT_QUALITY, full_page=False),
                timeout=_SHOT_TIMEOUT,
            )
            _shots_taken += 1
            return png, sorted(blocked_hosts)
        except ScreenshotUnavailable:
            raise
        except Exception as exc:  # noqa: BLE001
            # A crashed browser poisons every later shot, so drop the singleton
            # and let the next call relaunch.
            async with _lock:
                await _close_browser()
            raise ScreenshotUnavailable(str(exc)) from exc
        finally:
            if context is not None:
                try:
                    await context.close()
                except Exception:  # noqa: BLE001
                    pass
            await _release_browser()


async def shutdown() -> None:
    """Release Chromium (app lifespan shutdown)."""
    async with _lock:
        await _close_browser()
