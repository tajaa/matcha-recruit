"""Follow-ups from the PR #544 review — one test per behaviour it asked for.

Run from server/:  ./venv/bin/python -m pytest tests/cappe/test_cappe_review_followups.py -q
"""
import asyncio
import inspect
import os

os.environ.setdefault("LIVE_API", "test-key")
os.environ.setdefault("DATABASE_URL", "postgresql://test:test@localhost/test")
os.environ.setdefault("JWT_SECRET_KEY", "test-secret-key-cappe")

import pytest  # noqa: E402

from app.cappe.routes import auth as auth_mod  # noqa: E402
from app.cappe.routes import clients as clients_mod  # noqa: E402
from app.cappe.routes import domains as domains_mod  # noqa: E402
from app.cappe.routes import newsletter as news_mod  # noqa: E402
from app.cappe.routes import payments as payments_mod  # noqa: E402
from app.cappe.routes import sites as sites_mod  # noqa: E402
from app.cappe.routes.public import newsletter as public_news  # noqa: E402
from app.cappe.services import inventory as inventory_mod  # noqa: E402
from app.cappe.services.email import app_origin  # noqa: E402
from app.cappe.services.render.sanitize import _safe_href  # noqa: E402
from tests._helpers.routes import iter_api_routes  # noqa: E402


# ── href sanitizer: every spelling of a protocol-relative URL ────────────────

@pytest.mark.parametrize("href", [
    "//evil.test/x",
    "/\\evil.test",          # browsers read `\` as `/`
    "\\\\evil.test",
    "/\\/evil.test",
    "/\t/evil.test",         # tab/CR/LF are stripped before URL parsing
    "/\n/evil.test",
    "/\r/evil.test",
    "\t//evil.test",
    "java\nscript:alert(1)",
])
def test_off_site_spellings_of_a_relative_href_are_refused(href):
    assert _safe_href(href) == "#"


@pytest.mark.parametrize("href", [
    "/", "/about", "/shop/item?x=1#top", "#section",
    "https://example.com/a", "mailto:a@example.com", "tel:+15550100",
])
def test_ordinary_links_survive(href):
    assert _safe_href(href) == href


# ── booking slots are released with the order ────────────────────────────────

class FetchConn:
    def __init__(self, rows):
        self.rows, self.sql = rows, None

    async def fetch(self, sql, *args):
        self.sql = sql
        return self.rows


def test_release_order_bookings_frees_only_live_holds():
    conn = FetchConn([{"id": "b-1"}, {"id": "b-2"}])
    freed = asyncio.run(inventory_mod.release_order_bookings(conn, order_id="o-1"))
    assert freed == 2
    # The double-book index covers exactly these two states; a completed or
    # declined booking is history, not a hold.
    assert "status IN ('pending', 'confirmed')" in conn.sql
    assert "status = 'cancelled'" in conn.sql
    assert "booking_id IS NOT NULL" in conn.sql


def test_owner_cancel_path_releases_bookings_too():
    from app.cappe.routes import shop as shop_mod

    src = inspect.getsource(shop_mod)
    branch = src.split("if should_restock(current[\"status\"], body.status):", 1)[1][:300]
    assert "release_order_bookings" in branch


# ── confirmation emails: budgeted, and sent by a worker ──────────────────────

class ValConn:
    def __init__(self, value):
        self.value, self.sql = value, None

    async def fetchval(self, sql, *args):
        self.sql = sql
        return self.value


def test_confirmation_budget_is_per_account_per_day():
    conn = ValConn(120)
    left = asyncio.run(clients_mod._confirmation_budget(conn, "acct-1"))
    assert left == clients_mod._CONFIRMATIONS_PER_DAY - 120
    assert "s.account_id = $1" in conn.sql           # across ALL the account's sites
    assert "INTERVAL '24 hours'" in conn.sql


def test_confirmation_budget_never_goes_negative():
    assert asyncio.run(clients_mod._confirmation_budget(ValConn(10_000), "acct-1")) == 0


def test_import_truncates_to_the_budget_and_reports_it():
    src = inspect.getsource(clients_mod.import_clients)
    assert "_confirmation_budget" in src
    assert "newsletter_capped" in src


def test_confirmations_are_not_sent_from_an_in_process_task():
    """A BackgroundTask dies with the container on the next blue/green swap,
    leaving rows pending_confirmation with no mail ever sent."""
    src = inspect.getsource(clients_mod)
    assert "background.add_task" not in src
    assert "run_cappe_subscribe_confirm" in src


class _ConfirmConn:
    def __init__(self, rows):
        self.rows, self.claims, self.executed = list(rows), [], []

    async def fetchval(self, sql, *a):
        return "Shop"

    async def fetchrow(self, sql, *a):
        self.claims.append((sql, a))
        return self.rows.pop(0)

    async def execute(self, sql, *a):
        self.executed.append((sql, a))

    async def close(self):
        pass


def _confirm_worker(monkeypatch, conn, send):
    from app.workers.tasks import cappe_subscribe_confirm as worker

    async def _conn():
        return conn

    monkeypatch.setattr(worker, "get_db_connection", _conn)
    monkeypatch.setattr(worker, "send_cappe_subscribe_confirm_email", send)
    monkeypatch.setattr(worker, "THROTTLE_SECONDS", 0)
    return worker


def test_confirmation_worker_claims_each_row_before_sending(monkeypatch):
    conn = _ConfirmConn([
        {"id": "s-1", "email": "a@example.com", "name": "A", "confirm_token": "t1"},
        {"id": "s-2", "email": "b@example.com", "name": None, "confirm_token": "t2"},
        None,
    ])
    sent = []

    async def _send(email, name, site_name, url):
        sent.append((email, url))
        return True

    worker = _confirm_worker(monkeypatch, conn, _send)
    assert asyncio.run(worker._run("site-1")) == {"sent": 2, "failed": 0}
    assert sent[0][0] == "a@example.com" and "t1" in sent[0][1]
    claim = conn.claims[0][0]
    assert "SET confirm_sent_at = NOW()" in claim
    assert "confirm_sent_at IS NULL" in claim          # never mailed twice
    assert "FOR UPDATE SKIP LOCKED" in claim           # overlapping runs don't collide
    assert conn.executed == []                          # nothing released


@pytest.mark.parametrize("outcome", ["returns_false", "raises"])
def test_failed_confirmation_releases_its_claim_for_retry(monkeypatch, outcome):
    """The sender reports failure by RETURNING False. Counting that as sent left
    the row claimed and `pending_confirmation` for ever — only unclaimed rows
    are ever picked up again."""
    conn = _ConfirmConn([
        {"id": "s-1", "email": "a@example.com", "name": "A", "confirm_token": "t1"},
        None,
    ])

    async def _send(email, name, site_name, url):
        if outcome == "raises":
            raise RuntimeError("provider down")
        return False

    worker = _confirm_worker(monkeypatch, conn, _send)
    assert asyncio.run(worker._run("site-1")) == {"sent": 0, "failed": 1}
    sql, args = conn.executed[0]
    assert "SET confirm_sent_at = NULL" in sql and args == ("s-1",)
    # ...and the released row is not re-claimed within the same run.
    assert conn.claims[1][1][1] == ["s-1"]
    assert "id <> ALL($2::uuid[])" in conn.claims[1][0]


def test_confirmation_run_stops_when_the_provider_is_down(monkeypatch):
    from app.workers.tasks import cappe_subscribe_confirm as worker_mod

    rows = [{"id": f"s-{i}", "email": f"p{i}@example.com", "name": None, "confirm_token": "t"}
            for i in range(20)]
    conn = _ConfirmConn(rows)

    async def _send(*a):
        return False

    worker = _confirm_worker(monkeypatch, conn, _send)
    out = asyncio.run(worker._run("site-1"))
    assert out == {"sent": 0, "failed": worker_mod.MAX_CONSECUTIVE_FAILURES}
    assert len(conn.executed) == worker_mod.MAX_CONSECUTIVE_FAILURES   # all released


def test_confirm_email_reports_delivery_and_keeps_the_address_out_of_logs(monkeypatch, caplog):
    from app.cappe.services import email as email_mod

    class Svc:
        def __init__(self, result):
            self.result = result

        async def send_email_with_fallback(self, **kw):
            if isinstance(self.result, Exception):
                raise self.result
            return self.result

    for result, expected in ((True, True), (False, False), (RuntimeError("smtp"), False)):
        monkeypatch.setattr(email_mod, "get_email_service", lambda r=result: Svc(r))
        got = asyncio.run(email_mod.send_cappe_subscribe_confirm_email(
            "pat@example.com", "Pat", "Shop", "https://example.com/c/t"))
        assert got is expected
    assert not any("pat@example.com" in r.getMessage() for r in caplog.records)


def test_confirmation_worker_is_registered_with_celery():
    from app.workers.celery_app import celery_app

    assert "app.workers.tasks.cappe_subscribe_confirm" in celery_app.conf.include


# ── the confirm link must not act on a GET ───────────────────────────────────

def test_consent_is_a_post_and_the_get_changes_nothing():
    """Mail scanners and link-preview bots GET every URL in a message. If the GET
    subscribed the address, imported contacts behind a scanner would "consent"
    without a human ever reading the email."""
    methods = {}
    for route in iter_api_routes(public_news.router):
        if route.path.endswith("/subscribe/confirm/{token}"):
            for m in route.methods:
                methods[m] = route.endpoint
    assert set(methods) >= {"GET", "POST"}
    assert "UPDATE" not in inspect.getsource(methods["GET"]).upper().split('"""', 2)[2]
    assert "SET status = 'subscribed'" in inspect.getsource(methods["POST"])


def test_confirm_page_renders_a_post_form_when_asked():
    page = public_news._confirm_page("Confirm", "msg", confirm_action="/x/y").body.decode()
    assert '<form method="post" action="/x/y">' in page
    assert "<form" not in public_news._confirm_page("Done", "msg").body.decode()


# ── recipient ceiling counts campaigns still in flight ───────────────────────

def test_daily_recipient_cap_charges_in_flight_campaigns():
    """recipient_count is 0 until the worker finalizes a campaign, so three
    back-to-back sends (3 x 5k) all cleared a 5k cap."""
    src = inspect.getsource(news_mod.send_campaign)
    assert "c.status = 'sending'" in src
    assert "sub.status = 'subscribed'" in src


# ── signup collision email ───────────────────────────────────────────────────

def test_account_exists_email_is_recipient_throttled_and_uses_the_stored_name():
    collision = inspect.getsource(auth_mod.signup).split("UniqueViolationError", 1)[1]
    assert "check_recipient_send_ok(email)" in collision
    assert "SELECT name FROM cappe_accounts WHERE email = $1" in collision
    # The request's name is attacker-typed text; it must never reach the email.
    assert "send_cappe_account_exists_email, email, body.name" not in collision


# ── Stripe return URLs: our ORIGIN is the boundary, not /cappe ───────────────

@pytest.mark.parametrize("path", [
    "/cappe/sites", "/gummfit/creators/dashboard", "/sites/abc", "",
])
def test_any_path_on_our_origin_is_a_valid_return_target(path):
    url = f"{app_origin()}{path}"
    assert payments_mod._own_dashboard_url(url) == url


@pytest.mark.parametrize("url", ["https://evil.test/", "//evil.test", None, ""])
def test_foreign_return_target_is_still_dropped(url):
    assert payments_mod._own_dashboard_url(url) is None


def test_lookalike_host_is_not_our_origin():
    assert payments_mod._own_dashboard_url(f"{app_origin()}.evil.test/x") is None


# ── domains ──────────────────────────────────────────────────────────────────

def test_concurrent_activation_is_caught_by_type_not_index_name():
    """Two partial unique indexes guard an active domain; string-matching the
    wrong name turned this race into a 500 instead of a 409."""
    src = inspect.getsource(domains_mod.verify_domain)
    assert "asyncpg.UniqueViolationError" in src
    assert "cappe_domains_domain_key" not in src


def test_transfer_request_can_be_cancelled():
    paths = {r.path for r in iter_api_routes(domains_mod.router)}
    assert "/domains/{domain_id}/transfer-request/cancel" in paths
    src = inspect.getsource(domains_mod.cancel_transfer_request)
    assert "status = 'active'" in src and "status = 'transfer_requested'" in src
    assert "account_id = $2" in src


def test_retry_route_no_longer_requires_a_missing_tenant():
    src = inspect.getsource(domains_mod.retry_edge)
    assert 'if not row["cf_tenant_id"]' not in src


def test_open_transfer_lapses_at_expiry_without_charging():
    from app.workers.tasks import cappe_domain_renewals as renewals

    src = inspect.getsource(renewals._dispatch_cappe_domain_renewals)
    assert "status = 'transfer_requested' AND expires_at IS NOT NULL AND expires_at < NOW()" in src
    # and it is still excluded from the charge query
    assert "status = 'active' AND auto_renew" in src


# ── site delete ──────────────────────────────────────────────────────────────

def test_site_delete_collects_tenants_before_the_cascade():
    src = inspect.getsource(sites_mod.delete_site)
    assert src.index("SELECT cf_tenant_id, domain FROM cappe_domains") < src.index("DELETE FROM cappe_sites")


class _TombConn:
    def __init__(self, rows=()):
        self.rows, self.executed = list(rows), []

    async def fetch(self, sql, *a):
        return self.rows

    async def execute(self, sql, *a):
        self.executed.append((sql, a))


class _TombCtx:
    def __init__(self, conn):
        self.conn = conn

    async def __aenter__(self):
        return self.conn

    async def __aexit__(self, *exc):
        return False


def test_failed_fast_path_cleanup_leaves_the_tombstone(monkeypatch):
    """CloudFront refuses to delete a tenant still deploying its disable. The
    tombstone written with the site delete is what survives that."""
    from app.cappe.services import cloudfront_tenants as cf

    class Edge:
        async def delete_tenant(self, tenant_id):
            raise cf.CappeEdgeError("tenant is still deploying")

    conn = _TombConn()
    monkeypatch.setattr(cf, "get_cloudfront_tenants", lambda: Edge())
    monkeypatch.setattr(sites_mod, "get_connection", lambda: _TombCtx(conn))
    asyncio.run(sites_mod._delete_edge_tenants([("dt-7", "example.com")]))
    assert conn.executed == []            # tombstone NOT cleared


def test_tenants_are_deleted_after_a_site_is_removed(monkeypatch):
    from app.cappe.services import cloudfront_tenants as cf

    deleted = []

    class Edge:
        async def delete_tenant(self, tenant_id):
            deleted.append(tenant_id)

    conn = _TombConn()
    monkeypatch.setattr(cf, "get_cloudfront_tenants", lambda: Edge())
    monkeypatch.setattr(sites_mod, "get_connection", lambda: _TombCtx(conn))
    asyncio.run(sites_mod._delete_edge_tenants([("dt-1", "a.example.com"), ("dt-2", "b.example.com")]))
    assert deleted == ["dt-1", "dt-2"]
    assert [a for _, a in conn.executed] == [("dt-1",), ("dt-2",)]
    assert all("DELETE FROM cappe_edge_tombstones" in sql for sql, _ in conn.executed)


def test_site_delete_records_tombstones_in_the_same_transaction():
    src = inspect.getsource(sites_mod.delete_site)
    assert "INSERT INTO cappe_edge_tombstones" in src
    assert "conn.transaction()" in src
    assert src.index("INSERT INTO cappe_edge_tombstones") < src.index("DELETE FROM cappe_sites")


def test_sweeper_retries_tombstones_until_cloudfront_lets_go():
    from app.cappe.services import cloudfront_tenants as cf
    from app.workers.tasks import cappe_edge_sync as sync

    class Edge:
        async def delete_tenant(self, tenant_id):
            if tenant_id == "dt-busy":
                raise cf.CappeEdgeError("still deploying")

    conn = _TombConn([
        {"cf_tenant_id": "dt-busy", "domain": "a.example.com", "attempts": 2},
        {"cf_tenant_id": "dt-gone", "domain": "b.example.com", "attempts": 0},
    ])
    assert asyncio.run(sync._drain_tombstones(conn, Edge(), 50)) == 1
    busy, gone = conn.executed
    assert "attempts = $2" in busy[0] and busy[1][:2] == ("dt-busy", 3)
    assert "DELETE FROM cappe_edge_tombstones" in gone[0] and gone[1] == ("dt-gone",)
