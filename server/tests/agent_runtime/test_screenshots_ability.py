from contextlib import asynccontextmanager
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from app.matcha.services.matcha_work.browser import session as browser_session
from app.matcha.services.matcha_work.agent_card import images
from app.matcha.services.matcha_work.agent_runtime import catalog, enqueue
from app.matcha.services.matcha_work.agent_runtime.abilities import screenshots, web
from app.matcha.services.matcha_work.agent_runtime.context import RunState

from .helpers import context


def _state():
    return RunState(started=0.0)


def _ability(viewer=None, store=None, ready=True):
    return screenshots.build(
        viewer=viewer or AsyncMock(return_value=(
            {"url": "https://www.elevateto737.example/floor-plans", "title": "Floor Plans",
             "text": "Unit 0217 Studio $2,604 Available now"}, b"png-bytes")),
        store=store or AsyncMock(return_value="https://cdn.example/shot.webp"),
        env_ready=lambda: ready,
    )


async def _view(ability, state, url="https://www.elevateto737.example/floor-plans", ctx=None):
    tool = ability.tools[0]
    return await tool.handler(ctx or context(storage_prefix="matcha-work/c/assistant/ch/run"), state, {"url": url}, 60.0)


@pytest.mark.asyncio
async def test_a_view_returns_the_drawn_text_and_a_screenshot_id_never_the_image_url():
    store = AsyncMock(return_value="https://cdn.example/shot.webp")
    ability, state = _ability(store=store), _state()
    out = await _view(ability, state)
    assert out.status == "ok"
    assert out.payload["text"].startswith("Unit 0217") and out.payload["screenshot_id"] == "s1"
    assert "cdn.example" not in str(out.payload)
    assert out.provenance == {"https://www.elevateto737.example/floor-plans"}
    assert store.await_args.args == (b"png-bytes", "matcha-work/c/assistant/ch/run/screenshots")
    assert state.sessions["screenshots"]["shots"] == [{
        "id": "s1", "url": "https://cdn.example/shot.webp",
        "page_url": "https://www.elevateto737.example/floor-plans", "title": "Floor Plans",
    }]
    second = await _view(ability, state)
    assert second.payload["screenshot_id"] == "s2"


@pytest.mark.asyncio
async def test_no_stored_screenshot_still_gives_the_text():
    ability, state = _ability(store=AsyncMock(return_value=None)), _state()
    out = await _view(ability, state)
    assert out.payload["screenshot_id"] is None and "No screenshot" in out.payload["screenshot_note"]
    assert out.payload["text"] and state.sessions["screenshots"]["shots"] == []
    blank = _ability(viewer=AsyncMock(return_value=({"url": "https://a.example/", "title": ""}, None)))
    assert (await _view(blank, _state(), url="https://a.example/")).payload["screenshot_id"] is None


@pytest.mark.asyncio
async def test_a_page_that_will_not_open_is_a_plain_failure():
    ability = _ability(viewer=AsyncMock(side_effect=TimeoutError()))
    out = await _view(ability, _state())
    assert out.status == "error" and out.payload["error"] == "Could not open the page: TimeoutError"
    for bad in ("file:///etc/passwd", "javascript:alert(1)", "https://", "not a url"):
        out = await _view(_ability(), _state(), url=bad)
        assert out.status == "error" and "http(s)" in out.payload["error"], bad


def test_the_block_is_rebuilt_from_screenshots_this_run_took():
    state = _state()
    state.sessions["screenshots"] = {"shots": [
        {"id": f"s{i}", "url": f"https://cdn.example/{i}.webp", "page_url": f"https://a.example/{i}",
         "title": f"Page {i}"} for i in range(1, 7)
    ]}
    block, warnings = screenshots.gate_block("screenshots", {"screenshots": [
        {"id": "s1", "caption": "  The   unit list  "},
        {"id": "s1", "caption": "again"},
        {"id": "s9", "caption": "made up"},
        {"id": "s2"},
        "junk",
        *({"id": f"s{i}"} for i in range(3, 7)),
    ]}, state)
    assert block["screenshots"][0] == {"url": "https://cdn.example/1.webp", "page_url": "https://a.example/1",
                                       "caption": "The unit list"}
    assert block["screenshots"][1]["caption"] == "Page 2"
    assert len(block["screenshots"]) == screenshots.MAX_IN_RESULT
    assert warnings.count("Dropped a screenshot this run did not take") == 2
    assert f"Kept the first {screenshots.MAX_IN_RESULT} screenshots" in warnings
    assert screenshots.gate_block("screenshots", {"screenshots": [{"id": "s1"}]}, _state()) == (
        None, ["Dropped a screenshot this run did not take"])
    assert screenshots.gate_block("screenshots", "nope", _state()) == (None, [])


def test_offered_only_where_the_browser_queue_exists(monkeypatch):
    situation = catalog.Situation(private=True)
    assert catalog.availability(_ability(ready=False), situation).reason == "Not set up on this server yet."
    assert catalog.availability(_ability(ready=True), catalog.Situation(private=False)).available
    monkeypatch.delenv("AGENT_BROWSER_QUEUE", raising=False)
    assert not screenshots.build().env_ready()
    monkeypatch.setenv("AGENT_BROWSER_QUEUE", "agent_browser")
    assert screenshots.build().env_ready()
    # And a run that has it opens Chromium, so it goes to the browser worker.
    assert enqueue.queue_for(["web", "screenshots"]) == "agent_browser"


def test_navigation_stays_on_the_pages_own_site():
    assert screenshots._site("www.zillow.com") == "zillow.com"
    assert screenshots._site("tower737.example") == "tower737.example"
    assert screenshots._checked("https://WWW.Example.com./x") == ("https://WWW.Example.com./x", "www.example.com")


@pytest.mark.asyncio
async def test_the_browser_view_reads_the_settled_page(monkeypatch):
    calls = {}

    class Page:
        url = "https://www.example.com/units"

        async def goto(self, url, **kwargs):
            calls["goto"] = (url, kwargs)

        async def wait_for_load_state(self, state, timeout):
            raise TimeoutError("never quiet")

        async def title(self):
            return "Units"

        async def inner_text(self, selector):
            return "  Unit 1\n\n Studio   "

        async def screenshot(self, **kwargs):
            calls["shot"] = kwargs
            return b"png"

    @asynccontextmanager
    async def open_page(policy):
        calls["policy"] = policy
        yield SimpleNamespace(page=Page(), blocked_navigations=["https://elsewhere.example/"])

    monkeypatch.setattr(browser_session, "open_page", open_page)
    out, png = await screenshots._view_in_browser("https://www.example.com/units")
    assert png == b"png" and calls["shot"] == {"type": "png", "full_page": False}
    assert out == {"url": "https://www.example.com/units", "title": "Units", "text": "Unit 1 Studio",
                   "note": "The page tried to leave its own site; that was blocked."}
    assert calls["policy"].allowed_hosts == frozenset({"example.com"})
    assert calls["goto"][1]["wait_until"] == "domcontentloaded"


@pytest.mark.asyncio
async def test_screenshots_are_stored_like_photos(monkeypatch):
    store = AsyncMock(return_value="https://cdn.example/s.webp")
    monkeypatch.setattr(images, "store_image", store)
    assert await screenshots._store_screenshot(b"png", "p") == "https://cdn.example/s.webp"
    assert store.await_args.args == (b"png", "p", "screenshot.webp")
    store.side_effect = images.StorageHasNoPublicUrl("/uploads/x")
    assert await screenshots._store_screenshot(b"png", "p") is None


# ── photos from loaded pages ───────────────────────────────────────────────

def test_photos_are_only_images_a_loaded_page_showed():
    state = _state()
    web.remember_images(state, {"url": "https://www.zillow.com/a/", "og_image": "https://photos.zillow.example/1.jpg",
                                "products": [{"images": ["https://img.example/p.png", 7]}, "junk"]})
    web.remember_images(state, {"url": "https://x.example/", "error": "HTTP 403",
                                "og_image": "https://evil.example/x.png"})
    web.remember_images(state, {"og_image": "https://no-page.example/x.png"})
    web.remember_images(state, "junk")
    block, warnings = web.gate_block("photos", {"photos": [
        {"source_url": "https://photos.zillow.example/1.jpg", "alt": "  Tower 737   lobby "},
        {"source_url": "https://photos.zillow.example/1.jpg"},
        {"source_url": "https://evil.example/x.png"},
        {"source_url": "https://img.example/p.png", "page_url": "https://lies.example/"},
        "junk",
    ]}, state)
    assert block == {"type": "photos", "photos": [
        {"source_url": "https://photos.zillow.example/1.jpg", "page_url": "https://www.zillow.com/a/",
         "alt": "Tower 737 lobby"},
        {"source_url": "https://img.example/p.png", "page_url": "https://www.zillow.com/a/", "alt": ""},
    ]}
    assert warnings == ["Dropped a photo no loaded page showed"] * 2
    assert web.gate_block("photos", {"photos": []}, _state()) == (None, [])


def test_photos_are_capped():
    state = _state()
    web.remember_images(state, {"url": "https://a.example/", "products": [
        {"images": [f"https://img.example/{i}.png" for i in range(9)]}]})
    block, warnings = web.gate_block("photos", {"photos": [
        {"source_url": f"https://img.example/{i}.png"} for i in range(9)]}, state)
    assert len(block["photos"]) == web.MAX_PHOTOS and warnings == [f"Kept the first {web.MAX_PHOTOS} photos"]


@pytest.mark.asyncio
async def test_fetch_page_remembers_what_it_saw():
    page = {"url": "https://a.example/", "og_image": "https://img.example/a.png"}
    tool = web.fetch_tool(fetch_page=AsyncMock(return_value=(page, {"https://a.example/"})),
                          max_fetches=3, fetch_seconds=5)
    state = _state()
    await tool.handler(context(), state, {"url": "https://a.example/"}, 30.0)
    assert state.sessions["page_images"] == {"https://img.example/a.png": "https://a.example/"}
