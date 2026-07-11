"""ACORD form generation (branded equivalents of 125 / 126 / 130 / 140).

Not a fill of the official fillable ACORD PDFs (that needs a PDF-form library +
form licensing) — a Matcha-branded PDF that carries the same field set, built
from data already held (company profile, Statement of Values, WC class exposures,
loss runs). Reuses the WeasyPrint render stack (``safe_url_fetcher``) like the
submission packet + fleet PDF. Best-effort: a missing data source renders an
empty section, never a 500.
"""

import asyncio
import html
from uuid import UUID

from app.core.services.pdf import safe_url_fetcher
from . import property_sov, wc_depth

FORMS = {
    "125": "Commercial Insurance Application",
    "126": "Commercial General Liability Section",
    "130": "Workers Compensation Application",
    "140": "Property Section",
}


def _esc(v) -> str:
    return html.escape(str(v)) if v is not None else "—"


def _money(v) -> str:
    try:
        n = float(v)
    except (TypeError, ValueError):
        return "—"
    if n >= 1_000_000:
        return f"${n/1_000_000:.1f}M".replace(".0M", "M")
    if n >= 1_000:
        return f"${n/1_000:.0f}K"
    return f"${n:.0f}"


async def build_acord_context(conn, company_id: UUID) -> dict:
    """Pull every source the four forms draw on. Each piece is best-effort."""
    company = await conn.fetchrow(
        "SELECT name, industry FROM companies WHERE id = $1", company_id
    )
    locations = await conn.fetch(
        "SELECT city, state, county FROM business_locations "
        "WHERE company_id = $1 AND COALESCE(is_active, true) = true",
        company_id,
    )

    buildings, sov_rollup = [], None
    try:
        buildings = await property_sov.list_buildings(conn, company_id)
        if buildings:
            from datetime import date
            sov_rollup = property_sov.rollup(buildings, date.today().year)
    except Exception:
        buildings, sov_rollup = [], None

    wc_exposures = []
    try:
        wc_exposures = await wc_depth.class_exposures(conn, company_id)
    except Exception:
        wc_exposures = []

    return {
        "company": dict(company) if company else {"name": "Client"},
        "locations": [dict(r) for r in locations],
        "buildings": buildings,
        "sov_rollup": sov_rollup,
        "wc_exposures": wc_exposures,
    }


def _header_html(form: str, ctx: dict) -> str:
    c = ctx["company"]
    locs = ", ".join(f"{_esc(l.get('city'))}, {_esc(l.get('state'))}" for l in ctx["locations"]) or "—"
    return (f"<h1>ACORD {form} — {_esc(FORMS[form])}</h1>"
            f"<div class='sub'>Matcha-branded equivalent · not an official ACORD facsimile</div>"
            f"<table class='kv'>"
            f"<tr><td>Named insured</td><td>{_esc(c.get('name'))}</td></tr>"
            f"<tr><td>Industry</td><td>{_esc(c.get('industry'))}</td></tr>"
            f"<tr><td>Locations</td><td>{locs}</td></tr>"
            f"</table>")


def _acord130_html(ctx: dict) -> str:
    rows = "".join(
        f"<tr><td>{_esc(e.get('class_code'))}</td><td>{_esc(e.get('state'))}</td>"
        f"<td>{_esc(e.get('description'))}</td><td>{_money(e.get('payroll'))}</td>"
        f"<td>{_esc(e.get('headcount'))}</td><td>{_money(e.get('est_manual_premium'))}</td></tr>"
        for e in ctx["wc_exposures"]
    ) or "<tr><td colspan='6'>No WC class exposures on file.</td></tr>"
    return ("<h2>Workers Compensation — class exposures</h2>"
            "<table class='grid'><tr><th>Class</th><th>State</th><th>Description</th>"
            "<th>Payroll</th><th>Headcount</th><th>Est. manual premium</th></tr>"
            f"{rows}</table>")


def _acord140_html(ctx: dict) -> str:
    rollup = ctx.get("sov_rollup") or {}
    rows = "".join(
        f"<tr><td>{_esc(b.get('name') or b.get('address'))}</td>"
        f"<td>{_esc(b.get('construction_type'))}</td><td>{_money(b.get('building_value'))}</td>"
        f"<td>{_money(b.get('contents_value'))}</td><td>{_money(b.get('bi_value'))}</td></tr>"
        for b in ctx["buildings"]
    ) or "<tr><td colspan='5'>No buildings on the Statement of Values.</td></tr>"
    tiv = _money(rollup.get("tiv")) if rollup else "—"
    return ("<h2>Property — Statement of Values</h2>"
            f"<div class='sub'>Total insured value: {tiv}</div>"
            "<table class='grid'><tr><th>Building</th><th>Construction</th><th>Building</th>"
            "<th>Contents</th><th>BI</th></tr>"
            f"{rows}</table>")


def _acord126_html(ctx: dict) -> str:
    return ("<h2>General Liability</h2>"
            "<div class='sub'>Premises/operations exposure basis. Limits carried are "
            "maintained under the Limit Adequacy module.</div>")


def _form_html(form: str, ctx: dict) -> str:
    body = _header_html(form, ctx)
    if form == "130":
        body += _acord130_html(ctx)
    elif form == "140":
        body += _acord140_html(ctx)
    elif form == "126":
        body += _acord126_html(ctx)
    else:  # 125 — commercial application: company + locations summary + a bit of each
        body += _acord130_html(ctx) + _acord140_html(ctx)
    style = ("<style>body{font-family:Helvetica,Arial,sans-serif;color:#1a1a1a;font-size:12px}"
             "h1{color:#1f8a5b;font-size:18px;margin:0}h2{color:#1f8a5b;font-size:14px;margin-top:18px}"
             ".sub{color:#666;font-size:11px;margin:2px 0 8px}"
             "table{border-collapse:collapse;width:100%;margin-top:6px}"
             ".kv td{padding:3px 8px;border:1px solid #ddd}"
             ".grid th,.grid td{padding:4px 8px;border:1px solid #ddd;text-align:left}"
             ".grid th{background:#f0f7f3}</style>")
    return f"<html><head>{style}</head><body>{body}</body></html>"


async def render_acord_pdf(form: str, ctx: dict) -> bytes:
    def _render() -> bytes:
        from weasyprint import HTML
        return HTML(string=_form_html(form, ctx), url_fetcher=safe_url_fetcher).write_pdf()
    return await asyncio.to_thread(_render)
