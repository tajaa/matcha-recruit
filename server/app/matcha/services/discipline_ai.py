"""Discipline AI — grounded letter drafting + soft-risk review.

Two jobs, both strictly *downstream* of the deterministic gate in
`discipline_compliance.py`:

1. **Draft** the corrective-action letter (`description`,
   `expected_improvement`) from a plain-language account of what happened, so HR
   isn't staring at an empty textarea trying to write defensible prose. The
   draft is grounded in the company's own records — prior discipline, the
   policy mapping for this infraction, the employee's recent protected leave,
   and the statute row for their work state — and every factual claim must cite
   a corpus ID. `legal_defense.validate_citations` (shared, unit-tested) drops
   any citation the model invented before the draft reaches HR.

2. **Review** the final, HR-edited text for *soft* risks at issue time:
   documentation gaps, prose that describes protected activity as if it were
   the misconduct, tone that reads as pretext. These land as advisories.

What this module explicitly does NOT do is decide whether the discipline is
lawful. That verdict is deterministic and lives in `discipline_compliance.py`.
An LLM is the wrong instrument for a bright-line statutory question: it fails
silently and plausibly, and a confident all-clear on a protected-leave
termination is exactly the error nobody catches until discovery. So the model
gets the gate's verdict as *input* and may only add to it. Correspondingly, a
Gemini outage degrades to a single "review unavailable" advisory — it never
blocks issuance, because the legal gate already ran without it.

Corpus cid scheme (flat index; the citation gate keys on it):
- ``emp:profile``      — the employee's own record
- ``policy:<type>``    — the company's policy mapping for this infraction type
- ``disc:<uuid>``      — one record per prior discipline on file
- ``leave:<uuid>``     — one record per recent protected leave / sick PTO
- ``statute:<ST>``     — the curated sick-leave statute row for the work state
"""

from __future__ import annotations

import asyncio
import json
import logging
from typing import Any, Optional
from uuid import UUID

from app.core.services.genai_client import get_genai_client

from . import discipline_compliance, discipline_engine
from .legal_defense import _parse_json, validate_citations  # pure, unit-tested

logger = logging.getLogger(__name__)

MODEL = "gemini-3-flash-preview"
_GEMINI_TIMEOUT = 60
_MAX_PRIOR_DISCIPLINE = 20
_MAX_LEAVE_RECORDS = 20
_TEXT_CAP = 6_000

_client = None


def _genai():
    global _client
    if _client is None:
        _client = get_genai_client()
    return _client


# ── Corpus ──────────────────────────────────────────────────────────────

async def build_draft_corpus(
    conn, *, company_id: UUID, employee_id: UUID, infraction_type: str
) -> tuple[dict[str, Any], dict[str, Any]]:
    """Assemble the grounding corpus. Returns (corpus, index).

    `corpus` is what the prompt renders; `index` is the flat cid → record map
    the citation gate validates against. They are built together so a record can
    never be citable-but-unshown or shown-but-uncitable.
    """
    index: dict[str, Any] = {}

    emp = await conn.fetchrow(
        """
        SELECT id, first_name, last_name, job_title, work_state,
               start_date AS hire_date, email
        FROM employees
        WHERE id = $1 AND org_id = $2
        """,
        employee_id, company_id,
    )
    employee = dict(emp) if emp else {}
    if employee:
        index["emp:profile"] = employee

    mapping = await discipline_engine.get_policy_mapping(conn, company_id, infraction_type)
    policy_cid = f"policy:{infraction_type}"
    index[policy_cid] = mapping

    prior_rows = await conn.fetch(
        """
        SELECT id, discipline_type, severity, infraction_type, issued_date,
               status, description, expires_at
        FROM progressive_discipline
        WHERE employee_id = $1 AND company_id = $2
        ORDER BY issued_date DESC
        LIMIT $3
        """,
        employee_id, company_id, _MAX_PRIOR_DISCIPLINE,
    )
    priors = []
    for r in prior_rows:
        d = dict(r)
        cid = f"disc:{d['id']}"
        index[cid] = d
        priors.append({"cid": cid, **d})

    leave_rows = await discipline_compliance._fetch_protected_leave(conn, employee_id, company_id)
    pto_rows = await discipline_compliance._fetch_sick_pto(conn, employee_id, company_id)
    leaves = []
    for r in (leave_rows + pto_rows)[:_MAX_LEAVE_RECORDS]:
        cid = f"leave:{r['id']}"
        index[cid] = r
        leaves.append({"cid": cid, **r})

    statute = discipline_compliance.statute_for_state(employee.get("work_state"))
    if statute:
        index[f"statute:{statute['state']}"] = statute

    corpus = {
        "employee": employee,
        "policy_mapping": mapping,
        "policy_cid": policy_cid,
        "prior_discipline": priors,
        "protected_leave": leaves,
        "statute": statute,
    }
    return corpus, index


def _render_corpus(corpus: dict[str, Any]) -> str:
    emp = corpus.get("employee") or {}
    mapping = corpus.get("policy_mapping") or {}
    parts: list[str] = []

    parts.append("[emp:profile] EMPLOYEE")
    parts.append(
        f"  name: {(emp.get('first_name') or '')} {(emp.get('last_name') or '')}".rstrip()
        + f" | title: {emp.get('job_title') or 'unknown'}"
        + f" | work state: {emp.get('work_state') or 'unknown'}"
        + f" | hired: {emp.get('hire_date') or 'unknown'}"
    )

    parts.append(f"\n[{corpus.get('policy_cid')}] COMPANY POLICY FOR THIS INFRACTION TYPE")
    parts.append(
        f"  label: {mapping.get('label')} | default severity: {mapping.get('default_severity')}"
        f" | auto-escalates to written: {mapping.get('auto_to_written')}"
    )

    priors = corpus.get("prior_discipline") or []
    parts.append("\nPRIOR DISCIPLINE ON FILE")
    if not priors:
        parts.append("  (none)")
    for p in priors:
        parts.append(
            f"  [{p['cid']}] {p.get('issued_date')} — {p.get('discipline_type')} "
            f"({p.get('infraction_type')}, {p.get('severity')}, status={p.get('status')}): "
            f"{(p.get('description') or '')[:300]}"
        )

    leaves = corpus.get("protected_leave") or []
    parts.append("\nRECENT PROTECTED LEAVE / SICK TIME (legally protected — see rules)")
    if not leaves:
        parts.append("  (none on file)")
    for lv in leaves:
        parts.append(
            f"  [{lv['cid']}] {lv.get('start_date')} → {lv.get('end_date') or lv.get('start_date')} "
            f"— {lv.get('leave_type') or lv.get('request_type')} (status={lv.get('status')})"
        )

    statute = corpus.get("statute")
    parts.append("\nAPPLICABLE STATE SICK-LEAVE PROTECTION")
    if statute:
        parts.append(
            f"  [statute:{statute['state']}] {statute['statute']} — {statute['note']}"
        )
    else:
        parts.append("  (work state not in the verified statute table — do not assert it is permissive)")

    return "\n".join(parts)


# ── Draft ───────────────────────────────────────────────────────────────

_DRAFT_RULES = """
RULES — these are not style preferences, they are what keeps the document defensible:
- Write about CONDUCT and its BUSINESS IMPACT. Never about the person's character,
  attitude, or motives.
- Every factual assertion you make about this employee's record (prior warnings,
  leave, policy terms) MUST cite a bracketed corpus id in `evidence_map`. If a fact
  is not in the corpus, do not assert it — write only what the HR account states.
- NEVER characterize protected leave, a filed complaint, or an incident report as
  misconduct, as part of a pattern, or as an aggravating factor. If the HR account
  appears to do so, leave it out of the letter and flag it in `concerns`.
- `expected_improvement` must be specific, observable, and achievable — a standard the
  employee can actually meet and a manager can actually measure.
- Neutral, factual, non-inflammatory tone. This document will be read by the employee,
  by a lawyer, and possibly by a jury.

Return STRICT JSON, no markdown fence:
{
  "description": "the letter's statement of what occurred and why it violates policy",
  "expected_improvement": "the specific corrective standard going forward",
  "suggested_infraction_type": "attendance|performance|safety|harassment|policy_violation|gross_misconduct",
  "suggested_severity": "minor|moderate|severe|immediate_written",
  "evidence_map": [{"point": "<claim you made>", "cited_ids": ["disc:...", "policy:..."]}],
  "concerns": ["<anything about this action that looks legally risky>"]
}
"""


def _draft_prompt(corpus: dict[str, Any], situation: str,
                  infraction_type: Optional[str], severity: Optional[str]) -> str:
    return f"""You are an HR documentation specialist drafting a progressive-discipline
corrective action. You are drafting for review by a human HR administrator, who will
edit your text before anything is issued. You are not making the decision to discipline.

THE ONLY RECORDS YOU MAY CITE (bracketed ids are the citable corpus):
{_render_corpus(corpus)}

WHAT HR SAYS HAPPENED:
{situation[:_TEXT_CAP]}

HR's proposed classification: infraction_type={infraction_type or "(not yet chosen)"}, severity={severity or "(not yet chosen)"}
{_DRAFT_RULES}"""


async def draft_discipline_letter(
    conn, *, company_id: UUID, employee_id: UUID, situation: str,
    infraction_type: Optional[str] = None, severity: Optional[str] = None,
) -> dict[str, Any]:
    """Draft letter text from an HR account. Citation-gated. Never raises."""
    try:
        corpus, index = await build_draft_corpus(
            conn, company_id=company_id, employee_id=employee_id,
            infraction_type=infraction_type or "policy_violation",
        )
        resp = await asyncio.wait_for(
            _genai().aio.models.generate_content(
                model=MODEL,
                contents=_draft_prompt(corpus, situation, infraction_type, severity),
            ),
            timeout=_GEMINI_TIMEOUT,
        )
        data = _parse_json(getattr(resp, "text", "") or "")
    except Exception:
        logger.exception("[discipline_ai] draft generation failed")
        return {
            "description": "",
            "expected_improvement": "",
            "suggested_infraction_type": infraction_type,
            "suggested_severity": severity,
            "evidence_map": [],
            "dropped_citations": [],
            "concerns": [],
            "available": False,
        }

    evidence_map, dropped = validate_citations(data.get("evidence_map") or [], index)
    if dropped:
        logger.warning("[discipline_ai] dropped %d hallucinated citations: %s", len(dropped), dropped)

    return {
        "description": str(data.get("description") or "").strip()[:_TEXT_CAP],
        "expected_improvement": str(data.get("expected_improvement") or "").strip()[:_TEXT_CAP],
        "suggested_infraction_type": data.get("suggested_infraction_type") or infraction_type,
        "suggested_severity": data.get("suggested_severity") or severity,
        "evidence_map": evidence_map,
        "dropped_citations": dropped,
        "concerns": [str(c) for c in (data.get("concerns") or []) if c][:6],
        "available": True,
    }


# ── Final review ────────────────────────────────────────────────────────

_REVIEW_RULES = """
You are reviewing for LEGAL RISK IN THE WRITING, not deciding legality. A deterministic
statutory gate has already run and its verdict is given to you below — do not re-litigate
it, do not contradict it, and do not declare the action lawful or unlawful.

Flag only concrete, actionable problems in THIS text:
- The letter treats protected activity (leave, a complaint, an incident report) as
  misconduct or as part of the pattern justifying escalation.
- The letter asserts facts nowhere in the corpus or the HR account.
- `expected_improvement` is vague, unmeasurable, or impossible to satisfy.
- Tone attacks the person rather than describing conduct — reads as pretext.
- The stated basis doesn't actually support the discipline level chosen.

Say nothing if the text is clean. An advisory nobody needs trains HR to click through
all of them, including the one that mattered.

Return STRICT JSON, no markdown fence:
{"advisories": [{"detail": "<specific problem + how to fix it>", "cited_ids": ["..."]}]}
"""


async def review_final_text(
    conn, *, company_id: UUID, employee_id: UUID,
    situation: Optional[str], description: Optional[str],
    expected_improvement: Optional[str], infraction_type: str, severity: str,
    discipline_type: str, deterministic_verdict: dict[str, Any],
) -> list[dict[str, Any]]:
    """Soft-risk review of the final text. Returns advisories. Never raises."""
    if not (description or "").strip() and not (expected_improvement or "").strip():
        return []

    try:
        corpus, index = await build_draft_corpus(
            conn, company_id=company_id, employee_id=employee_id, infraction_type=infraction_type,
        )
    except Exception:
        logger.exception("[discipline_ai] final review corpus build failed")
        return [{
            "code": "ai_review_unavailable",
            "detail": (
                "The AI writing review could not run. The statutory compliance check "
                "DID run and its result stands — this only means the letter text was "
                "not reviewed for tone and documentation gaps."
            ),
        }]

    prompt = f"""You are an employment-law risk reviewer reading a corrective-action letter
that HR is about to issue.

THE ONLY RECORDS YOU MAY CITE:
{_render_corpus(corpus)}

DETERMINISTIC COMPLIANCE VERDICT (already computed — authoritative, not yours to revise):
{json.dumps({"blocks": deterministic_verdict.get("blocks"), "advisories": [a.get("code") for a in deterministic_verdict.get("advisories") or []]}, default=str)[:2000]}

THE ACTION: {discipline_type} | infraction={infraction_type} | severity={severity}

WHAT HR SAYS HAPPENED:
{(situation or "(not provided)")[:_TEXT_CAP]}

FINAL LETTER TEXT — "What occurred":
{(description or "(empty)")[:_TEXT_CAP]}

FINAL LETTER TEXT — "Expected improvement":
{(expected_improvement or "(empty)")[:_TEXT_CAP]}
{_REVIEW_RULES}"""

    try:
        resp = await asyncio.wait_for(
            _genai().aio.models.generate_content(model=MODEL, contents=prompt),
            timeout=_GEMINI_TIMEOUT,
        )
        data = _parse_json(getattr(resp, "text", "") or "")
    except Exception:
        logger.exception("[discipline_ai] final review failed")
        return [{
            "code": "ai_review_unavailable",
            "detail": (
                "The AI writing review could not run. The statutory compliance check "
                "DID run and its result stands — this only means the letter text was "
                "not reviewed for tone and documentation gaps."
            ),
        }]

    raw = data.get("advisories") or []
    clean, dropped = validate_citations(
        [{"point": str(a.get("detail") or ""), "cited_ids": a.get("cited_ids") or []}
         for a in raw if isinstance(a, dict)],
        index,
    )
    if dropped:
        logger.warning("[discipline_ai] review dropped %d hallucinated citations", len(dropped))

    return [
        {"code": "ai_review", "detail": item["point"], "cited_ids": item["cited_ids"]}
        for item in clean if item["point"].strip()
    ][:6]
