"""The analysis-memo PDF: deterministic appendix renderers (documents, platform
context, native sources, jurisdictions), the memo HTML, and build_memo_pdf.
Appendices render from DB rows / re-gathered context, never from model text.
"""
import asyncio
import json
import logging
from datetime import datetime, timezone
from app.core.services.pdf import render_pdf
from app.matcha.services._shared.pdf import _PDF_CSS, _esc, _fmt_dt

from ._config import DISCLAIMER, _GAP_SEVERITIES
from .templates import _lookup_template
from app.matcha.services._shared.text import _hum

logger = logging.getLogger(__name__)


# --------------------------------------------------------------------------- #
# Memo PDF — analysis narrative + grounded observations with footnote-style
# citations + deterministic appendix (document extractions + platform sections
# rendered from the re-gathered context, never from model text).
# --------------------------------------------------------------------------- #

def _cited_ids(memo: dict) -> list[str]:
    """Every record cited anywhere in the turn, in footnote order.

    Spans ALL cited buckets — a record cited only by a gap still has to reach the
    evidence index and the appendix, or the memo would footnote it as [?] and
    omit the record it rests on."""
    seen, out = set(), []
    for bucket in ("evidence_map", "gaps", "considerations"):
        for item in memo.get(bucket) or []:
            for c in item.get("cited_ids") or []:
                if c not in seen:
                    seen.add(c)
                    out.append(c)
    return out


_MEMO_CSS_EXTRA = """
  @page {
    size: Letter; margin: 20mm 16mm 18mm 16mm;
    @bottom-left { content: "Broker Pilot analysis memo — confidential; prepared for broker use";
      font-size: 7px; color: #9ca3af; }
    @bottom-right { content: "Page " counter(page) " of " counter(pages);
      font-size: 7px; color: #9ca3af; }
  }
  body { padding: 0; }
  .letterhead { display:flex; justify-content:space-between; align-items:flex-end;
    border-bottom:2px solid #166534; padding-bottom:10px; margin-bottom:0; }
  .letterhead .company { font-size:13px; font-weight:600; color:#1a1a2e; }
  .letterhead .meta { font-size:9px; color:#888; text-align:right; line-height:1.5; }
  .brand { font-size:8px; letter-spacing:2px; text-transform:uppercase; color:#166534;
    font-weight:700; margin-bottom:2px; }
  h1 { border:none; color:#14532d; font-size:19px; }
  h2 { border-bottom:2px solid #166534; color:#14532d; page-break-after: avoid; }
  .prep { display:flex; gap:0; border:1px solid #e5e7eb; border-radius:8px;
    margin:12px 0 4px; overflow:hidden; }
  .prep > div { flex:1; padding:7px 12px; border-left:1px solid #e5e7eb; }
  .prep > div:first-child { border-left:none; }
  .prep .l { font-size:7.5px; text-transform:uppercase; letter-spacing:.8px; color:#888; }
  .prep .v { font-size:10.5px; font-weight:600; margin-top:2px; color:#1a1a2e; }
  .narr { background:#f4faf6; border-left:3px solid #166534; white-space:normal; }
  .narr p { margin:0 0 7px; } .narr p:last-child { margin-bottom:0; }
  tr, .cell, .obs { page-break-inside: avoid; }
  .appendix-section { page-break-before: always; }
  sup.cite { color:#166534; font-weight:700; }
  .obs { display:flex; gap:10px; margin:8px 0; padding:8px 10px;
    border:1px solid #e5e7eb; border-radius:8px; }
  .obs-n { flex-shrink:0; width:18px; height:18px; border-radius:50%;
    background:#166534; color:#fff; font-size:9px; font-weight:700;
    display:flex; align-items:center; justify-content:center; }
  .obs-point { font-weight:600; margin-bottom:2px; }
  .obs ul { margin:2px 0 0; }
  .sev { margin-left:6px; padding:1px 5px; border-radius:8px; font-size:7.5px;
    font-weight:700; text-transform:uppercase; letter-spacing:.6px; vertical-align:middle; }
  .sev-high { background:#fee2e2; color:#991b1b; }
  .sev-medium { background:#fef3c7; color:#92400e; }
  .sev-low { background:#e5e7eb; color:#4b5563; }
"""


_GONE = "(no longer in scope at generation time)"


def _doc_appendix_html(doc: dict) -> str:
    """Deterministic per-document appendix section rendered ONLY from the
    stored row + extraction (never model text)."""
    ext = doc.get("extraction")
    if isinstance(ext, str):
        try:
            ext = json.loads(ext)
        except Exception:
            ext = {}
    ext = ext or {}
    figures = "".join(
        f"<tr><td>{_esc(f.get('label'))}</td><td>{_esc(f.get('value'))}</td>"
        f"<td>{_esc(f.get('context'))}</td></tr>"
        for f in ext.get("key_figures") or []
    ) or "<tr><td colspan='3'>No figures extracted.</td></tr>"
    notable = "".join(f"<li>{_esc(n)}</li>" for n in ext.get("notable") or [])
    notable_block = f"<h3>Notable items</h3><ul>{notable}</ul>" if notable else ""
    size = doc.get("file_size")
    size_s = f"{round(size / 1024)} KB" if size else "—"
    return f"""
      <h2>Appendix — Document: {_esc(doc.get('filename'))}</h2>
      <div class="grid">
        <div class="cell"><div class="l">Type</div><div class="v">{_esc(_hum(doc.get('doc_type')) or 'Unclassified')}</div></div>
        <div class="cell"><div class="l">Carrier</div><div class="v">{_esc(ext.get('carrier')) if ext.get('carrier') else '—'}</div></div>
        <div class="cell"><div class="l">Period</div><div class="v">{_esc(ext.get('period_label')) if ext.get('period_label') else '—'}</div></div>
        <div class="cell"><div class="l">Uploaded</div><div class="v">{_fmt_dt(doc.get('created_at'))} · {size_s}{f" · {doc['page_count']} pp" if doc.get('page_count') else ''}</div></div>
      </div>
      <div class="narr">{_esc(ext.get('summary')) if ext.get('summary') else 'No AI summary available (raw text only).'}</div>
      <h3>Extracted key figures</h3>
      <table><thead><tr><th>Figure</th><th>Value</th><th>Context</th></tr></thead>
      <tbody>{figures}</tbody></table>
      {notable_block}
    """


def _platform_appendix_html(section: str, corpus: dict) -> str:
    """Deterministic appendix for a cited platform section: re-renders that
    section's corpus records (which were themselves minted from the re-gathered
    context) as a table."""
    recs = [r for r in (corpus.get("sources", {}).get("platform", {}).get("records") or [])
            if r["cid"] == f"platform:{section}" or r["cid"].startswith(f"platform:{section}.")]
    rows = "".join(
        f"<tr><td>{_esc(r.get('ref'))}</td><td>{_esc(r.get('summary'))}</td>"
        f"<td>{_esc(r.get('when'))}</td></tr>"
        for r in recs
    ) or f"<tr><td colspan='3'>{_GONE}</td></tr>"
    return f"""
      <h2>Appendix — Platform data: {_esc(_hum(section))}</h2>
      <table><thead><tr><th>Item</th><th>What the platform shows</th><th>As of</th></tr></thead>
      <tbody>{rows}</tbody></table>
    """


def _native_appendix_html(source_key: str, cited: list[str], corpus: dict) -> str:
    """Deterministic appendix for a cited native operational source (incidents,
    ER cases, discipline, …): re-renders that source's CITED records as a table."""
    src = corpus.get("sources", {}).get(source_key, {})
    cited_set = set(cited)
    recs = [r for r in (src.get("records") or []) if r["cid"] in cited_set]
    rows = "".join(
        f"<tr><td>{_esc(r.get('ref'))}</td><td>{_esc(r.get('summary'))}</td>"
        f"<td>{_esc(r.get('when'))}</td></tr>"
        for r in recs
    ) or f"<tr><td colspan='3'>{_GONE}</td></tr>"
    return f"""
      <h2>Appendix — Platform records: {_esc(src.get('label') or _hum(source_key))}</h2>
      <table><thead><tr><th>Ref</th><th>What the platform recorded</th><th>When</th></tr></thead>
      <tbody>{rows}</tbody></table>
    """


def _jurisdiction_appendix_html(cited: list[str], corpus: dict) -> str:
    """Deterministic appendix for cited codified obligations. Its own builder,
    NOT the native one: these are statutes, not records the platform generated
    about this client, and `_native_appendix_html` would head the table
    "Platform records" / "What the platform recorded" — misrepresenting
    provenance in the one artifact that leaves the building. Carries the
    citation and, where the catalog has it, a link to the source."""
    src = corpus.get("sources", {}).get("jurisdiction", {})
    cited_set = set(cited)
    recs = [r for r in (src.get("records") or []) if r["cid"] in cited_set]
    rows = "".join(
        f"<tr><td>{_esc(r.get('ref'))}</td><td>{_esc(r.get('summary'))}</td>"
        f"<td>{_link_or_dash(r.get('source_url'))}</td></tr>"
        for r in recs
    ) or f"<tr><td colspan='3'>{_GONE}</td></tr>"
    return f"""
      <h2>Appendix — Codified statutory obligations</h2>
      <p style="font-size:9px; color:#888;">Codified law on file for this client's
      jurisdictions, not legal advice. Verify against the source before relying on it.</p>
      <table><thead><tr><th>Obligation</th><th>What the law requires</th><th>Source</th></tr></thead>
      <tbody>{rows}</tbody></table>
    """


def _link_or_dash(url: str | None) -> str:
    """Escaped anchor for a catalog source_url, else an em dash. Only http(s) —
    the URL is catalog data rendered into a PDF, never a caller-supplied scheme."""
    u = (url or "").strip()
    if not u.lower().startswith(("http://", "https://")):
        return "—"
    return f'<a href="{_esc(u)}">{_esc(u)}</a>'


def _narrative_html(text: str) -> str:
    """Model narrative → escaped paragraphs (blank-line separated). Keeps the
    memo typographically clean without trusting model markup."""
    paras = [p.strip() for p in (text or "").split("\n\n") if p.strip()]
    if not paras:
        return "<p>—</p>"
    return "".join(f"<p>{_esc(p)}</p>" for p in paras)


def _memo_html(session: dict, subject_name: str, corpus: dict, memo: dict,
               docs: list[dict], broker_name: str | None = None) -> str:
    index = corpus.get("index", {})
    cited = _cited_ids(memo)
    fn = {c: i + 1 for i, c in enumerate(cited)}

    narrative = _narrative_html(memo.get("assistant_text") or "")

    def _findings_html(bucket: str, empty: str, *, severity: bool = False) -> str:
        out = ""
        for n, item in enumerate(memo.get(bucket) or [], start=1):
            cites = "".join(
                f"<li><sup class='cite'>[{fn.get(c, '?')}]</sup> "
                f"{_esc(index[c].get('summary', '')) if c in index else _GONE} "
                f"<span style='color:#888'>({_esc(index.get(c, {}).get('when', ''))})</span></li>"
                for c in (item.get("cited_ids") or [])
            )
            sev = str(item.get("severity") or "") if severity else ""
            chip = (f"<span class='sev sev-{_esc(sev)}'>{_esc(sev)}</span>"
                    if sev in _GAP_SEVERITIES else "")
            out += (f"<div class='obs'><div class='obs-n'>{n}</div>"
                    f"<div class='obs-body'><div class='obs-point'>{_esc(item.get('point'))}{chip}</div>"
                    f"<ul>{cites or '<li>—</li>'}</ul></div></div>")
        return out or f"<p>{empty}</p>"

    # Gaps lead — they are what the broker acts on. Severity orders them; an
    # unranked gap sorts last rather than being dropped from the memo.
    gaps = sorted(memo.get("gaps") or [],
                  key=lambda g: _GAP_SEVERITIES.index(g["severity"])
                  if g.get("severity") in _GAP_SEVERITIES else len(_GAP_SEVERITIES))
    memo = {**memo, "gaps": gaps}

    gaps_block = _findings_html("gaps", "No gaps were established by the record.", severity=True)
    cons_block = _findings_html("considerations", "None recorded.")
    points = _findings_html("evidence_map", "No grounded observations were recorded.")

    kq = "".join(f"<li>{_esc(q)}</li>" for q in (memo.get("key_questions") or []))
    kq_block = f"<ul>{kq}</ul>" if kq else "<p>None recorded.</p>"

    idx_rows = "".join(
        f"<tr><td>[{fn[c]}]</td><td>{_esc(index[c].get('source_label', ''))}</td>"
        f"<td>{_esc(index[c].get('ref', ''))}</td>"
        f"<td>{_esc(index[c].get('summary', ''))}</td>"
        f"<td>{_esc(index[c].get('when', ''))}</td></tr>"
        if c in index else
        f"<tr><td>[{fn[c]}]</td><td colspan='4'>{_GONE}</td></tr>"
        for c in cited
    ) or "<tr><td colspan='5'>No records cited.</td></tr>"

    # Appendix: every cited document (full extraction table) + every cited
    # platform section, each deterministic. docfig cites collapse into their
    # parent document's section, rendered once.
    docs_by_id = {str(d.get("id")): d for d in docs or []}
    appendix = ""
    seen_docs: set = set()
    seen_sections: set = set()
    seen_native: set = set()
    for c in cited:
        if c.startswith("doc:") or c.startswith("docfig:"):
            did = c.split(":", 1)[1].split(".", 1)[0]
            if did in seen_docs:
                continue
            seen_docs.add(did)
            doc = docs_by_id.get(did)
            if doc:
                appendix += f"<div class='appendix-section'>{_doc_appendix_html(doc)}</div>"
        elif c.startswith("platform:"):
            section = c.split(":", 1)[1].split(".", 1)[0]
            if section in seen_sections:
                continue
            seen_sections.add(section)
            appendix += f"<div class='appendix-section'>{_platform_appendix_html(section, corpus)}</div>"
        elif c.startswith("jur:"):
            # Statutes get their own appendix — see _jurisdiction_appendix_html.
            if "jurisdiction" in seen_native:
                continue
            seen_native.add("jurisdiction")
            appendix += f"<div class='appendix-section'>{_jurisdiction_appendix_html(cited, corpus)}</div>"
        else:
            # native operational record (incident:, er_case:, discipline:, …) —
            # one appendix table per source, listing the cited records.
            source_key = index.get(c, {}).get("source")
            if not source_key or source_key in seen_native:
                continue
            seen_native.add(source_key)
            appendix += f"<div class='appendix-section'>{_native_appendix_html(source_key, cited, corpus)}</div>"

    notes = "".join(f"<li>{_esc(n)}</li>" for n in corpus.get("notes") or [])
    notes_block = f"<h2>Scope notes</h2><ul>{notes}</ul>" if notes else ""

    doc_rows = "".join(
        f"<tr><td>{_esc(d.get('filename'))}</td><td>{_esc(_hum(d.get('doc_type')) or '—')}</td>"
        f"<td>{_esc(_hum(d.get('status')))}</td><td>{_fmt_dt(d.get('created_at'))}</td></tr>"
        for d in docs or []
    ) or "<tr><td colspan='4'>No documents uploaded.</td></tr>"

    kind_label = "On-platform Matcha client" if session.get("subject_kind") == "company" \
        else "Off-platform client (broker-recorded data)"
    mode = _lookup_template(session.get("template_key"))
    mode_cell = (f"<div><div class='l'>Mode</div><div class='v'>{_esc(mode['label'])}</div></div>"
                 if mode else "")
    generated = datetime.now(timezone.utc).strftime("%B %d, %Y · %H:%M UTC")
    record_total = sum(len(s.get("records") or []) for s in corpus.get("sources", {}).values())

    return f"""<!DOCTYPE html><html><head><meta charset="utf-8">
      <style>{_PDF_CSS}{_MEMO_CSS_EXTRA}</style></head><body>
      <div class="letterhead">
        <div>
          <div class="brand">Matcha · Broker Pilot</div>
          <h1>Client Risk Analysis Memo</h1>
          <p class="sub">{_esc(session.get('title'))}</p>
        </div>
        <div class="meta">
          {f"<div class='company'>{_esc(broker_name)}</div>" if broker_name else ""}
          <div>Generated {generated}</div>
        </div>
      </div>

      <div class="prep">
        <div><div class="l">Client</div><div class="v">{_esc(subject_name)}</div></div>
        {mode_cell}
        <div><div class="l">Data basis</div><div class="v">{kind_label}</div></div>
        <div><div class="l">Records in scope</div><div class="v">{record_total}</div></div>
        <div><div class="l">Documents</div><div class="v">{len(docs or [])}</div></div>
        {f"<div><div class='l'>Prepared by</div><div class='v'>{_esc(broker_name)}</div></div>" if broker_name else ""}
      </div>

      <div class="narr"><b>About this memo.</b> A sourced analysis of this client's risk material — the broker's uploaded carrier documents combined with the client's platform records{", including the operational history generated on Matcha (incidents, ER cases, compliance, discipline, training)" if session.get('subject_kind') == 'company' else ""}. Every observation cites its underlying record; the evidence index and appendices reproduce the cited records verbatim. {_esc(DISCLAIMER)}</div>

      <h2>Analysis narrative</h2>
      <div class="narr">{narrative}</div>

      <h2>Key questions</h2>
      {kq_block}

      <h2>Strategic considerations</h2>
      {cons_block}

      <h2>Gaps identified in the record</h2>
      {gaps_block}

      <h2>Observations grounded in the material</h2>
      {points}

      <h2>Evidence index (cited records)</h2>
      <table><thead><tr><th>#</th><th>Source</th><th>Ref</th><th>Record</th><th>When</th></tr></thead>
      <tbody>{idx_rows}</tbody></table>

      <h2>Documents in this session</h2>
      <table><thead><tr><th>File</th><th>Type</th><th>Status</th><th>Uploaded</th></tr></thead>
      <tbody>{doc_rows}</tbody></table>

      {notes_block}
      {appendix}

      <div class="foot">{_esc(DISCLAIMER)}</div>
    </body></html>"""


async def _render_pdf(html_str: str) -> bytes:
    def _r() -> bytes:
        return render_pdf(html_str)
    return await asyncio.to_thread(_r)


async def build_memo_pdf(session: dict, subject_name: str, corpus: dict, memo: dict,
                         docs: list[dict], broker_name: str | None = None) -> dict:
    """Render the analysis memo. Returns ``{"pdf": bytes, "citations": [...]}``."""
    html = _memo_html(session, subject_name, corpus, memo, docs, broker_name=broker_name)
    pdf = await _render_pdf(html)
    return {"pdf": pdf, "citations": _cited_ids(memo)}
