"""Domain registration claims its row, and never publishes before TLS exists.

Two audit findings meet here:
  * W3 — `finalize_domain_registration` used to SELECT the row and call Porkbun
    without marking it, so the 15-minute reconciler could re-enter a
    registration already in flight and buy the same domain twice.
  * O4 — activation used to write `cappe_sites.custom_domain` immediately, which
    published a host whose certificate did not exist.

Run from server/:  ./venv/bin/python -m pytest tests/cappe/test_cappe_domain_register.py -q
"""
import asyncio
import os

os.environ.setdefault("LIVE_API", "test-key")
os.environ.setdefault("DATABASE_URL", "postgresql://test:test@localhost/test")
os.environ.setdefault("JWT_SECRET_KEY", "test-secret-key-cappe")

import pytest  # noqa: E402

from app.cappe.services import domain_register as mod  # noqa: E402
from app.cappe.services.cloudfront_tenants import CappeEdgeError, CfTenant  # noqa: E402
from app.cappe.services.porkbun import PorkbunError  # noqa: E402

CLAIM = {
    "id": "d-1",
    "site_id": "s-1",
    "domain": "example.com",
    "wholesale_cents": 1100,
    "stripe_payment_intent": "pi_1",
}


class FakeConn:
    def __init__(self, rows):
        self._rows = list(rows)
        self.executed = []
        self.fetchrow_sql = []

    async def fetchrow(self, sql, *args):
        self.fetchrow_sql.append((sql, args))
        return self._rows.pop(0) if self._rows else None

    async def execute(self, sql, *args):
        self.executed.append((sql, args))

    def sql_matching(self, needle):
        return [e for e in self.executed if needle in e[0]]


class FakeConnCtx:
    def __init__(self, conn):
        self._conn = conn

    async def __aenter__(self):
        return self._conn

    async def __aexit__(self, *exc):
        return False


class FakePorkbun:
    def __init__(self, register_exc=None, point_exc=None):
        self.register_exc = register_exc
        self.point_exc = point_exc
        self.registered = []
        self.pointed = []

    async def register(self, domain, *, cost_cents, idempotency_key):
        if self.register_exc:
            raise self.register_exc
        self.registered.append((domain, cost_cents, idempotency_key))

    async def point_at_app(self, domain, target):
        if self.point_exc:
            raise self.point_exc
        self.pointed.append((domain, target))


class FakeEdge:
    def __init__(self, tenant=None, exc=None):
        self.tenant = tenant or CfTenant(tenant_id="dt-1", routing_endpoint="d123.cloudfront.net")
        self.exc = exc
        self.created = []

    async def create_tenant(self, domain):
        if self.exc:
            raise self.exc
        self.created.append(domain)
        return self.tenant


def _patch(monkeypatch, conn, pb, edge, refunds=None):
    monkeypatch.setattr(mod, "connection_or_direct", lambda: FakeConnCtx(conn))
    monkeypatch.setattr(mod, "get_porkbun", lambda: pb)
    monkeypatch.setattr(mod, "get_cloudfront_tenants", lambda: edge)

    class FakeStripe:
        async def refund(self, intent):
            if refunds is not None:
                refunds.append(intent)

    monkeypatch.setattr(mod, "get_cappe_stripe", lambda: FakeStripe())


# ── the claim ────────────────────────────────────────────────────────────────

def test_finalize_claims_the_row_before_spending_money(monkeypatch):
    conn = FakeConn([CLAIM])
    pb, edge = FakePorkbun(), FakeEdge()
    _patch(monkeypatch, conn, pb, edge)

    asyncio.run(mod.finalize_domain_registration("d-1"))

    sql, args = conn.fetchrow_sql[0]
    # An UPDATE, not a SELECT: it both proves the row is still awaiting
    # registration and bumps updated_at so the reconciler's 15-minute window
    # means "nobody is working on this".
    assert sql.strip().upper().startswith("UPDATE")
    assert "status = 'registering'" in sql
    assert "SET updated_at = NOW()" in sql
    assert args == ("d-1",)
    assert len(pb.registered) == 1


def test_unclaimable_row_never_reaches_porkbun(monkeypatch):
    """Another worker already claimed it — registering again buys the domain
    a second time at our expense."""
    conn = FakeConn([None])
    pb, edge = FakePorkbun(), FakeEdge()
    _patch(monkeypatch, conn, pb, edge)

    asyncio.run(mod.finalize_domain_registration("d-1"))
    assert pb.registered == []
    assert edge.created == []


def test_registration_is_idempotency_keyed_on_the_domain_row(monkeypatch):
    conn = FakeConn([CLAIM])
    pb, edge = FakePorkbun(), FakeEdge()
    _patch(monkeypatch, conn, pb, edge)
    asyncio.run(mod.finalize_domain_registration("d-1"))
    assert pb.registered[0] == ("example.com", 1100, "d-1")


# ── the happy path ───────────────────────────────────────────────────────────

def test_success_activates_the_domain_but_does_not_publish_it(monkeypatch):
    conn = FakeConn([CLAIM])
    pb, edge = FakePorkbun(), FakeEdge()
    _patch(monkeypatch, conn, pb, edge)

    asyncio.run(mod.finalize_domain_registration("d-1"))

    assert conn.sql_matching("status = 'active'")
    assert conn.sql_matching("edge_status = 'pending_dns'")
    # The edge sweeper owns this write; doing it here serves a host with no cert.
    assert conn.sql_matching("UPDATE cappe_sites SET custom_domain") == []


def test_dns_points_at_the_routing_endpoint_not_an_ip(monkeypatch):
    """The edge has no stable IP; an A record to the EC2 bypasses CloudFront
    (and its certificate) entirely."""
    conn = FakeConn([CLAIM])
    pb, edge = FakePorkbun(), FakeEdge()
    _patch(monkeypatch, conn, pb, edge)

    asyncio.run(mod.finalize_domain_registration("d-1"))
    assert pb.pointed == [("example.com", "d123.cloudfront.net")]


# ── failure paths ────────────────────────────────────────────────────────────

def test_porkbun_failure_refunds_and_marks_the_row_failed(monkeypatch):
    conn = FakeConn([CLAIM])
    refunds = []
    pb, edge = FakePorkbun(register_exc=PorkbunError("domain taken")), FakeEdge()
    _patch(monkeypatch, conn, pb, edge, refunds=refunds)

    asyncio.run(mod.finalize_domain_registration("d-1"))

    assert conn.sql_matching("status = 'failed'")
    assert refunds == ["pi_1"]          # the customer is not charged for nothing
    assert edge.created == []


def test_edge_failure_keeps_the_paid_registration(monkeypatch):
    """The domain is registered and paid for. Losing the row because CloudFront
    was unavailable would strand a real purchase; it is recorded for retry."""
    conn = FakeConn([CLAIM])
    pb = FakePorkbun()
    edge = FakeEdge(exc=CappeEdgeError("AccessDenied"))
    _patch(monkeypatch, conn, pb, edge)

    asyncio.run(mod.finalize_domain_registration("d-1"))

    assert conn.sql_matching("status = 'active'")
    failed = conn.sql_matching("edge_status = 'failed'")
    assert failed and "AccessDenied" in failed[0][1][1]
    assert pb.pointed == []             # no endpoint to point at


def test_dns_pointing_failure_does_not_undo_the_registration(monkeypatch):
    conn = FakeConn([CLAIM])
    pb = FakePorkbun(point_exc=PorkbunError("dns api down"))
    _patch(monkeypatch, conn, pb, FakeEdge())

    asyncio.run(mod.finalize_domain_registration("d-1"))
    assert conn.sql_matching("status = 'active'")
    assert conn.sql_matching("status = 'failed'") == []


# ── retry ────────────────────────────────────────────────────────────────────

def test_retry_only_touches_an_active_row_with_no_tenant(monkeypatch):
    conn = FakeConn([None])
    pb, edge = FakePorkbun(), FakeEdge()
    _patch(monkeypatch, conn, pb, edge)

    assert asyncio.run(mod.retry_domain_edge("d-1")) == "none"
    sql, _ = conn.fetchrow_sql[0]
    # Guarded so a retry can never detach a domain that is already live.
    assert "status = 'active'" in sql and "cf_tenant_id IS NULL" in sql
    assert edge.created == []


def test_retry_repoints_dns_for_a_bought_domain(monkeypatch):
    conn = FakeConn([{"id": "d-1", "kind": "register", "domain": "example.com"}])
    pb, edge = FakePorkbun(), FakeEdge()
    _patch(monkeypatch, conn, pb, edge)

    assert asyncio.run(mod.retry_domain_edge("d-1")) == "pending_dns"
    assert pb.pointed == [("example.com", "d123.cloudfront.net")]


def test_retry_never_edits_dns_for_a_byo_domain(monkeypatch):
    """A connected domain's DNS lives at the tenant's own registrar — we have no
    business writing records there even if we could."""
    conn = FakeConn([{"id": "d-1", "kind": "connect", "domain": "example.com"}])
    pb, edge = FakePorkbun(), FakeEdge()
    _patch(monkeypatch, conn, pb, edge)

    assert asyncio.run(mod.retry_domain_edge("d-1")) == "pending_dns"
    assert pb.pointed == []
