"""Cappe mail goes out under the Gummfit name, and a confirmation email that
no provider accepted is logged as an error instead of vanishing.

Run from server/:  ./venv/bin/python -m pytest tests/cappe/test_cappe_email_sender.py -q
"""
import asyncio
import base64
import logging
import os
from email import message_from_bytes

os.environ.setdefault("LIVE_API", "test-key")
os.environ.setdefault("DATABASE_URL", "postgresql://test:test@localhost/test")
os.environ.setdefault("JWT_SECRET_KEY", "test-secret-key-cappe")

from app.cappe.services import email as email_mod  # noqa: E402
from app.core.services.email import client as client_mod  # noqa: E402


class _Svc:
    def __init__(self, result):
        self.result = result
        self.calls = []

    async def send_email_with_fallback(self, **kw):
        self.calls.append(kw)
        return self.result


def _errors(caplog):
    return [r for r in caplog.records if r.levelno >= logging.ERROR]


def test_verification_email_is_sent_as_gummfit(monkeypatch):
    svc = _Svc(True)
    monkeypatch.setattr(email_mod, "get_email_service", lambda: svc)
    monkeypatch.setenv("CAPPE_BASE_DOMAIN", "gummfit.com")
    asyncio.run(email_mod.send_cappe_verification_email("owner@example.com", "Pat", "tok-1"))

    [call] = svc.calls
    assert call["from_name"] == "Gummfit"
    assert "https://gummfit.com/cappe/verify?token=tok-1" in call["html_content"]


def test_an_undelivered_confirmation_is_logged_as_an_error(monkeypatch, caplog):
    monkeypatch.setattr(email_mod, "get_email_service", lambda: _Svc(False))
    monkeypatch.setattr(email_mod, "_is_reserved_test_domain", lambda _e: False)
    with caplog.at_level(logging.INFO):
        asyncio.run(email_mod.send_cappe_verification_email("owner@example.com", None, "tok-1"))
    assert len(_errors(caplog)) == 1


def test_a_skipped_reserved_domain_is_not_an_error(monkeypatch, caplog):
    monkeypatch.setattr(email_mod, "get_email_service", lambda: _Svc(False))
    with caplog.at_level(logging.INFO):
        asyncio.run(email_mod.send_cappe_verification_email("owner@example.com", None, "tok-1"))
    assert _errors(caplog) == []


def test_non_critical_mail_stays_quiet_when_undelivered(monkeypatch, caplog):
    monkeypatch.setattr(email_mod, "get_email_service", lambda: _Svc(False))
    monkeypatch.setattr(email_mod, "_is_reserved_test_domain", lambda _e: False)
    with caplog.at_level(logging.INFO):
        asyncio.run(email_mod.send_cappe_message_email(
            "owner@example.com", None, "Shop", "hello", "https://example.com/t", "Pat"))
        asyncio.run(email_mod.send_cappe_welcome_email("owner@example.com", "Pat"))
    assert _errors(caplog) == []


# ── the shared client honours from_name on both transports ───────────────────

class _Response:
    def __init__(self, status_code):
        self.status_code = status_code
        self.text = ""


class _HttpClient:
    posts = []

    def __init__(self, *a, **kw):
        pass

    async def __aenter__(self):
        return self

    async def __aexit__(self, *_args):
        return False

    async def post(self, url, json=None, **_kw):
        _HttpClient.posts.append((url, json))
        return _Response(200 if "raw" in json else 202)


def _service(monkeypatch, *, gmail):
    svc = object.__new__(client_mod.EmailService)
    svc.from_email = "sender@example.com"
    svc.from_name = "Matcha Recruit"
    svc.api_key = "" if gmail else "ms-key"
    svc.base_url = "https://mailersend.invalid/v1"
    svc.mailersend_from_email = "sender@example.com"
    svc._load_token = lambda: {"refresh_token": "r"} if gmail else None
    svc.is_configured = lambda: True

    async def _token():
        return "access"

    svc._get_access_token = _token
    _HttpClient.posts = []
    monkeypatch.setattr(client_mod.httpx, "AsyncClient", _HttpClient)
    monkeypatch.setattr(client_mod, "_is_reserved_test_domain", lambda _e: False)
    return svc


def _send(svc, **extra):
    return asyncio.run(svc.send_email_with_fallback(
        to_email="owner@example.com", to_name=None, subject="s", html_content="<p>h</p>", **extra))


def test_from_name_reaches_the_gmail_header(monkeypatch):
    svc = _service(monkeypatch, gmail=True)
    assert _send(svc, from_name="Gummfit") is True
    raw = _HttpClient.posts[0][1]["raw"]
    assert message_from_bytes(base64.urlsafe_b64decode(raw))["From"] == "Gummfit <sender@example.com>"


def test_from_name_reaches_the_mailersend_payload(monkeypatch):
    svc = _service(monkeypatch, gmail=False)
    assert _send(svc, from_name="Gummfit") is True
    assert _HttpClient.posts[0][1]["from"] == {"email": "sender@example.com", "name": "Gummfit"}


def test_the_default_sender_name_is_unchanged(monkeypatch):
    svc = _service(monkeypatch, gmail=False)
    assert _send(svc) is True
    assert _HttpClient.posts[0][1]["from"]["name"] == "Matcha Recruit"


# ── reply_to reaches both transports, and only as one plain address ──────────

def test_reply_to_reaches_the_gmail_header(monkeypatch):
    svc = _service(monkeypatch, gmail=True)
    assert _send(svc, from_name="Lumen via Gummfit", reply_to="hello@lumen.test") is True
    msg = message_from_bytes(base64.urlsafe_b64decode(_HttpClient.posts[0][1]["raw"]))
    assert msg["Reply-To"] == "hello@lumen.test"
    assert msg["From"] == "Lumen via Gummfit <sender@example.com>"


def test_reply_to_reaches_the_mailersend_payload(monkeypatch):
    svc = _service(monkeypatch, gmail=False)
    assert _send(svc, reply_to="hello@lumen.test") is True
    assert _HttpClient.posts[0][1]["reply_to"] == {"email": "hello@lumen.test"}


def test_a_reply_to_that_isnt_one_plain_address_is_dropped(monkeypatch):
    for bad in ("hello@lumen.test\r\nBcc: everyone@x.test", "Lumen <hello@lumen.test>", "a@b.test, c@d.test", "nope"):
        svc = _service(monkeypatch, gmail=True)
        assert _send(svc, reply_to=bad) is True
        msg = message_from_bytes(base64.urlsafe_b64decode(_HttpClient.posts[0][1]["raw"]))
        assert msg["Reply-To"] is None and msg["Bcc"] is None
        svc = _service(monkeypatch, gmail=False)
        assert _send(svc, reply_to=bad) is True
        assert "reply_to" not in _HttpClient.posts[0][1]


def test_without_reply_to_nothing_changes(monkeypatch):
    svc = _service(monkeypatch, gmail=True)
    assert _send(svc) is True
    assert message_from_bytes(base64.urlsafe_b64decode(_HttpClient.posts[0][1]["raw"]))["Reply-To"] is None


# ── a store's buyers get mail from the store ─────────────────────────────────

def test_the_store_sends_as_itself():
    assert email_mod.store_from_name("Lumen Candles") == "Lumen Candles via Gummfit"
    # Nothing that could end the header or split the address list survives.
    assert email_mod.store_from_name('Smith, Jones & Co. "<x>"\r\nBcc: y@z') == "Smith Jones & Co. x Bcc y z via Gummfit"
    assert email_mod.store_from_name("  ") == "Gummfit"
    assert len(email_mod.store_from_name("x" * 200)) == 60 + len(" via Gummfit")


def test_a_reply_reaches_the_stores_contact_address_else_the_owner():
    assert email_mod.store_reply_to({"contact_email": " hi@lumen.test "}, "owner@lumen.test") == "hi@lumen.test"
    assert email_mod.store_reply_to('{"contact_email": "hi@lumen.test"}') == "hi@lumen.test"
    assert email_mod.store_reply_to({}, "owner@lumen.test") == "owner@lumen.test"
    assert email_mod.store_reply_to(None, None) is None


def test_buyer_order_mail_is_sent_as_the_store(monkeypatch):
    svc = _Svc(True)
    monkeypatch.setattr(email_mod, "get_email_service", lambda: svc)
    asyncio.run(email_mod.send_cappe_order_shipped_email(
        "buyer@example.com", "B", "Lumen", "Candle × 1", "UPS", "1Z", None, True, reply_to="hi@lumen.test"))
    asyncio.run(email_mod.send_cappe_order_declined_email("buyer@example.com", "B", "Lumen", "Candle", None))
    assert [(c["from_name"], c.get("reply_to")) for c in svc.calls] == [
        ("Lumen via Gummfit", "hi@lumen.test"), ("Lumen via Gummfit", None)]


def test_owner_mail_is_still_from_gummfit(monkeypatch):
    svc = _Svc(True)
    monkeypatch.setattr(email_mod, "get_email_service", lambda: svc)
    asyncio.run(email_mod.send_cappe_order_alert_email(
        "owner@example.com", "Pat", "Lumen", "B", 1200, "USD", "https://example.com/o"))
    assert svc.calls[0]["from_name"] == "Gummfit" and "reply_to" not in svc.calls[0]


def test_the_paid_receipt_is_sent_as_the_store(monkeypatch):
    from app.cappe.services import receipt
    svc = _Svc(True)
    monkeypatch.setattr(receipt, "get_email_service", lambda: svc)
    order = {"customer_email": "buyer@example.com", "customer_name": "B", "receipt_number": "LUM-1",
             "business_name": "Lumen", "total_cents": 1200, "currency": "USD", "access_token": None,
             "meta_config": {"contact_email": "hi@lumen.test"}, "owner_email": "owner@lumen.test"}
    asyncio.run(receipt.email_receipt(order, b"%PDF"))
    [call] = svc.calls
    # It used to go out under Matcha's display name, replying to us.
    assert call["from_name"] == "Lumen via Gummfit" and call["reply_to"] == "hi@lumen.test"
