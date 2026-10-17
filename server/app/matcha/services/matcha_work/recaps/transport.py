"""Structured transactional email outcomes, preserving existing boolean callers."""
from __future__ import annotations

import base64
from dataclasses import dataclass
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText

import httpx

from app.core.services.email import _is_reserved_test_domain, get_email_service
from app.core.services.email.client import GMAIL_SEND_URI


@dataclass(frozen=True)
class SendResult:
    state: str
    provider: str | None = None
    message_id: str | None = None


def response_result(response, provider):
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


async def send(to: str, message: dict) -> SendResult:
    if _is_reserved_test_domain(to):
        return SendResult("suppressed")
    service = get_email_service()
    gmail = service.is_gmail_configured()
    if gmail:
        try:
            token = await service._get_access_token()
        except Exception:
            # No send request was made; another provider is safe here.
            token = None
        if token:
            try:
                mail = MIMEMultipart("alternative")
                mail["Subject"] = message["subject"]
                mail["From"] = f"Espresso <{service.from_email}>"
                mail["To"] = to
                mail.attach(MIMEText(message["text"], "plain", "utf-8"))
                mail.attach(MIMEText(message["html"], "html", "utf-8"))
                payload = {"raw": base64.urlsafe_b64encode(mail.as_bytes()).decode()}
            except (ValueError, TypeError):
                return SendResult("failed")
            try:
                async with httpx.AsyncClient(timeout=20) as client:
                    result = response_result(await client.post(GMAIL_SEND_URI, json=payload,
                        headers={"Authorization": f"Bearer {token}"}), "gmail")
            except (httpx.ConnectError, httpx.ConnectTimeout):
                result = SendResult("retry_wait", "gmail")
            except Exception:
                return SendResult("unknown", "gmail")
            if result.state in ("sent", "unknown"):
                return result
    if not service.api_key:
        return SendResult("retry_wait")
    try:
        async with httpx.AsyncClient(timeout=20) as client:
            response = await client.post(f"{service.base_url}/email", headers={"Authorization": f"Bearer {service.api_key}"},
                json={"from": {"email": service.mailersend_from_email, "name": "Espresso"},
                      "to": [{"email": to}], **message})
        return response_result(response, "mailersend")
    except (httpx.ConnectError, httpx.ConnectTimeout):
        return SendResult("retry_wait", "mailersend")
    except Exception:
        return SendResult("unknown", "mailersend")
