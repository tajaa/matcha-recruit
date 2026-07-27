"""Packet build — neutral evidence-assembly memo (PDF) + ZIP of source
documents. The appendix is rendered deterministically from DB rows."""

import asyncio
import io
import logging
import unicodedata
import zipfile
from datetime import datetime, timezone
from uuid import UUID

from app.core.services.pdf import render_pdf
from app.core.services.storage import get_storage

from ..._shared.pdf import _PDF_CSS, _esc, _fmt_dt
from ...claims_readiness import (
    build_er_packet,
    build_incident_packet,
)
from ._shared import DISCLAIMER
from .details import (
    _APPENDIX_SECTIONS,
    _describe_audit,
    _detail_accommodation,
    _detail_alert,
    _detail_compliance,
    _detail_discipline,
    _detail_law,
    _detail_training,
    _discipline_audit_by_record,
    _er_audit_by_case,
)

logger = logging.getLogger(__name__)


def safe_name(s: str) -> str:
    """ASCII-only filename slug (shared by the route and the Huume skill).
    Non-ASCII survives into Content-Disposition otherwise, and Starlette
    encodes header values as latin-1 — a title with an em dash or accent
    crashes every download of that packet with a 500."""
    ascii_s = unicodedata.normalize("NFKD", s or "matter").encode("ascii", "ignore").decode("ascii")
    return (ascii_s or "matter").replace("/", "-").replace('"', "").replace(" ", "-")[:60] or "matter"


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
def _research_html(research: dict | None) -> str:
    """Legal-landscape appendix page: externally researched cases + grounded
    guidance. Informational only — never presented as vetted precedent or
    an assessment of the company's position."""
    if not research:
        return ""
    cases = research.get("cases") or []
    guidance = research.get("guidance") or {}

    # A partial failure (e.g. CourtListener down) persists status='complete'
    # with an error note — surface it, or an empty cases table is
    # indistinguishable from a genuine zero-result search.
    error_note = ""
    if research.get("error"):
        error_note = (
            "<p style='font-weight:600;color:#b45309'>Partial run: "
            f"{_esc(research['error'])}. Sections below may be incomplete "
            "for that reason rather than because nothing was found.</p>"
        )

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
        {error_note}
        <h2>Cases located</h2>
        <table><thead><tr><th>Name</th><th>Citation</th><th>Court</th><th>Filed</th><th>URL</th></tr></thead>
        <tbody>{case_rows}</tbody></table>
        <h2>Public guidance summary</h2>
        <div class="narr">{summary}</div>
        <h3>Key authorities</h3>
        {authorities_block}
      </div>
    """


# Chronology covers company-conduct EVENTS. compliance_req is excluded on
# purpose: it's current tracked posture, and its last_changed_at is the LAW's
# change date, not a company action. Jurisdiction kinds (law/bill/case) are
# likewise not company events.
_CHRONOLOGY_KINDS = ("incident:", "er_case:", "compliance_alert:", "discipline:",
                     "training:", "policy_ack:", "accommodation:")


def _chronology_rows(index: dict) -> list[dict]:
    """Company-record events oldest-first, undated last. Pure (unit-tested)."""
    recs = [r for cid, r in index.items() if cid.startswith(_CHRONOLOGY_KINDS)]
    dated = sorted((r for r in recs if r.get("when_iso")), key=lambda r: r["when_iso"])
    undated = [r for r in recs if not r.get("when_iso")]
    return dated + undated


def _chronology_html(index: dict) -> str:
    rows = _chronology_rows(index)
    if not rows:
        return ""
    trs = "".join(
        f"<tr><td>{_esc((r.get('when_iso') or '')[:10]) if r.get('when_iso') else '—'}</td>"
        f"<td>{_esc(r.get('source_label', ''))}</td>"
        f"<td>{_esc(r.get('summary', ''))}</td></tr>"
        for r in rows
    )
    return f"""
      <div class="appendix-section">
        <h2>Chronology of records</h2>
        <p style="font-size:9px;color:#888;margin:0 0 4px">Every dated company record in the
        evidence scope, oldest first — rendered directly from system records, not model output.</p>
        <table><thead><tr><th>Date</th><th>Source</th><th>Record</th></tr></thead>
        <tbody>{trs}</tbody></table>
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

    # A cid validated at chat time can be absent from the packet-time
    # re-gather (RAG top-K drift, changed evidence window, retrieval-path
    # fallback). Render an explicit marker instead of silently-blank cells —
    # blanks in a legal exhibit read as corruption, not scope drift.
    _GONE = "(no longer in evidence scope at generation time)"

    points = ""
    for n, item in enumerate(memo.get("evidence_map") or [], start=1):
        cites = "".join(
            f"<li><sup class='cite'>[{fn.get(c, '?')}]</sup> "
            f"{_esc(index[c].get('summary', '')) if c in index else _GONE} "
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
        f"<tr><td>[{fn[c]}]</td><td>{_esc(index[c].get('source_label', ''))}</td>"
        f"<td>{_esc(index[c].get('ref', ''))}</td>"
        f"<td>{_esc(index[c].get('when', ''))}</td></tr>"
        if c in index else
        f"<tr><td>[{fn[c]}]</td><td colspan='3'>{_GONE}</td></tr>"
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
      {_chronology_html(index)}
      {appendix}

      {custody_block}
      {_research_html(research)}

      <div class="foot">{_esc(DISCLAIMER)}</div>
    </body></html>"""
async def _render_pdf(html_str: str) -> bytes:
    def _r() -> bytes:
        return render_pdf(html_str)
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

    # Chain-of-custody trails for every ER case / discipline record the appendix
    # will render — two queries for the whole packet, keyed back onto each record
    # inside the loop below. `_safe_detail` keeps a missing table or a failed
    # fetch from sinking the packet: the sections degrade to "no entries".
    er_audit = await _safe_detail(_er_audit_by_case(
        conn, [c.split(":", 1)[1] for c in appendix_ids if c.startswith("er_case:")])) or {}
    disc_audit = await _safe_detail(_discipline_audit_by_record(
        conn, [c.split(":", 1)[1] for c in appendix_ids if c.startswith("discipline:")])) or {}

    details: dict = {}
    for c in appendix_ids:
        if c.startswith("incident:"):
            d = await _safe_detail(build_incident_packet(conn, c.split(":", 1)[1], company_id))
            if d:
                details[c] = ("incident", d)
        elif c.startswith("er_case:"):
            case_id = c.split(":", 1)[1]
            d = await _safe_detail(build_er_packet(conn, UUID(case_id), company_id))
            if d:
                # Ownership is proved by the packet fetch above; the batched
                # audit rows are keyed on the same id (er_audit_log has no
                # company column of its own).
                d["audit_trail"] = er_audit.get(case_id, [])
                details[c] = ("er_case", d)
        elif c.startswith("discipline:"):
            disc_id = c.split(":", 1)[1]
            d = await _safe_detail(_detail_discipline(conn, disc_id, company_id))
            if d:
                d["audit_trail"] = disc_audit.get(disc_id, [])
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
