"""Huume ER (employee-relations) bridge — first consumer of the "generally"
part of the discovery pattern: a broad ask like "I have this ER situation…"
routes to the `deep` tier via `ask_er_copilot`'s registered `intent_hints`
(routing.py), with zero routing code written for this skill specifically.

Two tools, mirroring `legal_skill.py`'s split exactly:
  - `case_brief` — read-only, no Gemini. A name-free summary built from
    STORED rows (`er_cases` / `er_case_documents` / `er_case_analysis`).
  - `ask_case` — the deep tool. One grounded Gemini call over the case's
    document excerpts + stored analyses + jurisdiction requirements
    (reusing `services/er/er_case_context.py` + `er_compliance_grounding`,
    the SAME material `/er/cases` guidance endpoints ground on), citation-
    gated by the shared `validate_citations` anti-hallucination gate.

Same split as `legal_skill`/`onboarding_skill`: `actions.evaluate_pilot_tool`
owns the authz/feature envelope (re-asserting the `/er/cases` mount's own
`require_admin_or_client` + `require_feature("er_copilot")`, since the skill
engine gates nothing itself) — everything here assumes it already passed.
"""

from __future__ import annotations

import asyncio
import json
import logging
from datetime import datetime, timezone
from typing import Any, Optional
from uuid import UUID

from app.config import get_settings
from app.core.services.ai_usage import feature_scope

from .._shared.citations import _parse_json, validate_citations
from .._shared.gemini import _genai

logger = logging.getLogger(__name__)

_GEMINI_TIMEOUT = 60
_DOC_LIST_CAP = 20
_DOC_SUMMARY_CHARS = 200

_ASK_RULES = """
You are answering a question about ONE employee-relations (ER) case using
only the records shown to you below. You are NOT a lawyer and this is NOT
legal advice — you are relaying what the company's own records show.

Rules:
- Cite ONLY records shown to you, and copy the id inside the brackets
  VERBATIM, prefix included. A record shown as [ercase:doc-<uuid>] is cited
  as "ercase:doc-<uuid>", never the bare uuid. An id that doesn't match a
  record exactly is dropped and the claim it supported disappears with it.
- A claim with no supporting [cid] will be dropped before anyone sees it —
  don't bother making one.
- If the records don't answer the question, say so plainly in `answer`
  rather than guessing or filling the gap with general knowledge.

Return STRICT JSON, no markdown fence:
{
  "answer": "<your answer, in plain prose>",
  "evidence": [
    {"point": "<the specific claim in your answer this supports>",
     "cited_ids": ["<full bracketed id(s)>"]}
  ]
}
"""


def _resolve_cid(cid: str, index: dict[str, Any]) -> str:
    """Repair a bare id missing its namespace prefix — same fix
    discipline_policy_check applies, for the same observed failure mode:
    the corpus renders `[ercase:doc-<uuid>]`, the model answers with the
    bare `<uuid>`, and a naive gate would drop a citation the model actually
    grounded correctly. Only rewrites when EXACTLY ONE index key ends with
    `:<id>` — an unknown or ambiguous id is left untouched for
    `validate_citations` to drop."""
    if cid in index:
        return cid
    suffix = f":{cid}"
    matches = [key for key in index if key.endswith(suffix)]
    return matches[0] if len(matches) == 1 else cid


def _citation_records(cids: list[str], index: dict[str, Any]) -> list[dict[str, Any]]:
    """Resolve validated cids to the FE-renderable shape
    `components/ui/CitationSources.tsx` expects — same contract
    `legal_skill._citation_records` returns. Pure."""
    out: list[dict[str, Any]] = []
    seen: set[str] = set()
    for cid in cids or []:
        rec = (index or {}).get(cid)
        if not rec or cid in seen:
            continue
        seen.add(cid)
        out.append({
            "cid": cid,
            "ref": rec.get("ref") or cid,
            "summary": rec.get("summary") or "",
            "when": rec.get("when") or "",
            "source": rec.get("source") or "",
            "source_label": rec.get("source_label") or "",
        })
    return out


def _law_citation_record(cid: str, rec: dict[str, Any]) -> dict[str, Any]:
    """Normalize an `er_compliance_grounding` requirement record (title /
    description / statute_citation / state / category) into the shared
    citation shape the rest of this module and
    `components/ui/CitationSources.tsx` use (ref / summary / source_label).
    Pure; tolerates a missing key rather than raising, since the corpus
    builder owns that shape and may grow fields."""
    state = (rec.get("state") or "").strip()
    category = (rec.get("category") or "").strip().replace("_", " ")
    label = " · ".join(p for p in (state, category) if p) or "Jurisdiction requirement"
    return {
        "cid": cid,
        "ref": rec.get("title") or cid,
        "summary": rec.get("description") or "",
        "when": rec.get("statute_citation") or "",
        "source": "jurisdiction_requirement",
        "source_label": label,
        "source_url": rec.get("source_url"),
    }


def _analysis_headline(data: dict[str, Any]) -> str:
    """Structural 1-line summary of a stored `er_case_analysis` row for
    `case_brief` — a COUNT of whatever the analysis found, never its stored
    free text. `case_brief`'s own contract (and its tool description) is
    name-free: analysis rows are model-authored prose over this case's
    documents (timeline, discrepancies, retaliation risk) and routinely name
    the parties involved. Do NOT reuse this for `ask_case`'s grounding
    corpus — that tool is the admin-facing, `er_copilot`-gated deep read and
    is SUPPOSED to see real analysis content; use
    `_analysis_corpus_summary` there instead. Pure."""
    if not isinstance(data, dict):
        return "Analysis on file."
    for key, value in data.items():
        if isinstance(value, list) and value:
            return f"{len(value)} {key.replace('_', ' ')} on file."
    return "Analysis on file."


def _analysis_corpus_summary(data: dict[str, Any]) -> str:
    """Best-effort 1-line summary of a stored `er_case_analysis` row for
    `ask_case`'s grounding corpus — unlike `_analysis_headline`, this is
    allowed to (and meant to) carry real analysis content, since answering
    "what did the timeline analysis find?" is the entire point of the tool.
    The analyzer's per-type JSON shape isn't rigidly fixed, so this degrades
    gracefully rather than assuming a schema. Pure."""
    if not isinstance(data, dict):
        return "Analysis on file."
    summary = data.get("summary") or data.get("overview")
    if isinstance(summary, str) and summary.strip():
        return summary.strip()[:200]
    for key, value in data.items():
        if isinstance(value, list) and value:
            return f"{len(value)} {key.replace('_', ' ')} on file."
    return "Analysis on file."


async def case_brief(*, company_id: UUID, case_id: str) -> dict[str, Any]:
    """Model-facing read tool, no Gemini call. Name-free: reports counts and
    the case's OWN title/category (not a legal-record restriction — the same
    fields lookup_context(topic='er_cases') already returns), never the
    involved employees' names or the case description/narrative."""
    from app.database import get_connection

    try:
        cid = UUID(str(case_id))
    except (ValueError, TypeError):
        return {"status": "error", "message": "That case id doesn't look valid."}

    async with get_connection() as conn:
        case = await conn.fetchrow(
            "SELECT id, case_number, title, status, category, created_at, involved_employees "
            "FROM er_cases WHERE id = $1 AND company_id = $2",
            cid, company_id,
        )
        if not case:
            return {"status": "not_found", "message": "I don't see that ER case for this company."}

        from app.matcha.services.er.er_case_context import normalize_json_list
        involved_count = len(normalize_json_list(case["involved_employees"]))

        doc_rows = await conn.fetch(
            "SELECT id, filename, document_type FROM er_case_documents "
            "WHERE case_id = $1 ORDER BY created_at DESC LIMIT $2",
            cid, _DOC_LIST_CAP,
        )
        analysis_rows = await conn.fetch(
            "SELECT analysis_type, analysis_data, generated_at FROM er_case_analysis WHERE case_id = $1",
            cid,
        )
        notes_count = await conn.fetchval(
            "SELECT COUNT(*) FROM er_case_notes WHERE case_id = $1", cid,
        ) or 0

    analyses: dict[str, Any] = {}
    for r in analysis_rows:
        raw = r["analysis_data"]
        try:
            data = json.loads(raw) if isinstance(raw, str) else dict(raw or {})
        except (ValueError, TypeError):
            data = {}
        analyses[r["analysis_type"]] = {
            "generated_at": r["generated_at"].isoformat() if r.get("generated_at") else None,
            "headline": _analysis_headline(data),
        }

    created_at = case["created_at"]
    open_days = None
    if created_at:
        # er_cases.created_at is a naive TIMESTAMP column (no tz) — asyncpg
        # hands back a naive datetime, which can't be subtracted from an
        # aware `now()`. Assume UTC, the column's actual write-time zone
        # (every writer uses `datetime.now(timezone.utc)` / DB `NOW()` under
        # UTC session settings).
        aware_created_at = created_at if created_at.tzinfo else created_at.replace(tzinfo=timezone.utc)
        open_days = (datetime.now(timezone.utc) - aware_created_at).days

    return {
        "status": "ok",
        "case_id": str(case["id"]),
        "case_number": case["case_number"],
        "title": case["title"],
        "case_status": case["status"],
        "category": case["category"],
        "created_at": created_at.isoformat() if created_at else None,
        "involved_count": involved_count,
        "documents": [
            {"id": str(r["id"]), "filename": r["filename"], "document_type": r["document_type"]}
            for r in doc_rows
        ],
        "analyses": analyses,
        "notes_count": notes_count,
        "open_days": open_days,
    }


async def _resolve_case(conn, company_id: UUID, requested: Optional[str], fallback_id: Optional[str]):
    """Explicit case_id → the thread's active case (`current_state.huume_er`)
    → a refusal naming both options. Returns (case_row, error) mirroring
    `legal_skill.resolve_matter`'s shape."""
    candidate = requested or fallback_id
    if not candidate:
        return None, (
            "I don't have an ER case in mind — call er_case_brief with a case_id first, "
            "or name which case you mean."
        )
    try:
        cid = UUID(str(candidate))
    except (ValueError, TypeError):
        return None, f"'{candidate}' isn't a case id — call er_case_brief or name the case another way."
    case = await conn.fetchrow(
        "SELECT id, case_number, title, involved_employees FROM er_cases WHERE id = $1 AND company_id = $2",
        cid, company_id,
    )
    if not case:
        return None, "No ER case with that id exists for this company."
    return case, None


async def ask_case(
    *, company_id: UUID, actor_user_id: Optional[UUID],
    case_id: Optional[str], state_case_id: Optional[str], question: str,
) -> dict[str, Any]:
    """The deep tool: one grounded Gemini call over the case's document
    excerpts + stored analyses + jurisdiction requirements. Never raises —
    degrades to `{"status": "error", ...}` on any Gemini/grounding failure,
    same idiom as `discipline_policy_check`/`legal_skill.ask_matter`."""
    from app.core.services.audit_log import insert_audit_log
    from app.database import get_connection
    from app.matcha.services.er import er_compliance_grounding
    from app.matcha.services.er.er_case_context import (
        build_document_excerpts, load_guidance_context, normalize_json_list,
    )

    question = (question or "").strip()
    if not question:
        return {"status": "error", "message": "Ask a question about the ER case."}

    async with get_connection() as conn:
        case, err = await _resolve_case(conn, company_id, case_id, state_case_id)
        if err:
            return {"status": "error", "message": err}

        # A grounded AI read over an ER case's own documents/analyses is a
        # records-sensitive action on the same surface `/er/cases` audit-logs
        # every analysis run on (see routes/er_copilot/analysis.py's
        # `log_audit` calls) — leaving nothing behind here just because the
        # request came from chat would be a silent gap in that trail.
        await insert_audit_log(
            conn, table="er_audit_log", id_column="case_id", id_value=case["id"],
            user_id=actor_user_id, action="huume_ask_er_copilot", entity_type="er_case",
            entity_id=case["id"], details={"via": "huume", "question": question[:500]},
        )

        try:
            ctx = await load_guidance_context(conn, case["id"], case)
            involved_ids = [
                e["employee_id"] for e in normalize_json_list(case["involved_employees"])
                if isinstance(e, dict) and e.get("employee_id")
            ]
            _law_text, law_index, law_truncated = await er_compliance_grounding.build_jurisdiction_corpus(
                conn, company_id, involved_ids,
            )
        except Exception:
            logger.exception("[huume/er_skill] failed to build grounding for case %s", case["id"])
            return {"status": "error", "message": "Couldn't gather this case's records right now — try again shortly."}

        analysis_rows = await conn.fetch(
            "SELECT analysis_type, analysis_data, generated_at FROM er_case_analysis WHERE case_id = $1",
            case["id"],
        )

    # Build the citation index BEFORE releasing the connection's data (the
    # rows are already in memory) — the connection itself is released here,
    # never held across the Gemini call below (ask_matter's own rule).
    #
    # The case's OWN records, in the shared FE citation shape
    # (components/ui/CitationSources.tsx: cid/ref/summary/...). Kept separate
    # from the law records below because only these are rendered into the
    # "AVAILABLE RECORDS" block — `_law_text` renders the law itself.
    case_index: dict[str, Any] = {}
    for r in ctx["all_doc_text_rows"]:
        case_index[f"ercase:doc-{r['id']}"] = {
            "cid": f"ercase:doc-{r['id']}",
            "ref": r["filename"], "summary": (r["scrubbed_text"] or "")[:_DOC_SUMMARY_CHARS],
            "source": "er_case_document", "source_label": "Case document",
        }
    for r in analysis_rows:
        raw = r["analysis_data"]
        try:
            data = json.loads(raw) if isinstance(raw, str) else dict(raw or {})
        except (ValueError, TypeError):
            data = {}
        cid = f"ercase:analysis-{r['analysis_type']}"
        case_index[cid] = {
            "cid": cid,
            "ref": r["analysis_type"].replace("_", " ").title(),
            "summary": _analysis_corpus_summary(data),
            "source": "er_case_analysis", "source_label": "Case analysis",
        }

    # `er_compliance_grounding`'s index records carry title/description/
    # statute_citation — NOT the ref/summary this module and the citation
    # renderer use. Normalize on the way in: reading `rec['ref']` off a raw
    # law record raised KeyError for every company that actually HAS codified
    # requirements (the exact companies this grounding exists for), and the
    # `.get()`-based citation builder silently rendered them titleless.
    index: dict[str, Any] = {
        cid: _law_citation_record(cid, rec) for cid, rec in (law_index or {}).items()
    }
    index.update(case_index)

    if not index:
        return {
            "status": "ok", "case_id": str(case["id"]), "case_number": case["case_number"],
            "answer": "There's nothing on this case yet to ground an answer in — no documents, "
                      "analyses, or applicable jurisdiction requirements on file.",
            "citations": [], "dropped_citations": [], "truncated_grounding": False,
        }

    corpus_lines = [f"[{cid}] {rec['ref']}: {rec['summary']}" for cid, rec in case_index.items()]
    doc_text = build_document_excerpts(ctx["all_doc_text_rows"], text_key="scrubbed_text")
    # `_law_text` (not the index) is the only rendering that carries each
    # obligation's statute citation and the truncation note — dropping it, as
    # this did originally, meant the jurisdiction grounding the tool
    # advertises never actually reached the model.
    prompt = f"""{_ASK_RULES}

CASE: {case['title'] or case['case_number']}

AVAILABLE RECORDS
{chr(10).join(corpus_lines) or '(no case documents or analyses on file)'}

APPLICABLE JURISDICTION REQUIREMENTS
{_law_text or '(no codified requirements resolved for this company)'}

DOCUMENT TEXT
{doc_text or '(no document text on file)'}

QUESTION
{question}
"""

    # Same model `build_er_analyzer()` resolves for the standalone ER
    # Copilot page (settings.analysis_model) — a hardcoded literal here would
    # let the two surfaces silently diverge on model. Deliberately NOT
    # routed through ERAnalyzer._generate_content_async itself: that method
    # retries same-model on timeout and falls back across models, up to
    # 2x its own 120s call timeout BEFORE trying a fallback — worse-case
    # latency Huume's shared per-turn wall clock (300s across every tool
    # call in the turn) can't absorb. Single bounded attempt instead, same
    # shape as discipline_policy_check's and legal_defense's own Gemini
    # calls from inside the Huume/pilot-bridge tools.
    model = get_settings().analysis_model
    try:
        with feature_scope("matcha.huume.er_copilot"):
            resp = await asyncio.wait_for(
                _genai().aio.models.generate_content(model=model, contents=prompt),
                timeout=_GEMINI_TIMEOUT,
            )
        data = _parse_json(getattr(resp, "text", "") or "")

        # `_parse_json` returns {} for BOTH "empty reply" and "unparseable
        # reply". Falling through with {} would return status ok + an empty
        # answer, which the model reads as "the records say nothing about
        # this" and relays as a finding — a formatting failure must surface
        # as a failure, not as a grounded negative answer.
        answer = str(data.get("answer") or "").strip()
        if not answer:
            logger.warning(
                "[huume/er_skill] ask_case got an unparseable/answerless reply for case %s", case["id"],
            )
            return {
                "status": "error",
                "message": "I couldn't read the analysis back for that case — try asking again.",
            }

        # Kept inside the same try as the Gemini call — see
        # discipline_policy_check's identical comment: `data` is untrusted
        # model output, and this function's docstring promises it never
        # raises past a degraded {"status": "error"}.
        raw_evidence = data.get("evidence") or []
        for item in raw_evidence:
            if isinstance(item, dict):
                item["cited_ids"] = [
                    _resolve_cid(str(c), index) for c in (item.get("cited_ids") or []) if isinstance(c, (str, int))
                ]
        clean_map, dropped = validate_citations(raw_evidence, index)
        cited = [c for item in clean_map for c in (item.get("cited_ids") or [])]
    except Exception:
        logger.exception("[huume/er_skill] ask_case Gemini call failed for case %s", case["id"])
        return {"status": "error", "message": "The analysis is unavailable right now — try again shortly."}

    return {
        "status": "ok",
        "case_id": str(case["id"]),
        "case_number": case["case_number"],
        "answer": answer[:4000],
        "citations": cited,
        "dropped_citations": dropped,
        "truncated_grounding": bool(law_truncated),
        "citation_records": _citation_records(cited, index),
    }
