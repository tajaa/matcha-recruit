from unittest.mock import AsyncMock, Mock
from uuid import uuid4

import pytest

from app.core.services import ai_usage
from app.matcha.services.huume.luna_client import LunaResponse
from app.matcha.services.matcha_work.agent_card import agent

_counter = {"n": 0}


def _call(name, args):
    _counter["n"] += 1
    return {"call_id": f"call_{_counter['n']}", "name": name, "arguments": args}


def _search(query, sources=()):
    return {
        "type": "web_search_call", "status": "completed",
        "action": {"type": "search", "query": query, "sources": [{"type": "url", "url": u} for u in sources]},
    }


def _response(*calls, output=(), text=""):
    return LunaResponse(
        response_id="resp",
        text=text,
        function_calls=list(calls),
        usage={"input_tokens": 100, "output_tokens": 20, "total_tokens": 120},
        output_items=list(output),
    )


class _FakeClient:
    def __init__(self, responses):
        self.responses = list(responses)
        self.calls = []

    async def create_response(self, **kwargs):
        self.calls.append({**kwargs, "feature": ai_usage._feature_override.get()})
        return self.responses.pop(0)


RESULT = {
    "headline": "Organic Balm wins",
    "summary": "Best ingredients for the price.",
    "answer_type": "recommendation",
    "confidence": "medium",
    "top_pick": {
        "name": "Organic Balm",
        "buy_links": [
            {"retailer": "Shop", "url": "https://shop.example/buy/balm"},
            {"retailer": "Fake", "url": "https://invented.example/buy"},
        ],
        "images": [{"source_url": "https://cdn.example/a.jpg", "page_url": "https://shop.example/balm"}],
        "reviews": [{"quote": "Love it", "url": "https://reviews.example/roundup", "sentiment": "pos"}],
    },
    "sources": [{"title": "Roundup", "url": "https://reviews.example/roundup"}],
}


@pytest.fixture
def wired(monkeypatch):
    record_step, mark_run = AsyncMock(), AsyncMock()
    monkeypatch.setattr(agent.store, "record_step", record_step)
    monkeypatch.setattr(agent.store, "mark_run", mark_run)
    monkeypatch.setattr(agent.board, "set_progress", AsyncMock(return_value=None))
    monkeypatch.setattr(agent.board, "publish_task_updated", AsyncMock())

    async def rehost(result, **_kw):
        for pick in [result.get("top_pick"), *result.get("alternatives", [])]:
            if pick:
                pick["images"] = [{"url": "https://cdn.matcha.example/x.webp", "page_url": i["page_url"], "alt": i["alt"]} for i in pick["images"]]
        return []

    monkeypatch.setattr(agent.images, "rehost_images", rehost)
    return record_step, mark_run


def _kwargs(**over):
    base = dict(run_id=uuid4(), company_id=uuid4(), project_id=uuid4(), task_id=uuid4(),
                round=1, ask="Find me the best organic lip balm")
    base.update(over)
    return base


@pytest.mark.asyncio
async def test_search_fetch_finish_produces_a_gated_result(monkeypatch, wired):
    record_step, mark_run = wired
    client = _FakeClient([
        _response(_call("fetch_page", {"url": "https://shop.example/balm"}),
                  output=[_search("best organic lip balm", ["https://reviews.example/roundup"])]),
        _response(_call("finish", {"result": RESULT})),
    ])
    monkeypatch.setattr(agent, "get_luna_client", Mock(return_value=client))
    monkeypatch.setattr(agent, "fetch_page_tool", AsyncMock(return_value=(
        {"url": "https://shop.example/balm", "title": "Balm", "products": []},
        {"https://shop.example/balm", "https://shop.example/buy/balm"},
    )))
    stats = {}
    out = await agent.run_card_agent(**_kwargs(), stats=stats)

    result = out["result"]
    pick = result["top_pick"]
    assert [link["url"] for link in pick["buy_links"]] == ["https://shop.example/buy/balm"]
    assert pick["images"][0]["url"].startswith("https://cdn.matcha.example/")
    assert any("invented.example" in w for w in result["warnings"])
    assert result["round"] == 1
    assert out["search_calls"] == 1 and stats["search_calls"] == 1
    assert client.calls[0]["feature"] == "matcha.espresso.agent_card"
    assert client.calls[0]["tools"][0]["type"] == "web_search"
    assert client.calls[0]["include"] == ["web_search_call.action.sources"]
    assert client.calls[0]["max_tool_calls"] == agent._MAX_SEARCHES_PER_RESPONSE
    mark_run.assert_awaited_once()
    assert mark_run.await_args.kwargs["status"] == "done"
    assert mark_run.await_args.kwargs["search_calls"] == 1
    kinds = [c.args[3] for c in record_step.await_args_list]
    assert kinds[:3] == ["search", "fetch", "finish"]


@pytest.mark.asyncio
async def test_last_turn_forces_finish_without_search(monkeypatch, wired):
    monkeypatch.setattr(agent, "_MAX_MODEL_CALLS", 2)
    client = _FakeClient([
        _response(_call("fetch_page", {"url": "https://x.example"})),
        _response(_call("finish", {"result": {**RESULT, "top_pick": None, "sources": []}})),
    ])
    monkeypatch.setattr(agent, "get_luna_client", Mock(return_value=client))
    monkeypatch.setattr(agent, "fetch_page_tool", AsyncMock(return_value=({"error": "nope"}, set())))
    await agent.run_card_agent(**_kwargs())
    last = client.calls[-1]
    assert last["tool_choice"] == {"type": "function", "name": "finish"}
    assert all(t.get("type") != "web_search" for t in last["tools"])
    assert last["max_tool_calls"] is None


@pytest.mark.asyncio
async def test_invalid_finish_gets_one_repair_then_fails(monkeypatch, wired):
    client = _FakeClient([
        _response(_call("finish", {"result": {"headline": ""}})),
        _response(_call("finish", {"result": "nope"})),
    ])
    monkeypatch.setattr(agent, "get_luna_client", Mock(return_value=client))
    with pytest.raises(agent.CardAgentError):
        await agent.run_card_agent(**_kwargs())
    repair_input = client.calls[1]["input"][0]
    assert repair_input["type"] == "function_call_output" and "Invalid result" in repair_input["output"]


@pytest.mark.asyncio
async def test_never_finishing_raises(monkeypatch, wired):
    monkeypatch.setattr(agent, "_MAX_MODEL_CALLS", 2)
    client = _FakeClient([_response(text="prose"), _response(text="more prose")])
    monkeypatch.setattr(agent, "get_luna_client", Mock(return_value=client))
    stats = {}
    with pytest.raises(agent.CardAgentError, match="ran out of time"):
        await agent.run_card_agent(**_kwargs(), stats=stats)
    assert stats["model_calls"] == 2
    assert client.calls[1]["input"][0]["content"][0]["text"].startswith("Call the finish tool")


@pytest.mark.asyncio
async def test_fetch_budget_is_enforced(monkeypatch, wired):
    monkeypatch.setattr(agent, "_MAX_FETCHES", 1)
    client = _FakeClient([
        _response(_call("fetch_page", {"url": "https://a.example"}), _call("fetch_page", {"url": "https://b.example"})),
        _response(_call("finish", {"result": {**RESULT, "top_pick": None, "sources": []}})),
    ])
    monkeypatch.setattr(agent, "get_luna_client", Mock(return_value=client))
    fetch = AsyncMock(return_value=({"url": "https://a.example"}, {"https://a.example"}))
    monkeypatch.setattr(agent, "fetch_page_tool", fetch)
    await agent.run_card_agent(**_kwargs())
    assert fetch.await_count == 1
    outputs = client.calls[1]["input"]
    assert "budget" in outputs[1]["output"]


@pytest.mark.asyncio
async def test_revision_round_carries_note_previous_result_and_its_links(monkeypatch, wired):
    previous = {
        "top_pick": {"name": "Old", "buy_links": [{"url": "https://shop.example/buy/balm"}], "reviews": [], "price": None, "rating": None},
        "alternatives": [], "sources": [{"url": "https://reviews.example/roundup"}],
    }
    client = _FakeClient([_response(_call("finish", {"result": {**RESULT, "changes_from_previous": "Vegan only now."}}))])
    monkeypatch.setattr(agent, "get_luna_client", Mock(return_value=client))
    out = await agent.run_card_agent(**_kwargs(round=2, review_note="Only vegan options"), previous_result=previous)
    user_text = client.calls[0]["input"][0]["content"][0]["text"]
    assert "Only vegan options" in user_text and '"Old"' in user_text
    assert "revision round 2" in client.calls[0]["instructions"]
    # Links verified in round 1 remain usable without being re-fetched.
    assert out["result"]["top_pick"]["buy_links"][0]["url"] == "https://shop.example/buy/balm"
    assert out["result"]["changes_from_previous"] == "Vegan only now."


@pytest.mark.asyncio
async def test_fetch_page_tool_maps_refusals_and_errors(monkeypatch):
    from app.core.services.safe_fetch import FetchedResponse, UnsafeURL

    monkeypatch.setattr(agent, "fetch_public", AsyncMock(side_effect=UnsafeURL("private")))
    out, urls = await agent.fetch_page_tool("http://10.0.0.1")
    assert out["error"].startswith("Refused") and urls == set()

    monkeypatch.setattr(agent, "fetch_public", AsyncMock(side_effect=TimeoutError()))
    out, _ = await agent.fetch_page_tool("https://slow.example")
    assert "TimeoutError" in out["error"]

    def resp(status=200, ctype="text/html", body=b"<html><body>hi</body></html>"):
        return FetchedResponse(url="https://a.example", final_url="https://a.example/final",
                               status=status, content_type=ctype, body=body, truncated=False)

    monkeypatch.setattr(agent, "fetch_public", AsyncMock(return_value=resp(status=403)))
    out, _ = await agent.fetch_page_tool("https://a.example")
    assert "403" in out["error"]
    monkeypatch.setattr(agent, "fetch_public", AsyncMock(return_value=resp(ctype="application/pdf")))
    out, _ = await agent.fetch_page_tool("https://a.example")
    assert "Not an HTML page" in out["error"]
    monkeypatch.setattr(agent, "fetch_public", AsyncMock(return_value=resp(body=b"<p>" + b"w " * 20000 + b"</p>")))
    out, urls = await agent.fetch_page_tool("https://a.example")
    assert urls == {"https://a.example/final", "https://a.example"}
    assert out["text_truncated"]
