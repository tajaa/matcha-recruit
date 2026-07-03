"""ComplianceEmailMixin email-send methods.

Extracted from `email.py` during the 2026-05-16 package split. Mixed
into `EmailService` (see `client.py`) via multiple inheritance. Method
bodies call `self.send_email(...)` / `self.is_configured()` / etc. —
`self` is the composed `EmailService` at runtime.
"""
import html
import logging
from datetime import date, datetime
from typing import Optional

logger = logging.getLogger(__name__)


class ComplianceEmailMixin:
    async def send_policy_signature_email(
        self,
        to_email: str,
        to_name: str,
        policy_title: str,
        policy_version: str,
        token: str,
        expires_at,
        company_name: Optional[str] = None,
    ) -> bool:
        """Send a policy signature request email.

        Returns True if sent successfully, False otherwise.
        """
        if not self.is_configured():
            logger.warning("Gmail not configured, skipping policy signature email")
            return False

        app_base_url = self.settings.app_base_url
        signature_url = f"{app_base_url}/sign/{token}"

        company_section = f"<p><strong>From:</strong> {company_name}</p>" if company_name else ""
        version_section = f"<p><strong>Version:</strong> {policy_version}</p>" if policy_version else ""

        html_content = f"""
<!DOCTYPE html>
<html>
<head>
    <style>
        body {{ font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif; line-height: 1.6; color: #333; }}
        .container {{ max-width: 600px; margin: 0 auto; padding: 20px; }}
        .header {{ text-align: center; padding: 20px 0; border-bottom: 2px solid #22c55e; }}
        .logo {{ color: #22c55e; font-size: 24px; font-weight: bold; letter-spacing: 2px; }}
        .content {{ padding: 30px 0; }}
        .policy-card {{ background: #f8f9fa; border-left: 4px solid #22c55e; border-radius: 8px; padding: 20px; margin: 20px 0; }}
        .btn {{ display: inline-block; background: #22c55e; color: white; padding: 14px 28px; text-decoration: none; border-radius: 6px; font-weight: 600; margin: 20px 0; text-align: center; }}
        .btn:hover {{ background: #16a34a; }}
        .footer {{ text-align: center; padding-top: 20px; border-top: 1px solid #e5e7eb; color: #6b7280; font-size: 12px; }}
    </style>
</head>
<body>
    <div class="container">
        <div class="header">
            <div class="logo">MATCHA</div>
        </div>
        <div class="content">
            <p>Hi {to_name},</p>

            <p>You have been asked to sign the following policy document:</p>

            <div class="policy-card">
                <h2 style="margin-top: 0; color: #111;">{policy_title}</h2>
                {company_section}
                {version_section}
            </div>

            <p>Please review the policy and click the button below to sign it electronically.</p>

            <p>
                <a href="{signature_url}" class="btn">Sign Policy</a>
            </p>

            <p style="color: #6b7280; font-size: 14px;">
                This link will expire on {expires_at.strftime('%B %d, %Y at %I:%M %p')}.
            </p>

            <p style="color: #6b7280; font-size: 14px;">
                If you have questions about this policy, please contact your administrator.
            </p>
        </div>
        <div class="footer">
            <p>Sent via Matcha Recruit</p>
        </div>
    </div>
</body>
</html>
"""

        text_content = f"""
Hi {to_name},

You have been asked to sign the following policy document:

{policy_title}
{company_name if company_name else ''}
{('Version: ' + policy_version) if policy_version else ''}

Please review the policy and sign it using the link below:

{signature_url}

This link will expire on {expires_at.strftime('%B %d, %Y at %I:%M %p')}.

If you have questions, please contact your administrator.

- Matcha Recruit
"""

        return await self.send_email(
            to_email=to_email,
            to_name=to_name,
            subject=f"Action Required: Please sign {policy_title}",
            html_content=html_content,
            text_content=text_content,
        )

    async def send_compliance_change_notification_email(
        self,
        to_email: str,
        to_name: Optional[str],
        company_name: str,
        location_name: str,
        changed_requirements_count: int,
        jurisdictions: Optional[list[str]] = None,
    ) -> bool:
        """Send a general compliance change notification to a business admin."""
        if not self.is_configured():
            logger.warning("Gmail not configured, skipping email send")
            return False

        app_base_url = self.settings.app_base_url
        compliance_url = f"{app_base_url}/app/matcha/compliance"
        recipient_name = to_name or to_email

        requirement_word = "requirement" if changed_requirements_count == 1 else "requirements"
        requirement_verb = "has" if changed_requirements_count == 1 else "have"

        jurisdiction_lines = ""
        jurisdiction_text = ""
        if jurisdictions:
            preview = jurisdictions[:5]
            jurisdiction_items = "".join(f"<li>{name}</li>" for name in preview)
            jurisdiction_lines = f"""
            <p style="margin-top: 20px; margin-bottom: 8px;"><strong>Impacted jurisdictions:</strong></p>
            <ul style="margin-top: 0; color: #374151;">
                {jurisdiction_items}
            </ul>
            """
            jurisdiction_text = "\n".join([f"- {name}" for name in preview])

        html_content = f"""
<!DOCTYPE html>
<html>
<head>
    <style>
        body {{ font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif; line-height: 1.6; color: #333; }}
        .container {{ max-width: 600px; margin: 0 auto; padding: 20px; }}
        .header {{ text-align: center; padding: 20px 0; border-bottom: 2px solid #22c55e; }}
        .logo {{ color: #22c55e; font-size: 24px; font-weight: bold; letter-spacing: 2px; }}
        .content {{ padding: 30px 0; }}
        .alert-card {{ background: #fff7ed; border-left: 4px solid #f97316; border-radius: 8px; padding: 16px; margin: 20px 0; }}
        .btn {{ display: inline-block; background: #22c55e; color: white; padding: 14px 24px; text-decoration: none; border-radius: 6px; font-weight: 600; }}
        .footer {{ text-align: center; padding-top: 20px; border-top: 1px solid #e5e7eb; color: #6b7280; font-size: 12px; }}
    </style>
</head>
<body>
    <div class="container">
        <div class="header">
            <div class="logo">MATCHA</div>
        </div>
        <div class="content">
            <p>Hi {recipient_name},</p>

            <p>We detected an update to your compliance data for <strong>{location_name}</strong>.</p>

            <div class="alert-card">
                <p style="margin: 0;">
                    <strong>{changed_requirements_count}</strong> compliance {requirement_word} {requirement_verb} new information.
                </p>
            </div>

            {jurisdiction_lines}

            <p>Please log in and review the Compliance tab to see what changed and confirm any needed follow-up.</p>

            <p style="text-align: center; margin-top: 24px;">
                <a href="{compliance_url}" class="btn">Review Compliance Updates</a>
            </p>
        </div>
        <div class="footer">
            <p>Sent via Matcha Recruit</p>
        </div>
    </div>
</body>
</html>
"""

        text_content = f"""
Hi {recipient_name},

We detected an update to your compliance data for {location_name}.

{changed_requirements_count} compliance {requirement_word} {requirement_verb} new information.
{f"{chr(10)}Impacted jurisdictions:{chr(10)}{jurisdiction_text}{chr(10)}" if jurisdiction_text else ""}
Please log in and review the Compliance tab to see what changed:
{compliance_url}

- Matcha Recruit
"""

        _subject = f"{company_name}: Compliance update available"
        return await self._send_with_fallback(to_email, to_name, _subject, html_content, text_content)

    async def send_compliance_action_reminder(
        self,
        to_email: str,
        to_name: str,
        company_name: str,
        legislation_title: str,
        location_name: str,
        action_due_date: date,
        days_until_due: int,
    ) -> bool:
        """Send a compliance action reminder to the assigned owner."""
        if not self.is_configured():
            logger.warning("MailerSend not configured, skipping compliance action reminder")
            return False

        app_base_url = self.settings.app_base_url
        compliance_url = f"{app_base_url}/app/matcha/compliance?tab=upcoming"
        due_text = action_due_date.strftime("%B %d, %Y")
        urgency = "today" if days_until_due <= 0 else f"in {days_until_due} day{'s' if days_until_due != 1 else ''}"
        urgency_color = "#ef4444" if days_until_due <= 1 else "#f59e0b"

        html_content = f"""
<!DOCTYPE html>
<html>
<head>
    <style>
        body {{ font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif; line-height: 1.6; color: #333; }}
        .container {{ max-width: 600px; margin: 0 auto; padding: 20px; }}
        .header {{ text-align: center; padding: 20px 0; border-bottom: 2px solid #22c55e; }}
        .logo {{ color: #22c55e; font-size: 24px; font-weight: bold; letter-spacing: 2px; }}
        .content {{ padding: 30px 0; }}
        .card {{ background: #f9fafb; border-radius: 10px; padding: 20px; margin: 20px 0; border-left: 4px solid {urgency_color}; }}
        .btn {{ display: inline-block; background: #22c55e; color: white; padding: 12px 22px; text-decoration: none; border-radius: 6px; font-weight: 600; }}
        .footer {{ text-align: center; padding-top: 20px; border-top: 1px solid #e5e7eb; color: #6b7280; font-size: 12px; }}
    </style>
</head>
<body>
    <div class="container">
        <div class="header">
            <div class="logo">MATCHA</div>
        </div>
        <div class="content">
            <p>Hi {to_name},</p>
            <p>You have a compliance action due <strong style="color: {urgency_color};">{urgency}</strong>.</p>

            <div class="card">
                <p style="margin: 0;"><strong>Regulation:</strong> {legislation_title}</p>
                <p style="margin: 8px 0 0 0;"><strong>Location:</strong> {location_name}</p>
                <p style="margin: 8px 0 0 0;"><strong>Your deadline:</strong> {due_text}</p>
            </div>

            <p>Log in to review the regulation details and mark this action complete once handled.</p>
            <p>
                <a href="{compliance_url}" class="btn">Open Compliance Dashboard</a>
            </p>
        </div>
        <div class="footer">
            <p>Sent by Matcha on behalf of {company_name}</p>
        </div>
    </div>
</body>
</html>"""

        text_content = f"""Hi {to_name},

You have a compliance action due {urgency}.

Regulation: {legislation_title}
Location: {location_name}
Your deadline: {due_text}

Log in to review and mark complete: {compliance_url}

Sent by Matcha on behalf of {company_name}"""

        return await self.send_email(
            to_email=to_email,
            to_name=to_name,
            subject=f"[{company_name}] Compliance action due {urgency} — {legislation_title}",
            html_content=html_content,
            text_content=text_content,
        )

    async def send_ir_incident_notification_email(
        self,
        to_email: str,
        to_name: Optional[str],
        company_name: str,
        incident_id: str,
        incident_number: str,
        incident_title: str,
        event_type: str,
        current_status: str,
        changed_by_email: Optional[str] = None,
        previous_status: Optional[str] = None,
        location_name: Optional[str] = None,
        occurred_at: Optional[datetime] = None,
    ) -> bool:
        """Send incident lifecycle notifications to a company admin/client."""
        if not self.is_configured():
            logger.warning("Gmail not configured, skipping email send")
            return False

        app_base_url = self.settings.app_base_url
        incident_url = f"{app_base_url}/app/ir/incidents/{incident_id}"
        recipient_name = to_name or to_email

        status_label = current_status.replace("_", " ").title() if current_status else "Unknown"
        previous_status_label = (
            previous_status.replace("_", " ").title()
            if previous_status else "Unknown"
        )
        actor = changed_by_email or "a team member"
        occurred_text = occurred_at.strftime("%B %d, %Y at %I:%M %p") if occurred_at else "Not provided"
        location_text = location_name or "Not provided"

        # Escape user-supplied values for HTML email
        recipient_name = html.escape(recipient_name)
        incident_title = html.escape(incident_title)
        actor = html.escape(actor)
        location_text = html.escape(location_text)

        if event_type == "created":
            subject = f"{company_name}: New incident reported ({incident_number})"
            summary_line = "A new incident report was created."
            transition_line = f"Current status: <strong>{status_label}</strong>"
            transition_text = f"Current status: {status_label}"
        else:
            subject = f"{company_name}: Incident {incident_number} moved to {status_label}"
            summary_line = "An incident report changed stages."
            transition_line = (
                f"Status moved from <strong>{previous_status_label}</strong> "
                f"to <strong>{status_label}</strong>."
            )
            transition_text = f"Status moved from {previous_status_label} to {status_label}."

        html_content = f"""
<!DOCTYPE html>
<html>
<head>
    <style>
        body {{ font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif; line-height: 1.6; color: #333; }}
        .container {{ max-width: 600px; margin: 0 auto; padding: 20px; }}
        .header {{ text-align: center; padding: 20px 0; border-bottom: 2px solid #22c55e; }}
        .logo {{ color: #22c55e; font-size: 24px; font-weight: bold; letter-spacing: 2px; }}
        .content {{ padding: 30px 0; }}
        .event-card {{ background: #f8fafc; border-left: 4px solid #2563eb; border-radius: 8px; padding: 16px; margin: 20px 0; }}
        .incident-card {{ background: #f9fafb; border-radius: 8px; padding: 20px; margin: 20px 0; }}
        .btn {{ display: inline-block; background: #22c55e; color: white; padding: 14px 24px; text-decoration: none; border-radius: 6px; font-weight: 600; }}
        .footer {{ text-align: center; padding-top: 20px; border-top: 1px solid #e5e7eb; color: #6b7280; font-size: 12px; }}
    </style>
</head>
<body>
    <div class="container">
        <div class="header">
            <div class="logo">MATCHA</div>
        </div>
        <div class="content">
            <p>Hi {recipient_name},</p>

            <div class="event-card">
                <p style="margin: 0 0 8px 0;"><strong>{summary_line}</strong></p>
                <p style="margin: 0;">{transition_line}</p>
            </div>

            <div class="incident-card">
                <p><strong>Incident:</strong> {incident_number}</p>
                <p><strong>Title:</strong> {incident_title}</p>
                <p><strong>Occurred:</strong> {occurred_text}</p>
                <p><strong>Location:</strong> {location_text}</p>
                <p><strong>Updated by:</strong> {actor}</p>
            </div>

            <p style="text-align: center; margin-top: 24px;">
                <a href="{incident_url}" class="btn">Open Incident</a>
            </p>
        </div>
        <div class="footer">
            <p>Sent via Matcha Recruit</p>
        </div>
    </div>
</body>
</html>
"""

        text_content = f"""
Hi {recipient_name},

{summary_line}
{transition_text}

Incident: {incident_number}
Title: {incident_title}
Occurred: {occurred_text}
Location: {location_text}
Updated by: {actor}

Open incident:
{incident_url}

- Matcha Recruit
"""

        return await self._send_with_fallback(to_email, to_name, subject, html_content, text_content)

    async def send_ir_info_request_response_email(
        self,
        to_email: str,
        to_name: Optional[str],
        company_name: str,
        incident_number: str,
        respondent_name: str,
        link: str,
    ) -> bool:
        """Notify a company admin that a "Request More Info" form was submitted."""
        if not self.is_configured():
            logger.warning("Gmail not configured, skipping email send")
            return False

        recipient_name = html.escape(to_name or to_email)
        respondent_name_esc = html.escape(respondent_name)

        html_content = f"""
<!DOCTYPE html>
<html>
<head>
    <style>
        body {{ font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif; line-height: 1.6; color: #333; }}
        .container {{ max-width: 600px; margin: 0 auto; padding: 20px; }}
        .header {{ text-align: center; padding: 20px 0; border-bottom: 2px solid #22c55e; }}
        .logo {{ color: #22c55e; font-size: 24px; font-weight: bold; letter-spacing: 2px; }}
        .content {{ padding: 30px 0; }}
        .btn {{ display: inline-block; background: #22c55e; color: white; padding: 14px 24px; text-decoration: none; border-radius: 6px; font-weight: 600; }}
        .footer {{ text-align: center; padding-top: 20px; border-top: 1px solid #e5e7eb; color: #6b7280; font-size: 12px; }}
    </style>
</head>
<body>
    <div class="container">
        <div class="header">
            <div class="logo">MATCHA</div>
        </div>
        <div class="content">
            <p>Hi {recipient_name},</p>
            <p><strong>{respondent_name_esc}</strong> submitted the information requested on incident <strong>{incident_number}</strong>.</p>
            <p style="text-align: center; margin-top: 24px;">
                <a href="{link}" class="btn">Review the answers</a>
            </p>
        </div>
        <div class="footer">
            <p>Sent via Matcha Recruit</p>
        </div>
    </div>
</body>
</html>
"""

        text_content = f"""
Hi {to_name or to_email},

{respondent_name} submitted the information requested on incident {incident_number}.

Review the answers: {link}
"""

        subject = f"{company_name}: New info received for incident {incident_number}"
        return await self._send_with_fallback(to_email, to_name, subject, html_content, text_content)

    async def send_leave_request_notification_email(
        self,
        to_email: str,
        to_name: Optional[str],
        company_name: str,
        employee_name: str,
        leave_type: str,
        event_type: str,
        leave_id: str,
        start_date: str,
        end_date: Optional[str] = None,
        deadline_date: Optional[str] = None,
        deadline_type: Optional[str] = None,
    ) -> bool:
        """Send lifecycle notifications for leave requests and deadlines."""
        if not self.is_configured():
            logger.warning("Gmail not configured, skipping email send")
            return False

        app_base_url = self.settings.app_base_url
        leave_url = f"{app_base_url}/app/matcha/employees/leave/requests/{leave_id}"
        recipient_name = to_name or to_email
        leave_type_label = leave_type.replace("_", " ").upper()
        date_range = f"{start_date} to {end_date}" if end_date else start_date

        subject_map = {
            "submitted": f"{company_name}: Leave request from {employee_name}",
            "approved": f"{company_name}: Your leave request has been approved",
            "denied": f"{company_name}: Leave request update",
            "deadline_approaching": (
                f"{company_name}: Action needed — "
                f"{(deadline_type or 'deadline').replace('_', ' ').title()} due {deadline_date or 'soon'}"
            ),
            "notice_ready": f"{company_name}: Document ready for signature",
            "return_pending": f"{company_name}: Return-to-work tasks assigned",
        }
        subject = subject_map.get(event_type, f"{company_name}: Leave request update")

        if event_type == "submitted":
            summary = "A leave request was submitted and requires review."
        elif event_type == "approved":
            summary = "A leave request was approved."
        elif event_type == "denied":
            summary = "A leave request decision was recorded."
        elif event_type == "deadline_approaching":
            summary = "A leave compliance deadline is approaching."
        elif event_type == "notice_ready":
            summary = "A leave notice document is ready for review/signature."
        elif event_type == "return_pending":
            summary = "Return-to-work tasks were assigned."
        else:
            summary = "A leave request update is available."

        deadline_line = ""
        deadline_text = ""
        if deadline_type or deadline_date:
            dt_label = (deadline_type or "deadline").replace("_", " ").title()
            deadline_line = f"<p><strong>Deadline:</strong> {dt_label} ({deadline_date or 'soon'})</p>"
            deadline_text = f"Deadline: {dt_label} ({deadline_date or 'soon'})\n"

        html_content = f"""
<!DOCTYPE html>
<html>
<head>
    <style>
        body {{ font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif; line-height: 1.6; color: #333; }}
        .container {{ max-width: 600px; margin: 0 auto; padding: 20px; }}
        .header {{ text-align: center; padding: 20px 0; border-bottom: 2px solid #22c55e; }}
        .logo {{ color: #22c55e; font-size: 24px; font-weight: bold; letter-spacing: 2px; }}
        .content {{ padding: 30px 0; }}
        .event-card {{ background: #f9fafb; border-left: 4px solid #2563eb; border-radius: 8px; padding: 16px; margin: 20px 0; }}
        .leave-card {{ background: #f8fafc; border-radius: 8px; padding: 20px; margin: 20px 0; }}
        .btn {{ display: inline-block; background: #22c55e; color: white; padding: 14px 24px; text-decoration: none; border-radius: 6px; font-weight: 600; }}
        .footer {{ text-align: center; padding-top: 20px; border-top: 1px solid #e5e7eb; color: #6b7280; font-size: 12px; }}
    </style>
</head>
<body>
    <div class="container">
        <div class="header">
            <div class="logo">MATCHA</div>
        </div>
        <div class="content">
            <p>Hi {recipient_name},</p>

            <div class="event-card">
                <p style="margin: 0;"><strong>{summary}</strong></p>
            </div>

            <div class="leave-card">
                <p><strong>Employee:</strong> {employee_name}</p>
                <p><strong>Leave Type:</strong> {leave_type_label}</p>
                <p><strong>Date Range:</strong> {date_range}</p>
                {deadline_line}
            </div>

            <p style="text-align: center; margin-top: 24px;">
                <a href="{leave_url}" class="btn">Open Leave Request</a>
            </p>
        </div>
        <div class="footer">
            <p>Sent via Matcha Recruit</p>
        </div>
    </div>
</body>
</html>
"""

        text_content = f"""
Hi {recipient_name},

{summary}

Employee: {employee_name}
Leave Type: {leave_type_label}
Date Range: {date_range}
{deadline_text}Open leave request:
{leave_url}

- Matcha Recruit
"""

        return await self._send_with_fallback(to_email, to_name, subject, html_content, text_content)

    async def send_accommodation_notification_email(
        self,
        to_email: str,
        to_name: Optional[str],
        company_name: str,
        case_number: str,
        event_type: str,
        employee_name: Optional[str] = None,
        details: Optional[str] = None,
    ) -> bool:
        """Send lifecycle notifications for accommodation cases."""
        if not self.is_configured():
            logger.warning("Gmail not configured, skipping email send")
            return False

        app_base_url = self.settings.app_base_url
        accommodations_url = f"{app_base_url}/app/matcha/accommodations"
        recipient_name = to_name or to_email
        employee_line = employee_name or "Employee"

        subject_map = {
            "case_opened": f"{company_name}: Accommodation request received ({case_number})",
            "action_needed": f"{company_name}: Action needed on accommodation {case_number}",
            "determination_made": f"{company_name}: Accommodation determination for {case_number}",
            "interactive_meeting_scheduled": f"{company_name}: Interactive process update for {case_number}",
        }
        subject = subject_map.get(event_type, f"{company_name}: Accommodation case update ({case_number})")

        if event_type == "case_opened":
            summary = "A new accommodation case was opened."
        elif event_type == "action_needed":
            summary = "This accommodation case needs follow-up."
        elif event_type == "determination_made":
            summary = "A determination has been recorded for this accommodation case."
        elif event_type == "interactive_meeting_scheduled":
            summary = "An interactive process meeting update is available."
        else:
            summary = "An accommodation case update is available."

        details_line = f"<p><strong>Details:</strong> {details}</p>" if details else ""
        details_text = f"Details: {details}\n" if details else ""

        html_content = f"""
<!DOCTYPE html>
<html>
<head>
    <style>
        body {{ font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif; line-height: 1.6; color: #333; }}
        .container {{ max-width: 600px; margin: 0 auto; padding: 20px; }}
        .header {{ text-align: center; padding: 20px 0; border-bottom: 2px solid #22c55e; }}
        .logo {{ color: #22c55e; font-size: 24px; font-weight: bold; letter-spacing: 2px; }}
        .content {{ padding: 30px 0; }}
        .event-card {{ background: #f9fafb; border-left: 4px solid #7c3aed; border-radius: 8px; padding: 16px; margin: 20px 0; }}
        .case-card {{ background: #f8fafc; border-radius: 8px; padding: 20px; margin: 20px 0; }}
        .btn {{ display: inline-block; background: #22c55e; color: white; padding: 14px 24px; text-decoration: none; border-radius: 6px; font-weight: 600; }}
        .footer {{ text-align: center; padding-top: 20px; border-top: 1px solid #e5e7eb; color: #6b7280; font-size: 12px; }}
    </style>
</head>
<body>
    <div class="container">
        <div class="header">
            <div class="logo">MATCHA</div>
        </div>
        <div class="content">
            <p>Hi {recipient_name},</p>

            <div class="event-card">
                <p style="margin: 0;"><strong>{summary}</strong></p>
            </div>

            <div class="case-card">
                <p><strong>Case Number:</strong> {case_number}</p>
                <p><strong>Employee:</strong> {employee_line}</p>
                {details_line}
            </div>

            <p style="text-align: center; margin-top: 24px;">
                <a href="{accommodations_url}" class="btn">Open Accommodation Cases</a>
            </p>
        </div>
        <div class="footer">
            <p>Sent via Matcha Recruit</p>
        </div>
    </div>
</body>
</html>
"""

        text_content = f"""
Hi {recipient_name},

{summary}

Case Number: {case_number}
Employee: {employee_line}
{details_text}Open accommodation cases:
{accommodations_url}

- Matcha Recruit
"""

        return await self._send_with_fallback(to_email, to_name, subject, html_content, text_content)


    async def send_handbook_freshness_alert(
        self,
        to_email: str,
        to_name: Optional[str],
        company_name: str,
        handbook_id: str,
        impacted_sections: int,
    ) -> bool:
        """Send a handbook freshness alert to a business admin."""
        if not self.is_configured():
            logger.warning("Gmail not configured, skipping email send")
            return False

        app_base_url = self.settings.app_base_url
        handbook_url = f"{app_base_url}/app/matcha/handbooks/{handbook_id}"
        recipient_name = to_name or to_email

        section_word = "section" if impacted_sections == 1 else "sections"

        html_content = f"""
<!DOCTYPE html>
<html>
<head>
    <style>
        body {{ font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif; line-height: 1.6; color: #333; }}
        .container {{ max-width: 600px; margin: 0 auto; padding: 20px; }}
        .header {{ text-align: center; padding: 20px 0; border-bottom: 2px solid #22c55e; }}
        .logo {{ color: #22c55e; font-size: 24px; font-weight: bold; letter-spacing: 2px; }}
        .content {{ padding: 30px 0; }}
        .alert-card {{ background: #fff7ed; border-left: 4px solid #f97316; border-radius: 8px; padding: 16px; margin: 20px 0; }}
        .btn {{ display: inline-block; background: #22c55e; color: white; padding: 14px 24px; text-decoration: none; border-radius: 6px; font-weight: 600; }}
        .footer {{ text-align: center; padding-top: 20px; border-top: 1px solid #e5e7eb; color: #6b7280; font-size: 12px; }}
    </style>
</head>
<body>
    <div class="container">
        <div class="header">
            <div class="logo">MATCHA</div>
        </div>
        <div class="content">
            <p>Hi {html.escape(recipient_name)},</p>

            <p>A scheduled freshness check found that your employee handbook may need updates.</p>

            <div class="alert-card">
                <p style="margin: 0;">
                    <strong>{impacted_sections}</strong> {section_word} may be outdated based on current requirements or company profile changes.
                </p>
            </div>

            <p>Please log in and review your handbook to see pending change requests and recommended updates.</p>

            <p style="text-align: center; margin-top: 24px;">
                <a href="{handbook_url}" class="btn">Review Handbook</a>
            </p>
        </div>
        <div class="footer">
            <p>Sent via Matcha Recruit</p>
        </div>
    </div>
</body>
</html>
"""

        text_content = f"""
Hi {recipient_name},

A scheduled freshness check found that your employee handbook may need updates.

{impacted_sections} {section_word} may be outdated based on current requirements or company profile changes.

Please log in and review your handbook:
{handbook_url}

- Matcha Recruit
"""

        return await self.send_email(
            to_email=to_email,
            to_name=to_name,
            subject=f"{html.escape(company_name)}: Handbook may need updates ({impacted_sections} {section_word} affected)",
            html_content=html_content,
            text_content=text_content,
        )

