"""Rich text: what the editor types and the page shows.

A story's paragraphs are kept as a small document (`rt`), the JSON the
dashboard's text editor (ProseMirror, through Tiptap) works in:

    {"type": "doc", "content": [
        {"type": "paragraph", "content": [{"type": "text", "text": "Low tide", "marks": [{"type": "bold"}]}]},
        {"type": "heading", "attrs": {"level": 2}, "content": [...]},
        {"type": "bulletList", "content": [{"type": "listItem", "content": [{"type": "paragraph", ...}]}]},
    ]}

Everything is checked here before it is stored (`normalize_rt`): only the
nodes and marks below survive, a link keeps an http(s)/mailto address only,
unknown blocks keep their words as a paragraph, and the text is capped. The
page renders it with `render_rt` (escaped text, no attributes but a link's).
The Markdown a block also keeps (`md`, for emails, feeds, word counts and the
iOS app's `body`) is derived from it (`rt_to_md`), and old Markdown-only text
becomes a document (`md_to_rt`) for the editor.

`server/tests/cappe/fixtures/magazine_rt_cases.json` pins `render_rt` and
`rt_to_md` here, and the client checks its editor reads the same HTML back
into the same document.
"""
from __future__ import annotations

import re
from html import escape
from html.parser import HTMLParser
from typing import Any, Optional

from .richtext import render_md

BLOCKS = ("paragraph", "heading", "blockquote", "bulletList", "orderedList")
# In the editor's own order (its schema), so a document compares equal on both sides.
MARKS = ("link", "bold", "italic", "strike", "underline")
LINK_SCHEMES = ("http://", "https://", "mailto:")
MAX_DEPTH = 6
MAX_NODES = 6_000
MAX_HREF = 2_000
LINK_REL = "nofollow ugc noopener"


class RtError(ValueError):
    """Text the editor can't keep as given; the message is for the owner."""


def empty_rt() -> dict:
    return {"type": "doc", "content": [{"type": "paragraph"}]}


# ── checking ─────────────────────────────────────────────────────────────────

class _Budget:
    def __init__(self, chars: int):
        self.chars = chars
        self.nodes = 0

    def node(self) -> None:
        self.nodes += 1
        if self.nodes > MAX_NODES:
            raise RtError("This text is too long to keep. Split it into two blocks.")


def _href(value: Any) -> Optional[str]:
    href = value.strip() if isinstance(value, str) else ""
    if not href or len(href) > MAX_HREF or not href.lower().startswith(LINK_SCHEMES):
        return None
    if any(ord(c) < 0x20 for c in href):
        return None
    return href


def _marks(raw: Any) -> list[dict]:
    out: list[dict] = []
    seen: set[str] = set()
    for m in raw if isinstance(raw, list) else []:
        kind = m.get("type") if isinstance(m, dict) else None
        if kind not in MARKS or kind in seen:
            continue
        if kind == "link":
            href = _href((m.get("attrs") or {}).get("href") if isinstance(m.get("attrs"), dict) else None)
            if not href:
                continue
            out.append({"type": "link", "attrs": {"href": href}})
        else:
            out.append({"type": kind})
        seen.add(kind)
    # One order, so the same words always come out the same.
    return sorted(out, key=lambda m: MARKS.index(m["type"]))


def _inline(raw: Any, budget: _Budget, depth: int = 0) -> list[dict]:
    if depth > MAX_DEPTH:
        raise RtError("Lists and quotes can only go so deep.")
    out: list[dict] = []
    for n in raw if isinstance(raw, list) else []:
        if not isinstance(n, dict):
            continue
        kind = n.get("type")
        if kind == "hardBreak":
            budget.node()
            out.append({"type": "hardBreak"})
        elif kind == "text":
            text = n.get("text") if isinstance(n.get("text"), str) else ""
            text = text.replace("\r", "")[: max(budget.chars, 0)]
            if not text:
                continue
            budget.chars -= len(text)
            budget.node()
            node: dict = {"type": "text", "text": text}
            marks = _marks(n.get("marks"))
            if marks:
                node["marks"] = marks
            # Neighbours with the same marks are one run.
            if out and out[-1].get("type") == "text" and out[-1].get("marks") == node.get("marks"):
                out[-1]["text"] += text
            else:
                out.append(node)
        elif isinstance(n.get("content"), list):
            out += _inline(n["content"], budget, depth + 1)  # an unknown wrapper keeps its words
    return out


def _flatten(n: dict, budget: _Budget) -> list[dict]:
    """The words of a block we don't keep, as paragraphs."""
    content = n.get("content") if isinstance(n.get("content"), list) else []
    if any(isinstance(c, dict) and c.get("type") in BLOCKS + ("listItem",) for c in content):
        return _blocks(content, budget, 1)
    inline = _inline(content, budget)
    return [{"type": "paragraph", "content": inline}] if inline else []


def _block(n: Any, budget: _Budget, depth: int) -> list[dict]:
    if not isinstance(n, dict):
        return []
    if depth > MAX_DEPTH:
        raise RtError("Lists and quotes can only go so deep.")
    budget.node()
    kind = n.get("type")
    content = n.get("content")
    if kind == "paragraph":
        inline = _inline(content, budget)
        return [{"type": "paragraph", "content": inline} if inline else {"type": "paragraph"}]
    if kind == "heading":
        attrs = n.get("attrs") if isinstance(n.get("attrs"), dict) else {}
        level = 3 if attrs.get("level") in (3, 4, 5, 6) else 2
        inline = _inline(content, budget)
        return [{"type": "heading", "attrs": {"level": level}, **({"content": inline} if inline else {})}]
    if kind == "blockquote":
        inner = _blocks(content, budget, depth + 1, quote=True)
        return [{"type": "blockquote", "content": inner}] if inner else []
    if kind in ("bulletList", "orderedList"):
        items = []
        for item in content if isinstance(content, list) else []:
            if not isinstance(item, dict):
                continue
            budget.node()
            inner = _blocks(item.get("content"), budget, depth + 1, in_item=True)
            if inner:
                items.append({"type": "listItem", "content": inner})
        if not items:
            return []
        node: dict = {"type": kind, "content": items}
        if kind == "orderedList":
            attrs = n.get("attrs") if isinstance(n.get("attrs"), dict) else {}
            start = attrs.get("start")
            node["attrs"] = {"start": start if isinstance(start, int) and 1 <= start <= 9999 else 1}
        return [node]
    return _flatten(n, budget)


def _blocks(raw: Any, budget: _Budget, depth: int, *, quote: bool = False, in_item: bool = False) -> list[dict]:
    out: list[dict] = []
    for n in raw if isinstance(raw, list) else []:
        for b in _block(n, budget, depth):
            # A list item opens with a paragraph; a quote holds no headings.
            if in_item and not out and b["type"] != "paragraph":
                out.append({"type": "paragraph"})
            if quote and b["type"] == "heading":
                b = {"type": "paragraph", **({"content": b["content"]} if b.get("content") else {})}
            out.append(b)
    return out


def normalize_rt(raw: Any, *, max_chars: int = 20_000) -> Optional[dict]:
    """The storable document, or None when `raw` isn't one."""
    if not isinstance(raw, dict) or raw.get("type") != "doc":
        return None
    content = _blocks(raw.get("content"), _Budget(max_chars), 0)
    return {"type": "doc", "content": content or [{"type": "paragraph"}]}


# ── the page ─────────────────────────────────────────────────────────────────

_TAGS = {"bold": "strong", "italic": "em", "underline": "u", "strike": "s"}


def _render_inline(nodes: list[dict]) -> str:
    out = []
    for n in nodes:
        if n["type"] == "hardBreak":
            out.append("<br>")
            continue
        html = escape(n["text"], quote=False)
        for m in reversed(n.get("marks") or []):
            if m["type"] == "link":
                html = f'<a rel="{LINK_REL}" href="{escape(m["attrs"]["href"], quote=True)}">{html}</a>'
            else:
                tag = _TAGS[m["type"]]
                html = f"<{tag}>{html}</{tag}>"
        out.append(html)
    return "".join(out)


def _render_block(b: dict) -> str:
    kind = b["type"]
    if kind == "paragraph":
        return f"<p>{_render_inline(b.get('content') or [])}</p>"
    if kind == "heading":
        tag = f"h{b['attrs']['level']}"
        return f"<{tag}>{_render_inline(b.get('content') or [])}</{tag}>"
    if kind == "blockquote":
        return f"<blockquote>{''.join(_render_block(c) for c in b['content'])}</blockquote>"
    tag = "ul" if kind == "bulletList" else "ol"
    start = (b.get("attrs") or {}).get("start", 1)
    attr = f' start="{start}"' if tag == "ol" and start != 1 else ""
    items = "".join(f"<li>{''.join(_render_block(c) for c in item['content'])}</li>" for item in b["content"])
    return f"<{tag}{attr}>{items}</{tag}>"


def render_rt(rt: Optional[dict]) -> str:
    """Safe HTML for a checked document ("" when it has no words)."""
    if not rt or not rt_has_words(rt):
        return ""
    return "".join(_render_block(b) for b in rt.get("content") or [])


def rt_has_words(rt: Optional[dict]) -> bool:
    def walk(nodes: list) -> bool:
        return any(n.get("type") == "text" and n.get("text", "").strip() or walk(n.get("content") or [])
                   for n in nodes if isinstance(n, dict))
    return bool(rt) and walk(rt.get("content") or [])


# ── Markdown, both ways ──────────────────────────────────────────────────────

def _esc_md(text: str) -> str:
    return re.sub(r"([\\`*_\[\]])", r"\\\1", text.replace("\u00a0", " "))


def _esc_line_start(line: str) -> str:
    line = re.sub(r"^(\s*)(#{1,6})(\s|$)", r"\1\\\2\3", line)
    line = re.sub(r"^(\s*)>", r"\1\\>", line)
    line = re.sub(r"^(\s*)([-+])(\s)", r"\1\\\2\3", line)
    return re.sub(r"^(\s*)(\d+)\.(\s)", r"\1\2\\.\3", line)


def _wrap(inner: str, mark: str) -> str:
    m = re.match(r"^(\s*)(.*?)(\s*)$", inner, re.S)
    return f"{m[1]}{mark}{m[2]}{mark}{m[3]}" if m and m[2] else inner


def _md_inline(nodes: list[dict]) -> str:
    out = []
    for n in nodes:
        if n["type"] == "hardBreak":
            out.append("  \n")
            continue
        md = _esc_md(n["text"].replace("\n", " "))
        kinds = [m["type"] for m in n.get("marks") or []]
        if "italic" in kinds:
            md = _wrap(md, "*")
        if "bold" in kinds:
            md = _wrap(md, "**")
        link = next((m for m in n.get("marks") or [] if m["type"] == "link"), None)
        if link and md.strip():
            href = link["attrs"]["href"].replace("(", "%28").replace(")", "%29").replace(" ", "%20")
            md = f"[{md}]({href})"
        out.append(md)
    text = "".join(out).rstrip()
    return "\n".join(_esc_line_start(line) for line in text.split("\n")).strip()


def _md_block(b: dict) -> str:
    kind = b["type"]
    if kind == "paragraph":
        return _md_inline(b.get("content") or [])
    if kind == "heading":
        words = _md_inline(b.get("content") or []).replace("\n", " ")
        return f"{'#' * b['attrs']['level']} {words}" if words else ""
    if kind == "blockquote":
        inner = "\n\n".join(filter(None, (_md_block(c) for c in b["content"])))
        return "\n".join(f"> {line}" if line else ">" for line in inner.split("\n")) if inner else ""
    lines = []
    start = (b.get("attrs") or {}).get("start", 1)
    for i, item in enumerate(b["content"]):
        words = " ".join(filter(None, (_md_block(c).replace("\n", " ") for c in item["content"]))).strip()
        if words:
            lines.append(f"{start + i}. {words}" if kind == "orderedList" else f"- {words}")
    return "\n".join(lines)


def rt_to_md(rt: Optional[dict]) -> str:
    """The Markdown kept beside a document: what emails, feeds, word counts and
    the iOS app read. Underline and strike-through have no Markdown and are
    dropped; everything typed reads as typed."""
    if not rt:
        return ""
    return "\n\n".join(filter(None, (_md_block(b) for b in rt.get("content") or [])))


class _ToRt(HTMLParser):
    """`render_md`'s allowlisted HTML read back into a document."""

    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.root: dict = {"type": "doc", "content": []}
        self.stack: list[dict] = [self.root]
        self.marks: list[dict] = []

    def _open(self, node: dict) -> None:
        self.stack[-1].setdefault("content", []).append(node)
        self.stack.append(node)

    def handle_starttag(self, tag: str, attrs: list[tuple[str, Optional[str]]]) -> None:
        if tag == "p":
            self._open({"type": "paragraph"})
        elif tag in ("h2", "h3"):
            self._open({"type": "heading", "attrs": {"level": int(tag[1])}})
        elif tag == "blockquote":
            self._open({"type": "blockquote"})
        elif tag == "ul":
            self._open({"type": "bulletList"})
        elif tag == "ol":
            start = dict(attrs).get("start")
            self._open({"type": "orderedList", "attrs": {"start": int(start) if start and start.isdigit() else 1}})
        elif tag == "li":
            self._open({"type": "listItem"})
        elif tag == "br":
            self._inline({"type": "hardBreak"})
        elif tag in ("strong", "em"):
            self.marks.append({"type": "bold" if tag == "strong" else "italic"})
        elif tag == "a":
            self.marks.append({"type": "link", "attrs": {"href": dict(attrs).get("href") or ""}})

    def handle_endtag(self, tag: str) -> None:
        if tag in ("strong", "em", "a"):
            want = {"strong": "bold", "em": "italic", "a": "link"}[tag]
            for i in range(len(self.marks) - 1, -1, -1):
                if self.marks[i]["type"] == want:
                    del self.marks[i]
                    break
        elif tag in ("p", "h2", "h3", "blockquote", "ul", "ol", "li") and len(self.stack) > 1:
            self.stack.pop()

    def _inline(self, node: dict) -> None:
        top = self.stack[-1]
        if top["type"] in ("doc", "blockquote", "listItem"):
            # Loose words (a tight list item's): a paragraph of their own.
            if not (top.get("content") and top["content"][-1].get("type") == "paragraph" and top["content"][-1].get("_loose")):
                top.setdefault("content", []).append({"type": "paragraph", "_loose": True})
            top = top["content"][-1]
        elif top["type"] in ("bulletList", "orderedList"):
            return
        top.setdefault("content", []).append(node)

    def handle_data(self, data: str) -> None:
        if not data.strip() and self.stack[-1]["type"] not in ("paragraph", "heading"):
            return
        text = data.replace("\n", " ") if self.stack[-1]["type"] in ("paragraph", "heading") else data.strip()
        node: dict = {"type": "text", "text": text}
        if self.marks:
            node["marks"] = [dict(m) for m in self.marks]
        self._inline(node)


def md_to_rt(md: Optional[str]) -> dict:
    """A document for text kept only as Markdown (stories written before the
    rich editor, or Assist's suggestions)."""
    parser = _ToRt()
    parser.feed(render_md(md or ""))
    parser.close()
    # The newline between a line's words and a <br> in render_md's output.
    def tidy(nodes: list) -> None:
        for n in nodes:
            n.pop("_loose", None)
            content = n.get("content") or []
            for i, c in enumerate(content):
                if c.get("type") == "text" and i and content[i - 1].get("type") == "hardBreak":
                    c["text"] = c["text"].lstrip()
            tidy(content)
    tidy(parser.root["content"])
    return normalize_rt(parser.root) or empty_rt()
