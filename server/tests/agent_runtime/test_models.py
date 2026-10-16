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
async def test_with_a_key_the_menu_is_claude_only_and_starts_on_the_admin_setting(claude):
    rows, default = await models.picker()
    assert rows == [
        {"id": "claude-haiku-5-5", "label": "Claude Haiku 5.5"},
        {"id": "claude-sonnet-5-5", "label": "Claude Sonnet 5.5"},
    ]
    # An admin "default" (no Claude routing) runs Haiku, never Luna.
    assert default == "claude-haiku-5-5"
    claude.return_value = "claude-sonnet-5-5"
    assert (await models.picker())[1] == "claude-sonnet-5-5"
    claude.assert_awaited_with(agent_surfaces.ESPRESSO_ASSISTANT)


@pytest.mark.asyncio
async def test_no_anthropic_key_means_luna_only():
    # conftest blanks the key.
    assert await models.picker() == ([{"id": "gpt-5.6-luna", "label": "OpenAI Luna"}], "gpt-5.6-luna")
    assert await models.resolve("claude-haiku-5-5") == "gpt-5.6-luna"


def test_the_assistant_menu_and_the_schedule_picker_share_one_rule():
    from app.matcha.services.huume import routing

    for configured in (True, False):
        menu = models.anthropic_messages.offered_models(configured=configured)
        assert tuple(c.id for c in routing.schedule_choices(anthropic_configured=configured)) == menu
    assert models.offered() == models.anthropic_messages.offered_models()


@pytest.mark.asyncio
async def test_resolve_keeps_only_an_offered_pick(claude):
    claude.return_value = "claude-haiku-5-5"
    assert await models.resolve("claude-sonnet-5-5") == "claude-sonnet-5-5"
    # A stale Luna pick from an older app runs the default.
    for junk in (None, "", "gpt-4o", "gpt-5.6-luna", 7, ["claude-sonnet-5-5"]):
        assert await models.resolve(junk) == "claude-haiku-5-5"
    assert models.is_claude("claude-sonnet-5-5") and not models.is_claude("gpt-5.6-luna")


def test_every_offered_model_has_a_label():
    assert set(models.LABELS) >= {"gpt-5.6-luna", *models.CLAUDE_MODELS}
