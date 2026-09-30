"""Opening a page the guarded way.

Two independent locks:

  * where the browser may CONNECT: the egress proxy (public addresses only,
    pinned). Always on.
  * where the main frame may NAVIGATE: `BrowsePolicy.allowed_hosts`. A page is
    free to load scripts and images from wherever it likes (through the
    proxy), but the top-level page stays on the hosts the caller named. None
    means no navigation limit, which is what open-ended research needs.
"""
from __future__ import annotations

from contextlib import asynccontextmanager
from dataclasses import dataclass, field
from typing import AsyncIterator
from urllib.parse import urlsplit

from .egress import EgressProxy

VIEWPORT_W = 1440
VIEWPORT_H = 900


@dataclass(frozen=True)
class BrowsePolicy:
    allowed_hosts: frozenset[str] | None = None
    max_turns: int = 15
    wall_seconds: float = 150.0


@dataclass
class PageSession:
    page: object
    proxy: EgressProxy
    policy: BrowsePolicy
    blocked_navigations: list[str] = field(default_factory=list)


def host_allowed(url: str, allowed_hosts: frozenset[str] | None) -> bool:
    """Whether the main frame may go to `url`: http(s) only (plus the blank
    page a tab starts on). With an allowlist, the host must be one of the
    allowed hosts or a subdomain of one."""
    if url == "about:blank":
        return True
    try:
        parts = urlsplit(url)
    except ValueError:
        return False
    if (parts.scheme or "").lower() not in ("http", "https"):
        return False
    host = (parts.hostname or "").lower().rstrip(".")
    if not host:
        return False
    if allowed_hosts is None:
        return True
    return any(host == allowed or host.endswith("." + allowed) for allowed in allowed_hosts)


@asynccontextmanager
async def open_page(policy: BrowsePolicy) -> AsyncIterator[PageSession]:
    from playwright.async_api import async_playwright

    async with EgressProxy() as proxy, async_playwright() as playwright:
        browser = await playwright.chromium.launch(
            headless=True,
            proxy={"server": proxy.url},
            # Nothing skips the proxy, loopback included: by default Chromium
            # goes direct for localhost, which is exactly what must not happen.
            args=["--proxy-bypass-list=<-loopback>", "--disable-quic"],
        )
        try:
            context = await browser.new_context(
                viewport={"width": VIEWPORT_W, "height": VIEWPORT_H},
                service_workers="block",
                accept_downloads=False,
            )
            page = await context.new_page()
            session = PageSession(page=page, proxy=proxy, policy=policy)

            async def guard(route) -> None:
                request = route.request
                if (
                    request.is_navigation_request()
                    and request.frame == page.main_frame
                    and not host_allowed(request.url, policy.allowed_hosts)
                ):
                    session.blocked_navigations.append(request.url[:300])
                    await route.abort("blockedbyclient")
                    return
                await route.continue_()

            await context.route("**/*", guard)
            yield session
        finally:
            await browser.close()
