"""Grounded extraction helpers — feed fetched statute text to research, then gate
the model's answers on the citations it was actually given.

Gemini is a locator, never the source: the value must come from the official
statute/regulation text we fetched (``authority_index_items.body_text``), and the
model must cite which excerpt it read the value from. Any cited id not in the
supplied corpus is dropped — the same anti-hallucination shape as
``legal_defense.validate_citations``.

Both functions are pure (no DB, no AI) so they unit-test without fixtures.
"""
from __future__ import annotations

import re
from typing import Any, Dict, List, Optional, Tuple

# Per-excerpt and whole-corpus character budgets. Deterministic head-truncation
# keeps the prompt bounded (and the tests stable) without a tokenizer.
DEFAULT_PER_ITEM_CAP = 6000
DEFAULT_TOTAL_CAP = 60000

_ID_RE = re.compile(r"S\d+")


def build_grounded_corpus(
    items: List[Dict[str, Any]],
    *,
    per_item_cap: int = DEFAULT_PER_ITEM_CAP,
    total_cap: int = DEFAULT_TOTAL_CAP,
) -> Tuple[str, Dict[str, Dict[str, Any]]]:
    """Render fetched statute bodies into a bracketed-id corpus for the prompt.

    ``items``: ``{item_id, citation, heading, body_text}``. Items without body
    text are excluded (nothing to ground on). Returns ``(corpus_text, index)``
    where ``index[id] = {item_id, citation}`` — the id set the model may cite.
    IDs are assigned S1, S2, … in input order (stable for tests).
    """
    lines: List[str] = []
    index: Dict[str, Dict[str, Any]] = {}
    used = 0
    n = 0
    for it in items:
        body = (it.get("body_text") or "").strip()
        if not body:
            continue  # bodyless — can't ground a value on it
        n += 1
        sid = f"S{n}"
        excerpt = body[:per_item_cap]
        citation = it.get("citation") or ""
        heading = it.get("heading") or ""
        header = f"[{sid}] {citation}{' — ' + heading if heading else ''}"
        block = f"{header}\n{excerpt}"
        # Stop before blowing the total budget, but always keep the header/index
        # entry so a cited id still resolves.
        if used + len(block) > total_cap and lines:
            index[sid] = {"item_id": it.get("item_id"), "citation": citation}
            lines.append(header + "\n[excerpt omitted — corpus size limit]")
            break
        used += len(block)
        index[sid] = {"item_id": it.get("item_id"), "citation": citation}
        lines.append(block)
    return ("\n\n".join(lines), index)


def _normalize_ids(cited: Any) -> List[str]:
    """Coerce a model's ``cited_sources`` (list, bracketed string, junk) into
    bare S-ids. Tolerant: never raises on a malformed value."""
    if cited is None:
        return []
    if isinstance(cited, str):
        return _ID_RE.findall(cited.upper())
    if isinstance(cited, list):
        out: List[str] = []
        for c in cited:
            out.extend(_ID_RE.findall(str(c).upper()))
        return out
    return []


def validate_requirement_citations(
    reqs: List[Dict[str, Any]],
    citation_index: Optional[Dict[str, Dict[str, Any]]],
) -> Tuple[List[Dict[str, Any]], List[str]]:
    """Gate each researched requirement on the corpus it was given.

    Keeps only cited ids present in ``citation_index``; a req with ≥1 valid id is
    tagged ``grounded=True`` and gets ``grounded_citations`` (the resolved real
    citations). Reqs with no valid id keep ``grounded=False``. Returns
    ``(reqs, dropped_ids)`` — mutates each req in place (adds the two keys).

    Caveat: this proves the model cited a *real* excerpt in the corpus, not that
    the reported value actually appears in that excerpt's text (same shape as
    ``legal_defense.validate_citations``). ``grounded``/``gemini_grounded`` is an
    "anchored to a fetched source" signal, not a value-provenance guarantee.
    """
    citation_index = citation_index or {}
    dropped: List[str] = []
    for req in reqs:
        ids = _normalize_ids(req.get("cited_sources"))
        valid = [i for i in ids if i in citation_index]
        dropped.extend(i for i in ids if i not in citation_index)
        req["grounded"] = bool(valid)
        req["grounded_citations"] = [citation_index[i]["citation"] for i in valid]
    return reqs, dropped
