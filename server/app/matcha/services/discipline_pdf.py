"""Formal HR disciplinary letter PDF renderer.

Produces a single-page (or multi-page if needed) PDF suitable for
signature: company header, employee block, infraction description,
expected improvements, review date, signature lines for employee + HR.

Distinct from `matcha_work._render_project_pdf` (which renders the
generic project document). The discipline letter has fixed structure
because the document doubles as the legal record sent to the e-signature
provider.
"""

from __future__ import annotations

import asyncio
import html as _html
import logging
from datetime import date, datetime
from typing import Any, Optional

from fastapi import HTTPException

logger = logging.getLogger(__name__)


_LEVEL_LABELS = {
    "verbal_warning": "Verbal Warning",
    "written_warning": "Written Warning",
    "pip": "Performance Improvement Plan",
    "final_warning": "Final Warning",
    "suspension": "Suspension",
}

_SEVERITY_LABELS = {
    "minor": "Minor",
    "moderate": "Moderate",
    "severe": "Severe",
    "immediate_written": "Immediate Written",
}


def _fmt_date(value: Any) -> str:
    if value is None:
        return ""
    if isinstance(value, datetime):
        return value.strftime("%B %d, %Y")
    if isinstance(value, date):
        return value.strftime("%B %d, %Y")
    return str(value)


def _render_html(
    record: dict[str, Any],
    employee: dict[str, Any],
    company: dict[str, Any],
    issuer: Optional[dict[str, Any]],
) -> str:
    company_name = _html.escape(str(company.get("name") or "Company"))
    company_logo = company.get("logo_url") or ""
    name_parts = [
        str(employee.get("first_name") or "").strip(),
        str(employee.get("last_name") or "").strip(),
    ]
    derived_name = " ".join(p for p in name_parts if p) or str(employee.get("name") or "").strip() or "Employee"
    employee_name = _html.escape(derived_name)
    employee_role = _html.escape(str(employee.get("job_title") or ""))
    employee_email = _html.escape(str(employee.get("email") or ""))

    level_label = _LEVEL_LABELS.get(record.get("discipline_type"), str(record.get("discipline_type") or ""))
    severity_label = _SEVERITY_LABELS.get(record.get("severity"), str(record.get("severity") or ""))
    infraction_type = _html.escape(str(record.get("infraction_type") or "")).replace("_", " ").title()

    description = _html.escape(record.get("description") or "")
    expected_improvement = _html.escape(record.get("expected_improvement") or "")
    issued_date = _fmt_date(record.get("issued_date"))
    review_date = _fmt_date(record.get("review_date"))
    expires_at = _fmt_date(record.get("expires_at"))

    issuer_name = _html.escape(str((issuer or {}).get("name") or ""))
    issuer_title = _html.escape(str((issuer or {}).get("title") or "Human Resources"))

    logo_html = (
        f'<img class="logo" src="{_html.escape(company_logo)}" alt="">'
        if company_logo
        else ""
    )

    description_html = (
        f'<p class="body-text">{description}</p>'
        if description
        else '<p class="body-text muted">No description provided.</p>'
    )
    improvement_html = (
        f'<p class="body-text">{expected_improvement}</p>'
        if expected_improvement
        else '<p class="body-text muted">No specific improvement plan was attached to this record.</p>'
    )

    return f"""<!DOCTYPE html>
<html>
<head>
  <meta charset="UTF-8">
  <style>
    @page {{ size: A4; margin: 60px 70px; }}
    * {{ box-sizing: border-box; }}
    body {{
      font-family: 'Helvetica Neue', Arial, sans-serif;
      font-size: 11pt;
      line-height: 1.55;
      color: #1a1a1a;
      margin: 0;
    }}
    .header {{
      display: flex;
      align-items: center;
      justify-content: space-between;
      border-bottom: 3px solid #0f172a;
      padding-bottom: 12px;
      margin-bottom: 28px;
    }}
    .header .company {{ font-size: 14pt; font-weight: 700; color: #0f172a; }}
    .header .logo {{ max-height: 38px; max-width: 160px; }}
    h1.subject {{
      font-size: 19pt;
      font-weight: 700;
      color: #0f172a;
      margin: 0 0 4px 0;
    }}
    .subject-sub {{
      color: #475569;
      font-size: 11pt;
      margin: 0 0 28px 0;
    }}
    .meta-grid {{
      display: grid;
      grid-template-columns: 1fr 1fr;
      gap: 8px 24px;
      border: 1px solid #e2e8f0;
      border-radius: 6px;
      padding: 14px 18px;
      margin-bottom: 24px;
      background: #f8fafc;
    }}
    .meta-grid .label {{
      font-size: 8.5pt;
      text-transform: uppercase;
      letter-spacing: 0.06em;
      color: #64748b;
      font-weight: 600;
    }}
    .meta-grid .value {{ font-size: 11pt; color: #0f172a; }}
    h2 {{
      font-size: 12pt;
      font-weight: 600;
      color: #0f172a;
      margin: 22px 0 8px 0;
      border-bottom: 1px solid #e2e8f0;
      padding-bottom: 4px;
    }}
    .body-text {{ margin: 6px 0 14px 0; color: #1e293b; white-space: pre-wrap; }}
    .body-text.muted {{ color: #94a3b8; font-style: italic; }}
    .signatures {{
      display: grid;
      grid-template-columns: 1fr 1fr;
      gap: 36px;
      margin-top: 48px;
    }}
    .sig-block .sig-line {{
      border-top: 1px solid #0f172a;
      margin-top: 48px;
      padding-top: 6px;
    }}
    .sig-block .sig-name {{ font-weight: 600; color: #0f172a; }}
    .sig-block .sig-role {{ font-size: 9pt; color: #64748b; }}
    .footer {{
      margin-top: 40px;
      padding-top: 12px;
      border-top: 1px solid #e2e8f0;
      font-size: 8pt;
      color: #94a3b8;
      text-align: center;
    }}
  </style>
</head>
<body>
  <div class="header">
    <div class="company">{company_name}</div>
    {logo_html}
  </div>

  <h1 class="subject">{level_label}</h1>
  <p class="subject-sub">Subject: {infraction_type or 'Disciplinary Action'} — {severity_label} severity</p>

  <div class="meta-grid">
    <div><div class="label">Employee</div><div class="value">{employee_name}</div></div>
    <div><div class="label">Date Issued</div><div class="value">{issued_date}</div></div>
    <div><div class="label">Role</div><div class="value">{employee_role or '—'}</div></div>
    <div><div class="label">Active Through</div><div class="value">{expires_at or '—'}</div></div>
    <div><div class="label">Email</div><div class="value">{employee_email or '—'}</div></div>
    <div><div class="label">Review Date</div><div class="value">{review_date or '—'}</div></div>
  </div>

  <h2>Description of Conduct</h2>
  {description_html}

  <h2>Expected Improvement</h2>
  {improvement_html}

  <h2>Acknowledgement</h2>
  <p class="body-text">
    Your signature below acknowledges that you have received and read this notice.
    It does not necessarily indicate agreement with the conclusions described above.
    Continued conduct of this nature may result in further disciplinary action,
    up to and including termination of employment.
  </p>

  <div class="signatures">
    <div class="sig-block">
      <div class="sig-line"></div>
      <div class="sig-name">{employee_name}</div>
      <div class="sig-role">Employee — Date: ____________________</div>
    </div>
    <div class="sig-block">
      <div class="sig-line"></div>
      <div class="sig-name">{issuer_name or 'Issuing Manager'}</div>
      <div class="sig-role">{issuer_title} — Date: {issued_date}</div>
    </div>
  </div>

  <div class="footer">
    Generated by Matcha — discipline record {_html.escape(str(record.get('id') or ''))}
  </div>
</body>
</html>"""


async def render_discipline_letter(
    record: dict[str, Any],
    employee: dict[str, Any],
    company: dict[str, Any],
    issuer: Optional[dict[str, Any]] = None,
    *,
    timeout_seconds: float = 30.0,
) -> bytes:
    """Render the disciplinary letter to PDF bytes via WeasyPrint."""
    full_html = _render_html(record, employee, company, issuer)

    try:
        from weasyprint import HTML
    except ImportError:
        raise HTTPException(status_code=500, detail="PDF generation not available (weasyprint missing)")

    try:
        return await asyncio.wait_for(
            asyncio.to_thread(lambda: HTML(string=full_html).write_pdf()),
            timeout=timeout_seconds,
        )
    except asyncio.TimeoutError:
        raise HTTPException(status_code=504, detail="PDF generation timed out")
    except HTTPException:
        raise
    except Exception as e:  # noqa: BLE001
        logger.exception("Discipline PDF render failed for record %s", record.get("id"))
        raise HTTPException(status_code=500, detail=f"PDF generation failed: {type(e).__name__}")
