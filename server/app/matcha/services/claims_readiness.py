"""Claims-readiness / litigation-defense packet.

Repackages existing IR-incident and ER-case data into a defensible documentation
record (WTW p.4 "the broker of tomorrow is … defense-oriented"; litigation
funding heading to ~$31B by 2028 makes early, documented response the severity
lever). No new capture — assembled from `ir_incidents` / `er_cases` and their
satellite tables. Deterministic PDF (WeasyPrint, SSRF-guarded). Returns ``None``
when the record is not found / not owned by the company (caller raises 404).
"""

import asyncio
import html
import json
import logging
from uuid import UUID

from app.core.services.pdf import render_pdf

logger = logging.getLogger(__name__)


def _loads(v):
    if v is None:
        return None
    if isinstance(v, (dict, list)):
        return v
    try:
        return json.loads(v)
    except Exception:
        return None


def _fmt_dt(v) -> str:
    if v is None:
        return "—"
    try:
        return v.strftime("%Y-%m-%d %H:%M")
    except Exception:
        return str(v)


# --- IR incident packet -----------------------------------------------------

async def build_incident_packet(conn, incident_id: UUID, company_id) -> dict | None:
    inc = await conn.fetchrow(
        """
        SELECT id, incident_number, title, description, incident_type, severity, status,
               occurred_at, location, reported_by_name, witnesses, root_cause,
               corrective_actions, osha_recordable, osha_classification,
               days_away_from_work, days_restricted_duty, return_to_work_date,
               resolved_at, created_at
        FROM ir_incidents WHERE id = $1 AND company_id = $2
        """,
        str(incident_id), company_id,
    )
    if not inc:
        return None
    timeline = await conn.fetch(
        "SELECT action, entity_type, details, created_at FROM ir_audit_log "
        "WHERE incident_id = $1 ORDER BY created_at",
        str(incident_id),
    )
    docs = await conn.fetch(
        "SELECT document_type, filename, mime_type, file_size, created_at "
        "FROM ir_incident_documents WHERE incident_id = $1 ORDER BY created_at",
        str(incident_id),
    )
    pm = await conn.fetchrow(
        "SELECT analysis_data FROM ir_incident_analysis "
        "WHERE incident_id = $1 AND analysis_type = 'policy_mapping'",
        str(incident_id),
    )
    rec = await conn.fetchrow(
        "SELECT analysis_data FROM ir_incident_analysis "
        "WHERE incident_id = $1 AND analysis_type = 'recommendations'",
        str(incident_id),
    )
    return {
        "incident": dict(inc),
        "witnesses": _loads(inc["witnesses"]) or [],
        "timeline": [dict(t) for t in timeline],
        "documents": [dict(d) for d in docs],
        "policy_map": _loads(pm["analysis_data"]) if pm else None,
        "recommendations": _loads(rec["analysis_data"]) if rec else None,
    }


def _esc(v) -> str:
    return html.escape(str(v)) if v is not None else "—"


_PDF_CSS = """
  body { font-family: -apple-system, Helvetica, sans-serif; color:#1a1a2e; padding:30px; font-size:11px; }
  h1 { color:#1f3a8a; margin:0 0 2px; font-size:21px; }
  .sub { color:#666; margin:0 0 14px; }
  h2 { font-size:12px; border-bottom:2px solid #1f3a8a; padding-bottom:4px; margin:16px 0 6px; }
  .grid { display:flex; gap:8px; flex-wrap:wrap; margin-bottom:6px; }
  .cell { border:1px solid #e5e7eb; border-radius:8px; padding:6px 10px; min-width:90px; }
  .cell .l { font-size:8px; text-transform:uppercase; letter-spacing:.5px; color:#888; }
  .cell .v { font-size:14px; font-weight:400; margin-top:2px; }
  table { width:100%; border-collapse:collapse; margin-top:4px; }
  th { text-align:left; font-size:8px; text-transform:uppercase; color:#888; border-bottom:1px solid #ddd; padding:3px 6px; }
  td { padding:3px 6px; border-bottom:1px solid #f0f0f0; vertical-align:top; }
  .narr { background:#f2f4fb; border-left:3px solid #1f3a8a; padding:8px 12px; border-radius:0 6px 6px 0; margin:6px 0; white-space:pre-wrap; }
  ul { margin:4px 0; padding-left:18px; } li { margin:2px 0; }
  .foot { margin-top:22px; color:#999; font-size:8px; border-top:1px solid #eee; padding-top:6px; }
"""


def _incident_html(data: dict) -> str:
    inc = data["incident"]
    tl = "".join(
        f"<tr><td>{_fmt_dt(t['created_at'])}</td><td>{_esc(t['action'])}</td></tr>"
        for t in data["timeline"]
    ) or "<tr><td colspan='2'>No audit-trail entries.</td></tr>"

    wit = "".join(
        f"<tr><td>{_esc(w.get('name'))}</td><td>{_esc(w.get('statement'))}</td></tr>"
        for w in data["witnesses"] if isinstance(w, dict)
    ) or "<tr><td colspan='2'>No witness statements on file.</td></tr>"

    docs = "".join(
        f"<tr><td>{_esc(d['filename'])}</td><td>{_esc(d['document_type'])}</td><td>{_fmt_dt(d['created_at'])}</td></tr>"
        for d in data["documents"]
    ) or "<tr><td colspan='3'>No investigation documents attached.</td></tr>"

    pm = data.get("policy_map") or {}
    matches = pm.get("matches") if isinstance(pm, dict) else None
    pol = "".join(
        f"<li><b>{_esc(m.get('title'))}</b> — {_esc(m.get('description') or m.get('status'))}</li>"
        for m in (matches or []) if isinstance(m, dict)
    )
    pol_block = f"<ul>{pol}</ul>" if pol else "<p>No policy-violation mapping recorded.</p>"

    rec = data.get("recommendations") or {}
    actions = rec.get("actions") if isinstance(rec, dict) else None
    rec_items = "".join(
        f"<li>{_esc(a if isinstance(a, str) else (a.get('action') if isinstance(a, dict) else a))}</li>"
        for a in (actions or [])
    )
    corrective = inc.get("corrective_actions")
    corrective_block = (f"<div class='narr'>{_esc(corrective)}</div>" if corrective else "") + \
        (f"<ul>{rec_items}</ul>" if rec_items else "")
    if not corrective_block:
        corrective_block = "<p>No corrective actions documented.</p>"

    osha_block = ""
    if inc.get("osha_recordable"):
        osha_block = (f"<div class='narr'>OSHA recordable — classification "
                      f"{_esc(inc.get('osha_classification'))}; {_esc(inc.get('days_away_from_work'))} days away, "
                      f"{_esc(inc.get('days_restricted_duty'))} restricted; "
                      f"return-to-work {_esc(inc.get('return_to_work_date'))}.</div>")

    root = inc.get("root_cause")
    root_block = f"<div class='narr'>{_esc(root)}</div>" if root else "<p>No root-cause analysis recorded.</p>"

    return f"""<!DOCTYPE html><html><head><meta charset="utf-8"><style>{_PDF_CSS}</style></head><body>
      <h1>Claims-Readiness / Defense File</h1>
      <p class="sub">Incident {_esc(inc.get('incident_number'))} — {_esc(inc.get('title'))}</p>
      <div class="grid">
        <div class="cell"><div class="l">Type</div><div class="v">{_esc(inc.get('incident_type'))}</div></div>
        <div class="cell"><div class="l">Severity</div><div class="v">{_esc(inc.get('severity'))}</div></div>
        <div class="cell"><div class="l">Status</div><div class="v">{_esc(inc.get('status'))}</div></div>
        <div class="cell"><div class="l">Occurred</div><div class="v">{_fmt_dt(inc.get('occurred_at'))}</div></div>
        <div class="cell"><div class="l">Location</div><div class="v">{_esc(inc.get('location'))}</div></div>
      </div>
      {osha_block}

      <h2>Description</h2>
      <div class="narr">{_esc(inc.get('description'))}</div>

      <h2>Incident timeline (audit trail)</h2>
      <table><thead><tr><th>When</th><th>Action</th></tr></thead><tbody>{tl}</tbody></table>

      <h2>Witness statements</h2>
      <table><thead><tr><th>Witness</th><th>Statement</th></tr></thead><tbody>{wit}</tbody></table>

      <h2>Investigation documents</h2>
      <table><thead><tr><th>File</th><th>Type</th><th>Uploaded</th></tr></thead><tbody>{docs}</tbody></table>

      <h2>Policy-violation mapping</h2>
      {pol_block}

      <h2>Root-cause analysis</h2>
      {root_block}

      <h2>Corrective actions</h2>
      {corrective_block}

      <div class="foot">Documentation record assembled by Matcha for carrier / defense-counsel review.
      Reflects records on file as of generation; not legal advice.</div>
    </body></html>"""


async def render_incident_packet_pdf(data: dict) -> bytes:
    def _render() -> bytes:

        return render_pdf(_incident_html(data))

    return await asyncio.to_thread(_render)


# --- ER case packet ---------------------------------------------------------

async def build_er_packet(conn, case_id: UUID, company_id) -> dict | None:
    case = await conn.fetchrow(
        """
        SELECT id, case_number, title, description, status, category, outcome,
               created_at, closed_at, involved_employees
        FROM er_cases WHERE id = $1 AND company_id = $2
        """,
        case_id, company_id,
    )
    if not case:
        return None
    notes = await conn.fetch(
        "SELECT note_type, content, created_at FROM er_case_notes WHERE case_id = $1 ORDER BY created_at",
        case_id,
    )
    docs = await conn.fetch(
        "SELECT document_type, filename, created_at FROM er_case_documents WHERE case_id = $1 ORDER BY created_at",
        case_id,
    )
    analyses = await conn.fetch(
        "SELECT analysis_type, analysis_data, generated_at FROM er_case_analysis WHERE case_id = $1",
        case_id,
    )
    return {
        "case": dict(case),
        "notes": [dict(n) for n in notes],
        "documents": [dict(d) for d in docs],
        "analyses": {a["analysis_type"]: _loads(a["analysis_data"]) for a in analyses},
    }


def _er_html(data: dict) -> str:
    case = data["case"]
    notes = "".join(
        f"<tr><td>{_fmt_dt(n['created_at'])}</td><td>{_esc(n['note_type'])}</td>"
        f"<td>{_esc(n['content'])}</td></tr>"
        for n in data["notes"]
    ) or "<tr><td colspan='3'>No case notes on file.</td></tr>"

    docs = "".join(
        f"<tr><td>{_esc(d['filename'])}</td><td>{_esc(d['document_type'])}</td><td>{_fmt_dt(d['created_at'])}</td></tr>"
        for d in data["documents"]
    ) or "<tr><td colspan='3'>No documents attached.</td></tr>"

    analyses = data["analyses"]
    determination = analyses.get("determination") or analyses.get("summary")
    det_block = ""
    if isinstance(determination, dict):
        summ = determination.get("summary") or determination.get("determination") or ""
        det_block = f"<div class='narr'>{_esc(summ)}</div>" if summ else ""

    return f"""<!DOCTYPE html><html><head><meta charset="utf-8"><style>{_PDF_CSS}</style></head><body>
      <h1>Claims-Readiness / Defense File</h1>
      <p class="sub">ER case {_esc(case.get('case_number'))} — {_esc(case.get('title'))}</p>
      <div class="grid">
        <div class="cell"><div class="l">Category</div><div class="v">{_esc(case.get('category'))}</div></div>
        <div class="cell"><div class="l">Status</div><div class="v">{_esc(case.get('status'))}</div></div>
        <div class="cell"><div class="l">Outcome</div><div class="v">{_esc(case.get('outcome'))}</div></div>
        <div class="cell"><div class="l">Opened</div><div class="v">{_fmt_dt(case.get('created_at'))}</div></div>
        <div class="cell"><div class="l">Closed</div><div class="v">{_fmt_dt(case.get('closed_at'))}</div></div>
      </div>

      <h2>Description</h2>
      <div class="narr">{_esc(case.get('description'))}</div>

      {('<h2>Determination</h2>' + det_block) if det_block else ''}

      <h2>Case timeline &amp; notes</h2>
      <table><thead><tr><th>When</th><th>Type</th><th>Entry</th></tr></thead><tbody>{notes}</tbody></table>

      <h2>Documents</h2>
      <table><thead><tr><th>File</th><th>Type</th><th>Uploaded</th></tr></thead><tbody>{docs}</tbody></table>

      <div class="foot">Documentation record assembled by Matcha for carrier / defense-counsel review.
      Reflects records on file as of generation; not legal advice.</div>
    </body></html>"""


async def render_er_packet_pdf(data: dict) -> bytes:
    def _render() -> bytes:

        return render_pdf(_er_html(data))

    return await asyncio.to_thread(_render)
