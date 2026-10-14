"""Which model runs an assistant run: the person's pick, else the platform's.

Espresso's assistant menu sends a pick with each message (`assistant_model` on
the socket frame). `resolve` keeps it only when this server offers it, so a
stale or hand-written value runs the default instead of failing. The default
is what Admin → Settings → *AI models* routes `espresso.assistant` to, else
OpenAI Luna. An explicit pick wins over that setting, as the thread chat's
Claude pick does.

No plan check here: Sonnet's gate (`ai_model_pro`) and the assistant's own
(`assistant`) are both Pro and up, so anyone who can run the assistant may
pick any row.
"""
from __future__ import annotations

from app.core.services import agent_surfaces, anthropic_messages
from app.core.services.anthropic_messages import CLAUDE_HAIKU, CLAUDE_MODELS, CLAUDE_SONNET
from app.matcha.services.huume.routing import LUNA

LABELS: dict[str, str] = {
    LUNA: "OpenAI Luna",
    CLAUDE_HAIKU: "Claude Haiku 5.5",
    CLAUDE_SONNET: "Claude Sonnet 5.5",
}


def offered() -> tuple[str, ...]:
    """The models a run can use on this server, in menu order."""
    if anthropic_messages.anthropic_configured():
        return (LUNA, *CLAUDE_MODELS)
    return (LUNA,)


async def default_model() -> str:
    return await anthropic_messages.claude_override(agent_surfaces.ESPRESSO_ASSISTANT) or LUNA


async def picker() -> tuple[list[dict], str]:
    """The menu (`[{"id", "label"}]`) and the row it starts on, for entitlements."""
    return [{"id": m, "label": LABELS[m]} for m in offered()], await default_model()


async def resolve(pick: object) -> str:
    """The model a run will use: `pick` when offered, else the default."""
    if isinstance(pick, str) and pick in offered():
        return pick
    return await default_model()


def is_claude(model: str) -> bool:
    return model in CLAUDE_MODELS
