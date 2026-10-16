"""`web_search`: Brave when it has a key, the model's own search when Brave can't answer."""
import json
import time

import pytest

from app.core.services.anthropic_messages import CLAUDE_HAIKU, CLAUDE_SONNET
from app.matcha.services.matcha_work import brave_search
from app.matcha.services.matcha_work.agent_runtime import runner
from app.matcha.services.matcha_work.agent_runtime.abilities import web
from app.matcha.services.matcha_work.agent_runtime.context import RunLimits, RunState

from .helpers import FakeClient, ability, call, context, contract, response, wire_store

BRAVE_RESULTS = [
    {"title": "A", "url": "https://a.example/", "description": "about a"},
    {"title": "B", "url": "https://b.example/", "description": "about b"},
]


@pytest.fixture(autouse=True)
def _brave(monkeypatch):
    monkeypatch.setattr(brave_search, "_key", lambda: "brave-key")
    brave_search.reset()
    yield
    brave_search.reset()


def _model_answer(*, text="A | https://m.example/a | the facts"):
    return response(text=text, output=[
        {"type": "web_search_call", "status": "completed",
         "action": {"type": "search", "query": "q", "sources": [
             {"type": "url", "url": "https://m.example/a", "title": "M A"},
             {"type": "url", "url": "https://m.example/a"},
             {"type": "url", "url": "https://m.example/b"},
         ]}},
        {"type": "message", "content": [{"type": "output_text", "text": text, "annotations": [
            {"type": "url_citation", "url": "https://m.example/cited"}]}]},
    ])


def _model(monkeypatch, *answers):
    fake = FakeClient(list(answers) or [_model_answer()])
    picked = []

    def client_for(model):
        picked.append(model)
        return fake

    monkeypatch.setattr(web, "_model_client", client_for)
    return fake, picked


def _brave_answers(monkeypatch, *outcomes):
    asked = []

    async def search(query, *, freshness=None):
        asked.append((query, freshness))
        outcome = outcomes[len(asked) - 1]
        if isinstance(outcome, Exception):
            raise outcome
        return outcome

    monkeypatch.setattr(brave_search, "search", search)
    return asked


async def _handle(tool, args, ctx=None, state=None):
    state = state or RunState(started=time.monotonic())
    return await tool.handler(ctx or context(), state, args, 60.0), state


def test_the_tool_follows_the_key(monkeypatch):
    tool = web.search_tool()
    assert tool.hosted is None and tool.handler is not None
    assert tool.parameters["required"] == ["query"]
    assert web.search_tool(untrusted=True).untrusted_output
    monkeypatch.setattr(brave_search, "_key", lambda: None)
    hosted = web.search_tool()
    assert hosted.hosted == web.WEB_SEARCH_TOOL and hosted.observe is web.observe_searches
    # The ability's own search tool is the one the key picks.
    built = web.build(fetch_page=None, max_fetches=1, fetch_seconds=1)
    assert built.tools[0].hosted is not None


@pytest.mark.asyncio
async def test_brave_answers_and_its_urls_are_provenance(monkeypatch):
    asked = _brave_answers(monkeypatch, BRAVE_RESULTS)
    fake, _ = _model(monkeypatch)
    ctx = context()
    out, state = await _handle(web.brave_tool(), {"query": "  lip   balm ", "freshness": "week"}, ctx)
    assert asked == [("lip balm", "week")]
    assert out.payload == {"query": "lip balm", "results": BRAVE_RESULTS}
    assert out.provenance == {"https://a.example/", "https://b.example/"}
    assert out.audit == {"query": "lip balm", "freshness": "week", "by": "brave", "results": 2}
    assert out.usage is None and fake.calls == []
    assert state.hosted_calls == 1 and ctx.progress.notes == ["Searched the web (1)…"]


@pytest.mark.asyncio
async def test_brave_out_mid_run_hands_the_search_to_the_model(monkeypatch):
    _brave_answers(monkeypatch, brave_search.Unavailable("Brave has no searches left this period", out=True))
    fake, picked = _model(monkeypatch)
    ctx = context(model=CLAUDE_SONNET, usage_feature="matcha.espresso")
    out, _ = await _handle(web.brave_tool(), {"query": "lip balm", "freshness": "decade"}, ctx)
    # Claude runs search on Haiku, the cheapest Claude; same search either way.
    assert picked == [CLAUDE_HAIKU]
    sent = fake.calls[0]
    assert sent["model"] == CLAUDE_HAIKU and sent["tools"] == [web.WEB_SEARCH_TOOL]
    assert sent["max_tool_calls"] == 1 and sent["store"] is False and sent["chain"] is False
    assert sent["include"] == list(web.RESPONSE_INCLUDE) and sent["feature"] == "matcha.espresso"
    assert sent["input"][0]["content"][0]["text"] == "Query: lip balm"  # an unknown freshness is dropped
    assert out.payload == {
        "query": "lip balm",
        "results": [{"title": "M A", "url": "https://m.example/a"}, {"title": "", "url": "https://m.example/b"}],
        "summary": "A | https://m.example/a | the facts",
    }
    assert out.provenance == {"https://m.example/a", "https://m.example/b", "https://m.example/cited"}
    assert out.usage == {"input_tokens": 10, "output_tokens": 2, "total_tokens": 12}
    assert out.audit["by"] == "model" and "no searches left" in out.audit["why"]


@pytest.mark.asyncio
async def test_while_brave_is_out_it_is_not_asked(monkeypatch):
    brave_search.mark_out("Brave refused the API key (401)", 600)
    asked = _brave_answers(monkeypatch)
    fake, picked = _model(monkeypatch, _model_answer(text=""))
    ctx = context(model="gpt-5.6-luna")
    out, _ = await _handle(web.brave_tool(), {"query": "news", "freshness": "day"}, ctx)
    assert asked == [] and picked == ["gpt-5.6-luna"]  # not Claude: the run's own model
    assert "Prefer pages from the last day." in fake.calls[0]["input"][0]["content"][0]["text"]
    assert "summary" not in out.payload
    assert out.audit["why"] == "Brave refused the API key (401)"


@pytest.mark.asyncio
async def test_without_a_key_the_tool_still_searches_through_the_model(monkeypatch):
    monkeypatch.setattr(brave_search, "_key", lambda: None)
    _model(monkeypatch)
    out, _ = await _handle(web.brave_tool(), {"query": "q"})
    assert out.audit["by"] == "model" and out.audit["why"] == "no Brave key"


@pytest.mark.asyncio
async def test_bad_arguments_and_a_spent_budget_search_nothing(monkeypatch):
    asked = _brave_answers(monkeypatch)
    fake, _ = _model(monkeypatch)
    out, state = await _handle(web.brave_tool(), {"query": "   "})
    assert "query" in out.payload["error"] and state.hosted_calls == 0
    ctx = context(limits=RunLimits(max_hosted_per_run=2))
    state = RunState(started=time.monotonic(), hosted_calls=2)
    out, _ = await _handle(web.brave_tool(), {"query": "q"}, ctx, state)
    assert out.payload == {"error": web.SEARCH_EXHAUSTED}
    assert asked == [] and fake.calls == [] and state.hosted_calls == 2


@pytest.mark.asyncio
async def test_a_run_counts_searches_and_the_models_search_tokens(monkeypatch):
    record, _, _ = wire_store(monkeypatch)
    _brave_answers(monkeypatch, BRAVE_RESULTS, brave_search.Unavailable("Brave did not answer: 503"))
    _model(monkeypatch)
    client = FakeClient([
        response(call("web_search", {"query": "one"}), call("web_search", {"query": "two"})),
        response(call("finish", {"answer": "ok"})),
    ])
    ctx = context(model=CLAUDE_HAIKU)
    out = await runner.run_agent(
        ctx, client=client, abilities=[ability(web.brave_tool(untrusted=True), key="web")],
        contract=contract(), instructions="sys", first_input=[{"role": "user", "content": []}],
    )
    assert out.kind == "result" and out.search_calls == 2
    # Two run turns (12 each) plus the model's own search (12).
    assert out.token_usage["total_tokens"] == 36
    declared = client.calls[0]["tools"][0]
    assert declared["type"] == "function" and declared["name"] == "web_search"
    first, second = (json.loads(item["output"]) for item in client.calls[1]["input"])
    assert first["untrusted"] and first["content"]["results"][0]["url"] == "https://a.example/"
    assert second["content"]["summary"]
    steps = [(c.args[2], c.args[4], c.args[6]) for c in record.await_args_list]
    assert steps[0] == ("web_search", "Searched: one",
                        {"query": "one", "freshness": None, "by": "brave", "results": 2})
    assert steps[1][2]["by"] == "model" and "503" in steps[1][2]["why"]
