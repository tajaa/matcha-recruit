"""Claims-readiness / litigation-defense packet — ER case half.

The ER-case counterpart of `ir/ir_claims_packet.py`; see that module's
docstring for the shared rationale. Assembled from `er_cases` and its satellite
tables, deterministic PDF, ``None`` when not found / not owned.
"""
import asyncio
import logging
from uuid import UUID

from app.core.services.pdf import render_pdf

from app.matcha.services._shared.pdf import _PDF_CSS, _esc, _fmt_dt
from app.matcha.services._shared.jsonio import loads_or_none as _loads

logger = logging.getLogger(__name__)


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
