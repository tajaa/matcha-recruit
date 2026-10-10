"""Gummfit's AI calls follow Admin → Settings → AI models.

    cd server && ./venv/bin/python -m pytest tests/cappe/test_cappe_agent_models.py -q

Merlin's single-step turn, the Merlin Auto classifier, directory inference and
booking suggestions go through `anthropic_messages.generate_content_routed`:
Gemini while their row is built-in (the existing Cappe tests cover that), the
same request on Claude when it names a model. No network, no database: the
setting, the Messages call and both rate-limit buckets are faked.
"""

import json
import os
from datetime import date
from types import SimpleNamespace
from uuid import uuid4

import pytest

os.environ.setdefault("LIVE_API", "test-key")
os.environ.setdefault("DATABASE_URL", "postgresql://test:test@localhost/test")
os.environ.setdefault("JWT_SECRET_KEY", "test-secret-key-cappe")

from app.config import load_settings  # noqa: E402

load_settings()

from app.cappe.services import booking_suggestions, directory  # noqa: E402
from app.cappe.services.merlin import routing, turn  # noqa: E402
from app.core.services import agent_surfaces, anthropic_messages  # noqa: E402
from app.core.services import rate_limiter as rate_limiter_module  # noqa: E402

HAIKU = anthropic_messages.CLAUDE_HAIKU


class _Gemini:
    """A Gemini client that must not be called while Claude is routed."""

    def __init__(self):
        self.calls = 0
        self.aio = SimpleNamespace(models=self)

    async def generate_content(self, **kwargs):
        self.calls += 1
        return SimpleNamespace(text="{}")


class _Buckets:
    """Both rate-limit buckets: the Gemini one each Cappe module holds, and the
    anthropic one the routed helper reads through `get_rate_limiter`."""

    def __init__(self):
        self.recorded: list[tuple] = []

    def bucket(self, provider="gemini"):
        outer = self

        class _B:
            async def check_limit(self, *a, **kw):
                return None

            async def record_call(self, service, endpoint=None):
                outer.recorded.append((provider, service, endpoint))

        return _B()


@pytest.fixture
def claude(monkeypatch):
    """Route the given surfaces to Haiku; returns the captured Messages requests."""
    requests: list[dict] = []
    buckets = _Buckets()
    replies: dict[str, str] = {}

    def use(surface: str, reply: str):
        replies[surface] = reply

        async def override(asked):
            return HAIKU if asked in replies else None

        async def create(params, **kwargs):
            requests.append({**params, **kwargs})
            text = next(iter(replies.values()))
            return SimpleNamespace(stop_reason="end_turn", content=[SimpleNamespace(type="text", text=text)])

        monkeypatch.setattr(anthropic_messages, "claude_override", override)
        monkeypatch.setattr(anthropic_messages, "_create", create)
        monkeypatch.setattr(rate_limiter_module, "get_rate_limiter", buckets.bucket)
        return requests, buckets

    return use


@pytest.mark.asyncio
@pytest.mark.parametrize("tier, effort", [("lite", "low"), ("regular", "medium"), ("max", "high")])
async def test_merlin_turn_runs_on_claude_with_the_tiers_effort(monkeypatch, claude, tier, effort):
    requests, buckets = claude(agent_surfaces.GUMMFIT_MERLIN, json.dumps({
        "message": "Updated the hero.",
        "ops": [{"op": "set_field", "block": "b1", "path": "heading", "value": "New"}],
    }))
    gemini = _Gemini()
    monkeypatch.setattr(turn, "get_genai_client", lambda **kw: gemini)
    monkeypatch.setattr(turn, "_get_rate_limiter", lambda: buckets.bucket("gemini"))

    result = await turn.run_merlin_turn(
        message="Change the hero heading", history=[], blocks=[{"id": "b1", "type": "hero", "heading": "Old"}],
        theme={}, model_tier=tier,
    )

    assert result["message"] == "Updated the hero." and len(result["ops"]) == 1
    assert gemini.calls == 0
    assert requests[0]["model"] == HAIKU and requests[0]["output_config"] == {"effort": effort}
    # Counted once, in the anthropic bucket — not also in Gemini's.
    assert buckets.recorded == [("anthropic", "cappe_merlin", tier)]


@pytest.mark.asyncio
async def test_merlin_auto_classifier_runs_on_claude(monkeypatch, claude):
    requests, buckets = claude(agent_surfaces.GUMMFIT_MERLIN_ROUTER, '{"complexity": "complex"}')
    monkeypatch.setattr(routing, "get_genai_client", lambda **kw: _Gemini())
    monkeypatch.setattr(routing, "ApiRateLimiter", lambda: buckets.bucket("gemini"))

    assert await routing._classify("Redesign the whole page around our new brand", None) == "max"
    assert requests[0]["deadline"] == routing._CLASSIFIER_TIMEOUT  # the same 6s budget
    assert buckets.recorded == [("anthropic", "cappe_merlin", "route")]


@pytest.mark.asyncio
async def test_directory_inference_runs_on_claude(monkeypatch, claude):
    requests, buckets = claude(agent_surfaces.GUMMFIT_DIRECTORY, json.dumps({
        "category": "food", "tags": ["coffee"], "blurb": "A neighbourhood cafe.",
    }))

    class _Conn:
        pass

    from contextlib import asynccontextmanager

    @asynccontextmanager
    async def connection():
        yield _Conn()

    async def context(conn, site_id):
        return {"name": "Po Coffee", "pages": []}

    monkeypatch.setattr(directory, "get_connection", connection)
    monkeypatch.setattr(directory, "gather_site_context", context)
    monkeypatch.setattr(directory, "_build_prompt", lambda ctx: "Suggest a listing")
    monkeypatch.setattr(directory, "get_genai_client", lambda **kw: _Gemini())
    monkeypatch.setattr(directory, "_get_rate_limiter", lambda: buckets.bucket("gemini"))

    listing = await directory.infer_listing(uuid4())
    assert listing is not None and listing["blurb"] == "A neighbourhood cafe."
    assert len(requests) == 1
    assert buckets.recorded == [("anthropic", "cappe_directory", "infer")]


@pytest.mark.asyncio
async def test_booking_preference_runs_on_claude(monkeypatch, claude):
    requests, buckets = claude(agent_surfaces.GUMMFIT_BOOKING, json.dumps({
        "staff_names": ["Ana"], "windows": [], "requested_count": 2,
    }))
    monkeypatch.setattr(booking_suggestions, "get_genai_client", lambda **kw: _Gemini())
    monkeypatch.setattr(booking_suggestions, "ApiRateLimiter", lambda: buckets.bucket("gemini"))

    preference = await booking_suggestions.extract_booking_preference(
        "Two options with Ana please", today=date(2026, 10, 9),
    )
    assert preference is not None and preference.staff_names == ("Ana",) and preference.requested_count == 2
    assert requests[0]["deadline"] == booking_suggestions._MODEL_TIMEOUT_SECONDS
    assert buckets.recorded == [("anthropic", "cappe_booking_suggestions", "parse")]


@pytest.mark.asyncio
async def test_built_in_rows_keep_gummfit_on_gemini(monkeypatch, claude):
    """A Claude choice for one row (Merlin) leaves another (booking) on Gemini."""
    _requests, buckets = claude(agent_surfaces.GUMMFIT_MERLIN, "{}")
    gemini = _Gemini()
    monkeypatch.setattr(booking_suggestions, "get_genai_client", lambda **kw: gemini)
    monkeypatch.setattr(booking_suggestions, "ApiRateLimiter", lambda: buckets.bucket("gemini"))
    await booking_suggestions.extract_booking_preference("Any time", today=date(2026, 10, 9))
    assert gemini.calls == 1
    assert buckets.recorded == [("gemini", "cappe_booking_suggestions", "parse")]
