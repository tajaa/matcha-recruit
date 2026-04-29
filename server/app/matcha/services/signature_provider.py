"""E-signature provider abstraction.

One interface, two consumers: the matcha-work Discipline Project flow
and the platform-side discipline engine. Concrete impl is selected at
runtime via settings.signature_provider so we can swap DocuSign /
Dropbox Sign / a stub without touching call sites.

For local dev / tests / private-beta we ship a no-op `StubProvider`
that records what would have been sent and immediately marks it as
"signed" so the workflow can run end-to-end without an external
account. Configure with `SIGNATURE_PROVIDER=stub`.
"""

from __future__ import annotations

import logging
import secrets
from dataclasses import dataclass
from typing import Optional, Protocol

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
# Provider selection
# ──────────────────────────────────────────────────────────────────────

_provider: Optional[SignatureProvider] = None


def get_signature_provider() -> SignatureProvider:
    """Return the configured provider; default to StubProvider for now.

    Concrete providers (DocuSign, Dropbox Sign) drop into a new
    branch here. For v1 of the matcha-work discipline flow we ship
    only the stub so the rest of the workflow is testable without
    external dependencies.
    """
    global _provider
    if _provider is None:
        # TODO: branch on settings.signature_provider when a real
        # provider lands. For now, stub-only.
        _provider = StubProvider()
    return _provider
