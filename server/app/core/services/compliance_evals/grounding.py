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

Tier 2a (``cross_check_rows``, wired) is the golden cross-check: a grounded row
whose value DISAGREES with a hand-verified golden fact for the same key is a
critical ``grounded_but_wrong`` — the pipeline extracted the wrong number, harder
than a not-in-cited-text miss. Pure ``compare`` over the fetched rows, no new I/O.

Read-only over the catalog, like every eval suite. Pure core (``evaluate_row``,
``value_tokens``, ``cross_check_rows``) unit-tests without a DB. Tier-2b (an
adversarial LLM verifier on the rows tier 1 can't settle) is a documented
extension point at the bottom — deliberately not wired here (Part B).
"""
from __future__ import annotations

import logging
import re
from collections import defaultdict
from datetime import date
from typing import Any, Dict, List, Optional, Set, Tuple

from .golden import (
    GoldenFact,
    _resolve_jurisdiction_id,
    compare as golden_compare,
    load_fixtures,
)
from .keys import normalize_key

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
# Tier-2a: a grounded value that CONTRADICTS a hand-verified golden fact. The
# pipeline extracted the wrong number (right citation, wrong value) — a harder
# failure than value_not_in_text (which only proves the value isn't in the *cited*
# excerpt; golden proves it's the wrong value, period). CRITICAL.
GROUNDED_BUT_WRONG = "grounded_but_wrong"
# Tier-2b: the adversarial LLM verifier read the cited text and REFUTED the value.
# Scored as a contradiction; CRITICAL finding grounded_value_refuted.
LLM_REFUTED_BUCKET = "llm_refuted"


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


def _grounded_key(row: Dict) -> Optional[str]:
    """The `category:normalized_key` a grounded row indexes under — the SAME scheme
    golden._rows_for uses, so a golden fact (which names the normalized key) resolves
    to its grounded row. None when the row carries no usable key."""
    key = row.get("regulation_key")
    rk = row.get("requirement_key")
    if not key and rk and ":" in rk:
        key = rk.rsplit(":", 1)[-1]
    if not key:
        return None
    key = normalize_key(row["category"], key, row.get("level"), row.get("country_code"))
    return f"{row['category']}:{key}"


def cross_check_rows(
    active_facts: List[GoldenFact],
    grounded_by_key: Dict[str, Dict],
    *,
    comparator=golden_compare,
) -> Tuple[List[Dict], Set]:
    """Tier-2a: judge grounded ROWS against active golden facts (pure, no I/O).

    ``grounded_by_key`` holds ONLY grounded rows (caller restricts) indexed by
    ``category:normalized_key``. A fact with no matching grounded row is skipped —
    that's the golden suite's job; here we only judge the grounding pipeline's own
    output. A fact whose grounded row fails ``compare`` yields a critical
    ``grounded_but_wrong`` finding + the row id (so scoring can move it out of
    ``verified``). Returns ``(findings, contradicted_row_ids)``.
    """
    findings: List[Dict] = []
    contradicted: Set = set()
    for fact in active_facts:
        row = grounded_by_key.get(f"{fact.category}:{fact.requirement_key}")
        if row is None:
            continue
        verdict = comparator(fact, row)
        if verdict.get("passed"):
            continue
        contradicted.add(row["id"])
        findings.append({
            "suite": "grounding", "finding_type": GROUNDED_BUT_WRONG,
            "severity": "critical",
            "jurisdiction_id": row["jurisdiction_id"], "requirement_id": row["id"],
            "requirement_key": row["requirement_key"], "category": row["category"],
            "expected": {
                "comparator": fact.comparator,
                "numeric": fact.expected_numeric,
                "text": fact.expected_text,
                "date": str(fact.expected_date) if fact.expected_date else None,
                "authority_url": fact.authority_url,
                "golden_curated_by": fact.curated_by,
            },
            "observed": {**(verdict.get("observed") or {}),
                         "current_value": row.get("current_value"),
                         "reason": verdict.get("reason")},
        })
    return findings, contradicted


async def _grounded_rows(conn, jurisdiction_ids: Optional[List]) -> List[Dict]:
    # title/description/effective_date + jurisdiction level/country_code are here for
    # the tier-2a golden cross-check: golden.compare reads them (text_contains scans
    # title/description; date_eq reads effective_date) and normalize_key needs the
    # level/country_code to build the same key golden fixtures index on.
    sql = """
        SELECT jr.id, jr.jurisdiction_id, jr.requirement_key, jr.regulation_key,
               jr.category, jr.current_value, jr.numeric_value,
               jr.title, jr.description, jr.effective_date,
               j.level::text AS level, COALESCE(j.country_code, 'US') AS country_code,
               ARRAY(SELECT jsonb_array_elements_text(jr.metadata->'grounded_citations'))
                 AS cited
        FROM jurisdiction_requirements jr
        JOIN jurisdictions j ON j.id = jr.jurisdiction_id
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
              CORPUS_STUB: 0, VALUE_UNVERIFIABLE: 0, GROUNDED_BUT_WRONG: 0}
    # row id → (jid, current verdict bucket) so tier-2 overrides can move a row
    # out of whatever bucket tier-1 put it in.
    verdict_by_row: Dict[Any, Tuple[Any, str]] = {}
    row_by_id: Dict[Any, Dict] = {r["id"]: r for r in rows}
    corpus_by_id: Dict[Any, str] = {}
    # Findings for the two LLM-eligible verdicts are DEFERRED past the tier-2b pass
    # (the verifier can resolve or override them). {rid: tier-1 res}.
    pending: Dict[Any, Dict] = {}

    for r in rows:
        # The corpus the value was grounded on = the union of its cited excerpts.
        corpus = "\n\n".join(bodies.get(c, "") for c in (r["cited"] or []))
        corpus_by_id[r["id"]] = corpus
        res = evaluate_row(r["current_value"], r["numeric_value"], corpus)
        verdict = res["verdict"]
        totals[verdict] += 1
        per_jur[r["jurisdiction_id"]][verdict] += 1
        verdict_by_row[r["id"]] = (r["jurisdiction_id"], verdict)

        if verdict == CORPUS_STUB:
            findings.append({
                "suite": "grounding", "finding_type": "grounded_on_stub",
                "severity": "warn",
                "jurisdiction_id": r["jurisdiction_id"], "requirement_id": r["id"],
                "requirement_key": r["requirement_key"], "category": r["category"],
                "expected": {"cited_body_chars": f">= {STUB_BODY_THRESHOLD}"},
                "observed": {"cited_body_chars": res["body_len"], "cited": r["cited"]},
            })
        elif verdict in (VALUE_NOT_IN_TEXT, VALUE_UNVERIFIABLE):
            pending[r["id"]] = res
        # VALUE_IN_TEXT: verified, no finding.

    # ── Tier-2a: golden cross-check ──────────────────────────────────────────
    # Grounded rows vs hand-verified facts. A contradiction is the wrong VALUE
    # (not just "not in the cited excerpt"), so it overrides the tier-1 verdict
    # for scoring and settles the row (drops it from the pending tier-1 findings).
    grounded_index: Dict[Any, Dict[str, Dict]] = defaultdict(dict)
    for r in rows:
        gk = _grounded_key(r)
        if gk is not None:
            grounded_index[r["jurisdiction_id"]][gk] = r

    if grounded_index:
        today = date.today()
        for fixture in load_fixtures():
            jid = await _resolve_jurisdiction_id(conn, fixture.jurisdiction)
            if jid is None or jid not in grounded_index:
                continue
            active = [f for f in fixture.facts if f.active_on(today)]
            xfindings, contradicted = cross_check_rows(active, grounded_index[jid])
            findings.extend(xfindings)
            for rid in contradicted:
                old_jid, old_verdict = verdict_by_row[rid]
                per_jur[old_jid][old_verdict] -= 1
                totals[old_verdict] -= 1
                per_jur[old_jid][GROUNDED_BUT_WRONG] += 1
                totals[GROUNDED_BUT_WRONG] += 1
                verdict_by_row[rid] = (old_jid, GROUNDED_BUT_WRONG)
                pending.pop(rid, None)  # golden settled it — no tier-1 finding

    # ── Tier-2b: adversarial LLM verifier (flag-gated, network) ──────────────
    from app.config import get_settings

    if get_settings().grounding_llm_verifier_enabled and pending:
        from . import grounding_verifier as gv

        candidates = [
            {"id": rid, "current_value": row_by_id[rid]["current_value"],
             "corpus": corpus_by_id[rid]}
            for rid in list(pending)
        ]
        verdicts = await gv.verify_rows(conn, candidates)
        counts = {"llm_calls": 0, "llm_cache_hits": 0,
                  "llm_confirmed": 0, "llm_refuted": 0, "llm_unclear": 0}
        for rid, resd in verdicts.items():
            v = resd["verdict"]
            if resd.get("cached"):
                counts["llm_cache_hits"] += 1
            elif not resd.get("skipped"):
                counts["llm_calls"] += 1
            jid, tier1 = verdict_by_row[rid]
            r = row_by_id[rid]

            if v == gv.LLM_CONFIRMED:
                counts["llm_confirmed"] += 1
                if tier1 == VALUE_UNVERIFIABLE:
                    # LLM read the prose value in the cited text → now verified.
                    per_jur[jid][VALUE_UNVERIFIABLE] -= 1
                    totals[VALUE_UNVERIFIABLE] -= 1
                    per_jur[jid][VALUE_IN_TEXT] += 1
                    totals[VALUE_IN_TEXT] += 1
                    verdict_by_row[rid] = (jid, VALUE_IN_TEXT)
                    pending.pop(rid, None)
                else:
                    # tier1 == VALUE_NOT_IN_TEXT: the pure string check is hard
                    # evidence the number isn't in the excerpt; LLM agreement does
                    # not erase it. Keep the tier-1 critical, annotate it.
                    pending[rid] = {**pending[rid], "_llm": "confirmed"}
            elif v == gv.LLM_REFUTED:
                counts["llm_refuted"] += 1
                per_jur[jid][tier1] -= 1
                totals[tier1] -= 1
                per_jur[jid][LLM_REFUTED_BUCKET] += 1
                totals[LLM_REFUTED_BUCKET] = totals.get(LLM_REFUTED_BUCKET, 0) + 1
                verdict_by_row[rid] = (jid, LLM_REFUTED_BUCKET)
                findings.append({
                    "suite": "grounding", "finding_type": "grounded_value_refuted",
                    "severity": "critical",
                    "jurisdiction_id": jid, "requirement_id": rid,
                    "requirement_key": r["requirement_key"], "category": r["category"],
                    "observed": {"current_value": r["current_value"],
                                 "cited": r["cited"],
                                 "reason": "LLM verifier refuted the value against "
                                           "its cited text"},
                })
                pending.pop(rid, None)  # refuted finding emitted; suppress tier-1
            else:  # llm_unclear / skipped — tier-1 verdict stands
                counts["llm_unclear"] += 1
        totals.update(counts)

    # ── Emit deferred tier-1 findings for rows tier-2 didn't settle ──────────
    for rid, res in pending.items():
        r = row_by_id[rid]
        if res["verdict"] == VALUE_NOT_IN_TEXT:
            observed = {"current_value": r["current_value"],
                        "missing_from_text": res["missing"], "cited": r["cited"]}
            if res.get("_llm"):
                observed["llm"] = res["_llm"]
            findings.append({
                "suite": "grounding", "finding_type": "grounded_value_not_in_text",
                "severity": "critical",
                "jurisdiction_id": r["jurisdiction_id"], "requirement_id": r["id"],
                "requirement_key": r["requirement_key"], "category": r["category"],
                "expected": {"tokens_in_cited_text": res["found"] + res["missing"]},
                "observed": observed,
            })
        else:  # VALUE_UNVERIFIABLE
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
            # golden contradictions + LLM refutals count against grounding just
            # like a not-in-text miss does.
            "score": grounding_score(
                counts[VALUE_IN_TEXT],
                counts[VALUE_NOT_IN_TEXT] + counts.get(GROUNDED_BUT_WRONG, 0)
                + counts.get(LLM_REFUTED_BUCKET, 0),
            ),
            "detail": {"verdict_counts": dict(counts)},
        }
        for jid, counts in per_jur.items()
    }
    return {"results": results, "findings": findings, "totals": totals}


# ── Extension points (documented, not wired) ────────────────────────────────────
#
# Tier 2b — adversarial LLM verifier (Part B). For every row tier 1 can't settle
# (value_unverifiable) or wants a second opinion on (value_not_in_text), make ONE
# independent Gemini call framed to REFUTE: "excerpt + claimed value → does the text
# state this value? Answer strictly." Verifier framing ≠ extractor framing, so it
# catches recall the extractor smuggled in. Gate behind a settings flag + run only
# on new/changed grounded rows (cheap). Store the verdict alongside tier 1.
#
# Spot-check sampling — periodically re-run the LLM verifier on a random sample of
# value_in_text rows to catch right-number-wrong-meaning the golden set doesn't
# cover (golden is curated, not exhaustive).
