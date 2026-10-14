from unittest.mock import AsyncMock, Mock

import pytest

from app.core.services import agent_surfaces
from app.matcha.services.matcha_work.agent_runtime import models


@pytest.fixture
def claude(monkeypatch):
    monkeypatch.setattr(models.anthropic_messages, "anthropic_configured", Mock(return_value=True))
    override = AsyncMock(return_value=None)
    monkeypatch.setattr(models.anthropic_messages, "claude_override", override)
    return override


@pytest.mark.asyncio
async def test_the_menu_is_luna_then_claude_and_starts_on_the_admin_setting(claude):
    rows, default = await models.picker()
    assert rows == [
        {"id": "gpt-5.6-luna", "label": "OpenAI Luna"},
        {"id": "claude-haiku-5-5", "label": "Claude Haiku 5.5"},
        {"id": "claude-sonnet-5-5", "label": "Claude Sonnet 5.5"},
    ]
    assert default == "gpt-5.6-luna"
    claude.return_value = "claude-sonnet-5-5"
    assert (await models.picker())[1] == "claude-sonnet-5-5"
    claude.assert_awaited_with(agent_surfaces.ESPRESSO_ASSISTANT)


@pytest.mark.asyncio
async def test_no_anthropic_key_means_luna_only():
    # conftest blanks the key.
    assert await models.picker() == ([{"id": "gpt-5.6-luna", "label": "OpenAI Luna"}], "gpt-5.6-luna")
    assert await models.resolve("claude-haiku-5-5") == "gpt-5.6-luna"


@pytest.mark.asyncio
async def test_resolve_keeps_only_an_offered_pick(claude):
    claude.return_value = "claude-haiku-5-5"
    assert await models.resolve("claude-sonnet-5-5") == "claude-sonnet-5-5"
    assert await models.resolve("gpt-5.6-luna") == "gpt-5.6-luna"
    for junk in (None, "", "gpt-4o", 7, ["claude-sonnet-5-5"]):
        assert await models.resolve(junk) == "claude-haiku-5-5"
    assert models.is_claude("claude-sonnet-5-5") and not models.is_claude("gpt-5.6-luna")


def test_every_offered_model_has_a_label():
    assert set(models.LABELS) >= {"gpt-5.6-luna", *models.CLAUDE_MODELS}
