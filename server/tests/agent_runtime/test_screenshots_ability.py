import asyncio
from contextlib import asynccontextmanager
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from app.matcha.services.matcha_work.browser import session as browser_session
from app.matcha.services.matcha_work.agent_card import images
from app.matcha.services.matcha_work.agent_runtime import catalog, enqueue, result
from app.matcha.services.matcha_work.agent_runtime.abilities import screenshots, web
from app.matcha.services.matcha_work.agent_runtime.context import RunState
from app.workers import celery_app as celery_module
from app.workers.tasks import assistant as assistant_tasks

from .helpers import context

PAGE = {"url": "https://www.elevateto737.example/floor-plans", "title": "Floor Plans",
        "text": "Unit 0217 Studio $2,604 Available now\nLeasing: leasing@elevateto737.example",
        "screenshot_url": "https://cdn.example/shot.webp"}


def _state():
    return RunState(started=0.0)


def _ability(viewer=None, ready=True):
    return screenshots.build(viewer=viewer or AsyncMock(return_value=dict(PAGE)), env_ready=lambda: ready)


async def _view(ability, state, url="https://www.elevateto737.example/floor-plans", ctx=None):
    tool = ability.tools[0]
    return await tool.handler(ctx or context(storage_prefix="matcha-work/c/assistant/ch/run"), state, {"url": url}, 60.0)


@pytest.mark.asyncio
async def test_a_view_returns_the_drawn_text_and_a_screenshot_id_never_the_image_url():
    viewer = AsyncMock(return_value=dict(PAGE))
    ability, state = _ability(viewer=viewer), _state()
    out = await _view(ability, state)
    assert out.status == "ok"
    assert out.payload["text"].startswith("Unit 0217") and out.payload["screenshot_id"] == "s1"
    assert "cdn.example" not in str(out.payload)
    assert out.provenance == {"https://www.elevateto737.example/floor-plans"}
    assert viewer.await_args.args == ("https://www.elevateto737.example/floor-plans",
                                      "matcha-work/c/assistant/ch/run/screenshots")
    assert state.sessions["screenshots"]["shots"] == [{
        "id": "s1", "url": "https://cdn.example/shot.webp",
        "page_url": "https://www.elevateto737.example/floor-plans", "title": "Floor Plans",
    }]
    # An address the page showed counts as seen on a page (the sales email check).
    assert "leasing@elevateto737.example" in state.observed_emails
    second = await _view(ability, state)
    assert second.payload["screenshot_id"] == "s2"


@pytest.mark.asyncio
async def test_no_stored_screenshot_still_gives_the_text():
    for kept in (None, "http://cdn.example/shot.webp", ["https://cdn.example/x.webp"]):
        ability, state = _ability(viewer=AsyncMock(return_value={**PAGE, "screenshot_url": kept})), _state()
        out = await _view(ability, state)
        assert out.payload["screenshot_id"] is None and "No screenshot" in out.payload["screenshot_note"], kept
        assert out.payload["text"] and state.sessions["screenshots"]["shots"] == []
        assert "screenshot_url" not in out.payload


@pytest.mark.asyncio
async def test_a_page_that_will_not_open_is_a_plain_failure_and_never_a_source():
    state = _state()
    ability = _ability(viewer=AsyncMock(return_value={"url": PAGE["url"], "error": "HTTP 404"}))
    out = await _view(ability, state)
    assert out.status == "error" and out.payload == {"url": PAGE["url"], "error": "Could not open the page: HTTP 404"}
    assert out.provenance == frozenset() and state.sessions.get("screenshots", {"shots": []})["shots"] == []
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
        # Ids that are not strings are refused, never looked up.
        {"id": ["s3"]},
        {"id": {"s": 3}},
        *({"id": f"s{i}"} for i in range(3, 7)),
    ]}, state)
    assert block["screenshots"][0] == {"url": "https://cdn.example/1.webp", "page_url": "https://a.example/1",
                                       "caption": "The unit list"}
    assert block["screenshots"][1]["caption"] == "Page 2"
    assert len(block["screenshots"]) == screenshots.MAX_IN_RESULT
    assert warnings.count("Dropped a screenshot this run did not take") == 4
    assert f"Kept the first {screenshots.MAX_IN_RESULT} screenshots" in warnings
    assert screenshots.gate_block("screenshots", {"screenshots": [{"id": "s1"}]}, _state()) == (
        None, ["Dropped a screenshot this run did not take"])
    assert screenshots.gate_block("screenshots", "nope", _state()) == (None, [])


def test_a_gate_that_trips_costs_its_block_not_the_answer():
    def broken(_kind, _raw, _state):
        raise TypeError("unhashable type: 'list'")

    def refusing(_kind, _raw, _state):
        raise ValueError("ask again")

    finish = {"headline": "Tower 737", "summary": "Three studios.",
              "blocks": [{"type": "screenshots", "screenshots": [{"id": ["s1"]}]}]}
    tripped = screenshots.build(env_ready=lambda: True)
    object.__setattr__(tripped, "gate", broken)
    normalized, warnings = result.normalize(finish, _state(), [tripped])
    assert normalized["headline"] == "Tower 737" and not normalized.get("blocks")
    assert "Dropped a screenshots block: it could not be read" in warnings
    # A gate's ValueError is still the loop's ask-again signal.
    object.__setattr__(tripped, "gate", refusing)
    with pytest.raises(ValueError):
        result.normalize(finish, _state(), [tripped])


def test_offered_only_where_the_browser_queue_exists_and_never_moves_the_run(monkeypatch):
    situation = catalog.Situation(private=True)
    assert catalog.availability(_ability(ready=False), situation).reason == "Not set up on this server yet."
    assert catalog.availability(_ability(ready=True), catalog.Situation(private=False)).available
    monkeypatch.delenv("AGENT_BROWSER_QUEUE", raising=False)
    assert not screenshots.build().env_ready()
    monkeypatch.setenv("AGENT_BROWSER_QUEUE", "agent_browser")
    monkeypatch.setenv("AGENT_ASSISTANT_QUEUE", "assistant_runs")
    assert screenshots.build().env_ready()
    # Each view is its own browser task; the run stays on the assistant queue.
    assert enqueue.queue_for(["web", "screenshots"]) == "assistant_runs"
    # A booking drives the browser inside the run, so that run moves.
    assert enqueue.queue_for(["web", "screenshots", "reservations"]) == "agent_browser"


def test_navigation_stays_on_the_pages_own_site():
    assert screenshots._site("www.zillow.com") == "zillow.com"
    assert screenshots._site("tower737.example") == "tower737.example"
    assert screenshots._checked("https://WWW.Example.com./x") == ("https://WWW.Example.com./x", "www.example.com")


def _browser(monkeypatch, *, status=200, goto_error=None, blocked=(), lands="https://www.example.com/units",
             settles=None):
    calls = {}

    class Page:
        url = "about:blank"

        async def goto(self, url, **kwargs):
            calls["goto"] = (url, kwargs)
            if goto_error:
                raise goto_error
            self.url = lands
            return None if status is None else SimpleNamespace(status=status)

        async def wait_for_load_state(self, state, timeout):
            if settles:
                self.url = settles
            raise TimeoutError("never quiet")

        async def title(self):
            return "Units"

        async def inner_text(self, selector):
            return "  Unit 1   Studio\n\n   $2,604   \n Unit 2 One bed\n"

        async def screenshot(self, **kwargs):
            calls["shot"] = kwargs
            return b"png"

    @asynccontextmanager
    async def open_page(policy):
        calls["policy"] = policy
        yield SimpleNamespace(page=Page(), blocked_navigations=list(blocked))

    monkeypatch.setattr(browser_session, "open_page", open_page)
    return calls


@pytest.mark.asyncio
async def test_the_browser_view_reads_the_settled_page_row_by_row(monkeypatch):
    calls = _browser(monkeypatch, blocked=["https://elsewhere.example/"])
    out, png = await screenshots._view_in_browser("https://www.example.com/units")
    assert png == b"png" and calls["shot"] == {"type": "png", "full_page": False}
    # Each row keeps its own line, so a price stays with its unit.
    assert out == {"url": "https://www.example.com/units", "title": "Units",
                   "text": "Unit 1 Studio\n$2,604\nUnit 2 One bed",
                   "note": "The page tried to leave its own site; that was blocked."}
    assert calls["policy"].allowed_hosts == frozenset({"example.com"})
    assert calls["goto"][1]["wait_until"] == "domcontentloaded"
    _browser(monkeypatch, status=None)
    assert (await screenshots._view_in_browser("https://www.example.com/units"))[0]["title"] == "Units"


@pytest.mark.asyncio
@pytest.mark.parametrize("status", [403, 404, 503])
async def test_an_error_page_is_refused_not_read(monkeypatch, status):
    calls = _browser(monkeypatch, status=status)
    with pytest.raises(screenshots.ViewRefused, match=f"HTTP {status}"):
        await screenshots._view_in_browser("https://www.example.com/units")
    assert "shot" not in calls


@pytest.mark.asyncio
async def test_a_first_load_that_leaves_the_site_says_so(monkeypatch):
    _browser(monkeypatch, goto_error=RuntimeError("net::ERR_BLOCKED_BY_CLIENT"),
             blocked=["https://login.elsewhere.example/sso"])
    with pytest.raises(screenshots.ViewRefused, match="redirected to login.elsewhere.example, off its own site"):
        await screenshots._view_in_browser("https://www.example.com/units")
    _browser(monkeypatch, goto_error=RuntimeError("net::ERR_NAME_NOT_RESOLVED"))
    with pytest.raises(RuntimeError):
        await screenshots._view_in_browser("https://www.example.com/units")


@pytest.mark.asyncio
async def test_an_http_redirect_off_the_site_is_caught_where_the_page_lands(monkeypatch):
    # Playwright never routes a redirect hop, so the guard cannot stop it.
    calls = _browser(monkeypatch, lands="https://example.org/")
    with pytest.raises(screenshots.ViewRefused, match="redirected to example.org, off its own site"):
        await screenshots._view_in_browser("https://www.example.com/units")
    assert "shot" not in calls
    # Or once the page has settled (a script's navigation that then redirects).
    calls = _browser(monkeypatch, settles="https://tracker.example.net/x")
    with pytest.raises(screenshots.ViewRefused, match="redirected to tracker.example.net"):
        await screenshots._view_in_browser("https://www.example.com/units")
    assert "shot" not in calls
    # A hop within the site (apex to www) is fine.
    _browser(monkeypatch, lands="https://example.com/units")
    assert (await screenshots._view_in_browser("https://www.example.com/units"))[0]["title"] == "Units"


@pytest.mark.asyncio
async def test_view_and_store_always_answers_in_json(monkeypatch):
    store = AsyncMock(return_value="https://cdn.example/s.webp")
    monkeypatch.setattr(screenshots, "_store_screenshot", store)
    page = {"url": "https://a.example/", "title": "A", "text": "x"}
    monkeypatch.setattr(screenshots, "_view_in_browser", AsyncMock(return_value=(dict(page), b"png")))
    assert await screenshots.view_and_store("https://a.example/", "p") == {**page, "screenshot_url": "https://cdn.example/s.webp"}
    assert store.await_args.args == (b"png", "p")
    monkeypatch.setattr(screenshots, "_view_in_browser", AsyncMock(return_value=(dict(page), None)))
    assert (await screenshots.view_and_store("https://a.example/", "p"))["screenshot_url"] is None
    for raised, said in ((screenshots.ViewRefused("HTTP 404"), "HTTP 404"), (OSError("boom"), "OSError")):
        monkeypatch.setattr(screenshots, "_view_in_browser", AsyncMock(side_effect=raised))
        assert await screenshots.view_and_store("https://a.example/", "p") == {"url": "https://a.example/", "error": said}

    async def slow(_url, _recap=None):
        await asyncio.sleep(5)

    # The whole view, launch included, is held to VIEW_SECONDS.
    monkeypatch.setattr(screenshots, "VIEW_SECONDS", 0.01)
    monkeypatch.setattr(screenshots, "_view_in_browser", slow)
    assert await screenshots.view_and_store("https://a.example/", "p") == {
        "url": "https://a.example/", "error": "it took too long to load"}


@pytest.mark.asyncio
async def test_recap_capture_is_stored_after_the_views_own_budget(monkeypatch):
    # A page that loaded within VIEW_SECONDS never times out over recap storage.
    monkeypatch.setattr(screenshots, "_store_screenshot", AsyncMock(return_value="https://cdn.example/s.webp"))
    stored = []

    async def view(_url, recap):
        async def store():
            await asyncio.sleep(0.05)
            stored.append(True)
        recap.store = store
        return {"url": "https://a.example/", "title": "A", "text": "x"}, b"png"

    monkeypatch.setattr(screenshots, "VIEW_SECONDS", 0.02)
    monkeypatch.setattr(screenshots, "_view_in_browser", view)
    out = await screenshots.view_and_store("https://a.example/", "p")
    assert out["screenshot_url"] == "https://cdn.example/s.webp" and stored == [True]


@pytest.mark.asyncio
async def test_screenshots_are_stored_like_photos(monkeypatch):
    store = AsyncMock(return_value="https://cdn.example/s.webp")
    monkeypatch.setattr(images, "store_image", store)
    assert await screenshots._store_screenshot(b"png", "p") == "https://cdn.example/s.webp"
    assert store.await_args.args == (b"png", "p", "screenshot.webp")
    store.side_effect = images.StorageHasNoPublicUrl("/uploads/x")
    assert await screenshots._store_screenshot(b"png", "p") is None


# ── where a view runs ──────────────────────────────────────────────────────

class _Pending:
    def __init__(self, states, result=None):
        self.states, self._result = list(states), result

    @property
    def state(self):
        return self.states.pop(0) if len(self.states) > 1 else self.states[0]

    @property
    def result(self):
        return self._result


def _task(monkeypatch, pending):
    sent = {}

    def apply_async(**kwargs):
        sent.update(kwargs)
        return pending

    monkeypatch.setattr(assistant_tasks.view_page, "apply_async", apply_async)
    monkeypatch.setattr(screenshots, "_POLL_SECONDS", 0)
    monkeypatch.setenv("AGENT_BROWSER_QUEUE", "agent_browser")
    return sent


@pytest.mark.asyncio
async def test_a_view_from_another_worker_is_a_browser_task(monkeypatch):
    page = {**PAGE}
    sent = _task(monkeypatch, _Pending(["PENDING", "STARTED", "SUCCESS"], page))
    assert await screenshots._view_on_browser_worker(PAGE["url"], "p") == page
    assert sent == {"args": [PAGE["url"], "p"], "queue": "agent_browser", "expires": screenshots.QUEUE_SECONDS}
    _task(monkeypatch, _Pending(["FAILURE"]))
    assert (await screenshots._view_on_browser_worker(PAGE["url"], "p"))["error"] == "the browser task failed"
    _task(monkeypatch, _Pending(["SUCCESS"], "junk"))
    assert (await screenshots._view_on_browser_worker(PAGE["url"], "p"))["error"] == "no result"


@pytest.mark.asyncio
async def test_a_busy_or_slow_browser_worker_is_a_plain_no(monkeypatch):
    # Still queued: called off (and dropped by `expires`) rather than waited on.
    _task(monkeypatch, _Pending(["PENDING"]))
    monkeypatch.setattr(screenshots, "QUEUE_SECONDS", 0)
    assert await screenshots._view_on_browser_worker(PAGE["url"], "p") == {"url": PAGE["url"], "error": screenshots.BUSY}
    _task(monkeypatch, _Pending(["STARTED"]))
    monkeypatch.setattr(screenshots, "VIEW_SECONDS", 0)
    monkeypatch.setattr(screenshots, "STORE_SECONDS", 0)
    assert (await screenshots._view_on_browser_worker(PAGE["url"], "p"))["error"] == "it took too long to load"


@pytest.mark.asyncio
async def test_a_run_on_the_browser_worker_views_in_process(monkeypatch):
    here, there = AsyncMock(return_value={"where": "here"}), AsyncMock(return_value={"where": "there"})
    monkeypatch.setattr(screenshots, "view_and_store", here)
    monkeypatch.setattr(screenshots, "_view_on_browser_worker", there)
    monkeypatch.setenv("AGENT_BROWSER_QUEUE", "agent_browser")
    # Waiting on its own queue from its one slot would wait on itself.
    monkeypatch.setattr(celery_module, "_consumed_queues", frozenset({"agent_cards", "agent_browser"}))
    assert await screenshots.view("https://a.example/", "p") == {"where": "here"}
    monkeypatch.setattr(celery_module, "_consumed_queues", frozenset({"assistant_runs"}))
    assert await screenshots.view("https://a.example/", "p") == {"where": "there"}
    assert there.await_args.args == ("https://a.example/", "p")


def test_a_worker_process_knows_the_queues_it_was_started_for(monkeypatch):
    monkeypatch.setattr(celery_module, "_consumed_queues", None)
    # Outside a worker (the API) nothing counts as served here.
    assert not celery_module.consumes_queue("agent_browser")
    monkeypatch.setattr(celery_module.celery_app.amqp.queues, "_consume_from", {"agent_cards": None, "agent_browser": None})
    celery_module._note_consumed_queues()
    assert celery_module.consumes_queue("agent_browser") and celery_module.consumes_queue("agent_cards")
    assert not celery_module.consumes_queue("celery") and not celery_module.consumes_queue(None)


def test_the_browser_task_runs_the_view(monkeypatch):
    view = AsyncMock(return_value={"url": "https://a.example/", "error": "HTTP 404"})
    monkeypatch.setattr(screenshots, "view_and_store", view)
    assert assistant_tasks.view_page.run("https://a.example/", "p") == {"url": "https://a.example/", "error": "HTTP 404"}
    assert view.await_args.args == ("https://a.example/", "p")
    # Its own limits sit above the view's: the view times itself out first.
    assert assistant_tasks.view_page.soft_time_limit > screenshots.VIEW_SECONDS + screenshots.STORE_SECONDS


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
