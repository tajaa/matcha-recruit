"""OSHA Form 300A PDF rendering.

Standalone WeasyPrint helper (kept out of the route file like matcha_work's
_render_project_pdf). Builds an HTML replica of the federal Form 300A
"Summary of Work-Related Injuries and Illnesses" and rasterizes to PDF bytes.
"""
import asyncio
import html as _html
import logging

from fastapi import HTTPException

logger = logging.getLogger(__name__)


def _esc(val) -> str:
    """HTML-escape a value, rendering None as an empty string."""
    if val is None:
        return ""
    return _html.escape(str(val))


def _num(val) -> str:
    """Render a numeric total, blank-safe (0 still prints as 0)."""
    return "0" if val in (None, "") else _html.escape(str(val))


def _build_300a_html(s: dict) -> str:
    """Assemble the Form 300A HTML from a summary dict (Osha300ASummary.model_dump())."""
    establishment = _esc(s.get("establishment_name"))
    addr_line = ", ".join(
        p for p in [_esc(s.get("address")), _esc(s.get("city")), _esc(s.get("state")), _esc(s.get("zipcode"))] if p
    )
    year = _esc(s.get("year"))

    return f"""<!DOCTYPE html>
<html><head><meta charset="utf-8"><style>
  @page {{ size: letter; margin: 0.5in 0.6in; }}
  body {{ font-family: 'Helvetica Neue', Arial, sans-serif; font-size: 9.5pt; color: #111; }}
  .formhdr {{ display: flex; justify-content: space-between; align-items: flex-start; border-bottom: 2px solid #111; padding-bottom: 6px; }}
  .formhdr h1 {{ font-size: 15pt; margin: 0; }}
  .formhdr .sub {{ font-size: 8pt; color: #444; margin-top: 2px; }}
  .formhdr .agency {{ text-align: right; font-size: 8pt; color: #444; }}
  .yearbox {{ border: 1.5px solid #111; padding: 4px 10px; font-size: 12pt; font-weight: 700; }}
  .note {{ font-size: 7.5pt; color: #555; margin: 8px 0 14px; line-height: 1.35; }}
  table {{ border-collapse: collapse; width: 100%; margin: 6px 0 16px; }}
  th, td {{ border: 1px solid #111; padding: 6px 8px; text-align: center; vertical-align: top; }}
  th {{ background: #f0f0f0; font-size: 7.5pt; text-transform: uppercase; letter-spacing: 0.04em; }}
  .grouphdr {{ background: #e2e2e2; font-weight: 700; text-align: left; font-size: 8.5pt; }}
  .bignum {{ font-size: 15pt; font-weight: 300; }}
  .colcode {{ font-size: 7pt; color: #666; }}
  .estab td {{ text-align: left; font-size: 9pt; }}
  .estab th {{ text-align: left; width: 28%; background: #fafafa; }}
  .cert {{ margin-top: 18px; border-top: 1px solid #111; padding-top: 10px; font-size: 8.5pt; line-height: 1.5; }}
  .sigline {{ display: inline-block; border-bottom: 1px solid #111; min-width: 220px; margin: 0 6px; }}
  .footer {{ margin-top: 22px; font-size: 7pt; color: #888; text-align: center; }}
</style></head><body>

  <div class="formhdr">
    <div>
      <h1>OSHA's Form 300A</h1>
      <div class="sub">Summary of Work-Related Injuries and Illnesses</div>
    </div>
    <div class="agency">
      U.S. Department of Labor<br>Occupational Safety and Health Administration<br>
      <div class="yearbox" style="margin-top:6px;">Year {year}</div>
    </div>
  </div>

  <div class="note">
    All establishments covered by Part 1904 must complete this Summary page, even if no work-related
    injuries or illnesses occurred during the year. Remember to review the Log to verify that the
    entries are complete and accurate before completing this summary.
  </div>

  <table>
    <tr>
      <td class="grouphdr" colspan="2">Number of Cases</td>
      <td class="grouphdr" colspan="2">Number of Days</td>
    </tr>
    <tr>
      <th>Total number of<br>deaths <span class="colcode">(G)</span></th>
      <th>Cases with days away<br>from work <span class="colcode">(H)</span></th>
      <th>Total days away<br>from work <span class="colcode">(K)</span></th>
      <th>Total days of job transfer<br>or restriction <span class="colcode">(L)</span></th>
    </tr>
    <tr>
      <td class="bignum">{_num(s.get('total_deaths'))}</td>
      <td class="bignum">{_num(s.get('total_days_away_cases'))}</td>
      <td class="bignum">{_num(s.get('total_days_away'))}</td>
      <td class="bignum">{_num(s.get('total_days_restricted'))}</td>
    </tr>
    <tr>
      <th>Cases with job transfer<br>or restriction <span class="colcode">(I)</span></th>
      <th>Other recordable<br>cases <span class="colcode">(J)</span></th>
      <th colspan="2">Total recordable cases</th>
    </tr>
    <tr>
      <td class="bignum">{_num(s.get('total_restricted_cases'))}</td>
      <td class="bignum">{_num(s.get('total_other_recordable'))}</td>
      <td class="bignum" colspan="2">{_num(s.get('total_cases'))}</td>
    </tr>
  </table>

  <table>
    <tr><td class="grouphdr" colspan="6">Injury and Illness Types — Total number of …</td></tr>
    <tr>
      <th>(M1) Injuries</th>
      <th>(M2) Skin<br>disorders</th>
      <th>(M3) Respiratory<br>conditions</th>
      <th>(M4) Poisonings</th>
      <th>(M5) Hearing<br>loss</th>
      <th>(M6) All other<br>illnesses</th>
    </tr>
    <tr>
      <td class="bignum">{_num(s.get('total_injuries'))}</td>
      <td class="bignum">{_num(s.get('total_skin_disorders'))}</td>
      <td class="bignum">{_num(s.get('total_respiratory'))}</td>
      <td class="bignum">{_num(s.get('total_poisonings'))}</td>
      <td class="bignum">{_num(s.get('total_hearing_loss'))}</td>
      <td class="bignum">{_num(s.get('total_other_illnesses'))}</td>
    </tr>
  </table>

  <table class="estab">
    <tr><th>Establishment name</th><td>{establishment}</td></tr>
    <tr><th>Street / City / State / ZIP</th><td>{addr_line}</td></tr>
    <tr><th>Employer Identification No. (EIN)</th><td>{_esc(s.get('ein'))}</td></tr>
    <tr><th>Industry code (NAICS)</th><td>{_esc(s.get('naics'))}</td></tr>
    <tr><th>Annual average number of employees</th><td>{_esc(s.get('average_employees'))}</td></tr>
    <tr><th>Total hours worked by all employees last year</th><td>{_esc(s.get('total_hours_worked'))}</td></tr>
  </table>

  <div class="cert">
    <strong>Sign here.</strong> Knowingly falsifying this document may result in a fine.<br>
    I certify that I have examined this document and that to the best of my knowledge the entries are
    true, accurate, and complete.<br><br>
    Signed by <span class="sigline">{_esc(s.get('certified_by'))}</span>
    Title <span class="sigline">{_esc(s.get('certified_title'))}</span>
    Date <span class="sigline">{_esc(s.get('certified_date'))}</span>
  </div>

  <div class="footer">Generated by Matcha — replica of OSHA Form 300A for posting/recordkeeping.</div>
</body></html>"""


async def render_300a_pdf(summary: dict) -> bytes:
    """Render a 300A summary dict to PDF bytes (WeasyPrint, 60s timeout)."""
    full_html = _build_300a_html(summary)

    try:
        from weasyprint import HTML
    except ImportError as ie:
        logger.error("weasyprint import failed: %s", ie)
        raise HTTPException(
            status_code=501,
            detail="PDF generation not available — install weasyprint on the server (`pip install weasyprint`).",
        )

    try:
        return await asyncio.wait_for(
            asyncio.to_thread(lambda: HTML(string=full_html).write_pdf()),
            timeout=60.0,
        )
    except asyncio.TimeoutError:
        raise HTTPException(status_code=504, detail="PDF generation timed out.")
    except HTTPException:
        raise
    except Exception as e:
        logger.exception("OSHA 300A PDF render failed")
        raise HTTPException(status_code=500, detail=f"PDF generation failed: {type(e).__name__}")
