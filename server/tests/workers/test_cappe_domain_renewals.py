"""Cappe domain renewals — the charge names a card, a refusal is dunned not
punished on the spot, and nothing is skipped for ever.

The 2026-10 payments review found that the renewal charge passed only a Stripe
customer id (so it had nothing to charge and failed every time), that ANY
Stripe error past expiry expired the domain with no notice, and that domains
with no saved card or auto-renew off were skipped on every run and stayed
active past expiry indefinitely.

Run from server/:  ./venv/bin/python -m pytest tests/workers/test_cappe_domain_renewals.py -q
"""
import asyncio
import os

os.environ.setdefault("LIVE_API", "test-key")
os.environ.setdefault("DATABASE_URL", "postgresql://test:test@localhost/test")
os.environ.setdefault("JWT_SECRET_KEY", "test-secret-key-cappe")

import pytest  # noqa: E402

from app.cappe.services import email as email_mod  # noqa: E402
from app.cappe.services import stripe_connect as stripe_mod  # noqa: E402
from app.cappe.services.stripe_connect import CappeStripeCardError, CappeStripeError  # noqa: E402
from app.core.services import porkbun as porkbun_mod  # noqa: E402
from app.core.services.porkbun import PorkbunError  # noqa: E402
from app.workers.tasks import cappe_domain_renewals as mod  # noqa: E402


def _row(**over):
    row = {
        "id": "d-1", "domain": "studio.example", "site_id": "s-1", "retail_cents": 1600,
        "auto_renew": True, "stripe_customer_id": "cus_1", "stripe_payment_method_id": "pm_saved",
        "past_due": False, "past_grace": False, "recently_attempted": False, "notified": False,
        "expiry_key": "2026-11-01", "today_key": "20261020", "expires_on": "November 1, 2026",
        "account_email": "owner@example.com", "account_name": "Owner",
    }
    row.update(over)
    return row


# ── the plan for one domain (pure) ───────────────────────────────────────────

@pytest.mark.parametrize("over,plan", [
    ({}, "charge"),
    ({"past_due": True}, "charge"),                                   # still inside grace
    ({"recently_attempted": True}, "wait"),                           # dunning cadence
    ({"recently_attempted": True, "past_due": True}, "wait"),
    ({"recently_attempted": True, "past_due": True, "past_grace": True}, "lapse"),
    ({"past_due": True, "past_grace": True}, "charge"),               # one last try, then lapse
    ({"retail_cents": None}, "skip"),
    # Auto-renew off used to be skipped for ever and never lapsed.
    ({"auto_renew": False}, "remind"),
    ({"auto_renew": False, "past_due": True}, "lapse"),
])
def test_plan_for(over, plan):
    assert mod.plan_for(_row(**over)) == plan


# ── harness ──────────────────────────────────────────────────────────────────

class FakeConn:
    def __init__(self, rows=(), leaving=(), lapsed_transfers=()):
        self.rows, self.leaving, self.lapsed_transfers = list(rows), list(leaving), list(lapsed_transfers)
        self.executed, self.fetched = [], []

    async def fetch(self, sql, *args):
        self.fetched.append((sql, args))
        if "RETURNING domain, kind" in sql:
            return self.lapsed_transfers
        if "FROM cappe_domains d" in sql:
            return self.rows
        return self.leaving

    async def execute(self, sql, *args):
        self.executed.append((sql, args))

    async def close(self):
        pass

    def sql(self, needle):
        return [e for e in self.executed if needle in e[0]]


class FakeStripe:
    def __init__(self, charge_exc=None, saved="pm_listed", list_exc=None):
        self.charge_exc, self.saved, self.list_exc = charge_exc, saved, list_exc
        self.charges, self.lookups = [], []

    async def saved_card_for_customer(self, customer_id):
        self.lookups.append(customer_id)
        if self.list_exc:
            raise self.list_exc
        return self.saved

    async def charge_off_session(self, **kwargs):
        self.charges.append(kwargs)
        if self.charge_exc:
            raise self.charge_exc
        return {"id": "pi_renew"}


class FakePorkbun:
    def __init__(self, exc=None):
        self.exc, self.calls = exc, []

    async def set_auto_renew(self, domain, enabled):
        self.calls.append((domain, enabled))
        if self.exc:
            raise self.exc


def _patch(monkeypatch, conn, stripe=None, porkbun=None, *, enabled=True):
    stripe, porkbun = stripe or FakeStripe(), porkbun or FakePorkbun()
    emails = []

    async def _get_conn():
        return conn

    async def _enabled(_conn, key, default=False):
        return enabled

    async def _problem(to, name, domain, expires_on, reason, link):
        emails.append(("problem", domain, reason))

    async def _lapsed(to, name, domain, link):
        emails.append(("lapsed", domain))

    monkeypatch.setattr(mod, "get_db_connection", _get_conn)
    monkeypatch.setattr(mod, "scheduler_enabled", _enabled)
    monkeypatch.setattr(stripe_mod, "get_cappe_stripe", lambda: stripe)
    monkeypatch.setattr(porkbun_mod, "get_porkbun", lambda: porkbun)
    monkeypatch.setattr(email_mod, "send_cappe_domain_renewal_problem_email", _problem)
    monkeypatch.setattr(email_mod, "send_cappe_domain_lapsed_email", _lapsed)
    return stripe, porkbun, emails


def _run():
    return asyncio.run(mod._dispatch_cappe_domain_renewals())


# ── the charge ───────────────────────────────────────────────────────────────

def test_the_renewal_charges_the_saved_card_by_id(monkeypatch):
    """Passing only the customer id gave Stripe nothing to charge."""
    conn = FakeConn([_row()])
    stripe, porkbun, emails = _patch(monkeypatch, conn)
    out = _run()
    assert out["renewed"] == 1 and out["failed"] == 0 and out["lapsed"] == 0
    charge = stripe.charges[0]
    assert charge["customer_id"] == "cus_1" and charge["payment_method_id"] == "pm_saved"
    assert charge["amount_cents"] == 1600
    assert charge["metadata"] == {"type": "cappe_domain_renewal", "domain_id": "d-1"}
    # Same day → same key (an hourly restart replays); a later day retries.
    assert charge["idempotency_key"] == "cappe-renew-d-1-2026-11-01-20261020"
    renewed = conn.sql("+ INTERVAL '1 year'")[0]
    assert "renewal_failed_at = NULL" in renewed[0] and "renewal_notified_at = NULL" in renewed[0]
    assert renewed[1] == ("d-1", "pm_saved")
    assert emails == [] and porkbun.calls == []


def test_a_row_from_before_the_card_was_stored_falls_back_to_the_customers_card(monkeypatch):
    conn = FakeConn([_row(stripe_payment_method_id=None)])
    stripe, _pb, _emails = _patch(monkeypatch, conn)
    assert _run()["renewed"] == 1
    assert stripe.lookups == ["cus_1"]
    assert stripe.charges[0]["payment_method_id"] == "pm_listed"
    # … and the card found is stored for next time.
    assert conn.sql("+ INTERVAL '1 year'")[0][1] == ("d-1", "pm_listed")


# ── a refused card: dun, do not punish ───────────────────────────────────────

def test_a_declined_card_before_expiry_is_recorded_and_the_tenant_is_told(monkeypatch):
    conn = FakeConn([_row()])
    stripe = FakeStripe(charge_exc=CappeStripeCardError("declined", code="card_declined"))
    _stripe, porkbun, emails = _patch(monkeypatch, conn, stripe)
    out = _run()
    assert out == {"renewed": 0, "failed": 1, "lapsed": 0, "reminded": 0, "errors": 0}
    failure = conn.sql("renewal_failed_at = COALESCE(renewal_failed_at, NOW())")[0]
    assert "renewal_attempted_at = NOW()" in failure[0] and failure[1] == ("d-1", mod.REASON_DECLINED)
    assert emails == [("problem", "studio.example", mod.REASON_DECLINED)]
    assert conn.sql("renewal_notified_at = NOW()")
    # Still active, registrar untouched.
    assert conn.sql("status = 'expired'") == [] and porkbun.calls == []


def test_the_tenant_is_told_once_per_cycle_not_on_every_retry(monkeypatch):
    conn = FakeConn([_row(notified=True)])
    stripe = FakeStripe(charge_exc=CappeStripeCardError("declined"))
    _s, _p, emails = _patch(monkeypatch, conn, stripe)
    _run()
    assert emails == []
    assert conn.sql("renewal_notified_at = NOW()") == []


def test_a_recently_refused_card_is_not_hammered(monkeypatch):
    conn = FakeConn([_row(recently_attempted=True, past_due=True)])
    stripe, _p, emails = _patch(monkeypatch, conn)
    out = _run()
    assert stripe.charges == [] and emails == []
    assert out["failed"] == 0 and out["lapsed"] == 0


def test_a_past_due_domain_inside_grace_keeps_serving(monkeypatch):
    conn = FakeConn([_row(past_due=True)])
    stripe = FakeStripe(charge_exc=CappeStripeCardError("declined"))
    _s, porkbun, _e = _patch(monkeypatch, conn, stripe)
    assert _run()["lapsed"] == 0
    assert conn.sql("status = 'expired'") == [] and porkbun.calls == []


def test_a_card_still_refused_after_grace_lapses_the_domain_with_notice(monkeypatch):
    conn = FakeConn([_row(past_due=True, past_grace=True, notified=True)])
    stripe = FakeStripe(charge_exc=CappeStripeCardError("declined"))
    _s, porkbun, emails = _patch(monkeypatch, conn, stripe)
    out = _run()
    assert out["failed"] == 1 and out["lapsed"] == 1
    expired = conn.sql("status = 'expired'")[0]
    assert "WHERE id = $1 AND status = 'active'" in expired[0]
    assert porkbun.calls == [("studio.example", False)]      # stop paying the registrar
    assert emails == [("lapsed", "studio.example")]


def test_no_card_on_file_is_a_refusal_not_a_silent_skip(monkeypatch):
    """`continue` used to leave this domain active for ever."""
    conn = FakeConn([_row(stripe_customer_id=None, stripe_payment_method_id=None)])
    stripe, _p, emails = _patch(monkeypatch, conn)
    out = _run()
    assert out["failed"] == 1 and stripe.charges == []
    assert conn.sql("renewal_failed_at")[0][1] == ("d-1", mod.REASON_NO_CARD)
    assert emails == [("problem", "studio.example", mod.REASON_NO_CARD)]


def test_a_customer_with_no_saved_card_at_all_is_also_a_refusal(monkeypatch):
    conn = FakeConn([_row(stripe_payment_method_id=None)])
    stripe = FakeStripe(saved=None)
    _s, _p, emails = _patch(monkeypatch, conn, stripe)
    assert _run()["failed"] == 1
    assert stripe.charges == [] and emails[0][2] == mod.REASON_NO_CARD


# ── an outage is ours, not the tenant's ──────────────────────────────────────

@pytest.mark.parametrize("stripe", [
    FakeStripe(charge_exc=CappeStripeError("api down")),
    FakeStripe(list_exc=CappeStripeError("api down")),
])
def test_a_stripe_outage_past_expiry_changes_nothing_and_blames_nobody(monkeypatch, stripe):
    """Any Stripe error past expiry used to expire the domain and switch the
    registrar's auto-renew off."""
    conn = FakeConn([_row(past_due=True, past_grace=True, stripe_payment_method_id=None)])
    _s, porkbun, emails = _patch(monkeypatch, conn, stripe)
    out = _run()
    assert out["errors"] == 1 and out["failed"] == 0 and out["lapsed"] == 0
    assert conn.executed == []                    # no failure recorded, not expired
    assert porkbun.calls == [] and emails == []


# ── auto-renew off, and rows with nothing to charge ──────────────────────────

def test_auto_renew_off_is_reminded_once_and_the_registrar_is_stopped(monkeypatch):
    conn = FakeConn([_row(auto_renew=False)])
    stripe, porkbun, emails = _patch(monkeypatch, conn)
    out = _run()
    assert out["reminded"] == 1 and stripe.charges == []
    assert porkbun.calls == [("studio.example", False)]
    assert emails == [("problem", "studio.example", mod.REASON_AUTO_RENEW_OFF)]


def test_auto_renew_off_already_reminded_is_left_quiet(monkeypatch):
    conn = FakeConn([_row(auto_renew=False, notified=True)])
    _s, porkbun, emails = _patch(monkeypatch, conn)
    assert _run()["reminded"] == 0
    assert porkbun.calls == [] and emails == []


def test_auto_renew_off_lapses_at_expiry_instead_of_staying_active_for_ever(monkeypatch):
    conn = FakeConn([_row(auto_renew=False, past_due=True)])
    _s, porkbun, emails = _patch(monkeypatch, conn)
    assert _run()["lapsed"] == 1
    assert conn.sql("status = 'expired'") and emails == [("lapsed", "studio.example")]


def test_a_row_with_no_price_is_reported_and_left_alone(monkeypatch):
    conn = FakeConn([_row(retail_cents=None)])
    stripe, _p, _e = _patch(monkeypatch, conn)
    out = _run()
    assert stripe.charges == [] and conn.executed == []
    assert out["renewed"] == 0


# ── resilience ───────────────────────────────────────────────────────────────

def test_one_domain_blowing_up_does_not_stop_the_rest(monkeypatch):
    conn = FakeConn([_row(id="d-bad", domain="bad.example"), _row(id="d-2", domain="ok.example")])
    stripe, _p, _e = _patch(monkeypatch, conn)
    real = stripe.charge_off_session

    async def _charge(**kwargs):
        if kwargs["metadata"]["domain_id"] == "d-bad":
            raise RuntimeError("unexpected")
        return await real(**kwargs)

    stripe.charge_off_session = _charge
    out = _run()
    assert out["errors"] == 1 and out["renewed"] == 1


def test_email_failures_never_stop_the_sweep(monkeypatch):
    conn = FakeConn([_row(auto_renew=False, past_due=True)])
    _patch(monkeypatch, conn)

    async def _boom(*_a):
        raise RuntimeError("smtp down")

    monkeypatch.setattr(email_mod, "send_cappe_domain_lapsed_email", _boom)
    assert _run()["lapsed"] == 1                   # still lapsed


def test_a_failed_renewal_notice_is_not_marked_as_sent(monkeypatch):
    conn = FakeConn([_row(auto_renew=False)])
    _patch(monkeypatch, conn)

    async def _boom(*_a):
        raise RuntimeError("smtp down")

    monkeypatch.setattr(email_mod, "send_cappe_domain_renewal_problem_email", _boom)
    _run()
    assert conn.sql("renewal_notified_at = NOW()") == []      # so it is retried


def test_a_registrar_error_while_lapsing_is_tolerated(monkeypatch):
    conn = FakeConn([_row(auto_renew=False, past_due=True)])
    _patch(monkeypatch, conn, porkbun=FakePorkbun(exc=PorkbunError("down")))
    assert _run()["lapsed"] == 1


def test_a_registrar_error_while_reminding_is_tolerated(monkeypatch):
    conn = FakeConn([_row(auto_renew=False)])
    _s, _p, emails = _patch(monkeypatch, conn, porkbun=FakePorkbun(exc=PorkbunError("down")))
    assert _run()["reminded"] == 1 and len(emails) == 1


def test_an_account_with_no_email_is_not_notified(monkeypatch):
    conn = FakeConn([_row(auto_renew=False, account_email=None)])
    _s, _p, emails = _patch(monkeypatch, conn)
    _run()
    assert emails == []


# ── the sweep itself ─────────────────────────────────────────────────────────

def test_the_sweep_sees_every_active_registered_domain_in_the_window(monkeypatch):
    conn = FakeConn([])
    _patch(monkeypatch, conn)
    assert _run() == {"renewed": 0, "failed": 0, "lapsed": 0}
    sql, args = next(f for f in conn.fetched if "FROM cappe_domains d" in f[0])
    assert "d.kind = 'register' AND d.status = 'active'" in sql
    assert "auto_renew\n" not in sql.split("WHERE", 1)[1]      # no `AND auto_renew` filter
    assert args == (str(mod._RENEW_WINDOW_DAYS), str(mod._LAPSE_GRACE_DAYS), str(mod._RETRY_EVERY_DAYS))


def test_transfer_requests_still_stop_registrar_billing_and_lapse_at_expiry(monkeypatch):
    conn = FakeConn(
        [], leaving=[{"domain": "leaving.example"}],
        lapsed_transfers=[{"domain": "gone.example", "kind": "register"}],
    )
    _s, porkbun, _e = _patch(monkeypatch, conn)
    assert _run() == {"renewed": 0, "failed": 0, "lapsed": 1}
    assert porkbun.calls == [("gone.example", False), ("leaving.example", False)]


def test_a_registrar_error_on_a_leaving_domain_is_tolerated(monkeypatch):
    conn = FakeConn([], leaving=[{"domain": "leaving.example"}])
    _patch(monkeypatch, conn, porkbun=FakePorkbun(exc=PorkbunError("down")))
    assert _run()["lapsed"] == 0


def test_a_disabled_scheduler_does_nothing(monkeypatch):
    conn = FakeConn([_row()])
    stripe, _p, _e = _patch(monkeypatch, conn, enabled=False)
    assert _run() == {"renewed": 0, "skipped": True}
    assert stripe.charges == [] and conn.fetched == []
