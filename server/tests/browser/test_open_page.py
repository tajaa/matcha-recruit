import sys
import types
from contextlib import asynccontextmanager
from types import SimpleNamespace

import pytest

from app.matcha.services.matcha_work.browser import session
from app.matcha.services.matcha_work.browser.session import BrowsePolicy


class _Route:
    def __init__(self, url, *, navigation=True, frame=None):
        self.request = SimpleNamespace(url=url, frame=frame, is_navigation_request=lambda: navigation)
        self.outcome = None

    async def abort(self, reason):
        self.outcome = ("abort", reason)

    async def continue_(self):
        self.outcome = ("continue", None)


@pytest.fixture
def chromium(monkeypatch):
    seen = SimpleNamespace(launch=None, context=None, guard=None, closed=False, main_frame=object())

    class Page:
        main_frame = seen.main_frame

    class Context:
        async def new_page(self):
            return Page()

        async def route(self, pattern, handler):
            seen.pattern, seen.guard = pattern, handler

    class Browser:
        async def new_context(self, **kwargs):
            seen.context = kwargs
            return Context()

        async def close(self):
            seen.closed = True

    class Chromium:
        async def launch(self, **kwargs):
            seen.launch = kwargs
            return Browser()

    @asynccontextmanager
    async def async_playwright():
        yield SimpleNamespace(chromium=Chromium())

    fake = types.ModuleType("playwright.async_api")
    fake.async_playwright = async_playwright
    monkeypatch.setitem(sys.modules, "playwright", types.ModuleType("playwright"))
    monkeypatch.setitem(sys.modules, "playwright.async_api", fake)
    return seen


@pytest.mark.asyncio
async def test_the_browser_only_reaches_the_network_through_the_proxy(chromium):
    async with session.open_page(BrowsePolicy(allowed_hosts=frozenset({"tables.example"}))) as opened:
        assert chromium.launch["proxy"] == {"server": opened.proxy.url}
        assert opened.proxy.url.startswith("http://127.0.0.1:")
        # Loopback included: by default Chromium would go direct for localhost.
        assert "--proxy-bypass-list=<-loopback>" in chromium.launch["args"]
        assert chromium.launch["headless"] is True
        assert chromium.context["service_workers"] == "block"
        assert chromium.context["accept_downloads"] is False
        assert chromium.pattern == "**/*"
        assert not chromium.closed
    assert chromium.closed and opened.proxy.port is not None


@pytest.mark.asyncio
async def test_a_main_frame_navigation_off_the_allowlist_is_aborted(chromium):
    async with session.open_page(BrowsePolicy(allowed_hosts=frozenset({"tables.example"}))) as opened:
        main = chromium.main_frame
        off_site = _Route("https://evil.example/steal", frame=main)
        await chromium.guard(off_site)
        assert off_site.outcome == ("abort", "blockedbyclient")
        assert opened.blocked_navigations == ["https://evil.example/steal"]

        on_site = _Route("https://www.tables.example/r/nopa", frame=main)
        await chromium.guard(on_site)
        assert on_site.outcome == ("continue", None)

        # What a page loads for itself, and what a frame inside it does, is
        # the proxy's business, not the navigation allowlist's.
        script = _Route("https://cdn.elsewhere.example/app.js", navigation=False, frame=main)
        framed = _Route("https://js.payments.example/frame", navigation=True, frame=object())
        for route in (script, framed):
            await chromium.guard(route)
            assert route.outcome == ("continue", None)
        assert len(opened.blocked_navigations) == 1


@pytest.mark.asyncio
async def test_the_browser_is_closed_when_the_work_inside_raises(chromium):
    with pytest.raises(RuntimeError, match="boom"):
        async with session.open_page(BrowsePolicy()) as opened:
            route = _Route("https://anywhere.example/", frame=chromium.main_frame)
            await chromium.guard(route)
            assert route.outcome == ("continue", None)  # no allowlist: research goes anywhere public
            raise RuntimeError("boom")
    assert chromium.closed
