"""CandidateEmailMixin email-send methods.

Extracted from `email.py` during the 2026-05-16 package split. Mixed
into `EmailService` (see `client.py`) via multiple inheritance. Method
bodies call `self.send_email(...)` / `self.is_configured()` / etc. —
`self` is the composed `EmailService` at runtime.
"""
import html
import logging
from datetime import datetime
from typing import Optional

logger = logging.getLogger(__name__)


class CandidateEmailMixin:
    async def send_outreach_email(
        self,
        to_email: str,
        to_name: Optional[str],
        company_name: str,
        position_title: str,
        location: Optional[str],
        salary_range: Optional[str],
        outreach_token: str,
        custom_message: Optional[str] = None,
    ) -> bool:
        """Send an outreach email to a candidate.

        Returns True if sent successfully, False otherwise.
        """
        if not self.is_configured():
            logger.warning("Gmail not configured, skipping email send")
            return False

        app_base_url = self.settings.app_base_url
        outreach_url = f"{app_base_url}/outreach/{outreach_token}"

        # Build email HTML
        location_text = f" in {location}" if location else ""
        salary_text = f"\n<p><strong>Compensation:</strong> {salary_range}</p>" if salary_range else ""

        custom_section = ""
        if custom_message:
            custom_section = f"<p>{custom_message}</p><br>"

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
        .role-card {{ background: #f8f9fa; border-radius: 8px; padding: 20px; margin: 20px 0; }}
        .btn {{ display: inline-block; background: #22c55e; color: white; padding: 14px 28px; text-decoration: none; border-radius: 6px; font-weight: 600; margin: 10px 5px 10px 0; }}
        .btn-secondary {{ background: #6b7280; }}
        .footer {{ text-align: center; padding-top: 20px; border-top: 1px solid #e5e7eb; color: #6b7280; font-size: 12px; }}
    </style>
</head>
<body>
    <div class="container">
        <div class="header">
            <div class="logo">MATCHA</div>
        </div>
        <div class="content">
            <p>Hi{' ' + to_name if to_name else ''},</p>

            {custom_section}

            <p>We came across your profile and think you might be a great fit for an exciting opportunity:</p>

            <div class="role-card">
                <h2 style="margin-top: 0; color: #111;">{position_title}</h2>
                <p><strong>Company:</strong> {company_name}{location_text}</p>
                {salary_text}
            </div>

            <p>If you're interested in learning more, click the button below to express your interest. You'll then have the opportunity to complete a brief screening conversation.</p>

            <p>
                <a href="{outreach_url}" class="btn">I'm Interested</a>
                <a href="{outreach_url}?decline=true" class="btn btn-secondary">Not for me</a>
            </p>

            <p style="color: #6b7280; font-size: 14px;">This link is unique to you and will expire in 14 days.</p>
        </div>
        <div class="footer">
            <p>Sent via Matcha Recruit</p>
        </div>
    </div>
</body>
</html>
"""

        text_content = f"""
Hi{' ' + to_name if to_name else ''},

{custom_message + chr(10) + chr(10) if custom_message else ''}We came across your profile and think you might be a great fit for an exciting opportunity:

{position_title} at {company_name}{location_text}
{('Compensation: ' + salary_range + chr(10)) if salary_range else ''}
If you're interested, visit this link: {outreach_url}

Not interested? Let us know: {outreach_url}?decline=true

This link is unique to you and will expire in 14 days.

- Matcha Recruit
"""

        _subject = f"Opportunity: {position_title} at {company_name}"
        return await self._send_with_fallback(to_email, to_name, _subject, html_content, text_content)

    async def send_screening_invite_email(
        self,
        to_email: str,
        to_name: Optional[str],
        company_name: str,
        position_title: str,
        location: Optional[str],
        salary_range: Optional[str],
        screening_token: str,
        custom_message: Optional[str] = None,
    ) -> bool:
        """Send a direct screening interview invitation to a candidate.

        Unlike outreach emails, this goes directly to the screening interview
        (requires candidate to have an account to access).

        Returns True if sent successfully, False otherwise.
        """
        if not self.is_configured():
            logger.warning("Gmail not configured, skipping email send")
            return False

        app_base_url = self.settings.app_base_url
        screening_url = f"{app_base_url}/screening/{screening_token}"

        # Build email HTML
        location_text = f" in {location}" if location else ""
        salary_text = f"\n<p><strong>Compensation:</strong> {salary_range}</p>" if salary_range else ""

        custom_section = ""
        if custom_message:
            custom_section = f"<p>{custom_message}</p><br>"

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
        .role-card {{ background: #f8f9fa; border-radius: 8px; padding: 20px; margin: 20px 0; }}
        .btn {{ display: inline-block; background: #22c55e; color: white; padding: 14px 28px; text-decoration: none; border-radius: 6px; font-weight: 600; margin: 10px 5px 10px 0; }}
        .footer {{ text-align: center; padding-top: 20px; border-top: 1px solid #e5e7eb; color: #6b7280; font-size: 12px; }}
        .highlight {{ background: #ecfdf5; border-left: 4px solid #22c55e; padding: 15px; margin: 20px 0; }}
    </style>
</head>
<body>
    <div class="container">
        <div class="header">
            <div class="logo">MATCHA</div>
        </div>
        <div class="content">
            <p>Hi{' ' + to_name if to_name else ''},</p>

            {custom_section}

            <p>You've been invited to complete a screening interview for an exciting opportunity:</p>

            <div class="role-card">
                <h2 style="margin-top: 0; color: #111;">{position_title}</h2>
                <p><strong>Company:</strong> {company_name}{location_text}</p>
                {salary_text}
            </div>

            <div class="highlight">
                <strong>What to expect:</strong> A brief voice conversation (about 5-10 minutes) to learn more about your background and interests.
            </div>

            <p>Click below to start your screening interview:</p>

            <p>
                <a href="{screening_url}" class="btn">Start Screening Interview</a>
            </p>

            <p style="color: #6b7280; font-size: 14px;">You'll need to log in or create an account to access the interview. This link is unique to you.</p>
        </div>
        <div class="footer">
            <p>Sent via Matcha Recruit</p>
        </div>
    </div>
</body>
</html>
"""

        text_content = f"""
Hi{' ' + to_name if to_name else ''},

{custom_message + chr(10) + chr(10) if custom_message else ''}You've been invited to complete a screening interview for an exciting opportunity:

{position_title} at {company_name}{location_text}
{('Compensation: ' + salary_range + chr(10)) if salary_range else ''}
What to expect: A brief voice conversation (about 5-10 minutes) to learn more about your background and interests.

Start your screening interview here: {screening_url}

You'll need to log in or create an account to access the interview.

- Matcha Recruit
"""

        _subject = f"Screening Interview: {position_title} at {company_name}"
        return await self._send_with_fallback(to_email, to_name, _subject, html_content, text_content)

    async def send_investigation_interview_invite_email(
        self,
        to_email: str,
        to_name: Optional[str],
        company_name: str,
        interviewee_role: str,  # "witness", "complainant", "respondent", "manager"
        invite_token: str,
        custom_message: Optional[str] = None,
    ) -> bool:
        """Send a workplace investigation interview invitation.

        Keeps content vague for confidentiality — no incident details included.

        Returns True if sent successfully, False otherwise.
        """
        if not self.is_configured():
            logger.warning("Gmail not configured, skipping email send")
            return False

        invite_url = f"{self.settings.app_base_url}/investigation/{invite_token}"

        role_display = interviewee_role.replace("_", " ").capitalize()

        custom_section = ""
        if custom_message:
            custom_section = f"<p>{custom_message}</p><br>"

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
        .btn {{ display: inline-block; background: #22c55e; color: white; padding: 14px 28px; text-decoration: none; border-radius: 6px; font-weight: 600; margin: 10px 5px 10px 0; }}
        .footer {{ text-align: center; padding-top: 20px; border-top: 1px solid #e5e7eb; color: #6b7280; font-size: 12px; }}
        .highlight {{ background: #ecfdf5; border-left: 4px solid #22c55e; padding: 15px; margin: 20px 0; }}
    </style>
</head>
<body>
    <div class="container">
        <div class="header">
            <div class="logo">MATCHA</div>
        </div>
        <div class="content">
            <p>Hi{' ' + to_name if to_name else ''},</p>

            {custom_section}

            <p>You have been asked to participate in a workplace investigation interview as a <strong>{role_display}</strong>. This conversation helps ensure a thorough and fair review of the matter.</p>

            <div class="highlight">
                <strong>What to expect:</strong> A brief voice conversation (about 10–15 minutes). No account required — click the link to begin when you're ready.
            </div>

            <p>
                <a href="{invite_url}" class="btn">Begin Interview</a>
            </p>

            <p style="color: #6b7280; font-size: 14px;">This link is unique to you. Do not share it with others.</p>
        </div>
        <div class="footer">
            <p>Sent on behalf of {company_name} via Matcha</p>
        </div>
    </div>
</body>
</html>
"""

        text_content = f"""
Hi{' ' + to_name if to_name else ''},

{custom_message + chr(10) + chr(10) if custom_message else ''}You have been asked to participate in a workplace investigation interview as a {role_display}. This conversation helps ensure a thorough and fair review of the matter.

What to expect: A brief voice conversation (about 10–15 minutes). No account required — click the link to begin when you're ready.

Begin your interview here: {invite_url}

This link is unique to you. Do not share it with others.

Sent on behalf of {company_name} via Matcha
"""

        _subject = f"Workplace Investigation Interview Request from {company_name}"
        return await self._send_with_fallback(to_email, to_name, _subject, html_content, text_content)

    async def send_ir_info_request_email(
        self,
        to_email: str,
        to_name: Optional[str],
        company_name: str,
        incident_number: str,
        requested_by_name: str,
        questions: list[str],
        custom_message: Optional[str],
        link: str,
    ) -> bool:
        """Send an IR Copilot "Request More Info" invite to an outside party.

        Returns True if sent successfully, False otherwise.
        """
        if not self.is_configured():
            logger.warning("Gmail not configured, skipping email send")
            return False

        to_name_esc = html.escape(to_name) if to_name else None
        requested_by_name_esc = html.escape(requested_by_name)
        company_name_esc = html.escape(company_name)
        incident_number_esc = html.escape(incident_number)
        custom_message_esc = html.escape(custom_message) if custom_message else None

        custom_section = f"<p>{custom_message_esc}</p><br>" if custom_message_esc else ""
        custom_text = f"{custom_message}\n\n" if custom_message else ""
        questions_html = "".join(f"<li>{html.escape(q)}</li>" for q in questions)
        questions_text = "\n".join(f"- {q}" for q in questions)

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
        .btn {{ display: inline-block; background: #22c55e; color: white; padding: 14px 28px; text-decoration: none; border-radius: 6px; font-weight: 600; margin: 10px 5px 10px 0; }}
        .footer {{ text-align: center; padding-top: 20px; border-top: 1px solid #e5e7eb; color: #6b7280; font-size: 12px; }}
        .highlight {{ background: #ecfdf5; border-left: 4px solid #22c55e; padding: 15px; margin: 20px 0; }}
    </style>
</head>
<body>
    <div class="container">
        <div class="header">
            <div class="logo">MATCHA</div>
        </div>
        <div class="content">
            <p>Hi{' ' + to_name_esc if to_name_esc else ''},</p>

            {custom_section}

            <p>{requested_by_name_esc} at {company_name_esc} is asking for a bit more information about incident <strong>{incident_number_esc}</strong>:</p>

            <div class="highlight">
                <ul style="margin: 0; padding-left: 20px;">
                    {questions_html}
                </ul>
            </div>

            <p>
                <a href="{link}" class="btn">Answer questions</a>
            </p>

            <p style="color: #6b7280; font-size: 14px;">This link is unique to you and expires after a single use. Do not share it with others.</p>
        </div>
        <div class="footer">
            <p>Sent on behalf of {company_name_esc} via Matcha</p>
        </div>
    </div>
</body>
</html>
"""

        text_content = f"""
Hi{' ' + to_name if to_name else ''},

{custom_text}{requested_by_name} at {company_name} is asking for a bit more information about incident {incident_number}:

{questions_text}

Answer here: {link}

This link is unique to you and expires after a single use. Do not share it with others.

Sent on behalf of {company_name} via Matcha
"""

        subject = f"{company_name} needs more info on incident {incident_number}"
        return await self._send_with_fallback(to_email, to_name, subject, html_content, text_content)

    async def send_candidate_interview_invite_email(
        self,
        to_email: str,
        to_name: str,
        company_name: str,
        position_title: str,
        invite_url: str,
        custom_message: Optional[str] = None,
    ) -> bool:
        """Send a candidate screening interview invitation via email."""
        if not self.is_configured():
            logger.warning("Gmail not configured, skipping candidate interview invite")
            return False

        custom_section = ""
        if custom_message:
            custom_section = f"<p>{custom_message}</p><br>"

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
        .btn {{ display: inline-block; background: #22c55e; color: white; padding: 14px 28px; text-decoration: none; border-radius: 6px; font-weight: 600; }}
        .footer {{ text-align: center; padding-top: 20px; border-top: 1px solid #e5e7eb; color: #6b7280; font-size: 12px; }}
        .highlight {{ background: #ecfdf5; border-left: 4px solid #22c55e; padding: 15px; margin: 20px 0; }}
    </style>
</head>
<body>
    <div class="container">
        <div class="header">
            <div class="logo">MATCHA</div>
        </div>
        <div class="content">
            <p>Hi {to_name},</p>

            {custom_section}

            <p>You've been invited to interview for the <strong>{position_title}</strong> position at <strong>{company_name}</strong>.</p>

            <div class="highlight">
                <strong>What to expect:</strong> A brief voice conversation (about 10–15 minutes) with our AI interviewer. No account or download required — just click the link below when you're ready.
            </div>

            <p>
                <a href="{invite_url}" class="btn">Begin Interview</a>
            </p>

            <p style="color: #6b7280; font-size: 14px;">This link is unique to you. Do not share it with others.</p>
        </div>
        <div class="footer">
            <p>Sent on behalf of {company_name} via Matcha</p>
        </div>
    </div>
</body>
</html>
"""

        text_content = f"""
Hi {to_name},

{custom_message + chr(10) + chr(10) if custom_message else ''}You've been invited to interview for the {position_title} position at {company_name}.

What to expect: A brief voice conversation (about 10-15 minutes) with our AI interviewer. No account or download required.

Begin your interview here: {invite_url}

This link is unique to you. Do not share it with others.

Sent on behalf of {company_name} via Matcha
"""

        _subject = f"Interview Invitation: {position_title} at {company_name}"
        return await self._send_with_fallback(to_email, to_name, _subject, html_content, text_content)

    async def send_candidate_rejection_email(
        self,
        to_email: str,
        to_name: str,
        company_name: str,
        position_title: str,
        custom_message: Optional[str] = None,
    ) -> bool:
        """Send a polite rejection email to a candidate."""
        if not self.is_configured():
            logger.warning("Gmail not configured, skipping candidate rejection email")
            return False

        custom_section = ""
        if custom_message:
            custom_section = (
                f'<div class="highlight">{custom_message}</div>'
            )

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
        .footer {{ text-align: center; padding-top: 20px; border-top: 1px solid #e5e7eb; color: #6b7280; font-size: 12px; }}
        .highlight {{ background: #ecfdf5; border-left: 4px solid #22c55e; padding: 15px; margin: 20px 0; color: #374151; }}
    </style>
</head>
<body>
    <div class="container">
        <div class="header">
            <div class="logo">MATCHA</div>
        </div>
        <div class="content">
            <p>Hi {to_name},</p>

            <p>Thank you for your interest in the <strong>{position_title}</strong> position at <strong>{company_name}</strong> and for taking the time to apply.</p>

            <p>After careful consideration we've decided to move forward with other candidates whose experience more closely matches what we're looking for at this time. This was a tough call — we received many strong applications.</p>

            {custom_section}

            <p>We're grateful you considered joining us. We'll keep your details on file and encourage you to apply again if another role feels like a fit down the road.</p>

            <p>Wishing you the very best in your search,<br>The {company_name} team</p>
        </div>
        <div class="footer">
            <p>Sent on behalf of {company_name} via Matcha</p>
        </div>
    </div>
</body>
</html>
"""

        text_content = f"""
Hi {to_name},

Thank you for your interest in the {position_title} position at {company_name} and for taking the time to apply.

After careful consideration we've decided to move forward with other candidates whose experience more closely matches what we're looking for at this time. This was a tough call — we received many strong applications.

{(custom_message + chr(10) + chr(10)) if custom_message else ''}We're grateful you considered joining us. We'll keep your details on file and encourage you to apply again if another role feels like a fit down the road.

Wishing you the very best in your search,
The {company_name} team

Sent on behalf of {company_name} via Matcha
"""

        _subject = f"Update on your {position_title} application at {company_name}"
        return await self._send_with_fallback(to_email, to_name, _subject, html_content, text_content)

    async def send_candidate_reach_out_email(
        self,
        to_email: str,
        to_name: str,
        subject: str,
        body: str,
        from_name: str,
        from_company: str,
    ) -> bool:
        """Send a personalized meeting-request email to a candidate.

        The subject and body are admin-reviewed (possibly AI-drafted) text.
        Returns True if sent successfully, False otherwise.
        """
        if not self.is_configured():
            logger.warning("Gmail not configured, skipping email send")
            return False

        # Wrap the plain-text body in a simple HTML email
        html_body = body.replace('\n', '<br>')
        html_content = f"""
<!DOCTYPE html>
<html>
<head>
    <style>
        body {{ font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif; line-height: 1.7; color: #333; }}
        .container {{ max-width: 600px; margin: 0 auto; padding: 20px; }}
        .header {{ text-align: center; padding: 20px 0; border-bottom: 2px solid #22c55e; }}
        .logo {{ color: #22c55e; font-size: 24px; font-weight: bold; letter-spacing: 2px; }}
        .content {{ padding: 30px 0; font-size: 15px; }}
        .footer {{ text-align: center; padding-top: 20px; border-top: 1px solid #e5e7eb; color: #6b7280; font-size: 12px; }}
    </style>
</head>
<body>
    <div class="container">
        <div class="header">
            <div class="logo">MATCHA</div>
        </div>
        <div class="content">
            {html_body}
        </div>
        <div class="footer">
            <p>Sent via Matcha Recruit on behalf of {from_company}</p>
        </div>
    </div>
</body>
</html>
"""

        return await self._send_with_fallback(to_email, to_name, subject, html_content, text_content)

