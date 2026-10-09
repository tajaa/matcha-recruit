"""EMS channel `@huume` on Claude — the platform "Agent model" setting routes
the five Gemini paths (classify, inventory extraction, schedule parse, receipt
parse, the ASK tool loop) to Claude with the same prompts, the same parsers and
the same never-raises fallbacks.

    cd server && ./venv/bin/python -m pytest tests/ems/test_ems_claude_paths.py -q

No network and no database: `claude_override`, `generate_text` and the
`ClaudeSession` are fakes, and the loop's connection is an inert context.
"""

import json
from datetime import date
from unittest.mock import AsyncMock

import pytest

from app.core.services import anthropic_messages
from app.matcha.services.ems import categories, channel_agent, channel_grounding, event_intake
from app.matcha.services.huume.luna_client import LunaResponse
from app.matcha.services.inventory import extraction, receipts
from app.matcha.services.scheduling import schedule_chat

HAIKU = "claude-haiku-5-5"


def _boom_gemini():
    raise AssertionError("the Gemini client must not be built on the Claude path")


@pytest.fixture
def on_claude(monkeypatch):
    """Route to Claude and capture every generate_text call."""
    calls: list[dict] = []
    replies: list = []

    async def fake_generate_text(prompt, **kwargs):
        calls.append({"prompt": prompt, **kwargs})
        reply = replies.pop(0)
        if isinstance(reply, BaseException):
            raise reply
        return reply

    monkeypatch.setattr(anthropic_messages, "claude_override", AsyncMock(return_value=HAIKU))
    monkeypatch.setattr(anthropic_messages, "generate_text", fake_generate_text)
    return calls, replies


# --- classify_event ---------------------------------------------------------

@pytest.mark.asyncio
async def test_classify_runs_on_claude_with_the_same_parser(monkeypatch, on_claude):
    calls, replies = on_claude
    monkeypatch.setattr(event_intake, "_get_client", _boom_gemini)
    replies.append("```json\n" + json.dumps({
        "title": "Ice machine down", "category": "equipment", "severity_hint": "medium",
        "doc": {"what": "ice machine"}, "ack": "Logged it.",
    }) + "\n```")

    classified = await event_intake.classify_event("the ice machine is broken again", [])

    assert classified["category"] == "equipment"
    assert classified["model_ok"] is True
    assert calls[0]["model"] == HAIKU and calls[0]["json_output"] is True and calls[0]["effort"] == "low"
    assert "ice machine is broken" in calls[0]["prompt"]


@pytest.mark.asyncio
async def test_classify_claude_failure_still_logs_uncategorized(monkeypatch, on_claude):
    _calls, replies = on_claude
    monkeypatch.setattr(event_intake, "_get_client", _boom_gemini)
    replies.append(RuntimeError("Anthropic down"))

    classified = await event_intake.classify_event("the ice machine is broken", [])

    assert classified["category"] == categories.FALLBACK_KEY
    assert classified["model_ok"] is False
    assert classified["not_an_event"] is False


@pytest.mark.asyncio
async def test_classify_without_override_stays_on_gemini(monkeypatch):
    generate = AsyncMock()
    monkeypatch.setattr(anthropic_messages, "generate_text", generate)

    class _Resp:
        text = json.dumps({"title": "Spill", "category": "safety"})

    class _Models:
        async def generate_content(self, **kwargs):
            return _Resp()

    client = type("C", (), {"aio": type("A", (), {"models": _Models()})()})()
    monkeypatch.setattr(event_intake, "_get_client", lambda: client)

    classified = await event_intake.classify_event("someone spilled coffee by the door", [])

    assert classified["category"] == "safety"
    generate.assert_not_awaited()


# --- inventory extraction ---------------------------------------------------

@pytest.mark.asyncio
async def test_extraction_runs_on_claude_and_still_coerces_theft(monkeypatch, on_claude):
    calls, replies = on_claude
    monkeypatch.setattr(extraction, "_get_client", _boom_gemini)
    replies.append(json.dumps({
        "actionable": True, "kind": "waste",
        "lines": [{"item_name": "Spinach", "quantity": 3, "unit": "lb", "direction": "out"}],
        "waste_reason": "theft",
    }))

    result = await extraction.extract_inventory("someone took 3 lbs of spinach", ["Spinach"])

    assert result["actionable"] is True and result["kind"] == "waste"
    # A personnel accusation is never minted from a chat aside, on any model.
    assert result["waste_reason"] == "unknown"
    assert calls[0]["model"] == HAIKU and "Spinach" in calls[0]["prompt"]


@pytest.mark.asyncio
async def test_extraction_claude_failure_falls_back_to_logging(monkeypatch, on_claude):
    _calls, replies = on_claude
    monkeypatch.setattr(extraction, "_get_client", _boom_gemini)
    replies.append("not json at all")

    result = await extraction.extract_inventory("we ran out of cups", ["Cups"])

    assert result == extraction.fallback_extraction("we ran out of cups")


# --- schedule parse ---------------------------------------------------------

@pytest.mark.asyncio
async def test_schedule_parse_runs_on_claude(monkeypatch, on_claude):
    calls, replies = on_claude
    monkeypatch.setattr(schedule_chat, "_get_client", _boom_gemini)
    seen = []

    def fake_parse(raw):
        seen.append(raw)
        return {"actionable": True, "action": "create", "shift_requests": [{"x": 1}]}

    monkeypatch.setattr(schedule_chat, "_parse_schedule_json", fake_parse)
    replies.append('{"actionable": true}')

    parsed = await schedule_chat.parse_schedule_request("add an opener Monday 7-3", date(2026, 8, 10))

    assert parsed["actionable"] is True
    assert seen == ['{"actionable": true}']
    assert calls[0]["model"] == HAIKU and "opener" in calls[0]["prompt"]


@pytest.mark.asyncio
async def test_schedule_parse_claude_failure_returns_none(monkeypatch, on_claude):
    _calls, replies = on_claude
    monkeypatch.setattr(schedule_chat, "_get_client", _boom_gemini)
    replies.append(RuntimeError("Anthropic down"))

    assert await schedule_chat.parse_schedule_request("add an opener Monday", date(2026, 8, 10)) is None


# --- receipt parse ----------------------------------------------------------

def _no_analyzer():
    raise AssertionError("the Gemini analyzer must not be built on the Claude path")


@pytest.mark.asyncio
async def test_receipt_pdf_goes_to_claude_as_a_document(monkeypatch, on_claude):
    calls, replies = on_claude
    monkeypatch.setattr(receipts, "_get_analyzer", _no_analyzer)
    replies.append(json.dumps({
        "vendor": "Henry Schein", "invoice_number": "INV-9",
        "lines": [{"item_name": "Gloves", "quantity": 10}],
    }))

    result = await receipts.parse_receipt(b"%PDF-1.4 fake", "application/pdf", "invoice.pdf")

    assert result["available"] is True and result["vendor"] == "Henry Schein"
    assert result["lines"][0]["item_name"] == "Gloves"
    attachment = calls[0]["attachments"][0]
    assert attachment["type"] == "document" and attachment["source"]["media_type"] == "application/pdf"
    assert calls[0]["prompt"] == receipts._PROMPT


@pytest.mark.asyncio
async def test_receipt_photo_goes_to_claude_as_an_image(monkeypatch, on_claude):
    calls, replies = on_claude
    monkeypatch.setattr(receipts, "_get_analyzer", _no_analyzer)
    replies.append('{"lines": [{"item_name": "Cups", "quantity": 2}]}')

    result = await receipts.parse_receipt(b"\x89PNG fake", "image/png", "slip.png")

    assert result["lines"][0]["item_name"] == "Cups"
    assert calls[0]["attachments"][0]["type"] == "image"


@pytest.mark.asyncio
async def test_receipt_other_files_send_extracted_text(monkeypatch, on_claude):
    calls, replies = on_claude
    monkeypatch.setattr(receipts, "_get_analyzer", _no_analyzer)

    class _Parser:
        def extract_text_from_bytes(self, data, filename):
            return "Gloves x 4", 1

    monkeypatch.setattr("app.matcha.services.er.er_document_parser.ERDocumentParser", _Parser)
    replies.append('{"lines": [{"item_name": "Gloves", "quantity": 4}]}')

    result = await receipts.parse_receipt(b"docx bytes", "application/msword", "invoice.doc")

    assert result["lines"][0]["quantity"] == 4
    assert calls[0]["attachments"] == []
    assert calls[0]["prompt"].endswith("Invoice text follows:\n\nGloves x 4")


@pytest.mark.asyncio
async def test_receipt_claude_failure_is_an_empty_draft(monkeypatch, on_claude):
    _calls, replies = on_claude
    monkeypatch.setattr(receipts, "_get_analyzer", _no_analyzer)
    replies.append(RuntimeError("Anthropic down"))

    result = await receipts.parse_receipt(b"%PDF-1.4 fake", "application/pdf", "invoice.pdf")

    assert result["available"] is False and result["lines"] == []


@pytest.mark.asyncio
async def test_receipt_image_claude_cannot_take_stays_on_gemini(monkeypatch, on_claude):
    calls, _replies = on_claude

    class _Resp:
        text = '{"lines": [{"item_name": "Towels", "quantity": 1}]}'

    class _Models:
        async def generate_content(self, *, model, contents):
            return _Resp()

    class _Analyzer:
        model = "gemini"
        client = type("C", (), {"aio": type("A", (), {"models": _Models()})()})()

        def _parse_json_response(self, text):
            return json.loads(text)

    monkeypatch.setattr(receipts, "_get_analyzer", lambda: _Analyzer())

    result = await receipts.parse_receipt(b"heic bytes", "image/heic", "slip.heic")

    assert result["lines"][0]["item_name"] == "Towels"
    assert calls == []


@pytest.mark.asyncio
async def test_receipt_csv_never_reaches_a_model(monkeypatch, on_claude):
    calls, _replies = on_claude
    monkeypatch.setattr(receipts, "_get_analyzer", _no_analyzer)

    result = await receipts.parse_receipt(b"item_name,quantity\nGloves,5\n", "text/csv", "invoice.csv")

    assert result["available"] is True and calls == []


# --- the channel ASK loop ---------------------------------------------------

class _FakeSession:
    def __init__(self, responses):
        self.responses = list(responses)
        self.calls: list[dict] = []

    async def create_response(self, **kwargs):
        self.calls.append(kwargs)
        if not self.responses:
            raise AssertionError("the Claude loop made more calls than the test queued")
        item = self.responses.pop(0)
        if isinstance(item, BaseException):
            raise item
        return item


class _ConnCtx:
    async def __aenter__(self):
        return None

    async def __aexit__(self, *exc):
        return False


def _call(name, args, call_id=None):
    _call.n = getattr(_call, "n", 0) + 1
    return {"call_id": call_id or f"toolu_{_call.n}", "name": name, "arguments": args}


def _reply(*, calls=(), text=""):
    return LunaResponse(response_id="msg", text=text, function_calls=list(calls))


@pytest.fixture
def claude_loop(monkeypatch):
    monkeypatch.setattr(anthropic_messages, "claude_override", AsyncMock(return_value=HAIKU))
    monkeypatch.setattr(channel_agent, "genai_env_client", _boom_gemini)
    monkeypatch.setattr("app.database.get_connection", lambda: _ConnCtx())

    def install(responses):
        session = _FakeSession(responses)
        monkeypatch.setattr(channel_agent.claude_client, "get_claude_client", lambda: session)
        return session

    return install


def _kwargs(**over):
    kwargs = dict(
        question="what's going on", events=[], is_admin=True, filtered=False,
        company_id="c1", channel_id="ch1", asker_user_id="u1", asker_role="client",
        features={"inventory": True, "employee_schedule": True},
        location_id=None, location_unavailable=False,
    )
    kwargs.update(over)
    return kwargs


@pytest.mark.asyncio
async def test_claude_loop_looks_up_then_answers(monkeypatch, claude_loop):
    lookups = []

    async def fake_lookup(conn, **kwargs):
        lookups.append(kwargs["topic"])
        return {"text": "Cups: 4 on hand"}

    monkeypatch.setattr(channel_grounding, "run_topic_lookup", fake_lookup)
    session = claude_loop([
        _reply(calls=[_call("lookup_context", {"topic": "inventory"}, "toolu_a")]),
        _reply(text="We've got 4 cups left."),
    ])

    result = await channel_agent.answer_channel_question(**_kwargs(
        question="how many cups", recent_block="Casey: are we low on cups?",
    ))

    assert result["message"] == "\U0001F4CB We've got 4 cups left."
    assert lookups == ["inventory"]
    first, second = session.calls
    assert first["model"] == HAIKU and first["effort"] == "low"
    # Same prompts as the Gemini loop: untrusted channel text in the user turn.
    assert "Today is" in first["instructions"]
    assert "Casey: are we low on cups?" not in first["instructions"]
    assert "Casey: are we low on cups?" in first["input"][0]["content"][0]["text"]
    names = {tool["name"] for tool in first["tools"]}
    assert {"lookup_context", "stage_inventory_order", "find_shift_coverage", "propose_schedule_change"} <= names
    # The follow-up carries only the tool result, paired by call_id.
    assert second["input"] == [{
        "type": "function_call_output", "call_id": "toolu_a",
        "output": json.dumps({"result": "Cups: 4 on hand"}, separators=(",", ":")),
    }]


def test_tool_schemas_are_converted_from_the_gemini_declarations():
    tool = channel_agent._function_tool(channel_agent._SCHEDULE_CHANGE_DECLARATION)
    params = tool["parameters"]
    assert tool["type"] == "function" and tool["name"] == "propose_schedule_change"
    assert params["type"] == "object" and params["required"] == ["kind"]
    assert set(params["properties"]["target_staffing_hint"]["enum"]) == {"staffed", "unstaffed"}
    assert params["properties"]["employee_names"] == {
        "type": "array", "items": {"type": "string"},
        "description": "For kind='create', names to try pinning to the new shift.",
    }
    assert params["properties"]["count"]["type"] == "integer"


@pytest.mark.asyncio
async def test_claude_loop_stages_an_order_verbatim_and_stops(monkeypatch, claude_loop):
    pill = "\U0001F4E6 cups marked out of stock. Reply **confirm** to queue it."
    staged = []

    async def fake_stage(conn, **kwargs):
        staged.append(kwargs["item_name"])
        return {"text": "Staged fine", "order_id": "order-1", "pill_text": pill}

    monkeypatch.setattr(channel_agent, "_stage_inventory_order", fake_stage)
    session = claude_loop([
        _reply(calls=[
            _call("stage_inventory_order", {"item_name": "cups"}),
            _call("stage_inventory_order", {"item_name": "lids"}),
        ]),
    ])

    result = await channel_agent.answer_channel_question(**_kwargs(question="order more cups and lids"))

    assert result == {"message": pill, "pending_order_id": "order-1", "pending_proposal_id": None}
    # One staged thing per message, on either provider.
    assert staged == ["cups"]
    assert len(session.calls) == 1


@pytest.mark.asyncio
async def test_claude_loop_stages_a_schedule_change(monkeypatch, claude_loop):
    async def fake_change(conn, **kwargs):
        return {"text": "Reply confirm to move Dana to Friday.", "proposal_id": "prop-1"}

    monkeypatch.setattr(channel_grounding, "run_schedule_change", fake_change)
    claude_loop([_reply(calls=[_call("propose_schedule_change", {"kind": "reassign"})])])

    result = await channel_agent.answer_channel_question(**_kwargs(question="put Dana on Friday"))

    assert result["pending_proposal_id"] == "prop-1"
    assert result["message"] == "Reply confirm to move Dana to Friday."


@pytest.mark.asyncio
async def test_claude_loop_force_finishes_text_only_on_the_bound(monkeypatch, claude_loop):
    async def fake_coverage(conn, **kwargs):
        return {"text": "Sam is free", "shift_links": [{"id": "s1", "date": "2026-08-12"}]}

    monkeypatch.setattr(channel_grounding, "run_coverage_lookup", fake_coverage)
    always = [
        _reply(calls=[_call("find_shift_coverage", {"date": "2026-08-12"})])
        for _ in range(channel_agent._MAX_MODEL_CALLS)
    ]
    session = claude_loop([*always, _reply(text="Sam can cover Wednesday.")])

    result = await channel_agent.answer_channel_question(**_kwargs(question="who can cover Wednesday"))

    assert len(session.calls) == channel_agent._MAX_MODEL_CALLS + 1
    finish = session.calls[-1]
    # Tools stay declared (the history holds tool calls); "none" makes it text-only.
    assert finish["tool_choice"] == "none" and finish["tools"] == session.calls[0]["tools"]
    assert finish["input"][0]["type"] == "function_call_output"
    assert result["message"] == "\U0001F4CB Sam can cover Wednesday. [[shift:s1:2026-08-12]]"


@pytest.mark.asyncio
async def test_claude_loop_empty_reply_retries_with_nothing_resent(monkeypatch, claude_loop):
    session = claude_loop([_reply(text=""), _reply(text="Nothing logged here yet.")])

    result = await channel_agent.answer_channel_question(**_kwargs(
        is_admin=False, asker_role="employee", features={},
    ))

    assert result["message"] == "\U0001F4CB Nothing logged here yet."
    # No tools were offered, so no tool_choice; the first input was already sent.
    assert session.calls[0]["tools"] is None
    assert session.calls[1]["input"] == [] and session.calls[1]["tool_choice"] is None


@pytest.mark.asyncio
async def test_claude_loop_refuses_unoffered_and_unknown_tools(monkeypatch, claude_loop):
    staged = []

    async def fake_stage(conn, **kwargs):
        staged.append(kwargs)
        return {"text": "should not run"}

    monkeypatch.setattr(channel_agent, "_stage_inventory_order", fake_stage)
    session = claude_loop([
        _reply(calls=[_call("stage_inventory_order", {"item_name": "cups"}), _call("drop_tables", {})]),
        _reply(text="Inventory isn't set up here."),
    ])

    result = await channel_agent.answer_channel_question(**_kwargs(features={}, is_admin=False, asker_role="employee"))

    assert staged == []
    outputs = [json.loads(item["output"])["result"] for item in session.calls[1]["input"]]
    assert outputs == ["That's not available here.", "That's not available here."]
    assert "Inventory isn't set up here" in result["message"]


@pytest.mark.asyncio
async def test_claude_loop_failure_degrades_to_the_fallback_line(monkeypatch, claude_loop):
    claude_loop([RuntimeError("Anthropic down")])

    result = await channel_agent.answer_channel_question(**_kwargs())

    assert result == {"message": channel_agent._FALLBACK_TEXT, "pending_order_id": None, "pending_proposal_id": None}


@pytest.mark.asyncio
async def test_no_override_keeps_the_gemini_loop(monkeypatch):
    sessions = []
    monkeypatch.setattr(channel_agent.claude_client, "get_claude_client", lambda: sessions.append(1))

    class _Resp:
        candidates = []
        text = "All quiet."

    class _Models:
        async def generate_content(self, **kwargs):
            return _Resp()

    client = type("C", (), {"aio": type("A", (), {"models": _Models()})()})()
    monkeypatch.setattr(channel_agent, "genai_env_client", lambda: client)

    result = await channel_agent.answer_channel_question(**_kwargs())

    assert result["message"] == "\U0001F4CB All quiet."
    assert sessions == []
