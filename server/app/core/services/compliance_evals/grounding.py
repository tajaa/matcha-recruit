"""Grounding suite — does a ``gemini_grounded`` value actually appear in the
statute text it cites?

The scope-registry research path tags a requirement ``metadata.grounding =
'grounded'`` when the model cited a real excerpt from the fetched official text
(``grounded.validate_requirement_citations``). But "cited a real excerpt" is NOT
"the value is in that excerpt" — the model can attach a genuine citation to a
recalled number. `grounded.py`'s own docstring flags this: grounding is an
*anchored-to-a-source* signal, not a value-provenance guarantee. Nothing measured
the gap. This suite does.

Tier 1 (here) is deterministic and free: pull each grounded row's cited
``body_text``, extract the numeric tokens the value asserts, and check they appear
in the text. Verdicts:

  * ``value_in_text``       — every numeric token is present → grounded for real.
  * ``value_not_in_text``   — a real citation, a number the text never states.
                              CRITICAL: this is a recalled value wearing a
                              citation, and it flows straight into the existing
                              readiness gate's open-critical block.
  * ``corpus_stub``         — the cited body is a heading/stub (< threshold), so
                              "grounded" is meaningless — nothing to verify against.
  * ``value_unverifiable``  — the value is prose with no numeric claim tier 1 can
                              check (info; the tier-2 LLM verifier is the follow-up).

Read-only over the catalog, like every eval suite. Pure core (``evaluate_row``,
``value_tokens``) unit-tests without a DB. Tier-2 (an adversarial LLM verifier on
the unresolved rows) and a golden cross-check are documented extension points at
the bottom — deliberately not wired yet.
"""
from __future__ import annotations

import logging
import re
from collections import defaultdict
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)

# A cited body shorter than this is a heading/subpart stub, not the operative
# rule text — you cannot verify a value against it, so "grounded" is hollow.
STUB_BODY_THRESHOLD = 500

# Numeric tokens in a value string: "$844/week ($43,888/year)" → 844, 43888.
_NUM_RE = re.compile(r"\d[\d,]*(?:\.\d+)?")

# Citation references are not the value — strip them so a prose value that merely
# names its statute ("...per 29 CFR 1904") isn't judged on the citation's digits.
_CITATION_RE = re.compile(
    r"\d+\s+(?:cfr|u\.?s\.?c\.?|c\.?c\.?r\.?)\s+(?:§\s*)?[\d.]+"  # 29 CFR 1904, 29 U.S.C. § 207
    r"|§\s*[\d.]+"                                                 # § 207
    r"|\bpart\s+\d+|\bsubpart\s+[a-z]\b|\btitle\s+\d+",            # Part 1904, Subpart C, Title 8
    re.IGNORECASE,
)

# Legal prose spells numbers out; accept the common textual forms so a real
# grounding isn't flagged just because the statute says "forty" not "40".
_SPELLED: Dict[str, tuple] = {
    "1.5": ("one and one-half", "one and one half", "one-and-one-half",
            "time and a half", "time and one-half", "150%"),
    "2": ("two", "double", "twice"),
    "3": ("three", "triple"),
    "7": ("seven",),
    "8": ("eight",),
    "10": ("ten",),
    "11": ("eleven",),
    "15": ("fifteen",),
    "20": ("twenty",),
    "30": ("thirty",),
    "40": ("forty",),
    "50": ("fifty",),
    "60": ("sixty",),
    "90": ("ninety",),
}

VALUE_IN_TEXT = "value_in_text"
VALUE_NOT_IN_TEXT = "value_not_in_text"
CORPUS_STUB = "corpus_stub"
VALUE_UNVERIFIABLE = "value_unverifiable"


def _fmt_numeric(numeric_value: Any) -> Optional[str]:
    """A DB numeric → the token form a human would read: 844.0 → '844', 7.25 → '7.25'."""
    if numeric_value is None:
        return None
    f = float(numeric_value)
    return str(int(f)) if f == int(f) else str(f).rstrip("0").rstrip(".")


def value_tokens(current_value: Optional[str], numeric_value: Any = None) -> List[str]:
    """The distinct numeric claims a grounded value makes (pure).

    Citation references are stripped first (they're pointers, not values), then
    every remaining number is a token, plus the row's own ``numeric_value``.
    Commas are removed so '43,888' and '43888' compare equal. Order-preserving,
    de-duplicated.
    """
    text = _CITATION_RE.sub(" ", current_value or "")
    seen: Dict[str, None] = {}
    nv = _fmt_numeric(numeric_value)
    if nv is not None:
        seen.setdefault(nv.replace(",", ""), None)
    for m in _NUM_RE.findall(text):
        cleaned = m.replace(",", "")
        # drop a bare trailing-zero decimal artifact ('40.0' → '40')
        if "." in cleaned:
            cleaned = cleaned.rstrip("0").rstrip(".")
        if cleaned:
            seen.setdefault(cleaned, None)
    return list(seen)


def _token_in_text(token: str, body_low: str) -> bool:
    variants = {token}
    # a whole-number token may appear with a decimal/comma in the text
    variants.add(f"{token}.0")
    if len(token) > 3:
        variants.add(f"{token[:-3]},{token[-3:]}")  # 43888 → 43,888
    variants.update(_SPELLED.get(token, ()))
    return any(v and v in body_low for v in variants)


def evaluate_row(
    current_value: Optional[str],
    numeric_value: Any,
    body_text: Optional[str],
) -> Dict[str, Any]:
    """Verdict for one grounded row against its cited excerpt(s). Pure, no I/O."""
    body = body_text or ""
    if len(body.strip()) < STUB_BODY_THRESHOLD:
        return {"verdict": CORPUS_STUB, "body_len": len(body.strip()),
                "found": [], "missing": []}

    tokens = value_tokens(current_value, numeric_value)
    if not tokens:
        return {"verdict": VALUE_UNVERIFIABLE, "body_len": len(body),
                "found": [], "missing": [], "reason": "no numeric claim to verify"}

    body_low = body.lower()
    found = [t for t in tokens if _token_in_text(t, body_low)]
    missing = [t for t in tokens if t not in found]
    verdict = VALUE_NOT_IN_TEXT if missing else VALUE_IN_TEXT
    return {"verdict": verdict, "body_len": len(body), "found": found, "missing": missing}


async def _grounded_rows(conn, jurisdiction_ids: Optional[List]) -> List[Dict]:
    sql = """
        SELECT jr.id, jr.jurisdiction_id, jr.requirement_key, jr.regulation_key,
               jr.category, jr.current_value, jr.numeric_value,
               ARRAY(SELECT jsonb_array_elements_text(jr.metadata->'grounded_citations'))
                 AS cited
        FROM jurisdiction_requirements jr
        WHERE jr.metadata->>'grounding' = 'grounded'
          AND COALESCE(jr.status, 'active') = 'active'
    """
    params: List = []
    if jurisdiction_ids:
        sql += " AND jr.jurisdiction_id = ANY($1::uuid[])"
        params.append(jurisdiction_ids)
    return [dict(r) for r in await conn.fetch(sql, *params)]


async def _bodies_by_citation(conn, citations: List[str]) -> Dict[str, str]:
    """citation string → its longest fetched body_text (same citation can exist in
    two indexes; keep the substantive one)."""
    if not citations:
        return {}
    rows = await conn.fetch(
        "SELECT citation, body_text FROM authority_index_items "
        "WHERE citation = ANY($1::text[]) AND body_text IS NOT NULL",
        citations,
    )
    out: Dict[str, str] = {}
    for r in rows:
        prev = out.get(r["citation"], "")
        if len(r["body_text"] or "") > len(prev):
            out[r["citation"]] = r["body_text"]
    return out


async def run_grounding(conn, jurisdiction_ids: Optional[List] = None) -> Dict:
    """Verify every grounded value against its cited statute text.

    Returns ``{results: {jid: {score, detail}}, findings, totals}``. The
    ``value_not_in_text`` findings are ``critical`` and therefore block the
    existing onboarding-readiness gate through the runner's open-critical count —
    no new gate wiring needed.
    """
    rows = await _grounded_rows(conn, jurisdiction_ids)
    all_citations = sorted({c for r in rows for c in (r["cited"] or [])})
    bodies = await _bodies_by_citation(conn, all_citations)

    findings: List[Dict] = []
    per_jur: Dict = defaultdict(lambda: defaultdict(int))
    totals = {"grounded_rows": len(rows), VALUE_IN_TEXT: 0, VALUE_NOT_IN_TEXT: 0,
              CORPUS_STUB: 0, VALUE_UNVERIFIABLE: 0}

    for r in rows:
        # The corpus the value was grounded on = the union of its cited excerpts.
        corpus = "\n\n".join(bodies.get(c, "") for c in (r["cited"] or []))
        res = evaluate_row(r["current_value"], r["numeric_value"], corpus)
        verdict = res["verdict"]
        totals[verdict] += 1
        per_jur[r["jurisdiction_id"]][verdict] += 1

        if verdict == VALUE_NOT_IN_TEXT:
            findings.append({
                "suite": "grounding", "finding_type": "grounded_value_not_in_text",
                "severity": "critical",
                "jurisdiction_id": r["jurisdiction_id"], "requirement_id": r["id"],
                "requirement_key": r["requirement_key"], "category": r["category"],
                "expected": {"tokens_in_cited_text": res["found"] + res["missing"]},
                "observed": {"current_value": r["current_value"],
                             "missing_from_text": res["missing"],
                             "cited": r["cited"]},
            })
        elif verdict == CORPUS_STUB:
            findings.append({
                "suite": "grounding", "finding_type": "grounded_on_stub",
                "severity": "warn",
                "jurisdiction_id": r["jurisdiction_id"], "requirement_id": r["id"],
                "requirement_key": r["requirement_key"], "category": r["category"],
                "expected": {"cited_body_chars": f">= {STUB_BODY_THRESHOLD}"},
                "observed": {"cited_body_chars": res["body_len"], "cited": r["cited"]},
            })
        elif verdict == VALUE_UNVERIFIABLE:
            findings.append({
                "suite": "grounding", "finding_type": "grounded_value_unverifiable",
                "severity": "info",
                "jurisdiction_id": r["jurisdiction_id"], "requirement_id": r["id"],
                "requirement_key": r["requirement_key"], "category": r["category"],
                "observed": {"current_value": r["current_value"],
                             "reason": "prose value; tier-1 has no numeric claim to check"},
            })

    from .scoring import grounding_score

    results = {
        jid: {
            "score": grounding_score(counts[VALUE_IN_TEXT], counts[VALUE_NOT_IN_TEXT]),
            "detail": {"verdict_counts": dict(counts)},
        }
        for jid, counts in per_jur.items()
    }
    return {"results": results, "findings": findings, "totals": totals}


# ── Extension points (documented, not wired) ────────────────────────────────────
#
# Tier 2 — adversarial LLM verifier. For every row tier 1 can't settle
# (value_unverifiable) or wants a second opinion on (value_not_in_text), make ONE
# independent Gemini call framed to REFUTE: "excerpt + claimed value → does the text
# state this value? Answer strictly." Verifier framing ≠ extractor framing, so it
# catches recall the extractor smuggled in. Gate behind a settings flag + run only
# on new/changed grounded rows (cheap). Store the verdict alongside tier 1.
#
# Golden cross-check. golden.py already holds hand-verified facts with effective
# windows. A grounded row that DISAGREES with a golden fact for the same
# (jurisdiction, key) is a critical `grounded_but_wrong` — reuse golden.compare,
# no new infrastructure.
