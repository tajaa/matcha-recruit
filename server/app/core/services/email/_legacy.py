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
from .candidate import CandidateEmailMixin
from .compliance import ComplianceEmailMixin
from .training import TrainingEmailMixin


class EmailService(
    AuthEmailMixin,
    EmployeeEmailMixin,
    CandidateEmailMixin,
    ComplianceEmailMixin,
    TrainingEmailMixin,
):
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

# Singleton instance
_email_service: Optional[EmailService] = None


def get_email_service() -> EmailService:
    """Get the email service singleton."""
    global _email_service
    if _email_service is None:
        _email_service = EmailService()
    return _email_service
