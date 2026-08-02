"""Fuzzy item-name matching for auto-created inventory items. Pure,
stdlib-only — no pg_trgm (deliberately avoided on RDS, see the zzzzcappe25
migration docstring), so fuzzy match is Python's difflib."""

import difflib
import re

_PUNCT_RE = re.compile(r"[^\w\s]")
_WS_RE = re.compile(r"\s+")


def normalize_name(name: str) -> str:
    """Lowercase, strip punctuation, collapse whitespace, naive
    de-pluralize (trailing 's', not 'ss'/'us') so "Cookies!" and "cookie"
    both normalize toward the same key."""
    text = (name or "").strip().lower()
    text = _PUNCT_RE.sub("", text)
    text = _WS_RE.sub(" ", text).strip()
    if text.endswith("s") and not text.endswith("ss") and len(text) > 3:
        text = text[:-1]
    return text


def best_match(name: str, existing: list[dict]) -> dict | None:
    """existing: list of {id, name, normalized_name}. Returns the matched
    row dict, or None. Order: exact normalized match -> substring
    containment (either direction, guarded to avoid 1-2 char false
    positives) -> difflib fuzzy (cutoff 0.75, same cutoff family as
    core/routes/admin/_shared.py's 0.72)."""
    if not existing:
        return None
    target = normalize_name(name)
    if not target:
        return None

    for row in existing:
        if row["normalized_name"] == target:
            return row

    for row in existing:
        other = row["normalized_name"]
        if len(target) >= 4 and len(other) >= 4:
            if target in other or other in target:
                return row

    by_norm = {row["normalized_name"]: row for row in existing}
    matches = difflib.get_close_matches(target, list(by_norm.keys()), n=1, cutoff=0.75)
    if matches:
        return by_norm[matches[0]]
    return None
