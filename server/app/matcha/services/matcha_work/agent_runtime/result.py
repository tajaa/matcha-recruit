"""`agent_result.v2`: a headline, a summary and typed blocks.

v1 (the agent-card page) is one fixed shape built around product picks. v2 is
the same idea opened up: the answer is a list of blocks, and each block type
belongs to the ability that can vouch for it. `picks` and `sections` reuse the
card's provenance gates unchanged; an `emails` block is rebuilt from the
messages the run actually read, not from what the model wrote down.

A block type no enabled ability owns is dropped. Card runs keep storing v1;
`read_result` gives either version back in the v2 shape.
"""
from __future__ import annotations

from typing import Any, Sequence

from .context import RunState
from .registry import Ability, AgentTool

SCHEMA_VERSION = "agent_result.v2"
MAX_BLOCKS = 8
_CONFIDENCE = {"high", "medium", "low"}


def _text(value: Any, limit: int) -> str:
    return str(value or "").strip()[:limit] if value is not None else ""


def block_owners(abilities: Sequence[Ability]) -> dict[str, Ability]:
    return {block: ability for ability in abilities for block in ability.block_schemas}


def finish_tool(abilities: Sequence[Ability]) -> AgentTool:
    owners = block_owners(abilities)
    properties: dict[str, Any] = {
        "type": {"type": "string", "enum": sorted(owners) or ["none"]},
    }
    kinds = []
    for block, ability in owners.items():
        schema = ability.block_schemas[block]
        kinds.append(f"`{block}`: {schema.get('description', '')}".strip())
        for key, value in (schema.get("properties") or {}).items():
            properties.setdefault(key, value)
    return AgentTool(
        name="finish",
        effect="finish",
        description=(
            "Finish with the answer. Put what the person needs to know in `headline` and "
            "`summary`; add blocks for anything structured. Anything the run did not "
            "actually see or do is removed."
        ),
        parameters={
            "type": "object",
            "properties": {
                "headline": {"type": "string", "description": "One line answer"},
                "summary": {"type": "string", "description": "2-4 sentences, plain text"},
                "confidence": {"type": "string", "enum": sorted(_CONFIDENCE)},
                "caveats": {"type": "array", "items": {"type": "string"}},
                "blocks": {
                    "type": "array",
                    "description": "Structured parts of the answer. Block types: " + "; ".join(kinds),
                    "items": {"type": "object", "properties": properties, "required": ["type"]},
                },
            },
            "required": ["headline", "summary"],
        },
        step_kind="finish",
    )


def normalize(args: Any, state: RunState, abilities: Sequence[Ability]) -> tuple[dict, list[str]]:
    """Coerce and gate a v2 `finish` payload. ValueError => the loop asks once for a repair."""
    if not isinstance(args, dict):
        raise ValueError("finish takes an object")
    headline = _text(args.get("headline"), 200)
    summary = _text(args.get("summary"), 1200)
    if not headline or not summary:
        raise ValueError("headline and summary are required")
    owners = block_owners(abilities)
    warnings: list[str] = []
    blocks: list[dict] = []
    seen: set[str] = set()
    raw_blocks = args.get("blocks") if isinstance(args.get("blocks"), list) else []
    for raw in raw_blocks:
        if not isinstance(raw, dict):
            continue
        kind = str(raw.get("type") or "")
        owner = owners.get(kind)
        if owner is None or owner.gate is None:
            warnings.append(f"Dropped a {kind or 'untyped'} block: nothing enabled in this run provides it")
            continue
        if kind in seen:
            warnings.append(f"Dropped a second {kind} block")
            continue
        block, block_warnings = owner.gate(kind, raw, state)
        warnings.extend(block_warnings)
        if block is not None:
            seen.add(kind)
            blocks.append({**block, "type": kind})
    for ability in abilities:
        if ability.auto_blocks is None:
            continue
        for block in ability.auto_blocks(state):
            kind = block.get("type")
            if kind in ability.block_schemas and kind not in seen:
                seen.add(kind)
                blocks.append(block)
    if len(blocks) > MAX_BLOCKS:
        warnings.append(f"Trimmed blocks to {MAX_BLOCKS}")
    confidence = args.get("confidence")
    caveats = args.get("caveats") if isinstance(args.get("caveats"), list) else []
    return {
        "schema": SCHEMA_VERSION,
        "headline": headline,
        "summary": summary,
        "blocks": blocks[:MAX_BLOCKS],
        "caveats": [c for c in (_text(x, 300) for x in caveats) if c][:5],
        "confidence": confidence if confidence in _CONFIDENCE else "low",
    }, warnings


def read_result(stored: Any) -> dict | None:
    """A stored result in the v2 shape, whichever version wrote it."""
    if not isinstance(stored, dict):
        return None
    if stored.get("schema") == SCHEMA_VERSION:
        return stored
    blocks: list[dict] = []
    if stored.get("top_pick") or stored.get("alternatives"):
        blocks.append({
            "type": "picks",
            "criteria": stored.get("criteria") or [],
            "top_pick": stored.get("top_pick"),
            "alternatives": stored.get("alternatives") or [],
        })
    if stored.get("flights"):
        blocks.append({"type": "flights", "flights": stored["flights"]})
    if stored.get("sections"):
        blocks.append({"type": "sections", "sections": stored["sections"]})
    if stored.get("sources"):
        blocks.append({"type": "sources", "sources": stored["sources"]})
    return {
        "schema": SCHEMA_VERSION,
        "headline": stored.get("headline") or "",
        "summary": stored.get("summary") or "",
        "blocks": blocks,
        "caveats": stored.get("caveats") or [],
        "confidence": stored.get("confidence") or "low",
        "warnings": stored.get("warnings") or [],
    }


def picks_block(result: dict) -> dict | None:
    for block in result.get("blocks") or []:
        if block.get("type") == "picks":
            return block
    return None


def chat_view(result: dict) -> dict:
    """What the chat card carries. Bounded: a chat message is not a page."""
    from app.matcha.services.matcha_work.agent_card.chat_flow import _http_url, _pick_view, _short, flights_view

    blocks: list[dict] = []
    for block in result.get("blocks") or []:
        kind = block.get("type")
        if kind == "picks":
            top = block.get("top_pick")
            blocks.append({
                "type": "picks",
                "top_pick": _pick_view(top, full=True) if top else None,
                "alternatives": [_pick_view(p, full=False) for p in (block.get("alternatives") or [])[:3]],
            })
        elif kind == "sections":
            blocks.append({
                "type": "sections",
                "sections": [
                    {"heading": _short(s.get("heading") or "", 120), "body_md": (s.get("body_md") or "")[:1500]}
                    for s in (block.get("sections") or [])[:4]
                ],
            })
        elif kind == "flights":
            # The same compact rows the agent-card chat card shows.
            view = flights_view(block.get("flights"))
            if view:
                blocks.append({"type": "flights", "flights": view})
        elif kind == "sources":
            sources = [
                {"title": _short(s.get("title") or "", 80), "url": _http_url(s.get("url"))}
                for s in (block.get("sources") or [])[:6]
            ]
            blocks.append({"type": "sources", "sources": [s for s in sources if s["url"]]})
        else:
            # Server-authored or rebuilt from the run's own session: already bounded.
            blocks.append(block)
    return {
        "schema": SCHEMA_VERSION,
        "headline": _short(result.get("headline") or "", 200),
        "summary": _short(result.get("summary") or "", 600),
        "blocks": blocks,
        "caveats": [_short(c, 200) for c in (result.get("caveats") or [])[:3]],
        "confidence": result.get("confidence"),
    }


def text_fallback(result: dict) -> str:
    """Plain text for notifications and older apps. No raw URLs."""
    headline = (result.get("headline") or "").strip()
    summary = (result.get("summary") or "").strip()
    return f"{headline}\n\n{summary}".strip()[:3500] or "Done."
