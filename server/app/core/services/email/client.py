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
from .misc import MiscEmailMixin


class EmailService(
    AuthEmailMixin,
    EmployeeEmailMixin,
    CandidateEmailMixin,
    ComplianceEmailMixin,
    TrainingEmailMixin,
    MiscEmailMixin,
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

    async def send_email_with_fallback(
        self,
        to_email: str,
        to_name: Optional[str],
        subject: str,
        html_content: str,
        text_content: Optional[str] = None,
    ) -> bool:
        """Public send wrapper: Gmail first, MailerSend on Gmail failure.

        Use this for transactional emails where reliability matters and
        the payload doesn't need Gmail-specific features (no `attachments`,
        no `extra_headers` like List-Unsubscribe — those require Gmail
        because MailerSend's basic JSON payload doesn't carry them).

        Same body as the legacy `_send_with_fallback` — kept under both
        names so existing internal callers in `email/auth.py` etc. keep
        working without churn.
        """
        return await self._send_with_fallback(
            to_email=to_email,
            to_name=to_name,
            subject=subject,
            html_content=html_content,
            text_content=text_content,
        )

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
                    logger.warning(
                        "MailerSend fallback failed for %s: status=%s from=%r body=%s",
                        to_email, response.status_code,
                        self.mailersend_from_email,
                        response.text[:500],
                    )
                    return False
        except Exception:
            logger.exception("MailerSend fallback error for %s", to_email)
            return False


# Singleton instance
_email_service: Optional[EmailService] = None


def get_email_service() -> EmailService:
    """Get the email service singleton."""
    global _email_service
    if _email_service is None:
        _email_service = EmailService()
    return _email_service
