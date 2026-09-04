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
from pathlib import Path
from typing import Any

# Sidebar nav entries are single-line object literals by convention across every
# sidebar in the tree, e.g.
#   { to: '/app/ir', icon: AlertTriangle, label: 'Incidents', feature: 'incidents' },
_TO_RE = re.compile(r"""\bto:\s*['"]([^'"]+)['"]""")
_LABEL_RE = re.compile(r"""\blabel:\s*['"]([^'"]{1,80})['"]""")
_ITEMS_RE = re.compile(r"\bitems:\s*\[")
_ROUTE_RE = re.compile(r"""<Route\b[^>]*?\bpath=['"]([^'"]*)['"]""", re.DOTALL)

_SIDEBAR_DIRS = ("components/sidebars", "components/tier-sidebars")
_ROUTE_DIR = "routes"

# Trailing nouns a writer naturally appends to a nav label ("the Compliance
# page", "the Dropdown options tab"). Stripped before matching so they do not
# read as part of the label.
_TRAILING_NOUNS = {
    "tab", "tabs", "page", "pages", "screen", "section", "button", "menu",
    "link", "panel", "view", "sidebar", "nav", "navigation", "list", "form",
}


def _iter_tsx(root: Path) -> list[Path]:
    return sorted(p for p in root.rglob("*.tsx") if "generated" not in p.parts)


def _collect_sidebars(client_src: Path) -> list[dict[str, str]]:
    """Sidebar rows plus the group each one sits under.

    A group header is a `label:` line carrying no `to:` and followed by `items:`
    -- that is what distinguishes 'Compliance' the group from 'Compliance' the
    row inside it, which is precisely the ambiguity that produced the bad copy.
    """
    items: list[dict[str, str]] = []
    for directory in _SIDEBAR_DIRS:
        base = client_src / directory
        if not base.is_dir():
            continue
        for path in sorted(base.glob("*.tsx")):
            sidebar = path.stem
            group = ""
            pending_label = ""
            for line in path.read_text(encoding="utf-8").splitlines():
                to_match = _TO_RE.search(line)
                label_match = _LABEL_RE.search(line)
                if to_match and label_match:
                    items.append({
                        "sidebar": sidebar,
                        "group": group,
                        "label": label_match.group(1),
                        "to": to_match.group(1),
                    })
                    continue
                if label_match and not to_match:
                    pending_label = label_match.group(1)
                elif _ITEMS_RE.search(line) and pending_label:
                    group = pending_label
                    pending_label = ""
    return items


def _collect_routes(client_src: Path) -> list[str]:
    routes: set[str] = set()
    base = client_src / _ROUTE_DIR
    for path in _iter_tsx(base) if base.is_dir() else []:
        routes.update(_ROUTE_RE.findall(path.read_text(encoding="utf-8")))
    return sorted(r for r in routes if r)


def _collect_ui_labels(client_src: Path) -> list[str]:
    """Every other `label:` literal -- tab strips, controls, sections.

    Deliberately broad. The job is to reject navigation the model made up, not
    to police wording, so a real in-page tab must never look like an invention.
    """
    labels: set[str] = set()
    for path in _iter_tsx(client_src):
        labels.update(_LABEL_RE.findall(path.read_text(encoding="utf-8")))
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


def nav_tokens(text: str) -> list[str]:
    """Navigation claims inside one howToUse step.

    Only chains -- segments joined by an arrow -- are treated as claims about
    the UI's shape. Ordinary prose that names no surface is left alone, so this
    validates assertions rather than English.
    """
    normalized = text.replace("->", "→").replace("⇒", "→")
    if "→" not in normalized:
        return []
    return [segment for segment in (s.strip() for s in normalized.split("→")) if segment]


# Substring anchoring needs a floor: a two-letter label would match almost any
# sentence. Short labels must still match a whole segment exactly.
_ANCHOR_MIN_LEN = 5


def unknown_nav_tokens(text: str, inventory: dict[str, Any]) -> list[str]:
    """Segments of a navigation chain that name nothing in the client tree.

    A writer wraps a label in prose -- "Open Compliance", "Credential Templates
    and select Dropdown options" -- so a segment is grounded when it *contains*
    a real label, not when it equals one. A segment holding no real label at all
    is the invention worth dropping.
    """
    known = _known(inventory)
    anchors = [label for label in known if len(label) >= _ANCHOR_MIN_LEN]
    unknown: list[str] = []
    for token in nav_tokens(text):
        normalized = _normalize(token)
        if not normalized:
            continue
        if normalized in known or any(anchor in normalized for anchor in anchors):
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
