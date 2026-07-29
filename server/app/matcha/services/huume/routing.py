"""Huume's per-turn model/thinking tier — heuristic-first, mirroring cappe's
Merlin (`cappe/services/merlin/routing.py`): a free heuristic resolves the
obvious cases, an ambiguous turn lands in the safe middle tier rather than
the cheap one, and a routing failure never blocks the turn.

Unlike Merlin, this is heuristic-ONLY (no classifier call) — Huume's tool
loop already pays for its own Gemini calls per turn, and a routing verdict
doesn't need a second one. The registry-driven `intent_hints` on discovery
tools (`tools.HuumeTool.intent_hints`) double as the "this needs the strong
tier" signal, so a new skill gets tiering by declaring its tool, with no
changes here.

Three tiers, not two: `lite` for confirm turns (the most common turn shape —
"yes", "approve it"), `standard` for everything ordinary, `deep` for
discovery/analytical asks or a narrative-shaped message. `deep`'s model is
still flash — the user's call was thinking level, not a pro-tier model — kept
as a dataclass field so upgrading later is a one-line catalog edit.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Any, Iterable, Optional

from google.genai import types

from .tools import TOOLS, HuumeTool

# Public — agent.py's own `_MODEL` alias reads this (kept there, not
# re-literaled, so MODEL_PRICING lookups and any other "the model Huume
# uses" reference track this catalog). Leading underscore would make that a
# private-name reach-through; every other module-level name in this file
# that outside code reads (TIERS, FALLBACK_TIER, HINT_INDEX, ...) is public
# for the same reason.
FLASH = "gemini-3.6-flash"


@dataclass(frozen=True)
class HuumeTier:
    planner_model: str                 # first model call of the turn
    planner_thinking: Optional[str]    # None = omit ThinkingConfig entirely (today's behavior)
    executor_model: str                # calls 2..N (tool-result follow-ups)
    executor_thinking: Optional[str]


TIERS: dict[str, HuumeTier] = {
    "lite":     HuumeTier(FLASH, "none", FLASH, "none"),
    "standard": HuumeTier(FLASH, None,   FLASH, None),
    "deep":     HuumeTier(FLASH, "high", FLASH, "low"),
}
# Merlin's own rule: an unsure or failed routing decision lands in the
# middle, never the cheap tier — the cheap tier is only for turns the
# heuristic is CONFIDENT are a routine confirm.
FALLBACK_TIER = "standard"

# A short message shaped like "yes", "approve it", "go ahead" — only routes
# to `lite` when something is actually staged to confirm (has_pending_confirmable).
_CONFIRM_RE = re.compile(
    r"^(yes|yep|yeah|ok(ay)?|confirm(ed)?|go ahead|do it|send it|approve[d]?|proceed|sounds good)\b",
    re.I,
)
_CONFIRM_WORD_MAX = 8

_ANALYTICAL_RE = re.compile(
    r"\b(which|why|analy[sz]e|compare|recommend|assess|risk|what should|"
    r"how (do|should) (i|we)|what('s| is) (the best|going on)|help me (figure|decide|handle))\b",
    re.I,
)
# matcha_work_ai's own "this is a long/structured question, it's worth
# thinking" thresholds (services/matcha_work/matcha_work_ai/_models.py) —
# reused rather than re-derived.
_NARRATIVE_CHARS = 280
_NARRATIVE_NEWLINES = 2


def has_pending_confirmable(current_state: dict[str, Any]) -> bool:
    """True when a staged action or an active onboarding plan is waiting on
    the admin's confirmation — i.e. a short "yes" is a real confirm turn, not
    an empty message that happens to be short. `current_state` is untrusted
    (whatever the caller passed in) so every access is guarded; a malformed
    shape reads as "nothing pending", never raises."""
    from . import actions  # local: avoids import-order coupling with tools/agent

    try:
        action = current_state.get("huume_action")
        if isinstance(action, dict) and action.get("status") == "proposed":
            return True
        plans = current_state.get("huume_plans") or {}
        if isinstance(plans, dict):
            for plan in plans.values():
                if isinstance(plan, dict) and plan.get("status") in actions._ACTIVE_PLAN_STATUSES:
                    return True
    except Exception:
        return False
    return False


def build_hint_index(tools: Iterable[HuumeTool]) -> tuple[tuple[str, str], ...]:
    """`((lowercased hint, tool.name), ...)` — the registry `resolve_tier` and
    `prompt.build_discovery_block` both read, so a new discovery tool needs
    only its own `intent_hints` to get tiering. `HuumeTool._tool()` already
    lowercases hints at registration; this is a defensive re-lower in case a
    tool is constructed some other way."""
    return tuple(
        (hint.lower(), tool.name)
        for tool in tools
        for hint in tool.intent_hints
    )


# Built once at import time — TOOLS is a static module-level tuple.
HINT_INDEX: tuple[tuple[str, str], ...] = build_hint_index(TOOLS)


def resolve_tier(
    message: str, *, current_state: dict[str, Any], hint_index: tuple[tuple[str, str], ...] = HINT_INDEX,
) -> str:
    """Pure, never raises — any internal error routes to FALLBACK_TIER, the
    same "unsure lands in the middle" rule a routing exception follows.

    Order is load-bearing:
    1. A short confirm-shaped message with something actually pending -> lite.
       Without a pending confirmable, "yes" is just a short message (rule 4).
    2. Any registered intent hint substring-matches the message -> deep. This
       is what makes discovery tools "generally" tiered: a new skill declares
       intent_hints and gets routed here with no code change.
    3. An analytical-shaped question, or a long/narrative message -> deep.
    4. Otherwise FALLBACK_TIER.
    """
    try:
        text = (message or "").strip()
        if not text:
            return FALLBACK_TIER
        lowered = text.lower()

        if len(text.split()) <= _CONFIRM_WORD_MAX and _CONFIRM_RE.match(text) and has_pending_confirmable(current_state):
            return "lite"

        if any(hint in lowered for hint, _tool_name in hint_index):
            return "deep"

        if _ANALYTICAL_RE.search(text):
            return "deep"
        if len(text) > _NARRATIVE_CHARS or text.count("\n") > _NARRATIVE_NEWLINES:
            return "deep"

        return FALLBACK_TIER
    except Exception:
        return FALLBACK_TIER


def thinking_config(level: Optional[str]) -> Optional[types.ThinkingConfig]:
    """Mirrors matcha_work_ai's own mapping (services/matcha_work/
    matcha_work_ai/provider.py): `None` omits ThinkingConfig entirely (today's
    default behavior, unchanged for the `standard` tier); `"none"` sets an
    explicit zero budget; anything else is a `thinking_level`."""
    if level is None:
        return None
    if level == "none":
        return types.ThinkingConfig(thinking_budget=0)
    return types.ThinkingConfig(thinking_level=level)
