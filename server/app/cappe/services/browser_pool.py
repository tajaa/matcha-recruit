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
    """The shared Chromium, launched on first use and recycled periodically."""
    global _playwright, _browser, _shots_taken

    async with _lock:
        if _browser is not None and _shots_taken >= _RECYCLE_AFTER:
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
        return _browser


async def screenshot_html(html: str, viewport: str = DEFAULT_VIEWPORT) -> bytes:
    """Render an HTML document and return a PNG of the fold.

    The document is set with `set_content` rather than navigated to, so nothing
    here can be pointed at a URL — an agent-driven screenshot tool must not
    become an SSRF surface.
    """
    size = VIEWPORTS.get(viewport, VIEWPORTS[DEFAULT_VIEWPORT])
    global _shots_taken

    async with _get_semaphore():
        browser = await _get_browser()
        context = None
        try:
            context = await browser.new_context(viewport=size, device_scale_factor=1)
            page = await context.new_page()
            await asyncio.wait_for(
                page.set_content(html, wait_until="load"), timeout=_SHOT_TIMEOUT
            )
            # Fonts and entrance animations settle after `load`; without this
            # the shot can catch a mid-reveal section at opacity 0 and the
            # model "sees" an empty page it then tries to fix.
            await asyncio.sleep(0.4)
            png = await asyncio.wait_for(
                page.screenshot(type="png", full_page=False), timeout=_SHOT_TIMEOUT
            )
            _shots_taken += 1
            return png
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


async def shutdown() -> None:
    """Release Chromium (app lifespan shutdown)."""
    async with _lock:
        await _close_browser()
