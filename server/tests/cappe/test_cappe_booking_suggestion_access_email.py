"""Email payload coverage for booking suggestion access links."""
import os

import pytest

os.environ.setdefault("LIVE_API", "test-key")
os.environ.setdefault("DATABASE_URL", "postgresql://test:test@localhost/test")
os.environ.setdefault("JWT_SECRET_KEY", "test-secret-key-cappe")

from app.cappe.services import email  # noqa: E402
from app.core.services.email.client import EmailService  # noqa: E402


@pytest.mark.asyncio
async def test_access_email_keeps_token_in_fragment(monkeypatch):
    sent = {}

    async def fake_send(*args, **kwargs):
        sent.update({"to_email": args[0], "html": args[3], "text": args[4], **kwargs})

    monkeypatch.setattr(email, "_send", fake_send)
    await email.send_cappe_booking_suggestion_access_email(
        "maria@example.com",
        "Maria",
        "Lumiere",
        "https://lumiere.test/__cappe/booking-suggestions/access#secret",
    )
    assert "#secret" in sent["html"]
    assert "#secret" in sent["text"]
    assert "?token=secret" not in sent["html"]


@pytest.mark.asyncio
async def test_reserved_fixture_email_never_reaches_transport(monkeypatch):
    service = object.__new__(EmailService)
    monkeypatch.setattr(email, "get_email_service", lambda: service)
    await email.send_cappe_booking_suggestion_access_email(
        "ai-client@lumiere.test",
        "AI Test Client",
        "Lumiere",
        "https://lumiere-spa.gummfit.com/__cappe/booking-suggestions/access#secret",
    )

    assert await service.send_email_with_fallback(
        to_email="ai-client@lumiere.test",
        to_name="AI Test Client",
        subject="test",
        html_content="<p>test</p>",
        text_content="test",
    ) is False


def test_suggestion_access_url_does_not_reparse_origin():
    assert email.suggestion_access_url(
        "https://lumiere-spa.gummfit.com", "secret"
    ) == "https://lumiere-spa.gummfit.com/__cappe/booking-suggestions/access#secret"
