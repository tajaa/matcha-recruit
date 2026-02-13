"""
Leave Notices Service — generates compliance-required leave notice PDFs.

Produces FMLA eligibility (WH-381), FMLA designation (WH-382),
state leave notices, and return-to-work notices as PDFs stored in
employee_documents for employee viewing/signing via the portal.
"""
import html
import logging
from datetime import datetime, date
from uuid import UUID

from ...database import get_connection
from ...core.services.storage import get_storage

logger = logging.getLogger(__name__)


def _safe(value, default: str = "") -> str:
    """HTML-escape a value for safe embedding in templates."""
    return html.escape(str(value)) if value else default


# Mapping of notice_type to human-readable titles
NOTICE_TITLES = {
    "fmla_eligibility_notice": "FMLA Eligibility Notice (WH-381)",
    "fmla_designation_notice": "FMLA Designation Notice (WH-382)",
    "state_leave_notice": "State Leave Program Notice",
    "return_to_work_notice": "Return-to-Work Notice",
}

VALID_NOTICE_TYPES = set(NOTICE_TITLES.keys())

# Shared CSS for all notice PDFs
_NOTICE_CSS = """
    @page {
        size: letter;
        margin: 0.75in 1in;
    }
    body {
        font-family: 'Helvetica Neue', Helvetica, Arial, sans-serif;
        font-size: 10.5pt;
        line-height: 1.5;
        color: #1a1a1a;
    }
    .header {
        border-bottom: 2px solid #222;
        padding-bottom: 12px;
        margin-bottom: 24px;
    }
    .header .company-name {
        font-size: 16pt;
        font-weight: bold;
    }
    .header .doc-title {
        font-size: 12pt;
        text-transform: uppercase;
        letter-spacing: 1.5px;
        color: #444;
        margin-top: 4px;
    }
    .header .date-block {
        font-size: 9pt;
        color: #666;
        margin-top: 6px;
    }
    .section-title {
        font-size: 9pt;
        text-transform: uppercase;
        letter-spacing: 2px;
        color: #666;
        border-bottom: 1px solid #ddd;
        padding-bottom: 6px;
        margin-top: 24px;
        margin-bottom: 12px;
    }
    .info-grid {
        background: #f8f8f8;
        border: 1px solid #e0e0e0;
        padding: 16px;
        margin: 12px 0;
    }
    .info-row {
        display: flex;
        margin-bottom: 10px;
    }
    .info-item {
        flex: 1;
    }
    .info-label {
        font-size: 8.5pt;
        text-transform: uppercase;
        color: #666;
        margin-bottom: 2px;
    }
    .info-value {
        font-weight: bold;
    }
    .check-item {
        margin-bottom: 6px;
        padding-left: 20px;
        position: relative;
    }
    .check-item::before {
        content: "\\2610";
        position: absolute;
        left: 0;
    }
    .check-item.checked::before {
        content: "\\2611";
    }
    .eligible { color: #1a7f37; font-weight: bold; }
    .not-eligible { color: #cf222e; font-weight: bold; }
    .notice-box {
        border: 1px solid #bbb;
        background: #fffde7;
        padding: 14px;
        margin: 16px 0;
        font-size: 10pt;
    }
    .signature-section {
        margin-top: 50px;
        padding-top: 20px;
        border-top: 1px solid #ddd;
        display: flex;
        justify-content: space-between;
    }
    .signature-block {
        width: 44%;
    }
    .signature-line {
        border-bottom: 1px solid #333;
        height: 36px;
        margin-bottom: 6px;
    }
    .signature-label {
        font-size: 8.5pt;
        text-transform: uppercase;
        color: #666;
    }
    ul { padding-left: 20px; }
    li { margin-bottom: 4px; }
    p { margin: 8px 0; }
"""


class LeaveNoticeService:
    """Generates leave-related compliance notices as PDFs."""

    # ------------------------------------------------------------------
    # HTML generators (private)
    # ------------------------------------------------------------------

    def _generate_fmla_eligibility_notice_html(
        self, employee: dict, eligibility: dict, company: dict
    ) -> str:
        """WH-381 — FMLA Eligibility Notice."""
        company_name = _safe(company.get("name"))
        emp_name = _safe(f"{employee['first_name']} {employee['last_name']}")
        today_str = date.today().strftime("%B %d, %Y")

        fmla = eligibility.get("fmla", {})
        is_eligible = fmla.get("eligible", False)
        months = fmla.get("months_employed")
        hours = fmla.get("hours_worked_12mo")
        emp_count = fmla.get("company_employee_count")
        reasons = fmla.get("reasons", [])

        eligibility_class = "eligible" if is_eligible else "not-eligible"
        eligibility_text = "ELIGIBLE" if is_eligible else "NOT ELIGIBLE"

        reasons_html = "".join(f"<li>{_safe(r)}</li>" for r in reasons)

        return f"""<!DOCTYPE html>
<html><head><meta charset="UTF-8"><style>{_NOTICE_CSS}</style></head>
<body>
    <div class="header">
        <div class="company-name">{company_name}</div>
        <div class="doc-title">FMLA Eligibility Notice (WH-381)</div>
        <div class="date-block">Date: {today_str}</div>
    </div>

    <p>To: <strong>{emp_name}</strong></p>

    <p>
        On the date shown above, you informed us of your need for leave due to
        a reason covered by the Family and Medical Leave Act (FMLA).
        This notice is to inform you of your eligibility status.
    </p>

    <div class="section-title">Eligibility Determination</div>

    <p>You are currently <span class="{eligibility_class}">{eligibility_text}</span>
       for FMLA leave.</p>

    <div class="info-grid">
        <div class="info-row">
            <div class="info-item">
                <div class="info-label">Months Employed</div>
                <div class="info-value">{_safe(str(months) if months else 'N/A')}</div>
            </div>
            <div class="info-item">
                <div class="info-label">Hours Worked (Past 12 Months)</div>
                <div class="info-value">{_safe(str(hours) if hours else 'N/A')}</div>
            </div>
            <div class="info-item">
                <div class="info-label">Company Active Employees</div>
                <div class="info-value">{_safe(str(emp_count) if emp_count else 'N/A')}</div>
            </div>
        </div>
    </div>

    <div class="section-title">Basis for Determination</div>
    <ul>{reasons_html}</ul>

    <div class="section-title">Your Rights Under FMLA</div>
    <ul>
        <li>If eligible, you are entitled to up to 12 weeks of unpaid, job-protected leave
            in a 12-month period for qualifying reasons.</li>
        <li>Your group health benefits will be maintained during leave on the same terms
            as if you had continued to work.</li>
        <li>You have the right to be restored to the same or an equivalent position
            upon return from leave.</li>
        <li>The use of FMLA leave cannot be counted against you under a no-fault
            attendance policy.</li>
    </ul>

    <div class="section-title">Your Responsibilities</div>
    <ul>
        <li>Provide 30 days advance notice when the need for leave is foreseeable.</li>
        <li>Provide sufficient information for the employer to determine if the leave
            qualifies for FMLA protection.</li>
        <li>Provide medical certification within 15 calendar days of the employer's
            request, if applicable.</li>
        <li>Periodically report on your status and intent to return to work.</li>
    </ul>

    <div class="notice-box">
        If you have questions about your eligibility or FMLA rights, please contact
        your HR representative.
    </div>

    <div class="signature-section">
        <div class="signature-block">
            <div class="signature-line"></div>
            <div class="signature-label">Employer Representative</div>
        </div>
        <div class="signature-block">
            <div class="signature-line"></div>
            <div class="signature-label">Employee Acknowledgement</div>
        </div>
    </div>
</body></html>"""

    def _generate_fmla_designation_notice_html(
        self, employee: dict, leave_request: dict, company: dict
    ) -> str:
        """WH-382 — FMLA Designation Notice."""
        company_name = _safe(company.get("name"))
        emp_name = _safe(f"{employee['first_name']} {employee['last_name']}")
        today_str = date.today().strftime("%B %d, %Y")

        leave_type = _safe(leave_request.get("leave_type", ""))
        start_date = leave_request.get("start_date")
        end_date = leave_request.get("end_date")
        start_str = start_date.strftime("%B %d, %Y") if start_date else "TBD"
        end_str = end_date.strftime("%B %d, %Y") if end_date else "TBD"
        intermittent = leave_request.get("intermittent", False)
        schedule = _safe(leave_request.get("intermittent_schedule", ""))
        hours_approved = leave_request.get("hours_approved")
        reason = _safe(leave_request.get("reason", ""))
        status = _safe(leave_request.get("status", ""))

        intermittent_text = "Yes" if intermittent else "No"

        return f"""<!DOCTYPE html>
<html><head><meta charset="UTF-8"><style>{_NOTICE_CSS}</style></head>
<body>
    <div class="header">
        <div class="company-name">{company_name}</div>
        <div class="doc-title">FMLA Designation Notice (WH-382)</div>
        <div class="date-block">Date: {today_str}</div>
    </div>

    <p>To: <strong>{emp_name}</strong></p>

    <p>
        We have reviewed your request for leave under the Family and Medical
        Leave Act. This notice provides the designation of your leave and
        the conditions that apply.
    </p>

    <div class="section-title">Leave Details</div>

    <div class="info-grid">
        <div class="info-row">
            <div class="info-item">
                <div class="info-label">Leave Type</div>
                <div class="info-value">{leave_type}</div>
            </div>
            <div class="info-item">
                <div class="info-label">Status</div>
                <div class="info-value">{status}</div>
            </div>
        </div>
        <div class="info-row">
            <div class="info-item">
                <div class="info-label">Start Date</div>
                <div class="info-value">{start_str}</div>
            </div>
            <div class="info-item">
                <div class="info-label">End Date</div>
                <div class="info-value">{end_str}</div>
            </div>
        </div>
        <div class="info-row">
            <div class="info-item">
                <div class="info-label">Intermittent Leave</div>
                <div class="info-value">{intermittent_text}</div>
            </div>
            <div class="info-item">
                <div class="info-label">Hours Approved</div>
                <div class="info-value">{_safe(str(hours_approved) if hours_approved else 'N/A')}</div>
            </div>
        </div>
    </div>

    {"<p><strong>Intermittent Schedule:</strong> " + schedule + "</p>" if intermittent and schedule else ""}
    {"<p><strong>Reason:</strong> " + reason + "</p>" if reason else ""}

    <div class="section-title">Designation</div>

    <p>Your leave request <strong>has been designated</strong> as FMLA-qualifying leave.
       The leave will be counted against your FMLA entitlement.</p>

    <div class="section-title">Conditions</div>
    <ul>
        <li>You are required to substitute accrued paid leave (vacation, sick, or PTO)
            for unpaid FMLA leave, in accordance with company policy.</li>
        <li>If your leave is for a serious health condition, you may be required to
            provide a fitness-for-duty certification before returning to work.</li>
        <li>If circumstances change, contact HR immediately to discuss your leave status.</li>
        <li>Failure to return to work at the end of the leave period may result in
            termination of employment, unless an extension is approved.</li>
    </ul>

    <div class="section-title">Paid Leave Substitution</div>
    <p>
        Accrued paid leave (vacation, sick leave, PTO) will run concurrently with
        FMLA leave as permitted by company policy and applicable law. You will be
        notified of the specific amounts applied.
    </p>

    <div class="notice-box">
        If you have questions about this designation, please contact your HR
        representative within 7 calendar days.
    </div>

    <div class="signature-section">
        <div class="signature-block">
            <div class="signature-line"></div>
            <div class="signature-label">Employer Representative</div>
        </div>
        <div class="signature-block">
            <div class="signature-line"></div>
            <div class="signature-label">Employee Acknowledgement</div>
        </div>
    </div>
</body></html>"""

    def _generate_state_leave_notice_html(
        self, employee: dict, state_programs: dict, company: dict
    ) -> str:
        """State leave program notice with applicable programs and benefits."""
        company_name = _safe(company.get("name"))
        emp_name = _safe(f"{employee['first_name']} {employee['last_name']}")
        today_str = date.today().strftime("%B %d, %Y")
        work_state = _safe(state_programs.get("state", ""))

        programs = state_programs.get("programs", [])

        programs_html = ""
        for prog in programs:
            eligible_class = "eligible" if prog.get("eligible") else "not-eligible"
            eligible_text = "Eligible" if prog.get("eligible") else "Not Eligible"
            wage_pct = prog.get("wage_replacement_pct")
            wage_str = f"{wage_pct:.0f}%" if wage_pct else "N/A"
            max_weeks = prog.get("max_weeks")
            max_weeks_str = f"{max_weeks} weeks" if max_weeks else "N/A"
            paid = "Yes" if prog.get("paid") else "No"
            job_protection = "Yes" if prog.get("job_protection") else "No"
            notes = _safe(prog.get("notes", ""))

            reasons_list = "".join(
                f"<li>{_safe(r)}</li>" for r in prog.get("reasons", [])
            )

            programs_html += f"""
            <div style="margin-bottom: 20px; padding: 14px; border: 1px solid #e0e0e0; background: #fafafa;">
                <div style="font-weight: bold; font-size: 11pt; margin-bottom: 6px;">
                    {_safe(prog.get('label', prog.get('program', '')))}
                </div>
                <div class="info-row">
                    <div class="info-item">
                        <div class="info-label">Status</div>
                        <div class="{eligible_class}">{eligible_text}</div>
                    </div>
                    <div class="info-item">
                        <div class="info-label">Paid Leave</div>
                        <div class="info-value">{paid}</div>
                    </div>
                    <div class="info-item">
                        <div class="info-label">Wage Replacement</div>
                        <div class="info-value">{wage_str}</div>
                    </div>
                </div>
                <div class="info-row" style="margin-top: 8px;">
                    <div class="info-item">
                        <div class="info-label">Maximum Duration</div>
                        <div class="info-value">{max_weeks_str}</div>
                    </div>
                    <div class="info-item">
                        <div class="info-label">Job Protection</div>
                        <div class="info-value">{job_protection}</div>
                    </div>
                </div>
                <div style="margin-top: 8px;">
                    <div class="info-label">Details</div>
                    <ul style="margin-top: 4px;">{reasons_list}</ul>
                </div>
                {"<p style='font-size: 9pt; color: #555;'>" + notes + "</p>" if notes else ""}
            </div>"""

        no_programs_html = ""
        if not programs:
            no_programs_html = """
            <p>No state-specific leave programs were found for your work location.
               Federal FMLA protections may still apply.</p>"""

        return f"""<!DOCTYPE html>
<html><head><meta charset="UTF-8"><style>{_NOTICE_CSS}</style></head>
<body>
    <div class="header">
        <div class="company-name">{company_name}</div>
        <div class="doc-title">State Leave Program Notice</div>
        <div class="date-block">Date: {today_str}</div>
    </div>

    <p>To: <strong>{emp_name}</strong></p>
    <p>Work State: <strong>{work_state}</strong></p>

    <p>
        This notice provides information about state leave programs that may
        apply to you based on your work location. Eligibility for each program
        is evaluated based on your employment history and applicable requirements.
    </p>

    <div class="section-title">Applicable State Programs</div>

    {programs_html}
    {no_programs_html}

    <div class="section-title">Important Information</div>
    <ul>
        <li>State leave benefits may run concurrently with federal FMLA leave
            where both apply.</li>
        <li>You may be required to provide documentation or certification to
            establish eligibility for specific state programs.</li>
        <li>Benefit amounts and duration limits are subject to change based on
            current state regulations.</li>
        <li>Contact your HR representative for assistance with filing claims
            or understanding your benefits.</li>
    </ul>

    <div class="notice-box">
        This notice is provided for informational purposes. For the most current
        information about your state's leave programs, consult the applicable
        state agency website or contact HR.
    </div>

    <div class="signature-section">
        <div class="signature-block">
            <div class="signature-line"></div>
            <div class="signature-label">Employer Representative</div>
        </div>
        <div class="signature-block">
            <div class="signature-line"></div>
            <div class="signature-label">Employee Acknowledgement</div>
        </div>
    </div>
</body></html>"""

    def _generate_return_to_work_notice_html(
        self, employee: dict, leave_request: dict, company: dict
    ) -> str:
        """Return-to-work notice with fitness-for-duty and return requirements."""
        company_name = _safe(company.get("name"))
        emp_name = _safe(f"{employee['first_name']} {employee['last_name']}")
        today_str = date.today().strftime("%B %d, %Y")

        leave_type = _safe(leave_request.get("leave_type", ""))
        start_date = leave_request.get("start_date")
        end_date = leave_request.get("end_date")
        expected_return = leave_request.get("expected_return_date")
        actual_return = leave_request.get("actual_return_date")

        start_str = start_date.strftime("%B %d, %Y") if start_date else "N/A"
        end_str = end_date.strftime("%B %d, %Y") if end_date else "N/A"
        expected_str = expected_return.strftime("%B %d, %Y") if expected_return else "TBD"
        actual_str = actual_return.strftime("%B %d, %Y") if actual_return else "TBD"

        is_medical = leave_request.get("leave_type") in ("fmla", "medical")

        fitness_section = ""
        if is_medical:
            fitness_section = """
    <div class="section-title">Fitness-for-Duty Certification</div>
    <div class="notice-box">
        <strong>A fitness-for-duty certification is required before you may return
        to work.</strong> Please provide a certification from your health care
        provider confirming that you are able to resume your job duties. This
        certification must be received by HR before your scheduled return date.
    </div>
    <p>The certification should address your ability to perform the essential
       functions of your position. If you were on leave for a serious health
       condition, the certification must relate to the condition for which
       leave was taken.</p>"""

        return f"""<!DOCTYPE html>
<html><head><meta charset="UTF-8"><style>{_NOTICE_CSS}</style></head>
<body>
    <div class="header">
        <div class="company-name">{company_name}</div>
        <div class="doc-title">Return-to-Work Notice</div>
        <div class="date-block">Date: {today_str}</div>
    </div>

    <p>To: <strong>{emp_name}</strong></p>

    <p>
        This notice outlines the requirements and expectations for your return
        to work following your leave of absence.
    </p>

    <div class="section-title">Leave Summary</div>

    <div class="info-grid">
        <div class="info-row">
            <div class="info-item">
                <div class="info-label">Leave Type</div>
                <div class="info-value">{leave_type}</div>
            </div>
            <div class="info-item">
                <div class="info-label">Leave Period</div>
                <div class="info-value">{start_str} &mdash; {end_str}</div>
            </div>
        </div>
        <div class="info-row">
            <div class="info-item">
                <div class="info-label">Expected Return Date</div>
                <div class="info-value">{expected_str}</div>
            </div>
            <div class="info-item">
                <div class="info-label">Actual Return Date</div>
                <div class="info-value">{actual_str}</div>
            </div>
        </div>
    </div>

    {fitness_section}

    <div class="section-title">Return-to-Work Requirements</div>
    <ul>
        <li>Report to your supervisor or HR on your first day back at the
            scheduled start time.</li>
        <li>Review and acknowledge any policy updates or changes that occurred
            during your absence.</li>
        <li>Complete any required return-to-work paperwork before resuming duties.</li>
        <li>If you require any workplace accommodations upon return, notify HR
            as soon as possible so arrangements can be made.</li>
    </ul>

    <div class="section-title">Job Restoration</div>
    <p>
        In accordance with applicable law, you will be restored to your original
        position or an equivalent position with equivalent pay, benefits, and
        other terms and conditions of employment. If any changes to your role
        are necessary, your supervisor and HR will discuss them with you.
    </p>

    <div class="section-title">Modified Duty</div>
    <p>
        If your health care provider has recommended work restrictions or modified
        duty, please provide documentation to HR. We will evaluate the feasibility
        of accommodating any restrictions and discuss options with you.
    </p>

    <div class="notice-box">
        If you are unable to return on the expected date, contact HR
        immediately to discuss your options, including a possible leave extension.
    </div>

    <div class="signature-section">
        <div class="signature-block">
            <div class="signature-line"></div>
            <div class="signature-label">Employer Representative</div>
        </div>
        <div class="signature-block">
            <div class="signature-line"></div>
            <div class="signature-label">Employee Acknowledgement</div>
        </div>
    </div>
</body></html>"""

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    async def create_notice(
        self,
        conn,
        notice_type: str,
        employee_id: UUID,
        org_id: UUID,
        leave_request_id: UUID | None = None,
    ) -> dict:
        """Generate a leave notice PDF, upload it, and store in employee_documents.

        Returns the created document record as a dict.
        """
        if notice_type not in VALID_NOTICE_TYPES:
            raise ValueError(f"Invalid notice_type: {notice_type}")

        # Fetch employee
        employee = await conn.fetchrow(
            "SELECT * FROM employees WHERE id = $1 AND org_id = $2",
            employee_id, org_id,
        )
        if not employee:
            raise ValueError("Employee not found")
        employee = dict(employee)

        # Fetch company
        company = await conn.fetchrow(
            "SELECT * FROM companies WHERE id = $1", org_id
        )
        company = dict(company) if company else {"name": "Company"}

        # Fetch leave request if provided
        leave_request = None
        if leave_request_id:
            row = await conn.fetchrow(
                "SELECT * FROM leave_requests WHERE id = $1 AND org_id = $2",
                leave_request_id, org_id,
            )
            if row:
                leave_request = dict(row)

        # Fetch eligibility data (needed for fmla_eligibility and state notices)
        eligibility = None
        if notice_type in ("fmla_eligibility_notice", "state_leave_notice"):
            from .leave_eligibility_service import LeaveEligibilityService
            svc = LeaveEligibilityService()
            eligibility = await svc.get_eligibility_summary(employee_id)

        # Generate HTML
        if notice_type == "fmla_eligibility_notice":
            html_content = self._generate_fmla_eligibility_notice_html(
                employee, eligibility or {}, company
            )
        elif notice_type == "fmla_designation_notice":
            if not leave_request:
                raise ValueError("Leave request is required for designation notice")
            html_content = self._generate_fmla_designation_notice_html(
                employee, leave_request, company
            )
        elif notice_type == "state_leave_notice":
            state_programs = (eligibility or {}).get("state_programs", {})
            html_content = self._generate_state_leave_notice_html(
                employee, state_programs, company
            )
        elif notice_type == "return_to_work_notice":
            if not leave_request:
                raise ValueError("Leave request is required for return-to-work notice")
            html_content = self._generate_return_to_work_notice_html(
                employee, leave_request, company
            )
        else:
            raise ValueError(f"Unhandled notice_type: {notice_type}")

        # Generate PDF via WeasyPrint
        from weasyprint import HTML
        pdf_bytes = HTML(string=html_content).write_pdf()

        # Upload to S3
        emp_name_slug = f"{employee['first_name']}-{employee['last_name']}".replace(" ", "-").lower()
        filename = f"{notice_type}-{emp_name_slug}.pdf"
        storage_path = await get_storage().upload_file(
            pdf_bytes, filename, prefix="leave-notices", content_type="application/pdf"
        )

        # Insert into employee_documents
        title = NOTICE_TITLES[notice_type]
        doc = await conn.fetchrow(
            """INSERT INTO employee_documents
                   (org_id, employee_id, doc_type, title, storage_path, status)
               VALUES ($1, $2, $3, $4, $5, 'pending_signature')
               RETURNING id, org_id, employee_id, doc_type, title, description,
                         storage_path, status, expires_at, signed_at, assigned_by,
                         created_at, updated_at""",
            org_id, employee_id, notice_type, title, storage_path,
        )

        return dict(doc)
