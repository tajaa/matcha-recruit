"""Imported contacts are double opt-in, and campaign sending is throttled.

Before the 2026-09 audit an email-verified free account could upload a 5,000-row
CSV of addresses nobody consented to give us, have every row land `subscribed`,
and blast them through the same Gmail/MailerSend sender Matcha's transactional
mail uses — with no per-account rate limit and no bound on `body_html`. That is
a spam relay whose reputation damage lands on the shared sending domain
(audit B3).

Run from server/:  ./venv/bin/python -m pytest tests/cappe/test_cappe_subscriber_confirm.py -q
"""
import os

os.environ.setdefault("LIVE_API", "test-key")
os.environ.setdefault("DATABASE_URL", "postgresql://test:test@localhost/test")
os.environ.setdefault("JWT_SECRET_KEY", "test-secret-key-cappe")

import pytest  # noqa: E402
from pydantic import ValidationError  # noqa: E402

from app.cappe.routes import clients as clients_mod  # noqa: E402
from app.cappe.routes import newsletter as news_mod  # noqa: E402
from app.cappe.routes.public import newsletter as public_news  # noqa: E402


# ── staged, never subscribed ─────────────────────────────────────────────────

class FakeConn:
    def __init__(self, value=None):
        self.value = value
        self.args = None

    async def fetchval(self, sql, *args):
        self.args = (sql, args)
        return self.value


@pytest.mark.anyio
async def test_imported_contact_is_staged_pending_confirmation(monkeypatch):
    # Reserved domain (repo rule); the reserved-domain drop is the NEXT test's
    # subject, so it is switched off here rather than dodged with a real domain.
    monkeypatch.setattr(clients_mod, "_is_reserved_test_domain", lambda _e: False)
    conn = FakeConn("tok-1")
    token = await clients_mod._add_to_newsletter(conn, "site-1", "person@example.com", "Pat")
    assert token == "tok-1"
    sql, _ = conn.args
    assert "'pending_confirmation'" in sql
    # The campaign worker selects `status = 'subscribed'`; an import must never
    # write that directly.
    assert "'subscribed'" not in sql
    assert "confirm_token" in sql
    assert "ON CONFLICT (site_id, email) DO NOTHING" in sql


@pytest.mark.anyio
async def test_reserved_test_domain_is_never_added():
    """RFC-2606 addresses bounce and trigger send-storms (the medcenter.com
    incident); they are dropped before the insert, not after."""
    conn = FakeConn("tok-1")
    assert await clients_mod._add_to_newsletter(conn, "site-1", "nobody@example.com", None) is None
    assert conn.args is None


# ── the confirm link ─────────────────────────────────────────────────────────

def test_confirm_page_escapes_its_copy_and_is_not_cached():
    page = public_news._confirm_page("Heading <script>", "Body & <b>text</b>")
    body = page.body.decode()
    assert "<script>" not in body
    assert "&lt;script&gt;" in body
    assert page.headers["Cache-Control"] == "no-store"
    assert page.headers["Referrer-Policy"] == "no-referrer"


def test_confirm_page_reports_a_dead_link_with_404():
    page = public_news._confirm_page("Link not found", "no longer valid", status_code=404)
    assert page.status_code == 404


# ── send throttles ───────────────────────────────────────────────────────────

def test_send_limits_are_conservative():
    assert news_mod._SENDS_PER_DAY == 3
    assert news_mod._RECIPIENTS_PER_DAY == 5000


def test_campaign_body_is_bounded():
    """Unbounded `body_html` meant one request could stage an arbitrarily large
    payload for a 5,000-way fan-out."""
    from app.cappe.models.engage import CappeCampaignCreate

    ok = CappeCampaignCreate(subject="Hi", body_html="<p>hello</p>")
    assert ok.body_html == "<p>hello</p>"

    with pytest.raises(ValidationError):
        CappeCampaignCreate(subject="Hi", body_html="x" * 200_001)


def test_campaign_update_body_is_bounded_too():
    from app.cappe.models.engage import CappeCampaignUpdate

    with pytest.raises(ValidationError):
        CappeCampaignUpdate(body_html="x" * 200_001)
