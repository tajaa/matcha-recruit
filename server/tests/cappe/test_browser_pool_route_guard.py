"""The screenshot renderer's subresource request allowlist.

`_route_guard` is what stops a rendered Cappe page's own user-controlled
content (a business's logo URL, a generated image) from turning the Merlin
agent's screenshot tool into a live SSRF surface — Chromium would otherwise
issue those fetches for real, from inside the VPC. Pure logic (no real
Playwright browser needed): a fake `route`/`request` pair records whether
`continue_()` or `abort()` was called.

Run from server/:  ./venv/bin/python -m pytest tests/cappe/test_browser_pool_route_guard.py -q
"""
import os

import pytest

os.environ.setdefault("LIVE_API", "test-key")
os.environ.setdefault("DATABASE_URL", "postgresql://test:test@localhost/test")
os.environ.setdefault("JWT_SECRET_KEY", "test-secret-key-cappe")

from app.config import load_settings  # noqa: E402

load_settings()

from app.cappe.services import browser_pool  # noqa: E402
from app.cappe.services.browser_pool import _route_guard  # noqa: E402


class _FakeRequest:
    def __init__(self, url: str):
        self.url = url


class _FakeRoute:
    def __init__(self, url: str):
        self.request = _FakeRequest(url)
        self.continued = False
        self.aborted = False

    async def continue_(self):
        self.continued = True

    async def abort(self):
        self.aborted = True


async def _check(url: str) -> _FakeRoute:
    route = _FakeRoute(url)
    await _route_guard(route, set())
    return route


@pytest.fixture(autouse=True)
def _cloudfront_domain(monkeypatch):
    """Pin a known domain so the own-storage branch is exercised deterministically.
    `browser_pool.get_settings` IS `app.config.get_settings` (a plain import),
    so mutating the attribute on the singleton it returns is enough — no need
    to also patch the function itself."""
    settings = browser_pool.get_settings()
    monkeypatch.setattr(settings, "cloudfront_domain", "d123.cloudfront.net", raising=False)
    return settings


@pytest.mark.asyncio
async def test_own_storage_domain_is_allowed():
    route = await _check("https://d123.cloudfront.net/cappe/logo.png")
    assert route.continued and not route.aborted


@pytest.mark.asyncio
async def test_hardcoded_font_hosts_are_allowed():
    """These two are hardcoded by render.py itself, never user-controlled —
    blocking them would silently render every screenshot in fallback fonts."""
    for url in (
        "https://fonts.googleapis.com/css2?family=Inter",
        "https://fonts.gstatic.com/s/inter/v1/font.woff2",
    ):
        route = await _check(url)
        assert route.continued and not route.aborted, url


@pytest.mark.asyncio
async def test_data_about_and_blob_schemes_are_always_allowed():
    for url in ("data:image/png;base64,AAAA", "about:blank", "blob:https://x/y"):
        route = await _check(url)
        assert route.continued and not route.aborted, url


@pytest.mark.asyncio
async def test_an_arbitrary_external_host_is_aborted():
    """The SSRF case this exists for: a user-supplied or attacker-registered
    URL slipping into a design field (background image, logo) must not be
    fetched from inside the VPC just because a screenshot was requested."""
    route = await _check("https://attacker.example.test/track.png")
    assert route.aborted and not route.continued


@pytest.mark.asyncio
async def test_aborted_host_is_recorded_for_the_caller():
    """screenshot_html hands blocked_hosts back to the agent loop so it can
    tell the model a blank area is a blocked fetch, not a rendering bug."""
    blocked_hosts: set = set()
    route = _FakeRoute("https://attacker.example.test/track.png")
    await _route_guard(route, blocked_hosts)
    assert blocked_hosts == {"attacker.example.test"}


@pytest.mark.asyncio
async def test_a_lookalike_host_is_not_confused_for_the_real_one():
    """Prefix matching must anchor on the real domain, not just contain it —
    `d123.cloudfront.net.attacker.test` contains the substring but isn't it."""
    route = await _check("https://d123.cloudfront.net.attacker.test/x")
    assert route.aborted and not route.continued


@pytest.mark.asyncio
async def test_no_cloudfront_domain_configured_still_aborts_unknown_hosts(monkeypatch):
    """Local dev with no CLOUDFRONT_DOMAIN set must fail closed, not open."""
    settings = browser_pool.get_settings()
    monkeypatch.setattr(settings, "cloudfront_domain", None, raising=False)

    route = await _check("https://some-other-host.example.test/x")
    assert route.aborted and not route.continued
