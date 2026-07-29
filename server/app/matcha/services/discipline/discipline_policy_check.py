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
from typing import Any
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
- Cite ONLY corpus records shown to you, using their exact bracketed [cid].
- A finding with no supporting [cid] will be dropped before anyone sees it —
  don't bother proposing one.
- confidence is your own calibrated 0.0-1.0 estimate that the incident
  narrative actually describes conduct the cited policy governs.
- If nothing in the corpus is plausibly relevant, return an empty violations
  list and say so in `summary` — do not force a match.

Return STRICT JSON, no markdown fence:
{
  "violations": [
    {"policy_cid": "<cid>", "policy_title": "<title>", "relevance": "violated|bent|related",
     "confidence": 0.0, "reasoning": "<why>", "relevant_excerpt": "<short quote or null>"}
  ],
  "summary": "<one or two sentences>"
}
"""


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


async def check_incident_against_handbook(conn, *, company_id: UUID, incident: dict[str, Any]) -> dict[str, Any]:
    """Check `incident` against the company's handbook + active policies.

    `incident` needs: id, title, description, incident_type, severity
    (occurred_at is not read here — it's the caller's job to pass real
    occurrence_dates through to the discipline compliance gate downstream).

    Never raises. A Gemini outage or malformed response degrades to
    `{"available": False, ...}` — the caller (sweep or Huume tool) must treat
    that as "couldn't check", never as "checked, nothing found".
    """
    try:
        from ..pilots.handbook_pilot import build_corpus, gather_grounding

        grounding = await gather_grounding(conn, company_id, {"scopes": []})
        corpus = build_corpus(grounding, with_full_text=True)
    except Exception:
        logger.exception("[discipline_policy_check] failed to build grounding corpus")
        return _unavailable_result()

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
    except Exception:
        logger.exception("[discipline_policy_check] Gemini check failed for incident %s", incident.get("id"))
        return _unavailable_result()

    raw_violations = (data.get("violations") or [])[:_MAX_VIOLATIONS]
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

    violations = [
        {
            "policy_cid": v["policy_cid"],
            "policy_title": v.get("policy_title") or index.get(v["policy_cid"], {}).get("title") or v["policy_cid"],
            "relevance": v.get("relevance") if v.get("relevance") in ("violated", "bent", "related") else "related",
            "confidence": max(0.0, min(1.0, float(v.get("confidence") or 0))),
            "reasoning": str(v.get("reasoning") or "")[:2000],
            "relevant_excerpt": v.get("relevant_excerpt"),
        }
        for v in raw_violations
        if v.get("policy_cid") in clean_cids
    ]

    return {
        "violations": violations,
        "citations": [v["policy_cid"] for v in violations],
        "dropped_citations": dropped,
        "summary": str(data.get("summary") or "").strip()[:1000],
        "available": True,
    }


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
