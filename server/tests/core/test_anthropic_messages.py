"""The shared Claude pieces: the per-app/per-product "AI models" switch, the
one-shot call, and the admin endpoint that sets it. No network, no database.

    cd server && ./venv/bin/python -m pytest tests/core/test_anthropic_messages.py -q
"""

from contextlib import asynccontextmanager
from datetime import datetime, timezone
from types import SimpleNamespace
from unittest.mock import AsyncMock

import anthropic
import httpx2
import pytest
from anthropic.types.beta import BetaMessage
from fastapi import HTTPException

from app.core.services import anthropic_messages, platform_settings


def _message(*, text="ok", stop_reason="end_turn", model="claude-haiku-5-5"):
    return BetaMessage.model_validate({
        "id": "msg_1", "type": "message", "role": "assistant", "model": model,
        "content": [{"type": "text", "text": text}] if text else [],
        "stop_reason": stop_reason, "stop_sequence": None,
        "usage": {"input_tokens": 5, "output_tokens": 3},
    })


class _FakeAnthropic:
    def __init__(self, outcome):
        self.outcome = outcome
        self.params = None
        self.beta = SimpleNamespace(messages=SimpleNamespace(create=self._create))

    def with_options(self, **kwargs):
        self.options = kwargs
        return self

    async def _create(self, **params):
        self.params = params
        if isinstance(self.outcome, BaseException):
            raise self.outcome
        return self.outcome


@pytest.fixture
def ledger(monkeypatch):
    rows = []

    async def record(**kwargs):
        rows.append(kwargs)

    monkeypatch.setattr(anthropic_messages, "record_anthropic_response", record)
    return rows


@pytest.fixture(autouse=True)
def _reset_caches(monkeypatch):
    monkeypatch.setattr(anthropic_messages, "_client", None)
    monkeypatch.setattr(platform_settings, "_agent_models_cache", None)
    monkeypatch.setattr(platform_settings, "_agent_models_cached_at", 0.0)


def _settings(key):
    return lambda: SimpleNamespace(anthropic_api_key=key)


# --- JSON + blocks ------------------------------------------------------------

@pytest.mark.parametrize("raw", [
    '{"a": 1}',
    '```json\n{"a": 1}\n```',
    'Sure — here it is: {"a": 1} hope that helps',
])
def test_parse_json_object_tolerates_fences_and_prose(raw):
    assert anthropic_messages.parse_json_object(raw) == {"a": 1}


@pytest.mark.parametrize("raw", ["", "no json here", "[1, 2]"])
def test_parse_json_object_refuses_non_objects(raw):
    with pytest.raises(ValueError):
        anthropic_messages.parse_json_object(raw)


def test_image_and_pdf_blocks():
    block = anthropic_messages.image_block(b"\x89PNG", "IMAGE/PNG")
    assert block["source"]["media_type"] == "image/png" and block["source"]["data"]
    assert anthropic_messages.image_block(b"x", "image/tiff") is None
    assert anthropic_messages.image_block(b"", "image/png") is None
    assert anthropic_messages.pdf_block(b"%PDF")["source"]["media_type"] == "application/pdf"


def test_only_sonnet_sends_the_server_side_fallback():
    assert anthropic_messages.request_extras("claude-haiku-5-5") == {}
    assert anthropic_messages.request_extras("claude-sonnet-5-5") == {
        "fallbacks": "default", "betas": ["server-side-fallback-2026-07-01"],
    }


# --- The platform switch ------------------------------------------------------

def test_anthropic_configured_survives_unloaded_settings(monkeypatch):
    def unloaded():
        raise RuntimeError("Settings not initialized")

    monkeypatch.setattr(anthropic_messages, "get_settings", unloaded)
    assert anthropic_messages.anthropic_configured() is False


@pytest.mark.asyncio
async def test_no_key_means_default_without_reading_the_setting(monkeypatch):
    monkeypatch.setattr(anthropic_messages, "get_settings", _settings(None))
    reader = AsyncMock(return_value="claude-haiku-5-5")
    monkeypatch.setattr(platform_settings, "get_agent_model", reader)
    assert await anthropic_messages.claude_override("matcha.ir") is None
    reader.assert_not_awaited()


@pytest.mark.asyncio
@pytest.mark.parametrize("stored, expected", [
    ("claude-sonnet-5-5", "claude-sonnet-5-5"),
    ("claude-haiku-5-5", "claude-haiku-5-5"),
    ("default", None),
    ("gpt-4o", None),
])
async def test_override_follows_the_surfaces_setting(monkeypatch, stored, expected):
    monkeypatch.setattr(anthropic_messages, "get_settings", _settings("sk-test"))
    reader = AsyncMock(return_value=stored)
    monkeypatch.setattr(platform_settings, "get_agent_model", reader)
    assert await anthropic_messages.claude_override("matcha.ir") == expected
    reader.assert_awaited_once_with("matcha.ir")


@pytest.mark.asyncio
async def test_an_unreadable_setting_is_default_not_an_outage(monkeypatch):
    monkeypatch.setattr(anthropic_messages, "get_settings", _settings("sk-test"))
    monkeypatch.setattr(platform_settings, "get_agent_model", AsyncMock(side_effect=OSError("db down")))
    assert await anthropic_messages.claude_override("matcha.ir") is None


_SAVED_AT = datetime(2026, 10, 9, 12, 0, tzinfo=timezone.utc)


class _Conn:
    """platform_settings rows for `get_agent_models` (key → stored JSON text)."""

    def __init__(self, rows: dict):
        self.rows = rows
        self.reads = 0

    async def fetch(self, query):
        self.reads += 1
        return [{"key": k, "value": v, "updated_at": _SAVED_AT} for k, v in self.rows.items()]


@pytest.mark.asyncio
async def test_before_the_first_save_the_legacy_setting_seeds_matcha_and_espresso():
    conn = _Conn({"agent_model": '"claude-haiku-5-5"'})
    models = await platform_settings.get_agent_models(conn=conn)
    # Gummfit and Tell-Us never read the old setting, so they start built-in.
    assert models["apps"] == {
        "matcha": "claude-haiku-5-5", "espresso": "claude-haiku-5-5", "gummfit": "default", "tellus": "default",
    }
    assert set(models["surfaces"].values()) == {"inherit"}
    # Cached, the default included: no second query inside the TTL.
    await platform_settings.get_agent_models(conn=conn)
    assert conn.reads == 1


@pytest.mark.asyncio
async def test_saved_map_wins_over_the_legacy_row_and_resolves_per_surface():
    conn = _Conn({
        "agent_model": '"claude-haiku-5-5"',
        "agent_models": '{"apps": {"matcha": "claude-sonnet-5-5"}, '
                        '"surfaces": {"matcha.ir": "default", "matcha.huume": "claude-haiku-5-5", "bogus": "x"}}',
    })
    assert await platform_settings.get_agent_model("matcha.ir", conn=conn) == "default"
    assert await platform_settings.get_agent_model("matcha.huume", conn=conn) == "claude-haiku-5-5"
    assert await platform_settings.get_agent_model("matcha.handbooks", conn=conn) == "claude-sonnet-5-5"
    assert await platform_settings.get_agent_model("espresso.chat", conn=conn) == "default"  # app unset
    models = await platform_settings.get_agent_models(conn=conn)
    assert "bogus" not in models["surfaces"]


@pytest.mark.asyncio
async def test_nothing_stored_is_built_in_everywhere():
    assert await platform_settings.get_agent_model("matcha.ir", conn=_Conn({})) == "default"


def test_an_unregistered_surface_follows_its_app_and_never_crashes():
    models = platform_settings.normalize_agent_models({"apps": {"matcha": "claude-haiku-5-5"}})
    assert platform_settings.resolve_agent_model(models, "matcha.not_a_surface") == "claude-haiku-5-5"
    assert platform_settings.resolve_agent_model(models, "nowhere.at_all") == "default"


@pytest.mark.asyncio
async def test_get_agent_models_opens_its_own_connection(monkeypatch):
    conn = _Conn({"agent_models": '{"apps": {"espresso": "claude-haiku-5-5"}}'})

    @asynccontextmanager
    async def managed():
        yield conn

    monkeypatch.setattr(platform_settings, "get_connection", managed)
    assert await platform_settings.get_agent_model("espresso.chat") == "claude-haiku-5-5"


def test_prime_normalizes_unknown_values():
    models = platform_settings.prime_agent_models_cache({"apps": {"matcha": "nonsense"}})
    assert models["apps"]["matcha"] == "default"


# --- One-shot call -------------------------------------------------------------

@pytest.mark.asyncio
async def test_generate_text_sends_json_instruction_and_attachments(monkeypatch, ledger):
    fake = _FakeAnthropic(_message(text='{"ok": true}', model="claude-sonnet-5-5"))
    monkeypatch.setattr(anthropic_messages, "get_async_client", lambda: fake)
    image = anthropic_messages.image_block(b"\x89PNG", "image/png")
    text = await anthropic_messages.generate_text(
        "Classify this", model="claude-sonnet-5-5", system="Be brief.",
        attachments=[image], json_output=True, max_tokens=500, timeout_seconds=12,
    )
    assert text == '{"ok": true}'
    params = fake.params
    assert params["max_tokens"] == 4096  # floored: thinking shares the cap
    assert params["system"].startswith("Be brief.") and "exactly one JSON object" in params["system"]
    assert params["messages"][0]["content"][0] == image
    assert params["messages"][0]["content"][1] == {"type": "text", "text": "Classify this"}
    assert params["thinking"] == {"type": "adaptive"} and params["output_config"] == {"effort": "low"}
    assert params["fallbacks"] == "default"
    assert fake.options == {"timeout": 12}
    assert ledger[0]["message"]["id"] == "msg_1"


@pytest.mark.asyncio
async def test_generate_text_without_system_or_json(monkeypatch, ledger):
    fake = _FakeAnthropic(_message(text="Plain."))
    monkeypatch.setattr(anthropic_messages, "get_async_client", lambda: fake)
    assert await anthropic_messages.generate_text("Hi", model="claude-haiku-5-5") == "Plain."
    assert "system" not in fake.params and "fallbacks" not in fake.params


@pytest.mark.asyncio
async def test_a_refusal_raises(monkeypatch, ledger):
    monkeypatch.setattr(anthropic_messages, "get_async_client",
                        lambda: _FakeAnthropic(_message(text="", stop_reason="refusal")))
    with pytest.raises(RuntimeError, match="declined"):
        await anthropic_messages.generate_text("x", model="claude-haiku-5-5")


@pytest.mark.asyncio
@pytest.mark.parametrize("error, status", [
    (anthropic.APITimeoutError(request=httpx2.Request("POST", "https://api.anthropic.com")), "timeout"),
    (anthropic.APIConnectionError(request=httpx2.Request("POST", "https://api.anthropic.com")), "error"),
])
async def test_api_errors_are_recorded_then_raised(monkeypatch, ledger, error, status):
    monkeypatch.setattr(anthropic_messages, "get_async_client", lambda: _FakeAnthropic(error))
    with pytest.raises(RuntimeError):
        await anthropic_messages.generate_text("x", model="claude-haiku-5-5")
    assert ledger[0]["status"] == status


def test_client_needs_a_key_and_is_cached(monkeypatch):
    monkeypatch.setattr(anthropic_messages, "get_settings", _settings(None))
    with pytest.raises(RuntimeError, match="ANTHROPIC_API_KEY"):
        anthropic_messages.get_async_client()
    monkeypatch.setattr(anthropic_messages, "get_settings", _settings("sk-test"))
    first = anthropic_messages.get_async_client()
    assert isinstance(first, anthropic.AsyncAnthropic)
    assert anthropic_messages.get_async_client() is first


# --- Admin endpoint -------------------------------------------------------------

class _AdminDb:
    """platform_settings for the admin PUT: a transaction, the locked read,
    and the two upserts it writes."""

    def __init__(self, rows: dict | None = None):
        self.rows = dict(rows or {})
        self.saved_at = {k: _SAVED_AT for k in self.rows}
        self.writes: dict[str, object] = {}

    def transaction(self):
        @asynccontextmanager
        async def tx():
            yield

        return tx()

    async def fetch(self, query):
        assert "FOR UPDATE" in query
        return [{"key": k, "value": v, "updated_at": self.saved_at[k]} for k, v in self.rows.items()]

    async def fetchval(self, query, value):
        new_at = datetime(2026, 10, 10, tzinfo=timezone.utc)
        self.rows["agent_models"], self.saved_at["agent_models"] = value, new_at
        self.writes["agent_models"] = value
        return new_at

    async def execute(self, query, value):
        self.writes["agent_model"] = value


@pytest.fixture
def admin_db(monkeypatch):
    from app.core.routes.admin import platform_settings as route

    def use(rows=None, *, key="sk-test") -> _AdminDb:
        db = _AdminDb(rows)

        @asynccontextmanager
        async def connection():
            yield db

        monkeypatch.setattr(route, "get_connection", connection)
        monkeypatch.setattr(route, "get_settings", _settings(key))
        return db

    return use


async def _put(**body):
    from app.core.models.admin import AgentModelsUpdate
    from app.core.routes.admin import platform_settings as route

    return await route.update_agent_models(AgentModelsUpdate(**body), admin=None)


@pytest.mark.asyncio
async def test_admin_refuses_a_newly_chosen_claude_without_a_key(admin_db):
    admin_db(key=None)
    with pytest.raises(HTTPException) as err:
        await _put(surfaces={"matcha.ir": "claude-haiku-5-5"})
    assert err.value.status_code == 400 and "ANTHROPIC_API_KEY" in err.value.detail


@pytest.mark.asyncio
async def test_removing_the_key_never_locks_the_page(admin_db):
    """A Claude value already stored (even on a row the page doesn't change)
    rides through; only a newly chosen one needs the key."""
    import json

    stored = {"apps": {"matcha": "claude-haiku-5-5"}, "surfaces": {"espresso.chat": "claude-sonnet-5-5"}}
    db = admin_db({"agent_models": json.dumps(stored)}, key=None)
    out = await _put(
        apps={"matcha": "claude-haiku-5-5"},
        surfaces={"espresso.chat": "claude-sonnet-5-5", "matcha.ir": "default"},
        version=_SAVED_AT.isoformat(),
    )
    assert out["agent_models"]["surfaces"]["matcha.ir"] == "default"
    assert json.loads(db.writes["agent_models"])["surfaces"]["espresso.chat"] == "claude-sonnet-5-5"


@pytest.mark.asyncio
async def test_admin_refuses_an_unknown_app_product_or_model(admin_db):
    admin_db()
    with pytest.raises(HTTPException) as err:
        await _put(apps={"nope": "default"}, surfaces={"matcha.typo": "default"})
    assert err.value.status_code == 400 and "matcha.typo" in err.value.detail and "nope" in err.value.detail
    with pytest.raises(HTTPException) as err:
        await _put(surfaces={"matcha.ir": "claude-opus-9"})
    assert err.value.status_code == 400 and "claude-opus-9" in err.value.detail


@pytest.mark.asyncio
async def test_a_stale_page_gets_409_instead_of_overwriting(admin_db):
    import json

    admin_db({"agent_models": json.dumps({"apps": {"matcha": "claude-sonnet-5-5"}})})
    with pytest.raises(HTTPException) as err:
        await _put(apps={"matcha": "default"}, version="2026-01-01T00:00:00+00:00")
    assert err.value.status_code == 409
    with pytest.raises(HTTPException) as err:  # a page that never saw the first save
        await _put(apps={"matcha": "default"}, version=None)
    assert err.value.status_code == 409


@pytest.mark.asyncio
async def test_admin_saves_the_map_and_the_legacy_row_and_primes_the_cache(admin_db):
    import json

    db = admin_db({"agent_model": '"claude-haiku-5-5"'})  # never saved: version is None
    out = await _put(
        apps={"matcha": "claude-sonnet-5-5"}, surfaces={"matcha.ir": "claude-haiku-5-5"}, version=None,
    )
    saved = json.loads(db.writes["agent_models"])
    assert saved == out["agent_models"]
    assert saved["apps"] == {
        "matcha": "claude-sonnet-5-5", "espresso": "default", "gummfit": "default", "tellus": "default",
    }
    assert saved["surfaces"]["matcha.huume"] == "inherit"  # omitted → follows Matcha
    # A container still on the old code reads the legacy row: keep it current.
    assert json.loads(db.writes["agent_model"]) == "claude-sonnet-5-5"
    assert out["version"] == "2026-10-10T00:00:00+00:00"
    # The cache serves the write without a read.
    assert await platform_settings.get_agent_model("matcha.huume", conn=_Conn({})) == "claude-sonnet-5-5"


@pytest.mark.asyncio
async def test_settings_page_reports_the_map_registry_choices_version_and_key_state(monkeypatch):
    from app.core.routes.admin import platform_settings as route

    models = platform_settings.normalize_agent_models({"apps": {"matcha": "claude-haiku-5-5"}})
    for name, value in {
        "get_visible_features": [], "get_matcha_work_model_mode": "light",
        "get_jurisdiction_research_model_mode": "light", "get_er_similarity_weights": {},
        "get_tenant_codified_only": True, "get_autopr_board_capabilities": {},
        "get_agent_models": models,
    }.items():
        monkeypatch.setattr(route, name, AsyncMock(return_value=value))

    @asynccontextmanager
    async def connection():
        yield _Conn({"agent_models": "{}"})

    monkeypatch.setattr(route, "get_connection", connection)
    monkeypatch.setattr(route, "get_settings", _settings("sk-test"))
    out = await route.get_all_platform_settings()
    assert out["agent_models"]["apps"]["matcha"] == "claude-haiku-5-5" and out["anthropic_configured"] is True
    assert out["agent_models_version"] == _SAVED_AT.isoformat()
    assert [c["id"] for c in out["agent_model_choices"]] == ["claude-haiku-5-5", "claude-sonnet-5-5"]
    apps = {app["key"]: app for app in out["agent_model_registry"]}
    assert [s["key"] for s in apps["matcha"]["surfaces"]][:2] == ["matcha.huume", "matcha.scheduling"]
    assert [s["label"] for s in apps["espresso"]["surfaces"]] == ["Chat", "Purchase agent", "Assistant", "Projects"]


def test_an_unregistered_surface_is_warned_about_once(caplog):
    platform_settings._warned_unregistered_surfaces.discard("matcha.once_only")
    models = platform_settings.normalize_agent_models({})
    with caplog.at_level("WARNING"):
        for _ in range(3):
            platform_settings.resolve_agent_model(models, "matcha.once_only")
    assert sum("matcha.once_only" in r.message for r in caplog.records) == 1
