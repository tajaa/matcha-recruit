"""Platform subscription edges from the 2026-10 payments review.

  * The duplicate-subscription race cancelled the later subscription without
    refunding the invoice it had already collected — and made that Stripe call
    inside an open pooled transaction.
  * A failed plan upgrade returned 200 with the old plan, because the parked
    `pending_update` was never read. Add-on increases provisioned before their
    proration invoice cleared.
  * The $1 intro offer was per account only: the card-fingerprint column was
    never written.

Also here: the two domain-renewal emails.

Run from server/:  ./venv/bin/python -m pytest tests/cappe/test_cappe_billing_money_edges.py -q
"""
import asyncio
import logging
import os
from types import SimpleNamespace
from uuid import uuid4

os.environ.setdefault("LIVE_API", "test-key")
os.environ.setdefault("DATABASE_URL", "postgresql://test:test@localhost/test")
os.environ.setdefault("JWT_SECRET_KEY", "test-secret-key-cappe")

import pytest  # noqa: E402
from asyncpg.exceptions import UniqueViolationError  # noqa: E402
from fastapi import HTTPException  # noqa: E402

from app.cappe.routes import billing as routes  # noqa: E402
from app.cappe.services import billing as svc  # noqa: E402
from app.cappe.services import email as email_mod  # noqa: E402
from app.cappe.services.stripe_connect import CappeStripeError  # noqa: E402

ACCOUNT = uuid4()
SUB = {
    "id": "sub_dup", "status": "active", "customer": "cus_1", "latest_invoice": "in_dup",
    "items": {"data": [{"id": "si_1", "price": {"id": "price_1"}, "quantity": 1}]},
}
PRICE_ROWS = [{"stripe_price_id": "price_1", "price_id": uuid4(), "product_code": "business",
               "interval": "month", "kind": "plan"}]


class Tx:
    def __init__(self, conn):
        self.conn = conn

    async def __aenter__(self):
        self.conn.depth += 1
        return self

    async def __aexit__(self, *exc):
        self.conn.depth -= 1
        return False


class SyncConn:
    """Enough of a connection for `sync_subscription`'s insert path."""

    def __init__(self, *, insert_exc=None, existing_after=None):
        self.insert_exc, self.existing_after = insert_exc, existing_after
        self.depth, self.reads, self.executed = 0, 0, []
        self.open = True

    def transaction(self):
        return Tx(self)

    async def fetch(self, sql, *args):
        return PRICE_ROWS

    async def fetchrow(self, sql, *args):
        self.reads += 1
        return None if self.reads == 1 else self.existing_after

    async def fetchval(self, sql, *args):
        if "INSERT INTO cappe_subscriptions" in sql:
            if self.insert_exc:
                raise self.insert_exc
            return uuid4()
        return None

    async def execute(self, sql, *args):
        self.executed.append(sql)


def _violation(constraint):
    exc = UniqueViolationError("duplicate key")
    exc.constraint_name = constraint
    return exc


def _no_stripe(monkeypatch):
    def _boom():
        raise AssertionError("Stripe must not be called inside the transaction")

    monkeypatch.setattr(svc, "get_cappe_stripe", _boom)


# ── the duplicate-subscription race ──────────────────────────────────────────

def test_a_second_live_subscription_raises_instead_of_calling_stripe_in_the_transaction(monkeypatch):
    _no_stripe(monkeypatch)
    conn = SyncConn(insert_exc=_violation("uq_cappe_sub_live"))
    with pytest.raises(svc.DuplicateLiveSubscription) as exc:
        asyncio.run(svc.sync_subscription(conn, account_id=ACCOUNT, subscription=SUB))
    assert exc.value.stripe_subscription_id == "sub_dup"
    # The invoice it already collected travels with the exception, so the
    # resolver can refund it.
    assert exc.value.latest_invoice_id == "in_dup"


def test_a_concurrent_insert_of_the_same_subscription_is_not_a_duplicate(monkeypatch):
    """Cancelling here would hard-cancel the customer's only subscription."""
    _no_stripe(monkeypatch)
    existing_id = uuid4()
    conn = SyncConn(insert_exc=_violation("cappe_subscriptions_stripe_subscription_id_key"),
                    existing_after={"id": existing_id})
    assert asyncio.run(svc.sync_subscription(conn, account_id=ACCOUNT, subscription=SUB)) == existing_id


class Resolver:
    def __init__(self, cancel_exc=None, refund_exc=None):
        self.cancel_exc, self.refund_exc = cancel_exc, refund_exc
        self.cancelled, self.refunded = [], []

    async def cancel_subscription(self, sub_id, *, at_period_end=True):
        self.cancelled.append((sub_id, at_period_end))
        if self.cancel_exc:
            raise self.cancel_exc

    async def refund_invoice(self, invoice_id):
        self.refunded.append(invoice_id)
        if self.refund_exc:
            raise self.refund_exc
        return ["re_1"]


def _resolve(monkeypatch, caplog, resolver, invoice="in_dup"):
    monkeypatch.setattr(svc, "get_cappe_stripe", lambda: resolver)
    with caplog.at_level(logging.ERROR, logger=svc.logger.name):
        asyncio.run(svc.resolve_duplicate_subscription(svc.DuplicateLiveSubscription("sub_dup", invoice)))
    return " ".join(r.getMessage() for r in caplog.records)


def test_a_duplicate_is_cancelled_now_and_its_invoice_refunded(monkeypatch, caplog):
    """Cancelling alone kept the money the duplicate had already charged."""
    resolver = Resolver()
    log = _resolve(monkeypatch, caplog, resolver)
    assert resolver.cancelled == [("sub_dup", False)]
    assert resolver.refunded == ["in_dup"]
    assert "cancelled and invoice in_dup refunded" in log


def test_the_refund_is_still_attempted_when_the_cancel_fails(monkeypatch, caplog):
    resolver = Resolver(cancel_exc=CappeStripeError("down"))
    log = _resolve(monkeypatch, caplog, resolver)
    assert resolver.refunded == ["in_dup"]
    assert "CANCEL IT MANUALLY" in log


def test_a_failed_refund_of_a_duplicate_asks_for_a_human(monkeypatch, caplog):
    log = _resolve(monkeypatch, caplog, Resolver(refund_exc=CappeStripeError("down")))
    assert "MANUAL REFUND REQUIRED" in log


def test_a_duplicate_with_no_invoice_is_cancelled_and_flagged(monkeypatch, caplog):
    resolver = Resolver()
    log = _resolve(monkeypatch, caplog, resolver, invoice=None)
    assert resolver.cancelled and resolver.refunded == []
    assert "no invoice to refund" in log


class GcCtx:
    def __init__(self, conn):
        self.conn = conn

    async def __aenter__(self):
        return self.conn

    async def __aexit__(self, *exc):
        self.conn.open = False
        return False


def test_sync_tx_resolves_a_duplicate_only_after_the_connection_is_released(monkeypatch):
    conn = SyncConn()
    state = {}

    async def _sync(_conn, **kwargs):
        raise svc.DuplicateLiveSubscription("sub_dup", "in_dup")

    async def _resolve(dup):
        state["open_at_resolve"] = conn.open
        state["depth_at_resolve"] = conn.depth
        state["dup"] = dup.stripe_subscription_id

    monkeypatch.setattr(svc, "get_connection", lambda: GcCtx(conn))
    monkeypatch.setattr(svc, "sync_subscription", _sync)
    monkeypatch.setattr(svc, "resolve_duplicate_subscription", _resolve)
    assert asyncio.run(svc.sync_subscription_tx(ACCOUNT, SUB)) is None
    assert state == {"open_at_resolve": False, "depth_at_resolve": 0, "dup": "sub_dup"}


def test_sync_tx_runs_the_follow_up_in_the_same_transaction(monkeypatch):
    conn, sub_id, seen = SyncConn(), uuid4(), []

    async def _sync(_conn, **kwargs):
        return sub_id

    async def _after(_conn):
        seen.append(_conn.depth)

    monkeypatch.setattr(svc, "get_connection", lambda: GcCtx(conn))
    monkeypatch.setattr(svc, "sync_subscription", _sync)
    assert asyncio.run(svc.sync_subscription_tx(ACCOUNT, SUB, after=_after)) == sub_id
    assert seen == [1]


# ── pending updates: a declined change is not a successful no-op ─────────────

def test_pending_update_reason():
    assert svc.pending_update_reason({"id": "sub_1"}) is None
    assert svc.pending_update_reason({"id": "sub_1", "pending_update": None}) is None
    assert "card was declined" in svc.pending_update_reason({"pending_update": {"expires_at": 1}})


class RouteConn:
    def __init__(self, rows):
        self.rows = list(rows)

    async def fetchrow(self, sql, *args):
        return self.rows.pop(0)


class BillingStripe:
    def __init__(self, fresh):
        self.fresh, self.calls = fresh, []

    async def change_subscription_price(self, **kwargs):
        self.calls.append(("change", kwargs))

    async def add_subscription_item(self, **kwargs):
        self.calls.append(("add", kwargs))

    async def set_item_quantity(self, **kwargs):
        self.calls.append(("quantity", kwargs))

    async def remove_subscription_item(self, item_id):
        self.calls.append(("remove", item_id))

    async def retrieve_subscription(self, sub_id):
        return self.fresh


def _billing_route(monkeypatch, rows, fresh):
    account = SimpleNamespace(id=ACCOUNT, email="owner@example.com")
    stripe, synced = BillingStripe(fresh), []

    async def _current(_conn, account_id):
        return {"id": uuid4(), "source": "stripe", "stripe_subscription_id": "sub_1",
                "plan_code": "creator", "interval": "month", "status": "active"}

    async def _price(_conn, code, interval, role="standard"):
        return {"stripe_price_id": "price_new"}

    async def _sync(account_id, subscription, **_kw):
        synced.append(subscription)

    async def _response(account_id):
        return {"plan_code": "after"}

    monkeypatch.setattr(routes, "get_connection", lambda: GcCtx(SimpleNamespace(
        fetchrow=RouteConn(rows).fetchrow, open=True,
    )))
    monkeypatch.setattr(routes.billing_svc, "current_subscription", _current)
    monkeypatch.setattr(routes.billing_svc, "resolve_price", _price)
    monkeypatch.setattr(routes.billing_svc, "sync_subscription_tx", _sync)
    monkeypatch.setattr(routes, "get_cappe_stripe", lambda: stripe)
    monkeypatch.setattr(routes, "_subscription_response_or_409", _response)
    return account, stripe, synced


PLAN_ROWS = [{"code": "business", "status": "active", "kind": "plan"}, {"stripe_item_id": "si_plan"}]


def test_a_declined_upgrade_is_a_402_not_a_200_with_the_old_plan(monkeypatch):
    fresh = {"id": "sub_1", "pending_update": {"expires_at": 1}}
    account, stripe, synced = _billing_route(monkeypatch, PLAN_ROWS, fresh)
    with pytest.raises(HTTPException) as exc:
        asyncio.run(routes.change_plan(SimpleNamespace(plan_code="business", interval="month"), account=account))
    assert exc.value.status_code == 402 and "nothing was changed" in exc.value.detail
    # Local state was still synced (to the unchanged subscription) first.
    assert synced == [fresh]


def test_an_upgrade_that_took_effect_returns_the_new_subscription(monkeypatch):
    account, stripe, synced = _billing_route(monkeypatch, PLAN_ROWS, {"id": "sub_1"})
    out = asyncio.run(routes.change_plan(
        SimpleNamespace(plan_code="business", interval="month"), account=account,
    ))
    assert out == {"plan_code": "after"} and len(synced) == 1


ADDON_ROWS = [{"code": "mailbox", "name": "Mailbox", "max_quantity": 10}, None]


def test_an_add_on_whose_payment_failed_is_a_402_and_is_not_provisioned(monkeypatch):
    fresh = {"id": "sub_1", "pending_update": {"expires_at": 1}}
    account, stripe, synced = _billing_route(monkeypatch, ADDON_ROWS, fresh)
    with pytest.raises(HTTPException) as exc:
        asyncio.run(routes.set_addon_quantity(
            SimpleNamespace(addon_code="mailbox", quantity=2), account=account,
        ))
    assert exc.value.status_code == 402
    assert stripe.calls[0][0] == "add" and synced == [fresh]


def test_an_add_on_that_was_paid_for_goes_through(monkeypatch):
    account, _stripe, _synced = _billing_route(monkeypatch, ADDON_ROWS, {"id": "sub_1"})
    assert asyncio.run(routes.set_addon_quantity(
        SimpleNamespace(addon_code="mailbox", quantity=2), account=account,
    )) == {"plan_code": "after"}


# ── the intro offer's card fingerprint ───────────────────────────────────────

class FingerprintStripe:
    def __init__(self, fingerprint="fp_1", exc=None, sub=None):
        self.fingerprint, self.exc, self.sub, self.asked = fingerprint, exc, sub, []

    async def card_fingerprint(self, pm):
        self.asked.append(pm)
        if self.exc:
            raise self.exc
        return self.fingerprint

    async def retrieve_subscription(self, sub_id):
        return self.sub


@pytest.mark.parametrize("pm,asked", [("pm_1", ["pm_1"]), ({"id": "pm_obj"}, ["pm_obj"]), (None, []), ("", [])])
def test_intro_card_fingerprint_reads_the_subscriptions_card(monkeypatch, pm, asked):
    stripe = FingerprintStripe()
    monkeypatch.setattr(svc, "get_cappe_stripe", lambda: stripe)
    out = asyncio.run(svc._intro_card_fingerprint({"default_payment_method": pm}))
    assert stripe.asked == asked and out == ("fp_1" if asked else None)


def test_a_fingerprint_lookup_failure_never_fails_the_webhook(monkeypatch):
    stripe = FingerprintStripe(exc=CappeStripeError("down"))
    monkeypatch.setattr(svc, "get_cappe_stripe", lambda: stripe)
    assert asyncio.run(svc._intro_card_fingerprint({"default_payment_method": "pm_1"})) is None


class IntroConn:
    def __init__(self, reused=0):
        self.reused, self.executed, self.depth, self.open = reused, [], 0, True

    def transaction(self):
        return Tx(self)

    async def execute(self, sql, *args):
        self.executed.append((sql, args))

    async def fetchval(self, sql, *args):
        return self.reused


def _checkout_completed(monkeypatch, caplog, *, intro, reused=0):
    conn = IntroConn(reused=reused)
    sub = {"id": "sub_1", "default_payment_method": "pm_1"}
    stripe = FingerprintStripe(sub=sub)

    async def _sync(_conn, **kwargs):
        return uuid4()

    monkeypatch.setattr(svc, "get_connection", lambda: GcCtx(conn))
    monkeypatch.setattr(svc, "get_cappe_stripe", lambda: stripe)
    monkeypatch.setattr(svc, "sync_subscription", _sync)
    session = {"metadata": {"account_id": str(ACCOUNT), "intro": "1" if intro else "0"},
               "subscription": "sub_1", "customer": None}
    with caplog.at_level(logging.WARNING, logger=svc.logger.name):
        out = asyncio.run(svc.handle_checkout_completed(session, None))
    assert out == {"status": "ok"}
    return conn, stripe, " ".join(r.getMessage() for r in caplog.records)


def test_an_intro_redemption_records_the_card_fingerprint(monkeypatch, caplog):
    conn, stripe, log = _checkout_completed(monkeypatch, caplog, intro=True)
    sql, args = next(e for e in conn.executed if "cappe_intro_redemptions" in e[0])
    assert "card_fingerprint" in sql and args == (ACCOUNT, "sub_1", "fp_1")
    # A retry must not blank a fingerprint already stored.
    assert "COALESCE(cappe_intro_redemptions.card_fingerprint" in sql
    assert "already used" not in log


def test_a_card_reused_across_accounts_is_reported_not_punished(monkeypatch, caplog):
    """The customer was shown "$1 for 30 days"; ending the trial after the fact
    would charge a price they never agreed to. Visible, not enforced."""
    _conn, _stripe, log = _checkout_completed(monkeypatch, caplog, intro=True, reused=2)
    assert "already used for the intro on 2 other account(s)" in log


def test_a_non_intro_checkout_reads_no_fingerprint_and_records_no_redemption(monkeypatch, caplog):
    conn, stripe, _log = _checkout_completed(monkeypatch, caplog, intro=False)
    assert stripe.asked == []
    assert not any("cappe_intro_redemptions" in e[0] for e in conn.executed)


# ── domain renewal emails ────────────────────────────────────────────────────

def _capture_send(monkeypatch):
    sent = []

    async def _send(to_email, to_name, subject, html, text, *, label, **_kw):
        sent.append({"to": to_email, "subject": subject, "html": html, "text": text, "label": label})
        return True

    monkeypatch.setattr(email_mod, "_send", _send)
    return sent


def test_the_renewal_problem_email_says_what_when_and_how_to_fix_it(monkeypatch):
    sent = _capture_send(monkeypatch)
    asyncio.run(email_mod.send_cappe_domain_renewal_problem_email(
        "owner@example.com", "Owner", "studio.example", "November 1, 2026",
        "the card on file was declined.", "https://gummfit.example/cappe/sites/s-1",
    ))
    mail = sent[0]
    assert mail["subject"] == "Action needed — renew studio.example"
    assert "November 1, 2026" in mail["text"] and "declined" in mail["text"]
    assert "https://gummfit.example/cappe/sites/s-1" in mail["text"]
    assert "Renew domain" in mail["html"]


def test_the_renewal_problem_email_escapes_what_it_interpolates(monkeypatch):
    sent = _capture_send(monkeypatch)
    asyncio.run(email_mod.send_cappe_domain_renewal_problem_email(
        "owner@example.com", None, "<b>x</b>.example", "Nov 1", "<script>", "https://example.com/x",
    ))
    assert "<script>" not in sent[0]["html"] and "<b>x</b>" not in sent[0]["html"]


def test_the_lapsed_email_says_the_site_is_still_up_at_its_own_address(monkeypatch):
    sent = _capture_send(monkeypatch)
    asyncio.run(email_mod.send_cappe_domain_lapsed_email(
        "owner@example.com", "Owner", "studio.example", "https://example.com/x",
    ))
    assert sent[0]["subject"] == "studio.example has expired"
    assert "still available at its gummfit address" in sent[0]["text"]


# ── every webhook path goes through the transaction wrapper ──────────────────

def _event_harness(monkeypatch, *, account_id=ACCOUNT):
    calls = []

    class LookupConn:
        open = True

        async def execute(self, sql, *args):
            calls.append(("execute", sql, args))

    async def _account(_conn, stripe_sub_id):
        return account_id

    async def _sync_tx(acct, subscription, *, event_at=None, after=None):
        calls.append(("sync", acct, subscription["id"]))
        if after is not None:
            await after(LookupConn())
        return uuid4()

    monkeypatch.setattr(svc, "get_connection", lambda: GcCtx(LookupConn()))
    monkeypatch.setattr(svc, "_account_for_subscription", _account)
    monkeypatch.setattr(svc, "sync_subscription_tx", _sync_tx)
    monkeypatch.setattr(svc, "get_cappe_stripe", lambda: FingerprintStripe(sub={"id": "sub_1"}))
    return calls


def test_a_subscription_event_is_synced_through_the_wrapper(monkeypatch):
    """So a duplicate found here is cancelled + refunded outside the transaction too."""
    calls = _event_harness(monkeypatch)
    out = asyncio.run(svc.handle_subscription_event({"id": "sub_1", "status": "active"}, None))
    assert out == {"status": "ok"}
    assert calls == [("sync", ACCOUNT, "sub_1")]


def test_a_subscription_event_for_another_product_is_ignored(monkeypatch):
    calls = _event_harness(monkeypatch, account_id=None)
    assert asyncio.run(svc.handle_subscription_event({"id": "sub_x"}, None)) == {"status": "ignored"}
    assert calls == []


def test_an_invoice_event_stamps_the_invoice_inside_the_same_transaction(monkeypatch):
    calls = _event_harness(monkeypatch)
    out = asyncio.run(svc.handle_invoice_event(
        {"id": "in_9", "subscription": "sub_1"}, paid=True, event_at=None,
    ))
    assert out == {"status": "ok"}
    assert calls[0] == ("sync", ACCOUNT, "sub_1")
    kind, sql, args = calls[1]
    assert kind == "execute" and "latest_invoice_id = $1" in sql and args == ("in_9", "sub_1")
