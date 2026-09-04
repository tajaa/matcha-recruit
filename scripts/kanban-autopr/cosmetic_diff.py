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


def is_string_literal_only(diff: str) -> bool:
    added: Counter[str] = Counter()
    removed: Counter[str] = Counter()
    for line in diff.splitlines():
        if line.startswith(("+++", "---", "diff ", "index ", "@@", "new file", "deleted file")):
            continue
        if line.startswith("+"):
            added[skeleton(line[1:])] += 1
        elif line.startswith("-"):
            removed[skeleton(line[1:])] += 1
    if not added or not removed:
        # A pure addition or pure deletion is real work, not a reword.
        return False
    return added == removed


def main() -> int:
    return 0 if is_string_literal_only(sys.stdin.read()) else 1


if __name__ == "__main__":
    raise SystemExit(main())
