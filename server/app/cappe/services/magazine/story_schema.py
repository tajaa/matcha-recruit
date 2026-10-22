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

from .rt import RtError, md_to_rt, normalize_rt, rt_to_md

MAX_BLOCKS = 120
MAX_CONTENT_BYTES = 600_000  # a story's words are kept twice: the document and its Markdown
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

# How a text block reads: its type size, alignment and columns. The first of
# each list is the default.
TEXT_VARIANTS = ("body", "lede", "small", "statement")
ALIGNS = ("left", "center", "right", "justify")
# How a photo is framed: border, shape, colour, a crop, and words on it.
BORDERS = ("none", "thin", "thick", "mat")
SHAPES = ("rect", "rounded", "circle", "arch")
FILTERS = ("none", "bw", "sepia")
OVERLAY_SIZES = ("m", "s", "l", "xl")
OVERLAY_TONES = ("light", "dark")
OVERLAY_ALIGNS = ("center", "left", "right")
MAX_OVERLAYS = 8
MIN_CROP = 5  # percent of the picture's width or height


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


def _rich(b: dict, md_key: str, rt_key: str, limit: int) -> tuple[str, dict]:
    """A rich field's document and its Markdown. The document wins when it is
    sent (the editor's); Markdown alone (an old story, Assist, the iOS app)
    becomes a document."""
    try:
        doc = normalize_rt(b.get(rt_key), max_chars=limit)
    except RtError as exc:
        raise StoryError(str(exc)) from exc
    if doc is not None:
        return rt_to_md(doc)[:limit], doc
    md = _str(b.get(md_key), limit)
    return md, md_to_rt(md)


def _text(b: dict) -> dict:
    md, doc = _rich(b, "md", "rt", 20_000)
    return {
        "type": "text",
        "md": md,
        "rt": doc,
        "dropcap": bool(b.get("dropcap")),
        "columns": b.get("columns") if b.get("columns") in (2, 3) else 1,
        "variant": _choice(b.get("variant"), TEXT_VARIANTS),
        "align": _choice(b.get("align"), ALIGNS),
    }


def _crop(value: Any) -> Optional[dict]:
    """The part of the picture kept, in percent of its width and height, or
    None for the whole picture."""
    if not isinstance(value, dict):
        return None
    w = max(MIN_CROP, min(100, _pct(value.get("w"), 100)))
    h = max(MIN_CROP, min(100, _pct(value.get("h"), 100)))
    x = min(_pct(value.get("x"), 0), 100 - w)
    y = min(_pct(value.get("y"), 0), 100 - h)
    return None if (w, h) == (100, 100) else {"x": x, "y": y, "w": w, "h": h}


def _overlays(value: Any) -> list[dict]:
    """Words placed on the picture, each centred on its point (percent)."""
    items = value if isinstance(value, list) else []
    if len(items) > MAX_OVERLAYS:
        raise StoryError(f"A photo holds at most {MAX_OVERLAYS} pieces of text.")
    return [
        {"x": _pct(o.get("x")), "y": _pct(o.get("y")), "text": _str(o.get("text"), 300),
         "size": _choice(o.get("size"), OVERLAY_SIZES), "tone": _choice(o.get("tone"), OVERLAY_TONES),
         "box": bool(o.get("box")), "align": _choice(o.get("align"), OVERLAY_ALIGNS)}
        for o in items if isinstance(o, dict)
    ]


def _photo(b: dict) -> dict:
    return {
        "type": "photo",
        "asset_id": _asset_id(b.get("asset_id")),
        "caption": _str(b.get("caption"), 500),
        "size": _choice(b.get("size"), PHOTO_SIZES),
        "border": _choice(b.get("border"), BORDERS),
        "shape": _choice(b.get("shape"), SHAPES),
        "filter": _choice(b.get("filter"), FILTERS),
        "crop": _crop(b.get("crop")),
        "overlays": _overlays(b.get("overlays")),
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
    md, doc = _rich(b, "md", "rt", 4_000)
    return {"type": "sidebar", "title": _str(b.get("title"), 120), "md": md, "rt": doc}


def _qa_item(i: dict) -> dict:
    md, doc = _rich(i, "a_md", "a_rt", 5_000)
    return {"q": _str(i.get("q"), 500), "a_md": md, "a_rt": doc}


def _qa(b: dict) -> dict:
    items = b.get("items") if isinstance(b.get("items"), list) else []
    if len(items) > MAX_QA:
        raise StoryError(f"An interview block holds at most {MAX_QA} questions.")
    return {
        "type": "qa",
        "items": [_qa_item(i) for i in items if isinstance(i, dict)],
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
    # Through the normalizer, so a new story has every block's settings.
    return normalize_story({"blocks": starters.get(layout, starters["standard"])})


_WORD = re.compile(r"\w+(?:['’-]\w+)*")


def count_words(text: str) -> int:
    return len(_WORD.findall(text or ""))
