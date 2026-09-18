"""Cappe campaign send worker — per-recipient failures are counted, never hidden.

Before the 2026-09 audit a provider error was swallowed with `pass`, so a blast
that half-failed finalized as 'sent' with a low recipient_count and no trace of
what went wrong. The worker now records `failed_count` on the campaign row and
logs each failure by subscriber id (not address).

Run from server/:  ./venv/bin/python -m pytest tests/workers/test_cappe_campaign_send.py -q
"""
import asyncio
import logging
import os

os.environ.setdefault("LIVE_API", "test-key")
os.environ.setdefault("DATABASE_URL", "postgresql://test:test@localhost/test")
os.environ.setdefault("JWT_SECRET_KEY", "test-secret-key-cappe")

from app.cappe.services import campaigns as campaigns_mod  # noqa: E402
from app.workers.tasks import cappe_campaign_send as mod  # noqa: E402

CAMPAIGN = {
    "id": "camp-1", "subject": "Hello", "body_html": "<p>hi</p>", "from_name": None,
    "status": "sending", "site_id": "site-1", "slug": "shop", "site_name": "Shop",
}
# RFC-2606 reserved addresses only (repo rule: never a real-looking domain in
# test data). `deliverable_recipients` drops reserved domains on purpose, so the
# tests switch that one filter off rather than invent a deliverable address.
SUBSCRIBERS = [
    {"id": "sub-ok", "email": "ok@example.com", "name": "A", "unsubscribe_token": "t1"},
    {"id": "sub-bad", "email": "bad@example.org", "name": "B", "unsubscribe_token": "t2"},
]


class FakeConn:
    def __init__(self):
        self.executed = []
        self.closed = False

    async def fetchrow(self, sql, *args):
        return CAMPAIGN

    async def fetch(self, sql, *args):
        return SUBSCRIBERS

    async def execute(self, sql, *args):
        self.executed.append((sql, args))

    async def close(self):
        self.closed = True


class FakeEmailService:
    def __init__(self):
        self.sent_to = []

    async def send_email_with_fallback(self, *, to_email, **kwargs):
        if to_email.startswith("bad@"):
            raise RuntimeError("provider down")
        self.sent_to.append(to_email)


def test_failed_recipient_is_counted_and_logged(monkeypatch, caplog):
    conn = FakeConn()
    svc = FakeEmailService()

    async def _get_conn():
        return conn

    monkeypatch.setattr(mod, "get_db_connection", _get_conn)
    monkeypatch.setattr(mod, "THROTTLE_SECONDS", 0)
    monkeypatch.setattr(campaigns_mod, "_is_reserved_test_domain", lambda _e: False)
    import app.core.services.email as email_pkg
    monkeypatch.setattr(email_pkg, "EmailService", lambda: svc)

    with caplog.at_level(logging.WARNING, logger=mod.__name__):
        result = asyncio.run(mod._run("camp-1"))

    assert result == {"recipients": 2, "sent": 1, "failed": 1}
    assert svc.sent_to == ["ok@example.com"]

    finalize = [e for e in conn.executed if "SET status = 'sent'" in e[0]]
    assert len(finalize) == 1
    sql, args = finalize[0]
    assert "failed_count = $2" in sql
    assert args == (1, 1, "camp-1")
    assert conn.closed

    # The failure is visible in the log by subscriber id, never by address.
    messages = [r.getMessage() for r in caplog.records if r.levelno >= logging.WARNING]
    assert any("sub-bad" in m for m in messages)
    assert not any("bad@example.org" in m for m in messages)


def test_clean_blast_reports_zero_failures(monkeypatch):
    conn = FakeConn()
    svc = FakeEmailService()

    async def _get_conn():
        return conn

    async def _all_ok(*, to_email, **kwargs):
        svc.sent_to.append(to_email)

    svc.send_email_with_fallback = _all_ok
    monkeypatch.setattr(mod, "get_db_connection", _get_conn)
    monkeypatch.setattr(mod, "THROTTLE_SECONDS", 0)
    monkeypatch.setattr(campaigns_mod, "_is_reserved_test_domain", lambda _e: False)
    import app.core.services.email as email_pkg
    monkeypatch.setattr(email_pkg, "EmailService", lambda: svc)

    result = asyncio.run(mod._run("camp-1"))
    assert result == {"recipients": 2, "sent": 2, "failed": 0}
    sql, args = [e for e in conn.executed if "SET status = 'sent'" in e[0]][0]
    assert args == (2, 0, "camp-1")
