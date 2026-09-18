"""Domain routes, executed — verify, transfer cancel, edge retry, and the
platform webhook's domain branch, driven through a scripted connection.

`test_cappe_domains_routes.py` pins the gate and the DNS guards; this module
runs the handlers themselves so the status transitions are exercised, not just
read.

Run from server/:  ./venv/bin/python -m pytest tests/cappe/test_cappe_domains_routes_exec.py -q
"""
import asyncio
import os
from types import SimpleNamespace

os.environ.setdefault("LIVE_API", "test-key")
os.environ.setdefault("DATABASE_URL", "postgresql://test:test@localhost/test")
os.environ.setdefault("JWT_SECRET_KEY", "test-secret-key-cappe")

import asyncpg  # noqa: E402
import pytest  # noqa: E402
from fastapi import HTTPException  # noqa: E402

from app.cappe.routes import domains as mod  # noqa: E402

DOMAIN_ID = "33333333-3333-4333-8333-333333333333"
ACCOUNT = SimpleNamespace(id="a-1", email="owner@example.com")


class Settings:
    cappe_custom_domains_enabled = True
    cappe_cf_routing_endpoint = "d123.cloudfront.net"


@pytest.fixture
def enabled(monkeypatch):
    s = Settings()
    monkeypatch.setattr(mod, "get_settings", lambda: s)
    return s


class Tx:
    async def __aenter__(self):
        return self

    async def __aexit__(self, *exc):
        return False


class ScriptedConn:
    def __init__(self, rows=(), vals=(), execute_raises=None):
        self.rows, self.vals = list(rows), list(vals)
        self.execute_raises = execute_raises
        self.calls = []

    async def fetchrow(self, sql, *args):
        self.calls.append(("fetchrow", sql, args))
        return self.rows.pop(0)

    async def fetchval(self, sql, *args):
        self.calls.append(("fetchval", sql, args))
        return self.vals.pop(0)

    async def execute(self, sql, *args):
        self.calls.append(("execute", sql, args))
        if self.execute_raises is not None:
            raise self.execute_raises
        return "UPDATE 1"

    def transaction(self):
        return Tx()


class ConnCtx:
    def __init__(self, conn):
        self._conn = conn

    async def __aenter__(self):
        return self._conn

    async def __aexit__(self, *exc):
        return False


def _use(monkeypatch, conn):
    monkeypatch.setattr(mod, "get_connection", lambda: ConnCtx(conn))
    return conn


def _run(coro):
    return asyncio.run(coro)


# ── every create path is dark while the edge is unconfigured ─────────────────

def test_create_routes_503_while_disabled(monkeypatch):
    s = Settings()
    s.cappe_custom_domains_enabled = False
    monkeypatch.setattr(mod, "get_settings", lambda: s)
    calls = [
        mod.search_domains(q="studio", account=ACCOUNT),
        mod.purchase_domain(SimpleNamespace(domain="studio.example"), account=ACCOUNT),
        mod.connect_domain(SimpleNamespace(domain="studio.example"), account=ACCOUNT),
        mod.verify_domain(DOMAIN_ID, account=ACCOUNT),
        mod.retry_edge(DOMAIN_ID, account=ACCOUNT),
    ]
    for coro in calls:
        with pytest.raises(HTTPException) as exc:
            _run(coro)
        assert exc.value.status_code == 503


# ── verify (BYO connect) ─────────────────────────────────────────────────────

def _pending_row(**over):
    row = {"id": DOMAIN_ID, "domain": "studio.example", "status": "pending",
           "verification_token": "tok-123"}
    row.update(over)
    return row


def _txt(monkeypatch, *values):
    async def resolve(fqdn, rtype):
        assert fqdn == "_cappe-verify.studio.example" and rtype == "TXT"
        return [SimpleNamespace(strings=[v.encode()]) for v in values]

    monkeypatch.setattr(mod.dns.asyncresolver, "resolve", resolve)


def test_verified_domain_activates_and_attaches_to_the_edge(monkeypatch, enabled):
    conn = _use(monkeypatch, ScriptedConn(
        rows=[_pending_row(), _pending_row(status="active")], vals=[None],
    ))
    _txt(monkeypatch, "unrelated", "tok-123")
    provisioned = []

    async def _provision(did, domain):
        provisioned.append((did, domain))

    monkeypatch.setattr(mod, "provision_domain_edge", _provision)
    out = _run(mod.verify_domain(DOMAIN_ID, account=ACCOUNT))
    assert out["status"] == "active"
    assert provisioned == [(DOMAIN_ID, "studio.example")]
    assert any(c[0] == "execute" and "status = 'active'" in c[1] for c in conn.calls)
    # custom_domain is the edge sweeper's to write, never verify's.
    assert not any("custom_domain" in c[1] for c in conn.calls)


def test_domain_already_active_elsewhere_is_409(monkeypatch, enabled):
    _use(monkeypatch, ScriptedConn(rows=[_pending_row()], vals=[1]))
    _txt(monkeypatch, "tok-123")
    with pytest.raises(HTTPException) as exc:
        _run(mod.verify_domain(DOMAIN_ID, account=ACCOUNT))
    assert exc.value.status_code == 409


def test_activation_race_on_the_unique_index_is_409_not_500(monkeypatch, enabled):
    _use(monkeypatch, ScriptedConn(
        rows=[_pending_row()], vals=[None],
        execute_raises=asyncpg.UniqueViolationError("duplicate key"),
    ))
    _txt(monkeypatch, "tok-123")
    with pytest.raises(HTTPException) as exc:
        _run(mod.verify_domain(DOMAIN_ID, account=ACCOUNT))
    assert exc.value.status_code == 409


def test_missing_txt_record_is_400(monkeypatch, enabled):
    _use(monkeypatch, ScriptedConn(rows=[_pending_row()]))
    _txt(monkeypatch, "something-else")
    with pytest.raises(HTTPException) as exc:
        _run(mod.verify_domain(DOMAIN_ID, account=ACCOUNT))
    assert exc.value.status_code == 400


# ── transfer-out cancel ──────────────────────────────────────────────────────

def test_cancel_transfer_returns_the_domain_to_active(monkeypatch):
    conn = _use(monkeypatch, ScriptedConn(rows=[{"id": DOMAIN_ID, "domain": "studio.example",
                                                 "status": "active"}]))
    out = _run(mod.cancel_transfer_request(DOMAIN_ID, account=ACCOUNT))
    assert out["status"] == "active"
    sql = conn.calls[0][1]
    assert "status = 'transfer_requested'" in sql and "account_id = $2" in sql


def test_cancel_without_an_open_transfer_is_409(monkeypatch):
    _use(monkeypatch, ScriptedConn(rows=[None]))
    with pytest.raises(HTTPException) as exc:
        _run(mod.cancel_transfer_request(DOMAIN_ID, account=ACCOUNT))
    assert exc.value.status_code == 409


# ── edge retry ───────────────────────────────────────────────────────────────

def test_retry_edge_delegates_to_the_service(monkeypatch, enabled):
    _use(monkeypatch, ScriptedConn(rows=[
        {"id": DOMAIN_ID, "status": "active", "cf_tenant_id": None},
        {"id": DOMAIN_ID, "status": "active", "edge_status": "pending_dns"},
    ]))
    retried = []

    async def _retry(did):
        retried.append(did)

    monkeypatch.setattr(mod, "retry_domain_edge", _retry)
    out = _run(mod.retry_edge(DOMAIN_ID, account=ACCOUNT))
    assert retried == [DOMAIN_ID]
    assert out["edge_status"] == "pending_dns"


@pytest.mark.parametrize("row,code", [
    (None, 404),
    ({"id": DOMAIN_ID, "status": "pending", "cf_tenant_id": None}, 409),
])
def test_retry_edge_refuses_unknown_or_inactive(monkeypatch, enabled, row, code):
    _use(monkeypatch, ScriptedConn(rows=[row]))
    with pytest.raises(HTTPException) as exc:
        _run(mod.retry_edge(DOMAIN_ID, account=ACCOUNT))
    assert exc.value.status_code == code


# ── platform webhook: domain purchases ───────────────────────────────────────

class Request:
    headers = {"stripe-signature": "sig"}

    async def body(self):
        return b"{}"


class Background:
    def __init__(self):
        self.tasks = []

    def add_task(self, fn, *args):
        self.tasks.append((fn.__name__, args))


def _webhook(monkeypatch, event, *, claimed=True):
    released = []

    class Stripe:
        async def verify_platform_webhook(self, payload, sig):
            return event

    async def _claim(event_id, event_type, consumer):
        return claimed

    async def _release(event_id, consumer):
        released.append(event_id)

    monkeypatch.setattr(mod, "get_cappe_stripe", lambda: Stripe())
    monkeypatch.setattr(mod, "claim_stripe_event", _claim)
    monkeypatch.setattr(mod, "release_stripe_event", _release)
    bg = Background()
    return bg, released


def _domain_event(etype, **obj):
    return {"id": "evt_1", "type": etype, "created": 1_700_000_000,
            "data": {"object": {"metadata": {"type": "cappe_domain", "domain_id": DOMAIN_ID},
                                **obj}}}


def test_paid_domain_checkout_starts_registration(monkeypatch):
    conn = _use(monkeypatch, ScriptedConn(rows=[{"id": DOMAIN_ID}]))
    bg, _ = _webhook(monkeypatch, _domain_event(
        "checkout.session.completed", payment_status="paid",
        payment_intent="pi_1", customer="cus_1",
    ))
    out = _run(mod.domains_webhook(Request(), bg))
    assert out == {"received": True}
    _, sql, args = conn.calls[0]
    assert "status = 'registering'" in sql and "status = 'pending'" in sql
    assert args[1:] == ("pi_1", "cus_1")
    assert [t[0] for t in bg.tasks] == ["finalize_domain_registration"]


def test_unpaid_domain_checkout_waits_for_settlement(monkeypatch):
    conn = _use(monkeypatch, ScriptedConn())
    bg, _ = _webhook(monkeypatch, _domain_event(
        "checkout.session.completed", payment_status="unpaid",
    ))
    assert _run(mod.domains_webhook(Request(), bg)) == {"received": True, "status": "unpaid"}
    assert conn.calls == [] and bg.tasks == []


def test_failed_async_domain_payment_marks_the_row_failed(monkeypatch):
    conn = _use(monkeypatch, ScriptedConn())
    bg, _ = _webhook(monkeypatch, _domain_event("checkout.session.async_payment_failed"))
    out = _run(mod.domains_webhook(Request(), bg))
    assert out == {"received": True, "status": "payment_failed"}
    _, sql, args = conn.calls[0]
    assert "status = 'failed'" in sql and args[1] == "Payment failed"


def test_domain_event_without_a_domain_id_is_ignored(monkeypatch):
    event = _domain_event("checkout.session.completed", payment_status="paid")
    event["data"]["object"]["metadata"]["domain_id"] = "not-a-uuid"
    bg, _ = _webhook(monkeypatch, event)
    assert _run(mod.domains_webhook(Request(), bg)) == {"received": True, "status": "ignored"}


def test_duplicate_event_is_acknowledged_once(monkeypatch):
    bg, _ = _webhook(monkeypatch, _domain_event("checkout.session.completed"), claimed=False)
    assert _run(mod.domains_webhook(Request(), bg)) == {"received": True, "status": "duplicate"}


def test_handler_failure_releases_the_claim_for_retry(monkeypatch):
    class Boom(Exception):
        pass

    class BrokenConn(ScriptedConn):
        async def fetchrow(self, sql, *args):
            raise Boom()

    _use(monkeypatch, BrokenConn())
    bg, released = _webhook(monkeypatch, _domain_event(
        "checkout.session.completed", payment_status="paid",
    ))
    with pytest.raises(Boom):
        _run(mod.domains_webhook(Request(), bg))
    assert released == ["evt_1"]
