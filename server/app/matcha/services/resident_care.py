"""Resident-care risk asset service — summary + insurer-facing PDF.

Packages the controls underwriters value in healthcare / senior-living (WTW
p.175 "a strong resident-care risk management program is a valuable asset to
highlight for prospective insurers"; p.176 MVR reviews at hire & annually):
safety programs, MVR-review currency, and credentialing currency (from the
existing employee_credentials data). Deterministic PDF (WeasyPrint, SSRF-guarded).
"""

import html
from uuid import UUID

PROGRAM_LABELS = {
    "fall_prevention": "Fall prevention",
    "infection_control": "Infection control",
    "abuse_prevention": "Abuse prevention",
    "emergency_prep": "Emergency preparedness",
    "medication_safety": "Medication safety",
    "other": "Other",
}


async def summary(conn, company_id: UUID) -> dict:
    """Counts for the resident-care dashboard + asset cover page."""
    prog = await conn.fetch(
        "SELECT program_type, status FROM safety_programs WHERE company_id = $1", company_id
    )
    active = [p for p in prog if p["status"] == "active"]
    by_type = sorted({PROGRAM_LABELS.get(p["program_type"], p["program_type"]) for p in active})

    mvr = await conn.fetchrow(
        """
        SELECT COUNT(*) AS total,
               COUNT(*) FILTER (WHERE status = 'flagged') AS flagged,
               COUNT(*) FILTER (WHERE next_due_date IS NOT NULL AND next_due_date < CURRENT_DATE) AS overdue,
               COUNT(*) FILTER (WHERE status = 'clear'
                     AND (next_due_date IS NULL OR next_due_date >= CURRENT_DATE)) AS current
        FROM mvr_reviews WHERE company_id = $1
        """,
        company_id,
    )

    # Credentialing currency reuses employee_credentials (keyed by org_id = company id).
    cred = await conn.fetchrow(
        """
        SELECT COUNT(*) AS total,
               COUNT(*) FILTER (WHERE license_expiration IS NOT NULL
                     AND license_expiration < CURRENT_DATE) AS expired
        FROM employee_credentials WHERE org_id = $1
        """,
        company_id,
    )
    cred_total = int(cred["total"] or 0)
    cred_expired = int(cred["expired"] or 0)

    return {
        "programs": {"active": len(active), "total": len(prog), "active_types": by_type},
        "mvr": {
            "total": int(mvr["total"] or 0), "flagged": int(mvr["flagged"] or 0),
            "overdue": int(mvr["overdue"] or 0), "current": int(mvr["current"] or 0),
        },
        "credentialing": {
            "total": cred_total, "expired": cred_expired,
            "current_pct": round(100 * (cred_total - cred_expired) / cred_total) if cred_total else None,
        },
    }


# --- asset PDF (deterministic) ---------------------------------------------

def _esc(v) -> str:
    return html.escape(str(v)) if v is not None else "—"


def _asset_html(company_name: str, s: dict, programs: list[dict], mvr: list[dict]) -> str:
    prog_rows = "".join(
        f"<tr><td>{_esc(PROGRAM_LABELS.get(p['program_type'], p['program_type']))}</td>"
        f"<td>{_esc(p['name'])}</td><td>{_esc(p['owner'])}</td>"
        f"<td class='st {p['status']}'>{_esc(p['status'].upper())}</td>"
        f"<td>{_esc(p['last_reviewed_date'])}</td></tr>"
        for p in programs
    ) or "<tr><td colspan='5'>No safety programs on file.</td></tr>"

    mvr_rows = "".join(
        f"<tr><td>{_esc(m['driver_name'])}</td><td>{_esc(m['review_type'])}</td>"
        f"<td>{_esc(m['review_date'])}</td>"
        f"<td class='st {m['status']}'>{_esc(m['status'].upper())}</td>"
        f"<td>{_esc(m['next_due_date'])}</td></tr>"
        for m in mvr
    ) or "<tr><td colspan='5'>No MVR reviews on file.</td></tr>"

    cred = s["credentialing"]
    cred_line = (f"{cred['current_pct']}% of {cred['total']} licensed staff current"
                 if cred["current_pct"] is not None else "No licensed-staff credentials tracked")

    return f"""<!DOCTYPE html><html><head><meta charset="utf-8"><style>
      body {{ font-family: -apple-system, Helvetica, sans-serif; color:#1a1a2e; padding:30px; font-size:11px; }}
      h1 {{ color:#1f8a5b; margin:0 0 2px; font-size:22px; }}
      .sub {{ color:#666; margin:0 0 16px; }}
      h2 {{ font-size:13px; border-bottom:2px solid #1f8a5b; padding-bottom:4px; margin:18px 0 8px; }}
      .grid {{ display:flex; gap:8px; flex-wrap:wrap; margin-bottom:6px; }}
      .cell {{ border:1px solid #e5e7eb; border-radius:8px; padding:8px 12px; min-width:120px; }}
      .cell .l {{ font-size:8px; text-transform:uppercase; letter-spacing:.6px; color:#888; }}
      .cell .v {{ font-size:18px; font-weight:300; font-family:monospace; margin-top:3px; }}
      table {{ width:100%; border-collapse:collapse; margin-top:4px; }}
      th {{ text-align:left; font-size:8px; text-transform:uppercase; color:#888; border-bottom:1px solid #ddd; padding:4px 6px; }}
      td {{ padding:4px 6px; border-bottom:1px solid #f0f0f0; }}
      .st {{ font-size:8px; font-weight:700; }} .st.active,.st.clear{{color:#1f8a5b}} .st.flagged{{color:#b23b3b}} .st.pending,.st.inactive{{color:#b8902f}}
      .foot {{ margin-top:24px; color:#999; font-size:8px; border-top:1px solid #eee; padding-top:6px; }}
    </style></head><body>
      <h1>Resident-Care Risk Management Program</h1>
      <p class="sub">{_esc(company_name)} — prepared for prospective insurers</p>

      <h2>Program summary</h2>
      <div class="grid">
        <div class="cell"><div class="l">Active programs</div><div class="v">{_esc(s['programs']['active'])}</div></div>
        <div class="cell"><div class="l">MVR current</div><div class="v">{_esc(s['mvr']['current'])}/{_esc(s['mvr']['total'])}</div></div>
        <div class="cell"><div class="l">MVR overdue</div><div class="v">{_esc(s['mvr']['overdue'])}</div></div>
        <div class="cell"><div class="l">Credentialing</div><div class="v">{_esc(cred['current_pct'] if cred['current_pct'] is not None else '—')}{'%' if cred['current_pct'] is not None else ''}</div></div>
      </div>
      <p>{_esc(cred_line)}.</p>

      <h2>Safety &amp; risk-management programs</h2>
      <table><thead><tr><th>Type</th><th>Program</th><th>Owner</th><th>Status</th><th>Last reviewed</th></tr></thead>
        <tbody>{prog_rows}</tbody></table>

      <h2>Motor-vehicle-record (MVR) reviews</h2>
      <table><thead><tr><th>Driver</th><th>Type</th><th>Reviewed</th><th>Status</th><th>Next due</th></tr></thead>
        <tbody>{mvr_rows}</tbody></table>

      <div class="foot">Prepared by Matcha. Resident-care controls drawn from the client's safety, MVR, and
      credentialing records. Present alongside the loss run and insurance application.</div>
    </body></html>"""


async def render_asset_pdf(company_name: str, s: dict, programs: list[dict], mvr: list[dict]) -> bytes:
    from app.core.services.pdf import render_pdf_async

    return await render_pdf_async(_asset_html(company_name, s, programs, mvr))
