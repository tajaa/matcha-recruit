"""Legal Defense builder — litigation-readiness evidence assembly.

For full-platform (Pro) SMBs that lack in-house counsel: when a legal stressor
hits (subpoena / class action / EEOC / audit), this assembles the company's OWN
records — already in Matcha across IR/OSHA, ER, compliance, discipline, training,
handbooks, accommodations + the immutable ``*_audit_log`` trails — into an
attorney-facing evidence packet. The win is cutting the hourly cost their outside
counsel would spend reconstructing the factual record.

Framing is deliberate: the AI is an **organizer, not an advocate**. It surfaces
WHAT THE RECORDS SHOW and flags gaps as open questions; it renders no verdict and
no liability opinion (a company-authored "we did nothing wrong" memo is
discoverable + unprivileged and can help a plaintiff). Grounding is enforced:
the model may cite only record IDs from the retrieved corpus, and
``validate_citations`` drops any hallucinated ID; the PDF appendix is rendered
deterministically from DB rows, never from model text.

Reuses ``claims_readiness`` (per-record IR/ER builders + PDF style),
``core.services.pdf.safe_url_fetcher`` (SSRF-guarded WeasyPrint), and
``core.services.storage`` (S3 fetch for the ZIP bundle). Never raises on the
read/gather path — a dead subsystem degrades to "unavailable", never a 500.
"""

import asyncio
import io
import json
import logging
import zipfile
from datetime import datetime, timezone
from uuid import UUID

from app.config import get_settings
from app.core.compliance_registry import CATEGORY_KEYS
from app.core.services.genai_client import get_genai_client
from app.core.services.pdf import safe_url_fetcher
from app.core.services.storage import get_storage

from .claims_readiness import (
    build_er_packet,
    build_incident_packet,
    _PDF_CSS,
    _esc,
    _fmt_dt,
)

logger = logging.getLogger(__name__)

MODEL = "gemini-3-flash-preview"
_GEMINI_TIMEOUT = 90
_PER_SOURCE_CAP = 100
_HISTORY_TURNS = 12

DISCLAIMER = (
    "Prepared from system records to assist counsel. Reflects records on file as "
    "of generation. This is an evidence-assembly aid, not legal advice and not a "
    "legal conclusion; attorney review is required."
)

_client = None


def _genai():
    global _client
    if _client is None:
        _client = get_genai_client()
    return _client


def _parse_json(text: str) -> dict:
    """Parse a Gemini JSON reply, tolerating ```json fences / surrounding prose."""
    if not text:
        return {}
    t = text.strip()
    if t.startswith("```"):
        t = t.split("```", 2)[1] if t.count("```") >= 2 else t.strip("`")
        if t.lstrip().lower().startswith("json"):
            t = t.lstrip()[4:]
    t = t.strip()
    # Fall back to the outermost {...} if there's leading/trailing prose.
    if not t.startswith("{"):
        i, j = t.find("{"), t.rfind("}")
        if i != -1 and j != -1 and j > i:
            t = t[i : j + 1]
    try:
        out = json.loads(t)
        return out if isinstance(out, dict) else {}
    except Exception:
        return {}


# --------------------------------------------------------------------------- #
# Evidence gathering — one query per subsystem, each independently isolated.
# Compact {cid, ref, summary, when} records feed the AI; full detail (IR/ER) is
# pulled at packet time for the deterministic appendix.
# --------------------------------------------------------------------------- #

def _dt(v) -> str:
    return _fmt_dt(v)


def _hum(s) -> str:
    """Humanize a raw db enum/snake_case value for display — 'in_review' ->
    'In Review'. Feeds both the AI corpus text and the PDF, so the model's
    own summaries read cleanly too, not just the deterministic rendering."""
    if not s:
        return ""
    return str(s).replace("_", " ").replace("-", " ").strip().title()


async def resolve_matter_jurisdiction(conn, matter: dict) -> dict | None:
    """Resolve a matter's governing jurisdiction chain (federal → state → …)
    from its location or state override. Returns None when neither is set —
    callers treat that as "no jurisdiction grounding available", not an error.

    Deliberately NOT ``compliance_service.resolve_jurisdiction_stack`` — that
    CTE drags every requirement row along; this only needs the chain."""
    loc = None
    jid = None
    state = (matter.get("jurisdiction_state") or "").upper() or None
    if matter.get("location_id"):
        loc = await conn.fetchrow(
            "SELECT jurisdiction_id, name, state FROM business_locations "
            "WHERE id = $1 AND company_id = $2",
            matter["location_id"], matter["company_id"],
        )
        if loc:
            jid = loc["jurisdiction_id"]
            state = state or ((loc["state"] or "").upper() or None)
    if jid is None and state:
        row = await conn.fetchrow(
            "SELECT id FROM jurisdictions WHERE state = $1 AND level = 'state' "
            "AND country_code = 'US' LIMIT 1",
            state,
        )
        jid = row["id"] if row else None
    if jid is None:
        return None
    chain = await conn.fetch(
        """WITH RECURSIVE chain AS (
             SELECT id, parent_id, level, display_name, 0 AS depth
             FROM jurisdictions WHERE id = $1
             UNION ALL
             SELECT j.id, j.parent_id, j.level, j.display_name, c.depth + 1
             FROM jurisdictions j JOIN chain c ON j.id = c.parent_id
             WHERE c.depth < 6)
           SELECT id, level, display_name FROM chain ORDER BY depth""",
        jid,
    )
    return {
        "jurisdiction_id": jid,
        "chain": [dict(r) for r in chain],
        "state": state,
        "location_name": loc["name"] if loc else None,
    }


async def _src_incidents(conn, company_id, start, end) -> list[dict]:
    rows = await conn.fetch(
        """
        SELECT id, incident_number, title, incident_type, severity, status, occurred_at
        FROM ir_incidents
        WHERE company_id = $1
          AND ($2::date IS NULL OR occurred_at >= $2)
          AND ($3::date IS NULL OR occurred_at < ($3::date + 1))
        ORDER BY occurred_at DESC NULLS LAST
        """,
        company_id, start, end,
    )
    return [{
        "cid": f"incident:{r['id']}",
        "ref": r["incident_number"],
        "summary": f"{r['title']} — type {_hum(r['incident_type'])}, severity {_hum(r['severity'])}, status {_hum(r['status'])}",
        "when": _dt(r["occurred_at"]),
    } for r in rows]


async def _src_er_cases(conn, company_id, start, end) -> list[dict]:
    rows = await conn.fetch(
        """
        SELECT id, case_number, title, category, status, outcome, created_at
        FROM er_cases
        WHERE company_id = $1
          AND ($2::date IS NULL OR created_at >= $2)
          AND ($3::date IS NULL OR created_at < ($3::date + 1))
        ORDER BY created_at DESC NULLS LAST
        """,
        company_id, start, end,
    )
    return [{
        "cid": f"er_case:{r['id']}",
        "ref": r["case_number"],
        "summary": f"{r['title']} — {_hum(r['category'])}, status {_hum(r['status'])}"
                   + (f", outcome {_hum(r['outcome'])}" if r["outcome"] else ""),
        "when": _dt(r["created_at"]),
    } for r in rows]


async def _src_compliance(conn, company_id, start, end) -> list[dict]:
    # Current requirement state per location = proof of what the company tracks /
    # the protocol it follows. Joined via business_locations (requirements carry
    # location_id, not company_id). Not date-filtered — it's current posture.
    rows = await conn.fetch(
        """
        SELECT cr.id, cr.title, cr.category, cr.current_value, cr.jurisdiction_name,
               cr.last_changed_at, bl.name AS location_name, jr.statute_citation
        FROM compliance_requirements cr
        JOIN business_locations bl ON bl.id = cr.location_id
        LEFT JOIN jurisdiction_requirements jr ON jr.id = cr.jurisdiction_requirement_id
        WHERE bl.company_id = $1
        ORDER BY cr.last_changed_at DESC NULLS LAST
        """,
        company_id,
    )
    return [{
        "cid": f"compliance_req:{r['id']}",
        "ref": _hum(r["category"]),
        "summary": f"{r['title']}"
                   + (f" = {r['current_value']}" if r["current_value"] else "")
                   + (f" ({r['jurisdiction_name']})" if r["jurisdiction_name"] else "")
                   + (f" @ {r['location_name']}" if r["location_name"] else "")
                   + (f" [{r['statute_citation']}]" if r["statute_citation"] else ""),
        "when": _dt(r["last_changed_at"]),
    } for r in rows]


async def _src_discipline(conn, company_id, start, end) -> list[dict]:
    rows = await conn.fetch(
        """
        SELECT id, discipline_type, infraction_type, severity, status, issued_date
        FROM progressive_discipline
        WHERE company_id = $1
          AND ($2::date IS NULL OR issued_date >= $2)
          AND ($3::date IS NULL OR issued_date < ($3::date + 1))
        ORDER BY issued_date DESC NULLS LAST
        """,
        company_id, start, end,
    )
    return [{
        "cid": f"discipline:{r['id']}",
        "ref": _hum(r["discipline_type"]),
        "summary": f"{_hum(r['discipline_type'])}"
                   + (f" for {_hum(r['infraction_type'])}" if r["infraction_type"] else "")
                   + (f", severity {_hum(r['severity'])}" if r["severity"] else "")
                   + f", status {_hum(r['status'])}",
        "when": _dt(r["issued_date"]),
    } for r in rows]


async def _src_training(conn, company_id, start, end) -> list[dict]:
    rows = await conn.fetch(
        """
        SELECT id, title, training_type, status, completed_date, expiration_date
        FROM training_records
        WHERE company_id = $1
          AND ($2::date IS NULL OR COALESCE(completed_date, created_at) >= $2)
          AND ($3::date IS NULL OR COALESCE(completed_date, created_at) < ($3::date + 1))
        ORDER BY completed_date DESC NULLS LAST
        """,
        company_id, start, end,
    )
    return [{
        "cid": f"training:{r['id']}",
        "ref": _hum(r["training_type"]) or "Training",
        "summary": f"{r['title']} — status {_hum(r['status'])}"
                   + (f", expires {_dt(r['expiration_date'])}" if r["expiration_date"] else ""),
        "when": _dt(r["completed_date"]),
    } for r in rows]


async def _src_policy_ack(conn, company_id, start, end) -> list[dict]:
    rows = await conn.fetch(
        """
        SELECT ps.id, ps.signer_name, ps.signed_at, p.title AS policy_title
        FROM policy_signatures ps
        JOIN policies p ON p.id = ps.policy_id
        WHERE p.company_id = $1 AND ps.status = 'signed'
          AND ($2::date IS NULL OR ps.signed_at >= $2)
          AND ($3::date IS NULL OR ps.signed_at < ($3::date + 1))
        ORDER BY ps.signed_at DESC NULLS LAST
        """,
        company_id, start, end,
    )
    return [{
        "cid": f"policy_ack:{r['id']}",
        "ref": "policy acknowledgment",
        "summary": f"{r['policy_title'] or 'Policy'} acknowledged by {r['signer_name'] or 'employee'}",
        "when": _dt(r["signed_at"]),
    } for r in rows]


async def _src_accommodations(conn, company_id, start, end) -> list[dict]:
    rows = await conn.fetch(
        """
        SELECT id, case_number, title, status, disability_category, created_at
        FROM accommodation_cases
        WHERE org_id = $1
          AND ($2::date IS NULL OR created_at >= $2)
          AND ($3::date IS NULL OR created_at < ($3::date + 1))
        ORDER BY created_at DESC NULLS LAST
        """,
        company_id, start, end,
    )
    return [{
        "cid": f"accommodation:{r['id']}",
        "ref": r["case_number"],
        "summary": f"{r['title']} — {_hum(r['disability_category'])}, status {_hum(r['status'])}",
        "when": _dt(r["created_at"]),
    } for r in rows]


async def _src_compliance_alerts(conn, company_id, start, end) -> list[dict]:
    # Date-filtered (unlike _src_compliance's current-posture snapshot) — this
    # is deliberately a history: it shows the company was monitoring during
    # the matter window, not just what it tracks today.
    rows = await conn.fetch(
        """
        SELECT ca.id, ca.title, ca.severity, ca.status, ca.category, ca.deadline,
               ca.created_at, bl.name AS location_name
        FROM compliance_alerts ca
        JOIN business_locations bl ON bl.id = ca.location_id
        WHERE ca.company_id = $1
          AND ($2::date IS NULL OR ca.created_at >= $2)
          AND ($3::date IS NULL OR ca.created_at < ($3::date + 1))
        ORDER BY ca.created_at DESC
        """,
        company_id, start, end,
    )
    return [{
        "cid": f"compliance_alert:{r['id']}",
        "ref": _hum(r["category"]) or "Alert",
        "summary": f"{r['title']} — {_hum(r['severity'])}, {_hum(r['status'])}"
                   + (f", deadline {_dt(r['deadline'])}" if r["deadline"] else "")
                   + (f" @ {r['location_name']}" if r["location_name"] else ""),
        "when": _dt(r["created_at"]),
    } for r in rows]


# --------------------------------------------------------------------------- #
# Matter-scoped external legal context — jurisdiction, governing requirements,
# pending legislation, and externally-researched case law. Only populated
# when the matter carries a location/state (see resolve_matter_jurisdiction).
# --------------------------------------------------------------------------- #

_WAGE_HOUR = ["minimum_wage", "overtime", "meal_breaks", "pay_frequency", "final_pay",
              "scheduling_reporting", "sick_leave", "leave", "employee_classification",
              "equal_pay", "pay_transparency"]
_EEO = ["anti_discrimination", "equal_pay", "pregnancy_accommodation", "eeo_reporting",
        "background_checks", "pay_transparency", "whistleblower"]

# Matter type -> compliance categories most relevant to that theory of the
# case. None = no category filter (pull broadly across the jurisdiction).
_MATTER_TYPE_CATEGORIES: dict[str, list[str] | None] = {
    "class_action": _WAGE_HOUR,
    "single_plaintiff": _WAGE_HOUR,
    "eeoc_charge": _EEO,
    "subpoena": None,
    "audit": None,
    "other": None,
}
assert all(
    k in CATEGORY_KEYS for ks in _MATTER_TYPE_CATEGORIES.values() if ks for k in ks
), "legal_defense._MATTER_TYPE_CATEGORIES references a category not in the compliance registry"


async def _gather_law(conn, matter: dict, juris: dict) -> tuple[dict | None, dict | None]:
    """Governing requirements + pending legislation for the matter's
    jurisdiction chain, filtered to the matter type's relevant categories
    when possible. Returns ``(law_source, legislation_source)``, each shaped
    like an existing evidence source (``{"label", "records"}``) or None."""
    jurisdiction_ids = [c["id"] for c in juris["chain"]]
    categories = _MATTER_TYPE_CATEGORIES.get(matter.get("matter_type"))
    rows = None

    if get_settings().gemini_api_key and matter.get("allegation"):
        try:
            from app.core.services.compliance_rag import ComplianceRAGService
            from app.core.services.embedding_service import EmbeddingService

            es = EmbeddingService(api_key=get_settings().gemini_api_key)
            rag = ComplianceRAGService(es)
            query = f"{matter.get('allegation') or ''} {_hum(matter.get('matter_type'))}"
            hits = await rag.search_requirements(
                query=query, conn=conn, jurisdiction_ids=jurisdiction_ids,
                categories=categories, top_k=30, min_similarity=0.25,
            )
            if hits:
                rows = [{
                    "requirement_id": h["requirement_id"], "title": h["title"],
                    "category": h["category"], "current_value": h.get("current_value"),
                    "statute_citation": h.get("statute_citation"),
                    "effective_date": h.get("effective_date"),
                    "jurisdiction_level": h.get("jurisdiction_level"),
                    "jurisdiction_name": h.get("jurisdiction_name"),
                } for h in hits]
        except Exception as e:  # noqa: BLE001 — fall through to direct query
            logger.warning("legal_defense: RAG law retrieval unavailable: %s", e)

    if rows is None:
        rows = await conn.fetch(
            """
            SELECT id, title, category, current_value, statute_citation, effective_date,
                   jurisdiction_level, jurisdiction_name
            FROM jurisdiction_requirements
            WHERE jurisdiction_id = ANY($1::uuid[]) AND status = 'active'
              AND ($2::text[] IS NULL OR category = ANY($2))
            ORDER BY effective_date DESC NULLS LAST LIMIT 40
            """,
            jurisdiction_ids, categories,
        )
        if not rows and categories is not None:
            # A wage-hour category map on a non-wage class action must not
            # blank the source entirely — widen to the full jurisdiction.
            rows = await conn.fetch(
                """
                SELECT id, title, category, current_value, statute_citation, effective_date,
                       jurisdiction_level, jurisdiction_name
                FROM jurisdiction_requirements
                WHERE jurisdiction_id = ANY($1::uuid[]) AND status = 'active'
                ORDER BY effective_date DESC NULLS LAST LIMIT 40
                """,
                jurisdiction_ids,
            )
        rows = [dict(r) for r in rows]

    law_records = [{
        "cid": f"law:{r['requirement_id'] if 'requirement_id' in r else r['id']}",
        "ref": r.get("statute_citation") or _hum(r["category"]),
        "summary": f"{r['title']}"
                   + (f" = {r['current_value']}" if r.get("current_value") else "")
                   + f" ({r.get('jurisdiction_name') or ''}, {_hum(r.get('jurisdiction_level'))})",
        "when": _dt(r.get("effective_date")),
    } for r in rows]
    law_source = {"label": "Governing requirements (jurisdiction)", "records": law_records} if law_records else None

    bill_rows = await conn.fetch(
        """
        SELECT id, title, category, current_status, expected_effective_date, impact_summary
        FROM jurisdiction_legislation
        WHERE jurisdiction_id = ANY($1::uuid[])
        ORDER BY expected_effective_date ASC NULLS LAST LIMIT 15
        """,
        jurisdiction_ids,
    )
    bill_records = [{
        "cid": f"bill:{r['id']}",
        "ref": _hum(r["category"]) or "Legislation",
        "summary": f"{r['title']} — {_hum(r['current_status'])}"
                   + (f": {r['impact_summary'][:160]}" if r["impact_summary"] else ""),
        "when": _dt(r["expected_effective_date"]),
    } for r in bill_rows]
    bill_source = {"label": "Pending legislation (jurisdiction)", "records": bill_records} if bill_records else None

    return law_source, bill_source


async def _gather_case_law(conn, matter_id) -> dict | None:
    """Externally-researched case law from the most recent completed
    ``legal_matter_research`` run (see ``services/legal_research.py``).
    ``case:`` cids are minted only from these persisted CourtListener API
    rows — never from model text."""
    row = await conn.fetchrow(
        """SELECT cases FROM legal_matter_research
             WHERE matter_id = $1 AND status = 'complete' AND cases IS NOT NULL
             ORDER BY created_at DESC LIMIT 1""",
        matter_id,
    )
    if not row or not row["cases"]:
        return None
    cases = row["cases"]
    if isinstance(cases, str):
        try:
            cases = json.loads(cases)
        except Exception:
            return None
    records = [{
        "cid": f"case:{c['id']}",
        "ref": c.get("citation") or c.get("court") or "opinion",
        "summary": f"{c['case_name']} — {c.get('court') or ''}",
        "when": c.get("date_filed") or "",
    } for c in cases if isinstance(c, dict) and c.get("id") and c.get("case_name")]
    if not records:
        return None
    return {"label": "Case law (external research — informational)", "records": records}


# (key, label, query-fn, enabled(features)-predicate)
_SOURCES = [
    ("incidents", "Safety incidents (IR / OSHA)", _src_incidents,
     lambda f: bool(f.get("incidents"))),
    ("er_cases", "Employee-relations cases", _src_er_cases,
     lambda f: True),  # er_copilot has no feature gate in defaults
    ("compliance", "Compliance requirements tracked", _src_compliance,
     lambda f: bool(f.get("compliance") or f.get("compliance_lite"))),
    ("compliance_alerts", "Compliance monitoring alerts", _src_compliance_alerts,
     lambda f: bool(f.get("compliance") or f.get("compliance_lite"))),
    ("discipline", "Progressive discipline", _src_discipline,
     lambda f: bool(f.get("discipline"))),
    ("training", "Training completions", _src_training,
     lambda f: bool(f.get("training"))),
    ("policy_ack", "Policy / handbook acknowledgments", _src_policy_ack,
     lambda f: bool(f.get("handbooks", True))),
    ("accommodations", "Accommodation cases", _src_accommodations,
     lambda f: bool(f.get("accommodations", True))),
]


async def gather_evidence(conn, company_id, start, end, features: dict, matter: dict | None = None) -> dict:
    """Assemble the in-scope evidence corpus across every enabled subsystem.

    Each source is isolated: a failure (missing column, transient error) degrades
    that source to "unavailable" and is noted — it never aborts the whole gather.
    Returns ``{sources, index, notes, legal_context}`` where ``index`` is a flat
    cid→record map used for citation validation and the PDF evidence index.

    ``matter`` is optional (keyword, default None) so existing callers stay
    source-compatible; when given, jurisdiction-grounded law/legislation/case-law
    sources are added on top of the internal-record sources.
    """
    features = features or {}
    sources: dict = {}
    notes: list[str] = []

    for key, label, fn, enabled in _SOURCES:
        if not enabled(features):
            continue
        try:
            recs = await fn(conn, company_id, start, end)
        except Exception as e:  # noqa: BLE001 — isolation is the point
            logger.warning("legal_defense: source %s unavailable: %s", key, e)
            notes.append(f"{label}: unavailable")
            continue
        if not recs:
            continue
        if len(recs) > _PER_SOURCE_CAP:
            notes.append(f"{label}: showing {_PER_SOURCE_CAP} most recent of {len(recs)}")
            recs = recs[:_PER_SOURCE_CAP]
        sources[key] = {"label": label, "records": recs}

    legal_context = None
    if matter:
        try:
            legal_context = await resolve_matter_jurisdiction(conn, matter)
        except Exception as e:  # noqa: BLE001
            logger.warning("legal_defense: jurisdiction resolve failed: %s", e)
            notes.append("Jurisdiction: unavailable")
        if legal_context:
            try:
                law_src, bill_src = await _gather_law(conn, matter, legal_context)
                if law_src and law_src["records"]:
                    sources["law"] = law_src
                if bill_src and bill_src["records"]:
                    sources["legislation"] = bill_src
            except Exception as e:  # noqa: BLE001
                logger.warning("legal_defense: law source unavailable: %s", e)
                notes.append("Governing requirements (jurisdiction): unavailable")
        try:
            case_src = await _gather_case_law(conn, matter.get("id"))
            if case_src and case_src["records"]:
                sources["case_law"] = case_src
        except Exception as e:  # noqa: BLE001
            logger.warning("legal_defense: case-law source unavailable: %s", e)
            notes.append("Case law (external research): unavailable")

    index: dict = {}
    for key, s in sources.items():
        for r in s["records"]:
            index[r["cid"]] = {**r, "source": key, "source_label": s["label"]}

    return {"sources": sources, "index": index, "notes": notes, "legal_context": legal_context}


# --------------------------------------------------------------------------- #
# Grounded AI turn (organizer, not advocate)
# --------------------------------------------------------------------------- #

_SYSTEM = """You are a litigation-readiness analyst helping an employer prepare to hand its OUTSIDE COUNSEL an organized factual record. You are NOT a lawyer.

Your job is to ORGANIZE and SURFACE what the company's own system records show, in relation to the matter — so counsel can do the legal analysis efficiently.

HARD RULES:
- You are an ORGANIZER, NOT AN ADVOCATE. Do NOT argue the company is right, do NOT opine on liability, fault, or who will win, and do NOT render conclusions. State what the records show; let counsel draw conclusions.
- Cite ONLY the bracketed record IDs (e.g. [incident:<uuid>]) that appear in the EVIDENCE CORPUS below. NEVER invent a record, fact, date, name, or ID.
- Where the records DO NOT address a point, say so plainly and put it under open_questions — never speculate or fill gaps.
- Be neutral, precise, and specific. Tie each observation to the records that support it.
- This is not legal advice; frame everything for attorney review.
- Records with `law:`, `bill:`, or `case:` IDs are LEGAL CONTEXT (governing requirements, pending legislation, externally researched case law) — they describe the legal landscape, NOT the company's conduct. You may cite them to identify which requirements or authorities appear relevant. NEVER conclude the company complied with or violated anything, and NEVER present a `case:` record as precedent analysis — flag it for counsel to evaluate.

Return STRICT JSON ONLY (no markdown, no prose outside the JSON), shape:
{"assistant_text": "<your neutral, conversational reply to the user>",
 "evidence_map": [{"point": "<a factual observation grounded in the records>", "cited_ids": ["<source:uuid>", ...]}],
 "open_questions": ["<what the records do NOT establish / what counsel should clarify>"]}"""


def _corpus_text(corpus: dict) -> str:
    out = []
    for key, s in corpus.get("sources", {}).items():
        if not s["records"]:
            continue
        out.append(f"## {s['label']} ({key})")
        for r in s["records"]:
            out.append(f"- [{r['cid']}] ({r['when']}) {r['summary']}")
    return "\n".join(out) or "(no records found in the selected scope)"


def _history_text(history: list[dict]) -> str:
    msgs = [m for m in (history or []) if m.get("role") in ("user", "assistant")][-_HISTORY_TURNS:]
    return "\n".join(f"[{m['role']}] {m.get('content', '')}" for m in msgs) or "(no prior messages)"


def _build_prompt(matter: dict, history: list[dict], corpus: dict, latest: str) -> str:
    return f"""{_SYSTEM}

MATTER
Type: {matter.get('matter_type') or 'other'}
Jurisdiction: {" → ".join(c["display_name"] for c in (corpus.get("legal_context") or {}).get("chain", [])) or "(not specified)"}
Allegation / what's being claimed: {matter.get('allegation') or '(not specified)'}
Factual context the company provided: {matter.get('defense_theory') or '(not specified)'}

EVIDENCE CORPUS (the ONLY records you may cite):
{_corpus_text(corpus)}

CONVERSATION (oldest first):
{_history_text(history)}

LATEST USER MESSAGE:
{latest}
"""


def validate_citations(evidence_map, index: dict):
    """Anti-hallucination gate: keep only cited IDs that exist in the corpus.

    Pure function (unit-tested). Returns ``(clean_map, dropped_ids)``."""
    clean, dropped = [], []
    for item in evidence_map or []:
        if not isinstance(item, dict):
            continue
        raw = item.get("cited_ids")
        ids = [c for c in raw if isinstance(c, str)] if isinstance(raw, list) else []
        keep = [c for c in ids if c in index]
        dropped.extend(c for c in ids if c not in index)
        clean.append({"point": str(item.get("point", "")), "cited_ids": keep})
    return clean, dropped


async def _generate(matter: dict, history: list[dict], corpus: dict, latest: str) -> dict:
    prompt = _build_prompt(matter, history, corpus, latest)
    resp = await asyncio.wait_for(
        _genai().aio.models.generate_content(model=MODEL, contents=prompt),
        timeout=_GEMINI_TIMEOUT,
    )
    data = _parse_json(getattr(resp, "text", "") or "")
    return {
        "assistant_text": str(data.get("assistant_text") or "").strip(),
        "evidence_map": data.get("evidence_map") or [],
        "open_questions": [str(q) for q in (data.get("open_questions") or []) if q],
    }


async def run_chat_turn(matter: dict, history: list[dict], corpus: dict, latest: str):
    """Async generator of SSE-shaped dicts for one grounded chat turn.

    Yields a status tick, then a single validated ``result`` (groundedness over
    token-streaming — the citation gate runs before anything reaches the user)."""
    yield {"type": "status", "message": "Organizing your records…"}
    try:
        result = await _generate(matter, history, corpus, latest)
    except asyncio.TimeoutError:
        yield {"type": "error", "message": "Analysis timed out — please try again."}
        return
    except Exception:
        logger.exception("legal_defense: chat turn failed")
        yield {"type": "error", "message": "Analysis failed — please try again."}
        return

    clean_map, dropped = validate_citations(result.get("evidence_map"), corpus.get("index", {}))
    result["evidence_map"] = clean_map
    if dropped:
        result["dropped_citations"] = dropped
        logger.info("legal_defense: dropped %d hallucinated citation(s)", len(dropped))
    if not result["assistant_text"]:
        result["assistant_text"] = (
            "I couldn't organize a response from the records this time. Try rephrasing, "
            "or widen the matter's date range."
        )
    yield {"type": "result", "data": result}


# --------------------------------------------------------------------------- #
# Packet build — neutral evidence-assembly memo (PDF) + ZIP of source documents
# --------------------------------------------------------------------------- #

def _cited_ids(memo: dict) -> list[str]:
    seen, out = set(), []
    for item in memo.get("evidence_map") or []:
        for c in item.get("cited_ids") or []:
            if c not in seen:
                seen.add(c)
                out.append(c)
    return out


# Style layered on top of the shared `_PDF_CSS` (claims_readiness): a letterhead
# strip, footnote-style citation markers instead of raw record IDs, and explicit
# page-break rules so a table row or appendix doesn't split across pages.
_MEMO_CSS_EXTRA = """
  .letterhead { display:flex; justify-content:space-between; align-items:flex-end;
    border-bottom:2px solid #1f3a8a; padding-bottom:8px; margin-bottom:12px; }
  .letterhead .company { font-size:13px; font-weight:600; color:#1a1a2e; }
  .letterhead .meta { font-size:9px; color:#888; text-align:right; line-height:1.5; }
  h1 { border:none; }
  tr, .cell, .narr, .obs { page-break-inside: avoid; }
  h2 { page-break-after: avoid; }
  .appendix-section { page-break-before: always; }
  sup.cite { color:#1f3a8a; font-weight:700; }
  .obs { display:flex; gap:10px; margin:8px 0; padding:8px 10px;
    border:1px solid #e5e7eb; border-radius:8px; }
  .obs-n { flex-shrink:0; width:18px; height:18px; border-radius:50%;
    background:#1f3a8a; color:#fff; font-size:9px; font-weight:700;
    display:flex; align-items:center; justify-content:center; }
  .obs-point { font-weight:600; margin-bottom:2px; }
  .obs ul { margin:2px 0 0; }
  body::before {
    content: 'CONFIDENTIAL — ATTORNEY WORK PRODUCT';
    position: fixed; top: 50%; left: 50%;
    transform: translate(-50%, -50%) rotate(-45deg);
    font-size: 32pt; color: rgba(31, 58, 138, 0.08); font-weight: 800;
    z-index: -1; pointer-events: none; white-space: nowrap;
  }
"""


_AUDIT_ACTION_LABELS = {
    "create": "Matter created",
    "update": "Matter updated",
    "message": "Chat message ({role})",
    "generate_packet": "Packet generated ({kind})",
    "export": "Packet downloaded",
    "share": "Share link created",
    "shared_download": "Downloaded via share link",
    "research": "External legal research run",
}


def _describe_audit(row: dict) -> str:
    action = row.get("action") or ""
    details = row.get("details") or {}
    if isinstance(details, str):
        try:
            details = json.loads(details)
        except Exception:
            details = {}
    label = _AUDIT_ACTION_LABELS.get(action, _hum(action))
    if action == "message":
        return label.format(role=_hum(details.get("role", "")) or "—")
    if action == "generate_packet":
        return label.format(kind=(details.get("kind") or "").upper() or "—")
    return label


def _research_html(research: dict | None) -> str:
    """Legal-landscape appendix page: externally researched cases + grounded
    guidance. Informational only — never presented as vetted precedent or
    an assessment of the company's position."""
    if not research:
        return ""
    cases = research.get("cases") or []
    guidance = research.get("guidance") or {}

    case_rows = "".join(
        f"<tr><td>{_esc(c.get('case_name'))}</td><td>{_esc(c.get('citation'))}</td>"
        f"<td>{_esc(c.get('court'))}</td><td>{_fmt_dt(c.get('date_filed'))}</td>"
        f"<td>{_esc(c.get('url'))}</td></tr>"
        for c in cases
    ) or "<tr><td colspan='5'>No cases located.</td></tr>"

    summary = _esc(guidance.get("summary") or "") or "—"
    authorities = "".join(
        f"<li>{_esc(a.get('name'))}"
        + (f" — {_esc(a.get('publisher'))}" if a.get("publisher") else "")
        + f" ({_esc(a.get('url'))})</li>"
        for a in (guidance.get("key_authorities") or [])
    )
    authorities_block = f"<ul>{authorities}</ul>" if authorities else "<p>None recorded.</p>"

    return f"""
      <div class="appendix-section">
        <h2>Legal landscape — informational; verify with counsel</h2>
        <p style="font-weight:600">External research compiled from public sources. It is
        informational only, is not legal advice, has not been verified by an attorney,
        and must be independently evaluated by counsel.</p>
        <h2>Cases located</h2>
        <table><thead><tr><th>Name</th><th>Citation</th><th>Court</th><th>Filed</th><th>URL</th></tr></thead>
        <tbody>{case_rows}</tbody></table>
        <h2>Public guidance summary</h2>
        <div class="narr">{summary}</div>
        <h3>Key authorities</h3>
        {authorities_block}
      </div>
    """


def _memo_html(matter: dict, corpus: dict, memo: dict, details: dict, cited: list[str],
                company_name: str | None = None, audit_log: list[dict] | None = None,
                appendix_ids: list[str] | None = None, research: dict | None = None) -> str:
    index = corpus.get("index", {})
    # Footnote-style numbering: attorneys see "[1]", "[2]" inline, not raw
    # "incident:9c2a1e40-..." record IDs — the evidence index below maps
    # each number back to its source/ref/date.
    fn = {c: i + 1 for i, c in enumerate(cited)}

    counsel = ""
    if matter.get("counsel_directed"):
        who = _esc(matter.get("counsel_name") or "counsel")
        counsel = (f"<div class='narr'><b>Prepared at the direction of counsel</b> "
                   f"({who}). Intended as attorney work product for the matter below.</div>")

    narrative = _esc(memo.get("assistant_text") or "") or "—"

    points = ""
    for n, item in enumerate(memo.get("evidence_map") or [], start=1):
        cites = "".join(
            f"<li><sup class='cite'>[{fn.get(c, '?')}]</sup> {_esc(index.get(c, {}).get('summary', ''))} "
            f"<span style='color:#888'>({_esc(index.get(c, {}).get('when', ''))})</span></li>"
            for c in (item.get("cited_ids") or [])
        )
        points += (f"<div class='obs'><div class='obs-n'>{n}</div>"
                   f"<div class='obs-body'><div class='obs-point'>{_esc(item.get('point'))}</div>"
                   f"<ul>{cites or '<li>—</li>'}</ul></div></div>")
    points = points or "<p>No grounded observations were recorded.</p>"

    oq = "".join(f"<li>{_esc(q)}</li>" for q in (memo.get("open_questions") or []))
    oq_block = f"<ul>{oq}</ul>" if oq else "<p>None recorded.</p>"

    idx_rows = "".join(
        f"<tr><td>[{fn[c]}]</td><td>{_esc(index.get(c, {}).get('source_label', ''))}</td>"
        f"<td>{_esc(index.get(c, {}).get('ref', ''))}</td>"
        f"<td>{_esc(index.get(c, {}).get('when', ''))}</td></tr>"
        for c in cited
    ) or "<tr><td colspan='4'>No records cited.</td></tr>"

    # Deterministic appendices (rendered from DB rows). Covers every cited
    # record plus the full case-file dump (all incidents/ER cases/discipline
    # in scope, per build_defense_packet's appendix_ids) — each tagged with
    # whether the narrative above actually references it, so nothing is
    # silently present-but-unexplained or silently missing. Each starts on
    # its own page so a multi-page appendix never runs into the next record's
    # heading.
    appendix = ""
    for c in (appendix_ids if appendix_ids is not None else cited):
        kind_detail = details.get(c)
        if not kind_detail:
            continue
        kind, d = kind_detail
        section_fn = _APPENDIX_SECTIONS.get(kind)
        if not section_fn:
            continue
        if c in fn:
            tag = f"<p style='font-size:9px;color:#1f3a8a;margin:0 0 4px'>Referenced in narrative as [{fn[c]}]</p>"
        else:
            tag = "<p style='font-size:9px;color:#888;margin:0 0 4px'>Not referenced in narrative above — included for completeness</p>"
        appendix += f"<div class='appendix-section'>{tag}{section_fn(c, d)}</div>"

    notes = "".join(f"<li>{_esc(n)}</li>" for n in corpus.get("notes") or [])
    notes_block = f"<h2>Scope notes</h2><ul>{notes}</ul>" if notes else ""

    custody_rows = "".join(
        f"<tr><td>{_fmt_dt(r.get('created_at'))}</td><td>{_esc(r.get('user_email') or 'System')}</td>"
        f"<td>{_esc(_describe_audit(r))}</td></tr>"
        for r in (audit_log or [])
    ) or "<tr><td colspan='3'>No prior activity recorded.</td></tr>"
    custody_block = f"""
      <h2>Chain of custody</h2>
      <p style="font-size:9px;color:#888;margin:0 0 4px">Activity on this matter through the
      time of this export. Every packet generation, download, and share is logged.</p>
      <table><thead><tr><th>When</th><th>Who</th><th>What</th></tr></thead>
      <tbody>{custody_rows}</tbody></table>
    """

    generated = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")

    start_s, end_s = _esc(matter.get("evidence_start")), _esc(matter.get("evidence_end"))
    if start_s == "—" and end_s == "—":
        window = "Not specified — all records in scope"
    elif start_s == "—":
        window = f"Through {end_s}"
    elif end_s == "—":
        window = f"From {start_s}"
    else:
        window = f"{start_s} – {end_s}"

    return f"""<!DOCTYPE html><html><head><meta charset="utf-8">
      <style>{_PDF_CSS}{_MEMO_CSS_EXTRA}</style></head><body>
      <div class="letterhead">
        <div>
          <h1>Legal Pilot — Evidence Assembly</h1>
          <p class="sub">{_esc(matter.get('title'))} · {_esc(matter.get('matter_type') or 'matter')}</p>
        </div>
        <div class="meta">
          {f"<div class='company'>{_esc(company_name)}</div>" if company_name else ""}
          <div>Generated {generated}</div>
        </div>
      </div>
      {counsel}
      <div class="narr"><b>What this is.</b> An organized, sourced compilation of the company's own system records relevant to the matter, prepared to assist counsel. It states what the records show and flags open questions; it does not draw legal conclusions. {_esc(DISCLAIMER)}</div>

      <h2>Matter</h2>
      <table>
        <tr><th>Allegation / claim</th><td>{_esc(matter.get('allegation'))}</td></tr>
        <tr><th>Factual context provided</th><td>{_esc(matter.get('defense_theory'))}</td></tr>
        <tr><th>Evidence window</th><td>{window}</td></tr>
      </table>

      <h2>Summary of the record</h2>
      <div class="narr">{narrative}</div>

      <h2>Observations grounded in the records</h2>
      {points}

      <h2>Open questions for counsel</h2>
      {oq_block}

      <h2>Evidence index (cited records)</h2>
      <table><thead><tr><th>#</th><th>Source</th><th>Ref</th><th>When</th></tr></thead>
      <tbody>{idx_rows}</tbody></table>

      {notes_block}
      {appendix}

      {custody_block}
      {_research_html(research)}

      <div class="foot">{_esc(DISCLAIMER)}</div>
    </body></html>"""


def _hd(v) -> str:
    """Humanized-or-dash: same "—" convention as ``_esc`` for empty values."""
    return _esc(_hum(v)) if v else "—"


def _incident_section(cid: str, data: dict) -> str:
    inc = data.get("incident", {})
    tl = "".join(
        f"<tr><td>{_fmt_dt(t['created_at'])}</td><td>{_hd(t['action'])}</td></tr>"
        for t in data.get("timeline", [])
    ) or "<tr><td colspan='2'>No audit-trail entries.</td></tr>"
    return f"""
      <h2>Appendix — Incident {_esc(inc.get('incident_number'))}</h2>
      <div class="grid">
        <div class="cell"><div class="l">Type</div><div class="v">{_hd(inc.get('incident_type'))}</div></div>
        <div class="cell"><div class="l">Severity</div><div class="v">{_hd(inc.get('severity'))}</div></div>
        <div class="cell"><div class="l">Status</div><div class="v">{_hd(inc.get('status'))}</div></div>
        <div class="cell"><div class="l">Occurred</div><div class="v">{_fmt_dt(inc.get('occurred_at'))}</div></div>
      </div>
      <div class="narr">{_esc(inc.get('description'))}</div>
      <table><thead><tr><th>When</th><th>Audit action</th></tr></thead><tbody>{tl}</tbody></table>
    """


def _er_section(cid: str, data: dict) -> str:
    case = data.get("case", {})
    notes = "".join(
        f"<tr><td>{_fmt_dt(n['created_at'])}</td><td>{_hd(n['note_type'])}</td><td>{_esc(n['content'])}</td></tr>"
        for n in data.get("notes", [])
    ) or "<tr><td colspan='3'>No case notes on file.</td></tr>"
    return f"""
      <h2>Appendix — ER case {_esc(case.get('case_number'))}</h2>
      <div class="grid">
        <div class="cell"><div class="l">Category</div><div class="v">{_hd(case.get('category'))}</div></div>
        <div class="cell"><div class="l">Status</div><div class="v">{_hd(case.get('status'))}</div></div>
        <div class="cell"><div class="l">Outcome</div><div class="v">{_hd(case.get('outcome'))}</div></div>
      </div>
      <div class="narr">{_esc(case.get('description'))}</div>
      <table><thead><tr><th>When</th><th>Type</th><th>Entry</th></tr></thead><tbody>{notes}</tbody></table>
    """


async def _render_pdf(html_str: str) -> bytes:
    def _r() -> bytes:
        from weasyprint import HTML
        return HTML(string=html_str, url_fetcher=safe_url_fetcher).write_pdf()
    return await asyncio.to_thread(_r)


async def _collect_source_files(conn, cited: list[str]) -> list[tuple[str, str]]:
    """(zip_arcname, storage_path) for the uploaded documents behind cited records."""
    inc_ids = [c.split(":", 1)[1] for c in cited if c.startswith("incident:")]
    er_ids = [c.split(":", 1)[1] for c in cited if c.startswith("er_case:")]
    disc_ids = [c.split(":", 1)[1] for c in cited if c.startswith("discipline:")]
    files: list[tuple[str, str]] = []
    if inc_ids:
        rows = await conn.fetch(
            "SELECT incident_id, filename, file_path FROM ir_incident_documents "
            "WHERE incident_id = ANY($1::uuid[]) AND file_path IS NOT NULL",
            inc_ids,
        )
        files += [(f"incidents/{r['incident_id']}/{r['filename']}", r["file_path"]) for r in rows]
    if er_ids:
        rows = await conn.fetch(
            "SELECT case_id, filename, file_path FROM er_case_documents "
            "WHERE case_id = ANY($1::uuid[]) AND file_path IS NOT NULL",
            er_ids,
        )
        files += [(f"er-cases/{r['case_id']}/{r['filename']}", r["file_path"]) for r in rows]
    if disc_ids:
        # The signed warning itself — strongest documentary evidence behind a
        # discipline citation. Only present for physical_uploaded / e-signed
        # outcomes; NULL for the rest, which is fine — this just adds nothing.
        rows = await conn.fetch(
            "SELECT id, signed_pdf_storage_path FROM progressive_discipline "
            "WHERE id = ANY($1::uuid[]) AND signed_pdf_storage_path IS NOT NULL",
            disc_ids,
        )
        files += [(f"discipline/{r['id']}/signed-document.pdf", r["signed_pdf_storage_path"]) for r in rows]
    return files


def _build_zip(pdf: bytes, fetched: list[tuple[str, bytes]], skipped: list[str], matter: dict,
               generated: list[tuple[str, bytes]] | None = None) -> bytes:
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as z:
        z.writestr("defense-memo.pdf", pdf)
        for arc, data in fetched:
            z.writestr(f"source-documents/{arc}", data)
        for arc, data in generated or []:
            z.writestr(f"source-documents/{arc}", data)
        included = [f"  source-documents/{a}" for a, _ in fetched] or ["  (none)"]
        manifest = [
            f"Legal Defense evidence bundle — {matter.get('title', '')}",
            DISCLAIMER,
            "",
            "INCLUDED SOURCE DOCUMENTS:",
            *included,
        ]
        if generated:
            manifest += [
                "",
                "GENERATED CASE-FILE SUMMARIES (rendered from system records, not uploaded documents):",
                *[f"  source-documents/{a}" for a, _ in generated],
            ]
        if skipped:
            manifest += ["", "COULD NOT BE INCLUDED (fetch failed / missing):", *[f"  {s}" for s in skipped]]
        z.writestr("manifest.txt", "\n".join(manifest))
    return buf.getvalue()


async def _safe_detail(coro):
    try:
        return await coro
    except Exception as e:  # noqa: BLE001
        logger.warning("legal_defense: appendix detail failed: %s", e)
        return None


async def _fetch_audit_log(conn, matter_id) -> list[dict]:
    """Chain-of-custody rows through generation time — the current
    generate_packet audit row is written by the route *after* this build
    returns, so it won't include itself; the next regeneration shows it."""
    rows = await conn.fetch(
        """SELECT al.action, al.details, al.created_at, u.email AS user_email
             FROM legal_matter_audit_log al
             LEFT JOIN users u ON u.id = al.user_id
            WHERE al.matter_id = $1
            ORDER BY al.created_at""",
        matter_id,
    )
    return [dict(r) for r in rows]


# --------------------------------------------------------------------------- #
# Full-detail fetchers for the appendix — one query per cited record, run only
# for records the memo actually cites (never the whole corpus). Mirrors the
# incident/ER-case pattern (claims_readiness.build_incident_packet /
# build_er_packet) for the source types owned directly by this module.
# --------------------------------------------------------------------------- #

async def _detail_discipline(conn, disc_id: str, company_id) -> dict | None:
    row = await conn.fetchrow(
        """SELECT pd.*, e.first_name, e.last_name
             FROM progressive_discipline pd
             LEFT JOIN employees e ON e.id = pd.employee_id
            WHERE pd.id = $1 AND pd.company_id = $2""",
        disc_id, company_id,
    )
    return dict(row) if row else None


async def _detail_compliance(conn, req_id: str, company_id) -> dict | None:
    row = await conn.fetchrow(
        """SELECT cr.*, bl.name AS location_name, jr.statute_citation
             FROM compliance_requirements cr
             JOIN business_locations bl ON bl.id = cr.location_id
             LEFT JOIN jurisdiction_requirements jr ON jr.id = cr.jurisdiction_requirement_id
            WHERE cr.id = $1 AND bl.company_id = $2""",
        req_id, company_id,
    )
    return dict(row) if row else None


async def _detail_law(conn, req_id: str) -> dict | None:
    # jurisdiction_requirements is a global repository table (no company_id) —
    # every company can see the same governing-law text; tenant scoping isn't
    # meaningful here the way it is for the company's own compliance rows.
    row = await conn.fetchrow("SELECT * FROM jurisdiction_requirements WHERE id = $1", req_id)
    return dict(row) if row else None


async def _detail_alert(conn, alert_id: str, company_id) -> dict | None:
    row = await conn.fetchrow(
        """SELECT ca.*, bl.name AS location_name
             FROM compliance_alerts ca
             JOIN business_locations bl ON bl.id = ca.location_id
            WHERE ca.id = $1 AND ca.company_id = $2""",
        alert_id, company_id,
    )
    return dict(row) if row else None


async def _detail_training(conn, tr_id: str, company_id) -> dict | None:
    row = await conn.fetchrow(
        """SELECT tr.*, e.first_name, e.last_name
             FROM training_records tr
             LEFT JOIN employees e ON e.id = tr.employee_id
            WHERE tr.id = $1 AND tr.company_id = $2""",
        tr_id, company_id,
    )
    return dict(row) if row else None


async def _detail_accommodation(conn, acc_id: str, company_id) -> dict | None:
    row = await conn.fetchrow(
        """SELECT ac.*, e.first_name, e.last_name
             FROM accommodation_cases ac
             LEFT JOIN employees e ON e.id = ac.employee_id
            WHERE ac.id = $1 AND ac.org_id = $2""",
        acc_id, company_id,
    )
    return dict(row) if row else None


def _emp_name(d: dict) -> str:
    name = f"{d.get('first_name') or ''} {d.get('last_name') or ''}".strip()
    return name or "—"


def _discipline_section(cid: str, d: dict) -> str:
    return f"""
      <h2>Appendix — Discipline record ({_hd(d.get('discipline_type'))})</h2>
      <div class="grid">
        <div class="cell"><div class="l">Employee</div><div class="v">{_esc(_emp_name(d))}</div></div>
        <div class="cell"><div class="l">Infraction</div><div class="v">{_hd(d.get('infraction_type'))}</div></div>
        <div class="cell"><div class="l">Severity</div><div class="v">{_hd(d.get('severity'))}</div></div>
        <div class="cell"><div class="l">Status</div><div class="v">{_hd(d.get('status'))}</div></div>
        <div class="cell"><div class="l">Issued</div><div class="v">{_fmt_dt(d.get('issued_date'))}</div></div>
        <div class="cell"><div class="l">Review date</div><div class="v">{_fmt_dt(d.get('review_date'))}</div></div>
      </div>
      <div class="narr">{_esc(d.get('description'))}</div>
      {f"<div class='narr'><b>Expected improvement.</b> {_esc(d.get('expected_improvement'))}</div>" if d.get('expected_improvement') else ""}
      {f"<div class='narr'><b>Outcome.</b> {_esc(d.get('outcome_notes'))}</div>" if d.get('outcome_notes') else ""}
    """


def _compliance_section(cid: str, d: dict) -> str:
    return f"""
      <h2>Appendix — Compliance requirement ({_esc(d.get('title'))})</h2>
      <div class="grid">
        <div class="cell"><div class="l">Category</div><div class="v">{_hd(d.get('category'))}</div></div>
        <div class="cell"><div class="l">Jurisdiction</div><div class="v">{_esc(d.get('jurisdiction_name'))}</div></div>
        <div class="cell"><div class="l">Location</div><div class="v">{_esc(d.get('location_name'))}</div></div>
        <div class="cell"><div class="l">Current value</div><div class="v">{_esc(d.get('current_value'))}</div></div>
        <div class="cell"><div class="l">Effective</div><div class="v">{_fmt_dt(d.get('effective_date'))}</div></div>
        <div class="cell"><div class="l">Source</div><div class="v">{_esc(d.get('source_name'))}</div></div>
        <div class="cell"><div class="l">Statute citation</div><div class="v">{_esc(d.get('statute_citation'))}</div></div>
      </div>
      {f"<div class='narr'>{_esc(d.get('description'))}</div>" if d.get('description') else ""}
    """


def _law_section(cid: str, d: dict) -> str:
    penalties_note = ""
    meta = d.get("metadata")
    if isinstance(meta, str):
        try:
            meta = json.loads(meta)
        except Exception:
            meta = None
    if isinstance(meta, dict):
        penalties = meta.get("penalties")
        if isinstance(penalties, dict) and penalties.get("summary"):
            penalties_note = f"<div class='narr'><b>Penalties.</b> {_esc(penalties['summary'])}</div>"
    return f"""
      <h2>Appendix — Governing requirement ({_esc(d.get('title'))})</h2>
      <div class="grid">
        <div class="cell"><div class="l">Statute citation</div><div class="v">{_esc(d.get('statute_citation'))}</div></div>
        <div class="cell"><div class="l">Category</div><div class="v">{_hd(d.get('category'))}</div></div>
        <div class="cell"><div class="l">Jurisdiction</div><div class="v">{_esc(d.get('jurisdiction_name'))} ({_hd(d.get('jurisdiction_level'))})</div></div>
        <div class="cell"><div class="l">Current value</div><div class="v">{_esc(d.get('current_value'))}</div></div>
        <div class="cell"><div class="l">Effective</div><div class="v">{_fmt_dt(d.get('effective_date'))}</div></div>
        <div class="cell"><div class="l">Source</div><div class="v">{_esc(d.get('source_name'))}</div></div>
      </div>
      {f"<div class='narr'>{_esc(d.get('description'))}</div>" if d.get('description') else ""}
      {penalties_note}
    """


def _alert_section(cid: str, d: dict) -> str:
    return f"""
      <h2>Appendix — Compliance alert ({_esc(d.get('title'))})</h2>
      <div class="grid">
        <div class="cell"><div class="l">Severity</div><div class="v">{_hd(d.get('severity'))}</div></div>
        <div class="cell"><div class="l">Status</div><div class="v">{_hd(d.get('status'))}</div></div>
        <div class="cell"><div class="l">Category</div><div class="v">{_hd(d.get('category'))}</div></div>
        <div class="cell"><div class="l">Deadline</div><div class="v">{_fmt_dt(d.get('deadline'))}</div></div>
        <div class="cell"><div class="l">Location</div><div class="v">{_esc(d.get('location_name'))}</div></div>
      </div>
      <div class="narr">{_esc(d.get('message'))}</div>
      {f"<div class='narr'><b>Action required.</b> {_esc(d.get('action_required'))}</div>" if d.get('action_required') else ""}
    """


def _training_section(cid: str, d: dict) -> str:
    return f"""
      <h2>Appendix — Training ({_esc(d.get('title'))})</h2>
      <div class="grid">
        <div class="cell"><div class="l">Employee</div><div class="v">{_esc(_emp_name(d))}</div></div>
        <div class="cell"><div class="l">Type</div><div class="v">{_hd(d.get('training_type'))}</div></div>
        <div class="cell"><div class="l">Status</div><div class="v">{_hd(d.get('status'))}</div></div>
        <div class="cell"><div class="l">Assigned</div><div class="v">{_fmt_dt(d.get('assigned_date'))}</div></div>
        <div class="cell"><div class="l">Due</div><div class="v">{_fmt_dt(d.get('due_date'))}</div></div>
        <div class="cell"><div class="l">Completed</div><div class="v">{_fmt_dt(d.get('completed_date'))}</div></div>
        <div class="cell"><div class="l">Expires</div><div class="v">{_fmt_dt(d.get('expiration_date'))}</div></div>
        <div class="cell"><div class="l">Score</div><div class="v">{_esc(d.get('score'))}</div></div>
      </div>
      {f"<div class='narr'>{_esc(d.get('notes'))}</div>" if d.get('notes') else ""}
    """


def _accommodation_section(cid: str, d: dict) -> str:
    return f"""
      <h2>Appendix — Accommodation case ({_esc(d.get('case_number'))})</h2>
      <div class="grid">
        <div class="cell"><div class="l">Employee</div><div class="v">{_esc(_emp_name(d))}</div></div>
        <div class="cell"><div class="l">Category</div><div class="v">{_hd(d.get('disability_category'))}</div></div>
        <div class="cell"><div class="l">Status</div><div class="v">{_hd(d.get('status'))}</div></div>
        <div class="cell"><div class="l">Closed</div><div class="v">{_fmt_dt(d.get('closed_at'))}</div></div>
      </div>
      <div class="narr">{_esc(d.get('description'))}</div>
      {f"<div class='narr'><b>Requested accommodation.</b> {_esc(d.get('requested_accommodation'))}</div>" if d.get('requested_accommodation') else ""}
      {f"<div class='narr'><b>Approved accommodation.</b> {_esc(d.get('approved_accommodation'))}</div>" if d.get('approved_accommodation') else ""}
      {f"<div class='narr'><b>Denial reason.</b> {_esc(d.get('denial_reason'))}</div>" if d.get('denial_reason') else ""}
    """


_APPENDIX_SECTIONS = {
    "incident": lambda c, d: _incident_section(c, d),
    "er_case": lambda c, d: _er_section(c, d),
    "discipline": _discipline_section,
    "compliance_req": _compliance_section,
    "training": _training_section,
    "accommodation": _accommodation_section,
    "law": _law_section,
    "compliance_alert": _alert_section,
}

# ZIP folder per record kind — must match the arc-paths _collect_source_files
# uses for uploads, so a record's generated case file and its uploaded
# documents land in the same folder.
_ZIP_DIRS = {"incident": "incidents", "er_case": "er-cases", "discipline": "discipline"}


def _case_file_html(kind: str, cid: str, detail: dict, matter: dict,
                    company_name: str | None = None) -> str:
    """Standalone one-record case-file PDF (for the ZIP). Same deterministic
    section markup as the memo appendix, without .appendix-section (its
    page-break-before would emit a blank first page)."""
    generated = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")
    section = _APPENDIX_SECTIONS[kind](cid, detail)
    return f"""<!DOCTYPE html><html><head><meta charset="utf-8">
      <style>{_PDF_CSS}{_MEMO_CSS_EXTRA}</style></head><body>
      <div class="letterhead">
        <div>
          <h1>Legal Pilot — Case file</h1>
          <p class="sub">{_esc(matter.get('title'))} · {_esc(matter.get('matter_type') or 'matter')}</p>
        </div>
        <div class="meta">
          {f"<div class='company'>{_esc(company_name)}</div>" if company_name else ""}
          <div>Generated {generated}</div>
        </div>
      </div>
      {section}
      <div class="foot">{_esc(DISCLAIMER)}</div>
    </body></html>"""


async def build_defense_packet(conn, matter: dict, corpus: dict, memo: dict,
                                company_name: str | None = None,
                                research: dict | None = None) -> dict:
    """Render the memo PDF and (when source docs exist) the ZIP bundle.

    Returns ``{pdf: bytes, zip: bytes|None, citations: [cid]}``. The narrative
    and evidence index stay scoped to what the memo actually cites, but the
    appendix + ZIP additionally include every incident / ER case / discipline
    record in scope — whether cited or not. A packet that silently omits
    whole categories of records (e.g. all safety incidents, because none
    seemed relevant to a wage claim) looks selective to opposing counsel;
    including everything and tagging what wasn't referenced is safer.
    Compliance/training/accommodation stay cited-only — 100+ near-duplicate
    regulation entries as full appendix pages would swamp the document."""
    company_id = matter["company_id"]
    cited = _cited_ids(memo)
    cited_set = set(cited)

    case_file_ids = [
        cid for cid in corpus.get("index", {})
        if cid.startswith("incident:") or cid.startswith("er_case:") or cid.startswith("discipline:")
    ]
    appendix_ids = cited + [c for c in case_file_ids if c not in cited_set]

    details: dict = {}
    for c in appendix_ids:
        if c.startswith("incident:"):
            d = await _safe_detail(build_incident_packet(conn, c.split(":", 1)[1], company_id))
            if d:
                details[c] = ("incident", d)
        elif c.startswith("er_case:"):
            d = await _safe_detail(build_er_packet(conn, UUID(c.split(":", 1)[1]), company_id))
            if d:
                details[c] = ("er_case", d)
        elif c.startswith("discipline:"):
            d = await _safe_detail(_detail_discipline(conn, c.split(":", 1)[1], company_id))
            if d:
                details[c] = ("discipline", d)
        elif c.startswith("compliance_req:"):
            d = await _safe_detail(_detail_compliance(conn, c.split(":", 1)[1], company_id))
            if d:
                details[c] = ("compliance_req", d)
        elif c.startswith("training:"):
            d = await _safe_detail(_detail_training(conn, c.split(":", 1)[1], company_id))
            if d:
                details[c] = ("training", d)
        elif c.startswith("accommodation:"):
            d = await _safe_detail(_detail_accommodation(conn, c.split(":", 1)[1], company_id))
            if d:
                details[c] = ("accommodation", d)
        elif c.startswith("law:"):
            d = await _safe_detail(_detail_law(conn, c.split(":", 1)[1]))
            if d:
                details[c] = ("law", d)
        elif c.startswith("compliance_alert:"):
            d = await _safe_detail(_detail_alert(conn, c.split(":", 1)[1], company_id))
            if d:
                details[c] = ("compliance_alert", d)
        # bill:/case: cids get no appendix section — they still appear in the
        # evidence-index table; case-law informational context lives in the
        # separate research page (see `research` below).

    audit_log = await _safe_detail(_fetch_audit_log(conn, matter["id"])) or []

    pdf = await _render_pdf(_memo_html(matter, corpus, memo, details, cited, company_name, audit_log, appendix_ids, research))

    files = await _collect_source_files(conn, appendix_ids)
    fetched, skipped = [], []
    storage = get_storage()
    for arc, path in files:
        try:
            fetched.append((arc, await storage.download_file(path)))
        except Exception as e:  # noqa: BLE001
            logger.warning("legal_defense: skip source file %s: %s", arc, e)
            skipped.append(f"{arc} ({e})")

    # A generated case-file PDF per in-scope incident / ER case / discipline
    # record: without it, records with no uploaded documents (all 21 IRs for
    # a company that never attaches files) leave no trace in the ZIP at all.
    generated: list[tuple[str, bytes]] = []
    for c in appendix_ids:
        kind_detail = details.get(c)
        if not kind_detail or kind_detail[0] not in _ZIP_DIRS:
            continue
        kind, d = kind_detail
        rec_id = c.split(":", 1)[1]
        try:
            blob = await _render_pdf(_case_file_html(kind, c, d, matter, company_name))
            generated.append((f"{_ZIP_DIRS[kind]}/{rec_id}/case-file.pdf", blob))
        except Exception as e:  # noqa: BLE001 — one bad record never kills the packet
            logger.warning("legal_defense: case-file render failed for %s: %s", c, e)
            skipped.append(f"{_ZIP_DIRS[kind]}/{rec_id}/case-file.pdf ({e})")

    # Always build the ZIP (even with zero attachable source docs — the
    # manifest just says so) so requesting "zip"/"both" never silently comes
    # back with only a PDF and no explanation.
    zip_bytes = await asyncio.to_thread(_build_zip, pdf, fetched, skipped, matter, generated)
    return {"pdf": pdf, "zip": zip_bytes, "citations": cited}
