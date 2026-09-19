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

# `provision_domain_edge` claims the row too (RETURNING kind).
EDGE_CLAIM = {"kind": "register"}

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
        self.delete_exc = None
        self.created = []
        self.deleted = []

    async def create_tenant(self, domain, *, include_www=False):
        if self.exc:
            raise self.exc
        self.created.append((domain, include_www))
        return self.tenant

    async def delete_tenant(self, tenant_id):
        if self.delete_exc:
            raise self.delete_exc
        self.deleted.append(tenant_id)


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
    conn = FakeConn([CLAIM, EDGE_CLAIM])
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
    conn = FakeConn([CLAIM, EDGE_CLAIM])
    pb, edge = FakePorkbun(), FakeEdge()
    _patch(monkeypatch, conn, pb, edge)
    asyncio.run(mod.finalize_domain_registration("d-1"))
    assert pb.registered[0] == ("example.com", 1100, "d-1")


# ── the happy path ───────────────────────────────────────────────────────────

def test_success_activates_the_domain_but_does_not_publish_it(monkeypatch):
    conn = FakeConn([CLAIM, EDGE_CLAIM])
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
    conn = FakeConn([CLAIM, EDGE_CLAIM])
    pb, edge = FakePorkbun(), FakeEdge()
    _patch(monkeypatch, conn, pb, edge)

    asyncio.run(mod.finalize_domain_registration("d-1"))
    assert pb.pointed == [("example.com", "d123.cloudfront.net")]


# ── failure paths ────────────────────────────────────────────────────────────

def test_porkbun_failure_refunds_and_marks_the_row_failed(monkeypatch):
    conn = FakeConn([CLAIM, EDGE_CLAIM])
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
    conn = FakeConn([CLAIM, EDGE_CLAIM])
    pb = FakePorkbun()
    edge = FakeEdge(exc=CappeEdgeError("AccessDenied"))
    _patch(monkeypatch, conn, pb, edge)

    asyncio.run(mod.finalize_domain_registration("d-1"))

    assert conn.sql_matching("status = 'active'")
    failed = conn.sql_matching("edge_status = 'failed'")
    assert failed and "AccessDenied" in failed[0][1][1]
    assert pb.pointed == []             # no endpoint to point at


def test_dns_pointing_failure_does_not_undo_the_registration(monkeypatch):
    conn = FakeConn([CLAIM, EDGE_CLAIM])
    pb = FakePorkbun(point_exc=PorkbunError("dns api down"))
    _patch(monkeypatch, conn, pb, FakeEdge())

    asyncio.run(mod.finalize_domain_registration("d-1"))
    assert conn.sql_matching("status = 'active'")
    assert conn.sql_matching("status = 'failed'") == []


# ── the edge claim (double-click / verify+retry / webhook+sweeper) ──────────

def test_provisioning_claims_the_row_before_calling_aws(monkeypatch):
    conn = FakeConn([EDGE_CLAIM])
    pb, edge = FakePorkbun(), FakeEdge()
    _patch(monkeypatch, conn, pb, edge)

    assert asyncio.run(mod.provision_domain_edge("d-1", "example.com")) == (
        "pending_dns", "d123.cloudfront.net",
    )
    sql, _ = conn.fetchrow_sql[0]
    assert sql.strip().upper().startswith("UPDATE")
    assert "cf_tenant_id IS NULL" in sql
    assert "edge_status IN ('none', 'failed')" in sql
    # A claim whose process died between the UPDATE and the AWS call must not
    # be a permanent dead end.
    assert "edge_status = 'provisioning'" in sql and mod._STALE_CLAIM in sql


def test_losing_caller_never_creates_a_second_tenant_or_marks_the_winner_failed(monkeypatch):
    """The race this closes: the second create fails with "already exists" and
    then stamps edge_status='failed' over the first caller's healthy tenant."""
    conn = FakeConn([None, {"edge_status": "pending_dns", "cf_routing_endpoint": "d123.cloudfront.net"}])
    pb, edge = FakePorkbun(), FakeEdge()
    _patch(monkeypatch, conn, pb, edge)

    assert asyncio.run(mod.provision_domain_edge("d-1", "example.com")) == (
        "pending_dns", "d123.cloudfront.net",
    )
    assert edge.created == []
    assert conn.sql_matching("edge_status = 'failed'") == []


def test_failure_write_cannot_clobber_a_tenant_that_appeared(monkeypatch):
    conn = FakeConn([EDGE_CLAIM])
    _patch(monkeypatch, conn, FakePorkbun(), FakeEdge(exc=CappeEdgeError("boom")))
    asyncio.run(mod.provision_domain_edge("d-1", "example.com"))
    sql, _ = conn.sql_matching("edge_status = 'failed'")[0]
    assert "cf_tenant_id IS NULL" in sql


# ── which hostnames go on the certificate ────────────────────────────────────

def test_registered_domain_gets_www_because_we_set_both_records(monkeypatch):
    conn = FakeConn([{"kind": "register"}])
    edge = FakeEdge()
    _patch(monkeypatch, conn, FakePorkbun(), edge)
    asyncio.run(mod.provision_domain_edge("d-1", "example.com"))
    assert edge.created == [("example.com", True)]


def test_connected_domain_gets_exactly_the_host_the_tenant_connected(monkeypatch):
    """CloudFront validates EVERY name on a managed certificate. `www.` of a BYO
    host (which may itself be `shop.example.com`) is a name nobody pointed, and
    it holds the whole certificate at pending-validation forever."""
    conn = FakeConn([{"kind": "connect"}])
    edge = FakeEdge()
    _patch(monkeypatch, conn, FakePorkbun(), edge)
    asyncio.run(mod.provision_domain_edge("d-1", "shop.example.com"))
    assert edge.created == [("shop.example.com", False)]


# ── retry ────────────────────────────────────────────────────────────────────

def _retry_row(**over):
    row = {"id": "d-1", "kind": "register", "domain": "example.com",
           "cf_tenant_id": None, "edge_status": "failed"}
    row.update(over)
    return row


def test_retry_ignores_a_domain_that_is_not_active(monkeypatch):
    conn = FakeConn([None])
    pb, edge = FakePorkbun(), FakeEdge()
    _patch(monkeypatch, conn, pb, edge)
    assert asyncio.run(mod.retry_domain_edge("d-1")) == "none"
    assert "status = 'active'" in conn.fetchrow_sql[0][0]
    assert edge.created == []


def test_retry_provisions_a_domain_that_never_got_a_tenant(monkeypatch):
    """`active` + `none`: the background task died, or the domain predates the
    edge. Previously the sweeper ignored it and the UI offered no button."""
    conn = FakeConn([_retry_row(edge_status="none"), EDGE_CLAIM])
    pb, edge = FakePorkbun(), FakeEdge()
    _patch(monkeypatch, conn, pb, edge)
    assert asyncio.run(mod.retry_domain_edge("d-1")) == "pending_dns"
    assert pb.pointed == [("example.com", "d123.cloudfront.net")]


def test_retry_replaces_a_tenant_whose_certificate_died(monkeypatch):
    """The old retry only acted when cf_tenant_id IS NULL, so a failed
    certificate — the commonest failure — could never be retried."""
    conn = FakeConn([_retry_row(cf_tenant_id="dt-dead"), EDGE_CLAIM])
    pb, edge = FakePorkbun(), FakeEdge()
    _patch(monkeypatch, conn, pb, edge)

    assert asyncio.run(mod.retry_domain_edge("d-1")) == "pending_dns"
    assert edge.deleted == ["dt-dead"]
    cleared = conn.sql_matching("SET cf_tenant_id = NULL")
    assert cleared and "edge_status = 'failed'" in cleared[0][0]
    assert edge.created == [("example.com", True)]


@pytest.mark.parametrize("state", ["pending_dns", "provisioning", "live"])
def test_retry_never_touches_a_healthy_or_validating_tenant(monkeypatch, state):
    conn = FakeConn([_retry_row(cf_tenant_id="dt-1", edge_status=state)])
    pb, edge = FakePorkbun(), FakeEdge()
    _patch(monkeypatch, conn, pb, edge)
    assert asyncio.run(mod.retry_domain_edge("d-1")) == state
    assert edge.deleted == [] and edge.created == []


def test_retry_keeps_the_pointer_when_the_dead_tenant_cannot_be_deleted(monkeypatch):
    conn = FakeConn([_retry_row(cf_tenant_id="dt-dead")])
    edge = FakeEdge()
    edge.delete_exc = CappeEdgeError("AccessDenied")
    _patch(monkeypatch, conn, FakePorkbun(), edge)
    assert asyncio.run(mod.retry_domain_edge("d-1")) == "failed"
    assert conn.sql_matching("SET cf_tenant_id = NULL") == []
    assert edge.created == []


def test_retry_never_edits_dns_for_a_byo_domain(monkeypatch):
    """A connected domain's DNS lives at the tenant's own registrar."""
    conn = FakeConn([_retry_row(kind="connect", edge_status="none"), {"kind": "connect"}])
    pb, edge = FakePorkbun(), FakeEdge()
    _patch(monkeypatch, conn, pb, edge)
    assert asyncio.run(mod.retry_domain_edge("d-1")) == "pending_dns"
    assert pb.pointed == []
