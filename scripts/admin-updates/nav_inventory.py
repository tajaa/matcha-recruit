#!/usr/bin/env python3
"""Extract the client's real navigable surface so changelog copy can be grounded
in it instead of invented.

The changelog writer is asked to "name the actual navigation" but was never
handed the navigation, so it produced plausible-sounding paths that did not
exist -- e.g. "Open Compliance -> Credential Templates and select Dropdown
options", which merged a sidebar group with a page's tab strip and named a label
("Credential Templates") that the shipped build spelled "Credentialing".

This module reads the checked-out client tree and returns three things:

  routes     every registered route path
  navItems   sidebar rows, each with the group it sits under
  uiLabels   every other `label:` string literal in the client (tab strips,
             controls, sections) -- the allowlist that keeps a legitimate
             in-page tab from being mistaken for an invention

Nothing here is committed: it is regenerated from the working tree on each run,
so it cannot drift away from the code it describes.
"""

from __future__ import annotations

import argparse
import json
import re
from functools import lru_cache
from pathlib import Path
from typing import Any

# A quoted literal must close with the quote it opened with. Accepting either
# closer let `label: "What's New"` capture `What`, and a truncated label is
# exactly the wrong-label failure this module exists to prevent.
_QUOTED = r"(?P<{name}q>['\"])(?P<{name}>(?:\\.|(?!(?P={name}q))[^\\\n]){{1,120}})(?P={name}q)"
_TO_RE = re.compile(r"\bto:\s*" + _QUOTED.format(name="to"))
_LABEL_RE = re.compile(r"\blabel:\s*" + _QUOTED.format(name="label"))
_ROUTE_RE = re.compile(r"<Route\b[^>]*?\bpath=" + _QUOTED.format(name="path"), re.DOTALL)

_SIDEBAR_DIRS = ("components/sidebars", "components/tier-sidebars")
_ROUTE_DIR = "routes"

# Trailing nouns a writer naturally appends to a nav label ("the Compliance
# page", "the Dropdown options tab"). Stripped before matching so they do not
# read as part of the label.
_TRAILING_NOUNS = {
    "tab", "tabs", "page", "pages", "screen", "section", "button", "menu",
    "link", "panel", "view", "sidebar", "nav", "navigation", "list", "form",
}

_MAX_LABEL_LEN = 80


def _unescape(text: str) -> str:
    """Undo the source-level escaping inside a captured literal."""
    return re.sub(r"\\(.)", r"\1", text)


def _literal(match: re.Match[str], name: str) -> str | None:
    value = _unescape(match.group(name)).strip()
    return value if 0 < len(value) <= _MAX_LABEL_LEN else None


def _iter_tsx(root: Path) -> list[Path]:
    return sorted(p for p in root.rglob("*.tsx") if "generated" not in p.parts)


# Brace-aware lexer. Sidebar rows are single-line object literals *by
# convention*, not by rule: ClientSidebar's conditional "Broker Chat" row spells
# `to:` and `label:` on separate lines, and a line-at-a-time reader told the
# model that a shipped nav row did not exist.
_TOKEN_RE = re.compile(
    r"(?P<skip>\s+|//[^\n]*|/\*.*?\*/)"
    r"|(?P<string>'(?:\\.|[^'\\\n])*'|\"(?:\\.|[^\"\\\n])*\"|`(?:\\.|[^`\\])*`)"
    r"|(?P<ident>[A-Za-z_$][A-Za-z0-9_$]*)"
    r"|(?P<punct>[{}:])"
    r"|(?P<other>.)",
    re.DOTALL,
)


def _lex(text: str) -> list[tuple[str, str]]:
    tokens: list[tuple[str, str]] = []
    for match in _TOKEN_RE.finditer(text):
        kind = match.lastgroup
        if kind in ("string", "ident", "punct"):
            tokens.append((kind, match.group()))
    return tokens


def _string_value(token: str) -> str | None:
    if token.startswith("`"):
        return None  # an interpolated label is not a literal we can trust
    value = _unescape(token[1:-1]).strip()
    return value if 0 < len(value) <= _MAX_LABEL_LEN else None


class _Frame:
    __slots__ = ("to", "label", "items", "group")

    def __init__(self, group: str) -> None:
        self.to: str | None = None
        self.label: str | None = None
        self.items = False
        self.group = group


def _collect_sidebar_file(text: str, sidebar: str) -> list[dict[str, str]]:
    """Sidebar rows plus the group each one sits under.

    A group header is an object carrying a `label:` and an `items:` array but no
    `to:` -- that is what distinguishes 'Compliance' the group from 'Compliance'
    the row inside it, which is precisely the ambiguity that produced the bad
    copy.
    """
    items: list[dict[str, str]] = []
    stack: list[_Frame] = []
    tokens = _lex(text)
    index = 0
    while index < len(tokens):
        kind, value = tokens[index]
        if kind == "ident" and tokens[index + 1 : index + 2] == [("punct", ":")]:
            following = tokens[index + 2] if index + 2 < len(tokens) else None
            if stack:
                frame = stack[-1]
                if value in ("to", "label") and following and following[0] == "string":
                    literal = _string_value(following[1])
                    if literal is not None:
                        setattr(frame, value, literal)
                elif value == "items":
                    frame.items = True
            index += 2
            continue
        if kind == "punct" and value == "{":
            group = ""
            for frame in reversed(stack):
                if frame.items and frame.label:
                    group = frame.label
                    break
            stack.append(_Frame(group))
        elif kind == "punct" and value == "}" and stack:
            frame = stack.pop()
            if frame.to and frame.label:
                items.append({
                    "sidebar": sidebar,
                    "group": frame.group,
                    "label": frame.label,
                    "to": frame.to,
                })
        index += 1
    return items


def _collect_sidebars(client_src: Path) -> list[dict[str, str]]:
    items: list[dict[str, str]] = []
    seen: set[tuple[str, str, str, str]] = set()
    for directory in _SIDEBAR_DIRS:
        base = client_src / directory
        if not base.is_dir():
            continue
        for path in sorted(base.glob("*.tsx")):
            for item in _collect_sidebar_file(path.read_text(encoding="utf-8"), path.stem):
                key = (item["sidebar"], item["group"], item["label"], item["to"])
                if key in seen:
                    continue
                seen.add(key)
                items.append(item)
    return items


def _collect_routes(client_src: Path) -> list[str]:
    routes: set[str] = set()
    base = client_src / _ROUTE_DIR
    for path in _iter_tsx(base) if base.is_dir() else []:
        for match in _ROUTE_RE.finditer(path.read_text(encoding="utf-8")):
            value = _literal(match, "path")
            if value:
                routes.add(value)
    return sorted(routes)


def _collect_ui_labels(client_src: Path) -> list[str]:
    """Every other `label:` literal -- tab strips, controls, sections.

    Deliberately broad. The job is to reject navigation the model made up, not
    to police wording, so a real in-page tab must never look like an invention.
    """
    labels: set[str] = set()
    for path in _iter_tsx(client_src):
        for match in _LABEL_RE.finditer(path.read_text(encoding="utf-8")):
            value = _literal(match, "label")
            if value:
                labels.add(value)
    return sorted(labels)


def collect(repo_root: Path) -> dict[str, Any]:
    client_src = repo_root / "client" / "src"
    if not client_src.is_dir():
        raise FileNotFoundError(f"client source tree not found at {client_src}")
    nav_items = _collect_sidebars(client_src)
    return {
        "routes": _collect_routes(client_src),
        "navItems": nav_items,
        "uiLabels": _collect_ui_labels(client_src),
    }


def _normalize(token: str) -> str:
    text = token.strip().strip("\"'`.,;:!?()[]").strip()
    words = text.split()
    while len(words) > 1 and words[-1].lower() in _TRAILING_NOUNS:
        words.pop()
    return " ".join(words).casefold()


def _known(inventory: dict[str, Any]) -> set[str]:
    known = {_normalize(item["label"]) for item in inventory.get("navItems") or []}
    known |= {_normalize(item["group"]) for item in inventory.get("navItems") or [] if item.get("group")}
    known |= {_normalize(label) for label in inventory.get("uiLabels") or []}
    known |= {route.casefold() for route in inventory.get("routes") or []}
    known.discard("")
    return known


# The prompt renders the nav inventory as `Group > Row` and its own example
# steps are written that way, so `>` has to be a separator here too. It was not,
# which meant every step written in the form the prompt teaches skipped
# grounding entirely.
_SEPARATORS = ("->", "=>", "⇒", "›", "»", ">")


def nav_tokens(text: str) -> list[str]:
    """Navigation claims inside one howToUse step.

    Only chains -- segments joined by an arrow -- are treated as claims about
    the UI's shape. Ordinary prose that names no surface is left alone, so this
    validates assertions rather than English.
    """
    normalized = text
    for separator in _SEPARATORS:
        normalized = normalized.replace(separator, "→")
    if "→" not in normalized:
        return []
    return [segment for segment in (s.strip() for s in normalized.split("→")) if segment]


# Substring anchoring needs a floor: a two-letter label would match almost any
# sentence. Short labels must still match a whole segment exactly.
_ANCHOR_MIN_LEN = 5


@lru_cache(maxsize=8)
def _anchor_regex(anchors: frozenset[str]) -> re.Pattern[str] | None:
    """One word-boundary alternation over every anchorable label.

    Word-anchored, not raw substring: with ~900 labels in the tree a bare
    substring test passed almost anything -- "order" inside "reorder point" is
    not a claim that a control named Order exists.
    """
    if not anchors:
        return None
    ordered = sorted(anchors, key=len, reverse=True)
    return re.compile(r"(?<!\w)(?:" + "|".join(re.escape(a) for a in ordered) + r")(?!\w)")


def unknown_nav_tokens(text: str, inventory: dict[str, Any]) -> list[str]:
    """Segments of a navigation chain that name nothing in the client tree.

    A writer wraps a label in prose -- "Open Compliance", "Credential Templates
    and select Dropdown options" -- so a segment is grounded when it *contains*
    a real label, not when it equals one. A segment holding no real label at all
    is the invention worth dropping.
    """
    known = _known(inventory)
    anchors = _anchor_regex(frozenset(a for a in known if len(a) >= _ANCHOR_MIN_LEN))
    unknown: list[str] = []
    for token in nav_tokens(text):
        normalized = _normalize(token)
        if not normalized:
            continue
        if normalized in known or (anchors is not None and anchors.search(normalized)):
            continue
        unknown.append(token)
    return unknown


def render_prompt_block(inventory: dict[str, Any]) -> str:
    """Sidebar structure for the model prompt.

    Only the nav rows: they are what a "go here, then there" step describes, and
    listing every in-page label as well would bury that shape in noise. The
    wider label allowlist stays on the validator side.
    """
    lines = [
        "NAV INVENTORY - the sidebar rows that exist, by sidebar and group.",
        "A group is a collapsible heading; a row under it is a separate page.",
        "Two rows in the same group are SIBLINGS, not parent and child.",
        "",
    ]
    for sidebar in sorted({item["sidebar"] for item in inventory["navItems"]}):
        lines.append(f"{sidebar}:")
        for item in inventory["navItems"]:
            if item["sidebar"] != sidebar:
                continue
            where = f"{item['group']} > {item['label']}" if item["group"] else item["label"]
            lines.append(f"  - {where}  ({item['to']})")
        lines.append("")
    return "\n".join(lines).rstrip() + "\n"


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("output", type=Path)
    parser.add_argument("--repo-root", type=Path, default=Path(__file__).resolve().parents[2])
    parser.add_argument("--format", choices=("json", "text"), default="json")
    args = parser.parse_args()
    inventory = collect(args.repo_root)
    if args.format == "text":
        args.output.write_text(render_prompt_block(inventory) + "\n", encoding="utf-8")
    else:
        args.output.write_text(json.dumps(inventory, indent=2) + "\n", encoding="utf-8")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
