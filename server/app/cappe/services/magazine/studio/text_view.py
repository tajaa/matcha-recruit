"""A paged story read as running text: its Text view.

`text_blocks(doc)` walks the pages in order and, on each, what sits on it
from the top down: a text frame gives the paragraphs that start in it (a
thread continued on page 5 is read on page 5), a picture gives a photo. The
result is the block story vocabulary (`story_schema`), so everything that
reads block stories reads a paged one without knowing: the Text view page
(`/stories/<slug>/text`), the feed, issue emails, the word count, the iOS
app's `body`, search and Assist (`pages.story_blocks`).

The story's first picture (the biggest on its first page) is its cover. A
subscriber's part starts where its pages do (`paywall_page`): a paywall
marker sits before what the first locked page holds.
"""
from __future__ import annotations

from typing import Optional

from ..rt import RtError, md_to_rt, normalize_rt, rt_to_md
from ..story_schema import MAX_BLOCKS
from .limits import CHAR_DEFAULTS, MAX_DOC_CHARS, PARA_DEFAULTS
from .schema import flow_frame, len16, para_text, slice16
from .identity import resolved_threads

_HEADING = {"h1": 2, "h2": 2, "h3": 3}


def cover_image(doc: dict) -> Optional[dict]:
    """The picture that stands for the story: the biggest on its first page
    (not a subject in front: that is its photo's cut-out)."""
    if not doc.get("pages"):
        return None
    first = doc["pages"][0]["id"]
    pics = [i for i in doc.get("items") or [] if i["kind"] == "image" and i.get("asset_id") and i["page"] == first
            and not i.get("hidden") and not i.get("cutout")]
    return max(pics, key=lambda i: i["w"] * i["h"], default=None)


def _inline(p: dict, *, heading: bool = False) -> list[dict]:
    """A paragraph's runs as rich text: heavy type is bold (not in a heading,
    which is), slanted is italic, underlined stays underlined; a line break
    is a hard break."""
    out: list[dict] = []
    for r in p.get("runs") or []:
        a = {**CHAR_DEFAULTS, **r}
        marks = []
        if a["wt"] >= 600 and not heading:
            marks.append({"type": "bold"})
        if a["it"]:
            marks.append({"type": "italic"})
        if a["u"]:
            marks.append({"type": "underline"})
        for k, piece in enumerate(a.get("t", "").split("\n")):
            if k:
                out.append({"type": "hardBreak"})
            if piece:
                out.append({"type": "text", "text": piece, **({"marks": marks} if marks else {})})
    return out


# The longest pull quote a quote block holds (story_schema._quote).
QUOTE_MAX = 400


def _node(p: dict) -> dict:
    role = p.get("role", PARA_DEFAULTS["role"])
    inline = _inline(p, heading=role in _HEADING)
    content = {"content": inline} if inline else {}
    if role in _HEADING:
        return {"type": "heading", "attrs": {"level": _HEADING[role]}, **content}
    if role == "quote":  # one too long for a quote block
        return {"type": "blockquote", "content": [{"type": "paragraph", **content}]}
    return {"type": "paragraph", **content}


def _text_block(nodes: list[dict], dropcap: bool = False) -> dict:
    raw = {"type": "doc", "content": nodes}
    try:
        doc = normalize_rt(raw, max_chars=MAX_DOC_CHARS) or md_to_rt("")
    except RtError:
        doc = md_to_rt("\n\n".join(_plain(n) for n in nodes))
    return {"type": "text", "md": rt_to_md(doc), "rt": doc, "dropcap": dropcap, "columns": 1, "variant": "body",
            "align": "left", "font": "body", "size": 1, "color": "", "leading": 0}


def _plain(node: dict) -> str:
    """A node's words (a quote's are inside its paragraph)."""
    return "".join(c.get("text", "") if c.get("type") == "text" else _plain(c) for c in node.get("content") or [])


def _slice(p: dict, start: int, end: Optional[int] = None) -> dict:
    """A paragraph's text from `start` to `end` (UTF-16), its runs cut to fit."""
    runs, at = [], 0
    for r in p.get("runs") or []:
        size = len16(r.get("t", ""))
        a, b = max(start, at), min(end if end is not None else at + size, at + size)
        if b > a:
            runs.append({**r, "t": slice16(r["t"], a - at, b - at) or ""})
        at += size
    return {**p, "runs": runs}


def _thread_paras(doc: dict, paywall: Optional[int]) -> dict[str, list[dict]]:
    """For each text frame, the paragraphs (of its thread) that start in it:
    what its lines hold, so text past the last line (overset, on no page) is
    never read. A paragraph that runs from a free page onto a subscriber's is
    cut where it crosses, its rest read on that page."""
    page_of = {p["id"]: n for n, p in enumerate(doc.get("pages") or [], start=1)}
    item_page = {i["id"]: page_of.get(i["page"], 0) for i in doc.get("items") or []}
    out: dict[str, list[dict]] = {}
    for t in doc.get("threads") or []:
        lines = (t.get("comp") or {}).get("lines") or []
        if not lines:
            out.setdefault(t["frames"][flow_frame(doc, t, paywall)], []).extend(t["paras"])
            continue
        by_para: dict[int, list[list]] = {}
        for ln in lines:
            by_para.setdefault(ln[1], []).append(ln)
        for index, mine in by_para.items():
            p = t["paras"][index]
            end = mine[-1][3] if index == lines[-1][1] else None
            locked = [ln for ln in mine if paywall and item_page.get(t["frames"][ln[0]], 0) >= paywall]
            first = t["frames"][mine[0][0]]
            if locked and locked[0] is not mine[0]:
                cut = locked[0][2]
                out.setdefault(first, []).append(_slice(p, 0, cut))
                out.setdefault(t["frames"][locked[0][0]], []).append(_slice(p, cut, end))
            else:
                out.setdefault(first, []).append(_slice(p, 0, end) if end is not None else p)
    return out


def _with_parents(doc: dict) -> dict:
    """Applied parent text is visible story content too. Give every instance
    local frame IDs so reading order, hidden frames and paywalls work exactly
    as they do before capture or after detaching the parent."""
    parents = {p["id"]: p for p in (doc.get("identity") or {}).get("parents", [])}
    if not parents:
        return doc
    items, threads = [], []
    for index, page in enumerate(doc.get("pages") or []):
        parent = parents.get(page.get("parent"))
        if not parent:
            continue
        prefix = f"parent:{index}:"
        ids = {i["id"]: prefix + i["id"] for i in parent["items"]}
        scale = min(doc["size"]["w"] / parent["size"]["w"], doc["size"]["h"] / parent["size"]["h"])
        items.extend({**i, "id": ids[i["id"]], "page": page["id"],
                      **{k: i[k] * scale for k in ("x", "y", "w", "h")}} for i in parent["items"])
        threads.extend({**t, "id": prefix + t["id"], "frames": [ids[f] for f in t["frames"]]} for t in parent["threads"])
    return {**doc, "items": items + (doc.get("items") or []), "threads": threads + (doc.get("threads") or [])}


def text_blocks(doc: dict, paywall: Optional[int] = None) -> list[dict]:
    """The story as blocks, in reading order (see the module). `paywall`: the
    first page for subscribers (`schema.paywall_from`), marked where its
    words start; None reads every page through (the story's word count and
    `body`)."""
    doc = _with_parents(doc)
    doc = {**doc, "threads": resolved_threads(doc)}
    blocks: list[dict] = []
    cover = cover_image(doc)
    if cover:
        blocks.append({"type": "cover", "asset_id": cover["asset_id"], "style": "stacked", "tone": "light",
                       "focal": {"x": round(cover["fx"]), "y": round(cover["fy"])}, "design": None})
    starts = _thread_paras(doc, paywall)
    nodes: list[dict] = []
    dropcap = [False]  # the block's first paragraph has a drop cap on its page

    def flush() -> None:
        if any(_plain(n) for n in nodes):
            blocks.append(_text_block(list(nodes), dropcap[0]))
        nodes.clear()
        dropcap[0] = False

    page_w = (doc.get("size") or {}).get("w") or 612
    for number, page in enumerate(doc.get("pages") or [], start=1):
        if paywall and number == paywall:
            flush()
            blocks.append({"type": "paywall"})
        on_page = sorted((i for i in doc.get("items") or [] if i["page"] == page["id"] and not i.get("hidden")),
                         key=lambda i: (round(i["y"]), round(i["x"])))
        for item in on_page:
            if item["kind"] == "text":
                for p in starts.get(item["id"], []):
                    text = para_text(p).strip()
                    # A pull quote longer than a quote block holds is read
                    # as a paragraph, whole, never cut short.
                    if p.get("role") == "quote" and len(text) <= QUOTE_MAX:
                        flush()
                        if text and len(blocks) < MAX_BLOCKS - 2:
                            blocks.append({"type": "quote", "text": text, "attribution": "", "style": "big"})
                    elif text:
                        if not nodes and p.get("dc", 0) >= 2:
                            dropcap[0] = True
                        nodes.append(_node(p))
            # The subject in front is its photo's cut-out: the photo is the picture.
            elif item["kind"] == "image" and item.get("asset_id") and item is not cover and not item.get("cutout"):
                if len(blocks) >= MAX_BLOCKS - 2:
                    continue
                flush()
                blocks.append({"type": "photo", "asset_id": item["asset_id"], "caption": item.get("caption") or "",
                               "size": "wide" if item["w"] >= 0.6 * page_w else "column", "border": "none",
                               "shape": "rect", "filter": "none", "crop": None, "design": None})
    flush()
    return blocks
