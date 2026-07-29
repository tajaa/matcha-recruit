"""Incident narrative x handbook/policy check.

REPORTS, NEVER ADJUDICATES: the output carries candidate policy violations
with citations and a confidence score — no discipline level, no legality
verdict. The deterministic `discipline_compliance.check_discipline_compliance`
gate remains the only thing that can block a discipline write, and it runs
later, at record-write time, completely unchanged by this module.

Grounds on the same corpus the Handbook Pilot uses
(`handbook_pilot.gather_grounding` + `build_corpus`) rather than minting a
third handbook corpus — it already carries `handbook:<id>` (handbook
sections), `policy:<id>` (active company policies), and `law:<...>`
(jurisdiction requirements) cids in one flat index, so citation validation
covers all three sources for free.

Pool-free-safe: every function takes `conn` explicitly (no connection is
opened here) so this runs unchanged from the Celery sweep
(`app/workers/tasks/discipline_policy_sweep.py`) and from the Huume
`check_incident_policy` tool.
"""

from __future__ import annotations

import asyncio
import json
import logging
from datetime import datetime, timezone
from typing import Any, Optional
from uuid import UUID

from .._shared.citations import _parse_json, validate_citations
from .._shared.gemini import _genai

logger = logging.getLogger(__name__)

MODEL = "gemini-3-flash-preview"
_GEMINI_TIMEOUT = 60
_MAX_VIOLATIONS = 10

_CHECK_RULES = """
You are checking whether an incident's narrative describes conduct that may have
violated a company policy or handbook section already on file. You are NOT
deciding whether discipline is warranted, what level it should be, or whether
anything here is illegal — a separate deterministic system handles legality.
You are finding candidate matches for a human to review.

Rules:
- Cite ONLY corpus records shown to you, and copy the id inside the brackets
  VERBATIM — including the prefix before the colon. A record shown as
  [policy:0f6af555-bc1c-408c-944a-7218e879b5b3] is cited as
  "policy:0f6af555-bc1c-408c-944a-7218e879b5b3", NOT as
  "0f6af555-bc1c-408c-944a-7218e879b5b3". An id that doesn't match a record
  exactly is dropped and the finding disappears with it.
- A finding with no supporting [cid] will be dropped before anyone sees it —
  don't bother proposing one.
- confidence is your own calibrated 0.0-1.0 estimate that the incident
  narrative actually describes conduct the cited policy governs.
- If nothing in the corpus is plausibly relevant, return an empty violations
  list and say so in `summary` — do not force a match.

Return STRICT JSON, no markdown fence:
{
  "violations": [
    {"policy_cid": "<the full bracketed id, prefix included>", "policy_title": "<title>",
     "relevance": "violated|bent|related",
     "confidence": 0.0, "reasoning": "<why>", "relevant_excerpt": "<short quote or null>"}
  ],
  "summary": "<one or two sentences>"
}
"""


# The corpus renders a record's display name with a provenance label in front
# ("Existing policy — Sharps Handling", "Existing section — PPE"), which is right
# for a citation footer and wrong everywhere this check's output travels: the
# title ends up verbatim in a disciplinary LETTER ("POLICY IMPLICATED: Existing
# policy — Sharps Handling") and in the sweep's briefing. Stripped once here, at
# the point the corpus title becomes the feature's own output.
_CORPUS_LABEL_PREFIXES = ("Existing policy — ", "Existing section — ")

# handbook_pilot.build_corpus's own source-group keys for these two — every
# other group (`profile`, `compliance_floor`, `law`, `playbook`,
# `handbook_audit`, `handbook_freshness`) is grounding for OTHER pilots, not
# an obligation the company wrote for itself, and must never be citable here
# as a "policy violation".
_ALLOWED_SOURCE_GROUPS = ("existing_handbook", "existing_policies")


def _restrict_to_handbook_and_policy(corpus: dict[str, Any]) -> dict[str, Any]:
    """Narrow a handbook_pilot corpus to handbook sections + policies only.

    Filtering the corpus itself (not just prompting around it) means the
    model literally cannot see or cite `law:`/`playbook:`/`profile`/audit/
    freshness records — so a jurisdiction statute or the generic industry
    baseline can never survive `validate_citations` and be persisted as a
    "policy violation". It also fixes the emptiness check below: without
    this, `playbook` records make the index non-empty for every company
    (there's always an industry baseline), so a company with zero handbook
    content never hit the "nothing on file" branch — it burned a Gemini call
    and returned a clean result that looked identical to "nothing relevant"."""
    corpus = corpus or {}
    sources = {
        key: group for key, group in (corpus.get("sources") or {}).items()
        if key in _ALLOWED_SOURCE_GROUPS
    }
    index = {
        cid: rec for cid, rec in (corpus.get("index") or {}).items()
        if rec.get("source") in _ALLOWED_SOURCE_GROUPS
    }
    full_text = {
        cid: text for cid, text in (corpus.get("full_text") or {}).items()
        if cid in index
    }
    return {"sources": sources, "index": index, "notes": corpus.get("notes") or [], "full_text": full_text}


def _clean_title(title: str) -> str:
    for prefix in _CORPUS_LABEL_PREFIXES:
        if title.startswith(prefix):
            return title[len(prefix):].strip()
    return title


def _resolve_cid(cid: str, index: dict[str, Any]) -> str:
    """Repair a corpus id the model returned without its namespace prefix.

    Observed live: the corpus renders `[policy:<uuid>]` and the model answers
    with the bare `<uuid>`. The citation gate then correctly drops it, and the
    incident persists as `no_matching_policies` — reading as CLEAN when the
    model actually found the right policies. That is a silent wrong answer on a
    legal record, so it gets repaired here rather than left to prompt luck.

    This does NOT weaken the anti-hallucination gate. A bare id is only rewritten
    when EXACTLY ONE real index key ends with `:<id>` — the id still has to have
    come from the corpus, and an ambiguous or unknown one is returned untouched
    for `validate_citations` to drop.
    """
    if cid in index:
        return cid
    suffix = f":{cid}"
    matches = [key for key in index if key.endswith(suffix)]
    return matches[0] if len(matches) == 1 else cid


def _check_prompt(corpus: dict[str, Any], incident: dict[str, Any]) -> str:
    from ..pilots.hr_pilot_corpus import render_corpus_block  # local import: avoids a
    # module-load-order cycle between discipline/ and pilots/.

    corpus_text = render_corpus_block(corpus, corpus.get("full_text") or {})
    return f"""{_CHECK_RULES}

INCIDENT
Title: {incident.get('title') or '(untitled)'}
Type: {incident.get('incident_type') or 'unspecified'}
Severity: {incident.get('severity') or 'unspecified'}
Description: {incident.get('description') or '(no description on file)'}

COMPANY POLICY / HANDBOOK CORPUS
{corpus_text}
"""


async def _build_check_corpus(conn, company_id: UUID) -> Optional[dict[str, Any]]:
    """Build (and restrict) the company's handbook+policy corpus once. `None`
    on any grounding failure — callers treat that as `_unavailable_result()`.
    Split out of `check_incident_against_handbook` so a batch of incidents can
    share ONE corpus build instead of paying for grounding per incident."""
    try:
        from ..pilots.handbook_pilot import build_corpus, gather_grounding

        grounding = await gather_grounding(conn, company_id, {"scopes": []})
        return _restrict_to_handbook_and_policy(build_corpus(grounding, with_full_text=True))
    except Exception:
        logger.exception("[discipline_policy_check] failed to build grounding corpus")
        return None


async def _check_one(corpus: dict[str, Any], incident: dict[str, Any]) -> dict[str, Any]:
    """Run the check for one incident against an already-built `corpus`. No
    `conn` — safe to run concurrently under a semaphore in the batch path.
    Never raises; degrades to `_unavailable_result()`."""
    index = corpus.get("index") or {}
    if not index:
        return {
            "violations": [],
            "citations": [],
            "dropped_citations": [],
            "summary": "No handbook or policy content on file to check against.",
            "available": True,
        }

    try:
        resp = await asyncio.wait_for(
            _genai().aio.models.generate_content(
                model=MODEL,
                contents=_check_prompt(corpus, incident),
            ),
            timeout=_GEMINI_TIMEOUT,
        )
        data = _parse_json(getattr(resp, "text", "") or "")

        # Kept inside the same try as the Gemini call: `data` is untrusted
        # model output (e.g. a malformed `"violations": ["...", ...]` of bare
        # strings instead of objects), and the docstring promises this
        # function never raises — the sweep's own except would catch it, but
        # the Huume `check_incident_policy` tool call does not, so a
        # malformed response would fail the tool call instead of degrading
        # to `available: False` like every other bad-response path.
        raw_violations = (data.get("violations") or [])[:_MAX_VIOLATIONS]
        for v in raw_violations:
            if v.get("policy_cid"):
                v["policy_cid"] = _resolve_cid(str(v["policy_cid"]), index)
        # validate_citations' contract (services/_shared/citations.py) is
        # [{"point": str, "cited_ids": [str]}] -> ([{"point", "cited_ids"}], [dropped]).
        # One entry per violation, its single policy_cid as the sole cited id, so a
        # violation survives exactly when its cid is in the index.
        evidence_map = [
            {"point": str(v.get("reasoning") or ""), "cited_ids": [v["policy_cid"]]}
            for v in raw_violations
            if v.get("policy_cid")
        ]
        clean_map, dropped = validate_citations(evidence_map, index)
        clean_cids = {cid for entry in clean_map for cid in entry.get("cited_ids") or []}

        # Kept inside the same try: `v.get("confidence")` is untrusted model
        # output too (e.g. a string like "high" instead of a number) —
        # shaping the response is not exempt from the "never raises" promise
        # just because citation validation already succeeded. A single
        # malformed field here used to escape uncaught and (in the batch
        # path) take down every other incident's result with it.
        violations = [
            {
                "policy_cid": v["policy_cid"],
                "policy_title": _clean_title(
                    str(v.get("policy_title") or index.get(v["policy_cid"], {}).get("title") or v["policy_cid"])
                ),
                "relevance": v.get("relevance") if v.get("relevance") in ("violated", "bent", "related") else "related",
                "confidence": max(0.0, min(1.0, float(v.get("confidence") or 0))),
                "reasoning": str(v.get("reasoning") or "")[:2000],
                "relevant_excerpt": v.get("relevant_excerpt"),
            }
            for v in raw_violations
            if v.get("policy_cid") in clean_cids
        ]
    except Exception:
        logger.exception("[discipline_policy_check] Gemini check failed for incident %s", incident.get("id"))
        return _unavailable_result()

    return {
        "violations": violations,
        "citations": [v["policy_cid"] for v in violations],
        "dropped_citations": dropped,
        "summary": str(data.get("summary") or "").strip()[:1000],
        "available": True,
    }


async def check_incident_against_handbook(conn, *, company_id: UUID, incident: dict[str, Any]) -> dict[str, Any]:
    """Check `incident` against the company's handbook + active policies.

    `incident` needs: id, title, description, incident_type, severity
    (occurred_at is not read here — it's the caller's job to pass real
    occurrence_dates through to the discipline compliance gate downstream).

    Never raises. A Gemini outage or malformed response degrades to
    `{"available": False, ...}` — the caller (sweep or Huume tool) must treat
    that as "couldn't check", never as "checked, nothing found".
    """
    corpus = await _build_check_corpus(conn, company_id)
    if corpus is None:
        return _unavailable_result()
    return await _check_one(corpus, incident)


async def check_incidents_against_handbook(
    conn, *, company_id: UUID, incidents: list[dict[str, Any]], concurrency: int = 3,
    budget_seconds: Optional[float] = None,
) -> dict[str, dict[str, Any]]:
    """Batch check: builds the corpus ONCE for the whole batch (the expensive
    part is per-company, not per-incident) instead of the N grounding builds
    a naive loop over `check_incident_against_handbook` would pay for.

    `_check_one` calls run concurrently under a semaphore (safe — no `conn`
    use inside); each result is persisted as it lands (SEQUENTIALLY, on the
    caller's single `conn` — asyncpg connections aren't concurrency-safe),
    not batched up after every task finishes.

    `budget_seconds`, if given, bounds the WHOLE batch. This is deliberately
    an INTERNAL deadline rather than the caller wrapping this call in
    `asyncio.wait_for`: cancelling this coroutine from the outside would
    cancel it mid-persist-loop and throw away every already-completed (and
    already-billed) Gemini check along with the ones still running. Instead,
    once the budget expires, whatever has already completed and been
    persisted is returned; any incident whose task hadn't finished yet is
    simply ABSENT from the returned dict — the caller (Huume's
    `find_candidates`) already treats a missing id as "not yet checked", not
    a failure, so this needs no special-casing there.

    Never raises: a corpus-build failure degrades EVERY incident to
    `_unavailable_result()`; a single incident's Gemini failure degrades only
    that incident (defense in depth: `_bounded` below is also guarded, in
    case a future `_check_one` change reintroduces something that raises).

    Returns `{str(incident["id"]): result}` — a subset of the input ids when
    `budget_seconds` cuts the batch off early.
    """
    corpus = await _build_check_corpus(conn, company_id)
    if corpus is None:
        return {str(inc["id"]): _unavailable_result() for inc in incidents}

    sem = asyncio.Semaphore(max(1, concurrency))
    by_incident = {str(inc["id"]): inc for inc in incidents}

    async def _bounded(inc: dict[str, Any]) -> tuple[str, dict[str, Any]]:
        inc_id = str(inc["id"])
        async with sem:
            try:
                return inc_id, await _check_one(corpus, inc)
            except Exception:
                logger.exception("[discipline_policy_check] _check_one raised unexpectedly for incident %s", inc_id)
                return inc_id, _unavailable_result()

    loop = asyncio.get_event_loop()
    deadline = None if budget_seconds is None else loop.time() + budget_seconds
    pending = {asyncio.ensure_future(_bounded(inc)) for inc in incidents}
    by_id: dict[str, dict[str, Any]] = {}

    try:
        while pending:
            wait_timeout = None if deadline is None else max(0.0, deadline - loop.time())
            if wait_timeout == 0.0:
                break
            done, pending = await asyncio.wait(pending, timeout=wait_timeout, return_when=asyncio.FIRST_COMPLETED)
            if not done:
                break  # budget expired with nothing new finished
            for task in done:
                inc_id, result = task.result()  # _bounded never raises — see above
                by_id[inc_id] = result
                if result.get("available"):
                    await persist_policy_check(conn, incident_id=by_incident[inc_id]["id"], result=result)
    finally:
        for task in pending:
            task.cancel()

    return by_id


def _unavailable_result() -> dict[str, Any]:
    return {
        "violations": [],
        "citations": [],
        "dropped_citations": [],
        "summary": "",
        "available": False,
    }


async def persist_policy_check(conn, *, incident_id: UUID, result: dict[str, Any]) -> None:
    """Upsert `ir_incident_analysis(analysis_type='policy_mapping')` with this
    check's findings folded in. Preserves the `PolicyMappingAnalysis` reader
    contract (matches[]/summary/no_matching_policies/generated_at/...) that
    `get_policy_mapping`'s 24h cache and the IR analysis tab both read — keys
    are ADDED (citations, dropped_citations, checked_by), never renamed or
    removed, and existing keys (statute_matches etc.) are preserved if a
    prior _auto_map_policy_violations row already exists for this incident.
    """
    existing = await conn.fetchval(
        "SELECT analysis_data FROM ir_incident_analysis WHERE incident_id = $1 AND analysis_type = 'policy_mapping'",
        incident_id,
    )
    base: dict[str, Any] = {}
    if existing:
        try:
            base = json.loads(existing) if isinstance(existing, str) else dict(existing)
        except (ValueError, TypeError):
            base = {}

    matches = [
        {
            "policy_id": v["policy_cid"],
            "policy_title": v["policy_title"],
            "relevance": v["relevance"],
            "confidence": v["confidence"],
            "reasoning": v["reasoning"],
            "relevant_excerpt": v.get("relevant_excerpt"),
        }
        for v in result.get("violations") or []
    ]

    merged = {
        **base,
        "matches": matches,
        "summary": result.get("summary") or base.get("summary") or "",
        "no_matching_policies": len(matches) == 0,
        "generated_at": datetime.now(timezone.utc).replace(microsecond=0).isoformat(),
        "citations": result.get("citations") or [],
        "dropped_citations": result.get("dropped_citations") or [],
        "checked_by": "discipline_policy_check",
    }

    await conn.execute(
        """
        INSERT INTO ir_incident_analysis (incident_id, analysis_type, analysis_data)
        VALUES ($1, 'policy_mapping', $2::jsonb)
        ON CONFLICT (incident_id, analysis_type)
        DO UPDATE SET analysis_data = $2::jsonb, generated_at = now()
        """,
        incident_id, json.dumps(merged),
    )
