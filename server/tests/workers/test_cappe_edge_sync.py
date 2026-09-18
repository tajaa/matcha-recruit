"""Edge sync — a custom domain goes live only once its certificate exists.

This task owns the one write that publishes a custom domain:
`cappe_sites.custom_domain`. Registration and BYO verification deliberately stop
at `edge_status='pending_dns'`, because setting `custom_domain` before the
CloudFront managed certificate is issued is exactly what served every visitor a
TLS name-mismatch interstitial (audit O4).

Run from server/:  ./venv/bin/python -m pytest tests/workers/test_cappe_edge_sync.py -q
"""
import asyncio
import os

os.environ.setdefault("LIVE_API", "test-key")
os.environ.setdefault("DATABASE_URL", "postgresql://test:test@localhost/test")
os.environ.setdefault("JWT_SECRET_KEY", "test-secret-key-cappe")


from app.cappe.services.cloudfront_tenants import CappeEdgeError, CappeEdgeNotFound  # noqa: E402
from app.workers.tasks import cappe_edge_sync as mod  # noqa: E402

ROW = {"id": "d-1", "site_id": "s-1", "domain": "example.com", "cf_tenant_id": "dt-1"}


class FakeTx:
    async def __aenter__(self):
        return self

    async def __aexit__(self, *exc):
        return False


class FakeConn:
    def __init__(self, pending=(), stale=(), orphans=(), raise_on=None):
        self._queues = [list(pending), list(orphans), list(stale)]
        self.executed = []
        self.closed = False
        # substring of SQL → exception to raise the first time it is executed
        self._raise_on = dict(raise_on or {})

    async def fetch(self, sql, *args):
        return self._queues.pop(0) if self._queues else []

    async def execute(self, sql, *args):
        for needle, exc in list(self._raise_on.items()):
            if needle in sql:
                del self._raise_on[needle]
                raise exc
        self.executed.append((sql, args))

    def transaction(self):
        return FakeTx()

    async def close(self):
        self.closed = True

    def sql_matching(self, needle):
        return [e for e in self.executed if needle in e[0]]


class FakeEdge:
    def __init__(self, status=None, delete_exc=None):
        self._status = status
        self._delete_exc = delete_exc
        self.deleted = []

    async def tenant_status(self, tenant_id):
        if isinstance(self._status, Exception):
            raise self._status
        return self._status

    async def delete_tenant(self, tenant_id):
        if self._delete_exc:
            raise self._delete_exc
        self.deleted.append(tenant_id)


def _patch(monkeypatch, conn, edge, *, enabled=True, cap=50, feature_on=True):
    async def _get_conn():
        return conn

    async def _setting(_c, key):
        assert key == "cappe_edge_sync"
        return None if enabled is None else {"enabled": enabled, "max_per_cycle": cap}

    async def _invalidate(site_id):
        return None

    monkeypatch.setattr(mod, "get_db_connection", _get_conn)
    monkeypatch.setattr(mod, "scheduler_settings_row", _setting)
    class _Settings:
        cappe_custom_domains_enabled = feature_on

    adopted = []

    async def _retry(domain_id):
        adopted.append(domain_id)
        return "pending_dns"

    monkeypatch.setattr(mod, "get_cloudfront_tenants", lambda: edge)
    monkeypatch.setattr(mod, "invalidate_site_render_cache", _invalidate)
    monkeypatch.setattr(mod, "get_settings", lambda: _Settings)
    monkeypatch.setattr(mod, "retry_domain_edge", _retry)
    return adopted


# ── scheduler gate ───────────────────────────────────────────────────────────

def test_disabled_scheduler_does_nothing(monkeypatch):
    conn = FakeConn()
    _patch(monkeypatch, conn, FakeEdge(), enabled=False)
    assert asyncio.run(mod._run()) == {"skipped": True}
    assert conn.executed == []
    assert conn.closed


# ── going live ───────────────────────────────────────────────────────────────

def test_live_certificate_publishes_the_custom_domain(monkeypatch):
    conn = FakeConn(pending=[ROW])
    _patch(monkeypatch, conn, FakeEdge(status=("live", "")))
    out = asyncio.run(mod._run())
    assert out["checked"] == 1 and out["live"] == 1

    # THE publish: the renderer starts answering for this host only here.
    publish = conn.sql_matching("UPDATE cappe_sites SET custom_domain = $1")
    assert len(publish) == 1
    assert publish[0][1] == ("example.com", "s-1")
    assert conn.sql_matching("edge_status = 'live'")


def test_pending_dns_does_not_publish_the_domain(monkeypatch):
    """The resting state while the owner's DNS has not propagated — publishing
    here is what produced the certificate-error page."""
    conn = FakeConn(pending=[ROW])
    _patch(monkeypatch, conn, FakeEdge(status=("pending_dns", "waiting for DNS")))
    out = asyncio.run(mod._run())
    assert out["pending_dns"] == 1
    assert conn.sql_matching("UPDATE cappe_sites SET custom_domain = $1") == []


def test_failed_certificate_records_the_reason_without_publishing(monkeypatch):
    conn = FakeConn(pending=[ROW])
    _patch(monkeypatch, conn, FakeEdge(status=("failed", "certificate validation-timed-out")))
    out = asyncio.run(mod._run())
    assert out["failed"] == 1
    assert conn.sql_matching("UPDATE cappe_sites SET custom_domain = $1") == []
    failed = conn.sql_matching("edge_status = 'failed'")
    assert "validation-timed-out" in failed[0][1][1]


def test_transient_aws_error_leaves_the_status_alone_for_the_next_cycle(monkeypatch):
    conn = FakeConn(pending=[ROW])
    _patch(monkeypatch, conn, FakeEdge(status=CappeEdgeError("throttled")))
    out = asyncio.run(mod._run())
    assert out["error"] == 1
    # Only the timestamp moves — a blip must not mark a healthy domain failed.
    assert conn.sql_matching("SET edge_checked_at = NOW() WHERE id = $1")
    assert conn.sql_matching("edge_status = 'failed'") == []


def test_tenant_deleted_in_the_console_clears_the_pointer(monkeypatch):
    """Polling a tenant id that will never answer again is a dead loop; clearing
    it lets the retry endpoint recreate the tenant."""
    conn = FakeConn(pending=[ROW])
    _patch(monkeypatch, conn, FakeEdge(status=CappeEdgeNotFound("gone")))
    out = asyncio.run(mod._run())
    assert out["failed"] == 1
    cleared = conn.sql_matching("cf_tenant_id = NULL")
    assert cleared and "no longer exists" in cleared[0][0]


# ── teardown ─────────────────────────────────────────────────────────────────

def test_expired_domain_is_detached_and_unpublished(monkeypatch):
    edge = FakeEdge()
    conn = FakeConn(stale=[ROW])
    _patch(monkeypatch, conn, edge)
    out = asyncio.run(mod._run())

    assert out["detached"] == 1
    assert edge.deleted == ["dt-1"]
    unpublish = conn.sql_matching("UPDATE cappe_sites SET custom_domain = NULL")
    assert unpublish and unpublish[0][1] == ("s-1", "example.com")


def test_teardown_failure_does_not_clear_the_pointer(monkeypatch):
    """Clearing cf_tenant_id after a failed delete would orphan a tenant that
    still answers on our certificate and still bills us."""
    conn = FakeConn(stale=[ROW])
    _patch(monkeypatch, conn, FakeEdge(delete_exc=CappeEdgeError("AccessDenied")))
    out = asyncio.run(mod._run())
    assert out["detached"] == 0
    assert conn.sql_matching("cf_tenant_id = NULL, edge_status = 'none'") == []


def test_unpublish_only_clears_this_domain(monkeypatch):
    """Guarded on `custom_domain = $2` so detaching an old domain can't wipe a
    newer one the site has since connected."""
    conn = FakeConn(stale=[ROW])
    _patch(monkeypatch, conn, FakeEdge())
    asyncio.run(mod._run())
    sql, _ = conn.sql_matching("UPDATE cappe_sites SET custom_domain = NULL")[0]
    assert "custom_domain = $2" in sql


def test_a_requested_transfer_does_not_take_the_site_offline(monkeypatch):
    """Transfers take days and may never complete. Tearing down on the click
    left the site dark for the whole window with no way to cancel."""
    conn = FakeConn()
    _patch(monkeypatch, conn, FakeEdge())
    seen = []
    orig = conn.fetch

    async def _fetch(sql, *args):
        seen.append(sql)
        return await orig(sql, *args)

    conn.fetch = _fetch
    asyncio.run(mod._run())
    teardown_sql = [q for q in seen if "status = 'expired'" in q]
    assert len(teardown_sql) == 1
    assert "transfer_requested" not in teardown_sql[0]


# ── one bad row must not starve the rest ─────────────────────────────────────

def test_custom_domain_collision_is_recorded_not_raised(monkeypatch):
    """cappe_sites.custom_domain is UNIQUE. The violation used to escape the
    sweep; with `edge_checked_at NULLS FIRST` that row sorted first again next
    run and blocked every other domain for good."""
    import asyncpg

    other = dict(ROW, id="d-2", site_id="s-2", domain="other.example.com")
    conn = FakeConn(
        pending=[ROW, other],
        raise_on={"UPDATE cappe_sites SET custom_domain = $1": asyncpg.UniqueViolationError("dup")},
    )
    _patch(monkeypatch, conn, FakeEdge(status=("live", "")))
    out = asyncio.run(mod._run())

    assert out["checked"] == 2
    assert out["failed"] == 1 and out["live"] == 1      # the second domain still went live
    failed = conn.sql_matching("Another site is already published")
    assert failed and failed[0][1] == ("d-1",)


def test_unexpected_exception_bumps_the_timestamp_and_continues(monkeypatch):
    other = dict(ROW, id="d-2", domain="other.example.com")
    conn = FakeConn(
        pending=[ROW, other],
        raise_on={"SET edge_status = 'live'": RuntimeError("connection reset")},
    )
    _patch(monkeypatch, conn, FakeEdge(status=("live", "")))
    out = asyncio.run(mod._run())

    assert out["error"] == 1 and out["live"] == 1
    bumped = [e for e in conn.executed if e[0].startswith("UPDATE cappe_domains SET edge_checked_at = NOW()")]
    assert bumped and bumped[0][1] == ("d-1",)          # so it cannot sort first forever


# ── adoption ─────────────────────────────────────────────────────────────────

def test_active_domain_with_no_tenant_is_adopted(monkeypatch):
    conn = FakeConn(orphans=[{"id": "d-9", "site_id": "s-9", "domain": "legacy.example.com"}])
    adopted = _patch(monkeypatch, conn, FakeEdge())
    out = asyncio.run(mod._run())
    assert out["adopted"] == 1
    assert adopted == ["d-9"]


def test_nothing_is_adopted_while_the_feature_is_off(monkeypatch):
    """With the feature off there is no tenant distribution to attach to."""
    conn = FakeConn(stale=[])
    adopted = _patch(monkeypatch, conn, FakeEdge(), feature_on=False)
    # only two fetches happen (pending, stale): drop the orphan queue slot
    conn._queues = [[], []]
    out = asyncio.run(mod._run())
    assert out["adopted"] == 0 and adopted == []

