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
unknown blocks, and lists or quotes nested past `MAX_DEPTH`, keep their words
as paragraphs (nothing typed is dropped silently), and the text is capped. The
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

from .richtext import md_to_text, render_md

BLOCKS = ("paragraph", "heading", "blockquote", "bulletList", "orderedList")
# In the editor's own order (its schema), so a document compares equal on both sides.
MARKS = ("link", "bold", "italic", "strike", "underline")
LINK_SCHEMES = ("http://", "https://", "mailto:")
MAX_DEPTH = 6
# Enough for any 20,000 characters (a list of one-letter items is the most
# nodes per character); past it the owner is told, never cut short.
MAX_NODES = 30_000
MAX_HREF = 2_000
LINK_REL = "nofollow ugc noopener"
_HALVES = re.compile(r"[\ud800-\udfff]")


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


def _texts(raw: Any) -> list[dict]:
    """Every word and line break in `raw`, in order, however deeply it is
    wrapped (walked without recursion)."""
    out: list[dict] = []
    stack = list(reversed(raw)) if isinstance(raw, list) else []
    while stack:
        n = stack.pop()
        if not isinstance(n, dict):
            continue
        if n.get("type") in ("text", "hardBreak"):
            out.append(n)
        elif isinstance(n.get("content"), list):
            stack.extend(reversed(n["content"]))
    return out


def _inline(raw: Any, budget: _Budget, depth: int = 0) -> list[dict]:
    if depth > MAX_DEPTH:
        raw = _texts(raw)  # wrapped past any sense: the words, unwrapped
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
            # Half of a character (a lone surrogate) can't be printed on a page.
            text = _HALVES.sub("", text.replace("\r", ""))[: max(budget.chars, 0)]
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


def _flatten(n: dict, budget: _Budget, depth: int) -> list[dict]:
    """The words of a block we don't keep, as paragraphs."""
    content = n.get("content") if isinstance(n.get("content"), list) else []
    if any(isinstance(c, dict) and c.get("type") in BLOCKS + ("listItem",) for c in content):
        return _blocks(content, budget, depth + 1)
    inline = _inline(content, budget)
    return [{"type": "paragraph", "content": inline}] if inline else []


def _paragraphs(n: dict, budget: _Budget) -> list[dict]:
    """Blocks nested past `MAX_DEPTH`: each paragraph or heading in them a
    paragraph of its words (walked without recursion)."""
    groups: list[list[dict]] = [[]]
    stack: list[Any] = [n]
    while stack:
        node = stack.pop()
        if node is None:  # the end of a paragraph or heading
            groups.append([])
            continue
        if not isinstance(node, dict):
            continue
        if node.get("type") in ("text", "hardBreak"):
            groups[-1].append(node)
            continue
        if node.get("type") in ("paragraph", "heading"):
            groups.append([])
            stack.append(None)
        if isinstance(node.get("content"), list):
            stack.extend(reversed(node["content"]))
    out = []
    for words in groups:
        inline = _inline(words, budget)
        if inline:
            budget.node()
            out.append({"type": "paragraph", "content": inline})
    return out


def _block(n: Any, budget: _Budget, depth: int) -> list[dict]:
    if not isinstance(n, dict):
        return []
    if depth > MAX_DEPTH:
        return _paragraphs(n, budget)
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
    return _flatten(n, budget, depth)


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
    # Python-Markdown reads `#word` as a heading (no space needed), a line of
    # dashes as a rule or a heading's underline, and a line of `=` under
    # words as a heading. `=` can't be backslash-escaped; an underline must
    # start the line, so a space in front keeps it words.
    line = re.sub(r"^(\s*)#", r"\1\\#", line)
    line = re.sub(r"^(\s*)-(?=[\s-]*$)", r"\1\\-", line)
    line = re.sub(r"^(?=\s*=+\s*$)", " ", line)
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
    return _md_list(b)


# A list's own (unescaped) start: a nested list among an item's blocks
# (a paragraph that only looks like one is escaped, `\-` or `1\.`).
_LIST_START = re.compile(r"^(- |\d+\. )")


def _indent(md: str) -> str:
    return "\n".join(f"    {line}" if line else line for line in md.split("\n"))


def _md_list(b: dict) -> str:
    """A list, nesting and all: an item's later blocks are indented four
    spaces under it (a nested list right after its first line, a paragraph
    after a blank line), as `richtext.render_md` reads them; with such a
    paragraph anywhere the items are set apart by blank lines, else the next
    item would read as part of it."""
    items = [parts for parts in ([m for m in (_md_block(c) for c in item["content"]) if m] for item in b["content"]) if parts]
    loose = any(not _LIST_START.match(p) for parts in items for p in parts[1:])
    start = (b.get("attrs") or {}).get("start", 1)
    out = []
    for i, (first, *rest) in enumerate(items):
        marker = f"{start + i}." if b["type"] == "orderedList" else "-"
        tail = "".join(("\n" if _LIST_START.match(p) else "\n\n") + _indent(p) for p in rest)
        out.append(f"{marker} " + first.replace("\n", "\n    ") + tail)
    return ("\n\n" if loose else "\n").join(out)


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
        top = self.stack[-1]["type"]
        # A tight list item's words come straight in its <li>: their spaces
        # (around bold, between two marks) are the words' own; only the
        # paragraph's ends are trimmed, in md_to_rt.
        if not data.strip() and top not in ("paragraph", "heading", "listItem"):
            return
        text = data.replace("\n", " ") if top in ("paragraph", "heading", "listItem") else data.strip()
        node: dict = {"type": "text", "text": text}
        if self.marks:
            node["marks"] = [dict(m) for m in self.marks]
        self._inline(node)


def md_to_rt(md: Optional[str]) -> dict:
    """A document for text kept only as Markdown (stories written before the
    rich editor, or Assist's suggestions). Never fails: Markdown the editor
    couldn't hold in shape (more pieces than `MAX_NODES`) comes back as its
    paragraphs of plain words, so an old story always opens."""
    parser = _ToRt()
    parser.feed(render_md(md or ""))
    parser.close()
    # The newline between a line's words and a <br> in render_md's output
    # (walked without recursion: an old quote may be nested any depth).
    stack = [parser.root]
    while stack:
        n = stack.pop()
        if n.pop("_loose", None):
            texts = [c for c in n.get("content") or [] if c.get("type") == "text"]
            if texts:
                texts[0]["text"] = texts[0]["text"].lstrip()
                texts[-1]["text"] = texts[-1]["text"].rstrip()
        for c in n.get("content") or []:
            # Whitespace between a loose item's blocks made a paragraph of nothing.
            if c.get("_loose") and not any(t.get("type") != "text" or t.get("text", "").strip()
                                           for t in c.get("content") or []):
                c["_drop"] = True
        if n.get("content"):
            n["content"] = [c for c in n["content"] if not c.get("_drop")]
        content = n.get("content") or []
        for i, c in enumerate(content):
            if c.get("type") == "text" and i and content[i - 1].get("type") == "hardBreak":
                c["text"] = c["text"].lstrip()
        stack.extend(content)
    try:
        return normalize_rt(parser.root) or empty_rt()
    except RtError:
        words = [" ".join(p.split()) for p in re.split(r"\n\s*\n", md_to_text(md or ""))]
        doc = {"type": "doc", "content": [{"type": "paragraph", "content": [{"type": "text", "text": w}]} for w in words if w]}
        try:
            return normalize_rt(doc) or empty_rt()
        except RtError:
            return normalize_rt({"type": "doc", "content": [{"type": "paragraph", "content": [
                {"type": "text", "text": " ".join(words)}]}]}) or empty_rt()
