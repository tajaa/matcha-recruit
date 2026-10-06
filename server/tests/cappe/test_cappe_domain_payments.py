"""Domain money: purchase, renewal by hand, refunds, and the reconciler.

Findings from the 2026-10 payments review covered here:

  * the purchase route passed the caller's success/cancel URLs to Stripe
    verbatim (open redirect);
  * a refund that failed after a failed registration was log-only;
  * abandoned purchase rows never expired, and ANY existing row for a name —
    someone else's unpaid checkout included — blocked connecting it;
  * a domain refunded in Stripe stayed active and kept renewing;
  * there was no way to renew a domain once the automatic charge failed.

Run from server/:  ./venv/bin/python -m pytest tests/cappe/test_cappe_domain_payments.py -q
"""
import asyncio
import logging
import os
from types import SimpleNamespace
from uuid import UUID, uuid4

os.environ.setdefault("LIVE_API", "test-key")
os.environ.setdefault("DATABASE_URL", "postgresql://test:test@localhost/test")
os.environ.setdefault("JWT_SECRET_KEY", "test-secret-key-cappe")

import pytest  # noqa: E402
from fastapi import HTTPException  # noqa: E402

from app.cappe.models.domains import (  # noqa: E402
    CappeDomainConnectRequest,
    CappeDomainPurchaseRequest,
    CappeDomainRenewRequest,
)
from app.cappe.routes import domains as mod  # noqa: E402
from app.cappe.services import domain_register as reg  # noqa: E402
from app.cappe.services.email import dashboard_url  # noqa: E402
from app.cappe.services.stripe_connect import CappeStripeError  # noqa: E402
from app.core.services.porkbun import PorkbunError  # noqa: E402
from app.workers.tasks import cappe_domain_finalize as finalize_task  # noqa: E402

DID = UUID("33333333-3333-4333-8333-333333333333")
SITE = uuid4()
ACCOUNT = SimpleNamespace(id=uuid4(), email="owner@example.com")


class Settings:
    cappe_custom_domains_enabled = True
    cappe_cf_routing_endpoint = "d123.cloudfront.net"


class SqlConn:
    def __init__(self, answers=()):
        self.answers, self.calls = list(answers), []

    def _answer(self, kind, sql, args):
        self.calls.append((kind, sql, args))
        for needle, value in self.answers:
            if needle in sql:
                return value(sql, args) if callable(value) else value
        return None

    async def fetchrow(self, sql, *args):
        return self._answer("fetchrow", sql, args)

    async def fetchval(self, sql, *args):
        return self._answer("fetchval", sql, args)

    async def fetch(self, sql, *args):
        return self._answer("fetch", sql, args) or []

    async def execute(self, sql, *args):
        self._answer("execute", sql, args)

    async def close(self):
        self.closed = True

    def sql(self, needle):
        return [c for c in self.calls if needle in c[1]]


class Ctx:
    def __init__(self, conn):
        self.conn = conn

    async def __aenter__(self):
        return self.conn

    async def __aexit__(self, *exc):
        return False


class FakeStripe:
    def __init__(self, **over):
        self.sessions, self.refunds, self.expired = [], [], []
        self.create_exc = over.get("create_exc")
        self.refund_exc = over.get("refund_exc")
        self.pm = over.get("pm", "pm_card")
        self.pm_exc = over.get("pm_exc")
        self.expire_state = over.get("expire_state", "expired")
        self.session = over.get("session", {"payment_status": "unpaid"})

    async def create_platform_checkout_session(self, **kwargs):
        if self.create_exc:
            raise self.create_exc
        self.sessions.append(kwargs)
        return {"id": "cs_dom", "url": "https://checkout.example.com/dom"}

    async def payment_method_for_intent(self, payment_intent):
        if self.pm_exc:
            raise self.pm_exc
        return self.pm

    async def refund(self, payment_intent, *, idempotency_key=None):
        self.refunds.append((payment_intent, idempotency_key))
        if self.refund_exc:
            raise self.refund_exc
        return {"id": "re_dom"}

    async def expire_platform_checkout_session(self, session_id):
        self.expired.append(session_id)
        if isinstance(self.expire_state, Exception):
            raise self.expire_state
        return self.expire_state

    async def retrieve_platform_checkout_session(self, session_id):
        return self.session


class FakePorkbun:
    def __init__(self, available=True, exc=None):
        self.available, self.exc, self.auto_renew = available, exc, []

    async def check_domain(self, domain):
        return {"domain": domain, "available": self.available,
                "wholesale_cents": 1100, "retail_cents": 1600}

    async def set_auto_renew(self, domain, enabled):
        self.auto_renew.append((domain, enabled))
        if self.exc:
            raise self.exc


def _routes(monkeypatch, conn, stripe=None, porkbun=None):
    stripe, porkbun = stripe or FakeStripe(), porkbun or FakePorkbun()
    monkeypatch.setattr(mod, "get_settings", lambda: Settings())
    monkeypatch.setattr(mod, "get_connection", lambda: Ctx(conn))
    monkeypatch.setattr(mod, "get_cappe_stripe", lambda: stripe)
    monkeypatch.setattr(mod, "get_porkbun", lambda: porkbun)
    return stripe, porkbun


# ── purchase ─────────────────────────────────────────────────────────────────

def _purchase(conn, **over):
    body = CappeDomainPurchaseRequest(site_id=SITE, domain="studio.example", **over)
    return asyncio.run(mod.purchase_domain(body, account=ACCOUNT))


def _purchase_conn(held=None):
    return SqlConn([
        ("FROM cappe_sites WHERE id", 1),
        ("status = ANY($2::text[])", held),
        ("INSERT INTO cappe_domains", {"id": DID}),
    ])


def test_purchase_never_forwards_an_off_site_return_url_to_stripe(monkeypatch):
    """Stripe renders these as links on its own hosted page."""
    conn = _purchase_conn()
    stripe, _ = _routes(monkeypatch, conn)
    _purchase(conn, success_url="https://evil.test/phish", cancel_url="https://evil.test/again")
    sess = stripe.sessions[0]
    assert sess["success_url"] == dashboard_url(f"/sites/{SITE}?domain=success")
    assert sess["cancel_url"] == dashboard_url(f"/sites/{SITE}?domain=canceled")


def test_purchase_keeps_a_return_url_on_our_own_origin(monkeypatch):
    conn = _purchase_conn()
    stripe, _ = _routes(monkeypatch, conn)
    ours = dashboard_url("/sites/abc?tab=domains")
    _purchase(conn, success_url=ours, cancel_url=ours)
    assert stripe.sessions[0]["success_url"] == ours


def test_purchase_session_is_short_lived_and_saves_the_card(monkeypatch):
    conn = _purchase_conn()
    stripe, _ = _routes(monkeypatch, conn)
    out = _purchase(conn)
    sess = stripe.sessions[0]
    assert sess["save_card"] is True
    # A pending row is a claim on the name for as long as it can be paid.
    assert sess["expires_in_seconds"] == reg.PURCHASE_SESSION_SECONDS == 3600
    assert sess["metadata"] == {"type": "cappe_domain", "domain_id": str(DID)}
    assert out == {"domain_id": DID, "checkout_url": "https://checkout.example.com/dom"}
    assert conn.sql("SET stripe_session_id = $1")


def test_purchase_is_refused_for_a_name_that_is_really_held(monkeypatch):
    conn = _purchase_conn(held=1)
    stripe, _ = _routes(monkeypatch, conn)
    with pytest.raises(HTTPException) as exc:
        _purchase(conn)
    assert exc.value.status_code == 409
    assert stripe.sessions == [] and conn.sql("INSERT INTO cappe_domains") == []
    # Held means registering / active / transferring — never someone's pending.
    assert conn.sql("status = ANY($2::text[])")[0][2][1] == ["registering", "active", "transfer_requested"]


def test_purchase_rolls_its_row_back_when_checkout_cannot_open(monkeypatch):
    conn = _purchase_conn()
    _routes(monkeypatch, conn, stripe=FakeStripe(create_exc=CappeStripeError("down")))
    with pytest.raises(HTTPException) as exc:
        _purchase(conn)
    assert exc.value.status_code == 502
    assert conn.sql("DELETE FROM cappe_domains")


def test_purchase_of_an_unavailable_name_is_409(monkeypatch):
    conn = _purchase_conn()
    _routes(monkeypatch, conn, porkbun=FakePorkbun(available=False))
    with pytest.raises(HTTPException) as exc:
        _purchase(conn)
    assert exc.value.status_code == 409


# ── connect ──────────────────────────────────────────────────────────────────

def _connect(conn):
    body = CappeDomainConnectRequest(site_id=SITE, domain="studio.example")
    return asyncio.run(mod.connect_domain(body, account=ACCOUNT))


def test_someone_elses_pending_claim_does_not_block_connecting_a_domain(monkeypatch):
    """Any existing row used to 409 — so starting and abandoning a purchase
    locked the real owner out of their own domain."""
    new_row = {"id": DID, "domain": "studio.example", "status": "pending"}
    conn = SqlConn([
        ("FROM cappe_sites WHERE id", 1),
        ("AND kind = 'connect' AND status = 'pending'", None),   # no claim of our own
        ("status = ANY($2::text[])", None),                      # nothing HELD
        ("INSERT INTO cappe_domains", new_row),
    ])
    _routes(monkeypatch, conn)
    assert _connect(conn) == new_row


def test_a_held_domain_still_blocks_a_new_claim(monkeypatch):
    conn = SqlConn([
        ("FROM cappe_sites WHERE id", 1),
        ("status = ANY($2::text[])", 1),
    ])
    _routes(monkeypatch, conn)
    with pytest.raises(HTTPException) as exc:
        _connect(conn)
    assert exc.value.status_code == 409
    assert conn.sql("INSERT INTO cappe_domains") == []


def test_repeat_connect_clicks_reuse_our_own_pending_claim(monkeypatch):
    mine = {"id": DID, "domain": "studio.example", "status": "pending"}
    conn = SqlConn([
        ("FROM cappe_sites WHERE id", 1),
        ("AND kind = 'connect' AND status = 'pending'", mine),
    ])
    _routes(monkeypatch, conn)
    assert _connect(conn) == mine
    assert conn.sql("INSERT INTO cappe_domains") == []
    # Scoped to this account AND this site.
    assert conn.sql("AND kind = 'connect' AND status = 'pending'")[0][2] == (
        "studio.example", ACCOUNT.id, SITE,
    )


# ── renew by hand ────────────────────────────────────────────────────────────

def _renew_row(**over):
    row = {"id": DID, "site_id": SITE, "domain": "studio.example", "kind": "register",
           "status": "active", "retail_cents": 1600, "due": True}
    row.update(over)
    return row


def _renew(conn, **over):
    return asyncio.run(mod.renew_domain(DID, CappeDomainRenewRequest(**over), account=ACCOUNT))


def test_renew_opens_a_checkout_for_another_year_and_saves_the_card(monkeypatch):
    conn = SqlConn([("FROM cappe_domains WHERE id = $1 AND account_id = $2", _renew_row())])
    stripe, _ = _routes(monkeypatch, conn)
    out = _renew(conn, success_url="https://evil.test/x")
    sess = stripe.sessions[0]
    assert sess["metadata"] == {"type": "cappe_domain_renewal", "domain_id": str(DID)}
    assert sess["line_items"][0]["price_data"]["unit_amount"] == 1600
    assert sess["save_card"] is True
    # Same origin filter as the purchase.
    assert sess["success_url"] == dashboard_url(f"/sites/{SITE}") + "?domain=renewed"
    assert out["checkout_url"] == "https://checkout.example.com/dom"
    # Scoped to the caller's own account.
    assert conn.calls[0][2][:2] == (DID, ACCOUNT.id)


@pytest.mark.parametrize("row,code,fragment", [
    (None, 404, "not found"),
    (_renew_row(kind="connect"), 400, "your own registrar"),
    (_renew_row(status="expired"), 409, "Only an active domain"),
    (_renew_row(retail_cents=None), 409, "no renewal price"),
    (_renew_row(due=False), 409, "isn't due for renewal yet"),
])
def test_renew_refusals(monkeypatch, row, code, fragment):
    conn = SqlConn([("FROM cappe_domains WHERE id = $1 AND account_id = $2", row)])
    stripe, _ = _routes(monkeypatch, conn)
    with pytest.raises(HTTPException) as exc:
        _renew(conn)
    assert exc.value.status_code == code and fragment in exc.value.detail
    assert stripe.sessions == []


def test_renew_checkout_failure_is_a_502(monkeypatch):
    conn = SqlConn([("FROM cappe_domains WHERE id = $1 AND account_id = $2", _renew_row())])
    _routes(monkeypatch, conn, stripe=FakeStripe(create_exc=CappeStripeError("down")))
    with pytest.raises(HTTPException) as exc:
        _renew(conn)
    assert exc.value.status_code == 502


# ── platform webhook: a manual renewal settles ───────────────────────────────

def _renewal_meta():
    return {"type": "cappe_domain_renewal", "domain_id": str(DID)}


def _apply_renewal(event_type, obj):
    return asyncio.run(mod._apply_manual_renewal(event_type, obj, _renewal_meta()))


PAID = {"payment_status": "paid", "payment_intent": "pi_r", "customer": "cus_r"}


def test_a_paid_manual_renewal_extends_the_domain_and_replaces_the_saved_card(monkeypatch):
    conn = SqlConn([("UPDATE cappe_domains", {"domain": "studio.example"})])
    _stripe, porkbun = _routes(monkeypatch, conn)
    out = _apply_renewal("checkout.session.completed", PAID)
    assert out == {"received": True, "status": "renewed"}
    _, sql, args = conn.sql("UPDATE cappe_domains")[0]
    assert "+ INTERVAL '1 year'" in sql
    assert "renewal_failed_at = NULL" in sql and "renewal_notified_at = NULL" in sql
    assert "kind = 'register' AND status = 'active'" in sql
    assert args == (DID, "cus_r", "pm_card")
    # Our charge only recoups the registrar's renewal; Porkbun's own auto-renew
    # is what actually extends the registration.
    assert porkbun.auto_renew == [("studio.example", True)]


def test_a_renewal_paid_for_a_domain_that_lapsed_meanwhile_is_refunded(monkeypatch, caplog):
    conn = SqlConn([("UPDATE cappe_domains", None)])
    stripe, porkbun = _routes(monkeypatch, conn)
    with caplog.at_level(logging.ERROR, logger=mod.logger.name):
        out = _apply_renewal("checkout.session.completed", PAID)
    assert out == {"received": True, "status": "renewal_unapplied"}
    assert stripe.refunds == [("pi_r", "cappe-domain-renewal-unapplied-pi_r")]
    assert porkbun.auto_renew == []
    assert any("refunded automatically" in r.getMessage() for r in caplog.records)


def test_an_unapplied_renewal_whose_refund_fails_is_loud(monkeypatch, caplog):
    conn = SqlConn([("UPDATE cappe_domains", None)])
    _routes(monkeypatch, conn, stripe=FakeStripe(refund_exc=CappeStripeError("nope")))
    with caplog.at_level(logging.ERROR, logger=mod.logger.name):
        _apply_renewal("checkout.session.completed", PAID)
    assert any("MANUAL REFUND REQUIRED" in r.getMessage() for r in caplog.records)


def test_a_renewal_survives_the_payment_method_lookup_failing(monkeypatch):
    conn = SqlConn([("UPDATE cappe_domains", {"domain": "studio.example"})])
    _routes(monkeypatch, conn, stripe=FakeStripe(pm_exc=CappeStripeError("x")))
    assert _apply_renewal("checkout.session.completed", PAID)["status"] == "renewed"
    assert conn.sql("UPDATE cappe_domains")[0][2][2] is None


def test_a_renewal_whose_registrar_switch_fails_is_still_recorded_and_loud(monkeypatch, caplog):
    conn = SqlConn([("UPDATE cappe_domains", {"domain": "studio.example"})])
    _routes(monkeypatch, conn, porkbun=FakePorkbun(exc=PorkbunError("down")))
    with caplog.at_level(logging.ERROR, logger=mod.logger.name):
        assert _apply_renewal("checkout.session.completed", PAID)["status"] == "renewed"
    assert any("renew it at the registrar by hand" in r.getMessage() for r in caplog.records)


@pytest.mark.parametrize("event_type,obj,status", [
    ("checkout.session.completed", {"payment_status": "unpaid"}, "unpaid"),
    ("checkout.session.async_payment_failed", {}, "payment_failed"),
])
def test_an_unsettled_or_failed_renewal_changes_nothing(monkeypatch, event_type, obj, status):
    conn = SqlConn()
    _routes(monkeypatch, conn)
    assert _apply_renewal(event_type, obj) == {"received": True, "status": status}
    assert conn.calls == []


def test_a_renewal_event_without_a_domain_id_is_ignored(monkeypatch):
    conn = SqlConn()
    _routes(monkeypatch, conn)
    out = asyncio.run(mod._apply_manual_renewal("checkout.session.completed", PAID, {"domain_id": "x"}))
    assert out == {"received": True, "status": "ignored"}


# ── platform webhook: a refund made in Stripe ────────────────────────────────

def _charge(**over):
    obj = {"payment_intent": "pi_1", "amount": 1600, "amount_refunded": 1600, "refunded": True,
           "refunds": {"data": [{"id": "re_dash"}]}, "metadata": {}}
    obj.update(over)
    return obj


def test_a_refunded_active_domain_stops_renewing_but_is_not_torn_down(monkeypatch, caplog):
    """Before: it stayed `active` and Porkbun kept renewing it on our account."""
    row = {"id": DID, "domain": "studio.example", "kind": "register", "status": "active"}
    conn = SqlConn([("WHERE stripe_payment_intent = $1", row)])
    _stripe, porkbun = _routes(monkeypatch, conn)
    with caplog.at_level(logging.ERROR, logger=mod.logger.name):
        out = asyncio.run(mod._sync_platform_refund(_charge()))
    assert out == "domain_refunded"
    _, sql, args = conn.sql("WHERE stripe_payment_intent = $1")[0]
    assert "auto_renew = false" in sql and "refund_status = 'refunded'" in sql
    assert args == ("pi_1", "re_dash")
    assert porkbun.auto_renew == [("studio.example", False)]
    assert any("lapse at the end of its current term" in r.getMessage() for r in caplog.records)


def test_a_refund_before_registration_stops_the_registration(monkeypatch):
    """Otherwise finalize would still buy the name at Porkbun for a customer
    who has their money back."""
    row = {"id": DID, "domain": "studio.example", "kind": "register", "status": "failed"}
    conn = SqlConn([("WHERE stripe_payment_intent = $1", row)])
    _stripe, porkbun = _routes(monkeypatch, conn)
    asyncio.run(mod._sync_platform_refund(_charge()))
    sql = conn.sql("WHERE stripe_payment_intent = $1")[0][1]
    assert "WHEN status IN ('pending', 'registering') THEN 'failed'" in sql
    assert porkbun.auto_renew == []                # nothing registered to stop


def test_a_refunded_renewal_charge_is_found_by_its_metadata(monkeypatch):
    row = {"id": DID, "domain": "studio.example", "kind": "register", "status": "active"}
    conn = SqlConn([("WHERE id = $1 RETURNING", row)])
    _stripe, porkbun = _routes(monkeypatch, conn)
    out = asyncio.run(mod._sync_platform_refund(_charge(metadata=_renewal_meta())))
    assert out == "domain_refunded"
    assert conn.sql("WHERE id = $1 RETURNING")[0][2] == (DID,)
    assert porkbun.auto_renew == [("studio.example", False)]


@pytest.mark.parametrize("charge", [
    _charge(amount_refunded=400, refunded=False),       # a partial, goodwill refund
    _charge(payment_intent="pi_subscription"),           # not a domain's charge
    _charge(payment_intent=None, metadata={"type": "cappe_domain_renewal", "domain_id": "bad"}),
])
def test_refunds_that_are_not_a_full_domain_refund_are_left_to_billing(monkeypatch, charge):
    conn = SqlConn()
    _stripe, porkbun = _routes(monkeypatch, conn)
    assert asyncio.run(mod._sync_platform_refund(charge)) is None
    assert porkbun.auto_renew == []


def test_a_refund_survives_the_registrar_being_unreachable(monkeypatch):
    row = {"id": DID, "domain": "studio.example", "kind": "register", "status": "active"}
    conn = SqlConn([("WHERE stripe_payment_intent = $1", row)])
    _routes(monkeypatch, conn, porkbun=FakePorkbun(exc=PorkbunError("down")))
    assert asyncio.run(mod._sync_platform_refund(_charge())) == "domain_refunded"


class Request:
    headers = {"stripe-signature": "sig"}

    async def body(self):
        return b"{}"


def _webhook(monkeypatch, event):
    class Verifier(FakeStripe):
        async def verify_platform_webhook(self, payload, sig):
            return event

    async def _claim(event_id, event_type, consumer):
        return True

    async def _release(event_id, consumer):
        return None

    async def _billing(event_type, obj, event_at):
        return {"status": "ignored"}

    monkeypatch.setattr(mod, "get_cappe_stripe", lambda: Verifier())
    monkeypatch.setattr(mod, "claim_stripe_event", _claim)
    monkeypatch.setattr(mod, "release_stripe_event", _release)
    monkeypatch.setattr(mod, "dispatch_billing_event", _billing)
    return asyncio.run(mod.domains_webhook(Request(), SimpleNamespace(add_task=lambda *a: None)))


def test_the_webhook_routes_a_domain_refund_and_passes_other_refunds_on(monkeypatch):
    async def _domain(obj):
        return "domain_refunded"

    monkeypatch.setattr(mod, "_sync_platform_refund", _domain)
    event = {"id": "evt_1", "type": "charge.refunded", "data": {"object": _charge()}}
    assert _webhook(monkeypatch, event) == {"received": True, "status": "domain_refunded"}

    async def _not_a_domain(obj):
        return None

    monkeypatch.setattr(mod, "_sync_platform_refund", _not_a_domain)
    assert _webhook(monkeypatch, event) == {"received": True, "status": "ignored"}


def test_the_webhook_routes_a_manual_renewal(monkeypatch):
    async def _apply(event_type, obj, meta):
        return {"received": True, "status": "renewed"}

    monkeypatch.setattr(mod, "_apply_manual_renewal", _apply)
    event = {"id": "evt_2", "type": "checkout.session.completed",
             "data": {"object": {"metadata": _renewal_meta(), **PAID}}}
    assert _webhook(monkeypatch, event) == {"received": True, "status": "renewed"}


# ── begin_registration / refunds owed ────────────────────────────────────────

def _reg(monkeypatch, conn, stripe):
    monkeypatch.setattr(reg, "connection_or_direct", lambda: Ctx(conn))
    monkeypatch.setattr(reg, "get_cappe_stripe", lambda: stripe)


def test_begin_registration_records_the_card_next_years_renewal_will_charge(monkeypatch):
    conn = SqlConn([("UPDATE cappe_domains", {"id": DID})])
    _reg(monkeypatch, conn, FakeStripe())
    assert asyncio.run(reg.begin_registration(DID, "pi_1", "cus_1")) is True
    _, sql, args = conn.calls[0]
    assert "status = 'registering'" in sql and "WHERE id = $1 AND status = 'pending'" in sql
    assert "stripe_payment_method_id = $4" in sql
    assert args == (DID, "pi_1", "cus_1", "pm_card")


def test_begin_registration_is_false_for_a_row_no_longer_pending(monkeypatch):
    conn = SqlConn()
    _reg(monkeypatch, conn, FakeStripe())
    assert asyncio.run(reg.begin_registration(DID, "pi_1", "cus_1")) is False


def test_a_failed_card_lookup_does_not_strand_a_paid_registration(monkeypatch):
    conn = SqlConn([("UPDATE cappe_domains", {"id": DID})])
    _reg(monkeypatch, conn, FakeStripe(pm_exc=CappeStripeError("x")))
    assert asyncio.run(reg.begin_registration(DID, "pi_1", "cus_1")) is True
    assert conn.calls[0][2][3] is None


def test_a_refund_that_lands_is_recorded_with_its_id(monkeypatch):
    conn, stripe = SqlConn(), FakeStripe()
    _reg(monkeypatch, conn, stripe)
    assert asyncio.run(reg.refund_failed_registration(DID, "pi_1")) is True
    # Keyed, so a retry returns the first refund instead of attempting another.
    assert stripe.refunds == [("pi_1", f"cappe-domain-refund-{DID}")]
    _, sql, args = conn.calls[0]
    assert "refund_status = 'refunded'" in sql and args == (DID, "re_dom")


def test_a_refund_that_fails_is_marked_owed_not_just_logged(monkeypatch, caplog):
    conn, stripe = SqlConn(), FakeStripe(refund_exc=CappeStripeError("balance"))
    _reg(monkeypatch, conn, stripe)
    with caplog.at_level(logging.ERROR, logger=reg.logger.name):
        assert asyncio.run(reg.refund_failed_registration(DID, "pi_1")) is False
    sql = conn.calls[0][1]
    assert "refund_status = 'owed'" in sql
    assert "refund_status IS DISTINCT FROM 'refunded'" in sql     # never un-refund
    assert any("will retry" in r.getMessage() for r in caplog.records)


# ── abandoned purchases ──────────────────────────────────────────────────────

def test_an_abandoned_purchase_is_closed_at_stripe_then_removed(monkeypatch):
    conn, stripe = SqlConn(), FakeStripe()
    _reg(monkeypatch, conn, stripe)
    assert asyncio.run(reg.reap_abandoned_purchase(DID, "cs_1")) == "deleted"
    assert stripe.expired == ["cs_1"]                    # closed FIRST
    _, sql, args = conn.calls[0]
    assert sql.startswith("DELETE FROM cappe_domains")
    assert "kind = 'register' AND status = 'pending'" in sql and args == (DID,)


def test_a_purchase_with_no_session_is_just_removed(monkeypatch):
    conn, stripe = SqlConn(), FakeStripe()
    _reg(monkeypatch, conn, stripe)
    assert asyncio.run(reg.reap_abandoned_purchase(DID, None)) == "deleted"
    assert stripe.expired == []


def test_a_paid_purchase_whose_webhook_was_lost_is_registered_not_deleted(monkeypatch):
    conn = SqlConn([("UPDATE cappe_domains", {"id": DID})])
    stripe = FakeStripe(expire_state="complete",
                        session={"payment_status": "paid", "payment_intent": "pi_1", "customer": "cus_1"})
    _reg(monkeypatch, conn, stripe)
    finalized = []

    async def _finalize(domain_id):
        finalized.append(domain_id)

    monkeypatch.setattr(reg, "finalize_domain_registration", _finalize)
    assert asyncio.run(reg.reap_abandoned_purchase(DID, "cs_1")) == "paid"
    assert finalized == [DID]
    assert conn.sql("DELETE") == []


def test_a_purchase_still_settling_is_left_alone(monkeypatch):
    conn = SqlConn()
    _reg(monkeypatch, conn, FakeStripe(expire_state="complete"))
    assert asyncio.run(reg.reap_abandoned_purchase(DID, "cs_1")) == "settling"
    assert conn.calls == []


def test_stripe_being_unreachable_defers_the_reap(monkeypatch):
    conn = SqlConn()
    _reg(monkeypatch, conn, FakeStripe(expire_state=CappeStripeError("timeout")))
    assert asyncio.run(reg.reap_abandoned_purchase(DID, "cs_1")) == "retry"
    assert conn.calls == []


# ── the reconciler task ──────────────────────────────────────────────────────

def _task(monkeypatch, conn, *, enabled=True):
    seen = {"finalized": [], "refunded": [], "reaped": []}

    async def _get_conn():
        return conn

    async def _setting(_conn, key):
        return {"enabled": enabled, "max_per_cycle": 7} if enabled is not None else None

    async def _finalize(domain_id):
        seen["finalized"].append(domain_id)

    async def _refund(domain_id, intent):
        seen["refunded"].append((domain_id, intent))
        return domain_id == "d-ok"

    async def _reap(domain_id, session_id):
        seen["reaped"].append((domain_id, session_id))
        if domain_id == "d-boom":
            raise RuntimeError("boom")
        return "deleted"

    monkeypatch.setattr(finalize_task, "get_db_connection", _get_conn)
    monkeypatch.setattr(finalize_task, "scheduler_settings_row", _setting)
    monkeypatch.setattr(finalize_task, "finalize_domain_registration", _finalize)
    monkeypatch.setattr(finalize_task, "refund_failed_registration", _refund)
    monkeypatch.setattr(finalize_task, "reap_abandoned_purchase", _reap)
    return seen


def test_the_reconciler_redrives_refunds_and_reaps(monkeypatch):
    conn = SqlConn([
        ("status = 'registering'", [{"id": "d-stuck"}]),
        ("refund_status = 'owed'", [{"id": "d-ok", "stripe_payment_intent": "pi_a"},
                                    {"id": "d-still", "stripe_payment_intent": "pi_b"}]),
        ("status = 'pending'", [{"id": "d-gone", "stripe_session_id": "cs_1"},
                                {"id": "d-boom", "stripe_session_id": "cs_2"}]),
    ])
    seen = _task(monkeypatch, conn)
    out = asyncio.run(finalize_task._run())
    assert seen["finalized"] == ["d-stuck"]
    assert seen["refunded"] == [("d-ok", "pi_a"), ("d-still", "pi_b")]
    assert out["refunds_owed"] == 2 and out["refunds_settled"] == 1
    # One row failing does not stop the rest, and is retried next cycle.
    assert out["abandoned"] == {"deleted": 1, "retry": 1}
    assert conn.closed
    abandoned_sql = conn.sql("status = 'pending'")[0][1]
    assert f"INTERVAL '{reg.PURCHASE_ABANDONED_AFTER}'" in abandoned_sql and "kind = 'register'" in abandoned_sql
    assert all(c[2] == (7,) for c in conn.calls)


@pytest.mark.parametrize("enabled", [False, None])
def test_the_reconciler_does_nothing_when_disabled(monkeypatch, enabled):
    conn = SqlConn()
    seen = _task(monkeypatch, conn, enabled=enabled)
    assert asyncio.run(finalize_task._run()) == {"skipped": True}
    assert conn.calls == [] and seen["finalized"] == []
