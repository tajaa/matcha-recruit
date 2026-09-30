import asyncio

import pytest

from app.matcha.services.matcha_work.browser import computer_use
from app.matcha.services.matcha_work.browser.computer_use import ActionVerdict
from app.matcha.services.matcha_work.browser.session import BrowsePolicy

from .fakes import FakeModel, FakePage, action, reply

ONE_SITE = BrowsePolicy(allowed_hosts=frozenset({"tables.example"}), max_turns=5, wall_seconds=30)


async def drive(page, model, policy=ONE_SITE, **kw):
    return await computer_use.run(page, instructions="book it", model="m", policy=policy,
                                  client=model, settle_seconds=0, **kw)


@pytest.mark.asyncio
async def test_a_text_reply_ends_the_loop():
    page = FakePage()
    statuses = []

    async def on_status(text):
        statuses.append(text)

    model = FakeModel([reply(action("click_at", x=500, y=500)), reply("CONFIRMED", "AB12", tokens=7)])
    out = await drive(page, model, on_status=on_status)
    assert out.text == "CONFIRMED\nAB12" and out.turns == 2 and out.total_tokens == 17
    assert out.stopped is None and out.final_url == page.url
    assert page.log == [("mouse.click", (720, 450))]
    assert statuses[0] == "Analyzing page... (step 1/5)" and "clicking on element" in statuses[1]
    # The first message is the instructions and a screenshot.
    first = model.calls[0]["contents"][0]
    assert first.parts[0].text == "book it" and first.parts[1].inline_data.mime_type == "image/png"


@pytest.mark.asyncio
async def test_every_action_maps_to_the_page():
    page = FakePage()
    model = FakeModel([reply(
        action("double_click_at", x=0, y=0), action("hover_at", x=1000, y=1000),
        action("type_text_at", x=100, y=100, text="hi", clear_before_typing=True, press_enter_after_typing=True),
        action("scroll_document", direction="down", amount=2), action("scroll_at", x=10, y=10, direction="left"),
        action("navigate", url="https://www.tables.example/next"), action("go_back"), action("go_forward"),
        action("key_combination", keys="Control a"), action("wait", seconds=0), action("made_up"),
    ), reply("done")])
    out = await drive(page, model)
    names = [entry[0] for entry in page.log]
    assert names == [
        "mouse.dblclick", "mouse.move", "mouse.click", "keyboard.press", "keyboard.press", "keyboard.type",
        "keyboard.press", "mouse.wheel", "mouse.move", "mouse.wheel", "goto", "go_back", "go_forward",
        "keyboard.press",
    ]
    assert page.log[5] == ("keyboard.type", ("hi",)) and page.log[7] == ("mouse.wheel", (0, 200))
    assert page.log[9] == ("mouse.wheel", (-300, 0)) and page.log[13] == ("keyboard.press", ("Control+a",))
    assert out.text == "done"
    assert computer_use.describe_action("navigate", {"url": "https://x.example"}).startswith("navigating")
    assert computer_use.describe_action("scroll_at", {}) == "scrolling down"
    assert computer_use.describe_action("type_text_at", {}) == "typing text"
    assert computer_use.describe_action("go_back", {}) == "go back"


@pytest.mark.asyncio
async def test_a_navigation_off_the_allowed_site_is_refused_and_the_model_is_told():
    page = FakePage()
    model = FakeModel([
        reply(action("navigate", url="https://evil.example/steal"), action("search", query="best tables")),
        reply("UNAVAILABLE"),
    ])
    out = await drive(page, model)
    assert page.log == [] and page.url == "https://www.tables.example/r/nopa"
    assert out.refused == ["navigate outside the allowed site", "search outside the allowed site"]
    told = model.calls[1]["contents"][-2].parts
    assert [p.function_response.response["status"] for p in told] == [
        "refused: that address is outside the site you may use"] * 2


@pytest.mark.asyncio
async def test_research_may_search_and_go_anywhere_public():
    page = FakePage()
    model = FakeModel([reply(action("search", query="two bed flats"),
                             action("navigate", url="https://other.example/")), reply("{}")])
    await drive(page, model, policy=BrowsePolicy(allowed_hosts=None, max_turns=3))
    assert page.log == [("goto", ("https://www.google.com/search?q=two+bed+flats",)),
                        ("goto", ("https://other.example/",))]


@pytest.mark.asyncio
async def test_the_hook_can_stop_refuse_or_rewrite_an_action():
    page = FakePage()

    async def hook(page, name, args):
        if name == "click_at":
            return ActionVerdict(allow=False, note="not that button")
        if args.get("text") == "{{name}}":
            return ActionVerdict(args={**args, "text": "Ana Lee"})
        if args.get("text") == "4242":
            return ActionVerdict(stop="handoff")
        return None

    model = FakeModel([
        reply(action("click_at", x=1, y=1), action("type_text_at", x=1, y=1, text="{{name}}")),
        reply(action("type_text_at", x=1, y=1, text="4242"), action("click_at", x=9, y=9)),
        reply("never reached"),
    ])
    out = await drive(page, model, before_action=hook)
    assert out.stopped == "handoff" and out.turns == 2 and out.text == ""
    assert ("keyboard.type", ("Ana Lee",)) in page.log
    assert ("keyboard.type", ("4242",)) not in page.log
    assert out.refused == ["not that button"]
    assert len(model.replies) == 1


@pytest.mark.asyncio
async def test_the_turn_and_time_budgets_end_the_loop():
    page = FakePage()
    model = FakeModel([reply(action("wait", seconds=0))] * 3)
    out = await drive(page, model, policy=BrowsePolicy(allowed_hosts=None, max_turns=3))
    assert out.stopped == "turns" and out.turns == 3
    out = await drive(page, FakeModel([]), policy=BrowsePolicy(allowed_hosts=None, max_turns=3, wall_seconds=0))
    assert out.stopped == "time" and out.turns == 0


@pytest.mark.asyncio
async def test_a_model_failure_or_timeout_ends_the_loop(monkeypatch):
    page = FakePage()
    out = await drive(page, FakeModel([RuntimeError("quota")]))
    assert out.error == "RuntimeError" and out.turns == 1

    async def too_slow(awaitable, *_a, **_k):
        getattr(awaitable, "close", lambda: None)()
        raise asyncio.TimeoutError()

    statuses = []

    async def on_status(text):
        statuses.append(text)

    monkeypatch.setattr(computer_use.asyncio, "wait_for", too_slow)
    out = await drive(page, FakeModel([reply("x")]), on_status=on_status)
    assert out.error == "model_timeout" and any("timed out" in s for s in statuses)


@pytest.mark.asyncio
async def test_an_empty_reply_and_a_failing_action_do_not_crash():
    from types import SimpleNamespace

    page = FakePage()
    out = await drive(page, FakeModel([SimpleNamespace(candidates=[], usage_metadata=None)]))
    assert out.text == "" and out.turns == 1

    async def broken(*_a, **_k):
        raise RuntimeError("detached")

    page.mouse.click = broken
    out = await drive(page, FakeModel([reply(action("click_at", x=1, y=1)), reply("ok")]))
    assert out.text == "ok"
