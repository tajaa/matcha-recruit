import pytest

from app.matcha.services.matcha_work import research_browse_service as service
from app.matcha.services.matcha_work.browser import computer_use, session

from .fakes import FakeModel, FakePage, reply, session_factory


def _wire(monkeypatch, page, outcome, model, policies):
    async def run(page, *, instructions, model, policy, client, on_status):
        outcome.contents = ["history"]
        run.seen = dict(instructions=instructions, policy=policy)
        return outcome

    monkeypatch.setattr(session, "open_page", session_factory(page, policies))
    monkeypatch.setattr(computer_use, "run", run)
    monkeypatch.setattr("app.matcha.services._shared.gemini.genai_env_client", lambda: model)
    monkeypatch.setattr(service, "_twilio_configured", lambda: False)
    from types import SimpleNamespace

    monkeypatch.setattr("app.config.get_settings", lambda: SimpleNamespace(analysis_model="gemini-test"))

    async def no_sleep(_s):
        return None

    monkeypatch.setattr(service.asyncio, "sleep", no_sleep)
    return run


@pytest.mark.asyncio
async def test_research_browse_still_returns_the_same_shape(monkeypatch):
    page, policies = FakePage(url="about:blank"), []
    outcome = computer_use.Outcome(text='Here you go: {"rent": 2400, "summary": "Two bed"}', total_tokens=321)
    run = _wire(monkeypatch, page, outcome, FakeModel([]), policies)
    statuses = []

    async def on_status(text):
        statuses.append(text)

    out = await service.browse_and_extract("https://flats.example/unit/2", "Find the rent", on_status=on_status)
    assert out == {"findings": {"rent": 2400}, "summary": "Two bed", "error": None,
                   "screenshot_url": None, "total_tokens": 321}
    assert page.log == [("goto", ("https://flats.example/unit/2",))]
    assert statuses == ["Navigating to https://flats.example/unit/2..."]
    # Research follows links anywhere public; what it can connect to is the proxy's business.
    assert policies[0].allowed_hosts is None and policies[0].max_turns == service.MAX_TURNS
    assert "Find the rent" in run.seen["instructions"]


@pytest.mark.asyncio
async def test_prose_becomes_the_summary_and_nothing_is_asked_again(monkeypatch):
    page = FakePage()
    model = FakeModel([])
    _wire(monkeypatch, page, computer_use.Outcome(text="Rent is about $2,400."), model, [])
    out = await service.browse_and_extract("https://flats.example/", "Find the rent")
    assert out["summary"] == "Rent is about $2,400." and out["findings"] == {} and model.calls == []


@pytest.mark.asyncio
async def test_a_run_that_ends_without_an_answer_is_asked_to_compile_one(monkeypatch):
    page = FakePage()
    model = FakeModel([reply('{"rent": 2400, "summary": "Compiled"}')])
    _wire(monkeypatch, page, computer_use.Outcome(text="", stopped="turns", total_tokens=5), model, [])
    out = await service.browse_and_extract("https://flats.example/", "Find the rent")
    assert out["findings"] == {"rent": 2400} and out["summary"] == "Compiled"
    assert model.calls[0]["contents"][-1].parts[0].text.startswith("Stop browsing.")

    nothing = FakeModel([reply("I could not find it.")])
    _wire(monkeypatch, page, computer_use.Outcome(text=""), nothing, [])
    out = await service.browse_and_extract("https://flats.example/", "Find the rent")
    assert out["error"] == "No data extracted" and out["summary"] == "Could not extract data"

    failing = FakeModel([RuntimeError("quota")])
    _wire(monkeypatch, page, computer_use.Outcome(text=""), failing, [])
    assert (await service.browse_and_extract("https://flats.example/", "x"))["error"] == "No data extracted"


@pytest.mark.asyncio
async def test_a_start_address_that_is_not_a_web_page_is_never_opened(monkeypatch):
    page = FakePage()
    _wire(monkeypatch, page, computer_use.Outcome(text='{"summary": "s"}'), FakeModel([]), [])
    await service.browse_and_extract("file:///etc/passwd", "read it")
    assert page.log == []


def test_findings_are_parsed_from_a_reply():
    assert service._parse_findings('x {"a": 1} y') == {"a": 1}
    assert service._parse_findings("{broken") == {"summary": "{broken"}
    assert service._parse_findings("{not json}") == {"summary": "{not json}"}
    assert service._parse_findings("no braces") == {"summary": "no braces"}
    assert service._parse_findings("no braces", prose_as_summary=False) is None


@pytest.mark.asyncio
async def test_the_outer_deadline_is_reported_as_a_timeout(monkeypatch):
    async def too_slow(awaitable, *_a, **_k):
        awaitable.close()
        raise service.asyncio.TimeoutError()

    monkeypatch.setattr(service.asyncio, "wait_for", too_slow)
    out = await service.browse_and_extract("https://flats.example/", "x")
    assert out["error"] == "Timed out"
