"""The single-shot Luna calls follow the platform "Agent model" setting to Claude.

    cd server && ./venv/bin/python -m pytest tests/test_claude_single_shots.py -q

Five call sites — credential templates, sym-chat, inventory insight, waste
narration, the one-shot ticket draft — each keep their Luna path untouched
and, when `anthropic_messages.claude_override()` names a model, send the same
prompt to Claude with the same failure contract. No network, no database:
`claude_override` and `generate_text` are faked at the shared module.
"""

import json
from datetime import date
from types import SimpleNamespace

import pytest

from app.core.services import ai_usage, anthropic_messages
from app.core.services import credential_template_service as credentials
from app.matcha.services.huume.luna_client import LunaResponse
from app.matcha.services.inventory import insight
from app.matcha.services.inventory.waste import agent as waste_agent
from app.matcha.services.matcha_work.matcha_work_ai import task_draft
from app.matcha.services.sym_chat import extract
from app.matcha.services.sym_chat.kinds import materialize_config

CLAUDE = anthropic_messages.CLAUDE_HAIKU


class _Claude:
    """Stands in for `anthropic_messages.generate_text`: records each call
    (with the active ai_usage feature label) and returns `reply`, or raises it."""

    def __init__(self, reply):
        self.reply = reply
        self.calls = []

    async def __call__(self, prompt, **kwargs):
        self.calls.append({"prompt": prompt, "feature": ai_usage._feature_override.get(), **kwargs})
        if isinstance(self.reply, BaseException):
            raise self.reply
        return self.reply


@pytest.fixture
def route_to_claude(monkeypatch):
    """Point the AI-models setting at Claude; returns a setter for the reply.
    `surfaces` records which setting each call consulted."""
    surfaces: list[str] = []

    async def override(surface):
        surfaces.append(surface)
        return CLAUDE

    monkeypatch.setattr(anthropic_messages, "claude_override", override)

    def use(reply) -> _Claude:
        fake = _Claude(reply)
        fake.surfaces = surfaces
        monkeypatch.setattr(anthropic_messages, "generate_text", fake)
        return fake

    return use


def _no_openai(monkeypatch, module):
    """Luna unconfigured: proves the Claude branch never needed it."""
    monkeypatch.setattr(module, "get_settings", lambda: SimpleNamespace(openai_api_key=None, openai_luna_model=None))


# --- Credential templates ---------------------------------------------------

ROLE_ROWS = [{"key": "rn", "label": "Registered Nurse"}, {"key": "non_clinical", "label": "Non-clinical"}]


@pytest.mark.asyncio
async def test_credential_model_prefers_the_routed_claude_model(route_to_claude, monkeypatch):
    monkeypatch.setattr(credentials, "_luna_credentials", lambda: None)
    assert await credentials._text_model() == ("", CLAUDE)


@pytest.mark.asyncio
async def test_credential_model_falls_back_to_luna_without_an_override(monkeypatch):
    monkeypatch.setattr(credentials, "_luna_credentials", lambda: ("sk-test", "gpt-5.6-luna"))
    assert await credentials._text_model() == ("sk-test", "gpt-5.6-luna")


@pytest.mark.asyncio
async def test_role_classification_runs_on_claude_without_openai(route_to_claude, monkeypatch):
    monkeypatch.setattr(credentials, "_luna_credentials", lambda: None)
    claude = route_to_claude('{"key": "rn"}')

    row = await credentials._classify_role_via_luna(None, "Charge Nurse", ROLE_ROWS)

    assert row == ROLE_ROWS[0]
    call = claude.calls[0]
    assert call["model"] == CLAUDE and call["json_output"] is True and call["effort"] == "high"
    assert call["max_tokens"] == 512
    assert "Charge Nurse" in call["prompt"]


@pytest.mark.asyncio
async def test_role_classification_survives_a_claude_failure(route_to_claude, monkeypatch):
    monkeypatch.setattr(credentials, "_luna_credentials", lambda: None)
    route_to_claude(RuntimeError("Anthropic Messages request failed: 529"))
    assert await credentials._classify_role_via_luna(None, "Charge Nurse", ROLE_ROWS) is None


@pytest.mark.asyncio
async def test_claude_research_text_raises_like_luna(route_to_claude):
    route_to_claude(RuntimeError("Anthropic Messages request failed: 500"))
    with pytest.raises(RuntimeError):
        await credentials._generate_luna_text(
            "research", api_key="", model=CLAUDE, max_output_tokens=8192, json_output=True,
        )


@pytest.mark.asyncio
async def test_research_without_any_model_returns_nothing(monkeypatch):
    monkeypatch.setattr(credentials, "_luna_credentials", lambda: None)
    assert await credentials.research_credential_requirements(None, "CA", None, None) == []


# --- Sym-chat ---------------------------------------------------------------

SCHED = materialize_config(
    "schedule",
    {"date": "2030-01-15", "window_start": "09:00", "window_end": "17:00", "duration_min": 60},
    today=date(2030, 1, 1),
)


async def _sym_turn():
    return await extract.next_turn(
        "schedule", "", SCHED, [{"role": "user", "content": "free 2-4"}], None, [], "Dana",
    )


@pytest.mark.asyncio
async def test_sym_chat_turn_runs_on_claude_in_json_mode(route_to_claude, monkeypatch):
    _no_openai(monkeypatch, extract)
    claude = route_to_claude(
        '```json\n{"reply": "Got it — 2 to 4.", "stance": {"available": [{"start": "14:00", "end": "16:00"}]}}\n```'
    )

    out = await _sym_turn()

    assert out["error"] is False and out["reply"] == "Got it — 2 to 4."
    assert out["stance"]["available"] == [{"start": "14:00", "end": "16:00"}]
    call = claude.calls[0]
    assert call["json_output"] is True and call["effort"] == extract.REASONING_EFFORT
    assert call["timeout_seconds"] == extract.TURN_TIMEOUT
    assert call["feature"] == "sym_chat"


@pytest.mark.asyncio
@pytest.mark.parametrize("reply", [RuntimeError("Anthropic Messages request failed"), "not json", "[1, 2]"])
async def test_sym_chat_turn_falls_back_on_any_claude_failure(route_to_claude, monkeypatch, reply):
    _no_openai(monkeypatch, extract)
    route_to_claude(reply)
    out = await _sym_turn()
    assert out["error"] is True and out["reply"] == extract.FALLBACK_REPLY


# --- Inventory insight ------------------------------------------------------

TOKENS = {"loss": "$120", "item": "Oat milk"}


async def _insight():
    return await insight.interpret(surface="waste", diagnosis="over_ordering", tokens=TOKENS)


@pytest.mark.asyncio
async def test_insight_wording_comes_from_claude_when_routed(route_to_claude, monkeypatch):
    _no_openai(monkeypatch, insight)
    monkeypatch.setattr(insight, "get_redis_cache", lambda: None)
    claude = route_to_claude(json.dumps({
        "headline": "{item} is over-ordered.", "detail": "Trim the PAR; {loss} was lost.",
        "diagnosis": "over_ordering", "action": "right_size_par", "confidence": "high",
    }))

    result = await _insight()

    assert result == {
        "headline": "Oat milk is over-ordered.", "detail": "Trim the PAR; $120 was lost.",
        "diagnosis": "over_ordering", "action": "right_size_par", "confidence": "high",
    }
    assert claude.calls[0]["json_output"] is True and claude.calls[0]["timeout_seconds"] == 20


@pytest.mark.asyncio
async def test_insight_caches_a_claude_wording(route_to_claude, monkeypatch):
    stored = {}

    async def cache_get(_redis, _key):
        return None

    async def cache_set(_redis, key, value, ttl):
        stored[key] = (value, ttl)

    monkeypatch.setattr(insight, "get_redis_cache", lambda: object())
    monkeypatch.setattr(insight, "cache_get", cache_get)
    monkeypatch.setattr(insight, "cache_set", cache_set)
    route_to_claude(json.dumps({
        "headline": "{item} is over-ordered.", "detail": "Trim the PAR.",
        "diagnosis": "over_ordering", "action": "right_size_par",
    }))

    result = await _insight()

    assert result["confidence"] == "model"
    assert [ttl for _value, ttl in stored.values()] == [900]


@pytest.mark.asyncio
@pytest.mark.parametrize("reply", [
    RuntimeError("Anthropic Messages request failed"),
    "no json here",
    json.dumps({"headline": "x", "detail": "y", "diagnosis": "handling", "action": "none"}),
    json.dumps({"headline": "Lost 12 units.", "detail": "y", "diagnosis": "over_ordering", "action": "right_size_par"}),
])
async def test_insight_falls_back_to_the_deterministic_conclusion(route_to_claude, monkeypatch, reply):
    monkeypatch.setattr(insight, "get_redis_cache", lambda: None)
    route_to_claude(reply)
    assert await _insight() == insight.deterministic_insight(diagnosis="over_ordering", tokens=TOKENS)


# --- Waste narration --------------------------------------------------------

async def _narrate():
    return await waste_agent._narrate_with_luna(question="Why so much waste?", sources={"top": "spoilage"})


@pytest.mark.asyncio
async def test_waste_narration_runs_on_claude_in_plain_text(route_to_claude, monkeypatch):
    _no_openai(monkeypatch, waste_agent)
    claude = route_to_claude("Most of the loss is spoilage in the walk-in.")

    assert await _narrate() == "Most of the loss is spoilage in the walk-in."
    call = claude.calls[0]
    assert call.get("json_output", False) is False and call["effort"] == "high"
    assert "Why so much waste?" in call["prompt"]


@pytest.mark.asyncio
@pytest.mark.parametrize("reply", ["Spoilage cost $40 last week.", "", RuntimeError("Anthropic Messages request failed")])
async def test_waste_narration_rejects_numbers_and_failures(route_to_claude, reply):
    route_to_claude(reply)
    assert await _narrate() is None


# --- One-shot ticket draft --------------------------------------------------

class _Session:
    def __init__(self):
        self.calls = []

    async def create_response(self, *, model, input, instructions, **kwargs):
        self.calls.append({"model": model, "feature": ai_usage._feature_override.get(), **kwargs})
        return LunaResponse(response_id="msg_1", text=json.dumps({
            "title": "Add product editing", "description": "Use the product routes.",
            "priority": "high", "category": "product", "board_column": "todo",
            "assignee_name": None, "element_name": None, "subtasks": [],
        }), usage={"input_tokens": 100, "output_tokens": 20, "total_tokens": 120})


@pytest.mark.asyncio
async def test_ticket_draft_runs_on_claude_and_reports_that_model(route_to_claude, monkeypatch):
    claude, luna = _Session(), _Session()
    monkeypatch.setattr(task_draft, "get_claude_client", lambda: claude)
    monkeypatch.setattr(task_draft, "get_luna_client", lambda: luna)

    result = await task_draft.generate_task_draft(
        prompt="Let sellers edit products", project_title="Shop", collaborator_names=[], elements=[],
    )

    assert not luna.calls
    call = claude.calls[0]
    assert call["model"] == CLAUDE and call["response_format_json"] is True
    assert call["feature"] == "matcha.espresso.task_draft"
    assert result["title"] == "Add product editing"
    assert result["token_usage"] == {
        "model": CLAUDE, "prompt_tokens": 100, "completion_tokens": 20, "total_tokens": 120,
    }


@pytest.mark.asyncio
async def test_ticket_draft_stays_on_luna_without_an_override(monkeypatch):
    claude, luna = _Session(), _Session()
    monkeypatch.setattr(task_draft, "get_claude_client", lambda: claude)
    monkeypatch.setattr(task_draft, "get_luna_client", lambda: luna)

    result = await task_draft.generate_task_draft(
        prompt="Let sellers edit products", project_title="Shop", collaborator_names=[], elements=[],
    )

    assert not claude.calls
    assert luna.calls[0]["model"] == "gpt-5.6-luna"
    assert result["token_usage"]["model"] == "gpt-5.6-luna"
