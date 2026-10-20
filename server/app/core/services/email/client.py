"""Email service using Gmail API via OAuth2."""
import base64
import html
import httpx
import json
import logging
import re
from dataclasses import dataclass
from datetime import date, datetime
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from email.mime.base import MIMEBase
from email import encoders
from email.utils import formataddr
from pathlib import Path
from typing import Optional

from app.config import get_settings

logger = logging.getLogger(__name__)

GMAIL_TOKEN_URI = "https://oauth2.googleapis.com/token"
GMAIL_SEND_URI = "https://gmail.googleapis.com/gmail/v1/users/me/messages/send"

# A Reply-To is one plain address: no display name, no list, and nothing that
# could end the header (a CR/LF would let a stored value add headers of its own).
_REPLY_TO_RE = re.compile(r"[^@\s<>,;\"']{1,64}@[^@\s<>,;\"']{1,255}")


def clean_reply_to(value: Optional[str]) -> Optional[str]:
    """`value` as a Reply-To, or None when it isn't one plain address."""
    value = (value or "").strip()
    return value if value and _REPLY_TO_RE.fullmatch(value) else None

# Reserved-domain guard now lives in _shared.py. Re-imported here so the
# in-file `if _is_reserved_test_domain(to_email):` call sites still resolve.
from ._shared import (  # noqa: F401
    _is_reserved_test_domain,
    _RESERVED_EXAMPLE_DOMAINS,
    _RESERVED_TLDS,
)


@dataclass(frozen=True)
class SendResult:
    """What became of one send (`EmailService.send_with_result`): `sent`
    (accepted), `unknown` (the provider may have it, so it is never resent),
    `retry_wait` (certainly not sent; try later), `failed` or `suppressed`."""
    state: str
    provider: Optional[str] = None
    message_id: Optional[str] = None


def send_result(response: httpx.Response, provider: str) -> SendResult:
    """A provider's answer as a `SendResult`. Anything that may have been
    accepted (a 5xx, a timeout or conflict) is `unknown`, not a failure."""
    if 200 <= response.status_code < 300:
        message_id = response.headers.get("x-message-id")
        if provider == "gmail":
            try:
                message_id = response.json().get("id")
            except ValueError:
                pass  # Acceptance is authoritative even if the body is lost.
        return SendResult("sent", provider, message_id)
    if response.status_code >= 500 or response.status_code in (408, 409):
        return SendResult("unknown", provider)
    return SendResult("retry_wait" if response.status_code == 429 else "failed", provider)


from .auth import AuthEmailMixin
from .employee import EmployeeEmailMixin
from .candidate import CandidateEmailMixin
from .compliance import ComplianceEmailMixin
from .training import TrainingEmailMixin
from .misc import MiscEmailMixin
from .symlink import SymlinkEmailMixin


class EmailService(
    AuthEmailMixin,
    EmployeeEmailMixin,
    CandidateEmailMixin,
    ComplianceEmailMixin,
    TrainingEmailMixin,
    MiscEmailMixin,
    SymlinkEmailMixin,
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
        # MailerSend credentials (used by transactional emails)
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
        return self.is_gmail_configured()

    def is_gmail_configured(self) -> bool:
        """Whether the Gmail API backend specifically is usable. Callers that
        need Gmail-only features (e.g. attachments) must gate on this rather
        than `is_configured()` — the latter is True whenever MailerSend is set,
        which would let an attachment send through to a failing Gmail path."""
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

    def _mime_raw(
        self,
        to_email: str,
        to_name: Optional[str],
        subject: str,
        html_content: str,
        text_content: Optional[str] = None,
        attachments: Optional[list[dict]] = None,
        extra_headers: Optional[dict[str, str]] = None,
        from_name: Optional[str] = None,
    ) -> str:
        """The base64url RFC 822 message the Gmail API sends."""
        msg = MIMEMultipart("alternative") if not attachments else MIMEMultipart("mixed")
        msg["Subject"] = subject
        # formataddr quotes and RFC 2047-encodes the display name on its own;
        # a hand-built "<name> <addr>" with any non-ASCII character (a store
        # called "Café Lumen", a buyer called José) gets encoded whole,
        # address included, and the header no longer names an address.
        msg["From"] = formataddr((from_name or self.from_name or "", self.from_email))
        msg["To"] = formataddr((to_name, to_email)) if to_name else to_email
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

        return base64.urlsafe_b64encode(msg.as_bytes()).decode()

    def _mailersend_payload(
        self,
        to_email: str,
        to_name: Optional[str],
        subject: str,
        html_content: str,
        text_content: Optional[str] = None,
        attachments: Optional[list[dict]] = None,
        from_name: Optional[str] = None,
        reply_to: Optional[str] = None,
    ) -> dict:
        """The MailerSend `/email` request body."""
        payload = {
            "from": {"email": self.mailersend_from_email, "name": from_name or self.from_name},
            "to": [{"email": to_email, "name": to_name or to_email}],
            "subject": subject,
            "html": html_content,
            "text": text_content or "",
        }
        reply_to = clean_reply_to(reply_to)
        if reply_to:
            payload["reply_to"] = {"email": reply_to}
        if attachments:
            # MailerSend expects {content: <base64>, filename, disposition} —
            # same shape callers already build for the Gmail MIME path.
            payload["attachments"] = [
                {
                    "content": att["content"],
                    "filename": att["filename"],
                    "disposition": att.get("disposition", "attachment"),
                }
                for att in attachments
            ]
        return payload

    async def send_with_result(
        self,
        to_email: str,
        to_name: Optional[str],
        subject: str,
        html_content: str,
        text_content: Optional[str] = None,
        from_name: Optional[str] = None,
    ) -> "SendResult":
        """Gmail first, MailerSend only when Gmail certainly did not take it.

        `send_email_with_fallback` falls back on any Gmail failure, so a lost
        response can deliver twice. A caller with a durable outbox, which
        must never resend an email that may have gone, uses this instead and
        acts on the outcome (`SendResult`).
        """
        if _is_reserved_test_domain(to_email):
            logger.info("Skipping send to reserved test domain: %s", to_email)
            return SendResult("suppressed")
        gmail: Optional[SendResult] = None
        if self.is_gmail_configured():
            try:
                token = await self._get_access_token()
            except Exception:
                # No send request was made, so MailerSend cannot double it.
                logger.warning("Gmail token refresh failed for %s, trying MailerSend", to_email, exc_info=True)
                token = None
            if token:
                try:
                    raw = self._mime_raw(to_email, to_name, subject, html_content, text_content, from_name=from_name)
                except (ValueError, TypeError):
                    logger.warning("Email to %s could not be encoded", to_email, exc_info=True)
                    return SendResult("failed")
                try:
                    async with httpx.AsyncClient(timeout=20) as client:
                        gmail = send_result(await client.post(
                            GMAIL_SEND_URI, json={"raw": raw}, headers={"Authorization": f"Bearer {token}"},
                        ), "gmail")
                except (httpx.ConnectError, httpx.ConnectTimeout):
                    gmail = SendResult("retry_wait", "gmail")
                except Exception:
                    logger.warning("Gmail send to %s has an unknown outcome", to_email, exc_info=True)
                    return SendResult("unknown", "gmail")
                if gmail.state in ("sent", "unknown"):
                    if gmail.state == "sent":
                        logger.info("Sent email to %s", to_email)
                    return gmail
                logger.warning("Gmail did not send to %s (%s), trying MailerSend", to_email, gmail.state)
        if not self.api_key:
            logger.warning("MailerSend not configured, cannot send to %s", to_email)
            return gmail or SendResult("retry_wait")
        try:
            async with httpx.AsyncClient(timeout=20) as client:
                response = await client.post(
                    f"{self.base_url}/email",
                    json=self._mailersend_payload(to_email, to_name, subject, html_content, text_content,
                                                  from_name=from_name),
                    headers={"Authorization": f"Bearer {self.api_key}", "Content-Type": "application/json"},
                )
        except (httpx.ConnectError, httpx.ConnectTimeout):
            return SendResult("retry_wait", "mailersend")
        except Exception:
            logger.warning("MailerSend send to %s has an unknown outcome", to_email, exc_info=True)
            return SendResult("unknown", "mailersend")
        result = send_result(response, "mailersend")
        if result.state == "sent":
            logger.info("Sent email to %s via MailerSend fallback", to_email)
        else:
            logger.warning("MailerSend did not send to %s: status=%s", to_email, response.status_code)
        return result

    async def send_email(
        self,
        to_email: str,
        to_name: Optional[str],
        subject: str,
        html_content: str,
        text_content: Optional[str] = None,
        attachments: Optional[list[dict]] = None,
        extra_headers: Optional[dict[str, str]] = None,
        from_name: Optional[str] = None,
    ) -> bool:
        """Send an email via Gmail API.

        Attachments format: {"filename": "...", "content": "<base64>", "disposition": "attachment"}
        extra_headers lets callers attach RFC headers like List-Unsubscribe so
        Gmail/Outlook render the one-click unsubscribe button.
        from_name overrides the sender display name (the address is unchanged)
        for products that share this sender but not Matcha's brand.
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
            raw = self._mime_raw(
                to_email, to_name, subject, html_content, text_content,
                attachments=attachments, extra_headers=extra_headers, from_name=from_name,
            )
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
        attachments: Optional[list[dict]] = None,
        from_name: Optional[str] = None,
        reply_to: Optional[str] = None,
    ) -> bool:
        """Public send wrapper: Gmail first, MailerSend on Gmail failure.

        Use this for transactional emails where reliability matters. Both
        backends carry `attachments` (Gmail via MIME, MailerSend via its
        `attachments` array) and `reply_to` (a Reply-To header; MailerSend's
        `reply_to` — for products that send on someone else's behalf, so a
        reply reaches them, not us); `extra_headers` like List-Unsubscribe
        still require Gmail, so use `send_email` directly when you need those.

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
            attachments=attachments,
            from_name=from_name,
            reply_to=reply_to,
        )

    async def _send_with_fallback(
        self,
        to_email: str,
        to_name: Optional[str],
        subject: str,
        html_content: str,
        text_content: Optional[str] = None,
        attachments: Optional[list[dict]] = None,
        from_name: Optional[str] = None,
        reply_to: Optional[str] = None,
    ) -> bool:
        """Send via Gmail first, fall back to MailerSend if Gmail fails."""
        # Reserved-domain guard must be transport-independent: the Gmail path
        # checks this in send_email(), but when no Gmail token is loaded we skip
        # straight to MailerSend below — so guard here too (bounce-storm defense).
        if _is_reserved_test_domain(to_email):
            logger.info("Skipping send to reserved test domain: %s", to_email)
            return False
        # Try Gmail first
        gmail_token = self._load_token()
        if gmail_token and gmail_token.get("refresh_token"):
            reply = clean_reply_to(reply_to)
            sent = await self.send_email(
                to_email=to_email, to_name=to_name, subject=subject,
                html_content=html_content, text_content=text_content,
                attachments=attachments, from_name=from_name,
                **({"extra_headers": {"Reply-To": reply}} if reply else {}),
            )
            if sent:
                return True
            logger.warning("Gmail send failed for %s, trying MailerSend fallback", to_email)

        # Fallback to MailerSend
        if not self.api_key:
            logger.warning("MailerSend not configured, cannot send to %s", to_email)
            return False

        payload = self._mailersend_payload(
            to_email, to_name, subject, html_content, text_content,
            attachments=attachments, from_name=from_name, reply_to=reply_to,
        )
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
