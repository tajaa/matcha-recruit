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
               cr.last_changed_at, bl.name AS location_name
        FROM compliance_requirements cr
        JOIN business_locations bl ON bl.id = cr.location_id
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
                   + (f" @ {r['location_name']}" if r["location_name"] else ""),
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


# (key, label, query-fn, enabled(features)-predicate)
_SOURCES = [
    ("incidents", "Safety incidents (IR / OSHA)", _src_incidents,
     lambda f: bool(f.get("incidents"))),
    ("er_cases", "Employee-relations cases", _src_er_cases,
     lambda f: True),  # er_copilot has no feature gate in defaults
    ("compliance", "Compliance requirements tracked", _src_compliance,
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


async def gather_evidence(conn, company_id, start, end, features: dict) -> dict:
    """Assemble the in-scope evidence corpus across every enabled subsystem.

    Each source is isolated: a failure (missing column, transient error) degrades
    that source to "unavailable" and is noted — it never aborts the whole gather.
    Returns ``{sources, index, notes}`` where ``index`` is a flat cid→record map
    used for citation validation and the PDF evidence index.
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

    index: dict = {}
    for key, s in sources.items():
        for r in s["records"]:
            index[r["cid"]] = {**r, "source": key, "source_label": s["label"]}

    return {"sources": sources, "index": index, "notes": notes}


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
"""


def _memo_html(matter: dict, corpus: dict, memo: dict, details: dict, cited: list[str],
                company_name: str | None = None) -> str:
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

    # Deterministic appendices for cited IR / ER records (rendered from DB rows).
    # Each starts on its own page so a multi-page appendix never runs into the
    # next record's heading.
    appendix = ""
    for c in cited:
        kind_detail = details.get(c)
        if not kind_detail:
            continue
        kind, d = kind_detail
        section_fn = _APPENDIX_SECTIONS.get(kind)
        if section_fn:
            appendix += f"<div class='appendix-section'>{section_fn(c, d)}</div>"

    notes = "".join(f"<li>{_esc(n)}</li>" for n in corpus.get("notes") or [])
    notes_block = f"<h2>Scope notes</h2><ul>{notes}</ul>" if notes else ""

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
    """(zip_arcname, storage_path) for the uploaded documents behind cited IR/ER records."""
    inc_ids = [c.split(":", 1)[1] for c in cited if c.startswith("incident:")]
    er_ids = [c.split(":", 1)[1] for c in cited if c.startswith("er_case:")]
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
    return files


def _build_zip(pdf: bytes, fetched: list[tuple[str, bytes]], skipped: list[str], matter: dict) -> bytes:
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as z:
        z.writestr("defense-memo.pdf", pdf)
        for arc, data in fetched:
            z.writestr(f"source-documents/{arc}", data)
        included = [f"  source-documents/{a}" for a, _ in fetched] or ["  (none)"]
        manifest = [
            f"Legal Defense evidence bundle — {matter.get('title', '')}",
            DISCLAIMER,
            "",
            "INCLUDED SOURCE DOCUMENTS:",
            *included,
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
        """SELECT cr.*, bl.name AS location_name
             FROM compliance_requirements cr
             JOIN business_locations bl ON bl.id = cr.location_id
            WHERE cr.id = $1 AND bl.company_id = $2""",
        req_id, company_id,
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
      </div>
      {f"<div class='narr'>{_esc(d.get('description'))}</div>" if d.get('description') else ""}
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
}


async def build_defense_packet(conn, matter: dict, corpus: dict, memo: dict,
                                company_name: str | None = None) -> dict:
    """Render the memo PDF and (when source docs exist) the ZIP bundle.

    Returns ``{pdf: bytes, zip: bytes|None, citations: [cid]}``. The appendix +
    ZIP scope to the records the memo actually cites."""
    company_id = matter["company_id"]
    cited = _cited_ids(memo)

    details: dict = {}
    for c in cited:
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

    pdf = await _render_pdf(_memo_html(matter, corpus, memo, details, cited, company_name))

    files = await _collect_source_files(conn, cited)
    fetched, skipped = [], []
    storage = get_storage()
    for arc, path in files:
        try:
            fetched.append((arc, await storage.download_file(path)))
        except Exception as e:  # noqa: BLE001
            logger.warning("legal_defense: skip source file %s: %s", arc, e)
            skipped.append(f"{arc} ({e})")

    # Always build the ZIP (even with zero attachable source docs — the
    # manifest just says so) so requesting "zip"/"both" never silently comes
    # back with only a PDF and no explanation.
    zip_bytes = await asyncio.to_thread(_build_zip, pdf, fetched, skipped, matter)
    return {"pdf": pdf, "zip": zip_bytes, "citations": cited}
