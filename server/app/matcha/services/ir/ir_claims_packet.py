"""Claims-readiness / litigation-defense packet — IR incident half.

Repackages existing IR-incident data into a defensible documentation record
(WTW p.4 "the broker of tomorrow is ... defense-oriented"; litigation funding
heading to ~$31B by 2028 makes early, documented response the severity lever).
No new capture — assembled from `ir_incidents` and its satellite tables.
Deterministic PDF (WeasyPrint, SSRF-guarded). Returns ``None`` when the record
is not found / not owned by the company (caller raises 404).

Split out of the flat services/claims_readiness.py in refactor round 2 stage 6
so each half sits in its own domain package. `services/claims_readiness.py`
remains as a re-export shim — `broker/submission.py` imports it as `cr` and two
route files import it by module.
"""
import asyncio
import json
import logging
from uuid import UUID

from app.core.services.pdf import render_pdf

from app.matcha.services._shared.pdf import _PDF_CSS, _esc, _fmt_dt

logger = logging.getLogger(__name__)

# Lives in services/_shared/jsonio.py so the ER half can reach it without an
# er -> ir service import (it was only ever shared, never IR-specific).
# Aliased to the private name both packets already use.
from app.matcha.services._shared.jsonio import loads_or_none as _loads  # noqa: F401


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
