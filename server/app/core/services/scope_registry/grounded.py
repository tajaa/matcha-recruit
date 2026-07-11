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


# Penalty amounts are values too (§ WS2): a fine figure must come from the
# fetched statute text, not model recall. These are the keys that make a
# penalties block worth persisting — a grounding-only (or cited_sources-only)
# shell is not. This is the ONE definition of "substantive"; the read-side
# extractor (resolve.penalties_from_metadata) and the persist sink both reuse it,
# so the two can't drift.
PENALTY_SUBSTANTIVE_KEYS = (
    "enforcing_agency", "civil_penalty_min", "civil_penalty_max",
    "per_violation", "annual_cap", "criminal", "summary",
)


def penalty_is_substantive(penalties: Dict[str, Any]) -> bool:
    return any(penalties.get(k) not in (None, "", []) for k in PENALTY_SUBSTANTIVE_KEYS)


def sanitize_penalties_for_persist(penalties: Any) -> Any:
    """Sink-side guard for EVERY research path (not just the grounded one).

    ``cited_sources`` are corpus-run-local S-ids the model is asked to emit only
    when statute text is supplied; on ungrounded paths the model may emit them
    anyway. Drop the transport key so it never lands in ``metadata.penalties``,
    then collapse an insubstantive block (cited_sources-only / all-null) to None
    so it neither persists nor inflates the penalty-coverage counter. Idempotent;
    leaves non-dict values (None/absent) untouched. Mutates a dict in place.
    """
    if not isinstance(penalties, dict):
        return penalties
    penalties.pop("cited_sources", None)
    return penalties if penalty_is_substantive(penalties) else None


def validate_penalty_citations(
    reqs: List[Dict[str, Any]],
    citation_index: Optional[Dict[str, Dict[str, Any]]],
    *,
    verified_date: Optional[str] = None,
) -> Tuple[List[Dict[str, Any]], List[str]]:
    """Gate each requirement's ``penalties.cited_sources`` on the fetched corpus.

    Mirrors :func:`validate_requirement_citations` but for the nested penalties
    block, and INDEPENDENTLY of the requirement-level grounding — penalty text
    routinely lives in a different section (e.g. an enforcement subpart) than
    the value, so a value-grounded req can carry ungrounded penalties and vice
    versa.

    For each req with a dict ``penalties``:
      * insubstantive block (grounding-only shell, all-null) → ``penalties=None``
        so the additive upsert's ``any(penalties.values())`` check drops it;
      * ``cited_sources`` normalized to bare S-ids; ids present in the corpus →
        ``grounding='grounded'`` + ``grounded_citations=[resolved]`` (+
        ``verified_date`` when given); no valid id → ``grounding='ungrounded'``;
      * ``cited_sources`` is popped either way — the S-ids are corpus-run-local,
        only resolved citations persist.

    Mutates each req in place; returns ``(reqs, dropped_ids)``. Pure (no DB/AI).
    """
    citation_index = citation_index or {}
    dropped: List[str] = []
    for req in reqs:
        penalties = req.get("penalties")
        if not isinstance(penalties, dict):
            continue
        if not penalty_is_substantive(penalties):
            req["penalties"] = None
            continue
        ids = _normalize_ids(penalties.get("cited_sources"))
        valid = [i for i in ids if i in citation_index]
        dropped.extend(i for i in ids if i not in citation_index)
        penalties.pop("cited_sources", None)
        if valid:
            penalties["grounding"] = "grounded"
            penalties["grounded_citations"] = [citation_index[i]["citation"] for i in valid]
            if verified_date:
                penalties["verified_date"] = verified_date
        else:
            penalties["grounding"] = "ungrounded"
    return reqs, dropped
