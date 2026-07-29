"""Single-incident report HTML builder for the PDF export.

Pure, self-contained HTML rendering (no DB, no I/O) — extracted out of
crud.py the same way _osha_pdf.py was extracted from osha.py, so the route
file stays handlers. The caller (crud.py's export_incident_pdf) fetches the
rows and rasterizes the returned string with WeasyPrint.
"""
import html as html_lib
import json
from datetime import datetime


def _jsonb(value, fallback):
    """asyncpg returns JSONB columns as str unless a codec is set. Coerce."""
    if value is None:
        return fallback
    if isinstance(value, str):
        try:
            return json.loads(value)
        except (ValueError, TypeError):
            return fallback
    return value


def _human_size(n) -> str:
    try:
        n = float(n or 0)
    except (ValueError, TypeError):
        return ""
    if n < 1024:
        return f"{int(n)} B"
    if n < 1024 * 1024:
        return f"{n / 1024:.0f} KB"
    return f"{n / (1024 * 1024):.1f} MB"


def _render_analysis_block(analysis_type: str, data: dict) -> str:
    """Render one cached AI analysis to HTML. Per-type for the known shapes,
    generic key→value fallback for anything else so an unmapped type never
    crashes the export."""
    e = html_lib.escape

    def _list(items, key=None):
        out = []
        for it in items or []:
            if key and isinstance(it, dict):
                out.append(e(str(it.get(key, ""))))
            elif isinstance(it, dict):
                out.append(e(", ".join(f"{k}: {v}" for k, v in it.items() if v)))
            else:
                out.append(e(str(it)))
        return "".join(f"<li>{x}</li>" for x in out if x)

    body = ""
    if analysis_type == "categorization":
        body = (
            f"<p><strong>Suggested type:</strong> {e(str(data.get('suggested_type', '—')))}"
            f" &middot; <strong>Confidence:</strong> {e(str(data.get('confidence', '—')))}</p>"
            f"<p>{e(str(data.get('reasoning', '')))}</p>"
        )
    elif analysis_type == "severity":
        body = (
            f"<p><strong>Suggested severity:</strong> {e(str(data.get('suggested_severity', '—')))}</p>"
            f"<ul>{_list(data.get('factors'))}</ul>"
            f"<p>{e(str(data.get('reasoning', '')))}</p>"
        )
    elif analysis_type == "root_cause":
        body = (
            f"<p><strong>Primary cause:</strong> {e(str(data.get('primary_cause', '—')))}</p>"
            f"<p><strong>Contributing factors:</strong></p><ul>{_list(data.get('contributing_factors'))}</ul>"
            f"<p><strong>Prevention:</strong></p><ul>{_list(data.get('prevention_suggestions'))}</ul>"
            f"<p>{e(str(data.get('reasoning', '')))}</p>"
        )
    elif analysis_type == "recommendations":
        recs = ""
        for r in (data.get("recommendations") or []):
            if not isinstance(r, dict):
                continue
            line = f"<strong>{e(str(r.get('action', '')))}</strong> — priority {e(str(r.get('priority', '—')))}"
            if r.get("responsible_party"):
                line += f" &middot; {e(str(r['responsible_party']))}"
            recs += f"<li>{line}</li>"
        body = f"<p>{e(str(data.get('summary', '')))}</p><ul>{recs}</ul>"
    elif analysis_type in ("policy_mapping",):
        matches = "".join(
            f"<li><strong>{e(str(m.get('policy_title', '')))}</strong>"
            f" — relevance {e(str(m.get('relevance', '—')))}"
            f"<br><span class='excerpt'>{e(str(m.get('relevant_excerpt', '')))}</span></li>"
            for m in (data.get("matches") or [])
            if isinstance(m, dict)
        )
        body = f"<p>{e(str(data.get('summary', '')))}</p><ul>{matches}</ul>"
    else:
        rows = ""
        for k, v in (data or {}).items():
            if k == "generated_at":
                continue
            if isinstance(v, list):
                v = "; ".join(str(x) for x in v)
            rows += f"<p><strong>{e(k.replace('_', ' ').title())}:</strong> {e(str(v))}</p>"
        body = rows
    label = analysis_type.replace("_", " ").title()
    return f"<div class='analysis'><h3>{e(label)}</h3>{body}</div>"


def _build_incident_report_html(incident, messages, analyses, documents) -> str:
    """Pure HTML builder for the single-incident export. Every interpolated
    value is HTML-escaped. Self-contained document (no external assets)."""
    e = html_lib.escape

    def _fmt(d) -> str:
        return d.strftime("%Y-%m-%d %H:%M") if d else "—"

    def _field(label, value) -> str:
        return f"<tr><th>{e(label)}</th><td>{e(str(value)) if value not in (None, '') else '—'}</td></tr>"

    sev = (incident["severity"] or "").lower()
    sev_color = {"critical": "#dc2626", "high": "#ea580c", "medium": "#ca8a04", "low": "#16a34a"}.get(sev, "#52525b")

    # Location
    if incident.get("location_name"):
        place = ", ".join(p for p in (incident.get("location_city"), incident.get("location_state")) if p)
        location = f"{incident['location_name']}{f' — {place}' if place else ''}"
    else:
        location = incident.get("location") or "—"

    # Overview
    witnesses = _jsonb(incident.get("witnesses"), [])
    category = _jsonb(incident.get("category_data"), {})
    witnesses_html = ""
    for w in witnesses:
        if not isinstance(w, dict):
            continue
        line = f"<strong>{e(str(w.get('name', 'Unnamed')))}</strong>"
        if w.get("contact"):
            line += f" ({e(str(w['contact']))})"
        if w.get("statement"):
            line += f": {e(str(w['statement']))}"
        witnesses_html += f"<li>{line}</li>"
    witnesses_html = witnesses_html or "<li>None recorded</li>"
    category_html = "".join(
        f"<tr><th>{e(str(k).replace('_', ' ').title())}</th><td>{e(str(v))}</td></tr>"
        for k, v in category.items() if v not in (None, "", [], {})
    )

    # Activity / Notes — copilot transcript (text turns only)
    turn_html = ""
    for m in messages:
        if m["message_type"] != "text":
            continue
        role = m["role"]
        if role not in ("user", "assistant"):
            continue
        who = "Copilot" if role == "assistant" else "User"
        turn_html += (
            f"<div class='turn'><div class='turn-head'>{e(who)} "
            f"<span class='ts'>{_fmt(m['created_at'])}</span></div>"
            f"<div class='turn-body'>{e(m['content'] or '')}</div></div>"
        )
    if not turn_html:
        turn_html = "<p class='empty'>No activity recorded.</p>"

    # AI Guidance
    analyses_html = "".join(
        _render_analysis_block(a["analysis_type"], _jsonb(a["analysis_data"], {}))
        for a in analyses
    ) or "<p class='empty'>No AI analysis recorded.</p>"

    # Documents
    if documents:
        doc_rows = "".join(
            f"<tr><td>{e(d['filename'] or '')}</td>"
            f"<td>{e((d['document_type'] or 'other').replace('_', ' ').title())}</td>"
            f"<td>{_human_size(d['file_size'])}</td>"
            f"<td class='num'>{_fmt(d['created_at'])}</td></tr>"
            for d in documents
        )
        documents_html = (
            "<table class='grid'><thead><tr><th>Filename</th><th>Type</th>"
            f"<th>Size</th><th>Uploaded</th></tr></thead><tbody>{doc_rows}</tbody></table>"
        )
    else:
        documents_html = "<p class='empty'>No documents attached.</p>"

    title = e(incident["title"] or "Incident")
    return f"""<!DOCTYPE html>
<html><head><meta charset="utf-8"><style>
    @page {{ size: A4; margin: 40px; }}
    body {{ font-family: -apple-system, Helvetica, Arial, sans-serif; color: #18181b; font-size: 10pt; line-height: 1.45; }}
    h1 {{ font-size: 18pt; margin: 0 0 2px; }}
    h2 {{ font-size: 12pt; margin: 22px 0 8px; border-bottom: 2px solid #e4e4e7; padding-bottom: 4px; }}
    h3 {{ font-size: 10.5pt; margin: 12px 0 4px; color: #3f3f46; }}
    .sub {{ color: #71717a; font-size: 9pt; margin-bottom: 4px; }}
    .badges span {{ display: inline-block; font-size: 8pt; font-weight: 700; text-transform: uppercase;
        letter-spacing: 0.04em; padding: 2px 7px; border-radius: 4px; margin-right: 6px; }}
    .sev {{ color: #fff; }}
    table.kv {{ width: 100%; border-collapse: collapse; margin-top: 6px; }}
    table.kv th {{ text-align: left; width: 170px; color: #52525b; font-weight: 600; vertical-align: top; padding: 4px 8px 4px 0; font-size: 9pt; }}
    table.kv td {{ padding: 4px 0; vertical-align: top; }}
    table.grid {{ width: 100%; border-collapse: collapse; font-size: 9pt; margin-top: 6px; }}
    table.grid th {{ background: #f4f4f5; text-align: left; padding: 5px 8px; font-size: 7.5pt; text-transform: uppercase; letter-spacing: 0.05em; color: #52525b; }}
    table.grid td {{ padding: 5px 8px; border-bottom: 1px solid #e4e4e7; vertical-align: top; }}
    td.num {{ font-family: ui-monospace, monospace; font-size: 8pt; color: #52525b; }}
    p {{ margin: 4px 0; }} ul {{ margin: 4px 0; padding-left: 18px; }}
    .pre {{ white-space: pre-wrap; }}
    .turn {{ margin: 8px 0; padding-left: 10px; border-left: 2px solid #e4e4e7; }}
    .turn-head {{ font-size: 8.5pt; font-weight: 700; color: #3f3f46; }}
    .turn-head .ts {{ font-weight: 400; color: #a1a1aa; font-family: ui-monospace, monospace; }}
    .turn-body {{ white-space: pre-wrap; }}
    .analysis {{ margin: 10px 0; }}
    .excerpt {{ color: #71717a; font-style: italic; }}
    .empty {{ color: #a1a1aa; font-style: italic; }}
</style></head><body>
    <h1>{title}</h1>
    <div class="sub">{e(incident['incident_number'] or '')} &middot; {e(incident.get('company_name') or '')}</div>
    <div class="badges">
        <span class="sev" style="background: {sev_color}">{e((incident['severity'] or '').upper())}</span>
        <span style="background:#f4f4f5; color:#3f3f46">{e((incident['status'] or '').replace('_', ' ').upper())}</span>
        <span style="background:#f4f4f5; color:#3f3f46">{e((incident['incident_type'] or '').replace('_', ' ').upper())}</span>
    </div>

    <h2>Details</h2>
    <table class="kv">
        {_field('Occurred', _fmt(incident['occurred_at']))}
        {_field('Location', location)}
        {_field('Reported by', incident.get('reported_by_name'))}
        {_field('Reporter email', incident.get('reported_by_email'))}
        {_field('Reported at', _fmt(incident.get('reported_at')))}
    </table>
    <h3>Description</h3>
    <p class="pre">{e(incident.get('description') or '—')}</p>
    <h3>Root cause</h3>
    <p class="pre">{e(incident.get('root_cause') or '—')}</p>
    <h3>Corrective actions</h3>
    <p class="pre">{e(incident.get('corrective_actions') or '—')}</p>
    <h3>Witnesses</h3>
    <ul>{witnesses_html}</ul>
    {f'<h3>Category data</h3><table class="kv">{category_html}</table>' if category_html else ''}

    <h2>Activity &amp; Notes</h2>
    {turn_html}

    <h2>AI Guidance</h2>
    {analyses_html}

    <h2>Documents</h2>
    {documents_html}

    <div class="sub" style="margin-top:28px">Generated {datetime.utcnow().strftime('%Y-%m-%d %H:%M UTC')}</div>
</body></html>"""


def _export_location_label(r) -> str:
    if r["location_name"]:
        place = ", ".join([p for p in (r["location_city"], r["location_state"]) if p])
        return f"{r['location_name']}{f' — {place}' if place else ''}"
    return r["location"] or "—"


def _export_fmt_dt(d) -> str:
    return d.strftime("%Y-%m-%d %H:%M") if d else ""


def _build_incidents_export_html(rows, period_label: str, row_limit: int) -> str:
    """Pure HTML builder for the multi-incident PDF export (crud.py's
    GET /export). Every interpolated value is HTML-escaped — `rows` come
    straight off `ir_incidents`/`business_locations`, both tenant-writable,
    so an incident title or a location name/city/state must never reach the
    page unescaped."""
    e = html_lib.escape

    sev_color = {
        "critical": "#dc2626", "high": "#ea580c",
        "medium": "#ca8a04", "low": "#16a34a",
    }

    rows_html = "".join(
        f"""
        <tr>
            <td class="num">{e(r['incident_number'] or '')}</td>
            <td>{e(r['title'] or '')}</td>
            <td>{e((r['incident_type'] or '').replace('_', ' ').title())}</td>
            <td><span class="sev" style="color: {sev_color.get(r['severity'] or '', '#52525b')}">{e((r['severity'] or '').upper())}</span></td>
            <td>{e((r['status'] or '').replace('_', ' ').title())}</td>
            <td>{e(_export_location_label(r))}</td>
            <td class="num">{e(_export_fmt_dt(r['occurred_at']))}</td>
        </tr>
        """
        for r in rows
    )
    truncated_note = (
        f"<p class='note'>Result set capped at {row_limit} rows.</p>"
        if len(rows) >= row_limit else ""
    )
    return f"""
    <html><head><meta charset="utf-8"><style>
        @page {{ size: Letter landscape; margin: 0.5in; }}
        body {{ font-family: -apple-system, Helvetica, Arial, sans-serif; color: #18181b; font-size: 9pt; }}
        h1 {{ font-size: 16pt; margin: 0 0 4px; }}
        .meta {{ color: #71717a; font-size: 8pt; margin-bottom: 12px; }}
        .meta strong {{ color: #18181b; }}
        table {{ width: 100%; border-collapse: collapse; font-size: 8pt; }}
        th, td {{ text-align: left; padding: 6px 8px; border-bottom: 1px solid #e4e4e7; vertical-align: top; }}
        th {{ background: #f4f4f5; font-size: 7pt; text-transform: uppercase; letter-spacing: 0.05em; color: #52525b; }}
        td.num {{ font-family: ui-monospace, "SF Mono", monospace; font-size: 7.5pt; color: #52525b; }}
        .sev {{ font-weight: 700; font-size: 7pt; }}
        .note {{ color: #71717a; font-size: 7pt; margin-top: 12px; font-style: italic; }}
    </style></head><body>
    <h1>Incident Report</h1>
    <div class="meta">
        <strong>{len(rows)}</strong> incident{'s' if len(rows) != 1 else ''} ·
        Generated {datetime.utcnow().strftime('%Y-%m-%d %H:%M UTC')}
        {f' · Period {e(period_label)}' if period_label else ''}
    </div>
    <table>
        <thead>
            <tr><th>#</th><th>Title</th><th>Type</th><th>Severity</th><th>Status</th><th>Location</th><th>Occurred</th></tr>
        </thead>
        <tbody>{rows_html}</tbody>
    </table>
    {truncated_note}
    </body></html>
    """
