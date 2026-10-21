"""Constrained Markdown → safe HTML for story text.

Story text is typed by the owner (or drafted by Claude and edited by them), so
it is stored as Markdown and rendered here, never as HTML:

  * raw HTML is not allowed at all — every `<` is escaped before Markdown sees
    it, so `<script>` or `<img onerror>` is text on the page;
  * Markdown's output then goes through a strict allowlist (paragraphs,
    emphasis, links, h2/h3, lists, block quotes): any other tag is dropped and
    its text kept; `#` headings become h2 and `####`… h3 (the page owns h1);
    inline images are dropped (pictures are blocks, with credits); links keep
    only http(s)/mailto `href`s and get `rel="nofollow ugc noopener"`.

The allowlist is our own `html.parser` walk rather than bleach: the input is
Markdown's own well-formed output, so the job is small, and the test suite
stubs `bleach` in several places.
"""
from __future__ import annotations

import re
from html import escape
from html.parser import HTMLParser

import markdown

ALLOWED_TAGS = frozenset({"p", "br", "strong", "em", "a", "h2", "h3", "ul", "ol", "li", "blockquote"})
# HTML void elements never get an end tag, so they are never "open".
_VOID = frozenset({"br", "hr", "img", "input", "area", "base", "col", "embed", "link", "meta", "param",
                   "source", "track", "wbr"})
_RENAME = {"h1": "h2", "h4": "h3", "h5": "h3", "h6": "h3"}
_LINK_SCHEMES = ("http://", "https://", "mailto:")
MAX_MD = 20_000


class _Allowlist(HTMLParser):
    """Re-emits only the allowed tags, with escaped text and vetted links."""

    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.out: list[str] = []
        # (the tag as parsed, the name emitted or None when dropped), per open tag.
        self.open: list[tuple[str, str | None]] = []

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        name = _RENAME.get(tag, tag)
        allowed = name in ALLOWED_TAGS
        if allowed:
            self.out.append(_link(dict(attrs)) if name == "a" else f"<{name}>")
        if tag not in _VOID:
            self.open.append((tag, name if allowed else None))

    def handle_startendtag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        name = _RENAME.get(tag, tag)
        if name in ALLOWED_TAGS:
            self.out.append(f"<{name}>")

    def handle_endtag(self, tag: str) -> None:
        if not any(t == tag for t, _ in self.open):
            return
        # Close back to the matching tag; anything left open inside it closes too.
        while self.open:
            opened, name = self.open.pop()
            if name:
                self.out.append(f"</{name}>")
            if opened == tag:
                break

    def handle_data(self, data: str) -> None:
        self.out.append(escape(data, quote=False))

    def result(self) -> str:
        while self.open:  # markdown's output is well formed; this is belt and braces
            _opened, name = self.open.pop()
            if name:
                self.out.append(f"</{name}>")
        return "".join(self.out)


def _link(attrs: dict[str, str | None]) -> str:
    parts = ['<a rel="nofollow ugc noopener"']
    href = (attrs.get("href") or "").strip()
    if href.lower().startswith(_LINK_SCHEMES) and not any(ord(c) < 0x20 for c in href):
        parts.append(f'href="{escape(href, quote=True)}"')
    title = (attrs.get("title") or "").strip()
    if title:
        parts.append(f'title="{escape(title, quote=True)}"')
    return " ".join(parts) + ">"


def render_md(source: str | None) -> str:
    """Safe HTML for a block of story text ("" for empty input)."""
    text = (source or "")[:MAX_MD]
    if not text.strip():
        return ""
    html = markdown.markdown(text.replace("<", "&lt;"), output_format="html")
    parser = _Allowlist()
    parser.feed(html)
    parser.close()
    return parser.result()


_MD_MARKS = re.compile(r"(\*\*|__|\*|_|`|^#{1,6}\s*|^>\s*|^\s*[-*+]\s+|^\s*\d+\.\s+)", re.M)
_MD_LINK = re.compile(r"!?\[([^\]]*)\]\([^)]*\)")


def md_to_text(source: str | None) -> str:
    """Plain words from Markdown: for word counts, the derived `body`, feeds
    and search."""
    text = _MD_LINK.sub(r"\1", source or "")
    text = _MD_MARKS.sub("", text)
    return re.sub(r"[ \t]+", " ", text).strip()
