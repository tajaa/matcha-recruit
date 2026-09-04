#!/usr/bin/env python3
"""Detect a staged diff that only rewrites string literals.

When a card's acceptance criteria are already satisfied and the model is
forbidden from saying so, the highest-scoring legal move is a diff that changes
nothing real. PR #418 was exactly this: its whole merged client change was

    -  { to: '/app/credential-templates', ..., label: 'Credentialing', ... },
    +  { to: '/app/credential-templates', ..., label: 'Credential Templates', ... },

Reads a unified diff on stdin. Exits 0 when every changed line differs only
inside quoted spans -- i.e. strip the quoted text and the added and removed
sides are identical. Exits 1 otherwise, including for an empty diff.

This is a signal, not a verdict: a card that genuinely asks for a copy change
produces the same shape, so the caller decides what the card was asking for.
"""

from __future__ import annotations

import re
import sys
from collections import Counter

# Quoted spans in the languages this bot may touch: TS/TSX, Python, Swift.
# Escaped quotes stay inside their span so an apostrophe cannot end one early.
_QUOTED = re.compile(
    r"'(?:\\.|[^'\\])*'"      # single-quoted
    r'|"(?:\\.|[^"\\])*"'     # double-quoted
    r"|`(?:\\.|[^`\\])*`",    # template literal
)


def skeleton(line: str) -> str:
    """The line with every quoted span blanked and whitespace collapsed.

    Two lines with the same skeleton differ only in what the strings say.
    """
    return " ".join(_QUOTED.sub('""', line).split())


def _literals(line: str) -> list[str]:
    """The quoted spans on one line, quotes stripped."""
    return [match.group()[1:-1] for match in _QUOTED.finditer(line)]


def _is_path_like(literal: str) -> bool:
    """A quoted span that names a location rather than copy.

    A route path or a nav destination is structure: rewriting `/app/old` to
    `/app/new`, or moving a row that carries one, changes where the product
    goes. Only prose rewrites are cosmetic.
    """
    text = literal.strip()
    return text.startswith("/") or text.startswith("./") or text.startswith("../")


def is_string_literal_only(diff: str) -> bool:
    added_raw: Counter[str] = Counter()
    removed_raw: Counter[str] = Counter()
    for line in diff.splitlines():
        if line.startswith(("+++", "---", "diff ", "index ", "@@", "new file", "deleted file")):
            continue
        if line.startswith("+"):
            added_raw[line[1:]] += 1
        elif line.startswith("-"):
            removed_raw[line[1:]] += 1
    if not added_raw or not removed_raw:
        # A pure addition or pure deletion is real work, not a reword.
        return False

    # A line that appears verbatim on both sides was relocated, not reworded --
    # a nav row moved into another group is exactly this shape, and it is real
    # structural work. Set it aside before judging what actually changed.
    relocated = added_raw & removed_raw
    added_raw -= relocated
    removed_raw -= relocated
    if not added_raw or not removed_raw:
        return False

    added = Counter(skeleton(line) for line in added_raw.elements())
    removed = Counter(skeleton(line) for line in removed_raw.elements())
    if added != removed:
        return False

    # Same code, different strings -- but if one of those strings is a path,
    # the diff repoints the product rather than rewording it.
    added_literals: Counter[str] = Counter()
    removed_literals: Counter[str] = Counter()
    for line in added_raw.elements():
        added_literals.update(_literals(line))
    for line in removed_raw.elements():
        removed_literals.update(_literals(line))
    changed = (added_literals - removed_literals) + (removed_literals - added_literals)
    return not any(_is_path_like(literal) for literal in changed)


def main() -> int:
    return 0 if is_string_literal_only(sys.stdin.read()) else 1


if __name__ == "__main__":
    raise SystemExit(main())
