"""Training certificate PDF renderer.

WeasyPrint inline-CSS pattern, mirrors `_render_project_pdf` in
`server/app/matcha/routes/matcha_work.py`. Generated PDFs uploaded to a
private S3 prefix (`training-certificates/`) — retention enforced by an
S3 lifecycle policy (1500 days / ~4 years) and surfaced in DB via
`training_records.retention_until`.
"""

import asyncio
import html as _html
import logging
from datetime import date, datetime
from typing import Optional
from uuid import UUID, uuid4


from ...core.services.pdf import render_pdf
from ...core.services.storage import get_storage

logger = logging.getLogger(__name__)


def _esc(value: Optional[str]) -> str:
    return _html.escape(value or "")


def _format_date(d) -> str:
    if d is None:
        return ""
    if isinstance(d, datetime):
        d = d.date()
    if isinstance(d, date):
        return d.strftime("%B %-d, %Y")
    return str(d)


def _build_html(
    *,
    employee_first: str,
    employee_last: str,
    company_name: str,
    training_title: str,
    variant_label: str,
    completed_date: date,
    score_percent: float,
    required_minutes: int,
    expiration_date: Optional[date],
    attested_at: datetime,
    attestation_ip: str,
    certificate_id: UUID,
    legal_citation: str = "California SB 1343 / Gov. Code §12950.1",
) -> str:
    return f"""<!DOCTYPE html>
<html><head><meta charset="UTF-8"><style>
  @page {{ size: Letter; margin: 60px 70px; }}
  body {{ font-family: 'Helvetica Neue', Arial, sans-serif; color: #0f172a; }}
  .border {{ border: 6px double #16a34a; padding: 50px 56px; }}
  .eyebrow {{ font-size: 11pt; letter-spacing: .25em; color: #16a34a;
              text-transform: uppercase; }}
  h1 {{ font-size: 30pt; font-weight: 700; margin: 8px 0 24px 0;
        line-height: 1.15; }}
  .recipient {{ font-size: 24pt; font-weight: 600; margin: 24px 0 8px 0; }}
  .training {{ font-size: 13pt; color: #334155; margin-bottom: 32px; }}
  .grid {{ display: grid; grid-template-columns: 1fr 1fr; gap: 16px;
           font-size: 11pt; margin-top: 32px; }}
  .grid .label {{ color: #64748b; text-transform: uppercase;
                  font-size: 9pt; letter-spacing: .15em; }}
  .grid .value {{ color: #0f172a; font-weight: 500; padding-top: 2px; }}
  .attestation {{ margin-top: 36px; font-size: 10pt; color: #334155;
                  line-height: 1.55; padding: 16px; background: #f8fafc;
                  border-left: 3px solid #16a34a; }}
  .footer {{ margin-top: 40px; font-size: 8pt; color: #94a3b8;
             text-align: center; }}
  .cert-id {{ font-family: 'SF Mono', Monaco, Consolas, monospace;
              font-size: 8pt; color: #64748b; }}
</style></head><body>
<div class="border">
  <div class="eyebrow">Certificate of Completion</div>
  <h1>{_esc(training_title)}</h1>
  <p>This certifies that</p>
  <div class="recipient">{_esc(employee_first)} {_esc(employee_last)}</div>
  <p>completed the training program in compliance with</p>
  <div class="training">{_esc(legal_citation)}</div>

  <div class="grid">
    <div><div class="label">Company</div>
         <div class="value">{_esc(company_name)}</div></div>
    <div><div class="label">Variant</div>
         <div class="value">{_esc(variant_label)}</div></div>
    <div><div class="label">Completion Date</div>
         <div class="value">{_format_date(completed_date)}</div></div>
    <div><div class="label">Score</div>
         <div class="value">{score_percent:.1f}%</div></div>
    <div><div class="label">Duration Required</div>
         <div class="value">{required_minutes} minutes</div></div>
    <div><div class="label">Valid Until</div>
         <div class="value">{_format_date(expiration_date) or "—"}</div></div>
  </div>

  <div class="attestation">
    <strong>Attestation.</strong> The recipient affirmed on
    {_format_date(attested_at)} from IP {_esc(attestation_ip)} that they
    personally completed all training modules and the assessment without
    assistance, and understand that this certificate is a legal record retained
    by their employer for a minimum of four years pursuant to 2 CCR §11024(a)(10).
  </div>

  <div class="footer">
    <div class="cert-id">Certificate ID: {certificate_id}</div>
    Issued by Matcha on behalf of {_esc(company_name)}
  </div>
</div>
</body></html>"""


async def render_certificate_pdf(
    *,
    employee_first: str,
    employee_last: str,
    company_name: str,
    training_title: str,
    variant_label: str,
    completed_date: date,
    score_percent: float,
    required_minutes: int,
    expiration_date: Optional[date],
    attested_at: datetime,
    attestation_ip: str,
    certificate_id: UUID,
) -> bytes:
    """Render the certificate HTML to PDF bytes.

    60-second hard timeout (mirrors `_render_project_pdf`).
    """
    full_html = _build_html(
        employee_first=employee_first,
        employee_last=employee_last,
        company_name=company_name,
        training_title=training_title,
        variant_label=variant_label,
        completed_date=completed_date,
        score_percent=score_percent,
        required_minutes=required_minutes,
        expiration_date=expiration_date,
        attested_at=attested_at,
        attestation_ip=attestation_ip,
        certificate_id=certificate_id,
    )
    return await asyncio.wait_for(
        asyncio.to_thread(lambda: render_pdf(full_html)),
        timeout=60.0,
    )


async def upload_certificate(
    *,
    pdf_bytes: bytes,
    company_id: UUID,
    employee_id: UUID,
    certificate_id: UUID,
) -> str:
    """Upload to private S3 prefix `training-certificates/`. Returns s3:// URI.

    Filename: {company_id}_{employee_id}_{certificate_id}.pdf
    """
    storage = get_storage()
    filename = f"{company_id}_{employee_id}_{certificate_id}.pdf"
    return await storage.upload_private_file(
        pdf_bytes,
        filename,
        prefix="training-certificates",
        content_type="application/pdf",
    )


def new_certificate_id() -> UUID:
    return uuid4()
