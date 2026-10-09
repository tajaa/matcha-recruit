"""Gemini one-shots that follow the platform "Agent model" setting to Claude.

    cd server && ./venv/bin/python -m pytest tests/test_claude_gemini_routed.py -q

`anthropic_messages.generate_content_routed` is the one switch Sym-link chat,
the IR analysis / copilot / intake / consistency / OSHA / interview /
precedent calls and the handbook audit / guided draft / pilot / upload check
go through: Gemini untouched while the setting is "default", the same request
on Claude when it names a model. No network, no database: `claude_override`
and `generate_text` are faked at the shared module.
"""

import asyncio
import json
from types import SimpleNamespace

import pytest
from google.genai import types

from app.core.services import anthropic_messages
from app.matcha.services import precedent_common
from app.matcha.services.ir import ir_analysis, ir_chat_intake
from app.matcha.services.symlink import chat as symlink_chat
from app.matcha.services.symlink.kinds import materialize_spec

CLAUDE = anthropic_messages.CLAUDE_HAIKU
PDF = b"%PDF-1.4 fake"


class _Gemini:
    def __init__(self, text="gemini"):
        self.text = text
        self.calls = []
        self.aio = SimpleNamespace(models=self)

    async def generate_content(self, **kwargs):
        self.calls.append(kwargs)
        return SimpleNamespace(text=self.text)


class _Claude:
    def __init__(self, reply):
        self.reply = reply
        self.calls = []

    async def __call__(self, prompt, **kwargs):
        self.calls.append({"prompt": prompt, **kwargs})
        if isinstance(self.reply, BaseException):
            raise self.reply
        return self.reply


@pytest.fixture
def setting(monkeypatch):
    """Set the Agent model (None = default) and the Claude reply."""
    def use(model, reply="{}") -> _Claude:
        async def override():
            return model

        monkeypatch.setattr(anthropic_messages, "claude_override", override)
        fake = _Claude(reply)
        monkeypatch.setattr(anthropic_messages, "generate_text", fake)
        return fake

    return use


# --- The helper -------------------------------------------------------------

def test_default_setting_runs_gemini_unchanged(setting):
    claude = setting(None)
    gemini = _Gemini("hi")
    config = types.GenerateContentConfig(temperature=0.2)
    out = asyncio.run(anthropic_messages.generate_content_routed(
        gemini, model="gemini-x", contents="prompt", config=config, timeout_seconds=5,
    ))
    assert out.text == "hi"
    assert gemini.calls == [{"model": "gemini-x", "contents": "prompt", "config": config}]
    assert claude.calls == []


def test_claude_gets_the_text_pdf_and_system_instruction(setting):
    claude = setting(CLAUDE, "plain answer")
    gemini = _Gemini()
    contents = [
        types.Part.from_bytes(data=PDF, mime_type="application/pdf"),
        "Extract the sections.",
        types.Content(role="user", parts=[types.Part(text="More context.")]),
    ]
    config = types.GenerateContentConfig(system_instruction="Be terse.", temperature=0.0)
    out = asyncio.run(anthropic_messages.generate_content_routed(
        gemini, model="gemini-x", contents=contents, config=config, timeout_seconds=5,
    ))
    assert out.text == "plain answer"
    assert gemini.calls == []
    call = claude.calls[0]
    assert call["model"] == CLAUDE
    assert call["prompt"] == "Extract the sections.\n\nMore context."
    assert call["system"] == "Be terse."
    assert [block["type"] for block in call["attachments"]] == ["document"]
    assert call["json_output"] is False
    assert call["timeout_seconds"] == 5  # the site's own budget, not a longer one


def test_json_mode_follows_the_config_and_normalizes_the_reply(setting):
    claude = setting(CLAUDE, 'Sure:\n```json\n{"ok": true}\n```')
    config = types.GenerateContentConfig(response_mime_type="application/json")
    out = asyncio.run(anthropic_messages.generate_content_routed(
        _Gemini(), model="m", contents=["p"], config=config, timeout_seconds=5,
    ))
    assert claude.calls[0]["json_output"] is True
    assert json.loads(out.text) == {"ok": True}  # strict json.loads works


def test_unparseable_json_reply_is_passed_through_for_the_site_to_report(setting):
    setting(CLAUDE, "no json here")
    out = asyncio.run(anthropic_messages.generate_content_routed(
        _Gemini(), model="m", contents="p", timeout_seconds=5, json_output=True,
    ))
    assert out.text == "no json here"


def test_claude_is_held_to_the_sites_timeout(setting, monkeypatch):
    """A 20s chat turn stays 20s on Claude: past the budget the call raises
    asyncio.TimeoutError, which every site already turns into its retry reply."""
    started = asyncio.Event()

    async def slow(prompt, **kwargs):
        started.set()
        await asyncio.sleep(10)
        return "{}"

    setting(CLAUDE)
    monkeypatch.setattr(anthropic_messages, "generate_text", slow)
    with pytest.raises(asyncio.TimeoutError):
        asyncio.run(anthropic_messages.generate_content_routed(
            _Gemini(), model="m", contents="p", timeout_seconds=0.05,
        ))
    assert started.is_set()


def test_claude_failure_raises_like_gemini(setting):
    setting(CLAUDE, RuntimeError("Anthropic down"))
    with pytest.raises(RuntimeError):
        asyncio.run(anthropic_messages.generate_content_routed(
            _Gemini(), model="m", contents="p", timeout_seconds=5,
        ))


def test_inline_image_part_becomes_an_image_block():
    prompt, blocks = anthropic_messages._gemini_contents_to_claude(
        [types.Part.from_bytes(data=b"\x89PNG", mime_type="image/png"), "describe"],
    )
    assert prompt == "describe"
    assert blocks[0]["type"] == "image"


# --- Call sites ---------------------------------------------------------------

CRED = materialize_spec("credential_upload")


def test_symlink_chat_turn_runs_on_claude(setting, monkeypatch):
    claude = setting(CLAUDE, json.dumps({"assistant_message": "When does it expire?"}))
    gemini = _Gemini()
    monkeypatch.setattr(symlink_chat, "genai_env_client", lambda: gemini)
    result = asyncio.run(symlink_chat.next_turn(
        [{"role": "user", "content": "my RN license"}], {}, CRED, [],
    ))
    assert result["error"] is False
    assert result["assistant_message"] == "When does it expire?"
    assert gemini.calls == []
    assert claude.calls[0]["json_output"] is True


def test_symlink_chat_keeps_its_20s_budget_on_claude(setting, monkeypatch):
    assert symlink_chat.CHAT_TURN_TIMEOUT == 20
    claude = setting(CLAUDE, json.dumps({"assistant_message": "ok"}))
    monkeypatch.setattr(symlink_chat, "genai_env_client", lambda: _Gemini())
    asyncio.run(symlink_chat.next_turn([], {}, CRED, []))
    assert claude.calls[0]["timeout_seconds"] == 20


def test_ir_chat_intake_keeps_its_20s_budget_on_claude(setting, monkeypatch):
    assert ir_chat_intake.CHAT_TURN_TIMEOUT == 20
    claude = setting(CLAUDE, json.dumps({"assistant_message": "Where did it happen?"}))
    monkeypatch.setattr(ir_chat_intake, "genai_env_client", lambda: _Gemini())
    result = asyncio.run(ir_chat_intake.next_turn([], {}, location_options=[]))
    assert result["error"] is False
    assert claude.calls[0]["timeout_seconds"] == 20


def test_ir_analysis_retry_loop_runs_on_claude(setting, monkeypatch):
    claude = setting(CLAUDE, '{"category": "safety"}')

    class _Limiter:
        async def check_limit(self, *a):
            return None

        async def record_call(self, *a):
            return None

    monkeypatch.setattr(ir_analysis, "get_rate_limiter", lambda: _Limiter())
    analyzer = ir_analysis.IRAnalyzer.__new__(ir_analysis.IRAnalyzer)
    analyzer.client = _Gemini()
    analyzer.model = "gemini-x"
    result = asyncio.run(analyzer._call_with_retry(lambda feedback=None: "p", lambda r: None, label="t"))
    assert result == {"category": "safety"}
    assert analyzer.client.calls == []
    assert claude.calls[0]["effort"] == "medium"


def test_precedent_enrichment_is_claude_for_ir_only(setting, monkeypatch):
    claude = setting(CLAUDE, '{"scores": [], "pattern_summary": "x"}')
    gemini = _Gemini('{"scores": [], "pattern_summary": "gemini"}')

    class _Limiter:
        async def check_limit(self, *a):
            return None

        async def record_call(self, *a):
            return None

    import app.config as app_config
    import app.core.services.genai_client as genai_client
    import app.core.services.rate_limiter as rate_limiter

    monkeypatch.setattr(app_config, "get_settings", lambda: SimpleNamespace(analysis_model="gemini-x"))

    monkeypatch.setattr(genai_client, "get_genai_client", lambda api_key=None: gemini)
    monkeypatch.setattr(rate_limiter, "get_rate_limiter", lambda: _Limiter())

    er = asyncio.run(precedent_common.run_semantic_enrichment("p", domain="er_analysis"))
    assert er["pattern_summary"] == "gemini"
    assert claude.calls == []

    ir = asyncio.run(precedent_common.run_semantic_enrichment("p", domain="ir_analysis", agent_model=True))
    assert ir["pattern_summary"] == "x"
    assert len(claude.calls) == 1
