"""The story-block vocabulary and the five magazine layouts.

A story's `content` is `{"blocks": [...]}`. Every block is checked and
reshaped here before it is stored: unknown keys are dropped, enum fields fall
back to their default, lengths are capped, and pictures are referenced by
library `asset_id` only — never by URL — so a credit can't be left off or
typed in by hand (the renderer prints the asset's own).

A picture slot may be empty (`asset_id: null`) while a story is being made:
the editor shows "choose a picture" and the page leaves it out.

The client mirror is `client/src/cappe/magazine/storyBlocks.ts`;
`test_cappe_story_schema.py` keeps the two block lists equal.
"""
from __future__ import annotations

import json
import re
from typing import Any, Optional
from uuid import UUID

MAX_BLOCKS = 120
MAX_CONTENT_BYTES = 200_000
MAX_PHOTOS = 12
MAX_QA = 40

LAYOUTS: dict[str, str] = {
    "standard": "Standard",
    "cover_story": "Cover story",
    "photo_essay": "Photo essay",
    "interview": "Interview",
    "dispatch": "Dispatch",
    "lookbook": "Lookbook",
}

COVER_STYLES = ("overlay", "stacked", "split")
TONES = ("light", "dark")
PHOTO_SIZES = ("column", "wide", "full")
PHOTOS_LAYOUTS = ("pair", "trio", "grid", "mosaic")
QUOTE_STYLES = ("big", "side")

STORY_BLOCKS = ("cover", "text", "photo", "photos", "quote", "sidebar", "qa", "divider", "paywall")


class StoryError(ValueError):
    """The story content can't be stored as given; the message is for the owner."""


def _str(value: Any, limit: int) -> str:
    return str(value or "").strip()[:limit] if value is not None else ""


def _choice(value: Any, choices: tuple[str, ...]) -> str:
    return value if value in choices else choices[0]


def _asset_id(value: Any) -> Optional[str]:
    if value in (None, ""):
        return None
    try:
        return str(UUID(str(value)))
    except ValueError as exc:
        raise StoryError("A picture in this story isn't from your library.") from exc


def _pct(value: Any, default: int = 50) -> int:
    try:
        return max(0, min(100, int(value)))
    except (TypeError, ValueError):
        return default


def _cover(b: dict) -> dict:
    focal = b.get("focal") if isinstance(b.get("focal"), dict) else {}
    return {
        "type": "cover",
        "asset_id": _asset_id(b.get("asset_id")),
        "style": _choice(b.get("style"), COVER_STYLES),
        "tone": _choice(b.get("tone"), TONES),
        "focal": {"x": _pct(focal.get("x")), "y": _pct(focal.get("y"))},
    }


def _text(b: dict) -> dict:
    return {
        "type": "text",
        "md": _str(b.get("md"), 20_000),
        "dropcap": bool(b.get("dropcap")),
        "columns": 2 if b.get("columns") == 2 else 1,
    }


def _photo(b: dict) -> dict:
    return {
        "type": "photo",
        "asset_id": _asset_id(b.get("asset_id")),
        "caption": _str(b.get("caption"), 500),
        "size": _choice(b.get("size"), PHOTO_SIZES),
    }


def _photos(b: dict) -> dict:
    items = b.get("items") if isinstance(b.get("items"), list) else []
    if len(items) > MAX_PHOTOS:
        raise StoryError(f"A photo group holds at most {MAX_PHOTOS} pictures.")
    return {
        "type": "photos",
        "layout": _choice(b.get("layout"), PHOTOS_LAYOUTS),
        "items": [
            {"asset_id": _asset_id(i.get("asset_id")), "caption": _str(i.get("caption"), 300)}
            for i in items if isinstance(i, dict)
        ],
    }


def _quote(b: dict) -> dict:
    return {
        "type": "quote",
        "text": _str(b.get("text"), 400),
        "attribution": _str(b.get("attribution"), 120),
        "style": _choice(b.get("style"), QUOTE_STYLES),
    }


def _sidebar(b: dict) -> dict:
    return {"type": "sidebar", "title": _str(b.get("title"), 120), "md": _str(b.get("md"), 4_000)}


def _qa(b: dict) -> dict:
    items = b.get("items") if isinstance(b.get("items"), list) else []
    if len(items) > MAX_QA:
        raise StoryError(f"An interview block holds at most {MAX_QA} questions.")
    return {
        "type": "qa",
        "items": [{"q": _str(i.get("q"), 500), "a_md": _str(i.get("a_md"), 5_000)}
                  for i in items if isinstance(i, dict)],
    }


_SHAPERS = {
    "cover": _cover, "text": _text, "photo": _photo, "photos": _photos, "quote": _quote,
    "sidebar": _sidebar, "qa": _qa,
    "divider": lambda _b: {"type": "divider"},
    "paywall": lambda _b: {"type": "paywall"},
}
assert set(_SHAPERS) == set(STORY_BLOCKS)


def normalize_story(content: Any) -> dict:
    """The storable form of `content` (`{"blocks": [...]}`). Raises
    `StoryError` for anything the owner has to fix."""
    if content in (None, {}):
        return {"blocks": []}
    if not isinstance(content, dict) or not isinstance(content.get("blocks"), list):
        raise StoryError("A story is a list of blocks.")
    raw = content["blocks"]
    if len(raw) > MAX_BLOCKS:
        raise StoryError(f"A story holds at most {MAX_BLOCKS} blocks.")
    blocks = []
    for i, b in enumerate(raw):
        kind = b.get("type") if isinstance(b, dict) else None
        if kind not in _SHAPERS:
            raise StoryError(f"Block {i + 1} isn't a kind of block a story can have.")
        if kind == "cover" and i != 0:
            raise StoryError("The cover has to be the first block.")
        blocks.append(_SHAPERS[kind](b))
    if sum(1 for b in blocks if b["type"] == "paywall") > 1:
        raise StoryError("A story has one place where the paid part starts.")
    out = {"blocks": blocks}
    if len(json.dumps(out)) > MAX_CONTENT_BYTES:
        raise StoryError("This story is too long to save. Split it into two.")
    return out


def normalize_layout(value: Any) -> str:
    return value if value in LAYOUTS else "standard"


def referenced_asset_ids(content: dict, cover_asset_id: Any = None) -> set[str]:
    """Every library picture the story shows (its cover included)."""
    ids: set[str] = set()
    if cover_asset_id:
        ids.add(str(cover_asset_id))
    for b in content.get("blocks") or []:
        if b.get("asset_id"):
            ids.add(b["asset_id"])
        for item in b.get("items") or []:
            if isinstance(item, dict) and item.get("asset_id"):
                ids.add(item["asset_id"])
    return ids


def cover_block(content: dict) -> Optional[dict]:
    blocks = content.get("blocks") or []
    return blocks[0] if blocks and blocks[0].get("type") == "cover" else None


def starter_content(layout: str) -> dict:
    """The block list a new story of `layout` starts with — slots to fill."""
    cover = lambda style, tone="light": {"type": "cover", "asset_id": None, "style": style, "tone": tone,  # noqa: E731
                                         "focal": {"x": 50, "y": 50}}
    text = lambda dropcap=False: {"type": "text", "md": "", "dropcap": dropcap, "columns": 1}  # noqa: E731
    photo = lambda size: {"type": "photo", "asset_id": None, "caption": "", "size": size}  # noqa: E731
    photos = lambda layout_, n: {"type": "photos", "layout": layout_,  # noqa: E731
                                 "items": [{"asset_id": None, "caption": ""} for _ in range(n)]}
    quote = {"type": "quote", "text": "", "attribution": "", "style": "big"}
    starters = {
        "standard": [cover("stacked"), text(True)],
        "cover_story": [cover("overlay"), text(True), quote, photo("full"), text()],
        "photo_essay": [cover("overlay", "dark"), photo("full"), text(), photos("pair", 2), photo("full"), text()],
        "interview": [cover("split"), text(True), {"type": "qa", "items": [{"q": "", "a_md": ""}]}, photo("wide")],
        "dispatch": [cover("stacked"), text(True), {"type": "sidebar", "title": "", "md": ""}, photo("wide"), text()],
        "lookbook": [cover("overlay"), photos("mosaic", 6), text(), photos("trio", 3)],
    }
    return {"blocks": starters.get(layout, starters["standard"])}


_WORD = re.compile(r"\w+(?:['’-]\w+)*")


def count_words(text: str) -> int:
    return len(_WORD.findall(text or ""))
