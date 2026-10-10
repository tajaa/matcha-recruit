"""Tell-Us's flyer AI follows Admin → Settings → AI models.

    cd server && ./venv/bin/python -m pytest tests/tellus/test_flyer_ai_agent_models.py -q

`turn._generate` (the one call behind both the assistant and the idea
generator) goes through `anthropic_messages.generate_content_routed`: Gemini
while the Tell-Us row is built-in (test_flyer_ai covers that path), the same
request on Claude when it names a model. No network, no database.
"""

from types import SimpleNamespace

import pytest

from app.core.services import agent_surfaces, anthropic_messages
from app.core.services import rate_limiter as rate_limiter_module
from app.tellus.services.flyer_ai import turn

HAIKU = anthropic_messages.CLAUDE_HAIKU


class _Gemini:
    def __init__(self):
        self.calls = 0
        self.aio = SimpleNamespace(models=self)

    async def generate_content(self, **kwargs):
        self.calls += 1
        return SimpleNamespace(text='{"message": "gemini"}')


class _Buckets:
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
def env(monkeypatch):
    """Route `surfaces` to Haiku; returns (Messages requests, buckets, Gemini)."""
    requests: list[dict] = []
    buckets = _Buckets()
    gemini = _Gemini()

    def use(*surfaces: str):
        async def override(asked):
            return HAIKU if asked in surfaces else None

        async def create(params, **kwargs):
            requests.append({**params, **kwargs})
            return SimpleNamespace(stop_reason="end_turn",
                                   content=[SimpleNamespace(type="text", text='{"message": "claude"}')])

        monkeypatch.setattr(anthropic_messages, "claude_override", override)
        monkeypatch.setattr(anthropic_messages, "_create", create)
        monkeypatch.setattr(rate_limiter_module, "get_rate_limiter", buckets.bucket)
        monkeypatch.setattr(turn, "get_genai_client", lambda **kw: gemini)
        monkeypatch.setattr(turn, "_get_rate_limiter", lambda: buckets.bucket("gemini"))
        return requests, buckets, gemini

    return use


@pytest.mark.asyncio
async def test_flyer_ai_runs_on_claude_with_its_timeout(env):
    requests, buckets, gemini = env(agent_surfaces.TELLUS_FLYER_AI)
    response = await turn._generate("Make the title bigger")
    assert response.text == '{"message": "claude"}'
    assert gemini.calls == 0
    assert requests[0]["model"] == HAIKU and requests[0]["output_config"] == {"effort": "medium"}
    assert requests[0]["deadline"] == turn._TURN_TIMEOUT_SECONDS
    # Counted once, in the anthropic bucket — not also in Gemini's.
    assert buckets.recorded == [("anthropic", "tellus_flyer_ai", "assist")]


@pytest.mark.asyncio
async def test_built_in_keeps_the_flyer_ai_on_gemini(env):
    _requests, buckets, gemini = env(agent_surfaces.GUMMFIT_MERLIN)  # another app's row
    response = await turn._generate("Make the title bigger")
    assert response.text == '{"message": "gemini"}' and gemini.calls == 1
    assert buckets.recorded == [("gemini", "tellus_flyer_ai", "assist")]


@pytest.mark.asyncio
async def test_ideas_count_under_their_own_label(env):
    """`generate_ideas` checked the "ideas" budget but recorded under "assist"."""
    _requests, buckets, _gemini = env(agent_surfaces.TELLUS_FLYER_AI)
    await turn.generate_ideas(campaign={"title": "Free coffee for feedback", "reward": "Coffee"})
    assert buckets.recorded == [("anthropic", "tellus_flyer_ai", "ideas")]
