"""Email service using Gmail API via OAuth2."""
import base64
import html
import httpx
import json
import logging
from datetime import date, datetime
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from email.mime.base import MIMEBase
from email import encoders
from pathlib import Path
from typing import Optional

from app.config import get_settings

logger = logging.getLogger(__name__)

GMAIL_TOKEN_URI = "https://oauth2.googleapis.com/token"
GMAIL_SEND_URI = "https://gmail.googleapis.com/gmail/v1/users/me/messages/send"

# Reserved-domain guard now lives in _shared.py. Re-imported here so the
# in-file `if _is_reserved_test_domain(to_email):` call sites still resolve.
from ._shared import (  # noqa: F401
    _is_reserved_test_domain,
    _RESERVED_EXAMPLE_DOMAINS,
    _RESERVED_TLDS,
)


from .auth import AuthEmailMixin
from .employee import EmployeeEmailMixin


class EmailService(AuthEmailMixin, EmployeeEmailMixin):
    """Service for sending emails via Gmail API.

    Composes per-domain mixins (see `email/<domain>.py`). This class
    keeps only transport + composition.
    """

    def __init__(self):
        import os
        self.settings = get_settings()
        self.from_email = self.settings.gmail_from_email
        self.from_name = self.settings.gmail_from_name
        self._token_data: Optional[dict] = None
        # MailerSend credentials (used by broker invite and other transactional emails)
        self.api_key = os.getenv("MAILERSEND_API_KEY", "")
        self.base_url = os.getenv("MAILERSEND_BASE_URL", "https://api.mailersend.com/v1")
        self.mailersend_from_email = os.getenv("MAILERSEND_FROM_EMAIL", self.from_email)

    def _load_token(self) -> Optional[dict]:
        token_path = Path(self.settings.gmail_token_path)
        if not token_path.is_absolute():
            # Resolve relative to server/ directory
            token_path = Path(__file__).parent.parent.parent.parent / self.settings.gmail_token_path
        if not token_path.exists():
            return None
        with open(token_path) as f:
            return json.load(f)

    def is_configured(self) -> bool:
        """Check if any email backend (Gmail or MailerSend) is configured."""
        if self.api_key:
            return True
        data = self._load_token()
        return bool(data and data.get("refresh_token") and data.get("client_id") and data.get("client_secret"))

    async def _get_access_token(self) -> str:
        """Return a valid access token, refreshing if necessary."""
        data = self._load_token()
        if not data:
            raise RuntimeError("Gmail token.json not found")

        async with httpx.AsyncClient() as client:
            resp = await client.post(
                GMAIL_TOKEN_URI,
                data={
                    "client_id": data["client_id"],
                    "client_secret": data["client_secret"],
                    "refresh_token": data["refresh_token"],
                    "grant_type": "refresh_token",
                },
                timeout=10.0,
            )
            resp.raise_for_status()
            return resp.json()["access_token"]

    async def send_email(
        self,
        to_email: str,
        to_name: Optional[str],
        subject: str,
        html_content: str,
        text_content: Optional[str] = None,
        attachments: Optional[list[dict]] = None,
        extra_headers: Optional[dict[str, str]] = None,
    ) -> bool:
        """Send an email via Gmail API.

        Attachments format: {"filename": "...", "content": "<base64>", "disposition": "attachment"}
        extra_headers lets callers attach RFC headers like List-Unsubscribe so
        Gmail/Outlook render the one-click unsubscribe button.
        """
        if not self.is_configured():
            logger.warning("Gmail not configured — token.json missing or incomplete")
            return False

        if _is_reserved_test_domain(to_email):
            logger.warning(
                "Skipping send to reserved/test email domain: %s (subject=%r)",
                to_email,
                subject,
            )
            return False

        try:
            msg = MIMEMultipart("alternative") if not attachments else MIMEMultipart("mixed")
            msg["Subject"] = subject
            msg["From"] = f"{self.from_name} <{self.from_email}>"
            msg["To"] = f"{to_name} <{to_email}>" if to_name else to_email
            if extra_headers:
                for name, value in extra_headers.items():
                    msg[name] = value

            if attachments:
                alt = MIMEMultipart("alternative")
                if text_content:
                    alt.attach(MIMEText(text_content, "plain"))
                alt.attach(MIMEText(html_content, "html"))
                msg.attach(alt)
                for att in attachments:
                    part = MIMEBase("application", "octet-stream")
                    part.set_payload(base64.b64decode(att["content"]))
                    encoders.encode_base64(part)
                    part.add_header("Content-Disposition", att.get("disposition", "attachment"), filename=att["filename"])
                    msg.attach(part)
            else:
                if text_content:
                    msg.attach(MIMEText(text_content, "plain"))
                msg.attach(MIMEText(html_content, "html"))

            raw = base64.urlsafe_b64encode(msg.as_bytes()).decode()
            token = await self._get_access_token()

            async with httpx.AsyncClient() as client:
                response = await client.post(
                    GMAIL_SEND_URI,
                    json={"raw": raw},
                    headers={"Authorization": f"Bearer {token}"},
                    timeout=30.0,
                )

            if response.status_code == 200:
                logger.info("Sent email to %s", to_email)
                return True
            else:
                logger.warning(
                    "Failed to send email to %s: %s - %s",
                    to_email, response.status_code, response.text[:200],
                )
                return False

        except Exception:
            logger.exception("Error sending email to %s", to_email)
            return False

    async def _send_with_fallback(
        self,
        to_email: str,
        to_name: Optional[str],
        subject: str,
        html_content: str,
        text_content: Optional[str] = None,
    ) -> bool:
        """Send via Gmail first, fall back to MailerSend if Gmail fails."""
        # Try Gmail first
        gmail_token = self._load_token()
        if gmail_token and gmail_token.get("refresh_token"):
            sent = await self.send_email(
                to_email=to_email, to_name=to_name, subject=subject,
                html_content=html_content, text_content=text_content,
            )
            if sent:
                return True
            logger.warning("Gmail send failed for %s, trying MailerSend fallback", to_email)

        # Fallback to MailerSend
        if not self.api_key:
            logger.warning("MailerSend not configured, cannot send to %s", to_email)
            return False

        payload = {
            "from": {"email": self.mailersend_from_email, "name": self.from_name},
            "to": [{"email": to_email, "name": to_name or to_email}],
            "subject": subject,
            "html": html_content,
            "text": text_content or "",
        }
        try:
            async with httpx.AsyncClient() as client:
                response = await client.post(
                    f"{self.base_url}/email",
                    json=payload,
                    headers={"Authorization": f"Bearer {self.api_key}", "Content-Type": "application/json"},
                    timeout=30.0,
                )
                if response.status_code in (200, 201, 202):
                    logger.info("Sent email to %s via MailerSend fallback", to_email)
                    return True
                else:
                    logger.warning("MailerSend fallback failed for %s: %s", to_email, response.status_code)
                    return False
        except Exception:
            logger.exception("MailerSend fallback error for %s", to_email)
            return False

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

    async def send_contact_form_email(
        self,
        sender_name: str,
        sender_email: str,
        company_name: str,
        message: str,
        preferred_date: str | None = None,
        preferred_time: str | None = None,
    ) -> bool:
        """Send a contact form submission to the admin email.

        Returns True if sent successfully, False otherwise.
        """
        if not self.is_configured():
            logger.warning("Gmail not configured, skipping contact form email")
            return False

        contact_email = self.settings.contact_email

        is_consultation = preferred_date is not None or preferred_time is not None
        subject_prefix = "Consultation Request" if is_consultation else "Contact Form"

        schedule_html = ""
        schedule_text = ""
        if is_consultation:
            date_str = preferred_date or "Not specified"
            time_str = preferred_time or "Not specified"
            schedule_html = f"""
                <div style="margin-bottom: 16px;">
                    <div class="label">Requested Date</div>
                    <div class="value">{date_str}</div>
                </div>
                <div style="margin-bottom: 16px;">
                    <div class="label">Requested Time (ET)</div>
                    <div class="value">{time_str}</div>
                </div>"""
            schedule_text = f"\nRequested Date: {date_str}\nRequested Time (ET): {time_str}"

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
        .info-card {{ background: #f8f9fa; border-radius: 8px; padding: 20px; margin: 20px 0; }}
        .label {{ font-weight: 600; color: #6b7280; font-size: 12px; text-transform: uppercase; letter-spacing: 1px; }}
        .value {{ margin-top: 4px; color: #111; }}
        .message {{ background: #fff; border: 1px solid #e5e7eb; border-radius: 8px; padding: 20px; margin-top: 20px; white-space: pre-wrap; }}
        .footer {{ text-align: center; padding-top: 20px; border-top: 1px solid #e5e7eb; color: #6b7280; font-size: 12px; }}
    </style>
</head>
<body>
    <div class="container">
        <div class="header">
            <div class="logo">MATCHA</div>
        </div>
        <div class="content">
            <h2 style="margin-top: 0;">{'New Consultation Request' if is_consultation else 'New Contact Form Submission'}</h2>

            <div class="info-card">
                <div style="margin-bottom: 16px;">
                    <div class="label">Company</div>
                    <div class="value">{company_name}</div>
                </div>
                <div style="margin-bottom: 16px;">
                    <div class="label">Contact Name</div>
                    <div class="value">{sender_name}</div>
                </div>
                <div style="margin-bottom: 16px;">
                    <div class="label">Email</div>
                    <div class="value"><a href="mailto:{sender_email}">{sender_email}</a></div>
                </div>{schedule_html}
            </div>

            <div class="label">Message</div>
            <div class="message">{message}</div>
        </div>
        <div class="footer">
            <p>Sent from Matcha Recruit contact form</p>
        </div>
    </div>
</body>
</html>
"""

        text_content = f"""
{'New Consultation Request' if is_consultation else 'New Contact Form Submission'}

Company: {company_name}
Contact: {sender_name}
Email: {sender_email}{schedule_text}

Message:
{message}

---
Sent from Matcha Recruit contact form
"""

        return await self.send_email(
            to_email=contact_email,
            to_name="Matcha Team",
            subject=f"{subject_prefix}: {company_name} - {sender_name}",
            html_content=html_content,
            text_content=text_content,
        )

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

    async def send_blog_comment_pending_notification(
        self,
        to_email: str,
        post_title: str,
        post_slug: str,
        author_label: str,
        comment_excerpt: str,
        comment_id: str,
    ) -> bool:
        """Notify a platform admin that a blog comment is awaiting review."""
        if not self.is_configured():
            logger.warning("Email not configured, skipping blog comment notification")
            return False

        app_base_url = (self.settings.app_base_url or "").rstrip("/")
        post_url = f"{app_base_url}/blog/{post_slug}" if app_base_url else f"/blog/{post_slug}"
        admin_url = f"{app_base_url}/admin/blogs?tab=comments" if app_base_url else "/admin/blogs?tab=comments"

        post_title_safe = html.escape(post_title)
        author_safe = html.escape(author_label)
        excerpt_safe = html.escape(comment_excerpt)

        html_content = f"""
<!DOCTYPE html>
<html>
<head>
    <style>
        body {{ font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif; line-height: 1.6; color: #333; }}
        .container {{ max-width: 600px; margin: 0 auto; padding: 20px; }}
        .logo {{ color: #22c55e; font-size: 22px; font-weight: bold; letter-spacing: 2px; }}
        .card {{ background: #f8fafc; border-left: 4px solid #2563eb; border-radius: 8px; padding: 16px; margin: 16px 0; }}
        .quote {{ background: #f9fafb; border-radius: 6px; padding: 12px 14px; font-style: italic; color: #444; margin: 12px 0; white-space: pre-wrap; }}
        .btn {{ display: inline-block; background: #22c55e; color: white; padding: 12px 20px; text-decoration: none; border-radius: 6px; font-weight: 600; }}
        .footer {{ text-align: center; padding-top: 20px; border-top: 1px solid #e5e7eb; color: #6b7280; font-size: 12px; margin-top: 24px; }}
    </style>
</head>
<body>
    <div class="container">
        <div class="logo">MATCHA</div>
        <h2 style="font-size:18px;color:#111;">New blog comment awaiting review</h2>
        <div class="card">
            <p style="margin:0 0 4px 0;"><strong>Post:</strong> <a href="{post_url}">{post_title_safe}</a></p>
            <p style="margin:0;"><strong>From:</strong> {author_safe}</p>
        </div>
        <div class="quote">{excerpt_safe}</div>
        <p style="text-align:center;">
            <a href="{admin_url}" class="btn">Review &amp; moderate</a>
        </p>
        <div class="footer">Sent via Matcha Recruit · comment id {comment_id}</div>
    </div>
</body>
</html>
"""
        text_content = (
            f"New blog comment awaiting review\n\n"
            f"Post: {post_title}\n{post_url}\n\n"
            f"From: {author_label}\n\n"
            f"\"{comment_excerpt}\"\n\n"
            f"Review & moderate: {admin_url}\n"
        )

        return await self.send_email(
            to_email=to_email,
            subject=f"[Matcha] New blog comment on \"{post_title}\" awaiting review",
            html_content=html_content,
            text_content=text_content,
        )

    async def send_training_assignment_email(
        self,
        to_email: str,
        to_name: Optional[str],
        training_title: str,
        due_date: Optional[date],
        login_url: str,
    ) -> bool:
        """Notify an employee they've been assigned a training (CA SB 1343 et al)."""
        title_safe = html.escape(training_title)
        due_label = due_date.strftime("%B %-d, %Y") if due_date else "as soon as possible"
        html_content = f"""<!DOCTYPE html>
<html><head><meta charset="UTF-8"><style>
  body {{ font-family: 'Helvetica Neue', Arial, sans-serif; color: #1f2937; background: #f8fafc; margin: 0; padding: 24px; }}
  .container {{ max-width: 560px; margin: 0 auto; background: white; border-radius: 8px; padding: 28px; }}
  .logo {{ color: #16a34a; font-weight: bold; letter-spacing: 2px; font-size: 18px; }}
  h1 {{ font-size: 20px; margin: 16px 0; }}
  .btn {{ display: inline-block; background: #16a34a; color: white; padding: 12px 22px;
          text-decoration: none; border-radius: 6px; font-weight: 600; margin-top: 16px; }}
  .meta {{ background: #f1f5f9; border-left: 3px solid #16a34a; padding: 12px 16px;
           border-radius: 6px; margin: 16px 0; font-size: 14px; }}
  .footer {{ font-size: 12px; color: #94a3b8; margin-top: 24px; }}
</style></head>
<body>
  <div class="container">
    <div class="logo">MATCHA</div>
    <h1>Required training assigned</h1>
    <p>Hi {html.escape(to_name or '')},</p>
    <p>You've been assigned a required training: <strong>{title_safe}</strong>.</p>
    <div class="meta">
      <div><strong>Complete by:</strong> {due_label}</div>
    </div>
    <p>This training is required by California SB 1343. It must be completed
    fully — there's a minimum seat-time requirement, followed by a short
    quiz and an attestation.</p>
    <p><a class="btn" href="{login_url}">Start training</a></p>
    <div class="footer">If you have questions, reply to this email or contact your HR administrator.</div>
  </div>
</body></html>"""
        text_content = (
            f"Required training assigned: {training_title}\n\n"
            f"Complete by: {due_label}\n\n"
            f"Start at: {login_url}\n"
        )
        return await self._send_with_fallback(
            to_email=to_email,
            to_name=to_name,
            subject=f"Required training: {training_title}",
            html_content=html_content,
            text_content=text_content,
        )

    async def send_training_completion_email(
        self,
        to_email: str,
        to_name: Optional[str],
        training_title: str,
        score_percent: float,
        expiration_date: Optional[date],
        pdf_bytes: bytes,
    ) -> bool:
        """Send completion confirmation with PDF cert attached."""
        title_safe = html.escape(training_title)
        valid_until = expiration_date.strftime("%B %-d, %Y") if expiration_date else "—"
        html_content = f"""<!DOCTYPE html>
<html><head><meta charset="UTF-8"><style>
  body {{ font-family: 'Helvetica Neue', Arial, sans-serif; color: #1f2937; background: #f8fafc; margin: 0; padding: 24px; }}
  .container {{ max-width: 560px; margin: 0 auto; background: white; border-radius: 8px; padding: 28px; }}
  .logo {{ color: #16a34a; font-weight: bold; letter-spacing: 2px; font-size: 18px; }}
  h1 {{ font-size: 20px; margin: 16px 0; }}
  .meta {{ background: #ecfdf5; border-left: 3px solid #16a34a; padding: 12px 16px;
           border-radius: 6px; margin: 16px 0; font-size: 14px; }}
  .footer {{ font-size: 12px; color: #94a3b8; margin-top: 24px; }}
</style></head>
<body>
  <div class="container">
    <div class="logo">MATCHA</div>
    <h1>Training completed</h1>
    <p>Hi {html.escape(to_name or '')},</p>
    <p>You completed <strong>{title_safe}</strong>. Your certificate is attached
    to this email.</p>
    <div class="meta">
      <div><strong>Score:</strong> {score_percent:.1f}%</div>
      <div><strong>Valid until:</strong> {valid_until}</div>
    </div>
    <p>Save this certificate for your records. Your employer also retains a
    copy. You'll be notified when renewal is due.</p>
    <div class="footer">California SB 1343 / Gov. Code §12950.1</div>
  </div>
</body></html>"""
        text_content = (
            f"Training completed: {training_title}\n"
            f"Score: {score_percent:.1f}%\n"
            f"Valid until: {valid_until}\n"
        )
        attachment = {
            "filename": "training_certificate.pdf",
            "content": base64.b64encode(pdf_bytes).decode(),
            "disposition": "attachment",
        }
        return await self.send_email(
            to_email=to_email,
            to_name=to_name,
            subject=f"Training certificate: {training_title}",
            html_content=html_content,
            text_content=text_content,
            attachments=[attachment],
        )


# Singleton instance
_email_service: Optional[EmailService] = None


def get_email_service() -> EmailService:
    """Get the email service singleton."""
    global _email_service
    if _email_service is None:
        _email_service = EmailService()
    return _email_service
