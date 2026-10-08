"""ClaudeSession behaviors the agent loops rely on beyond the Huume basics:
forced tools per model, tools pinned for the turn, hosted web search and its
translation back into Responses items, `pause_turn`, JSON mode, effort.

    cd server && ./venv/bin/python -m pytest tests/huume/test_claude_session.py -q
"""

from types import SimpleNamespace
from uuid import uuid4

import pytest
from anthropic.types.beta import BetaMessage

from app.core.services.openai_responses import cited_urls, web_search_calls
from app.matcha.services.huume import claude_client
from app.matcha.services.huume.luna_client import text_item, tool_output_item

HAIKU, SONNET = "claude-haiku-5-5", "claude-sonnet-5-5"
FN = {"type": "function", "name": "finish", "description": "Finish.",
      "parameters": {"type": "object", "properties": {}}}
LOOKUP = {"type": "function", "name": "lookup", "description": "Look.",
          "parameters": {"type": "object", "properties": {}}}


def _message(content, *, stop_reason="end_turn", model=HAIKU, usage=None):
    return BetaMessage.model_validate({
        "id": f"msg_{uuid4().hex[:6]}", "type": "message", "role": "assistant", "model": model,
        "content": content, "stop_reason": stop_reason, "stop_sequence": None,
        "usage": usage or {"input_tokens": 10, "output_tokens": 4},
    })


def _tool_use(name="finish", id_="toolu_1"):
    return {"type": "tool_use", "id": id_, "name": name, "input": {}}


class _Fake:
    def __init__(self, outcomes):
        self.outcomes = list(outcomes)
        self.calls = []
        self.beta = SimpleNamespace(messages=SimpleNamespace(create=self._create))

    def with_options(self, **kwargs):
        return self

    async def _create(self, **params):
        self.calls.append({**params, "messages": [dict(m) for m in params["messages"]]})
        return self.outcomes.pop(0)


@pytest.fixture(autouse=True)
def _no_ledger(monkeypatch):
    async def record(**kwargs):
        return None

    monkeypatch.setattr(claude_client, "record_anthropic_response", record)


def _texts(message):
    return [b["text"] for b in message["content"] if isinstance(b, dict) and b.get("type") == "text"]


@pytest.mark.asyncio
@pytest.mark.parametrize("choice, expected", [
    ("required", {"type": "any"}),
    ({"type": "function", "name": "finish"}, {"type": "tool", "name": "finish"}),
])
async def test_haiku_takes_a_forced_tool_choice(choice, expected):
    fake = _Fake([_message([_tool_use()], stop_reason="tool_use")])
    out = await claude_client.ClaudeSession(client=fake).create_response(
        model=HAIKU, input=[text_item("user", "go")], instructions="", tools=[FN], tool_choice=choice,
    )
    assert fake.calls[0]["tool_choice"] == expected
    assert out.function_calls[0]["name"] == "finish"


@pytest.mark.asyncio
async def test_sonnet_is_told_which_tool_and_nudged_once_when_it_answers_in_prose():
    fake = _Fake([
        _message([{"type": "text", "text": "Here you go."}], model=SONNET),
        _message([_tool_use()], stop_reason="tool_use", model=SONNET),
    ])
    out = await claude_client.ClaudeSession(client=fake).create_response(
        model=SONNET, input=[text_item("user", "go")], instructions="", tools=[FN],
        tool_choice={"type": "function", "name": "finish"},
    )
    first, retry = fake.calls
    assert "tool_choice" not in first  # Sonnet 5.5 rejects a forced choice
    assert "Call the `finish` tool now." in _texts(first["messages"][-1])
    assert [m["role"] for m in retry["messages"]] == ["user", "assistant", "user"]
    assert _texts(retry["messages"][-1]) == ["You must call a tool now."]
    assert out.function_calls[0]["name"] == "finish"
    assert out.usage["input_tokens"] == 20  # both calls counted


@pytest.mark.asyncio
async def test_sonnet_required_without_a_named_tool():
    fake = _Fake([_message([_tool_use("lookup")], stop_reason="tool_use", model=SONNET)])
    await claude_client.ClaudeSession(client=fake).create_response(
        model=SONNET, input=[text_item("user", "go")], instructions="", tools=[LOOKUP], tool_choice="required",
    )
    assert "Respond by calling one of the available tools." in _texts(fake.calls[0]["messages"][-1])


@pytest.mark.asyncio
async def test_tools_stay_fixed_for_the_turn_and_withdrawn_ones_are_named():
    fake = _Fake([
        _message([_tool_use("lookup")], stop_reason="tool_use"),
        _message([_tool_use("finish", "toolu_2")], stop_reason="tool_use"),
        _message([{"type": "text", "text": "done"}]),
    ])
    session = claude_client.ClaudeSession(client=fake)
    await session.create_response(model=HAIKU, input=[text_item("user", "go")], instructions="s",
                                  tools=[LOOKUP, FN])
    await session.create_response(model=HAIKU, input=[tool_output_item("toolu_1", {"ok": 1})],
                                  instructions="s", tools=[FN])
    # A later call offering no tools at all: same tools sent, tool use off.
    await session.create_response(model=HAIKU, input=[tool_output_item("toolu_2", {"ok": 1})],
                                  instructions="s", tools=[])
    first, second, third = fake.calls
    assert first["tools"] == second["tools"] == third["tools"]
    assert "do not call them: lookup." in _texts(second["messages"][-1])[0]
    assert third["tool_choice"] == {"type": "none"}


@pytest.mark.asyncio
async def test_tool_choice_none_passes_through():
    fake = _Fake([_message([{"type": "text", "text": "ok"}])])
    await claude_client.ClaudeSession(client=fake).create_response(
        model=HAIKU, input=[text_item("user", "go")], instructions="", tools=[FN], tool_choice="none",
    )
    assert fake.calls[0]["tool_choice"] == {"type": "none"}


@pytest.mark.asyncio
@pytest.mark.parametrize("model, tool_type", [
    (HAIKU, "web_search_20250305"), (SONNET, "web_search_20260209"),
])
async def test_hosted_web_search_maps_per_model(model, tool_type):
    fake = _Fake([_message([{"type": "text", "text": "ok"}], model=model)])
    await claude_client.ClaudeSession(client=fake).create_response(
        model=model, input=[text_item("user", "go")], instructions="",
        tools=[{"type": "web_search", "search_context_size": "medium"}, FN, {"type": "file_search"}],
        max_tool_calls=3,
    )
    tools = fake.calls[0]["tools"]
    assert tools[0] == {"type": tool_type, "name": "web_search", "max_uses": 3}
    assert [t["name"] for t in tools] == ["web_search", "finish"]  # unknown hosted tools dropped


@pytest.mark.asyncio
async def test_search_blocks_come_back_as_responses_items():
    fake = _Fake([_message([
        {"type": "server_tool_use", "id": "srvtoolu_1", "name": "web_search", "input": {"query": "lip balm"}},
        {"type": "web_search_tool_result", "tool_use_id": "srvtoolu_1", "content": [
            {"type": "web_search_result", "url": "https://reviews.example/a", "title": "A",
             "encrypted_content": "e", "page_age": None},
        ]},
        {"type": "server_tool_use", "id": "srvtoolu_2", "name": "web_search", "input": {"query": "again"}},
        {"type": "web_search_tool_result", "tool_use_id": "srvtoolu_2",
         "content": {"type": "web_search_tool_result_error", "error_code": "max_uses_exceeded"}},
        {"type": "text", "text": "The best one.", "citations": [
            {"type": "web_search_result_location", "url": "https://reviews.example/b", "title": "B",
             "encrypted_index": "i", "cited_text": "best"},
        ]},
    ])])
    out = await claude_client.ClaudeSession(client=fake).create_response(
        model=HAIKU, input=[text_item("user", "go")], instructions="", tools=[{"type": "web_search"}],
    )
    calls = web_search_calls(out.output_items)
    assert [c["action"]["query"] for c in calls] == ["lip balm", "again"]
    assert [c["status"] for c in calls] == ["completed", "failed"]
    assert cited_urls(out.output_items) == ["https://reviews.example/a", "https://reviews.example/b"]
    assert out.text == "The best one."


@pytest.mark.asyncio
async def test_a_paused_server_tool_loop_is_resumed_and_merged():
    fake = _Fake([
        _message([{"type": "server_tool_use", "id": "srvtoolu_1", "name": "web_search",
                   "input": {"query": "q"}}], stop_reason="pause_turn"),
        _message([{"type": "text", "text": "Found it."}]),
    ])
    session = claude_client.ClaudeSession(client=fake)
    out = await session.create_response(model=HAIKU, input=[text_item("user", "go")], instructions="",
                                        tools=[{"type": "web_search"}])
    resumed = fake.calls[1]["messages"]
    assert [m["role"] for m in resumed] == ["user", "assistant"]  # no extra user turn
    assert out.text == "Found it." and not out.truncated
    assert out.usage["output_tokens"] == 8
    assert len(session._messages[-1]["content"]) == 2  # both halves kept as one reply


@pytest.mark.asyncio
async def test_json_mode_asks_for_json_and_unwraps_fences():
    fake = _Fake([
        _message([{"type": "text", "text": '```json\n{"title": "Fix it"}\n```'}]),
        _message([{"type": "text", "text": "not json"}]),
    ])
    session = claude_client.ClaudeSession(client=fake)
    out = await session.create_response(model=HAIKU, input=[text_item("user", "draft")], instructions="",
                                        response_format_json=True)
    assert out.text == '{"title": "Fix it"}'
    assert any("exactly one JSON object" in t for t in _texts(fake.calls[0]["messages"][-1]))
    raw = await claude_client.ClaudeSession(client=fake).create_response(
        model=HAIKU, input=[text_item("user", "draft")], instructions="", response_format_json=True,
    )
    assert raw.text == "not json"  # left for the caller's own parse to report


@pytest.mark.asyncio
@pytest.mark.parametrize("kwargs, expected", [
    ({}, "medium"),
    ({"reasoning_effort": "minimal"}, "low"),
    ({"reasoning_effort": "high"}, "high"),
    ({"reasoning_effort": "high", "effort": "low"}, "low"),
])
async def test_effort_mapping(kwargs, expected):
    fake = _Fake([_message([{"type": "text", "text": "ok"}])])
    await claude_client.ClaudeSession(client=fake).create_response(
        model=HAIKU, input=[text_item("user", "go")], instructions="", **kwargs,
    )
    assert fake.calls[0]["output_config"] == {"effort": expected}


@pytest.mark.asyncio
async def test_unchained_call_ignores_the_turns_history():
    fake = _Fake([_message([{"type": "text", "text": "a"}]), _message([{"type": "text", "text": "b"}])])
    session = claude_client.ClaudeSession(client=fake)
    await session.create_response(model=HAIKU, input=[text_item("user", "one")], instructions="")
    await session.create_response(model=HAIKU, input=[text_item("user", "two")], instructions="", chain=False)
    assert len(fake.calls[1]["messages"]) == 1


def test_to_messages_skips_responses_output_items():
    items = [
        text_item("user", "hi"),
        {"type": "reasoning", "encrypted_content": "x"},
        {"type": "web_search_call", "action": {"query": "q"}},
        {"type": "function_call", "call_id": "c", "name": "n", "arguments": "{}"},
    ]
    assert claude_client.to_messages(items) == [{"role": "user", "content": [{"type": "text", "text": "hi"}]}]


@pytest.mark.asyncio
async def test_the_deadline_bounds_continuations():
    session = claude_client.ClaudeSession(client=_Fake([]))
    with pytest.raises(RuntimeError, match="deadline"):
        await session._call(session._client, {"model": HAIKU}, [], deadline=0)


def test_usage_helpers():
    assert claude_client._usage(SimpleNamespace()) == {}
    assert claude_client._sum_usage({}, {"input_tokens": 1}) == {"input_tokens": 1}
    assert claude_client._sum_usage({"input_tokens": 1}, {}) == {"input_tokens": 1}
