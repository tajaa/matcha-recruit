"""OSHA Form 300A PDF rendering.

Standalone WeasyPrint helper (kept out of the route file like matcha_work's
_render_project_pdf). Builds an HTML replica of the federal Form 300A
"Summary of Work-Related Injuries and Illnesses" and rasterizes to PDF bytes.

Layout follows the official federal Form 300A (OMB approved OSHA-0042204):

  Header           OSHA's Form 300A   |   Year box  |  USDOL · OSHA
  Note             Three short paragraphs on Part 1904 completion + review
  ┌─────────────────────────────┬──────────────────────────┐
  │ Number of Cases (G H I J)   │ Establishment Information│
  │ Number of Days (K L)        │   name / street / city / │
  │ Injury & Illness Types      │   state / zip /          │
  │   (M1 M2 M3 M4 M5 M6)       │   industry desc / NAICS  │
  │                             │ Employment Information   │
  │                             │   avg employees / hours  │
  └─────────────────────────────┴──────────────────────────┘
  Sign here   …   Company executive · Title · Phone · Date

Note: not a 1:1 pixel match to the federal scanned PDF — that's not necessary
for posting/recordkeeping (the rule is that the *content* be correct, posted
in a "conspicuous place"). The block names, column letter codes (G–M6), and
field labels are what regulators look for.
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


def _hours(val) -> str:
    """Render total hours worked with thousands separators ('410,000')."""
    if val in (None, ""):
        return ""
    try:
        return f"{int(val):,}"
    except (TypeError, ValueError):
        return _html.escape(str(val))


def _build_300a_html(s: dict) -> str:
    """Assemble the Form 300A HTML from a summary dict (Osha300ASummary.model_dump())."""
    year = _esc(s.get("year"))

    return f"""<!DOCTYPE html>
<html><head><meta charset="utf-8"><style>
  @page {{ size: letter landscape; margin: 0.4in 0.5in; }}
  body {{ font-family: 'Helvetica Neue', Arial, sans-serif; font-size: 9pt; color: #111; line-height: 1.2; }}

  /* Header */
  .formhdr {{ display: flex; justify-content: space-between; align-items: flex-start; border-bottom: 1.5px solid #111; padding-bottom: 6px; }}
  .formhdr h1 {{ font-size: 15pt; margin: 0; font-weight: 700; }}
  .formhdr .sub {{ font-size: 8pt; color: #444; margin-top: 2px; }}
  .formhdr .agency {{ text-align: right; font-size: 7.5pt; color: #333; }}
  .yearbox {{ display: inline-block; border: 1.5px solid #111; padding: 4px 14px; font-size: 13pt; font-weight: 700; margin-top: 4px; }}

  /* Intro / instruction paragraphs */
  .note {{ font-size: 7pt; color: #444; margin: 5px 0 6px; line-height: 1.3; }}
  .note p {{ margin: 0 0 3px; }}

  /* Two-column main area */
  .main {{ display: flex; gap: 10px; align-items: stretch; }}
  .col-left {{ flex: 1.45; min-width: 0; }}
  .col-right {{ flex: 1; min-width: 0; }}

  /* Block — a bordered card with a grey title bar */
  .block {{ border: 1px solid #111; margin-bottom: 5px; }}
  .block-hdr {{ background: #d8d8d8; padding: 4px 8px; font-size: 8pt; font-weight: 700; text-transform: uppercase; letter-spacing: 0.04em; }}

  /* Number grids (cases / days / illness types) */
  .row4 {{ display: grid; grid-template-columns: 1fr 1fr 1fr 1fr; }}
  .row2 {{ display: grid; grid-template-columns: 1fr 1fr; border-top: 1px solid #111; }}
  .row6 {{ display: grid; grid-template-columns: repeat(6, 1fr); }}
  .cell {{ padding: 4px 6px; border-right: 1px solid #111; min-height: 56px; position: relative; }}
  .cell:last-child {{ border-right: none; }}
  .cell .label {{ font-size: 7pt; line-height: 1.25; color: #222; }}
  .cell .code {{ font-size: 7pt; color: #666; font-weight: 700; }}
  .cell .value {{ font-size: 15pt; font-weight: 300; text-align: center; margin-top: 4px; font-family: 'Courier New', monospace; }}

  /* Establishment / Employment Info — labeled fields with underline values */
  .field {{ display: flex; padding: 5px 8px; border-top: 1px solid #ddd; align-items: baseline; gap: 6px; }}
  .info-block .field:first-of-type {{ border-top: none; }}
  .field .lbl {{ font-size: 6.5pt; color: #555; text-transform: uppercase; letter-spacing: 0.03em; flex: 0 0 38%; line-height: 1.25; }}
  .field .val {{ font-size: 9pt; font-weight: 500; flex: 1; min-width: 0; border-bottom: 1px solid #aaa; min-height: 14px; padding-bottom: 1px; overflow-wrap: break-word; }}

  /* Cert block */
  .cert {{ margin-top: 8px; border-top: 1.5px solid #111; padding-top: 6px; font-size: 8.5pt; }}
  .cert .signline {{ font-style: italic; color: #444; font-size: 7.5pt; margin-top: 2px; }}
  .sigrow {{ display: grid; grid-template-columns: 2fr 1.4fr 1.2fr 1fr; gap: 14px; margin-top: 10px; }}
  .sigrow .siglbl {{ font-size: 6.5pt; color: #555; text-transform: uppercase; letter-spacing: 0.04em; }}
  .sigrow .sigval {{ border-bottom: 1px solid #111; padding: 4px 2px; font-size: 9.5pt; min-height: 16px; }}

  .postnote {{ margin-top: 8px; font-size: 9pt; font-weight: 700; color: #111; text-align: center; }}
  .burden {{ margin-top: 4px; font-size: 7.5pt; color: #444; text-align: center; line-height: 1.3; max-width: 8.5in; margin-left: auto; margin-right: auto; }}
  .footer {{ margin-top: 5px; font-size: 6.5pt; color: #aaa; text-align: center; }}
</style></head><body>

  <div class="formhdr">
    <div>
      <h1>OSHA's Form 300A</h1>
      <div class="sub">Summary of Work-Related Injuries and Illnesses</div>
    </div>
    <div class="agency">
      U.S. Department of Labor<br>
      Occupational Safety and Health Administration<br>
      <div class="yearbox">Year {year}</div>
    </div>
  </div>

  <div class="note">
    <p>All establishments covered by Part 1904 must complete this Summary page, even if no work-related
    injuries or illnesses occurred during the year. Remember to review the Log to verify that the entries are
    complete and accurate before completing this summary.</p>
    <p>Using the Log, count the individual entries you made for each category. Then write the totals below,
    making sure you've added the entries from every page of the Log. If you had no cases, write &quot;0.&quot;</p>
    <p>Employees, former employees, and their representatives have the right to review the OSHA Form 300 in
    its entirety. They also have limited access to the OSHA Form 301 or its equivalent. See 29 CFR
    Part 1904.35, in OSHA's recordkeeping rule, for further details on the access provisions for these forms.</p>
  </div>

  <div class="main">
    <div class="col-left">
      <div class="block">
        <div class="block-hdr">Number of Cases</div>
        <div class="row4">
          <div class="cell">
            <div class="label">Total number of deaths</div>
            <div class="code">(G)</div>
            <div class="value">{_num(s.get('total_deaths'))}</div>
          </div>
          <div class="cell">
            <div class="label">Total number of cases with days away from work</div>
            <div class="code">(H)</div>
            <div class="value">{_num(s.get('total_days_away_cases'))}</div>
          </div>
          <div class="cell">
            <div class="label">Total number of cases with job transfer or restriction</div>
            <div class="code">(I)</div>
            <div class="value">{_num(s.get('total_restricted_cases'))}</div>
          </div>
          <div class="cell">
            <div class="label">Total number of other recordable cases</div>
            <div class="code">(J)</div>
            <div class="value">{_num(s.get('total_other_recordable'))}</div>
          </div>
        </div>
      </div>

      <div class="block">
        <div class="block-hdr">Number of Days</div>
        <div class="row2">
          <div class="cell">
            <div class="label">Total number of days away from work</div>
            <div class="code">(K)</div>
            <div class="value">{_num(s.get('total_days_away'))}</div>
          </div>
          <div class="cell">
            <div class="label">Total number of days of job transfer or restriction</div>
            <div class="code">(L)</div>
            <div class="value">{_num(s.get('total_days_restricted'))}</div>
          </div>
        </div>
      </div>

      <div class="block">
        <div class="block-hdr">Injury and Illness Types — Total number of …</div>
        <div class="row6">
          <div class="cell">
            <div class="label">Injuries</div>
            <div class="code">(M1)</div>
            <div class="value">{_num(s.get('total_injuries'))}</div>
          </div>
          <div class="cell">
            <div class="label">Skin disorders</div>
            <div class="code">(M2)</div>
            <div class="value">{_num(s.get('total_skin_disorders'))}</div>
          </div>
          <div class="cell">
            <div class="label">Respiratory conditions</div>
            <div class="code">(M3)</div>
            <div class="value">{_num(s.get('total_respiratory'))}</div>
          </div>
          <div class="cell">
            <div class="label">Poisonings</div>
            <div class="code">(M4)</div>
            <div class="value">{_num(s.get('total_poisonings'))}</div>
          </div>
          <div class="cell">
            <div class="label">Hearing loss</div>
            <div class="code">(M5)</div>
            <div class="value">{_num(s.get('total_hearing_loss'))}</div>
          </div>
          <div class="cell">
            <div class="label">All other illnesses</div>
            <div class="code">(M6)</div>
            <div class="value">{_num(s.get('total_other_illnesses'))}</div>
          </div>
        </div>
      </div>
    </div>

    <div class="col-right">
      <div class="block info-block">
        <div class="block-hdr">Establishment Information</div>
        <div class="field"><span class="lbl">Your establishment name</span><span class="val">{_esc(s.get('establishment_name'))}</span></div>
        <div class="field"><span class="lbl">Street</span><span class="val">{_esc(s.get('address'))}</span></div>
        <div class="field"><span class="lbl">City</span><span class="val">{_esc(s.get('city'))}</span></div>
        <div class="field"><span class="lbl">State</span><span class="val">{_esc(s.get('state'))}</span></div>
        <div class="field"><span class="lbl">ZIP</span><span class="val">{_esc(s.get('zipcode'))}</span></div>
        <div class="field"><span class="lbl">Industry description (e.g. Manufacture of motor trailers)</span><span class="val">{_esc(s.get('industry_description')) or '&nbsp;'}</span></div>
        <div class="field"><span class="lbl">NAICS code (e.g. 336212), if known</span><span class="val">{_esc(s.get('naics'))}</span></div>
      </div>

      <div class="block info-block">
        <div class="block-hdr">Employment Information</div>
        <div class="field"><span class="lbl">Annual average number of employees</span><span class="val">{_esc(s.get('average_employees'))}</span></div>
        <div class="field"><span class="lbl">Total hours worked by all employees last year</span><span class="val">{_hours(s.get('total_hours_worked'))}</span></div>
      </div>
    </div>
  </div>

  <div class="cert">
    <strong>Sign here.</strong> Knowingly falsifying this document may result in a fine.
    <div class="signline">I certify that I have examined this document and that to the best of my knowledge the entries are true, accurate, and complete.</div>
    <div class="sigrow">
      <div>
        <div class="siglbl">Company executive</div>
        <div class="sigval">{_esc(s.get('executive_name'))}</div>
      </div>
      <div>
        <div class="siglbl">Title</div>
        <div class="sigval">{_esc(s.get('executive_title'))}</div>
      </div>
      <div>
        <div class="siglbl">Phone</div>
        <div class="sigval">{_esc(s.get('executive_phone'))}</div>
      </div>
      <div>
        <div class="siglbl">Date</div>
        <div class="sigval">{_esc(s.get('certified_date'))}</div>
      </div>
    </div>
  </div>

  <div class="postnote">
    Post this Summary page from February 1 to April 30 of the year following the year covered by the form.
  </div>
  <div class="burden">
    Public reporting burden for this collection of information is estimated to average 50 minutes per response,
    including time to review the instructions, search existing data sources, gather and maintain the data needed,
    and complete and review the collection of information.
  </div>
  <div class="footer">Generated by Matcha — replica of OSHA Form 300A for posting/recordkeeping.</div>
</body></html>"""


async def render_300a_pdf(summary: dict) -> bytes:
    """Render a 300A summary dict to PDF bytes (WeasyPrint, 60s timeout)."""
    full_html = _build_300a_html(summary)

    try:
        from ....core.services.pdf import render_pdf
    except ImportError as ie:
        logger.error("weasyprint import failed: %s", ie)
        raise HTTPException(
            status_code=501,
            detail="PDF generation not available — install weasyprint on the server (`pip install weasyprint`).",
        )

    try:
        return await asyncio.wait_for(
            asyncio.to_thread(lambda: render_pdf(full_html)),
            timeout=60.0,
        )
    except asyncio.TimeoutError:
        raise HTTPException(status_code=504, detail="PDF generation timed out.")
    except HTTPException:
        raise
    except Exception as e:
        logger.exception("OSHA 300A PDF render failed")
        raise HTTPException(status_code=500, detail=f"PDF generation failed: {type(e).__name__}")
