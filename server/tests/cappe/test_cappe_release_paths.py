"""Releasing an order, a domain, or a DNS zone — without leaving something live
behind it.

Second review round on PR #544. The common shape: a release path let go of our
side (stock, slots, billing) while the other side stayed open — a payable Stripe
session, a renewing Porkbun registration, an A record beside the new ALIAS.

Run from server/:  ./venv/bin/python -m pytest tests/cappe/test_cappe_release_paths.py -q
"""
import asyncio
import os
from types import SimpleNamespace

os.environ.setdefault("LIVE_API", "test-key")
os.environ.setdefault("DATABASE_URL", "postgresql://test:test@localhost/test")
os.environ.setdefault("JWT_SECRET_KEY", "test-secret-key-cappe")

import pytest  # noqa: E402
from fastapi import HTTPException  # noqa: E402

from app.cappe.routes import shop as shop_mod  # noqa: E402
from app.cappe.routes.public import messages as messages_mod  # noqa: E402
from app.cappe.models.cappe import CappeMessageCreate  # noqa: E402
from app.cappe.services import inventory as inv_mod  # noqa: E402
from app.cappe.services import porkbun as porkbun_mod  # noqa: E402
from app.cappe.services.stripe_connect import CappeStripeError  # noqa: E402
from app.workers.tasks import cappe_domain_renewals as renewals_mod  # noqa: E402

SITE, ORDER, ACCOUNT_ID = "site-1", "order-1", "acct-row-1"


class ConnCtx:
    def __init__(self, conn):
        self.conn = conn

    async def __aenter__(self):
        return self.conn

    async def __aexit__(self, *exc):
        return False


# ── shop: the payment page closes before the order is let go ─────────────────

class OneRow:
    def __init__(self, row):
        self.row = row

    async def fetchrow(self, sql, *args):
        return self.row


class Stripe:
    def __init__(self, outcome):
        self.outcome, self.expired = outcome, []

    async def expire_checkout_session(self, account_id, session_id):
        self.expired.append((account_id, session_id))
        if isinstance(self.outcome, Exception):
            raise self.outcome
        return self.outcome


def _close(monkeypatch, row, outcome="expired"):
    stripe = Stripe(outcome)
    monkeypatch.setattr(shop_mod, "get_connection", lambda: ConnCtx(OneRow(row)))
    monkeypatch.setattr(shop_mod, "get_cappe_stripe", lambda: stripe)
    return stripe


PENDING = {"status": "pending", "stripe_session_id": "cs_1", "stripe_account_id": "acct_1"}


def test_open_session_is_expired_before_release(monkeypatch):
    stripe = _close(monkeypatch, PENDING)
    assert asyncio.run(shop_mod._close_open_checkout(SITE, ORDER, ACCOUNT_ID)) is None
    assert stripe.expired == [("acct_1", "cs_1")]


def test_completed_checkout_blocks_the_release(monkeypatch):
    """The buyer already paid (or an ACH debit is settling). Releasing now is
    what produced charged-but-cancelled orders."""
    _close(monkeypatch, PENDING, "complete")
    with pytest.raises(HTTPException) as exc:
        asyncio.run(shop_mod._close_open_checkout(SITE, ORDER, ACCOUNT_ID))
    assert exc.value.status_code == 409


def test_stripe_outage_leaves_the_order_untouched(monkeypatch):
    _close(monkeypatch, PENDING, CappeStripeError("timeout"))
    with pytest.raises(HTTPException) as exc:
        asyncio.run(shop_mod._close_open_checkout(SITE, ORDER, ACCOUNT_ID))
    assert exc.value.status_code == 502


@pytest.mark.parametrize("row", [
    None,                                                      # not this owner's order
    {**PENDING, "status": "paid"},                             # refunding a paid order
    {**PENDING, "stripe_session_id": None},                    # never went to Stripe
    {**PENDING, "stripe_account_id": None},
])
def test_nothing_to_close_is_a_no_op(monkeypatch, row):
    stripe = _close(monkeypatch, row)
    asyncio.run(shop_mod._close_open_checkout(SITE, ORDER, ACCOUNT_ID))
    assert stripe.expired == []


class OrderConn:
    def __init__(self, rows):
        self.rows, self.sql = list(rows), []

    async def fetchrow(self, sql, *args):
        self.sql.append(sql)
        return self.rows.pop(0)

    async def fetch(self, sql, *args):
        return []

    def transaction(self):
        return ConnCtx(self)


ORDER_ROW = {"id": ORDER, "status": "declined"}


def _route(monkeypatch, conn):
    log = []

    async def _owned(_conn, site_id, account_id):
        return {"id": site_id}

    async def _closed(site_id, order_id, account_id):
        log.append("close")

    async def _restock(_conn, *, site_id, order_id, reason):
        log.append(f"restock:{reason}")

    async def _bookings(_conn, *, order_id):
        log.append("bookings")
        return 1

    monkeypatch.setattr(shop_mod, "get_connection", lambda: ConnCtx(conn))
    monkeypatch.setattr(shop_mod, "get_owned_site", _owned)
    monkeypatch.setattr(shop_mod, "_close_open_checkout", _closed)
    monkeypatch.setattr(shop_mod, "restock_order", _restock)
    monkeypatch.setattr(shop_mod, "release_order_bookings", _bookings)
    monkeypatch.setattr(shop_mod, "_order_row", lambda order, items: dict(order))
    return log


def test_decline_closes_checkout_then_frees_stock_and_every_held_slot(monkeypatch):
    """The inline release this replaced freed only `pending` bookings, so a
    confirmed booking in a declined cart kept its slot off the calendar."""
    conn = OrderConn([ORDER_ROW])
    log = _route(monkeypatch, conn)
    asyncio.run(shop_mod.decline_order(
        SITE, ORDER, SimpleNamespace(reason="out of stock"), account=SimpleNamespace(id=ACCOUNT_ID),
    ))
    assert log == ["close", "restock:decline_restock", "bookings"]
    assert not any("cappe_bookings" in sql for sql in conn.sql)   # no inline release left


@pytest.mark.parametrize("new_status,closes", [
    ("cancelled", True), ("refunded", True), ("fulfilled", False), (None, False),
])
def test_only_a_releasing_transition_closes_checkout(monkeypatch, new_status, closes):
    conn = OrderConn([{"status": "pending"}, {"id": ORDER, "status": new_status or "pending"}])
    log = _route(monkeypatch, conn)
    monkeypatch.setattr(shop_mod, "build_patch", lambda *a, **k: (["status = $1"], [new_status]))
    asyncio.run(shop_mod.update_order_status(
        SITE, ORDER, SimpleNamespace(status=new_status, tracking_number=None), account=SimpleNamespace(id=ACCOUNT_ID),
    ))
    assert ("close" in log) is closes
    assert ("bookings" in log) is closes


# ── inventory: retake is the exact inverse of restock ────────────────────────

class StockConn:
    def __init__(self, items, balance):
        self.items, self.balance, self.updates = items, balance, []

    async def fetch(self, sql, *args):
        return self.items

    async def fetchval(self, sql, *args):
        self.updates.append((sql, args))
        return self.balance


def test_retake_decrements_product_and_variants_and_may_go_negative(monkeypatch):
    logged = []

    async def _log(conn, **kw):
        logged.append(kw)

    monkeypatch.setattr(inv_mod, "log_adjustment", _log)
    conn = StockConn(
        [{"product_id": "p-1", "quantity": 5, "selected_option_ids": ["opt-1"]}], balance=-2,
    )
    asyncio.run(inv_mod.retake_order_stock(conn, site_id=SITE, order_id=ORDER))

    assert "inventory = inventory - $1" in conn.updates[0][0]
    assert "cappe_product_options" in conn.updates[1][0]
    # No `inventory >= qty` guard: the buyer is charged, so the unit is owed.
    assert not any(">=" in sql for sql, _ in conn.updates)
    assert [(entry["delta"], entry["balance_after"], entry["reason"]) for entry in logged] == [
        (-5, -2, "sale"), (-5, -2, "sale"),
    ]


def test_retake_skips_untracked_stock(monkeypatch):
    logged = []

    async def _log(conn, **kw):
        logged.append(kw)

    monkeypatch.setattr(inv_mod, "log_adjustment", _log)
    conn = StockConn([{"product_id": "p-1", "quantity": 1, "selected_option_ids": None}], None)
    asyncio.run(inv_mod.retake_order_stock(conn, site_id=SITE, order_id=ORDER))
    assert logged == []          # inventory IS NULL = unlimited, nothing to record


# ── porkbun: repointing clears what already answers ──────────────────────────

class FakePorkbun(porkbun_mod.Porkbun):
    def __init__(self, records):
        self.records, self.deleted, self.created = records, [], []

    async def list_dns_records(self, domain):
        return self.records

    async def delete_dns_record(self, domain, record_id):
        self.deleted.append(record_id)

    async def create_dns_record(self, domain, *, record_type, name, content, **kw):
        self.created.append((record_type, name, content))


EDGE = "d123.cloudfront.net"


def test_legacy_a_record_and_www_cname_are_removed_first():
    """A domain registered before the edge existed: `A → app IP` beside the new
    ALIAS meant CloudFront's certificate never validated."""
    pb = FakePorkbun([
        {"id": "1", "name": "studio.example", "type": "A", "content": "203.0.113.10"},
        {"id": "2", "name": "www.studio.example", "type": "CNAME", "content": "studio.example"},
        {"id": "3", "name": "studio.example", "type": "MX", "content": "mail.example.net"},
        {"id": "4", "name": "studio.example", "type": "TXT", "content": "v=spf1 -all"},
        {"id": "5", "name": "shop.studio.example", "type": "A", "content": "203.0.113.11"},
    ])
    asyncio.run(pb.point_at_app("Studio.Example", EDGE))
    assert pb.deleted == ["1", "2"]                      # mail, TXT, other hosts untouched
    assert pb.created == [("ALIAS", "", EDGE), ("CNAME", "www", EDGE)]


def test_repointing_an_already_correct_zone_is_a_no_op():
    pb = FakePorkbun([
        {"id": "1", "name": "studio.example", "type": "ALIAS", "content": f"{EDGE}."},
        {"id": "2", "name": "www.studio.example", "type": "CNAME", "content": EDGE},
    ])
    asyncio.run(pb.point_at_app("studio.example", EDGE))
    assert pb.deleted == [] and pb.created == []


def test_repointing_without_an_endpoint_refuses():
    with pytest.raises(porkbun_mod.PorkbunError):
        asyncio.run(FakePorkbun([]).point_at_app("studio.example", ""))


# ── renewals: a domain that is leaving stops costing us ──────────────────────

class RenewConn:
    def __init__(self, lapsed, leaving):
        self.answers = [lapsed, leaving, []]   # lapse UPDATE, leaving SELECT, renewal SELECT
        self.sql = []

    async def fetch(self, sql, *args):
        self.sql.append(sql)
        return self.answers.pop(0)

    async def close(self):
        pass


def _renewals(monkeypatch, conn, *, fail=False):
    calls = []

    class PB:
        async def set_auto_renew(self, domain, enabled):
            calls.append((domain, enabled))
            if fail:
                raise porkbun_mod.PorkbunError("porkbun down")

    async def _conn():
        return conn

    async def _enabled(_conn, key, default=False):
        return True

    monkeypatch.setattr(renewals_mod, "get_db_connection", _conn)
    monkeypatch.setattr(renewals_mod, "scheduler_enabled", _enabled)
    monkeypatch.setattr(porkbun_mod, "get_porkbun", lambda: PB())
    return calls


def test_transfer_out_switches_porkbun_auto_renew_off(monkeypatch):
    """Porkbun renews BEFORE expiry, on our account. Nobody is paying us for a
    domain that is leaving, so it is switched off on entering the window — and
    again on lapse — not just when the row finally expires."""
    conn = RenewConn(
        lapsed=[{"domain": "gone.example", "kind": "register"},
                {"domain": "byo.example", "kind": "connect"}],
        leaving=[{"domain": "leaving.example"}],
    )
    calls = _renewals(monkeypatch, conn)
    out = asyncio.run(renewals_mod._dispatch_cappe_domain_renewals())

    assert sorted(calls) == [("gone.example", False), ("leaving.example", False)]
    assert out == {"renewed": 0, "failed": 0, "lapsed": 2}
    assert "RETURNING domain, kind" in conn.sql[0]
    assert "status = 'transfer_requested'" in conn.sql[1]


def test_porkbun_failure_does_not_abort_the_renewal_run(monkeypatch):
    conn = RenewConn(lapsed=[], leaving=[{"domain": "leaving.example"}])
    _renewals(monkeypatch, conn, fail=True)
    assert asyncio.run(renewals_mod._dispatch_cappe_domain_renewals())["lapsed"] == 0


# ── public replies: the pre-parse cap fits the model's own limit ─────────────

def test_longest_allowed_reply_fits_under_the_body_cap():
    limit = CappeMessageCreate.model_fields["body"].metadata
    max_chars = next(m.max_length for m in limit if hasattr(m, "max_length"))
    route = next(r for r in messages_mod.router.routes if "POST" in getattr(r, "methods", ()))
    worst_case = max_chars * 4 + 512          # 4-byte UTF-8 + JSON envelope
    assert type(route).max_body_bytes >= worst_case
