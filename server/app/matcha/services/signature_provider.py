"""E-signature provider abstraction.

One interface, two consumers: the matcha-work Discipline Project flow
and the platform-side discipline engine. Concrete impl is selected at
runtime via the `SIGNATURE_PROVIDER` env var so we can swap providers
without touching call sites.

Available providers:
- `stub` (default) — no-op recorder used in local dev / tests / private
  beta. Returns canned envelope IDs and treats every send as "signed".
- `docuseal` — open source self-hosted DocuSeal instance. Configured via
  `DOCUSEAL_BASE_URL`, `DOCUSEAL_API_KEY`, `DOCUSEAL_WEBHOOK_SECRET`.
"""

from __future__ import annotations

import hashlib
import hmac
import logging
import os
import secrets
from dataclasses import dataclass
from typing import Optional, Protocol

import httpx

logger = logging.getLogger(__name__)


@dataclass
class SendResult:
    """Returned from `send`. envelope_id is provider-specific."""
    envelope_id: str
    status: str  # 'sent' | 'queued'


class SignatureProvider(Protocol):
    async def send(
        self,
        *,
        recipient_email: str,
        recipient_name: Optional[str],
        document_pdf: bytes,
        subject: str,
        metadata: Optional[dict] = None,
    ) -> SendResult:
        """Send a one-off document for signature."""
        ...

    async def fetch_signed_pdf(self, envelope_id: str) -> Optional[bytes]:
        """Pull the signed PDF after webhook fires.

        Returns None if the envelope hasn't been signed yet or doesn't
        exist on the provider.
        """
        ...

    def webhook_secret(self) -> str:
        """Shared secret for verifying incoming webhook signatures."""
        ...


# ──────────────────────────────────────────────────────────────────────
# Stub implementation — local dev / tests / pre-provider beta
# ──────────────────────────────────────────────────────────────────────

class StubProvider:
    """No-op provider that pretends to send + immediately mark signed.

    The 'signed PDF' it returns is just the original document bytes.
    Useful so the discipline workflow can run end-to-end before we
    sign up for DocuSign / Dropbox Sign.
    """

    def __init__(self):
        self._envelopes: dict[str, bytes] = {}

    async def send(
        self,
        *,
        recipient_email: str,
        recipient_name: Optional[str],
        document_pdf: bytes,
        subject: str,
        metadata: Optional[dict] = None,
    ) -> SendResult:
        envelope_id = f"stub-{secrets.token_hex(8)}"
        self._envelopes[envelope_id] = document_pdf
        logger.info(
            "[StubSignatureProvider] would send envelope=%s to=%s subject=%s metadata=%s",
            envelope_id, recipient_email, subject, metadata,
        )
        return SendResult(envelope_id=envelope_id, status="sent")

    async def fetch_signed_pdf(self, envelope_id: str) -> Optional[bytes]:
        return self._envelopes.get(envelope_id)

    def webhook_secret(self) -> str:
        return "stub-secret"


# ──────────────────────────────────────────────────────────────────────
# DocuSeal — open source, self-hosted (https://www.docuseal.com)
# ──────────────────────────────────────────────────────────────────────

class DocuSealProvider:
    """DocuSeal REST API client.

    Submitter flow: POST /api/submissions with a fresh template containing
    the document + a single signer (the employee). DocuSeal returns the
    submission id, which we store as `signature_envelope_id`. After the
    employee signs, DocuSeal POSTs to our webhook with HMAC-SHA256 of
    the raw body in `X-Docuseal-Signature`. We then `fetch_signed_pdf`
    to pull the merged signed file.
    """

    def __init__(self, base_url: str, api_key: str, webhook_secret: str):
        self.base_url = base_url.rstrip("/")
        self.api_key = api_key
        self._webhook_secret = webhook_secret

    def _headers(self) -> dict[str, str]:
        return {
            "X-Auth-Token": self.api_key,
            "Accept": "application/json",
        }

    async def send(
        self,
        *,
        recipient_email: str,
        recipient_name: Optional[str],
        document_pdf: bytes,
        subject: str,
        metadata: Optional[dict] = None,
    ) -> SendResult:
        # 1. Create a one-off template from the raw PDF
        async with httpx.AsyncClient(timeout=60.0) as client:
            files = {"files[]": ("discipline.pdf", document_pdf, "application/pdf")}
            data = {"name": subject}
            tmpl_resp = await client.post(
                f"{self.base_url}/api/templates/pdf",
                headers=self._headers(),
                data=data,
                files=files,
            )
            if tmpl_resp.status_code >= 400:
                logger.error(
                    "[DocuSeal] template create failed status=%s body=%s",
                    tmpl_resp.status_code, tmpl_resp.text[:500],
                )
                tmpl_resp.raise_for_status()
            template = tmpl_resp.json()
            template_id = template.get("id") or (template[0].get("id") if isinstance(template, list) else None)
            if not template_id:
                raise RuntimeError("DocuSeal template create returned no id")

            # 2. Create a submission for that template targeting the employee
            sub_payload = {
                "template_id": template_id,
                "send_email": True,
                "subject": subject,
                "submitters": [
                    {
                        "email": recipient_email,
                        "name": recipient_name or recipient_email,
                        "role": "Employee",
                    }
                ],
                "metadata": metadata or {},
            }
            sub_resp = await client.post(
                f"{self.base_url}/api/submissions",
                headers={**self._headers(), "Content-Type": "application/json"},
                json=sub_payload,
            )
            if sub_resp.status_code >= 400:
                logger.error(
                    "[DocuSeal] submission create failed status=%s body=%s",
                    sub_resp.status_code, sub_resp.text[:500],
                )
                sub_resp.raise_for_status()
            submission = sub_resp.json()
            # DocuSeal returns a list of submitters; pull submission id
            submission_id = None
            if isinstance(submission, list) and submission:
                submission_id = submission[0].get("submission_id") or submission[0].get("id")
            elif isinstance(submission, dict):
                submission_id = submission.get("id") or submission.get("submission_id")
            if not submission_id:
                raise RuntimeError("DocuSeal submission create returned no id")

        return SendResult(envelope_id=str(submission_id), status="sent")

    async def fetch_signed_pdf(self, envelope_id: str) -> Optional[bytes]:
        async with httpx.AsyncClient(timeout=60.0) as client:
            resp = await client.get(
                f"{self.base_url}/api/submissions/{envelope_id}",
                headers=self._headers(),
            )
            if resp.status_code == 404:
                return None
            resp.raise_for_status()
            data = resp.json()
            # documents/audit_log_url/combined_document_url depending on version
            doc_url = (
                data.get("audit_log_url")
                or data.get("combined_document_url")
                or (data.get("documents", [{}])[0] or {}).get("url")
            )
            if not doc_url:
                # Fallback to the per-submission documents endpoint
                doc_resp = await client.get(
                    f"{self.base_url}/api/submissions/{envelope_id}/documents",
                    headers=self._headers(),
                )
                if doc_resp.status_code >= 400:
                    return None
                doc_list = doc_resp.json()
                if isinstance(doc_list, list) and doc_list:
                    doc_url = doc_list[0].get("url")

            if not doc_url:
                return None

            pdf_resp = await client.get(doc_url)
            if pdf_resp.status_code >= 400:
                return None
            return pdf_resp.content

    def webhook_secret(self) -> str:
        return self._webhook_secret


def verify_webhook_signature(provider: SignatureProvider, raw_body: bytes, header_signature: str) -> bool:
    """Constant-time HMAC-SHA256 verification of an incoming webhook."""
    secret = provider.webhook_secret().encode("utf-8")
    expected = hmac.new(secret, raw_body, hashlib.sha256).hexdigest()
    # Some providers send `sha256=<hex>`; tolerate both forms.
    candidate = header_signature.split("=", 1)[1] if "=" in header_signature else header_signature
    return hmac.compare_digest(expected, candidate.lower())


# ──────────────────────────────────────────────────────────────────────
# Provider selection
# ──────────────────────────────────────────────────────────────────────

_provider: Optional[SignatureProvider] = None


def get_signature_provider() -> SignatureProvider:
    """Return the configured provider; default to StubProvider.

    Selected by `SIGNATURE_PROVIDER` env var: `stub` | `docuseal`.
    Cached per-process so we don't rebuild the HTTP-client provider on
    every call.
    """
    global _provider
    if _provider is not None:
        return _provider
    name = (os.getenv("SIGNATURE_PROVIDER") or "stub").lower()
    if name == "docuseal":
        base_url = os.environ.get("DOCUSEAL_BASE_URL")
        api_key = os.environ.get("DOCUSEAL_API_KEY")
        webhook_secret = os.environ.get("DOCUSEAL_WEBHOOK_SECRET")
        if not base_url or not api_key or not webhook_secret:
            logger.warning(
                "[SignatureProvider] SIGNATURE_PROVIDER=docuseal but DOCUSEAL_BASE_URL/"
                "DOCUSEAL_API_KEY/DOCUSEAL_WEBHOOK_SECRET are not all set — falling back to stub"
            )
            _provider = StubProvider()
        else:
            _provider = DocuSealProvider(base_url=base_url, api_key=api_key, webhook_secret=webhook_secret)
    else:
        _provider = StubProvider()
    return _provider


def reset_signature_provider() -> None:
    """Test helper — drop the cached provider so env-var changes take effect."""
    global _provider
    _provider = None
