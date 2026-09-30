"""Comparing things to buy: the picks contract agent cards introduced."""
from __future__ import annotations

from typing import Any

from ..context import RunState
from ..registry import Ability

_PROMPT = """Choosing something to buy:
- Compare real options against the criteria that matter for the request; say what they are.
- Prefer primary pages (the brand, a major retailer) for prices and buy links, and independent reviews for quality claims.
- Review quotes must be verbatim excerpts from a page you saw, at most 280 characters.
- Images: only image URLs fetch_page reported, paired with the page_url they came from.
- Researching is not buying: give the best option with its exact price and buy link. Never ask for card details.
- Only buy when the person asks you to and a buying tool is offered; without one, say they can finish at the buy link."""


def _picks_block() -> dict[str, Any]:
    from app.matcha.services.matcha_work.agent_card.schema import RESULT_SCHEMA

    properties = RESULT_SCHEMA["properties"]
    return {
        "type": "object",
        "description": "A recommendation: one top pick and up to four alternatives.",
        "properties": {
            "criteria": properties["criteria"],
            "top_pick": properties["top_pick"],
            "alternatives": properties["alternatives"],
        },
    }


def gate_block(block_type: str, raw: Any, state: RunState) -> tuple[dict | None, list[str]]:
    from app.matcha.services.matcha_work.agent_card import schema

    if not isinstance(raw, dict):
        return None, ["Dropped a picks block: not an object"]
    gate = schema.Gate(state.provenance)
    top_pick = schema.gate_pick(raw.get("top_pick"), gate) if raw.get("top_pick") else None
    alternatives = [
        p for p in (schema.gate_pick(a, gate) for a in (raw.get("alternatives") or []) if isinstance(a, dict)) if p
    ][: schema.MAX_ALTERNATIVES]
    if top_pick is None and not alternatives:
        return None, gate.warnings
    return {
        "type": "picks",
        "criteria": schema.gate_criteria(raw.get("criteria")),
        "top_pick": top_pick,
        "alternatives": alternatives,
    }, gate.warnings


def build() -> Ability:
    return Ability(
        key="shopping",
        label="Shopping research",
        tools=(),
        prompt_block=lambda _ctx: _PROMPT,
        block_schemas={"picks": _picks_block()},
        gate=gate_block,
    )
