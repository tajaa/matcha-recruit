"""Gemini one-shots that follow the platform "Agent model" setting to Claude.

    cd server && ./venv/bin/python -m pytest tests/test_claude_gemini_routed.py -q

`anthropic_messages.generate_content_routed` is the one switch Sym-link chat,
the IR analysis / copilot / intake / consistency / OSHA / interview /
precedent calls and the handbook audit / guided draft / pilot / upload check
go through: Gemini untouched while the setting is "default", the same request
on Claude when it names a model. No network, no database: `claude_override`,
the Messages call (`_create`) and the rate limiter are faked.
"""

import asyncio
import contextlib
import io
import json
from types import SimpleNamespace
from uuid import uuid4

import pytest
from google.genai import types

from app.core.services import anthropic_messages
from app.core.services import rate_limiter as rate_limiter_module
from app.core.services.anthropic_messages import RoutedClaudeError
from app.core.services.rate_limiter import RateLimitExceeded
from app.matcha.services import precedent_common
from app.matcha.services.ir import ir_analysis, ir_chat_intake, ir_interview_questions
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


def _message(text: str, stop_reason: str = "end_turn"):
    return SimpleNamespace(stop_reason=stop_reason, content=[SimpleNamespace(type="text", text=text)])


class _Claude:
    """Stands in for `anthropic_messages._create`: records each request and
    returns `reply` as a Messages reply, or raises it."""

    def __init__(self, reply, stop_reason="end_turn"):
        self.reply = reply
        self.stop_reason = stop_reason
        self.calls = []

    async def __call__(self, params, **kwargs):
        self.calls.append({**params, **kwargs})
        if isinstance(self.reply, BaseException):
            raise self.reply
        return _message(self.reply, self.stop_reason)


class _Limiter:
    def __init__(self):
        self.full: set[str] = set()
        self.checked: list[tuple] = []
        self.recorded: list[tuple] = []

    def for_provider(self, provider="gemini"):
        outer = self

        class _Bucket:
            async def check_limit(self, service, endpoint=None):
                outer.checked.append((provider, service, endpoint))
                if provider in outer.full:
                    raise RateLimitExceeded(f"{provider} API hourly limit exceeded", "hourly", 1, 1)

            async def record_call(self, service, endpoint=None):
                outer.recorded.append((provider, service, endpoint))

        return _Bucket()


@pytest.fixture
def limiter(monkeypatch):
    fake = _Limiter()
    monkeypatch.setattr(rate_limiter_module, "get_rate_limiter", fake.for_provider)
    return fake


@pytest.fixture
def setting(monkeypatch, limiter):
    """Set the Agent model (None = default) and the Claude reply."""
    def use(model, reply="{}", stop_reason="end_turn") -> _Claude:
        async def override(surface):
            return model

        monkeypatch.setattr(anthropic_messages, "claude_override", override)
        fake = _Claude(reply, stop_reason)
        monkeypatch.setattr(anthropic_messages, "_create", fake)
        return fake

    return use


def _route(**kwargs):
    kwargs.setdefault("model", "gemini-x")
    kwargs.setdefault("contents", "p")
    kwargs.setdefault("timeout_seconds", 5)
    kwargs.setdefault("surface", "matcha.ir")
    client = kwargs.pop("client", None) or _Gemini()
    return asyncio.run(anthropic_messages.generate_content_routed(client, **kwargs))


def _text_of(call) -> str:
    return " ".join(b["text"] for m in call["messages"] for b in m["content"] if b["type"] == "text")


# --- The helper -------------------------------------------------------------

def test_default_setting_runs_gemini_unchanged(setting, limiter):
    claude = setting(None)
    gemini = _Gemini("hi")
    config = types.GenerateContentConfig(temperature=0.2)
    out = _route(client=gemini, contents="prompt", config=config)
    assert out.text == "hi"
    assert gemini.calls == [{"model": "gemini-x", "contents": "prompt", "config": config}]
    assert claude.calls == [] and limiter.checked == []
    assert not anthropic_messages.ran_on_claude(out)


def test_claude_gets_the_text_pdf_and_system_instruction(setting):
    claude = setting(CLAUDE, "plain answer")
    gemini = _Gemini()
    contents = [
        types.Part.from_bytes(data=PDF, mime_type="application/pdf"),
        "Extract the sections.",
        types.Content(role="user", parts=[types.Part(text="More context.")]),
    ]
    config = types.GenerateContentConfig(system_instruction="Be terse.", temperature=0.0)
    out = _route(client=gemini, contents=contents, config=config)
    assert out.text == "plain answer" and anthropic_messages.ran_on_claude(out)
    assert gemini.calls == []
    call = claude.calls[0]
    assert call["model"] == CLAUDE
    assert call["system"] == "Be terse."
    assert [m["role"] for m in call["messages"]] == ["user"]
    assert [b["type"] for b in call["messages"][0]["content"]] == ["document", "text", "text"]
    assert call["timeout_seconds"] == 5 and call["deadline"] == 5  # the site's own budget


def test_json_mode_keeps_arrays_and_normalizes_the_reply(setting):
    claude = setting(CLAUDE, 'Here you go:\n```json\n[{"question": "When?"}]\n```')
    config = types.GenerateContentConfig(response_mime_type="application/json")
    out = _route(contents=["p"], config=config)
    assert "object or an array" in claude.calls[0]["system"]
    assert json.loads(out.text) == [{"question": "When?"}]  # strict json.loads works


def test_unparseable_json_reply_is_passed_through_for_the_site_to_report(setting):
    setting(CLAUDE, "no json here")
    assert _route(json_output=True).text == "no json here"


def test_reply_cut_off_at_max_tokens_is_an_error_not_broken_json(setting):
    setting(CLAUDE, '{"sections": [{"title": "Leave', stop_reason="max_tokens")
    with pytest.raises(RoutedClaudeError, match="max_tokens"):
        _route(json_output=True, max_tokens=32_000)


def test_claude_failure_is_a_routed_claude_error(setting):
    setting(CLAUDE, RuntimeError("Anthropic Messages request failed: 404 model not found"))
    with pytest.raises(RoutedClaudeError):
        _route()


def test_full_anthropic_bucket_runs_the_call_on_gemini(setting, limiter):
    claude = setting(CLAUDE, "claude")
    limiter.full.add("anthropic")
    gemini = _Gemini("gemini")
    out = _route(client=gemini, rate_label=("symlink", "chat_turn"))
    assert out.text == "gemini" and claude.calls == []
    assert limiter.checked == [("anthropic", "symlink", "chat_turn")]


def test_claude_calls_count_in_the_anthropic_bucket(setting, limiter):
    setting(CLAUDE, "ok")
    _route(rate_label=("ir_chat_intake", "public_turn"))
    assert limiter.recorded == [("anthropic", "ir_chat_intake", "public_turn")]


def test_limiter_outage_lets_the_claude_call_through(setting, limiter, monkeypatch):
    claude = setting(CLAUDE, "ok")

    class _Down:
        async def check_limit(self, *a):
            raise OSError("db down")

        async def record_call(self, *a):
            raise OSError("db down")

    monkeypatch.setattr(rate_limiter_module, "get_rate_limiter", lambda provider="gemini": _Down())
    assert _route().text == "ok" and len(claude.calls) == 1


def test_attachments_past_claudes_limits_run_on_gemini(setting, monkeypatch):
    from pypdf import PdfWriter

    writer = PdfWriter()
    for _ in range(3):
        writer.add_blank_page(width=72, height=72)
    pdf = io.BytesIO()
    writer.write(pdf)
    contents = [types.Part.from_bytes(data=pdf.getvalue(), mime_type="application/pdf"), "Sections?"]

    claude = setting(CLAUDE, "{}")
    monkeypatch.setattr(anthropic_messages, "_MAX_PDF_PAGES", 2)
    assert _route(client=_Gemini("gemini"), contents=contents).text == "gemini"
    monkeypatch.setattr(anthropic_messages, "_MAX_PDF_PAGES", 600)
    monkeypatch.setattr(anthropic_messages, "_MAX_ROUTED_ATTACHMENT_B64", 10)
    assert _route(client=_Gemini("gemini"), contents=contents).text == "gemini"
    assert claude.calls == []


def test_no_surface_pins_gemini(setting, limiter):
    claude = setting(CLAUDE)
    assert _route(client=_Gemini("gemini"), surface=None).text == "gemini"
    assert claude.calls == [] and limiter.checked == []


def test_deadline_timeout_writes_its_ledger_row(monkeypatch):
    """Our deadline fires before the SDK's own timeout, so `_create` must
    write the status='timeout' row itself or the slowest calls go uncounted."""
    rows = []

    async def record(**kwargs):
        rows.append(kwargs)

    class _Slow:
        def with_options(self, **_):
            return self

        @property
        def beta(self):
            return SimpleNamespace(messages=SimpleNamespace(create=self.create))

        async def create(self, **_):
            await asyncio.sleep(10)

    monkeypatch.setattr(anthropic_messages, "get_async_client", lambda: _Slow())
    monkeypatch.setattr(anthropic_messages, "record_anthropic_response", record)
    with pytest.raises(asyncio.TimeoutError):
        asyncio.run(anthropic_messages._create({"model": CLAUDE}, timeout_seconds=0.05, deadline=0.05))
    assert rows[0]["status"] == "timeout" and rows[0]["model"] == CLAUDE


def test_translator_keeps_roles_and_puts_files_in_user_turns():
    contents = [
        types.Content(role="model", parts=[types.Part(text="Earlier answer")]),
        types.Content(role="user", parts=[
            types.Part.from_bytes(data=b"\x89PNG", mime_type="image/png"),
            types.Part.from_bytes(data=PDF, mime_type="application/pdf"),
            types.Part(text="What changed?"),
        ]),
        types.Content(role="model", parts=[types.Part.from_bytes(data=PDF, mime_type="application/pdf")]),
    ]
    messages = anthropic_messages.gemini_contents_to_messages(contents)
    assert [m["role"] for m in messages] == ["user", "assistant", "user"]  # padded to open on the user
    assert [b["type"] for b in messages[2]["content"]] == ["image", "document", "text"]


# --- Call sites ---------------------------------------------------------------

CRED = materialize_spec("credential_upload")


def test_symlink_chat_turn_runs_on_claude_within_its_20s_budget(setting, monkeypatch):
    assert symlink_chat.CHAT_TURN_TIMEOUT == 20
    claude = setting(CLAUDE, json.dumps({"assistant_message": "When does it expire?"}))
    gemini = _Gemini()
    monkeypatch.setattr(symlink_chat, "genai_env_client", lambda: gemini)
    result = asyncio.run(symlink_chat.next_turn(
        [{"role": "user", "content": "my RN license"}], {}, CRED, [],
    ))
    assert result["error"] is False
    assert result["assistant_message"] == "When does it expire?"
    assert gemini.calls == []
    assert claude.calls[0]["deadline"] == 20


def test_ir_chat_intake_keeps_its_20s_budget_on_claude(setting, monkeypatch):
    assert ir_chat_intake.CHAT_TURN_TIMEOUT == 20
    claude = setting(CLAUDE, json.dumps({"assistant_message": "Where did it happen?"}))
    monkeypatch.setattr(ir_chat_intake, "genai_env_client", lambda: _Gemini())
    result = asyncio.run(ir_chat_intake.next_turn([], {}, location_options=[]))
    assert result["error"] is False
    assert claude.calls[0]["deadline"] == 20


def test_ir_analysis_on_claude_does_not_count_in_the_gemini_bucket(setting, limiter, monkeypatch):
    claude = setting(CLAUDE, '{"category": "safety"}')
    monkeypatch.setattr(ir_analysis, "get_rate_limiter", limiter.for_provider)
    analyzer = ir_analysis.IRAnalyzer.__new__(ir_analysis.IRAnalyzer)
    analyzer.client = _Gemini()
    analyzer.model = "gemini-x"
    result = asyncio.run(analyzer._call_with_retry(lambda feedback=None: "p", lambda r: None, label="t"))
    assert result == {"category": "safety"}
    assert analyzer.client.calls == []
    assert claude.calls[0]["output_config"] == {"effort": "medium"}
    assert limiter.recorded == [("anthropic", "ir_analysis", "t")]  # nothing in the gemini bucket


def test_interview_questions_keep_their_list_on_claude(setting, monkeypatch):
    monkeypatch.setattr(ir_interview_questions, "get_genai_client", lambda api_key=None: _Gemini())
    setting(CLAUDE, 'Sure:\n[{"question": "What did you see?", "category": "facts"}]')
    questions = asyncio.run(ir_interview_questions.generate_investigation_questions(
        {"title": "Slip"}, "Ana", "witness",
    ))
    assert questions == [{"question": "What did you see?", "category": "facts"}]


def test_interview_questions_do_not_resend_a_failed_claude_call(setting, monkeypatch):
    monkeypatch.setattr(ir_interview_questions, "get_genai_client", lambda api_key=None: _Gemini())
    claude = setting(CLAUDE, RuntimeError("Anthropic Messages request failed: 404 model not found"))
    with pytest.raises(RoutedClaudeError):
        asyncio.run(ir_interview_questions.generate_investigation_questions({"title": "Slip"}, "Ana", "witness"))
    assert len(claude.calls) == 1  # not once per Gemini fallback model


@pytest.fixture
def precedent_env(monkeypatch, limiter):
    import app.config as app_config
    import app.core.services.genai_client as genai_client

    gemini = _Gemini('{"scores": [], "pattern_summary": "gemini"}')
    monkeypatch.setattr(app_config, "get_settings", lambda: SimpleNamespace(analysis_model="gemini-x"))
    monkeypatch.setattr(genai_client, "get_genai_client", lambda api_key=None: gemini)
    return gemini


def test_precedent_enrichment_is_claude_for_ir_only(setting, limiter, precedent_env):
    claude = setting(CLAUDE, '{"scores": [], "pattern_summary": "x"}')
    er = asyncio.run(precedent_common.run_semantic_enrichment("p", domain="er_analysis"))
    assert er["pattern_summary"] == "gemini"
    assert claude.calls == []
    assert ("gemini", "er_analysis", "precedent_semantic") in limiter.recorded

    limiter.recorded.clear()
    ir = asyncio.run(precedent_common.run_semantic_enrichment("p", domain="ir_analysis", surface="matcha.ir"))
    assert ir["pattern_summary"] == "x"
    assert len(claude.calls) == 1
    assert limiter.recorded == [("anthropic", "ir_analysis", "precedent_semantic")]


def test_precedent_does_not_resend_a_failed_claude_call(setting, precedent_env):
    claude = setting(CLAUDE, RuntimeError("Anthropic Messages request failed: 404 model not found"))
    out = asyncio.run(precedent_common.run_semantic_enrichment("p", domain="ir_analysis", surface="matcha.ir"))
    assert out == {"scores": [], "pattern_summary": None}
    assert len(claude.calls) == 1


def test_osha_determination_releases_the_connection_before_the_model_call(monkeypatch):
    from app.matcha.routes.ir_incidents.osha import recordability

    held = {"open": False}

    class _Conn:
        async def fetchrow(self, *_a):
            return {"title": "Cut", "description": "Cut hand", "incident_type": "injury",
                    "severity": "medium", "category_data": "{}"}

    @contextlib.asynccontextmanager
    async def connection():
        held["open"] = True
        try:
            yield _Conn()
        finally:
            held["open"] = False

    async def routed(*_a, **_k):
        assert held["open"] is False, "model called while holding a DB connection"
        return SimpleNamespace(text='{"recordable": true, "classification": "medical_treatment", "reasoning": "x"}')

    async def company_id(_user):
        return uuid4()

    monkeypatch.setattr(recordability, "get_connection", connection)
    monkeypatch.setattr(recordability, "generate_content_routed", routed)
    monkeypatch.setattr(recordability, "get_client_company_id", company_id)
    monkeypatch.setattr(recordability, "get_genai_client", lambda: object())
    monkeypatch.setattr(recordability, "get_settings", lambda: SimpleNamespace(analysis_model="gemini-x"))
    out = asyncio.run(recordability.osha_ai_determination(uuid4(), current_user=object(), _gate=None))
    assert out["recordable"] is True and out["classification"] == "medical_treatment"
