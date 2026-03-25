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

from ...config import get_settings

logger = logging.getLogger(__name__)

GMAIL_TOKEN_URI = "https://oauth2.googleapis.com/token"
GMAIL_SEND_URI = "https://gmail.googleapis.com/gmail/v1/users/me/messages/send"


class EmailService:
    """Service for sending emails via Gmail API."""

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
    ) -> bool:
        """Send an email via Gmail API.

        Attachments format: {"filename": "...", "content": "<base64>", "disposition": "attachment"}
        """
        if not self.is_configured():
            logger.warning("Gmail not configured — token.json missing or incomplete")
            return False

        try:
            msg = MIMEMultipart("alternative") if not attachments else MIMEMultipart("mixed")
            msg["Subject"] = subject
            msg["From"] = f"{self.from_name} <{self.from_email}>"
            msg["To"] = f"{to_name} <{to_email}>" if to_name else to_email

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

        payload = {
            "from": {
                "email": self.from_email,
                "name": self.from_name,
            },
            "to": [
                {
                    "email": to_email,
                    "name": to_name or to_email,
                }
            ],
            "subject": f"Opportunity: {position_title} at {company_name}",
            "html": html_content,
            "text": text_content,
        }

        try:
            async with httpx.AsyncClient() as client:
                response = await client.post(
                    f"{self.base_url}/email",
                    json=payload,
                    headers={
                        "Authorization": f"Bearer {self.api_key}",
                        "Content-Type": "application/json",
                    },
                    timeout=30.0,
                )

                if response.status_code in (200, 201, 202):
                    logger.info("Sent outreach email to %s", to_email)
                    return True
                else:
                    logger.warning("Failed to send to %s: %s - %s", to_email, response.status_code, response.text[:200])
                    return False

        except Exception as e:
            logger.exception("Error sending to %s", to_email)
            return False

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

        payload = {
            "from": {
                "email": self.from_email,
                "name": self.from_name,
            },
            "to": [
                {
                    "email": to_email,
                    "name": to_name or to_email,
                }
            ],
            "subject": f"Screening Interview: {position_title} at {company_name}",
            "html": html_content,
            "text": text_content,
        }

        try:
            async with httpx.AsyncClient() as client:
                response = await client.post(
                    f"{self.base_url}/email",
                    json=payload,
                    headers={
                        "Authorization": f"Bearer {self.api_key}",
                        "Content-Type": "application/json",
                    },
                    timeout=30.0,
                )

                if response.status_code in (200, 201, 202):
                    logger.info("Sent screening invite to %s", to_email)
                    return True
                else:
                    logger.warning("Failed to send to %s: %s - %s", to_email, response.status_code, response.text[:200])
                    return False

        except Exception as e:
            logger.exception("Error sending to %s", to_email)
            return False

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

        payload = {
            "from": {
                "email": self.from_email,
                "name": self.from_name,
            },
            "to": [
                {
                    "email": to_email,
                    "name": to_name or to_email,
                }
            ],
            "subject": f"Workplace Investigation Interview Request from {company_name}",
            "html": html_content,
            "text": text_content,
        }

        try:
            async with httpx.AsyncClient() as client:
                response = await client.post(
                    f"{self.base_url}/email",
                    json=payload,
                    headers={
                        "Authorization": f"Bearer {self.api_key}",
                        "Content-Type": "application/json",
                    },
                    timeout=30.0,
                )

                if response.status_code in (200, 201, 202):
                    logger.info("Sent investigation invite to %s", to_email)
                    return True
                else:
                    logger.warning("Failed to send to %s: %s - %s", to_email, response.status_code, response.text[:200])
                    return False

        except Exception as e:
            logger.exception("Error sending to %s", to_email)
            return False

    async def send_contact_form_email(
        self,
        sender_name: str,
        sender_email: str,
        company_name: str,
        message: str,
    ) -> bool:
        """Send a contact form submission to the admin email.

        Returns True if sent successfully, False otherwise.
        """
        if not self.is_configured():
            logger.warning("Gmail not configured, skipping contact form email")
            return False

        contact_email = self.settings.contact_email

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
            <h2 style="margin-top: 0;">New Contact Form Submission</h2>

            <div class="info-card">
                <div style="margin-bottom: 16px;">
                    <div class="label">Company</div>
                    <div class="value">{company_name}</div>
                </div>
                <div style="margin-bottom: 16px;">
                    <div class="label">Contact Name</div>
                    <div class="value">{sender_name}</div>
                </div>
                <div>
                    <div class="label">Email</div>
                    <div class="value"><a href="mailto:{sender_email}">{sender_email}</a></div>
                </div>
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
New Contact Form Submission

Company: {company_name}
Contact: {sender_name}
Email: {sender_email}

Message:
{message}

---
Sent from Matcha Recruit contact form
"""

        return await self.send_email(
            to_email=contact_email,
            to_name="Matcha Team",
            subject=f"Contact Form: {company_name} - {sender_name}",
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

    async def send_broker_client_setup_invitation_email(
        self,
        to_email: str,
        to_name: str,
        broker_name: str,
        company_name: str,
        invite_url: str,
        expires_at: Optional[datetime] = None,
    ) -> bool:
        """Send a broker client onboarding invitation email."""
        if not self.is_configured():
            logger.warning("Gmail not configured, skipping email send")
            return False

        expires_text = (
            expires_at.strftime('%B %d, %Y at %I:%M %p')
            if isinstance(expires_at, datetime)
            else "in a limited time window"
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
        .card {{ background: #f8fafc; border: 1px solid #e5e7eb; border-radius: 10px; padding: 18px; margin: 20px 0; }}
        .btn {{ display: inline-block; background: #22c55e; color: white; padding: 14px 28px; text-decoration: none; border-radius: 8px; font-weight: 600; margin: 12px 0; }}
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

            <p>{broker_name} invited you to activate your compliance workspace for <strong>{company_name}</strong>.</p>

            <div class="card">
                <p style="margin: 0 0 8px 0;"><strong>What you'll do:</strong></p>
                <p style="margin: 0;">Create your account, review your preconfigured setup, and begin compliance onboarding.</p>
            </div>

            <p style="text-align: center;">
                <a href="{invite_url}" class="btn">Activate Client Workspace</a>
            </p>

            <p style="color: #6b7280; font-size: 14px; text-align: center;">
                This invitation expires on {expires_text}.
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

{broker_name} invited you to activate your compliance workspace for {company_name}.

Use this invite link to activate your client workspace:
{invite_url}

This invitation expires on {expires_text}.

- Matcha Recruit
"""

        subject = f"{broker_name} invited you to activate {company_name} on Matcha"

        if not self.api_key:
            # Fall back to Gmail API if MailerSend not configured
            return await self.send_email(
                to_email=to_email, to_name=to_name, subject=subject,
                html_content=html_content, text_content=text_content,
            )

        payload = {
            "from": {"email": self.mailersend_from_email, "name": self.from_name},
            "to": [{"email": to_email, "name": to_name}],
            "subject": subject,
            "html": html_content,
            "text": text_content,
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
                    logger.info("Sent broker client invite to %s via MailerSend", to_email)
                    return True
                else:
                    logger.warning("Failed to send to %s: %s - %s", to_email, response.status_code, response.text[:200])
                    return False
        except Exception:
            logger.exception("Error sending broker invite to %s", to_email)
            return False

    async def send_broker_welcome_email(
        self,
        to_email: str,
        to_name: str,
        broker_name: str,
        broker_slug: str,
        password: str,
    ) -> bool:
        """Send a welcome email to a newly created broker owner with their login credentials."""
        if not self.is_configured():
            logger.warning("Gmail not configured, skipping email send")
            return False

        app_base_url = self.settings.app_base_url
        login_url = f"{app_base_url}/login/{broker_slug}"
        safe_name = html.escape(to_name)
        safe_broker = html.escape(broker_name)
        safe_email = html.escape(to_email)
        safe_password = html.escape(password)

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
        .card {{ background: #f9fafb; border: 1px solid #e5e7eb; border-radius: 8px; padding: 20px; margin: 20px 0; }}
        .card-label {{ font-size: 12px; color: #6b7280; text-transform: uppercase; letter-spacing: 1px; margin-bottom: 4px; }}
        .card-value {{ font-size: 16px; font-weight: 600; color: #111; }}
        .card-value.mono {{ font-family: 'SF Mono', Monaco, Consolas, monospace; }}
        .btn {{ display: inline-block; background: #22c55e; color: white; padding: 16px 32px; text-decoration: none; border-radius: 8px; font-weight: 600; font-size: 16px; }}
        .security-note {{ background: #fffbeb; border-left: 4px solid #f59e0b; border-radius: 4px; padding: 12px 16px; margin: 20px 0; font-size: 14px; color: #92400e; }}
        .footer {{ text-align: center; padding-top: 20px; border-top: 1px solid #e5e7eb; color: #6b7280; font-size: 12px; }}
    </style>
</head>
<body>
    <div class="container">
        <div class="header">
            <div class="logo">MATCHA</div>
        </div>
        <div class="content">
            <p>Hi {safe_name},</p>

            <p>Your broker account <strong>{safe_broker}</strong> has been created on Matcha. Here are your login credentials:</p>

            <div class="card">
                <div style="margin-bottom: 16px;">
                    <div class="card-label">Email</div>
                    <div class="card-value">{safe_email}</div>
                </div>
                <div>
                    <div class="card-label">Password</div>
                    <div class="card-value mono">{safe_password}</div>
                </div>
            </div>

            <p style="text-align: center; margin-top: 24px;">
                <a href="{login_url}" class="btn">Log In to Your Dashboard</a>
            </p>

            <div class="security-note">
                For security, please change your password after your first login.
            </div>
        </div>
        <div class="footer">
            <p>Sent via Matcha Recruit</p>
        </div>
    </div>
</body>
</html>
"""

        text_content = f"""Hi {to_name},

Your broker account "{broker_name}" has been created on Matcha.

Your login credentials:
  Email: {to_email}
  Password: {password}

Log in at: {login_url}

For security, please change your password after your first login.

- Matcha Recruit
"""

        return await self.send_email(
            to_email=to_email,
            to_name=to_name,
            subject=f"Welcome to Matcha — Your {broker_name} broker account is ready",
            html_content=html_content,
            text_content=text_content,
        )

    async def send_employee_invitation_email(
        self,
        to_email: str,
        to_name: str,
        company_name: str,
        token: str,
        expires_at,
    ) -> bool:
        """Send an employee onboarding invitation email.

        This email is sent when an admin creates an employee and wants them to set up their account.

        Returns True if sent successfully, False otherwise.
        """
        if not self.is_configured():
            logger.warning("Gmail not configured, skipping employee invitation email")
            return False

        app_base_url = self.settings.app_base_url
        invitation_url = f"{app_base_url}/invite/{token}"

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
        .welcome-card {{ background: linear-gradient(135deg, #ecfdf5 0%, #f0fdf4 100%); border-radius: 12px; padding: 30px; margin: 20px 0; text-align: center; }}
        .company-name {{ font-size: 28px; font-weight: 700; color: #111; margin-bottom: 8px; }}
        .btn {{ display: inline-block; background: #22c55e; color: white; padding: 16px 32px; text-decoration: none; border-radius: 8px; font-weight: 600; margin: 20px 0; font-size: 16px; }}
        .btn:hover {{ background: #16a34a; }}
        .steps {{ background: #f9fafb; border-radius: 8px; padding: 20px; margin: 20px 0; }}
        .step {{ display: flex; align-items: flex-start; margin-bottom: 12px; }}
        .step-number {{ background: #22c55e; color: white; width: 24px; height: 24px; border-radius: 50%; display: flex; align-items: center; justify-content: center; font-size: 12px; font-weight: 600; margin-right: 12px; flex-shrink: 0; }}
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

            <p>Welcome! You've been invited to join the employee portal.</p>

            <div class="welcome-card">
                <div class="company-name">{company_name}</div>
                <p style="color: #6b7280; margin: 0;">is inviting you to set up your account</p>
            </div>

            <div class="steps">
                <div class="step">
                    <div class="step-number">1</div>
                    <div>Click the button below to get started</div>
                </div>
                <div class="step">
                    <div class="step-number">2</div>
                    <div>Create your password</div>
                </div>
                <div class="step">
                    <div class="step-number">3</div>
                    <div>Access your employee portal</div>
                </div>
            </div>

            <p style="text-align: center;">
                <a href="{invitation_url}" class="btn">Set Up My Account</a>
            </p>

            <p style="color: #6b7280; font-size: 14px; text-align: center;">
                This invitation expires on {expires_at.strftime('%B %d, %Y at %I:%M %p')}.
            </p>

            <p style="color: #6b7280; font-size: 14px;">
                If you weren't expecting this invitation or have questions, please contact your HR administrator.
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

Welcome! You've been invited to join the employee portal at {company_name}.

To set up your account, please visit:
{invitation_url}

This invitation expires on {expires_at.strftime('%B %d, %Y at %I:%M %p')}.

If you weren't expecting this invitation, please contact your HR administrator.

- Matcha Recruit
"""

        return await self.send_email(
            to_email=to_email,
            to_name=to_name,
            subject=f"Welcome to {company_name} - Set Up Your Account",
            html_content=html_content,
            text_content=text_content,
        )


    async def send_employee_welcome_email(
        self,
        to_email: str,
        to_name: str,
        company_name: str,
        login_email: str,
    ) -> bool:
        """Send a getting-started welcome email to the employee's work email after they accept their invitation.

        Explains how to log in and what they can do in the Matcha employee portal.
        Returns True if sent successfully, False otherwise.
        """
        if not self.is_configured():
            logger.warning("Gmail not configured, skipping employee welcome email")
            return False

        app_base_url = self.settings.app_base_url
        portal_url = f"{app_base_url}/app/portal"
        login_url = f"{app_base_url}/login"

        html_content = f"""
<!DOCTYPE html>
<html>
<head>
    <style>
        body {{ font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif; line-height: 1.6; color: #333; margin: 0; padding: 0; }}
        .container {{ max-width: 600px; margin: 0 auto; padding: 20px; }}
        .header {{ text-align: center; padding: 20px 0; border-bottom: 2px solid #22c55e; }}
        .logo {{ color: #22c55e; font-size: 24px; font-weight: bold; letter-spacing: 2px; }}
        .content {{ padding: 30px 0; }}
        .hero {{ background: linear-gradient(135deg, #052e16 0%, #14532d 100%); border-radius: 12px; padding: 30px; margin: 20px 0; text-align: center; color: white; }}
        .hero-title {{ font-size: 22px; font-weight: 700; margin-bottom: 6px; }}
        .hero-sub {{ font-size: 14px; color: #86efac; margin: 0; }}
        .btn {{ display: inline-block; background: #22c55e; color: white !important; padding: 14px 28px; text-decoration: none; border-radius: 8px; font-weight: 600; margin: 20px 0; font-size: 15px; }}
        .login-box {{ background: #f9fafb; border: 1px solid #e5e7eb; border-radius: 8px; padding: 16px 20px; margin: 20px 0; font-size: 13px; }}
        .login-box strong {{ display: block; margin-bottom: 4px; color: #111; }}
        .login-box code {{ background: #e5e7eb; padding: 2px 6px; border-radius: 4px; font-size: 13px; }}
        .features {{ margin: 24px 0; }}
        .feature-row {{ display: flex; align-items: flex-start; margin-bottom: 14px; }}
        .feature-icon {{ font-size: 20px; margin-right: 14px; flex-shrink: 0; width: 28px; text-align: center; }}
        .feature-title {{ font-weight: 600; color: #111; font-size: 14px; }}
        .feature-desc {{ color: #6b7280; font-size: 13px; margin: 2px 0 0 0; }}
        .divider {{ border: none; border-top: 1px solid #e5e7eb; margin: 24px 0; }}
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
            <p>Your account at <strong>{company_name}</strong> is ready. Here's everything you can do in your employee portal.</p>

            <div class="hero">
                <div class="hero-title">Welcome to {company_name}</div>
                <div class="hero-sub">Your employee portal is live</div>
            </div>

            <div class="login-box">
                <strong>Log in at:</strong>
                <a href="{login_url}">{login_url}</a><br><br>
                <strong>Your login email:</strong>
                <code>{login_email}</code>
            </div>

            <p style="text-align: center;">
                <a href="{portal_url}" class="btn">Open My Portal</a>
            </p>

            <hr class="divider">

            <p style="font-weight: 600; font-size: 15px; margin-bottom: 16px;">What you can do in Matcha:</p>

            <div class="features">
                <div class="feature-row">
                    <div class="feature-icon">✅</div>
                    <div>
                        <div class="feature-title">Complete your onboarding</div>
                        <p class="feature-desc">Finish any pending tasks, sign documents, and get set up from day one.</p>
                    </div>
                </div>
                <div class="feature-row">
                    <div class="feature-icon">🏖️</div>
                    <div>
                        <div class="feature-title">Request time off</div>
                        <p class="feature-desc">Submit PTO requests, view your balance, and track approvals in one place.</p>
                    </div>
                </div>
                <div class="feature-row">
                    <div class="feature-icon">📋</div>
                    <div>
                        <div class="feature-title">View company policies</div>
                        <p class="feature-desc">Read and acknowledge company policies, handbooks, and compliance docs.</p>
                    </div>
                </div>
                <div class="feature-row">
                    <div class="feature-icon">🚨</div>
                    <div>
                        <div class="feature-title">Submit incident reports</div>
                        <p class="feature-desc">Report workplace incidents or safety concerns quickly and confidentially.</p>
                    </div>
                </div>
            </div>

            <hr class="divider">

            <p style="color: #6b7280; font-size: 13px;">
                Questions? Reach out to your HR administrator or reply to this email.
            </p>
        </div>
        <div class="footer">
            <p>Sent via Matcha Recruit &mdash; {company_name}</p>
        </div>
    </div>
</body>
</html>
"""

        text_content = f"""Hi {to_name},

Your account at {company_name} is ready. Log in to your employee portal to get started.

Log in at: {login_url}
Your login email: {login_email}

Portal: {portal_url}

What you can do in Matcha:
- Complete your onboarding tasks and sign documents
- Request time off and track your PTO balance
- View and acknowledge company policies
- Submit incident reports

Questions? Contact your HR administrator.

- Matcha Recruit / {company_name}
"""

        return await self.send_email(
            to_email=to_email,
            to_name=to_name,
            subject=f"You're all set — welcome to {company_name}",
            html_content=html_content,
            text_content=text_content,
        )

    async def send_task_reminder(
        self,
        to_email: str,
        to_name: str,
        company_name: str,
        employee_name: str,
        task_title: str,
        due_date: date,
    ) -> bool:
        """Send a standard onboarding task reminder email."""
        if not self.is_configured():
            logger.warning("MailerSend not configured, skipping onboarding reminder email")
            return False

        app_base_url = self.settings.app_base_url
        portal_url = f"{app_base_url}/app/portal"
        due_text = due_date.strftime("%B %d, %Y")

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
        .card {{ background: #f9fafb; border-radius: 10px; padding: 20px; margin: 20px 0; }}
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
            <p>This is a reminder to complete an onboarding task for <strong>{employee_name}</strong>.</p>

            <div class="card">
                <p style="margin: 0;"><strong>Task:</strong> {task_title}</p>
                <p style="margin: 8px 0 0 0;"><strong>Due date:</strong> {due_text}</p>
            </div>

            <p>
                <a href="{portal_url}" class="btn">Open Onboarding Portal</a>
            </p>
        </div>
        <div class="footer">
            <p>Sent via Matcha Recruit — {company_name}</p>
        </div>
    </div>
</body>
</html>
"""

        text_content = f"""
Hi {to_name},

This is a reminder to complete an onboarding task for {employee_name}.

Task: {task_title}
Due date: {due_text}

Open onboarding portal: {portal_url}

- Matcha Recruit / {company_name}
"""

        payload = {
            "from": {"email": self.from_email, "name": self.from_name},
            "to": [{"email": to_email, "name": to_name or to_email}],
            "subject": f"Onboarding reminder: {task_title}",
            "html": html_content,
            "text": text_content,
        }

        try:
            async with httpx.AsyncClient() as client:
                response = await client.post(
                    f"{self.base_url}/email",
                    json=payload,
                    headers={
                        "Authorization": f"Bearer {self.api_key}",
                        "Content-Type": "application/json",
                    },
                    timeout=30.0,
                )
                if response.status_code in (200, 201, 202):
                    logger.info("Sent onboarding reminder to %s", to_email)
                    return True
                logger.warning("Failed onboarding reminder to %s: %s - %s", to_email, response.status_code, response.text[:200])
                return False
        except Exception as e:
            logger.exception("Error sending onboarding reminder to %s", to_email)
            return False

    async def send_task_completion_notification(
        self,
        to_email: str,
        to_name: str,
        company_name: str,
        employee_name: str,
        task_title: str,
    ) -> bool:
        """Send a notification email when an onboarding task is completed."""
        if not self.is_configured():
            logger.warning("MailerSend not configured, skipping task completion notification")
            return False

        app_base_url = self.settings.app_base_url
        portal_url = f"{app_base_url}/app/onboarding"

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
        .card {{ background: #f0fdf4; border-radius: 10px; padding: 20px; margin: 20px 0; border-left: 4px solid #22c55e; }}
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
            <p><strong>{employee_name}</strong> has completed an onboarding task.</p>

            <div class="card">
                <p style="margin: 0;"><strong>Task:</strong> {task_title}</p>
                <p style="margin: 8px 0 0 0;">Status: Completed</p>
            </div>

            <p>
                <a href="{portal_url}" class="btn">View Onboarding Dashboard</a>
            </p>
        </div>
        <div class="footer">
            <p>Sent via Matcha Recruit &mdash; {company_name}</p>
        </div>
    </div>
</body>
</html>
"""

        text_content = f"""
Hi {to_name},

{employee_name} has completed an onboarding task.

Task: {task_title}
Status: Completed

View onboarding dashboard: {portal_url}

- Matcha Recruit / {company_name}
"""

        payload = {
            "from": {"email": self.from_email, "name": self.from_name},
            "to": [{"email": to_email, "name": to_name or to_email}],
            "subject": f"[{company_name}] Onboarding task completed \u2014 {employee_name}",
            "html": html_content,
            "text": text_content,
        }

        try:
            async with httpx.AsyncClient() as client:
                response = await client.post(
                    f"{self.base_url}/email",
                    json=payload,
                    headers={
                        "Authorization": f"Bearer {self.api_key}",
                        "Content-Type": "application/json",
                    },
                    timeout=30.0,
                )
                if response.status_code in (200, 201, 202):
                    logger.info("Sent task completion notification to %s", to_email)
                    return True
                logger.warning("Failed task completion notification to %s: %s - %s", to_email, response.status_code, response.text[:200])
                return False
        except Exception as e:
            logger.exception("Error sending task completion notification to %s", to_email)
            return False

    async def send_task_escalation(
        self,
        to_email: str,
        to_name: str,
        company_name: str,
        employee_name: str,
        task_title: str,
        due_date: date,
        escalation_target: str,
        overdue_days: int,
    ) -> bool:
        """Send an onboarding escalation email for overdue tasks."""
        if not self.is_configured():
            logger.warning("MailerSend not configured, skipping onboarding escalation email")
            return False

        app_base_url = self.settings.app_base_url
        portal_url = f"{app_base_url}/app/onboarding"
        due_text = due_date.strftime("%B %d, %Y")
        escalation_label = "Manager" if escalation_target == "manager" else "HR"

        html_content = f"""
<!DOCTYPE html>
<html>
<head>
    <style>
        body {{ font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif; line-height: 1.6; color: #333; }}
        .container {{ max-width: 600px; margin: 0 auto; padding: 20px; }}
        .header {{ text-align: center; padding: 20px 0; border-bottom: 2px solid #ef4444; }}
        .logo {{ color: #22c55e; font-size: 24px; font-weight: bold; letter-spacing: 2px; }}
        .content {{ padding: 30px 0; }}
        .alert {{ background: #fef2f2; border-left: 4px solid #ef4444; border-radius: 6px; padding: 16px; margin: 20px 0; }}
        .btn {{ display: inline-block; background: #ef4444; color: white; padding: 12px 22px; text-decoration: none; border-radius: 6px; font-weight: 600; }}
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
            <p>An onboarding task for <strong>{employee_name}</strong> has been escalated to {escalation_label} follow-up.</p>

            <div class="alert">
                <p style="margin: 0;"><strong>Task:</strong> {task_title}</p>
                <p style="margin: 8px 0 0 0;"><strong>Due date:</strong> {due_text}</p>
                <p style="margin: 8px 0 0 0;"><strong>Overdue by:</strong> {overdue_days} day(s)</p>
            </div>

            <p>
                <a href="{portal_url}" class="btn">Review Onboarding Status</a>
            </p>
        </div>
        <div class="footer">
            <p>Sent via Matcha Recruit — {company_name}</p>
        </div>
    </div>
</body>
</html>
"""

        text_content = f"""
Hi {to_name},

An onboarding task for {employee_name} has been escalated to {escalation_label} follow-up.

Task: {task_title}
Due date: {due_text}
Overdue by: {overdue_days} day(s)

Review onboarding status: {portal_url}

- Matcha Recruit / {company_name}
"""

        payload = {
            "from": {"email": self.from_email, "name": self.from_name},
            "to": [{"email": to_email, "name": to_name or to_email}],
            "subject": f"Onboarding escalation ({escalation_label}): {task_title}",
            "html": html_content,
            "text": text_content,
        }

        try:
            async with httpx.AsyncClient() as client:
                response = await client.post(
                    f"{self.base_url}/email",
                    json=payload,
                    headers={
                        "Authorization": f"Bearer {self.api_key}",
                        "Content-Type": "application/json",
                    },
                    timeout=30.0,
                )
                if response.status_code in (200, 201, 202):
                    logger.info("Sent onboarding escalation to %s", to_email)
                    return True
                logger.warning("Failed onboarding escalation to %s: %s - %s", to_email, response.status_code, response.text[:200])
                return False
        except Exception as e:
            logger.exception("Error sending onboarding escalation to %s", to_email)
            return False

    async def send_manager_onboarding_summary(
        self,
        to_email: str,
        to_name: str,
        company_name: str,
        summary_lines: list[str],
    ) -> bool:
        """Send a weekly manager summary of onboarding items."""
        if not self.is_configured():
            logger.warning("MailerSend not configured, skipping manager onboarding summary email")
            return False

        app_base_url = self.settings.app_base_url
        portal_url = f"{app_base_url}/app/onboarding"
        bullet_items = "".join([f"<li>{line}</li>" for line in summary_lines]) if summary_lines else "<li>No pending items this week.</li>"
        text_bullets = "\n".join([f"- {line}" for line in summary_lines]) if summary_lines else "- No pending items this week."

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
        .card {{ background: #f9fafb; border-radius: 10px; padding: 20px; margin: 20px 0; }}
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
            <p>Here is your weekly onboarding summary for {company_name}.</p>
            <div class="card">
                <ul>{bullet_items}</ul>
            </div>
            <p>
                <a href="{portal_url}" class="btn">Open Onboarding Dashboard</a>
            </p>
        </div>
        <div class="footer">
            <p>Sent via Matcha Recruit — {company_name}</p>
        </div>
    </div>
</body>
</html>
"""

        text_content = f"""
Hi {to_name},

Here is your weekly onboarding summary for {company_name}.

{text_bullets}

Open onboarding dashboard: {portal_url}

- Matcha Recruit / {company_name}
"""

        payload = {
            "from": {"email": self.from_email, "name": self.from_name},
            "to": [{"email": to_email, "name": to_name or to_email}],
            "subject": f"Weekly onboarding summary — {company_name}",
            "html": html_content,
            "text": text_content,
        }

        try:
            async with httpx.AsyncClient() as client:
                response = await client.post(
                    f"{self.base_url}/email",
                    json=payload,
                    headers={
                        "Authorization": f"Bearer {self.api_key}",
                        "Content-Type": "application/json",
                    },
                    timeout=30.0,
                )
                if response.status_code in (200, 201, 202):
                    logger.info("Sent manager onboarding summary to %s", to_email)
                    return True
                logger.warning("Failed manager onboarding summary to %s: %s - %s", to_email, response.status_code, response.text[:200])
                return False
        except Exception as e:
            logger.exception("Error sending manager onboarding summary to %s", to_email)
            return False


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

        payload = {
            "from": {
                "email": self.from_email,
                "name": self.from_name,
            },
            "to": [
                {
                    "email": to_email,
                    "name": recipient_name,
                }
            ],
            "subject": f"{company_name}: Compliance update available",
            "html": html_content,
            "text": text_content,
        }

        try:
            async with httpx.AsyncClient() as client:
                response = await client.post(
                    f"{self.base_url}/email",
                    json=payload,
                    headers={
                        "Authorization": f"Bearer {self.api_key}",
                        "Content-Type": "application/json",
                    },
                    timeout=30.0,
                )

                if response.status_code in (200, 201, 202):
                    logger.info("Sent compliance change notification to %s", to_email)
                    return True
                else:
                    logger.warning("Failed to send to %s: %s - %s", to_email, response.status_code, response.text[:200])
                    return False

        except Exception as e:
            logger.exception("Error sending to %s", to_email)
            return False

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

        payload = {
            "from": {
                "email": self.from_email,
                "name": self.from_name,
            },
            "to": [
                {
                    "email": to_email,
                    "name": recipient_name,
                }
            ],
            "subject": subject,
            "html": html_content,
            "text": text_content,
        }

        try:
            async with httpx.AsyncClient() as client:
                response = await client.post(
                    f"{self.base_url}/email",
                    json=payload,
                    headers={
                        "Authorization": f"Bearer {self.api_key}",
                        "Content-Type": "application/json",
                    },
                    timeout=30.0,
                )

                if response.status_code in (200, 201, 202):
                    logger.info("Sent IR notification to %s", to_email)
                    return True
                else:
                    logger.warning("Failed to send to %s: %s - %s", to_email, response.status_code, response.text[:200])
                    return False

        except Exception as e:
            logger.exception("Error sending to %s", to_email)
            return False

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

        payload = {
            "from": {
                "email": self.from_email,
                "name": self.from_name,
            },
            "to": [
                {
                    "email": to_email,
                    "name": recipient_name,
                }
            ],
            "subject": subject,
            "html": html_content,
            "text": text_content,
        }

        try:
            async with httpx.AsyncClient() as client:
                response = await client.post(
                    f"{self.base_url}/email",
                    json=payload,
                    headers={
                        "Authorization": f"Bearer {self.api_key}",
                        "Content-Type": "application/json",
                    },
                    timeout=30.0,
                )

                if response.status_code in (200, 201, 202):
                    logger.info("Sent leave notification to %s", to_email)
                    return True
                else:
                    logger.warning("Failed to send to %s: %s - %s", to_email, response.status_code, response.text[:200])
                    return False

        except Exception as e:
            logger.exception("Error sending to %s", to_email)
            return False

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

        payload = {
            "from": {
                "email": self.from_email,
                "name": self.from_name,
            },
            "to": [
                {
                    "email": to_email,
                    "name": recipient_name,
                }
            ],
            "subject": subject,
            "html": html_content,
            "text": text_content,
        }

        try:
            async with httpx.AsyncClient() as client:
                response = await client.post(
                    f"{self.base_url}/email",
                    json=payload,
                    headers={
                        "Authorization": f"Bearer {self.api_key}",
                        "Content-Type": "application/json",
                    },
                    timeout=30.0,
                )

                if response.status_code in (200, 201, 202):
                    logger.info("Sent accommodation notification to %s", to_email)
                    return True
                else:
                    logger.warning("Failed to send to %s: %s - %s", to_email, response.status_code, response.text[:200])
                    return False

        except Exception as e:
            logger.exception("Error sending to %s", to_email)
            return False


    async def send_business_registration_pending_email(
        self,
        to_email: str,
        to_name: str,
        company_name: str,
    ) -> bool:
        """Send an email confirming business registration is pending review.

        Returns True if sent successfully, False otherwise.
        """
        if not self.is_configured():
            logger.warning("Gmail not configured, skipping email send")
            return False

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
        .status-card {{ background: linear-gradient(135deg, #fef3c7 0%, #fef9c3 100%); border-radius: 12px; padding: 30px; margin: 20px 0; text-align: center; border-left: 4px solid #f59e0b; }}
        .status-icon {{ font-size: 48px; margin-bottom: 10px; }}
        .company-name {{ font-size: 24px; font-weight: 700; color: #111; margin-bottom: 8px; }}
        .info-box {{ background: #f9fafb; border-radius: 8px; padding: 20px; margin: 20px 0; }}
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

            <p>Thank you for registering <strong>{company_name}</strong> with Matcha!</p>

            <div class="status-card">
                <div class="status-icon">⏳</div>
                <div class="company-name">{company_name}</div>
                <p style="color: #92400e; margin: 0;">Registration Pending Review</p>
            </div>

            <div class="info-box">
                <h3 style="margin-top: 0;">What happens next?</h3>
                <ul style="margin: 0; padding-left: 20px;">
                    <li>Our team will review your registration within 1-2 business days</li>
                    <li>You'll receive an email once your account is approved</li>
                    <li>Once approved, you'll have full access to all Matcha features</li>
                </ul>
            </div>

            <p>In the meantime, you can log in to see your pending status. If you have any questions, feel free to reach out to our support team.</p>
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

Thank you for registering {company_name} with Matcha!

Your business registration is currently pending review.

What happens next?
- Our team will review your registration within 1-2 business days
- You'll receive an email once your account is approved
- Once approved, you'll have full access to all Matcha features

In the meantime, you can log in to see your pending status. If you have any questions, feel free to reach out to our support team.

- Matcha Recruit
"""

        payload = {
            "from": {
                "email": self.from_email,
                "name": self.from_name,
            },
            "to": [
                {
                    "email": to_email,
                    "name": to_name,
                }
            ],
            "subject": f"Registration Pending: {company_name}",
            "html": html_content,
            "text": text_content,
        }

        try:
            async with httpx.AsyncClient() as client:
                response = await client.post(
                    f"{self.base_url}/email",
                    json=payload,
                    headers={
                        "Authorization": f"Bearer {self.api_key}",
                        "Content-Type": "application/json",
                    },
                    timeout=30.0,
                )

                if response.status_code in (200, 201, 202):
                    logger.info("Sent business registration pending email to %s", to_email)
                    return True
                else:
                    logger.warning("Failed to send to %s: %s - %s", to_email, response.status_code, response.text[:200])
                    return False

        except Exception as e:
            logger.exception("Error sending to %s", to_email)
            return False

    async def send_business_approved_email(
        self,
        to_email: str,
        to_name: str,
        company_name: str,
    ) -> bool:
        """Send an email notifying that business registration was approved.

        Returns True if sent successfully, False otherwise.
        """
        if not self.is_configured():
            logger.warning("Gmail not configured, skipping email send")
            return False

        app_base_url = self.settings.app_base_url
        dashboard_url = f"{app_base_url}/app"

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
        .status-card {{ background: linear-gradient(135deg, #ecfdf5 0%, #d1fae5 100%); border-radius: 12px; padding: 30px; margin: 20px 0; text-align: center; border-left: 4px solid #22c55e; }}
        .status-icon {{ font-size: 48px; margin-bottom: 10px; }}
        .company-name {{ font-size: 24px; font-weight: 700; color: #111; margin-bottom: 8px; }}
        .btn {{ display: inline-block; background: #22c55e; color: white; padding: 16px 32px; text-decoration: none; border-radius: 8px; font-weight: 600; margin: 20px 0; font-size: 16px; }}
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

            <p>Great news! Your business registration has been approved.</p>

            <div class="status-card">
                <div class="status-icon">✅</div>
                <div class="company-name">{company_name}</div>
                <p style="color: #166534; margin: 0;">Registration Approved!</p>
            </div>

            <p>You now have full access to all Matcha features:</p>
            <ul>
                <li>AI-powered candidate screening</li>
                <li>Employee management tools</li>
                <li>HR compliance features</li>
                <li>And much more!</li>
            </ul>

            <p style="text-align: center;">
                <a href="{dashboard_url}" class="btn">Go to Dashboard</a>
            </p>

            <p>Welcome to Matcha! We're excited to have you on board.</p>
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

Great news! Your business registration has been approved.

{company_name} - Registration Approved!

You now have full access to all Matcha features:
- AI-powered candidate screening
- Employee management tools
- HR compliance features
- And much more!

Go to your dashboard: {dashboard_url}

Welcome to Matcha! We're excited to have you on board.

- Matcha Recruit
"""

        payload = {
            "from": {
                "email": self.from_email,
                "name": self.from_name,
            },
            "to": [
                {
                    "email": to_email,
                    "name": to_name,
                }
            ],
            "subject": f"Welcome to Matcha! {company_name} is Approved",
            "html": html_content,
            "text": text_content,
        }

        try:
            async with httpx.AsyncClient() as client:
                response = await client.post(
                    f"{self.base_url}/email",
                    json=payload,
                    headers={
                        "Authorization": f"Bearer {self.api_key}",
                        "Content-Type": "application/json",
                    },
                    timeout=30.0,
                )

                if response.status_code in (200, 201, 202):
                    logger.info("Sent business approved email to %s", to_email)
                    return True
                else:
                    logger.warning("Failed to send to %s: %s - %s", to_email, response.status_code, response.text[:200])
                    return False

        except Exception as e:
            logger.exception("Error sending to %s", to_email)
            return False

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

        payload = {
            "from": {
                "email": self.from_email,
                "name": from_name or self.from_name,
            },
            "to": [
                {
                    "email": to_email,
                    "name": to_name,
                }
            ],
            "subject": subject,
            "html": html_content,
            "text": body,
        }

        try:
            async with httpx.AsyncClient() as client:
                response = await client.post(
                    f"{self.base_url}/email",
                    json=payload,
                    headers={
                        "Authorization": f"Bearer {self.api_key}",
                        "Content-Type": "application/json",
                    },
                    timeout=30.0,
                )

                if response.status_code in (200, 201, 202):
                    logger.info("Sent reach-out email to %s", to_email)
                    return True
                else:
                    logger.warning("Failed to send to %s: %s - %s", to_email, response.status_code, response.text[:200])
                    return False

        except Exception as e:
            logger.exception("Error sending to %s", to_email)
            return False

    async def send_business_rejected_email(
        self,
        to_email: str,
        to_name: str,
        company_name: str,
        reason: str,
    ) -> bool:
        """Send an email notifying that business registration was rejected.

        Returns True if sent successfully, False otherwise.
        """
        if not self.is_configured():
            logger.warning("Gmail not configured, skipping email send")
            return False

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
        .status-card {{ background: linear-gradient(135deg, #fef2f2 0%, #fee2e2 100%); border-radius: 12px; padding: 30px; margin: 20px 0; text-align: center; border-left: 4px solid #ef4444; }}
        .status-icon {{ font-size: 48px; margin-bottom: 10px; }}
        .company-name {{ font-size: 24px; font-weight: 700; color: #111; margin-bottom: 8px; }}
        .reason-box {{ background: #f9fafb; border-radius: 8px; padding: 20px; margin: 20px 0; border-left: 4px solid #6b7280; }}
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

            <p>We've reviewed your business registration and unfortunately, we're unable to approve it at this time.</p>

            <div class="status-card">
                <div class="status-icon">❌</div>
                <div class="company-name">{company_name}</div>
                <p style="color: #991b1b; margin: 0;">Registration Not Approved</p>
            </div>

            <div class="reason-box">
                <h4 style="margin-top: 0; color: #374151;">Reason:</h4>
                <p style="margin-bottom: 0;">{reason}</p>
            </div>

            <p>If you believe this was a mistake or have additional information to provide, please contact our support team at <a href="mailto:support@hey-matcha.com">support@hey-matcha.com</a>.</p>
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

We've reviewed your business registration and unfortunately, we're unable to approve it at this time.

{company_name} - Registration Not Approved

Reason:
{reason}

If you believe this was a mistake or have additional information to provide, please contact our support team at support@hey-matcha.com.

- Matcha Recruit
"""

        payload = {
            "from": {
                "email": self.from_email,
                "name": self.from_name,
            },
            "to": [
                {
                    "email": to_email,
                    "name": to_name,
                }
            ],
            "subject": f"Registration Update: {company_name}",
            "html": html_content,
            "text": text_content,
        }

        try:
            async with httpx.AsyncClient() as client:
                response = await client.post(
                    f"{self.base_url}/email",
                    json=payload,
                    headers={
                        "Authorization": f"Bearer {self.api_key}",
                        "Content-Type": "application/json",
                    },
                    timeout=30.0,
                )

                if response.status_code in (200, 201, 202):
                    logger.info("Sent business rejected email to %s", to_email)
                    return True
                else:
                    logger.warning("Failed to send to %s: %s - %s", to_email, response.status_code, response.text[:200])
                    return False

        except Exception as e:
            logger.exception("Error sending to %s", to_email)
            return False


    async def send_admin_interview_invitation_email(
        self,
        candidate_email: str,
        candidate_name: Optional[str],
        company_name: str,
        position_title: str,
    ) -> bool:
        """Send an admin interview invitation to a top-ranked candidate.

        This email goes to the top 3 candidates after project closes and ranking is complete.
        It congratulates them and lets them know the hiring team will reach out personally.

        Returns True if sent successfully, False otherwise.
        """
        if not self.is_configured():
            logger.warning("Gmail not configured, skipping email send")
            return False

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
        .highlight {{ background: #ecfdf5; border-left: 4px solid #22c55e; padding: 15px; margin: 20px 0; border-radius: 0 6px 6px 0; }}
        .footer {{ text-align: center; padding-top: 20px; border-top: 1px solid #e5e7eb; color: #6b7280; font-size: 12px; }}
    </style>
</head>
<body>
    <div class="container">
        <div class="header">
            <div class="logo">MATCHA</div>
        </div>
        <div class="content">
            <p>Hi{' ' + candidate_name if candidate_name else ''},</p>

            <p>Congratulations — you've been selected as a <strong>top candidate</strong> for the following role:</p>

            <div class="role-card">
                <h2 style="margin-top: 0; color: #111;">{position_title}</h2>
                <p><strong>Company:</strong> {company_name}</p>
            </div>

            <div class="highlight">
                <strong>What's next:</strong> A member of the hiring team will be reaching out to you directly to schedule a personal interview. Please keep an eye on your inbox.
            </div>

            <p>Thank you for going through our process — we were impressed by your background and look forward to speaking with you.</p>
        </div>
        <div class="footer">
            <p>Sent via Matcha Recruit</p>
        </div>
    </div>
</body>
</html>
"""

        text_content = f"""Hi{' ' + candidate_name if candidate_name else ''},

Congratulations — you've been selected as a top candidate for:

{position_title} at {company_name}

What's next: A member of the hiring team will be reaching out to you directly to schedule a personal interview. Please keep an eye on your inbox.

Thank you for going through our process — we were impressed by your background and look forward to speaking with you.

- Matcha Recruit
"""

        payload = {
            "from": {
                "email": self.from_email,
                "name": self.from_name,
            },
            "to": [
                {
                    "email": candidate_email,
                    "name": candidate_name or candidate_email,
                }
            ],
            "subject": f"You're a top candidate: {position_title} at {company_name}",
            "html": html_content,
            "text": text_content,
        }

        try:
            async with httpx.AsyncClient() as client:
                response = await client.post(
                    f"{self.base_url}/email",
                    json=payload,
                    headers={
                        "Authorization": f"Bearer {self.api_key}",
                        "Content-Type": "application/json",
                    },
                    timeout=30.0,
                )

                if response.status_code in (200, 201, 202):
                    logger.info("Sent admin interview invitation to %s", candidate_email)
                    return True
                else:
                    logger.warning("Failed to send to %s: %s - %s", candidate_email, response.status_code, response.text[:200])
                    return False

        except Exception as e:
            logger.exception("Error sending to %s", candidate_email)
            return False


    async def send_provisioning_welcome_email(
        self,
        to_email: str,
        to_name: str,
        company_name: str,
        work_email: Optional[str] = None,
        temp_password: Optional[str] = None,
        slack_workspace_name: Optional[str] = None,
        slack_invite_link: Optional[str] = None,
    ) -> bool:
        """Send a welcome email to a new employee with their provisioned credentials.

        Sent to the employee's personal email with their new work email,
        temporary password, and Slack invite info.
        """
        if not self.is_configured():
            logger.warning("MailerSend not configured, skipping provisioning welcome email")
            return False

        # Build credential sections
        google_section_html = ""
        google_section_text = ""
        if work_email:
            password_html = ""
            password_text = ""
            if temp_password:
                password_html = f"""
                    <div style="margin-top: 12px;">
                        <div style="font-weight: 600; color: #6b7280; font-size: 12px; text-transform: uppercase; letter-spacing: 1px;">Temporary Password</div>
                        <div style="margin-top: 4px; font-family: monospace; font-size: 16px; background: #fff; border: 1px solid #e5e7eb; border-radius: 4px; padding: 8px 12px; display: inline-block;">{temp_password}</div>
                        <div style="margin-top: 8px; color: #dc2626; font-size: 13px;">You will be asked to change this password on your first login.</div>
                    </div>"""
                password_text = f"\nTemporary Password: {temp_password}\n(You will be asked to change this on first login.)"

            google_section_html = f"""
            <div style="background: #f0fdf4; border: 1px solid #bbf7d0; border-radius: 8px; padding: 20px; margin: 20px 0;">
                <h3 style="margin: 0 0 12px 0; color: #166534;">Google Workspace Account</h3>
                <div>
                    <div style="font-weight: 600; color: #6b7280; font-size: 12px; text-transform: uppercase; letter-spacing: 1px;">Work Email</div>
                    <div style="margin-top: 4px; font-size: 16px; color: #111;">{work_email}</div>
                </div>{password_html}
                <div style="margin-top: 16px;">
                    <a href="https://accounts.google.com" style="display: inline-block; background: #22c55e; color: white; padding: 10px 20px; text-decoration: none; border-radius: 6px; font-weight: 600; font-size: 14px;">Sign in to Google Workspace</a>
                </div>
            </div>"""
            google_section_text = f"""
Google Workspace Account
------------------------
Work Email: {work_email}{password_text}
Sign in: https://accounts.google.com
"""

        slack_section_html = ""
        slack_section_text = ""
        if slack_workspace_name and slack_invite_link:
            slack_section_html = f"""
            <div style="background: #faf5ff; border: 1px solid #e9d5ff; border-radius: 8px; padding: 20px; margin: 20px 0;">
                <h3 style="margin: 0 0 12px 0; color: #7c3aed;">Slack Workspace</h3>
                <div>
                    <div style="font-weight: 600; color: #6b7280; font-size: 12px; text-transform: uppercase; letter-spacing: 1px;">Workspace</div>
                    <div style="margin-top: 4px; font-size: 16px; color: #111;">{slack_workspace_name}</div>
                </div>
                <div style="margin-top: 16px;">
                    <a href="{slack_invite_link}" style="display: inline-block; background: #7c3aed; color: white; padding: 10px 20px; text-decoration: none; border-radius: 6px; font-weight: 600; font-size: 14px;">Join Slack Workspace</a>
                </div>
            </div>"""
            slack_section_text = f"""
Slack Workspace
---------------
Workspace: {slack_workspace_name}
Join here: {slack_invite_link}
"""

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
    </style>
</head>
<body>
    <div class="container">
        <div class="header">
            <div class="logo">MATCHA</div>
        </div>
        <div class="content">
            <p>Hi {to_name},</p>

            <p>Welcome to <strong>{company_name}</strong>! Your accounts have been set up and are ready to go.</p>

            {google_section_html}
            {slack_section_html}

            <p style="color: #6b7280; font-size: 14px; margin-top: 24px;">If you have any questions about getting started, reach out to your manager or HR team.</p>
        </div>
        <div class="footer">
            <p>Sent via Matcha Recruit</p>
        </div>
    </div>
</body>
</html>
"""

        text_content = f"""Hi {to_name},

Welcome to {company_name}! Your accounts have been set up and are ready to go.
{google_section_text}{slack_section_text}
If you have any questions about getting started, reach out to your manager or HR team.

- Matcha Recruit
"""

        return await self.send_email(
            to_email=to_email,
            to_name=to_name,
            subject=f"Welcome to {company_name} — Your account credentials",
            html_content=html_content,
            text_content=text_content,
        )


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


# Singleton instance
_email_service: Optional[EmailService] = None


def get_email_service() -> EmailService:
    """Get the email service singleton."""
    global _email_service
    if _email_service is None:
        _email_service = EmailService()
    return _email_service
